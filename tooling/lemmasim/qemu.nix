# Host-only derived QEMU. Historical pkgs.qemu and its profiles are untouched.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pin = lock.nodes.nixpkgs.locked;
  source = builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/${pin.rev}.tar.gz";
    sha256 = pin.narHash;
  };
  pkgs = import source { system = "x86_64-linux"; };
  base = pkgs.qemu.override {
    hostCpuTargets = [ "riscv64-softmmu" ];
    minimal = true; gtkSupport = true; sdlSupport = false; vncSupport = true;
    enableDocs = false; enableTools = false; guestAgentSupport = false;
  };
in base.overrideAttrs (old: {
  pname = "lemmasim-qemu";
  nativeBuildInputs = old.nativeBuildInputs ++ [ pkgs.python3Packages.qemu-qmp ];
  buildInputs = old.buildInputs ++ [ pkgs.pixman ];
  buildPhase = ''
    set -e
    runHook preBuild
    make -C build -j$NIX_BUILD_CORES qemu-system-riscv64
    test -x build/qemu-system-riscv64
    runHook postBuild
  '';
  installPhase = ''
    set -e
    runHook preInstall
    make -C build install
    test -x "$out/bin/qemu-system-riscv64"
    "$out/bin/qemu-system-riscv64" -machine help > machine-help.txt
    grep -q lemmasim-virt machine-help.txt
    runHook postInstall
  '';
  postPatch = (old.postPatch or "") + ''
    ${pkgs.python3}/bin/python3 ${./apply_qemu.py} . --host-source ${../../sim/host}
  '';
})
