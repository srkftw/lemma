#pragma once
// Host-only process I/O. It never calculates link sequences or device success.
#include <chrono>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace lemma::radio {
struct BLEPeerReply {
 uint64_t request_id=0; // zero is process startup/private restore
 std::string action;
 std::string state; // alias of logical_state for the narrow runtime adapter
 std::string logical_state; // exact accepted STATE ... trailer, no host pointers
 std::string frame;
};
struct BLEPeerOptions {
 std::string executable;
 std::vector<std::string> arguments;
 std::string private_state; // nonempty only for a new privately bound process
 std::chrono::milliseconds timeout{10000};
};
class BLEPeerTransport {
public:
 explicit BLEPeerTransport(const BLEPeerOptions&);
 BLEPeerTransport(std::string executable,std::vector<std::string> arguments,
   std::optional<std::string> private_state=std::nullopt,unsigned timeout_ms=10000);
 ~BLEPeerTransport();
 BLEPeerTransport(const BLEPeerTransport&)=delete;
 BLEPeerTransport& operator=(const BLEPeerTransport&)=delete;
 bool is_ready() const {return phase_==Phase::ready;}
 bool is_pending() const {return phase_==Phase::handshake||phase_==Phase::restore||phase_==Phase::request;}
 bool submit_rx(uint64_t request_id,uint8_t header,const std::vector<uint8_t>& actual_crc_head);
 bool submit_credit(uint64_t request_id);
 bool submit_cancel(uint64_t request_id);
 std::optional<BLEPeerReply> poll(); // captures actual complete response first
 static BLEPeerReply parse_recorded_reply(const std::string& frame); // pure captured-frame admission
 const std::string& cached_state() const {return cached_;} // observational
 const std::string& accepted_state() const {return cached_;}
 const std::string& error_output() const {return errors_;}
 void shutdown(); // cancels only this owned process; no guest/link acknowledgment
private:
 enum class Phase {handshake,restore,ready,request,closed};
 Phase phase_=Phase::closed;
 int descriptor_=-1,error_descriptor_=-1,process_=-1;
 uint64_t request_id_=0;
 std::string output_,input_,cached_,restore_,errors_;
 std::chrono::milliseconds timeout_;
 std::chrono::steady_clock::time_point deadline_;
 bool submit(uint64_t,const std::string&);
 static BLEPeerReply parse(const std::string&);
 static std::string restore_command(const std::string&);
 void flush_output();
};
using BlePeerTransport=BLEPeerTransport;
using BlePeerReply=BLEPeerReply;
}
namespace lemma {
using BlePeerTransport=radio::BLEPeerTransport;
using BlePeerReply=radio::BLEPeerReply;
}
