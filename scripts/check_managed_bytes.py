#!/usr/bin/env python3
"""Mutate actual genuine bytes artifacts; no target mathematical authority."""
import argparse
import copy
import re
import sys
from pathlib import Path
from core0_common import Core0Error, load_json, sha256, write_json
import managed_bytes as payload
import arithmetic_bytes_identity as identity


def check(directory,output):
    unit=load_json(directory/'unit.json')
    pre=(directory/'program.ll').read_text();post=(directory/'program.opt.ll').read_text()
    receipts={stage:{'bytes':payload.validate(ir,unit,optimized=optimized),
                     'implementation':identity.validate(ir,unit,optimized=optimized)}
              for stage,ir,optimized in [('pre',pre,False),('post',post,True)]}
    if any(not all(row.values()) for row in receipts.values()):
        raise Core0Error('actual selected Bytes authority missing')
    rejected=[]
    def reject(name,fn):
        try:fn()
        except Core0Error as error:rejected.append({'name':name,'error':str(error)});return
        raise Core0Error('actual mutation was admitted: '+name)
    def metadata(name,mutate,observer=identity.contract):
        changed=copy.deepcopy(unit);mutate(changed)
        reject(name,lambda:observer(changed))
    for key in ('implementation','lowering','runtime','resources'):
        metadata('wrong_'+key,lambda u,key=key:u[identity.FIELD][key].__setitem__('id',u[identity.FIELD][key]['id']+1))
    for name,key,value in [('old_profile','contract_version','core0-user-v0.3'),
                           ('old_configuration','configuration','lemmasim-silicon-sums-notebook'),
                           ('wrong_role','role','kernel'),('wrong_image','image_key','notebook')]:
        metadata(name,lambda u,key=key,value=value:u.__setitem__(key,value))
    for key in ('maximum_payload','slots'):
        metadata('wrong_'+key,lambda u,key=key:u[payload.FIELD].__setitem__(key,u[payload.FIELD][key]+1),payload.contract)
    append_index=next(i for i,row in enumerate(unit[payload.FIELD]['functions']) if row['source']==payload.PREFIX+'appendWord')
    if 'ByteArray.push' not in unit[payload.FIELD]['functions'][append_index]['genuine_ir']:
        raise Core0Error('actual genuine push anchor absent')
    metadata('genuine_push_changed',lambda u:u[payload.FIELD]['functions'][append_index].__setitem__('genuine_ir',
        u[payload.FIELD]['functions'][append_index]['genuine_ir'].replace('ByteArray.push','ByteArray.get!',1)),payload.contract)
    names={row['source']:row['symbol'] for row in unit['functions']}
    generated=payload.GENERATED+payload.PREFIX+'appendWord'
    row_index=next(i for i,row in enumerate(unit['functions']) if row['source']==generated)
    metadata('generated_effects_removed',lambda u:u['functions'][row_index].__setitem__('effects',[]),
             lambda u:identity.validate(pre,u,optimized=False))
    metadata('generated_signature_changed',lambda u:u['functions'][row_index].__setitem__('args',['u64']),payload.contract)
    # Mutate a real consuming push call and an actual caller release. The
    # complete identity pin independently detects semantic changes below the
    # generated call boundary in each emitted optimization stage.
    push=names['Lemma.User.Runtime.ManagedBytes.push']
    get=names['Lemma.User.Runtime.ManagedBytes.get']
    from audit_kernel import _ir_definition_body
    append_body=_ir_definition_body(pre,names[generated])
    altered,count=re.subn('@'+re.escape(push)+r'\(', '@'+get+'(',append_body,count=1)
    if count!=1:raise Core0Error('actual consuming-push anchor absent')
    changed=pre.replace(append_body,altered,1)
    reject('push_replaced_by_read',lambda:payload.validate(changed,unit,optimized=False))
    reject('push_replaced_by_read_identity',lambda:identity.validate(changed,unit,optimized=False))
    reject('unreviewed_global_state',lambda:identity.validate(
        '@unreviewed = private global i64 0\n'+pre,unit,optimized=False))
    for stage,ir,optimized in [('pre',pre,False),('post',post,True)]:
        source='Lemma.User.Runtime.ManagedBytes.get';symbol=names[source]
        body=_ir_definition_body(ir,symbol)
        altered,count=re.subn(r'\bicmp ult\b','icmp ule',body,count=1)
        if count!=1:raise Core0Error('actual byte-bound anchor absent: '+stage)
        reject(stage+'_inclusive_byte_bound',lambda altered=altered,ir=ir,body=body,optimized=optimized:
               identity.validate(ir.replace(body,altered,1),unit,optimized=optimized))
        source='Lemma.User.Runtime.Arena.release';symbol=names[source]
        pattern=r'(define[^\n]*@'+re.escape(symbol)+r'\([^\n]*\)[^\n]*\{)'
        altered,count=re.subn(pattern,lambda m:m[1]+'\n  %changed_lifetime_body = add i64 1, 2',ir,count=1)
        if count!=1:raise Core0Error('actual lifetime anchor absent: '+stage)
        reject(stage+'_lifetime_body',lambda altered=altered,optimized=optimized:
               identity.validate(altered,unit,optimized=optimized))
    result={'status':'PASS','scope':'Actual genuine Unit4 pre/post ordinary ByteArray and complete allocation/access/lifetime/version authority; isolated RV64 execution separate',
            'inputs':{file:sha256(directory/file) for file in ('unit.json','program.ll','program.opt.ll','program.o')},
            'baseline':receipts,'rejected_actual_mutations':rejected}
    write_json(output,result)
    print('MANAGED_BYTES_AUDIT:PASS',len(rejected),'actual artifact mutations; linked execution separate')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    ns=parser.parse_args()
    if ns.output.exists():raise Core0Error('output already exists')
    check(ns.directory,ns.output)
if __name__=='__main__':
    try:main()
    except (Core0Error,OSError,ValueError) as error:print('MANAGED_BYTES_AUDIT:FAIL',error,file=sys.stderr);raise SystemExit(1)
