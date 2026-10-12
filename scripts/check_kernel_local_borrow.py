#!/usr/bin/env python3
"""Focused fail-closed mutations of a genuinely elaborated transfer probe.

Generate input with tests/kernel/LocalAuthorityCompile.lean. This checks compiler
observations; finite-RAM fixtures and full guest execution remain separate.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
from audit_kernel import (validate_surface_read_page_borrow, validate_task_capture_borrow,
                          _ir_definition_body)
from core0_common import Core0Error


def check(probe: Path, output: Path) -> None:
    if output.exists(): raise Core0Error('refusing to overwrite local borrow evidence')
    unit_path=probe/'transfer-unit.json';ir_path=probe/'transfer.ll'
    unit=json.loads(unit_path.read_text());ir=ir_path.read_text()
    names={re.sub(r'^_private\..*?\.[0-9]+\.','',r['source']):r['symbol'] for r in unit['functions']}
    reports={'capture':validate_task_capture_borrow(unit,ir),
             'surface':validate_surface_read_page_borrow(unit,ir)}
    def mutate(source, old, new):
        body=_ir_definition_body(ir,names[source])
        if body.count(old)!=1: raise Core0Error('mutation does not identify exactly one genuine source site')
        return ir.replace(body,body.replace(old,new))
    d='Lemma.Platform.LemmaSim.DeviceService.';u='Lemma.Kernel.Memory.UserCopy.';t='Lemma.Kernel.Task.'
    mutations=[]
    # Actual fresh result substitution, descriptor alias admission, write/schedule
    # insertion, missing live row scan, context overlap and stale stack top.
    body=_ir_definition_body(ir,names[d+'uploadBorrowed'])
    borrowed=re.search(r'call \{ i64, i64 \} @'+re.escape(names[u+'copyFromUserReusingReadPage'])+r'\(([^\n]*)\)',body)[1]
    args=borrowed.split(', ')
    for label,index,new in [('different-descriptor',0,'i64 %arg1'),('fabricated-alias',2,'i64 0'),
                            ('different-reference',1,'i64 %arg2'),('unowned-handle',4,'i64 0')]:
        changed=args.copy();changed[index]=new
        mutations.append((label,validate_surface_read_page_borrow,
            mutate(d+'uploadBorrowed','@'+names[u+'copyFromUserReusingReadPage']+'('+borrowed+')',
                '@'+names[u+'copyFromUserReusingReadPage']+'('+', '.join(changed)+')')))
    wrapper=_ir_definition_body(ir,names[d+'upload'])
    alias=re.search(r'icmp eq i64 (%[\w.$-]+), %arg0',wrapper)[0]
    mutations.append(('descriptor-alias-bypass',validate_surface_read_page_borrow,
        mutate(d+'upload',alias,alias.replace('%arg0','%arg1'))))
    mutations.append(('intervening-write',validate_surface_read_page_borrow,
        mutate(d+'uploadBorrowed','entry:\n','entry:\n  %unexpected = call { i64, i64 } @evil_write(i64 %arg0)\n')))
    mutations.append(('removed-page-bound',validate_surface_read_page_borrow,
        mutate(u+'copyFromUserReusingReadPage','icmp ule i64 %arg6,','icmp uge i64 %arg6,')))
    capture=_ir_definition_body(ir,names[t+'capture'])
    top=re.search(r'add i64 %arg1, 288',capture)[0]
    mutations.append(('wrong-stack-top',validate_task_capture_borrow,mutate(t+'capture',top,top.replace('288','280'))))
    base='@'+names['Lemma.Kernel.Memory.AddressSpace.base']+'(i64 %arg0)'
    mutations.append(('different-capture-descriptor',validate_task_capture_borrow,
        mutate(t+'capture',base,base.replace('%arg0','%arg1'))))
    sanitizer=_ir_definition_body(ir,names[t+'contextAt'])
    write=re.search(r'@'+re.escape(names['Lemma.Kernel.Memory.Access.write64'])+r'\(i64 ([^,\n]+), i64 8589934624\)',sanitizer)[0]
    mutations.append(('wrong-status-sanitization',validate_task_capture_borrow,
        mutate(t+'contextAt',write,write.replace('8589934624','8589934880'))))
    scan=_ir_definition_body(ir,names[t+'findStep'])
    state=re.search(r'icmp ult i64 [^\n]+',scan)[0]
    mutations.append(('removed-live-row-state-bound',validate_task_capture_borrow,
        mutate(t+'findStep',state,state.replace('icmp ult','icmp ule'))))
    rejected=[]
    for label,validator,changed in mutations:
        try: validator(unit,changed)
        except Core0Error: rejected.append(label)
        else: raise Core0Error('local borrow mutation escaped: '+label)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'status':'PASS','scope':'genuine maintained Lean checked-lowering local borrow guards and negative mutations; no guest-execution claim',
        'inputs':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (unit_path,ir_path)},
        'guards':reports,'rejected_mutations':rejected},indent=2)+'\n')
    print('KERNEL_LOCAL_BORROW:PASS '+str(len(rejected))+' actual compiled mutation negatives')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--probe',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();check(args.probe,args.output)
