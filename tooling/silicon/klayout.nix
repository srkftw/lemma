# SPDX-License-Identifier: Apache-2.0
# Host process-rule tool only. Use --max-jobs 0 for the separately budgeted
# cache-only admission; a cache miss must not start a source compilation.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pin = lock.nodes.nixpkgs.locked;
  source = builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/${pin.rev}.tar.gz";
    sha256 = pin.narHash;
  };
  pkgs = import source { system = "x86_64-linux"; };
in assert pkgs.klayout.version == "0.30.12"; pkgs.klayout
