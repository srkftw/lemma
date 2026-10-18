# Host-only published-source Wasm64 QEMU/TCI toolchain. No target runtime.
let
 lock=builtins.fromJSON(builtins.readFile ../../../flake.lock);
 pin=lock.nodes.nixpkgs.locked;
 source=builtins.fetchTarball {url="https://github.com/NixOS/nixpkgs/archive/${pin.rev}.tar.gz";sha256=pin.narHash;};
 pkgs=import source {system=builtins.currentSystem;};
 py=pkgs.python3.withPackages(ps:[ps.pycotap ps.qemu-qmp ps.setuptools ps.wheel ps.pip]);
in pkgs.mkShell {packages=[pkgs.emscripten pkgs.meson pkgs.ninja pkgs.pkg-config py pkgs.gcc pkgs.autoconf pkgs.automake pkgs.libtool pkgs.gettext];}
