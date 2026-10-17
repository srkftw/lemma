// SPDX-License-Identifier: Apache-2.0
// Literal initialized watchdog/controller state in the real reusable Machine.
// Genuine driver-issued watchdog writes are qualified separately.
#include "machine_runtime.h"
#include "Vlemma_soc___024root.h"
#include <algorithm>
#include <cassert>
#include <iostream>
using namespace lemma;
Options options(const std::string&d,const std::string&n){Options o;o.quiet_uart=true;o.deadline=30;o.memory_latency=1024;o.uart_path=d+"/"+n+".uart";o.fork_directory=d;return o;}
int main(int argc,char**argv){assert(argc==7);std::string dir=argv[1];
 auto load=[&](Machine&m){m.load_elf(argv[2]);m.load_rom(argv[3]);auto dtb=bytes(argv[4]);m.put(number(argv[6]),dtb.data(),dtb.size());m.descriptor(argv[5]);};
 Machine m(options(dir,"live"));load(m);m.run(8);auto&s=const_cast<State&>(m.state());
 s.ram[0x3000100]=0x55;s.overlay[7].fill(0x66);s.visible[0]=2;s.optical_pending[0]=1;
 m.soc().power_watchdog_timeout=32;m.soc().power_watchdog_remaining=32;m.soc().power_watchdog_armed=1;
 auto retired=s.retired;m.run(15);assert(m.soc().power_watchdog_remaining==17&&!m.soc().power_domain_reset);
 m.snapshot(dir+"/watchdog.snap");m.run(26);assert(m.soc().power_cause==4&&!m.soc().power_domain_reset&&s.retired==retired);
 assert(m.soc().rootp->lemma_soc__DOT__pen__DOT__loss&&m.soc().rootp->lemma_soc__DOT__pen__DOT__resync);
 assert(s.ram[0x3000100]==0x55&&s.overlay.at(7)[0]==0x66&&s.visible[0]==2&&s.optical_pending.empty());m.snapshot(dir+"/watchdog-complete.snap");
 Machine fork(options(dir,"watchdog-fork"));fork.restore(dir+"/watchdog.snap");fork.run(26);fork.snapshot(dir+"/watchdog-replay.snap");assert(bytes(dir+"/watchdog-complete.snap")==bytes(dir+"/watchdog-replay.snap"));
 auto cycle=s.cycle;m.schedule({cycle,"pgood",{0},{}});m.schedule({cycle+4,"pen",{1,12000,33000,2048,1,0,0},{}});m.schedule({cycle+6,"pgood",{1},{}});m.run(2);
 assert(m.soc().power_cause==6&&m.soc().power_domain_reset&&s.ram[0x3000100]==0&&s.overlay.empty()&&s.visible[0]==2);
 m.snapshot(dir+"/loss.snap");m.run(14);assert(!m.soc().power_domain_reset&&m.soc().power_reset_epoch==2&&s.pen_accepted==0&&s.samples.empty());m.snapshot(dir+"/loss-complete.snap");
 Machine loss_fork(options(dir,"loss-fork"));loss_fork.restore(dir+"/loss.snap");loss_fork.run(14);loss_fork.snapshot(dir+"/loss-replay.snap");assert(bytes(dir+"/loss-complete.snap")==bytes(dir+"/loss-replay.snap"));
 cycle=s.cycle;m.schedule({cycle,"brownout",{1},{}});m.run(2);assert(m.soc().power_cause==5&&m.soc().power_domain_reset);
 assert(!m.soc().mem_valid&&!m.soc().media_valid&&!m.soc().fb_valid&&!m.soc().panel_valid&&!m.soc().panel_drive_valid);
 std::cout<<"PASS real machine watchdog while CPU memory-stalled, actual RAM/overlay loss, optical retention, blocked DMA/controller traffic and exact reset-edge checkpoint suffixes\n";
}
