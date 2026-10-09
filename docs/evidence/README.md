# Evidence

The scaffold commit contains no target-execution evidence. Task 001's bounded scalar
execution evidence is now recorded in [001-core0.md](001-core0.md), with a compact
[machine-readable summary](001-core0-summary.json) and [SHA-256
inventory](001-core0-sha256s.txt). The report identifies the clean source commit that
produced the results and keeps the remaining G1 work explicit.

Large generated outputs remain under ignored `build/`; CI uploads the corresponding
Core0 build directory as a retrievable artifact. Checked-in evidence contains hashes,
not toolchains or target binaries.

Use `templates/EVIDENCE_REPORT.md` as a reporting structure. Never rename scaffold
metadata tests to imply that the freestanding image booted.
