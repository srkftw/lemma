// SPDX-License-Identifier: Apache-2.0
#include "machine_runtime.h"
#include "../../host/backing_io_posix.h"
#include "Vlemma_soc___024root.h"
#include "verilated_save.h"
#include "lemma_silicon_binding.h"
#include "lemma_runtime_identity.h"
#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstring>
#include <elf.h>
#include <fcntl.h>
#include <filesystem>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <sys/stat.h>
#include <sys/file.h>
#include <unistd.h>
namespace lemma {
static constexpr uint64_t RAM_BASE=BINDING_RAM_BASE,RAM_SIZE=BINDING_RAM_BYTES,ROM_BASE=BINDING_RESET_VECTOR;
static constexpr uint64_t MEDIUM_SECTORS=524288,MAX_EVENTS=1000000,MAX_UART=16*1024*1024;
static constexpr uint64_t MAX_BACKING_LOG=64*1024*1024;
static constexpr uint64_t MAX_EVENT_PAYLOAD=2*MAX_UART,MAX_EVENT_LINE=MAX_EVENT_PAYLOAD+8192,MAX_EVENT_FILE=256*1024*1024;
static std::string json_string(const std::string& text){std::ostringstream out;out<<'"';for(unsigned char c:text){if(c=='"'||c=='\\')out<<'\\'<<c;else if(c<32)out<<"\\u00"<<"0123456789abcdef"[c>>4]<<"0123456789abcdef"[c&15];else out<<c;}out<<'"';return out.str();}
std::vector<uint8_t> bytes(const std::string& path){std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("cannot read "+path);return std::vector<uint8_t>((std::istreambuf_iterator<char>(f)),{});}
uint64_t number(const std::string& text){size_t used=0;if(text.empty()||text[0]=='-'||std::isspace(static_cast<unsigned char>(text[0])))throw std::runtime_error("invalid unsigned input");uint64_t value=std::stoull(text,&used,0);if(used!=text.size())throw std::runtime_error("trailing numeric input");return value;}
std::vector<uint8_t> hexbytes(const std::string& hex){if(hex.size()%2||hex.size()>2*MAX_UART)throw std::runtime_error("invalid hex input length");auto nibble=[](char c){if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;throw std::runtime_error("invalid hex input");};std::vector<uint8_t>b;for(size_t i=0;i<hex.size();i+=2)b.push_back((nibble(hex[i])<<4)|nibble(hex[i+1]));return b;}
static void validate_event_fields(const Event&e){
 if((e.kind=="pen"&&e.words.size()!=7)||(e.kind=="reset"&&(e.words.size()!=1||!e.words[0]||e.words[0]>UINT64_MAX-e.cycle))||(e.kind=="uart"&&!e.words.empty())||(e.kind=="button"&&(!BINDING_POWER_ENABLED||e.words.size()!=1||e.words[0]>1))||(e.kind!="pen"&&e.kind!="uart"&&e.kind!="reset"&&e.kind!="button"))throw std::runtime_error("invalid external event fields");
 if(e.kind=="pen"&&(e.words[1]>65535||e.words[2]>65535||e.words[3]>4095||e.words[4]>15||e.words[5]>2||e.words[6]>7))throw std::runtime_error("pen sample field outside admitted range");
}

Event parse_event(const std::string& line){if(line.size()>MAX_EVENT_LINE)throw std::runtime_error("event line exceeds byte bound");std::istringstream ss(line);Event e;std::string c;if(!(ss>>c>>e.kind))throw std::runtime_error("invalid event header");e.cycle=number(c);if(e.kind=="uart"){std::string extra;if(!(ss>>e.payload)||(ss>>extra))throw std::runtime_error("invalid UART event");hexbytes(e.payload);}else{if(e.kind!="pen"&&e.kind!="reset"&&e.kind!="button")throw std::runtime_error("invalid event kind");std::string w;while(ss>>w){if(e.words.size()>=7)throw std::runtime_error("event word bound exceeded");e.words.push_back(number(w));}}
 validate_event_fields(e);return e;}
std::vector<Event> events(const std::string& path){std::vector<Event> out;if(path.empty())return out;struct stat st{};if(stat(path.c_str(),&st)||!S_ISREG(st.st_mode)||st.st_size<0||uint64_t(st.st_size)>MAX_EVENT_FILE)throw std::runtime_error("events require a regular file at most256MiB");std::ifstream f(path);if(!f)throw std::runtime_error("cannot read events");std::string line;uint64_t total=0,payload=0;auto admit=[&](){if(line.empty()||line[0]=='#')return;auto e=parse_event(line);if(out.size()>=MAX_EVENTS||(!out.empty()&&e.cycle<out.back().cycle))throw std::runtime_error("event queue bound/order");if(e.payload.size()>MAX_EVENT_PAYLOAD-payload)throw std::runtime_error("event payload budget exceeded");payload+=e.payload.size();out.push_back(std::move(e));};char ch;while(f.get(ch)){if(++total>MAX_EVENT_FILE)throw std::runtime_error("event file byte bound exceeded");if(ch=='\n'){admit();line.clear();}else{if(line.size()>=MAX_EVENT_LINE)throw std::runtime_error("event line exceeds byte bound");line.push_back(ch);}}if(!f.eof())throw std::runtime_error("event read failed");admit();return out;}
static void backing_header(int fd){std::string header="LMIOLOG2";header+=LEMMA_RUNTIME_IDENTITY;if(write(fd,header.data(),header.size())!=ssize_t(header.size()))throw std::runtime_error("backing capture header failed");}
static std::vector<TimedBackingRecord> read_backing_replay(const std::string& path){
 std::vector<TimedBackingRecord> result;
  struct stat logstat{};if(stat(path.c_str(),&logstat)||!S_ISREG(logstat.st_mode)||logstat.st_size<72||uint64_t(logstat.st_size)>MAX_BACKING_LOG)throw std::runtime_error("backing replay requires a bounded regular log");
  auto wire=bytes(path);if(wire.size()<72||wire.size()>MAX_BACKING_LOG||std::memcmp(wire.data(),"LMIOLOG2",8)||std::memcmp(wire.data()+8,LEMMA_RUNTIME_IDENTITY,64))throw std::runtime_error("unsupported backing outcome log");
  uint64_t offset=72,previous=0,cycle=0;std::optional<BackingRequest>request;
  auto word=[&](){if(wire.size()-offset<8)throw std::runtime_error("incomplete backing outcome entry");uint64_t n=0;for(int i=0;i<8;i++)n|=uint64_t(wire[offset++])<<(8*i);return n;};
  while(offset<wire.size()){
   auto tag=word(),n=word();if(tag>1||!n||n>wire.size()-offset)throw std::runtime_error("invalid backing outcome entry");
   if(!tag){if(request)throw std::runtime_error("multiple pending backing requests");request=decode_backing_request(wire.data()+offset,n);}
   else{auto record=decode_timed_backing_record(wire.data()+offset,n);
    if(!request||!equal_backing_request(*request,record.record.request)||result.size()>=MAX_EVENTS||(previous&&request->id!=previous+1)||request->boundary<cycle)throw std::runtime_error("backing outcome identity, order or count");
    previous=request->id;cycle=record.accepted_boundary;result.push_back(std::move(record));request.reset();
   }offset+=n;
  }
  if(request)throw std::runtime_error("backing outcome log ends with unresolved external work");
  if(result.empty())throw std::runtime_error("backing outcome log has no complete outcome");
 return result;
}
Machine::Machine(const Options&o):context(new VerilatedContext),options(o){context->randReset(0);
#ifdef __EMSCRIPTEN__
 context->threads(1);
#endif
 model.reset(new Vlemma_soc(context.get()));s.ram.resize(RAM_SIZE);s.rom.resize(BINDING_ROM_BYTES);s.framebuffer.resize(2*BINDING_WIDTH*BINDING_HEIGHT,15);s.visible.resize(BINDING_WIDTH*BINDING_HEIGHT,15);s.fail_flush=o.fail_flush;s.memory_latency=o.memory_latency;s.stop_marker=o.stop_marker;s.stop_panels=o.stop_panels;s.observer_cycle=o.observer_cycle;
 if(!o.backing_capture_path.empty()&&!o.backing_replay_path.empty())throw std::runtime_error("backing capture and replay are mutually exclusive");
 if(!o.backing_replay_path.empty())backing_replay=read_backing_replay(o.backing_replay_path);
 if(!o.backing_capture_path.empty()){
  backing_capture=open(o.backing_capture_path.c_str(),O_RDWR|O_CREAT|O_EXCL,0600);if(backing_capture<0)throw std::runtime_error("backing capture requires a new file");
  try{backing_header(backing_capture);}catch(...){close(backing_capture);backing_capture=-1;unlink(o.backing_capture_path.c_str());throw;}backing_capture_bytes=72;active_backing_capture=o.backing_capture_path;
 }
 if(o.stop_marker.size()>65536)throw std::runtime_error("stop marker too long");
 if(!o.drive_trace_path.empty()){drive_trace.open(o.drive_trace_path,std::ios::binary);if(!drive_trace)throw std::runtime_error("cannot open drive trace");drive_trace.write("LMDIG1\0\0",8);}
 if(o.uart_path.empty())throw std::runtime_error("--uart-output required");uart.open(o.uart_path,std::ios::binary);if(!uart)throw std::runtime_error("cannot open UART output");
 if(!o.trace_path.empty()){trace.open(o.trace_path);if(!trace)throw std::runtime_error("cannot open trace");trace<<"cycle,pc,privilege,retire,trap,cause,memory,write,address,timer\n";}
 if(!o.panel_path.empty()){panel_log.open(o.panel_path+".events");if(!panel_log)throw std::runtime_error("cannot open panel trace");panel_log<<"cycle,event,sequence,x,y,gray\n";}
 if(!o.input_capture_path.empty()){input_capture.open(o.input_capture_path);if(!input_capture)throw std::runtime_error("cannot open input capture");}
 if(!o.block_trace_path.empty()){block_trace.open(o.block_trace_path);if(!block_trace)throw std::runtime_error("cannot open block trace");block_trace<<"cycle,event,write,size,address,raw_wdata,wdata,rdata,error,state,status,queue_num,queue_ready,interrupt_status,result\n";}
 auto&soc=*model;for(int i=0;i<64;i++)soc.descriptor[i]=0;soc.clk=0;soc.reset=1;soc.power_reset_cause=1;soc.raw_button_level=0;soc.preload_valid=0;soc.preload_index=0;soc.preload_data=0;soc.eval();if(soc.register_memory_enabled)s.reset_until=520;
 soc.mem_ready=1;soc.mem_error=0;soc.uart_rx_valid=0;soc.uart_rx_data=0;soc.sample_valid=0;soc.sample_time=0;soc.sample_x=0;soc.sample_y=0;soc.sample_pressure=0;soc.sample_flags=0;soc.sample_tool=0;soc.sample_buttons=0;soc.fb_ready=1;soc.fb_error=0;soc.fb_rdata=15;soc.panel_ready=1;soc.media_ready=1;soc.media_error=0;soc.external_media_busy=0;
}
Machine::~Machine(){if(medium>=0)close(medium);if(backing_capture>=0)close(backing_capture);}
void Machine::put(uint64_t addr,const uint8_t*data,size_t n){if(prepared)throw std::runtime_error("cannot preload running machine");if(addr>=RAM_BASE&&n<=RAM_SIZE&&addr-RAM_BASE<=RAM_SIZE-n)std::memcpy(s.ram.data()+addr-RAM_BASE,data,n);else if(addr>=ROM_BASE&&n<=s.rom.size()&&addr-ROM_BASE<=s.rom.size()-n)std::memcpy(s.rom.data()+addr-ROM_BASE,data,n);else throw std::runtime_error("preload outside declared RAM/ROM");}
void Machine::load_rom(const std::string&path){auto b=bytes(path);put(ROM_BASE,b.data(),b.size());}
void Machine::load_elf(const std::string&path){auto b=bytes(path);if(b.size()<sizeof(Elf64_Ehdr))throw std::runtime_error("short ELF");Elf64_Ehdr e;std::memcpy(&e,b.data(),sizeof(e));if(std::memcmp(e.e_ident,ELFMAG,SELFMAG)||e.e_ident[EI_CLASS]!=ELFCLASS64||e.e_ident[EI_DATA]!=ELFDATA2LSB||e.e_machine!=EM_RISCV)throw std::runtime_error("expected little endian RV64 ELF");if(e.e_phentsize!=sizeof(Elf64_Phdr)||e.e_phoff>b.size()||e.e_phnum>(b.size()-e.e_phoff)/sizeof(Elf64_Phdr))throw std::runtime_error("invalid ELF headers");for(unsigned i=0;i<e.e_phnum;i++){Elf64_Phdr p;std::memcpy(&p,b.data()+e.e_phoff+i*sizeof(p),sizeof(p));if(p.p_type!=PT_LOAD)continue;if(p.p_filesz>p.p_memsz||p.p_offset>b.size()||p.p_filesz>b.size()-p.p_offset||p.p_memsz>RAM_SIZE)throw std::runtime_error("invalid ELF segment");std::vector<uint8_t>seg(p.p_memsz);std::memcpy(seg.data(),b.data()+p.p_offset,p.p_filesz);put(p.p_paddr,seg.data(),seg.size());}}
void Machine::descriptor(const std::string&path){auto b=bytes(path);if(b.size()!=256)throw std::runtime_error("descriptor must be256bytes");std::memcpy(model->descriptor.data(),b.data(),256);}
void Machine::attach_backing(std::shared_ptr<BackingPlatform>platform){if(backing||s.medium_present)throw std::runtime_error("backing already attached");if(!platform||platform->capacity()!=512*MEDIUM_SECTORS)throw std::runtime_error("medium capacity mismatch");// Initial external bytes are sampled once before guest admission. Thereafter
 // snapshots use only accepted outcomes; they never contact a pending peer.
 std::map<uint64_t,std::array<uint8_t,512>> initial;
 std::array<uint8_t,1048576> chunk{};
 for(uint64_t first=0;first<MEDIUM_SECTORS;first+=chunk.size()/512){platform->passive_read(first*512,chunk.data(),chunk.size());for(size_t offset=0;offset<chunk.size();offset+=512)if(std::any_of(chunk.begin()+offset,chunk.begin()+offset+512,[](uint8_t v){return v!=0;})){std::array<uint8_t,512>b;std::memcpy(b.data(),chunk.data()+offset,512);initial[first+offset/512]=b;}}
 s.accepted_medium=std::move(initial);backing=std::move(platform);s.medium_present=true;}
void Machine::rebind_private_backing(std::shared_ptr<BackingPlatform>platform){
 if((s.backing_pending&&!backing_fork_suspended&&options.backing_replay_path.empty())||s.backing.poisoned||!s.isolated||!s.medium_present||!backing||!platform||platform->capacity()!=512*MEDIUM_SECTORS)throw std::runtime_error("private backing rebind requires matching isolated capacity");
 std::array<uint8_t,1048576>a{},b{};for(uint64_t offset=0;offset<512*MEDIUM_SECTORS;offset+=a.size()){backing->passive_read(offset,a.data(),a.size());platform->passive_read(offset,b.data(),b.size());if(a!=b)throw std::runtime_error("private backing rebind bytes differ");}
 backing=std::move(platform);if(medium>=0){close(medium);medium=-1;}if(!private_medium_path.empty()){unlink(private_medium_path.c_str());private_medium_path.clear();}
}
void Machine::open_medium(const std::string&path){if(medium>=0||backing)throw std::runtime_error("medium already open");int fd=open(path.c_str(),O_RDWR);if(fd<0)throw std::runtime_error("cannot open medium");try{attach_backing(std::make_shared<PosixBacking>(fd));}catch(...){close(fd);throw;}medium=fd;}
void Machine::prepare(){if(prepared)return;for(size_t p=0;p<s.ram.size();p+=4096)if(std::any_of(s.ram.begin()+p,s.ram.begin()+p+4096,[](uint8_t v){return v!=0;})){std::array<uint8_t,4096>b;std::memcpy(b.data(),s.ram.data()+p,4096);s.boot_pages[p/4096]=b;}prepared=true;}
void Machine::schedule(Event e){validate_event_fields(e);if(e.kind=="uart")hexbytes(e.payload);else if(!e.payload.empty())throw std::runtime_error("non-UART event has byte payload");if(e.cycle<s.cycle)throw std::runtime_error("event timestamp is in the past");if(s.input.size()-s.event_index>=MAX_EVENTS)throw std::runtime_error("external event queue full");uint64_t consumed=0;for(uint64_t i=0;i<s.event_index;i++)consumed+=s.input[i].payload.size();if(e.payload.size()>MAX_EVENT_PAYLOAD-(s.event_payload_bytes-consumed))throw std::runtime_error("event payload budget exceeded");if(s.event_index){s.input.erase(s.input.begin(),s.input.begin()+s.event_index);s.event_index=0;s.event_payload_bytes-=consumed;}auto position=std::upper_bound(s.input.begin(),s.input.end(),e.cycle,[](uint64_t c,const Event&v){return c<v.cycle;});s.input.insert(position,e);s.event_payload_bytes+=e.payload.size();if(input_capture){input_capture<<e.cycle<<' '<<e.kind;if(e.kind=="uart")input_capture<<' '<<e.payload;else for(auto w:e.words)input_capture<<' '<<w;input_capture<<'\n';}}
void Machine::schedule_all(const std::vector<Event>&list){if(list.size()>MAX_EVENTS)throw std::runtime_error("event queue full");uint64_t payload=0;for(auto&e:list){if(e.payload.size()>MAX_EVENT_PAYLOAD-payload)throw std::runtime_error("event payload budget exceeded");payload+=e.payload.size();}s.input=list;s.event_index=0;s.event_payload_bytes=payload;}
void Machine::initial_uart(const std::vector<uint8_t>&b){if(b.size()>MAX_UART-s.rx.size())throw std::runtime_error("UART queue full");s.rx.insert(s.rx.end(),b.begin(),b.end());if(input_capture&&!b.empty()){static const char*h="0123456789abcdef";input_capture<<s.cycle<<" uart ";for(auto v:b)input_capture<<h[v>>4]<<h[v&15];input_capture<<'\n';}}
void Machine::capture_backing(uint64_t tag,const std::vector<uint8_t>&wire){
 if(backing_capture<0)return;
 if(wire.size()+16>MAX_BACKING_LOG-backing_capture_bytes)throw std::runtime_error("backing outcome capture full");
 uint8_t header[16];for(int i=0;i<8;i++){header[i]=tag>>(8*i);header[8+i]=wire.size()>>(8*i);}
 if(pwrite(backing_capture,header,16,backing_capture_bytes)!=16||pwrite(backing_capture,wire.data(),wire.size(),backing_capture_bytes+16)!=ssize_t(wire.size()))throw std::runtime_error("backing outcome capture write failed");
 backing_capture_bytes+=wire.size()+16;
}
void Machine::observe_backing(const BackingRecord& record){
 const auto&r=record.request;const auto&o=record.outcome;
 if(r.kind==BackingKind::Barrier)return;
 for(uint64_t i=0;i<o.transferred;){auto address=r.offset+i,sector=address/512,within=address%512,count=std::min<uint64_t>(512-within,o.transferred-i);auto&b=s.accepted_medium[sector];std::copy_n(o.bytes.data()+i,count,b.data()+within);if(std::all_of(b.begin(),b.end(),[](uint8_t v){return !v;}))s.accepted_medium.erase(sector);i+=count;}
}
std::optional<BackingOutcome> Machine::backing_operation(BackingKind kind,uint64_t offset,uint64_t length,const uint8_t*data){
 if(!backing)throw std::runtime_error("no backing platform");
 if(!s.backing_pending){
  // Reserve both entries before admitting an irreversible external operation.
  if(backing_capture>=0&&160+3*length>MAX_BACKING_LOG-backing_capture_bytes)throw std::runtime_error("backing outcome capture full");
  auto request=begin_backing(s.backing,kind,s.cycle,offset,length,data);s.backing_pending=request;
  try{capture_backing(0,encode_backing_request(request));
   if(!options.backing_replay_path.empty()){
    if(!s.isolated||backing_replay_cursor>=backing_replay.size()||!equal_backing_request(request,backing_replay[backing_replay_cursor].record.request))throw std::runtime_error("backing replay request mismatch or missing outcome");
   }else backing->submit(request);
  }catch(...){s.backing.poisoned=true;throw;}
  s.backing_poll_cycle=s.cycle;
 }else{
  const auto&r=*s.backing_pending;if(r.kind!=kind||r.offset!=offset||r.length!=length||(kind==BackingKind::Write&&!std::equal(r.bytes.begin(),r.bytes.end(),data)))throw std::runtime_error("external medium owner changed under backpressure");
 }
 return poll_backing();
}
std::optional<BackingOutcome> Machine::poll_backing(){
 if(!s.backing_pending)return std::nullopt;
 if(s.cycle<s.backing_poll_cycle)return std::nullopt;
 try{
  std::optional<BackingOutcome>outcome;
  if(!options.backing_replay_path.empty()){
   const auto&r=backing_replay.at(backing_replay_cursor);
   if(s.cycle<r.accepted_boundary){if(s.cycle>UINT64_MAX-1000)throw std::runtime_error("backing poll clock exhausted");s.backing_poll_cycle=s.cycle+1000;return std::nullopt;}
   if(s.cycle!=r.accepted_boundary)throw std::runtime_error("backing replay completion boundary mismatch");
   outcome=r.record.outcome;backing->apply_recorded(*s.backing_pending,*outcome);
  }else outcome=backing->poll();
  if(!outcome){if(options.backing_replay_path.empty())s.backing_retry_ready=backing->retry_ready();if(s.cycle>UINT64_MAX-1000)throw std::runtime_error("backing poll clock exhausted");s.backing_poll_cycle=s.cycle+1000;return std::nullopt;}
  BackingRecord record{*s.backing_pending,*outcome};validate_backing_record(record);
  capture_backing(1,encode_timed_backing_record({record,s.cycle}));observe_backing(record);complete_backing(s.backing,record);
  s.backing_pending.reset();s.backing_poll_cycle=0;s.backing_retry_ready=false;if(!options.backing_replay_path.empty())backing_replay_cursor++;
  return outcome;
 }catch(...){s.backing.poisoned=true;throw;}
}
void Machine::abandon_media(){
 if(s.backing_pending)s.backing_orphan=true;
 s.media_active=s.media_kind=s.media_sector=s.flush_active=s.flush_cursor=0;
}
void Machine::retry_backing(){
 if(s.backing.poisoned||!s.backing_pending)throw std::runtime_error("no known pending external backing request");
 if(backing_fork_suspended)throw std::runtime_error("pending fork awaits captured external outcome tape");
 if(!s.backing_retry_ready)throw std::runtime_error("backing retry is not ready");
 if(options.backing_replay_path.empty()&&!backing->retry_pending())throw std::runtime_error("backing retry is not ready");
 s.backing_retry_ready=false;
}
void Machine::block_row(uint64_t c,const char*event,unsigned write,unsigned size,uint64_t address,uint64_t raw,uint64_t wdata,uint64_t rdata,unsigned error){if(!block_trace.is_open())return;if(s.block_rows>=4096){s.block_omitted++;return;}s.block_rows++;auto*r=model->rootp;block_trace<<c<<','<<event<<','<<write<<','<<size<<",0x"<<std::hex<<address<<",0x"<<raw<<",0x"<<wdata<<",0x"<<rdata<<std::dec<<','<<error<<','<<unsigned(r->lemma_soc__DOT__blockdev__DOT__state)<<','<<r->lemma_soc__DOT__blockdev__DOT__status<<','<<r->lemma_soc__DOT__blockdev__DOT__queue_num<<','<<r->lemma_soc__DOT__blockdev__DOT__queue_ready<<','<<r->lemma_soc__DOT__blockdev__DOT__interrupt_status<<','<<unsigned(r->lemma_soc__DOT__blockdev__DOT__result)<<'\n';}
void Machine::tick(){auto&soc=*model;uint64_t c=s.cycle;
  if(soc.power_cancel_pen){
   s.samples.clear();s.rx.clear();std::vector<Event> pending;
   for(size_t i=s.event_index;i<s.input.size();i++)if(s.input[i].kind=="button"||s.input[i].kind=="reset")pending.push_back(std::move(s.input[i]));
   s.input=std::move(pending);s.event_index=0;s.event_payload_bytes=0;
  }
  while(s.event_index<s.input.size()&&s.input[s.event_index].cycle<=c){auto e=s.input[s.event_index++];if(e.kind=="button"){s.button_level=e.words[0];}else if(e.kind=="uart"){if(soc.power_suspended)continue;auto b=hexbytes(e.payload);if(b.size()>MAX_UART-s.rx.size())throw std::runtime_error("UART queue full");s.rx.insert(s.rx.end(),b.begin(),b.end());}else if(e.kind=="reset"){s.reset_until=c+e.words[0];s.power_reset_cause=3;abandon_media();s.overlay.clear();s.optical_pending.clear();}else {if(soc.power_suspended)continue;if(s.samples.size()>=65536)throw std::runtime_error("pen adapter queue full");s.samples.push_back(e);}}
  soc.clk=0;soc.reset=c<s.reset_until;if(soc.reset)abandon_media();
  if(s.backing_orphan&&poll_backing())s.backing_orphan=false;
  soc.external_media_busy=s.backing_pending.has_value();soc.media_ready=0;soc.power_reset_cause=s.power_reset_cause;soc.raw_button_level=s.button_level;
  if(soc.reset){s.memory_pending=0;s.memory_wait=0;}
  if(s.memory_pending&&s.memory_wait)s.memory_wait--;
  soc.mem_ready=!s.memory_latency||(s.memory_pending&&!s.memory_wait);
  uint64_t boot_elapsed=c-s.boot_cycle;
  soc.preload_valid=soc.register_memory_enabled&&boot_elapsed<512;soc.preload_index=boot_elapsed&511;soc.preload_data=0;
  if(soc.preload_valid){uint64_t a=boot_elapsed<384?RAM_BASE+8*boot_elapsed:boot_elapsed<448?0x807ffe00+8*(boot_elapsed-384):0x81000000+8*(boot_elapsed-448);std::memcpy(&soc.preload_data,s.ram.data()+a-RAM_BASE,8);}
  soc.uart_rx_valid=!s.rx.empty();soc.uart_rx_data=s.rx.empty()?0:s.rx.front();soc.sample_valid=!s.samples.empty();
  if(!s.samples.empty()){auto&w=s.samples.front().words;soc.sample_time=w[0];soc.sample_x=w[1];soc.sample_y=w[2];soc.sample_pressure=w[3];soc.sample_flags=w[4];soc.sample_tool=w[5];soc.sample_buttons=w[6];}
  soc.eval();soc.mem_rdata=0;soc.mem_error=0;
  uint8_t* ram_pointer=nullptr;
  if(soc.mem_valid&&s.memory_latency){
   if(!s.memory_pending){s.memory_pending=1;s.memory_wait=s.memory_latency;s.memory_addr=soc.mem_addr;s.memory_write=soc.mem_write;s.memory_wdata=soc.mem_wdata;s.memory_strb=soc.mem_strb;soc.mem_ready=0;}
   else if(s.memory_addr!=soc.mem_addr||s.memory_write!=soc.mem_write||s.memory_wdata!=soc.mem_wdata||s.memory_strb!=soc.mem_strb)throw std::runtime_error("external memory owner changed under backpressure");
  }
  bool memory_completion=soc.mem_valid&&soc.mem_ready&&!soc.reset;
  if(soc.mem_valid){uint64_t addr=soc.mem_addr;if(addr>=RAM_BASE&&addr-RAM_BASE<=RAM_SIZE-8)ram_pointer=s.ram.data()+addr-RAM_BASE;else if(addr>=ROM_BASE&&addr-ROM_BASE<=s.rom.size()-8)ram_pointer=s.rom.data()+addr-ROM_BASE;else soc.mem_error=1;
   if(addr&7)soc.mem_error=1;
   if(ram_pointer){std::memcpy(&soc.mem_rdata,ram_pointer,8);if(soc.mem_write&&addr<ROM_BASE+s.rom.size())soc.mem_error=1;}}
  soc.fb_error=soc.fb_valid&&soc.fb_addr>=s.framebuffer.size();soc.fb_rdata=soc.fb_error?0:s.framebuffer[soc.fb_addr%s.framebuffer.size()];
  soc.media_error=0;for(int i=0;i<128;i++)soc.media_rdata[i]=0;
  if(soc.media_valid&&!soc.reset&&!s.backing_orphan){
   uint64_t sector=soc.media_sector;if(!s.media_active){s.media_active=1;s.media_kind=soc.media_kind;s.media_sector=sector;s.media_requests++;}
   else if(s.media_kind!=soc.media_kind||s.media_sector!=sector)throw std::runtime_error("RTL medium request changed under backpressure");
   bool complete=true;
   if(!s.medium_present||sector>=MEDIUM_SECTORS)soc.media_error=1;
   else if(soc.media_kind==0){auto a=s.overlay.find(sector);
    if(a!=s.overlay.end())std::memcpy(soc.media_rdata.data(),a->second.data(),512);
    else{auto outcome=backing_operation(BackingKind::Read,sector*512,512);complete=outcome.has_value();if(outcome){soc.media_error=outcome->error||outcome->transferred!=512;if(!soc.media_error)std::memcpy(soc.media_rdata.data(),outcome->bytes.data(),512);}}
   }else if(soc.media_kind==1){std::array<uint8_t,512>b{};std::memcpy(b.data(),soc.media_wdata.data(),512);if(!s.overlay.count(sector)&&s.overlay.size()>=32768)soc.media_error=1;else s.overlay[sector]=b;}
   else if(soc.media_kind==4){
    if(!s.flush_active){s.flushes++;s.flush_active=1;s.flush_cursor=0;}
    if(s.fail_flush&&s.flushes==s.fail_flush)soc.media_error=1;
    else{
     auto a=s.overlay.lower_bound(s.flush_cursor);
     while(a!=s.overlay.end()){
      auto outcome=backing_operation(BackingKind::Write,a->first*512,512,a->second.data());
      if(!outcome){complete=false;break;}
      if(outcome->error||outcome->transferred!=512){soc.media_error=1;break;}
      s.flush_cursor=a->first+1;a=s.overlay.lower_bound(s.flush_cursor);
     }
     if(complete&&!soc.media_error){auto outcome=backing_operation(BackingKind::Barrier,0,0);complete=outcome.has_value();if(outcome)soc.media_error=outcome->error;}
     if(complete&&!soc.media_error)s.overlay.clear();
    }
   }else soc.media_error=1;
   if(complete){soc.media_ready=1;s.media_active=s.media_kind=s.media_sector=s.flush_active=s.flush_cursor=0;
    block_row(c,soc.media_kind==0?"media-read":soc.media_kind==1?"media-write":soc.media_kind==4?"media-flush":"media-invalid",soc.media_kind==1,9,sector,0,0,0,soc.media_error);
   }
  }
  soc.external_media_busy=s.backing_pending.has_value();
  soc.eval();
  if(!soc.reset){
   auto*r=soc.rootp;
   if(block_trace.is_open()){
    uint64_t state=(uint64_t(r->lemma_soc__DOT__blockdev__DOT__state)<<32)|r->lemma_soc__DOT__blockdev__DOT__status;
    if(state!=s.previous_block_state){block_row(c,"state",0,0,0,0,0,0,0);s.previous_block_state=state;}
    if(r->lemma_soc__DOT____Vcellinp__blockdev__valid&&r->lemma_soc__DOT__compute__DOT__hready)
     block_row(c,"mmio",r->lemma_soc__DOT__compute__DOT__write_d,r->lemma_soc__DOT__compute__DOT__size_d,r->lemma_soc__DOT__compute__DOT__addr_d,r->lemma_soc__DOT__compute__DOT__core__DOT__LSUHWDATA,r->lemma_soc__DOT____Vcellinp__blockdev__wdata,r->lemma_soc__DOT__compute__DOT__hrdata,r->lemma_soc__DOT__compute__DOT__hresp);
    if(r->lemma_soc__DOT__dma_valid&&r->lemma_soc__DOT__dma_ready)
     // This observer is limited to the external-memory configuration: its
     // response error is the actual host s.input. selected_fault is the retained
     // RTL rejection for the active beat, including held-owner semantics.
     block_row(c,"dma",soc.mem_write,r->lemma_soc__DOT__dma_size,r->lemma_soc__DOT__dma_addr,soc.mem_wdata,soc.mem_wdata>>(8*(r->lemma_soc__DOT__dma_addr&7)),r->lemma_soc__DOT__dma_rdata,r->lemma_soc__DOT__selected_fault||soc.mem_error);
   }
   if(!soc.register_memory_enabled&&soc.mem_valid&&soc.mem_ready&&soc.mem_write&&!soc.mem_error&&ram_pointer)for(int j=0;j<8;j++)if(soc.mem_strb&(1<<j))ram_pointer[j]=soc.mem_wdata>>(j*8);
   if(soc.fb_valid&&soc.fb_ready&&!soc.fb_error){
    if(soc.fb_write){s.framebuffer[soc.fb_addr]=soc.fb_wdata;s.fb_writes++;}
    else s.fb_reads++;
   }
   if(soc.uart_tx_valid){uart.put(soc.uart_tx_data);s.uart_text.push_back(soc.uart_tx_data);if(s.uart_text.size()>65536)s.uart_text.erase(0,32768);if(!options.quiet_uart){std::cout.put(soc.uart_tx_data);}}
   if(soc.uart_rx_ready&&!s.rx.empty())s.rx.pop_front();if(soc.sample_valid&&soc.sample_ready&&!s.samples.empty()){s.samples.pop_front();s.pen_ingress++;}
   if(soc.sample_accepted)s.pen_accepted++;
   // Passive digital-port observation. The synthetic phase program is in
   // circuitry; this adapter does not infer electrophoretic response.
   if(soc.panel_drive_valid){
    if(soc.panel_drive_phase>=3||soc.panel_drive_x>=BINDING_WIDTH||soc.panel_drive_y>=BINDING_HEIGHT||soc.panel_drive_code>3)throw std::runtime_error("invalid digital panel beat");
    s.drive_clocks++;if(soc.panel_source_clock){s.drive_pixels++;s.drive_phases[soc.panel_drive_phase]++;
    for(uint64_t field:{uint64_t(soc.panel_drive_phase),uint64_t(soc.panel_drive_x),uint64_t(soc.panel_drive_y),uint64_t(soc.panel_drive_code)})for(int i=0;i<8;i++){s.drive_hash^=uint8_t(field>>(i*8));s.drive_hash*=1099511628211ULL;}}
    if(drive_trace&&s.drive_clocks<=1000000){uint8_t b[28];for(int i=0;i<8;i++){b[i]=c>>(8*i);b[8+i]=soc.panel_sequence>>(8*i);}for(int i=0;i<4;i++){b[16+i]=soc.panel_drive_x>>(8*i);b[20+i]=soc.panel_drive_y>>(8*i);}b[24]=soc.panel_drive_phase;b[25]=soc.panel_drive_code;b[26]=soc.panel_power_enable;b[27]=soc.panel_gate_clock|(soc.panel_source_clock<<1);drive_trace.write(reinterpret_cast<const char*>(b),sizeof(b));}
   }
   if(soc.panel_valid&&soc.panel_ready){if(soc.panel_x>=BINDING_WIDTH||soc.panel_y>=BINDING_HEIGHT)throw std::runtime_error("controller pixel out of bounds");s.panel_pixels++;s.optical_pending[soc.panel_y*BINDING_WIDTH+soc.panel_x]=soc.panel_gray;if(panel_log)panel_log<<c<<",pixel,"<<soc.panel_sequence<<","<<soc.panel_x<<","<<soc.panel_y<<","<<unsigned(soc.panel_gray)<<"\n";}
   if(soc.panel_complete){for(auto&[i,v]:s.optical_pending)s.visible[i]=v;s.optical_pending.clear();s.panel_completed++;if(panel_log)panel_log<<c<<",complete,"<<soc.panel_sequence<<",0,0,0\n";}
   if(soc.panel_abort){s.optical_pending.clear();s.panel_aborted++;if(panel_log)panel_log<<c<<",abort,"<<soc.panel_sequence<<",0,0,0\n";}
   if(soc.finish_valid){s.finished=true;s.finish=soc.finish_code;}if(soc.debug_retire)s.retired++;
   s.privilege_cycles[soc.debug_privilege]++;if(soc.debug_privilege!=s.old_privilege){s.transitions++;s.old_privilege=soc.debug_privilege;}
   if(soc.debug_trap){s.traps++;if(soc.debug_cause==0x8000000000000007ULL)s.timer_traps++;}
   if(trace&&c<options.trace_limit)trace<<c<<",0x"<<std::hex<<soc.debug_pc<<std::dec<<","<<unsigned(soc.debug_privilege)<<","<<unsigned(soc.debug_retire)<<","<<unsigned(soc.debug_trap)<<",0x"<<std::hex<<soc.debug_cause<<std::dec<<","<<unsigned(soc.mem_valid)<<","<<unsigned(soc.mem_write)<<",0x"<<std::hex<<soc.mem_addr<<std::dec<<","<<soc.timer_ticks<<"\n";
  }
  soc.clk=1;soc.eval();
 if(memory_completion){s.memory_pending=0;s.memory_wait=0;}
 context->timeInc(2);s.cycle++;
 s.stopped=(!s.stop_marker.empty()&&s.uart_text.find(s.stop_marker)!=std::string::npos)||(s.stop_panels&&s.panel_completed>=s.stop_panels)||(s.observer_cycle&&s.cycle>=s.observer_cycle);
}
uint64_t Machine::run(uint64_t count){if(backing_fork_suspended)throw std::runtime_error("pending fork awaits captured external outcome tape; virtual clock unchanged");if(s.backing.poisoned)throw std::runtime_error("backing owner poisoned by ambiguous execution/capture");if(!count||count>1000000000)throw std::runtime_error("run interval must be1..1000000000cycles");if(s.cycle>UINT64_MAX/2||count>UINT64_MAX/2-s.cycle)throw std::runtime_error("virtual clock exhausted");prepare();s.stopped=false;auto begin=std::chrono::steady_clock::now();uint64_t first=s.cycle;while(s.cycle-first<count&&!s.finished&&!s.stopped){tick();if((s.cycle&0x3ffff)==0&&std::chrono::steady_clock::now()-begin>std::chrono::seconds(options.deadline))throw std::runtime_error("RTL wall deadline exceeded");}uart.flush();trace.flush();panel_log.flush();block_trace.flush();input_capture.flush();drive_trace.flush();if(!options.quiet_uart)std::cout.flush();if(!uart)throw std::runtime_error("UART output failed");return s.cycle-first;}
void Machine::warm_reset(uint64_t length){if(!length||length>1000000||s.cycle>std::numeric_limits<uint64_t>::max()-length)throw std::runtime_error("invalid reset interval");s.reset_until=s.cycle+length;abandon_media();s.power_reset_cause=2;s.memory_pending=0;s.memory_wait=0;s.finished=false;s.stopped=false;s.finish=0;s.samples.clear();s.input.clear();s.event_index=0;s.event_payload_bytes=0;s.rx.clear();s.optical_pending.clear();std::fill(s.framebuffer.begin(),s.framebuffer.end(),15);}
void Machine::cold_cycle(){prepare();s.boot_cycle=s.cycle;std::fill(s.ram.begin(),s.ram.end(),0);for(auto&[p,b]:s.boot_pages)std::memcpy(s.ram.data()+4096*p,b.data(),4096);s.overlay.clear();s.samples.clear();s.input.clear();s.event_index=0;s.event_payload_bytes=0;s.rx.clear();warm_reset(model->register_memory_enabled?520:8);s.power_reset_cause=1;s.button_level=0;}
void Machine::panel(const std::string&path)const{std::ofstream f(path,std::ios::binary);if(!f)throw std::runtime_error("cannot open panel output");f<<"P5\n"<<BINDING_WIDTH<<' '<<BINDING_HEIGHT<<"\n255\n";for(auto v:s.visible)f.put(v*17);if(!f.flush())throw std::runtime_error("panel output failed");}
void Machine::ram_dump(uint64_t address,uint64_t size,const std::string&path)const{if(model->register_memory_enabled||!size||size>1048576||address<RAM_BASE||address-RAM_BASE>RAM_SIZE-size)throw std::runtime_error("RAM dump requires1..1048576external RAM bytes");std::ofstream f(path,std::ios::binary);if(!f.write(reinterpret_cast<const char*>(s.ram.data()+address-RAM_BASE),size)||!f.flush())throw std::runtime_error("RAM dump failed");}
std::string Machine::inspect()const{std::ostringstream r;auto*root=model->rootp;r<<"{\"backend\":\"rtl\",\"snapshot_identity\":\""<<LEMMA_RUNTIME_IDENTITY<<"\",\"cycle\":"<<s.cycle<<",\"ticks\":"<<model->timer_ticks<<",\"pc\":"<<model->debug_pc<<",\"privilege\":"<<unsigned(model->debug_privilege)<<",\"retired\":"<<s.retired<<",\"finished\":"<<(s.finished?"true":"false")<<",\"finish_code\":"<<s.finish<<",\"isolated_medium\":"<<(s.isolated?"true":"false")<<",\"private_medium_path\":"<<json_string(private_medium_path)<<",\"volatile_sectors\":"<<s.overlay.size()<<",\"flushes\":"<<s.flushes<<",\"fail_flush\":"<<s.fail_flush<<",\"stop_panels\":"<<s.stop_panels<<",\"observer_cycle\":"<<s.observer_cycle<<",\"event_queue\":"<<s.input.size()-s.event_index<<",\"pen_queue\":"<<s.samples.size()<<",\"uart_queue\":"<<s.rx.size()<<",\"panel_pending_pixels\":"<<s.optical_pending.size()<<",\"drive_clocks\":"<<s.drive_clocks<<",\"drive_pixels\":"<<s.drive_pixels<<",\"drive_hash\":"<<s.drive_hash<<",\"drive_phase_counts\":["<<s.drive_phases[0]<<","<<s.drive_phases[1]<<","<<s.drive_phases[2]<<"],\"panel_power\":"<<unsigned(model->panel_power_enable)<<",\"panel_completed\":"<<s.panel_completed<<",\"panel_sequence\":"<<model->panel_sequence<<",\"paper_busy\":"<<unsigned(root->lemma_soc__DOT__paper__DOT__busy)<<",\"block_state\":"<<unsigned(root->lemma_soc__DOT__blockdev__DOT__state)<<",\"memory_latency\":"<<s.memory_latency<<",\"memory_pending\":"<<s.memory_pending<<",\"memory_wait\":"<<s.memory_wait<<",\"dma_outstanding\":"<<unsigned(root->lemma_soc__DOT__port_held)<<",\"backing_io\":{\"next_id\":"<<s.backing.next_id<<",\"completed\":"<<s.backing.completed<<",\"durable_barrier\":"<<s.backing.durable_barrier<<",\"observed_write\":"<<s.backing.observed_write<<",\"phase\":"<<uint64_t(s.backing.phase)<<",\"retry_ready\":"<<(s.backing_retry_ready?"true":"false")<<",\"fork_suspended\":"<<(backing_fork_suspended?"true":"false")<<",\"orphan\":"<<(s.backing_orphan?"true":"false")<<",\"poisoned\":"<<(s.backing.poisoned?"true":"false")<<"},\"power\":{\"enabled\":"<<(BINDING_POWER_ENABLED?"true":"false")<<",\"state\":"<<unsigned(model->power_suspended)<<",\"error\":"<<model->power_error<<",\"reset_cause\":"<<unsigned(model->power_cause)<<",\"button_level\":"<<s.button_level<<",\"events\":"<<model->power_events<<",\"epoch\":"<<model->power_epoch<<",\"wake_cause\":"<<model->power_wake_cause<<"}}";return r.str();}
void Machine::report(const std::string&path)const{std::ofstream r(path);r<<"{\n\"block_rows\":"<<s.block_rows<<",\"block_omitted\":"<<s.block_omitted<<",\"cycles\":"<<s.cycle<<",\"retired\":"<<s.retired<<",\"privilege_cycles\":["<<s.privilege_cycles[0]<<","<<s.privilege_cycles[1]<<","<<s.privilege_cycles[2]<<","<<s.privilege_cycles[3]<<"],\"privilege_transitions\":"<<s.transitions<<",\"traps\":"<<s.traps<<",\"timer_traps\":"<<s.timer_traps<<",\"pen_ingress\":"<<s.pen_ingress<<",\"pen_accepted\":"<<s.pen_accepted<<",\"fb_reads\":"<<s.fb_reads<<",\"fb_writes\":"<<s.fb_writes<<",\"panel_pixels\":"<<s.panel_pixels<<",\"drive_clocks\":"<<s.drive_clocks<<",\"drive_pixels\":"<<s.drive_pixels<<",\"drive_hash\":"<<s.drive_hash<<",\"drive_phase_counts\":["<<s.drive_phases[0]<<","<<s.drive_phases[1]<<","<<s.drive_phases[2]<<"],\"panel_power\":"<<unsigned(model->panel_power_enable)<<",\"panel_completed\":"<<s.panel_completed<<",\"panel_aborted\":"<<s.panel_aborted<<",\"media_requests\":"<<s.media_requests<<",\"flushes\":"<<s.flushes<<",\"volatile_sectors_discarded\":"<<s.overlay.size()<<",\"finished\":"<<(s.finished?"true":"false")<<",\"explicit_observer_stop\":"<<(s.stopped?"true":"false")<<",\"observer_cycle\":"<<options.observer_cycle<<",\"finish_code\":"<<s.finish<<"\n}\n";if(!r.flush())throw std::runtime_error("report write failed");}
// Checkpoint container v2: bounded lengths and CRC64-ECMA integrity (not
// authentication). Every byte is verified before allocating decoded machine
// state or applying the implementation-specific Verilator serialization.
namespace {
struct Writer { std::ostream&f;void raw(const void*p,size_t n){if(!f.write(static_cast<const char*>(p),n))throw std::runtime_error("checkpoint write failed");}void u64(uint64_t n){uint8_t b[8];for(int i=0;i<8;i++)b[i]=n>>(8*i);raw(b,8);}void str(const std::string&v){u64(v.size());raw(v.data(),v.size());}void vec(const std::vector<uint8_t>&v){u64(v.size());raw(v.data(),v.size());} };
struct Reader { std::istream&f;uint64_t remaining;bool validate;void raw(void*p,size_t n){if(n>remaining)throw std::runtime_error("truncated checkpoint state");if(p){if(!f.read(static_cast<char*>(p),n))throw std::runtime_error("checkpoint read failed");}else{f.seekg(n,std::ios::cur);if(!f)throw std::runtime_error("checkpoint skip failed");}remaining-=n;}uint64_t u64(){uint8_t b[8];raw(b,8);uint64_t n=0;for(int i=0;i<8;i++)n|=uint64_t(b[i])<<(8*i);return n;}uint64_t count(uint64_t maximum){auto n=u64();if(n>maximum)throw std::runtime_error("checkpoint length exceeds state bound");return n;}std::string str(uint64_t maximum){auto n=count(maximum);std::string v;if(!validate)v.resize(n);raw(validate?nullptr:v.data(),n);return v;}void vec(std::vector<uint8_t>&v,uint64_t expected){if(u64()!=expected)throw std::runtime_error("checkpoint memory geometry mismatch");if(!validate)v.resize(expected);raw(validate?nullptr:v.data(),expected);} };
uint64_t crc(std::istream&f,uint64_t n){static std::array<uint64_t,256>table=[](){std::array<uint64_t,256>t{};for(unsigned i=0;i<256;i++){uint64_t x=uint64_t(i)<<56;for(int k=0;k<8;k++)x=(x<<1)^((x>>63)?0x42f0e1eba9ea3693ULL:0);t[i]=x;}return t;}();uint64_t c=0;std::array<char,65536>b;while(n){size_t q=std::min<uint64_t>(n,b.size());if(!f.read(b.data(),q))throw std::runtime_error("checkpoint checksum read failed");for(size_t i=0;i<q;i++)c=(c<<8)^table[((c>>56)^uint8_t(b[i]))&255];n-=q;}return c;}
uint64_t length(const std::string&p){struct stat st{};if(stat(p.c_str(),&st)||st.st_size<0)throw std::runtime_error("cannot stat checkpoint component");return st.st_size;}
struct Temp { std::string path; explicit Temp(const std::string&prefix){std::string p=prefix+".XXXXXX";std::vector<char>b(p.begin(),p.end());b.push_back(0);int fd=mkstemp(b.data());if(fd<0)throw std::runtime_error("cannot create checkpoint temporary");close(fd);path=b.data();}~Temp(){unlink(path.c_str());} };
struct PrivateCapture {
 int fd=-1;std::string path;bool retained=false;
 ~PrivateCapture(){if(fd>=0)close(fd);if(!retained&&!path.empty())unlink(path.c_str());}
 void create(const std::string&base,uint64_t branch,const std::optional<BackingRequest>&pending){std::string pattern=base+".fork-"+std::to_string(branch)+"-XXXXXX";std::vector<char>name(pattern.begin(),pattern.end());name.push_back(0);fd=mkstemp(name.data());if(fd<0)throw std::runtime_error("cannot create private backing capture");path=name.data();backing_header(fd);if(pending){auto wire=encode_backing_request(*pending);uint8_t entry[16]{};for(int i=0;i<8;i++)entry[8+i]=wire.size()>>(8*i);if(write(fd,entry,16)!=16||write(fd,wire.data(),wire.size())!=ssize_t(wire.size()))throw std::runtime_error("private pending capture failed");}}
};
struct PrivateMedium {
 int fd=-1;std::string path;bool retained=false;
 ~PrivateMedium(){if(fd>=0)close(fd);if(!retained&&!path.empty())unlink(path.c_str());}
 void create(const std::string&directory,const std::map<uint64_t,std::array<uint8_t,512>>&base){
  if(directory.empty())throw std::runtime_error("restoring a medium requires --fork-directory");
  auto root=std::filesystem::canonical(directory);if(!std::filesystem::is_directory(root))throw std::runtime_error("fork directory is not a directory");
  std::string pattern=(root/"medium-fork-XXXXXX").string();std::vector<char>name(pattern.begin(),pattern.end());name.push_back(0);fd=mkstemp(name.data());if(fd<0)throw std::runtime_error("cannot exclusively create private medium");path=name.data();
  if(flock(fd,LOCK_EX|LOCK_NB)||ftruncate(fd,MEDIUM_SECTORS*512))throw std::runtime_error("cannot lock or size private medium");
  for(auto&[sector,b]:base)if(pwrite(fd,b.data(),512,sector*512)!=512)throw std::runtime_error("private medium initialization failed");
  if(fsync(fd))throw std::runtime_error("private medium initialization barrier failed");
  // Retain the newly created name across host crashes as well as closing the
  // session. The volatile overlay has never been written to this file.
  int dirfd=open(root.c_str(),O_RDONLY|O_DIRECTORY);if(dirfd<0)throw std::runtime_error("cannot open private medium directory");int failed=fsync(dirfd);close(dirfd);if(failed)throw std::runtime_error("private medium directory barrier failed");
 }
};
void copy_bytes(std::istream&in,std::ostream&out,uint64_t n){std::array<char,65536>b;while(n){size_t q=std::min<uint64_t>(n,b.size());if(!in.read(b.data(),q)||!out.write(b.data(),q))throw std::runtime_error("checkpoint copy failed");n-=q;}}
#define STATE_SCALARS(X) X(event_index) X(cycle) X(reset_until) X(boot_cycle) X(drive_clocks) X(drive_pixels) X(drive_hash) X(retired) X(traps) X(timer_traps) X(flushes) X(media_requests) X(pen_ingress) X(pen_accepted) X(panel_completed) X(panel_aborted) X(fb_reads) X(fb_writes) X(panel_pixels) X(transitions) X(block_rows) X(block_omitted) X(previous_block_state) X(fail_flush) X(stop_panels) X(observer_cycle) X(memory_latency) X(memory_pending) X(memory_wait) X(memory_addr) X(memory_write) X(memory_wdata) X(memory_strb) X(button_level) X(power_reset_cause) X(media_active) X(media_kind) X(media_sector) X(flush_active) X(flush_cursor) X(backing_poll_cycle) X(backing_orphan) X(backing_retry_ready)
void write_event(Writer&w,const Event&e){w.u64(e.cycle);w.str(e.kind);w.u64(e.words.size());for(auto v:e.words)w.u64(v);w.str(e.payload);}
Event read_event(Reader&r,uint64_t&payload_budget){Event e;e.cycle=r.u64(); // Kind is read even during preflight; only bounded data strings may be skipped.
 bool pre=r.validate;r.validate=false;e.kind=r.str(8);r.validate=pre;auto n=r.count(7);for(uint64_t i=0;i<n;i++){auto v=r.u64();e.words.push_back(v);}auto before=r.remaining;e.payload=r.str(std::min<uint64_t>(2*MAX_UART,payload_budget));auto payload_size=before-r.remaining-8;payload_budget-=payload_size;if(e.kind!="uart"&&payload_size)throw std::runtime_error("non-UART checkpoint byte payload");validate_event_fields(e);if(!pre&&e.kind=="uart")hexbytes(e.payload);return e;}
template<size_t N>void write_map(Writer&w,const std::map<uint64_t,std::array<uint8_t,N>>&m){w.u64(m.size());for(auto&[i,b]:m){w.u64(i);w.raw(b.data(),N);}}
template<size_t N>void read_map(Reader&r,std::map<uint64_t,std::array<uint8_t,N>>&m,uint64_t max_count,uint64_t max_key){auto n=r.count(max_count);uint64_t prior=0;for(uint64_t j=0;j<n;j++){auto i=r.u64();if(i>=max_key||(j&&i<=prior))throw std::runtime_error("invalid checkpoint sector/page index");prior=i;std::array<uint8_t,N>b{};r.raw(r.validate?nullptr:b.data(),N);if(!r.validate)m[i]=b;}}
void write_state(Writer&w,const State&s){
#define PUT(n) w.u64(s.n);
 STATE_SCALARS(PUT)
#undef PUT
 for(auto v:s.drive_phases)w.u64(v);for(auto v:s.privilege_cycles)w.u64(v);w.u64(s.old_privilege);w.u64(s.finished);w.u64(s.stopped);w.u64(s.finish);w.u64(s.medium_present);w.str(s.uart_text);w.str(s.stop_marker);w.vec(s.ram);w.vec(s.rom);w.vec(s.framebuffer);w.vec(s.visible);write_map(w,s.boot_pages);write_map(w,s.overlay);write_map(w,s.accepted_medium);w.u64(s.optical_pending.size());for(auto&[i,v]:s.optical_pending){w.u64(i);w.u64(v);}w.u64(s.rx.size());for(auto v:s.rx)w.raw(&v,1);w.u64(s.input.size());for(auto&e:s.input)write_event(w,e);w.u64(s.samples.size());for(auto&e:s.samples)write_event(w,e);w.u64(s.backing.next_id);w.u64(s.backing.completed);w.u64(s.backing.durable_barrier);w.u64(s.backing.observed_write);w.u64(uint64_t(s.backing.phase));w.u64(s.backing.poisoned);w.u64(s.backing_pending.has_value());if(s.backing_pending){auto wire=encode_backing_request(*s.backing_pending);w.vec(wire);}
}
void read_state(Reader&r,State&s){
#define GET(n) s.n=r.u64();
 STATE_SCALARS(GET)
#undef GET
 for(auto&v:s.drive_phases)v=r.u64();for(auto&v:s.privilege_cycles)v=r.u64();auto p=r.u64(),f=r.u64(),st=r.u64(),finish=r.u64(),present=r.u64();if(p>3||f>1||st>1||finish>UINT32_MAX||present>1||s.cycle>UINT64_MAX/2||s.boot_cycle>s.cycle||s.block_rows>4096||s.memory_latency>1024||s.memory_pending>1||s.memory_wait>s.memory_latency||s.memory_write>1||s.memory_strb>255||s.button_level>1||s.power_reset_cause<1||s.power_reset_cause>3||s.media_active>1||s.flush_active>1||s.flush_cursor>MEDIUM_SECTORS||s.media_kind>7||s.media_sector>=MEDIUM_SECTORS||(s.flush_active&&(!s.media_active||s.media_kind!=4)))throw std::runtime_error("invalid checkpoint scalar state");s.old_privilege=p;s.finished=f;s.stopped=st;s.finish=finish;s.medium_present=present;s.uart_text=r.str(MAX_UART);s.stop_marker=r.str(65536);r.vec(s.ram,RAM_SIZE);r.vec(s.rom,BINDING_ROM_BYTES);r.vec(s.framebuffer,2*BINDING_WIDTH*BINDING_HEIGHT);r.vec(s.visible,BINDING_WIDTH*BINDING_HEIGHT);read_map(r,s.boot_pages,RAM_SIZE/4096,RAM_SIZE/4096);read_map(r,s.overlay,32768,MEDIUM_SECTORS);read_map(r,s.accepted_medium,MEDIUM_SECTORS,MEDIUM_SECTORS);auto n=r.count(BINDING_WIDTH*BINDING_HEIGHT);uint64_t prior=0;for(uint64_t j=0;j<n;j++){auto i=r.u64(),v=r.u64();if(i>=BINDING_WIDTH*BINDING_HEIGHT||v>15||(j&&i<=prior))throw std::runtime_error("invalid checkpoint optical state");prior=i;if(!r.validate)s.optical_pending[i]=v;}n=r.count(MAX_UART);for(uint64_t i=0;i<n;i++){uint8_t v;r.raw(&v,1);if(!r.validate)s.rx.push_back(v);}n=r.count(MAX_EVENTS);if(s.event_index>n)throw std::runtime_error("invalid checkpoint event cursor");prior=0;uint64_t payload_budget=MAX_EVENT_PAYLOAD;for(uint64_t i=0;i<n;i++){auto e=read_event(r,payload_budget);if(i&&e.cycle<prior)throw std::runtime_error("checkpoint events out of order");if(i>=s.event_index&&e.cycle<s.cycle)throw std::runtime_error("checkpoint pending event in past");prior=e.cycle;if(!r.validate)s.input.push_back(std::move(e));}n=r.count(65536);for(uint64_t i=0;i<n;i++){auto e=read_event(r,payload_budget);if(e.kind!="pen")throw std::runtime_error("invalid checkpoint pen adapter queue");if(!r.validate)s.samples.push_back(std::move(e));}s.backing.next_id=r.u64();s.backing.completed=r.u64();s.backing.durable_barrier=r.u64();s.backing.observed_write=r.u64();s.backing.phase=BackingPhase(r.u64());auto poisoned=r.u64();if(poisoned>1)throw std::runtime_error("invalid backing poison state");s.backing.poisoned=poisoned;validate_backing_state(s.backing);auto pending=r.u64();if(pending>1)throw std::runtime_error("invalid pending backing flag");if(pending){auto n=r.count(512+48);std::vector<uint8_t> wire(n);r.raw(wire.data(),n);s.backing_pending=decode_backing_request(wire.data(),n);const auto&q=*s.backing_pending;if(q.id!=s.backing.next_id-1||q.boundary>s.cycle||q.offset>MEDIUM_SECTORS*512-q.length||q.length>512||s.backing_poll_cycle<s.cycle)throw std::runtime_error("invalid pending backing request boundary or capacity");}
 if(s.backing.poisoned||s.backing_orphan>1||s.backing_retry_ready>1||pending!=(s.backing.phase==BackingPhase::Pending)||(!pending&&(s.backing_poll_cycle||s.backing_orphan||s.backing_retry_ready)))throw std::runtime_error("invalid checkpoint external ownership state");s.event_payload_bytes=MAX_EVENT_PAYLOAD-payload_budget;if(r.remaining)throw std::runtime_error("trailing checkpoint wrapper state");s.isolated=true;
}
}
void Machine::model_save(const std::string&path){VerilatedSave f;f.open(path);if(!f.isOpen())throw std::runtime_error("cannot open model checkpoint");f<<*model;f.close();}
void Machine::snapshot(const std::string&path){if(backing_capture>=0&&fsync(backing_capture))throw std::runtime_error("backing capture checkpoint barrier failed");if(s.backing.poisoned)throw std::runtime_error("ambiguous backing operation cannot be checkpointed");prepare();Temp wrapper(path+".wrapper"),rtl(path+".model"),output(path+".partial");
 // Completed rising-edge observation: no platform read, poll, drain or flush.
 // accepted_medium includes observed partial writes independently of durability.
 {std::ofstream f(wrapper.path,std::ios::binary);Writer w{f};write_state(w,s);if(!f.flush())throw std::runtime_error("wrapper checkpoint failed");}model_save(rtl.path);
 uint64_t wn=length(wrapper.path),mn=length(rtl.path);std::ifstream wf(wrapper.path,std::ios::binary),mf(rtl.path,std::ios::binary);auto wc=crc(wf,wn),mc=crc(mf,mn);wf.clear();wf.seekg(0);mf.clear();mf.seekg(0);std::ofstream out(output.path,std::ios::binary);Writer w{out};w.raw("LMSSRTL1",8);w.u64(2);w.raw(LEMMA_RUNTIME_IDENTITY,64);w.u64(wn);w.u64(mn);w.u64(wc);w.u64(mc);copy_bytes(wf,out,wn);copy_bytes(mf,out,mn);if(!out.flush())throw std::runtime_error("checkpoint output failed");out.close();int snapshot_fd=open(output.path.c_str(),O_RDONLY);if(snapshot_fd<0||fsync(snapshot_fd)){if(snapshot_fd>=0)close(snapshot_fd);throw std::runtime_error("checkpoint barrier failed");}close(snapshot_fd);
#ifdef __EMSCRIPTEN__
 // MEMFS has no hard-link implementation. This exports an observational
 // artifact only; it is not the browser medium's persistence barrier.
 int destination_fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);if(destination_fd<0)throw std::runtime_error("checkpoint destination exists or cannot be created");
 int source_fd=open(output.path.c_str(),O_RDONLY);try{if(source_fd<0)throw std::runtime_error("cannot read checkpoint publication source");std::array<uint8_t,65536>buffer{};uint64_t remaining=length(output.path);while(remaining){auto count=std::min<uint64_t>(remaining,buffer.size());ssize_t n=read(source_fd,buffer.data(),count);if(n<=0)throw std::runtime_error("checkpoint publication read failed");uint64_t done=0;while(done<uint64_t(n)){ssize_t written=write(destination_fd,buffer.data()+done,n-done);if(written<=0)throw std::runtime_error("checkpoint publication write failed");done+=written;}remaining-=n;}if(fsync(destination_fd))throw std::runtime_error("checkpoint publication failed");close(source_fd);source_fd=-1;if(close(destination_fd)){destination_fd=-1;throw std::runtime_error("checkpoint publication close failed");}destination_fd=-1;}catch(...){if(source_fd>=0)close(source_fd);if(destination_fd>=0)close(destination_fd);unlink(path.c_str());throw;}
#else
 if(link(output.path.c_str(),path.c_str()))throw std::runtime_error("checkpoint destination exists or cannot be created");
#endif
}
void Machine::restore(const std::string&path){if(s.backing_pending||s.backing.poisoned)throw std::runtime_error("cannot discard a pending or ambiguous external operation during restore");uint64_t total=length(path);if(total<112||total>768ULL*1024*1024)throw std::runtime_error("invalid checkpoint container length");std::ifstream f(path,std::ios::binary);Reader head{f,total,false};char magic[8],identity[64];head.raw(magic,8);auto version=head.u64();head.raw(identity,64);auto wn=head.u64(),mn=head.u64(),wc=head.u64(),mc=head.u64();if(std::memcmp(magic,"LMSSRTL1",8)||version!=2||std::memcmp(identity,LEMMA_RUNTIME_IDENTITY,64))throw std::runtime_error("unsupported checkpoint machine/implementation identity");if(wn>head.remaining||mn!=head.remaining-wn||!mn||mn>64*1024*1024)throw std::runtime_error("invalid checkpoint component lengths");if(crc(f,wn)!=wc||crc(f,mn)!=mc)throw std::runtime_error("checkpoint checksum mismatch");f.clear();f.seekg(112);State probe;Reader preflight{f,wn,true};read_state(preflight,probe);f.clear();f.seekg(112);State replacement;Reader decode{f,wn,false};read_state(decode,replacement);
 Temp saved("/tmp/lemma-rtl-current"),incoming("/tmp/lemma-rtl-incoming");model_save(saved.path);if(length(saved.path)!=mn)throw std::runtime_error("checkpoint model shape mismatch");{std::ofstream mf(incoming.path,std::ios::binary);copy_bytes(f,mf,mn);if(!mf.flush())throw std::runtime_error("checkpoint model extraction failed");}
 // Generated state covers CVW pipeline, caches/TLBs, privilege/CSRs, fabric
 // owner, controller queues/cursors and all top-level port phase values.
 std::unique_ptr<VerilatedContext> restored_context(new VerilatedContext);restored_context->randReset(0);
#ifdef __EMSCRIPTEN__
 restored_context->threads(1);
#endif
 std::unique_ptr<Vlemma_soc> restored(new Vlemma_soc(restored_context.get()));{VerilatedRestore mf;mf.open(incoming.path);if(!mf.isOpen())throw std::runtime_error("cannot restore model");mf>>*restored;mf.close();}
 uint64_t replay_id=replacement.backing_pending?replacement.backing_pending->id:replacement.backing.next_id;
 auto cursor=std::lower_bound(backing_replay.begin(),backing_replay.end(),replay_id,[](const TimedBackingRecord&r,uint64_t id){return r.record.request.id<id;});
 if(!options.backing_replay_path.empty()){
  if(replacement.backing_pending){if(cursor==backing_replay.end()||!equal_backing_request(*replacement.backing_pending,cursor->record.request)||cursor->accepted_boundary<replacement.backing_poll_cycle||(cursor->accepted_boundary-replacement.backing_poll_cycle)%1000)throw std::runtime_error("backing replay does not cover pending checkpoint boundary");}
  else if(cursor!=backing_replay.end()&&(cursor->record.request.id!=replay_id||cursor->record.request.boundary<replacement.cycle))throw std::runtime_error("backing replay does not cover checkpoint boundary");
 }
 PrivateMedium fork;if(replacement.medium_present)fork.create(options.fork_directory,replacement.accepted_medium);
 std::shared_ptr<BackingPlatform>replacement_backing=fork.fd>=0?std::make_shared<PosixBacking>(fork.fd):nullptr;
 // Rewinding machine IDs starts a new external capture stream. Retain the
 // original log; never append duplicate IDs or truncate historical outcomes.
 PrivateCapture branch_capture;if(backing_capture>=0){if(backing_capture_branch==UINT64_MAX)throw std::runtime_error("backing capture branch exhausted");branch_capture.create(options.backing_capture_path,backing_capture_branch+1,replacement.backing_pending);}
 context.swap(restored_context);model.swap(restored);s=std::move(replacement);prepared=true;backing_replay_cursor=cursor-backing_replay.begin();backing_fork_suspended=s.backing_pending.has_value()&&options.backing_replay_path.empty();context->time(s.cycle*2);if(medium>=0)close(medium);medium=fork.fd;backing=std::move(replacement_backing);fork.fd=-1;private_medium_path=std::move(fork.path);fork.retained=true;
 if(branch_capture.fd>=0){close(backing_capture);backing_capture=branch_capture.fd;branch_capture.fd=-1;active_backing_capture=std::move(branch_capture.path);branch_capture.retained=true;backing_capture_bytes=72+(s.backing_pending?16+encode_backing_request(*s.backing_pending).size():0);backing_capture_branch++;}
}
void Machine::bind_backing_replay(const std::string& path){
 if(!s.isolated||!s.medium_present||s.backing.poisoned||!backing_fork_suspended||!s.backing_pending)throw std::runtime_error("outcome binding requires a suspended isolated pending fork");
 auto candidate=read_backing_replay(path);auto cursor=std::lower_bound(candidate.begin(),candidate.end(),s.backing_pending->id,[](const TimedBackingRecord&r,uint64_t id){return r.record.request.id<id;});
 if(cursor==candidate.end()||!equal_backing_request(*s.backing_pending,cursor->record.request)||cursor->accepted_boundary<s.backing_poll_cycle||(cursor->accepted_boundary-s.backing_poll_cycle)%1000)throw std::runtime_error("outcome tape does not cover inherited request and poll boundary");
 auto index=cursor-candidate.begin();backing_replay=std::move(candidate);backing_replay_cursor=index;options.backing_replay_path=path;backing_fork_suspended=false;
}
void Machine::export_medium(const std::string&path)const{if(s.backing_pending||s.backing.poisoned)throw std::runtime_error("pending or ambiguous backing cannot be exported");export_backing(path);}
void Machine::export_private_medium(const std::string&path)const{
 if(!s.isolated||!s.medium_present||s.backing.poisoned||(s.backing_pending&&!backing_fork_suspended&&options.backing_replay_path.empty()))throw std::runtime_error("private export requires an isolated backing without owned live external work");
 export_backing(path);
}
void Machine::export_backing(const std::string&path)const{if(!s.medium_present)throw std::runtime_error("no medium");int fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);if(fd<0)throw std::runtime_error("export destination exists or cannot be created");try{if(ftruncate(fd,MEDIUM_SECTORS*512))throw std::runtime_error("export capacity failed");std::array<uint8_t,1048576>b{};for(uint64_t offset=0;offset<MEDIUM_SECTORS*512;offset+=b.size()){backing->passive_read(offset,b.data(),b.size());if(pwrite(fd,b.data(),b.size(),offset)!=ssize_t(b.size()))throw std::runtime_error("export copy failed");}if(fsync(fd))throw std::runtime_error("export barrier failed");close(fd);}catch(...){close(fd);unlink(path.c_str());throw;}}
}
