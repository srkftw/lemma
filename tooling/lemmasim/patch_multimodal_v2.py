"""Exact five-file MM2 overlay on an independently bound configured predecessor."""
import argparse,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--mode',choices=('native','tci'),required=True);p.add_argument('--host-source',type=Path,required=True);a=p.parse_args()
host=a.host_source;sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
f=a.source/'hw/riscv/lemma_qemu.c';before=sha(f)
assert before=={'native':'dabf894ff96f811f36417dfdd60d6c3d8d65cf7dfe1f1c77135acd06e09f7057','tci':'fdc43ca62debd47d68088ddc15f1106bb48f220eb8d954440437d1b6ecd81df7'}[a.mode]
s=f.read_text()
changes=[
 ('#include "lemma_multimodal.h"','#include "lemma_multimodal.h"\n#include "lemma_multimodal_v2.h"\n/* Hardware model composition; no target policy. */\n#include "lemma_multimodal_v2.c"'),
 ('    LemmaMM multimodal;','    LemmaMM multimodal;\n    LemmaMM2 multimodal_v2;\n    uint32_t multimodal_controller_abi;'),
 ('if(s->multimodal_enabled){timer_del(s->multimodal_timer);lemma_mm_init(&s->multimodal);s->multimodal.tick=(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/10;}','if(s->multimodal_enabled){timer_del(s->multimodal_timer);if(s->multimodal_controller_abi==2)lemma_mm2_init(&s->multimodal_v2);else lemma_mm_init(&s->multimodal);lemma_mm_core(s)->tick=(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/10;}'),
 ('    s->multimodal_enabled=s->fast_binding&&LS_MULTIMODAL_ENABLED;','    if(s->multimodal_controller_abi!=1&&s->multimodal_controller_abi!=2){error_setg(errp,"multimodal-controller-abi must be1 or2");return;}\n    s->multimodal_enabled=s->fast_binding&&LS_MULTIMODAL_ENABLED;'),
 ('        lemma_mm_init(&s->multimodal);','        if(s->multimodal_controller_abi==2)lemma_mm2_init(&s->multimodal_v2);else lemma_mm_init(&s->multimodal);'),
 ('"lemma-multimodal-v1",LS_MULTIMODAL_SPAN','s->multimodal_controller_abi==2?"lemma-multimodal-v2":"lemma-multimodal-v1",LS_MULTIMODAL_SPAN'),
 ('    DEFINE_PROP_STRING("multimodal-audio-output",LemmaDevices,multimodal_audio_path),','    DEFINE_PROP_UINT32("multimodal-controller-abi",LemmaDevices,multimodal_controller_abi,1),\n    DEFINE_PROP_STRING("multimodal-audio-output",LemmaDevices,multimodal_audio_path),'),
]
if a.mode=='native':changes.append(('{&lemma_mm_checkpoint_vmstate,NULL}','{&lemma_mm_checkpoint_vmstate,&lemma_mm2_checkpoint_vmstate,NULL}'))
for old,new in changes:
 assert s.count(old)==1,(a.mode,old[:80],s.count(old));s=s.replace(old,new)
f.write_text(s)
for name in ('lemma_multimodal_v2.c','lemma_multimodal_v2.h','lemma_multimodal_checkpoint_valid.inc.c'):(a.source/'hw/riscv'/name).write_bytes((host/name).read_bytes())
adapter=(host/'lemma_multimodal_qemu.inc.c').read_bytes()
if a.mode=='native':adapter+=b'\n'+(host/'lemma_multimodal_checkpoint.inc.c').read_bytes()
(a.source/'hw/riscv/lemma_multimodal_qemu.inc.c').write_bytes(adapter)
print(json.dumps({'mode':a.mode,'predecessor_main_sha256':before,'files':{n:sha(a.source/'hw/riscv'/n) for n in ('lemma_qemu.c','lemma_multimodal_qemu.inc.c','lemma_multimodal_v2.c','lemma_multimodal_v2.h','lemma_multimodal_checkpoint_valid.inc.c')}},indent=2))
