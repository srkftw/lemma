// Host-only raw controller bus/sample adapter. Link policy runs in Lean.
#include "Vlemma_ble_packet.h"
#include "verilated.h"
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
struct Endpoint {
 std::unique_ptr<VerilatedContext> context=std::make_unique<VerilatedContext>();
 std::unique_ptr<Vlemma_ble_packet> circuit=std::make_unique<Vlemma_ble_packet>(context.get());
 uint64_t clocks=0;
 Endpoint(){circuit->reset=1;circuit->enabled=1;circuit->coex_allow=1;circuit->valid=0;step(false,0);circuit->reset=0;}
 void step(bool valid,unsigned bit){circuit->rx_sample_valid=valid;circuit->rx_sample_bit=bit;
  circuit->clk=0;circuit->eval();context->timeInc(1);circuit->clk=1;circuit->eval();context->timeInc(1);++clocks;}
 void write(unsigned address,uint64_t value){circuit->valid=1;circuit->write=1;circuit->size=3;
  circuit->addr=address;circuit->wdata=value;circuit->eval();require(!circuit->error,"controller rejected bus write");
  step(false,0);circuit->valid=0;circuit->eval();}
 uint64_t read(unsigned address){circuit->valid=1;circuit->write=0;circuit->size=3;circuit->addr=address;
  circuit->eval();require(!circuit->error,"controller rejected bus read");uint64_t value=circuit->rdata;
  circuit->valid=0;circuit->eval();return value;}
};
static unsigned nibble(char c){if(c>='0'&&c<='9')return unsigned(c-'0');if(c>='a'&&c<='f')return unsigned(c-'a'+10);throw std::runtime_error("invalid lower-case hex");}
static std::vector<unsigned> bytes(const std::string& text){if(text=="-")return {};
 require(text.size()<=54&&text.size()%2==0,"payload outside27bytes");std::vector<unsigned> result;
 for(size_t i=0;i<text.size();i+=2)result.push_back((nibble(text[i])<<4)|nibble(text[i+1]));return result;}
static std::string hex(const std::vector<unsigned>& data){if(data.empty())return "-";std::ostringstream text;
 for(unsigned byte:data)text<<std::hex<<std::setfill('0')<<std::setw(2)<<byte;return text.str();}
static bool line(std::string& text){text.clear();char byte;
 for(unsigned i=0;i<=256;++i){if(!std::cin.get(byte)){require(text.empty(),"incomplete raw command");return false;}
  if(byte=='\n')return true;require(i<256,"command exceeds256bytes");text.push_back(byte);}
 throw std::runtime_error("unreachable raw frame limit");}
int main(){try {
 Endpoint a,b;bool pendingA=false,pendingB=false;unsigned bitA=0,bitB=0;
 std::cout<<"BLEWIRE/1 RAW_CONTROLLER_SAMPLES\n"<<std::flush;
 std::string raw;
 while(line(raw)){
  std::istringstream input(raw);std::string operation,name;
  input>>operation;
  if(operation=="QUIT")return 0;
  if(operation=="CLOCK"){
   unsigned count,dropA,dropB,corruptA;input>>count>>dropA>>dropB>>corruptA;
   require(bool(input)&&count<=1000000&&dropA<=1&&dropB<=1,"invalid bounded sample advance");
   std::string bitsA,bitsB;unsigned index=0;
   for(unsigned i=0;i<count;++i){
    a.step(pendingB&&!dropB,bitB);b.step(pendingA&&!dropA,bitA);
    pendingA=a.circuit->tx_sample_valid;pendingB=b.circuit->tx_sample_valid;
    bitA=a.circuit->tx_sample_bit;bitB=b.circuit->tx_sample_bit;
    if(pendingA){bitsA.push_back(char('0'+bitA));if(index++==corruptA)bitA^=1;}
    if(pendingB)bitsB.push_back(char('0'+bitB));
   }
   std::cout<<"CLOCK "<<a.clocks<<" A "<<(bitsA.empty()?"-":bitsA)<<" B "<<(bitsB.empty()?"-":bitsB)<<"\n";
  }else{
   input>>name;require(name=="A"||name=="B","unknown endpoint");Endpoint& endpoint=name=="A"?a:b;
   if(operation=="TX"){
    unsigned header;std::string data;input>>header>>data;require(bool(input)&&header<=255,"invalid TX command");
    auto payload=bytes(data);endpoint.write(48,header);endpoint.write(56,payload.size());
    for(unsigned i=0;i<payload.size();++i)endpoint.write(256+8*i,payload[i]);endpoint.write(64,1);
    require(endpoint.circuit->tx_active,"controller did not admit TX");std::cout<<"TX "<<name<<" STARTED\n";
   }else if(operation=="RX"){
    if(!(endpoint.read(16)&4))std::cout<<"HEAD "<<name<<" NONE\n";
    else{uint64_t metadata=endpoint.read(88);unsigned length=unsigned(metadata>>8);require(length<=27,"invalid controller head");
     std::vector<unsigned> payload;for(unsigned i=0;i<length;++i)payload.push_back(unsigned(endpoint.read(512+8*i)));
     std::cout<<"RX "<<name<<" "<<(metadata&255)<<" "<<length<<" "<<hex(payload)<<"\n";}
   }else if(operation=="POP"){
    endpoint.write(64,2);endpoint.write(72,15);std::cout<<"POP "<<name<<" DONE\n";
   }else if(operation=="STATUS"){
    std::cout<<"STATUS "<<name<<" "<<endpoint.read(16)<<" "<<endpoint.read(72)<<" "<<endpoint.read(80)
     <<" "<<endpoint.circuit->tx_packets<<" "<<endpoint.circuit->rx_packets<<" "<<endpoint.circuit->crc_errors<<" "<<endpoint.circuit->rx_errors<<"\n";
   }else if(operation=="RESET"){
    endpoint.circuit->reset=1;endpoint.step(false,0);endpoint.circuit->reset=0;
    if(name=="A")pendingA=false;else pendingB=false;std::cout<<"RESET "<<name<<" DONE\n";
   }else throw std::runtime_error("unknown raw command");
  }
  std::string extra;require(!(input>>extra),"extra raw command fields");std::cout<<std::flush;
 }
 return 0;
}catch(const std::exception& error){std::cerr<<"BLEWIRE FAIL: "<<error.what()<<"\n";return 1;}}
