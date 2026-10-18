#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Adapt the real upstream QEMU Wasm64 port to the maintained controller bridge.

Run after apply_qemu.py, patch_counter_clock.py and patch_uart_ingress.py.
The native QEMU tree is never edited. Every required anchor is fail-closed.
"""
from pathlib import Path
import argparse,hashlib,json,shutil

EXPORTS='addFunction,removeFunction,TTY,FS,ccall,UTF8ToString'

def apply(source,control):
    source,control=Path(source).resolve(),Path(control).resolve()
    if (source/'VERSION').read_text().strip()!='11.1.1':raise ValueError('Wasm64 TCI patch requires exact QEMU11.1.1')
    changed={}
    def replace(name,old,new,count=1):
        p=source/name;text=p.read_text()
        if text.count(old)!=count:raise ValueError('Wasm host source anchor differs: '+name)
        p.write_text(text.replace(old,new));changed[name]={'before_sha256':changed.get(name,{}).get('before_sha256',hashlib.sha256(text.encode()).hexdigest()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    replace('meson.build',"enable_cpp = host_os == 'windows' or get_option('plugins')","enable_cpp = host_os in ['windows', 'emscripten'] or get_option('plugins')")
    replace('include/qemu/osdep.h','#define QEMU_OSDEP_H\n','#define QEMU_OSDEP_H\n\n/* Emscripten SDK6 exposes __EMSCRIPTEN__; retain upstream Wasm branches. */\n#if defined(__EMSCRIPTEN__) && !defined(EMSCRIPTEN)\n#define EMSCRIPTEN __EMSCRIPTEN__\n#endif\n')
    replace('configs/meson/emscripten.txt',"-sEXPORTED_RUNTIME_METHODS=addFunction,removeFunction,TTY,FS",'-sEXPORTED_RUNTIME_METHODS='+EXPORTS,count=2)
    replace('hw/riscv/lemma_qemu.c','static void lemma_realize(DeviceState *dev,Error **errp)','#include "lemma_browser_control.inc.c"\n\nstatic void lemma_realize(DeviceState *dev,Error **errp)')
    replace('hw/riscv/lemma_qemu.c','    lemma_load_input(s,errp);\n','    lemma_load_input(s,errp);\n    lemma_browser_control_init();\n')
    out=source/'hw/riscv/lemma_browser_control.inc.c';shutil.copyfile(control,out)
    changed['hw/riscv/lemma_browser_control.inc.c']={'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
    config=source/'configs/devices/riscv64-softmmu/lemma.mak'
    if config.exists():raise ValueError('Preexisting private device config rejected')
    config.write_text('CONFIG_RISCV_VIRT=y\n');changed[str(config.relative_to(source))]={'sha256':hashlib.sha256(config.read_bytes()).hexdigest()}
    return {'schema':'lemma-tci-host-patch/1','qemu':'11.1.1','abi':'lemma-qemu-wasm-control/1','changed':changed,'scope':'Host-only Wasm64 TCI CPU, actual maintained controllers, bounded QMP/presentation bridge. No target implementation or exact RTL timing claim.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--control',type=Path,default=Path(__file__).with_name('lemma_browser_control.inc.c'));p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    data=apply(a.source,a.control);a.report.write_text(json.dumps(data,indent=2)+'\n')
if __name__=='__main__':main()
