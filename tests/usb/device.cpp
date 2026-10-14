#include "Vlemma_usb_device.h"
#include "verilated.h"
#include "verilated_save.h"
#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
using Bytes=std::vector<uint8_t>;
static Bytes file(const std::filesystem::path& p){std::ifstream in(p,std::ios::binary);return Bytes(std::istreambuf_iterator<char>(in),{});}
static void need(bool b,const std::string& message){if(!b)throw std::runtime_error(message);}
// Independent MSB-first polynomial register, reflected at the boundary. RTL
// uses an LSB-first register; these checks also require standard USB residues.
static unsigned reversed(unsigned v,unsigned n){unsigned x=0;for(unsigned i=0;i<n;i++)x=(x<<1)|((v>>i)&1);return x;}
static unsigned crc(const Bytes& bytes,unsigned width,unsigned polynomial){
 unsigned c=(1u<<width)-1,mask=c;
 for(auto v:bytes)for(unsigned i=0;i<8;i++){unsigned b=(c>>(width-1))^((v>>i)&1);c=(c<<1)&mask;if(b&1)c^=polynomial;}
 return reversed(c,width);
}
static Bytes data(bool one,const Bytes& payload){Bytes out{uint8_t(one?0x4b:0xc3)};out.insert(out.end(),payload.begin(),payload.end());unsigned c=crc(payload,16,0x8005)^0xffff;out.push_back(c&255);out.push_back(c>>8);return out;}
static Bytes token(uint8_t pid,unsigned address,unsigned ep){
 unsigned v=address|(ep<<7),c=31;
 for(unsigned i=0;i<11;i++){unsigned b=(c>>4)^((v>>i)&1);c=(c<<1)&31;if(b&1)c^=5;}
 unsigned check=reversed(c,5)^31;
 return {pid,uint8_t(v),uint8_t((v>>8)|(check<<3))};
}
struct Device {
 struct Context:VerilatedContext{Context(){threads(1);}} context;
 Vlemma_usb_device top{&context};uint64_t cycles=0;
 Device(){top.rx_abort=0;top.enabled=1;top.connected=1;top.tx_ready=1;top.size=3;top.reset=1;step();top.reset=0;}
 void step(){top.clk=0;top.eval();top.clk=1;top.eval();cycles++;}
 uint64_t read(unsigned addr){top.addr=addr;top.valid=1;top.write=0;top.eval();need(!top.error,"MMIO read");auto v=top.rdata;step();top.valid=0;return v;}
 bool write(unsigned addr,uint64_t value){top.addr=addr;top.wdata=value;top.valid=1;top.write=1;top.eval();bool ok=!top.error;step();top.valid=0;top.write=0;return ok;}
 void packet(const Bytes& bytes){need(!bytes.empty(),"packet empty");for(size_t i=0;i<bytes.size();i++){top.eval();need(top.rx_ready,"RX backpressure");top.rx_valid=1;top.rx_byte=bytes[i];top.rx_last=i+1==bytes.size();step();}top.rx_valid=0;top.rx_last=0;}
 Bytes output(){Bytes bytes;top.eval();for(unsigned n=0;top.tx_valid&&n<100;n++){bytes.push_back(top.tx_byte);bool last=top.tx_last;step();if(last)break;}need(!top.tx_valid,"unbounded TX");return bytes;}
 void setup(const Bytes& request){packet(token(0x2d,top.device_address,0));packet(data(false,request));need(output()==Bytes{0xd2},"SETUP ACK");need(write(168,read(160)),"bind exact SETUP generation");}
 void arm(unsigned ep,const Bytes& bytes){need(bytes.size()<=64,"arm bound");for(unsigned i=0;i<8;i++){uint64_t word=0;for(unsigned j=0;j<8;j++)if(i*8+j<bytes.size())word|=uint64_t(bytes[i*8+j])<<(j*8);need(write(256+ep*64+i*8,word),"TX byte bank");}need(write(64+ep*8,bytes.size()),"TX len");need(write(56,1+(ep<<8)),"arm");}
 void ack(){packet({0xd2});}
 void save(const std::filesystem::path& path){VerilatedSave out;out.open(path.string().c_str());out<<cycles<<top;out.close();}
 void restore(const std::filesystem::path& path){VerilatedRestore in;in.open(path.string().c_str());in>>cycles>>top;in.close();top.eval();}
};
static Bytes control(Device& d,const Bytes& setup,const Bytes& reply,bool ack=true){d.setup(setup);d.arm(0,reply);need(d.write(56,2),"release setup");d.packet(token(0x69,d.top.device_address,0));auto out=d.output();need(out==data(true,reply),"EP0 DATA1 and CRC");if(ack)d.ack();return out;}
int main(int argc,char** argv){try{
 need(argc==2,"device WORKDIR");std::filesystem::path dir=argv[1];std::filesystem::create_directories(dir);
 need((crc(Bytes{'1','2','3','4','5','6','7','8','9'},16,0x8005)^0xffff)==0xb4c8,"CRC16 USB independent known answer");
 auto t=token(0xe1,0,0);need(t==Bytes({0xe1,0,0x10}),"CRC5 default OUT literal");
 // New Clocked2 facts cannot leak into this default historical controller.
 Device identity;
 for(unsigned offset=176;offset<=216;offset+=8){
  identity.top.addr=offset;identity.top.valid=1;identity.top.write=0;identity.top.eval();
  need(identity.top.error&&identity.top.rdata==0,"historical controller acquired Clocked2 identity");
  identity.top.valid=0;need(!identity.write(offset,0),"historical unknown identity accepted write");
 }
 // Staging, token cursor and partial DATA are saved without completing RX.
 Device prefix;prefix.packet(token(0x2d,0,0));auto pending=data(false,Bytes{0,5,7,0,0,0,0,0});
 for(unsigned i=0;i<4;i++){prefix.top.rx_valid=1;prefix.top.rx_byte=pending[i];prefix.top.rx_last=0;prefix.step();}
 prefix.save(dir/"partial.state");Device partial;partial.restore(dir/"partial.state");
 for(unsigned i=4;i<pending.size();i++)for(Device* x:{&prefix,&partial}){x->top.rx_valid=1;x->top.rx_byte=pending[i];x->top.rx_last=i+1==pending.size();x->step();}
 for(Device* x:{&prefix,&partial}){x->top.rx_valid=0;x->top.rx_last=0;need(x->output()==Bytes{0xd2},"partial checkpoint actual ACK");}
 prefix.save(dir/"partial-live.state");partial.save(dir/"partial-fork.state");need(file(dir/"partial-live.state")==file(dir/"partial-fork.state"),"partial RX exact suffix");
 Device d;d.top.bus_reset=1;for(unsigned i=0;i<999999;i++)d.step();need(d.read(40)==0,"reset premature");d.step();need(d.read(40)&1,"reset 10ms qualified");d.top.bus_reset=0;d.step();d.write(40,63);
 need(!d.write(96,128),"invalid address bus fault");d.write(40,63);
 d.write(96,7);need(d.top.device_address==0&&d.read(48)==2,"no synthetic address without SETUP");d.write(40,63);
 const Bytes descriptor{18,1,0,2,0,0,0,64,0,0,0,0,0,1,0,0,0,1};
 control(d,{0x80,6,0,1,0,0,18,0},descriptor);
 d.setup({0,5,7,0,0,0,0,0});d.write(96,7);d.arm(0,{});d.write(56,2);
 d.packet(token(0x69,0,0));need(d.output()==data(true,{}),"address status DATA1");need(d.top.device_address==0,"address delayed before ACK");
 d.save(dir/"status.state");Device fork;fork.restore(dir/"status.state");
 d.ack();fork.ack();need(d.top.device_address==7&&fork.top.device_address==7,"address status ACK commit");d.save(dir/"live.state");fork.save(dir/"fork.state");
 need(file(dir/"live.state")==file(dir/"fork.state"),"exact pending status ACK suffix state");
 d.setup({0,9,1,0,0,0,0,0});d.write(104,1);d.arm(0,{});d.write(56,2);d.packet(token(0x69,7,0));d.output();need(!d.top.configured,"config delayed");d.ack();need(d.top.configured,"configured after guest-approved actual status ACK");
 // Bulk OUT: first accepted, duplicate ACK even while head is retained, next
 // expected PID NAK under backpressure; immutable original bytes survive.
 Bytes opaque{0x4c,0x4d,0x43,0x4d,0x50,0x30,0x30,0x31,1,0,2,0};
 d.packet(token(0xe1,7,2));d.packet(data(false,opaque));need(d.output()==Bytes{0xd2},"bulk OUT ACK");auto head=d.read(576);
 d.packet(token(0xe1,7,2));d.packet(data(false,opaque));need(d.output()==Bytes{0xd2}&&d.read(576)==head,"duplicate retained OUT");
 d.packet(token(0xe1,7,2));d.packet(data(true,Bytes{9}));need(d.output()==Bytes{0x5a}&&d.read(576)==head,"full OUT NAK");d.write(56,2+(2<<8));
 auto bad=data(true,opaque);bad.back()^=1;d.packet(token(0xe1,7,2));d.packet(bad);need(d.output().empty()&&!(d.read(16)&32),"CRC failure no publish/ACK");
 d.write(56,3+(2<<8));d.packet(token(0xe1,7,2));d.packet(data(true,opaque));need(d.output()==Bytes{0x1e},"OUT halt STALL");d.write(56,4+(2<<8));
 d.packet(token(0xe1,7,2));d.packet(data(false,opaque));need(d.output()==Bytes{0xd2},"clear halt DATA0 restart");d.write(56,2+(2<<8));
 // Bulk IN: commit locks the staging bank; lost ACK returns identical packet
 // and only a real ACK advances DATA toggle/releases the owned slot.
 d.arm(1,opaque);d.write(320,0);need(d.read(48)==3,"queued IN staging immutable");d.packet(token(0x69,7,1));auto first=d.output();need(first==data(false,opaque),"bulk IN DATA0");
 d.packet(token(0x69,7,1));need(d.output()==first,"lost ACK retry exact bytes");d.ack();d.packet(token(0x69,7,1));need(d.output()==Bytes{0x5a},"empty IN NAK after real ACK");
 d.arm(1,Bytes{8});d.packet(token(0x69,7,1));need(d.output()==data(true,Bytes{8}),"IN toggle DATA1");
 d.write(56,5+(1<<8));d.packet(token(0x69,7,1));need(d.output()==Bytes{0x5a},"cancel releases slot");
 // A generation captured before a newer SETUP cannot queue old responses or
 // consume the new head, including after bus reset.
 auto stale=d.read(160);d.setup({0x80,6,0,1,0,0,18,0});d.write(168,stale);d.write(48,0);d.write(56,2);need((d.read(16)&16)!=0&&d.read(48)==2,"stale control generation cannot consume newer SETUP");d.write(168,d.read(160));
 // New valid SETUP aborts a not-yet-ACKed configuration change.
 d.setup({0,9,0,0,0,0,0,0});d.write(104,0);d.setup({0x80,6,0,1,0,0,18,0});d.arm(0,{});d.write(56,2);d.packet(token(0x69,7,0));d.output();d.ack();need(d.top.configured,"new SETUP cancels stale config");
 d.top.connected=0;d.step();need(d.top.device_address==0&&!d.top.configured&&(d.read(40)&16),"disconnect resets address/config/transactions");
 std::cout<<"USB_DEVICE_LITERAL_PASS cycles="<<d.cycles<<" rx="<<d.top.rx_packets<<" tx="<<d.top.tx_packets<<" errors="<<d.top.packet_errors<<"\n";return 0;
 }catch(const std::exception& e){std::cerr<<"USB_DEVICE_LITERAL_FAIL "<<e.what()<<"\n";return 1;}}
