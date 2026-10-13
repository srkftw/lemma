#include "ble_peer_transport.h"
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <iomanip>
#include <signal.h>
#include <sstream>
#include <stdexcept>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

namespace lemma::radio {
namespace {
void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
uint64_t decimal(const std::string& text){
 require(!text.empty()&&(text.size()==1||text[0]!='0'),"noncanonical peer number");uint64_t value=0;
 for(char c:text){require(c>='0'&&c<='9',"invalid peer number");unsigned digit=unsigned(c-'0');
  require(value<=(UINT64_MAX-digit)/10,"overflowed peer number");value=value*10+digit;}
 return value;
}
std::vector<std::string> words(const std::string& text){
 std::vector<std::string> result;std::istringstream input(text);std::string word;
 while(input>>word)result.push_back(word);
 std::string normalized;
 for(const auto& value:result){if(!normalized.empty())normalized+=' ';normalized+=value;}
 require(normalized==text,"noncanonical peer fields");return result;
}
void validate_state(const std::string& text){
 auto fields=words(text);require(fields.size()==9&&fields[0]=="STATE"&&fields[2]=="ACCEPTED"&&
  fields[4]=="DUPLICATES"&&fields[6]=="PENDING","incomplete peer state");
 const uint64_t state=decimal(fields[1]),accepted=decimal(fields[3]),duplicates=decimal(fields[5]),length=decimal(fields[7]);
 require(state<=0x30f&&accepted<=INT64_MAX&&duplicates<=INT64_MAX&&length<=27,"peer state field exceeds bound");
 const unsigned attempts=unsigned((state>>8)&3);const bool pending=(state&4)!=0,frozen=(state&8)!=0;
 require((state&0x30f)==state&&!(pending&&frozen)&&(bool(attempts)==pending),"malformed peer state bits");
 if(length==0)require(fields[8]=="-","nonempty zero-length peer head");
 else {require(accepted>0&&fields[8].size()==length*2,"peer head size/count differs");
  for(char c:fields[8])require((c>='0'&&c<='9')||(c>='a'&&c<='f'),"invalid opaque peer hex");}
}
}
BLEPeerReply BLEPeerTransport::parse(const std::string& frame){
 require(frame.size()<=256&&frame.find_first_of("\r\n")==std::string::npos,"peer frame exceeds bound");
 const auto split=frame.find(" | ");require(split!=std::string::npos&&frame.find(" | ",split+3)==std::string::npos,"peer frame state trailer missing");
 BLEPeerReply reply;reply.frame=frame;reply.action=frame.substr(0,split);reply.logical_state=frame.substr(split+3);
 validate_state(reply.logical_state);reply.state=reply.logical_state;
 auto fields=words(reply.action);require(!fields.empty(),"empty peer action");
 if(fields[0]=="TX")require(fields.size()==4&&decimal(fields[1])<=255&&fields[2]=="0"&&fields[3]=="-","invalid opaque ACK request");
 else if(fields[0]=="ERROR")require(fields.size()==3&&decimal(fields[1])<=255&&
  (fields[2]=="RESTORE"||fields[2]=="SIZE"||fields[2]=="FORMAT"||fields[2]=="COMMAND"||fields[2]=="COUNTER"||
   fields[2]=="CONTEXT"||fields[2]=="FROZEN"||fields[2]=="HEADER"),"unknown peer error response");
 else require(reply.action=="BLEPEER/2 OPEN_MANUAL_UNAUTHENTICATED_CONTEXT"||reply.action=="RESTORED PRIVATE_CONTEXT"||
  reply.action=="EMPTY_RX"||reply.action=="STATUS"||reply.action=="CREDIT 1","unknown peer response action");
 return reply;
}
std::string BLEPeerTransport::restore_command(const std::string& state){
 validate_state(state);auto fields=words(state);return "RESTORE "+fields[1]+" "+fields[3]+" "+fields[5]+" "+fields[8]+"\n";
}
BLEPeerTransport::BLEPeerTransport(const BLEPeerOptions& options):restore_(options.private_state),timeout_(options.timeout){
 require(!options.executable.empty()&&options.executable.find('\0')==std::string::npos,"missing peer executable");
 require(timeout_.count()>=1&&timeout_.count()<=60000,"invalid peer response timeout");
 if(!restore_.empty())restore_command(restore_); // validate before creating a process
 for(const auto& argument:options.arguments)require(argument.find('\0')==std::string::npos&&argument!="--private-restore","invalid caller peer argument");
 int pair[2],errors[2];if(socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0,pair)<0)throw std::runtime_error("peer socketpair failed");
 if(pipe2(errors,O_CLOEXEC)<0){close(pair[0]);close(pair[1]);throw std::runtime_error("peer error pipe failed");}
 std::vector<std::string> arguments{options.executable};arguments.insert(arguments.end(),options.arguments.begin(),options.arguments.end());
 if(!restore_.empty())arguments.push_back("--private-restore");
 std::vector<char*> argv;
 for(auto& argument:arguments)argv.push_back(argument.data());
 argv.push_back(nullptr);
 process_=fork();if(process_<0){close(pair[0]);close(pair[1]);close(errors[0]);close(errors[1]);throw std::runtime_error("peer fork failed");}
 if(process_==0){setpgid(0,0);dup2(pair[1],STDIN_FILENO);dup2(pair[1],STDOUT_FILENO);dup2(errors[1],STDERR_FILENO);
  close(pair[0]);close(pair[1]);close(errors[0]);close(errors[1]);execv(options.executable.c_str(),argv.data());_exit(127);}
 setpgid(process_,process_);close(pair[1]);close(errors[1]);descriptor_=pair[0];error_descriptor_=errors[0];
 if(fcntl(descriptor_,F_SETFL,fcntl(descriptor_,F_GETFL)|O_NONBLOCK)<0||
    fcntl(error_descriptor_,F_SETFL,fcntl(error_descriptor_,F_GETFL)|O_NONBLOCK)<0){
  shutdown();throw std::runtime_error("actual peer nonblocking setup failed");
 }
 phase_=Phase::handshake;deadline_=std::chrono::steady_clock::now()+timeout_;
}
BLEPeerTransport::BLEPeerTransport(std::string executable,std::vector<std::string> arguments,
 std::optional<std::string> private_state,unsigned timeout_ms):BLEPeerTransport(BLEPeerOptions{
  std::move(executable),std::move(arguments),private_state.value_or(""),std::chrono::milliseconds(timeout_ms)}){}
BLEPeerTransport::~BLEPeerTransport(){shutdown();}
void BLEPeerTransport::flush_output(){
 while(!output_.empty()){
  const auto count=send(descriptor_,output_.data(),output_.size(),MSG_NOSIGNAL);
  if(count>0)output_.erase(0,size_t(count));
  else if(count<0&&(errno==EAGAIN||errno==EWOULDBLOCK||errno==EINTR))return;
  else throw std::runtime_error("actual peer input write failed");
 }
}
bool BLEPeerTransport::submit(uint64_t id,const std::string& command){
 if(!is_ready()||id==0)return false;
 require(command.size()<=256&&command.find_first_of("\r\n")==std::string::npos,"peer command exceeds bound");
 require(input_.empty()&&output_.empty(),"uncaptured peer bytes precede new request");
 request_id_=id;output_=command+'\n';phase_=Phase::request;deadline_=std::chrono::steady_clock::now()+timeout_;flush_output();return true;
}
bool BLEPeerTransport::submit_rx(uint64_t id,uint8_t header,const std::vector<uint8_t>& bytes){
 require(bytes.size()<=27,"actual controller head exceeds27bytes");std::ostringstream command;
 command<<"RX "<<unsigned(header)<<" "<<bytes.size()<<" ";if(bytes.empty())command<<"-";
 else for(uint8_t value:bytes)command<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(value);
 return submit(id,command.str());
}
bool BLEPeerTransport::submit_credit(uint64_t id){return submit(id,"CREDIT");}
bool BLEPeerTransport::submit_cancel(uint64_t id){return submit(id,"CANCEL");}
std::optional<BLEPeerReply> BLEPeerTransport::poll(){
 if(phase_==Phase::closed)return std::nullopt;
 if(is_pending()&&std::chrono::steady_clock::now()>deadline_)throw std::runtime_error("actual peer response timeout");
 flush_output();char buffer[256];
 for(;;){auto count=read(error_descriptor_,buffer,sizeof(buffer));if(count>0){
  require(errors_.size()+size_t(count)<=4096,"peer stderr exceeds bounded capture");errors_.append(buffer,size_t(count));}
  else if(count<0&&errno==EINTR)continue;else break;}
 for(;;){const auto count=recv(descriptor_,buffer,sizeof(buffer),0);
  if(count>0){input_.append(buffer,size_t(count));require(input_.size()<=257,"peer output exceeds bounded frame");}
  else if(count==0)throw std::runtime_error("actual peer disconnected before shutdown");
  else if(errno==EINTR)continue;else if(errno==EAGAIN||errno==EWOULDBLOCK)break;
  else throw std::runtime_error("actual peer output read failed");
 }
 const auto end=input_.find('\n');if(end==std::string::npos)return std::nullopt;
 require(is_pending()&&end+1==input_.size()&&output_.empty(),"unsolicited or multiple peer responses");
 auto reply=parse(input_.substr(0,end));input_.clear();reply.request_id=request_id_;
 if(phase_==Phase::handshake){require(reply.action=="BLEPEER/2 OPEN_MANUAL_UNAUTHENTICATED_CONTEXT"&&
  reply.logical_state=="STATE 0 ACCEPTED 0 DUPLICATES 0 PENDING 0 -","actual peer startup state differs");
  cached_=reply.logical_state;
  if(!restore_.empty()){phase_=Phase::restore;output_=restore_command(restore_);deadline_=std::chrono::steady_clock::now()+timeout_;flush_output();}
  else phase_=Phase::ready;
  reply.action="READY"; // host process readiness only, original frame retained
 }else if(phase_==Phase::restore){require(reply.action=="RESTORED PRIVATE_CONTEXT"&&reply.logical_state==restore_,"actual private peer restore differs");cached_=reply.logical_state;phase_=Phase::ready;reply.action="RESTORED";}
 else {cached_=reply.logical_state;phase_=Phase::ready;}
 return reply;
}
void BLEPeerTransport::shutdown(){
 if(descriptor_>=0){close(descriptor_);descriptor_=-1;}if(error_descriptor_>=0){close(error_descriptor_);error_descriptor_=-1;}
 if(process_>0){kill(-process_,SIGKILL);kill(process_,SIGKILL);while(waitpid(process_,nullptr,0)<0&&errno==EINTR){}process_=-1;}
 phase_=Phase::closed;input_.clear();output_.clear();
}
}
