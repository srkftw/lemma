#pragma once
#include <chrono>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>
namespace lemma {
// Raw, bounded, independently running hosted-Lean process boundary. It does
// not parse USB packets, opcodes, receipt state, or guest documents. Machine
// adapters own virtual scheduling and capture each actual command before use.
struct UsbRawCommand { uint64_t id;std::string frame; };
class UsbProcessTransport {
 public:
  UsbProcessTransport(const std::string& executable,const std::vector<std::string>& arguments,unsigned timeout_ms=10000);
  ~UsbProcessTransport();
  UsbProcessTransport(const UsbProcessTransport&)=delete;
  UsbProcessTransport& operator=(const UsbProcessTransport&)=delete;
  std::optional<UsbRawCommand> poll();
  void reply(uint64_t id,const std::string& frame);
  // This first adapter does not export the Lean host's complete logical state.
  // A live attachment is therefore unresolved external state for snapshots,
  // including the interval between a raw reply and the next captured command.
  bool is_pending() const{return fd_>=0;}
  void shutdown() noexcept;
 private:
  void progress();
  int fd_=-1,pid_=-1;
  unsigned timeout_ms_;
  uint64_t next_=1,outstanding_=0;
  std::string input_,output_;
  std::chrono::steady_clock::time_point activity_;
};
}
