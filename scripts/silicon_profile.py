#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Deterministic silicon binding generation; no guest policy lives here."""
from __future__ import annotations
import argparse, hashlib, json, struct, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'sim/profiles/lemma-silicon-dev-0.1.0.json'
FULL_PROFILE = ROOT / 'sim/profiles/lemma-silicon-dev-0.2.0.json'
POWER_PROFILE = ROOT / 'sim/profiles/lemma-silicon-dev-0.3.0.json'
SAFETY_PROFILE = ROOT / 'sim/profiles/lemma-silicon-dev-0.4.0.json'
BLE_PROFILE = ROOT / 'sim/profiles/lemma-silicon-dev-0.5.0.json'
USB_PROFILE = ROOT / 'sim/profiles/lemma-silicon-dev-0.6.0.json'
PRODUCT_PROFILE = ROOT / 'sim/profiles/lemma-silicon-dev-0.7.0.json'
USB_NEXT_PROFILE = ROOT / 'sim/profiles/lemma-silicon-dev-0.8.0.json'
PRODUCT_NEXT_PROFILE = ROOT / 'sim/profiles/lemma-silicon-dev-0.9.0.json'
PRODUCT_EXECUTED_PROFILE = ROOT / 'sim/profiles/lemma-silicon-dev-0.10.0.json'
USB_WIRE_PROFILE = ROOT / 'sim/profiles/lemma-silicon-dev-0.11.0.json'
WIFI_COMMON_PROFILE = ROOT / 'sim/profiles/lemma-silicon-dev-0.12.0.json'
USB_CLOCKED_PROFILE = ROOT / 'sim/profiles/lemma-silicon-dev-0.13.0.json'

def profile(name=None):
    path = profile_path(name)
    p = json.loads(path.read_text())
    if p['schema_version'] != 1 or p['profile'] != (name or 'lemma-silicon-dev/0.1.0'):
        raise ValueError('unsupported silicon binding')
    if p['ram_base'] + p['ram_bytes'] != p['dtb_base'] + p['dtb_reserve_bytes']:
        raise ValueError('silicon RAM/DTB bounds contradict')
    expected = (0x82000000,0x2000000,8192,8192) if path in (FULL_PROFILE,POWER_PROFILE,SAFETY_PROFILE,BLE_PROFILE,USB_PROFILE,PRODUCT_PROFILE,USB_NEXT_PROFILE,PRODUCT_NEXT_PROFILE,PRODUCT_EXECUTED_PROFILE,USB_WIRE_PROFILE,WIFI_COMMON_PROFILE,USB_CLOCKED_PROFILE) else (0x82000000,0x400000,1024,128)
    if (p['frame_pool_base'],p['frame_pool_bytes'],p['frame_count'],p['frame_quota']) != expected:
        raise ValueError('silicon development allocator binding differs')
    if p['frame_count']*4096 != p['frame_pool_bytes']:
        raise ValueError('silicon frame count does not describe its memory window')
    if path == BLE_PROFILE:
        if p.get('ble_enabled') != 1 or p.get('descriptor_features') != 7 or p['descriptor']['abi'] != 6 or p['plic_sources'] != 15 or p.get('power_safety') != 1:
            raise ValueError('BLE binding feature/authority fields differ')
        if p['devices'].get('ble') != dict(base=0x10010600,span=0x400,irq=15,payload_max=27,clocks_per_bit=100):
            raise ValueError('BLE fixed packet aperture differs')
    if path in (USB_PROFILE,PRODUCT_PROFILE,USB_NEXT_PROFILE,PRODUCT_NEXT_PROFILE,PRODUCT_EXECUTED_PROFILE,USB_WIRE_PROFILE,WIFI_COMMON_PROFILE,USB_CLOCKED_PROFILE):
        features,abi,irqs=(15,14,16) if path==USB_CLOCKED_PROFILE else (15,12,16) if path==USB_WIRE_PROFILE else (47,13,18) if path==WIFI_COMMON_PROFILE else (31,11,17) if path==PRODUCT_EXECUTED_PROFILE else (31,10,17) if path==PRODUCT_NEXT_PROFILE else (15,9,16) if path==USB_NEXT_PROFILE else (31,8,17) if path==PRODUCT_PROFILE else (15,7,16)
        if p.get('usb_enabled') != 1 or p.get('ble_enabled') != 1 or p.get('descriptor_features') != features or p['descriptor']['abi'] != abi or p['plic_sources'] != irqs or p.get('power_safety') != 1:
            raise ValueError('USB binding feature/authority fields differ')
        if p['devices'].get('usb') != dict(base=0x10010a00,span=0x400,irq=16,payload_max=64,endpoints=3,reset_clocks=1000000):
            raise ValueError('USB fixed packet aperture differs')
    if path in (PRODUCT_PROFILE,PRODUCT_NEXT_PROFILE,PRODUCT_EXECUTED_PROFILE):
        if p.get('boot_nv_enabled') != 1 or p['rom_bytes'] != 65536 or p['reset_vector'] != 0x1000:
            raise ValueError('product immutable-ROM binding differs')
        if p['devices'].get('boot_nv') != dict(base=0x10012000,span=0x400,irq=17,capacity_sectors=65544,sector_bytes=512):
            raise ValueError('product boot medium aperture differs')
    if path in (USB_NEXT_PROFILE,PRODUCT_NEXT_PROFILE,PRODUCT_EXECUTED_PROFILE,USB_WIRE_PROFILE,WIFI_COMMON_PROFILE,USB_CLOCKED_PROFILE):
        if p.get('paper_version')!=(3 if path in (PRODUCT_EXECUTED_PROFILE,USB_WIRE_PROFILE,WIFI_COMMON_PROFILE,USB_CLOCKED_PROFILE) else 2) or p.get('paper_stage_offset')!=3584:
            raise ValueError('Paper2 successor requires its disjoint512-byte staging alias')
        if not (p['devices']['paper']['base']+3584+512 == p['devices']['pen']['base']):
            raise ValueError('Paper2 stage must end exactly before the separate pen aperture')
    elif p.get('paper_version',1)!=1 or p.get('paper_stage_offset',2048)!=2048:
        raise ValueError('Historical paper staging binding may not acquire successor semantics')
    if path in (PRODUCT_EXECUTED_PROFILE,USB_WIRE_PROFILE,WIFI_COMMON_PROFILE,USB_CLOCKED_PROFILE) and p.get('paper_executed_registers') != dict(sequence=192,x=200,y=208,width=216,height=224,mode=232):
        raise ValueError('Paper3 executed refresh witness registers differ')
    if path==USB_CLOCKED_PROFILE:
        if (p.get('usb_phy_enabled'),p.get('usb_phy_version'),p.get('usb_phy_sample_hz'),p.get('usb_phy_bit_hz'),p.get('boot_nv_enabled',0),p['clock_hz'])!=(1,2,48000000,12000000,0,100000000):
            raise ValueError('Clocked USB PHY/controller namespace differs')
        if tuple(p.get(k) for k in ('usb_clocked_enabled','usb_clocked_quantum_hz','usb_clocked_ppm_bound','usb_clocked_cdc_version','usb_clocked_fifo_bytes','usb_clocked_packet_bytes'))!=(1,2400000000,2500,1,128,67) or p.get('usb_clocked_registers')!=dict(phy_version=176,phy_nominal_hz=184,controller_nominal_hz=192,cdc_version=200,fifo_bytes=208,packet_bytes=216):
            raise ValueError('Clocked USB timing/CDC/readonly contract differs')
    elif path in (USB_WIRE_PROFILE,WIFI_COMMON_PROFILE):
        if (p.get('usb_phy_enabled'),p.get('usb_phy_version'),p.get('usb_phy_sample_hz'),p.get('usb_phy_bit_hz'),p.get('boot_nv_enabled',0))!=(1,1,48000000,12000000,0):
            raise ValueError('USB wire binding clock/PHY/boot namespace differs')
    elif any(p.get(k,0) for k in ('usb_phy_enabled','usb_phy_version','usb_phy_sample_hz','usb_phy_bit_hz')):
        raise ValueError('historical USB profile may not acquire PHY semantics')
    if path!=USB_CLOCKED_PROFILE and any(k.startswith('usb_clocked_') for k in p):
        raise ValueError('historical binding may not acquire clocked USB semantics')
    if path==WIFI_COMMON_PROFILE:
        if (p.get('wifi_enabled'),p.get('wifi_version'),p.get('boot_nv_enabled',0),p['clock_hz'])!=(1,1,0,100000000):
            raise ValueError('CommonOFDM opt-in clock/version/NV scope differs')
        if p['devices'].get('wifi')!=dict(base=0x10013000,span=0x400,irq=18,payload_max=16,sample_hz=20000000):
            raise ValueError('CommonOFDM fixed aperture/IRQ/sample policy differs')
    elif p.get('wifi_enabled',0) or p.get('wifi_version',0) or 'wifi' in p['devices']:
        raise ValueError('historical binding may not acquire CommonOFDM semantics')
    return p

def profile_path(name=None):
    if name in (None, 'lemma-silicon-dev/0.1.0'): return PROFILE
    if name == 'lemma-silicon-dev/0.2.0': return FULL_PROFILE
    if name == 'lemma-silicon-dev/0.3.0': return POWER_PROFILE
    if name == 'lemma-silicon-dev/0.4.0': return SAFETY_PROFILE
    if name == 'lemma-silicon-dev/0.5.0': return BLE_PROFILE
    if name == 'lemma-silicon-dev/0.6.0': return USB_PROFILE
    if name == 'lemma-silicon-dev/0.7.0': return PRODUCT_PROFILE
    if name == 'lemma-silicon-dev/0.8.0': return USB_NEXT_PROFILE
    if name == 'lemma-silicon-dev/0.9.0': return PRODUCT_NEXT_PROFILE
    if name == 'lemma-silicon-dev/0.10.0': return PRODUCT_EXECUTED_PROFILE
    if name == 'lemma-silicon-dev/0.11.0': return USB_WIRE_PROFILE
    if name == 'lemma-silicon-dev/0.12.0': return WIFI_COMMON_PROFILE
    if name == 'lemma-silicon-dev/0.13.0': return USB_CLOCKED_PROFILE
    raise ValueError('unsupported silicon binding')

def configuration_profile(configuration):
    from closure_deployment import KERNEL_CONFIGURATIONS as CLOSURE_CONFIGURATIONS
    if configuration in CLOSURE_CONFIGURATIONS:return "lemma-silicon-dev/0.3.0"
    from course_await_deployment import CONFIGURATIONS as COURSE_AWAIT_CONFIGURATIONS
    if configuration in COURSE_AWAIT_CONFIGURATIONS:return "lemma-silicon-dev/0.3.0"
    if configuration in ("lemmasim-silicon-course-bulk-notebook","lemmasim-silicon-course-bulk-initialize"):return "lemma-silicon-dev/0.3.0"
    if configuration in ('lemmasim-silicon-usb-clocked-closure-retry-bulk-notebook','lemmasim-silicon-usb-clocked-closure-retry-bulk-initialize'):return 'lemma-silicon-dev/0.13.0'
    if configuration in ('lemmasim-silicon-usb-clocked-retry-bulk-notebook','lemmasim-silicon-usb-clocked-retry-bulk-initialize'):return 'lemma-silicon-dev/0.13.0'
    if configuration in ('lemmasim-silicon-usb-clocked-bulk-notebook','lemmasim-silicon-usb-clocked-bulk-initialize'):return 'lemma-silicon-dev/0.13.0'
    if configuration in ("lemmasim-silicon-wifi-common-probe","lemmasim-silicon-wifi-common-read-probe"):return "lemma-silicon-dev/0.12.0"
    if configuration in ('lemmasim-silicon-usb-wire-bulk-notebook','lemmasim-silicon-usb-wire-bulk-initialize'):return 'lemma-silicon-dev/0.11.0'
    if configuration in ('lemmasim-silicon-product-executed-bulk-notebook','lemmasim-silicon-product-executed-boot'):return 'lemma-silicon-dev/0.10.0'
    if configuration in ('lemmasim-silicon-product-next-bulk-notebook','lemmasim-silicon-product-next-boot'):return 'lemma-silicon-dev/0.9.0'
    if configuration in ('lemmasim-silicon-usb-next-bulk-notebook','lemmasim-silicon-usb-next-bulk-initialize'):return 'lemma-silicon-dev/0.8.0'
    if configuration in ('lemmasim-silicon-product-bulk-notebook','lemmasim-silicon-product-boot','lemmasim-silicon-product-notebook','lemmasim-silicon-product-initialize'):return 'lemma-silicon-dev/0.7.0'
    if configuration in ('lemmasim-silicon-usb-link-probe','lemmasim-silicon-usb-notebook','lemmasim-silicon-usb-initialize','lemmasim-silicon-usb-bulk-notebook','lemmasim-silicon-usb-bulk-initialize'):return 'lemma-silicon-dev/0.6.0'
    if configuration=='lemmasim-silicon-ble-link-probe':return 'lemma-silicon-dev/0.5.0'
    if configuration=='lemmasim-silicon-power-safety-probe':return 'lemma-silicon-dev/0.4.0'
    if configuration in ('lemmasim-silicon-string-bulk-notebook','lemmasim-silicon-string-bulk-initialize','lemmasim-silicon-string-arithmetic-oom-development','lemmasim-silicon-array-bulk-notebook','lemmasim-silicon-array-bulk-initialize','lemmasim-silicon-array-arithmetic-oom-development','lemmasim-silicon-bytes-bulk-notebook','lemmasim-silicon-bytes-bulk-initialize','lemmasim-silicon-bytes-arithmetic-oom-development','lemmasim-silicon-bulk-notebook','lemmasim-silicon-bulk-initialize','lemmasim-silicon-sums-notebook','lemmasim-silicon-sums-initialize','lemmasim-silicon-sums-arithmetic-oom-development','lemmasim-silicon-managed-notebook','lemmasim-silicon-managed-initialize','lemmasim-silicon-power-notebook','lemmasim-silicon-power-initialize','lemmasim-silicon-power-probe',
        'lemmasim-silicon-power-arithmetic-oom-development',
        'lemmasim-silicon-power-arithmetic-fault-development',
        'lemmasim-silicon-power-arithmetic-stall-development'):return 'lemma-silicon-dev/0.3.0'
    return 'lemma-silicon-dev/0.2.0' if configuration in (
        'lemmasim-silicon-full-notebook', 'lemmasim-silicon-full-initialize') else 'lemma-silicon-dev/0.1.0'

def constants(p):
    c = {k: p[k] for k in ('reset_vector','rom_bytes','entry','hart_count','ram_base','ram_bytes','dtb_base',
                           'dtb_reserve_bytes','timebase_hz','clock_hz','boot_timer_probe_ticks','pressure_max','frame_pool_base','frame_pool_bytes','frame_count','frame_quota','plic_sources')}
    c.update(width=p['geometry'][0], height=p['geometry'][1])
    c['paper_sequencer'] = p.get('paper_sequencer', 0)
    c['paper_version'] = p.get('paper_version', 1)
    c['paper_stage_offset'] = p.get('paper_stage_offset', 2048)
    if p.get('paper_version')==3:
        for k,v in p['paper_executed_registers'].items():c['paper_executed_'+k+'_offset']=v
    c['power_enabled']=p.get('power_enabled',0)
    c['power_safety']=p.get('power_safety',0)
    c['power_version']=p.get('power_version',1)
    c.update(power_base=0,power_span=0,power_irq=0)
    c.update(usb_phy_enabled=p.get('usb_phy_enabled',0),usb_phy_version=p.get('usb_phy_version',0),usb_phy_sample_hz=p.get('usb_phy_sample_hz',0),usb_phy_bit_hz=p.get('usb_phy_bit_hz',0))
    c.update({k:p.get(k,0) for k in ('usb_clocked_enabled','usb_clocked_quantum_hz','usb_clocked_ppm_bound','usb_clocked_cdc_version','usb_clocked_fifo_bytes','usb_clocked_packet_bytes')})
    if p.get('usb_clocked_enabled',0):
        for k,v in p['usb_clocked_registers'].items():c['usb_clocked_'+k+'_offset']=v
    c.update(usb_enabled=p.get('usb_enabled',0),usb_base=0,usb_span=0,usb_irq=0,usb_payload_max=0,usb_endpoints=0,usb_reset_clocks=0)
    c.update(boot_nv_enabled=p.get('boot_nv_enabled',0),boot_nv_base=0,boot_nv_span=0,boot_nv_irq=0,boot_nv_capacity_sectors=0,boot_nv_sector_bytes=0)
    c.update(wifi_enabled=p.get('wifi_enabled',0),wifi_version=p.get('wifi_version',0),wifi_base=0,wifi_span=0,wifi_irq=0,wifi_payload_max=0,wifi_sample_hz=0)
    c.update(ble_enabled=p.get('ble_enabled',0),ble_base=0,ble_span=0,ble_irq=0,ble_payload_max=0,ble_clocks_per_bit=0)
    power=p if p.get('power_safety',0) else json.loads(POWER_PROFILE.read_text())
    c['power_magic_value']=power['power_magic']
    for k,v in power['power_registers'].items():c['power_'+k+'_offset']=v
    for name, dev in p['devices'].items():
        for k, value in dev.items(): c[name+'_'+k] = value
    for k, value in p['descriptor'].items(): c['descriptor_'+k] = value
    return c

def power_header():
    p=json.loads(POWER_PROFILE.read_text())
    return '// Generated from sim/profiles/lemma-silicon-dev-0.3.0.json.\n#pragma once\n'+''.join(
        f'#define LEMMA_POWER_{k.upper()} {v}u\n' for k,v in p['power_registers'].items())+f'#define LEMMA_POWER_IDENTITY {p["power_magic"]}u\n'

def binding_namespace(p):
    names = {1:'Binding',2:'BindingFull',3:'BindingPower',4:'BindingSafety',
             5:'BindingBLE',6:'BindingUSB',7:'BindingProduct',8:'BindingUSBNext',
             9:'BindingProductNext',10:'BindingProductExecuted',11:'BindingUSBWire',
             12:'BindingWiFiCommon',13:'BindingUSBClocked'}
    return names[int(p['profile'].split('/')[1].split('.')[1])]


def lean_text(p):
    namespace = binding_namespace(p)
    return f'-- Generated by scripts/silicon_profile.py from the versioned binding.\nnamespace Lemma.Platform.Silicon.{namespace}\n' + ''.join(
        f'def {k} : UInt64 := {v}\n' for k,v in constants(p).items() if (k not in ('paper_version','paper_stage_offset') or p['profile'] in ('lemma-silicon-dev/0.8.0','lemma-silicon-dev/0.9.0','lemma-silicon-dev/0.10.0','lemma-silicon-dev/0.11.0','lemma-silicon-dev/0.12.0','lemma-silicon-dev/0.13.0')) and (not k.startswith('usb_phy_') or p['profile'] in ('lemma-silicon-dev/0.11.0','lemma-silicon-dev/0.12.0','lemma-silicon-dev/0.13.0')) and (not k.startswith('usb_clocked_') or p['profile']=='lemma-silicon-dev/0.13.0') and (not k.startswith('wifi_') or p['profile']=='lemma-silicon-dev/0.12.0') and (p.get('ble_enabled',0) or not k.startswith('ble_')) and (p.get('usb_enabled',0) or not k.startswith('usb_')) and (p.get('boot_nv_enabled',0) or not k.startswith('boot_nv_'))) + f'end Lemma.Platform.Silicon.{namespace}\n'

def descriptor(p, dtb_bytes):
    d=p['devices']; words=[p['descriptor']['magic'],p['descriptor']['abi'],256,0,p['ram_base'],p['ram_bytes'],
        p['frame_pool_base'],p['frame_pool_bytes'],p['timebase_hz'],d['paper']['base'],d['paper']['span'],d['paper']['irq'],
        d['pen']['base'],d['pen']['span'],d['pen']['irq'],d['block']['base'],d['block']['span'],d['block']['irq'],
        *p['geometry'],p['pressure_max'],p.get('descriptor_features',3),d['timer']['base'],d['plic']['base'],d['uart']['base'],d.get('power',{}).get('base',0),
        p['dtb_base'],dtb_bytes,p['ram_base'],33554432,p['dtb_base'],p['dtb_reserve_bytes']]
    words[3]=sum(words)&((1<<64)-1)
    return struct.pack('<32Q',*words)

def dts(p, devices=True):
    d=p['devices']; reg=lambda name:f'0x0 0x{d[name]["base"]:x} 0x0 0x{d[name]["span"]:x}'
    root=f'''/dts-v1/;
/ {{
  #address-cells = <2>; #size-cells = <2>;
  compatible = "lemma,silicon-dev-v1";
  model = "Lemma silicon development binding {p['profile'].split('/')[1]}";
  memory@80000000 {{ device_type = "memory"; reg = <0x0 0x{p['ram_base']:x} 0x0 0x{p['ram_bytes']:x}>; }};
  cpus {{ #address-cells = <1>; #size-cells = <0>; timebase-frequency = <{p['timebase_hz']}>;
    cpu@0 {{ device_type = "cpu"; reg = <0>; compatible = "riscv"; riscv,isa = "rv64im_zicsr_zifencei"; mmu-type = "riscv,sv39";
      cpu_intc: interrupt-controller {{ #interrupt-cells = <1>; interrupt-controller; compatible = "riscv,cpu-intc"; phandle = <1>; }};
    }};
  }};
  soc {{ #address-cells = <2>; #size-cells = <2>; compatible = "simple-bus"; ranges;
    serial@10000000 {{ compatible = "lemma,diagnostic-uart-v1"; reg = <{reg('uart')}>; clock-frequency = <{p['clock_hz']}>; interrupts = <10>; interrupt-parent = <&plic>; }};
    clint@2000000 {{ compatible = "sifive,clint0", "riscv,clint0"; reg = <{reg('timer')}>; interrupts-extended = <&cpu_intc 3 &cpu_intc 7>; }};
    plic: interrupt-controller@c000000 {{ compatible = "sifive,plic-1.0.0", "riscv,plic0"; reg = <{reg('plic')}>; phandle = <2>; riscv,ndev = <{p['plic_sources']}>; #interrupt-cells = <1>; #address-cells = <0>; interrupt-controller; interrupts-extended = <&cpu_intc 11 &cpu_intc 9>; }};
'''
    if devices:
        paper_version=p.get('paper_version',1)
        paper_stage=f" lemma,staging-offset = <{p['paper_stage_offset']}>;" if paper_version in (2,3) else ''
        if paper_version==3:paper_stage+=' lemma,executed-refresh = <192 200 208 216 224 232>;'
        root+=f'''    lemma-paper@10010000 {{ compatible = "lemma,paper-v{paper_version}"; reg = <{reg('paper')}>; interrupts = <12>; interrupt-parent = <&plic>; lemma,abi-version = <{paper_version}>; lemma,width = <{p['geometry'][0]}>; lemma,height = <{p['geometry'][1]}>; lemma,descriptor = <0x0 0x{p['descriptor']['base']:x} 0x0 256>;{paper_stage} }};
    lemma-pen@10011000 {{ compatible = "lemma,pen-v1"; reg = <{reg('pen')}>; interrupts = <13>; interrupt-parent = <&plic>; lemma,abi-version = <1>; lemma,max-x = <65535>; lemma,max-y = <65535>; lemma,pressure-max = <{p['pressure_max']}>; }};
    virtio_mmio@10001000 {{ compatible = "virtio,mmio"; reg = <{reg('block')}>; interrupts = <1>; interrupt-parent = <&plic>; }};
'''
    if devices and p.get('power_enabled',0):
        root+=f'''    lemma-power@10010500 {{ compatible = "lemma,power-v{p.get('power_version',1)}"; reg = <{reg('power')}>; interrupts = <14>; interrupt-parent = <&plic>; lemma,abi-version = <{p.get('power_version',1)}>; }};
'''
    if devices and p.get('ble_enabled',0):
        root+=f'''    lemma-ble@10010600 {{ compatible = "lemma,ble-packet-v1"; reg = <{reg('ble')}>; interrupts = <15>; interrupt-parent = <&plic>; lemma,abi-version = <1>; lemma,payload-max = <27>; lemma,clocks-per-bit = <100>; lemma,manual-context = <1>; }};
'''
    if devices and p.get('wifi_enabled',0):
        root+=f'''    lemma-wifi-common@10013000 {{ compatible = "lemma,wifi-common-ofdm-data-v1"; reg = <{reg('wifi')}>; interrupts = <18>; interrupt-parent = <&plic>; lemma,abi-version = <1>; lemma,payload-max = <16>; lemma,sample-hz = <20000000>; lemma,aligned-data-only = <1>; }};
'''
    if devices and p.get('usb_enabled',0):
        usb_compatible='lemma,usb-device-clocked-v2' if p.get('usb_clocked_enabled',0) else 'lemma,usb-device-wire-v1' if p.get('usb_phy_enabled',0) else 'lemma,usb-device-packet-v1'
        usb_phy=f" lemma,phy-version = <{p.get('usb_phy_version',0)}>; lemma,phy-sample-hz = <48000000>; lemma,phy-bit-hz = <12000000>; lemma,development-mac = <1>;" if p.get('usb_phy_enabled',0) else ''
        if p.get('usb_clocked_enabled',0):usb_phy+=' lemma,controller-clock-hz = <100000000>; lemma,cdc-version = <1>; lemma,cdc-fifo-capacity = <128>; lemma,packet-bytes = <67>;'
        root+=f'''    lemma-usb@10010a00 {{ compatible = "{usb_compatible}"; reg = <{reg('usb')}>; interrupts = <16>; interrupt-parent = <&plic>; lemma,abi-version = <1>; lemma,payload-max = <64>; lemma,endpoints = <3>; lemma,reset-clocks = <1000000>; lemma,decoded-packet-boundary = <{0 if p.get('usb_phy_enabled',0) else 1}>;{usb_phy} }};
'''
    if devices and p.get('boot_nv_enabled',0):
        root+=f'''    lemma-boot-nv@10012000 {{ compatible = "lemma,boot-nv-v1"; reg = <{reg('boot_nv')}>; interrupts = <17>; interrupt-parent = <&plic>; lemma,abi-version = <1>; lemma,sector-bytes = <512>; lemma,capacity-sectors = <65544>; lemma,rom-bytes = <65536>; lemma,integrity-only = <1>; }};
'''
    return root+'  };\n};\n'

def generate(out, *, devices=True, name=None):
    p=profile(name);out.mkdir(parents=True,exist_ok=True)
    (out/'platform.dts').write_text(dts(p,devices))
    subprocess.run(['dtc','-I','dts','-O','dtb','-o',str(out/'platform.dtb'),str(out/'platform.dts')],check=True,timeout=30)
    (out/'descriptor.bin').write_bytes(descriptor(p,(out/'platform.dtb').stat().st_size))
    fields=constants(p)
    package=f'// Generated from {profile_path(name).relative_to(ROOT)}\npackage lemma_silicon_binding;\n'
    package+=''.join(f'  localparam logic [63:0] {k.upper()} = 64\'h{v:016x};\n' for k,v in fields.items())
    package+='endpackage\n';(out/'lemma_silicon_binding.sv').write_text(package)
    (out/'binding.json').write_text(json.dumps({'profile':p['profile'],'profile_sha256':hashlib.sha256(profile_path(name).read_bytes()).hexdigest(),
        'devices_enabled':devices,'constants':fields},indent=2)+'\n')
    return p

def validate_evidence(dtb, source, name=None):
    # Independently recompile the authoritative DTS into a temporary output.
    import tempfile
    p=profile(name)
    if source != dts(p, True) and source != dts(p, False): raise ValueError('silicon discovery differs from exact binding')
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp);(path/'input.dts').write_text(source)
        subprocess.run(['dtc','-I','dts','-O','dtb','-o',str(path/'out.dtb'),str(path/'input.dts')],check=True,timeout=30,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if hashlib.sha256((path/'out.dtb').read_bytes()).hexdigest()!=dtb: raise ValueError('silicon DTB bytes differ from regenerated binding')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path);parser.add_argument('--compute-only',action='store_true');parser.add_argument('--check',action='store_true');parser.add_argument('--profile',default='lemma-silicon-dev/0.1.0')
    args=parser.parse_args();p=profile(args.profile);generated=ROOT/f'Lemma/Platform/Silicon/{binding_namespace(p)}.lean'
    power_abi=ROOT/'sim/host/lemma_power_abi.h'
    if args.check:
        if not power_abi.exists() or power_abi.read_text()!=power_header():raise SystemExit('FAIL: generated power ABI is stale')
        if generated.read_text()!=lean_text(p):raise SystemExit('FAIL: generated Lean silicon binding is stale')
    else:
        power_abi.write_text(power_header())
        generated.parent.mkdir(parents=True,exist_ok=True);generated.write_text(lean_text(p))
    if args.output_dir:generate(args.output_dir,devices=not args.compute_only,name=args.profile)
