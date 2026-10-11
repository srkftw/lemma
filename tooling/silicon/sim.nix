# SPDX-License-Identifier: Apache-2.0
# Host-only CVW/Verilator tools, independent of slow optional physical-flow preparation.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pin = lock.nodes.nixpkgs.locked;
  source = builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/${pin.rev}.tar.gz";
    sha256 = pin.narHash;
  };
  pkgs = import source { system = "x86_64-linux"; };
in pkgs.mkShell {
  packages = [ pkgs.verilator pkgs.gnumake pkgs.gcc pkgs.gitMinimal pkgs.python3 ];
  LEMMA_SILICON_NIXPKGS_REV = pin.rev;
}
