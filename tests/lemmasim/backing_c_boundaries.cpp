#include "../../sim/companion/backing_c.h"
#include "../../sim/host/backing_io.h"
#include <array>
#include <cassert>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <string>
#include <unistd.h>

int main(int argc,char **argv) {
  assert(argc==2);std::string dir=argv[1],medium=dir+"/medium",capture=dir+"/capture";
  int fd=open(medium.c_str(),O_RDWR|O_CREAT|O_EXCL,0600);assert(fd>=0);
  assert(ftruncate(fd,268435456)==0);char error[256]{};
  auto owner=lemma_backing_create(fd,nullptr,nullptr,nullptr,nullptr,nullptr,capture.c_str(),
    std::string(64,'a').c_str(),error,sizeof error);assert(owner);
  std::array<uint8_t,512>bytes{};bytes.fill(0x93);LemmaBackingOutcome outcome;
  assert(!lemma_backing_execute(owner,1,400,512,bytes.size(),bytes.data(),&outcome,error,sizeof error));
  assert(outcome.transferred==512 && !outcome.error);
  assert(!lemma_backing_execute(owner,2,500,0,0,nullptr,&outcome,error,sizeof error));
  LemmaBackingState state{};assert(!lemma_backing_get_state(owner,&state));
  assert(state.next_id==3 && state.completed==2 && state.durable_barrier==2 && state.observed_write==1);
  auto invalid=state;invalid.phase=1;
  assert(lemma_backing_set_state(owner,&invalid,error,sizeof error)==-1);
  LemmaBackingState after{};assert(!lemma_backing_get_state(owner,&after));
  assert(!memcmp(&after,&state,sizeof state));
  std::array<uint8_t,512>observed{};
  assert(!lemma_backing_passive(owner,512,512,observed.data(),error,sizeof error));assert(observed==bytes);
  assert(!lemma_backing_export(owner,(dir+"/export").c_str(),error,sizeof error));
  assert(lemma_backing_export(owner,(dir+"/export").c_str(),error,sizeof error)==-1);
  assert(!lemma_backing_get_state(owner,&after));assert(!memcmp(&after,&state,sizeof state));
  // Actual OS error is an accepted outcome, while the capture itself stays open.
  close(fd);
  assert(!lemma_backing_execute(owner,0,600,512,512,observed.data(),&outcome,error,sizeof error));
  assert(!outcome.transferred && outcome.error==EBADF);
  assert(!lemma_backing_execute(owner,2,700,0,0,nullptr,&outcome,error,sizeof error));
  assert(outcome.error==EBADF);
  assert(!lemma_backing_capture_checkpoint(owner,error,sizeof error));
  assert(!lemma_backing_get_state(owner,&after));assert(after.completed==4 && after.durable_barrier==2 && !after.poisoned);
  lemma_backing_destroy(owner);
  std::ifstream input(capture,std::ios::binary);
  std::string header(72,'\0');input.read(header.data(),header.size());assert(header=="LMIOLOG1"+std::string(64,'a'));
  for(uint64_t id=1;id<=4;++id) {
    uint8_t size[8];input.read(reinterpret_cast<char*>(size),8);uint64_t n=0;for(unsigned i=0;i<8;++i)n|=uint64_t(size[i])<<(i*8);
    std::vector<uint8_t>raw(n);input.read(reinterpret_cast<char*>(raw.data()),raw.size());assert(input.good());
    auto record=lemma::decode_backing_record(raw.data(),raw.size());assert(record.request.id==id);
    assert(record.request.boundary==300+id*100);assert(record.outcome.error==(id>=3?EBADF:0));
  }
  assert(input.peek()==EOF);std::cout<<"PASS actual EBADF capture, observational export, rejected pending restore\n";
}
