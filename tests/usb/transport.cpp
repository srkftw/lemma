#include "usb_transport.h"
#include <cerrno>
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <sys/wait.h>
#include <thread>
using namespace lemma;
static void check(bool p,const char* s){if(!p)throw std::runtime_error(s);}
static UsbRawCommand command(UsbProcessTransport& t){auto end=std::chrono::steady_clock::now()+std::chrono::seconds(2);while(std::chrono::steady_clock::now()<end){if(auto c=t.poll())return *c;std::this_thread::sleep_for(std::chrono::milliseconds(1));}throw std::runtime_error("fixture command timeout");}
int main(int argc,char**argv){try{
 check(argc==3,"transport fixture arguments");
 {UsbProcessTransport t(argv[1],{argv[2],"normal"},1000);check(t.is_pending(),"attached process omitted external state");auto first=command(t);check(first.id==1&&first.frame=="FIRST","actual first frame/identity");bool rejected=false;try{t.reply(2,"ONE");}catch(...){rejected=true;}check(rejected,"wrong identity accepted");t.reply(1,"ONE");auto second=command(t);check(second.id==2&&second.frame=="SECOND","actual ordered second frame");t.reply(2,"TWO");}
 for(const std::string mode:{"oversized","two","nul","stall"}){bool rejected=false;{UsbProcessTransport t(argv[1],{argv[2],mode},100);try{(void)command(t);}catch(...){rejected=true;}}check(rejected,"malformed/unresolved raw process accepted");}
 int status;check(waitpid(-1,&status,WNOHANG)==-1&&errno==ECHILD,"owned raw process not reaped");
 std::cout<<"USB_RAW_TRANSPORT_PASS stable IDs/framing/timeout/reaping/pending-state exclusion\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
