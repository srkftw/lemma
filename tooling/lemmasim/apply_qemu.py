#!/usr/bin/env python3
"""Apply the narrow LemmaSim binding to the immutable pinned host QEMU source."""
import argparse,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--repository',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--host-source',type=Path);a=p.parse_args()
s=a.source;r=a.repository;host=a.host_source or r/'sim/host'
for name in ['lemma_qemu.c','lemma_model.c','lemma_model.h','lemma_device_abi.h']:
    shutil.copyfile(host/name,s/'hw/riscv'/name)
f=s/'hw/riscv/meson.build';text=f.read_text();old="riscv_ss.add(when: 'CONFIG_RISCV_VIRT', if_true: files('virt.c'))";assert text.count(old)==1
f.write_text(text.replace(old,"riscv_ss.add(when: 'CONFIG_RISCV_VIRT', if_true: files('virt.c', 'lemma_qemu.c', 'lemma_model.c'))"))
f=s/'hw/riscv/virt.c';text=f.read_text();text=text.replace('#include \"qemu/osdep.h\"','#include \"qemu/osdep.h\"\n#include <libfdt.h>')
anchor='static void virt_machine_done(Notifier *notifier, void *data)';assert text.count(anchor)==1
text=text.replace(anchor,'void lemma_binding_create(MachineState *, DeviceState *);\nvoid lemma_binding_add_fdt(MachineState *);\nvoid lemma_binding_set_dtb(uint64_t, uint64_t);\n\n'+anchor)
# The DTB is finalized in machine_done; create controllers before its actual loading.
needle='    riscv_load_fdt(fdt_load_addr, machine->fdt);';assert text.count(needle)==1
text=text.replace(needle,'    lemma_binding_set_dtb(fdt_load_addr, fdt_totalsize(machine->fdt));\n'+needle)
anchor='static void virt_machine_init_register_types(void)'
extra='''static void lemmasim_machine_init(MachineState *machine)
{
    RISCVVirtState *s = RISCV_VIRT_MACHINE(machine);
    virt_machine_init(machine);
    if (s->aia_type != VIRT_AIA_TYPE_NONE || s->have_aclint) {
        error_report("lemmasim-virt/0.1.0 requires legacy CLINT/PLIC binding");
        exit(1);
    }
    lemma_binding_create(machine, s->irqchip[0]);
}
static void lemmasim_machine_class_init(ObjectClass *oc, const void *data)
{
    MachineClass *mc = MACHINE_CLASS(oc);
    mc->desc = "LemmaSim virt binding 0.1.0 (paper/pen v1)";
    mc->init = lemmasim_machine_init;
    mc->max_cpus = 1;
    mc->default_ram_size = 128 * MiB;
}
static const TypeInfo lemmasim_machine_typeinfo = {
    .name = MACHINE_TYPE_NAME("lemmasim-virt"),
    .parent = TYPE_RISCV_VIRT_MACHINE,
    .class_init = lemmasim_machine_class_init,
};

'''
assert text.count(anchor)==1;text=text.replace(anchor,extra+anchor)
needle='    type_register_static(&virt_machine_typeinfo);';assert text.count(needle)==1
text=text.replace(needle,needle+'\n    type_register_static(&lemmasim_machine_typeinfo);')
# finalize_fdt creates parent PLIC; only afterward add derived binding's nodes.
needle='        finalize_fdt(s);';assert text.count(needle)==1
text=text.replace(needle,needle+'\n        if (object_dynamic_cast(OBJECT(machine), MACHINE_TYPE_NAME("lemmasim-virt"))) {\n            lemma_binding_add_fdt(machine);\n        }')
f.write_text(text)
