// SPDX-License-Identifier: Apache-2.0
// Host property driver: every USB packet and guest MMIO operation is executed
// by the maintained RTL and genuine audited RV64 Wire initializer.
// The host reads generated phases; it never changes them or fabricates packets.
#include "machine_runtime.h"
#include "Vlemma_soc___024root.h"
#include <cassert>
#include <chrono>
#include <fstream>
#include <iostream>
#include <sstream>
#include <sys/resource.h>
using namespace lemma;
#ifndef USB_CLOCKED_TEST
#define USB_CLOCKED_TEST 0
#endif
#if USB_CLOCKED_TEST
#define HOST_PHY(field) r->lemma_soc__DOT__packet_usb__DOT__full_speed_wire__DOT__independent_clocks__DOT__host_phy__DOT__transceiver__DOT__##field
#define CHIP_PHY(field) r->lemma_soc__DOT__packet_usb__DOT__full_speed_wire__DOT__independent_clocks__DOT__chip_phy__DOT__transceiver__DOT__##field
#else
#define HOST_PHY(field) r->lemma_soc__DOT__packet_usb__DOT__full_speed_wire__DOT__host_phy__DOT__##field
#define CHIP_PHY(field) r->lemma_soc__DOT__packet_usb__DOT__full_speed_wire__DOT__chip_phy__DOT__##field
#endif
#undef assert
#define assert(value) ((value)?void(0):throw std::runtime_error("property failed: " #value))
static Options options(const std::string&dir,const std::string&label){Options o;o.quiet_uart=true;o.uart_path=dir+"/"+label+".uart";o.fork_directory=dir;o.deadline=120;o.usb_peer_timeout_ms=60000;
#if USB_CLOCKED_TEST
 o.usb_host_clock_ppm=2500;o.usb_chip_clock_ppm=-2500;o.usb_host_clock_phase=7;o.usb_chip_clock_phase=38;
#endif
 return o;}

template<class F>static void rejects(Machine&m,F f){auto before=m.inspect();bool rejected=false;try{f();}catch(const std::runtime_error&){rejected=true;}assert(rejected&&m.inspect()==before);}
static void store(const std::string&p,const std::vector<uint8_t>&v){std::ofstream f(p,std::ios::binary);f.write(reinterpret_cast<const char*>(v.data()),v.size());assert(f);}
#if USB_CLOCKED_TEST
static void wrong_physical_reply(const std::string&path,const std::string&output,uint64_t cut){
 std::ifstream f(path);std::string header,horizon,line;assert(bool(std::getline(f,header))&&bool(std::getline(f,horizon)));uint64_t until=number(horizon.substr(8));std::vector<std::string>rows;bool changed=false;
 while(std::getline(f,line)){if(line.rfind("CHECKSUM ",0)==0)break;std::istringstream parse(line);uint64_t cycle,tag,id;assert(bool(parse>>cycle>>tag>>id));std::string frame;std::getline(parse>>std::ws,frame);
  if(!changed&&cycle>=cut&&tag==1&&frame=="SENT"){line=std::to_string(cycle)+" 1 "+std::to_string(id)+" WRONG_PHYSICAL_REPLY";changed=true;}rows.push_back(line+"\n");}
 assert(changed);uint64_t hash=14695981039346656037ULL;auto add=[&](const std::string&text){for(unsigned char c:text){hash^=c;hash*=1099511628211ULL;}};for(auto&row:rows)add(row);add(std::to_string(until)+" 3 0 HORIZON\n");
 std::ofstream out(output);out<<header<<'\n'<<horizon<<'\n';for(auto&row:rows)out<<row;out<<"CHECKSUM "<<hash<<'\n';assert(bool(out));
}
#endif
static void exact_case(Machine&original,const std::string&dir,const std::string&label,uint64_t suffix){
 auto before=original.inspect();uint64_t cycle=original.state().cycle;auto*r=original.soc().rootp;auto cursor=original.state().usb_cursor;auto incoming=original.state().usb_incoming.size();auto host_state=HOST_PHY(tx_state);auto chip_rx_state=CHIP_PHY(rx_state);auto chip_state=CHIP_PHY(tx_state);auto guard=HOST_PHY(guard_samples);auto capture=bytes(dir+"/live.raw");auto start=std::chrono::steady_clock::now();
#if USB_CLOCKED_TEST
 assert(original.state().usb_clock_position==0);
 assert(original.state().usb_host_clock.ppm==2500&&original.state().usb_chip_clock.ppm==-2500);
 assert(original.state().usb_host_clock.initial_phase_quanta==7&&original.state().usb_chip_clock.initial_phase_quanta==38);
 original.state().usb_host_clock.validate_boundary(cycle);original.state().usb_chip_clock.validate_boundary(cycle);
#endif
 original.snapshot(dir+"/"+label+".snap");assert(original.inspect()==before&&bytes(dir+"/live.raw")==capture);
 original.export_usb_replay(dir+"/"+label+"-prefix.tape");assert(original.inspect()==before&&bytes(dir+"/live.raw")==capture);
 original.run(suffix);original.snapshot(dir+"/"+label+"-final.snap");original.export_usb_replay(dir+"/"+label+".tape");auto final_cycle=original.state().cycle;
 Machine fork(options(dir,label+"-fork"));fork.restore(dir+"/"+label+".snap");assert(fork.state().cycle==cycle&&fork.state().usb_attached);fork.snapshot(dir+"/"+label+"-restored.snap");assert(bytes(dir+"/"+label+".snap")==bytes(dir+"/"+label+"-restored.snap"));
 rejects(fork,[&]{fork.run(1);});auto wrong=bytes(dir+"/"+label+".tape");wrong[10]^=1;store(dir+"/"+label+"-wrong-identity.tape",wrong);rejects(fork,[&]{fork.bind_usb_replay(dir+"/"+label+"-wrong-identity.tape");});
 Machine validation(options(dir,label+"-validation"));auto corrupted=bytes(dir+"/"+label+".snap");corrupted.back()^=1;store(dir+"/"+label+"-corrupt.snap",corrupted);rejects(validation,[&]{validation.restore(dir+"/"+label+"-corrupt.snap");});
 auto bad=bytes(dir+"/"+label+".tape");bad[bad.size()-3]^=1;store(dir+"/"+label+"-corrupt.tape",bad);rejects(fork,[&]{fork.bind_usb_replay(dir+"/"+label+"-corrupt.tape");});
 auto final_capture=bytes(dir+"/live.raw");auto independent_before=original.inspect();fork.bind_usb_replay(dir+"/"+label+"-prefix.tape");rejects(fork,[&]{fork.run(1);});fork.bind_usb_replay(dir+"/"+label+".tape");rejects(fork,[&]{fork.run(final_cycle-cycle+1);});fork.run(final_cycle-cycle);fork.snapshot(dir+"/"+label+"-replay.snap");assert(bytes(dir+"/"+label+"-final.snap")==bytes(dir+"/"+label+"-replay.snap"));
#if USB_CLOCKED_TEST
 if(label=="physical-send"){
  auto path=dir+"/physical-send-semantic-error.tape";wrong_physical_reply(dir+"/"+label+".tape",path,cycle);Machine interrupted(options(dir,"interrupted"));interrupted.restore(dir+"/"+label+".snap");interrupted.bind_usb_replay(path);
  bool rejected=false;try{interrupted.run(suffix);}catch(const std::runtime_error&){rejected=true;}assert(rejected&&interrupted.state().usb_clock_position>0);
  // Actual generated SEND completion exposed a checksum-valid but wrong future
  // reply. The half-executed host tick cannot poll, advance or be checkpointed.
  rejects(interrupted,[&]{interrupted.run(1);});rejects(interrupted,[&]{interrupted.snapshot(dir+"/interrupted.snap");});
 }
#endif
 assert(original.inspect()==independent_before&&bytes(dir+"/live.raw")==final_capture); // No fork touches the original owner.
 rusage usage{};assert(!getrusage(RUSAGE_SELF,&usage));std::cout<<"{\"case\":\""<<label<<"\",\"snapshot_cycle\":"<<cycle<<",\"suffix_cycles\":"<<final_cycle-cycle<<",\"host_seconds\":"<<std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()<<",\"peak_rss_kib\":"<<usage.ru_maxrss<<",\"captured_host_tx_state\":"<<unsigned(host_state)<<",\"captured_chip_rx_state\":"<<unsigned(chip_rx_state)<<",\"captured_chip_tx_state\":"<<unsigned(chip_state)<<",\"captured_guard_samples\":"<<unsigned(guard)<<",\"captured_cursor\":"<<cursor<<",\"captured_incoming_bytes\":"<<incoming<<",\"pending_command\":"<<(original.state().usb_command?original.state().usb_command->id:0)<<"}\n"<<std::flush;
}
int main(int argc,char**argv){std::unique_ptr<Machine> diagnostic;std::string diagnostic_dir;try{assert(argc==10);std::string dir=argv[1];diagnostic_dir=dir;auto o=options(dir,"live");o.usb_peer_executable=argv[6];o.usb_peer_arguments={argv[7],argv[8],"83",argv[9]};o.usb_capture_path=dir+"/live.raw";diagnostic=std::make_unique<Machine>(o);auto&original=*diagnostic;original.load_elf(argv[2]);original.load_rom(argv[3]);original.descriptor(argv[5]);auto dtb=bytes(argv[4]);original.put(0x87e00000,dtb.data(),dtb.size());original.prepare();
 exact_case(original,dir,"startup",5000);
 while(!original.state().usb_command||original.state().usb_command->frame!="RESET 5000000"){assert(original.state().cycle<1000000);original.run(1000);}
 exact_case(original,dir,"reset",3000);bool receive=false,submit=false,host_tx=false,chip_rx=false,chip_tx=false,guard=false;
 while(!receive||!submit||!host_tx||!chip_rx||!chip_tx||!guard){
  assert(original.state().cycle<70000000&&!original.state().finished);
  // Small increments only while real PHY/command work is present. These clocks
  // remain in the machine; host polling never advances virtual time separately.
  uint64_t quantum=(original.soc().usb_wire_host_busy||original.soc().usb_wire_chip_busy||
    (original.state().usb_command&&original.state().usb_command->frame.rfind("SEND ",0)==0))?1:1000;
  // An idle machine may accept a new SEND at its next raw poll. A whole
  // 1000-clock leap could hide every symbol of a short 300-clock packet.
  // Observe that boundary before selecting another quantum; machine ordering
  // and virtual clocks are unchanged.
  const auto&phase=original.state();
  if(phase.usb_attached&&!phase.usb_terminal)quantum=std::min(quantum,phase.usb_next_poll>phase.cycle?phase.usb_next_poll-phase.cycle:1);
  original.run(quantum);
  auto*r=original.soc().rootp;
  if(original.state().usb_command&&original.state().usb_command->frame.rfind("SEND ",0)==0&&
     original.state().usb_cursor==original.state().usb_incoming.size()&&original.soc().usb_wire_host_oe&&!host_tx){
   assert(original.soc().usb_wire_host_busy);exact_case(original,dir,"physical-send",5000);host_tx=true;
  }else if(CHIP_PHY(rx_state)==2&&
           original.soc().usb_wire_host_oe&&!chip_rx){exact_case(original,dir,"physical-receive",5000);chip_rx=true;
  }else if(original.soc().usb_wire_chip_oe&&!chip_tx){
   assert(original.soc().usb_wire_chip_busy);exact_case(original,dir,"physical-chip-send",5000);chip_tx=true;
  }else if(original.state().usb_command&&original.state().usb_command->frame.rfind("SEND ",0)==0&&
           original.state().usb_cursor==original.state().usb_incoming.size()&&
           !original.soc().usb_wire_host_oe&&HOST_PHY(guard_samples)&&!guard){
   assert(original.soc().usb_wire_host_busy);exact_case(original,dir,"physical-guard",5000);guard=true;
  }else if(original.soc().usb_configured&&(r->lemma_soc__DOT__packet_usb__DOT__endpoint__DOT__rx_pending&2)&&!receive){
   assert(original.soc().usb_rx_packets>0);exact_case(original,dir,"owned-receive",5000);receive=true;
  }else if(original.soc().usb_configured&&(r->lemma_soc__DOT__packet_usb__DOT__endpoint__DOT__tx_queued&2)&&!submit){
   assert(original.soc().usb_tx_packets>0);exact_case(original,dir,"owned-submit",5000);submit=true;
  }
 }
 assert(original.state().usb_records>20&&original.soc().usb_packet_errors==0);
 assert(original.soc().usb_phy_host_tx_packets>0&&original.soc().usb_phy_chip_rx_packets>0&&
        original.soc().usb_phy_chip_tx_packets>0&&original.soc().usb_phy_host_rx_packets>0);
 assert(original.soc().usb_phy_host_underflows==0&&original.soc().usb_phy_chip_underflows==0);
#if USB_CLOCKED_TEST
 assert(original.soc().usb_phy_host_stuff_errors==0&&original.soc().usb_phy_chip_stuff_errors==0);
 assert(original.soc().usb_phy_host_line_errors==0&&original.soc().usb_phy_chip_line_errors==0);
#endif
 // Observe an actual pending symbol before applying a declared domain-reset
 // input. The captured cut remains before the reset edge and pending output.
 auto*r=original.soc().rootp;
 while(!original.soc().usb_wire_host_oe||HOST_PHY(tx_state)!=2){
  assert(original.state().cycle<70000000&&!original.state().finished);original.run(1);
 }
 original.schedule({original.state().cycle+10,"reset",{8},{}});exact_case(original,dir,"domain-reset",3000);
 assert(original.state().usb_terminal&&!original.state().usb_connected);
 std::cout<<"PASS real RV64 USB Wire startup/reset/physical-symbol/guard and owned receive/submit Pending snapshots; private exact captured native suffixes\n";return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";if(diagnostic){std::cerr<<"FAIL_STATE "<<diagnostic->inspect()<<"\n";try{diagnostic->snapshot(diagnostic_dir+"/failure.snap");}catch(const std::exception&d){std::cerr<<"FAIL_SNAPSHOT "<<d.what()<<"\n";}try{diagnostic->ram_dump(0x80400000,0x100000,diagnostic_dir+"/failure-control.raw");}catch(const std::exception&d){std::cerr<<"FAIL_CONTROL_RAM "<<d.what()<<"\n";}}return 1;}
}
