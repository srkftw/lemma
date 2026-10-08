# Evidence report: repository scaffold

Status: **passed for scaffold checks only**. No target build, RV64 boot, compiler audit
or integration gate is complete.

## Prepared content

Architecture baseline, four initial contracts, seven gates, 56 software construction
units, six physical-port units, the full first Codex prompt, host-only metadata checks
and a private GitHub publishing helper. Every construction unit remains `planned`.
The toolchain lock is deliberately `unresolved` pending actual compiler probes.

## Commands executed

```sh
python3 scripts/check_scaffold.py
python3 -m unittest discover -s tests/scaffold -v
bash -n scripts/publish-github.sh
```

Results: metadata check passed; dependency graph acyclic; **18 unit tests passed**;
publishing script syntax check passed. Publishing tests use a fake `gh` executable
in temporary directories; they make no GitHub requests and do not establish remote
creation. They exercise private-create arguments, authentication/account errors,
existing repository/origin refusal, a dirty worktree, creation failure and failed
private-visibility confirmation. An initial test invocation found missing helper
files; those were supplied and the complete suite was rerun successfully.

## Publication state

During initial preparation, no remote repository was created: the available tools
could not create one, and the local runtime had no authenticated GitHub CLI.
The owner subsequently created `srkftw/lemma`. A live connected read confirmed
private visibility, `main` as the configured default branch, and push access.
A branch read showed that it was empty before the publication operation.

The prepared Git bundle was restored locally. Publication notes and metadata were
updated. Two full-suite invocations exceeded this session's command time limit;
they were not counted as successful suite runs. All 18 tests were then rerun in
completed batches: 10 metadata tests and publishing-test batches of 3, 3 and 2.
Every case passed. The metadata checker and shell syntax check also passed.
The starter is uploaded through GitHub's file/tree/commit operations. No force-push, visibility change,
license selection, Codex execution, Lean build or QEMU run is part of publication.
The post-publication handoff must confirm the resulting branch and file contents;
a successful local test is not a substitute for that remote check.

## Limits

These checks establish only preparation metadata and mocked publishing behavior.
They do not validate the proposed target ABI, Lean/LLVM compatibility, device drivers,
Core0 language membership, generated image provenance or any physical assembly.
