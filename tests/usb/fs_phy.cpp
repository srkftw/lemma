// SPDX-License-Identifier: Apache-2.0
#include "VUSBFullSpeed.h"
#include "verilated.h"
#include "verilated_save.h"
#include <cstdint>
#include <fstream>
#include <iterator>
#include <deque>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using Bytes=std::vector<uint8_t>;
static void require(bool b,const char*s){if(!b)throw std::runtime_error(s);}
static uint32_t primary_crc(const Bytes&bytes,unsigned width,uint32_t polynomial,unsigned bits=0){
 uint32_t mask=(1U<<width)-1,c=mask;unsigned n=bits?bits:unsigned(bytes.size()*8);
 for(unsigned i=0;i<n;i++){bool x=bool(c&(1U<<(width-1)))^bool((bytes[i/8]>>(i%8))&1);c=(c<<1)&mask;if(x)c^=polynomial;}
 return c;
}
static uint32_t reverse(uint32_t x,unsigned n){uint32_t r=0;for(unsigned b=0;b<n;b++)r=(r<<1)|((x>>b)&1);return r;}
static Bytes token(uint8_t pid,unsigned address,unsigned ep){
 unsigned value=address|(ep<<7);Bytes field{uint8_t(value),uint8_t(value>>8)};
 unsigned crc=reverse((~primary_crc(field,5,5,11))&31,5);
 return {pid,uint8_t(value),uint8_t((value>>8)|(crc<<3))};
}
static Bytes packet_data(const Bytes&payload,bool one=false){
 unsigned crc=reverse((~primary_crc(payload,16,0x8005))&65535,16);Bytes out{uint8_t(one?0x4b:0xc3)};
 out.insert(out.end(),payload.begin(),payload.end());out.push_back(uint8_t(crc));out.push_back(uint8_t(crc>>8));return out;
}
static std::vector<unsigned> symbols(const Bytes&bytes){
 std::vector<unsigned> out;unsigned line=1,ones=0;
 auto bit=[&](unsigned b){if(!b)line=3-line;out.push_back(line);ones=b?ones+1:0;if(ones==6){line=3-line;out.push_back(line);ones=0;}};
 for(unsigned i=0;i<8;i++)bit((0x80>>i)&1);
 for(auto v:bytes)for(unsigned i=0;i<8;i++)bit((v>>i)&1);
 out.insert(out.end(),{0,0,1});return out;
}
struct Rig {
 std::unique_ptr<VerilatedContext> context=std::make_unique<VerilatedContext>();
 std::unique_ptr<VUSBFullSpeed> m;
 uint64_t cycle=0;Bytes receiving;std::deque<Bytes> packets;
 std::vector<unsigned> host_wave,chip_wave;bool record=false;
 Rig(){context->threads(1);m=std::make_unique<VUSBFullSpeed>(context.get());m->connected=1;m->host_rx_ready=1;}
 void step(){
  m->clk=0;m->eval();
  if(m->host_rx_valid&&m->host_rx_ready){receiving.push_back(m->host_rx_byte);if(m->host_rx_last){packets.push_back(receiving);receiving.clear();}}
  m->clk=1;m->eval();cycle++;context->time(cycle*2);
  if(record){host_wave.push_back(m->host_oe?m->host_line:4);chip_wave.push_back(m->chip_oe?m->chip_line:4);}
 }
 void clocks(unsigned n){for(unsigned i=0;i<n;i++)step();}
 void reset(){m->reset=1;clocks(4);m->reset=0;clocks(80);packets.clear();receiving.clear();}
 void write(unsigned addr,uint64_t value){m->mmio_valid=1;m->mmio_write=1;m->mmio_addr=addr;m->mmio_wdata=value;m->eval();require(!m->mmio_error,"literal MMIO write rejected");step();m->mmio_valid=0;m->mmio_write=0;step();}
 uint64_t read(unsigned addr){m->mmio_valid=1;m->mmio_write=0;m->mmio_addr=addr;m->eval();require(!m->mmio_error,"literal MMIO read rejected");auto r=m->mmio_rdata;step();m->mmio_valid=0;step();return r;}
 void send(const Bytes&packet){
  require(!packet.empty()&&packet.size()<=67,"source packet capacity");
  for(unsigned i=0;i<packet.size();i++){
   m->host_valid=1;m->host_last=i+1==packet.size();m->host_byte=packet[i];m->eval();
   unsigned wait=0;while(!m->host_ready){require(++wait<10000,"host source backpressure deadline");step();}
   step();
  }
  m->host_valid=0;m->host_last=0;
 }
 Bytes receive(unsigned deadline=20000){unsigned start=0;while(packets.empty()){require(++start<deadline,"actual wire packet deadline");step();}auto p=packets.front();packets.pop_front();return p;}
 void expect(const Bytes&bytes){require(receive()==bytes,"independently decoded wire packet differs");}
 void ack(){send({0xd2});clocks(500);}
 void inject(const std::vector<unsigned>&wave,int ppm=0){
  m->force_wire=1;m->force_line=1;clocks(100);
  unsigned previous=0;
  for(unsigned i=0;i<wave.size();i++){m->force_line=wave[i];unsigned next=unsigned((25000000ULL*(i+1)+(3000000+3*ppm)/2)/(3000000+3*ppm));clocks(next-previous);previous=next;}
  m->force_line=1;clocks(500);m->force_wire=0;clocks(100);
  packets.clear();receiving.clear();
 }
 void setup(uint64_t word,unsigned address){
  send(token(0x2d,address,0));clocks(500);
  Bytes payload;for(unsigned i=0;i<8;i++)payload.push_back(uint8_t(word>>(8*i)));
  send(packet_data(payload));expect({0xd2});clocks(100);write(168,read(160));
 }
 void queue(unsigned ep,const Bytes&bytes){
  write(ep?72:64,bytes.size());
  for(unsigned o=0;o<bytes.size();o+=8){uint64_t w=0;for(unsigned b=0;b<8&&o+b<bytes.size();b++)w|=uint64_t(bytes[o+b])<<(8*b);write((ep?320:256)+o,w);}
  write(56,1|(uint64_t(ep)<<8));
 }
 void status(unsigned address){queue(0,{});send(token(0x69,address,0));expect(packet_data({},true));ack();write(56,2);}
 void save(const std::string&path){VerilatedSave s;s.open(path.c_str());s<<cycle<<*m;s.close();}
 void load(const std::string&path){VerilatedRestore s;s.open(path.c_str());s>>cycle>>*m;s.close();context->time(cycle*2);}
};
static Bytes file_bytes(const std::string&path){std::ifstream f(path,std::ios::binary);require(bool(f),"state artifact read");return Bytes(std::istreambuf_iterator<char>(f),{});}
static void state_equal(Rig&live,Rig&fork,const std::string&prefix){
 live.save(prefix+"-live");fork.save(prefix+"-fork");require(file_bytes(prefix+"-live")==file_bytes(prefix+"-fork"),"authoritative generated PHY/controller state differs");
}
static void wave_equal(const std::vector<unsigned>&wave,const Bytes&packet){
 size_t begin=0;while(begin<wave.size()&&wave[begin]==4)begin++;require(begin<wave.size(),"no physical SOP");
 size_t end=begin;while(end<wave.size()&&wave[end]!=4)end++;
 auto expected=symbols(packet);
 require((end-begin)*3+3>=expected.size()*25&&(end-begin)*3<=expected.size()*25+3,"predeclared rational symbol duration");
 for(unsigned i=0;i<expected.size();i++){size_t at=begin+(25*(2*i+1))/6;require(at<end&&wave[at]==expected[i],"primary-spec NRZI/stuff/EOP symbols differ");}
}
int main(int argc,char**argv){try{
 require(argc==2,"fixture output directory");
 Bytes digits{'1','2','3','4','5','6','7','8','9'};require(packet_data(digits)==Bytes({0xc3,'1','2','3','4','5','6','7','8','9',0xc8,0xb4}),"CRC16 fixed known answer");
 require(token(0x2d,0,0)==Bytes({0x2d,0,0x10}),"CRC5 fixed token answer");
 Rig r;r.reset();r.record=true;r.send(token(0x69,0,0));r.expect({0x5a});r.clocks(100);
 wave_equal(r.host_wave,token(0x69,0,0));wave_equal(r.chip_wave,{0x5a});r.record=false;
 r.setup(0x0000000000070500ULL,0);r.write(96,7);r.status(0);require(r.m->device_address==7,"address did not commit through real status ACK");
 r.setup(0x0000000000010900ULL,7);r.write(104,1);r.status(7);require(r.m->configured,"configuration did not commit through real status ACK");
 Bytes opaque(64);for(unsigned i=0;i<64;i++)opaque[i]=uint8_t(255-i);
 r.queue(1,opaque);r.send(token(0x69,7,1));r.expect(packet_data(opaque));r.clocks(11000);
 r.send(token(0x69,7,1));r.expect(packet_data(opaque));r.ack();require(!(r.read(16)&0x80),"lost ACK duplicated or consumed queued effect");
 Bytes ones(64,0xff);r.send(token(0xe1,7,2));r.clocks(500);r.host_wave.clear();r.record=true;
 r.send(packet_data(ones));r.expect({0xd2});r.clocks(100);r.record=false;wave_equal(r.host_wave,packet_data(ones));
 require((r.read(88)&127)==64,"real64-byte OUT head missing");
 for(unsigned i=0;i<8;i++)require(r.read(576+i*8)==UINT64_MAX,"real64-byte OUT field differs");
 // Real NAK for a different, correctly toggled OUT while the owned head is
 // retained; neither valid backpressure nor a corrupt following frame erases it.
 Bytes newer(64,0);r.send(token(0xe1,7,2));r.clocks(500);r.send(packet_data(newer,true));r.expect({0x5a});
 require((r.read(88)&127)==64&&r.read(576)==UINT64_MAX,"NAK replaced the retained OUT head");
 auto corrupt_following=packet_data(newer,true);corrupt_following[5]^=1;r.send(token(0xe1,7,2));r.clocks(500);r.send(corrupt_following);r.clocks(2000);
 require(r.packets.empty()&&(r.read(88)&127)==64&&r.read(576)==UINT64_MAX,"bad CRC erased the retained OUT head");
 r.write(56,2|(2<<8));
 auto emitted=r.m->chip_tx_packets;
 std::vector<unsigned> malformed_sync{2,1,2,1,2,1,2,1};auto nested=symbols(token(0x69,7,0));
 malformed_sync.insert(malformed_sync.end(),nested.begin(),nested.end());r.inject(malformed_sync);
 require(r.m->chip_tx_packets==emitted,"malformed SYNC resynchronized inside the same physical packet");
 auto short_eop=symbols(token(0x69,7,0));short_eop.erase(short_eop.end()-2);r.inject(short_eop);
 require(r.m->chip_tx_packets==emitted,"one-symbol SE0 EOP admitted a packet");
 Rig recover;recover.reset();auto truncated_eop=symbols(token(0x69,0,0));truncated_eop.erase(truncated_eop.end()-2);recover.inject(truncated_eop);
 require(recover.m->chip_rx_packets==0,"truncated EOP admitted packet");
 recover.send(token(0x69,0,0));recover.clocks(2000);require(!recover.packets.empty()&&recover.receive()==Bytes({0x5a}),"valid packet after malformed short EOP remained quarantined");
 auto illegal_se1=symbols(token(0x69,7,0));illegal_se1[11]=3;r.inject(illegal_se1);
 require(r.m->chip_tx_packets==emitted,"SE1 admitted a packet");
 auto dribble=symbols(token(0x69,7,0));dribble.insert(dribble.end()-3,dribble[dribble.size()-4]);r.inject(dribble);
 require(r.m->chip_tx_packets==emitted+1,"bounded last-bit dribble was not accepted");
 r.send(token(0xe1,7,2));r.clocks(500);
 auto corrupt_stuff=symbols(packet_data(ones));unsigned run=1,stuff_at=0;
 for(unsigned i=8;i+3<corrupt_stuff.size();i++){
  if(corrupt_stuff[i]==corrupt_stuff[i-1])run++;else run=0;
  if(run==6){stuff_at=i+1;break;}
 }
 require(stuff_at&&corrupt_stuff[stuff_at]!=corrupt_stuff[stuff_at-1],"independent stuffed-zero locator");
 corrupt_stuff[stuff_at]=corrupt_stuff[stuff_at-1];auto stuff_before=r.m->chip_stuff_errors;
 emitted=r.m->chip_tx_packets;r.inject(corrupt_stuff);
 require(r.m->chip_tx_packets==emitted&&r.m->chip_stuff_errors>stuff_before&&!(r.read(16)&0x20),
         "seven ones produced an ACK or published an OUT head");
 Rig starving;starving.reset();starving.m->host_valid=1;starving.m->host_byte=0xd2;starving.m->host_last=0;starving.step();starving.m->host_valid=0;starving.clocks(1000);
 require(starving.m->hu==1&&starving.m->chip_rx_packets==0&&starving.m->host_tx_packets==0,
         "source underflow emitted a valid shortened packet");
 // A complete blocked output is retained; a following physical packet is
 // rejected rather than overwriting the accepted byte or withdrawing valid.
 Rig held;held.reset();held.m->host_rx_ready=0;held.send(token(0x69,0,0));held.clocks(1000);
 require(held.m->host_rx_valid&&held.m->host_rx_last&&held.m->host_rx_byte==0x5a,"completed blocked RX head not retained");
 held.send(token(0x69,0,0));held.clocks(1000);
 require(held.m->host_rx_valid&&held.m->host_rx_last&&held.m->host_rx_byte==0x5a&&held.m->host_line_errors>0,
         "new wire packet overwrote a blocked accepted RX head");
 held.m->host_rx_ready=1;held.expect({0x5a});held.clocks(100);require(held.packets.empty(),"blocked RX head duplicated");
 Rig blocked;blocked.reset();blocked.queue(0,ones);blocked.m->host_rx_ready=0;
 blocked.send(token(0x69,0,0));blocked.clocks(7000);
 require(blocked.m->host_rx_packets==0&&blocked.m->host_line_errors>0&&!blocked.m->host_rx_valid,
         "stream backpressure published a truncated packet");
 // Independent nominal +/-2500ppm sources at every rational sampling phase.
 // These are digital input vectors, not oscillator/analog qualification.
 for(int ppm:{-2500,0,2500})for(unsigned phase=0;phase<25;phase++){
  Rig shifted;shifted.reset();shifted.clocks(phase);shifted.inject(symbols(packet_data(ones)),ppm);
  require(shifted.m->chip_rx_packets==1&&shifted.m->chip_stuff_errors==0&&shifted.m->chip_line_errors==0,
          "independent permitted source rate/phase packet was not decoded");
 }
 Rig overlength;overlength.reset();overlength.inject(symbols(packet_data(Bytes(65,0xff))));
 require(overlength.m->chip_rx_packets==0&&overlength.m->chip_line_errors>0,
         "over-capacity physical packet published a complete head");
 auto wrong=token(0x69,7,1);wrong[2]^=8;auto errors=r.m->controller_errors;r.send(wrong);r.clocks(2000);
 require(r.packets.empty()&&r.m->controller_errors==errors+1,"wire CRC corruption manufactured response");
 for(unsigned cut:{12U,70U,98U,560U}){
  Rig original;original.reset();original.record=true;original.send(packet_data(Bytes(64,0xff)));original.clocks(cut);
  std::string path=std::string(argv[1])+"/cut-"+std::to_string(cut);original.save(path);
  Rig fork;fork.load(path);original.host_wave.clear();original.chip_wave.clear();fork.record=true;
  original.clocks(7000);fork.clocks(7000);
  require(original.host_wave==fork.host_wave&&original.chip_wave==fork.chip_wave&&original.m->chip_rx_packets==fork.m->chip_rx_packets,
          "in-flight codec checkpoint suffix differs");
  require(original.m->chip_rx_packets==1&&original.m->chip_stuff_errors==0&&original.m->chip_line_errors==0,
          "checkpoint equality hid a failed actual codec packet");
  state_equal(original,fork,path+"-suffix");
 }
 Rig midreset;midreset.reset();midreset.send(packet_data(ones));midreset.clocks(70);midreset.m->force_wire=1;midreset.m->force_line=0;midreset.clocks(120);
 std::string reset_path=std::string(argv[1])+"/mid-reset";midreset.save(reset_path);Rig reset_fork;reset_fork.load(reset_path);
 midreset.clocks(500);reset_fork.clocks(500);midreset.m->force_wire=0;reset_fork.m->force_wire=0;midreset.clocks(200);reset_fork.clocks(200);
 require(midreset.m->chip_rx_packets==0&&midreset.m->chip_oe==0&&midreset.m->host_oe==0,"in-flight reset retained completed packet/drive");
 state_equal(midreset,reset_fork,reset_path+"-suffix");
 Rig retained;retained.reset();retained.m->host_rx_ready=0;retained.send(token(0x69,0,0));retained.clocks(1000);
 require(retained.m->host_rx_valid&&retained.m->host_rx_last,"checkpoint completed retained head missing");
 std::string held_path=std::string(argv[1])+"/held-rx";retained.save(held_path);Rig held_fork;held_fork.load(held_path);
 retained.clocks(200);held_fork.clocks(200);retained.m->host_rx_ready=1;held_fork.m->host_rx_ready=1;retained.clocks(200);held_fork.clocks(200);
 require(retained.packets==held_fork.packets&&retained.packets.front()==Bytes({0x5a}),"retained head fork outcome differs");state_equal(retained,held_fork,held_path+"-suffix");
 r.m->force_wire=1;r.m->force_line=0;r.clocks(5000000);r.m->force_wire=0;r.clocks(1000);
 require(r.m->device_address==0&&!r.m->configured,"actual SE0 reset retained address/configuration");
 std::cout<<"USB_FS_LITERAL_PASS two PHYs control/status opaque64 lostACK CRC reset NRZI stuff EOP clockphase backpressure exact6statecuts\n";
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
