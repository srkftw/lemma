# Development image authentication1

`lemmasim-silicon-public-development-auth-boot` is an explicit additive ROM
software configuration on the existing `lemma-silicon-dev/0.10.0` machine.
It uses the unchanged `core0-boot-v0.1` checked lowering, RAM regions, reset
boundary, BootNV controller, Product10 image format and transactional metadata.
The original integrity-only ROM remains available. Running image bytes enter
through guest PIO transactions; the adapter loads only immutable ROM contents.

This configuration intentionally uses the **public development key** `00..1f`
and key ID `0x4445560000000001`. It tests real HMAC enforcement and recovery.
Anyone knowing this published key can author an accepted image. It provides
no production owner identity, confidential key storage, entropy provisioning,
immutable anti-rollback, side-channel resistance or cryptographic certification.
All commands require `--public-development-key`. No production credential is
created or transmitted. Recovery remains a local owner transport.

`lemma-development-boot-tag/1` is a512-byte sector. UInt64 fields are little
endian; bytes48..79 are the full32-byte HMAC-SHA-256 digest.

| Offset | Field |
| --- | --- |
| 0 | Magic `0x31474154414d454c` |
| 8 | Version1 |
| 16 | Slot0 or1 |
| 24 | Nonzero image identity |
| 32 | Exact Product10 compatibility `0x000a000300010001` |
| 40 | Public development key ID |
| 48 | Full32-byte digest |
| 80–503 | Zero reserved bytes |
| 504 | CRC32 of bytes0..503 in a UInt64 slot |

Tags occupy BootNV sectors2/3 for slots0/1. Metadata remains in sectors0/1;
image slots still start at8/32776. A tag does not publish an image. The MAC
stream is the concatenation of a32-byte domain, the exact512-byte validated
image header, the loaded discovery bytes, and loaded file bytes for each
segment in descriptor order. The domain contains four UInt64 values:
`[0x31544855414d454c, 1, keyId, slot]`. The signed header includes image identity,
compatibility, entry, discovery length/checksum, segment destinations, file
lengths, memory lengths and checksums. Existing checked loading establishes
zero-filled BSS. Padding outside declared file spans is not part of the MAC.

`DevelopmentAuthentication.load` first invokes the ordinary Product10 loader,
then validates the tag and hashes the actual loaded RAM. No second medium read
substitutes for bytes about to execute. A digest mismatch returns240 and never
publishes metadata or hands off. Source/CRC/controller/access errors propagate.
The caller must reject every nonzero result. SHA/HMAC errors cannot become an
authentication success. Crypto scratch is private ROM RAM, never an authority
passed by an untrusted caller.

All workspaces fit the original admitted16KiB ROM scratch region. The command,
payload, tag, header, domain, key, output,2048-byte HMAC workspace and both
metadata buffers are disjoint. Stack and image spans are unchanged. This
placement matters: the sector helper and compiled physical primitives each
reject out-of-region accesses. Their checks were not widened for this feature.

Boot uses the existing transactional selection and bounded trial-attempt
policy. It authenticates the selected loaded image before handoff. A failed
trial MAC can fall back only to a separately loaded and authenticated confirmed
image from validated metadata. It publishes the confirmed boot context, never
a context that allows confirmation of the rejected trial. Authentication does
not imply that any image is healthy; existing guest health/confirmation policy
and its interrupted-update qualifications remain separate.

`lemma-local-uart-development-auth-recovery/2` retains the80-byte CRC-framed
`LMRECOV1` request structure, with transport version2. Transaction0 is reserved
for the capability beacon. Operations are:

| Operation | Meaning |
| --- | --- |
| 0 | Capacity/version capability |
| 1 | Opaque image-sector installation, existing inactive-slot enforcement |
| 2 | Load/MAC validation followed by existing transactional image publication |
| 3 | Authenticated boot and checked handoff |
| 4 | Existing fresh-barrier image receipt plus independent load/MAC validation |
| 5 | Validate/write a tag to the inactive slot, then real backing barrier |
| 6 | Public development key ID |

The guest performs every write and barrier. Error does not imply rollback of
observed medium bytes. No image or tag operation accesses user-document media.
The host tag authoring tool writes a new ordinary file, never a live medium,
guest state, configured flag or verification result. Authenticated boot/update,
independent cold recovery, checkpoints and browser distribution need their own
observed results; component digests and successful ROM linking are insufficient.

`lemmasim-auth --public-development-key install-resume` is an additive owner
transport command over the unchanged version2 protocol. It first requests
operation4 for the supplied slot/image. A successful confirmed1 or trial2
receipt ends the command without sending image, tag or metadata writes. The
receipt still requires the ROM's actual fresh backing barrier and complete
load/MAC validation. It is not inferred from medium bytes, a previous command
result or a matching transaction number in an old transcript.
An image identity names immutable contents in the owner registry. Changed image
contents require a new identity. This receipt binds the requested slot/identity,
compatibility and actual authenticated medium image; it is not a host-file hash
comparison or a guarantee against an owner reusing an identity.

Only the ROM's recovery215 or nonmatching-receipt217, with value0, permit
staging. The command retransmits complete opaque sectors from the beginning,
then the tag and publication request, then obtains a new authenticated status
receipt. The ROM enforces inactive-slot ownership and all installation policy.
No host cursor marks a partially transferred image complete. Barrier failure,
corruption, conflicting metadata, authentication denial, timeout and unknown
status stop the command. They never become durable success. Observed partial
writes remain possible; the command does not roll back backing bytes.

Every phase shares one original cumulative host/cycle budget and monotonically
assigned transaction IDs. A timeout does not automatically retry or reboot.
The owner may explicitly reconnect and issue a new bounded command. That new
command reconciles through fresh guest transactions before attempting writes.
An interrupted partial UART frame may still be owned by the old ROM receiver;
re-enter the announced recovery path before retrying that case. The command
does not silently drain/reset a live machine or claim transport resynchronization.
Ordinary `install`, `tag`, `publish`, `status` and `boot` remain available.
