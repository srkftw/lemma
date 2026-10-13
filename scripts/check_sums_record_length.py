#!/usr/bin/env python3
"""Host-only actual-emitted-IR negatives for document4's checked length lookup."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from core0_common import Core0Error
from audit_kernel import validate_readonly_pmp_lookup


def verify_object(directory:Path)->dict:
    from lemmasim_readonly import validate_object
    from audit_kernel import validate_backend_jump_tables
    unit=json.loads((directory/'unit.json').read_text());ir=(directory/'program.opt.ll').read_text()
    _,tables=validate_readonly_pmp_lookup(ir,unit,optimized=True)
    sections=(directory/'audit-program.o-sections.txt').read_text()
    symbols=(directory/'audit-program.o-symbols.txt').read_text()
    relocations=(directory/'audit-program.o-relocations.txt').read_text()
    raw=(directory/'audit-rodata-literals.bin').read_bytes()
    rows=validate_object(sections,symbols,relocations,{'.rodata':raw},tables,'users/notebook/program.o')['readonly_tables']
    selected=next(row for row in rows if row['source'].endswith('Notebook.openCourse'))
    kwargs={'section_text':sections,'symbol_text':symbols,'relocation_text':relocations,
        'rodata':(directory/'program-audit-rodata.bin').read_bytes(),'unit':unit,'optimized_ir':ir,
        'optimization':'O2','readonly_tables':rows,'assembly':(directory/'program-audit-companion.s').read_text(),
        'companion_symbols':(directory/'audit-program-jump-companion-symbols.txt').read_text(),
        'companion_relocations':(directory/'audit-program-jump-companion-relocations.txt').read_text(),
        'text':(directory/'program-audit-text.bin').read_bytes(),
        'companion_text':(directory/'program-audit-companion-text.bin').read_bytes()}
    baseline=validate_backend_jump_tables(**kwargs);negatives=[]
    for name,key,value in [('incompatible-config','configuration','lemmasim-bringup'),
                           ('wrong-profile','contract_version','core0-user-v0.3'),
                           ('wrong-image','image_key','arithmetic')]:
        changed=copy.deepcopy(kwargs);changed['unit'][key]=value
        try:validate_backend_jump_tables(**changed)
        except Core0Error as error:negatives.append({'name':name,'rejection':str(error)})
        else:raise Core0Error('Changed object authority admitted: '+name)
    for name,key,value in [('wrong-owner','source','Lemma.Applications.Notebook.other'),
                           ('wrong-extent','bytes',32),('wrong-content','values',[1856,2496,1856])]:
        changed=copy.deepcopy(kwargs);row=next(row for row in changed['readonly_tables'] if row['source'].endswith('Notebook.openCourse'));row[key]=value
        try:validate_backend_jump_tables(**changed)
        except Core0Error as error:negatives.append({'name':name,'rejection':str(error)})
        else:raise Core0Error('Changed actual object receipt admitted: '+name)
    changed=bytearray(raw);changed[selected['offset']+16]^=1
    try:validate_object(sections,symbols,relocations,{'.rodata':bytes(changed)},tables,'users/notebook/program.o')
    except Core0Error as error:negatives.append({'name':'actual-object-byte-corruption','rejection':str(error)})
    else:raise Core0Error('Changed actual object content admitted')
    return {'status':'PASS','scope':'Actual object bytes, local companion relocation/code binding and exact software-owner authority',
      'object_sha256':hashlib.sha256((directory/'program.o').read_bytes()).hexdigest(),
      'lookup':selected,'jump_tables':len(baseline['jump_tables']),'negative_count':len(negatives),'negatives':negatives}


def verify(directory:Path)->dict:
    unit=json.loads((directory/'unit.json').read_text())
    ir=(directory/'program.opt.ll').read_text()
    sites,tables=validate_readonly_pmp_lookup(ir,unit,optimized=True)
    lengths=[row for row in tables if row.get('literal_schema')=='document-v4-length-v1']
    if len(lengths)!=1 or lengths[0]['values']!=[1856,2496,2496]:
        raise Core0Error('Actual notebook lacks its single exact document4 length lookup')
    target=lengths[0]['function'];read=next(row['symbol'] for row in unit['functions']
        if re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])=='Lemma.Applications.Notebook.readObject')
    def changed(old:str,new:str)->str:
        if ir.count(old)!=1:raise Core0Error('Mutation stimulus is not one actual emitted site: '+old)
        return ir.replace(old,new,1)
    cases={
      'wrong-version2-size':changed('[i64 1856, i64 2496, i64 2496]','[i64 832, i64 2496, i64 2496]'),
      'wrong-version4-size':changed('[i64 1856, i64 2496, i64 2496]','[i64 1856, i64 2496, i64 1856]'),
      'wrong-version-origin':changed('%switch.tableidx = add i64 %action.call.value39, -2','%switch.tableidx = add i64 %action.call.value39, -1'),
      'weaker-bound':changed('%0 = icmp ult i64 %switch.tableidx, 3','%0 = icmp ult i64 %switch.tableidx, 4'),
      'guard-bypass':changed('br i1 %0, label %switch.lookup, label %action.if.merge.20','br i1 %0, label %action.if.merge.20, label %switch.lookup'),
      'different-read-destination':changed(f'@{read}(i64 %call22, i64 3313664, i64 %switch.load)',f'@{read}(i64 %call22, i64 3313672, i64 %switch.load)'),
      'length-ignored':changed(f'@{read}(i64 %call22, i64 3313664, i64 %switch.load)',f'@{read}(i64 %call22, i64 3313664, i64 2496)'),
      'table-reference-escape':ir+'\ndefine i64 @unadmitted_table_use() {\nentry:\n'
          +'  %p = getelementptr inbounds [3 x i64], ptr @switch.table.'+target+', i64 0, i64 0\n'
          +'  %v = load i64, ptr %p, align 8\n  ret i64 %v\n}\n',
    }
    failed=[]
    for name,mutated in cases.items():
        if mutated==ir:raise Core0Error('Unchanged mutation: '+name)
        try:validate_readonly_pmp_lookup(mutated,unit,optimized=True)
        except Core0Error as error:failed.append({'name':name,'rejection':str(error)})
        else:raise Core0Error('Mutated actual lookup admitted: '+name)
    for name,key,value in [('incompatible-configuration','configuration','lemmasim-bringup'),
                           ('kernel-role','role','kernel'),
                           ('wrong-reader-profile','contract_version','core0-user-v0.3')]:
        mutated=copy.deepcopy(unit);mutated[key]=value
        try:validate_readonly_pmp_lookup(ir,mutated,optimized=True)
        except Core0Error as error:failed.append({'name':name,'rejection':str(error)})
        else:raise Core0Error('Wrong lookup authority admitted: '+name)
    mutated=copy.deepcopy(unit)
    row=next(row for row in mutated['functions'] if row['symbol']==target);row['effects']=[]
    try:validate_readonly_pmp_lookup(ir,mutated,optimized=True)
    except Core0Error as error:failed.append({'name':'removed-effect-authority','rejection':str(error)})
    else:raise Core0Error('Removed checked read authority admitted')
    return {'schema':'lemma-document4-length-observer/1','status':'PASS',
       'scope':'Actual emitted optimized notebook lookup and independently changed negatives; not full image audit or target execution',
       'directory':str(directory),'unit_sha256':hashlib.sha256((directory/'unit.json').read_bytes()).hexdigest(),
       'llvm_sha256':hashlib.sha256((directory/'program.opt.ll').read_bytes()).hexdigest(),
       'lookup':lengths[0],'negative_count':len(failed),'negatives':failed}


def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--object',action='store_true',help='Require actual object/companion artifacts emitted by the complete per-image auditor');args=parser.parse_args()
    if args.output.exists():raise Core0Error('Refuse to replace retained output')
    try:
        result=verify(args.directory)
        if args.object:result['object']=verify_object(args.directory)
    except (Core0Error,ValueError,OSError,StopIteration) as error:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps({'status':'FAIL','error':str(error)},indent=2)+'\n')
        print('DOCUMENT4 LENGTH OBSERVER FAIL: '+str(error),file=sys.stderr);return 1
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('DOCUMENT4 LENGTH OBSERVER PASS: '+str(result['negative_count'])+' actual emitted mutations');return 0

if __name__=='__main__':raise SystemExit(main())
