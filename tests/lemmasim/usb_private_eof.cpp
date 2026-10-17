// Host-only probe of the exact archived raw transport. No guest or USB policy.
#include "usb_transport.h"
#include <chrono>
#include <fstream>
#include <iostream>
#include <signal.h>
#include <stdexcept>
#include <thread>
#include <unistd.h>
#include <vector>
int main(int argc,char**argv){try{
 if(argc!=6)throw std::runtime_error("probe executable socket outbox writer helper");
 std::vector<std::string>args;for(int i=2;i<argc;i++)args.emplace_back(argv[i]);
 lemma::UsbProcessTransport transport(argv[1],args,10000);
 auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(10);
 std::optional<lemma::UsbRawCommand> command;
 while(!command&&std::chrono::steady_clock::now()<deadline){command=transport.poll();std::this_thread::sleep_for(std::chrono::milliseconds(1));}
 if(!command||command->id!=1||command->frame!="USBHOST/2 PACKET_BYTES_DEV")throw std::runtime_error("actual hosted Lean startup request differs");
 std::ifstream children("/proc/self/task/"+std::to_string(getpid())+"/children");int child=0,extra=0;
 if(!(children>>child)||child<=0||(children>>extra))throw std::runtime_error("probe does not own exactly one host child");
 std::cout<<"REQUEST "<<command->id<<" "<<command->frame<<"\nCHILD "<<child<<"\n"<<std::flush;
 // A deliberate digital cable loss: stop only this newly owned private host.
 // Do not reply OPEN, issue a packet, or touch an original process.
 if(kill(-child,SIGTERM))throw std::runtime_error("private host termination failed");
 while(std::chrono::steady_clock::now()<deadline){
  try{transport.check();}catch(const lemma::UsbTransportFailure&e){
   if(std::string(e.what())!="USB process disconnected read")throw;
   std::cout<<"FAULT "<<e.what()<<"\n"<<std::flush;return 0;
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(1));
 }
 throw std::runtime_error("private EOF was not observed within original10s bound");
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
