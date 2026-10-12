// SPDX-License-Identifier: Apache-2.0
// Literal controller-output staging plus real RV64 pipeline continuation.
// This does not synthesize guest ink or qualify a panel/Ready workload.
#include "machine_runtime.h"
#include <cassert>
#include <map>
#include <iostream>
using namespace lemma;
Options options(const std::string&d,const std::string&n){Options o;o.quiet_uart=true;o.deadline=30;o.uart_path=d+"/"+n+".uart";o.fork_directory=d;return o;}
void compare(const PanelPending& actual,const std::map<uint64_t,uint8_t>& expected){
 assert(actual.size()==expected.size());auto p=expected.begin();
 actual.each([&](uint64_t i,uint8_t v){assert(p!=expected.end()&&i==p->first&&v==p->second);++p;});assert(p==expected.end());
}
int main(int argc,char**argv){assert(argc==7);std::string dir=argv[1];
 Machine live(options(dir,"live"));live.load_elf(argv[2]);live.load_rom(argv[3]);
 auto dtb=bytes(argv[4]);live.put(number(argv[6]),dtb.data(),dtb.size());live.descriptor(argv[5]);live.run(20000);
 auto& state=const_cast<State&>(live.state());std::map<uint64_t,uint8_t> expected;
 for(uint64_t i=0;i<1650ULL*2200;i+=71){state.optical_pending[i]=uint8_t(i&15);expected[i]=i&15;}
 state.optical_pending[1650ULL*2200-1]=7;expected[1650ULL*2200-1]=7;
 compare(state.optical_pending,expected);auto cycles=state.cycle,retired=state.retired;
 live.snapshot(dir+"/pending.snap");assert(state.cycle==cycles&&state.retired==retired);compare(state.optical_pending,expected);
 Machine fork(options(dir,"fork"));fork.restore(dir+"/pending.snap");compare(fork.state().optical_pending,expected);
 fork.snapshot(dir+"/restored.snap");assert(bytes(dir+"/pending.snap")==bytes(dir+"/restored.snap"));
 auto suffix=[&](Machine&m){auto&s=const_cast<State&>(m.state());s.optical_pending[0]=9;s.optical_pending[64]=4;m.run(40000);m.snapshot(dir+"/"+(m.state().isolated?"fork-complete":"live-complete")+".snap");};
 suffix(live);suffix(fork);expected[0]=9;expected[64]=4;compare(live.state().optical_pending,expected);compare(fork.state().optical_pending,expected);
 assert(bytes(dir+"/live-complete.snap")==bytes(dir+"/fork-complete.snap"));
 assert(live.state().retired>retired);live.warm_reset(8);fork.warm_reset(8);assert(live.state().optical_pending.empty()&&fork.state().optical_pending.empty());
 live.run(17);fork.run(17);live.snapshot(dir+"/live-reset.snap");fork.snapshot(dir+"/fork-reset.snap");assert(bytes(dir+"/live-reset.snap")==bytes(dir+"/fork-reset.snap"));
 std::cout<<"PASS literal staged pixels observational snapshot/ordered restore/overwrite/reset and real RV64 exact suffix; no controller/Ready claim\n";
}
