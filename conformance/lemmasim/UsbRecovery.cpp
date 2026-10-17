// Host-only raw external ownership fixture. No guest image, journal policy,
// enumeration/configuration or durable Saved claim. Real generated RTL clocks.
#include "machine_runtime.h"
#include <fstream>
#include <iostream>
#include <chrono>
#include <sys/wait.h>
#include <cerrno>
using namespace lemma;
static void need(bool v,const char*s){if(!v)throw std::runtime_error(s);}
static Options opts(const std::string&d,const std::string&n){Options o;o.usb_recovery=true;o.quiet_uart=true;o.uart_path=d+"/"+n+".uart";o.fork_directory=d;o.deadline=120;return o;}
static void text(const std::string&p,const std::string&s){std::ofstream f(p);f<<s;need(bool(f),"fixture write");}
template<class F>static void rejects(Machine&m,const std::string&capture,F f){auto before=m.inspect();auto bytes_before=bytes(capture);bool bad=false;try{f();}catch(const std::runtime_error&){bad=true;}need(bad&&m.inspect()==before&&bytes(capture)==bytes_before,"rejection changed live state/capture");}
static void exact(Machine&m,const std::string&d,const std::string&prefix,const std::string&final,uint64_t until){Machine branch(opts(d,prefix+"-fork"));branch.restore(d+"/"+prefix+".snap");branch.snapshot(d+"/"+prefix+"-restored.snap");need(bytes(d+"/"+prefix+".snap")==bytes(d+"/"+prefix+"-restored.snap"),"restore boundary differs");rejects(branch,d+"/live.raw",[&]{branch.run(1);});rejects(branch,d+"/live.raw",[&]{branch.reconnect_usb(2,3);});branch.bind_usb_replay(d+"/final.tape");rejects(branch,d+"/live.raw",[&]{branch.run(until-branch.state().cycle+1);});branch.run(until-branch.state().cycle);branch.snapshot(d+"/"+prefix+"-suffix.snap");need(bytes(d+"/"+final+".snap")==bytes(d+"/"+prefix+"-suffix.snap"),"complete suffix differs");need(m.state().cycle==until,"fork advanced original");}
int main(int argc,char**argv)try{need(argc==5,"fixture arguments");std::string d=argv[1];auto started=std::chrono::steady_clock::now();{
 auto o=opts(d,"live");o.usb_peer_executable=argv[2];o.usb_peer_arguments={argv[3],d};o.usb_capture_path=d+"/live.raw";o.usb_recovery_binding=argv[4];Machine live(o);
 auto progress=[&]{need(live.state().cycle<95000,"predeclared100k cycle bound");need(std::chrono::steady_clock::now()-started<std::chrono::seconds(170),"component deadline");live.run(1000);};
 while(!live.state().usb_command||live.state().usb_command->frame!="WAIT 100000")progress();
 need(live.state().usb_command->id==2&&live.state().usb_next_id==3,"first command namespace");live.snapshot(d+"/pending.snap");text(d+"/observed-pending","observed real retained request");
 while(!live.state().usb_terminal)progress();need(!live.state().usb_command&&!live.state().usb_connected&&live.state().usb_connection_epoch==1,"terminal ownership");
 live.snapshot(d+"/before-attach.snap");auto first=live.state().cycle;
 rejects(live,d+"/live.raw",[&]{live.reconnect_usb(4,3);});rejects(live,d+"/live.raw",[&]{live.reconnect_usb(2,4);});
 live.reconnect_usb(2,3);need(live.state().cycle==first&&live.state().usb_connection_epoch==2&&live.state().usb_next_id==3&&!live.state().usb_connected&&!live.soc().usb_configured,"attach changed clock/configuration/namespace");
 live.snapshot(d+"/after-attach.snap");live.export_usb_replay(d+"/after-attach-prefix.tape");rejects(live,d+"/live.raw",[&]{live.reconnect_usb(2,3);});
 while(!live.state().usb_command||live.state().usb_command->frame!="RESET 5000000")progress();need(live.state().usb_command->id==4&&live.state().usb_next_id==5&&live.state().usb_connected&&!live.soc().usb_configured,"new process IDs/real reset");
 live.run(5003);need(live.state().cycle<=100000,"total component cycle bound");need(live.state().usb_command&&live.state().usb_command->id==4,"reset must remain in flight");live.snapshot(d+"/final.snap");live.export_usb_replay(d+"/final.tape");auto until=live.state().cycle;
 exact(live,d,"before-attach","final",until);exact(live,d,"after-attach","final",until);exact(live,d,"pending","final",until);
 auto raw=bytes(d+"/live.raw");std::string capture(raw.begin(),raw.end());need(capture.rfind("LMUSBRW3 ",0)==0&&capture.find("USB process disconnected read")!=std::string::npos&&capture.find(" 3 2 ATTACH 3 "+o.usb_recovery_binding+"\n")!=std::string::npos,"actual EOF/attach capture");
 std::cout<<"{\"scope\":\"raw ownership component, no guest recovery or Saved claim\",\"first_attach_cycle\":"<<first<<",\"final_cycle\":"<<until<<",\"connection_epoch\":2,\"next_request\":5,\"exact_full_archive_suffixes\":3,\"real_reset_pending\":true}\n";
 }
 int status=0;need(waitpid(-1,&status,WNOHANG)==-1&&errno==ECHILD,"owned child not reaped");std::cout<<"NATIVE_USB_RECOVERY_PASS actualEOF globalIDs zero-clockattach realresetpending exactthreeforks no-live-fork horizon stale duplicate rejection\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}
