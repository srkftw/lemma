# Indexed controller-output staging

The native and portable RTL Machine now stage Gray4 controller output in a
bounded pixel vector with a presence bitmap. This replaces one host map node
per pending pixel. It does not draw ink, choose waveforms, skip scans or change
guest cycles. Ascending iteration retains the existing snapshot wire encoding;
unmarked vector bytes are unobservable and are not serialized. Reset and scan
abort clear presence, and repeated writes retain the latest value.

The independent ordered-map property checks sparse writes, overwrites, copying,
clearing, edge indices and invalid geometry/value rejection. A full canonical
3,630,000-pixel workload plus deterministic overwrites produced identical
checksums: map staging1.71352s/230460KiB peak RSS, indexed staging0.015082s/14580KiB.
The indexed storage itself is4,083,752 bytes. These are host staging measurements.

The source-bound native integration fixture then ran genuine archived RV64
instructions, inserted literal controller-output pixels, and tested observational
snapshot, ordered restore, overwrite, reset and an exact40,000-cycle pipeline
suffix. The full original/restored archives matched. This fixture does not
qualify guest ink, controller scan completion, canonical Ready or physical panel
behavior. The new native and Wasm builds have independent implementation
identities; historical artifacts are unchanged.

Exact identities, commands, measured results and retained environment/fixture
failures are in `006-indexed-panel.json`. The unchanged native property requires
the pinned silicon shell, which supplies Verilator. Ordinary `nix develop` does
not supply that executable.
