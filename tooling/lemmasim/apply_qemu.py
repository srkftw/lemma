#!/usr/bin/env python3
"""Apply the narrow LemmaSim binding to the immutable pinned host QEMU source."""
import argparse,shutil,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--repository',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--host-source',type=Path);p.add_argument('--companion-source',type=Path);p.add_argument('--silicon-profile',type=Path);a=p.parse_args()
s=a.source;r=a.repository;host=a.host_source or r/'sim/host'
companion=a.companion_source or r/'sim/companion'
# Pinned QEMU's PPM exporter writes the padded RGB24 pixman stride. PPM rows
# must contain exactly width*3 bytes, otherwise 1650-wide output is sheared.
# Keep this host presentation correction confined to the derived binary.
f=s/'ui/ui-qmp-cmds.c';text=f.read_text();needle='                                  pixman_image_get_stride(linebuf), errp) < 0) {';assert text.count(needle)==1
f.write_text(text.replace(needle,'                                  width * 3, errp) < 0) {'))
for name in ['lemma_qemu.c','lemma_model.c','lemma_model.h','lemma_device_abi.h','lemma_power_abi.h','lemma_fast_block.c','lemma_multimodal.c','lemma_multimodal.h','lemma_multimodal_v2.c','lemma_multimodal_v2.h','lemma_multimodal_checkpoint_valid.inc.c','lemma_multimodal_qemu.inc.c']:
    shutil.copyfile(host/name,s/'hw/riscv'/name)
shutil.copyfile(host/'lemma_durable.c',s/'block/lemma-durable.c')
for directory,origin,names in [('host',host,['backing_io.h','backing_io.cpp','backing_io_posix.h','backing_io_posix.cpp']),
                             ('companion',companion,['backing_peer.h','backing_peer.cpp','backing_c.h','backing_c.cpp'])]:
    (s/'hw/riscv'/directory).mkdir()
    for name in names:shutil.copyfile(origin/name,s/'hw/riscv'/directory/name)
profile=json.loads((a.silicon_profile or r/'sim/profiles/lemma-silicon-dev-0.1.0.json').read_text())
fields={k:v for k,v in profile.items() if isinstance(v,int)}
fields.update(width=profile['geometry'][0],height=profile['geometry'][1],paper_sequencer=profile.get('paper_sequencer',0),
              power_enabled=profile.get('power_enabled',0),power_base=0,power_span=0,power_irq=0)
for dev,values in profile['devices'].items():
    fields.update({dev+'_'+key:value for key,value in values.items() if isinstance(value,int)})
fields.update({'descriptor_'+key:value for key,value in profile['descriptor'].items()})
if profile['profile']=='lemma-silicon-dev/0.4.0':
    for name in ['lemma_power_safety.h','lemma_power_safety.c','lemma_power_clock.h','lemma_power_clock.c','lemma_power_qemu.inc.c']:
        shutil.copyfile(host/name,s/'hw/riscv'/name)
(s/'hw/riscv/lemma_silicon_fast.h').write_text('/* Generated from selected maintained silicon profile. Host only. */\n'+''.join(f'#define LS_{key.upper()} UINT64_C({value})\n' for key,value in fields.items()))

f=s/'block/meson.build';text=f.read_text();needle="system_ss.add(files('block-ram-registrar.c'))";assert text.count(needle)==1
f.write_text(text.replace(needle,needle+"\nsystem_ss.add(files('lemma-durable.c'))"))
f=s/'qapi/block-core.json';text=f.read_text()
needle="'data': [ 'blkdebug', 'blklogwrites', 'blkreplay', 'blkverify', 'bochs',";assert text.count(needle)==1
text=text.replace(needle,"'data': [ 'lemma-durable', 'blkdebug', 'blklogwrites', 'blkreplay', 'blkverify', 'bochs',")
needle="      'blkreplay':  'BlockdevOptionsBlkreplay',";assert text.count(needle)==1
text=text.replace(needle,needle+"\n      'lemma-durable': 'BlockdevOptionsLemmaDurable',")
needle="# @BlockdevOptionsBlkreplay:";assert text.count(needle)==1
definition='''# @BlockdevOptionsLemmaDurable:
#
# LemmaSim host-only stable/volatile medium v1, project extension.
#
# @pending-sectors: Maximum RAM overlay sectors, default 32768.
# @fail-write: Fail this numbered write before changing volatile RAM.
# @fail-flush: Fail this numbered flush before stable writes.
# @cut-before-flush: Cut power before this numbered flush.
# @cut-after-flush: Cut power after this numbered durable flush.
# @tear-flush: Tear first sector at this flush, then cut power.
# @delay-after-ns: Earliest virtual time for one delayed write.
# @delay-write-ns: Virtual delay of first eligible write.
#     Default disabled.
# @trace-file: New file for normalized media-device observations.
#
# Since: 11.1
##
{ 'struct': 'BlockdevOptionsLemmaDurable',
  'base': 'BlockdevOptionsGenericFormat',
  'data': { '*pending-sectors': 'uint64', '*fail-write': 'uint64',
            '*fail-flush': 'uint64', '*cut-before-flush': 'uint64',
            '*cut-after-flush': 'uint64', '*tear-flush': 'uint64',
            '*delay-after-ns': 'uint64', '*delay-write-ns': 'uint64',
            '*trace-file': 'str' } }

##
'''
text=text.replace(needle,definition+needle);f.write_text(text)
f=s/'hw/riscv/meson.build';text=f.read_text();old="riscv_ss.add(when: 'CONFIG_RISCV_VIRT', if_true: files('virt.c'))";assert text.count(old)==1
f.write_text(text.replace(old,"riscv_ss.add(when: 'CONFIG_RISCV_VIRT', if_true: files('virt.c', 'lemma_qemu.c', 'lemma_model.c', 'lemma_multimodal.c', 'lemma_fast_block.c', 'host/backing_io.cpp', 'host/backing_io_posix.cpp', 'companion/backing_peer.cpp', 'companion/backing_c.cpp'))"))
if profile['profile']=='lemma-silicon-dev/0.4.0':
    f=s/'hw/riscv/meson.build';text=f.read_text();needle="'lemma_model.c', 'lemma_multimodal.c', 'lemma_fast_block.c'";assert text.count(needle)==1
    f.write_text(text.replace(needle,"'lemma_model.c', 'lemma_multimodal.c', 'lemma_power_safety.c', 'lemma_power_clock.c', 'lemma_fast_block.c'"))
f=s/'hw/riscv/virt.c';text=f.read_text();text=text.replace('#include \"qemu/osdep.h\"','#include \"qemu/osdep.h\"\n#include <libfdt.h>\n#include \"lemma_silicon_fast.h\"')
anchor='static void virt_machine_done(Notifier *notifier, void *data)';assert text.count(anchor)==1
text=text.replace(anchor,'void lemma_binding_create(MachineState *, DeviceState *);\nvoid lemma_binding_add_fdt(MachineState *);\nvoid lemma_binding_set_dtb(uint64_t, uint64_t);\nvoid lemma_fast_block_create(MachineState *, DeviceState *);\n\n'+anchor)
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
static void lemma_fast_machine_init(MachineState *machine)
{
    RISCVVirtState *s = RISCV_VIRT_MACHINE(machine);
    if (!machine->dtb || machine->ram_size != LS_RAM_BYTES || machine->smp.cpus != LS_HART_COUNT ||
        s->aia_type != VIRT_AIA_TYPE_NONE || s->have_aclint || kvm_enabled()) {
        error_report("lemma-silicon-fast requires the selected profile DTB, RAM, one hart and TCG CLINT/PLIC");
        exit(1);
    }
    /* Profile counts real sources1..N; QEMU also allocates reserved source0. */
    s->num_sources = LS_PLIC_SOURCES + 1;
    s->acpi = ON_OFF_AUTO_OFF;
    s->iommu_sys = ON_OFF_AUTO_OFF;
    virt_machine_init(machine);
    RISCVCPU *cpu = &s->soc[0].harts[0];
    /* qtest executes no CPU. Its literal controller fixtures have no ISA
     * claim; TCG remains subject to the complete declared admission guard. */
    if (!qtest_enabled() && (cpu->env.misa_ext != (RVI | RVM | RVS | RVU) ||
        !cpu->cfg.mmu || !cpu->cfg.pmp || cpu->cfg.pmp_regions != 16 ||
        cpu->cfg.max_satp_mode != VM_1_10_SV39 ||
        !cpu->cfg.ext_zicsr || !cpu->cfg.ext_zifencei || !cpu->cfg.ext_zicntr ||
        cpu->cfg.ext_zihpm || cpu->cfg.ext_sstc || cpu->cfg.ext_smrnmi || cpu->cfg.ext_smdbltrp)) {
        error_report("lemma-silicon-fast requires the declared RV64IM/MSU/Sv39/PMP scalar CPU configuration");
        exit(1);
    }
    lemma_binding_create(machine, s->irqchip[0]);
    lemma_fast_block_create(machine, s->irqchip[0]);
}
static void lemma_fast_machine_class_init(ObjectClass *oc, const void *data)
{
    MachineClass *mc = MACHINE_CLASS(oc);
    mc->desc = "Lemma silicon selected development profile, fast functional binding";
    mc->init = lemma_fast_machine_init;
    mc->max_cpus = 1;
    mc->default_ram_size = LS_RAM_BYTES;
    mc->default_cpu_type = TYPE_RISCV_CPU_RV64I;
}
static const TypeInfo lemma_fast_machine_typeinfo = {
    .name = MACHINE_TYPE_NAME("lemma-silicon-fast"),
    .parent = TYPE_RISCV_VIRT_MACHINE,
    .class_init = lemma_fast_machine_class_init,
};

'''
assert text.count(anchor)==1;text=text.replace(anchor,extra+anchor)
needle='    type_register_static(&virt_machine_typeinfo);';assert text.count(needle)==1
text=text.replace(needle,needle+'\n    type_register_static(&lemmasim_machine_typeinfo);\n    type_register_static(&lemma_fast_machine_typeinfo);')
# finalize_fdt creates parent PLIC; only afterward add derived binding's nodes.
needle='        finalize_fdt(s);';assert text.count(needle)==1
text=text.replace(needle,needle+'\n        if (object_dynamic_cast(OBJECT(machine), MACHINE_TYPE_NAME("lemmasim-virt"))) {\n            lemma_binding_add_fdt(machine);\n        }')
# The fast binding instantiates only the selected silicon device inventory.
# The historical virt branch keeps its exact construction and inherited maps.
needle='    int socket_count = riscv_socket_count(machine);'
text=text.replace(needle,needle+'\n    bool lemma_fast = object_dynamic_cast(OBJECT(machine), MACHINE_TYPE_NAME("lemma-silicon-fast")) != NULL;')
text=text.replace('int base_hartid, int hart_count)\n{\n    g_autofree char *plic_hart_config', 'int base_hartid, int hart_count, int sources)\n{\n    g_autofree char *plic_hart_config')
text=text.replace('             VIRT_IRQCHIP_NUM_SOURCES,\n             ((1U', '             sources,\n             ((1U')
text=text.replace('base_hartid, hart_count);\n        } else {\n            s->irqchip[i]', 'base_hartid, hart_count, s->num_sources);\n        } else {\n            s->irqchip[i]')
text=text.replace('    s->fw_cfg = create_fw_cfg(machine, s->memmap[VIRT_FW_CFG].base);\n    rom_set_fw(s->fw_cfg);', '    if (!lemma_fast) {\n        s->fw_cfg = create_fw_cfg(machine, s->memmap[VIRT_FW_CFG].base);\n        rom_set_fw(s->fw_cfg);\n    }')
text=text.replace('for (i = 0; i < VIRTIO_COUNT; i++) {\n        sysbus_create_simple', 'for (i = 0; i < (lemma_fast ? 0 : VIRTIO_COUNT); i++) {\n        sysbus_create_simple')
text=text.replace('    gpex_pcie_init(system_memory, pcie_irqchip, s);\n\n    create_platform_bus(s, mmio_irqchip);', '    if (!lemma_fast) {\n        gpex_pcie_init(system_memory, pcie_irqchip, s);\n        create_platform_bus(s, mmio_irqchip);\n    }')
text=text.replace('    sysbus_create_simple("goldfish_rtc", s->memmap[VIRT_RTC].base,\n        qdev_get_gpio_in(mmio_irqchip, RTC_IRQ));', '    if (!lemma_fast) sysbus_create_simple("goldfish_rtc", s->memmap[VIRT_RTC].base,\n        qdev_get_gpio_in(mmio_irqchip, RTC_IRQ));')
text=text.replace('    virt_flash_map(s, system_memory);', '    if (!lemma_fast) virt_flash_map(s, system_memory);')
text=text.replace('for (i = 0; i < ARRAY_SIZE(s->flash); i++) {', 'for (i = 0; i < (lemma_fast ? 0 : ARRAY_SIZE(s->flash)); i++) {')
text=text.replace('    virt_flash_create(s);', '    if (!object_dynamic_cast(obj, MACHINE_TYPE_NAME("lemma-silicon-fast"))) virt_flash_create(s);')
text=text.replace('    pflash_blk0 = pflash_cfi01_get_blk(s->flash[0]);', '    pflash_blk0 = object_dynamic_cast(OBJECT(machine), MACHINE_TYPE_NAME("lemma-silicon-fast")) ? NULL : pflash_cfi01_get_blk(s->flash[0]);')
text=text.replace('    virt_build_smbios(s);', '    if (s->fw_cfg) virt_build_smbios(s);')
text=text.replace('        machine->fdt = load_device_tree(machine->dtb, &s->fdt_size);', '''        if (lemma_fast) {
            s->fdt_size = get_image_size(machine->dtb, NULL);
            if (s->fdt_size < 40 || s->fdt_size > LS_DTB_RESERVE_BYTES) {
                error_report("silicon-fast DTB must fit its bounded boot reservation");
                exit(1);
            }
            machine->fdt = g_malloc0(s->fdt_size);
            if (load_image_size(machine->dtb, machine->fdt, s->fdt_size) != s->fdt_size ||
                fdt_check_full(machine->fdt, s->fdt_size) ||
                fdt_totalsize(machine->fdt) != s->fdt_size) {
                error_report("silicon-fast DTB is malformed or has trailing bytes");
                exit(1);
            }
        } else {
            machine->fdt = load_device_tree(machine->dtb, &s->fdt_size);
        }''')
f.write_text(text)

# QEMU ordinary stop drains and flushes block graphs. The fast machine has no
# QEMU block graph or yielding I/O coroutines: every request is explicit device
# state and synchronous external barriers finish within one timer callback.
# Its pause therefore only stops execution/time; it never completes a transfer.
f=s/'system/cpus.c';text=f.read_text();needle='    bdrv_drain_all();\n    /*\n     * Even if vm_state_notify() return failure,';assert text.count(needle)==1
text=text.replace(needle,'    if (object_dynamic_cast(OBJECT(qdev_get_machine()), MACHINE_TYPE_NAME("lemma-silicon-fast"))) {\n        return ret;\n    }\n'+needle);f.write_text(text)

# In no-sleep icount mode a WFI vCPU can dispatch the stop timer itself.
# vm_stop then queues its main-loop stop; no subsequent idle warp may cross
# that already-executed lifecycle boundary before the stop is processed.
f=s/'accel/tcg/icount-common.c';text=f.read_text()
needle='void icount_start_warp_timer(void)\n{';assert text.count(needle)==1
text=text.replace(needle,'bool lemma_sim_stop_pending(void);\n\n'+needle)
start=text.index('void icount_start_warp_timer(void)');end=text.index('\nvoid icount_account_warp_timer',start)
part=text[start:end];needle='    if (!runstate_is_running()) {';assert part.count(needle)==1
part=part.replace(needle,'    if (!runstate_is_running() || lemma_sim_stop_pending()) {')
text=text[:start]+part+text[end:];f.write_text(text)

f=s/'qapi/migration.json';text=f.read_text();text += '\n' + '''##
# @lemma-save-machine:
#
# Save a state-complete Lemma silicon fast machine without flushing
# its external medium.
#
# Requires paused execution and no block graph.
#
# @filename: New output filename.
#
# Since: 11.1
##
{ 'command': 'lemma-save-machine', 'data': { 'filename': 'str' } }

##
# @lemma-load-machine:
#
# Restore into a paused machine with the identical selected profile
# and an isolated medium whose digest matches the saved device state.
#
# @filename: Existing saved-state filename.
#
# Since: 11.1
##
{ 'command': 'lemma-load-machine', 'data': { 'filename': 'str' } }
''';f.write_text(text)
f=s/'migration/savevm.c';text=f.read_text();text += '\n' + '''
static bool lemma_state_boundary(Error **errp)
{
    if (!object_dynamic_cast(OBJECT(qdev_get_machine()), MACHINE_TYPE_NAME("lemma-silicon-fast")) ||
        runstate_is_running() || migration_is_running()) {
        error_setg(errp, "Lemma exact state requires a paused silicon-fast machine and no active migration");
        return false;
    }
    cpu_synchronize_all_states();
    return true;
}
void qmp_lemma_save_machine(const char *filename, Error **errp)
{
    QEMUFile *f; QIOChannelFile *ioc; int ret;
    if (!lemma_state_boundary(errp)) return;
    ioc = qio_channel_file_new_path(filename, O_WRONLY | O_CREAT | O_EXCL, 0600, errp);
    if (!ioc) return;
    f = qemu_file_new_output(QIO_CHANNEL(ioc)); object_unref(OBJECT(ioc));
    global_state_store();
    ret = qemu_savevm_state(f, errp);
    if (qemu_fclose(f) < 0 && ret >= 0) error_setg(errp, "Lemma state file close failed");
}
void qmp_lemma_load_machine(const char *filename, Error **errp)
{
    QEMUFile *f; QIOChannelFile *ioc; int ret;
    if (!lemma_state_boundary(errp)) return;
    ioc = qio_channel_file_new_path(filename, O_RDONLY | O_BINARY, 0, errp);
    if (!ioc) return;
    f = qemu_file_new_input(QIO_CHANNEL(ioc)); object_unref(OBJECT(ioc));
    /* Mirror the pinned load_snapshot incoming lifetime without its block
     * drain or machine reset: this binding has no asynchronous block graph. */
    if (!yank_register_instance(MIGRATION_YANK_INSTANCE, errp)) {
        qemu_fclose(f);
        return;
    }
    migration_incoming_get_current()->from_src_file = f;
    cpu_synchronize_all_pre_loadvm();
    ret = qemu_loadvm_state(f, errp);
    if (ret < 0) error_prepend(errp, "Lemma machine state restore failed: ");
    migration_incoming_state_destroy();
}
''';f.write_text(text)

# ELF-preload is an explicit development boot mechanism. Initial power-on loads
# RAM once; a warm reset must not covertly reinstall executable/data segments.
f=s/'hw/core/loader.c';text=f.read_text();needle='static void rom_reset(void *unused)\n{\n    Rom *rom;';assert text.count(needle)==1
text=text.replace(needle,needle+'\n    static bool lemma_fast_loaded;\n    bool lemma_fast = object_dynamic_cast(OBJECT(qdev_get_machine()), MACHINE_TYPE_NAME("lemma-silicon-fast")) != NULL;')
needle='    QTAILQ_FOREACH(rom, &roms, next) {\n        if (rom->fw_file) {'
start=text.index('static void rom_reset(void *unused)');end=text.index('\n}',start)
part=text[start:end];assert part.count(needle)==1
part=part.replace(needle,'    QTAILQ_FOREACH(rom, &roms, next) {\n        if (lemma_fast && lemma_fast_loaded && !rom->isrom) continue;\n        if (rom->fw_file) {')
text=text[:start]+part+text[end:]
needle='static void rom_reset(void *unused)';start=text.index(needle);end=text.index('\n}',start)
text=text[:end]+'\n    if (lemma_fast) lemma_fast_loaded = true;'+text[end:];f.write_text(text)
