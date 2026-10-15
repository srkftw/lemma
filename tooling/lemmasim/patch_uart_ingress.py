#!/usr/bin/env python3
"""Mechanical opt-in hooks for the pinned host UART ingress implementation.

The historical QEMU derivation and maintained base adapter are unchanged.
"""
import argparse
from pathlib import Path
import shutil

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('source', type=Path)
p.add_argument('--header', type=Path, required=True)
p.add_argument('--implementation', type=Path, required=True)
a = p.parse_args()
file = a.source / 'hw/riscv/lemma_qemu.c'
text = file.read_text()

def replace(before, after):
    global text
    if text.count(before) != 1:
        raise SystemExit('raw UART patch anchor absent/ambiguous: ' + before[:90])
    text = text.replace(before, after)

replace('#include "lemma_model.h"', '#include "lemma_model.h"\n#include "lemma_uart_ingress.h"')
replace('    bool dirty,reset_seen,run_stopping,fast_binding;',
        '    bool dirty,reset_seen,run_stopping,fast_binding;\n    LemmaUARTIngress uart_ingress;')
replace('static LemmaDevices *binding_devices;',
        '#include "lemma_uart_qemu.inc.c"\nstatic LemmaDevices *binding_devices;')
replace('    timer_del(s->timer);timer_del(s->pen_timer);',
        '    timer_del(s->timer);timer_del(s->pen_timer);\n    lemma_uart_reset(s);')
replace('    s->run_timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,lemma_run_stop,s);',
        '    s->run_timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,lemma_run_stop,s);\n'
        '    s->uart_ingress.timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,lemma_uart_poll,s);')
replace('    if(s->input)qemu_input_handler_unregister(s->input);',
        '    if(s->uart_ingress.timer)timer_free(s->uart_ingress.timer);\n'
        '    if(s->input)qemu_input_handler_unregister(s->input);')
replace('.name="lemma-paper-pen/1",.version_id=3,.minimum_version_id=3,',
        '.name="lemma-paper-pen/1",.version_id=4,.minimum_version_id=4,')
# Required state, rather than an optional subsection whose absence could
# silently reconstruct an empty ingress queue. No raw host pointer is saved.
replace('        VMSTATE_UINT32_EQUAL(width,LemmaDevices),VMSTATE_UINT32_EQUAL(height,LemmaDevices),',
        '        VMSTATE_STRUCT(uart_ingress,LemmaDevices,0,lemma_uart_state_vmstate,LemmaUARTIngress),\n'
        '        VMSTATE_UINT32_EQUAL(width,LemmaDevices),VMSTATE_UINT32_EQUAL(height,LemmaDevices),')
replace('    object_class_property_add_str(klass,"virtual-time",lemma_virtual_time,NULL);',
        '    object_class_property_add_str(klass,"raw-uart-version",lemma_uart_version,NULL);\n'
        '    object_class_property_add_str(klass,"enable-raw-uart",NULL,lemma_uart_enable);\n'
        '    object_class_property_add_str(klass,"external-uart",NULL,lemma_uart_inject);\n'
        '    object_class_property_add_str(klass,"raw-uart-state",lemma_uart_state,NULL);\n'
        '    object_class_property_add_str(klass,"virtual-time",lemma_virtual_time,NULL);')
# The base load reads globalstate but omitted its saved paused runstate.
# Reconstruct lifecycle without running/resetting the CPU or vm_stop's drain.
savevm = a.source / 'migration/savevm.c'
save_text = savevm.read_text()
boundary = '        runstate_is_running() || migration_is_running()) {'
if save_text.count(boundary) != 1:
    raise SystemExit('raw UART migration boundary anchor absent/ambiguous')
save_text = save_text.replace(boundary,
    '        (runstate_get() != RUN_STATE_PAUSED && runstate_get() != RUN_STATE_PRELAUNCH) ||\n'
    '        migration_is_running()) {')
save_anchor = ('    if (ret < 0) error_prepend(errp, "Lemma machine state restore failed: ");\n'
               '    migration_incoming_state_destroy();')
if save_text.count(save_anchor) != 1:
    raise SystemExit('raw UART migration runstate anchor absent/ambiguous')
save_text = save_text.replace(save_anchor, '''    if (ret < 0) error_prepend(errp, "Lemma machine state restore failed: ");
    if (ret >= 0) {
        if (!global_state_received() ||
            (global_state_get_runstate() != RUN_STATE_PAUSED &&
             global_state_get_runstate() != RUN_STATE_PRELAUNCH)) {
            error_setg(errp, "Lemma raw UART checkpoint requires its saved paused/prelaunch runstate");
        } else if (runstate_get() != global_state_get_runstate()) {
            if (runstate_get() != RUN_STATE_PRELAUNCH) {
                error_setg(errp, "Lemma raw UART restore candidate must start prelaunch");
            } else {
                runstate_set(RUN_STATE_FINISH_MIGRATE);
                runstate_set(global_state_get_runstate());
            }
        }
    }
    migration_incoming_state_destroy();''')
for path, name in ((a.header, 'lemma_uart_ingress.h'),
                   (a.implementation, 'lemma_uart_qemu.inc.c')):
    if not path.is_file() or path.is_symlink():
        raise SystemExit('regular maintained UART helper required')
    # Nix source paths carry a content-hash prefix; the C include names are
    # deliberately stable and must not inherit those store basenames.
    shutil.copyfile(path, file.parent/name)
file.write_text(text)
savevm.write_text(save_text)
