// Host-only pin stimulus and independent observations. No guest/radio policy.
#include "Vlemma_ble_packet.h"
#include "verilated.h"
#include "verilated_save.h"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
using Bits=std::vector<unsigned>;
static void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
struct Endpoint{
 std::unique_ptr<VerilatedContext> context=std::make_unique<VerilatedContext>();
 std::unique_ptr<Vlemma_ble_packet> d=std::make_unique<Vlemma_ble_packet>(context.get());
 uint64_t clocks=0;
 Endpoint(){d->clk=0;d->reset=1;d->enabled=1;d->coex_allow=1;d->valid=0;d->rx_sample_valid=0;step();d->reset=0;}
 void step(bool sample=false,unsigned bit=0){d->rx_sample_valid=sample;d->rx_sample_bit=bit;d->clk=0;d->eval();context->timeInc(1);d->clk=1;d->eval();context->timeInc(1);clocks++;}
 void put(unsigned a,uint64_t v){d->valid=1;d->write=1;d->size=3;d->addr=a;d->wdata=v;d->eval();need(!d->error,"unexpected MMIO error");step();d->valid=0;d->eval();}
 uint64_t get(unsigned a){d->valid=1;d->write=0;d->size=3;d->addr=a;d->eval();need(!d->error,"read bus error");auto v=d->rdata;d->valid=0;d->eval();return v;}
 void submit(unsigned h,const std::vector<uint8_t>&p){put(48,h);put(56,p.size());for(unsigned i=0;i<p.size();i++)put(256+8*i,p[i]);put(64,1);need(d->tx_active,"submit rejected");}
 void save(const std::string&p){VerilatedSave s;s.open(p);s<<clocks;s<<*d;s.close();}
 void load(const std::string&p){VerilatedRestore s;s.open(p);s>>clocks;s>>*d;s.close();}
};
static Bits literal(const std::string&s){Bits b;for(char c:s)if(c=='0'||c=='1')b.push_back(c-'0');return b;}
// Official BT5.4 Vol6C4.3.1 sequence, transmission order (not computed from implementation).
static const Bits official=literal("10101010 11010100 10011000 00010000 01010101 01100011 11011001 01001010 10001100 11011011 01111101 10111001 10110010 00101111 10011000");
static unsigned byte(const Bits&b,size_t begin){unsigned v=0;for(unsigned i=0;i<8;i++)v|=b.at(begin+i)<<i;return v;}
// Independent oracle uses diagram-position arrays, unlike RTL integer shift feedback.
static Bits encode(unsigned aa,unsigned init,unsigned channel,unsigned header,const std::vector<uint8_t>&payload){
 Bits out;for(unsigned i=0;i<8;i++)out.push_back((aa&1)^(i&1));for(unsigned i=0;i<32;i++)out.push_back((aa>>i)&1);
 unsigned r[24],w[7];for(unsigned i=0;i<24;i++)r[i]=(init>>(23-i))&1;for(unsigned i=0;i<7;i++)w[i]=((channel|64)>>i)&1;
 auto append=[&](unsigned bit){out.push_back(bit^w[0]);unsigned old=w[0];for(unsigned i=0;i<6;i++)w[i]=w[i+1];w[6]=old;w[2]^=old;};
 auto octet=[&](unsigned x){for(unsigned i=0;i<8;i++){unsigned bit=(x>>i)&1,fb=r[0]^bit;for(unsigned j=0;j<23;j++)r[j]=r[j+1];r[23]=0;for(unsigned exponent:{0,1,3,4,6,9,10})r[23-exponent]^=fb;append(bit);}};
 octet(header);octet(payload.size());for(auto x:payload)octet(x);for(unsigned i=0;i<24;i++)append(r[i]);return out;
}
static std::vector<uint8_t> decode(const Bits&bits,unsigned aa,unsigned init,unsigned channel){
 need(bits.size()>=80,"oracle short packet");for(unsigned i=0;i<8;i++)need(bits[i]==((aa&1)^(i&1)),"oracle preamble");for(unsigned i=0;i<32;i++)need(bits[8+i]==((aa>>i)&1),"oracle access address");
 Bits plain;unsigned w[7];for(unsigned i=0;i<7;i++)w[i]=((channel|64)>>i)&1;
 for(size_t i=40;i<bits.size();i++){plain.push_back(bits[i]^w[0]);unsigned old=w[0];for(unsigned j=0;j<6;j++)w[j]=w[j+1];w[6]=old;w[2]^=old;}
 unsigned n=byte(plain,8);need(bits.size()==80+8*n,"oracle length");std::vector<uint8_t> data;for(unsigned i=0;i<n;i++)data.push_back(byte(plain,16+8*i));
 need(encode(aa,init,channel,byte(plain,0),data)==bits,"oracle CRC/encoded packet differs");return data;
}
struct Wire{Bits a,b;std::vector<uint64_t> a_times,b_times;};
static void run(Endpoint&a,Endpoint&b,Wire&wire,unsigned clocks,unsigned corrupt=~0U,bool lose=false){
 bool sampleA=false,sampleB=false;unsigned bitA=0,bitB=0;
 for(unsigned i=0;i<clocks;i++){
   a.step(sampleB,bitB);b.step(sampleA,bitA);sampleA=a.d->tx_sample_valid;sampleB=b.d->tx_sample_valid;
   bitA=a.d->tx_sample_bit;bitB=b.d->tx_sample_bit;
   if(sampleA){unsigned at=wire.a.size();wire.a.push_back(bitA);wire.a_times.push_back(a.clocks);if(at==corrupt){if(lose)sampleA=false;else bitA^=1;}}
   if(sampleB){wire.b.push_back(bitB);wire.b_times.push_back(b.clocks);}
 }
 // End the last propagated decision; this does not drain either modeled device.
}
static void head(Endpoint&e,unsigned h,const std::vector<uint8_t>&p){need(e.get(16)&4,"RX queue empty");need(e.get(88)==(h|(p.size()<<8)),"RX metadata");for(unsigned i=0;i<p.size();i++)need(e.get(512+8*i)==p[i],"RX data");}
static void inject(Endpoint&e,const Bits&b){for(auto x:b){e.step(true,x);for(unsigned t=0;t<99;t++)e.step();}e.step();}
int main(int argc,char**argv){try{
 need(argc==2,"snapshot output directory required");std::string out=argv[1];
 need(encode(0xaa08192b,0xc4c181,16,0x16,{1,2,3,4,5})==official,"independent oracle official KAT mismatch");
 Endpoint a,b;Wire wire;a.submit(0x16,{1,2,3,4,5});auto submitted=a.clocks;run(a,b,wire,14000);
 need(wire.a_times.front()-submitted==100&&wire.a_times.back()-submitted==12000,"first/last symbol clock");for(size_t i=1;i<wire.a_times.size();i++)need(wire.a_times[i]-wire.a_times[i-1]==100,"LE1M symbol cadence");need(a.get(104)==13000,"predeclared interpacket guard countdown");
 need(wire.a==official,"actual RTL official packet bits mismatch");need(decode(wire.a,0xaa08192b,0xc4c181,16)==std::vector<uint8_t>({1,2,3,4,5}),"independent decoder");head(b,0x16,{1,2,3,4,5});
 need(a.d->tx_packets==1&&b.d->rx_packets==1,"actual completion counts");b.put(64,2);run(a,b,wire,16000);
 b.submit(2,{0x4c,0x4d,0x43,0x4d,0x50,0x30,0x30,0x31,1,0,2,0});run(a,b,wire,22000);
 need(decode(wire.b,0xaa08192b,0xc4c181,16)==std::vector<uint8_t>({0x4c,0x4d,0x43,0x4d,0x50,0x30,0x30,0x31,1,0,2,0}),"reverse independent decode");head(a,2,{0x4c,0x4d,0x43,0x4d,0x50,0x30,0x30,0x31,1,0,2,0});
 std::cout<<"BLE KAT official5.4 data bytes and two endpoints independently decoded PASS\n";
 std::cout<<"BLE observed bits="<<wire.a.size()<<" first_clocks="<<wire.a_times.front()-submitted<<" last_clocks="<<wire.a_times.back()-submitted<<" reverse_bytes="<<wire.b.size()/8-10<<"\n";
 for(unsigned channel:{0U,36U}){Endpoint c,d;c.put(40,channel);d.put(40,channel);std::vector<uint8_t> payload;for(unsigned i=0;i<27;i++)payload.push_back(i);Wire w;c.submit(2,payload);c.put(256,99);need(c.get(80)==3,"active staging did not reject mutation");run(c,d,w,33000);need(decode(w.a,0xaa08192b,0xc4c181,channel)==payload,"maximum packet independent decode");head(d,2,payload);}
 {Endpoint c,d;Wire w;c.submit(1,{});run(c,d,w,10000);need(decode(w.a,0xaa08192b,0xc4c181,16).empty(),"empty data packet CRC");head(d,1,{});}
 {Endpoint c;c.d->valid=1;c.d->write=1;c.d->size=3;c.d->addr=56;c.d->wdata=28;c.d->eval();need(c.d->error,"oversized TX length accepted");c.step();c.d->valid=0;need(c.get(56)==0,"oversized length mutated staging");}
  {Endpoint c;inject(c,official);head(c,0x16,{1,2,3,4,5});inject(c,official);need(c.d->rx_packets==1&&c.d->rx_errors==1&&c.get(80)==4,"overflow overwrote stable RX head");head(c,0x16,{1,2,3,4,5});}
 {Endpoint c;auto broken=official;broken[67]^=1;inject(c,broken);need(c.d->crc_errors==1&&!(c.get(16)&4),"CRC corruption published packet");}
 {Endpoint c;for(unsigned i=0;i<official.size();i++){if(i!=67)c.step(true,official[i]);else c.step();for(unsigned t=0;t<99;t++)c.step();}need(c.d->rx_errors==1&&!(c.get(16)&4),"lost sample published packet");}
 {Endpoint c;c.put(40,15);inject(c,official);need(c.d->crc_errors+c.d->rx_errors!=0&&!(c.get(16)&4),"wrong whitening channel admitted");}
 {Endpoint c;c.submit(2,{9,8,7});for(unsigned t=0;t<6500;t++)c.step();need(c.d->tx_active,"coexistence probe not in flight");c.d->coex_allow=0;c.step();need(!c.d->tx_active&&!c.d->tx_sample_valid&&c.get(80)==6,"coex withdrawal failed cancel");c.d->enabled=0;c.d->valid=1;c.d->write=1;c.d->addr=64;c.d->wdata=1;c.d->eval();need(c.d->error,"powered-down admission");c.step();need(c.d->tx_packets==0&&c.d->rx_packets==0,"power loss retained packet state");}
 {Endpoint c;inject(c,official);c.d->reset=1;c.step();c.d->reset=0;need(!(c.get(16)&7)&&c.get(72)==0,"reset retained packet or irq");}
 {Endpoint c;for(unsigned i=0;i<official.size();i++){if(i+1==official.size()){c.d->valid=1;c.d->write=1;c.d->size=3;c.d->addr=72;c.d->wdata=15;}c.step(true,official[i]);c.d->valid=0;for(unsigned t=0;t<99;t++)c.step();}need(c.get(72)==2&&c.d->irq,"RX event lost to coincident W1C");c.put(72,2);need(c.get(72)==0&&!c.d->irq,"IRQ W1C failed");}
 {Endpoint c;for(unsigned i=0;i<60;i++){c.step(true,official[i]);for(unsigned t=0;t<99;t++)c.step();}need(c.d->rx_active,"reset probe not receiving");c.d->reset=1;c.step();c.d->reset=0;for(unsigned i=60;i<official.size();i++){c.step(true,official[i]);for(unsigned t=0;t<99;t++)c.step();}need(c.d->rx_packets==0&&!(c.get(16)&4),"reset prefix resumed without sync");}
 {Endpoint c;for(uint64_t aa:{0ULL,0xffffffffULL,0x8e89bed6ULL,0x8e89bed7ULL,0xaaaaaaaaULL,0x33333333ULL,0x100000000ULL}){c.d->valid=1;c.d->write=1;c.d->size=3;c.d->addr=24;c.d->wdata=aa;c.d->eval();need(c.d->error,"invalid data access address bus admitted");c.step();c.d->valid=0;need(c.get(24)==0xaa08192b,"bad address changed context");}}
  std::cout<<"BLE corruption loss wrong-channel bounded-head reset power coexistence PASS\n";
 // Observational snapshots at arbitrary TX/RX whitening/CRC boundaries. Original untouched.
 for(unsigned cut:{1U,4100U,6901U,11199U}){
   Endpoint x,y;Wire prefix;x.submit(0x16,{1,2,3,4,5});run(x,y,prefix,cut);
   x.save(out+"/tx-"+std::to_string(cut)+".state");y.save(out+"/rx-"+std::to_string(cut)+".state");
   // Pending external decisions are authoritative input state, saved before their effect.
   {std::ofstream io(out+"/wire-"+std::to_string(cut)+".state");io<<unsigned(x.d->tx_sample_valid)<<" "<<unsigned(y.d->tx_sample_valid)<<" "<<unsigned(x.d->tx_sample_bit)<<" "<<unsigned(y.d->tx_sample_bit)<<"\n";need(bool(io),"wire checkpoint write");}
   Endpoint xx,yy;xx.load(out+"/tx-"+std::to_string(cut)+".state");yy.load(out+"/rx-"+std::to_string(cut)+".state");
   // Rebind only owned host model references. Propagate in-flight wire sample explicitly.
   bool sa=x.d->tx_sample_valid,sb=y.d->tx_sample_valid;unsigned ba=x.d->tx_sample_bit,bb=y.d->tx_sample_bit;
   unsigned fsa,fsb,fba,fbb;{std::ifstream io(out+"/wire-"+std::to_string(cut)+".state");io>>fsa>>fsb>>fba>>fbb;need(bool(io)&&fsa<=1&&fsb<=1&&fba<=1&&fbb<=1,"invalid wire checkpoint");}
   for(unsigned t=0;t<30000;t++){
     x.step(sb,bb);y.step(sa,ba);xx.step(fsb,fbb);yy.step(fsa,fba);
     need(x.d->tx_sample_valid==xx.d->tx_sample_valid&&x.d->tx_sample_bit==xx.d->tx_sample_bit&&y.d->tx_sample_valid==yy.d->tx_sample_valid&&y.d->tx_sample_bit==yy.d->tx_sample_bit,"checkpoint wire suffix");
     need(x.get(16)==xx.get(16)&&y.get(16)==yy.get(16)&&x.get(72)==xx.get(72)&&y.get(72)==yy.get(72)&&x.get(80)==xx.get(80)&&y.get(80)==yy.get(80),"checkpoint state/IRQ suffix");
     sa=x.d->tx_sample_valid;sb=y.d->tx_sample_valid;ba=x.d->tx_sample_bit;bb=y.d->tx_sample_bit;
     fsa=xx.d->tx_sample_valid;fsb=yy.d->tx_sample_valid;fba=xx.d->tx_sample_bit;fbb=yy.d->tx_sample_bit;
   }
   need(x.d->ticks==xx.d->ticks&&y.d->ticks==yy.d->ticks&&x.d->tx_packets==xx.d->tx_packets&&y.d->rx_packets==yy.d->rx_packets,"checkpoint counters");head(y,0x16,{1,2,3,4,5});head(yy,0x16,{1,2,3,4,5});
 }
 std::cout<<"BLE four arbitrary live TX/RX checkpoints exact30000-clock suffix PASS\n";
 return 0;
 }catch(const std::exception&e){std::cerr<<"BLE FAIL: "<<e.what()<<"\n";return 1;}}
