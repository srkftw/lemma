// SPDX-License-Identifier: Apache-2.0
// Host-only digital oscillator phase. It supplies RTL clock edges, never bytes.
#pragma once
#include <cstdint>
#include <stdexcept>
namespace lemma {
struct UsbClockDomain {
 static constexpr uint32_t half_period_numerator=25000000;
 int32_t ppm=0;
 uint32_t initial_phase_quanta=0,residue=0;
 bool level=false;
 static UsbClockDomain cold(int32_t rate_ppm,uint32_t phase_quanta){
  if(rate_ppm < -2500 || rate_ppm > 2500 || phase_quanta>=50)
   throw std::runtime_error("USB clock rate/initial phase outside declared bound");
  UsbClockDomain d;d.ppm=rate_ppm;d.initial_phase_quanta=phase_quanta;
  uint64_t phase=uint64_t(phase_quanta)*uint32_t(1000000+rate_ppm);
  d.level=(phase/half_period_numerator)&1;d.residue=phase%half_period_numerator;return d;
 }
 uint32_t rate()const{
  if(ppm < -2500 || ppm > 2500 || initial_phase_quanta>=50 || residue>=half_period_numerator)
   throw std::runtime_error("invalid USB clock logical state");
  return uint32_t(1000000+ppm);
 }
 uint32_t next_edge()const{auto r=rate();return (half_period_numerator-residue+r-1)/r;}
 bool advance(uint32_t quanta){
  auto r=rate();if(!quanta||quanta>next_edge())throw std::runtime_error("USB clock interval would skip an edge");
  uint32_t next=residue+quanta*r;
  bool edge=next>=half_period_numerator;
  if(edge){next-=half_period_numerator;level=!level;}residue=next;return edge;
 }
 void validate_boundary(uint64_t cycles)const{
  auto r=rate();
  // Reduce before multiplication, so even the declared64-bit cycle boundary
  // cannot overflow. One100MHz period is24 common2.4GHz quanta.
  uint64_t phase=((cycles%50000000)*24+initial_phase_quanta)*r%50000000;
  if(residue!=phase%half_period_numerator||level!=bool(phase/half_period_numerator))
   throw std::runtime_error("USB clock state differs from declared origin/boundary");
 }
};
}
