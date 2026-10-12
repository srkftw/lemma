# Native immutable development bundle v1

`lemmasim-native-bundle/1` packs the source-validated canonical0.3 RTL
Machine, matched QEMU backend, Lean reset ROM, audited Notebook and initializer
ELFs, all guest provenance artifacts, complete consumed compiler/RTL input
bytes and profile identity. This is explicit ELF-preload development boot.

`native-bundle-build` first runs the ordinary current-source validators. An
immutable launch validates the complete archived inventory, source closure,
build/provenance/audit/capacity identities, reset-ROM words, runtime binary,
profile, admitted workloads and actual host loader/library digests before
creating a session. The ordinary checkout path still requires current inputs.
An earlier bundle is earlier compilation even when its guest runs freshly.
No user medium or initialized application state is packed. Initialization
exclusively creates new backing and runs the real guest utility/barrier.

Files are bounded to2048/1GiB. Traversal, duplicate JSON keys, symlinked,
missing, changed or unlisted files fail closed. This inventory is integrity
metadata for a locally trusted build, not owner authentication. An unfamiliar
package must not be treated as authenticated firmware. Restore retains the
existing same-backend/private-fork contract; QEMU cached-state limitations
remain open. Bundling establishes no new timing parity or snapshot claim.

The package uses the same native Machine/session controller. Linux x86-64,
Python3, optional Tk/evdev and the manifest's exact external Nix dynamic
loader/libraries remain required. It is not a standalone operating-system
installer. Guest artifacts have no target host-runtime dependency. License
notices identify CVW, Verilator and QEMU; project redistribution rights remain
unresolved. Local preparation changes no licensing or repository settings.
