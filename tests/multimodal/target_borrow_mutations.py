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

def exercise_number_pad(directory):
    """Use the actual audit companion, retaining the original machine pin."""
    from audit_kernel import _jump_assembly_function
    from package_notebook_target import _normalized_jump_code
    from authored_hint_target import number_pad_machine
    path=Path(directory)/'users/notebook'
    unit=json.loads((path/'unit.json').read_text())
    names={row['symbol']:canonical(row['source'])for row in unit['functions']}
    symbol=next(symbol for symbol,source in names.items()if source=='Lemma.Courses.NumberPad.character')
    assembly=(path/'program-audit-companion.s').read_text()
    table='.LJTI'+symbol.rsplit('_',1)[1]+'_0'
    def normalize(text):
        code,labels=_jump_assembly_function(text,symbol)
        return number_pad_machine(_normalized_jump_code(code,labels,table,names),unit,text,symbol)
    result=normalize(assembly)
    identity=hashlib.sha256(repr(result).encode()).hexdigest()
    assert identity=='282404da5329dd00a33e6cf3c980e772af3e3eab1e76b8ddda412e7ce4f828fa'
    # Locate actual paired names; do not assume a current declaration ordinal.
    code,_=_jump_assembly_function(assembly,symbol)
    first=code[21][1][1];second=code[26][1][1]
    cases=[]
    for label,changed in (
            ('wrong-register',assembly.replace(first,first.replace('(a0)','(a1)'),1)),
            ('wrong-pair',assembly.replace(first,second,1)),
            ('literal-corruption',assembly.replace('.quad\t4123376619178973524','.quad\t4123376619178973525',1))):
        assert changed!=assembly
        try:normalize(changed)
        except Core0Error as exc:cases.append({'case':label,'result':'EXPECTED_REJECTION','reason':str(exc)})
        else:raise AssertionError('accepted actual NumberPad machine negative: '+label)
    return {'scope':'actual companion name-only normalization and negatives; full object/relocation/table audit remains required',
            'assembly_sha256':hashlib.sha256(assembly.encode()).hexdigest(),'original_machine_sha256':identity,'negative_controls':cases}

def exercise_reader_guard(directory):
    from audit_kernel import _jump_assembly_guard
    path=Path(directory)/'users/notebook';unit=json.loads((path/'unit.json').read_text())
    source='Lemma.Courses.PackageReader.step'
    symbol=next(row['symbol']for row in unit['functions']if canonical(row['source'])==source)
    assembly=(path/'program-audit-companion.s').read_text()
    start=assembly.index(symbol+':');end=assembly.index('.size\t'+symbol,start)
    body=assembly[start:end];table=re.search(r'\.LJTI\d+_\d+',body)[0]
    cells=re.search(r'(?m)^'+re.escape(table)+r':\n((?:\s*\.quad\s+\.LBB\d+_\d+\s*\n)+)',assembly)[1]
    targets=re.findall(r'\.quad\s+(\.LBB\d+_\d+)',cells)
    def observe(text,configuration=unit['configuration']):
        return _jump_assembly_guard(text,symbol,table,targets,6,0,source=source,
                                    configuration=configuration,image_key='notebook')
    positive=observe(assembly);cases=[]
    for label,before,after in (
            ('bound-edge','\tbltu\ta0, a1,','\tbgeu\ta0, a1,'),
            ('index-transfer','\tmv\ta0, a1','\tmv\ta0, a2'),
            ('scale','\tslli\ta0, a0, 3','\tslli\ta0, a0, 4')):
        changed=body.replace(before,after,1);assert changed!=body
        mutated=assembly[:start]+changed+assembly[end:]
        try:observe(mutated)
        except Core0Error as exc:cases.append({'case':label,'result':'EXPECTED_REJECTION','reason':str(exc)})
        else:raise AssertionError('accepted actual Reader machine negative: '+label)
    try:observe(assembly,'unregistered-multimodal-profile')
    except Core0Error as exc:cases.append({'case':'foreign-configuration','result':'EXPECTED_REJECTION','reason':str(exc)})
    else:raise AssertionError('foreign configuration acquired Reader index rebind')
    return {'scope':'actual bounded Reader index-transfer guard and negatives only; complete source/IR/object relations remain required',
            'positive':positive,'negative_controls':cases}

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
            'program_sha256':hashlib.sha256(pre.encode()).hexdigest(),'positive_guards':positive,'negative_controls':cases,
            'number_pad_machine':exercise_number_pad(directory),'reader_guard':exercise_reader_guard(directory)}

if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit('usage: target_borrow_mutations.py GENUINE_BOOT_OUTPUT REPORT_JSON')
    report=exercise(sys.argv[1]);Path(sys.argv[2]).write_text(json.dumps(report,indent=2)+'\n')
    count=sum(len(part['negative_controls'])for part in (report,report['number_pad_machine'],report['reader_guard']))
    print('PASS actual Kernel9 shared-borrow/machine guards and',count,'negative controls')
