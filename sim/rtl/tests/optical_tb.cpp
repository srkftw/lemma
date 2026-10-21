// SPDX-License-Identifier: Apache-2.0
// Exact raw controller trace comparison plus independently stated packet rules.
#include "Vlemma_optical.h"
#include "Vlemma_optical___024root.h"
#include "verilated.h"
extern "C" {
#include "lemma_optical.h"
}
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>
static uint64_t checks=0,cases=0;
static void require(bool ok,const std::string& what){++checks;if(!ok)throw std::runtime_error(what);}
struct Rig {
 LemmaOptical m{};Vlemma_optical rtl;std::vector<uint8_t> ram;uint64_t edges=0,writes=0,reads=0;
 Rig():ram(0x2000000){lemma_of_init(&m);rtl.clk=0;rtl.por_reset=1;rtl.reset=0;rtl.valid=0;rtl.write=0;rtl.addr=0;rtl.size=3;rtl.wdata=0;rtl.source_valid=0;rtl.source_endpoint=0;rtl.source_kind=0;rtl.source_data=0;rtl.source_bytes=0;rtl.source_quality=0;rtl.dma_ready=0;rtl.dma_error=0;rtl.dma_rdata=0;rtl.eval();rtl.clk=1;rtl.eval();rtl.por_reset=0;observe();}
 uint64_t read(unsigned a){return lemma_of_read(&m,a);}
 void put(uint64_t address,uint64_t word){require(address>=LEMMA_OF_POOL&&address<=LEMMA_OF_POOL+ram.size()-8,"fixture range");for(unsigned n=0;n<8;n++)ram[address-LEMMA_OF_POOL+n]=word>>(n*8);}
 uint64_t get(uint64_t address){require(address>=LEMMA_OF_POOL&&address<=LEMMA_OF_POOL+ram.size()-8,"physical range");uint64_t word=0;for(unsigned n=0;n<8;n++)word|=uint64_t(ram[address-LEMMA_OF_POOL+n])<<(n*8);return word;}
 void observe(){
  for(unsigned a=0;a<1024;a+=8){rtl.addr=a;rtl.eval();auto expected=read(a);if(rtl.rdata!=expected)throw std::runtime_error("register "+std::to_string(a)+" C="+std::to_string(expected)+" RTL="+std::to_string(rtl.rdata)+" edge="+std::to_string(edges));++checks;}
  require(bool(rtl.irq)==lemma_of_irq(&m),"IRQ relation");
  bool wr=false;uint64_t addr=0,data=0;bool held=lemma_of_dma(&m,&wr,&addr,&data);
  require(bool(rtl.dma_valid)==held,"held validity");if(held){require(bool(rtl.dma_write)==wr,"held direction");require(rtl.dma_addr==addr&&rtl.dma_wdata==data&&rtl.dma_size==3,"immutable held beat");}
 }
 bool step(LemmaOFSource source={},bool acknowledge=true,bool fault=false,bool reset=false,int mmio=-1,uint64_t value=0,bool full=true,bool writing=true,unsigned bus_size=3){
  rtl.clk=0;rtl.reset=reset;rtl.valid=mmio>=0;rtl.write=mmio>=0&&writing;rtl.addr=mmio<0?0:mmio;rtl.wdata=value;rtl.size=bus_size;
  rtl.source_valid=source.valid;rtl.source_endpoint=source.endpoint;rtl.source_kind=source.kind;rtl.source_data=source.data;rtl.source_bytes=source.bytes;rtl.source_quality=source.quality;
  rtl.eval();bool bus_ok=mmio<0||lemma_of_access(unsigned(mmio),writing,1u<<bus_size);
  require(bool(rtl.ready)==(mmio>=0&&!reset),"actual bus response validity");
  require(bool(rtl.error)==(mmio>=0&&!reset&&!bus_ok),"bus error is distinct from semantic refusal");
  if(mmio>=0&&!writing&&bus_ok)require(rtl.rdata==read(unsigned(mmio)),"admitted bus read value");
  bool advertised=!reset&&lemma_of_source_ready(&m,m.tick+1,&source);
  require(bool(rtl.source_ready)==advertised,"pre-edge source ready");
  bool wr=false;uint64_t address=0,word=0;bool held=lemma_of_dma(&m,&wr,&address,&word);uint64_t data=0;
  require(bool(rtl.dma_valid)==held,"pre-edge DMA valid");
  if(held){require(rtl.dma_addr==address&&rtl.dma_wdata==word&&bool(rtl.dma_write)==wr,"pre-edge retained tuple");if(acknowledge&&!fault){if(wr){put(address,word);++writes;}else {data=get(address);++reads;}}}
  rtl.dma_ready=held&&acknowledge;rtl.dma_error=fault;rtl.dma_rdata=data;
  auto input=source;if(reset)input.valid=false;
  bool accepted=lemma_of_clock_reset(&m,m.tick+1,held&&acknowledge,fault,data,&input,reset);
  if(!reset&&mmio>=0&&writing&&bus_ok)lemma_of_write(&m,mmio,value);
  rtl.clk=1;rtl.eval();++edges;
  require(accepted==advertised,"source acceptance was advertised");
  if(full)observe();return accepted;
 }
 void write(unsigned a,uint64_t v){step({},true,false,false,int(a),v);}
 uint64_t send(unsigned ep,unsigned kind,uint64_t data=0,unsigned bytes=0,uint64_t quality=0){
  LemmaOFSource source{true,ep,kind,data,bytes,quality};uint64_t limit=edges+100000;
  while(!step(source)){require(edges<limit,"bounded raw source acceptance");}
  return m.tick;
 }
 void idle(unsigned n){for(unsigned k=0;k<n;k++)step({},true,false,false,-1,0,k%256==0);observe();}
 void table(bool invalid=false){
  uint64_t cursor=LEMMA_OF_POOL+8192;
  for(unsigned slot=0;slot<6;slot++){
   unsigned pages=slot<4?5:19;uint64_t base=LEMMA_OF_POOL+slot*256;
   put(base,pages);put(base+8,pages*4096);put(base+16,1);
   for(unsigned p=0;p<pages;p++){put(base+32+p*8,cursor);cursor+=4096;}
  }
  if(invalid)put(LEMMA_OF_POOL+32+8,get(LEMMA_OF_POOL+32));
  write(96,LEMMA_OF_POOL);write(104,1536);write(112,1);
  for(unsigned n=0;n<193&&read(120)==1;n++)step();
  require(read(120)==(invalid?3:2),"whole table admission");
  require(read(80)==(invalid?1:2),"table publish epoch");
 }
 void start(unsigned ep,unsigned format=1,uint64_t gain=1,uint64_t expiry=10000000,uint64_t row_ticks=2){
  unsigned b=ep*256;width_config(ep,format);write(b+80,gain);write(b+88,8);write(b+96,row_ticks);write(b+128,1);write(b+24,2);
  write(56,0);write(b+120,expiry);write(b+112,1);write(b+24,3);write(b+24,4);
  require(read(b+8)==5,"actual running command state");
 }
 void width_config(unsigned ep,unsigned format){unsigned b=ep*256,w=ep==3?320:format==1?16:160,h=ep==3?240:format==1?16:120;
  write(b+48,w);write(b+56,h);write(b+64,w*(format==1?2:1));write(b+72,format);write(b+104,ep==3?6666667:format==1?1000000:1666667);
 }
 uint64_t payload(unsigned ep,unsigned format){return ep==3?76800:format==1?512:19200;}
 uint64_t fill(unsigned ep,unsigned format=1,uint64_t gain=1){
  uint64_t prior=read(ep*256+144);uint64_t capture=send(ep,0,0,0,2);unsigned captured_slot=unsigned(m.endpoint[ep-1].active_slot);auto bytes=payload(ep,format);unsigned unit=format==1?2:1;std::vector<uint8_t> expected;
  for(uint64_t off=0;off<bytes;off+=8){uint64_t word=0;for(unsigned k=0;k<8;k+=unit){uint64_t sample=(off+k)*37+311,maximum=unit==2?65535:255;sample&=maximum;if(off==0&&k==0)sample=maximum;word|=sample<<(k*8);sample*=gain;if(sample>maximum)sample=maximum;for(unsigned j=0;j<unit;j++)expected.push_back(sample>>(j*8));}uint64_t accepted_tick=send(ep,1,word,8);require(accepted_tick>=capture+8+((off+7)/m.endpoint[ep-1].stride)*m.endpoint[ep-1].row_ticks,"last affected row readout deadline");}
  uint64_t eof=send(ep,2);for(unsigned n=0;n<35&&read(ep*256+144)==prior;n++)step();
  require(read(ep*256+144)==prior+1,"READY only completed header");
  unsigned slot=captured_slot;uint64_t physical=m.slots[slot].pages[0];
  require(get(physical)==LEMMA_OF_FRAME_MAGIC&&get(physical+8)==1,"actual wire magic/version");
  require(get(physical+6*8)==capture&&get(physical+7*8)==capture+8&&get(physical+8*8)==eof,"actual capture/readout timestamps");
  require(get(physical+18*8)==(gain>1?3:2),"actual saturation and source quality");
  require(get(physical+19*8)==bytes&&get(physical+20*8)==32&&get(physical+27*8)==format,"complete raw representation");
  for(uint64_t n=0;n<bytes;n++)require(ram[m.slots[slot].pages[(256+n)/4096]-LEMMA_OF_POOL+(256+n)%4096]==expected[n],"independent complete digital gain payload");
  return physical;
 }
};
static void successful_formats(){for(auto pair:std::array<std::array<unsigned,2>,4>{{{1,1},{1,2},{2,2},{3,2}}}){Rig r;r.table();r.start(pair[0],pair[1],3);r.fill(pair[0],pair[1],3);++cases;}}
static void fragmented_frames(){
 for(auto pair:std::array<std::array<unsigned,2>,2>{{{2,2},{1,1}}}){
  Rig r;r.table();r.start(pair[0],pair[1],3,10000000,100);
  const unsigned ep=pair[0],format=pair[1],unit=format==1?2:1;
  const uint64_t maximum=unit==2?65535:255,bytes=r.payload(ep,format);
  std::vector<uint8_t> raw(bytes),expected(bytes);
  for(uint64_t n=0;n<bytes;n+=unit){uint64_t code=(n*509+311)&maximum;if(n==0)code=maximum;uint64_t amplified=code*3;if(amplified>maximum)amplified=maximum;for(unsigned j=0;j<unit;j++){raw[n+j]=code>>(8*j);expected[n+j]=amplified>>(8*j);}}
  uint64_t capture=r.send(ep,0,0,0,2),off=0;unsigned slot=unsigned(r.m.endpoint[ep-1].active_slot),turn=0;
  const std::array<unsigned,11> split{4,8,1,8,7,8,1,7,3,8,1};
  while(off<bytes){unsigned count=split[turn++%split.size()];if(count>bytes-off)count=unsigned(bytes-off);uint64_t word=0;for(unsigned n=0;n<count;n++)word|=uint64_t(raw[off+n])<<(8*n);
   LemmaOFSource source{true,ep,1,word,count,0};bool accepted=false;
   for(unsigned n=0;n<128&&!accepted;n++)accepted=r.step(source);
   require(accepted,"legal partial4-to8 byte packing must make bounded progress");
   require(r.read(ep*256+16)==0,"arbitrary byte splits remain valid raw input");
   require(r.m.tick>=capture+8+((off+count-1)/r.m.endpoint[ep-1].stride)*100,"cross-row beat waits for LAST affected row");off+=count;
  }
  uint64_t eof=r.send(ep,2);for(unsigned n=0;n<35&&r.read(ep*256+144)==0;n++)r.step();
  require(r.read(ep*256+144)==1,"fragmented payload publishes only after complete header");
  require(r.get(r.m.slots[slot].pages[0]+8*8)==eof,"fragmented availability is actual accepted EOF");
  for(uint64_t n=0;n<bytes;n++)require(r.ram[r.m.slots[slot].pages[(256+n)/4096]-LEMMA_OF_POOL+(256+n)%4096]==expected[n],"complete independently amplified fragmented byte order");
  ++cases;
 }
}
static void fragmented_held_and_reset(){
 Rig r;r.table();r.start(1,1,3);r.send(1,0);
 r.send(1,1,0x0004000300020001ULL,8);
 require(r.m.held_kind==2,"first whole processed word is a real held write");
 const uint64_t address=r.m.held_address,data=r.m.held_data;
 LemmaOFSource low{true,1,1,0x34,1,0};
 require(r.step(low,false),"raw low U16 byte can remain pending behind held word");
 require(r.m.endpoint[0].packing_bytes==8&&r.m.endpoint[0].pixel_low==0x34,"incomplete pixel is not amplified or padded");
 LemmaOFSource crossing{true,1,1,0x7f00060005000412ULL,8,0};
 require(r.step(crossing,false),"1+8 odd source split uses bounded carry behind held DMA");
 require(r.m.endpoint[0].packing_bytes==16&&r.m.endpoint[0].received==17,"two complete words plus one raw low byte retained");
 LemmaOFSource high{true,1,1,0xff,1,0};
 for(unsigned n=0;n<5;n++){
  require(!r.step(high,false),"full carry backpressures the high pixel byte");
  require(r.m.held_address==address&&r.m.held_data==data,"source carry cannot change held physical write");
 }
 require(!r.step(high,true),"completion cannot accept a beat not advertised ready before the edge");
 require(r.step(high,true),"pending pixel completes after actual old-word retirement");
 require(r.get(address)==0x000c000900060003ULL,"independent first processed word survives carry");
 require(r.get(address+8)==0x0012000f000c369cULL,"cross-beat pixels retain LE16 order and apply gain once");
 require(r.m.endpoint[0].packing_bytes==2&&(r.m.slots[0].header[18]&1),"split final pixel saturates only on its high byte");
 r.send(1,1,0x11,1);
 require(r.m.endpoint[0].received==19&&r.m.endpoint[0].pixel_low==0x11,"new odd low byte remains owned by this capture");
 r.step({},false,false,true);r.step({},true,false,true);
 require(r.read(256+144)==0&&r.read(256+112)==0&&r.m.endpoint[0].packing_bytes==0&&r.m.endpoint[0].pixel_low==0,"ordinary reset invalidates carry and partial pixel without publication");
 ++cases;
 Rig q;q.table();q.start(1,1,3);q.send(1,0);q.send(1,1,0x0004000300020001ULL,8);
 require(q.step(low,false)&&q.step(crossing,false),"second capture has real held write, full carry, and partial pixel");
 const uint64_t old_address=q.m.held_address,old_data=q.m.held_data;
 q.step({},false,false,true);
 require(q.m.held_kind==2&&q.m.held_address==old_address&&q.m.held_data==old_data&&q.m.held_cancel,"reset keeps accepted fabric tuple while invalidating all carry");
 q.step({},true,false,true);
 require(q.get(old_address)==old_data&&q.read(136)==0&&q.read(256+144)==0&&q.m.endpoint[0].packing_bytes==0&&q.m.endpoint[0].pixel_low==0,"retired physical prefix survives while old capture remains unpublished");
 ++cases;
}
static void bad_tables(){
 for(unsigned mutation=0;mutation<7;mutation++){Rig r;uint64_t cursor=LEMMA_OF_POOL+8192;
  for(unsigned s=0;s<6;s++){unsigned pages=s<4?5:19;uint64_t b=LEMMA_OF_POOL+s*256;r.put(b,pages);r.put(b+8,pages*4096);r.put(b+16,1);for(unsigned p=0;p<pages;p++){r.put(b+32+p*8,cursor);cursor+=4096;}}
  if(mutation==0)r.put(LEMMA_OF_POOL+40,r.get(LEMMA_OF_POOL+32));
  if(mutation==1)r.put(LEMMA_OF_POOL+32,LEMMA_OF_POOL);
  if(mutation==2)r.put(LEMMA_OF_POOL+32,LEMMA_OF_POOL+1);
  if(mutation==3)r.put(LEMMA_OF_POOL+8,19456);
  if(mutation==4)r.put(LEMMA_OF_POOL+16,0);
  if(mutation==5)r.put(LEMMA_OF_POOL+24,1);
  if(mutation==6)r.put(LEMMA_OF_POOL+23*8,1);
  r.write(96,LEMMA_OF_POOL);r.write(112,1);r.idle(193);require(r.read(120)==3&&r.read(80)==1&&r.writes==0,"atomic invalid table never publishes or writes");++cases;
 }
}
static void bus_admission(){
 Rig r;
 for(unsigned a:std::array<unsigned,5>{1,1024,2048,4088,4096})for(bool write:{false,true}){
  require(!lemma_of_access(a,write,8),"unsupported aperture offset refused");r.step({},true,false,false,int(a),123,true,write);
  require(r.read(128)==0&&r.read(80)==1,"bad bus access does not mutate controller status or identity");++cases;
 }
 for(unsigned a:std::array<unsigned,7>{0,8,80,240,248,256,256+240}){
  require(!lemma_of_access(a,true,8),"read-only direction refused");r.step({},true,false,false,int(a),999);
  require(r.read(128)==0&&r.read(240)==0&&r.read(248)==0,"wrong direction cannot stamp status or reset witnesses");++cases;
 }
 for(unsigned a:std::array<unsigned,4>{48,112,200,256+184}){
  require(!lemma_of_access(a,false,8),"write-only direction refused");r.step({},true,false,false,int(a),0,true,false);++cases;
 }
 for(unsigned size:std::array<unsigned,4>{0,1,2,4}){r.step({},true,false,false,0,0,true,false,size);require(r.read(128)==0,"unsupported width has no semantic side effect");++cases;}
 r.write(104,99);require(r.read(128)==3,"supported semantic command refusal latches range without bus fault");++cases;
}
static void delivery_fence(){Rig r;r.table();r.start(1);r.fill(1);r.write(184,1);r.write(192,1);r.write(200,1);require(r.read(208)==1,"actual delivery pin");uint64_t generation=r.read(224);r.write(256+184,1);require(r.read(256+144)==1&&r.read(224)==generation,"direct consume cannot erase pin");r.write(256+112,0);require(r.read(208)==2&&r.read(256+224)==3,"revoke waits for kernel copy release");r.write(184,2);require(r.read(184)==1&&r.read(208)==2,"lease staging cannot retarget");r.write(200,3);require(r.read(208)==0&&r.read(256+224)==0&&r.read(256+240)==generation+1,"retire only after release");++cases;}
static void reset_held(){for(unsigned phase=1;phase<=3;phase++){Rig r;if(phase==1){r.table(true);r.write(96,LEMMA_OF_POOL);r.write(112,1);}else{r.table();r.start(1);r.send(1,0);for(unsigned n=0;n<(phase==2?1:64);n++)r.send(1,1,0x1234123412341234ULL,8);if(phase==3)r.send(1,2);}
 require(r.m.held_kind==phase,"selected real held phase");bool wr;uint64_t a,d;lemma_of_dma(&r.m,&wr,&a,&d);for(unsigned n=0;n<3;n++){r.step({},false,false,true);require(r.rtl.dma_addr==a&&r.rtl.dma_wdata==d&&bool(r.rtl.dma_write)==wr,"reset retained exact pending request");}
 r.step({},true,false,true);require(r.read(136)==0&&r.read(120)==0&&r.read(208)==0,"reset retires before initialization");require(r.read(256+144)==0&&r.read(256+112)==0,"reset exposes no frame or grant");++cases;}}
static void source_faults(){Rig r;r.table();r.start(1);r.send(1,0);r.send(1,1,0x1234,2);r.send(1,2);require(r.read(256+16)==3&&r.read(256+144)==0,"truncated EOF faults without publication");++cases;
 Rig q;q.table();q.start(1);q.send(1,0);q.send(1,1,0x34,1);q.send(1,2);require(q.read(256+16)==3&&q.read(256+144)==0,"dangling U16 byte cannot be padded into a complete frame");++cases;
 Rig z;z.table();z.start(1);z.send(1,0);z.send(1,3,2,0,4);require(z.read(256+192)==2&&z.read(256+144)==0,"GAP has loss without fabricated frame");z.send(1,0);require(z.read(256+192)==3&&z.read(256+144)==0,"SOF truncates old and drops new");++cases;}
static void expiry_final_header(){Rig r;r.table();r.start(1,1,1,1000);r.send(1,0);for(unsigned n=0;n<64;n++)r.send(1,1,0x1234123412341234ULL,8);r.send(1,2);while(r.m.endpoint[0].header_index<31)r.step();require(r.m.held_kind==3,"last real header beat held");uint64_t address=r.m.held_address;while(r.m.tick<999)r.step({},false);r.step({},true);require(r.get(address)==0&&r.read(256+144)==0&&r.read(256+40)==0&&r.read(256+112)==0,"expiry on final physical ack has no READY or grant");++cases;}
static void source_during_header(){Rig r;r.table();r.start(1);r.send(1,0);for(unsigned n=0;n<64;n++)r.send(1,1,0x1234123412341234ULL,8);r.send(1,2);uint64_t address=r.m.held_address,data=r.m.held_data;LemmaOFSource next{true,1,0,0,0,0};r.step(next,false);require(r.m.held_address==address&&r.m.held_data==data&&r.read(256+192)==1,"new SOF cannot replace old header owner");r.idle(33);require(r.read(256+144)==1&&r.read(256+160)==1,"old completed source sequence preserved");++cases;}
static void row_schedule(){Rig r;r.table();r.start(2,2,1,10000000,100);r.fill(2,2,1);++cases;}
static void reset_identity(){
 Rig r;r.table();r.start(1);r.fill(1);r.write(184,1);r.write(192,1);r.write(200,1);
 uint64_t tick=r.read(24),generation=r.read(256+240);
 require(r.read(240)==0&&r.read(248)==0&&r.read(208)==1,"POR has no orphan-release witness and live pin remains owned");
 for(unsigned n=0;n<3;n++)r.step({},false,false,true);
 require(r.read(24)==tick+3&&r.read(80)==3&&r.read(240)==3&&r.read(248)==1&&r.read(256+32)==2,"ordinary reset clocks and advances identities exactly once");
 require(r.read(256+24)==1&&r.read(256+112)==0&&r.read(256+208)==1&&r.read(256+40)==1,"ordinary reset preserves consent/config/completed sequence floors");
 require(r.m.endpoint[0].source_sequence==1&&r.read(208)==2&&r.read(224)==generation&&r.read(256+240)==generation,"ordinary reset revokes but never reuses a copy pin");
 r.step();r.write(240,999);require(r.read(240)==3,"software cannot stamp reset witness");
 r.write(200,3);require(r.read(208)==0&&r.read(256+240)==generation+1,"new kernel retires witnessed orphan after held owner is absent");
 // The stale descriptor seed is rejected after the actual retirement floor.
 r.write(112,1);r.idle(193);require(r.read(120)==3&&r.read(80)==3&&r.read(248)==0,"ordinary reset cannot revive descriptor generation1 or its stale fence");
 for(unsigned s=0;s<6;s++)r.put(LEMMA_OF_POOL+s*256+16,3);
 r.write(112,1);r.idle(193);require(r.read(120)==2&&r.read(80)==4&&r.read(240)==3,"new table invalidates old boot witness by real epoch advance");
 r.write(256+128,1);r.write(256+24,2);r.write(56,0);r.write(256+120,10000000);r.write(256+112,1);
 require(r.read(256+112)==0&&r.read(256+24)==1,"stale consent cannot reactivate after ordinary reset");
 r.write(256+112,2);r.write(256+24,3);r.write(256+24,4);r.fill(1);
 require(r.read(256+40)==2&&r.read(256+160)==2,"new capture continues the actual source sequence floor");++cases;
}
static void reset_exhaustion(){
 Rig r;r.table();r.start(1);
 // Finite injected counter boundary, not a public MMIO/debug interface or a
 // claim of reaching 2^63 transitions during this test.
 r.m.epoch=LEMMA_OF_MAX_ID;r.rtl.rootp->lemma_optical__DOT__controller_epoch=LEMMA_OF_MAX_ID;
 r.step({},true,false,true);
 require(r.read(80)==LEMMA_OF_MAX_ID&&r.read(240)==0&&r.read(248)==1&&r.read(128)==14&&r.read(256+112)==0&&r.read(120)==0,"exhausted reset has retirement fence without fresh identity or authority");
 r.step();r.write(112,1);require(r.read(120)==0&&r.read(128)==14,"exhausted identity cannot publish a replacement table");++cases;
}
static void exhausted_orphan_and_held(){
 Rig r;r.table();r.start(1);r.fill(1);r.write(184,1);r.write(192,1);r.write(200,1);
 r.start(2,2);r.send(2,0);r.send(2,1,0x2222222222222222ULL,8);
 require(r.m.held_kind==2&&r.read(208)==1,"real other-endpoint held payload and live delivery pin");
 uint64_t address=r.m.held_address,data=r.m.held_data;
 r.m.epoch=LEMMA_OF_MAX_ID;r.rtl.rootp->lemma_optical__DOT__controller_epoch=LEMMA_OF_MAX_ID;
 r.step({},false,false,true);
 require(r.read(248)==1&&r.read(240)==0&&r.read(208)==2&&r.m.held_address==address&&r.m.held_data==data,"MAX reset revokes copy while retaining old immutable write");
 r.step({},false,false,false,200,3);
 require(r.read(208)==2&&r.m.held_kind==2,"held request prevents orphan copy release");
 r.step({},true);r.write(200,3);
 require(r.read(208)==0&&r.read(136)==0&&r.read(120)==0&&r.read(128)==14&&r.read(256+112)==0&&r.read(512+112)==0,"retired orphan at exhaustion leaves sensor permanently unavailable");
 r.write(112,1);r.idle(4);require(r.read(136)==0&&r.read(120)==0,"quarantine has no future descriptor DMA");++cases;
}
static void exhausted_slot_orphan(){
 Rig r;r.table();for(unsigned n=0;n<6;n++)r.put(LEMMA_OF_POOL+n*256+16,LEMMA_OF_MAX_ID);
 r.write(112,1);r.idle(193);require(r.read(120)==2,"actual maximum-generation table admitted once");
 r.start(1);r.fill(1);r.write(184,1);r.write(192,1);r.write(200,1);r.step({},true,false,true);r.step();
 require(r.read(208)==2&&r.read(224)==LEMMA_OF_MAX_ID&&r.read(248)==1,"MAX slot remains pinned through real reset");
 r.write(200,3);require(r.read(208)==0&&r.read(256+240)==LEMMA_OF_MAX_ID&&r.read(256+224)==3&&r.read(128)==14&&r.read(136)==0,"MAX slot retires references without inventing generation or future DMA");++cases;
}
static void full_slots(){Rig r;r.table();r.start(1);r.fill(1);auto target=r.m.endpoint[0].last_sof+r.m.endpoint[0].period;while(r.m.tick<target)r.step({},true,false,false,-1,0,(r.edges&1023)==0);r.fill(1);require(r.read(256+144)==2,"two owned complete slots");target=r.m.endpoint[0].last_sof+r.m.endpoint[0].period;while(r.m.tick<target)r.step({},true,false,false,-1,0,(r.edges&1023)==0);r.send(1,0);require(r.read(256+144)==2&&r.read(256+160)==1&&r.read(256+192)==1&&r.read(256+16)==9,"third source explicitly drops without fake head");r.write(64,0);require(r.read(256+144)==0&&r.read(256+112)==0,"link fence invalidates all completed capture authority");++cases;}
int main(int argc,char**argv){Verilated::commandArgs(argc,argv);try{fragmented_frames();fragmented_held_and_reset();bus_admission();bad_tables();successful_formats();delivery_fence();reset_held();source_faults();expiry_final_header();source_during_header();row_schedule();reset_identity();reset_exhaustion();exhausted_orphan_and_held();exhausted_slot_orphan();full_slots();std::printf("PASS optical-frame/1 cases=%llu checks=%llu\n",(unsigned long long)cases,(unsigned long long)checks);return 0;}catch(const std::exception&e){std::fprintf(stderr,"FAIL optical-frame/1: %s\n",e.what());return 1;}}
