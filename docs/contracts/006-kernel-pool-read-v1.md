# Checked kernel metadata reads, version 1

This is an algorithm refinement of ordinary Lean `Objects.get` and
`IPCStorage.get`, with unchanged admitted language, effects and machine profile.
An aligned eight-byte read wholly within `[0x82000000, 0x82200000)` calls the
same checked physical-read primitive directly. Every kernel execution profile
admits that interval. All other addresses execute the original general getter,
now named private `getGeneric`. Both paths preserve the original status-to-fatal
mapping. Expanded-pool addresses retain the general checks.

No allocation choice, owner, handle generation, purpose, quota, pinning,
revocation, zeroing or publication rule changes. This introduces no cache,
unchecked pointer, new effect, allocator stub or host policy. The actual
canonical machine still has its 32 MiB/8192-frame guest pool and full display.

`tests/kernel/PoolReadRefinement.lean` executes both production Actions for
twelve boundary/wrap/alignment addresses and two primitive status outcomes:
48 ordered physical-read and return/error observations. These are host Action
observations, not a compiler proof. Full genuine canonical normal/initializer
builds, complete linked audits and actual guest execution are separate checks.

Historical full-artifact authorities remain immutable. The additive
`tooling/kernel-pool-read-target-authority.json` selects exact new kernel
catalogs for eleven existing product/recovery configurations. Each entry binds
its complete predecessor file and role, genuine typed/effect/root catalog,
complete pre/post body/global/caller corpora and the exact added functions.
Seven selectors add only the two getter fallbacks. Four older USB authorities
also predate the already-maintained owned-registry-count borrow and descriptor
direct-load refinements specified in `006-task-entry-borrow-v2.md`. Their
explicit composition adds those two registry helpers as well. Genuine preceding
`2dc2d64` component exports separate that earlier change from the new getters;
the original authorities and failures remain intact. Existing
role validators still require the complete selected corpus and their original
entry, ownership, recovery and physical-access checks. There is no wildcard or
instruction/body tolerance. Historical catalogs keep their original authority.

The qualification compares every shared genuine predecessor body, signature
and effect. Against the immediately preceding source, only the two getter bodies change
before optimization; each new
fallback is byte-exact under the existing source-name normalization. After
optimization, LLVM also renames some inlined local labels because the two new
definitions shift generated symbols. An explanatory simultaneous symbol-to-
local-label comparison distinguishes that alpha-renaming from changed code.
Admission pins the complete actual emitted corpora, including those labels;
it does not perform the explanatory rebinding or mask any state.

Fast instruction-clock measurements do not establish RTL pipeline timing.
Source-bound canonical RTL execution and browser execution retain their own
acceptance results and original resource bounds. Checkpoints, cold recovery,
distribution and physical closure remain separate obligations.
