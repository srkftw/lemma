#!/usr/bin/env python3
"""Selected compiled call-chain/ownership audit for the expanded LemmaSim floor.

This is a bounded artifact audit, not the complete kernel acceptance/audit.
It never substitutes for machine discovery, device or notebook observations.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re

from audit_kernel import (machine_frame, parse_stack_sizes, weighted_stack_graph,
                          validate_compiled_stack, validate_stack_entries,
                          parse_definitions_and_calls, _ir_definition_body,
                          optimizer_intrinsics, validate_layout,
                          validate_fresh_descriptor_helpers)
from core0_common import Core0Error, load_json, require_tools, run_bounded, sha256, write_json

CAPACITY = 16352
ARITHMETIC_DEVELOPMENT_CONFIGURATIONS=frozenset({
    'lemmasim-silicon-power-arithmetic-oom-development',
    'lemmasim-silicon-power-arithmetic-fault-development',
    'lemmasim-silicon-power-arithmetic-stall-development',
})
POWER_CONFIGURATIONS=frozenset({'lemmasim-silicon-power-notebook',
                              'lemmasim-silicon-power-initialize',
                              'lemmasim-silicon-managed-notebook',
                              'lemmasim-silicon-managed-initialize',
                              'lemmasim-silicon-sums-notebook',
                              'lemmasim-silicon-sums-initialize',
                              'lemmasim-silicon-sums-arithmetic-oom-development'})|ARITHMETIC_DEVELOPMENT_CONFIGURATIONS
USB_CONFIGURATIONS=frozenset({'lemmasim-silicon-usb-notebook','lemmasim-silicon-usb-initialize'})
PRODUCT_CONFIGURATIONS=frozenset({'lemmasim-silicon-product-notebook'})
ADMITTED_CONFIGURATIONS=frozenset({'lemmasim-bringup','lemmasim-notebook',
    'lemmasim-initialize','lemmasim-isolation-development','lemmasim-silicon-devices',
    'lemmasim-silicon-full-notebook','lemmasim-silicon-notebook',
    'lemmasim-silicon-full-initialize','lemmasim-silicon-initialize'})|POWER_CONFIGURATIONS|USB_CONFIGURATIONS|PRODUCT_CONFIGURATIONS


def construction(unit: dict, pre_ir: str, *, expanded: bool = True) -> dict:
    product=unit.get('configuration') in PRODUCT_CONFIGURATIONS
    if product and not expanded:
        raise Core0Error('Product address spaces require the genuine expanded pool')
    names = {re.sub(r'^_private\..*?\.[0-9]+\.', '', row['source']): row['symbol']
             for row in unit['functions']}
    edges = {
        'Lemma.Kernel.Loader.allocateStack': ['Lemma.Kernel.Loader.allocateStackQuad'],
        'Lemma.Kernel.Loader.allocateStackQuad': ['Lemma.Kernel.Memory.Frames.allocateContiguous4',
                                                 'Lemma.Kernel.Loader.installStackQuad'],
        'Lemma.Kernel.Loader.installStackQuad': ['Lemma.Kernel.Loader.storedQuad'],
        'Lemma.Kernel.Loader.storedQuad': ['Lemma.Kernel.Loader.quadFrame'],
        'Lemma.Kernel.Loader.quadFrame': ['Lemma.Kernel.Loader.stackFrame'],
        'Lemma.Kernel.Loader.stackFrame': ['Lemma.Kernel.Memory.Frames.resolvePurpose',
                                          'Lemma.Kernel.Memory.Access.read64',
                                          'Lemma.Kernel.Memory.Frames.record'],
        'Lemma.Kernel.Process.validateStackAt': ['Lemma.Kernel.Loader.validateExpandedStackAt'],
        'Lemma.Kernel.Loader.validateExpandedStackAt': ['Lemma.Kernel.Loader.storedQuad'],
        'Lemma.Kernel.Loader.teardown': ['Lemma.Kernel.Loader.storedQuad',
                                        'Lemma.Kernel.Loader.releaseStackHandle'],
        'Lemma.Kernel.Memory.AddressSpace.create': ['Lemma.Kernel.Memory.AddressSpace.buildRegistry'],
        'Lemma.Kernel.Memory.AddressSpace.buildRegistry': ['Lemma.Kernel.Memory.Batch.allocate',
                                                          'Lemma.Kernel.Memory.AddressSpace.copyRegistryStep'],
        'Lemma.Kernel.Memory.AddressSpace.base': ['Lemma.Kernel.Memory.AddressSpace.validateRegistry'],
        'Lemma.Kernel.Memory.AddressSpace.destroy': ['Lemma.Kernel.Memory.AddressSpace.rollbackRegistry'],
    }
    if product:
        edges.update({
            'Lemma.Kernel.Process.initProduct':['Lemma.Kernel.Memory.AddressSpace.createProduct'],
            'Lemma.Kernel.Task.prepareManagedProduct':['Lemma.Kernel.Task.prepareProduct'],
            'Lemma.Kernel.Task.prepareProduct':['Lemma.Kernel.Loader.loadProduct'],
            'Lemma.Kernel.Loader.loadProduct':['Lemma.Kernel.Memory.AddressSpace.createProduct'],
            'Lemma.Kernel.Memory.AddressSpace.createProduct':['Lemma.Kernel.Memory.AddressSpace.buildRegistry',
                'Lemma.Kernel.Memory.AddressSpace.buildProductKernel','Lemma.Kernel.Memory.Batch.allocate'],
            'Lemma.Kernel.Memory.AddressSpace.buildProductKernel':['Lemma.Kernel.Memory.AddressSpace.buildKernel',
                'Lemma.Kernel.Memory.AddressSpace.link','Lemma.Kernel.Memory.AddressSpace.fillRange'],
        })
    required = set(edges) | {name for callees in edges.values() for name in callees}
    required |= {'Lemma.Kernel.Memory.Frames.runtimeCount', 'Lemma.Kernel.Memory.Frames.runtimeQuota',
                 'Lemma.Kernel.Memory.Frames.configure', 'Lemma.Kernel.Loader.stackCanary',
                 'Lemma.Kernel.Loader.kernelStackHandleOffset',
                 'Lemma.Kernel.Loader.kernelStackSecondHandleOffset','Lemma.Kernel.Loader.kernelStackTopOffset',
                 'Lemma.Kernel.Loader.kernelStackThirdHandleOffset',
                 'Lemma.Kernel.Loader.kernelStackFourthHandleOffset',
                 'Lemma.Kernel.Loader.kernelStackPagesOffset', 'Lemma.Kernel.Loader.kernelStackBaseOffset'}
    required |= {'Lemma.Kernel.Memory.AddressSpace.registryCount',
                 'Lemma.Kernel.Memory.AddressSpace.registryList',
                 'Lemma.Kernel.Memory.AddressSpace.expandedCapacity',
                 'Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue'}
    if not required <= names.keys():
        raise Core0Error(f'expanded-stack genuine source closure missing: {sorted(required - names.keys())}')
    for caller, callees in edges.items():
        called = parse_definitions_and_calls(_ir_definition_body(pre_ir, names[caller]))[2]
        if not {names[callee] for callee in callees} <= called:
            raise Core0Error(f'expanded-stack ownership/cleanup edge missing: {caller}')
    constants = {'kernelStackHandleOffset':2400,'kernelStackSecondHandleOffset':2480,'kernelStackTopOffset':2408,
                 'kernelStackThirdHandleOffset':2488, 'kernelStackFourthHandleOffset':2496,
                 'kernelStackPagesOffset':2504, 'kernelStackBaseOffset':2512,
                 'stackCanary':0x4c4d535441434b34}
    for short, value in constants.items():
        body = _ir_definition_body(pre_ir, names['Lemma.Kernel.Loader.' + short])
        if re.fullmatch(r'\s*entry:\s*ret i64 ' + str(value) + r'\s*', body) is None:
            raise Core0Error('expanded-stack layout constant differs from emitted value')
    for short, value in {'registryCount':1408, 'registryList':1424, 'expandedCapacity':1024}.items():
        body = _ir_definition_body(pre_ir, names['Lemma.Kernel.Memory.AddressSpace.' + short])
        if re.fullmatch(r'\s*entry:\s*ret i64 ' + str(value) + r'\s*', body) is None:
            raise Core0Error('expanded registry layout differs from emitted value')
    body = _ir_definition_body(pre_ir, names['Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue'])
    if re.fullmatch(r'\s*entry:\s*ret i64 16384\s*', body) is None:
        raise Core0Error('four-page stack source capacity differs from its emitted value')
    fresh=validate_fresh_descriptor_helpers(unit,pre_ir)
    return {'allocated_pages':4, 'allocated_bytes':16384, 'usable_bytes':CAPACITY,
            'sentinel_bytes':32, 'sentinels_are_hardware_guards':False,
            'construction':'owned-physically-contiguous-four',
            'source_symbols':{name:names[name] for name in sorted(required)},
            'fresh_descriptor_helpers':fresh,
            'initial_page_table_frames':14 if product else 13 if expanded else 11, 'leaf_registry_frames':8 if expanded else 0,
            'address_space_layout':3 if product else 2 if expanded else 1,
            'user_leaf_capacity':1024 if expanded else 32, 'owned_task_base_frames':31 if product else 30 if expanded else 18,
            'global_task_base_frames':32 if product else 31 if expanded else 19, 'user_stack_pages':4 if expanded else 2,
            'user_stack_bytes':16384 if expanded else 8192,
            'user_stack_base':0x3fffa000 if expanded else 0x3fffc000,
            'user_stack_guards':[0x3fff9000,0x3fffe000] if expanded else [0x3fffb000,0x3fffe000],
            'accounting_formula': ('14 initial tables + 8 leaf registry + 1 data + 4 user stack + 4 kernel stack; text/lazy tables additional; descriptor charged separately to owner1' if product else '13 initial tables + 8 leaf registry + 1 data + 4 user stack + 4 kernel stack; text/lazy tables additional; descriptor charged separately to owner1' if expanded else
                '11 initial tables + 1 data + 2 user stack + 4 kernel stack =18 privately owned; descriptor separately charged toowner1 makes19 global; text additional')}


def audit(build: Path, output: Path, timeout: float) -> dict:
    require_tools(['llvm-readelf', 'llvm-objdump'])
    unit = load_json(build / 'kernel/unit.json')
    if unit.get('configuration') not in ADMITTED_CONFIGURATIONS or unit.get('role') != 'kernel' or unit.get('contract_version') != ('core0-kernel-v0.7' if unit.get('configuration') in PRODUCT_CONFIGURATIONS else 'core0-kernel-v0.6' if unit.get('configuration') in USB_CONFIGURATIONS else 'core0-kernel-v0.4' if unit.get('configuration') in POWER_CONFIGURATIONS else 'core0-kernel-v0.3'):
        raise Core0Error('selected capacity audit requires exact LemmaSim kernel configuration/profile')
    commands=[]
    def invoke(argv):
        result=run_bounded(argv,cwd=build,timeout_seconds=timeout)
        commands.append({'argv':list(result.argv),'returncode':result.returncode,
                         'stdout':result.stdout.decode('utf-8',errors='replace'),
                         'stderr':result.stderr.decode('utf-8',errors='replace'),
                         'elapsed_seconds':result.elapsed_seconds})
        if result.returncode != 0:
            raise Core0Error(f'inspection command failed: {argv}')
        return commands[-1]['stdout']
    pre_ir=(build/'kernel/program.ll').read_text()
    validate_layout(load_json(build/'layout.json'),configuration=unit['configuration'])
    owned=construction(unit,pre_ir)
    frames=parse_stack_sizes(invoke(['llvm-readelf','--stack-sizes','kernel/program.o']))
    validate_compiled_stack(invoke(['llvm-objdump','-d','--no-show-raw-insn','kernel/program.o']),frames)
    startup=(build/'startup.S').read_text()
    primitives={row['primitive_symbol']:machine_frame(startup,row['primitive_symbol'])
                for row in unit['used_execution_ops'] if row['primitive_symbol'] is not None}
    if unit['used_device_ops'] or any(row['stable_id'].startswith('lemmasim.device-') for row in unit['used_execution_ops']):
        primitives['core0_io_fence']=machine_frame(startup,'core0_io_fence')
    ir=(build/'kernel/program.opt.ll').read_text()
    called=parse_definitions_and_calls(ir)[2]
    for intrinsic in called & optimizer_intrinsics(unit):
        primitives[intrinsic]=0
    graph=weighted_stack_graph(ir,frames,primitives)
    entries=validate_stack_entries(unit,graph,capacities={'machine':65536,'boot':61440,'kernel-trap':CAPACITY,'user':16384},vector_bytes=288)
    selected=[entry for entry in entries if entry['domain']=='kernel-trap']
    if len(selected)!=1 or any(entry['margin_bytes']*4<CAPACITY for entry in selected):
        raise Core0Error('expanded selected trap chain has less than 25percent usable stack headroom')
    result={'schema_version':1,'status':'PASS','scope':'selected compiled kernel call-chain/ownership audit; complete acceptance is separate',
            'build_record':({'status':'FAIL','artifact_sha256':sha256(build/'build-failure.json'),'candidate_acceptance':'FAILED_SNAPSHOT_DIAGNOSTIC_ONLY'} if (build/'build-failure.json').exists() else
                           {'status':'BUILT','artifact_sha256':sha256(build/'build.json'),'candidate_acceptance':'NOT_ESTABLISHED'} if (build/'build.json').exists() else
                           {'status':'UNKNOWN','candidate_acceptance':'NOT_ESTABLISHED'}),
            'configuration':unit['configuration'],'profile':unit['contract_version'],'ownership':owned,'entries':entries,
            'minimum_headroom_percent':25,'s_interrupt_nesting':'disabled (SIE clear); one 288byte vector',
            'machine_interrupt_stack':'separate firmware-private stack; audited separately',
            'whole_program_stack_proof':False,'physical_measurement':False,
            'artifacts':{name:sha256(build/name) for name in ['kernel/unit.json','kernel/program.ll','kernel/program.opt.ll','kernel/program.o','startup.S','image.elf']},
            'commands':commands}
    write_json(output,result)
    return result


def main():
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout',type=float,default=60)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('refuse to overwrite retained capacity evidence')
    try:
        result=audit(args.build.resolve(),args.output.resolve(),args.timeout)
        entry=[row for row in result['entries'] if row['domain']=='kernel-trap'][0]
        print(f"PASS selected trap stack: {entry['total_bytes']}/{CAPACITY} bytes; margin {entry['margin_bytes']} bytes")
        return 0
    except (Core0Error,OSError,ValueError,TypeError,KeyError) as error:
        write_json(args.output,{'schema_version':1,'status':'FAIL','scope':'selected capacity audit','reason':str(error)})
        print(f'FAIL: {error}')
        return 1

if __name__=='__main__':
    raise SystemExit(main())
