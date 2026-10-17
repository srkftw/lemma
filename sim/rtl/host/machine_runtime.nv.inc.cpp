// Host-only independent raw nonvolatile boot-medium ownership. No image policy.
void Machine::initialize_boot_io(){
 if(options.boot_write_limit&&(!BINDING_BOOT_NV_ENABLED||options.host_threads!=1||!options.boot_replay_path.empty()))throw std::runtime_error("boot write limit requires single-thread native live product backing");
 if((!options.boot_capture_path.empty()||!options.boot_replay_path.empty())&&!BINDING_BOOT_NV_ENABLED)throw std::runtime_error("boot backing requires profile7");
 if(!options.boot_capture_path.empty()&&!options.boot_replay_path.empty())throw std::runtime_error("boot capture and replay are exclusive");
 if(!options.boot_replay_path.empty())boot_replay=read_backing_replay(options.boot_replay_path,"LMNVLOG2");
 if(!options.boot_capture_path.empty()){
  boot_capture=open(options.boot_capture_path.c_str(),O_RDWR|O_CREAT|O_EXCL,0600);if(boot_capture<0)throw std::runtime_error("boot capture requires a new file");
  try{backing_header(boot_capture,"LMNVLOG2");}catch(...){close(boot_capture);boot_capture=-1;unlink(options.boot_capture_path.c_str());throw;}
  boot_capture_bytes=72;active_boot_capture=options.boot_capture_path;
 }
 auto&soc=*model;soc.boot_media_ready=0;soc.boot_media_result=0;soc.boot_media_bytes=0;soc.boot_reset_origin=s.boot_reset_origin;soc.external_boot_media_busy=0;for(unsigned i=0;i<128;i++)soc.boot_media_rdata[i]=0;
}
void Machine::attach_boot_backing(std::shared_ptr<BackingPlatform>platform){
 if(!BINDING_BOOT_NV_ENABLED||prepared||boot_platform||s.boot_medium_present||!platform||platform->capacity()!=BINDING_BOOT_NV_CAPACITY_SECTORS*512)throw std::runtime_error("boot backing requires unattached product capacity before execution");
 std::map<uint64_t,std::array<uint8_t,512>>initial;std::array<uint8_t,1048576>chunk{};
 for(uint64_t offset=0;offset<platform->capacity();){auto count=std::min<uint64_t>(chunk.size(),platform->capacity()-offset);platform->passive_read(offset,chunk.data(),count);for(uint64_t i=0;i<count;i+=512)if(std::any_of(chunk.begin()+i,chunk.begin()+i+512,[](uint8_t b){return b!=0;})){std::array<uint8_t,512>sector{};std::memcpy(sector.data(),chunk.data()+i,512);initial[(offset+i)/512]=sector;}offset+=count;}
 s.accepted_boot_medium=std::move(initial);boot_platform=std::move(platform);s.boot_medium_present=1;
}
std::shared_ptr<BackingPlatform> Machine::boot_posix_platform(int fd){
 auto platform=std::make_shared<PosixBacking>(fd);
 if(options.boot_write_limit){auto span=*options.boot_write_limit;platform->limit_write_span(span[0],span[1],span[2]);}
 return platform;
}
void Machine::open_boot_medium(const std::string&path){
 if(boot_medium>=0||boot_platform)throw std::runtime_error("boot medium already attached");int fd=open(path.c_str(),O_RDWR);if(fd<0)throw std::runtime_error("cannot open boot medium");
 try{attach_boot_backing(boot_posix_platform(fd));}catch(...){close(fd);throw;}boot_medium=fd;
}
void Machine::capture_boot(uint64_t tag,const std::vector<uint8_t>&wire){
 if(boot_capture<0)return;if(wire.size()+16>MAX_BACKING_LOG-boot_capture_bytes)throw std::runtime_error("boot outcome capture full");uint8_t header[16];for(unsigned i=0;i<8;i++){header[i]=tag>>(8*i);header[8+i]=uint64_t(wire.size())>>(8*i);}
 if(pwrite(boot_capture,header,16,boot_capture_bytes)!=16||pwrite(boot_capture,wire.data(),wire.size(),boot_capture_bytes+16)!=ssize_t(wire.size()))throw std::runtime_error("boot outcome capture failed");boot_capture_bytes+=wire.size()+16;
}
void Machine::observe_boot(const BackingRecord&record){
 if(record.request.kind==BackingKind::Barrier)return;
 for(uint64_t i=0;i<record.outcome.transferred;){auto address=record.request.offset+i,sector=address/512,within=address%512,count=std::min<uint64_t>(512-within,record.outcome.transferred-i);auto&b=s.accepted_boot_medium[sector];std::copy_n(record.outcome.bytes.data()+i,count,b.data()+within);if(std::all_of(b.begin(),b.end(),[](uint8_t v){return v==0;}))s.accepted_boot_medium.erase(sector);i+=count;}
}
std::optional<BackingOutcome> Machine::boot_operation(BackingKind kind,uint64_t offset,uint64_t length,const uint8_t*data){
 if(!boot_platform)throw std::runtime_error("no boot backing platform");
 if(!s.boot_pending){
  if(boot_capture>=0&&160+3*length>MAX_BACKING_LOG-boot_capture_bytes)throw std::runtime_error("boot capture resource bound");
  auto request=begin_backing(s.boot_backing,kind,s.cycle,offset,length,data);s.boot_pending=request;s.boot_poll_cycle=s.cycle;
  try{capture_boot(0,encode_backing_request(request));if(!options.boot_replay_path.empty()){
    if(!s.isolated||boot_replay_cursor>=boot_replay.size()||!equal_backing_request(request,boot_replay[boot_replay_cursor].record.request))throw std::runtime_error("boot replay request mismatch or missing outcome");
   }else boot_platform->submit(request);
  }catch(...){s.boot_backing.poisoned=true;throw;}
 }else{auto&r=*s.boot_pending;if(r.kind!=kind||r.offset!=offset||r.length!=length||(kind==BackingKind::Write&&!std::equal(r.bytes.begin(),r.bytes.end(),data)))throw std::runtime_error("boot owner changed under backpressure");}
 return poll_boot();
}
std::optional<BackingOutcome> Machine::poll_boot(){
 if(!s.boot_pending||s.cycle<s.boot_poll_cycle)return std::nullopt;
 try{std::optional<BackingOutcome>outcome;
  if(!options.boot_replay_path.empty()){
   const auto&r=boot_replay.at(boot_replay_cursor);if(s.cycle<r.accepted_boundary){if(s.cycle>UINT64_MAX-1000)throw std::runtime_error("boot poll clock exhausted");s.boot_poll_cycle=s.cycle+1000;return std::nullopt;}
   if(s.cycle!=r.accepted_boundary)throw std::runtime_error("boot replay completion boundary mismatch");outcome=r.record.outcome;boot_platform->apply_recorded(*s.boot_pending,*outcome);
  }else outcome=boot_platform->poll();
  if(!outcome){if(s.cycle>UINT64_MAX-1000)throw std::runtime_error("boot poll clock exhausted");s.boot_poll_cycle=s.cycle+1000;return std::nullopt;}
  BackingRecord record{*s.boot_pending,*outcome};validate_backing_record(record);capture_boot(1,encode_timed_backing_record({record,s.cycle}));observe_boot(record);complete_backing(s.boot_backing,record);s.boot_pending.reset();s.boot_poll_cycle=0;if(!options.boot_replay_path.empty())boot_replay_cursor++;return outcome;
 }catch(...){s.boot_backing.poisoned=true;throw;}
}
void Machine::boot_before_edge(bool domain_reset){
 auto&soc=*model;soc.boot_media_ready=0;soc.boot_media_result=0;soc.boot_media_bytes=0;for(unsigned i=0;i<128;i++)soc.boot_media_rdata[i]=0;
 if(!BINDING_BOOT_NV_ENABLED){soc.external_boot_media_busy=0;soc.boot_reset_origin=1;return;}
 if(domain_reset&&!s.boot_reset_seen){if(s.boot_reset_origin==UINT64_MAX)throw std::runtime_error("boot reset origin exhausted");s.boot_reset_origin++;}s.boot_reset_seen=domain_reset;soc.boot_reset_origin=s.boot_reset_origin;
 if(s.boot_pending&&(domain_reset||!soc.boot_media_valid||soc.boot_media_origin!=s.boot_request_origin||soc.boot_media_id!=s.boot_request_id))s.boot_orphan=1;
 if(s.boot_orphan){if(poll_boot()){s.boot_orphan=0;s.boot_request_origin=s.boot_request_id=s.boot_request_kind=s.boot_request_sector=0;}}
 else if(soc.boot_media_valid&&!domain_reset){
  if(s.boot_pending&&(soc.boot_media_kind!=s.boot_request_kind||soc.boot_media_sector!=s.boot_request_sector))throw std::runtime_error("boot controller changed retained request");
  if(!s.boot_pending){s.boot_request_origin=soc.boot_media_origin;s.boot_request_id=soc.boot_media_id;s.boot_request_kind=soc.boot_media_kind;s.boot_request_sector=soc.boot_media_sector;}
  std::optional<BackingOutcome>outcome;
  if(!s.boot_medium_present)outcome=BackingOutcome{0,19,{}};
  else if(soc.boot_media_kind<1||soc.boot_media_kind>3||(soc.boot_media_kind!=3&&soc.boot_media_sector>=BINDING_BOOT_NV_CAPACITY_SECTORS))outcome=BackingOutcome{0,22,{}};
  else{std::array<uint8_t,512>data{};std::memcpy(data.data(),soc.boot_media_wdata.data(),512);auto kind=soc.boot_media_kind==1?BackingKind::Read:soc.boot_media_kind==2?BackingKind::Write:BackingKind::Barrier;outcome=boot_operation(kind,kind==BackingKind::Barrier?0:soc.boot_media_sector*512,kind==BackingKind::Barrier?0:512,data.data());}
  if(outcome){soc.boot_media_ready=1;soc.boot_media_result=outcome->error;soc.boot_media_bytes=outcome->transferred;if(soc.boot_media_kind==1&&!outcome->bytes.empty())std::memcpy(soc.boot_media_rdata.data(),outcome->bytes.data(),outcome->bytes.size());s.boot_request_origin=s.boot_request_id=s.boot_request_kind=s.boot_request_sector=0;}
 }
 soc.external_boot_media_busy=s.boot_pending.has_value();
}
void Machine::export_boot_medium(const std::string&path)const{
 if(!s.boot_medium_present||s.boot_backing.poisoned||(s.boot_pending&&!boot_fork_suspended))throw std::runtime_error("boot export requires resolved live or suspended private accepted bytes");
 int fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);if(fd<0)throw std::runtime_error("boot export destination exists");try{if(ftruncate(fd,BINDING_BOOT_NV_CAPACITY_SECTORS*512))throw std::runtime_error("boot export capacity failed");for(auto&[sector,b]:s.accepted_boot_medium)if(pwrite(fd,b.data(),512,sector*512)!=512)throw std::runtime_error("boot export copy failed");if(fsync(fd))throw std::runtime_error("boot export barrier failed");close(fd);}catch(...){close(fd);unlink(path.c_str());throw;}
}
