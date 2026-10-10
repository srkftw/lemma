#!/usr/bin/env python3
"""Host-only generation of the fixed subordinate ABIs; no generic IDL."""
import argparse, json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
p=json.loads((root/'sim/profiles/lemmasim-virt-0.1.0.json').read_text())
rows=['/* Generated from sim/profiles/lemmasim-virt-0.1.0.json. Host only. */','#ifndef LEMMA_DEVICE_ABI_H','#define LEMMA_DEVICE_ABI_H']
for dev, regs in p['registers'].items():
    for k,v in regs.items(): rows.append(f'#define LEMMA_{dev.upper()}_{k} {v}u')
    for k in ['base','span','irq','magic']:
        rows.append(f'#define LEMMA_{dev.upper()}_{("IDENTITY" if k=="magic" else k.upper())} {p["devices"][dev][k]}u')
rows+=['#define LEMMA_DESCRIPTOR_MAGIC 1280132179u','#define LEMMA_ABI_VERSION 1u','#endif','']
text='\n'.join(rows)
a=argparse.ArgumentParser(); a.add_argument('--check',action='store_true'); args=a.parse_args()
lean_rows=['-- Generated from sim/profiles/lemmasim-virt-0.1.0.json.', '-- Fixed scalar constants only; no hardware authority is conferred by this module.', 'namespace Lemma.Platform.LemmaSim.DeviceABI', '']
for dev, regs in p['registers'].items():
    for k,v in regs.items():
        name=dev+''.join(part.title() for part in k.lower().split('_'))+'Offset'
        lean_rows.append(f'def {name} : UInt64 := {v}')
    for k in ['base','span','irq','magic']:
        name=dev+k.title()
        lean_rows.append(f'def {name} : UInt64 := {p["devices"][dev][k]}')
lean_rows += ['def descriptorMagic : UInt64 := 1280132179', 'def abiVersion : UInt64 := 1', '', 'end Lemma.Platform.LemmaSim.DeviceABI', '']
lean_text='\n'.join(lean_rows)
f=root/'sim/host/lemma_device_abi.h'
lean_file=root/'Lemma/Platform/LemmaSim/DeviceABI.lean'
if args.check:
    if not f.exists() or f.read_text()!=text: raise SystemExit('generated device ABI header is stale')
    if not lean_file.exists() or lean_file.read_text()!=lean_text: raise SystemExit('generated Lean device ABI constants are stale')
else:
    f.write_text(text)
    lean_file.parent.mkdir(parents=True,exist_ok=True)
    lean_file.write_text(lean_text)
