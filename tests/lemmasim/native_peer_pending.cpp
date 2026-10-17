// SPDX-License-Identifier: Apache-2.0
// Real hosted-Lean opaque peer + literal RTL controller state. Guest RV64
// instructions execute; this fixture does not claim Ready/guest-driver use.
#include "machine_runtime.h"
#include "../../sim/companion/backing_peer.h"
#include "Vlemma_soc___024root.h"
#include <cassert>
#include <chrono>
#include <fstream>
#include <iostream>
#include <thread>
using namespace lemma;
using Clock=std::chrono::steady_clock;
struct Observed final:BackingPlatform {
 std::shared_ptr<BackingPlatform> peer;mutable uint64_t reads=0;uint64_t submits=0,polls=0;
 explicit Observed(std::shared_ptr<BackingPlatform> p):peer(std::move(p)){}
 uint64_t capacity()const override{return peer->capacity();}
 void passive_read(uint64_t p,uint8_t*b,uint64_t n)const override{reads++;peer->passive_read(p,b,n);}
 BackingOutcome execute(const BackingRequest&r)override{return peer->execute(r);}
 void submit(const BackingRequest&r)override{submits++;peer->submit(r);}
 std::optional<BackingOutcome>poll()override{polls++;return peer->poll();}
 bool retry_ready()const override{return peer->retry_ready();}
 bool retry_pending()override{return peer->retry_pending();}
 void apply_recorded(const BackingRequest&,const BackingOutcome&)override{throw std::runtime_error("fork contacted original peer");}
};
template<class F>void rejects(F f){bool no=false;try{f();}catch(const std::runtime_error&){no=true;}assert(no);}
Options options(const std::string&dir,const std::string&name){Options o;o.quiet_uart=true;o.deadline=30;o.uart_path=dir+"/"+name+".uart";o.fork_directory=dir;return o;}
void held(Machine&m,uint32_t kind){auto*r=m.soc().rootp;r->lemma_soc__DOT__blockdev__DOT__state=8;r->lemma_soc__DOT__blockdev__DOT__kind=kind;r->lemma_soc__DOT__blockdev__DOT__sector=3;r->lemma_soc__DOT__blockdev__DOT__data_address=0x82001000;r->lemma_soc__DOT__blockdev__DOT__status_address=0x82002000;for(unsigned i=0;i<128;i++)r->lemma_soc__DOT__blockdev__DOT__sector_buffer[i]=0x83838383;}
void signal(const char*name){std::cout<<name<<std::endl;std::string command;assert(std::getline(std::cin,command)&&command=="continue");}
int main(int argc,char**argv){assert(argc==11);std::string dir=argv[1];auto o=options(dir,"original");o.backing_capture_path=dir+"/actual.io";
 auto peer=std::make_shared<Observed>(make_peer_backing({argv[7],argv[8],argv[9],"17",argv[10],true}));Machine m(o);m.load_elf(argv[2]);m.load_rom(argv[3]);auto dtb=bytes(argv[4]);m.put(number(argv[6]),dtb.data(),dtb.size());m.descriptor(argv[5]);
 auto initialized=Clock::now();m.attach_backing(peer);double initialize_seconds=std::chrono::duration<double>(Clock::now()-initialized).count();m.run(8);signal("INITIALIZED");
 held(m,1);m.run(20);assert(m.state().overlay.size()==1&&peer->submits==0);held(m,4);
 auto start=Clock::now();while(!m.state().backing_retry_ready){m.run(100);std::this_thread::sleep_for(std::chrono::milliseconds(1));assert(Clock::now()-start<std::chrono::seconds(15));}
 assert(m.state().backing_pending&&m.state().backing_pending->kind==BackingKind::Barrier&&m.state().backing.completed==1&&m.state().backing.durable_barrier==0);assert(m.state().accepted_medium.at(3)[0]==0x83);assert(peer->submits==2);
 m.schedule({m.state().cycle+1000,"pen",{1,12000,33000,2048,1,0,0},{}});
 auto read_count=peer->reads,poll_count=peer->polls,submit_count=peer->submits,cycle=m.state().cycle;
 auto saved=Clock::now();m.snapshot(dir+"/pending.snap");double snapshot_seconds=std::chrono::duration<double>(Clock::now()-saved).count();assert(peer->reads==read_count&&peer->polls==poll_count&&peer->submits==submit_count&&m.state().cycle==cycle);
 Machine fork(options(dir,"fork"));fork.restore(dir+"/pending.snap");assert(fork.state().backing_pending&&equal_backing_request(*fork.state().backing_pending,*m.state().backing_pending));assert(fork.state().backing_poll_cycle==m.state().backing_poll_cycle&&fork.state().backing_retry_ready==1);
 fork.snapshot(dir+"/fork-pending.snap");assert(bytes(dir+"/pending.snap")==bytes(dir+"/fork-pending.snap"));rejects([&]{fork.run(1);});assert(fork.state().cycle==cycle);rejects([&]{fork.bind_backing_replay(dir+"/actual.io");});assert(fork.state().cycle==cycle);
 signal("PENDING_SNAPSHOT");m.retry_backing();start=Clock::now();while(m.state().backing.phase==BackingPhase::Pending){m.run(100);std::this_thread::sleep_for(std::chrono::milliseconds(1));assert(Clock::now()-start<std::chrono::seconds(15));}
 m.run(2000);assert(m.state().backing.completed==2&&m.state().backing.durable_barrier==2&&m.state().pen_accepted==1);m.snapshot(dir+"/complete.snap");auto target=m.state().cycle;
 signal("COMPLETED"); // The observer stops the peer before isolated suffix execution.
 auto log=bytes(dir+"/actual.io");log[8]^=1;{std::ofstream f(dir+"/bad.io",std::ios::binary);f.write(reinterpret_cast<char*>(log.data()),log.size());}rejects([&]{fork.bind_backing_replay(dir+"/bad.io");});assert(fork.state().cycle==cycle);fork.snapshot(dir+"/rejected.snap");assert(bytes(dir+"/pending.snap")==bytes(dir+"/rejected.snap"));
 fork.bind_backing_replay(dir+"/actual.io");fork.retry_backing();fork.run(target-cycle);fork.snapshot(dir+"/replay.snap");assert(bytes(dir+"/complete.snap")==bytes(dir+"/replay.snap"));assert(peer->submits==submit_count&&peer->reads==read_count);
 std::cout<<"PASS real peer lost-ACK Pending snapshot, observational request ownership, suspended missing-tape fork, isolated exact RTL suffix\n";
 std::cout<<"{\"initialize_seconds\":"<<initialize_seconds<<",\"snapshot_seconds\":"<<snapshot_seconds<<",\"snapshot_cycle\":"<<cycle<<",\"final_cycle\":"<<target<<",\"passive_reads\":"<<read_count<<",\"submissions\":"<<submit_count<<",\"retired\":"<<m.state().retired<<",\"accepted_sectors\":"<<m.state().accepted_medium.size()<<"}\n";
}
