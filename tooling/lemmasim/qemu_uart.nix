# Opt-in host raw UART ingress on the unchanged canonical fast machine.
{ siliconProfile ? ../../sim/profiles/lemma-silicon-dev-0.3.0.json
, logicalSoftTlb ? false }:
let
  selected = builtins.fromJSON (builtins.readFile siliconProfile);
  base = import ./qemu.nix { inherit siliconProfile logicalSoftTlb; };
in assert builtins.elem selected.profile [ "lemma-silicon-dev/0.3.0" "lemma-silicon-dev/0.14.0" ];
base.overrideAttrs (old: {
  pname = if logicalSoftTlb then (if selected.profile == "lemma-silicon-dev/0.14.0" then "lemmasim-qemu-raw-uart-logical-v2" else "lemmasim-qemu-raw-uart-logical-v1") else "lemmasim-qemu-raw-uart-v1";
  buildPhase = ''
    runHook preBuild
    python3 ${./uart_build_budget.py}
    test -x build/qemu-system-riscv64
    runHook postBuild
  '';
  # Preserve the consumed configured source and actual native object closure.
  # A future bounded incremental producer must still verify this immutable seed
  # and bind its own changed-object/link result; this is not fresh execution.
  postInstall = (old.postInstall or "") + ''
    mkdir -p "$out/share/lemma-build"
    tar -czf "$out/share/lemma-build/consumed-build.tar.gz" .
  '';
  postPatch = old.postPatch + ''
    python3 ${./patch_uart_ingress.py} . \
      --header ${../../sim/host/lemma_uart_ingress.h} \
      --implementation ${../../sim/host/lemma_uart_qemu.inc.c}
  '' + (if logicalSoftTlb && selected.profile == "lemma-silicon-dev/0.14.0" then ''
    python3 ${./patch_logical2_lifecycle.py} .
  '' else "");
})
