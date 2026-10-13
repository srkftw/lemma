<!--
# Paper3 executed refresh witness

`lemma-silicon-dev/0.10.0` is an explicit Product successor with descriptor
ABI11/features31. It retains the 1650×2200 Gray4 capacity, 512-byte staging at
`0x10010e00`, synthetic three-phase scan, clocks, power/reset domains, and
separate boot/user media of Product9. Kernel7 authority and the admitted ISA
remain unchanged. Historical profiles0.1–0.9 retain their selected Paper1/2
semantics and archived implementation identities.

The real Product9 trial reached the expected full display but failed its
original confirmation deadline. Paper2 returns zero for its write-only rectangle
configuration registers. Its guest BootHealth required1650/2200 from those
reads. The original failure, exact checkpoint and backing media are retained.
Paper3 does not reinterpret those historical registers.

The new aligned64-bit read-only offsets describe the latest accepted refresh:

| Offset | Read |
| --- | --- |
| 192 | Executed sequence, or0 when invalid |
| 200 | Latched executed x |
| 208 | Latched executed y |
| 216 | Latched executed width |
| 224 | Latched executed height |
| 232 | Latched executed mode |

All six read as0 when the witness is invalid. Paper1/2 return their historical0
at these offsets. Writes remain rejected by the controller's existing error
policy. Paper3 reports version3 and its actual staging offset3584 at184.
The DTB carries `lemma,paper-v3`, ABI3, the staging offset, and the exact six-cell
`lemma,executed-refresh` register vector. Compiled discovery independently
validates those bytes and actual controller version before allocator setup.

Acceptance latches the geometry/mode and makes the witness valid. Subsequent
configuration or tile writes cannot rewrite it. The witness may describe an
in-flight refresh, so it is insufficient without the current busy/error and
completion registers. A successful ACK clears notification while retaining
execution authority. Any controller reset, global/domain reset or abort of the
accepted refresh invalidates it. An idle controller reset retains its old
completion number and modeled optical display, but returns executed sequence0;
that old completion cannot authorize a new trial confirmation. A new accepted
refresh binds the witness to its own sequence before any panel output.

`BootHealthExecuted` requires a nonzero completed sequence equal to both current
accepted sequence112 and executed sequence192, busy0, error0, executed x/y0,
width1650, height2200 and quality mode2. It then revalidates live owned Store and
Notebook task identities before the real alternating boot-metadata WRITE and
BARRIER. Configuration values are never health authority. Failed barriers can
leave changed metadata bytes and never manufacture confirmation or repeat the
publication on a later scheduler step. Raw notebook Save remains Store policy.

The added witness lives in RTL state and participates in generated Verilator
serialization. Native implementation identities include the new profile and
circuitry; old Product9 checkpoints cannot be loaded into this different machine.
An exact same-backend suffix still requires independent observational tests
around acceptance, scan backpressure, abort/reset and retained old completion.
Literal circuit and finite-memory policy tests do not substitute for that check
or actual Product10 ROM install/Notebook Ready/healthy confirmation.

Product10 immutable ROM compatibility is `0x000a000300010001`. A fresh separate
boot medium and owner-local installation are required. Product7/9 confirmed
images are incompatible and are never adopted as healthy fallback. Existing
user journals are copied privately byte-for-byte; installation never formats or
updates them. Integrity remains CRC32 only. Authentication, anti-rollback,
complete fast parity, browser product execution and physical qualification stay
separate open obligations.
-->
