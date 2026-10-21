# Optional verified retained-object action for the normal logical2 derivation.
# A cold, independently reproducible build remains qemu_uart.nix logicalSoftTlb=true.
{ seed, normalReference
, siliconProfile ? ../../sim/profiles/lemma-silicon-dev-0.14.0.json }:
let
  selected = builtins.fromJSON (builtins.readFile siliconProfile);
  base = import ./qemu_uart.nix { inherit siliconProfile; logicalSoftTlb = true; };
  files = [
    "tooling/lemmasim/qemu.nix" "tooling/lemmasim/qemu_uart.nix"
    "tooling/lemmasim/qemu_logical2_reuse.nix" "tooling/lemmasim/native_logical2_reuse.py"
    "tooling/lemmasim/patch_soft_tlb.py" "tooling/lemmasim/patch_soft_tlb2.py"
    "tooling/lemmasim/patch_multimodal_checkpoint.py" "tooling/lemmasim/patch_logical2_lifecycle.py"
  ];
  repo = ../..;
  inputs = builtins.path {
    path = repo; name = "lemmasim-logical2-native-inputs";
    filter = path: type:
      let relative = builtins.substring ((builtins.stringLength (toString repo)) + 1) 1000 (toString path);
      in (type == "directory" && builtins.elem relative [ "" "sim" "sim/host" "sim/companion" "tooling" "tooling/lemmasim" ])
      || builtins.elem relative files
      || (type == "regular" && (builtins.match "sim/host/[^/]+" relative != null || builtins.match "sim/companion/backing_[^/]+" relative != null));
  };
in assert selected.profile == "lemma-silicon-dev/0.14.0";
assert builtins.elem (builtins.hashFile "sha256" (seed + "/share/lemma-build/consumed-build.tar.gz")) [
  "2050b67858e74648d8be03a938d847a9f4ab0a1f5c4af31b510377488cac898f"
  "d0cd825a4ef187f5db5d2418551ea6d02d1e337429c1c6d37df93843742c70c5"
];
base.overrideAttrs (old: {
  pname = "lemmasim-qemu-raw-uart-logical-v2-retained";
  separateDebugInfo = false;
  dontUpdateAutotoolsGnuConfigScripts = true;
  unpackPhase = ''
    mkdir qemu-11.1.1
    cd qemu-11.1.1
    tar -xzf ${seed}/share/lemma-build/consumed-build.tar.gz
  '';
  patchPhase = "true"; postPatch = "";
  configurePhase = "true"; preConfigure = ""; postConfigure = "";
  buildPhase = ''
    python3 ${./native_logical2_reuse.py} \
      --reference ${normalReference}/share/lemma-build/consumed-build.tar.gz \
      --inputs ${inputs}
  '';
  installPhase = ''
    mkdir -p "$out/bin" "$out/share/lemma-build"
    cp build/qemu-system-riscv64 "$out/bin/"
    cp -r ${inputs} "$out/share/lemma-build/producer-inputs"
    cp logical2-reuse-current/result.json "$out/share/lemma-build/result.json"
    cp logical2-reuse-current/retained-objects.json "$out/share/lemma-build/retained-objects.json"
    tar -czf "$out/share/lemma-build/consumed-build.tar.gz" .
  '';
  preInstall = ""; postInstall = "";
})
