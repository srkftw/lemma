// SPDX-License-Identifier: Apache-2.0
// Host-only real syscall/signal regression, independent file-byte oracle.
#include "../../sim/host/backing_io.h"
#include "../../sim/host/backing_io_posix.h"
#include <array>
#include <cassert>
#include <cerrno>
#include <csignal>
#include <fcntl.h>
#include <iostream>
#include <pthread.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>
using namespace lemma;
static void child(int fd,bool pending) {
 struct sigaction disposition{};disposition.sa_handler=SIG_DFL;
 assert(!sigemptyset(&disposition.sa_mask));assert(!sigaction(SIGXFSZ,&disposition,nullptr));
 sigset_t one,previous;assert(!sigemptyset(&one));assert(!sigaddset(&one,SIGXFSZ));
 assert(!pthread_sigmask(pending?SIG_BLOCK:SIG_UNBLOCK,&one,&previous));
 if(pending)assert(!raise(SIGXFSZ));
 struct rlimit limit{};assert(!getrlimit(RLIMIT_FSIZE,&limit));limit.rlim_cur=640;
 assert(!setrlimit(RLIMIT_FSIZE,&limit));
 BackingState state;std::array<uint8_t,512>bytes{};bytes.fill(0x5a);
 auto request=begin_backing(state,BackingKind::Write,73,512,512,bytes.data());
 PosixBacking io(fd);BackingRecord record{request,io.execute(request)};
 assert(record.outcome.transferred==128 && record.outcome.error==EFBIG);
 complete_backing(state,record);assert(state.observed_write==1 && state.durable_barrier==0);
 auto encoded=encode_backing_record(record);auto decoded=decode_backing_record(encoded.data(),encoded.size());
 assert(decoded.outcome.error==EFBIG && decoded.outcome.bytes==std::vector<uint8_t>(128,0x5a));
 sigset_t after,held;assert(!pthread_sigmask(SIG_BLOCK,nullptr,&after));assert(!sigpending(&held));
 assert(sigismember(&after,SIGXFSZ)==(pending?1:0));
 assert(sigismember(&held,SIGXFSZ)==(pending?1:0));
 struct sigaction actual{};assert(!sigaction(SIGXFSZ,nullptr,&actual));assert(actual.sa_handler==SIG_DFL);
 std::array<uint8_t,512>observed{};assert(pread(fd,observed.data(),512,512)==512);
 for(size_t i=0;i<512;i++)assert(observed[i]==(i<128?0x5a:0));
 _exit(0);
}
int main(int argc,char**argv) {
 assert(argc==2);
 for(bool pending:{false,true}) {
  auto name=std::string(argv[1])+(pending?"/pending.raw":"/default.raw");
  int fd=open(name.c_str(),O_RDWR|O_CREAT|O_EXCL,0600);assert(fd>=0 && !ftruncate(fd,1024));
  auto pid=fork();assert(pid>=0);if(!pid)child(fd,pending);
  int status=0;assert(waitpid(pid,&status,0)==pid);
  if(!WIFEXITED(status)||WEXITSTATUS(status)!=0) {
   std::cerr<<"FAIL actual backing child pending="<<pending<<" wait_status="<<status
            <<" signal="<<(WIFSIGNALED(status)?WTERMSIG(status):0)<<"\n";close(fd);return 1;
  }
  close(fd);
 }
 std::cout<<"PASS actual default-SIGXFSZ partial pwrite/EFBIG capture; unchanged signal policy and prior pending signal\n";
}

