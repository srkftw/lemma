// SPDX-License-Identifier: Apache-2.0
// Host property driver: every USB packet and guest MMIO operation is executed
// by the maintained RTL and genuine audited RV64 initializer.
#include "machine_runtime.h"
#include "Vlemma_soc___024root.h"
#include <cassert>
#include <chrono>
#include <fstream>
#include <iostream>
#include <sys/resource.h>
using namespace lemma;
#undef assert
#define assert(value) ((value)?void(0):throw std::runtime_error("property failed: " #value))
static Options options(const std::string&dir,const std::string&label){Options o;o.quiet_uart=true;o.uart_path=dir+"/"+label+".uart";o.fork_directory=dir;o.deadline=120;return o;}
template<class F>static void rejects(Machine&m,F f){auto before=m.inspect();bool rejected=false;try{f();}catch(const std::runtime_error&){rejected=true;}assert(rejected&&m.inspect()==before);}
static void store(const std::string&p,const std::vector<uint8_t>&v){std::ofstream f(p,std::ios::binary);f.write(reinterpret_cast<const char*>(v.data()),v.size());assert(f);}
static void exact_case(Machine&original,const std::string&dir,const std::string&label,uint64_t suffix){
 auto before=original.inspect();uint64_t cycle=original.state().cycle;auto capture=bytes(dir+"/live.raw");auto start=std::chrono::steady_clock::now();
 original.snapshot(dir+"/"+label+".snap");assert(original.inspect()==before&&bytes(dir+"/live.raw")==capture);
 original.export_usb_replay(dir+"/"+label+"-prefix.tape");assert(original.inspect()==before&&bytes(dir+"/live.raw")==capture);
 original.run(suffix);original.snapshot(dir+"/"+label+"-final.snap");original.export_usb_replay(dir+"/"+label+".tape");auto final_cycle=original.state().cycle;
 Machine fork(options(dir,label+"-fork"));fork.restore(dir+"/"+label+".snap");assert(fork.state().cycle==cycle&&fork.state().usb_attached);fork.snapshot(dir+"/"+label+"-restored.snap");assert(bytes(dir+"/"+label+".snap")==bytes(dir+"/"+label+"-restored.snap"));
 rejects(fork,[&]{fork.run(1);});auto wrong=bytes(dir+"/"+label+".tape");wrong[10]^=1;store(dir+"/"+label+"-wrong-identity.tape",wrong);rejects(fork,[&]{fork.bind_usb_replay(dir+"/"+label+"-wrong-identity.tape");});
 Machine validation(options(dir,label+"-validation"));auto corrupted=bytes(dir+"/"+label+".snap");corrupted.back()^=1;store(dir+"/"+label+"-corrupt.snap",corrupted);rejects(validation,[&]{validation.restore(dir+"/"+label+"-corrupt.snap");});
 auto bad=bytes(dir+"/"+label+".tape");bad[bad.size()-3]^=1;store(dir+"/"+label+"-corrupt.tape",bad);rejects(fork,[&]{fork.bind_usb_replay(dir+"/"+label+"-corrupt.tape");});
 auto final_capture=bytes(dir+"/live.raw");auto independent_before=original.inspect();fork.bind_usb_replay(dir+"/"+label+"-prefix.tape");rejects(fork,[&]{fork.run(1);});fork.bind_usb_replay(dir+"/"+label+".tape");rejects(fork,[&]{fork.run(final_cycle-cycle+1);});fork.run(final_cycle-cycle);fork.snapshot(dir+"/"+label+"-replay.snap");assert(bytes(dir+"/"+label+"-final.snap")==bytes(dir+"/"+label+"-replay.snap"));
 assert(original.inspect()==independent_before&&bytes(dir+"/live.raw")==final_capture); // No fork touches the original owner.
 rusage usage{};assert(!getrusage(RUSAGE_SELF,&usage));std::cout<<"{\"case\":\""<<label<<"\",\"snapshot_cycle\":"<<cycle<<",\"suffix_cycles\":"<<final_cycle-cycle<<",\"host_seconds\":"<<std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()<<",\"peak_rss_kib\":"<<usage.ru_maxrss<<",\"pending_command\":"<<(original.state().usb_command?original.state().usb_command->id:0)<<"}\n"<<std::flush;
}
int main(int argc,char**argv){try{assert(argc==10);std::string dir=argv[1];auto o=options(dir,"live");o.usb_peer_executable=argv[6];o.usb_peer_arguments={argv[7],argv[8],"83",argv[9]};o.usb_capture_path=dir+"/live.raw";Machine original(o);original.load_elf(argv[2]);original.load_rom(argv[3]);original.descriptor(argv[5]);auto dtb=bytes(argv[4]);original.put(0x87e00000,dtb.data(),dtb.size());original.prepare();
 exact_case(original,dir,"startup",5000);
 while(!original.state().usb_command||original.state().usb_command->frame!="RESET 5000000"){assert(original.state().cycle<1000000);original.run(1000);}
 exact_case(original,dir,"reset",3000);bool receive=false,submit=false;
 while(!receive||!submit){assert(original.state().cycle<70000000&&!original.state().finished);original.run(1000);auto*r=original.soc().rootp;
  if(original.soc().usb_configured&&(r->lemma_soc__DOT__packet_usb__DOT__endpoint__DOT__rx_pending&2)&&!receive){assert(original.soc().usb_rx_packets>0);exact_case(original,dir,"owned-receive",5000);receive=true;}
  if(original.soc().usb_configured&&(r->lemma_soc__DOT__packet_usb__DOT__endpoint__DOT__tx_queued&2)&&!submit){assert(original.soc().usb_tx_packets>0);exact_case(original,dir,"owned-submit",5000);submit=true;}
 }
 assert(original.state().usb_records>20&&original.soc().usb_packet_errors==0);original.schedule({original.state().cycle+100,"reset",{8},{}});exact_case(original,dir,"domain-reset",3000);assert(original.state().usb_terminal&&!original.state().usb_connected);std::cout<<"PASS real RV64 USB startup/reset and owned receive/submit raw Pending snapshots; private exact captured native suffixes\n";return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}
}
