# Synthetic digital panel sequencer v1

This compatible extension is enabled only by `PAPER_SEQUENCER=1` in the
`lemma-silicon-dev/0.2.0` binding and its matching fast binding. Historical
`lemma-silicon-dev/0.1.0` selects zero and retains its v1 timing/state machine.
The controller register version remains v1; offsets 384–448 are a read-only
extension. The persistent notebook format is unchanged.

`virtual-panel-synthetic/1` is a fixed, redistributable digital program. Its
codes are logical symbols, **not voltage values**, manufacturer waveforms,
electrophoretic predictions or physically safe driving instructions. Physical
panel qualification and configurable qualified waveform programs remain open.
The program intentionally does not depend on old pixels. Target pixels, the
immutable accepted plane and the external retained visible panel are distinct.

The ordinary Lean driver still uploads tiles and accepts mode1 (thresholded
fast) or mode2 (exact-gray quality) rectangle refreshes. Accepted data is copied
into the isolated latch before sequencing. Later uploads cannot change that
latch. Once the existing synthetic deadline has arrived and copying has
completed, the digital controller performs:

| Stage | Digital behavior | Controller clocks with ready external ports |
| --- | --- | --- |
| Power up | Power-enable asserted; neutral code | 2 |
| Condition scan, phase0 | Row-major accepted rectangle, code3 | 1 read + 2 drive per pixel |
| Gap | Neutral code, no source/gate clocks | 1 |
| Target scan, phase1 | Accepted gray below8: code1; otherwise code2 | 1 read + 2 drive per pixel |
| Gap | Neutral code, no source/gate clocks | 1 |
| Neutral scan, phase2 | Row-major accepted rectangle, code0 | 1 read + 2 drive per pixel |
| Gap | Neutral code, no source/gate clocks | 1 |
| Visible commit | Exact accepted gray through existing panel output | 1 read + 1 acknowledged output per pixel |
| Power down | Neutral code; power-enable remains asserted until end | 2 |

Thus an N-pixel rectangle takes `11*N+7` controller clocks after the sequence
start boundary when both ports are ready. Snapshot-copy clocks precede this
boundary. Frame-memory and final-panel backpressure extend this duration;
there is no cycle skipping. Busy remains asserted through power down. Only
then does the controller publish completion, advance the completed sequence and
raise the existing completion interrupt. The visible abstraction accepts only
controller-produced pixels and commits them on that completion.

`panel_drive_valid` denotes each of the two held drive clocks. `panel_source_clock`
pulses on the first clock for each pixel. `panel_gate_clock` pulses on that first
clock at each rectangle row start. The accompanying phase, absolute x/y and
2-bit code are controller outputs. No host gesture or rendering algorithm
supplies these values. Outside drive clocks the code is zero; power and drive
are immediately inactive under asserted reset or an admitted reset command.

The added aligned 64-bit reads are:

| Offset | Value |
| --- | --- |
| 384 | Extension version1 when enabled, otherwise0 |
| 392 | Fixed program identity `0x31504d53`, otherwise0 |
| 400 | Bit0 power-stage active; bits8–9 phase0–2; bits16–17 remaining drive clocks0–2 |
| 408 /416 | Current absolute scan/commit x / y |
| 424 | Current logical drive code0–3 |
| 432 | Held drive clocks in this accepted update |
| 440 | Power-enable0/1 |
| 448 | Completed digital pixel drives in this accepted update |

Phase and counters remain inspectable after completion. Counters restart at
refresh acceptance. Disabled bindings return zero at every extension offset.
Writes to these offsets fail with the existing malformed-command error.
Reads retain the controller's registered sampling/response behavior.

Reset/cancel wins over simultaneous drive or final-output progress. It aborts
an active update, clears private sequencing progress, and retains the previous
completed sequence and visible panel. It clears the target plane using the
existing reset protocol; that is not a white-panel completion. A frame-memory
error aborts with error1, disables digital drive/power, and publishes no
completion. Invalid mode/rectangle acceptance produces error3 before any scan;
a busy second refresh produces error4 without replacing accepted data.

The bounded `PaperSequencer.sv` corpus observes raw pins, memory and completion
independently: every phase/row/source clock, immutable accepted data despite
later uploads, stalled reads, power-down ordering, invalid modes, reset during
drive, retained visible state and memory-error cancellation. It is literal
circuit simulation, separate from guest integration and physical closure.
