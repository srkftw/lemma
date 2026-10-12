// SPDX-License-Identifier: Apache-2.0
#include "backing_io.h"
#include <algorithm>
#include <limits>
#include <stdexcept>
namespace lemma {
void validate_backing_request(const BackingRequest&r){
 auto kind=uint64_t(r.kind);
 if(!r.id||kind>2||r.length>BACKING_MAX_TRANSFER||r.offset>UINT64_MAX-r.length||
    (kind==2&&(r.length||r.offset||!r.bytes.empty()))||
    (kind!=2&&!r.length)||(kind==1&&r.bytes.size()!=r.length)||
    (kind!=1&&!r.bytes.empty()))throw std::runtime_error("invalid backing request");
}
void validate_backing_record(const BackingRecord&r){
 validate_backing_request(r.request);auto&q=r.request;auto&o=r.outcome;
 if(o.transferred>q.length||o.error>4095||o.bytes.size()!=o.transferred||
    (!o.error&&o.transferred!=q.length)||
    (q.kind==BackingKind::Write&&!std::equal(o.bytes.begin(),o.bytes.end(),q.bytes.begin())))
  throw std::runtime_error("invalid backing outcome");
}
void validate_backing_state(const BackingState&s){
 if(!s.next_id||s.completed>=s.next_id||s.durable_barrier>s.completed||
    s.observed_write>s.completed||uint64_t(s.phase)>3||
    (s.phase==BackingPhase::Idle&&(s.next_id!=1||s.completed))||
    (s.phase==BackingPhase::Completed&&s.completed!=s.next_id-1))
  throw std::runtime_error("invalid backing state");
}
bool equal_backing_request(const BackingRequest&a,const BackingRequest&b){
 return a.id==b.id&&a.boundary==b.boundary&&a.offset==b.offset&&a.length==b.length&&a.kind==b.kind&&a.bytes==b.bytes;
}
BackingRequest begin_backing(BackingState&s,BackingKind kind,uint64_t boundary,uint64_t offset,uint64_t length,const uint8_t*bytes){
 validate_backing_state(s);
 if(s.poisoned||s.phase==BackingPhase::Pending||s.next_id==UINT64_MAX)
  throw std::runtime_error("backing owner is pending, poisoned or exhausted");
 BackingRequest r;r.id=s.next_id;r.kind=kind;r.boundary=boundary;r.offset=offset;r.length=length;
 if(length>BACKING_MAX_TRANSFER)throw std::runtime_error("backing transfer exceeds bound");
 if(kind==BackingKind::Write){if(!bytes)throw std::runtime_error("missing backing write bytes");r.bytes.assign(bytes,bytes+length);}
 validate_backing_request(r);s.next_id++;s.phase=BackingPhase::Pending;return r;
}
void complete_backing(BackingState&s,const BackingRecord&r){
 validate_backing_record(r);
 if(s.poisoned||s.phase!=BackingPhase::Pending||r.request.id!=s.next_id-1)
  throw std::runtime_error("unexpected backing completion");
 s.completed=r.request.id;s.phase=BackingPhase::Completed;
 if(r.request.kind==BackingKind::Write&&r.outcome.transferred)s.observed_write=r.request.id;
 if(r.request.kind==BackingKind::Barrier&&!r.outcome.error)s.durable_barrier=r.request.id;
}
void cancel_backing(BackingState&s,const BackingRequest&r){
 if(s.poisoned||s.phase!=BackingPhase::Pending||r.id!=s.next_id-1)
  throw std::runtime_error("unexpected backing cancellation");
 s.phase=BackingPhase::Cancelled;
}
namespace {
void put(std::vector<uint8_t>&b,uint64_t v){for(int i=0;i<8;i++)b.push_back(v>>(8*i));}
uint64_t get(const uint8_t*&p,const uint8_t*end){if(end-p<8)throw std::runtime_error("truncated backing record");uint64_t v=0;for(int i=0;i<8;i++)v|=uint64_t(*p++)<<(8*i);return v;}
uint64_t checksum(const uint8_t*p,uint64_t n){uint64_t x=0;for(uint64_t i=0;i<n;i++){x^=uint64_t(p[i])<<56;for(int j=0;j<8;j++)x=(x<<1)^((x>>63)?0x42f0e1eba9ea3693ULL:0);}return x;}
}
std::vector<uint8_t> encode_backing_record(const BackingRecord&r){
 validate_backing_record(r);std::vector<uint8_t>b;
 for(auto v:{r.request.id,r.request.boundary,uint64_t(r.request.kind),r.request.offset,r.request.length,r.outcome.transferred,r.outcome.error})put(b,v);
 b.insert(b.end(),r.request.bytes.begin(),r.request.bytes.end());b.insert(b.end(),r.outcome.bytes.begin(),r.outcome.bytes.end());put(b,checksum(b.data(),b.size()));return b;
}
BackingRecord decode_backing_record(const uint8_t*p,uint64_t n){
 if(n<64||n>64+2*BACKING_MAX_TRANSFER)throw std::runtime_error("invalid backing record length");
 auto*first=p;auto*end=p+n;BackingRecord r;r.request.id=get(p,end);r.request.boundary=get(p,end);r.request.kind=BackingKind(get(p,end));r.request.offset=get(p,end);r.request.length=get(p,end);r.outcome.transferred=get(p,end);r.outcome.error=get(p,end);
 if(uint64_t(r.request.kind)>2||r.request.length>BACKING_MAX_TRANSFER||r.outcome.transferred>r.request.length)throw std::runtime_error("invalid backing record fields");
 uint64_t requested=r.request.kind==BackingKind::Write?r.request.length:0;
 if(n!=64+requested+r.outcome.transferred)throw std::runtime_error("backing record payload length mismatch");
 r.request.bytes.assign(p,p+requested);p+=requested;r.outcome.bytes.assign(p,p+r.outcome.transferred);p+=r.outcome.transferred;
 if(get(p,end)!=checksum(first,n-8))throw std::runtime_error("backing record checksum mismatch");
 validate_backing_record(r);return r;
}
}
