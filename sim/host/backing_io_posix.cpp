// SPDX-License-Identifier: Apache-2.0
#include "backing_io_posix.h"
#include <cerrno>
#include <limits>
#include <stdexcept>
#include <sys/stat.h>
#include <unistd.h>
namespace lemma {
uint64_t PosixBacking::capacity()const{struct stat st{};if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size<0)throw std::runtime_error("backing must be a regular file");return st.st_size;}
void PosixBacking::passive_read(uint64_t offset,uint8_t*b,uint64_t length)const{
 if(offset>uint64_t(std::numeric_limits<off_t>::max())-length)throw std::runtime_error("passive backing read offset overflow");
 uint64_t done=0;while(done<length){ssize_t n=pread(fd,b+done,length-done,offset+done);if(n<=0)throw std::runtime_error("passive backing read failed");done+=n;}
}
BackingOutcome PosixBacking::execute(const BackingRequest&r){
 validate_backing_request(r);BackingOutcome o;
 if(r.offset>uint64_t(std::numeric_limits<off_t>::max())-r.length){o.error=EOVERFLOW;return o;}
 if(r.kind==BackingKind::Barrier){if(fsync(fd))o.error=errno;return o;}
 std::vector<uint8_t>b(r.length);if(r.kind==BackingKind::Write)b=r.bytes;
 while(o.transferred<r.length){
  ssize_t n=r.kind==BackingKind::Read?pread(fd,b.data()+o.transferred,r.length-o.transferred,r.offset+o.transferred):pwrite(fd,b.data()+o.transferred,r.length-o.transferred,r.offset+o.transferred);
  // EINTR has no known byte effect; bounded failure is captured rather than
  // an unbounded host retry that changes the selected virtual boundary.
  if(n<=0){o.error=n<0?errno:EIO;break;}o.transferred+=n;
 }
 o.bytes.assign(b.begin(),b.begin()+o.transferred);return o;
}
void PosixBacking::apply_recorded(const BackingRequest&r,const BackingOutcome&o){
 validate_backing_record({r,o});
 if(r.kind==BackingKind::Write&&o.transferred){BackingRequest prefix=r;prefix.length=o.transferred;prefix.bytes=o.bytes;auto actual=execute(prefix);if(actual.error)throw std::runtime_error("private replay backing write failed");}
 // Fork barriers must themselves succeed even when the original returned an
 // error. Recorded success/error remains the sole guest-visible outcome.
 if(r.kind==BackingKind::Barrier){auto actual=execute(r);if(actual.error)throw std::runtime_error("private replay backing barrier failed");}
}
}
