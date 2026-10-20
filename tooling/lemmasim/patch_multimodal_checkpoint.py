#!/usr/bin/env python3
"""Full controller VMState only for the separately selected logical2 machine."""
import argparse
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('source',type=Path)
p.add_argument('--qemu-helper',type=Path,required=True)
p.add_argument('--model-helper',type=Path,required=True)
a=p.parse_args()
path=a.source/'hw/riscv/lemma_qemu.c'
s=path.read_text()
def rep(before,after):
 global s
 if s.count(before)!=1:raise SystemExit('multimodal checkpoint anchor absent/ambiguous: '+before[:80])
 s=s.replace(before,after)
rep('bool multimodal_enabled;', 'bool multimodal_enabled,multimodal_state_loaded;')
rep('static int lemma_post_load(void *opaque,int version)', '''static int lemma_pre_load(void *opaque)
{
 ((LemmaDevices *)opaque)->multimodal_state_loaded=false;return 0;
}
static int lemma_post_load(void *opaque,int version)''')
rep('    uint64_t now=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);\n    /* The pinned migration stream restores timer/icount before this device.', '    if(s->multimodal_enabled && (!s->multimodal_state_loaded || lemma_mm_checkpoint_validate(s)))return -EINVAL;\n    uint64_t now=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);\n    /* The pinned migration stream restores timer/icount before this device.')
rep('    s->dirty=true;lemma_update_irqs(s);return 0;', '''    /* Logical continuation already migrated CPU/PLIC pending and claimed
     * state. Re-driving an unchanged high line would create a new PLIC
     * assertion, not restore a physical edge. Future controller updates still
     * drive the same normal IRQ path. */
    s->dirty=true;if(!lemma_mm_checkpoint_selected())lemma_update_irqs(s);return 0;''')
rep('    LemmaDevices *s=opaque;if(s->multimodal_enabled)return -ENOTSUP;', '''    LemmaDevices *s=opaque;
    if(s->multimodal_enabled && lemma_mm_checkpoint_validate(s))return -ENOTSUP;
    /* Exact capture does not advance the original paper/converter state. */
    if(lemma_mm_checkpoint_selected())return 0;''')
rep('.minimum_version_id=3,.pre_save=lemma_pre_save,.post_load=lemma_post_load,', '''.minimum_version_id=3,.pre_load=lemma_pre_load,.pre_save=lemma_pre_save,.post_load=lemma_post_load,
    .subsections=(const VMStateDescription * const[]){&lemma_mm_checkpoint_vmstate,NULL},''')
path.write_text(s)
path=a.source/'hw/riscv/lemma_multimodal.c';path.write_text(path.read_text()+'\n'+a.model_helper.read_text())
path=a.source/'hw/riscv/lemma_multimodal.h';s=path.read_text();assert s.count('#endif')==1
path.write_text(s.replace('#endif','bool lemma_mm_checkpoint_valid(const LemmaMM *);\n#endif'))
path=a.source/'hw/riscv/lemma_multimodal_qemu.inc.c';path.write_text(path.read_text()+'\n'+a.qemu_helper.read_text())
