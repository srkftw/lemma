#!/usr/bin/env python3
"""Selected profile0.4 host-only Power-v2 clock/reset adapter; historical files untouched."""
import argparse,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();root=a.source
# Pinned upstream reset lifecycle. The derived Lemma adapter is separately
# source-bound by the derivation and the preceding counter patch.
expected={'include/hw/intc/riscv_aclint.h':'6bd7dac8694d4d8012f1036c00d6b1e9e746d3d7635fc0380d100026e01f7d39','hw/intc/riscv_aclint.c':'0b2ba0e01c110141df685e16b1ce98383646f95ec426c92b23ab3313a6cb1b89','system/runstate.c':'cc0ceeffd2dd2b8c61eed5d9bf14c25d211c2259df3de537ebf8f2927c1ae7ab'}
for name,digest in expected.items():
 if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise SystemExit('unsupported Power-v2 upstream identity: '+name)
def replace(name,before,after):
 path=root/name;text=path.read_text()
 if text.count(before)!=1:raise SystemExit('Power-v2 patch anchor ambiguous: '+name+' '+before[:80])
 path.write_text(text.replace(before,after))
def transform(name,fn):
 path=root/name;path.write_text(fn(path.read_text()))
n='hw/riscv/lemma_qemu.c'
replace(n,'#include "lemma_model.h"','#include "lemma_model.h"\n#include "lemma_power_clock.h"\n#include "system/cpus.h"\n#include "hw/core/cpu.h"')
replace(n,'    LemmaPower power;','    LemmaPowerClock power_clock;\n    QEMUTimer *power_timer;\n    bool power_reset_pending,power_reset_release,power_reset_loss;')
transform(n,lambda t:t.replace('s->power.','s->power_clock.circuit.legacy.').replace('&s->power,','&s->power_clock.circuit.legacy,').replace('&s->power)','&s->power_clock.circuit.legacy)'))
replace(n,'static LemmaDevices *binding_devices;','''static LemmaDevices *binding_devices;
static void lemma_enqueue_external(LemmaDevices *,uint64_t,uint8_t,LemmaSample,Error **);
#include "lemma_power_qemu.inc.c"''')
replace(n,'{ return binding_devices && binding_devices->run_stopping; }','{ return binding_devices && (binding_devices->run_stopping || binding_devices->power_reset_pending); }')
replace(n,'    if(s->power_enabled)qemu_set_irq(s->power_irq,lemma_power_irq(&s->power_clock.circuit.legacy));',
'''    if(lemma_power2_held(s)){qemu_set_irq(s->paper_irq,0);qemu_set_irq(s->pen_irq,0);qemu_set_irq(s->power_irq,0);return;}
    if(s->power_enabled)qemu_set_irq(s->power_irq,lemma_power_irq(&s->power_clock.circuit.legacy));''')
replace(n,'    bool suspended=s->power_enabled && s->power_clock.circuit.legacy.state==1;',
 '    bool suspended=lemma_power2_held(s)||(s->power_enabled && s->power_clock.circuit.legacy.state==1);')
replace(n,'    uint64_t old=s->pen.epoch;','    if(lemma_power2_held(s))return;\n    uint64_t old=s->pen.epoch;')
replace(n,'    lemma_paper_advance(&s->paper,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));\n    lemma_trace(s,"paper-complete",s->paper.completed,s->paper.status,0);',
 '    if(lemma_power2_held(s))return;\n    lemma_paper_advance(&s->paper,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));\n    lemma_trace(s,"paper-complete",s->paper.completed,s->paper.status,0);')
replace(n,'        if(s->external_kind[from]!=1)continue;','        if(s->external_kind[from]==0)continue;')
replace(n,'s->external_kind[to]=1;','s->external_kind[to]=s->external_kind[from];')
replace(n,'    if(lemma_power_address(s,a))return size==8 && !(a&7)?lemma_power_read(&s->power_clock.circuit.legacy,a-(LS_POWER_BASE-LEMMA_PAPER_BASE)):0;',
 '    if(lemma_power_address(s,a))return lemma_power2_read(s,a-(LS_POWER_BASE-LEMMA_PAPER_BASE),size);\n    if(lemma_power2_held(s))return 0;')
start='    if(lemma_power_address(s,a)) {\n        bool accepted=false;';end='    lemma_paper_write(&s->paper,a,v,size,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));'
def powerwrite(t):
 i=t.index(start);j=t.index(end,i)
 return t[:i]+'''    if(lemma_power_address(s,a)) {
        lemma_power2_write(s,a-(LS_POWER_BASE-LEMMA_PAPER_BASE),v,size);return;
    }
    if(lemma_power2_held(s))return;
'''+t[j:]
transform(n,powerwrite)
replace(n,'    return size==8 && !(a&7) ? lemma_pen_read(&s->pen,a) : 0;','    return !lemma_power2_held(s) && size==8 && !(a&7) ? lemma_pen_read(&s->pen,a) : 0;')
replace(n,'    if(size==8 && !(a&7))lemma_pen_write(&s->pen,a,v);else s->pen.error=3;',
 '    if(lemma_power2_held(s))return;\n    if(size==8 && !(a&7))lemma_pen_write(&s->pen,a,v);else s->pen.error=3;')
def poweraccess(t):
 i=t.index('static bool lemma_power_access(');j=t.index('\nstatic MemTxResult',i)
 return t[:i]+'''static bool lemma_power_access(hwaddr a,unsigned size,bool write,uint64_t value)
{ return lemma_power_safety_access(a-(LS_POWER_BASE-LEMMA_PAPER_BASE),size,write,value); }
'''+t[j:]
transform(n,poweraccess)
replace(n,'(offset==LEMMA_POWER_COMMAND || offset==LEMMA_POWER_ACK || offset==LEMMA_POWER_CLEAR_ERROR):',
 '(offset==LEMMA_POWER_COMMAND || offset==LEMMA_POWER_ACK || offset==LEMMA_POWER_CLEAR_ERROR || offset==96 || offset==104):')
replace(n,'        if(boundary==UINT64_MAX || boundary>now)break;',
 '''        if(boundary==UINT64_MAX || boundary>now || s->power_reset_pending)break;
        /* Catch up using the previous raw levels before this sampled edge.
         * A long unsafe hold cannot retroactively qualify a newly safe input. */
        if(boundary/10>s->power_clock.edge)lemma_power2_advance(s,boundary/10-1);
        if(s->power_reset_pending)break;''')
replace(n,'        if(button_seen) {',
 '        if(button_seen) {')
replace(n,'    }\n    lemma_schedule_watchdog(s);lemma_update_irqs(s);lemma_schedule_input(s);',
 '        lemma_power2_advance(s,boundary/10);\n        if(s->power_reset_pending)break;\n    }\n    lemma_schedule_watchdog(s);lemma_update_irqs(s);lemma_schedule_input(s);')
replace(n,'            if(s->external_kind[s->external_head]==1) {',
'''            uint8_t kind=s->external_kind[s->external_head];
            if(kind==2)s->power_clock.raw_good=sample->flags;
            else if(kind==3)s->power_clock.raw_brownout=sample->flags;
            else if(kind==1) {''')
replace(n,'            lemma_power_button(&s->power_clock.circuit.legacy,button_level);','            s->power_clock.raw_button=button_level;')
replace(n,'    lemma_schedule_watchdog(s);lemma_update_irqs(s);lemma_schedule_input(s);',
 '    lemma_power2_advance(s,now/10);lemma_power2_schedule(s);\n    lemma_schedule_watchdog(s);lemma_update_irqs(s);lemma_schedule_input(s);')
# Run central clock before admitting new queue entries at the current edge;
# same-time queued entries are sampled together by its timer.
replace(n,'    s->external_count++;lemma_schedule_input(s);','    s->external_count++;lemma_schedule_input(s);')
replace(n,'    lemma_enqueue_external(s,fields[0],1,(LemmaSample){.flags=fields[1]},errp);',
 '    if(fields[0]%10){error_setg(errp,"Power-v2 button requires 10ns clock edge");return;}\n    lemma_enqueue_external(s,fields[0],1,(LemmaSample){.flags=fields[1]},errp);')
replace(n,'        timer_del(s->input_timer);s->external_head=s->external_count=0;s->recorded_next=s->recorded_count;s->input_dirty=false;',
 '        timer_del(s->input_timer);lemma_prune_pen_inputs(s);')
replace(n,'    if(s->power_enabled) {if(initial_fast)lemma_power_init(&s->power_clock.circuit.legacy);else lemma_power_warm_reset(&s->power_clock.circuit.legacy);}',
'''    if(s->power_enabled && !s->power_reset_pending) {
        bool good=s->power_clock.raw_good,brown=s->power_clock.raw_brownout;
        lemma_power_clock_reset(&s->power_clock,initial_fast?1:2,s->power_clock.raw_button,
                               (uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/10);
        if(!initial_fast){s->power_clock.raw_good=good;s->power_clock.raw_brownout=brown;}
        s->power_clock.circuit.reset_remaining=8;
    }''')
replace(n,'    s->reset_seen=true;lemma_paper_reset(&s->paper);','    s->reset_seen=true;lemma_power2_paper_reset(s);')
replace(n,'    s->run_timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,lemma_run_stop,s);',
 '    s->run_timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,lemma_run_stop,s);\n    s->power_timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,lemma_power2_timer,s);')
replace(n,'    if(s->run_timer)timer_free(s->run_timer);','    if(s->run_timer)timer_free(s->run_timer);\n    if(s->power_timer)timer_free(s->power_timer);')
replace(n,'    LemmaDevices *s=LEMMA_PAPER_PEN(obj);LemmaPower *p=&s->power;','    return lemma_get_power2_state(obj,errp);\n    LemmaDevices *s=LEMMA_PAPER_PEN(obj);LemmaPower *p=&s->power_clock.circuit.legacy;')
# Pure scalar logical state only, no timer/CPU/host reference pointers.
replace(n,'static const VMStateDescription lemma_sample_vmstate=', '''static const VMStateDescription lemma_safety_vmstate={.name="lemma-power/2",.version_id=1,.minimum_version_id=1,
    .fields=(const VMStateField[]){
        VMSTATE_STRUCT(legacy,LemmaPowerSafety,0,lemma_power_vmstate,LemmaPower),
        VMSTATE_UINT64(timeout,LemmaPowerSafety),VMSTATE_UINT64(remaining,LemmaPowerSafety),
        VMSTATE_UINT64(reset_remaining,LemmaPowerSafety),VMSTATE_UINT64(reset_epoch,LemmaPowerSafety),
        VMSTATE_BOOL(armed,LemmaPowerSafety),VMSTATE_BOOL(power_good,LemmaPowerSafety),VMSTATE_BOOL(brownout,LemmaPowerSafety),
        VMSTATE_BOOL(last_safe,LemmaPowerSafety),VMSTATE_BOOL(power_loss,LemmaPowerSafety),VMSTATE_END_OF_LIST()}};
static const VMStateDescription lemma_clock_vmstate={.name="lemma-power-clock/1",.version_id=1,.minimum_version_id=1,
    .fields=(const VMStateField[]){
        VMSTATE_STRUCT(circuit,LemmaPowerClock,0,lemma_safety_vmstate,LemmaPowerSafety),
        VMSTATE_UINT64(edge,LemmaPowerClock),VMSTATE_UINT64(write_edge,LemmaPowerClock),VMSTATE_UINT64(write_value,LemmaPowerClock),
        VMSTATE_UINT32(write_addr,LemmaPowerClock),VMSTATE_UINT32(write_size,LemmaPowerClock),
        VMSTATE_BOOL(write_pending,LemmaPowerClock),VMSTATE_BOOL(raw_good,LemmaPowerClock),VMSTATE_BOOL(raw_brownout,LemmaPowerClock),
        VMSTATE_UINT64(raw_button,LemmaPowerClock),VMSTATE_END_OF_LIST()}};
static const VMStateDescription lemma_sample_vmstate=''')
replace(n,'s->power_clock.circuit.legacy.reset_cause>2','s->power_clock.circuit.legacy.reset_cause>6')
replace(n,'s->external_kind[at]>1 || (s->external_kind[at]==1', 's->external_kind[at]>3 || (s->external_kind[at]!=0')
replace(n,'    uint64_t now=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);\n    /* The pinned migration stream restores timer/icount before this device.',
'''    uint64_t now=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if(!lemma_power_clock_validate(&s->power_clock,now/10) || s->power_reset_pending ||
       s->power_reset_release || s->power_reset_loss)return -EINVAL;
    /* The pinned migration stream restores timer/icount before this device.''')
replace(n,'    LemmaDevices *s=opaque;if(!s->power_enabled)lemma_paper_advance',
 '    LemmaDevices *s=opaque;if(s->power_reset_pending)return -EBUSY;\n    if(!s->power_enabled)lemma_paper_advance')
replace(n,'.name="lemma-paper-pen/1",.version_id=3,.minimum_version_id=3,',
 '.name="lemma-paper-pen/1",.version_id=4,.minimum_version_id=4,')
replace(n,'VMSTATE_STRUCT(power,LemmaDevices,0,lemma_power_vmstate,LemmaPower)',
 'VMSTATE_STRUCT(power_clock,LemmaDevices,0,lemma_clock_vmstate,LemmaPowerClock)')
replace(n,'        VMSTATE_UINT64(pen_clock_origin_ns,LemmaDevices),',
'''        VMSTATE_UINT64(pen_clock_origin_ns,LemmaDevices),
        VMSTATE_BOOL(power_reset_pending,LemmaDevices),VMSTATE_BOOL(power_reset_release,LemmaDevices),VMSTATE_BOOL(power_reset_loss,LemmaDevices),
        VMSTATE_TIMER_PTR(power_timer,LemmaDevices),''')
replace(n,'    object_class_property_add_str(klass,"external-button",NULL,lemma_inject_button);',
 '    object_class_property_add_str(klass,"external-button",NULL,lemma_inject_button);\n    object_class_property_add_str(klass,"external-supply",NULL,lemma_inject_supply);')
# Actual reset hook holds the CPU for the eight digital edges. Raw supply
# state and queued future wake/supply edges survive supervised-domain reset.
replace('system/runstate.c','void qemu_system_reset(ShutdownCause reason)',
 'void lemma_power2_before_system_reset(void);\nvoid lemma_power2_after_system_reset(void);\n\nvoid qemu_system_reset(ShutdownCause reason)')
replace('system/runstate.c','    cpu_synchronize_all_states();\n\n    switch (reason)',
 '    cpu_synchronize_all_states();\n    lemma_power2_before_system_reset();\n\n    switch (reason)')
replace('system/runstate.c','    vm_set_suspended(false);\n}', '    lemma_power2_after_system_reset();\n    vm_set_suspended(false);\n}')
replace('hw/core/loader.c','static void rom_reset(void *unused)',
 'bool lemma_power2_rom_reload(void);\n\nstatic void rom_reset(void *unused)')
replace('hw/core/loader.c','if (lemma_fast && lemma_fast_loaded && !rom->isrom) continue;',
 'if (lemma_fast && lemma_fast_loaded && !rom->isrom && !lemma_power2_rom_reload()) continue;')
# Block reset already retains and polls unknown irreversible outcomes. Supply
# loss removes volatile sectors only and cannot erase captured partial writes.
n='hw/riscv/lemma_fast_block.c'
replace(n,'static LemmaFastBlock *active_fast_block;', 'static LemmaFastBlock *active_fast_block;\nbool lemma_power2_domain_held(void);')
replace(n,'    switch(s->phase) {','    if(lemma_power2_domain_held())return;\n    switch(s->phase) {')
replace(n,'    LemmaFastBlock *s=opaque;bool idle=s->phase==IDLE;',
 '    LemmaFastBlock *s=opaque;bool idle=s->phase==IDLE;\n    if(lemma_power2_domain_held())return;')
replace(n,'static void block_reset(Object *obj,ResetType type) {',
'''void lemma_fast_block_power_loss(void) {
    LemmaFastBlock *s=active_fast_block;if(!s)return;
    s->pending_count=0;g_hash_table_remove_all(s->pending_index);
}
static void block_reset(Object *obj,ResetType type) {''')

# MTIMECMP is specified all-ones on supervised-domain reset, unlike the
# upstream unknown-retention rule. Clear stale timer IRQs before releasing CPU.
replace('hw/intc/riscv_aclint.c','#include "qemu/osdep.h"',
 '#include "qemu/osdep.h"\n#include "hw/core/boards.h"')
replace('hw/intc/riscv_aclint.c','    riscv_aclint_mtimer_write(mtimer, mtimer->time_base, 0, 8);',
 '''    if (object_dynamic_cast(OBJECT(qdev_get_machine()), MACHINE_TYPE_NAME("lemma-silicon-fast"))) {
        for (uint32_t i=0; i<mtimer->num_harts; i++) {
            mtimer->timecmp[i]=UINT64_MAX;timer_del(mtimer->timers[i]);qemu_irq_lower(mtimer->timer_irqs[i]);
        }
    }
    riscv_aclint_mtimer_write(mtimer, mtimer->time_base, 0, 8);''')

# Exact supervised reset-phase state, selected only for Power-v2.
replace('include/hw/intc/riscv_aclint.h','    uint64_t time_delta;',
 '    uint64_t time_delta;\n    uint64_t lemma_reset_origin_ns;')
replace('hw/intc/riscv_aclint.c','static uint64_t cpu_riscv_read_rtc_raw(uint32_t timebase_freq)',
 'bool lemma_power2_domain_held(void);\n\nstatic uint64_t cpu_riscv_read_rtc_raw(RISCVAclintMTimerState *mtimer)')
replace('hw/intc/riscv_aclint.c',
 '''    return muldiv64(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),
        timebase_freq, NANOSECONDS_PER_SECOND);''',
 '''    uint64_t now=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (object_dynamic_cast(OBJECT(qdev_get_machine()), MACHINE_TYPE_NAME("lemma-silicon-fast"))) {
        if (lemma_power2_domain_held()) return 0;
        g_assert(now>=mtimer->lemma_reset_origin_ns);
        now-=mtimer->lemma_reset_origin_ns;
    }
    return muldiv64(now,mtimer->timebase_freq,NANOSECONDS_PER_SECOND);''')
transform('hw/intc/riscv_aclint.c',lambda t:t.replace('cpu_riscv_read_rtc_raw(mtimer->timebase_freq)','cpu_riscv_read_rtc_raw(mtimer)'))
replace('hw/intc/riscv_aclint.c',
 '    riscv_aclint_mtimer_write(mtimer, mtimer->time_base, 0, 8);',
 '    mtimer->lemma_reset_origin_ns=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);\n    riscv_aclint_mtimer_write(mtimer, mtimer->time_base, 0, 8);')
replace('hw/intc/riscv_aclint.c',
 '        next = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + ns_diff;',
 '''        uint64_t now=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
        if (object_dynamic_cast(OBJECT(qdev_get_machine()), MACHINE_TYPE_NAME("lemma-silicon-fast"))) {
            g_assert(mtimer->timebase_freq==10000000 && now>=mtimer->lemma_reset_origin_ns);
            ns_diff-=(now-mtimer->lemma_reset_origin_ns)%100;
        }
        next = now + ns_diff;''')
replace('hw/intc/riscv_aclint.c','static const VMStateDescription vmstate_riscv_mtimer = {',
 '''static int lemma_mtimer_post_load(void *opaque,int version)
{
    RISCVAclintMTimerState *m=opaque;
    if (m->lemma_reset_origin_ns>(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)) return -EINVAL;
    return 0;
}
static const VMStateDescription vmstate_riscv_mtimer = {''')
replace('hw/intc/riscv_aclint.c',
 '    .name = "riscv_mtimer",\n    .version_id = 3,\n    .minimum_version_id = 3,',
 '    .name = "riscv_mtimer",\n    .version_id = 4,\n    .minimum_version_id = 4,\n    .post_load = lemma_mtimer_post_load,')
replace('hw/intc/riscv_aclint.c','            VMSTATE_UINT64(time_delta, RISCVAclintMTimerState),',
 '            VMSTATE_UINT64(time_delta, RISCVAclintMTimerState),\n            VMSTATE_UINT64(lemma_reset_origin_ns,RISCVAclintMTimerState),')
replace('hw/riscv/lemma_qemu.c',
 's->pen_clock_origin_ns=(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/100*100;',
 's->pen_clock_origin_ns=(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/10*10;')
replace('hw/riscv/lemma_qemu.c','s->pen_clock_origin_ns%100','s->pen_clock_origin_ns%10')
