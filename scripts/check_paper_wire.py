#!/usr/bin/env python3
"""Bounded genuine USBWire kernel source lowering and artifact guard negatives.

This component command does not run a CPU or qualify a full linked image,
physical USB timing, Pending continuation, Ready or durable Save.
"""
import argparse,json,re,sys,time
from pathlib import Path
from core0_common import Core0Error,require_tools,run_bounded,sha256
from build_core0 import LLC_ARGUMENTS
from build_kernel import source_inputs
from paper_wire import validate,canonical
from lemmasim_readonly import validate_lookup
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/kernel'))
from paper_wire_mutations import exercise


def validate_kernel_attributes(attributes):
 required=['Format: elf64-littleriscv','Arch: riscv64','AddressSize: 64bit',
  'Class: 64-bit (0x2)','DataEncoding: LittleEndian (0x1)',
  'Type: Relocatable (0x1)','Machine: EM_RISCV (0xF3)']
 if any(attributes.count(field)!=1 for field in required):
  raise Core0Error('kernel component is not exact little-endian ELF64 relocatable RISC-V')
 arches=re.findall(r'^\s*Value: (rv[^\s]+)\s*$',attributes,re.MULTILINE)
 if arches!=['rv64i2p1_m2p0_zicsr2p0_zifencei2p0_zmmul1p0'] or not re.search(r'Flags \[ \(0x0\)\s*\]',attributes):
  raise Core0Error('kernel component integer-only CSR/fence ISA or ELF flags differ')


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--dtb',type=Path,required=True,help='Actual compiled profile11 FDT for the independent raw-leaf/fault fixture');p.add_argument('--timeout',type=int,default=420);a=p.parse_args();out=a.work_dir.resolve()
 if not 60<=a.timeout<=600 or out.exists() or not out.is_relative_to(ROOT/'build'):p.error('unused work-dir under build/ and timeout60..600 required')
 out.mkdir(parents=True);started=time.monotonic();r={'schema_version':1,'status':'FAIL','scope':__doc__,'commands':[]}
 def inventory():return {**source_inputs(ROOT),**{n:sha256(ROOT/n) for n in ['scripts/check_paper_wire.py','tests/kernel/paper_wire_mutations.py','tests/kernel/WireDiscoveryFlags.lean']}}
 try:
  before=inventory();r['source_inputs']=before;r['raw_fdt']={'path':str(a.dtb.resolve()),'sha256':sha256(a.dtb)};tools=require_tools(['lean','lake','opt','llc','llvm-nm','llvm-readobj']);r['tools']={}
  for name,path in tools.items():
   v=run_bounded([path,'--version'],cwd=ROOT,timeout_seconds=30)
   if v.returncode or not path.startswith('/nix/store/') or not v.stdout.strip():raise Core0Error('missing pinned tool identity')
   r['tools'][name]={'path':path,'sha256':sha256(Path(path)),'version':v.stdout.decode().splitlines()[:4]}
  def run(argv,log,cwd=ROOT,env=None):
   remaining=a.timeout-(time.monotonic()-started)
   if remaining<=0:raise Core0Error('predeclared component deadline exhausted')
   result=run_bounded(argv,cwd=cwd,timeout_seconds=remaining,env=env)
   (out/log).write_bytes(result.stdout+result.stderr);r['commands'].append({'argv':list(result.argv),'returncode':result.returncode,'elapsed_seconds':result.elapsed_seconds,'log':log})
   if result.returncode:raise Core0Error('genuine command failed: '+log)
   return result.stdout.decode()
  run(['flock',str(ROOT/'build/task006-lake.lock'),tools['lake'],'build','Lemma.Platform.LemmaSim.NotebookKernel','Lemma.Compiler.KernelExport'],'lake.log')
  import os
  raw=run(['flock',str(ROOT/'build/task006-lake.lock'),tools['lake'],'env','lean','tests/kernel/WireDiscoveryFlags.lean'],'raw-fdt-model.log',env={**os.environ,'LEMMA_WIRE_DTB':str(a.dtb.resolve())})
  if raw.count('WIRE_RAW_FDT_FLAGS:PASS8191_WRONGBOUNDARY_DUPLICATE_WIDTH_5FAULTS')!=1:raise Core0Error('missing actual raw-FDT/fault observations')
  roles={};shared=[]
  for role,root in [('notebook','siliconUSBWireBoot'),('initializer','siliconUSBWireInitializeMedium')]:
   d=out/role;d.mkdir();source=d/'Export.lean';source.write_text('import Lemma.Platform.LemmaSim.NotebookKernel\nimport Lemma.Compiler.KernelExport\n\n#lemma_export_unit "kernel" [Lemma.Platform.LemmaSim.NotebookKernel.'+root+', Lemma.Platform.LemmaSim.NotebookKernel.dispatchUSBWireBulk]\n')
   cfg='lemmasim-silicon-usb-wire-bulk-'+('initialize' if role=='initializer' else 'notebook')
   import os
   env={**os.environ,'LEMMA_KERNEL_CONFIGURATION':cfg,'LEMMA_KERNEL_OUT':str(d)}
   run(['flock',str(ROOT/'build/task006-lake.lock'),tools['lake'],'env','lean',str(source)],role+'-export.log',env=env)
   run([tools['opt'],'-S','-passes=default<O2>','program.ll','-o','program.opt.ll'],role+'-opt.log',cwd=d)
   run([tools['llc'],*LLC_ARGUMENTS,'-O2','-stack-size-section','program.opt.ll','-o','program.o'],role+'-object.log',cwd=d)
   unit=json.loads((d/'unit.json').read_text());pre=(d/'program.ll').read_text();post=(d/'program.opt.ll').read_text()
   reports={kind:validate(ir,unit,optimized=kind=='post') for kind,ir in [('pre',pre),('post',post)]}
   _,tables,_=validate_lookup(post,unit)
   rejected=exercise(pre,post,unit)
   bad=json.loads(json.dumps(unit));bad['role']='user'
   try:validate_lookup(post,bad)
   except Core0Error as e:rejected.append({'mutation':'independent-wrong-role-reachable-literal','status':'REJECTED','reason':str(e)})
   else:raise Core0Error('readonly owner acquired user authority')
   attrs=run([tools['llvm-readobj'],'--file-headers','--arch-specific','program.o'],role+'-attributes.log',cwd=d);validate_kernel_attributes(attrs)
   undef=run([tools['llvm-nm'],'--undefined-only','program.o'],role+'-undefined.log',cwd=d)
   actual={line.split()[-1] for line in undef.splitlines() if line.strip()};declared={row['primitive_symbol'] for row in unit['used_execution_ops'] if row['primitive_symbol'] is not None}
   if unit['used_device_ops'] or any(row['stable_id'].startswith('lemmasim.device-') for row in unit['used_execution_ops']):declared.add('core0_io_fence')
   if actual!=declared:raise Core0Error('kernel object undefined boundary differs from declared primitive closure')
   shared.append({kind:{name:digest for name,digest in reports[kind]['complete_body_identities'].items() if not name.endswith(('.siliconUSBWireBoot','.siliconUSBWireInitializeMedium'))} for kind in ('pre','post')})
   roles[role]={'configuration':cfg,'authorities':reports,'readonly_pools':len(tables),'rejected_mutations':rejected,'declared_undefined_boundaries':sorted(actual),'artifacts':{n:sha256(d/n) for n in ['Export.lean','unit.json','program.ll','program.opt.ll','program.o']}}
  if shared[0]!=shared[1] or any(len(shared[0][kind])!=46 for kind in ('pre','post')):raise Core0Error('notebook/initializer shared genuine authority changed')
  if sha256(a.dtb)!=r['raw_fdt']['sha256']:raise Core0Error('raw FDT changed during qualification')
  if inventory()!=before:raise Core0Error('consumed component source changed during qualification')
  r.update(status='PASS_GENUINE_COMPONENT_AND_ARTIFACT_GUARDS',roles=roles,source_inputs_equal=True,shared_authorities_pre_post=46)
 except (Core0Error,OSError,ValueError,KeyError,RuntimeError,AssertionError) as e:r['error']=str(e)
 finally:r['host_seconds']=time.monotonic()-started;(out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k in ['status','error','host_seconds']},indent=2))
 return 0 if r['status'].startswith('PASS_') else 1
if __name__=='__main__':raise SystemExit(main())
