# Empty course-ingress polling policy2

`lemma-course-ingress-idle/2` is a guest service policy in the maintained
`PackageInstaller.mainAwait` path. Hardware profiles, clocks, scheduler quantum,
capability grants, course-command1 frames and durable formats are unchanged.
Historical `main`, `step` and `receive` retain their source/behavior. This is
neither a UART implementation nor an additional storage acknowledgment.

Before the first byte of a command header, an actual console read returning
`noByte`/zero sleeps for1,2,4,8,16,32,64, then100ms, saturating at100ms. These are
10MHz MTIME requested delays; ordinary kernel timer/scheduling latency still
applies. This is not a100ms worst-case service or responsiveness guarantee.
A successful nonempty read resets the exponent immediately and advances only
by the actual returned count. Counts outside the requested64-byte header and
inconsistent status/count pairs fail; no header or package is inferred.

Any partial header or body uses the historical receiver, its1ms empty-read
sleep,256-byte maximum read and unchanged body deadline. No backoff extends an
in-progress command. The existing transport has no partial-header expiry; this
policy does not claim to add one. A complete header still undergoes the same
shape checks and real Store transactions. Input admission never implies an
installed package or a durable receipt.

The owned state word at`PackageInstaller.state+56` stores exponent0..7. Startup
sets it to0 before entering the loop; the cap is7. An out-of-range exponent at
an empty read fails rather than applying a masked shift. Failed sleeps retain
the already written exponent prefix; no rollback is promised. Snapshots retain
this ordinary RAM, user PC and the existing kernel sleep deadline. There is no
new checkpoint field, clean-boundary condition, flush or drain.

The motivation is passive sampling of the already running canonical11 cold
case:25 of32 boundary samples were in S mode, including repeated address-space
registry, object and IPC validation. The installer source independently shows
two frequent syscalls at the1ms empty-input cadence. The samples are not a
cycle-exact profile or proof of its contribution. A new guest must demonstrate
any Ready improvement on comparable inputs; no speedup is inferred here and
no ownership or registry validation is removed.

Literal Action checks cover every backoff step/cap, first-byte reset, partial
header/body waits, original body timeout, invalid read counts/statuses, corrupt
exponents and failed read/sleep prefixes. Genuine existing User1 elaboration,
checked lowering and LLVM produce171 functions, with169 common functions and
only `mainAwait` changed from the previous installer. The two new functions are
`receiveIdleHeader` and`stepIdle`. The verified RV64 object has only the declared
`lemma_exec_syscall` external. These are component results; full linked audits,
actual UART installation/backpressure, notebook Ready/Save/cold and comparative
performance remain separate acceptance work.
