#!/usr/bin/env python3
"""Inspect actual aligned Notebook catalogs/IR/readonly/RV64 jump objects.
No guest execution, document recovery or expected-success transcript occurs.
"""
import argparse,json,os,resource,shutil,time
from pathlib import Path
from core0_common import Core0Error,run_bounded,sha256,require_tools
from audit_kernel import validate_unit,validate_ir,parse_definitions_and_calls,alloc_section_names,inspect_backend_jump_tables,_ir_definition_body
from lemmasim_readonly import validate_object
from aligned_notebook_target import validate,AUTHORITY,candidate
from paper_next import canonical
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--component',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True);a=p.parse_args();origin=a.component.resolve();out=a.work_dir.resolve()
 if out.exists() or not out.is_relative_to(ROOT/'build'):p.error('unused ignored output required')
 out.mkdir(parents=True);start=time.monotonic();resource.setrlimit(resource.RLIMIT_AS,(16<<30,16<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30));r={'status':'FAIL','scope':__doc__,'bounds':{'seconds':600,'command_seconds':180,'address_space_bytes':16<<30,'file_bytes':1<<30},'roles':{},'commands':[]}
 before={str(f.relative_to(ROOT)):sha256(f) for f in (ROOT/'scripts').rglob('*.py') if '__pycache__' not in f.parts};before[str(AUTHORITY.relative_to(ROOT))]=sha256(AUTHORITY);r['observer_inputs']=before
 tools=require_tools(('opt','llc','llvm-mc','llvm-readelf','llvm-nm','llvm-objcopy','llvm-objdump'))
 def run(label,argv,cwd=ROOT):
  remaining=600-(time.monotonic()-start)
  if remaining<=0:raise Core0Error('predeclared600s artifact qualification bound')
  q=run_bounded(argv,cwd=cwd,timeout_seconds=min(180,remaining));(out/(label+'.log')).write_bytes(q.stdout+q.stderr);r['commands'].append({'label':label,'argv':list(q.argv),'seconds':q.elapsed_seconds,'returncode':q.returncode})
  if q.returncode:raise Core0Error('actual tool failed: '+label)
  return q.stdout.decode()
 try:
  capture=json.loads((origin/'result.json').read_text());authority=json.loads(AUTHORITY.read_text())
  if capture.get('status')!='PASS_GENUINE_NOTEBOOK_COMPONENTS_ONLY' or not capture.get('source_inputs_equal') or not capture.get('archive_equal') or authority['origin_sha256']!=sha256(origin/'result.json'):raise Core0Error('complete genuine original capture/authority required')
  if set(capture['roles'])!={'canonical','canonical-init','companion','companion-init'}:raise Core0Error('complete four actual catalog matrix required')
  for n,h in capture['source_inputs'].items():
   if sha256(origin/'consumed-source-root'/n)!=h or n.startswith('Lemma/') and sha256(ROOT/n)!=h:raise Core0Error('actual target/compiler source binding differs: '+n)
  r['origin']={'path':str(origin),'sha256':sha256(origin/'result.json'),'source_count':len(capture['source_inputs'])}
  for name,row in capture['roles'].items():
   source=Path(row['path']);d=out/name;d.mkdir()
   for n,h in row['artifacts'].items():
    if sha256(source/n)!=h:raise Core0Error('actual captured artifact changed: '+name+'/'+n)
    shutil.copyfile(source/n,d/n)
   u=json.loads((d/'unit.json').read_text());validate_unit(u,'user',configuration=u['configuration'],image_key='notebook')
   pre=(d/'program.ll').read_text();post=(d/'program.opt.ll').read_text();audits={phase:validate_ir(ir,u,optimized=phase=='post',optimization='O2') for phase,ir in [('pre',pre),('post',post)]}
   if name.endswith('-init'):
    normal=capture['roles'][name.removesuffix('-init')]['artifacts']
    if any(row['artifacts'][n]!=normal[n] for n in ('program.ll','program.opt.ll','program.o')):raise Core0Error('initializer actual IR/object differs; separate full inspection required')
    r['roles'][name]={'status':'PASS_CATALOG_IR_AND_EXACT_NORMAL_OBJECT_BYTES','unit_sha256':sha256(d/'unit.json')};continue
   def inspect(tool,args,label):return run(name+'-'+label,[tools[tool],*(['--elf-output-style=GNU'] if tool=='llvm-readelf' else []),*args],d)
   undefined=inspect('llvm-nm',['--undefined-only','program.o'],'undefined');declarations=parse_definitions_and_calls(post)[1];wanted={n for n in declarations if not n.startswith('llvm.')}
   if {line.split()[-1] for line in undefined.splitlines() if line.strip()}!=wanted:raise Core0Error('RV64 object helper/primitive closure differs')
   sections=inspect('llvm-readelf',['-S','--wide','program.o'],'sections');symbols=inspect('llvm-readelf',['-s','--wide','program.o'],'symbols');relocs=inspect('llvm-readelf',['-r','program.o'],'relocations');raws={}
   for section in ('.rodata','.rodata.cst32'):
    if section in alloc_section_names(sections):
     f=section[1:]+'.bin';inspect('llvm-objcopy',['-O','binary','--only-section='+section,'program.o',f],f);raws[section]=(d/f).read_bytes()
   readonly=validate_object(sections,symbols,relocs,raws,audits['post']['readonly_optimizer_tables'],'program.o');backend=inspect_backend_jump_tables(inspect,d,object_file='program.o',section_text=sections,symbol_text=symbols,relocation_text=relocs,unit=u,optimization='O2',readonly_tables=readonly['readonly_tables']);r['roles'][name]={'status':'PASS_GENERIC_UNIT_IR_READONLY_OBJECT_JUMPS','functions':len(u['functions']),'pre':audits['pre'],'post':audits['post'],'readonly':readonly,'backend':backend};print(name,'PASS_GENERIC_OBJECT',len(u['functions']),flush=True)
  d=out/'canonical';u=json.loads((d/'unit.json').read_text());ir=(d/'program.ll').read_text();rows={canonical(x['source']):x for x in u['functions']};mutants=[]
  import re
  for name,source,pattern,replacement in [('wrong-third-glyph-shift','alignedSpanWord',r'icmp eq i64 (%[-\w.]+), 40',r'icmp eq i64 \1, 32'),('wrong-row-chunks','alignedDeltaStep',r'urem i64 (%[-\w.]+), 25',r'urem i64 \1, 24'),('missing-last-chunk','renderAlignedDelta',r'(icmp ult i32 %[-\w.]+, )8000',r'\g<1>7999')]:
   body=_ir_definition_body(ir,rows['Lemma.Courses.PackageRender.'+source]['symbol']);bad,n=re.subn(pattern,replacement,body,count=1)
   if n!=1:raise Core0Error('prospective actual semantic mutation site missing: '+name)
   changed=ir.replace(body,bad,1);f=out/(name+'.ll');f.write_text(changed);run(name+'-verify',[tools['opt'],'-passes=verify','-disable-output',str(f)])
   try:validate(changed,u,optimized=False)
   except Core0Error as e:mutants.append({'name':name,'valid_llvm':True,'reason':str(e),'sha256':sha256(f)})
   else:raise Core0Error('actual semantic mutant admitted: '+name)
  r.update(status='PASS_ALIGNED_NOTEBOOK_ARTIFACTS_ONLY',mutants=mutants)
 except BaseException as e:r['error']=repr(e);raise
 finally:
  r['seconds']=time.monotonic()-start;r['observer_inputs_equal']=all(sha256(ROOT/n)==h for n,h in before.items())
  if not r['observer_inputs_equal'] or r['seconds']>600:r['status']='FAIL'
  (out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 print(r['status'],r['seconds'])
if __name__=='__main__':main()
