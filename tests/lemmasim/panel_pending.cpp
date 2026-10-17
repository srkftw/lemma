// SPDX-License-Identifier: Apache-2.0
// Independent ordered-map oracle for the host-only controller pixel staging.
#include "../../sim/host/panel_pending.h"
#include <cassert>
#include <chrono>
#include <iostream>
#include <map>
#include <string>

uint64_t checksum=0;
void consume(uint64_t i,uint8_t v){checksum=checksum*1099511628211ULL+(i^v);}
int main(int argc,char**argv){
 constexpr uint64_t capacity=1650ULL*2200;
 const std::string mode=argc>1?argv[1]:"property";
 const auto start=std::chrono::steady_clock::now();
 if(mode=="property"){
  lemma::PanelPending actual(capacity);std::map<uint64_t,uint8_t> reference;
  uint64_t seed=0x6729171319;
  for(uint64_t n=0;n<100000;n++){
   seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;
   auto i=seed%capacity;auto v=uint8_t((seed>>40)&15);
   actual.put(i,v);reference[i]=v;
   if(n%1009==0){actual.put(i,uint8_t(v^15));reference[i]=v^15;}
  }
  auto compare=[&](const lemma::PanelPending& value){
   assert(value.size()==reference.size());auto p=reference.begin();
   value.each([&](uint64_t i,uint8_t v){assert(p!=reference.end()&&p->first==i&&p->second==v);++p;});
   assert(p==reference.end());
  };
  compare(actual);auto copied=actual;actual.clear();assert(actual.empty());compare(copied);
  actual.put(capacity-1,15);actual.put(0,0);actual.put(63,3);actual.put(64,4);
  reference={{0,0},{63,3},{64,4},{capacity-1,15}};compare(actual);
  for(auto i:{capacity,UINT64_MAX}){bool reject=false;try{actual.put(i,0);}catch(const std::runtime_error&){reject=true;}assert(reject);}
  bool reject=false;try{actual.put(0,16);}catch(const std::runtime_error&){reject=true;}assert(reject);compare(actual);
  std::cout<<"PASS ordered sparse/overwrite/clear/copy/edge/rejection; host staging only\n";
 }else if(mode=="indexed"){
  lemma::PanelPending actual(capacity);
  for(uint64_t i=0;i<capacity;i++)actual.put(i,uint8_t(i&15));
  for(uint64_t i=0;i<capacity;i+=97)actual.put(i,uint8_t((i+7)&15));
  actual.each(consume);std::cout<<"storage_bytes="<<actual.storage_bytes()<<" ";actual.clear();assert(actual.empty());
 }else if(mode=="map"){
  std::map<uint64_t,uint8_t> actual;
  for(uint64_t i=0;i<capacity;i++)actual[i]=uint8_t(i&15);
  for(uint64_t i=0;i<capacity;i+=97)actual[i]=uint8_t((i+7)&15);
  for(auto [i,v]:actual){consume(i,v);}
  actual.clear();assert(actual.empty());
 }else return 2;
 std::cout<<"checksum="<<checksum<<" host_seconds="<<std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()<<"\n";
}
