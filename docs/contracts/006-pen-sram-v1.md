# Optional physical pen SRAM implementation v1

`lemma_pen.IHP_SRAM=1` selects three real
`RM_IHPSG13_1P_256x64_c2_bm_bist` macros in the existing controller. This is a
provisional SG13G2 physical implementation option, not a new digital machine
profile or a qualified silicon part. The default remains the full-depth banked
register implementation. The SoC/native/Wasm profiles do not enable this option;
their state formats and source-bound archives retain their original identities.

The same control process owns admission, loss/resynchronization, ACK, head and
tail, epochs, contact watchdog and reset. All256 entries retain all
181 bits, including64-bit sequence/time. Entries are packed into three64-bit
field banks with11 unused upper bits fixed zero. Delayed ingress writes use the
preceding registered payload/address. A refill reads all field banks at the
existing refill=2 edge, and the existing refill=1 edge publishes the next head.
There is no extra public clock, reduced capacity or ready/accepted bypass.
Read/write collision is forbidden and checked by the actual functional model
corpus. An enabled configuration with FIFO_DEPTH other than256 rejects.

Reset gates memory transactions and clears the original controller registers;
it does not clear or initialize SRAM bytes. Count/head publication prevents
unwritten/stale rows from becoming accepted samples. The macros use the pinned
documented delay setting1, all write-mask bits1, and disabled BIST inputs. The
pure sequence increment has a retained hierarchy boundary through technology
mapping and is flattened afterward; no sequential state or clock is added.

The host qualification command consumes existing Git objects from public PDK
revision `5e6d592e4002946a4616f798c357f0f3c06cf3b6`; it does not fetch, modify
the PDK or synthesize a replacement memory. It retains the original license,
documentation, Verilog functional model, Liberty, LEF, GDS and CDL. Missing
objects/tools fail. All views have separately recorded hashes. Icarus13.0 runs
the published four-state `FUNCTIONAL` model with its delay-input checks active.
The actual default and SRAM controller ports are compared against the immutable
banked controller from `bbce92dc724ded15814543181c09f72f6256a8e2`, plus independent
literal full-capacity field/order/refill/reset/watchdog observations. Real
sequence truncation and address-alias mutants must fail. This finite corpus is
not a full equivalence proof.

`--map` additionally maps the same maintained controller through pinned Yosys
and actual typical-corner libraries. It rejects unknown cells, latches, residual
memories, a macro count other than3, wrong port widths, delay/mask/BIST values or
timestamp-to-sequence-D graph depth above the prospectively fixed20-cell bound.
The bound qualifies a changed-source routing candidate, not delay or timing.
`read_slang --keep-hierarchy` preserves the arithmetic boundary before mapping;
`flatten -noscopeinfo` flattens mapped circuitry while retaining source
attributes. The documented `abc -exe` interface invokes the same pinned ABC
binary in batch mode. Scratch remains under the owned output directory.

```sh
nix-shell tooling/silicon/pen-sram.nix --run \
  'python3 scripts/check_pen_sram.py --pdk build/silicon/deps/ihp-open-pdk \
    --work-dir build/silicon/AN_UNUSED_PEN_SRAM_CHECK --map'
```

This command does not route or establish process DRC/LVS/PEX, PVT, macro power
delivery, test access, retention qualification or full-chip integration. The
completed experimental routes retain actual failures, including setup/hold,
electrical and router violations. No100MHz clock change, false path or rule
waiver follows from selecting SRAM. The option is not admitted to machine
checkpoint execution until its complete logical memory state and corresponding
runtime/profile binding are implemented and qualified. It does not implement
the physical128MiB system memory.
