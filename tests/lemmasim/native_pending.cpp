// SPDX-License-Identifier: Apache-2.0
// Literal controller-state/runtime qualification. This fixture initializes a
// held medium request directly; it does not claim guest-driver execution.
#include "machine_runtime.h"
#include "Vlemma_soc___024root.h"
#include <algorithm>
#include <cassert>
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace lemma;
struct PendingMedium final:BackingPlatform {
 bool released=false;unsigned submissions=0,polls=0;
 std::optional<BackingRequest> request;
 uint64_t capacity()const override{return 268435456;}
 void passive_read(uint64_t offset,uint8_t*b,uint64_t n)const override{
  std::fill(b,b+n,0);for(uint64_t i=0;i<n;i++)if(offset+i>=1536&&offset+i<2048)b[i]=0x6d;
 }
 BackingOutcome execute(const BackingRequest&)override{throw std::runtime_error("synchronous path used");}
 void submit(const BackingRequest&r)override{assert(!request);validate_backing_request(r);request=r;submissions++;}
 std::optional<BackingOutcome> poll()override{
  assert(request);polls++;if(!released)return std::nullopt;
  BackingOutcome out;out.transferred=request->length;out.bytes.resize(out.transferred);
  if(request->kind==BackingKind::Read)passive_read(request->offset,out.bytes.data(),out.bytes.size());
  else out.bytes=request->bytes;
  request.reset();return out;
 }
 void apply_recorded(const BackingRequest&,const BackingOutcome&)override{throw std::runtime_error("original platform contacted by replay");}
};
template<class F>void rejects(F f){bool no=false;try{f();}catch(const std::runtime_error&){no=true;}assert(no);}
void held_read(Machine&m){auto*r=m.soc().rootp;r->lemma_soc__DOT__blockdev__DOT__state=8;
 r->lemma_soc__DOT__blockdev__DOT__kind=0;r->lemma_soc__DOT__blockdev__DOT__sector=3;
 r->lemma_soc__DOT__blockdev__DOT__data_address=0x82001000;
 r->lemma_soc__DOT__blockdev__DOT__status_address=0x82002000;}
Options opts(const std::string&dir,const std::string&name){Options o;o.quiet_uart=true;o.deadline=30;
 o.uart_path=dir+"/"+name+".uart";o.fork_directory=dir;return o;}
int main(int argc,char**argv){assert(argc==7);std::string dir=argv[1];auto o=opts(dir,"original");o.backing_capture_path=dir+"/actual.io";
 auto load=[&](Machine&m){m.load_elf(argv[2]);m.load_rom(argv[3]);auto dtb=bytes(argv[4]);m.put(number(argv[6]),dtb.data(),dtb.size());m.descriptor(argv[5]);};
 auto medium=std::make_shared<PendingMedium>();Machine original(o);load(original);original.attach_backing(medium);original.run(8);held_read(original);
 original.schedule({10,"pen",{1,12000,33000,2048,1,0,0},{}});original.snapshot(dir+"/start.snap");
 auto retired_before=original.state().retired;
 original.run(3000);assert(original.state().backing.phase==BackingPhase::Pending&&!original.state().backing.poisoned);
 assert(original.state().retired>retired_before);
 assert(medium->submissions==1&&medium->polls==3);assert(original.state().pen_accepted==1);assert(original.soc().external_media_busy);
 auto polls=medium->polls;original.snapshot(dir+"/pending.snap");assert(medium->polls==polls&&medium->submissions==1);Machine pending(opts(dir,"pending-fork"));pending.restore(dir+"/pending.snap");auto frozen=pending.state().cycle;rejects([&]{pending.run(1);});assert(pending.state().cycle==frozen);rejects([&]{original.restore(dir+"/start.snap");});rejects([&]{original.export_medium(dir+"/pending.medium");});
 medium->released=true;original.run(2000);assert(original.state().backing.completed==1&&original.state().backing.next_id==2);
 assert(!original.soc().external_media_busy);original.snapshot(dir+"/complete.snap");
 auto replay_o=opts(dir,"replay");replay_o.backing_replay_path=dir+"/actual.io";Machine replay(replay_o);replay.restore(dir+"/start.snap");replay.run(5000);replay.snapshot(dir+"/replay.snap");
 assert(bytes(dir+"/complete.snap")==bytes(dir+"/replay.snap"));pending.bind_backing_replay(dir+"/actual.io");pending.run(2000);pending.snapshot(dir+"/pending-replay.snap");assert(bytes(dir+"/complete.snap")==bytes(dir+"/pending-replay.snap"));
 auto reset_o=opts(dir,"reset");reset_o.backing_capture_path=dir+"/reset.io";auto reset_medium=std::make_shared<PendingMedium>();Machine reset(reset_o);load(reset);reset.attach_backing(reset_medium);reset.run(8);held_read(reset);reset.run(500);
 reset.warm_reset(8);reset.run(1500);assert(reset.state().backing.phase==BackingPhase::Pending);
 assert(reset.soc().external_media_busy&&!reset.state().backing.poisoned);assert(reset.state().media_active==0);
 reset_medium->released=true;reset.run(1500);assert(reset.state().backing.completed==1&&!reset.soc().external_media_busy);
 assert(reset.state().overlay.empty());assert(std::all_of(reset.state().ram.begin()+0x2001000,reset.state().ram.begin()+0x2001200,[](uint8_t v){return !v;}));
 std::cout<<"PASS held request raw pen ingress, observational pending snapshot and suspended fork binding, exact timed private replay, reset orphan without DMA\n";
}
