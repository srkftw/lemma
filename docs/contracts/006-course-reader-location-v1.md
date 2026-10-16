# Course reader location1

`lemma-course-reader-location/1` is a separate128-byte record for an explicit
course-node bookmark. It preserves the unchanged workspace, submission,
checker evidence, learner history and raw ink formats. It is not mathematical
evidence. The first version records a node; text role and intra-node position
are not represented.

Sixteen little-endian64-bit words contain magic`0x31524452434d454c`, version1,
namespace, page, package identity, edition, package CRC, node identifier,
source anchor, reader revision, and six reserved zero words. Namespace1..2
and page1..64 retain existing notebook ownership. Revisions range1 through
`0x7fffffffffffffff`. The object identifier is`0x5244000000000000 | page`,
outside the existing package, workspace, mathematics and ink object ranges.
The ordinary Store journal supplies its existing record integrity and
transactional durability; this record introduces no authentication claim.

The guest capture Action validates the complete installed package and selected
node before publication. It reads every selected field before clearing the
private staging span and writes magic last. Resolution validates the complete
current package and requires exact package, edition, CRC and source anchor
agreement. Stale bindings return selectionAbsent244. Malformed or reserved
fields are errors. Error values are zero; access faults retain their status.
All arithmetic and span checks precede access. Resolution has read authority
only, including for explanation, example and review nodes.

Reader18 is an additive software deployment on unchanged silicon0.3. Its two
closed configurations are`lemmasim-silicon-package-reader-bulk-notebook` and
`lemmasim-silicon-package-reader-bulk-initialize`. The latter explicitly formats
new development media; ordinary notebook launch never formats existing media.
Historical history17 and number-entry roots remain selected by their existing
configurations and complete artifact authorities.

An explicit Save in an open, fully validated course captures the current node
and starts the existing Store BEGIN/WRITE/COMMIT protocol. Active raw/checker
or Store work retains its IPC slot. Request admission publishes Pending.
BEGIN and WRITE replies cannot publish the reader or Saved. Only the existing
validated durable COMMIT response reaches the unchanged stage3 Saved path;
the reader wrapper then adopts the acknowledged record. A failed transaction
retains the last acknowledged reader and existing Failed behavior. No adapter
constructs this record or acknowledges a missing barrier.

Reopen first follows the existing workspace/history path, then cooperatively
reads the separate record through actual Store calls. The exact128 bytes and
a separate zero-length EOF response are required before adoption. Only actual
StoreNotFound230 permits the legacy history fallback. Other errors remain
errors. Display text requires subsequent full package validation and exact
source-anchor resolution. Input cancellation consumes an outstanding reader
transaction through the existing cancel/poll path.

Private package-state words208/216/224 hold lookup phase, acknowledged reader
revision and publication flag. Staging occupies128 bytes at offset3840 of the
owned mathematics-save page, after the codec's3808-byte maximum. The live copy
occupies128 bytes after the unchanged3712-byte workspace in its owned page.
These private package words are distinct from notebook state words208..224,
which retain the existing Store source/length/object meanings.

Component Action tests, genuine lowering, full linked-image audit, actual
guest Save/cold recovery and native/browser distribution are separate results.
The presence of this contract does not establish the latter qualifications.
