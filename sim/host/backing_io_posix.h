// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "backing_io.h"
namespace lemma {
// Does not own the descriptor. Runtime owns locks, private paths and lifetime.
struct PosixBacking : BackingPlatform {
 int fd=-1;
 explicit PosixBacking(int descriptor=-1):fd(descriptor){}
 uint64_t capacity() const override;
 void passive_read(uint64_t,uint8_t*,uint64_t) const override;
 BackingOutcome execute(const BackingRequest&) override;
 void apply_recorded(const BackingRequest&,const BackingOutcome&) override;
};
}
