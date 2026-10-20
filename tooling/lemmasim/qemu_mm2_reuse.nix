# One independently observed retained-object successor to qualified logical2.
{ seed, siliconProfile ? ../../sim/profiles/lemma-silicon-dev-0.14.0.json }:
let
 selected=builtins.fromJSON (builtins.readFile siliconProfile);
 base=import ./qemu_uart.nix { inherit siliconProfile; logicalSoftTlb=true; };
 repo=../..;
 files=[ "tooling/lemmasim/patch_multimodal_v2.py" "tooling/lemmasim/native_mm2_reuse.py" "tooling/lemmasim/qemu_mm2_reuse.nix" ];
 inputs=builtins.path { path=repo; name="lemmasim-mm2-native-inputs";
  filter = path: type: let relative = builtins.substring ((builtins.stringLength (toString repo))+1) 1000 (toString path);
   in (type=="directory" && builtins.elem relative [ "" "sim" "sim/host" "tooling" "tooling/lemmasim" ]) || builtins.elem relative files || (type=="regular" && builtins.match "sim/host/[^/]+" relative!=null); };
in assert selected.profile=="lemma-silicon-dev/0.14.0";
assert builtins.hashFile "sha256" (seed+"/share/lemma-build/consumed-build.tar.gz")=="6f33bdfcbb44fee70080fa2e6002dfdc115b268a9ab54db7f632ab8328744321";
base.overrideAttrs (old: {
 pname="lemmasim-qemu-mm2-subset-retained";separateDebugInfo=false;dontUpdateAutotoolsGnuConfigScripts=true;
 unpackPhase=''
  mkdir qemu-11.1.1
  cd qemu-11.1.1
  tar -xzf ${seed}/share/lemma-build/consumed-build.tar.gz
 '';
 patchPhase="true";postPatch="";configurePhase="true";preConfigure="";postConfigure="";
 buildPhase=''python3 ${./native_mm2_reuse.py} --inputs ${inputs}'';
 installPhase=''
  mkdir -p "$out/bin" "$out/share/lemma-build"
  cp build/qemu-system-riscv64 "$out/bin/"
  cp -r ${inputs} "$out/share/lemma-build/producer-inputs"
  cp mm2-reuse/result.json "$out/share/lemma-build/result.json"
  cp mm2-reuse/retained-objects.json "$out/share/lemma-build/retained-objects.json"
  tar -czf "$out/share/lemma-build/consumed-build.tar.gz" .
 '';
 preInstall="";postInstall="";
})
