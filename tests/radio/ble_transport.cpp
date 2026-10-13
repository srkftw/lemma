// Independent host adapter observers. Policy is executed by the hosted Lean peer.
#include "../../sim/radio/ble_peer_transport.h"
#include <array>
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <thread>
using namespace lemma::radio;
static void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
static BLEPeerReply response(BLEPeerTransport& peer){
 const auto end=std::chrono::steady_clock::now()+std::chrono::seconds(30);
 while(std::chrono::steady_clock::now()<end){auto reply=peer.poll();if(reply)return *reply;std::this_thread::sleep_for(std::chrono::milliseconds(1));}
 throw std::runtime_error("bounded adapter observation expired");
}
static void ready(BLEPeerTransport& peer){require(peer.is_pending(),"startup is not pending");
 while(!peer.is_ready())require(response(peer).request_id==0,"startup generated a request ACK");}
int main(int argc,char** argv){try{
 require(argc>=2,"actual hosted peer executable and args required");std::vector<std::string> args;
 for(int i=2;i<argc;++i)args.emplace_back(argv[i]);
 BLEPeerTransport original(argv[1],args);ready(original);
 const std::vector<uint8_t> payload{0x4c,0x4d,0x43,0x4d,0x50,0x30,0x30,0x31,1,0,2,0};
 require(original.submit_rx(17,2,payload),"actual RX not submitted");
 require(original.is_pending()&&!original.submit_rx(18,2,payload),"overlapping external request was admitted");
 require(original.accepted_state()=="STATE 0 ACCEPTED 0 DUPLICATES 0 PENDING 0 -","pending request guessed future state");
 auto first=response(original);require(first.request_id==17&&first.action=="TX 5 0 -"&&
  first.logical_state=="STATE 262 ACCEPTED 1 DUPLICATES 0 PENDING 12 4c4d434d5030303101000200","actual Lean acceptance differs");
 const auto recorded=BLEPeerTransport::parse_recorded_reply(first.frame);
 require(recorded.request_id==0&&recorded.action==first.action&&recorded.frame==first.frame&&
  recorded.logical_state==first.logical_state&&recorded.state==first.state,
  "pure recorded response differs from accepted complete frame");
 const std::array<std::string,4> invalid_frames{first.frame+'\n',first.frame+" | STATE 0 ACCEPTED 0 DUPLICATES 0 PENDING 0 -",
  "TX 5 0 - | STATE 262 ACCEPTED 1 DUPLICATES 0 PENDING 12 -",std::string(257,'x')};
 for(const auto& invalid:invalid_frames){
  bool bad=false;try{BLEPeerTransport::parse_recorded_reply(invalid);}catch(const std::exception&){bad=true;}
  require(bad,"invalid recorded response was admitted");
 }
 const auto cached=original.accepted_state(); // no STATUS request, flush or drain
 BLEPeerTransport fork(argv[1],args,cached);ready(fork);require(fork.accepted_state()==cached,"privately rebound complete state differs");
 require(original.submit_rx(18,2,payload)&&fork.submit_rx(18,2,payload),"lost-ACK retry did not submit");
 auto a=response(original),b=response(fork);require(a.action=="TX 5 0 -"&&a.frame==b.frame&&a.request_id==b.request_id,
  "original/private peer suffix diverged");
 require(a.logical_state=="STATE 518 ACCEPTED 1 DUPLICATES 1 PENDING 12 4c4d434d5030303101000200","retry duplicated effect");
 require(original.submit_cancel(19)&&fork.submit_cancel(19),"cancel not submitted");
 a=response(original);b=response(fork);require(a.frame==b.frame&&a.action=="ERROR 200 FROZEN","private cancellation suffix differs");
 require(a.logical_state=="STATE 10 ACCEPTED 1 DUPLICATES 1 PENDING 12 4c4d434d5030303101000200","uncertain context not frozen");
 original.shutdown();fork.shutdown();require(!original.is_pending()&&!original.is_ready(),"shutdown retained live external request");
 bool rejected=false;try{BLEPeerTransport invalid(argv[1],args,std::string("STATE 12 ACCEPTED 0 DUPLICATES 0 PENDING 0 -"));}catch(const std::exception&){rejected=true;}
 require(rejected,"invalid private record spawned an ordinary peer");
 {BLEPeerTransport missing("/no/such/lemma-radio-peer",{},std::nullopt,1000);rejected=false;
  try{response(missing);}catch(const std::exception&){rejected=true;}require(rejected,"actual exec/EOF failure fabricated readiness");}
 std::cout<<"BLE_PEER_TRANSPORT realLean nonblocking IDs/overlap/pending/private exact suffix/cancel/EOF/reap PASS\n";
 return 0;
}catch(const std::exception& error){std::cerr<<"BLE_PEER_TRANSPORT FAIL: "<<error.what()<<"\n";return 1;}}
