# Host-only portable RTL build tools, resolved from the existing repository pin.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pin = lock.nodes.nixpkgs.locked;
  source = builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/${pin.rev}.tar.gz";
    sha256 = pin.narHash;
  };
  pkgs = import source { system = "x86_64-linux"; };
in pkgs.mkShell {
  packages = [ pkgs.emscripten pkgs.verilator pkgs.gnumake pkgs.python3 pkgs.nodejs ];
  LEMMA_WASM_NIXPKGS_REV = pin.rev;
}
