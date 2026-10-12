#!/usr/bin/env python3
"""Pinned host-only PMU clock/reset/state extension for silicon profile0.3."""
import argparse
import hashlib
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();root=a.source
expected={
 'target/riscv/tcg/pmu.c':'bdd7627a1cc6cc406c88d4bc6cf2c9a179d243473ac877e92e0ecf460b37cbdd',
 'target/riscv/tcg/pmu.h':'bd0aaba64dfcb94032b6825f89ee3fe2fc01a5a69d97b7995da06d22a9ad97c7',
 'target/riscv/tcg/csr.c':'631294ef82387021c1a40d2125b636b4097a9350a2bc50d299ff38d5aa856360',
 'target/riscv/cpu.c':'47a2a33230a5597dfc75294601bae8994a1d00d34cbec6af88a7b01bc3ca7645',
 'target/riscv/cpu.h':'123cc029c9240ab6a1337f08ba17c3f88d2c1b48cd1f63b9902812d90df33cef',
 'target/riscv/machine.c':'d56f11912fb01d79ba91b191a4fc3a0bc05c793531f0ee004c2ad6661e703fcf',
 'hw/char/serial.c':'b67d258a7dcb02174ad25eac3fc8ebc89b625aabf87e74f6f8ace7d94eb8b18f',
}
for name,sha in expected.items():
 if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:
  raise SystemExit('unsupported counter source identity: '+name)

def replace(name,before,after):
 path=root/name;data=path.read_text()
 if data.count(before)!=1:raise SystemExit('counter patch anchor ambiguous: '+name)
 path.write_text(data.replace(before,after))

# Frequency is immutable implementation configuration; the matching marker is
# migrated state. Profile identity is still independently checked by LemmaSim.
replace('target/riscv/cpu.h','    PMUFixedCtrState pmu_fixed_ctrs[2];',
 '''    PMUFixedCtrState pmu_fixed_ctrs[2];
    uint64_t lemma_counter_clock_hz;''')
replace('target/riscv/cpu.h','    /* Configuration Settings */\n    RISCVCPUConfig cfg;',
 '''    /* Configuration Settings */
    RISCVCPUConfig cfg;
    uint64_t lemma_counter_hz;''')
replace('target/riscv/tcg/pmu.h','void riscv_pmu_decr_instret(CPURISCVState *env);',
 '''void riscv_pmu_decr_instret(CPURISCVState *env);
uint64_t riscv_pmu_cycle_ticks(CPURISCVState *env);
void riscv_pmu_lemma_reset(CPURISCVState *env);''')
replace('target/riscv/tcg/pmu.c','#include "qemu/timer.h"',
 '#include "qemu/timer.h"\n#include "qemu/host-utils.h"')
replace('target/riscv/tcg/pmu.c','#define RISCV_TIMEBASE_FREQ 1000000000 /* 1Ghz */',
 '''#define RISCV_TIMEBASE_FREQ 1000000000 /* 1Ghz */

uint64_t riscv_pmu_cycle_ticks(CPURISCVState *env)
{
    RISCVCPU *cpu = env_archcpu(env);
    if (cpu->lemma_counter_hz) {
        g_assert(icount_enabled());
        /* Scale the absolute clock BEFORE baseline subtraction. Fractional
         * phase stays in the migrated icount clock, including WFI warps. */
        return muldiv64((uint64_t)icount_get(), cpu->lemma_counter_hz,
                        NANOSECONDS_PER_SECOND);
    }
    return icount_enabled() ? icount_get() : cpu_get_host_ticks();
}

void riscv_pmu_lemma_reset(CPURISCVState *env)
{
    RISCVCPU *cpu = env_archcpu(env);
    uint64_t cycles, retired;
    if (!cpu->lemma_counter_hz) {
        return;
    }
    g_assert(icount_enabled() && !cpu->cfg.ext_zihpm &&
             !cpu->cfg.ext_smcntrpmf && cpu->pmu_avail_ctrs == 0);
    cycles = riscv_pmu_cycle_ticks(env);
    retired = icount_get_raw();
    env->lemma_counter_clock_hz = cpu->lemma_counter_hz;
    env->mcountinhibit = env->scountinhibit = 0;
    env->mcyclecfg = env->minstretcfg = 0;
    memset(env->pmu_ctrs, 0, sizeof(env->pmu_ctrs));
    memset(env->pmu_fixed_ctrs, 0, sizeof(env->pmu_fixed_ctrs));
    memset(env->mhpmevent_val, 0, sizeof(env->mhpmevent_val));
    env->pmu_ctrs[0].mhpmcounter_prev = cycles;
    env->pmu_ctrs[2].mhpmcounter_prev = retired;
    for (int priv = 0; priv < 4; ++priv) {
        env->pmu_fixed_ctrs[0].counter_prev[priv] = cycles;
        env->pmu_fixed_ctrs[1].counter_prev[priv] = retired;
    }
    for (int priv = 0; priv < 2; ++priv) {
        env->pmu_fixed_ctrs[0].counter_virt_prev[priv] = cycles;
        env->pmu_fixed_ctrs[1].counter_virt_prev[priv] = retired;
    }
}''')
replace('target/riscv/tcg/pmu.c',
 '''    if (icount_enabled()) {
        current_ticks = icount_get();
    } else {
        current_ticks = cpu_get_host_ticks();
    }''',
 '    current_ticks = riscv_pmu_cycle_ticks(env);')
replace('target/riscv/tcg/csr.c',
 '''                curr_val = inst ? icount_get_raw() : icount_get();''',
 '''                curr_val = inst ? icount_get_raw() :
                                  riscv_pmu_cycle_ticks(env);''')
replace('target/riscv/cpu.c','#include "target/riscv/tcg/csr.h"',
 '#include "target/riscv/tcg/csr.h"\n#include "target/riscv/tcg/pmu.h"')
replace('target/riscv/cpu.c','    /* Initialized default priorities of local interrupts. */',
 '''    riscv_pmu_lemma_reset(env);

    /* Initialized default priorities of local interrupts. */''')

# Fixed counter per-privilege snapshots are private execution state even
# though Smcntrpmf is not admitted. Preserve them as well as the already
# serialized counter values/baselines and icount virtual phase.
replace('target/riscv/machine.c','static int riscv_cpu_post_load(void *opaque, int version_id)',
 '''static int riscv_cpu_lemma_pre_load(void *opaque)
{
    RISCVCPU *cpu = opaque;
    if (cpu->lemma_counter_hz) {
        /* Require the successor subsection; absent old-state data cannot
         * inherit an initialized marker and silently become compatible. */
        cpu->env.lemma_counter_clock_hz = 0;
    }
    return 0;
}

static int riscv_cpu_post_load(void *opaque, int version_id)''')
replace('target/riscv/machine.c','    env->xl = cpu_recompute_xl(env);\n    return 0;',
 '''    if (cpu->lemma_counter_hz &&
        env->lemma_counter_clock_hz != cpu->lemma_counter_hz) {
        return -EINVAL;
    }
    env->xl = cpu_recompute_xl(env);
    return 0;''')
replace('target/riscv/machine.c','const VMStateDescription vmstate_riscv_cpu = {',
 '''static const VMStateDescription vmstate_lemma_fixed_ctr = {
    .name = "cpu/lemma-fixed-counter",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT64_ARRAY(counter, PMUFixedCtrState, 4),
        VMSTATE_UINT64_ARRAY(counter_prev, PMUFixedCtrState, 4),
        VMSTATE_UINT64_ARRAY(counter_virt, PMUFixedCtrState, 2),
        VMSTATE_UINT64_ARRAY(counter_virt_prev, PMUFixedCtrState, 2),
        VMSTATE_END_OF_LIST()
    }
};

static bool lemma_counter_needed(void *opaque)
{
    return RISCV_CPU(opaque)->lemma_counter_hz != 0;
}

static const VMStateDescription vmstate_lemma_counter = {
    .name = "cpu/lemma-counter-clock",
    .version_id = 1,
    .minimum_version_id = 1,
    .needed = lemma_counter_needed,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT64(env.lemma_counter_clock_hz, RISCVCPU),
        VMSTATE_UINT64(env.mcyclecfg, RISCVCPU),
        VMSTATE_UINT64(env.minstretcfg, RISCVCPU),
        VMSTATE_STRUCT_ARRAY(env.pmu_fixed_ctrs, RISCVCPU, 2, 1,
                             vmstate_lemma_fixed_ctr, PMUFixedCtrState),
        VMSTATE_END_OF_LIST()
    }
};

const VMStateDescription vmstate_riscv_cpu = {''')
replace('target/riscv/machine.c','    .post_load = riscv_cpu_post_load,',
 '    .pre_load = riscv_cpu_lemma_pre_load,\n    .post_load = riscv_cpu_post_load,')
replace('target/riscv/machine.c','        &vmstate_pmp,',
 '        &vmstate_pmp,\n        &vmstate_lemma_counter,')

# This script is selected only by the maintained profile0.3 in qemu.nix.
# qtest has no running CPU and retains the literal-controller-only scope.
replace('hw/riscv/virt.c','#include "lemma_silicon_fast.h"',
 '#include "lemma_silicon_fast.h"\n#include "exec/icount.h"')
replace('hw/riscv/virt.c','    lemma_binding_create(machine, s->irqchip[0]);\n    lemma_fast_block_create(machine, s->irqchip[0]);',
 '''    if (!qtest_enabled()) {
        if (icount_enabled() != ICOUNT_PRECISE ||
            cpu->cfg.ext_smcntrpmf || cpu->cfg.ext_zihpm ||
            cpu->pmu_avail_ctrs != 0 ||
            LS_CLOCK_HZ != UINT64_C(100000000)) {
            error_report("silicon0.3 counters require precise icount, declared100MHz and no filtered/programmed PMU");
            exit(1);
        }
        cpu->lemma_counter_hz = LS_CLOCK_HZ;
    }
    lemma_binding_create(machine, s->irqchip[0]);
    lemma_fast_block_create(machine, s->irqchip[0]);''')

# Pinned16550 reset leaves FCR from the prior boot but clears its IIR mirror.
# Restore then derives a different guest-visible IIR from the stale FCR.
# Reset the selected machine's FIFO control to its declared reset value;
# legacy machines in this binary and unpatched0.1/0.2 stay unchanged.
replace('hw/char/serial.c','#include "hw/char/serial.h"',
 '#include "hw/char/serial.h"\n#include "hw/core/boards.h"')
replace('hw/char/serial.c','    s->iir = UART_IIR_NO_INT;',
 '''    s->iir = UART_IIR_NO_INT;
    if (object_dynamic_cast(OBJECT(qdev_get_machine()),
                            MACHINE_TYPE_NAME("lemma-silicon-fast"))) {
        s->fcr = s->fcr_vmstate = 0;
        s->recv_fifo_itl = 1;
    }''')

# Selected profile0.3 pen clock and hardware reset. Historical derivations do
# not consume this script. Keep software RESET1's loss/resync transition intact.
name = 'hw/riscv/lemma_qemu.c'
if hashlib.sha256((root/name).read_bytes()).hexdigest() != '82358469ea6f6a0378e983c4e923ab651c42c71a06a0daa227a993c1c3c83c33':
 raise SystemExit('unsupported pen adapter source identity: '+name)
replace(name,'    uint64_t ingress_sequence;',
 '''    uint64_t ingress_sequence;
    /* Aligned ACLINT reset epoch. Fractional virtual phase remains icount
     * state: ticks=floor(absolute_ns/100)-floor(reset_ns/100). */
    uint64_t pen_clock_origin_ns;''')
replace(name,'static void lemma_watchdog(void *opaque)',
 '''static uint64_t lemma_pen_clock_ticks(LemmaDevices *s)
{
    uint64_t now=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    return (now-(s->power_enabled?s->pen_clock_origin_ns:0))/100;
}
static void lemma_watchdog(void *opaque)''')
replace(name,'    lemma_pen_advance(&s->pen,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/100);',
 '    lemma_pen_advance(&s->pen,lemma_pen_clock_ticks(s));')
replace(name,'    if(s->pen.contact_deadline)timer_mod_ns(s->pen_timer,s->pen.contact_deadline*100);',
 '''    if(s->pen.contact_deadline) {
        uint64_t origin=s->power_enabled?s->pen_clock_origin_ns:0;
        uint64_t limit=(INT64_MAX-origin)/100;
        /* An admitted u64 timestamp may exceed the bounded signed virtual
         * clock. Saturate the host deadline without wrapping it into now. */
        uint64_t deadline=s->pen.contact_deadline>limit?INT64_MAX:
                          origin+s->pen.contact_deadline*100;
        timer_mod_ns(s->pen_timer,deadline);
    }''')
replace(name,'    LemmaSample sample={.time=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/100,',
 '    LemmaSample sample={.time=lemma_pen_clock_ticks(s),')
replace(name,'    if(!initial_fast)lemma_pen_write(&s->pen,LEMMA_PEN_RESET,1);',
 '''    if(s->power_enabled) {
        lemma_pen_init(&s->pen,65535,65535,s->pressure_max);
        s->pen_clock_origin_ns=(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/100*100;
    } else if(!initial_fast)lemma_pen_write(&s->pen,LEMMA_PEN_RESET,1);''')
replace(name,'    s->dirty=true;lemma_update_irqs(s);return 0;',
 '''    uint64_t now=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    /* The pinned migration stream restores timer/icount before this device.
     * Reject missing/wrapped epochs and retain the actual 100ns grid phase. */
    if(s->pen_clock_origin_ns>INT64_MAX || s->pen_clock_origin_ns%100 ||
       s->pen_clock_origin_ns>now || (!s->power_enabled && s->pen_clock_origin_ns) ||
       s->pen.last_time>UINT64_MAX-10000000 ||
       (s->pen.contact_deadline &&
        (s->pen.contact_deadline!=s->pen.last_time+10000000 || s->pen.loss)))return -EINVAL;
    s->dirty=true;lemma_update_irqs(s);return 0;''')
replace(name,'.name="lemma-paper-pen/1",.version_id=2,.minimum_version_id=2,',
 '.name="lemma-paper-pen/1",.version_id=3,.minimum_version_id=3,')
replace(name,'        VMSTATE_BOOL(power_enabled,LemmaDevices),VMSTATE_STRUCT(power,LemmaDevices,0,lemma_power_vmstate,LemmaPower),',
 '''        VMSTATE_BOOL(power_enabled,LemmaDevices),VMSTATE_STRUCT(power,LemmaDevices,0,lemma_power_vmstate,LemmaPower),
        VMSTATE_UINT64(pen_clock_origin_ns,LemmaDevices),''')
