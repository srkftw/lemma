<!--
# Archived compiler workspace v1

This host-only build interface compiles ordinary maintained Lean from a complete original input archive. It changes neither target language/runtime semantics nor the machine profile. The default live-checkout build and Git-based immutable tool realization remain unchanged.

`build_kernel.py --source-archive ARCHIVE --source-workspace UNUSED` requires both arguments. The fresh workspace must be under the repository's ignored `build/kernel`; the independent original archive must be under `build`. Every named input, its SHA256 and the complete file set are checked before copying and after compilation. Symlinks, special files, extra files, changed manifests and mixed toolchain inputs are rejected. The archive's source identity is never retagged with the current Git revision.

Nix receives only a dedicated realization directory containing the exact locked `flake.nix`, `flake.lock` and `tooling/toolchain-lock.json`, bounded to 262144 bytes. The qualified specimen contains 12443 bytes. A `path:` flake expression resolves this small directory instead of fetching the ignored compiler tree through Git. Cache directories and generated build output never enter that Nix input. The resulting immutable Lean source, NAR, UInt source, tool paths and versions retain the ordinary pinned checks.

The producer records the actual compiler workspace, original inventory hash, realization CWD and three-file closure. Git observations from the workspace identify its actual parent checkout and current HEAD separately. Its current host orchestration input hashes are also distinct from the original target/compiler inventory. No Git repository or fictional historical HEAD is created inside the workspace.

The ordinary audit requires the explicit complete original source archive. The alternate command relation is admitted only with valid workspace metadata and original inventory. Compile/link paths are relative to the recorded private compiler root. Both exact Lake build invocations, their module list, every actual export, pinned executables, ordered compiler/link commands and both Nix commands/CWDs remain load-bearing. Missing metadata, wrong parent/CWD/expression, additional commands or changed consumer files fail. Independent user-image auditing does not inherit this boot-image archive admission.

The retained course initializer and missing notebook were compiled from the same original 372-input archive. The initializer's original full-audit failures and corrected observations remain separate. The missing notebook's original audit rejected the private CWD relation after genuine compilation; a corrected observer audited the unchanged original image. This establishes artifact/source closure, not guest execution, compiler correctness, production boot, course UI or journal recovery.

Example, using a fresh output workspace:

```
nix develop --no-write-lock-file --command python3 scripts/build_kernel.py \
  --configuration lemmasim-silicon-course-await-bulk-notebook --stage supervisor \
  --opt-level O2 --source-archive build/courses/task006-course-await-whole-a3/consumed-source-root \
  --source-workspace build/kernel/course-copy-new/target --output-dir build/kernel/notebook
nix develop --no-write-lock-file --command python3 scripts/audit_kernel.py \
  build/kernel/course-copy-new/target/build/kernel/notebook \
  --source-root build/courses/task006-course-await-whole-a3/consumed-source-root
```

Use `build/task006-lake.lock` around Lake-bearing commands. The original source archive is a local retained artifact; its absence fails and never falls back to current source. Native delivery validates the same original audited guest archive and independently identifies each role's original Git observation. A cold run uses opaque acknowledged backing bytes and a fresh machine; these build artifacts do not replace that run.
-->
