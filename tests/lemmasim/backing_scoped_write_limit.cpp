// SPDX-License-Identifier: Apache-2.0
// Host boundary test: real OS calls, independent file reads and process policy.
#include "../../sim/host/backing_io_posix.h"
#include <atomic>
#include <cassert>
#include <cerrno>
#include <csignal>
#include <fcntl.h>
#include <iostream>
#include <sys/resource.h>
#include <thread>
#include <unistd.h>
using namespace lemma;
int main(int argc,char**argv){
 assert(argc==2);std::string root=argv[1];
 int fd=open((root+"/medium").c_str(),O_CREAT|O_EXCL|O_RDWR,0600);
 int log=open((root+"/capture").c_str(),O_CREAT|O_EXCL|O_RDWR,0600);
 int fork=open((root+"/fork").c_str(),O_CREAT|O_EXCL|O_RDWR,0600);
 assert(fd>=0&&log>=0&&fork>=0&&ftruncate(fd,2048)==0&&ftruncate(fork,2048)==0);
 assert(signal(SIGXFSZ,SIG_DFL)!=SIG_ERR);
 rlimit before{},after{};assert(getrlimit(RLIMIT_FSIZE,&before)==0);
 PosixBacking platform(fd);platform.limit_write_span(512,1024,768);
 BackingRequest request{1,123,512,512,BackingKind::Write,std::vector<uint8_t>(512,0xa5)};
 auto result=platform.execute(request);
 assert(result.transferred==256&&result.error==EFBIG&&result.bytes==std::vector<uint8_t>(256,0xa5));
 assert(getrlimit(RLIMIT_FSIZE,&after)==0&&before.rlim_cur==after.rlim_cur&&before.rlim_max==after.rlim_max);
 struct sigaction action{};assert(sigaction(SIGXFSZ,nullptr,&action)==0&&action.sa_handler==SIG_DFL);
 std::vector<uint8_t> actual(2048),expected(2048);
 std::fill(expected.begin()+512,expected.begin()+768,0xa5);
 assert(pread(fd,actual.data(),actual.size(),0)==2048&&actual==expected);
 // An unrelated backing write and the outcome log exceed the fault ceiling.
 auto other=request;other.id=2;other.offset=1024;other.bytes.assign(512,0x39);
 auto succeeded=platform.execute(other);assert(!succeeded.error&&succeeded.transferred==512);
 auto encoded=encode_backing_record({request,result});
 std::vector<uint8_t> logging(8192,0x6d);
 assert(write(log,logging.data(),logging.size())==8192&&fsync(log)==0);
 assert(write(log,encoded.data(),encoded.size())==ssize_t(encoded.size()));
 auto decoded=decode_backing_record(encoded.data(),encoded.size());
 PosixBacking private_store(fork);private_store.limit_write_span(0,2048,0);
 private_store.apply_recorded(decoded.request,decoded.outcome);
 assert(pread(fork,actual.data(),actual.size(),0)==2048&&actual==expected);
 BackingRequest barrier{3,125,0,0,BackingKind::Barrier,{}};
 auto receipt=platform.execute(barrier);assert(!receipt.error);
 private_store.apply_recorded(barrier,receipt);
 // A process-wide policy cannot safely scope one write with another thread.
 std::atomic<bool> ready{false},done{false};
 std::thread worker([&]{ready=true;while(!done.load())std::this_thread::yield();});
 while(!ready.load())std::this_thread::yield();
 bool rejected=false;try{platform.execute(request);}catch(const std::runtime_error&){rejected=true;}
 done=true;worker.join();assert(rejected);
 assert(getrlimit(RLIMIT_FSIZE,&after)==0&&before.rlim_cur==after.rlim_cur&&before.rlim_max==after.rlim_max);
 std::fill(expected.begin()+1024,expected.begin()+1536,0x39);
 assert(pread(fd,actual.data(),actual.size(),0)==2048&&actual==expected);
 assert(close(fd)==0&&close(log)==0&&close(fork)==0);
 std::cout<<"PASS actual scoped partial pwrite/EFBIG, unaffected logs, isolated replay, multithread rejection\n";
}
