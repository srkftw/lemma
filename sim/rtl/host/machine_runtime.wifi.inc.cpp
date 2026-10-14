// Host-only raw PIO/sample transport. Both coding endpoints execute in RTL;
// no packet encoder, decoder, semantic ACK, guest buffer or verdict is here.
static bool wifi_pio_valid(uint64_t offset,uint64_t value){
 if(offset&7)return false;
 return ((offset==24||offset==40)&&value>=1&&value<=16)||
  ((offset==32||offset==48)&&value>=1&&value<=127)||
  (offset==56&&value>=1&&value<=4)||(offset==64&&value<=7)||
  (offset>=256&&offset<=376&&value<=255);
}
void Machine::wifi_before_edge(){
 auto&d=*model;d.wifi_peer_valid=0;d.wifi_peer_write=0;d.wifi_peer_addr=0;d.wifi_peer_size=3;d.wifi_peer_wdata=0;
 d.wifi_coex_allow=s.wifi_coex;d.wifi_peer_coex_allow=1;d.wifi_peer_enabled=BINDING_WIFI_ENABLED;
 d.wifi_peer_reset=s.cycle-s.boot_cycle<8;
 if(!BINDING_WIFI_ENABLED){d.wifi_rx_sample_valid=0;d.wifi_peer_rx_sample_valid=0;return;}
 if(s.wifi_raw_valid&&s.wifi_to_chip_valid)throw std::runtime_error("raw CommonOFDM sample collides with pending peer wire");
 d.wifi_rx_sample_valid=s.wifi_raw_valid||s.wifi_to_chip_valid;
 d.wifi_rx_i=s.wifi_raw_valid?s.wifi_raw_i:s.wifi_to_chip_i;
 d.wifi_rx_q=s.wifi_raw_valid?s.wifi_raw_q:s.wifi_to_chip_q;s.wifi_raw_valid=0;
 d.wifi_peer_rx_sample_valid=s.wifi_to_peer_valid;d.wifi_peer_rx_i=s.wifi_to_peer_i;d.wifi_peer_rx_q=s.wifi_to_peer_q;
 if(!s.wifi_pio.empty()){
  auto beat=s.wifi_pio.front();d.wifi_peer_valid=1;d.wifi_peer_write=1;d.wifi_peer_addr=beat[0];d.wifi_peer_wdata=beat[1];
  d.eval();if(d.wifi_peer_error||!d.wifi_peer_ready||d.wifi_peer_reset)throw std::runtime_error("raw CommonOFDM peer PIO cannot cross this boundary");
  s.wifi_pio.pop_front();s.wifi_peer_beats++;
 }
}
void Machine::wifi_after_edge(){
 if(!BINDING_WIFI_ENABLED)return;
 auto&d=*model;s.wifi_to_chip_valid=d.wifi_peer_tx_sample_valid;s.wifi_to_chip_i=uint16_t(d.wifi_peer_tx_i);s.wifi_to_chip_q=uint16_t(d.wifi_peer_tx_q);
 s.wifi_to_peer_valid=d.wifi_tx_sample_valid;s.wifi_to_peer_i=uint16_t(d.wifi_tx_i);s.wifi_to_peer_q=uint16_t(d.wifi_tx_q);
 s.wifi_chip_samples+=s.wifi_to_peer_valid;s.wifi_peer_samples+=s.wifi_to_chip_valid;
}
std::string Machine::wifi_inspect()const{
 auto&d=*model;std::ostringstream r;
 auto head_hex=[](const auto&words){std::string bytes;constexpr char alphabet[]="0123456789abcdef";
  for(unsigned n=0;n<16;n++){auto octet=(words[n/4]>>((n%4)*8))&255;bytes+=alphabet[octet>>4];bytes+=alphabet[octet&15];}return bytes;};
 r<<"{\"enabled\":"<<(BINDING_WIFI_ENABLED?"true":"false")<<",\"version\":"<<BINDING_WIFI_VERSION
  <<",\"coex\":"<<s.wifi_coex<<",\"pio_queued\":"<<s.wifi_pio.size()<<",\"peer_pio_beats\":"<<s.wifi_peer_beats
  <<",\"chip_samples\":"<<s.wifi_chip_samples<<",\"peer_samples\":"<<s.wifi_peer_samples
  <<",\"wire_to_chip\":"<<s.wifi_to_chip_valid<<",\"wire_to_peer\":"<<s.wifi_to_peer_valid;
 auto endpoint=[&](const char*name,auto tx,auto rx,auto active_tx,auto active_rx,auto events,auto fault,auto metric,auto valid,auto length,const auto&bytes){
  r<<",\""<<name<<"\":{\"tx_packets\":"<<tx<<",\"rx_packets\":"<<rx<<",\"tx_active\":"<<unsigned(active_tx)
   <<",\"rx_active\":"<<unsigned(active_rx)<<",\"events\":"<<unsigned(events)<<",\"fault\":"<<unsigned(fault)
   <<",\"metric\":"<<metric<<",\"head_valid\":"<<unsigned(valid)<<",\"head_length\":"<<unsigned(length)
   <<",\"head_bytes\":\""<<head_hex(bytes)<<"\"}";};
 endpoint("chip",d.wifi_tx_packets,d.wifi_rx_packets,d.wifi_tx_active,d.wifi_rx_active,d.wifi_events,d.wifi_last_fault,d.wifi_last_metric,d.wifi_head_valid,d.wifi_head_length,d.wifi_head_bytes);
 endpoint("peer",d.wifi_peer_tx_packets,d.wifi_peer_rx_packets,d.wifi_peer_tx_active,d.wifi_peer_rx_active,d.wifi_peer_events,d.wifi_peer_last_fault,d.wifi_peer_last_metric,d.wifi_peer_head_valid,d.wifi_peer_head_length,d.wifi_peer_head_bytes);
 r<<"}";return r.str();
}
