// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "backing_io.h"
namespace lemma {
// Does not own the descriptor. Runtime owns locks, private paths and lifetime.
struct PosixBacking : BackingPlatform {
private:
 struct WriteLimit { uint64_t first,past,ceiling; };
 std::optional<WriteLimit> write_limit;
public:
 int fd=-1;
 explicit PosixBacking(int descriptor=-1):fd(descriptor){}
 // Laboratory host environment only. Matching live writes use a real scoped
 // RLIMIT_FSIZE; capture/logging and recorded replay run after restoration.
 // Not portable machine state. Admission requires a single-threaded owner.
 void limit_write_span(uint64_t first,uint64_t past,uint64_t ceiling);
 void clear_write_limit() { write_limit.reset(); }
 uint64_t capacity() const override;
 void passive_read(uint64_t,uint8_t*,uint64_t) const override;
 BackingOutcome execute(const BackingRequest&) override;
 void apply_recorded(const BackingRequest&,const BackingOutcome&) override;
};
}
