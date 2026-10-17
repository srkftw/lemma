// SPDX-License-Identifier: Apache-2.0
// Real raw supply/reset edges. No initialized guest/controller success state.
// UART at reset release survives the pen-only loss handshake; pen is canceled.
#include "machine_runtime.h"
#include <cassert>
#include <iostream>
using namespace lemma;
int main(int argc,char**argv){
 assert(argc==2);Options o;o.quiet_uart=true;o.uart_path=std::string(argv[1])+"/uart.bin";o.fork_directory=argv[1];
 Machine m(o);m.run(8);m.schedule({m.state().cycle,"brownout",{1},{}});m.run(16);
 assert(m.soc().power_domain_reset&&m.soc().power_cause==5);
 m.schedule({m.state().cycle,"brownout",{0},{}});m.run(8);
 assert(!m.soc().power_domain_reset&&m.soc().power_cancel_pen);
 const auto release=m.state().cycle;
 m.schedule({release,"uart",{},"52"});
 m.schedule({release+16,"uart",{},"53"});
 m.schedule({release+20,"pen",{0,123,456,2048,3,1,0},{}});
 m.run(32);
 assert(m.state().rx.size()==2&&m.state().rx[0]==0x52&&m.state().rx[1]==0x53);
 assert(m.state().event_payload_bytes==4);
 assert(m.state().samples.empty());
 for(size_t i=m.state().event_index;i<m.state().input.size();i++)assert(m.state().input[i].kind!="pen");
 assert(!m.soc().power_domain_reset);
 const std::string dir=argv[1];
 m.snapshot(dir+"/retained.snap");
 Options fork_options;fork_options.quiet_uart=true;fork_options.uart_path=dir+"/fork.uart";fork_options.fork_directory=dir;
 Machine fork(fork_options);fork.restore(dir+"/retained.snap");
 assert(fork.state().event_payload_bytes==m.state().event_payload_bytes);
 for(Machine*machine:{&m,&fork}){
  machine->schedule({release+64,"uart",{},"54"});
  assert(machine->state().event_payload_bytes==2);
  machine->run(64);
  assert(machine->state().rx.size()==3&&machine->state().rx[2]==0x54);
 }
 m.snapshot(dir+"/original-suffix.snap");fork.snapshot(dir+"/fork-suffix.snap");
 assert(bytes(dir+"/original-suffix.snap")==bytes(dir+"/fork-suffix.snap"));
 std::cout<<"PASS raw brownout exact8 release pen cancellation retains current/future UART recovery bytes and quota; observational snapshot exact suffix\n";
}
