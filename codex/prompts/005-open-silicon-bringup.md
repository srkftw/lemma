<!--
# Task005 — open RV64 silicon bring-up and the shared Lean notebook

Owner authorized this implementation in the task conversation, 2026-10-10.
Reviewed/fetched main: `23b19296f5938821cdc5c092c3921e55e0067a28`,
tree `09c283a305feb746e8165dc2f0fca3c45f3350ea`; PR#5 is merged.
Branch `task/005-open-silicon-bringup`. PR#6's exact specification commit
`dee6415dcb42dd242fa744b8dd271e5618873d50` is incorporated with author
attribution; do not merge, close or rewrite that PR. Publish one draft PR
against current main, with no merge authority.

Implement a reusable synthesizable open RV64 compute/fabric configuration,
architectural reset and genuine Lean/Core0/LLVM RV64 boot, then existing
M/S/U Sv39 services, IPC/preemption/capability/fault containment. Continue
through synthesizable pen FIFO, paper accepted-update controller and modern
VirtIO split-ring block/DMA/flush, into the shared notebook/store's short
pressure-varying stroke, edit/navigation, durability ACK and cold reopening.
The native QEMU notebook remains usable; RTL is an explicit development
backend in `scripts/lemmasim`, never a silent fallback or a policy fork.

Select and pin one open core after focused CVW/CVA6 inspection and early
simulation/synthesis. Preserve licenses. All maintained target software and
project compiler algorithms remain Lean. Host generated C++ and adapters
are explicitly inventoried and excluded from the RV64 link; no guest CPU,
MMU, interrupt, queue, notebook, codec or recovery implementation on the host.
One small authoritative development-binding JSON supplies numeric values.
Audit actual ISA/CSR/fence/counter/privilege needs, not just `rv64im` shorthand.

Separate circuitry, bounded implementable register/macro memories and larger
external simulation memory/media/panel models. Execute technology-independent
compute synthesis, SG13G2 mapping with exact public inputs, and available open
placement/routing of a substantial circuit used in the running system.
Record area, corners, clocks, constraints, timing, DRC and LVS separately;
retain genuine blockers without fabricating signoff or physical equivalence.
IHP SG13G2 stays provisional. No radios, analog digitizer, proprietary IP,
outreach, purchases, paid infrastructure, fabrication or unrelated repository.

Acceptance claims remain independent: A real Lean arithmetic/control/trap/timer;
B isolated services/IPC/preemption/contained denial; C guest RTL pen/paper plus
targeted error/Busy/loss/reset; D notebook stroke/edit/save/cold reopen;
E storage cut/failed flush cannot become SAVED; F measured scoped synthesis/layout.
Independent observations, pinned identities and bounded/reaped processes are
required. Preserve historical failures/profiles, fail-closed audits and useful
legacy regression checks. Final stable implementation is qualified once;
fixes rerun affected claims. Report-only publication identifies its tested tree.
Remove duplicate automatic task-branch push campaigns while retaining main,
PR, manual verification and meaningful existing CI jobs.

Resume `docs/plan/005-session-state.md`. Deliver the strongest observed running
slice if a genuine dependency blocks completion, with one exact next bottleneck.
Do not claim completion from scaffolding, a UART banner or CI alone.

-->
