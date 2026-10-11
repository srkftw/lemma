The silicon EDA environment is separate from the accepted Lean/LLVM/QEMU shell.
It imports the existing `flake.lock` nixpkgs revision; it does not upgrade that
lock or link any EDA runtime into RV64 firmware. `physical-lock.json` records the
public PDK revision and inspected digital corner. The exact public Liberty and
LEF inputs carry IHP PDK Authors Apache-2.0 notices. The PDK's README describes
the release as a preview not intended for production. No redistribution claim
is made for uninspected analog, RF or other design inputs.
OpenROAD uses the same pinned 26Q2 source with GUI, top-level OpenROAD test
targets and release LTO disabled. OpenSTA's separate test targets still build;
the upstream tool self-tests are not run in this development derivation.
The original default package's 90-minute preparation
timeout is retained separately. These host build exclusions do not skip the
design synthesis, placement/routing, timing or requested process checks.
The source closure includes OpenSTA under GPL-3.0-or-later alongside OpenROAD's
BSD-3-Clause main license and ABC's own component notices. Their pinned gitlinks
and original notices are retained; Lemma does not relicense that host tool.

Prepare once:

```sh
python3 scripts/prepare_silicon_pdk.py
nix build --file tooling/silicon/eda.nix openroad --out-link build/silicon/eda-openroad
nix-shell tooling/silicon/eda.nix --run 'verilator --version; yosys -V; openroad -version'
```

Build a fresh full-depth pen synthesis result (FIFO register bits included):

```sh
nix-shell tooling/silicon/eda.nix --run 'python3 scripts/silicon_synth.py --top lemma_pen --source sim/rtl/lemma_pen.sv --map --output-dir build/silicon/physical/pen-map --deadline 1800'
```

The same command with `--layout` requests placement, clock-tree construction,
global routing and detailed signal routing. `layout.tcl` uses a 10 ns clock
(the development binding's 100 MHz), 2 ns input/output delays, a declared
6 fF output load, typical 1.20 V / 25 C cells and public PDK RC values.
Its timing reports use global-route estimated parasitics after detailed routing,
not extracted post-route timing. The recipe repairs high-fanout nets and uses
four CPU threads and three detailed-route refinement iterations. It saves
global-route geometry, area and timing before that bounded detailed route, so
a timeout retains the strongest completed stage. It reports actual router
violations separately and fails if any remain. Timing and electrical violations
retain their own results even when the signal-routing recipe completes.
Power-grid closure and the pad ring are excluded. Optional `--process-checks`
requests original standard-cell GDS import, process DRC and transistor extraction
with Magic, followed by Netgen LVS against the original public CDL cells and
the synthesized circuit. Full-rule DRC/streamout and transistor extraction run
in separate Magic processes: selecting `drc(full)` and then extracting causes
the pinned Magic to segfault on an original public inverter. Fresh extraction
reads the actual streamed GDS. The supplied `ngspice(lvs)` extraction style
emits primitive MOS devices matching the original CDL, including width,
length and bulk connectivity. It differs from the public PDK README's
recommendation for its ordinary Magic/Netgen flow; an original-cell comparison
and independent width/bulk negative cases validate this explicit CDL route.
It requires `--layout`; failures retain the completed
layout and separate check results. Omitting it records process DRC/LVS as
`NOT_RUN`. Public beta PDK checks do not establish foundry signoff, and a
peripheral-only result does not certify a complete SoC.

For compute/fabric, first export the exact ordered core closure:

```sh
python3 scripts/silicon_compute.py manifest > build/silicon/sources.json
nix-shell tooling/silicon/eda.nix --run 'python3 scripts/silicon_synth.py --manifest build/silicon/sources.json --top lemma_compute --output-dir build/silicon/physical/compute-generic --deadline 1800'
```

The compute slice has an explicit external memory port; external simulation
memory is excluded. Its register file, TLB and 4 KiB instruction cache are
synthesized as bounded register logic. Its data cache is disabled. The small
configuration includes a real 4 KiB register RAM, with the firmware ROM,
framebuffer and medium still external:

```sh
python3 scripts/silicon_compute.py manifest --register-ram > build/silicon/sources-small.json
nix-shell tooling/silicon/eda.nix --run 'python3 scripts/silicon_synth.py --manifest build/silicon/sources-small.json --top lemma_soc --parameter REGISTER_RAM=1 --map --map-effort bounded --output-dir build/silicon/physical/soc-small-map --deadline 2400'
```

The small memory configuration runs scalar Core0 workloads; it is too small
for the existing kernel or notebook. It does not establish an on-chip 128 MiB
RAM or a physical nonvolatile boot device. Every command uses a new result directory, saves source,
tool and collateral identities, rejects latches/unresolved cells, and retains
failed command logs. `PASS` means the requested recipe ran with these checks;
the independently reported DRC/LVS/physical-system statuses still apply.
`--map-effort bounded` uses ABC structural hashing and standard-cell mapping
without the normal SAT sweeping and logic rewriting. Its distinct result profile
records this feasibility setting; it is not an area-optimal or timing signoff result.

Upstream EBU ignores AHB HRESP. The deterministic inspected `apply_cvw.py`
patch propagates completed instruction/load/store responses into the existing
PMA/PMP/HPTW access-fault path, holding faults while the pipeline stalls. The
project fabric implements the two-cycle AHB error response. These are modified
open RTL sources under their preserved notices, hashed with the patch script.
