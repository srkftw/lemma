#!/usr/bin/env python3
"""Apply flow/1 to an exact already raw-UART/paced configured source tree.

This bounded overlay is used by independently bound incremental producers.
It does not admit their object closures or alter compiler/guest inputs.
"""
from pathlib import Path
import argparse
import shutil


def apply(source, header, implementation):
    p = source / 'hw/riscv/lemma_qemu.c'
    text = p.read_text()
    def replace(before, after):
        nonlocal text
        if text.count(before) != 1:
            raise ValueError('UART flow predecessor anchor differs: ' + before[:90])
        text = text.replace(before, after)
    replace('#include "lemma_uart_qemu.inc.c"\nstatic LemmaDevices *binding_devices;',
            'static LemmaDevices *binding_devices;\n#include "lemma_uart_qemu.inc.c"')
    replace('.name="lemma-paper-pen/1",.version_id=4,.minimum_version_id=4,',
            '.name="lemma-paper-pen/1",.version_id=5,.minimum_version_id=5,')
    replace('    if(s->uart_ingress.timer)timer_free(s->uart_ingress.timer);',
            '    if(binding_devices==s)binding_devices=NULL;\n    if(s->uart_ingress.timer)timer_free(s->uart_ingress.timer);')
    replace('    object_class_property_add_str(klass,"raw-uart-state",lemma_uart_state,NULL);',
            '    object_class_property_add_str(klass,"raw-uart-flow-version",lemma_uart_flow_version,NULL);\n'
            '    object_class_property_add_str(klass,"enable-raw-uart-flow",NULL,lemma_uart_flow_enable);\n'
            '    object_class_property_add_str(klass,"execution-state",lemma_execution_state,NULL);\n'
            '    object_class_property_add_str(klass,"raw-uart-state",lemma_uart_state,NULL);')
    fe = source / 'chardev/char-fe.c'
    fe_text = fe.read_text()
    anchor = '    qemu_notify_event();\n}\n\nvoid qemu_chr_fe_printf'
    include = '#include "chardev/char-fe.h"'
    if fe_text.count(anchor) != 1 or fe_text.count(include) != 1:
        raise ValueError('UART frontend readiness anchors differ')
    fe_text = fe_text.replace(anchor, '    lemma_raw_uart_accept_input(s);\n' + anchor)
    fe_text = fe_text.replace(include, include + '\nextern void lemma_raw_uart_accept_input(Chardev *);')
    serial = source / 'hw/char/serial.c'
    serial_text = serial.read_text()
    serial_include = '#include "chardev/char-serial.h"'
    serial_reset = '            fifo8_reset(&s->recv_fifo);'
    if serial_text.count(serial_include) != 1 or serial_text.count(serial_reset) != 1:
        raise ValueError('UART receive-FIFO reset readiness anchors differ')
    serial_text = serial_text.replace(serial_include, serial_include + '\nextern void lemma_raw_uart_accept_input(Chardev *);')
    serial_text = serial_text.replace(serial_reset, serial_reset + '\n            lemma_raw_uart_accept_input(s->chr.chr);')
    # Validate before replacing any retained source bytes. Caller works on a copy.
    for src, name in ((header, 'lemma_uart_ingress.h'), (implementation, 'lemma_uart_qemu.inc.c')):
        if not src.is_file() or src.is_symlink():
            raise ValueError('Regular frozen UART overlay required')
        shutil.copyfile(src, p.parent / name)
    p.write_text(text)
    fe.write_text(fe_text)
    serial.write_text(serial_text)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--header', type=Path, required=True)
    parser.add_argument('--implementation', type=Path, required=True)
    args = parser.parse_args()
    apply(args.source, args.header, args.implementation)
