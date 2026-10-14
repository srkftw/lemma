"""Quarantined mutations of actual genuine page-word LLVM exports.

Positive inputs must be original elaborated unit/pre/post files. Changed LLVM
is used only to require observer rejection, never to compile or run a target.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from core0_common import Core0Error
from paper_next import canonical
from audit_kernel import _ir_definition_body,validate_surface_read_page_borrow,validate_ir
from usercopy_page_words import BASE,validate,validate_if_present


def exercise(unit, pre, post):
    rows = {canonical(row['source']):row for row in unit['functions']}
    result=[]
    positive={phase:validate(ir,unit,optimized=phase=='post') for phase,ir in [('pre',pre),('post',post)]}
    borrow=validate_surface_read_page_borrow(unit,pre)
    def reject(label,operation):
        try:operation()
        except Core0Error as error:result.append({'mutation':label,'status':'REJECTED','reason':str(error)})
        else:raise AssertionError('actual page-word mutation admitted: '+label)
    def changed(ir,suffix,old,new):
        body=_ir_definition_body(ir,rows[BASE+suffix]['symbol'])
        assert body is not None and old in body and ir.count(body)==1,(suffix,old)
        return ir.replace(body,body.replace(old,new,1),1)
    for phase,ir in [('pre',pre),('post',post)]:
        for suffix in ('copyWord','copyWordTailStep','copyWordGenericBlockStep','copyWordBlockStep',
                       'copyPageWords','copyFromPages','copyToPages','copyFromUserResult','copyFromUserReusingReadPage'):
            body=_ir_definition_body(ir,rows[BASE+suffix]['symbol'])
            old=re.search(r'(?m)^\s*ret [^\n]+$',body)[0]
            mutant=ir.replace(body,body.replace(old,old+'\n  unreachable',1),1)
            reject(phase+'-complete-body-'+suffix,lambda x=mutant,p=phase:validate(x,unit,optimized=p=='post'))
        mutant=deepcopy(unit);mutant['functions'].remove(rows[BASE+'copyPageWords'])
        reject(phase+'-partial-selected-family',lambda m=mutant,x=ir,p=phase:validate_if_present(x,m,optimized=p=='post'))
        mutant=deepcopy(unit);mutant['role']='user'
        reject(phase+'-nonkernel-escape',lambda m=mutant,x=ir,p=phase:validate_if_present(x,m,optimized=p=='post'))
        for field,value in [('args',['u64']*7),('effects',['checked-access','physical-read'])]:
            mutant=deepcopy(unit)
            row=next(r for r in mutant['functions'] if canonical(r['source'])==BASE+'copyWordBlockStep')
            row[field]=value
            reject(phase+'-signature-or-effect-'+field,lambda m=mutant,x=ir,p=phase:validate(x,m,optimized=p=='post'))
    for label,suffix,old,new in [
        ('block-stride','copyWordGenericBlockStep',', 64',', 32'),
        ('block-budget','copyPageWords',', 64',', 65'),
        ('tail-budget','copyPageWords',', 7',', 8'),
        ('tail-word-stride','copyWordTailStep',', 8',', 4'),
        ('first-read-status','copyWordGenericBlockStep','icmp eq i8','icmp ne i8'),
        ('borrow-page-equality','copyFromUserReusingReadPage','udiv i64 %arg1, 4096','udiv i64 %arg1, 2048'),
        ('borrow-scratch-span','copyFromUserReusingReadPage','i64 %arg4, i64 %arg5, i64 %arg6','i64 %arg4, i64 %arg5, i64 8'),
        ('borrow-whole-span-bound','copyFromUserReusingReadPage','icmp ule i64 %arg6','icmp ult i64 %arg6'),
        ('borrow-fallback-argument','copyFromUserReusingReadPage','i64 %arg0, i64 %arg3, i64 %arg4','i64 %arg0, i64 %arg1, i64 %arg4'),
    ]:
        mutant=changed(pre,suffix,old,new)
        reject(label,lambda x=mutant:validate_surface_read_page_borrow(unit,x))
    block=_ir_definition_body(pre,rows[BASE+'copyWordGenericBlockStep']['symbol'])
    write=rows['Lemma.Kernel.Memory.Access.write64']['symbol']
    match=re.search(r'@'+re.escape(write)+r'\(i64 (%[-\w.]+), i64 (%[-\w.]+)\)',block)
    assert match
    mutant=pre.replace(block,block.replace(match[0],match[0].replace('i64 '+match[2]+')','i64 0)'),1),1)
    reject('substitute-first-read-value',lambda:validate(mutant,unit,optimized=False))
    for suffix in ('copyWordGenericBlockStep','copyWordBlockStep'):
        for label,old,new in [('remove-volatile-load','load volatile i64','load i64'),
                              ('remove-volatile-store','store volatile i64','store i64'),
                              ('truncate-optimized-load','load volatile i64','load volatile i32')]:
            mutant=changed(post,suffix,old,new)
            reject(suffix+'-'+label,lambda x=mutant:validate(x,unit,optimized=True))
    # A new caller uses an actual existing call-site body, not an invented
    # positive LLVM program. The unchanged helper pins cannot mask its escape.
    source='Lemma.Platform.LemmaSim.DeviceService.uploadBorrowed'
    body=_ir_definition_body(pre,rows[source]['symbol'])
    original='@'+rows[BASE+'copyFromUserReadPage']['symbol']+'('
    replacement='@'+rows[BASE+'copyPageWords']['symbol']+'('
    assert original in body
    mutant=pre.replace(body,body.replace(original,replacement,1),1)
    reject('new-helper-caller-escape',lambda:validate(mutant,unit,optimized=False))
    return {'positive':positive,'surface_borrow':borrow,'rejected_actual_mutations':result}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--unit-dir',type=Path,required=True)
    p.add_argument('--legacy-unit-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    assert not a.output.exists(),'retain original qualification; use an unused output'
    unit=json.loads((a.unit_dir/'unit.json').read_text());pre=(a.unit_dir/'program.ll').read_text();post=(a.unit_dir/'program.opt.ll').read_text()
    result={'status':'FAIL','scope':__doc__,'inputs':{str(d/n):hashlib.sha256((d/n).read_bytes()).hexdigest() for d in (a.unit_dir,a.legacy_unit_dir) for n in ('unit.json','program.ll','program.opt.ll')}}
    try:
        result.update(exercise(unit,pre,post))
        old=json.loads((a.legacy_unit_dir/'unit.json').read_text());old_ir=(a.legacy_unit_dir/'program.ll').read_text()
        legacy=validate_surface_read_page_borrow(old,old_ir)
        assert 'page_word_successor' not in legacy
        result['legacy_unchanged']=legacy
        # Complete ordinary generic IR validation exercises the new hook under
        # both phases; object/full image acceptance remains a separate check.
        for phase,ir in [('pre',pre),('post',post)]:validate_ir(ir,unit,optimized=phase=='post',optimization='O2')
        result['status']='PASS_ACTUAL_PAGE_WORD_OBSERVER_AND_LEGACY'
    except BaseException as error:
        result['error']=repr(error)
        raise
    finally:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],len(result['rejected_actual_mutations']),'actual mutations rejected')


if __name__=='__main__':main()
