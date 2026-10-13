// SPDX-License-Identifier: Apache-2.0
// Literal BootNV circuit state + actual POSIX backing errors. This fixture
// qualifies external ownership/continuation, not ROM or guest-driver execution.
#include "machine_runtime.h"
#include "../../sim/host/backing_io_posix.h"
#include "Vlemma_soc___024root.h"
#include <cassert>
#include <algorithm>
#include <csignal>
#include <chrono>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <sys/resource.h>
#include <unistd.h>
using namespace lemma;
struct Deferred final:BackingPlatform {
 int fd;PosixBacking raw;bool released=false,partial=false;unsigned reads=0,polls=0,submissions=0;std::optional<BackingOutcome>outcome;
 explicit Deferred(int f):fd(f),raw(f){}
 ~Deferred(){if(fd>=0)close(fd);}
 uint64_t capacity()const override{return raw.capacity();}
 void passive_read(uint64_t a,uint8_t*b,uint64_t n)const override{const_cast<Deferred*>(this)->reads++;raw.passive_read(a,b,n);}
 BackingOutcome execute(const BackingRequest&)override{throw std::runtime_error("unexpected direct execution");}
 void submit(const BackingRequest&r)override{assert(!outcome);submissions++;if(partial){rlimit old{};assert(!getrlimit(RLIMIT_FSIZE,&old));auto limit=old;limit.rlim_cur=1538;assert(!setrlimit(RLIMIT_FSIZE,&limit));outcome=raw.execute(r);assert(!setrlimit(RLIMIT_FSIZE,&old));}else outcome=raw.execute(r);}
 std::optional<BackingOutcome>poll()override{polls++;if(!released)return std::nullopt;auto result=outcome;outcome.reset();return result;}
 void apply_recorded(const BackingRequest&,const BackingOutcome&)override{throw std::runtime_error("fork contacted original boot medium");}
};
Options options(const std::string&d,const std::string&n){Options o;o.quiet_uart=true;o.uart_path=d+"/"+n+".uart";o.fork_directory=d;return o;}
template<class F>void rejects(F f){bool rejected=false;try{f();}catch(const std::runtime_error&){rejected=true;}assert(rejected);}
void held(Machine&m,unsigned kind){auto*r=m.soc().rootp;r->lemma_soc__DOT__product_boot_medium__DOT__boot_store__DOT__state=1;r->lemma_soc__DOT__product_boot_medium__DOT__boot_store__DOT__kind=kind;r->lemma_soc__DOT__product_boot_medium__DOT__boot_store__DOT__active_sector=3;r->lemma_soc__DOT__product_boot_medium__DOT__boot_store__DOT__request_id=1;r->lemma_soc__DOT__product_boot_medium__DOT__boot_store__DOT__active_origin=m.state().boot_reset_origin;for(unsigned i=0;i<128;i++)r->lemma_soc__DOT__product_boot_medium__DOT__boot_store__DOT__buffer_data[i]=0x91919191;m.soc().eval();}
int main(int argc,char**argv){assert(argc==2);std::signal(SIGXFSZ,SIG_IGN);std::string dir=argv[1];
 for(unsigned scenario=0;scenario<3;scenario++){
  std::string name=scenario==0?"partial-cancel":scenario==1?"barrier-error":"reset-orphan";std::string path=dir+"/"+name+".raw";int fd=open(path.c_str(),O_RDWR|O_CREAT|O_EXCL,0600);assert(fd>=0&&!ftruncate(fd,65544ULL*512));auto platform=std::make_shared<Deferred>(fd);auto o=options(dir,name);o.boot_capture_path=dir+"/"+name+".nvio";Machine original(o);auto initialized=std::chrono::steady_clock::now();original.attach_boot_backing(platform);double initialization_seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-initialized).count();original.run(8);assert(original.state().boot_pages.empty());rejects([&]{uint8_t b=1;original.put(0x80000000,&b,1);});
  platform->partial=scenario==0;held(original,scenario==1?3:2);if(scenario==1){assert(!close(fd));platform->fd=-1;}original.run(1000);assert(original.state().boot_pending&&platform->submissions==1&&platform->outcome);if(scenario==0){assert(platform->outcome->error&&platform->outcome->transferred==2);uint8_t b[4]{};assert(pread(fd,b,4,1536)==4&&b[0]==0x91&&b[1]==0x91&&!b[2]&&!b[3]);assert(original.state().accepted_boot_medium.empty());}
  if(scenario==0)original.soc().rootp->lemma_soc__DOT__product_boot_medium__DOT__boot_store__DOT__cancel_pending=1;
  if(scenario==2){original.warm_reset(8);original.run(8);assert(original.state().boot_orphan&&original.state().boot_reset_origin==2);}
  auto cycle=original.state().cycle;auto reads=platform->reads,polls=platform->polls;auto saved=std::chrono::steady_clock::now();original.snapshot(dir+"/"+name+"-pending.snap");double snapshot_seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-saved).count();assert(original.state().cycle==cycle&&platform->reads==reads&&platform->polls==polls&&platform->submissions==1);
  Machine fork(options(dir,name+"-fork"));fork.restore(dir+"/"+name+"-pending.snap");assert(fork.state().boot_pending&&equal_backing_request(*fork.state().boot_pending,*original.state().boot_pending));fork.snapshot(dir+"/"+name+"-fork-pending.snap");assert(bytes(dir+"/"+name+"-pending.snap")==bytes(dir+"/"+name+"-fork-pending.snap"));rejects([&]{fork.run(1);});assert(fork.state().cycle==cycle);rejects([&]{fork.bind_boot_replay(dir+"/"+name+".nvio");});assert(fork.state().cycle==cycle);
  platform->released=true;original.run(2000);assert(original.state().boot_backing.completed==1&&!original.state().boot_pending&&platform->submissions==1);if(scenario<2)assert(original.state().boot_backing.durable_barrier==0);if(scenario==0){auto*r=original.soc().rootp;assert(r->lemma_soc__DOT__product_boot_medium__DOT__boot_store__DOT__state==3&&r->lemma_soc__DOT__product_boot_medium__DOT__boot_store__DOT__returned_bytes==2);assert(original.state().accepted_boot_medium.at(3)[0]==0x91&&original.state().accepted_boot_medium.at(3)[1]==0x91&&!original.state().accepted_boot_medium.at(3)[2]);}
  if(scenario==2){assert(original.state().boot_orphan==0&&original.soc().rootp->lemma_soc__DOT__product_boot_medium__DOT__boot_store__DOT__state==0);assert(original.state().accepted_boot_medium.at(3)[0]==0x91);}
  original.snapshot(dir+"/"+name+"-complete.snap");auto wrong=bytes(dir+"/"+name+".nvio");std::copy_n("LMIOLOG2",8,wrong.begin());{std::ofstream stream(dir+"/"+name+"-wrong-namespace.io",std::ios::binary);stream.write(reinterpret_cast<const char*>(wrong.data()),wrong.size());}rejects([&]{fork.bind_boot_replay(dir+"/"+name+"-wrong-namespace.io");});assert(fork.state().cycle==cycle&&fork.state().boot_backing.completed==0);fork.bind_boot_replay(dir+"/"+name+".nvio");fork.run(2000);fork.snapshot(dir+"/"+name+"-replay.snap");assert(bytes(dir+"/"+name+"-complete.snap")==bytes(dir+"/"+name+"-replay.snap"));assert(platform->submissions==1&&platform->reads==reads);
  fork.export_boot_medium(dir+"/"+name+"-fork.raw");rlimit limit{};assert(!getrlimit(RLIMIT_FSIZE,&limit));rusage usage{};assert(!getrusage(RUSAGE_SELF,&usage));std::cout<<"{\"case\":\""<<name<<"\",\"initialization_seconds\":"<<initialization_seconds<<",\"snapshot_seconds\":"<<snapshot_seconds<<",\"peak_native_rss_kib\":"<<usage.ru_maxrss<<",\"snapshot_cycle\":"<<cycle<<",\"final_cycle\":"<<original.state().cycle<<",\"boot_submissions\":"<<platform->submissions<<",\"initial_passive_reads\":"<<reads<<"}\n";
 }
 {Machine loss(options(dir,"loss"));loss.run(8);auto&literal=const_cast<State&>(loss.state());literal.ram[0]=0x5a;literal.ram[0x7e00000]=0x6b;loss.schedule({loss.state().cycle,"brownout",{1},{}});loss.run(16);assert(!loss.state().ram[0]&&!loss.state().ram[0x7e00000]&&loss.state().boot_pages.empty());}
 std::cout<<"PASS literal BootNV actual partial pwrite/cancel, fsync EBADF, reset orphan, observational Pending snapshots, isolated exact native suffixes\n";
}
