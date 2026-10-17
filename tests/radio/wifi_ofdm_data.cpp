// Host-only raw clocks/MMIO/IQ stimuli and independent numerical observations.
// No instruction execution, receiver publication, guest verdict, or RF claim.
#include "VWiFiDataProbe.h"
#include "verilated.h"
#include "verilated_save.h"
#include <array>
#include <cmath>
#include <complex>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
using Bytes=std::vector<uint8_t>;
using Bits=std::vector<unsigned>;
static void need(bool b,const std::string&s){if(!b)throw std::runtime_error(s);}
static constexpr double pi=3.141592653589793238462643383279502884;
static int tone(unsigned d){static const int bins[]={-26,-25,-24,-23,-22,-20,-19,-18,-17,-16,-15,-14,-13,-12,-11,-10,-9,-8,-6,-5,-4,-3,-2,-1,1,2,3,4,5,6,8,9,10,11,12,13,14,15,16,17,18,19,20,22,23,24,25,26};return bins[d];}
static uint32_t crc(const Bytes&v){
 // Polynomial long division in diagram order, independent of RTL octet helper.
 std::array<unsigned,32> s;for(auto&b:s)b=1;
 for(auto octet:v)for(unsigned bit=0;bit<8;bit++){
  unsigned f=s[31]^((octet>>bit)&1);for(unsigned j=31;j>0;j--)s[j]=s[j-1];s[0]=0;
  for(unsigned exponent:{0U,1U,2U,4U,5U,7U,8U,10U,11U,12U,16U,22U,23U,26U})s[exponent]^=f;
 }
 uint32_t vout=0;for(unsigned j=0;j<32;j++)vout|=(s[31-j]^1U)<<j;return vout;
}
static Bits convolution(const Bits&input){
 std::array<unsigned,6> delay{};Bits out;
 for(auto b:input){out.push_back(b^delay[1]^delay[2]^delay[4]^delay[5]);out.push_back(b^delay[0]^delay[1]^delay[2]^delay[5]);for(unsigned j=5;j>0;j--)delay[j]=delay[j-1];delay[0]=b;}
 return out;
}
static Bits scramble(const Bits&input,unsigned seed){
 std::array<unsigned,7> s;for(unsigned j=0;j<7;j++)s[j]=(seed>>j)&1;Bits out;
 for(auto b:input){auto f=s[6]^s[3];out.push_back(b^f);for(unsigned j=6;j>0;j--)s[j]=s[j-1];s[0]=f;}
 return out;
}
static std::vector<Bits> encode(const Bytes&payload,unsigned seed,bool bad_fcs=false){
 Bytes psdu=payload;uint32_t fcs=crc(payload)^(bad_fcs?1U:0U);for(unsigned i=0;i<4;i++)psdu.push_back(fcs>>(8*i));
 Bits raw(16,0);for(auto b:psdu)for(unsigned k=0;k<8;k++)raw.push_back((b>>k)&1);
 unsigned tail=raw.size();unsigned total=((tail+6+23)/24)*24;raw.resize(total,0);Bits plain=scramble(raw,seed);
 for(unsigned k=tail;k<tail+6;k++)plain[k]=0;
 auto coded=convolution(plain);std::vector<Bits> blocks;
 for(unsigned begin=0;begin<coded.size();begin+=48){
  // Column write, row read of a 16x3 matrix; no RTL permutation expression.
  Bits output;for(unsigned row=0;row<16;row++)for(unsigned column=0;column<3;column++)output.push_back(coded[begin+column*16+row]);
  blocks.push_back(output);
 }
 return blocks;
}
static std::complex<double> expected_sample(const Bits&bits,unsigned n,unsigned symbol){
 std::complex<double> sum{};
 for(unsigned d=0;d<48;d++)sum+=double(bits[d]?1:-1)*std::polar(1.0,2*pi*tone(d)*n/64);
 Bits pilot_raw(128,0);auto p=scramble(pilot_raw,127);int sign=p.at(symbol+1)?-1:1;
 for(unsigned j=0;j<4;j++){int t=std::array<int,4>{-21,-7,7,21}[j];sum+=double(j==3?-sign:sign)*std::polar(1.0,2*pi*t*n/64);}
 return sum*(16384.0/64.0);
}
struct Sample{bool valid=false;int16_t i=0,q=0;};
struct Endpoint{
 std::unique_ptr<VerilatedContext> context=std::make_unique<VerilatedContext>();
 std::unique_ptr<VWiFiDataProbe> d=std::make_unique<VWiFiDataProbe>(context.get());uint64_t clocks=0;
 Endpoint(){d->clk=0;d->reset=1;d->enabled=1;d->coex_allow=1;d->valid=0;d->rx_sample_valid=0;d->probe_bits=0;d->probe_state=0;d->probe_index=0;d->probe_pilot=0;step();d->reset=0;}
 void step(Sample s={}){d->rx_sample_valid=s.valid;d->rx_i=uint16_t(s.i);d->rx_q=uint16_t(s.q);d->clk=0;d->eval();context->timeInc(1);d->clk=1;d->eval();context->timeInc(1);clocks++;}
 void put(unsigned a,uint64_t v){d->valid=1;d->write=1;d->size=3;d->addr=a;d->wdata=v;d->eval();need(!d->error,"bus write admission");step();d->valid=0;d->eval();}
 uint64_t get(unsigned a){d->valid=1;d->write=0;d->size=3;d->addr=a;d->eval();need(!d->error,"bus read admission");auto value=d->rdata;d->valid=0;d->eval();return value;}
 void stage(const Bytes&v,unsigned seed){put(24,v.size());put(32,seed);for(unsigned j=0;j<v.size();j++)put(256+8*j,v[j]);}
 void arm(unsigned size,unsigned seed){put(40,size);put(48,seed);put(56,2);need(d->rx_active,"RX arm");}
 void submit(){put(56,1);need(d->tx_active,"TX submit");}
 Sample sample()const{return {bool(d->tx_sample_valid),int16_t(d->tx_i),int16_t(d->tx_q)};}
 void save(const std::string&p){VerilatedSave f;f.open(p);f<<clocks;f<<*d;f.close();}
 void load(const std::string&p){VerilatedRestore f;f.open(p);f>>clocks;f>>*d;f.close();context->time(clocks*2);}
};
struct Link{
 Sample a,b;std::vector<Sample> samples_a,samples_b;std::vector<uint64_t> times_a,times_b;
 void step(Endpoint&x,Endpoint&y,unsigned lose=~0U,unsigned flips=0,const std::vector<Bits>*reference=nullptr){
  x.step(b);y.step(a);a=x.sample();b=y.sample();
  if(a.valid){unsigned at=samples_a.size();samples_a.push_back(a);times_a.push_back(x.clocks);
   if(at==lose)a.valid=false;
   if(flips&&at<80){need(reference,"corruption needs independent transmitted-symbol oracle");unsigned n=at<16?at+48:at-16;std::complex<double> delta{};
    for(unsigned j=0;j<flips;j++)delta+=double((*reference)[0][j]?-2:2)*std::polar(1.0,2*pi*tone(j)*n/64)*(16384.0/64.0);
    a.i=int16_t(int(a.i)+int(std::llround(delta.real())));a.q=int16_t(int(a.q)+int(std::llround(delta.imag())));
   }
  }
  if(b.valid){samples_b.push_back(b);times_b.push_back(y.clocks);}
 }
 void run(Endpoint&x,Endpoint&y,unsigned count,unsigned lose=~0U,unsigned flips=0,const std::vector<Bits>*reference=nullptr){for(unsigned j=0;j<count;j++)step(x,y,lose,flips,reference);}
};
static void head(Endpoint&e,const Bytes&p){need(e.get(16)&4,"RX head absent fault="+std::to_string(e.get(72)));need(e.get(88)==p.size(),"RX immutable length");for(unsigned j=0;j<16;j++)need(e.get(512+8*j)==(j<p.size()?p[j]:0),"actual receiver payload/padding differs");}
static double waveform(const Link&w,const Bytes&data,unsigned seed){
 auto ref=encode(data,seed);need(w.samples_a.size()==ref.size()*80,"real complex sample count");double error=0;
 for(unsigned k=0;k<w.samples_a.size();k++){unsigned n=k%80<16?k%80+48:k%80-16;auto exp=expected_sample(ref[k/80],n,k/80);auto s=w.samples_a[k];error=std::max(error,std::max(std::abs(s.i-exp.real()),std::abs(s.q-exp.imag())));
  if(k)need(w.times_a[k]-w.times_a[k-1]==5,"20Msample cadence includes a gap");
 }
 need(error<=1.5,"integer IFFT exceeded independently derived Q14 bound: "+std::to_string(error));return error;
}
static Bytes file_bytes(const std::string&p){std::ifstream f(p,std::ios::binary);need(bool(f),"state file absent");return Bytes(std::istreambuf_iterator<char>(f),{});}
static void raw_equal(Endpoint&x,Endpoint&y){
 need(x.sample().valid==y.sample().valid&&x.sample().i==y.sample().i&&x.sample().q==y.sample().q,"restored raw sample suffix differs");
 need(x.d->ready==y.d->ready&&x.d->error==y.d->error&&x.d->irq==y.d->irq&&x.d->controller_busy==y.d->controller_busy,"restored bus/interrupt/busy outputs differ");
 for(unsigned a:{0U,8U,16U,24U,32U,40U,48U,56U,64U,72U,80U,88U,96U,104U,112U,120U,128U,136U})need(x.get(a)==y.get(a),"restored public state differs");
 for(unsigned i=0;i<16;i++)for(unsigned base:{256U,512U})need(x.get(base+8*i)==y.get(base+8*i),"restored staging/retained head differs");
}
int main(int argc,char**argv){try{
 need(argc==2||argc==3,"new snapshot directory and optional guest-produced payload file required");std::string out=argv[1];
 need(crc(Bytes{'1','2','3','4','5','6','7','8','9'})==0xcbf43926,"independent IEEE CRC32 known answer");
 // IEEE99/107 Tables7/8 (proposal) literal bits, not manufactured by the RTL.
 const uint64_t literal_encoded=0x0e45889f13b0ULL;
 Endpoint kat;kat.d->probe_bits=0x00d064;kat.d->eval();need(kat.d->probe_encoded==literal_encoded&&kat.d->probe_final==0,"IEEE public SIGNAL BCC numerical vector");
 // Explicitly derived from the complete Table8 and16x3 permutation, with
 // all visible Table9 entries independently checked. Table10 is rejected:
 // its tone+11 contradicts its own Table9 bit33=0. Original a2 FAIL retained.
 const std::array<int,48> literal_sign={-1,1,1,-1,1,-1,-1,1,1,-1,1,-1,1,1,-1,1,-1,-1,-1,-1,1,1,1,-1,1,-1,-1,1,-1,1,-1,-1,1,-1,1,1,1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,-1};
 Bits literal_bits;for(auto s:literal_sign)literal_bits.push_back(s>0);
 for(unsigned d=0;d<48;d++)need(((kat.d->probe_interleaved>>d)&1)==literal_bits[d],"published BCC vector under explicit common permutation differs");
 need(kat.d->probe_interleaved==0x401d2970b596ULL,"derived literal complete interleaver vector");
 for(auto entry:std::vector<std::pair<unsigned,unsigned>>{{0,0},{1,1},{2,1},{8,1},{9,0},{10,1},{16,0},{17,0},{18,0},{24,1},{25,0},{26,0},{32,1},{33,0},{34,1},{40,0},{41,0}})
  need(((kat.d->probe_interleaved>>entry.first)&1)==entry.second,"visible primary Table9 entry differs");
 double kat_error=0;
 for(unsigned n=0;n<64;n++){kat.d->probe_index=n;kat.d->eval();auto expected=expected_sample(literal_bits,n,0);kat_error=std::max(kat_error,std::max(std::abs(int16_t(kat.d->probe_i)-expected.real()),std::abs(int16_t(kat.d->probe_q)-expected.imag())));}
 need(kat_error<=1.5,"known-vector complex IFFT bound");
 Bytes data={'L','E','M','M','A',0x00,0xff,0x80,0x01};Endpoint a,b;Link link;a.stage(data,93);b.arm(data.size(),93);a.submit();link.run(a,b,5000);head(b,data);double maximum_error=waveform(link,data,93);need(a.d->tx_packets==1&&b.d->rx_packets==1&&b.d->last_metric==0,"genuine endpoint completion counters");
 b.put(56,3);b.put(64,7);a.put(64,7);a.arm(16,127);Bytes reply(16);for(unsigned j=0;j<16;j++)reply[j]=uint8_t(j*17);b.stage(reply,127);b.submit();Link reverse;reverse.run(b,a,6000);head(a,reply);maximum_error=std::max(maximum_error,waveform(reverse,reply,127));
 std::cout<<"WIFI common BCC known-answer + actual complex OFDM two-endpoint payload PASS\n";
 std::cout<<"WIFI IQ observations sample_hz=20000000 clock_hz=100000000 maximum_Q14_error="<<maximum_error<<" KAT_error="<<kat_error<<" forward_samples="<<link.samples_a.size()<<" reverse_samples="<<reverse.samples_a.size()<<"\n";
 for(unsigned length:{1U,2U,15U,16U})for(unsigned seed:{1U,93U,127U}){
  Bytes payload(length);for(unsigned j=0;j<length;j++)payload[j]=uint8_t((j*73+length*11)^seed);Endpoint x,y;Link w;x.stage(payload,seed);y.arm(length,seed);x.submit();w.run(x,y,6000);head(y,payload);waveform(w,payload,seed);
 }
 {Endpoint x,y;Link w;x.stage(data,93);y.arm(data.size(),93);x.submit();auto ref=encode(data,93);w.run(x,y,5000,~0U,1,&ref);head(y,data);need(y.d->last_metric==1,"single changed BPSK tone was not actual corrected BCC error");}
 {Endpoint x,y;Link w;x.stage(data,93);y.arm(data.size(),93);x.submit();auto ref=encode(data,93);w.run(x,y,5000,~0U,24,&ref);need(y.d->rx_packets==0&&!(y.get(16)&4)&&y.get(72)!=0,"many changed tones published corrupt data");}
 for(unsigned lost:{0U,17U,79U,80U,159U,479U}){Endpoint x,y;Link w;x.stage(data,93);y.arm(data.size(),93);x.submit();w.run(x,y,5000,lost);std::cout<<"WIFI loss_observation index="<<lost<<" packets="<<y.d->rx_packets<<" head="<<(y.get(16)&4)<<" fault="<<y.get(72)<<"\n";need(y.d->rx_packets==0&&!(y.get(16)&4)&&y.get(72)==(lost==0?9U:4U),"lost I/Q sample did not fail closed under acquired versus initial alignment contract");}
 // Clean BCC with deliberately bad FCS: independent complex waveform input.
 // This exercises CRC rejection separately from FEC metric/SERVICE rejection.
 {Endpoint y;y.arm(data.size(),93);auto forged=encode(data,93,true);unsigned clock=0;
  for(unsigned symbol=0;symbol<forged.size();symbol++)for(unsigned at=0;at<80;at++){
   unsigned n=at<16?at+48:at-16;auto v=expected_sample(forged[symbol],n,symbol);
   y.step({true,int16_t(std::llround(v.real())),int16_t(std::llround(v.imag()))});clock++;
   for(unsigned gap=0;gap<4;gap++){y.step();clock++;}
  }
  for(;clock<5000;clock++)y.step();
  need(y.d->rx_packets==0&&!(y.get(16)&4)&&y.get(72)==6&&y.d->last_metric==0,"clean-code bad FCS did not reject through actual CRC");
 }
 {Endpoint x,y;Link w;x.stage(data,93);y.arm(data.size(),92);x.submit();w.run(x,y,5000);need(y.d->rx_packets==0&&!(y.get(16)&4),"wrong scrambler metadata published data");}
 {Endpoint x;x.arm(1,1);for(unsigned j=0;j<8200;j++)x.step();need(!x.d->rx_active&&x.get(72)==4,"no-sample arm lacks bounded timeout");}
 {Endpoint x,y;Link w;x.stage(data,93);y.arm(data.size(),93);x.submit();w.run(x,y,5000);head(y,data);y.arm(reply.size(),127);x.stage(reply,127);x.submit();Link second;second.run(x,y,6000);need(y.d->rx_packets==1&&y.get(72)==8,"full one-slot head overflow");head(y,data);y.put(56,3);need(!(y.get(16)&4),"head ACK");}
 {Endpoint x;x.stage(data,93);x.submit();x.put(256,99);need(x.get(72)==2&&x.get(256)==data[0],"private TX capture/staging busy");x.d->coex_allow=0;x.step();need(!x.d->tx_active&&!x.d->tx_sample_valid&&x.get(72)==3,"coexistence cancel");x.d->enabled=0;x.step();x.d->valid=1;x.d->write=0;x.d->size=3;x.d->addr=16;x.d->eval();need(x.d->error&&x.d->rdata==0&&x.d->ticks==0&&x.d->tx_packets==0,"power disable clears state and rejects bus access");x.d->valid=0;}
 {Endpoint x;for(unsigned size:{0U,1U,2U}){x.d->valid=1;x.d->write=1;x.d->size=size;x.d->addr=24;x.d->wdata=16;x.d->eval();need(x.d->error,"bad width bus admitted");x.step();x.d->valid=0;}need(x.get(24)==1,"bad width changed configuration");for(unsigned value:{0U,17U,0xffffffffU}){x.d->valid=1;x.d->write=1;x.d->size=3;x.d->addr=24;x.d->wdata=value;x.d->eval();need(x.d->error,"bad payload bound admitted");x.step();x.d->valid=0;}}
 {Endpoint x,y;Link w;x.stage(data,93);y.arm(data.size(),93);x.submit();for(unsigned j=0;j<4800;j++){
   bool collision=y.d->observed_decode_phase==6;if(collision){y.d->valid=1;y.d->write=1;y.d->size=3;y.d->addr=64;y.d->wdata=7;}
   w.step(x,y);y.d->valid=0;if(collision){need(y.get(64)==2&&y.d->irq,"new RX publication event lost to coincident W1C");break;}
  }head(y,data);}
 {Endpoint x,y;Link w;x.stage(data,93);y.arm(data.size(),93);x.submit();w.run(x,y,5000);head(y,data);
  y.arm(16,127);x.stage(reply,127);x.submit();Link next;bool collided=false;
  for(unsigned j=0;j<6000;j++){bool publish=y.d->observed_decode_phase==6;
   if(publish){y.d->valid=1;y.d->write=1;y.d->size=3;y.d->addr=56;y.d->wdata=3;}
   next.step(x,y);y.d->valid=0;if(publish){collided=true;break;}
  }
  need(collided&&y.d->rx_packets==2,"RX ACK/publication collision did not replace head exactly once");head(y,reply);
 }
 {Endpoint x,y;Link w;x.stage(data,93);y.arm(data.size(),93);x.submit();
  do{w.step(x,y);}while(!w.a.valid&&x.clocks<100);need(w.a.valid,"early strobe fixture lacked actual transmitted sample");
  w.step(x,y);y.step({true,0,0});need(!y.d->rx_active&&y.d->rx_packets==0&&!(y.get(16)&4)&&y.get(72)==4,"extra early acquired sample did not abort");
 }
 {Endpoint x,y;Link w;x.stage(reply,127);y.arm(16,127);x.submit();w.run(x,y,751);need(x.d->tx_active&&y.d->rx_active,"reset fixture not in flight");x.d->reset=1;y.d->reset=1;w.step(x,y);x.d->reset=0;y.d->reset=0;need(x.d->tx_packets==0&&y.d->rx_packets==0&&!x.d->tx_active&&!y.d->rx_active&&y.get(64)==0,"reset retained coding/publication state");}
 std::cout<<"WIFI error-correction corruption loss bounds reset power coexistence IRQ/head PASS\n";
 for(unsigned selected:{19U,0U,421U,3251U,3390U,3600U}){
  Endpoint x,y;Link w;x.stage(reply,93);y.arm(16,93);x.submit();unsigned cut=selected;
  if(selected==0){cut=0;do{w.step(x,y);cut++;}while(!w.a.valid&&cut<64);need(w.a.valid,"bounded live pending I/Q wire boundary absent");}else w.run(x,y,cut);
  std::cout<<"WIFI checkpoint cut="<<cut<<" tx_active="<<unsigned(x.d->tx_active)<<" rx_active="<<unsigned(y.d->rx_active)<<" decode_phase="<<unsigned(y.d->observed_decode_phase)<<" pending_wire="<<w.a.valid<<"\n";
  std::string prefix=out+"/cut-"+std::to_string(cut);x.save(prefix+"-tx.state");y.save(prefix+"-rx.state");
  {std::ofstream f(prefix+"-wire.state",std::ios::binary);f.write(reinterpret_cast<const char*>(&w.a.valid),sizeof(bool));f.write(reinterpret_cast<const char*>(&w.a.i),2);f.write(reinterpret_cast<const char*>(&w.a.q),2);f.write(reinterpret_cast<const char*>(&w.b.valid),sizeof(bool));f.write(reinterpret_cast<const char*>(&w.b.i),2);f.write(reinterpret_cast<const char*>(&w.b.q),2);need(bool(f),"pending wire checkpoint");}
  Endpoint xx,yy;xx.load(prefix+"-tx.state");yy.load(prefix+"-rx.state");Link fork;
  {std::ifstream f(prefix+"-wire.state",std::ios::binary);f.read(reinterpret_cast<char*>(&fork.a.valid),sizeof(bool));f.read(reinterpret_cast<char*>(&fork.a.i),2);f.read(reinterpret_cast<char*>(&fork.a.q),2);f.read(reinterpret_cast<char*>(&fork.b.valid),sizeof(bool));f.read(reinterpret_cast<char*>(&fork.b.i),2);f.read(reinterpret_cast<char*>(&fork.b.q),2);need(bool(f),"pending wire restore");}
  for(unsigned j=0;j<6000;j++){w.step(x,y);fork.step(xx,yy);raw_equal(x,xx);raw_equal(y,yy);}
  head(y,reply);head(yy,reply);x.save(prefix+"-tx-final.state");xx.save(prefix+"-fork-tx-final.state");y.save(prefix+"-rx-final.state");yy.save(prefix+"-fork-rx-final.state");
  need(file_bytes(prefix+"-tx-final.state")==file_bytes(prefix+"-fork-tx-final.state")&&file_bytes(prefix+"-rx-final.state")==file_bytes(prefix+"-fork-rx-final.state"),"entire unmasked coding state final suffix differs");
 }
 std::cout<<"WIFI six live CRC/BCC/IFFT/DFT/Viterbi checkpoints full-state exact suffix PASS\n";
 if(argc==3){auto raw=file_bytes(argv[2]);need(raw.size()==32,"audited guest payload capacity");
  Bytes first(raw.begin(),raw.begin()+16),second(raw.begin()+16,raw.end());Endpoint x,y;Link w;
  x.stage(first,93);y.arm(16,93);x.submit();w.run(x,y,6000);head(y,first);waveform(w,first,93);
  x.arm(16,127);y.stage(second,127);y.submit();Link back;back.run(y,x,6000);head(x,second);waveform(back,second,127);
  need(x.d->tx_packets==1&&x.d->rx_packets==1&&y.d->tx_packets==1&&y.d->rx_packets==1,"guest-generated bytes did not traverse two actual sample endpoints");
  std::cout<<"WIFI actual RV64-produced payload bytes two-endpoint complex waveform PASS\n";
 }
 return 0;
 }catch(const std::exception&e){std::cerr<<"WIFI FAIL: "<<e.what()<<"\n";return 1;}}
