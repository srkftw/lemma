# Notebook dirty-tile batch1

`lemma-notebook-dirty-batch/1` is a Package notebook successor on the existing
canonical0.3 and Clocked13 deployments. Artifact cohort9 keeps the current
four-tile refresh-work budget and input-drain cadence. It submits the selected
FIFO tiles through the already versioned Surface-v2 owned-page operation5.
There is no new instruction, hardware ABI, heap, page, persistent record or
mathematical authority. The historical `pumpRefresh` and Surface definitions
remain unchanged; only the two Package loops select `pumpRefreshBatched`.

`Surface.uploadIndexedBulk(cap,width,height,packed,count)` admits zero to four
16-bit tile indices in FIFO order. Zero count touches no owned data or device.
Nonzero count first rejects count>4 and dimensions outside1..4096 with16, then
rejects nonzero unused slots, duplicate or out-of-range indices with234 before
owned data access. The final used slot is at shift48; no shift by64 is formed.
The helper prepares every rectangle and payload before submitting one packet.
Ordinary checked word operations retain the historical word-copy optimization's
closed caller ownership; the new callback is not added to that old exception.

The existing private staging page holds the normal version2 header, reserved
zeros, up to four32-byte descriptors and512-byte payload slots. Existing tile
gather/edge compaction supplies Gray4 bytes. The kernel still copies owned data,
validates every rectangle and checks the current capability, frame generation,
owner and purpose before controller work. A staging fault may change private
packet bytes but sends no controller transaction and consumes no queue entry.

The kernel returns the actual successfully uploaded prefix. A failed batch can
already have changed those controller staging pixels. The guest consumes only
that ordered prefix, clearing its bitmap bits and advancing the16384-entry
queue modulo capacity. Every uncompleted tile remains queued. A later caller
retry starts at the remaining prefix; this helper does not add automatic
application recovery. A malformed completion count rejects with95. Controller
and private-memory errors remain failures, with no atomic-upload promise.

Refresh publication, accepted sequence checks, busy waits, reset restoration
and controller-produced visible pixels retain their existing path. No refresh
is requested after a failed batch or while queued tiles remain. This work does
not synthesize Ready, Saved or panel completion. Store acknowledgments still
depend on their own real barriers.

The component fixtures cover a wrapped/noncontiguous queue, four-tile and tail
budgets, partial controller completion/retry, late packet-preparation failure,
malformed indices and odd/canonical clipped geometry. These are literal Action
observations and genuine checked lowering; whole linked artifact audits and
actual guest execution remain separate requirements. Timing, complete browser
workflows, fast cached-state continuation and physical closure do not follow
from this component contract.
