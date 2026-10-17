#!/usr/bin/env python3
"""Bounded genuine ROM, actual Lean policy and literal BootNV qualification.

This is a component qualifier. It neither claims product cold boot nor
initializes image metadata outside the guest.
"""
import argparse,copy,json,os,resource,struct,sys,time
from pathlib import Path
from core0_common import Core0Error,require_tools,run_bounded,sha256
from product_boot_audit import validate_unit,validate_elf
from check_silicon import device_build
ROOT=Path(__file__).resolve().parents[1]
def mutations(rom):
 unit=json.loads((rom/'unit.json').read_text());pre=(rom/'program.ll').read_text();post=(rom/'program.opt.ll').read_text()
 validate_unit(unit,pre,post);count=0
 def reject(u,p=pre,o=post):
  nonlocal count
  try:validate_unit(u,p,o)
  except Core0Error:count+=1;return
  raise Core0Error('independent boot auditor accepted a corrupt authority fixture')
 for key,value in [('contract_version','core0-firmware-v0.1'),('root','Lemma.Boot.Product.boot'),('rom_bytes',65540),('stack_floor',0x81fc0000),('integrity','authenticated'),('backend_dispatch','unchecked')]:
  bad=copy.deepcopy(unit);bad[key]=value;reject(bad)
 bad=copy.deepcopy(unit);bad['used_device_ops'].append('uart.enable-reset-fifo-trigger14');reject(bad)
 bad=copy.deepcopy(unit);bad['used_execution_ops'].append('execution.syscall');reject(bad)
 bad=copy.deepcopy(unit);bad['functions'][0]['source']='Lemma.Applications.Hidden.boot';reject(bad)
 bad=copy.deepcopy(unit);bad['functions'].append(copy.deepcopy(bad['functions'][0]));reject(bad)
 bad=copy.deepcopy(unit);bad['functions'][0]['effects']=[''];reject(bad)
 reject(unit,pre.replace('"no-jump-tables"="true"','',1))
 reject(unit,pre+'\n@hidden = global i64 1\n')
 reject(unit,pre+'\ndeclare i64 @malloc(i64)\n')
 reject(unit,o=post+'\ndeclare i64 @llvm.unregistered.i64(i64)\n')
 status=next(row for row in unit['functions'] if row['source']=='Lemma.Core0.Memory.Status.iterationStop')
 begin=pre.index('@'+status['symbol']+'()');end=pre.index('\n}',begin)
 changed=pre[:begin]+pre[begin:end].replace('ret i8 10','ret i8 0')+pre[end:];reject(unit,changed)
 elf=(rom/'image.elf').read_bytes();wire=(rom/'rom.bin').read_bytes();validate_elf(elf,wire)
 for badelf,badrom in [(elf[:63],wire),(elf,wire[:-4]),(elf,wire+b'\0\0\0\0'),(elf[:18]+b'\x3e\x00'+elf[20:],wire)]:
  try:validate_elf(badelf,badrom)
  except Core0Error:count+=1;continue
  raise Core0Error('boot ELF envelope mutation accepted')
 # Mutate the actual linked constant pool and its section permissions,
 # while retaining the authoritative load/ROM byte equality.
 header=struct.unpack_from('<16sHHIQQQIHHHHHH',elf)
 rows=[struct.unpack_from('<IIQQQQIIQQ',elf,header[6]+i*64) for i in range(header[12])]
 index=next(i for i,row in enumerate(rows) if row[2]==18)
 pool=rows[index]
 for offset in (0,8,16,24,32):
  badelf=bytearray(elf);badrom=bytearray(wire)
  badelf[pool[4]+offset]^=1;badrom[pool[3]-4096+offset]^=1
  try:validate_elf(bytes(badelf),bytes(badrom))
  except Core0Error:count+=1;continue
  raise Core0Error('linked magic-pool mutation accepted')
 for field,value in [(2,19),(2,22),(8,4),(9,0)]:
  badelf=bytearray(elf);row=list(pool);row[field]=value
  struct.pack_into('<IIQQQQIIQQ',badelf,header[6]+index*64,*row)
  try:validate_elf(bytes(badelf),wire)
  except Core0Error:count+=1;continue
  raise Core0Error('readonly section authority mutation accepted')
 return count
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--timeout',type=int,default=240);a=p.parse_args();out=a.work_dir.resolve()
 if out.exists() or not out.is_relative_to(ROOT/'build'):p.error('work-dir must be unused under build/')
 if not 90<=a.timeout<=600:p.error('component timeout must be90..600seconds')
 out.mkdir(parents=True);started=time.monotonic();r={'schema':'lemma-product-boot-components/1','status':'FAIL','scope':'genuine ROM compiler/link closure +actual Lean policy on raw I/O model +literal controller; product acceptance separate','commands':[]}
 try:
  tools=require_tools(['lake','nix-shell']);r['tests']={str(x.relative_to(ROOT)):sha256(x) for x in sorted((ROOT/'tests/boot').glob('*')) if x.is_file()}
  r['host_inputs']={n:sha256(ROOT/n) for n in ['scripts/check_product_boot.py','scripts/check_silicon.py','tooling/silicon/sim.nix','flake.lock']}
  def run(argv,name):
   remain=a.timeout-(time.monotonic()-started)
   if remain<=0:raise Core0Error('predeclared component deadline exhausted')
   result=run_bounded(argv,cwd=ROOT,timeout_seconds=remain);(out/(name+'.log')).write_bytes(result.stdout+result.stderr)
   r['commands'].append({'argv':argv,'returncode':result.returncode,'host_seconds':result.elapsed_seconds})
   if result.returncode:raise Core0Error('component command failed: '+name)
   return result.stdout.decode()
  run([sys.executable,'scripts/build_product_boot.py','--work-dir',str(out/'rom'),'--timeout',str(min(a.timeout,300))],'rom')
  r['artifact_mutations_rejected']=mutations(out/'rom')
  for file,marker in [('ProductPolicy.lean','BOOT_POLICY_HOST:PASS'),('ProductNVPolicy.lean','BOOT_NV_GUEST_POLICY:PASS')]:
   text=run(['flock','build/task006-lake.lock',tools['lake'],'env','lean','tests/boot/'+file],file)
   if text.count(marker)!=1:raise Core0Error('missing actual source policy result')
  obj=out/'rtl'
  argv=['verilator','--binary','--timing','--top-module','boot_nv_tb','-Wno-fatal','--Mdir',str(obj),'-j','2','sim/rtl/lemma_boot_nv.sv','tests/boot/boot_nv_tb.sv']
  remaining=a.timeout-(time.monotonic()-started)
  if remaining<=0:raise Core0Error('predeclared component deadline exhausted')
  record,r['rtl_tools']=device_build(argv,out/'rtl-tools.json',out/'rtl-build.log',remaining)
  r['commands'].append(record)
  text=run([str(obj/'Vboot_nv_tb')],'rtl-run')
  if text.count('BOOT_NV_LITERAL:PASS')!=1:raise Core0Error('literal NV protocol did not pass')
  r['status']='PASS';r['rom_build_sha256']=sha256(out/'rom/build.json')
 except BaseException as e:r['error']=str(e)
 finally:
  r['host_seconds']=time.monotonic()-started;r['largest_reaped_child_peak_rss_kib']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
  (out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({'status':r['status'],'result':str(out/'result.json'),'error':r.get('error')},indent=2));return 0 if r['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
