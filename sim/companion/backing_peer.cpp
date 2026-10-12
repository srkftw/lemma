#include "backing_peer.h"
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <fcntl.h>
#include <poll.h>
#include <sstream>
#include <stdexcept>
#include <sys/syscall.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

namespace lemma {
namespace {
constexpr uint64_t medium_bytes = 268435456;
constexpr uint64_t line_bound = 2 * 1048576 + 128;
std::string hex(const std::vector<uint8_t>& bytes) {
  if (bytes.empty()) return "-";
  static const char digits[] = "0123456789abcdef";
  std::string result;
  result.reserve(bytes.size() * 2);
  for (auto b : bytes) { result.push_back(digits[b >> 4]); result.push_back(digits[b & 15]); }
  return result;
}
std::vector<uint8_t> unhex(const std::string& text) {
  if (text == "-") return {};
  if (text.size() > 2 * 1048576 || text.size() % 2) throw std::runtime_error("peer raw prefix bound");
  auto digit=[](char c)->uint8_t {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    throw std::runtime_error("peer raw prefix encoding");
  };
  std::vector<uint8_t> bytes;
  bytes.reserve(text.size()/2);
  for (size_t i=0; i<text.size(); i+=2) bytes.push_back((digit(text[i])<<4)|digit(text[i+1]));
  return bytes;
}

class PeerBacking final : public BackingPlatform {
  mutable int input_ = -1, output_ = -1;
  pid_t child_ = -1;
  mutable std::string buffered_;
  void stop() noexcept {
    if (input_ >= 0) { close(input_); input_ = -1; }
    if (output_ >= 0) { close(output_); output_ = -1; }
    if (child_ > 0) {
      kill(child_, SIGTERM);
      for (unsigned i=0; i<50; ++i) {
        int status;
        auto result=waitpid(child_, &status, WNOHANG);
        if (result == child_ || (result<0 && errno == ECHILD)) { child_ = -1; break; }
        usleep(10000);
      }
      if (child_ > 0) { kill(child_, SIGKILL); while (waitpid(child_, nullptr, 0)<0 && errno==EINTR) {} child_ = -1; }
    }
  }
  std::string line() const {
    const auto deadline = std::chrono::steady_clock::now()+std::chrono::seconds(8);
    for (;;) {
      auto end=buffered_.find('\n');
      if (end!=std::string::npos) { auto out=buffered_.substr(0,end); buffered_.erase(0,end+1); return out; }
      if (buffered_.size()>line_bound) throw std::runtime_error("peer raw output resource bound");
      auto left=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-std::chrono::steady_clock::now()).count();
      if (left<=0) throw std::runtime_error("peer raw reply timeout; persistence unresolved");
      pollfd fd{output_,POLLIN,0};
      int ready=poll(&fd,1,static_cast<int>(left));
      if (ready<0 && errno==EINTR) continue;
      if (ready<=0) throw std::runtime_error("peer raw reply unavailable; persistence unresolved");
      char data[8192];
      auto n=read(output_,data,sizeof data);
      if (n<0 && errno==EINTR) continue;
      if (n<=0) throw std::runtime_error("hosted Lean client disconnected; persistence unresolved");
      buffered_.append(data,static_cast<size_t>(n));
    }
  }
  BackingOutcome exchange(const BackingRequest& request) const {
    auto message=std::to_string(static_cast<unsigned>(request.kind))+" "+std::to_string(request.id)+" "+
      std::to_string(request.boundary)+" "+std::to_string(request.offset)+" "+std::to_string(request.length)+" "+hex(request.bytes)+"\n";
    size_t sent=0;
    while (sent<message.size()) {
      auto n=send(input_,message.data()+sent,message.size()-sent,MSG_NOSIGNAL);
      if (n<0 && errno==EINTR) continue;
      if (n<=0) throw std::runtime_error("hosted Lean client raw request failure");
      sent+=static_cast<size_t>(n);
    }
    auto raw=line();
    if (raw=="PENDING") throw std::runtime_error("companion persistence unresolved; durable outbox must reconcile before restart");
    std::istringstream response(raw);
    BackingOutcome out;
    std::string data,extra;
    if (!(response>>out.transferred>>out.error>>data) || response>>extra) throw std::runtime_error("invalid hosted Lean raw outcome");
    out.bytes=unhex(data);
    validate_backing_record({request,out});
    return out;
  }
public:
  explicit PeerBacking(const PeerOptions& options) {
    if (options.client.empty() || options.socket.empty() || options.state.empty() || options.writer.empty() || options.helper.empty())
      throw std::runtime_error("companion raw adapter requires all prepared client paths");
    int to_child[2],from_child[2];
    if (socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0,to_child)<0) throw std::runtime_error("companion request socket pair");
    if (socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0,from_child)<0) { close(to_child[0]);close(to_child[1]);throw std::runtime_error("companion outcome socket pair"); }
    child_=fork();
    if (child_<0) { for (int fd:to_child) close(fd);for (int fd:from_child) close(fd);throw std::runtime_error("companion hosted client fork"); }
    if (!child_) {
      if (dup2(to_child[0],STDIN_FILENO)<0 || dup2(from_child[1],STDOUT_FILENO)<0) _exit(126);
#ifdef SYS_close_range
      if (syscall(SYS_close_range,3,~0u,0)<0)
#endif
        for (int fd=3;fd<65536;++fd) close(fd);
      execl(options.client.c_str(),options.client.c_str(),options.socket.c_str(),options.state.c_str(),options.writer.c_str(),options.helper.c_str(),static_cast<char*>(nullptr));
      _exit(127);
    }
    close(to_child[0]);close(from_child[1]); input_=to_child[1];output_=from_child[0];
    try {
      std::istringstream status(line());
      std::string ready,writer,sequence,extra;
      uint64_t capacity;
      if (!(status>>ready>>capacity>>writer>>sequence) || status>>extra || ready!="READY" || capacity!=medium_bytes || writer!=options.writer)
        throw std::runtime_error("hosted Lean protocol did not reach backing Ready");
    } catch (...) { stop();throw; }
  }
  ~PeerBacking() override { stop(); }
  uint64_t capacity() const override { return medium_bytes; }
  void passive_read(uint64_t offset,uint8_t* bytes,uint64_t length) const override {
    if (offset%512 || length%512 || offset>medium_bytes || length>medium_bytes-offset)
      throw std::runtime_error("peer passive read bounds");
    while (length) {
      auto n=std::min<uint64_t>(length,1048576);
      auto out=exchange({1,0,offset,n,BackingKind::Read,{}});
      if (out.error || out.transferred!=n) throw std::runtime_error("peer passive read failed");
      std::copy(out.bytes.begin(),out.bytes.end(),bytes);offset+=n;bytes+=n;length-=n;
    }
  }
  BackingOutcome execute(const BackingRequest& request) override {
    validate_backing_request(request);
    if (request.offset>medium_bytes || request.length>medium_bytes-request.offset) throw std::runtime_error("peer request medium bounds");
    return exchange(request);
  }
  void apply_recorded(const BackingRequest&,const BackingOutcome&) override {
    throw std::runtime_error("external companion cannot be a replay fork; restore privately first");
  }
};
}
std::shared_ptr<BackingPlatform> make_peer_backing(const PeerOptions& options) { return std::make_shared<PeerBacking>(options); }
}
