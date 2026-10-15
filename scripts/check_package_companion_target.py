#!/usr/bin/env python3
"""Qualify genuine six-role package/recovery4 components with unchanged generic
unit, IR, readonly and RV64 object/jump-table guards. No linked/CPU/peer claim.
"""
import argparse,copy,json,os,resource,shutil,sys,time,re
from pathlib import Path
from core0_common import Core0Error,run_bounded,sha256,require_tools
from audit_kernel import validate_unit,validate_ir,alloc_section_names,inspect_backend_jump_tables,parse_definitions_and_calls
from lemmasim_readonly import validate_object
from package_companion_target import AUTHORITY,VERSION,validate,canonical
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--component',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--timeout',type=int,default=600);a=p.parse_args()
 out=a.work_dir.resolve();origin=a.component.resolve()
 if out.exists() or not out.is_relative_to(ROOT/'build') or a.timeout!=600:p.error('unused ignored build output and predeclared600s component bound required')
 out.mkdir(parents=True);start=time.monotonic();resource.setrlimit(resource.RLIMIT_AS,(16<<30,16<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30))
 report={'schema':'lemma-package-recovery4-component-qualification/1','status':'FAIL','scope':__doc__,'bounds':{'seconds':600,'address_space_bytes':16<<30,'file_bytes':1<<30},'roles':{},'commands':[]}
 observer_before={str(p.relative_to(ROOT)):sha256(p) for p in (ROOT/'scripts').rglob('*.py') if '__pycache__' not in p.parts};observer_before[str(AUTHORITY.relative_to(ROOT))]=sha256(AUTHORITY)
 report['observer_source_inputs']=observer_before
 tools=require_tools(('opt','llc','llvm-mc','llvm-readelf','llvm-nm','llvm-objcopy','llvm-objdump'))
 def run(label,argv,cwd=ROOT):
  remaining=600-(time.monotonic()-start)
  if remaining<=0:raise Core0Error('predeclared600s qualification deadline exhausted')
  r=run_bounded(argv,cwd=cwd,env={**os.environ,'LEAN_NUM_THREADS':'2'},timeout_seconds=min(remaining,180))
  (out/(label+'.log')).write_bytes(r.stdout+r.stderr);report['commands'].append({'label':label,'argv':list(r.argv),'returncode':r.returncode,'seconds':r.elapsed_seconds})
  if r.returncode:raise Core0Error('actual component tool failed: '+label)
  return r.stdout.decode()
 try:
  captured=json.loads((origin/'result.json').read_text());authority=json.loads(AUTHORITY.read_text())
  if captured.get('status')!='PASS_GENUINE_COMPONENTS_ONLY' or captured.get('source_inputs_equal') is not True or captured.get('archive_equal') is not True or authority['origin_sha256']!=sha256(origin/'result.json'):raise Core0Error('exact complete original genuine capture/authority missing')
  report['origin']={'path':str(origin),'sha256':sha256(origin/'result.json'),'source_count':len(captured['source_inputs']),'authority_sha256':sha256(AUTHORITY)}
  for name,digest in captured['source_inputs'].items():
   if sha256(origin/'consumed-source-root'/name)!=digest:raise Core0Error('original consumed source changed: '+name)
   if name.startswith('Lemma/') and sha256(ROOT/name)!=digest:raise Core0Error('current staged target/compiler source differs from genuine capture: '+name)
  for role,row in captured['roles'].items():
   source=Path(row['path']);d=out/role;d.mkdir()
   for name,digest in row['artifacts'].items():
    if sha256(source/name)!=digest:raise Core0Error('original genuine artifact changed: '+role+'/'+name)
    shutil.copyfile(source/name,d/name)
   unit=json.loads((d/'unit.json').read_text());validate_unit(unit,unit['role'],configuration=unit['configuration'],image_key=unit.get('image_key'))
   pre=(d/'program.ll').read_text();post=(d/'program.opt.ll').read_text()
   audits={phase:validate_ir(ir,unit,optimized=phase=='post',optimization='O2') for phase,ir in [('pre',pre),('post',post)]}
   def inspect(tool,args,label):return run(role+'-'+label,[tools[tool],*(['--elf-output-style=GNU'] if tool=='llvm-readelf' else []),*args],d)
   undefined=inspect('llvm-nm',['--undefined-only','program.o'],'undefined')
   declarations=parse_definitions_and_calls(post)[1]
   expected={x for x in declarations if not x.startswith('llvm.')}
   if {line.split()[-1] for line in undefined.splitlines() if line.strip()}!=expected:raise Core0Error('RV64 object introduces or omits an actual declared primitive dependency')
   sections=inspect('llvm-readelf',['-S','--wide','program.o'],'sections');symbols=inspect('llvm-readelf',['-s','--wide','program.o'],'symbols');relocs=inspect('llvm-readelf',['-r','program.o'],'relocations');raws={}
   for section in ('.rodata','.rodata.cst32'):
    if section in alloc_section_names(sections):
     name=section[1:]+'.bin';inspect('llvm-objcopy',['-O','binary','--only-section='+section,'program.o',name],name);raws[section]=(d/name).read_bytes()
   readonly=validate_object(sections,symbols,relocs,raws,audits['post']['readonly_optimizer_tables'],'program.o')
   backend=inspect_backend_jump_tables(inspect,d,object_file='program.o',section_text=sections,symbol_text=symbols,relocation_text=relocs,unit=unit,optimization='O2',readonly_tables=readonly['readonly_tables'])
   report['roles'][role]={'status':'PASS','functions':len(unit['functions']),'external_primitives':sorted(expected),'pre':audits['pre'],'post':audits['post'],'readonly':readonly,'backend':backend}
   print(role,'PASS_GENERIC_UNIT_IR_OBJECT',len(unit['functions']),flush=True)
   (out/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
  from audit_kernel import _ir_definition_body
  mutants=[]
  for role,source,phase,kind in [
      ('notebook','Lemma.Applications.Notebook.packageRecoverableFinishRetained','pre','wrong-successor'),
      ('store','Lemma.Services.Store.ServerRecoveryAwait.stepAwait','pre','early-normal-service'),
      ('notebook','Lemma.Applications.Notebook.packageRecoverableValidateRecord','post','wrong-decoded-size')]:
   d=out/role;u=json.loads((d/'unit.json').read_text());ir=(d/('program.opt.ll' if phase=='post' else 'program.ll')).read_text();rows={canonical(r['source']):r for r in u['functions']};body=_ir_definition_body(ir,rows[source]['symbol'])
   if kind=='wrong-successor':bad,n=re.subn(r'(add i64 %[-A-Za-z0-9_.$]+, )1\b',r'\g<1>2',body,count=1)
   elif kind=='wrong-decoded-size':bad,n=re.subn(r'(icmp eq i64 %[-A-Za-z0-9_.$]+, )3712\b',r'\g<1>3713',body,count=1)
   else:
    old='@'+rows['Lemma.Services.Store.ServerRecovery.pumpRecoveryPhase']['symbol']+'(';new='@'+rows['Lemma.Services.Store.Server.courseService']['symbol']+'(';n=int(old in body);bad=body.replace(old,new,1)
   if n!=1:raise Core0Error('prospective actual semantic mutation site absent: '+kind)
   mutated=ir.replace(body,bad,1);path=out/(kind+'.ll');path.write_text(mutated);run(kind+'-verify',[tools['opt'],'-passes=verify','-disable-output',str(path)])
   try:validate(mutated,u,optimized=phase=='post')
   except Core0Error as error:mutants.append({'name':kind,'valid_llvm':True,'reason':str(error),'sha256':sha256(path)})
   else:raise Core0Error('semantic LLVM mutant admitted: '+kind)
  report['mutants']=mutants
  report['status']='PASS_COMPONENT_ARTIFACTS_ONLY' 
 except BaseException as e:report['error']=repr(e);raise
 finally:
  report['seconds']=time.monotonic()-start
  if report['seconds']>600:report['status']='FAIL';report['deadline_exceeded']=True
  report['observer_sources_equal']=all(sha256(ROOT/p)==d for p,d in observer_before.items())
  if not report['observer_sources_equal']:report['status']='FAIL';report['source_changed']=True
  report['observer_sha256']=sha256(Path(__file__));(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print(report['status'],report['seconds'])
if __name__=='__main__':main()
