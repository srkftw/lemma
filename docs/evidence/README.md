<!--
# Evidence

The scaffold commit contains no target-execution evidence. Task 001's bounded scalar
execution evidence is now recorded in [001-core0.md](001-core0.md), with a compact
[machine-readable summary](001-core0-summary.json) and [SHA-256
inventory](001-core0-sha256s.txt). The report identifies the clean source commit that
produced the results and keeps the remaining G1 work explicit.

Large generated outputs remain under ignored `build/`; CI uploads the corresponding
Core0 build directory as a retrievable artifact. Checked-in evidence contains hashes,
not toolchains or target binaries.

Task 002's bounded passing Gates 0--11 are recorded in
[002-machine-foundation.md](002-machine-foundation.md), with a
[machine-readable summary](002-machine-foundation-summary.json) and
[hash inventory](002-machine-foundation-sha256s.txt). Repaired source `09c47ba`
passed cold clean detached qualification: 438 foundation hosts, 482 cumulative
plus 23 legacy boots, and 26 retained-session replays. Both actual
[push CI](https://github.com/srkftw/lemma/actions/runs/37825241614) and
[PR CI](https://github.com/srkftw/lemma/actions/runs/37825247231) passed with
verified source/checkout/artifact identities. The branch has an upstream and
[draft stacked PR #2](https://github.com/srkftw/lemma/pull/2), still unmerged.
Earlier `e0e1f2` local success and initial fresh-store Gate 3 CI failures are
retained separately, not relabeled. Full local artifacts/logs are inventoried;
remote archives were stream-inspected/hash-verified but not retained locally.
The report contains the Task 001→002 RV64 capability delta, remaining risks and
partial-only unit mapping. G1/G2 and complete construction-unit qualification
remain open; implementation and report-bearing identities stay separate.

Use `templates/EVIDENCE_REPORT.md` as a reporting structure. Never rename scaffold
metadata tests to imply that the freestanding image booted.

-->
