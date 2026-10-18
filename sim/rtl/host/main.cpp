// SPDX-License-Identifier: Apache-2.0
// Host-only command/presentation adapter around the reusable RTL machine core.
#include "machine_runtime.h"
#include "lemma_silicon_binding.h"
#include "../../companion/backing_peer.h"
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <fcntl.h>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <unistd.h>
using namespace lemma;
static std::string escaped(const std::string&s){std::string out;for(unsigned char c:s){if(c=='"'||c=='\\'){out+='\\';out+=c;}else if(c=='\n')out+="\\n";else if(c=='\r')out+="\\r";else if(c<32)out+=' ';else out+=c;}return out;}
static std::string remaining(std::istringstream&ss){std::string rest;std::getline(ss>>std::ws,rest);if(rest.empty())throw std::runtime_error("missing command argument");return rest;}
static bool command_line(std::istream&in,std::string&line,bool&oversized){line.clear();oversized=false;bool any=false;char c;while(in.get(c)){any=true;if(c=='\n')break;if(line.size()<32768)line.push_back(c);else oversized=true;}return any;}
static void reply(Machine&m){std::cout<<"{\"ok\":true,\"result\":"<<m.inspect()<<"}\n"<<std::flush;}
int main(int argc,char**argv)try{
 Options o;uint64_t cycles=20000000;bool session=false,uart_stdin=false,have_elf=false,have_rom=false;
 PeerOptions peer;
 std::string descriptor_path,medium_path,boot_medium_path,event_path,report_path,snapshot_path,restore_path,usb_replay_path,dump;
 std::vector<std::pair<std::string,std::string>> loads;std::vector<uint8_t>initial;
 for(int i=1;i<argc;i++){std::string a=argv[i];auto val=[&](){if(++i>=argc)throw std::runtime_error("missing value "+a);return std::string(argv[i]);};
  if(a=="--image"){loads.push_back({a,val()});have_elf=true;}else if(a=="--rom"){loads.push_back({a,val()});have_rom=true;}else if(a=="--load")loads.push_back({a,val()});
  else if(a=="--uart-input"){auto b=bytes(val());initial.insert(initial.end(),b.begin(),b.end());}
  else if(a=="--multimodal-pcm-output")o.multimodal_pcm_path=val();else if(a=="--uart-output")o.uart_path=val();else if(a=="--trace")o.trace_path=val();else if(a=="--cycles")cycles=number(val());
  else if(a=="--host-threads"){auto n=number(val());if(n>64)throw std::runtime_error("host thread pool must be0..64");o.host_threads=n;}else if(a=="--trace-limit")o.trace_limit=number(val());else if(a=="--deadline"){auto d=number(val());if(!d||d>7200)throw std::runtime_error("deadline must be1..7200seconds");o.deadline=d;}
  else if(a=="--quiet-uart")o.quiet_uart=true;else if(a=="--uart-stdin")uart_stdin=true;
  else if(a=="--panel-drive-trace")o.drive_trace_path=val();
  else if(a=="--usb-recovery")o.usb_recovery=true;else if(a=="--usb-recovery-binding")o.usb_recovery_binding=val();else if(a=="--usb-peer")o.usb_peer_executable=val();else if(a=="--usb-peer-arg")o.usb_peer_arguments.push_back(val());else if(a=="--usb-capture")o.usb_capture_path=val();else if(a=="--usb-peer-timeout-ms")o.usb_peer_timeout_ms=number(val());else if(a=="--usb-replay")usb_replay_path=val();
  else if(a=="--ble-peer")o.ble_peer_executable=val();else if(a=="--ble-peer-arg")o.ble_peer_arguments.push_back(val());else if(a=="--ble-capture")o.ble_capture_path=val();else if(a=="--ble-wire-trace")o.ble_wire_path=val();else if(a=="--ble-replay")o.ble_replay_path=val();else if(a=="--ble-drop-packets")o.ble_drop_packets=number(val());else if(a=="--ble-peer-timeout-ms")o.ble_peer_timeout_ms=number(val());
  else if(a=="--backing-capture")o.backing_capture_path=val();else if(a=="--backing-replay")o.backing_replay_path=val();
  else if(a=="--boot-medium")boot_medium_path=val();else if(a=="--boot-io-capture")o.boot_capture_path=val();else if(a=="--boot-io-replay")o.boot_replay_path=val();
  else if(a=="--boot-write-limit"){auto v=val();auto first=v.find(':'),past=first==std::string::npos?first:v.find(':',first+1);if(first==std::string::npos||past==std::string::npos||v.find(':',past+1)!=std::string::npos)throw std::runtime_error("boot write limit requires first:past:ceiling");o.boot_write_limit=std::array<uint64_t,3>{number(v.substr(0,first)),number(v.substr(first+1,past-first-1)),number(v.substr(past+1))};}
  else if(a=="--companion-client")peer.client=val();else if(a=="--companion-socket")peer.socket=val();else if(a=="--companion-state")peer.state=val();else if(a=="--companion-writer")peer.writer=val();else if(a=="--companion-helper")peer.helper=val();
  else if(a=="--input-capture")o.input_capture_path=val();else if(a=="--uart-stop-hex"){auto b=hexbytes(val());o.stop_marker=std::string(b.begin(),b.end());}
  else if(a=="--descriptor")descriptor_path=val();else if(a=="--medium")medium_path=val();else if(a=="--events")event_path=val();else if(a=="--fork-directory")o.fork_directory=val();
  else if(a=="--panel-output")o.panel_path=val();else if(a=="--report")report_path=val();else if(a=="--uart-stop")o.stop_marker=val();
  else if(a=="--stop-after-panel")o.stop_panels=number(val());else if(a=="--fail-flush")o.fail_flush=number(val());else if(a=="--observer-cycle")o.observer_cycle=number(val());
  else if(a=="--ram-dump")dump=val();else if(a=="--block-trace")o.block_trace_path=val();
  else if(a=="--memory-latency"){o.memory_latency=number(val());if(o.memory_latency>1024)throw std::runtime_error("memory latency must be0..1024cycles");}
  else if(a=="--session")session=true;else if(a=="--snapshot-out")snapshot_path=val();else if(a=="--restore")restore_path=val();else throw std::runtime_error("unknown argument "+a);
 }
 if(BINDING_BOOT_NV_ENABLED){
  if(have_elf||std::any_of(loads.begin(),loads.end(),[](const auto&row){return row.first!="--rom";}))throw std::runtime_error("product boot accepts immutable ROM only; image and DTB load through real NV transactions");
  if(restore_path.empty()&&(!have_rom||boot_medium_path.empty()))throw std::runtime_error("product cold boot requires --rom and --boot-medium");
  if(!restore_path.empty()&&!boot_medium_path.empty())throw std::runtime_error("restored product machine owns a private boot backing fork");
 }else{
  if((restore_path.empty()&&(!have_elf||!have_rom)))throw std::runtime_error("development boot requires --image and --rom");
  if(!boot_medium_path.empty()||!o.boot_capture_path.empty()||!o.boot_replay_path.empty())throw std::runtime_error("boot-medium options require product profile7");
 }
 if(o.uart_path.empty())throw std::runtime_error("--uart-output required");
 if(o.observer_cycle>cycles&&restore_path.empty())throw std::runtime_error("observer cycle exceeds cycle budget");
 if(!restore_path.empty()&&(!event_path.empty()||!initial.empty()))throw std::runtime_error("restored checkpoint owns input; inject new events after restore");
 if(session&&uart_stdin)throw std::runtime_error("session commands and raw UART stdin need separate streams");if(session)o.quiet_uart=true;
 if(!o.backing_replay_path.empty()&&restore_path.empty()&&!session)throw std::runtime_error("backing replay requires --restore or a session restored before running");
 if(!o.boot_replay_path.empty()&&restore_path.empty()&&!session)throw std::runtime_error("boot replay requires --restore or an isolated session restore before running");
 if(peer.client.empty()&&(!peer.socket.empty()||!peer.state.empty()||!peer.writer.empty()||!peer.helper.empty()))throw std::runtime_error("companion options require --companion-client");
 if(!peer.client.empty()&&(!medium_path.empty()||!restore_path.empty()||!o.backing_replay_path.empty()))throw std::runtime_error("external companion requires a cold machine without local medium/replay; restore makes a private fork");
 if(o.ble_peer_executable.empty()&&!o.ble_peer_arguments.empty())throw std::runtime_error("BLE arguments require --ble-peer");if(!o.ble_replay_path.empty()&&restore_path.empty()&&!session)throw std::runtime_error("BLE replay requires an isolated restore");
 if(!restore_path.empty()&&(!o.usb_peer_executable.empty()||!o.usb_peer_arguments.empty()||!o.usb_capture_path.empty()))throw std::runtime_error("restored USB fork excludes live peer/capture; bind recorded outcomes only");
 if(!usb_replay_path.empty()&&(!BINDING_USB_ENABLED||BINDING_BOOT_NV_ENABLED||restore_path.empty()))throw std::runtime_error("USB recorded outcomes require USB6 --restore");
 Machine m(o);for(auto&[kind,path]:loads){if(kind=="--image")m.load_elf(path);else if(kind=="--rom")m.load_rom(path);else{auto c=path.find(':');if(c==std::string::npos)throw std::runtime_error("--load address:path");auto b=bytes(path.substr(c+1));m.put(number(path.substr(0,c)),b.data(),b.size());}}
 if(!descriptor_path.empty())m.descriptor(descriptor_path);if(!peer.client.empty())(peer.asynchronous=true,m.attach_backing(make_peer_backing(peer)));else if(!medium_path.empty())m.open_medium(medium_path);if(!boot_medium_path.empty())m.open_boot_medium(boot_medium_path);m.schedule_all(events(event_path));m.initial_uart(initial);m.prepare();if(!restore_path.empty())m.restore(restore_path);if(!usb_replay_path.empty())m.bind_usb_replay(usb_replay_path);
 if(session){std::string line;bool oversized;while(command_line(std::cin,line,oversized)){try{if(oversized)throw std::runtime_error("command length exceeds32768bytes");std::istringstream ss(line);std::string cmd;ss>>cmd;if(cmd=="run")m.run(number(remaining(ss)));else if(cmd=="inspect"||cmd=="pause"){}else if(cmd=="inject")m.schedule(parse_event(remaining(ss)));else if(cmd=="snapshot")m.snapshot(remaining(ss));else if(cmd=="restore")m.restore(remaining(ss));else if(cmd=="warm-reset"){std::string amount;ss>>amount;m.warm_reset(amount.empty()?8:number(amount));}else if(cmd=="cold-cycle")m.cold_cycle();else if(cmd=="companion-retry")m.retry_backing();else if(cmd=="ble-outcomes")m.bind_ble_replay(remaining(ss));else if(cmd=="usb-outcomes")m.bind_usb_replay(remaining(ss));else if(cmd=="usb-reconnect"){std::string epoch,next,extra;if(!(ss>>epoch>>next)||ss>>extra)throw std::runtime_error("usb-reconnect requires expected epoch and next request");m.reconnect_usb(number(epoch),number(next));}else if(cmd=="export-usb-replay")m.export_usb_replay(remaining(ss));else if(cmd=="backing-outcomes")m.bind_backing_replay(remaining(ss));else if(cmd=="boot-outcomes")m.bind_boot_replay(remaining(ss));else if(cmd=="panel")m.panel(remaining(ss));else if(cmd=="export-medium")m.export_medium(remaining(ss));else if(cmd=="export-boot-medium")m.export_boot_medium(remaining(ss));else if(cmd=="export-private-medium")m.export_private_medium(remaining(ss));else if(cmd=="destroy"){reply(m);break;}else throw std::runtime_error("unknown session command");reply(m);}catch(const std::exception&e){std::cout<<"{\"ok\":false,\"error\":\""<<escaped(e.what())<<"\"}\n"<<std::flush;}}}
 else if(uart_stdin){int flags=fcntl(STDIN_FILENO,F_GETFL,0);if(flags<0||fcntl(STDIN_FILENO,F_SETFL,flags|O_NONBLOCK)<0)throw std::runtime_error("cannot configure raw UART stdin");auto start=std::chrono::steady_clock::now();auto stop=m.state().cycle+cycles;while(m.state().cycle<stop&&!m.state().finished&&!m.state().stopped){uint8_t b[4096];ssize_t n=read(STDIN_FILENO,b,sizeof(b));if(n>0)m.initial_uart(std::vector<uint8_t>(b,b+n));else if(n<0&&errno!=EAGAIN&&errno!=EWOULDBLOCK&&errno!=EINTR)throw std::runtime_error("raw UART stdin read failed");m.run(std::min<uint64_t>(1024,stop-m.state().cycle));if(std::chrono::steady_clock::now()-start>std::chrono::seconds(o.deadline))throw std::runtime_error("RTL wall deadline exceeded");}}
 else if(cycles){uint64_t stop=m.state().cycle+cycles;if(stop<m.state().cycle)throw std::runtime_error("virtual clock exhausted");while(m.state().cycle<stop&&!m.state().finished&&!m.state().stopped)m.run(std::min<uint64_t>(1000000000,stop-m.state().cycle));}
 if(!snapshot_path.empty())m.snapshot(snapshot_path);
 if(!dump.empty()&&(m.state().finished||m.state().stopped)){auto a=dump.find(':'),b=a==std::string::npos?a:dump.find(':',a+1);if(a==std::string::npos||b==std::string::npos||b+1==dump.size())throw std::runtime_error("--ram-dump address:bytes:path");m.ram_dump(number(dump.substr(0,a)),number(dump.substr(a+1,b-a-1)),dump.substr(b+1));}
 if(!o.panel_path.empty())m.panel(o.panel_path);if(!report_path.empty())m.report(report_path);
 std::cerr<<"\nRTL cycles="<<m.state().cycle<<" retired="<<m.state().retired<<" timer_traps="<<m.state().timer_traps<<" finish=0x"<<std::hex<<m.state().finish<<std::dec<<" observer_stop="<<m.state().stopped<<" block_rows="<<m.state().block_rows<<" block_omitted="<<m.state().block_omitted<<'\n';
 return session?0:m.state().finished?(m.state().finish==0x5555?0:2):m.state().stopped?0:3;
}catch(const std::exception&e){std::cerr<<"RTL adapter: "<<e.what()<<'\n';return 1;}
