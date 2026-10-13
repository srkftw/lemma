// Host-only raw sampled wire and captured external framing. Link decisions stay
// in the genuine hosted Lean peer; both packet codecs execute in separate RTL.
static constexpr uint64_t BLE_LOG_MAX=64*1024*1024;
static void ble_word(std::ostream&f,uint64_t n){uint8_t b[8];for(int i=0;i<8;i++)b[i]=n>>(8*i);if(!f.write(reinterpret_cast<const char*>(b),8))throw std::runtime_error("BLE capture write failed");}
static std::vector<BleOutcome> ble_read_outcomes(const std::string&path){
 struct stat st{};if(stat(path.c_str(),&st)||!S_ISREG(st.st_mode)||st.st_size<72||uint64_t(st.st_size)>BLE_LOG_MAX)throw std::runtime_error("BLE outcomes require a bounded regular capture");
 auto wire=bytes(path);if(std::memcmp(wire.data(),"LMBLELG1",8)||std::memcmp(wire.data()+8,LEMMA_RUNTIME_IDENTITY,64))throw std::runtime_error("BLE outcome implementation identity differs");
 size_t at=72;auto word=[&](){if(wire.size()-at<8)throw std::runtime_error("truncated BLE outcome entry");uint64_t n=0;for(int k=0;k<8;k++)n|=uint64_t(wire[at++])<<(8*k);return n;};
 std::vector<BleOutcome> result;std::optional<BleOutcome>pending;uint64_t previous=0,accepted=0;
 while(at<wire.size()){
  auto tag=word();BleOutcome record;record.id=word();record.issued=word();record.header=word();auto n=word();if(tag>1||record.header>31||n>27||n>wire.size()-at)throw std::runtime_error("invalid BLE outcome fields");record.payload.assign(wire.begin()+at,wire.begin()+at+n);at+=n;
  record.accepted=word();auto count=word();if(count>256||count>wire.size()-at)throw std::runtime_error("invalid BLE outcome framing bound");record.frame.assign(reinterpret_cast<const char*>(wire.data()+at),count);at+=count;
  if(!tag){if(pending||count||record.accepted||(record.id&&record.payload.empty())||(!record.id&&(record.header||n||record.issued)))throw std::runtime_error("invalid BLE request capture");pending=record;}
  else{
   if(!pending||pending->id!=record.id||pending->issued!=record.issued||pending->header!=record.header||pending->payload!=record.payload||!count||record.accepted<record.issued||record.accepted<accepted||(!result.empty()&&record.id!=previous+1)||result.size()>=1000000)throw std::runtime_error("BLE outcome request, order or admission differs");
#ifndef __EMSCRIPTEN__
   BlePeerTransport::parse_recorded_reply(record.frame);
#else
   throw std::runtime_error("hosted BLE outcomes are not admitted by this portable adapter");
#endif
   previous=record.id;accepted=record.accepted;result.push_back(record);pending.reset();
  }
 }
 if(pending||result.empty())throw std::runtime_error("BLE outcomes have unresolved or empty work");return result;
}
void Machine::ble_record(uint64_t tag,const BleOutcome&r){
 if(!ble_capture.is_open())return;
 uint64_t length=7*8+r.payload.size()+r.frame.size();if(length>BLE_LOG_MAX-ble_capture_bytes)throw std::runtime_error("BLE outcome capture bound exhausted");
 ble_word(ble_capture,tag);ble_word(ble_capture,r.id);ble_word(ble_capture,r.issued);ble_word(ble_capture,r.header);ble_word(ble_capture,r.payload.size());ble_capture.write(reinterpret_cast<const char*>(r.payload.data()),r.payload.size());ble_word(ble_capture,r.accepted);ble_word(ble_capture,r.frame.size());ble_capture.write(r.frame.data(),r.frame.size());ble_capture.flush();if(!ble_capture)throw std::runtime_error("BLE outcome capture failed before admission");ble_capture_bytes+=length;
}
uint64_t Machine::ble_read(uint64_t offset){auto&soc=*model;soc.ble_peer_valid=0;soc.ble_peer_write=0;soc.ble_peer_addr=offset;soc.ble_peer_size=3;soc.eval();if(soc.ble_peer_error||!soc.ble_peer_ready)throw std::runtime_error("BLE peer observational PIO read failed");return soc.ble_peer_rdata;}
void Machine::ble_queue(uint64_t offset,uint64_t value){if(s.ble_pio.size()>=32)throw std::runtime_error("BLE peer PIO queue exhausted");s.ble_pio.push_back({offset,value});}
void Machine::ble_reply_action(const std::string&frame){
#ifndef __EMSCRIPTEN__
 auto reply=BlePeerTransport::parse_recorded_reply(frame);s.ble_accepted_state=reply.logical_state;
 if(!s.ble_ready){if(reply.action!="BLEPEER/2 OPEN_MANUAL_UNAUTHENTICATED_CONTEXT")throw std::runtime_error("BLE startup did not reach declared manual context");s.ble_ready=1;s.ble_peer_reset_until=s.cycle+8;return;}
 std::istringstream input(reply.action);std::string action;input>>action;
 if(action=="TX"){
  std::string header,length,hex,extra;if(!(input>>header>>length>>hex)||(input>>extra)||number(header)>31||number(length)!=0||hex!="-"||(number(header)&3)!=1)throw std::runtime_error("BLE peer action exceeds copied empty-ACK transport");
  s.ble_ack_pending=1;s.ble_ack_header=number(header);
 }else if(action!="EMPTY_RX"&&action!="ERROR")throw std::runtime_error("unexpected BLE peer response action");
 // Pop/W1C are consequences of an accepted external response, never a host
 // guess that a packet was acknowledged. The immutable head remained held.
 ble_queue(64,2);ble_queue(72,ble_read(72));
#else
 throw std::runtime_error("hosted BLE response adapter unavailable in portable worker");
#endif
}
void Machine::ble_accept(const BleOutcome&r){
 if(!s.ble_pending||r.id!=(s.ble_ready?s.ble_next_id-1:0)||r.issued!=s.ble_request_cycle||r.header!=s.ble_request_header||r.payload!=s.ble_request_payload||r.accepted!=s.cycle)throw std::runtime_error("BLE completion identity or boundary differs");
 ble_record(1,r); // Actual complete response is captured before any PIO effect.
 ble_reply_action(r.frame);s.ble_last=r;s.ble_pending=0;s.ble_poll_cycle=0;s.ble_request_cycle=0;s.ble_request_header=0;s.ble_request_payload.clear();s.ble_accepted_replies++;
}
void Machine::ble_before_edge(){
 auto&soc=*model;soc.ble_peer_valid=0;soc.ble_peer_write=0;
 if(!BINDING_BLE_ENABLED)return;
 soc.ble_coex_allow=s.ble_coex;soc.ble_peer_coex_allow=1;soc.ble_peer_enabled=s.ble_attached&&s.ble_ready;soc.ble_peer_reset=s.cycle<s.ble_peer_reset_until;
 if(s.ble_raw_valid&&s.ble_to_chip_valid)throw std::runtime_error("raw BLE sample collides with peer wire at one boundary");
 soc.ble_rx_sample_valid=s.ble_raw_valid||s.ble_to_chip_valid;soc.ble_rx_sample_bit=s.ble_raw_valid?s.ble_raw_bit:s.ble_to_chip_bit;s.ble_raw_valid=0;
 soc.ble_peer_rx_sample_valid=s.ble_to_peer_valid;soc.ble_peer_rx_sample_bit=s.ble_to_peer_bit;
 if(soc.ble_peer_tx_active&&!s.ble_peer_sending){s.ble_peer_sending=1;s.ble_peer_dropping=s.ble_drop_remaining!=0;if(s.ble_peer_dropping){s.ble_drop_remaining--;s.ble_dropped_packets++;}}
 else if(!soc.ble_peer_tx_active&&!soc.ble_peer_tx_sample_valid){s.ble_peer_sending=0;s.ble_peer_dropping=0;}
 if(s.ble_pending&&s.cycle>=s.ble_poll_cycle){
  if(!ble_replay.empty()){
   if(ble_replay_cursor>=ble_replay.size())throw std::runtime_error("BLE outcome tape exhausted while pending");const auto&r=ble_replay[ble_replay_cursor];
   if(r.accepted<s.cycle)throw std::runtime_error("BLE accepted outcome boundary passed");if(r.accepted==s.cycle){ble_accept(r);ble_replay_cursor++;}else s.ble_poll_cycle=s.cycle+1000;
  }else{
#ifndef __EMSCRIPTEN__
   if(!ble_peer)throw std::runtime_error("BLE pending operation has no external binding");
   if(auto reply=ble_peer->poll()){BleOutcome r;r.id=reply->request_id;r.issued=s.ble_request_cycle;r.header=s.ble_request_header;r.payload=s.ble_request_payload;r.accepted=s.cycle;r.frame=reply->frame;ble_accept(r);}else s.ble_poll_cycle=s.cycle+1000;
#else
   throw std::runtime_error("hosted BLE request unavailable in portable worker");
#endif
  }
 }
 if(s.ble_ready&&s.ble_attached&&s.cycle>=s.ble_peer_reset_until&&s.ble_pio.empty()&&!s.ble_pending){
  auto status=ble_read(16);
  if((status&4)&&!s.ble_ack_pending){
   auto head=ble_read(88);auto count=(head>>8)&255;if(!count||count>27||(head&255)>31||s.ble_next_id==UINT64_MAX)throw std::runtime_error("BLE peer immutable head exceeds admitted RX scope");
   BleOutcome request;request.id=s.ble_next_id;request.issued=s.cycle;request.header=head&255;for(uint64_t i=0;i<count;i++)request.payload.push_back(ble_read(512+8*i));
   if(!ble_replay.empty()){
    if(ble_replay_cursor>=ble_replay.size())throw std::runtime_error("BLE outcome tape lacks external request");const auto&r=ble_replay[ble_replay_cursor];if(r.id!=request.id||r.issued!=request.issued||r.header!=request.header||r.payload!=request.payload||r.accepted<s.cycle+1000||(r.accepted-(s.cycle+1000))%1000)throw std::runtime_error("BLE replay request differs from actual CRC-valid head");
   }
   ble_record(0,request);
#ifndef __EMSCRIPTEN__
   if(ble_replay.empty()&&(!ble_peer||!ble_peer->submit_rx(request.id,request.header,request.payload)))throw std::runtime_error("BLE external RX request not accepted");
#endif
   s.ble_next_id++;s.ble_pending=1;s.ble_request_cycle=request.issued;s.ble_request_header=request.header;s.ble_request_payload=request.payload;s.ble_poll_cycle=s.cycle+1000;s.ble_rx_heads++;
  }else if(s.ble_ack_pending&&!(status&3)&&ble_read(104)==0){ble_queue(48,s.ble_ack_header);ble_queue(56,0);ble_queue(64,1);s.ble_ack_pending=0;}
 }
 if(!s.ble_pio.empty()&&s.cycle>=s.ble_peer_reset_until){soc.ble_peer_valid=1;soc.ble_peer_write=1;soc.ble_peer_addr=s.ble_pio.front()[0];soc.ble_peer_size=3;soc.ble_peer_wdata=s.ble_pio.front()[1];}
}
void Machine::ble_after_edge(){
 if(!BINDING_BLE_ENABLED)return;auto&soc=*model;
 if(soc.ble_peer_valid){if(!soc.ble_peer_ready||soc.ble_peer_error)throw std::runtime_error("BLE peer queued PIO transaction failed");if(s.ble_pio.empty())throw std::runtime_error("BLE peer PIO owner missing");s.ble_pio.pop_front();}
 // Sampled decisions cross this declared wire on the next machine clock,
 // including the final packet bit. No decoder/CRC/whitener exists in host code.
 if(ble_wire.is_open()){
  if(s.ble_chip_samples+s.ble_peer_samples>=1000000)throw std::runtime_error("BLE sampled trace resource bound exceeded");
  if(soc.ble_tx_sample_valid)ble_wire<<s.cycle<<",chip,"<<unsigned(soc.ble_tx_sample_bit)<<",1\n";
  if(soc.ble_peer_tx_sample_valid)ble_wire<<s.cycle<<",peer,"<<unsigned(soc.ble_peer_tx_sample_bit)<<','<<unsigned(!s.ble_peer_dropping)<<'\n';
  if(!ble_wire)throw std::runtime_error("BLE sampled trace failed");
 }
 s.ble_to_peer_valid=soc.ble_tx_sample_valid;s.ble_to_peer_bit=soc.ble_tx_sample_bit;
 s.ble_to_chip_valid=soc.ble_peer_tx_sample_valid&&!s.ble_peer_dropping;s.ble_to_chip_bit=soc.ble_peer_tx_sample_bit;
 s.ble_chip_samples+=soc.ble_tx_sample_valid;s.ble_peer_samples+=soc.ble_peer_tx_sample_valid;
}
static uint64_t ble_tape_cursor(const State&s,const std::vector<BleOutcome>&tape){
 uint64_t id=s.ble_pending?(s.ble_ready?s.ble_next_id-1:0):s.ble_next_id;
 auto next=std::lower_bound(tape.begin(),tape.end(),id,[](const BleOutcome&r,uint64_t request){return r.id<request;});
 if(s.ble_ready){
  if(next==tape.begin()||(next-1)->id!=s.ble_last.id||(next-1)->issued!=s.ble_last.issued||(next-1)->accepted!=s.ble_last.accepted||(next-1)->header!=s.ble_last.header||(next-1)->payload!=s.ble_last.payload||(next-1)->frame!=s.ble_last.frame)throw std::runtime_error("BLE tape lacks exact accepted checkpoint outcome");
#ifndef __EMSCRIPTEN__
  if(BlePeerTransport::parse_recorded_reply((next-1)->frame).logical_state!=s.ble_accepted_state)throw std::runtime_error("BLE tape cached peer context differs");
#endif
 }
 if(s.ble_pending){
  if(next==tape.end()||next->id!=id||next->issued!=s.ble_request_cycle||next->header!=s.ble_request_header||next->payload!=s.ble_request_payload||next->accepted<s.ble_poll_cycle||(next->accepted-s.ble_poll_cycle)%1000)throw std::runtime_error("BLE tape does not cover inherited request and poll boundary");
 }else if(next!=tape.end()&&(next->id!=s.ble_next_id||next->issued<s.cycle))throw std::runtime_error("BLE tape next request predates checkpoint");
 return next-tape.begin();
}
void Machine::bind_ble_replay(const std::string&path){
 if(!BINDING_BLE_ENABLED||!s.isolated||!s.ble_attached||!ble_fork_suspended)throw std::runtime_error("BLE outcomes require a suspended isolated peer fork");
 auto tape=ble_read_outcomes(path);auto cursor=ble_tape_cursor(s,tape);
 ble_replay=std::move(tape);ble_replay_cursor=cursor;options.ble_replay_path=path;ble_fork_suspended=false;
}
