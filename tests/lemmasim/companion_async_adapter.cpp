#include "../../sim/companion/backing_c.h"
#include "../../sim/host/backing_io.h"
#include <array>
#include <cassert>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <unistd.h>
#include <vector>

int main(int argc,char **argv) {
 assert(argc==7);char error[256];
 void *owner=lemma_backing_create_async(-1,argv[1],argv[2],argv[3],argv[4],argv[5],argv[6],std::string(64,'b').c_str(),error,sizeof error);
 if(!owner){std::cerr<<error;return 1;}
 std::array<uint8_t,512> bytes;bytes.fill(0x83);
 assert(!lemma_backing_submit(owner,1,17,512,512,bytes.data(),error,sizeof error));
 LemmaBackingState state;assert(!lemma_backing_get_state(owner,&state));
 assert(state.phase==1&&!state.poisoned&&!state.completed&&state.next_id==2);
 assert(lemma_backing_capture_checkpoint(owner,error,sizeof error)<0);
 LemmaBackingOutcome result{};
 for(unsigned n=0;!lemma_backing_retry_ready(owner);++n) {
  assert(n<8000);assert(lemma_backing_poll(owner,23,bytes.data(),&result,error,sizeof error)==1);usleep(1000);
 }
 assert(!lemma_backing_get_state(owner,&state));assert(state.phase==1&&!state.poisoned&&!state.completed);
 std::cout<<"PENDING_NO_SUCCESS"<<std::endl;
 std::string command;std::getline(std::cin,command);assert(command=="retry");
 assert(!lemma_backing_retry(owner,error,sizeof error));
 int status=1;
 for(unsigned n=0;status==1;++n){assert(n<8000);status=lemma_backing_poll(owner,41,bytes.data(),&result,error,sizeof error);usleep(1000);}
 assert(!status&&result.transferred==512&&!result.error);
 assert(!lemma_backing_get_state(owner,&state));assert(state.phase==2&&state.completed==1&&state.observed_write==1&&!state.durable_barrier);
 assert(!lemma_backing_submit(owner,2,50,0,0,nullptr,error,sizeof error));status=1;
 for(unsigned n=0;status==1;++n){assert(n<8000);status=lemma_backing_poll(owner,51,nullptr,&result,error,sizeof error);usleep(1000);}
 assert(!status&&!result.error&&!result.transferred);
 assert(!lemma_backing_capture_checkpoint(owner,error,sizeof error));lemma_backing_destroy(owner);
 std::ifstream stream(argv[6],std::ios::binary);std::vector<uint8_t> wire((std::istreambuf_iterator<char>(stream)),{});
 assert(wire.size()>=72&&!std::memcmp(wire.data(),"LMIOLOG2",8));size_t position=72;
 auto get=[&](){assert(position+8<=wire.size());uint64_t v=0;for(unsigned i=0;i<8;++i)v|=uint64_t(wire[position++])<<(8*i);return v;};
 for(unsigned i=0;i<4;++i){auto tag=get(),size=get();assert(tag==i%2&&position+size<=wire.size());
  if(!tag){auto q=lemma::decode_backing_request(wire.data()+position,size);assert(q.id==i/2+1);}
  else {auto q=lemma::decode_timed_backing_record(wire.data()+position,size);assert(q.record.request.id==i/2+1&&q.accepted_boundary==(i==1?41:51));}
  position+=size;
 }
 assert(position==wire.size());std::cout<<"PASS same-ID actual completion after independent peer restart"<<std::endl;
}
