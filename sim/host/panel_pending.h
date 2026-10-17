// SPDX-License-Identifier: Apache-2.0
// Host-only controller-output staging. No ink, waveform or guest policy.
#pragma once
#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace lemma {
class PanelPending {
 std::vector<uint8_t> pixels;
 std::vector<uint64_t> present;
 uint64_t count=0;
 static uint64_t bounded(uint64_t capacity) {
  if(capacity>1650ULL*2200)throw std::runtime_error("panel staging exceeds admitted geometry");
  return capacity;
 }
public:
 explicit PanelPending(uint64_t capacity=0):pixels(bounded(capacity)),present((capacity+63)/64) {}
 void configure(uint64_t capacity) {
  if(count)throw std::runtime_error("cannot resize in-flight panel state");
  *this=PanelPending(capacity);
 }
 uint64_t size()const{return count;}
 bool empty()const{return count==0;}
 uint64_t storage_bytes()const{return pixels.size()+8*present.size();}
 struct Slot {
  PanelPending& owner;uint64_t index;
  void operator=(uint8_t value){owner.put(index,value);}
 };
 Slot operator[](uint64_t index){return {*this,index};}
 void put(uint64_t index,uint8_t value) {
  if(index>=pixels.size()||value>15)throw std::runtime_error("invalid staged controller pixel");
  const auto mask=uint64_t(1)<<(index&63);
  auto &word=present[index>>6];
  if(!(word&mask)){word|=mask;count++;}
  pixels[index]=value;
 }
 void clear(){std::fill(present.begin(),present.end(),0);count=0;}
 // Ascending indices retain the existing logical map wire encoding. Values
 // without a presence bit are acceleration-only storage and never observed.
 template<class Function> void each(Function consume)const {
  for(uint64_t group=0;group<present.size();group++) {
   uint64_t bits=present[group];
   while(bits) {
    const auto index=group*64+unsigned(__builtin_ctzll(bits));
    consume(index,pixels[index]);bits&=bits-1;
   }
  }
 }
};
}
