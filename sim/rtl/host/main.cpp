// SPDX-License-Identifier: Apache-2.0
// Host-only clock/reset, external RAM/SRAM/media bytes, raw input and optical
// panel adapter. No instruction emulation, guest-PC actions, journal or drawing.
#include "Vlemma_soc.h"
#include "Vlemma_soc___024root.h"
#include "verilated.h"
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <deque>
#include <map>
#include <array>
#include <sstream>
#include <chrono>
#include <cerrno>
#include <cctype>
#include <limits>
#include <elf.h>
#include <fcntl.h>
#include <unistd.h>
#include "lemma_silicon_binding.h"
static constexpr uint64_t RAM_BASE=BINDING_RAM_BASE,RAM_SIZE=BINDING_RAM_BYTES,ROM_BASE=BINDING_RESET_VECTOR;
static std::vector<uint8_t> ram(RAM_SIZE),rom(BINDING_ROM_BYTES);
static std::vector<uint8_t> bytes(const std::string& path){std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("cannot read "+path);return std::vector<uint8_t>((std::istreambuf_iterator<char>(f)),{});}
static void put(uint64_t addr,const uint8_t* data,size_t n){
 if(addr>=RAM_BASE&&addr+n<=RAM_BASE+RAM_SIZE)std::memcpy(ram.data()+addr-RAM_BASE,data,n);
 else if(addr>=ROM_BASE&&addr+n<=ROM_BASE+rom.size())std::memcpy(rom.data()+addr-ROM_BASE,data,n);
 else throw std::runtime_error("preload outside declared RAM/ROM");}
static void load_elf(const std::string& path){auto b=bytes(path);if(b.size()<sizeof(Elf64_Ehdr))throw std::runtime_error("short ELF");auto*e=reinterpret_cast<const Elf64_Ehdr*>(b.data());
 if(std::memcmp(e->e_ident,ELFMAG,SELFMAG)||e->e_ident[EI_CLASS]!=ELFCLASS64||e->e_ident[EI_DATA]!=ELFDATA2LSB||e->e_machine!=EM_RISCV)throw std::runtime_error("expected little endian RV64 ELF");
 if(e->e_phentsize!=sizeof(Elf64_Phdr)||e->e_phoff+e->e_phnum*sizeof(Elf64_Phdr)>b.size())throw std::runtime_error("invalid ELF headers");
 for(unsigned i=0;i<e->e_phnum;i++){auto*p=reinterpret_cast<const Elf64_Phdr*>(b.data()+e->e_phoff+i*sizeof(Elf64_Phdr));if(p->p_type!=PT_LOAD)continue;
  if(p->p_filesz>p->p_memsz||p->p_offset+p->p_filesz>b.size())throw std::runtime_error("invalid ELF segment");
  std::vector<uint8_t>s(p->p_memsz,0);std::memcpy(s.data(),b.data()+p->p_offset,p->p_filesz);put(p->p_paddr,s.data(),s.size());}}
struct Event{uint64_t cycle;std::string kind;std::vector<uint64_t> words;std::string payload;};
static uint64_t number(const std::string& text){size_t used=0;if(text.empty()||text[0]=='-'||std::isspace(static_cast<unsigned char>(text[0])))throw std::runtime_error("invalid unsigned input");uint64_t value=std::stoull(text,&used,0);if(used!=text.size())throw std::runtime_error("trailing numeric input");return value;}
struct RamDump{uint64_t address=0,size=0;std::string path;};
static RamDump ram_dump(const std::string& text){
 auto a=text.find(':'),b=a==std::string::npos?a:text.find(':',a+1);
 if(a==std::string::npos||b==std::string::npos||b+1==text.size())throw std::runtime_error("--ram-dump address:bytes:path");
 RamDump d{number(text.substr(0,a)),number(text.substr(a+1,b-a-1)),text.substr(b+1)};
 if(!d.size||d.size>1048576||d.address<RAM_BASE||d.address>RAM_BASE+RAM_SIZE-d.size)throw std::runtime_error("RAM dump must be 1..1048576 bytes inside external RAM");
 return d;
}
static std::vector<uint8_t> hexbytes(const std::string& hex){if(hex.size()%2)throw std::runtime_error("odd hex input");auto nibble=[](char c){if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;throw std::runtime_error("invalid hex input");};std::vector<uint8_t>b;for(size_t i=0;i<hex.size();i+=2)b.push_back((nibble(hex[i])<<4)|nibble(hex[i+1]));return b;}
static std::vector<Event> events(const std::string& path){std::vector<Event> out;if(path.empty())return out;std::ifstream f(path);if(!f)throw std::runtime_error("cannot read events");std::string line;
 while(std::getline(f,line)){if(line.empty()||line[0]=='#')continue;std::istringstream ss(line);Event e{};std::string cycle;if(!(ss>>cycle>>e.kind))throw std::runtime_error("invalid event header: "+line);e.cycle=number(cycle);if(e.kind=="uart"){std::string extra;if(!(ss>>e.payload)||(ss>>extra))throw std::runtime_error("invalid UART event: "+line);hexbytes(e.payload);}else{std::string w;while(ss>>w)e.words.push_back(number(w));}
  if((e.kind=="pen"&&e.words.size()!=7)||(e.kind=="reset"&&(e.words.size()!=1||!e.words[0]||e.words[0]>std::numeric_limits<uint64_t>::max()-e.cycle))||(e.kind!="pen"&&e.kind!="uart"&&e.kind!="reset"))throw std::runtime_error("invalid event: "+line);
  if(!out.empty()&&e.cycle<out.back().cycle)throw std::runtime_error("events not ordered");out.push_back(e);}return out;}
int main(int argc,char**argv)try{
 Verilated::commandArgs(argc,argv);Vlemma_soc soc;
 uint64_t cycles=20000000,trace_limit=10000,stop_panels=0,fail_flush=0,observer_cycle=0;unsigned deadline=120;
 std::string uart_path,trace_path,descriptor_path,medium_path,event_path,panel_path,report_path,stop_marker,input_capture_path,block_trace_path;
 RamDump dump;
 std::deque<uint8_t> rx;bool have_elf=false,have_rom=false,quiet_uart=false,uart_stdin=false;
 for(int i=1;i<argc;i++){std::string a=argv[i];auto val=[&](){if(++i>=argc)throw std::runtime_error("missing value "+a);return std::string(argv[i]);};
  if(a=="--image"){load_elf(val());have_elf=true;}else if(a=="--rom"){auto b=bytes(val());put(ROM_BASE,b.data(),b.size());have_rom=true;}
  else if(a=="--load"){auto v=val();auto c=v.find(':');if(c==std::string::npos)throw std::runtime_error("--load address:path");auto b=bytes(v.substr(c+1));put(number(v.substr(0,c)),b.data(),b.size());}
  else if(a=="--uart-input"){auto b=bytes(val());rx.insert(rx.end(),b.begin(),b.end());}
  else if(a=="--uart-output")uart_path=val();else if(a=="--trace")trace_path=val();else if(a=="--cycles")cycles=number(val());
  else if(a=="--trace-limit")trace_limit=number(val());else if(a=="--deadline"){auto d=number(val());if(!d||d>3600)throw std::runtime_error("deadline must be1..3600seconds");deadline=d;}
  else if(a=="--quiet-uart")quiet_uart=true;
  else if(a=="--uart-stdin")uart_stdin=true;
  else if(a=="--input-capture")input_capture_path=val();
  else if(a=="--uart-stop-hex"){auto b=hexbytes(val());stop_marker=std::string(b.begin(),b.end());}
  else if(a=="--descriptor")descriptor_path=val();else if(a=="--medium")medium_path=val();else if(a=="--events")event_path=val();
  else if(a=="--panel-output")panel_path=val();else if(a=="--report")report_path=val();else if(a=="--uart-stop")stop_marker=val();
  else if(a=="--stop-after-panel")stop_panels=number(val());else if(a=="--fail-flush")fail_flush=number(val());
  else if(a=="--observer-cycle")observer_cycle=number(val());
  else if(a=="--ram-dump")dump=ram_dump(val());else if(a=="--block-trace")block_trace_path=val();
  else throw std::runtime_error("unknown argument "+a);}
 if(!have_elf||!have_rom||uart_path.empty())throw std::runtime_error("--image --rom --uart-output required");
 if(observer_cycle>cycles)throw std::runtime_error("observer cycle exceeds cycle budget");
 std::ofstream uart(uart_path,std::ios::binary),trace,panel_log,input_capture,block_trace;if(!uart)throw std::runtime_error("cannot open UART output");
 if(!block_trace_path.empty()){block_trace.open(block_trace_path);if(!block_trace)throw std::runtime_error("cannot open block transaction capture");block_trace<<"cycle,event,write,size,address,raw_wdata,wdata,rdata,error,state,status,queue_num,queue_ready,interrupt_status,result\n";}
 uint64_t block_rows=0,block_omitted=0;uint64_t previous_block_state=~uint64_t(0);
 // Literal circuit transactions and state only. This observer never parses a
 // guest queue, predicts a completion, or changes a device response.
 auto block_row=[&](uint64_t c,const char*event,unsigned write,unsigned size,uint64_t address,uint64_t raw,uint64_t wdata,uint64_t rdata,unsigned error){
  if(!block_trace.is_open())return;if(block_rows>=4096){block_omitted++;return;}block_rows++;auto*r=soc.rootp;
  block_trace<<c<<','<<event<<','<<write<<','<<size<<",0x"<<std::hex<<address<<",0x"<<raw<<",0x"<<wdata<<",0x"<<rdata<<std::dec<<','<<error<<','<<unsigned(r->lemma_soc__DOT__blockdev__DOT__state)<<','<<r->lemma_soc__DOT__blockdev__DOT__status<<','<<r->lemma_soc__DOT__blockdev__DOT__queue_num<<','<<r->lemma_soc__DOT__blockdev__DOT__queue_ready<<','<<r->lemma_soc__DOT__blockdev__DOT__interrupt_status<<','<<unsigned(r->lemma_soc__DOT__blockdev__DOT__result)<<'\n';
  block_trace.flush();if(!block_trace)throw std::runtime_error("block capture write failed");
 };
 if(!input_capture_path.empty()){input_capture.open(input_capture_path);if(!input_capture)throw std::runtime_error("cannot open input capture");}
 if(uart_stdin){int flags=fcntl(STDIN_FILENO,F_GETFL,0);if(flags<0||fcntl(STDIN_FILENO,F_SETFL,flags|O_NONBLOCK)<0)throw std::runtime_error("cannot configure raw UART stdin");}
 auto capture_uart=[&](uint64_t cycle,const uint8_t* b,size_t n){if(input_capture){static const char*hex="0123456789abcdef";input_capture<<cycle<<" uart ";for(size_t i=0;i<n;i++)input_capture<<hex[b[i]>>4]<<hex[b[i]&15];input_capture<<"\n";input_capture.flush();}};
 if(!rx.empty()){std::vector<uint8_t>b(rx.begin(),rx.end());capture_uart(0,b.data(),b.size());}
 if(!trace_path.empty()){trace.open(trace_path);trace<<"cycle,pc,privilege,retire,trap,cause,memory,write,address,timer\n";}
 if(!panel_path.empty()){panel_log.open(panel_path+".events");panel_log<<"cycle,event,sequence,x,y,gray\n";}
 for(int i=0;i<64;i++)soc.descriptor[i]=0;
 if(!descriptor_path.empty()){auto b=bytes(descriptor_path);if(b.size()!=256)throw std::runtime_error("descriptor must be256bytes");std::memcpy(soc.descriptor.data(),b.data(),256);}
 int medium=-1;if(!medium_path.empty()){medium=open(medium_path.c_str(),O_RDWR);if(medium<0)throw std::runtime_error("cannot open medium");if(lseek(medium,0,SEEK_END)!=512LL*524288)throw std::runtime_error("medium capacity mismatch");}
 std::map<uint64_t,std::array<uint8_t,512>> overlay;
 std::vector<uint8_t> framebuffer(2*BINDING_WIDTH*BINDING_HEIGHT,15),visible(BINDING_WIDTH*BINDING_HEIGHT,15);
 std::map<uint64_t,uint8_t> optical_pending;std::vector<Event> input=events(event_path);size_t event_index=0;std::deque<Event> samples;
 auto start=std::chrono::steady_clock::now();uint64_t retired=0,privilege_cycles[4]={0},traps=0,timer_traps=0,flushes=0,media_requests=0,pen_ingress=0,pen_accepted=0,panel_completed=0,panel_aborted=0;
 // Successful byte transfers on the controller's external framebuffer port,
 // and accepted pixel beats on its panel port. Counts span this execution,
 // exclude reset cycles, and include pixels later discarded by panel_abort.
 uint64_t fb_reads=0,fb_writes=0,panel_pixels=0;
 unsigned old_privilege=3;uint64_t transitions=0,reset_until=8,actual_cycles=0;bool finished=false,stopped=false;uint32_t finish=0;std::string uart_text;
 soc.clk=0;soc.reset=1;soc.preload_valid=0;soc.preload_index=0;soc.preload_data=0;soc.eval();
 if(soc.register_memory_enabled&&!dump.path.empty())throw std::runtime_error("RAM dump requires the external-memory configuration");
 if(soc.register_memory_enabled&&block_trace.is_open())throw std::runtime_error("Block tracing requires the external-memory configuration");
 if(soc.register_memory_enabled)reset_until=520;soc.mem_ready=1;soc.mem_error=0;soc.uart_rx_valid=0;soc.uart_rx_data=0;
 soc.sample_valid=0;soc.sample_time=0;soc.sample_x=0;soc.sample_y=0;soc.sample_pressure=0;soc.sample_flags=0;soc.sample_tool=0;soc.sample_buttons=0;
 soc.fb_ready=1;soc.fb_error=0;soc.fb_rdata=15;soc.panel_ready=1;soc.media_ready=1;soc.media_error=0;
 for(uint64_t c=0;c<cycles;c++){actual_cycles=c+1;
  if(uart_stdin&&(c&1023)==0){uint8_t b[4096];ssize_t n=read(STDIN_FILENO,b,sizeof(b));if(n>0){rx.insert(rx.end(),b,b+n);capture_uart(c,b,n);}else if(n<0&&errno!=EAGAIN&&errno!=EWOULDBLOCK&&errno!=EINTR)throw std::runtime_error("raw UART stdin read failed");}
  while(event_index<input.size()&&input[event_index].cycle<=c){auto e=input[event_index++];if(e.kind=="uart"){auto b=hexbytes(e.payload);rx.insert(rx.end(),b.begin(),b.end());}else if(e.kind=="reset"){reset_until=c+e.words[0];overlay.clear();optical_pending.clear();}else samples.push_back(e);}
  soc.clk=0;soc.reset=c<reset_until;
  soc.preload_valid=soc.register_memory_enabled&&c<512;soc.preload_index=c&511;soc.preload_data=0;
  if(soc.preload_valid){uint64_t a=c<384?RAM_BASE+8*c:c<448?0x807ffe00+8*(c-384):0x81000000+8*(c-448);std::memcpy(&soc.preload_data,ram.data()+a-RAM_BASE,8);}
  soc.uart_rx_valid=!rx.empty();soc.uart_rx_data=rx.empty()?0:rx.front();soc.sample_valid=!samples.empty();
  if(!samples.empty()){auto&w=samples.front().words;soc.sample_time=w[0];soc.sample_x=w[1];soc.sample_y=w[2];soc.sample_pressure=w[3];soc.sample_flags=w[4];soc.sample_tool=w[5];soc.sample_buttons=w[6];}
  soc.eval();soc.mem_rdata=0;soc.mem_error=0;
  uint8_t* ram_pointer=nullptr;
  if(soc.mem_valid){uint64_t addr=soc.mem_addr;if(addr>=RAM_BASE&&addr+8<=RAM_BASE+RAM_SIZE)ram_pointer=ram.data()+addr-RAM_BASE;else if(addr>=ROM_BASE&&addr+8<=ROM_BASE+rom.size())ram_pointer=rom.data()+addr-ROM_BASE;else soc.mem_error=1;
   if(ram_pointer){std::memcpy(&soc.mem_rdata,ram_pointer,8);if(soc.mem_write&&addr<ROM_BASE+rom.size())soc.mem_error=1;}}
  soc.fb_error=soc.fb_valid&&soc.fb_addr>=framebuffer.size();soc.fb_rdata=soc.fb_error?0:framebuffer[soc.fb_addr%framebuffer.size()];
  soc.media_error=0;for(int i=0;i<128;i++)soc.media_rdata[i]=0;
  if(soc.media_valid&&!soc.reset){media_requests++;uint64_t sector=soc.media_sector;
   if(medium<0||sector>=524288)soc.media_error=1;
   else if(soc.media_kind==0){std::array<uint8_t,512>b{};if(overlay.count(sector))b=overlay.at(sector);else if(pread(medium,b.data(),512,sector*512)!=512)throw std::runtime_error("short medium read");std::memcpy(soc.media_rdata.data(),b.data(),512);}
   else if(soc.media_kind==1){std::array<uint8_t,512>b{};std::memcpy(b.data(),soc.media_wdata.data(),512);overlay[sector]=b;}
   else if(soc.media_kind==4){flushes++;if(fail_flush&&flushes==fail_flush)soc.media_error=1;else{for(auto&[s,b]:overlay)if(pwrite(medium,b.data(),512,s*512)!=512)throw std::runtime_error("short medium write");if(fsync(medium))throw std::runtime_error("medium fsync failed");overlay.clear();}}
   else soc.media_error=1;
   block_row(c,soc.media_kind==0?"media-read":soc.media_kind==1?"media-write":soc.media_kind==4?"media-flush":"media-invalid",soc.media_kind==1,9,sector,0,0,0,soc.media_error);
  }
  soc.eval();
  if(!soc.reset){
   auto*r=soc.rootp;
   if(block_trace.is_open()){
    uint64_t state=(uint64_t(r->lemma_soc__DOT__blockdev__DOT__state)<<32)|r->lemma_soc__DOT__blockdev__DOT__status;
    if(state!=previous_block_state){block_row(c,"state",0,0,0,0,0,0,0);previous_block_state=state;}
    if(r->lemma_soc__DOT____Vcellinp__blockdev__valid&&r->lemma_soc__DOT__compute__DOT__hready)
     block_row(c,"mmio",r->lemma_soc__DOT__compute__DOT__write_d,r->lemma_soc__DOT__compute__DOT__size_d,r->lemma_soc__DOT__compute__DOT__addr_d,r->lemma_soc__DOT__compute__DOT__core__DOT__LSUHWDATA,r->lemma_soc__DOT____Vcellinp__blockdev__wdata,r->lemma_soc__DOT__compute__DOT__hrdata,r->lemma_soc__DOT__compute__DOT__hresp);
    if(r->lemma_soc__DOT__dma_valid&&r->lemma_soc__DOT__dma_ready)
     // This observer is limited to the external-memory configuration: its
     // response error is the actual host input. selected_fault is the retained
     // RTL rejection for the active beat, including held-owner semantics.
     block_row(c,"dma",soc.mem_write,r->lemma_soc__DOT__dma_size,r->lemma_soc__DOT__dma_addr,soc.mem_wdata,soc.mem_wdata>>(8*(r->lemma_soc__DOT__dma_addr&7)),r->lemma_soc__DOT__dma_rdata,r->lemma_soc__DOT__selected_fault||soc.mem_error);
   }
   if(!soc.register_memory_enabled&&soc.mem_valid&&soc.mem_ready&&soc.mem_write&&!soc.mem_error&&ram_pointer)for(int j=0;j<8;j++)if(soc.mem_strb&(1<<j))ram_pointer[j]=soc.mem_wdata>>(j*8);
   if(soc.fb_valid&&soc.fb_ready&&!soc.fb_error){
    if(soc.fb_write){framebuffer[soc.fb_addr]=soc.fb_wdata;fb_writes++;}
    else fb_reads++;
   }
   if(soc.uart_tx_valid){uart.put(soc.uart_tx_data);uart.flush();uart_text.push_back(soc.uart_tx_data);if(!quiet_uart){std::cout.put(soc.uart_tx_data);std::cout.flush();}}
   if(soc.uart_rx_ready&&!rx.empty())rx.pop_front();if(soc.sample_valid&&soc.sample_ready&&!samples.empty()){samples.pop_front();pen_ingress++;}
   if(soc.sample_accepted)pen_accepted++;
   if(soc.panel_valid&&soc.panel_ready){if(soc.panel_x>=BINDING_WIDTH||soc.panel_y>=BINDING_HEIGHT)throw std::runtime_error("controller pixel out of bounds");panel_pixels++;optical_pending[soc.panel_y*BINDING_WIDTH+soc.panel_x]=soc.panel_gray;if(panel_log)panel_log<<c<<",pixel,"<<soc.panel_sequence<<","<<soc.panel_x<<","<<soc.panel_y<<","<<unsigned(soc.panel_gray)<<"\n";}
   if(soc.panel_complete){for(auto&[i,v]:optical_pending)visible[i]=v;optical_pending.clear();panel_completed++;if(panel_log)panel_log<<c<<",complete,"<<soc.panel_sequence<<",0,0,0\n";}
   if(soc.panel_abort){optical_pending.clear();panel_aborted++;if(panel_log)panel_log<<c<<",abort,"<<soc.panel_sequence<<",0,0,0\n";}
   if(soc.finish_valid){finished=true;finish=soc.finish_code;}if(soc.debug_retire)retired++;
   privilege_cycles[soc.debug_privilege]++;if(soc.debug_privilege!=old_privilege){transitions++;old_privilege=soc.debug_privilege;}
   if(soc.debug_trap){traps++;if(soc.debug_cause==0x8000000000000007ULL)timer_traps++;}
   if(trace&&c<trace_limit)trace<<c<<",0x"<<std::hex<<soc.debug_pc<<std::dec<<","<<unsigned(soc.debug_privilege)<<","<<unsigned(soc.debug_retire)<<","<<unsigned(soc.debug_trap)<<",0x"<<std::hex<<soc.debug_cause<<std::dec<<","<<unsigned(soc.mem_valid)<<","<<unsigned(soc.mem_write)<<",0x"<<std::hex<<soc.mem_addr<<std::dec<<","<<soc.timer_ticks<<"\n";
  }
  soc.clk=1;soc.eval();
  stopped=(!stop_marker.empty()&&uart_text.find(stop_marker)!=std::string::npos)||(stop_panels&&panel_completed>=stop_panels)||(observer_cycle&&c+1>=observer_cycle);
  if(finished||stopped)break;
  if(c&&c%1000000==0)std::cerr<<"RTL progress cycles="<<c<<" pc=0x"<<std::hex<<soc.debug_pc<<std::dec<<" privilege="<<unsigned(soc.debug_privilege)<<" retired="<<retired<<" ticks="<<soc.timer_ticks<<" timer_traps="<<timer_traps<<" UART="<<uart_text.size()<<" fb_reads="<<fb_reads<<" fb_writes="<<fb_writes<<" panel_pixels="<<panel_pixels<<" panel_completed="<<panel_completed<<"\n";
  if((c&0x3ffff)==0&&std::chrono::steady_clock::now()-start>std::chrono::seconds(deadline))throw std::runtime_error("RTL wall deadline exceeded");
 }
 if(!dump.path.empty()&&(finished||stopped)){std::ofstream f(dump.path,std::ios::binary);if(!f||!f.write(reinterpret_cast<const char*>(ram.data()+dump.address-RAM_BASE),dump.size)||!f.flush())throw std::runtime_error("external RAM snapshot write failed");}
 if(block_trace.is_open()){block_trace.flush();if(!block_trace)throw std::runtime_error("block capture write failed");}
 if(!panel_path.empty()){std::ofstream pgm(panel_path,std::ios::binary);pgm<<"P5\n"<<BINDING_WIDTH<<" "<<BINDING_HEIGHT<<"\n255\n";for(auto v:visible)pgm.put(v*17);}
 if(medium>=0)close(medium);
 if(!report_path.empty()){std::ofstream r(report_path);r<<"{\n\"block_rows\":"<<block_rows<<",\"block_omitted\":"<<block_omitted<<",\"cycles\":"<<actual_cycles<<",\"retired\":"<<retired<<",\"privilege_cycles\":["<<privilege_cycles[0]<<","<<privilege_cycles[1]<<","<<privilege_cycles[2]<<","<<privilege_cycles[3]<<"],\"privilege_transitions\":"<<transitions<<",\"traps\":"<<traps<<",\"timer_traps\":"<<timer_traps<<",\"pen_ingress\":"<<pen_ingress<<",\"pen_accepted\":"<<pen_accepted<<",\"fb_reads\":"<<fb_reads<<",\"fb_writes\":"<<fb_writes<<",\"panel_pixels\":"<<panel_pixels<<",\"panel_completed\":"<<panel_completed<<",\"panel_aborted\":"<<panel_aborted<<",\"media_requests\":"<<media_requests<<",\"flushes\":"<<flushes<<",\"volatile_sectors_discarded\":"<<overlay.size()<<",\"finished\":"<<(finished?"true":"false")<<",\"explicit_observer_stop\":"<<(stopped?"true":"false")<<",\"observer_cycle\":"<<observer_cycle<<",\"finish_code\":"<<finish<<"\n}\n";}
 std::cerr<<"\nRTL cycles="<<actual_cycles<<" retired="<<retired<<" timer_traps="<<timer_traps<<" finish=0x"<<std::hex<<finish<<std::dec<<" observer_stop="<<stopped<<" block_rows="<<block_rows<<" block_omitted="<<block_omitted<<"\n";
 return finished?(finish==0x5555?0:2):stopped?0:3;
}catch(const std::exception&e){std::cerr<<"RTL adapter: "<<e.what()<<"\n";return 1;}
