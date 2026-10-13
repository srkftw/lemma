#!/usr/bin/env python3
"""Compile/audit the genuine Lean product ROM; no running guest is preloaded.

ROM build and finite policy/controller qualification are component results.
Use the product machine/boot-medium path for actual boot/update acceptance.
"""
import argparse,fcntl,json,os,resource,time
from pathlib import Path
from build_core0 import LLC_ARGUMENTS,STARTUP_ARGUMENTS
from core0_common import Core0Error,require_tools,run_bounded,sha256
from product_boot_audit import validate_unit,validate_elf
from audit_kernel import validate_machine
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True)
 p.add_argument('--timeout',type=int,default=300);p.add_argument('--product-profile',choices=['7','9'],default='7');a=p.parse_args();out=a.work_dir.resolve()
 if out.exists() or not out.is_relative_to(ROOT/'build'):p.error('work-dir must be unused under build/')
 if not 60<=a.timeout<=600:p.error('timeout must be60..600seconds')
 out.mkdir(parents=True);started=time.monotonic();report={'schema':'lemma-product-rom-build/1','status':'FAIL',
  'scope':'genuine Lean checked boot-v0.1 to LLVM/RV64 immutable ROM; actual product machine and boot/update recovery remain separate'}
 try:
  names=['scripts/build_product_boot.py','scripts/product_boot_audit.py','scripts/build_core0.py','scripts/core0_common.py',
   'scripts/audit_kernel.py','flake.nix','flake.lock','lakefile.toml','lean-toolchain','tooling/toolchain-lock.json']
  names+=sorted(str(f.relative_to(ROOT)) for f in (ROOT/'Lemma').rglob('*.lean'))
  before={n:sha256(ROOT/n) for n in names};report['source_inputs']=before
  names_tools=['lean','lake','opt','llc','clang','ld.lld','llvm-nm','llvm-readelf','llvm-objdump','llvm-objcopy']
  tools=require_tools(names_tools);report['tools']={};commands=[];report['commands']=commands
  for name,path in tools.items():
   result=run_bounded([path,'--version'],cwd=ROOT,timeout_seconds=30)
   if result.returncode or not path.startswith('/nix/store/') or not result.stdout.strip():raise Core0Error('missing pinned ROM tool identity')
   report['tools'][name]={'path':path,'sha256':sha256(Path(path)),'version':result.stdout.decode().splitlines()[:4]}
  def run(argv,label,cwd=out,env=None):
   remain=a.timeout-(time.monotonic()-started)
   if remain<=0:raise Core0Error('predeclared ROM build deadline exceeded')
   result=run_bounded(argv,cwd=cwd,timeout_seconds=remain,env=env)
   (out/(label+'.log')).write_bytes(result.stdout+result.stderr)
   commands.append({'argv':argv,'cwd':str(cwd),'returncode':result.returncode,'host_seconds':result.elapsed_seconds})
   if result.returncode:raise Core0Error('ROM command failed: '+label)
   return result.stdout.decode()
  exporter='Lemma.Compiler.BootNextExport' if a.product_profile=='9' else 'Lemma.Compiler.BootExport'
  command='#lemma_export_product_next_boot' if a.product_profile=='9' else '#lemma_export_product_boot'
  marker='PRODUCT_NEXT_BOOT_EXPORT:PASS' if a.product_profile=='9' else 'PRODUCT_BOOT_EXPORT:PASS'
  output_env='LEMMA_PRODUCT_NEXT_BOOT_OUT' if a.product_profile=='9' else 'LEMMA_PRODUCT_BOOT_OUT'
  # Shared olean publication is serialized with the other target lanes.
  with (ROOT/'build/task006-lake.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   run([tools['lake'],'build',exporter],'build',ROOT)
  source=out/'Export.lean';source.write_text('import '+exporter+'\n'+command+'\n')
  env=dict(os.environ);env[output_env]=str(out)
  text=run([tools['lake'],'env','lean',str(source)],'export',ROOT,env)
  if text.count(marker)!=1:raise Core0Error('missing genuine ROM export result')
  run([tools['opt'],'-S','-passes=default<O2>','program.ll','-o','program.opt.ll'],'opt')
  unit=json.loads((out/'unit.json').read_text())
  report['checked_closure']=validate_unit(unit,(out/'program.ll').read_text(),(out/'program.opt.ll').read_text())
  run([tools['llc'],*LLC_ARGUMENTS,'-O2','-stack-size-section','program.opt.ll','-o','program.o'],'llvm')
  run([tools['clang'],*STARTUP_ARGUMENTS,'startup.S','-o','startup.o'],'startup')
  root=unit['entry_symbol']
  undefined=run([tools['llvm-nm'],'--undefined-only','program.o'],'program-undefined').split()
  if undefined!=['U','core0_io_fence']:raise Core0Error('unaccounted ROM program runtime')
  undefined=run([tools['llvm-nm'],'--undefined-only','startup.o'],'startup-undefined').split()
  if undefined!=['U',root]:raise Core0Error('structured reset boundary linkage differs')
  run([tools['ld.lld'],'-m','elf64lriscv','--no-relax','-T','link.ld','-Map=image.map',
   '-o','image.elf','startup.o','program.o'],'link')
  run([tools['llvm-objcopy'],'-O','binary','image.elf','rom.bin'],'rom')
  if run([tools['llvm-nm'],'--undefined-only','image.elf'],'undefined').strip():raise Core0Error('unresolved ROM target code')
  relocation=run([tools['llvm-readelf'],'--elf-output-style=GNU','-r','image.elf'],'relocations')
  if 'There are no relocations in this file.' not in relocation:raise Core0Error('ROM retains runtime relocations')
  machine=run([tools['llvm-objdump'],'-d','--no-show-raw-insn','image.elf'],'machine')
  validate_machine(machine)
  report['elf']=validate_elf((out/'image.elf').read_bytes(),(out/'rom.bin').read_bytes(),unit['configuration'])
  run([tools['llvm-readelf'],'--elf-output-style=GNU','-h','-l','-A','-s','image.elf'],'elf')
  if before!={n:sha256(ROOT/n) for n in names}:raise Core0Error('consumed ROM compiler/source changed during build')
  artifacts=['program.ll','program.opt.ll','program.o','startup.S','startup.o','link.ld','unit.json','symbols.txt','image.elf','rom.bin']
  report['artifacts']={n:sha256(out/n) for n in artifacts};report['status']='PASS'
  if a.product_profile=='9':report.update(hardware_profile='lemma-silicon-dev/0.9.0',configuration=unit['configuration'],image_compatibility=unit['image_compatibility'])
 except BaseException as e:report['error']=str(e)
 finally:
  report['host_seconds']=time.monotonic()-started
  usage=resource.getrusage(resource.RUSAGE_CHILDREN);report['largest_reaped_child_peak_rss_kib']=usage.ru_maxrss
  (out/'build.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'result':str(out/'build.json'),'error':report.get('error')},indent=2))
 return 0 if report['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
