#include "backing_c.h"
#include "backing_peer.h"
#include "../host/backing_io_posix.h"
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <stdexcept>
#include <unistd.h>

namespace {
constexpr uint64_t capture_bound=64*1024*1024;
struct Owner {
  std::shared_ptr<lemma::BackingPlatform> platform;
  lemma::BackingState state;
  int capture=-1;
  uint64_t captured=72;
  bool asynchronous=false;
  std::optional<lemma::BackingRequest> pending;
  ~Owner() { if(capture>=0)close(capture); }
};
std::string text(const char *value) { return value?value:""; }
void failed(char *error,size_t size,const std::exception& e) {
  if(size) { std::strncpy(error,e.what(),size-1);error[size-1]=0; }
}
void write_exact(int fd,const void *raw,uint64_t n,uint64_t offset) {
  auto data=static_cast<const uint8_t*>(raw);
  while(n) { auto size=pwrite(fd,data,n,offset);if(size<=0)throw std::runtime_error("backing capture actual write failure");data+=size;offset+=size;n-=size; }
}
void capture_entry(Owner& owner,uint64_t tag,const std::vector<uint8_t>& wire) {
  if(owner.capture<0)return;
  if(wire.size()+16>capture_bound-owner.captured)throw std::runtime_error("backing capture entry bound");
  uint8_t header[16];for(unsigned i=0;i<8;++i) {header[i]=tag>>(8*i);header[8+i]=wire.size()>>(8*i);}
  write_exact(owner.capture,header,sizeof header,owner.captured);
  write_exact(owner.capture,wire.data(),wire.size(),owner.captured+16);
  owner.captured+=wire.size()+16;
}
}
static void *create_backing(bool asynchronous,int fd,const char *client,const char *socket,
  const char *state,const char *writer,const char *helper,const char *capture,
  const char *identity,char *error,size_t size) {
  try {
    auto owner=std::make_unique<Owner>();
    owner->asynchronous=asynchronous;
    if(!text(client).empty()) {
      if(fd>=0)throw std::runtime_error("companion and POSIX backing are mutually exclusive");
      owner->platform=lemma::make_peer_backing({text(client),text(socket),text(state),text(writer),text(helper),asynchronous});
    } else {
      if(fd<0)throw std::runtime_error("missing backing descriptor");
      owner->platform=std::make_shared<lemma::PosixBacking>(fd);
    }
    if(owner->platform->capacity()!=268435456)throw std::runtime_error("backing capacity mismatch");
    if(!text(capture).empty()) {
      auto binding=text(identity);
      if(binding.size()!=64 || binding.find_first_not_of("0123456789abcdef")!=std::string::npos)throw std::runtime_error("backing capture lacks exact backend identity");
      owner->capture=open(capture,O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC,0600);
      if(owner->capture<0)throw std::runtime_error("backing capture requires a new file");
      auto header=std::string(asynchronous?"LMIOLOG2":"LMIOLOG1")+binding;write_exact(owner->capture,header.data(),header.size(),0);
    }
    return owner.release();
  } catch(const std::exception&e) { failed(error,size,e);return nullptr; }
}
extern "C" void *lemma_backing_create(int fd,const char *client,const char *socket,
 const char *state,const char *writer,const char *helper,const char *capture,const char *identity,char *error,size_t size) {
 return create_backing(false,fd,client,socket,state,writer,helper,capture,identity,error,size);
}
extern "C" void *lemma_backing_create_async(int fd,const char *client,const char *socket,
 const char *state,const char *writer,const char *helper,const char *capture,const char *identity,char *error,size_t size) {
 return create_backing(true,fd,client,socket,state,writer,helper,capture,identity,error,size);
}
extern "C" void lemma_backing_destroy(void *raw) { delete static_cast<Owner*>(raw); }
extern "C" int lemma_backing_execute(void *raw,uint64_t kind,uint64_t boundary,
  uint64_t offset,uint64_t length,uint8_t *bytes,LemmaBackingOutcome *out,char *error,size_t size) {
  auto owner=static_cast<Owner*>(raw);
  try {
    if(!owner || owner->asynchronous || kind>2 || !out || (kind!=2 && !bytes))throw std::runtime_error("invalid backing C invocation");
    uint64_t slot=owner->captured;
    if(owner->capture>=0) {
      if(length>lemma::BACKING_MAX_TRANSFER || 72+2*length>capture_bound-slot)throw std::runtime_error("backing capture resource bound");
      uint64_t pending=0;write_exact(owner->capture,&pending,8,slot);
    }
    auto request=lemma::begin_backing(owner->state,lemma::BackingKind(kind),boundary,offset,length,kind==1?bytes:nullptr);
    lemma::BackingRecord record{request,owner->platform->execute(request)};
    lemma::validate_backing_record(record);
    if(owner->capture>=0) {
      auto wire=lemma::encode_backing_record(record);uint8_t count[8];
      for(unsigned i=0;i<8;++i)count[i]=wire.size()>>(8*i);
      write_exact(owner->capture,wire.data(),wire.size(),slot+8);write_exact(owner->capture,count,8,slot);
      owner->captured+=wire.size()+8;
    }
    lemma::complete_backing(owner->state,record);
    out->transferred=record.outcome.transferred;out->error=record.outcome.error;
    if(kind==0 && out->transferred)std::memcpy(bytes,record.outcome.bytes.data(),out->transferred);
    return 0;
  } catch(const std::exception&e) { if(owner)owner->state.poisoned=true;failed(error,size,e);return -1; }
}
extern "C" int lemma_backing_submit(void *raw,uint64_t kind,uint64_t boundary,
 uint64_t offset,uint64_t length,const uint8_t *bytes,char *error,size_t size) {
 auto owner=static_cast<Owner*>(raw);
 try {
  if(!owner||!owner->asynchronous||owner->pending||kind>2||(kind==1&&!bytes))throw std::runtime_error("invalid backing async admission");
  if(owner->capture>=0&&(length>lemma::BACKING_MAX_TRANSFER||160+3*length>capture_bound-owner->captured))throw std::runtime_error("backing capture admission resource bound");
  auto request=lemma::begin_backing(owner->state,lemma::BackingKind(kind),boundary,offset,length,bytes);
  owner->pending=request;capture_entry(*owner,0,lemma::encode_backing_request(request));
  owner->platform->submit(request);return 0;
 }catch(const std::exception&e){if(owner)owner->state.poisoned=true;failed(error,size,e);return -1;}
}
extern "C" int lemma_backing_poll(void *raw,uint64_t boundary,uint8_t *bytes,
 LemmaBackingOutcome *out,char *error,size_t size) {
 auto owner=static_cast<Owner*>(raw);
 try {
  if(!owner||!owner->asynchronous||!owner->pending||owner->state.poisoned||!out||
     (owner->pending->kind==lemma::BackingKind::Read&&!bytes)||boundary<owner->pending->boundary)
    throw std::runtime_error("invalid backing async acceptance");
  auto result=owner->platform->poll();if(!result)return 1;
  lemma::BackingRecord record{*owner->pending,std::move(*result)};lemma::validate_backing_record(record);
  capture_entry(*owner,1,lemma::encode_timed_backing_record({record,boundary}));
  lemma::complete_backing(owner->state,record);
  out->transferred=record.outcome.transferred;out->error=record.outcome.error;
  if(record.request.kind==lemma::BackingKind::Read&&out->transferred)std::memcpy(bytes,record.outcome.bytes.data(),out->transferred);
  owner->pending.reset();return 0;
 }catch(const std::exception&e){if(owner)owner->state.poisoned=true;failed(error,size,e);return -1;}
}
extern "C" int lemma_backing_retry_ready(void *raw) {
 auto owner=static_cast<Owner*>(raw);return owner&&owner->pending&&!owner->state.poisoned&&owner->platform->retry_ready();
}
extern "C" int lemma_backing_retry(void *raw,char *error,size_t size) {
 auto owner=static_cast<Owner*>(raw);
 try {
  if(!owner||!owner->pending||owner->state.poisoned||!owner->platform->retry_pending())throw std::runtime_error("backing retry is not admitted at this pending boundary");
  return 0;
 }catch(const std::exception&e){failed(error,size,e);return -1;}
}
extern "C" int lemma_backing_passive(void *raw,uint64_t offset,uint64_t length,
  uint8_t *bytes,char *error,size_t size) {
  try {
    auto owner=static_cast<Owner*>(raw);
    if(!owner || owner->state.poisoned || owner->state.phase==lemma::BackingPhase::Pending ||
       !bytes || offset>268435456 || length>268435456-offset)
      throw std::runtime_error("ambiguous backing owner cannot be observed as complete");
    owner->platform->passive_read(offset,bytes,length);return 0;
  } catch(const std::exception&e) { failed(error,size,e);return -1; }
}
extern "C" int lemma_backing_get_state(void *raw,LemmaBackingState *state) {
  auto owner=static_cast<Owner*>(raw);if(!owner || !state)return -1;
  auto &s=owner->state;*state={s.next_id,s.completed,s.durable_barrier,s.observed_write,uint64_t(s.phase),uint64_t(s.poisoned)};
  return 0;
}
extern "C" int lemma_backing_capture_checkpoint(void *raw,char *error,size_t size) {
  try {
    auto owner=static_cast<Owner*>(raw);
    if(!owner || owner->state.poisoned || owner->state.phase==lemma::BackingPhase::Pending)throw std::runtime_error("pending/ambiguous backing checkpoint");
    if(owner->capture>=0 && fsync(owner->capture))throw std::runtime_error("backing capture checkpoint fsync failed");
    return 0;
  } catch(const std::exception&e) { failed(error,size,e);return -1; }
}
extern "C" int lemma_backing_export(void *raw,const char *path,char *error,size_t size) {
  int fd=-1;
  try {
    auto owner=static_cast<Owner*>(raw);
    if(!owner || owner->state.poisoned || owner->state.phase==lemma::BackingPhase::Pending || !path)throw std::runtime_error("pending/ambiguous backing export");
    fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
    if(fd<0)throw std::runtime_error("backing export requires an unused destination");
    if(ftruncate(fd,268435456))throw std::runtime_error("backing export capacity");
    std::array<uint8_t,1048576>bytes{};
    for(uint64_t offset=0;offset<268435456;offset+=bytes.size()) {
      owner->platform->passive_read(offset,bytes.data(),bytes.size());
      if(std::any_of(bytes.begin(),bytes.end(),[](uint8_t b){return b!=0;}))write_exact(fd,bytes.data(),bytes.size(),offset);
    }
    if(fsync(fd))throw std::runtime_error("backing export artifact fsync failed");
    if(close(fd)) { fd=-1;unlink(path);throw std::runtime_error("backing export close failed"); }
    return 0;
  } catch(const std::exception&e) { if(fd>=0){close(fd);unlink(path);}failed(error,size,e);return -1; }
}
extern "C" int lemma_backing_set_state(void *raw,const LemmaBackingState *state,char *error,size_t size) {
  try {
    auto owner=static_cast<Owner*>(raw);if(!owner || owner->pending || !state || state->phase>3 || state->poisoned>1)throw std::runtime_error("invalid backing restore");
    lemma::BackingState replacement{state->next_id,state->completed,state->durable_barrier,state->observed_write,lemma::BackingPhase(state->phase),bool(state->poisoned)};
    lemma::validate_backing_state(replacement);
    if(replacement.poisoned || replacement.phase==lemma::BackingPhase::Pending)throw std::runtime_error("ambiguous external operation cannot restore");
    owner->state=replacement;return 0;
  } catch(const std::exception&e) { failed(error,size,e);return -1; }
}
