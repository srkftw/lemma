// SPDX-License-Identifier: Apache-2.0
// Actual external process faults + literal machine-controller responsiveness.
// This fixture does not execute a guest notebook or perform a storage commit.
#include "machine_runtime.h"
#include "Vlemma_soc___024root.h"
#include <chrono>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <sstream>
#include <sys/wait.h>
#include <cerrno>
using namespace lemma;
static void require(bool p,const char*s){if(!p)throw std::runtime_error(s);}
static std::string contents(const std::string&p){auto b=bytes(p);return {b.begin(),b.end()};}
static bool seen(const std::string&p,const std::string&s){return contents(p).find(s)!=std::string::npos;}
static bool failed(const std::string&p){std::istringstream input(contents(p));std::string line;while(std::getline(input,line)){std::istringstream row(line);uint64_t cycle,tag,id;if(row>>cycle>>tag>>id)if(tag==2)return true;}return false;}
int main(int argc,char**argv){try{
 require(argc==4,"native USB disconnect fixture arguments");std::string dir=argv[1];
 for(const std::string mode:{"closed","pending-exit","reset"}){
  Options o;o.quiet_uart=true;o.uart_path=dir+"/"+mode+".uart";o.usb_capture_path=dir+"/"+mode+".raw";o.usb_peer_executable=argv[2];o.usb_peer_arguments={argv[3],mode};o.usb_peer_timeout_ms=60000;
  Machine m(o);auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(45);bool reset=false;
  while(!failed(o.usb_capture_path)){
   require(std::chrono::steady_clock::now()<deadline,"external failure was not observed within fixture bound");m.run(1000);
   if(mode=="reset"&&!reset&&seen(o.usb_capture_path," RECV\n")){require(m.soc().usb_connected,"root reset did not attach actual controller");m.warm_reset(8);reset=true;}
   std::this_thread::sleep_for(std::chrono::microseconds(50));
  }
  auto cycle=m.state().cycle;require(!m.soc().usb_connected&&!m.soc().usb_configured,"external failure left digital attach/configuration visible");
  require(contents(o.usb_capture_path).rfind("LMUSBRW2 ",0)==0,"failure-capable capture did not identify its wire contract");
  if(mode=="reset")require(reset&&seen(o.usb_capture_path,"DOMAIN_RESET"),"reset did not capture owner cancellation");
  else require(seen(o.usb_capture_path,"USB process disconnected read"),"actual EOF reason not captured");
  m.schedule({cycle+16,"pen",{1,12345,34567,1024,1,0,0},{}});m.run(2000);
  require(m.state().cycle==cycle+2000,"external failure stopped virtual scheduling");
  require(m.soc().rootp->lemma_soc__DOT__pen__DOT__count==1,"raw pen controller did not accept independent input after failure");
  bool rejected=false;try{m.snapshot(dir+"/"+mode+".snap");}catch(const std::runtime_error&){rejected=true;}
  require(rejected,"unserialized external USB policy acquired checkpoint admission");
  std::cout<<"{\"case\":\""<<mode<<"\",\"failure_cycle\":"<<cycle<<",\"suffix_cycles\":2000,\"actual_pen_fifo_entries\":1}\n";
 }
 int status;require(waitpid(-1,&status,WNOHANG)==-1&&errno==ECHILD,"owned USB external process was not reaped");
 std::cout<<"PASS actual USB EOF/pending-RECV/domain-reset capture, controller disconnect, raw pen continuation and unresolved-snapshot rejection\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
