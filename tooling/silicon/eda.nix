# SPDX-License-Identifier: Apache-2.0
# Separate host-only RTL/EDA tools. The accepted Lean/LLVM/QEMU shell is unchanged.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pin = lock.nodes.nixpkgs.locked;
  source = builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/${pin.rev}.tar.gz";
    sha256 = pin.narHash;
  };
  pkgs = import source { system = "x86_64-linux"; };
  # The unchanged upstream source supplies a headless host tool. Its large
  # upstream test/GUI/LTO build is separately retained as a timed-out attempt;
  # our design synthesis/layout/DRC/LVS commands are still executed explicitly.
  openroad = pkgs.openroad.overrideAttrs (old: {
    doCheck = false;
    cmakeFlags = old.cmakeFlags ++ [
      "-DENABLE_TESTS=OFF" "-DBUILD_GUI=OFF" "-DLINK_TIME_OPTIMIZATION=OFF"
    ];
  });
in pkgs.mkShell {
  packages = [ pkgs.verilator pkgs.yosys openroad pkgs.magic-vlsi pkgs.netgen-vlsi pkgs.python3
    pkgs.gnumake pkgs.gcc pkgs.gitMinimal ];
  passthru.openroad = openroad;
  LEMMA_EDA_NIXPKGS_REV = pin.rev;
}
