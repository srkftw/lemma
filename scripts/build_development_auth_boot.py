#!/usr/bin/env python3
"""Genuine public-development-key authenticated ROM; no running image preload.
The mandatory flag acknowledges deterministic public test material, not a
production credential or anti-rollback guarantee. Host orchestration only.
"""
import argparse,fcntl,json,os,re,resource,subprocess,time
from pathlib import Path
from core0_common import Core0Error,require_tools,run_bounded,sha256
from build_core0 import LLC_ARGUMENTS,STARTUP_ARGUMENTS
from audit_core0 import parse_stack_sizes,validate_loop_stack_call_graph
from audit_kernel import validate_machine
from check_crypto import audit_elf
ROOT=Path(__file__).resolve().parents[1]
CONFIG='lemmasim-silicon-public-development-auth-boot'
ROOT_NAME='Lemma.Boot.DevelopmentRecovery.entry'
WATCHDOG_CONFIG='lemmasim-silicon-public-development-trial-watchdog-boot'
WATCHDOG_ROOT='Lemma.Boot.TrialWatchdog.entry'
WATCHDOG_BINDINGS={
 'Lemma.Platform.Silicon.BindingSafety.power_watchdog_timeout_offset':96,
 'Lemma.Platform.Silicon.BindingSafety.power_watchdog_command_offset':104,
 'Lemma.Platform.Silicon.BindingSafety.power_magic_value':1280333650,
 'Lemma.Platform.Silicon.BindingPower.power_base':268502272,
 'Lemma.Platform.Silicon.BindingPower.power_reset_cause_offset':32}
KEY_ID=0x4445560000000001
LITERALS={0x31444d42414d454c,0x31474d49414d454c,0x31585443414d454c,0x3154504345524d4c,0x31564f4345524d4c,
 0x000a000300010001,0x315348414d4c,0x3143414d484d4c,0x31474154414d454c,KEY_ID,0x31544855414d454c,
 0x0706050403020100,0x0f0e0d0c0b0a0908,0x1716151413121110,0x1f1e1d1c1b1a1918,(2<<32)|65544}
def audit(unit,pre,post,*,trial_watchdog=False):
 root=WATCHDOG_ROOT if trial_watchdog else ROOT_NAME
 expected={'schema_version':1,'contract_version':'core0-boot-v0.2' if trial_watchdog else 'core0-boot-v0.1','configuration':WATCHDOG_CONFIG if trial_watchdog else CONFIG,'role':'boot',
  'hardware_profile':'lemma-silicon-dev/0.10.0','image_compatibility':0x000a000300010001,'root':root,
  'rom_base':4096,'rom_bytes':65536,'stack_floor':0x81fd0000,'stack_top':0x82000000,
  'authentication':'HMAC-SHA-256 with PUBLIC DEVELOPMENT KEY; production identity/anti-rollback OPEN',
  'key_id':KEY_ID,'key_public':True,'tag_format':'lemma-development-boot-tag/1',
  'recovery_transport':'lemma-local-uart-development-auth-recovery/2','backend_dispatch':'lemma-boot-direct-branches-v1'}
 if trial_watchdog:expected.update(boot_watchdog_contract='lemma-trial-boot-watchdog/1',trial_watchdog_clocks=2000000000)
 if any(unit.get(k)!=v for k,v in expected.items()) or set(unit)!=set(expected)|{'entry_symbol','functions','used_execution_ops','used_device_ops'}:raise Core0Error('development ROM authority tuple differs')
 rows={};symbols={}
 for row in unit['functions']:
  name=re.sub(r'^_private\.[^.]+(?:\.[^.]+)*?\.[0-9]+\.(Lemma\..*)$',r'\1',row['source']);symbol=row['symbol']
  allowed=('Lemma.Boot.ProductExecuted.','Lemma.Boot.RecoveryExecuted.','Lemma.Boot.DevelopmentAuthentication.','Lemma.Boot.DevelopmentRecovery.','Lemma.Crypto.SHA256.','Lemma.Crypto.HMAC256.','Lemma.Kernel.Memory.Access.','Lemma.Platform.LemmaSim.IO.','Lemma.Core0.Memory.Status.')
  if trial_watchdog:allowed+=('Lemma.Boot.TrialWatchdog.','Lemma.Drivers.PowerSafety.','Lemma.Drivers.Power.')
  if not name.startswith(allowed) and not (trial_watchdog and name in WATCHDOG_BINDINGS):raise Core0Error('foreign ROM source '+name)
  if name in WATCHDOG_BINDINGS and (row['args'] or row['effects']):raise Core0Error('power binding is not a pure closed constant')
  prefix='lemma_trial_watchdog_auth_boot_' if trial_watchdog else 'lemma_development_auth_boot_'
  if name in rows or symbol in symbols or not re.fullmatch(prefix+r'core0_(scalar|action)_[0-9]+',symbol):raise Core0Error('ambiguous ROM provenance')
  if any(a not in ('u8','u32','u64','bool') for a in row['args']) or not set(row['effects'])<={'checked-access','physical-read','physical-write','mmio-read','mmio-write','io-order'}:raise Core0Error('unknown ROM ABI/effects')
  rows[name]=row;symbols[symbol]=name
 required={ROOT_NAME,'Lemma.Boot.DevelopmentAuthentication.boot','Lemma.Boot.DevelopmentAuthentication.verifyLoaded','Lemma.Boot.DevelopmentAuthentication.compareDigest','Lemma.Boot.DevelopmentAuthentication.fallback','Lemma.Boot.DevelopmentRecovery.writeTag','Lemma.Crypto.HMAC256.begin','Lemma.Crypto.HMAC256.update','Lemma.Crypto.HMAC256.finish','Lemma.Crypto.SHA256.compress','Lemma.Boot.ProductExecuted.loadImage','Lemma.Boot.ProductExecuted.publishMetadata'}
 if trial_watchdog:required|={WATCHDOG_ROOT,'Lemma.Boot.TrialWatchdog.armTrial','Lemma.Boot.TrialWatchdog.clearPolicy','Lemma.Drivers.PowerSafety.arm'}|WATCHDOG_BINDINGS.keys()
 if not required<=rows.keys() or unit['entry_symbol']!=rows[root]['symbol'] or rows[root]['args']:raise Core0Error('missing actual authenticated policy closure')
 if any(n in rows for n in ('Lemma.Boot.RecoveryExecuted.entry','Lemma.Boot.RecoveryExecuted.recovery','Lemma.Boot.RecoveryExecuted.commandStep')):raise Core0Error('integrity-only handoff escaped into authenticated ROM')
 if set(unit['used_execution_ops'])!={'lemmasim.device-read64','lemmasim.device-write64','execution.physical-read8','execution.physical-read64','execution.physical-write8','execution.physical-write64'} or set(unit['used_device_ops'])!={'uart.read-status','uart.read-byte','uart.write-byte','uart.enable-reset-fifo'}:raise Core0Error('ROM primitive scope differs')
 for phase,ir in [('pre',pre),('post',post)]:
  if phase=='pre' and trial_watchdog:
   for name,value in WATCHDOG_BINDINGS.items():
    body=re.search(r'(?ms)^define[^\n]*@'+re.escape(rows[name]['symbol'])+r'\(\)[^\n]*\{\n(.*?)^\}',ir)
    if body is None:raise Core0Error('missing actual power constant definition')
    instructions=[line.strip() for line in body[1].splitlines() if line.strip() and not line.strip().endswith(':') and not line.strip().startswith(';')]
    if instructions!=['ret i64 '+str(value)]:raise Core0Error('power constant body differs: '+name)
  definitions=re.findall(r'(?m)^define[^\n]*@([A-Za-z_0-9.$]+)\(',ir)
  if len(definitions)!=len(set(definitions)) or not definitions or not set(definitions)<=symbols.keys() or phase=='pre' and set(definitions)!=symbols.keys():raise Core0Error('ROM LLVM provenance differs')
  if re.search(r'(?m)^@|\basm\b|\b(?:invoke|landingpad|resume|callbr|indirectbr|alloca)\b',ir) or re.search(r'\bcall[^\n]*%[A-Za-z_][A-Za-z_0-9]*\(',ir):raise Core0Error('foreign ROM dispatch/runtime/data')
  declared={}
  for result,name,args in re.findall(r'(?m)^declare\s+(void|i[0-9]+)\s+@([^ (]+)\(([^)]*)\)',ir):declared[name]=result+'('+re.sub(r'\s+','',args)+')'
  if declared.pop('core0_io_fence',None)!='void()' or phase=='pre' and declared or any({'llvm.umin.i64':'i64(i64,i64)','llvm.umax.i4':'i4(i4,i4)','llvm.fshl.i64':'i64(i64,i64,i64)'}.get(n)!=s for n,s in declared.items()):raise Core0Error('unknown ROM helper/intrinsic')
  if not set(re.findall(r'\bcall[^\n]*@([A-Za-z_0-9.$]+)\(',ir))<=set(definitions)|set(declared)|{'core0_io_fence'}:raise Core0Error('unresolved ROM call')
 return {'genuine_functions':len(rows),'optimized_functions':len(definitions),'runtime_helpers':['core0_io_fence'],'intrinsics':declared,'key_scope':'PUBLIC DEVELOPMENT KEY ONLY'}
def build(out,*,trial_watchdog=False):
 if out.exists() or not out.is_relative_to(ROOT/'build'):raise ValueError('unused ignored output required')
 out.mkdir(parents=True);began=time.monotonic();report={'schema':'lemma-development-auth-rom-build/1','status':'FAIL','bounds':{'seconds':600,'command_seconds':180,'per_process_address_space':16<<30,'file_bytes':1<<30},'commands':[]}
 resource.setrlimit(resource.RLIMIT_AS,(16<<30,16<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30))
 try:
  from build_kernel import source_inputs
  before=source_inputs(ROOT)
  for n in ('scripts/build_development_auth_boot.py','scripts/check_crypto.py'):before[n]=sha256(ROOT/n)
  if trial_watchdog:before['scripts/build_trial_watchdog_boot.py']=sha256(ROOT/'scripts/build_trial_watchdog_boot.py')
  report.update(source_inputs=before,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),dirty_paths=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True).splitlines())
  tools=require_tools(('lake','lean','opt','llc','clang','ld.lld','llvm-readelf','llvm-objdump','llvm-objcopy','llvm-nm'));report['tools']={n:{'path':p,'sha256':sha256(Path(p))} for n,p in tools.items()}
  if any(not str(p).startswith('/nix/store/') for p in tools.values()):raise Core0Error('pinned Nix tools required')
  def run(label,argv,env=None):
   left=600-(time.monotonic()-began)
   if left<=0:raise Core0Error('auth ROM aggregate deadline')
   r=run_bounded(argv,cwd=out,timeout_seconds=min(180,left),env=env);(out/(label+'.log')).write_bytes(r.stdout+r.stderr);report['commands'].append({'argv':list(r.argv),'seconds':r.elapsed_seconds,'returncode':r.returncode})
   if r.returncode:raise Core0Error('actual auth ROM command failed: '+label)
   return r.stdout.decode()
  marker='TRIAL_WATCHDOG_AUTH_BOOT_EXPORT:PASS' if trial_watchdog else 'DEVELOPMENT_AUTH_BOOT_EXPORT:PASS'
  command='#lemma_export_trial_watchdog_auth_boot' if trial_watchdog else '#lemma_export_development_auth_boot'
  env={**os.environ,'LEAN_NUM_THREADS':'2','LEMMA_DEVELOPMENT_AUTH_BOOT_OUT':str(out/'component')};export=out/'Export.lean';export.write_text('import Lemma.Compiler.DevelopmentBootExport\n'+command+'\n')
  with (ROOT/'build/task006-lake.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX);run('elaborate',[tools['lake'],'-d',str(ROOT),'build','Lemma.Boot.DevelopmentRecovery','Lemma.Compiler.DevelopmentBootExport'],env)
   if run('export',[tools['lake'],'-d',str(ROOT),'env','lean',str(export)],env).count(marker)!=1:raise Core0Error('missing genuine ROM export')
  d=out/'component';run('verify',[tools['opt'],'-passes=verify','-disable-output',str(d/'program.ll')]);run('opt',[tools['opt'],'-S','-passes=default<O2>',str(d/'program.ll'),'-o',str(d/'program.opt.ll')]);u=json.loads((d/'unit.json').read_text());post=(d/'program.opt.ll').read_text();report['closure']=audit(u,(d/'program.ll').read_text(),post,trial_watchdog=trial_watchdog)
  run('llvm',[tools['llc'],*LLC_ARGUMENTS,'-O2','-stack-size-section',str(d/'program.opt.ll'),'-o',str(d/'program.o')]);run('startup',[tools['clang'],*STARTUP_ARGUMENTS,str(d/'startup.S'),'-o',str(d/'startup.o')]);run('link',[tools['ld.lld'],'-m','elf64lriscv','--no-relax','-T',str(d/'link.ld'),'-o',str(d/'image.elf'),str(d/'startup.o'),str(d/'program.o')]);run('rom',[tools['llvm-objcopy'],'-O','binary',str(d/'image.elf'),str(d/'rom.bin')])
  if run('program-undefined',[tools['llvm-nm'],'--undefined-only',str(d/'program.o')]).split()!=['U','core0_io_fence'] or run('undefined',[tools['llvm-nm'],'--undefined-only',str(d/'image.elf')]).strip():raise Core0Error('unknown auth ROM linked runtime')
  if 'There are no relocations in this file.' not in run('relocations',[tools['llvm-readelf'],'--elf-output-style=GNU','-r',str(d/'image.elf')]):raise Core0Error('ROM runtime relocations')
  literals=LITERALS|({0x31574454414d454c,2000000000} if trial_watchdog else set())
  validate_machine(run('machine',[tools['llvm-objdump'],'-d','--no-show-raw-insn',str(d/'image.elf')]));report['stack']=validate_loop_stack_call_graph(post,parse_stack_sizes(run('stack',[tools['llvm-readelf'],'--elf-output-style=GNU','--stack-sizes',str(d/'program.o')])));report['elf']=audit_elf((d/'image.elf').read_bytes(),base=4096,literals=literals)
  if len((d/'rom.bin').read_bytes())!=report['elf']['RX_load_bytes']:raise Core0Error('ROM raw bytes/load extent differ')
  if any(sha256(ROOT/n)!=h for n,h in before.items()):raise Core0Error('auth ROM source changed')
  report.update(status='PASS_GENUINE_DEVELOPMENT_AUTH_ROM',artifacts={str(f.relative_to(out)):sha256(f) for f in d.iterdir() if f.is_file()},authentication='PUBLIC DEVELOPMENT KEY; production provisioning/anti-rollback OPEN',actual_boot='NOT_RUN')
  if trial_watchdog:report.update(status='PASS_GENUINE_TRIAL_WATCHDOG_AUTH_ROM',boot_watchdog_contract='lemma-trial-boot-watchdog/1',trial_watchdog_clocks=2000000000)
 except BaseException as e:report['error']=repr(e)
 finally:
  report['seconds']=time.monotonic()-began
  if report['seconds']>600:report['status']='FAIL';report['deadline_error']=True
  (out/'build.json').write_text(json.dumps(report,indent=2)+'\n')
 return report
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--public-development-key',action='store_true',required=True);a=p.parse_args();r=build(a.work_dir.resolve());print(json.dumps({'status':r['status'],'seconds':r['seconds'],'error':r.get('error')},indent=2));return 0 if r['status'].startswith('PASS_') else 1
if __name__=='__main__':raise SystemExit(main())
