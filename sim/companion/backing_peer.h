#pragma once
#include "../host/backing_io.h"
#include <memory>
#include <string>

namespace lemma {
// Host raw pipe adapter only. Framing, outbox, retry and receipt policy execute
// in the separately compiled hosted-Lean client, never in the RV64 image.
struct PeerOptions {
  std::string client, socket, state, writer, helper;
  bool asynchronous=false;
};
std::shared_ptr<BackingPlatform> make_peer_backing(const PeerOptions& options);
}
