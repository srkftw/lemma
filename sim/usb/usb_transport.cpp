#include "usb_transport.h"
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <signal.h>
#include <stdexcept>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>
namespace lemma {
namespace {
void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
void external(bool value,const char* text){if(!value)throw UsbTransportFailure(text);}
bool bounded(const std::string& frame){return !frame.empty()&&frame.size()<=160&&frame.find_first_of("\n\r\0",0,3)==std::string::npos;}
}
UsbProcessTransport::UsbProcessTransport(const std::string& executable,const std::vector<std::string>& arguments,unsigned timeout_ms,uint64_t first_request_id):timeout_ms_(timeout_ms),next_(first_request_id),activity_(std::chrono::steady_clock::now()){
 require(first_request_id&&first_request_id!=UINT64_MAX,"USB process request namespace");
 require(!executable.empty()&&executable.size()<=4096&&executable.find('\0')==std::string::npos&&arguments.size()<=32&&timeout_ms>=100&&timeout_ms<=60000,"USB process arguments");
 std::vector<char*> argv;argv.push_back(const_cast<char*>(executable.c_str()));
 for(const auto& value:arguments){require(value.size()<=4096&&value.find('\0')==std::string::npos,"USB process argument bound");argv.push_back(const_cast<char*>(value.c_str()));}
 argv.push_back(nullptr);int pair[2];if(socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0,pair))throw std::runtime_error("USB process socketpair");
 pid_=fork();
 if(pid_==0){setpgid(0,0);close(pair[0]);if(dup2(pair[1],STDIN_FILENO)<0||dup2(pair[1],STDOUT_FILENO)<0)_exit(126);close(pair[1]);execv(executable.c_str(),argv.data());_exit(127);}
 close(pair[1]);if(pid_<0){close(pair[0]);throw std::runtime_error("USB process fork");}
 fd_=pair[0];setpgid(pid_,pid_);
 if(fcntl(fd_,F_SETFL,fcntl(fd_,F_GETFL)|O_NONBLOCK)<0){shutdown();throw std::runtime_error("USB process nonblocking");}
}
UsbProcessTransport::~UsbProcessTransport(){shutdown();}
void UsbProcessTransport::shutdown() noexcept {
 if(fd_>=0){close(fd_);fd_=-1;}
 if(pid_>0){int status=0;if(waitpid(pid_,&status,WNOHANG)==0){kill(-pid_,SIGTERM);for(unsigned i=0;i<100;i++){if(waitpid(pid_,&status,WNOHANG)==pid_){pid_=-1;break;}usleep(1000);}if(pid_>0){kill(-pid_,SIGKILL);while(waitpid(pid_,&status,0)<0&&errno==EINTR){}}}pid_=-1;}
}
void UsbProcessTransport::progress(){
 require(fd_>=0&&pid_>0,"USB process unavailable");
 while(!output_.empty()){
  auto n=send(fd_,output_.data(),output_.size(),MSG_NOSIGNAL);
  if(n<0){if(errno==EINTR)continue;if(errno==EAGAIN||errno==EWOULDBLOCK)break;throw UsbTransportFailure("USB process write errno="+std::to_string(errno));}
  external(n!=0,"USB process disconnected write");output_.erase(0,size_t(n));activity_=std::chrono::steady_clock::now();
 }
 char bytes[162];
 while(true){
  auto n=recv(fd_,bytes,sizeof(bytes),0);
  if(n<0){if(errno==EINTR)continue;if(errno==EAGAIN||errno==EWOULDBLOCK)break;throw UsbTransportFailure("USB process read errno="+std::to_string(errno));}
  external(n!=0,"USB process disconnected read");input_.append(bytes,size_t(n));activity_=std::chrono::steady_clock::now();
  external(input_.size()<=161,"USB process output resource bound");
  if(input_.find('\n')!=std::string::npos)break;
 }
 if(std::chrono::steady_clock::now()-activity_>std::chrono::milliseconds(timeout_ms_))throw UsbTransportFailure("USB process timeout");
}
std::optional<UsbRawCommand> UsbProcessTransport::poll(){
 progress();auto end=input_.find('\n');if(end==std::string::npos)return {};
 require(!outstanding_&&next_!=UINT64_MAX,"USB process output internal ordering");
 external(end+1==input_.size(),"USB process output ordering");
 std::string frame=input_.substr(0,end);external(bounded(frame),"USB process output framing");input_.clear();
 outstanding_=next_++;return UsbRawCommand{outstanding_,std::move(frame)};
}
void UsbProcessTransport::check(){progress();external(!outstanding_||input_.empty(),"USB process unsolicited command while pending");}
void UsbProcessTransport::reply(uint64_t id,const std::string& frame){
 require(outstanding_==id&&id!=0&&output_.empty()&&bounded(frame),"USB process reply ordering/framing");
 output_=frame+'\n';outstanding_=0;activity_=std::chrono::steady_clock::now();progress();
}
}
