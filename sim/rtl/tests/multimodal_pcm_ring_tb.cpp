// SPDX-License-Identifier: Apache-2.0
#include "Vlemma_multimodal.h"
#include "verilated.h"
extern "C" {
#include "lemma_multimodal_v2.h"
}
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
static Vlemma_multimodal rtl;
static LemmaMM2 fast;
static uint64_t checks=0,beats=0,pcm=0,ringEmitted=0;static bool ringPhase=false;
static uint16_t waveform(uint64_t n){return uint16_t(n*7919+311);}
static void equal(uint64_t a,uint64_t b,const std::string&what){checks++;if(a!=b)throw std::runtime_error(what+" rtl="+std::to_string(a)+" reference="+std::to_string(b)+" tick="+std::to_string(fast.legacy.tick));}
static uint64_t read(unsigned a){rtl.addr=a;rtl.eval();return rtl.rdata;}
static void compare(){
 for(unsigned a: {0u,8u,16u,24u,32u,40u,56u,64u,72u,80u,88u,96u,104u,112u,120u,128u,136u,144u,152u,160u,168u})equal(read(a),lemma_mm2_read(&fast,a),"header "+std::to_string(a));
 for(unsigned i=0;i<9;i++)for(unsigned o:{0u,8u,16u,32u,40u,48u,56u,64u,72u,80u,88u,96u,104u,112u,120u,128u,136u,144u,160u,168u,184u,192u,200u,208u,216u,224u,232u,240u,248u})equal(read(256*(i+1)+o),lemma_mm2_read(&fast,256*(i+1)+o),"stream "+std::to_string(i)+" offset "+std::to_string(o));
 equal(rtl.irq,lemma_mm_irq(&fast.legacy),"IRQ");equal(rtl.pcm_valid,fast.legacy.pcm_valid,"PCMvalid");if(rtl.pcm_valid){if(ringPhase){equal(rtl.pcm_data,uint64_t(int64_t(int16_t(waveform(ringEmitted)))),"independent ring sample");equal(rtl.pcm_position,ringEmitted+1,"ring emitted position");ringEmitted++;}pcm++;equal(rtl.pcm_data,fast.legacy.pcm_data,"PCMword");equal(rtl.pcm_position,fast.legacy.pcm_position,"PCMposition");equal(rtl.pcm_tick,fast.legacy.pcm_tick,"PCMtime");}
 uint64_t a,v;bool write;bool active=lemma_mm2_dma(&fast,&write,&a,&v);equal(rtl.dma_valid,active,"DMAvalid");if(active){equal(rtl.dma_write,write,"DMAwrite");equal(rtl.dma_addr,a,"DMAaddress");equal(rtl.dma_wdata,v,"DMAdata");}
}
static void step(unsigned n=1,bool do_write=false,unsigned address=0,uint64_t value=0){for(unsigned t=0;t<n;t++){
 rtl.valid=do_write;rtl.write=do_write;rtl.addr=address;rtl.wdata=value;rtl.size=3;
 uint64_t a,v;bool write;if(rtl.dma_ready&&lemma_mm2_dma(&fast,&write,&a,&v))beats++;
 lemma_mm2_clock(&fast,fast.legacy.tick+1,rtl.dma_ready,rtl.dma_error,rtl.dma_rdata);if(do_write)lemma_mm2_write(&fast,address,value);
 rtl.clk=0;rtl.eval();rtl.clk=1;rtl.eval();compare();rtl.valid=0;rtl.write=0;rtl.eval();
}}
static void wr(unsigned i,unsigned o,uint64_t v){step(1,true,256*(i+1)+o,v);}
static void stim(unsigned i,int32_t v,int32_t r,unsigned q=0){rtl.stimulus[i]=uint32_t(v);rtl.reference_input[i]=uint32_t(r);rtl.source_quality[i/2]=(rtl.source_quality[i/2]&~(0xffffu<<(16*(i%2))))|(q<<(16*(i%2)));lemma_mm_stimulus(&fast.legacy,i,v,r,q);}
static void config(unsigned i,uint64_t gain=2,uint64_t selector=0){wr(i,48,gain);wr(i,56,256);wr(i,64,4);wr(i,72,selector);wr(i,96,1);wr(i,24,2);wr(i,80,fast.legacy.stream[i].consent+1);wr(i,104,fast.legacy.tick+100000);wr(i,24,3);}
int main(int argc,char**argv){Verilated::commandArgs(argc,argv);try{
 rtl.size=3;rtl.dma_ready=0;rtl.dma_error=0;rtl.reset=1;rtl.clk=0;rtl.eval();rtl.clk=1;rtl.eval();rtl.reset=0;lemma_mm2_init(&fast);compare();
 wr(1,104,10000);equal(read(512+16),15,"default-off calibration/lease interlock");
 step(1,true,56,0);step(1,true,40,511);
 for(unsigned i=0;i<8;i++){stim(i,10+int(i),2);config(i,2,i==3?3:i==4?7:0);wr(i,24,4);step(5);}
 equal(read(256+112),16,"EEG independent arithmetic (10-2)*2");
 equal(read(512+112),72,"PPG independent integration (11-2)*2*4");
 equal(read(768+112),80,"fNIRS independent integration (12-2)*2*4");
 equal(read(1024+112),112,"NIR ROI independent integration (13-2+3)*2*4");
 equal(read(1280+112),(7u<<24)|56u,"ToF selected raw histogram bin7 count14*4");
 equal(read(1536+112),15,"Flow deadtime-limited event-window count ceil(15*4/4)");
 equal(read(1792+112),28,"MicrophoneL independent signedcode");equal(read(2048+112),30,"MicrophoneR independent signedcode");
 // Gain/config history changes are rejected until cancel returns queue ownership.
 wr(0,48,4);equal(read(256+16),6,"busy live reconfiguration");wr(0,24,6);config(0,4);wr(0,24,4);step(5);equal(read(256+112),32,"changed gain independently changes raw code");
 wr(0,24,6);stim(0,INT32_MAX,0);config(0,64);wr(0,24,4);step(5);equal(read(256+112),8388607,"EEG independent positive saturation");equal(read(256+136)&1,1,"saturation quality");
 // DMA immutable head, alignment rejection, and held data before final acknowledgement.
 wr(0,160,0x82000001);wr(0,168,8);wr(0,176,1);equal(read(256+16),3,"DMA malformed descriptor");wr(0,160,0x82000000);wr(0,176,1);step(5);equal(read(256+184),1,"DMA backpressure owns descriptor");
 wr(0,152,1);equal(read(256+16),6,"DMA head cannot be popped");rtl.dma_ready=1;step(8);rtl.dma_ready=0;equal(read(256+184),2,"DMA eight words completed");
 // PCM accepts arbitrary signed sample words. Cancellation cannot erase emitted samples.
 config(8);wr(8,112,0x0123abcd);wr(8,112,0xffff0001);wr(8,24,4);step(1);equal(read(2304+232),1,"PCM first actual digital consumption");equal(rtl.pcm_data,uint64_t(int64_t(-32768)),"PCM independently checked signed16 gain and DAC clipping");wr(8,80,0);wr(8,80,1);equal(read(2304+16),4,"revocation cannot reset consent high-water for stale replay");step(300);equal(read(2304+232),1,"local cancellation prevents later queued consumption");
 // Consequential quality faults retain actual raw codes and explicit origin quality.
 wr(1,24,6);stim(1,101,10,2);config(1);wr(1,24,4);step(5);equal(read(512+112),728,"PPG contact-loss raw optical count retained");equal(read(512+136)&2,2,"PPG contact-loss quality");
 wr(2,24,6);stim(2,102,10,4);config(2,2,256);wr(2,24,4);step(5);equal(read(768+112),20,"fNIRS source-off dark reference code");equal(read(768+136)&4,4,"fNIRS corrupt-reference quality");equal(read(768+200),0,"source-off really inhibits emitter");
 auto beforeQuiet=read(512+144);wr(1,208,fast.legacy.tick+1000);step(300);equal(read(512+144),beforeQuiet,"quiet window invents no optical records");equal(read(512+16),15,"quiet-window gap outcome");
 // Reset in the middle of an optical conversion clears its pending completion.
 wr(3,24,6);config(3);wr(3,24,4);step(1);wr(3,24,1);step(4);equal(read(1024+144),0,"reset during exposure prevents completion");equal(read(1024+32),2,"reset exposure epoch");equal(read(1024+80),0,"reset exposure invalidates consent");
 // Cancel waits for an already accepted DMA beat before returning ownership.
 wr(0,176,1);equal(read(256+184),1,"second DMA owns immutable head");wr(0,80,0);step(3);equal(read(256+184),1,"revoked DMA remains pinned until held beat responds");rtl.dma_ready=1;step(1);rtl.dma_ready=0;equal(read(256+184),3,"cancelled DMA returns ownership after response");equal(read(256+144),0,"revocation clears transient acquisition queue");
 // Bounded FIFO overflow is explicit; it cannot masquerade as complete capture.
 step(5000);equal(read(2048+144),16,"microphone FIFO bounded capacity");equal(read(2048+16),9,"microphone overflow is explicit");
 // Lease expiry, independent streams and disconnected safe state.
 wr(6,104,fast.legacy.tick+2);step(3);equal(read(1792+8),3,"microphone acquisition lease expires");equal(read(2048+8),5,"other independently authorized microphone continues");
 step(1,true,64,0);for(unsigned i=0;i<9;i++){equal(read(256*(i+1)+8),8,"disconnect state");equal(read(256*(i+1)+144),0,"disconnect clears transient queue");}
 step(1,true,64,1);wr(0,24,8);wr(0,24,1);equal(read(256+32),2,"reset changes epoch");equal(read(256+80),0,"reset revokes consent");
 std::cout<<"PASS synthetic-aperture/1 checks="<<checks<<" cycles="<<fast.legacy.tick<<" DMA_beats="<<beats<<" PCM_observations="<<pcm<<"\n";
 // Private ring-enabled successor: real bus reads serve a bounded 64-sample memory ring.
 for(unsigned i=0;i<8;i++){rtl.stimulus[i]=0;rtl.reference_input[i]=0;}for(unsigned i=0;i<4;i++)rtl.source_quality[i]=0;
 rtl.reset=1;rtl.clk=0;rtl.eval();rtl.clk=1;rtl.eval();rtl.reset=0;lemma_mm2_init(&fast);rtl.dma_ready=0;rtl.dma_rdata=0;compare();
 step(1,true,56,0);wr(8,56,6250);wr(8,96,1);wr(8,80,1);wr(8,104,10000000);wr(8,24,2);wr(8,24,3);
 step(1,true,104,0x82000000);step(1,true,112,64);step(1,true,136,1);
 uint16_t memory[64]={};const uint64_t total=1027;uint64_t published=0,reads=0;bool eof=false,started=false;ringPhase=true;
 auto publish=[&](uint64_t to){for(uint64_t n=published;n<to;n++)memory[n%64]=waveform(n);published=to;step(1,true,120,to);};
 publish(32);
 for(uint64_t cycle=0;cycle<7000000&&fast.status==1;cycle++){
  if(published<total&&published-fast.fetch<=32){auto n=total-published;if(n>16)n=16;publish(published+n);}
  if(published==total&&!eof){step(1,true,136,2);eof=true;}
  if(!started&&fast.legacy.stream[8].count==16){wr(8,24,4);started=true;}
  bool w;uint64_t a,v;bool active=lemma_mm2_dma(&fast,&w,&a,&v);rtl.dma_ready=active&&(cycle%7==0);rtl.dma_error=0;rtl.dma_rdata=0;
  if(active){if(w)throw std::runtime_error("unexpected record write during ring-only stream");for(unsigned j=0;j<4;j++)rtl.dma_rdata|=uint64_t(memory[((a-0x82000000)/2+j)%64])<<(16*j);if(rtl.dma_ready)reads++;}
  lemma_mm2_clock(&fast,fast.legacy.tick+1,rtl.dma_ready,false,rtl.dma_rdata);rtl.valid=0;rtl.write=0;rtl.clk=0;rtl.eval();rtl.clk=1;rtl.eval();
  equal(rtl.pcm_valid,fast.legacy.pcm_valid,"ring PCMvalid");equal(rtl.dma_valid,fast.bus_kind!=0,"ring DMAvalid");
  if(cycle%1000==0||rtl.pcm_valid||rtl.dma_ready)compare();
 }
 equal(ringEmitted,total,"EOF total");equal(fast.fetch,total,"ring fetched total");equal(fast.legacy.stream[8].submitted,total,"ring actual FIFO submitted");equal(fast.legacy.stream[8].consumed,total,"ring consumed total");equal(fast.status,2,"ring EOF completion");equal(fast.gaps,0,"ring gap counter");
 std::cout<<"PASS MM2 RTL/C ring samples="<<ringEmitted<<" reads="<<reads<<" cycles="<<fast.legacy.tick<<" EOFtail=3 checks="<<checks<<"\n";
 ringPhase=false;
 auto resetAll=[](){for(unsigned i=0;i<8;i++){rtl.stimulus[i]=0;rtl.reference_input[i]=0;}for(unsigned i=0;i<4;i++)rtl.source_quality[i]=0;rtl.valid=0;rtl.write=0;rtl.dma_ready=0;rtl.dma_error=0;rtl.dma_rdata=0;rtl.reset=1;rtl.clk=0;rtl.eval();rtl.clk=1;rtl.eval();rtl.reset=0;lemma_mm2_init(&fast);compare();};
 auto ringSetup=[](){step(1,true,56,0);config(8,1);step(1,true,104,0x82000000);step(1,true,112,64);step(1,true,136,1);step(1,true,120,16);};
 // Incoming record DMA cannot replace an already exposed ring read. After its
 // completion, arbitration gives the record engine a beat before another read.
 resetAll();ringSetup();uint64_t held=read(0xa8);equal(held,2,"held audio read kind");uint64_t heldAddress=rtl.dma_addr;
 stim(0,1234,6,2);config(0,1);wr(0,24,4);step(5);wr(0,160,0x82001000);wr(0,168,8);wr(0,176,1);
 equal(rtl.dma_addr,heldAddress,"record arrival preserves held ring address");equal(rtl.dma_write,0,"record arrival preserves held read direction");rtl.dma_rdata=0x80007fff1234abcdULL;rtl.dma_ready=1;step(1);rtl.dma_ready=0;
 equal(rtl.dma_write,1,"record wins next beat");equal(rtl.dma_addr,0x82001000,"record address");equal(rtl.dma_wdata,1228,"actual converter record value");step(3);equal(rtl.dma_addr,0x82001000,"record backpressure address stable");equal(rtl.dma_wdata,1228,"record backpressure data stable");
 rtl.dma_ready=1;step(32);rtl.dma_ready=0;equal(read(256+184),2,"interleaved record complete");equal(read(128),16,"ring independently refilled");
 // Local mute retains a held memory owner until the acknowledged read, while
 // it revokes playback immediately and blocks reuse of the private ring frame.
 resetAll();ringSetup();heldAddress=rtl.dma_addr;step(1,true,56,1);equal(read(144),3,"mute marks canceled ring");equal(read(168),258,"muted held read remains pinned");step(1,true,104,0x82001000);equal(read(104),heldAddress,"cannot reuse canceled held frame");step(4);equal(rtl.dma_valid,1,"cancel never strands exposed read");rtl.dma_ready=1;step(1);rtl.dma_ready=0;equal(rtl.dma_valid,0,"cancel returns frame after response");equal(read(2304+240),0,"canceled read submits no sample");equal(read(2304+232),0,"canceled read consumes no sample");
 // Permission is checked again at the actual completion edge, including an
 // exact lease deadline. The memory response still retires its bus owner.
 resetAll();ringSetup();uint64_t expiry=fast.legacy.tick+5;wr(8,104,expiry);while(fast.legacy.tick+1<expiry)step();rtl.dma_ready=1;step(1);rtl.dma_ready=0;equal(read(144),3,"lease boundary cancels read");equal(read(2304+240),0,"expired read submits no sample");equal(rtl.dma_valid,0,"expired read owner retired");
 resetAll();ringSetup();rtl.dma_ready=1;rtl.dma_error=1;step(1);rtl.dma_ready=0;rtl.dma_error=0;equal(read(144),4,"failed memory read faults ring");equal(read(2304+16),3,"failed memory read explicit range fault");equal(read(2304+240),0,"failed read submits no sample");
 resetAll();ringSetup();wr(8,24,1);equal(read(2304+8),2,"reset preserves IDLE");equal(read(2304+32),2,"reset advances epoch");equal(read(168),258,"reset retains held read");rtl.dma_ready=1;step(1);rtl.dma_ready=0;equal(read(2304+8),2,"completed canceled read preserves reset IDLE");equal(read(2304+240),0,"reset never submits held data");
 resetAll();ringSetup();step(1,true,64,0);equal(read(2304+8),8,"link loss preserves disconnected state");equal(read(168),258,"link loss retains held read");rtl.dma_ready=1;step(1);rtl.dma_ready=0;equal(read(2304+8),8,"completed read preserves link loss");equal(read(2304+240),0,"link loss never submits held data");
 resetAll();ringSetup();wr(8,80,0);wr(8,24,1);wr(8,96,1);wr(8,24,2);wr(8,80,2);wr(8,104,100000);wr(8,24,3);wr(8,112,7);equal(read(2304+144),0,"new direct data cannot mix with old held read");rtl.dma_ready=1;step(1);rtl.dma_ready=0;equal(read(2304+8),4,"stale read completion preserves new ARMED grant");equal(read(2304+104),100000,"stale read completion preserves new lease");wr(8,112,7);equal(read(2304+144),1,"new grant works after old read retires");
 std::cout<<"PASS MM2 RTL/C held-owner fairness, mute, exact-expiry and read-failure cuts checks="<<checks<<"\n";
 return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}}
