# Authenticated trial boot watchdog policy v1

Implementation in progress; execution, interrupted confirmation, fallback and
document-preservation acceptance are not yet qualified.

`core0-boot-v0.2` inherits exactly the scalar language, calls, checked physical
RAM, UART and nonvolatile I/O of `core0-boot-v0.1`. It adds aligned64-bit device
accesses only to Power-v2 `[0x10010500,0x100105a0)`, including the last152-byte
reset-epoch offset. Width, alignment, exclusive range, error and I/O fences
remain checked by the maintained LLVM lowering. The old boot profile still
admits only its nonvolatile controller for these device operations. Neither
profile acquires kernel/User authority, heap/managed values or general MMIO.

The additive ROM configuration is
`lemmasim-silicon-public-development-trial-watchdog-boot`, with policy identity
`lemma-trial-boot-watchdog/1`. Hardware remains Product10/Power-v2. Authentication
still uses explicitly public deterministic development material. No production
identity, entropy or durable antirollback trust state is introduced.

The new Lean entry calls the original authenticated recovery/selection/loading
entry. Attempt metadata and payload/tag validation retain their existing
barriers and ordering. After a successful validated trial load, it arms the
independent hardware watchdog for2,000,000,000 machine clocks (20s at100MHz).
This prospective stage bound exceeds the admitted1.2B trial-start/health ceiling;
it is not a host deadline, physical qualification or a general WCET proof.
Confirmed fallback and recovery transport are unarmed. No host loading of the
running image, preinstalled application state or host-selected confirmation is
part of this policy.

The original boot-context words0..5 remain unchanged. The entry clears words6/7
before calling the original policy, then publishes the version1 policy magic
and timeout there only for a selected trial. The new kernel wrapper consumes
that marker in private boot scratch and the original health state. It disarms
only after phase3/status0, which the original kernel publishes after actual
durable confirmation. Failed confirmation remains supervised. It verifies
actual armed=0, records completion once, and preserves the original dispatch
result. Old ROMs/images and their exported profiles retain their own semantics.

Watchdog expiry uses the existing independent hardware clock, eight-cycle
domain reset, watchdog cause and retained nonvolatile backing. ROM attempt
tracking then selects the trial or known-good image under its unchanged limit.
Brownout/power-good and cancellation rules remain Power-v2 responsibilities.
Successful checking of source or ROM compilation alone does not establish any
of these execution/failure outcomes.

The separate kernel deployment is
`lemmasim-silicon-product-course-watchdog-bulk-notebook`, selecting
`TrialWatchdogKernel.boot/dispatch`, Kernel7 and unchanged Product10 hardware.
Its software identity is `lemma-package-reader-product10-watchdog-deployment-v1`.
It has the same four isolated Store/notebook/arithmetic/course roles and no
initializer. All1,302 previous pre-LLVM kernel function bodies, signatures and
effects are retained; exactly15 supervised-entry/Power driver declarations are
added. Complete new pre/post catalogs, globals and callers remain pinned.
The notebook LLVM remains identical except the optimizer's input-path ModuleID
comment; all source metadata except the explicit deployment tuple is unchanged.
The whole linked image and positive healthy-trial disarm require their own
qualification. A validated old image can run under the new ROM but does not
acquire the new disarm policy merely by being packaged.
