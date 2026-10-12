// SPDX-License-Identifier: Apache-2.0
// Host embodiment of the existing RTL machine, never a guest implementation.
#include "machine_runtime.h"
#include "backing_io.h"
#include "lemma_silicon_binding.h"
#include <emscripten.h>
#include <algorithm>
#include <memory>
#include <stdexcept>

EM_JS(int, backing_read, (uint8_t* p, unsigned n, double offset), {
 try { return Module.backing.read(HEAPU8.subarray(p,p+n), {at:offset}); }
 catch(e) { Module.backingError=String(e); Module.backingFailure=e; return -({QuotaExceededError:28,NotAllowedError:13,SecurityError:13,InvalidStateError:9,AbortError:125,NotFoundError:2}[e.name]||5); }
});
EM_JS(int, backing_write, (const uint8_t* p, unsigned n, double offset), {
 try { return Module.backing.write(HEAPU8.subarray(p,p+n), {at:offset}); }
 catch(e) { Module.backingError=String(e); Module.backingFailure=e; return -({QuotaExceededError:28,NotAllowedError:13,SecurityError:13,InvalidStateError:9,AbortError:125,NotFoundError:2}[e.name]||5); }
});
EM_JS(int, backing_barrier, (), {
 try { Module.backing.flush(); return 0; }
 catch(e) { Module.backingError=String(e); Module.backingFailure=e; return ({QuotaExceededError:28,NotAllowedError:13,SecurityError:13,InvalidStateError:9,AbortError:125,NotFoundError:2}[e.name]||5); }
});
EM_JS(double, backing_capacity, (), { return Module.backing.getSize(); });

namespace {
class BrowserBacking final : public lemma::BackingPlatform {
 uint64_t bytes_;
public:
 BrowserBacking():bytes_(backing_capacity()){}
 uint64_t capacity() const override { return bytes_; }
 void passive_read(uint64_t offset,uint8_t* p,uint64_t n) const override {
  if(offset>capacity()||n>capacity()-offset||n>lemma::BACKING_MAX_TRANSFER)
   throw std::runtime_error("browser backing read outside capacity");
  if(backing_read(p,n,offset)!=int(n))throw std::runtime_error("browser backing observational read failed");
 }
 lemma::BackingOutcome execute(const lemma::BackingRequest& r) override {
  lemma::BackingOutcome o;
  if(r.kind==lemma::BackingKind::Barrier){o.error=backing_barrier();return o;}
  if(r.kind==lemma::BackingKind::Read){o.bytes.resize(r.length);int n=backing_read(o.bytes.data(),r.length,r.offset);
   if(n<0){o.error=-n;o.bytes.clear();}else{o.transferred=n;o.bytes.resize(n);if(n!=int(r.length))o.error=5;}return o;}
  std::vector<uint8_t> before(r.length);
  int observed=backing_read(before.data(),r.length,r.offset);
  // If the observational preflight fails, the write has not been issued.
  // Its empty changed prefix is known, so the guest receives an I/O error
  // without poisoning later writing. A failure after issuing the write has
  // stricter requirements because its changed bytes may be unknown.
  if(observed!=int(r.length)){o.error=observed<0?-observed:5;return o;}
  int n=backing_write(r.bytes.data(),r.length,r.offset);
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
 void apply_recorded(const lemma::BackingRequest&r,const lemma::BackingOutcome&o) override {
  if(r.kind==lemma::BackingKind::Write&&o.transferred){int n=backing_write(o.bytes.data(),o.transferred,r.offset);
   if(n!=int(o.transferred))throw std::runtime_error("browser private replay write failed");}
  if(r.kind==lemma::BackingKind::Barrier&&!o.error&&backing_barrier())throw std::runtime_error("browser private replay barrier failed");
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
 auto next=std::make_unique<lemma::Machine>(o);next->load_elf("/image.elf");next->load_rom("/boot.bin");
 auto dtb=lemma::bytes("/machine.dtb");next->put(BINDING_DTB_BASE,dtb.data(),dtb.size());next->descriptor("/descriptor.bin");
 next->attach_backing(std::make_shared<BrowserBacking>());next->prepare();machine.swap(next);
 });}
EMSCRIPTEN_KEEPALIVE int lemma_create(){return lemma_create_mode(0);}
EMSCRIPTEN_KEEPALIVE int lemma_run(unsigned cycles){return checked([=]{if(!machine||cycles>1000000)throw std::runtime_error("invalid bounded browser run");machine->run(cycles);});}
EMSCRIPTEN_KEEPALIVE const char* lemma_inspect(){if(!machine)return "{}";result=machine->inspect();return result.c_str();}
EMSCRIPTEN_KEEPALIVE int lemma_event(const char*event){return checked([=]{if(!machine)throw std::runtime_error("no machine");machine->schedule(lemma::parse_event(event));});}
EMSCRIPTEN_KEEPALIVE const uint8_t* lemma_pixels(){return machine?machine->state().visible.data():nullptr;}
EMSCRIPTEN_KEEPALIVE unsigned lemma_pixel_count(){return machine?machine->state().visible.size():0;}
EMSCRIPTEN_KEEPALIVE int lemma_snapshot(const char*path){return checked([=]{if(!machine)throw std::runtime_error("no machine");machine->snapshot(path);});}
EMSCRIPTEN_KEEPALIVE int lemma_restore(const char*path){return checked([=]{if(!machine)throw std::runtime_error("no machine");machine->restore(path);});}
EMSCRIPTEN_KEEPALIVE int lemma_export(const char*path){return checked([=]{if(!machine)throw std::runtime_error("no machine");machine->export_medium(path);});}
EMSCRIPTEN_KEEPALIVE int lemma_rebind_private(){return checked([]{if(!machine)throw std::runtime_error("no machine");machine->rebind_private_backing(std::make_shared<BrowserBacking>());});}
EMSCRIPTEN_KEEPALIVE int lemma_reset(unsigned cold){return checked([=]{if(!machine)throw std::runtime_error("no machine");if(cold)machine->cold_cycle();else machine->warm_reset();});}
EMSCRIPTEN_KEEPALIVE void lemma_destroy(){machine.reset();}
}
