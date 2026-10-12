// SPDX-License-Identifier: Apache-2.0
// Host-only byte I/O boundary. No device, journal or document policy lives here.
#pragma once
#include <cstdint>
#include <vector>

namespace lemma {
enum class BackingKind : uint64_t { Read=0, Write=1, Barrier=2 };
enum class BackingPhase : uint64_t { Idle=0, Pending=1, Completed=2, Cancelled=3 };
constexpr uint64_t BACKING_MAX_TRANSFER=1024*1024;
struct BackingRequest {
 uint64_t id=0, boundary=0, offset=0, length=0;
 BackingKind kind=BackingKind::Read;
 std::vector<uint8_t> bytes;
};
struct BackingOutcome {
 uint64_t transferred=0, error=0;
 // Read: exact returned prefix. Write: exact prefix changed in the backing.
 // Failed barriers confer no durability guarantee and never undo writes.
 std::vector<uint8_t> bytes;
};
struct BackingRecord { BackingRequest request; BackingOutcome outcome; };
struct BackingState {
 uint64_t next_id=1, completed=0, durable_barrier=0, observed_write=0;
 BackingPhase phase=BackingPhase::Idle;
 bool poisoned=false;
};
struct BackingPlatform {
 virtual ~BackingPlatform()=default;
 virtual uint64_t capacity() const=0;
 // Observational snapshot/export read. It neither changes operation IDs nor
 // executes a barrier; it cannot complete or cancel guest device work.
 virtual void passive_read(uint64_t offset,uint8_t*,uint64_t length) const=0;
 virtual BackingOutcome execute(const BackingRequest&)=0;
 // Replay materializes a captured write prefix in a private backing only.
 // It must not contact the original file, network or peer. A replayed barrier
 // establishes local fork persistence, then returns the recorded outcome.
 virtual void apply_recorded(const BackingRequest&,const BackingOutcome&)=0;
};
void validate_backing_request(const BackingRequest&);
void validate_backing_record(const BackingRecord&);
void validate_backing_state(const BackingState&);
bool equal_backing_request(const BackingRequest&,const BackingRequest&);
BackingRequest begin_backing(BackingState&,BackingKind,uint64_t boundary,
                             uint64_t offset,uint64_t length,const uint8_t*bytes=nullptr);
void complete_backing(BackingState&,const BackingRecord&);
// Cancellation is permitted before execution only. An ambiguous execution or
// capture failure poisons the owner; it cannot be retried, advanced or saved.
void cancel_backing(BackingState&,const BackingRequest&);
std::vector<uint8_t> encode_backing_record(const BackingRecord&);
BackingRecord decode_backing_record(const uint8_t*,uint64_t);
}
