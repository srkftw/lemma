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
Gates 0--8, including checked memory, compiled polling UART sessions, synchronous
M-mode traps, and actual timer interrupts. Gate 9 is in progress; G1, G2, the remaining Task 002
gates, separate-worktree qualification,
and publication remain open. Tested implementation and later report-bearing
identities are kept separate.

Use `templates/EVIDENCE_REPORT.md` as a reporting structure. Never rename scaffold
metadata tests to imply that the freestanding image booted.
