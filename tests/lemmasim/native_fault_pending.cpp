// SPDX-License-Identifier: Apache-2.0
// Actual POSIX failures withheld at an external completion boundary. The host
// supplies bytes/errors only; the literal controller exposes them to RTL.
#include "machine_runtime.h"
#include "../../sim/host/backing_io_posix.h"
#include "Vlemma_soc___024root.h"
#include <algorithm>
#include <cassert>
#include <csignal>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <sys/resource.h>
#include <unistd.h>
using namespace lemma;
struct Deferred final:BackingPlatform {
 int fd;bool released=false,partial=false;unsigned polls=0;mutable unsigned reads=0;std::optional<BackingOutcome> result;BackingRequest request;PosixBacking raw;
 explicit Deferred(int f):fd(f),raw(f){}
 ~Deferred(){if(fd>=0)close(fd);}
 uint64_t capacity()const override{return raw.capacity();}
 void passive_read(uint64_t p,uint8_t*b,uint64_t n)const override{reads++;raw.passive_read(p,b,n);}
 BackingOutcome execute(const BackingRequest&)override{throw std::runtime_error("unexpected synchronous bypass");}
 void submit(const BackingRequest&r)override{request=r;assert(!result);if(partial){rlimit old{};assert(!getrlimit(RLIMIT_FSIZE,&old));auto limit=old;limit.rlim_cur=1538;assert(!setrlimit(RLIMIT_FSIZE,&limit));result=raw.execute(r);assert(!setrlimit(RLIMIT_FSIZE,&old));}else result=raw.execute(r);}
 std::optional<BackingOutcome>poll()override{polls++;if(!released)return std::nullopt;auto o=result;result.reset();return o;}
 void apply_recorded(const BackingRequest&,const BackingOutcome&)override{throw std::runtime_error("fork contacted original failed medium");}
};
void held(Machine&m,uint32_t kind){auto*r=m.soc().rootp;r->lemma_soc__DOT__blockdev__DOT__state=8;r->lemma_soc__DOT__blockdev__DOT__kind=kind;r->lemma_soc__DOT__blockdev__DOT__sector=3;r->lemma_soc__DOT__blockdev__DOT__data_address=0x82001000;r->lemma_soc__DOT__blockdev__DOT__status_address=0x82002000;for(unsigned i=0;i<128;i++)r->lemma_soc__DOT__blockdev__DOT__sector_buffer[i]=0x91919191;}
Options options(const std::string&d,const std::string&n){Options o;o.quiet_uart=true;o.deadline=30;o.uart_path=d+"/"+n+".uart";o.fork_directory=d;return o;}
int main(int argc,char**argv){assert(argc==7);std::signal(SIGXFSZ,SIG_IGN);std::string dir=argv[1];
 auto load=[&](Machine&m){m.load_elf(argv[2]);m.load_rom(argv[3]);auto dtb=bytes(argv[4]);m.put(number(argv[6]),dtb.data(),dtb.size());m.descriptor(argv[5]);};
 for(bool partial:{true,false}){
  std::string name=partial?"partial":"barrier",path=dir+"/"+name+".raw";int fd=open(path.c_str(),O_RDWR|O_CREAT|O_EXCL,0600);assert(fd>=0&&!ftruncate(fd,268435456));auto platform=std::make_shared<Deferred>(fd);auto o=options(dir,name);o.backing_capture_path=dir+"/"+name+".io";Machine original(o);load(original);original.attach_backing(platform);original.run(8);
  if(partial){platform->partial=true;held(original,1);original.run(20);held(original,4);}else{assert(!close(fd));held(original,4);}
  original.run(1000);assert(original.state().backing_pending&&platform->result&&platform->result->error);if(partial){assert(platform->result->transferred==2);uint8_t b[4]{};assert(pread(fd,b,4,1536)==4&&b[0]==0x91&&b[1]==0x91&&!b[2]&&!b[3]);assert(original.state().accepted_medium.empty());}else assert(platform->result->transferred==0);
  auto polls=platform->polls,reads=platform->reads;auto cycle=original.state().cycle;original.snapshot(dir+"/"+name+"-pending.snap");assert(platform->polls==polls&&platform->reads==reads&&original.state().cycle==cycle);
  Machine fork(options(dir,name+"-fork"));fork.restore(dir+"/"+name+"-pending.snap");bool rejected=false;try{fork.run(1);}catch(const std::runtime_error&){rejected=true;}assert(rejected&&fork.state().cycle==cycle);
  platform->released=true;original.run(2000);assert(original.state().backing.completed==1&&!original.state().backing.durable_barrier);if(partial){assert(original.state().accepted_medium.at(3)[0]==0x91&&original.state().accepted_medium.at(3)[1]==0x91&&!original.state().accepted_medium.at(3)[2]);assert(original.state().overlay.size()==1);}original.snapshot(dir+"/"+name+"-complete.snap");
  fork.bind_backing_replay(dir+"/"+name+".io");fork.run(2000);fork.snapshot(dir+"/"+name+"-replay.snap");assert(bytes(dir+"/"+name+"-complete.snap")==bytes(dir+"/"+name+"-replay.snap"));
  if(partial){fork.export_medium(dir+"/partial-fork.raw");int f=open((dir+"/partial-fork.raw").c_str(),O_RDONLY);uint8_t b[4]{};assert(f>=0&&pread(f,b,4,1536)==4&&b[0]==0x91&&b[1]==0x91&&!b[2]&&!b[3]);close(f);}else platform->fd=-1;
 }
 std::cout<<"PASS actual partial pwrite failure and actual fsync EBADF Pending snapshots, isolated exact native suffixes and retained unacknowledged prefix\n";
}
