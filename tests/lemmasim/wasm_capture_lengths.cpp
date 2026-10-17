// SPDX-License-Identifier: Apache-2.0
// Host-only 32-bit portable backing API regression; never linked into RV64.
#include "../../sim/companion/backing_c.h"
#include "../../sim/host/backing_io.h"
#include <array>
#include <cassert>
#include <cerrno>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

static uint64_t word(const std::array<uint8_t,8>& bytes) {
  uint64_t value=0;
  for(unsigned i=0;i<8;++i)value|=uint64_t(bytes[i])<<(8*i);
  return value;
}
static std::array<uint8_t,8> length(std::ifstream& input,uint64_t expected) {
  std::array<uint8_t,8> bytes{};
  input.read(reinterpret_cast<char*>(bytes.data()),bytes.size());assert(input.good());
  // Independently require the whole wire length, including all four high
  // bytes. Reading only uint32_t would hide the original undefined shifts.
  assert(word(bytes)==expected);
  for(unsigned i=4;i<8;++i)assert(bytes[i]==0);
  return bytes;
}
static void exercise(bool asynchronous) {
  const std::string base=asynchronous?"/case/async":"/case/sync";
  int fd=open((base+".raw").c_str(),O_RDWR|O_CREAT|O_EXCL,0600);assert(fd>=0);
  assert(ftruncate(fd,268435456)==0);
  const std::string identity(64,'a');char error[256]{};
  auto create=asynchronous?lemma_backing_create_async:lemma_backing_create;
  auto owner=create(fd,nullptr,nullptr,nullptr,nullptr,nullptr,
                    (base+".io").c_str(),identity.c_str(),error,sizeof error);
  assert(owner);
  std::array<uint8_t,512> bytes{};
  for(unsigned i=0;i<512;++i)bytes[i]=(i*29+7)&255;
  const auto expected=bytes;
  auto operation=[&](uint64_t kind,uint64_t cycle) {
    LemmaBackingOutcome result{};
    if(asynchronous) {
      assert(!lemma_backing_submit(owner,kind,cycle,kind==2?0:512,
          kind==2?0:512,kind==1?bytes.data():nullptr,error,sizeof error));
      assert(!lemma_backing_poll(owner,cycle+13,bytes.data(),&result,error,sizeof error));
    } else assert(!lemma_backing_execute(owner,kind,cycle,kind==2?0:512,
        kind==2?0:512,bytes.data(),&result,error,sizeof error));
    assert(result.error==0 && result.transferred==(kind==2?0:512));
  };
  operation(1,101);operation(2,202);bytes.fill(0);operation(0,303);assert(bytes==expected);
  assert(!lemma_backing_capture_checkpoint(owner,error,sizeof error));
  LemmaBackingState state{};assert(!lemma_backing_get_state(owner,&state));
  assert(state.next_id==4 && state.completed==3 && state.durable_barrier==2 && state.observed_write==1);
  lemma_backing_destroy(owner);close(fd);
  std::ifstream input(base+".io",std::ios::binary);std::string header(72,'\0');
  input.read(header.data(),header.size());assert(header==(asynchronous?"LMIOLOG2":"LMIOLOG1")+identity);
  const unsigned kinds[]={1,2,0};
  for(unsigned id=1;id<=3;++id) {
    unsigned kind=kinds[id-1],requested=kind==1?512:0,returned=kind==2?0:512;
    if(asynchronous) {
      length(input,0);length(input,48+requested);
      std::vector<uint8_t> submit(48+requested);input.read(reinterpret_cast<char*>(submit.data()),submit.size());
      auto request=lemma::decode_backing_request(submit.data(),submit.size());
      assert(request.id==id && uint64_t(request.kind)==kind && request.boundary==id*101);
      length(input,1);length(input,80+requested+returned);
      std::vector<uint8_t> complete(80+requested+returned);input.read(reinterpret_cast<char*>(complete.data()),complete.size());
      auto outcome=lemma::decode_timed_backing_record(complete.data(),complete.size());
      assert(outcome.record.request.id==id && outcome.accepted_boundary==id*101+13);
    } else {
      length(input,64+requested+returned);
      std::vector<uint8_t> raw(64+requested+returned);input.read(reinterpret_cast<char*>(raw.data()),raw.size());
      auto record=lemma::decode_backing_record(raw.data(),raw.size());
      assert(record.request.id==id && record.outcome.transferred==returned && !record.outcome.error);
    }
  }
  assert(input.peek()==EOF);
}
int main() {
  static_assert(sizeof(size_t)==4,"This regression must execute the 32-bit Wasm ABI");
  assert(mkdir("/case",0700)==0);exercise(false);exercise(true);
  std::cout<<"PASS actual32-bit backing WRITE/barrier/READ captures; full64-bit lengths and CRCs\n";
}
