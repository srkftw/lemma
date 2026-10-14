// SPDX-License-Identifier: Apache-2.0
// Host property for independent clock phase and the generated reset-domain state.
// No guest ELF or external peer is installed; guest traffic is a separate check.
#include "machine_runtime.h"
#include <fstream>
#include <iostream>
#include <tuple>
using namespace lemma;
static void need(bool b,const char*why){if(!b)throw std::runtime_error(why);}
static Options opts(const std::string&dir,const std::string&label){Options o;o.uart_path=dir+"/"+label+".uart";o.quiet_uart=true;o.fork_directory=dir;o.deadline=30;return o;}
static uint64_t word(const std::vector<uint8_t>&b,size_t i){need(i<=b.size()-8,"missing word");uint64_t v=0;for(unsigned n=0;n<8;n++)v|=uint64_t(b[i+n])<<(8*n);return v;}
static void put_word(std::vector<uint8_t>&b,size_t i,uint64_t v){need(i<=b.size()-8,"missing word");for(unsigned n=0;n<8;n++)b[i+n]=v>>(8*n);}
static uint64_t checksum(const std::vector<uint8_t>&b,size_t i,size_t n){uint64_t c=0;for(size_t j=0;j<n;j++){c^=uint64_t(b[i+j])<<56;for(unsigned k=0;k<8;k++)c=(c<<1)^((c>>63)?0x42f0e1eba9ea3693ULL:0);}return c;}
static void save(const std::string&p,const std::vector<uint8_t>&b){std::ofstream f(p,std::ios::binary);f.write(reinterpret_cast<const char*>(b.data()),b.size());need(bool(f),"output failed");}
static void reject_restore(Machine&m,const std::string&p){auto before=m.inspect();bool rejected=false;try{m.restore(p);}catch(const std::runtime_error&){rejected=true;}need(rejected&&m.inspect()==before,"corrupt clock restore changed live machine");}
int main(int argc,char**argv){try{need(argc==2,"expected work directory");std::string dir=argv[1];unsigned case_id=0;
 for(auto [ppm,host_phase,chip_phase]:{std::tuple<int,unsigned,unsigned>{0,0,0},{2500,7,38},{-2500,41,3}}){
  std::string label="clock-"+std::to_string(case_id++);auto o=opts(dir,label+"-live");o.usb_host_clock_ppm=ppm;o.usb_chip_clock_ppm=-ppm;o.usb_host_clock_phase=host_phase;o.usb_chip_clock_phase=chip_phase;Machine original(o);need(original.run(173)==173&&original.state().cycle==173,"initial clock interval did not complete");auto start_cycle=original.state().cycle;
  auto before=original.inspect();original.snapshot(dir+"/"+label+".snap");need(before==original.inspect(),"snapshot changed clock owner");auto initial=bytes(dir+"/"+label+".snap");need(word(initial,8)==10,"wrong Clocked container");
  need(original.run(10003)==10003&&original.state().cycle==start_cycle+10003,"live clock suffix did not complete");original.snapshot(dir+"/"+label+"-live.snap");
  Machine fork(opts(dir,label+"-fork"));fork.restore(dir+"/"+label+".snap");need(fork.state().cycle==start_cycle,"restored clock cycle differs");fork.snapshot(dir+"/"+label+"-restored.snap");need(initial==bytes(dir+"/"+label+"-restored.snap"),"restored complete clock state differs");need(fork.run(10003)==10003&&fork.state().cycle==original.state().cycle,"private clock suffix did not complete");fork.snapshot(dir+"/"+label+"-fork.snap");need(bytes(dir+"/"+label+"-live.snap")==bytes(dir+"/"+label+"-fork.snap"),"exact independently clocked suffix differs");
  auto final_before=original.inspect();Machine validation(opts(dir,label+"-validation"));validation.run(29);auto bad=initial;auto length=word(bad,80);need(length>=64&&length<=bad.size()-112,"wrapper length differs");
  // This selected profile's final64 wrapper bytes are the two logical clocks.
  // Correct the outer checksum so validation must examine the omitted-state
  // class itself, rather than merely rejecting corrupt container bytes.
  put_word(bad,112+length-16,(word(bad,112+length-16)+1)%25000000);put_word(bad,96,checksum(bad,112,length));save(dir+"/"+label+"-fraction.snap",bad);reject_restore(validation,dir+"/"+label+"-fraction.snap");
  bad=initial;put_word(bad,112+length-48,50);put_word(bad,96,checksum(bad,112,length));save(dir+"/"+label+"-phase.snap",bad);reject_restore(validation,dir+"/"+label+"-phase.snap");
  bad=initial;put_word(bad,8,8);save(dir+"/"+label+"-old-container.snap",bad);reject_restore(validation,dir+"/"+label+"-old-container.snap");need(original.inspect()==final_before,"private clock fork changed original");
  std::cout<<"{\"case\":\""<<label<<"\",\"host_ppm\":"<<ppm<<",\"chip_ppm\":"<<-ppm<<",\"host_phase\":"<<host_phase<<",\"chip_phase\":"<<chip_phase<<",\"start_cycle\":"<<start_cycle<<",\"suffix_cycles\":"<<original.state().cycle-start_cycle<<",\"snapshot_bytes\":"<<initial.size()<<"}\n";
 }
 std::cout<<"NATIVE_USB_CLOCK_PASS complete fractional/generated reset-domain suffixes and valid-checksum phase/container negatives; no guest traffic claim\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
