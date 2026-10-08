# Evidence

The scaffold commit contains no target-execution evidence. Task 001's bounded scalar
execution evidence is now recorded in [001-core0.md](001-core0.md), with a compact
[machine-readable summary](001-core0-summary.json) and [SHA-256
inventory](001-core0-sha256s.txt). The report identifies the clean source commit that
produced the results and keeps the remaining G1 work explicit.

Large generated outputs remain under ignored `build/`; CI uploads the corresponding
Core0 build directory as a retrievable artifact. Checked-in evidence contains hashes,
not toolchains or target binaries.

Task 002's current passing prefix is recorded in
[002-machine-foundation.md](002-machine-foundation.md), with a
[machine-readable summary](002-machine-foundation-summary.json) and
[hash inventory](002-machine-foundation-sha256s.txt). It currently covers passing
Gates 0--10: checked memory, compiled UART, real M-mode traps/timer interrupts,
the integrated monitor, and clean detached cumulative/stress/legacy/reproducibility
and failure-path qualification. Gate 11 is in progress; Task 002 publication and
actual GitHub CI remain unrun. G1/G2 and complete construction-unit qualification
remain open. Tested implementation and later report-bearing identities stay separate.
The report includes a Gate 0--11 status table and the profile-bound RV64 capability
delta from Task 001.

Use `templates/EVIDENCE_REPORT.md` as a reporting structure. Never rename scaffold
metadata tests to imply that the freestanding image booted.
