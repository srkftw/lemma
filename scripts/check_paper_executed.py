#!/usr/bin/env python3
"""Bounded Paper3 circuitry/state, actual Lean health and genuine RV64 authority.

Component qualification only: the miniature panel exposes corner states; full
canonical Product10 cold Ready, metadata confirmation and physical qualification
remain separately observed obligations. There is no artifact-absent success.
"""
import argparse,json,os,resource,shutil,sys,time
from pathlib import Path
from core0_common import Core0Error,require_tools,run_bounded,sha256
from build_core0 import LLC_ARGUMENTS
from build_kernel import source_inputs
from audit_kernel import validate_unit,validate_ir,validate_readonly_pmp_lookup,alloc_section_names,inspect_backend_jump_tables
from lemmasim_readonly import validate_object
from check_silicon import device_build
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/kernel'))
from paper_executed_mutations import mutations

def run_generated_state(binary,directory,timeout):
 # The generated circuit fixture owns snapshots only in its explicit output.
 result=run_bounded([str(binary),str(directory)],cwd=directory,timeout_seconds=timeout)
 if result.returncode or result.stdout.decode().count('PAPER3-STATE PASS')!=1:
  raise Core0Error('literal generated-state suffix failed: '+result.stderr.decode())
 return result

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work-dir',type=Path,required=True)
 parser.add_argument('--timeout',type=int,default=540);parser.add_argument('--kernel-component',type=Path,help='Reuse an explicit successful genuine component receipt; exact target/compiler/tool inputs must remain unchanged, observer-only differences are recorded');a=parser.parse_args();out=a.work_dir.resolve()
 if out.exists() or not out.is_relative_to(ROOT/'build'):parser.error('work-dir must be unused under build/')
 if not 240<=a.timeout<=900:parser.error('timeout must be240..900seconds')
 out.mkdir(parents=True);start=time.monotonic();r={'schema_version':1,'status':'FAIL','scope':__doc__.strip(),'commands':[]}
 try:
  inputs=source_inputs(ROOT);extra=['scripts/check_paper_executed.py','tests/kernel/paper_executed_mutations.py',
    'tests/boot/BootHealthExecuted.lean','conformance/silicon/PaperExecuted.sv',
    'conformance/silicon/PaperExecutedState.sv','conformance/silicon/paper_executed_state.cpp','sim/rtl/lemma_paper.sv']
  before={**inputs,**{n:sha256(ROOT/n) for n in extra}};r['source_inputs']=before
  tools=require_tools(['lake','opt','llc','llvm-readelf','llvm-objcopy','llvm-mc']);r['tools']={}
  for name,path in tools.items():
   q=run_bounded([path,'--version'],cwd=ROOT,timeout_seconds=30)
   if q.returncode or not path.startswith('/nix/store/') or not q.stdout.strip():raise Core0Error('missing pinned compiler identity: '+name)
   r['tools'][name]={'path':path,'sha256':sha256(Path(path)),'version':q.stdout.decode().splitlines()[:4]}
  def remaining():
   seconds=a.timeout-(time.monotonic()-start)
   if seconds<=0:raise Core0Error('original component deadline exhausted')
   return seconds
  def run(argv,name,cwd=ROOT,env=None):
   q=run_bounded(argv,cwd=cwd,env=env,timeout_seconds=remaining())
   (out/(name+'.log')).write_bytes(q.stdout+q.stderr);r['commands'].append({'argv':argv,'returncode':q.returncode,'host_seconds':q.elapsed_seconds})
   if q.returncode:raise Core0Error('component command failed: '+name)
   return q.stdout.decode()
  component=out/'kernel';component.mkdir()
  if a.kernel_component is None:
   run(['flock','build/task006-lake.lock',tools['lake'],'build','Lemma.Platform.LemmaSim.NotebookKernel','Lemma.Compiler.KernelExport'],'lake')
   source=component/'Export.lean';source.write_text('import Lemma.Platform.LemmaSim.NotebookKernel\nimport Lemma.Compiler.KernelExport\n\n#lemma_export_unit "kernel" [Lemma.Platform.LemmaSim.NotebookKernel.siliconProductExecutedBoot, Lemma.Platform.LemmaSim.NotebookKernel.dispatchProductExecutedBulk]\n')
   env={**os.environ,'LEMMA_KERNEL_CONFIGURATION':'lemmasim-silicon-product-executed-bulk-notebook','LEMMA_KERNEL_OUT':str(component)}
   run(['flock','build/task006-lake.lock',tools['lake'],'env','lean',str(source)],'export',env=env)
   run([tools['opt'],'-S','-passes=default<O2>','program.ll','-o','program.opt.ll'],'opt',component)
   run([tools['llc'],*LLC_ARGUMENTS,'-O2','-stack-size-section','program.opt.ll','-o','program.o'],'llc',component)
  else:
   origin=a.kernel_component.resolve();receipt=json.loads((origin/'result.json').read_text())
   if receipt.get('status')!='PASS' or not isinstance(receipt.get('source_inputs'),dict):raise Core0Error('reused component lacks a successful genuine source receipt')
   original=receipt['source_inputs'];observers={'scripts/audit_kernel.py','scripts/lemmasim_readonly.py','scripts/paper_bulk.py','scripts/paper_executed.py'}
   changed={n for n in set(original)|set(inputs) if original.get(n)!=inputs.get(n)}
   if set(original)!=set(inputs) or not changed<=observers:raise Core0Error('reused component target/compiler/tool inputs changed')
   for name in ('Export.lean','unit.json','program.ll','program.opt.ll','program.o'):
    if receipt.get('artifacts',{}).get(name)!=sha256(origin/name):raise Core0Error('reused genuine component artifact changed: '+name)
    shutil.copyfile(origin/name,component/name)
   r['reused_component']={'path':str(origin),'original_receipt_sha256':sha256(origin/'result.json'),'original_artifacts':receipt['artifacts'],'observer_only_changes':{n:{'original':original[n],'current':inputs[n]} for n in sorted(changed)},'scope':'No target recompile; same genuine emitted component qualified under the current independent observer'}
  unit=json.loads((component/'unit.json').read_text());validate_unit(unit,'kernel',configuration=unit['configuration'])
  pre=(component/'program.ll').read_text();post=(component/'program.opt.ll').read_text()
  r['ir']={'pre':validate_ir(pre,unit,optimized=False),'post':validate_ir(post,unit,optimized=True,optimization='O2')}
  r['actual_artifact_mutations_rejected']=mutations(unit,pre,post)
  def inspect(tool,args,label):return run([tools[tool],*(['--elf-output-style=GNU'] if tool=='llvm-readelf' else []),*args],label,component)
  sections=inspect('llvm-readelf',['-S','--wide','program.o'],'sections');symbols=inspect('llvm-readelf',['-s','--wide','program.o'],'symbols');relocations=inspect('llvm-readelf',['-r','program.o'],'relocations')
  raw={}
  for name in ('.rodata','.rodata.cst32'):
   if name in alloc_section_names(sections):
    filename='literal-'+name[1:]+'.bin';inspect('llvm-objcopy',['-O','binary','--only-section='+name,'program.o',filename],filename);raw[name]=(component/filename).read_bytes()
  r['readonly_object']=validate_object(sections,symbols,relocations,raw,r['ir']['post']['readonly_optimizer_tables'],'program.o')
  r['backend_object']=inspect_backend_jump_tables(inspect,component,object_file='program.o',section_text=sections,symbol_text=symbols,relocation_text=relocations,unit=unit,optimization='O2',readonly_tables=r['readonly_object']['readonly_tables'])
  text=run(['flock','build/task006-lake.lock',tools['lake'],'env','lean','tests/boot/BootHealthExecuted.lean'],'health-action')
  if text.count('PRODUCT10_BOOT_HEALTH:PASS')!=1:raise Core0Error('actual compiled health Action fixture did not complete')
  r['rtl_versions']=[]
  for version in (1,2,3):
   model=out/('rtl'+str(version));argv=['verilator','--binary','--timing','--top-module','PaperExecuted','-Wno-fatal','-GVERSION='+str(version),'--Mdir',str(model),'-j','2','sim/rtl/lemma_paper.sv','conformance/silicon/PaperExecuted.sv']
   record,identity=device_build(argv,out/('rtl'+str(version)+'-tools.json'),out/('rtl'+str(version)+'-build.log'),remaining());r['commands'].append(record)
   text=run([str(model/'VPaperExecuted')],'rtl'+str(version))
   if text.count('PAPER-EXECUTED version'+str(version))!=1:raise Core0Error('literal controller version did not complete')
   r['rtl_versions'].append({'version':version,'tools':identity})
  model=out/'state';argv=['verilator','--cc','--exe','--build','--savable','--top-module','PaperExecutedState','-Wno-fatal','--Mdir',str(model),'-j','2','sim/rtl/lemma_paper.sv','conformance/silicon/PaperExecutedState.sv',str(ROOT/'conformance/silicon/paper_executed_state.cpp')]
  record,r['state_tools']=device_build(argv,out/'state-tools.json',out/'state-build.log',remaining());r['commands'].append(record)
  q=run_generated_state(model/'VPaperExecutedState',out,remaining())
  (out/'exact-generated-state.log').write_bytes(q.stdout+q.stderr)
  r['commands'].append({'argv':[str(model/'VPaperExecutedState'),str(out)],'returncode':q.returncode,'host_seconds':q.elapsed_seconds})
  after={**source_inputs(ROOT),**{n:sha256(ROOT/n) for n in extra}}
  if before!=after:raise Core0Error('component consumed source changed during qualification')
  r['artifacts']={n:sha256(component/n) for n in ('Export.lean','unit.json','program.ll','program.opt.ll','program.o')};r['status']='PASS'
 except BaseException as e:r['error']=repr(e)
 finally:
  r['host_seconds']=time.monotonic()-start;r['largest_reaped_child_peak_rss_kib']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
  (out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:r.get(k) for k in ('status','error','host_seconds')},indent=2));return 0 if r['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
