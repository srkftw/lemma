# Opt-in host raw UART ingress on the unchanged canonical fast machine.
{ siliconProfile ? ../../sim/profiles/lemma-silicon-dev-0.3.0.json }:
let
  selected = builtins.fromJSON (builtins.readFile siliconProfile);
  base = import ./qemu.nix { inherit siliconProfile; };
in assert builtins.elem selected.profile [ "lemma-silicon-dev/0.3.0" "lemma-silicon-dev/0.14.0" ];
base.overrideAttrs (old: {
  pname = "lemmasim-qemu-raw-uart-v1";
  buildPhase = ''
    runHook preBuild
    python3 ${./uart_build_budget.py}
    test -x build/qemu-system-riscv64
    runHook postBuild
  '';
  postPatch = old.postPatch + ''
    python3 ${./patch_uart_ingress.py} . \
      --header ${../../sim/host/lemma_uart_ingress.h} \
      --implementation ${../../sim/host/lemma_uart_qemu.inc.c}
  '';
})
