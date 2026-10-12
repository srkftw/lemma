# Task006 native immutable package observation

The package at `build/native/task006-canonical-a1` validates separately from
current checkout compilation. Its complete input inventory retains Notebook
`b79b020dd52428bb2a115b5a81cb07df9ab64079cab66a0a9655ce3e38b40af7`,
initializer `622f4e5c319fac5c5678f3a9a3faadb22ccf67cdcddbf6fa344a34ecb680f2f8`,
native RTL `44442fc19ba05bc6ff315116fcad84421e1d851464cb080267da3409982c10b9`
and QEMU `2874932d1816b47d98ed5884a124087bbcd41a6d57c212be624b4dbcc4537716`.
This pack includes still-uncommitted companion host inputs; their exact hashes
are archived. It does not infer clean source from the recorded Git parent.

The actual new-medium guest initialization acknowledged0x41f at30,000,001 fast
count cycles in1.049128453s host. This is not RTL pipeline timing. A separate
public RTL session validated the package and remained paused atcycle0. After
arena source changes, normal preparation rejected the stale whole-source
snapshot while both immutable backend validators passed. The full receipt is
`build/native/task006-bundle-validation-a1.json`; bounded inventory negatives
passed2tests in0.005s. No Ready, notebook Save or new checkpoint-completeness
claim follows from these package checks.

Retained failures: the first init invocation exposed an unbound fast-module
import in the new bundle branch before any guest execution; the import was
fixed and a new output/medium used. A notebook launch without backing was
correctly rejected before session creation. Nothing overwrote those results.

Commands:

```sh
./scripts/lemmasim native-bundle-build --output-dir build/native/task006-canonical-a1
./scripts/lemmasim init --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --native-bundle build/native/task006-canonical-a1 \
  --disk build/native/task006-bundle-medium-a2.raw \
  --session-dir build/native/task006-bundle-init-a2 --timeout 120
./scripts/lemmasim session --backend rtl --profile lemma-silicon-dev/0.3.0 \
  --native-bundle build/native/task006-canonical-a1 --headless --paused \
  --disk build/native/task006-bundle-medium-a2.raw \
  --session-dir build/native/task006-bundle-launch-rtl-a2 --timeout 120
python3 -m unittest discover -s tests/lemmasim -p test_native_bundle.py -v
```

Host runtime files remain
external pinned dependencies; product boot, standalone distribution and
project redistribution rights remain unresolved.
