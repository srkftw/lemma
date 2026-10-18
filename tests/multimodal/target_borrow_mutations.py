"""Negative observer checks over actual produced Kernel9 LLVM, never fabricated positives.

Call with a genuine complete boot output. No target compilation/execution claim.
Patching the outer pin validator in two negative-only cases isolates the unchanged
independent lower-body/private-caller checks; production never bypasses pins.
"""
from pathlib import Path
import hashlib
import json
import re
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from core0_common import Core0Error
from audit_kernel import (_ir_definition_body,validate_fresh_descriptor_helpers,
                          validate_capability_header_helpers,validate_task_capture_borrow,
                          validate_surface_read_page_borrow)
from ipc_poll_borrow import validate_reachable_helpers
import multimodal_target as target
from paper_next import canonical

def exercise(directory):
    directory=Path(directory);unit=json.loads((directory/'kernel/unit.json').read_text())
    pre=(directory/'kernel/program.ll').read_text();rows={canonical(r['source']):r for r in unit['functions']}
    positive={}
    for function in (validate_fresh_descriptor_helpers,validate_capability_header_helpers,
                     validate_reachable_helpers,validate_task_capture_borrow,validate_surface_read_page_borrow):
        positive[function.__name__]=function(unit,pre)
    cases=[]
    def reject(label,operation):
        try:operation()
        except Core0Error as exc:cases.append({'case':label,'result':'EXPECTED_REJECTION','reason':str(exc)})
        else:raise AssertionError('accepted produced-LLVM negative: '+label)
    source='Lemma.Kernel.Capability.requireActiveAt'
    body=_ir_definition_body(pre,rows[source]['symbol'])
    changed=re.sub(r'ret \{ i64, i64 \} [^\n]+','ret { i64, i64 } zeroinitializer',body,count=1)
    assert changed!=body
    mutated=pre.replace(body,changed,1)
    reject('actual-body-corruption-full-corpus',lambda:target.capability_header_borrow(mutated,unit))
    with patch.object(target,'validate',return_value={'negative_only_pin_bypass':True}):
        reject('actual-body-corruption-independent-old-body',lambda:target.capability_header_borrow(mutated,unit))
        console='Lemma.Kernel.Console.record';body=_ir_definition_body(pre,rows[console]['symbol'])
        extra='  %negative.borrow = call { i64, i64 } @'+rows['Lemma.Kernel.Capability.lookupAt']['symbol']+'(i64 0, i64 0, i64 0, i64 0, i64 0)\n'
        changed=re.sub(r'(?m)^(  ret [^\n]+)$',lambda m:extra+m[1],body,count=1);assert changed!=body
        mutated=pre.replace(body,changed,1)
        reject('actual-foreign-private-caller-independent',lambda:target.capability_header_borrow(mutated,unit))
    return {'schema':'lemma-multimodal-shared-borrow-observation/1','status':'PASS',
            'scope':'actual produced-LLVM source/CFG observer positives and negatives only; no guest execution or full artifact audit',
            'input':str(directory),'unit_sha256':hashlib.sha256((directory/'kernel/unit.json').read_bytes()).hexdigest(),
            'program_sha256':hashlib.sha256(pre.encode()).hexdigest(),'positive_guards':positive,'negative_controls':cases}

if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit('usage: target_borrow_mutations.py GENUINE_BOOT_OUTPUT REPORT_JSON')
    report=exercise(sys.argv[1]);Path(sys.argv[2]).write_text(json.dumps(report,indent=2)+'\n')
    print('PASS actual Kernel9 shared-borrow guards and',len(report['negative_controls']),'negative controls')
