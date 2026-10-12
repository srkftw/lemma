// SPDX-License-Identifier: Apache-2.0
// Host-only independent effects oracle for the external byte-I/O boundary.
#include "backing_io.h"
#include "backing_io_posix.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cerrno>
#include <csignal>
#include <fcntl.h>
#include <iostream>
#include <stdexcept>
#include <sys/resource.h>
#include <unistd.h>
using namespace lemma;
template<class F>void rejects(F f){bool rejected=false;try{f();}catch(const std::runtime_error&){rejected=true;}assert(rejected);}
int main(int argc,char**argv){
 assert(argc==2);std::string root=argv[1];int fd=open((root+"/original.raw").c_str(),O_RDWR|O_CREAT|O_EXCL,0600);assert(fd>=0);assert(!ftruncate(fd,1024));
 PosixBacking live(fd);BackingState state;std::array<uint8_t,512>payload{};for(size_t i=0;i<payload.size();i++)payload[i]=i*37+11;
 auto write_request=begin_backing(state,BackingKind::Write,100,512,512,payload.data());
 assert(state.phase==BackingPhase::Pending);rejects([&](){begin_backing(state,BackingKind::Read,100,0,512);});
 // A real buffered pwrite returns a partial prefix at RLIMIT_FSIZE, followed
 // by an actual EFBIG. The file existed before the resource limit was set.
 struct rlimit previous{};assert(!getrlimit(RLIMIT_FSIZE,&previous));struct rlimit limit=previous;limit.rlim_cur=640;assert(!setrlimit(RLIMIT_FSIZE,&limit));signal(SIGXFSZ,SIG_IGN);
 BackingRecord partial{write_request,live.execute(write_request)};assert(!setrlimit(RLIMIT_FSIZE,&previous));
 assert(partial.outcome.transferred==128&&partial.outcome.error==EFBIG);complete_backing(state,partial);
 std::array<uint8_t,512>actual{};assert(pread(fd,actual.data(),actual.size(),512)==512);
 assert(std::equal(actual.begin(),actual.begin()+128,payload.begin()));assert(std::all_of(actual.begin()+128,actual.end(),[](uint8_t v){return !v;}));
 assert(state.observed_write==1&&state.durable_barrier==0);
 auto wire=encode_backing_record(partial);auto decoded=decode_backing_record(wire.data(),wire.size());assert(equal_backing_request(partial.request,decoded.request)&&partial.outcome.bytes==decoded.outcome.bytes);
 wire.back()^=1;rejects([&](){decode_backing_record(wire.data(),wire.size());});rejects([&](){decode_backing_record(wire.data(),wire.size()-1);});
 // Actual pread/fsync EBADF errors are distinct recorded operations; failed
 // sync cannot move the acknowledged barrier or roll back the earlier prefix.
 PosixBacking invalid(-1);auto read_request=begin_backing(state,BackingKind::Read,101,0,512);BackingRecord read_failure{read_request,invalid.execute(read_request)};assert(read_failure.outcome.error==EBADF&&!read_failure.outcome.transferred);complete_backing(state,read_failure);
 auto barrier_request=begin_backing(state,BackingKind::Barrier,102,0,0);BackingRecord barrier_failure{barrier_request,invalid.execute(barrier_request)};assert(barrier_failure.outcome.error==EBADF);complete_backing(state,barrier_failure);assert(!state.durable_barrier);
 // The original descriptor is closed before replay. An independent fork
 // receives exactly the captured changed prefix and never consults live.
 close(fd);int fork=open((root+"/fork.raw").c_str(),O_RDWR|O_CREAT|O_EXCL,0600);assert(fork>=0&&!ftruncate(fork,1024));PosixBacking isolated(fork);BackingState replay;
 auto again=begin_backing(replay,BackingKind::Write,100,512,512,payload.data());assert(equal_backing_request(again,partial.request));isolated.apply_recorded(again,partial.outcome);complete_backing(replay,partial);
 again=begin_backing(replay,BackingKind::Read,101,0,512);assert(equal_backing_request(again,read_failure.request));isolated.apply_recorded(again,read_failure.outcome);complete_backing(replay,read_failure);
 again=begin_backing(replay,BackingKind::Barrier,102,0,0);isolated.apply_recorded(again,barrier_failure.outcome);complete_backing(replay,barrier_failure);assert(!replay.durable_barrier);
 std::array<uint8_t,512>replayed{};isolated.passive_read(512,replayed.data(),512);assert(actual==replayed&&replay.next_id==state.next_id&&replay.completed==state.completed);
 auto successful=begin_backing(replay,BackingKind::Barrier,103,0,0);BackingRecord acknowledged{successful,isolated.execute(successful)};assert(!acknowledged.outcome.error);complete_backing(replay,acknowledged);assert(replay.durable_barrier==4);
 auto cancelled=begin_backing(replay,BackingKind::Read,104,0,512);cancel_backing(replay,cancelled);rejects([&](){complete_backing(replay,{cancelled,{512,0,std::vector<uint8_t>(512)}});});
 replay.poisoned=true;rejects([&](){begin_backing(replay,BackingKind::Barrier,105,0,0);});
 close(fork);std::cout<<"actual partial pwrite/EFBIG, pread/fsync EBADF, retained failed effects, isolated recorded replay, acknowledgement/cancellation/poison and record corruption PASS\n";
}
