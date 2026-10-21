// SPDX-License-Identifier: Apache-2.0
// Host embodiment of the existing RTL machine, never a guest implementation.
#include "machine_runtime.h"
#include "backing_io.h"
#include "lemma_silicon_binding.h"
#include "Vlemma_soc___024root.h"
#include <emscripten.h>
#ifndef LEMMA_MULTIMODAL_ENABLED
#define LEMMA_MULTIMODAL_ENABLED 0
#endif
#include <algorithm>
#include <memory>
#include <stdexcept>

EM_JS(int, storage_read, (uint8_t* p, unsigned n, double offset, unsigned boot), {
 try { return (boot?Module.bootBacking:Module.backing).read(HEAPU8.subarray(p,p+n), {at:offset}); }
 catch(e) { Module.backingError=String(e); Module.backingFailure=e; return -({QuotaExceededError:28,NotAllowedError:13,SecurityError:13,InvalidStateError:9,AbortError:125,NotFoundError:2}[e.name]||5); }
});
EM_JS(int, storage_write, (const uint8_t* p, unsigned n, double offset, unsigned boot), {
 try { return (boot?Module.bootBacking:Module.backing).write(HEAPU8.subarray(p,p+n), {at:offset}); }
 catch(e) { Module.backingError=String(e); Module.backingFailure=e; return -({QuotaExceededError:28,NotAllowedError:13,SecurityError:13,InvalidStateError:9,AbortError:125,NotFoundError:2}[e.name]||5); }
});
EM_JS(int, storage_barrier, (unsigned boot), {
 try { (boot?Module.bootBacking:Module.backing).flush(); return 0; }
 catch(e) { Module.backingError=String(e); Module.backingFailure=e; return ({QuotaExceededError:28,NotAllowedError:13,SecurityError:13,InvalidStateError:9,AbortError:125,NotFoundError:2}[e.name]||5); }
});
EM_JS(double, storage_capacity, (unsigned boot), { return (boot?Module.bootBacking:Module.backing).getSize(); });
// Optional external transport. IDs and virtual boundaries cross the JS ABI as
// decimal strings; offsets/lengths are independently bounded below 2^53.
EM_JS(int, backing_async_mode, (), {
 const submit=typeof Module.backing.submit==='function',poll=typeof Module.backing.poll==='function';
 return submit===poll?(submit?1:0):-1;
});
EM_JS(int, backing_submit, (const char* request,const uint8_t* p,unsigned n), {
 try { Module.backing.submit(JSON.parse(UTF8ToString(request)),HEAPU8.slice(p,p+n));return 0; }
 catch(e){Module.backingError=String(e);return -1;}
});
EM_JS(int, backing_poll, (uint8_t* p,unsigned capacity,uint32_t* metadata), {
 try {
  const o=Module.backing.poll();if(o===null||o===undefined)return 0;
  if(!Number.isSafeInteger(o.transferred)||o.transferred<0||o.transferred>capacity||
     !Number.isSafeInteger(o.error)||o.error<0||o.error>0xffffffff||
     !(o.bytes instanceof Uint8Array)||o.bytes.length!==o.transferred)throw Error('Invalid bounded backing outcome');
  HEAPU8.set(o.bytes,p);HEAPU32[metadata>>>2]=o.transferred;HEAPU32[(metadata>>>2)+1]=o.error;return 1;
 }catch(e){Module.backingError=String(e);return -1;}
});

namespace {
class BrowserBacking final : public lemma::BackingPlatform {
 bool boot_;
 uint64_t bytes_;
 int read(uint8_t*p,unsigned n,double offset)const{return storage_read(p,n,offset,boot_);}
 int write(const uint8_t*p,unsigned n,double offset){return storage_write(p,n,offset,boot_);}
 int barrier(){return storage_barrier(boot_);}
 bool asynchronous_;
 std::optional<lemma::BackingRequest> pending_;
public:
 BrowserBacking(bool boot=false):boot_(boot),bytes_(storage_capacity(boot)),asynchronous_(!boot&&backing_async_mode()==1){
  if(!boot&&backing_async_mode()<0)throw std::runtime_error("external backing requires both submit and poll");
 }
 uint64_t capacity() const override { return bytes_; }
 void passive_read(uint64_t offset,uint8_t* p,uint64_t n) const override {
  if(offset>capacity()||n>capacity()-offset||n>lemma::BACKING_MAX_TRANSFER)
   throw std::runtime_error("browser backing read outside capacity");
  if(read(p,n,offset)!=int(n))throw std::runtime_error("browser backing observational read failed");
 }
 lemma::BackingOutcome execute(const lemma::BackingRequest& r) override {
  if(asynchronous_)throw std::runtime_error("asynchronous backing must use request admission");
  lemma::BackingOutcome o;
  if(r.kind==lemma::BackingKind::Barrier){o.error=barrier();return o;}
  if(r.kind==lemma::BackingKind::Read){o.bytes.resize(r.length);int n=read(o.bytes.data(),r.length,r.offset);
   if(n<0){o.error=-n;o.bytes.clear();}else{o.transferred=n;o.bytes.resize(n);if(n!=int(r.length))o.error=5;}return o;}
  std::vector<uint8_t> before(r.length);
  int observed=read(before.data(),r.length,r.offset);
  // If the observational preflight fails, the write has not been issued.
  // Its empty changed prefix is known, so the guest receives an I/O error
  // without poisoning later writing. A failure after issuing the write has
  // stricter requirements because its changed bytes may be unknown.
  if(observed!=int(r.length)){o.error=observed<0?-observed:5;return o;}
  int n=write(r.bytes.data(),r.length,r.offset);
  if(n>=0){o.transferred=n;o.error=n==int(r.length)?0:5;}
  else {
   o.error=-n;std::vector<uint8_t> after(r.length);passive_read(r.offset,after.data(),after.size());
   // A throwing external write may have changed bytes. Observe its actual
   // result instead of assuming rollback. Non-prefix mutations poison the
   // session rather than inventing an outcome unsupported by this contract.
   for(uint64_t i=0;i<r.length;i++)if(before[i]!=after[i])o.transferred=i+1;
   for(uint64_t i=0;i<o.transferred;i++)if(after[i]!=r.bytes[i])
    throw std::runtime_error("browser write failure has unsupported non-prefix mutation");
  }
  o.bytes.assign(r.bytes.begin(),r.bytes.begin()+o.transferred);return o;
 }
 void submit(const lemma::BackingRequest& r) override {
  if(!asynchronous_){BackingPlatform::submit(r);return;}
  if(pending_)throw std::runtime_error("external backing already has a pending request");
  lemma::validate_backing_request(r);pending_=r;
  auto wire="{\"id\":\""+std::to_string(r.id)+"\",\"boundary\":\""+std::to_string(r.boundary)+
   "\",\"kind\":"+std::to_string(uint64_t(r.kind))+",\"offset\":"+std::to_string(r.offset)+
   ",\"length\":"+std::to_string(r.length)+"}";
  if(backing_submit(wire.c_str(),r.bytes.data(),r.bytes.size()))
   throw std::runtime_error("external backing submit failed with unknown outcome");
 }
 std::optional<lemma::BackingOutcome> poll() override {
  if(!asynchronous_)return BackingPlatform::poll();
  if(!pending_)throw std::runtime_error("external backing polled without a request");
  lemma::BackingOutcome o;o.bytes.resize(pending_->length);uint32_t metadata[2]={0,0};
  int state=backing_poll(o.bytes.data(),o.bytes.size(),metadata);
  if(state<0)throw std::runtime_error("external backing completion failed with unknown outcome");
  if(!state)return std::nullopt;
  o.transferred=metadata[0];o.error=metadata[1];o.bytes.resize(o.transferred);pending_.reset();return o;
 }
 void apply_recorded(const lemma::BackingRequest&r,const lemma::BackingOutcome&o) override {
  if(r.kind==lemma::BackingKind::Write&&o.transferred){int n=write(o.bytes.data(),o.transferred,r.offset);
   if(n!=int(o.transferred))throw std::runtime_error("browser private replay write failed");}
  // The recorded error is the guest result. Applying a fork still requires a
  // real local barrier, including when the original barrier returned failure.
  if(r.kind==lemma::BackingKind::Barrier&&barrier())throw std::runtime_error("browser private replay barrier failed");
 }
};
std::unique_ptr<lemma::Machine> machine;
std::string error,result,capture_path;
unsigned instance=0;
template<class F>int checked(F f){try{error.clear();f();return 0;}catch(const std::exception&e){error=e.what();return -1;}}
}
extern "C" {
EMSCRIPTEN_KEEPALIVE const char* lemma_error(){return error.c_str();}
EMSCRIPTEN_KEEPALIVE const char* lemma_capture_path(){return machine?machine->backing_capture_path().c_str():"";}
EMSCRIPTEN_KEEPALIVE int lemma_create_mode(unsigned replay){return checked([=]{
 lemma::Options o;o.uart_path="/uart.bin";o.quiet_uart=true;o.deadline=120;o.trace_limit=0;o.fork_directory="/forks";
 if(replay)o.backing_replay_path="/replay.io";
 else {capture_path="/backing-"+std::to_string(++instance)+".io";o.backing_capture_path=capture_path;}
 if(BINDING_BOOT_NV_ENABLED){if(replay)throw std::runtime_error("product browser replay needs separate boot/user outcome tapes");o.boot_capture_path="/boot-backing-"+std::to_string(instance)+".io";}
 auto next=std::make_unique<lemma::Machine>(o);next->load_rom("/boot.bin");
 if(BINDING_BOOT_NV_ENABLED){
  // Separate opaque OPFS backing. The genuine Lean ROM loads the image and
  // its MAC-bound discovery bytes through actual BootNV transactions.
  next->attach_boot_backing(std::make_shared<BrowserBacking>(true));
 }else{
  next->load_elf("/image.elf");auto dtb=lemma::bytes("/machine.dtb");next->put(BINDING_DTB_BASE,dtb.data(),dtb.size());
 }
 next->descriptor("/descriptor.bin");
 next->attach_backing(std::make_shared<BrowserBacking>());next->prepare();machine.swap(next);
 });}
EMSCRIPTEN_KEEPALIVE int lemma_create(){return lemma_create_mode(0);}
// Recorded Clocked13 transport only. The caller must independently admit its
// archived producer; this API never adopts an external process or live peer.
EMSCRIPTEN_KEEPALIVE int lemma_create_usb_private(){return checked([]{
 if(!LEMMA_USB_CLOCKED_ENABLED||machine)throw std::runtime_error("private USB create requires an unused Clocked instance");
 lemma::Options o;o.uart_path="/uart.bin";o.quiet_uart=true;o.deadline=120;o.trace_limit=0;o.fork_directory="/forks";
 machine=std::make_unique<lemma::Machine>(o);
 });}
EMSCRIPTEN_KEEPALIVE int lemma_usb_outcomes(const char*path){return checked([=]{
 if(!machine||!LEMMA_USB_CLOCKED_ENABLED)throw std::runtime_error("no Clocked private machine");
 machine->bind_usb_replay(path);
 });}
EMSCRIPTEN_KEEPALIVE int lemma_run(unsigned cycles){return checked([=]{if(!machine||cycles>1000000)throw std::runtime_error("invalid bounded browser run");machine->run(cycles);});}
EMSCRIPTEN_KEEPALIVE const char* lemma_pcm(){
#if LEMMA_MULTIMODAL_ENABLED
 if(!machine)return "{}";result=machine->take_multimodal_pcm();return result.c_str();
#else
 return "{}";
#endif
}
EMSCRIPTEN_KEEPALIVE const char* lemma_inspect(){if(!machine)return "{}";result=machine->inspect();return result.c_str();}
// Presentation reads the actual controller's completed sequence. An accepted
// refresh or a boot UART prefix does not establish displayed-page readiness.
EMSCRIPTEN_KEEPALIVE const char* lemma_paper_inspect(){if(!machine)return "{}";
 auto*r=machine->soc().rootp;
 result="{\"completed\":\""+std::to_string(r->lemma_soc__DOT__paper__DOT__completed)+
   "\",\"accepted\":\""+std::to_string(machine->soc().panel_sequence)+
   "\",\"busy\":"+std::to_string(r->lemma_soc__DOT__paper__DOT__busy)+"}";
 return result.c_str();}
EMSCRIPTEN_KEEPALIVE int lemma_multimodal_diagnostic_records(){return checked([]{
#if LEMMA_MULTIMODAL_ENABLED
 if(!machine)throw std::runtime_error("no machine");machine->ram_dump(0x80410000,640,"/multimodal-probe.bin");
#else
 throw std::runtime_error("multimodal diagnostic absent");
#endif
});}
EMSCRIPTEN_KEEPALIVE int lemma_event(const char*event){return checked([=]{if(!machine)throw std::runtime_error("no machine");machine->schedule(lemma::parse_event(event));});}
EMSCRIPTEN_KEEPALIVE const uint8_t* lemma_pixels(){return machine?machine->state().visible.data():nullptr;}
EMSCRIPTEN_KEEPALIVE unsigned lemma_pixel_count(){return machine?machine->state().visible.size():0;}
EMSCRIPTEN_KEEPALIVE int lemma_snapshot(const char*path){return checked([=]{if(!machine)throw std::runtime_error("no machine");machine->snapshot(path);});}
EMSCRIPTEN_KEEPALIVE int lemma_restore(const char*path){return checked([=]{if(!machine)throw std::runtime_error("no machine");machine->restore(path);});}
EMSCRIPTEN_KEEPALIVE int lemma_export(const char*path){return checked([=]{if(!machine)throw std::runtime_error("no machine");machine->export_medium(path);});}
EMSCRIPTEN_KEEPALIVE int lemma_export_private(const char*path){return checked([=]{if(!machine)throw std::runtime_error("no machine");machine->export_private_medium(path);});}
EMSCRIPTEN_KEEPALIVE int lemma_backing_outcomes(const char*path){return checked([=]{if(!machine)throw std::runtime_error("no machine");machine->bind_backing_replay(path);});}
EMSCRIPTEN_KEEPALIVE int lemma_rebind_private(){return checked([]{if(!machine)throw std::runtime_error("no machine");machine->rebind_private_backing(std::make_shared<BrowserBacking>());});}
EMSCRIPTEN_KEEPALIVE int lemma_reset(unsigned cold){return checked([=]{if(!machine)throw std::runtime_error("no machine");if(cold)machine->cold_cycle();else machine->warm_reset();});}
EMSCRIPTEN_KEEPALIVE void lemma_destroy(){machine.reset();}
}
