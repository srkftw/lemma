# Pinned host-only presentation environment. No package enters the RV64 image.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pin = lock.nodes.nixpkgs.locked;
  source = builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/${pin.rev}.tar.gz";
    sha256 = pin.narHash;
  };
  pkgs = import source { system = "x86_64-linux"; };
in pkgs.mkShell {
  packages = [ (pkgs.python3.withPackages (ps: [ ps.tkinter ])) ];
}
