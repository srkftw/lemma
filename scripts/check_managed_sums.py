#!/usr/bin/env python3
"""Mutate actual genuine emitted sums artifacts; no target mathematical oracle."""
import argparse
import copy
import json
import re
import sys
from pathlib import Path
from core0_common import Core0Error, load_json, sha256, write_json
import managed_sums as sums
import arithmetic_sums_identity as identity


def check(directory,output):
    unit=load_json(directory/'unit.json')
    pre=(directory/'program.ll').read_text()
    post=(directory/'program.opt.ll').read_text()
    identity.contract(unit)
    receipts={stage:{'sums':sums.validate(ir,unit,optimized=optimized),
                    'implementation':identity.validate(ir,unit,optimized=optimized)}
              for stage,ir,optimized in [('pre',pre,False),('post',post,True)]}
    negative=[]
    def reject(name,fn):
        try: fn()
        except Core0Error as error:negative.append({'name':name,'error':str(error)});return
        raise Core0Error('actual mutation was admitted: '+name)
    def changed_unit(name,mutate):
        changed=copy.deepcopy(unit);mutate(changed)
        reject(name,lambda:identity.validate(pre,changed,optimized=False))
    for key in ('implementation','lowering','runtime','resources'):
        changed_unit('wrong_'+key,lambda u,key=key:u[identity.FIELD][key].__setitem__('id',u[identity.FIELD][key]['id']+1))
    changed_unit('historical_user_profile',lambda u:u.__setitem__('contract_version','core0-user-v0.2'))
    changed_unit('legacy_configuration',lambda u:u.__setitem__('configuration','lemmasim-silicon-managed-notebook'))
    effect_index=next((index for index,row in enumerate(unit['functions']) if row['effects']),None)
    if effect_index is None:raise Core0Error('actual sums unit has no authority effects')
    changed_unit('missing_effect',lambda u:u['functions'][effect_index].__setitem__('effects',[]))
    changed_unit('changed_genuine_case',lambda u:u[sums.FIELD]['functions'][0].__setitem__('genuine_ir',u[sums.FIELD]['functions'][0]['genuine_ir'].replace('case','badcase',1)))
    changed=copy.deepcopy(unit);changed[sums.FIELD]['shapes'][0]['constructors'][1]['tag']=0
    reject('duplicate_constructor_tag',lambda:sums.contract(changed))
    names={row['source']:row['symbol'] for row in unit['functions']}
    mutate=[('wrong_tag',r'(@'+re.escape(names['Lemma.User.Runtime.ManagedSums.allocate'])+r'\(i64 1, i64 )1(, i64 16)',r'\g<1>0\2'),
            ('wrong_layout',r'(@'+re.escape(names['Lemma.User.Runtime.ManagedSums.constructorTag'])+r'\(i64 %arg0, i64 1, i64 2, i64 )35(\))',r'\g<1>34\2'),
            ('wrong_projection_tag',r'(@'+re.escape(names['Lemma.User.Runtime.ManagedSums.readField'])+r'\(i64 %arg0, i64 1, i64 )1(, i64 16, i64 8\))',r'\g<1>0\2')]
    for name,pattern,replacement in mutate:
        changed,count=re.subn(pattern,replacement,pre,count=1)
        if count!=1:raise Core0Error('actual target mutation anchor absent: '+name)
        reject(name,lambda changed=changed:sums.validate(changed,unit,optimized=False))
        reject(name+'_closed_identity',lambda changed=changed:identity.validate(changed,unit,optimized=False))
    # Complete independent digest authority includes checked lifetime/runtime
    # bodies, declaration ABI, calls and the optimized semantic result.
    for stage,ir,optimized in [('pre',pre,False),('post',post,True)]:
        for source in ('Lemma.User.Runtime.Arena.release','Lemma.User.Runtime.ManagedSums.allocate'):
            symbol=names[source]
            pattern=r'(define[^\n]*@'+re.escape(symbol)+r'\([^\n]*\)[^\n]*\{)'
            changed,count=re.subn(pattern,lambda m:m[1]+'\n  %invented_contract_mutation = add i64 1, 2',ir,count=1)
            if count!=1:raise Core0Error('actual runtime body anchor absent')
            reject(stage+'_runtime_body_'+source,lambda changed=changed,optimized=optimized:identity.validate(changed,unit,optimized=optimized))
    result={'status':'PASS','scope':'Actual genuine unit pre/post implementation and emitted tag/layout/projection/runtime authority; linked RV64 execution separate',
            'inputs':{file:sha256(directory/file) for file in ('unit.json','program.ll','program.opt.ll','program.o')},
            'baseline':receipts,'rejected_actual_mutations':negative}
    write_json(output,result)
    print('MANAGED_SUMS_AUDIT:PASS',len(negative),'actual-artifact mutations; linked execution separate')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    ns=parser.parse_args()
    if ns.output.exists():raise Core0Error('output already exists')
    check(ns.directory,ns.output)
if __name__=='__main__':
    try:main()
    except (Core0Error,OSError,ValueError) as error:print('MANAGED_SUMS_AUDIT:FAIL',error,file=sys.stderr);raise SystemExit(1)
