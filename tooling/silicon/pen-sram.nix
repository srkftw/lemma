# SPDX-License-Identifier: Apache-2.0
# Host qualification of the optional physical pen memory; target shell unchanged.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pin = lock.nodes.nixpkgs.locked;
  source = builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/${pin.rev}.tar.gz";
    sha256 = pin.narHash;
  };
  pkgs = import source { system = "x86_64-linux"; };
in pkgs.mkShell {
  packages = [ pkgs.iverilog pkgs.yosys pkgs.python3 pkgs.gitMinimal ];
}
