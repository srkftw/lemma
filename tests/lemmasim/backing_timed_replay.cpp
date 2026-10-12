#include "../../sim/companion/backing_c.h"
#include <array>
#include <cassert>
#include <cerrno>
#include <csignal>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <string>
#include <sys/resource.h>
#include <unistd.h>
#include <vector>

int main(int argc,char **argv) {
 assert(argc==2);const std::string root=argv[1],identity(64,'c');char error[256];
 auto open_medium=[&](const std::string& path){int fd=open(path.c_str(),O_RDWR|O_CREAT|O_EXCL,0600);assert(fd>=0);assert(!ftruncate(fd,268435456));return fd;};
 int fd=open_medium(root+"/original");
 auto live=lemma_backing_create_async(fd,nullptr,nullptr,nullptr,nullptr,nullptr,(root+"/actual.io").c_str(),identity.c_str(),error,sizeof error);assert(live);
 std::array<uint8_t,8> bytes{1,2,3,4,5,6,7,8};LemmaBackingOutcome result{};
 struct rlimit saved,limited;assert(!getrlimit(RLIMIT_FSIZE,&saved));limited=saved;limited.rlim_cur=8192;
 std::signal(SIGXFSZ,SIG_IGN);assert(!setrlimit(RLIMIT_FSIZE,&limited));
 assert(!lemma_backing_submit(live,1,20,8190,8,bytes.data(),error,sizeof error));
 assert(!setrlimit(RLIMIT_FSIZE,&saved));
 assert(!lemma_backing_poll(live,25,nullptr,&result,error,sizeof error));assert(result.transferred==2&&result.error==EFBIG);
 close(fd);
 assert(!lemma_backing_submit(live,2,30,0,0,nullptr,error,sizeof error));
 assert(!lemma_backing_poll(live,30,nullptr,&result,error,sizeof error));assert(!result.transferred&&result.error==EBADF);
 assert(!lemma_backing_capture_checkpoint(live,error,sizeof error));lemma_backing_destroy(live);
 assert(!unlink((root+"/original").c_str())); // No original backing exists during replay.
 fd=open_medium(root+"/private");
 auto replay=lemma_backing_create_async(fd,nullptr,nullptr,nullptr,nullptr,nullptr,(root+"/replayed.io").c_str(),identity.c_str(),error,sizeof error);assert(replay);
 assert(lemma_backing_attach_replay(replay,(root+"/actual.io").c_str(),identity.c_str(),0,error,sizeof error)<0);
 assert(lemma_backing_attach_replay(replay,(root+"/actual.io").c_str(),std::string(64,'d').c_str(),1,error,sizeof error)<0);
 LemmaBackingState state{};assert(!lemma_backing_get_state(replay,&state));assert(state.next_id==1&&!state.poisoned);
 assert(!lemma_backing_attach_replay(replay,(root+"/actual.io").c_str(),identity.c_str(),1,error,sizeof error));
 assert(!lemma_backing_submit(replay,1,20,8190,8,bytes.data(),error,sizeof error));
 assert(lemma_backing_poll(replay,24,nullptr,&result,error,sizeof error)==1);
 uint8_t observed[8];assert(pread(fd,observed,8,8190)==8);assert(observed[0]==0);
 assert(lemma_backing_capture_checkpoint(replay,error,sizeof error)<0);
 assert(!lemma_backing_poll(replay,25,nullptr,&result,error,sizeof error));assert(result.transferred==2&&result.error==EFBIG);
 assert(pread(fd,observed,8,8190)==8);assert(observed[0]==1&&observed[1]==2&&observed[2]==0);
 assert(!lemma_backing_submit(replay,2,30,0,0,nullptr,error,sizeof error));
 assert(!lemma_backing_poll(replay,30,nullptr,&result,error,sizeof error));assert(result.error==EBADF);
 assert(!lemma_backing_get_state(replay,&state));assert(state.next_id==3&&state.completed==2&&state.observed_write==1&&!state.durable_barrier);
 auto outside=state;outside.next_id=4;outside.completed=3;
 assert(lemma_backing_set_state(replay,&outside,error,sizeof error)<0);
 LemmaBackingState unchanged{};assert(!lemma_backing_get_state(replay,&unchanged));
 assert(!std::memcmp(&state,&unchanged,sizeof state));
 assert(!lemma_backing_capture_checkpoint(replay,error,sizeof error));lemma_backing_destroy(replay);close(fd);
 auto read=[](const std::string& path){std::ifstream s(path,std::ios::binary);return std::vector<uint8_t>((std::istreambuf_iterator<char>(s)),{});};
 auto actual=read(root+"/actual.io");assert(actual==read(root+"/replayed.io"));
 // Validation is transactional: a corrupted complete log does not poison or
 // advance an otherwise usable live owner.
 auto corrupt=actual;corrupt.back()^=1;std::ofstream c(root+"/corrupt.io",std::ios::binary);c.write(reinterpret_cast<char*>(corrupt.data()),corrupt.size());c.close();
 fd=open_medium(root+"/negative");replay=lemma_backing_create_async(fd,nullptr,nullptr,nullptr,nullptr,nullptr,nullptr,nullptr,error,sizeof error);assert(replay);
 assert(lemma_backing_attach_replay(replay,(root+"/corrupt.io").c_str(),identity.c_str(),1,error,sizeof error)<0);
 assert(!lemma_backing_get_state(replay,&state));assert(state.next_id==1&&!state.poisoned);
 assert(!lemma_backing_attach_replay(replay,(root+"/actual.io").c_str(),identity.c_str(),1,error,sizeof error));
 bytes[0]^=1;assert(lemma_backing_submit(replay,1,20,8190,8,bytes.data(),error,sizeof error)<0);
 assert(!lemma_backing_get_state(replay,&state));assert(state.poisoned);
 lemma_backing_destroy(replay);close(fd);
 fd=open_medium(root+"/missed");replay=lemma_backing_create_async(fd,nullptr,nullptr,nullptr,nullptr,nullptr,nullptr,nullptr,error,sizeof error);assert(replay);
 assert(!lemma_backing_attach_replay(replay,(root+"/actual.io").c_str(),identity.c_str(),1,error,sizeof error));bytes[0]^=1;
 assert(!lemma_backing_submit(replay,1,20,8190,8,bytes.data(),error,sizeof error));
 assert(lemma_backing_poll(replay,26,nullptr,&result,error,sizeof error)<0);
 assert(pread(fd,observed,8,8190)==8&&observed[0]==0);lemma_backing_destroy(replay);close(fd);
 std::cout<<"PASS exact timed actual partial pwrite/EFBIG and failed fsync replay; private medium, corruption, request and timing rejection\n";
}
