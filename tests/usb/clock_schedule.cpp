// SPDX-License-Identifier: Apache-2.0
#include "../../sim/host/usb_clock.h"
#include <algorithm>
#include <iostream>
#include <stdexcept>
using lemma::UsbClockDomain;
static void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
static bool equal(const UsbClockDomain&a,const UsbClockDomain&b){return a.ppm==b.ppm&&a.initial_phase_quanta==b.initial_phase_quanta&&a.residue==b.residue&&a.level==b.level;}
int main(){try{
 uint64_t edges=0;
 for(int ppm:{-2500,-1,0,1,2500})for(unsigned phase=0;phase<50;phase++){
  auto d=UsbClockDomain::cold(ppm,phase);d.validate_boundary(0);uint64_t ticks=0;
  for(uint64_t cycle=1;cycle<=10000;cycle++){
   uint32_t left=24;
   while(left){uint32_t step=std::min(left,d.next_edge());bool changed=d.advance(step);ticks+=step;left-=step;
    uint64_t reference=(ticks+phase)*uint64_t(1000000+ppm);
    need(d.level==bool((reference/25000000)&1)&&d.residue==reference%25000000,"independent oscillator reference differs");edges+=changed;}
   d.validate_boundary(cycle);
  }
  auto original=d;
  try{d.advance(1000);throw std::runtime_error("accepted skipped edge");}catch(const std::runtime_error&e){need(std::string(e.what())!="accepted skipped edge","skip rejected");}
  need(equal(d,original),"invalid advance changed oscillator");
  d.residue=(d.residue+1)%25000000;bool rejected=false;try{d.validate_boundary(10000);}catch(const std::runtime_error&){rejected=true;}need(rejected,"corrupt fractional phase accepted");
 }
 for(auto [ppm,phase]:{std::pair<int,unsigned>{-2501,0},{2501,0},{0,50}}){bool rejected=false;try{UsbClockDomain::cold(ppm,phase);}catch(const std::runtime_error&){rejected=true;}need(rejected,"invalid static oscillator input accepted");}
 std::cout<<"USB_CLOCK_SCHEDULE_PASS250ratephases10000periods independentfractionalphase corruptskipinvalidinputs edges="<<edges<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
