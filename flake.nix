{
  description = "Pinned host toolchain for the Lemma Core0 freestanding RV64 slice";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/7dd199b0e2993e37b4775ed66b1c291699608c9f";

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    in {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          llvm = pkgs.llvmPackages_20;
        in {
          default = pkgs.mkShell {
            packages = [
              pkgs.lean4
              # The Nix cc-wrapper injects host-only flags that Clang rejects for
              # riscv64-unknown-elf.  Use the pinned upstream binary directly.
              llvm.clang-unwrapped
              llvm.llvm
              llvm.lld
              pkgs.qemu
              pkgs.dtc
              pkgs.python3
              pkgs.jq
            ];

            LEMMA_NIXPKGS_REV = "7dd199b0e2993e37b4775ed66b1c291699608c9f";
          };
        });
    };
}
