// SPDX-License-Identifier: Apache-2.0
#include "backing_io_posix.h"
#include <algorithm>
#include <cerrno>
#include <limits>
#include <stdexcept>
#include <sys/stat.h>
#include <unistd.h>
#ifndef __EMSCRIPTEN__
#include <csignal>
#include <pthread.h>
#include <time.h>
#endif
#if defined(__linux__) && !defined(__EMSCRIPTEN__)
#include <dirent.h>
#include <sys/resource.h>
#endif
namespace lemma {
namespace {
// A process-wide limit must never leak into a second thread or the outcome
// logger. Only the actual synchronous selected backing operation is scoped.
class ScopedWriteLimit {
#if defined(__linux__) && !defined(__EMSCRIPTEN__)
 rlimit previous{};
 bool active=false;
#endif
public:
 explicit ScopedWriteLimit(uint64_t ceiling){
#if defined(__linux__) && !defined(__EMSCRIPTEN__)
  DIR*tasks=opendir("/proc/self/task");
  if(!tasks)throw std::runtime_error("cannot inspect scoped backing owner threads");
  unsigned count=0;while(auto*row=readdir(tasks))if(row->d_name[0]!='.')++count;
  closedir(tasks);
  if(count!=1)throw std::runtime_error("scoped backing write limit requires one owner thread");
  if(getrlimit(RLIMIT_FSIZE,&previous))throw std::runtime_error("cannot read backing write limit");
  rlimit selected=previous;
  if(selected.rlim_cur==RLIM_INFINITY||ceiling<selected.rlim_cur)selected.rlim_cur=ceiling;
  if(setrlimit(RLIMIT_FSIZE,&selected))throw std::runtime_error("cannot apply backing write limit");
  active=true;
#else
  (void)ceiling;
  throw std::runtime_error("scoped backing write limit requires Linux native execution");
#endif
 }
 ScopedWriteLimit(const ScopedWriteLimit&)=delete;
 ScopedWriteLimit&operator=(const ScopedWriteLimit&)=delete;
 ~ScopedWriteLimit(){
#if defined(__linux__) && !defined(__EMSCRIPTEN__)
  // Continuing with a leaked process policy could lose capture or UART data.
  // Fail the host before returning an uncaptured result to the machine.
  if(active&&setrlimit(RLIMIT_FSIZE,&previous))std::terminate();
#endif
 }
};
// RLIMIT_FSIZE can deliver SIGXFSZ as well as returning EFBIG. Keep that
// synchronous write failure observable without installing a process-wide
// handler or changing another thread's signal policy. An already pending
// signal belongs to the caller and must remain pending.
ssize_t captured_pwrite(int fd,const void*bytes,size_t count,off_t offset){
#ifdef __EMSCRIPTEN__
 return pwrite(fd,bytes,count,offset);
#else
 sigset_t selected,previous,pending;
 sigemptyset(&selected);sigaddset(&selected,SIGXFSZ);
 if(pthread_sigmask(SIG_BLOCK,&selected,&previous))
  throw std::runtime_error("cannot guard backing file-limit signal");
 if(sigpending(&pending)){
  pthread_sigmask(SIG_SETMASK,&previous,nullptr);
  throw std::runtime_error("cannot inspect backing file-limit signal");
 }
 const bool inherited=sigismember(&pending,SIGXFSZ)==1;
 const ssize_t transferred=pwrite(fd,bytes,count,offset);
 const int failure=errno;
 if(transferred<0&&failure==EFBIG&&!inherited){
  const timespec immediate{};int result;unsigned interrupted=0;
  do{result=sigtimedwait(&selected,nullptr,&immediate);}
  while(result<0&&errno==EINTR&&++interrupted<16);
  // Ignored signals need not become pending. Repeated unrelated signal
  // interference is a host failure: the owner poisons an ambiguous operation.
  if(result!=SIGXFSZ&&!(result<0&&errno==EAGAIN)){
   pthread_sigmask(SIG_SETMASK,&previous,nullptr);
   throw std::runtime_error("cannot consume backing file-limit signal");
  }
 }
 if(pthread_sigmask(SIG_SETMASK,&previous,nullptr))
  throw std::runtime_error("cannot restore backing signal mask");
 errno=failure;return transferred;
#endif
}
}
uint64_t PosixBacking::capacity()const{struct stat st{};if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size<0)throw std::runtime_error("backing must be a regular file");return st.st_size;}
void PosixBacking::limit_write_span(uint64_t first,uint64_t past,uint64_t ceiling){
 const auto bytes=capacity();
 if(first>=past||past>bytes||ceiling>bytes)throw std::runtime_error("invalid scoped backing write range");
 write_limit=WriteLimit{first,past,ceiling};
}
void PosixBacking::passive_read(uint64_t offset,uint8_t*b,uint64_t length)const{
 if(offset>uint64_t(std::numeric_limits<off_t>::max())-length)throw std::runtime_error("passive backing read offset overflow");
 uint64_t done=0;while(done<length){ssize_t n=pread(fd,b+done,length-done,offset+done);if(n<=0)throw std::runtime_error("passive backing read failed");done+=n;}
}
BackingOutcome PosixBacking::execute(const BackingRequest&r){
 validate_backing_request(r);BackingOutcome o;
 if(r.offset>uint64_t(std::numeric_limits<off_t>::max())-r.length){o.error=EOVERFLOW;return o;}
 if(r.kind==BackingKind::Barrier){if(fsync(fd))o.error=errno;return o;}
 std::vector<uint8_t>b(r.length);if(r.kind==BackingKind::Write)b=r.bytes;
 std::vector<uint8_t> before;
 if(r.kind==BackingKind::Write){
  before.resize(r.length);uint64_t at=0;
  while(at<r.length){auto n=pread(fd,before.data()+at,r.length-at,r.offset+at);
   // A failed preflight precedes any write, so its empty effect is known.
   if(n<=0){o.error=n<0?errno:EIO;return o;}at+=n;
  }
 }
 {
 std::optional<ScopedWriteLimit> limit;
 if(r.kind==BackingKind::Write&&write_limit&&r.offset<write_limit->past&&
    write_limit->first<r.offset+r.length)limit.emplace(write_limit->ceiling);
 while(o.transferred<r.length){
  ssize_t n=r.kind==BackingKind::Read?pread(fd,b.data()+o.transferred,r.length-o.transferred,r.offset+o.transferred):captured_pwrite(fd,b.data()+o.transferred,r.length-o.transferred,r.offset+o.transferred);
  // EINTR has no known byte effect; bounded failure is captured rather than
  // an unbounded host retry that changes the selected virtual boundary.
  if(n<=0){o.error=n<0?errno:EIO;break;}o.transferred+=n;
 }
 } // Restore the real process limit before returning any captured outcome.
 if(r.kind==BackingKind::Write){
  std::vector<uint8_t> observed(r.length);
  passive_read(r.offset,observed.data(),r.length);
  std::copy_n(b.begin(),o.transferred,before.begin());
  // An error need not roll back or faithfully report every changed byte.
  // Capture only an independently observed known prefix. Unknown effects
  // poison the owner before a guest completion, rather than invent rollback.
  if(observed!=before)throw std::runtime_error("backing write has unrepresented byte effects");
 }
 o.bytes.assign(b.begin(),b.begin()+o.transferred);return o;
}
void PosixBacking::apply_recorded(const BackingRequest&r,const BackingOutcome&o){
 validate_backing_record({r,o});
 PosixBacking private_replay(fd); // Recorded effects never reuse live fault configuration.
 if(r.kind==BackingKind::Write&&o.transferred){BackingRequest prefix=r;prefix.length=o.transferred;prefix.bytes=o.bytes;auto actual=private_replay.execute(prefix);if(actual.error)throw std::runtime_error("private replay backing write failed");}
 // Fork barriers must themselves succeed even when the original returned an
 // error. Recorded success/error remains the sole guest-visible outcome.
 if(r.kind==BackingKind::Barrier){auto actual=private_replay.execute(r);if(actual.error)throw std::runtime_error("private replay backing barrier failed");}
}
}
