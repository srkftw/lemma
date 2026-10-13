#!/usr/bin/env python3
"""Actual retained LLVM/object mutations for modern USB descriptor admission.

This host-only qualifier preserves the original artifacts. It does not run USB,
qualify an entire image, or turn a corrected observer into the original observer.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from core0_common import Core0Error
from audit_kernel import (validate_unit, validate_usb_descriptor_lookup,
    validate_readonly_pmp_lookup, validate_backend_jump_tables,
    inspect_backend_jump_tables, _artifact_inspector, _ir_definition_body,
    alloc_section_names)
from lemmasim_readonly import validate_object


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def descriptor(ir: str, unit: dict) -> tuple[set[int],list[dict],set[str]]:
    sites,tables,removed=validate_usb_descriptor_lookup(ir,unit)
    if (len(sites),len(tables),len(removed))!=(2,2,2):
        raise Core0Error('The exact two-table descriptor authority was not admitted')
    return sites,tables,removed


def rejected(name: str, operation, negatives: list[dict]) -> None:
    try: operation()
    except Core0Error as error:
        negatives.append({'name':name,'rejection':str(error)})
    else: raise Core0Error('Changed actual descriptor authority admitted: '+name)


def verify(source: Path, output: Path, root: Path) -> dict:
    unit=json.loads((source/'unit.json').read_text());ir=(source/'program.opt.ll').read_text()
    validate_unit(unit,'kernel',configuration=unit['configuration'])
    _,descriptors,_=descriptor(ir,unit)
    config=descriptors[1];device=descriptors[0];body=_ir_definition_body(ir,config['function'])
    if body is None: raise Core0Error('Actual descriptor function body absent')
    def body_change(old: str,new: str) -> str:
        if body.count(old)!=1: raise Core0Error('Mutation is not one actual owner site: '+old)
        return ir.replace(body,body.replace(old,new,1),1)
    def global_change(old: str,new: str) -> str:
        pattern='@'+re.escape(old)+r'(?![A-Za-z0-9_.$-])'
        if len(re.findall(pattern,ir))!=2: raise Core0Error('Expected one definition and one use')
        return re.sub(pattern,'@'+new,ir)
    negatives=[]
    changes={
      'wrong-device-word':ir.replace('i64 4611686018460942610','i64 4611686018460942611',1),
      'weaker-device-bound':body_change('icmp ult i64 %arg1, 3','icmp ult i64 %arg1, 4'),
      'weaker-config-bound':body_change('icmp ult i64 %arg1, 4','icmp ule i64 %arg1, 4'),
      'wrong-index':body_change('i64 0, i64 %arg1','i64 0, i64 %arg0') if body.count('i64 0, i64 %arg1')==1 else
                    ir.replace(body,body.replace('i64 0, i64 %arg1','i64 0, i64 %arg0',1),1),
      'foreign-owner':global_change(config['global'],'switch.table.foreign_descriptor.35'),
      'extra-real-load':ir+'\ndefine i64 @unadmitted_descriptor_use() {\nentry:\n'
          +'  %p = getelementptr inbounds [4 x i64], ptr @'+config['global']+', i64 0, i64 0\n'
          +'  %v = load i64, ptr %p, align 8\n  ret i64 %v\n}\n',
    }
    for name,changed in changes.items():
        if changed==ir: raise Core0Error('Unchanged descriptor mutation: '+name)
        rejected(name,lambda changed=changed:descriptor(changed,unit),negatives)
    for name,key,value in [('wrong-role','role','user'),('wrong-profile','contract_version','core0-kernel-v0.4'),
                            ('wrong-configuration','configuration','lemmasim-silicon-power-notebook')]:
        changed=copy.deepcopy(unit);changed[key]=value
        rejected(name,lambda changed=changed:descriptor(ir,changed),negatives)
    for name,key,value in [('wrong-source-owner','source','Lemma.USB.Control.other'),
                            ('wrong-signature','args',['u64']),('unexpected-effect','effects',['virtual-read'])]:
        changed=copy.deepcopy(unit)
        row=next(row for row in changed['functions'] if row['symbol']==config['function']);row[key]=value
        rejected(name,lambda changed=changed:descriptor(ir,changed),negatives)
    renamed_name=re.sub(r'\.[0-9]+$','.935',config['global'])
    renamed=global_change(config['global'],renamed_name)
    if renamed==ir: raise Core0Error('Unchanged suffix-renaming positive stimulus')
    descriptor(renamed,unit)
    # Actual object and an independently regenerated, unlinked LLVM companion.
    output.mkdir()
    for name in ('program.o','program.opt.ll','unit.json'):shutil.copyfile(source/name,output/name)
    logs=[];inspect=_artifact_inspector(root,output,300,logs)
    sections=inspect('llvm-readelf',['-S','--wide','program.o'],'object-sections')
    symbols=inspect('llvm-readelf',['-s','--wide','program.o'],'object-symbols')
    relocations=inspect('llvm-readelf',['-r','program.o'],'object-relocations')
    _,tables=validate_readonly_pmp_lookup(ir,unit,optimized=True)
    raw={}
    for section in ('.rodata','.rodata.cst32'):
        if section in alloc_section_names(sections):
            filename=section[1:]+'.bin'
            inspect('llvm-objcopy',['-O','binary','--only-section='+section,'program.o',filename],filename)
            raw[section]=(output/filename).read_bytes()
    rows=validate_object(sections,symbols,relocations,raw,tables,'kernel/program.o')['readonly_tables']
    baseline=inspect_backend_jump_tables(inspect,output,object_file='program.o',section_text=sections,
        symbol_text=symbols,relocation_text=relocations,unit=unit,optimization='O2',readonly_tables=rows)
    kwargs=dict(section_text=sections,symbol_text=symbols,relocation_text=relocations,
      rodata=(output/'program-audit-rodata.bin').read_bytes(),unit=unit,optimized_ir=ir,
      optimization='O2',readonly_tables=rows,assembly=(output/'program-audit-companion.s').read_text(),
      companion_symbols=(output/'audit-program-jump-companion-symbols.txt').read_text(),
      companion_relocations=(output/'audit-program-jump-companion-relocations.txt').read_text(),
      text=(output/'program-audit-text.bin').read_bytes(),
      companion_text=(output/'program-audit-companion-text.bin').read_bytes())
    object_negatives=[]
    selected=[row for row in rows if row['source']=='Lemma.USB.Control.descriptorWord']
    if len(selected)!=2: raise Core0Error('Actual object descriptor owner count differs')
    for i,row in enumerate(selected):
        changed={name:bytearray(data) for name,data in raw.items()};changed[row['section']][row['offset']]^=1
        rejected('actual-descriptor-object-byte-'+str(i),
          lambda changed=changed:validate_object(sections,symbols,relocations,changed,tables,'kernel/program.o'),object_negatives)
    for name,key,value in [('wrong-role','role','user'),('wrong-profile','contract_version','core0-kernel-v0.4'),
                            ('wrong-configuration','configuration','lemmasim-silicon-power-notebook')]:
        changed=copy.deepcopy(kwargs);changed['unit'][key]=value
        rejected('object-'+name,lambda changed=changed:validate_backend_jump_tables(**changed),object_negatives)
    for name,key,value in [('foreign-owner','source','Lemma.USB.Control.foreign'),
                            ('wrong-extent','bytes',40),('wrong-values','values',[1,2,3])]:
        changed=copy.deepcopy(kwargs);row=next(row for row in changed['readonly_tables'] if row['source']=='Lemma.USB.Control.descriptorWord');row[key]=value
        rejected('object-'+name,lambda changed=changed:validate_backend_jump_tables(**changed),object_negatives)
    # Rename the actual local object symbol, re-inspect it, and compile a real
    # companion from the correspondingly renamed actual optimized LLVM.
    (output/'renamed.opt.ll').write_text(renamed)
    inspect('llvm-objcopy',['--redefine-sym=.L'+config['global']+'=.L'+renamed_name,'program.o','renamed.o'],'suffix-object-rename')
    ns=inspect('llvm-readelf',['-S','--wide','renamed.o'],'renamed-sections')
    ny=inspect('llvm-readelf',['-s','--wide','renamed.o'],'renamed-symbols')
    nr=inspect('llvm-readelf',['-r','renamed.o'],'renamed-relocations')
    _,nt=validate_readonly_pmp_lookup(renamed,unit,optimized=True)
    renamed_rows=validate_object(ns,ny,nr,raw,nt,'kernel/renamed.o')['readonly_tables']
    rename_report=inspect_backend_jump_tables(inspect,output,object_file='renamed.o',section_text=ns,
      symbol_text=ny,relocation_text=nr,unit=unit,optimization='O2',readonly_tables=renamed_rows)
    if rename_report['code_sha256']!=baseline['code_sha256']:
        raise Core0Error('Suffix-only symbol rename changed actual machine code')
    return dict(configuration=unit['configuration'],profile=unit['contract_version'],
      directory=str(source),artifacts={name:sha(source/name) for name in ('unit.json','program.opt.ll','program.o')},
      descriptor_tables=descriptors,llvm_negatives=negatives,object_negatives=object_negatives,
      suffix_rename={'status':'PASS','old':config['global'],'new':renamed_name,
        'actual_object_and_regenerated_companion':True,'code_sha256':baseline['code_sha256']},commands=logs)


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories',nargs='+',type=Path);parser.add_argument('--work-dir',required=True,type=Path)
    args=parser.parse_args();out=args.work_dir.resolve();root=Path(__file__).resolve().parents[1]
    if out.exists():raise Core0Error('Refuse to overwrite retained qualifier outputs')
    out.mkdir(parents=True);report={'schema':'lemma-modern-usb-descriptor-observer/1','status':'FAIL',
      'scope':'Actual retained LLVM/object owner and mutation qualification of the current observer; not original full audit, USB transactions or compiler correctness',
      'observer_sha256':sha(root/'scripts/audit_kernel.py'),'qualifier_sha256':sha(Path(__file__)),'variants':[]}
    try:
        for i,path in enumerate(args.directories):report['variants'].append(verify(path.resolve(),out/str(i),root))
        if sha(root/'scripts/audit_kernel.py')!=report['observer_sha256']:raise Core0Error('Observer changed during qualification')
        report['status']='PASS'
    except (Core0Error,OSError,ValueError,KeyError,StopIteration) as error:
        report['error']=str(error);print('MODERN USB DESCRIPTOR OBSERVER FAIL: '+str(error),file=sys.stderr)
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    if report['status']=='PASS':print('MODERN USB DESCRIPTOR OBSERVER PASS: '+str(len(report['variants']))+' actual variants')
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
