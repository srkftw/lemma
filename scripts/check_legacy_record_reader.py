#!/usr/bin/env python3
"""Qualify the shared scalar reader on actual legacy Notebook LLVM exports.
This host observer never implements guest record recovery or format policy.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from core0_common import Core0Error
from audit_kernel import _ir_definition_body, _structured_ir_blocks
from check_sums_record_length import verify

SELECTIONS = {'lemmasim-silicon-power-notebook':'core0-user-v0.1',
              'lemmasim-silicon-managed-notebook':'core0-user-v0.2'}

def legacy_route(ir: str, unit: dict) -> dict:
    if unit.get('configuration') not in SELECTIONS or unit.get('role')!='user' or unit.get('image_key')!='notebook' or unit.get('contract_version')!=SELECTIONS[unit['configuration']]:
        raise Core0Error('Legacy reader qualification has incompatible exact configuration/profile/image')
    rows={re.sub(r'^_private\..*?\.[0-9]+\.','',r['source']):r for r in unit['functions']}
    prefix='Lemma.Applications.Notebook.'
    sources=[prefix+'main',prefix+'mainWithExecution',prefix+'upgradeArithmetic',prefix+'get',
             'Lemma.Documents.Mathematics.validate','Lemma.Documents.Mathematics.upgradeCurrent']
    if not all(n in rows for n in sources):raise Core0Error('Legacy route lacks actual selected source closure')
    main=rows[prefix+'main'];upgrade=rows[prefix+'upgradeArithmetic']
    if main['args']!=['u64'] or upgrade['args']!=['u64','u64']:
        raise Core0Error('Legacy source signature differs')
    mainbody=_ir_definition_body(ir,main['symbol'])
    call='call { i64, i64 } @'+rows[prefix+'mainWithExecution']['symbol']+'(i64 %arg0, i64 2)'
    if mainbody is None or mainbody.count(call)!=1 or re.search(r'i64 3\)',mainbody):
        raise Core0Error('Historical main no longer selects execution2')
    upgradebody=_ir_definition_body(ir,upgrade['symbol'])
    blocks=_structured_ir_blocks("\n".join(line.split(";",1)[0].rstrip() for line in upgradebody.splitlines()))
    branch=blocks.get('action.if.else.1',[])
    if 'i64 2, label %action.if.then.9' not in branch or 'i64 3, label %action.if.then.3' not in branch:
        raise Core0Error('Execution selection no longer binds its original exact branches')
    validate=rows['Lemma.Documents.Mathematics.validate']['symbol']
    current=rows['Lemma.Documents.Mathematics.upgradeCurrent']['symbol']
    oldvalidation=f'call {{ i64, i64 }} @{validate}(i64 3313664, i64 %arg0, i64 %arg1)'
    oldupgrade=f'call {{ i64, i64 }} @{current}(i64 3313664)'
    if sum(oldvalidation in line for line in blocks.get('action.if.then.9',[]))!=1 or sum(oldupgrade in line for line in blocks.get('action.if.else.13',[]))!=1:
        raise Core0Error('Historical selection bypassed original codec validation/upgrade')
    return {'selection':2,'validator':'Lemma.Documents.Mathematics.validate',
            'upgrade':'Lemma.Documents.Mathematics.upgradeCurrent',
            'scope':'Actual selected source and CFG; codec semantic rejection tested separately'}

def qualify(directory: Path)->dict:
    unit=json.loads((directory/'unit.json').read_text());ir=(directory/'program.opt.ll').read_text()
    result=verify(directory);result['legacy_route']=legacy_route(ir,unit)
    names={re.sub(r'^_private\..*?\.[0-9]+\.','',r['source']):r['symbol'] for r in unit['functions']}
    validate=names['Lemma.Documents.Mathematics.validate'];sums=names['Lemma.Documents.Mathematics.validateSums']
    main=names['Lemma.Applications.Notebook.main'];body=_ir_definition_body(ir,main)
    changed=ir.replace(body,body.replace('i64 2)','i64 3)'),1)
    old=f'@{validate}(i64 3313664, i64 %arg0, i64 %arg1)'
    if ir.count(old)!=1:raise Core0Error('Route corruption stimulus is not one actual call')
    cases={'historical-main-selects-sums':changed,'historical-validation-replaced':ir.replace(old,f'@{sums}(i64 3313664, i64 %arg0, i64 %arg1)',1),
           'wrong-branch-binding':ir.replace(_ir_definition_body(ir,names['Lemma.Applications.Notebook.upgradeArithmetic']),_ir_definition_body(ir,names['Lemma.Applications.Notebook.upgradeArithmetic']).replace('i64 2, label %action.if.then.9','i64 2, label %action.if.then.3',1),1)}
    negatives=[]
    for name,mutated in cases.items():
        if mutated==ir:raise Core0Error('Unchanged actual route mutation')
        try:legacy_route(mutated,unit)
        except Core0Error as error:negatives.append({'name':name,'rejection':str(error)})
        else:raise Core0Error('Changed legacy route admitted: '+name)
    for name,key,value in [('wrong-config','configuration','lemmasim-bringup'),('wrong-image','image_key','arithmetic'),('wrong-profile','contract_version','core0-user-v0.3')]:
        altered=copy.deepcopy(unit);altered[key]=value
        try:legacy_route(ir,altered)
        except Core0Error as error:negatives.append({'name':name,'rejection':str(error)})
        else:raise Core0Error('Changed legacy route authority admitted')
    result['route_negatives']=negatives
    return result

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('directories',type=Path,nargs=2);p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    if args.output.exists():raise Core0Error('Refuse to replace retained receipt')
    try:
        results=[qualify(d) for d in args.directories]
        if {r['lookup']['values'][0] for r in results}!={1856}:raise Core0Error('Reader lengths differ')
        record={'status':'PASS','schema':'lemma-legacy-record-reader-observer/1','scope':'Two genuinely emitted historical Notebook user units; corrected reader observer only, not full-image execution',
                'results':results,'observer_sha256':hashlib.sha256(Path('scripts/lemmasim_readonly.py').read_bytes()).hexdigest()}
    except (Core0Error,OSError,ValueError,StopIteration) as error:
        record={'status':'FAIL','error':str(error)}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(record,indent=2)+'\n')
    print('LEGACY RECORD READER '+record['status']+': '+str(args.output));return int(record['status']!='PASS')
if __name__=='__main__':raise SystemExit(main())
