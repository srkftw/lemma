#!/usr/bin/env python3
"""Local public-development-key ROM sessions over the existing Product10 core.
Host code validates build provenance, transports opaque sectors and presents
actual receipts. MAC checking, selection, loading and installation are Lean.
"""
import argparse,fcntl,json,os,re,selectors,struct,subprocess,time,zlib
from pathlib import Path
import lemmasim_product as product
import lemmasim_session as sessions
import development_install
import product_native as inputs
from build_development_auth_boot import audit,CONFIG,WATCHDOG_CONFIG,KEY_ID,LITERALS
from check_crypto import audit_elf
ROOT=Path(__file__).resolve().parents[1]
SCHEMA='lemma-development-auth-prepared/1'
WATCHDOG_SCHEMA='lemma-development-auth-prepared/2'
CAPABILITY=(2<<32)|65544
def boot_write_limit(value,mode,threads,restoring=False):
 if value is None:return None
 if mode!='laboratory' or threads!=1 or restoring:raise ValueError('boot write limit requires a single-thread Laboratory cold launch')
 if not isinstance(value,str) or not re.fullmatch(r'[0-9]{1,20}:[0-9]{1,20}:[0-9]{1,20}',value):raise ValueError('boot write limit requires decimal first:past:ceiling')
 first,past,ceiling=map(int,value.split(':'))
 if not 0<=first<past<=product.BOOT_BYTES or not 0<=ceiling<=product.BOOT_BYTES:raise ValueError('boot write limit outside actual raw backing')
 return f'{first}:{past}:{ceiling}'
def watchdog_policy(data):
 if data.get('schema')==SCHEMA and data.get('rom_configuration')==CONFIG:
  if 'boot_watchdog_contract' in data or 'trial_watchdog_clocks' in data:raise ValueError('legacy preparation cannot claim trial watchdog authority')
  return False
 if (data.get('schema')==WATCHDOG_SCHEMA and data.get('rom_configuration')==WATCHDOG_CONFIG and
     data.get('boot_watchdog_contract')=='lemma-trial-boot-watchdog/1' and data.get('trial_watchdog_clocks')==2000000000):return True
 raise ValueError('unknown exact development authentication/watchdog tuple')
def rom(build,archive=None,*,trial_watchdog=False):
 build=Path(build).resolve();m=json.loads((build/'build.json').read_text())
 expected_status='PASS_GENUINE_TRIAL_WATCHDOG_AUTH_ROM' if trial_watchdog else 'PASS_GENUINE_DEVELOPMENT_AUTH_ROM'
 if m.get('schema')!='lemma-development-auth-rom-build/1' or m.get('status')!=expected_status:raise ValueError('genuine audited development authentication ROM required')
 if trial_watchdog and (m.get('boot_watchdog_contract')!='lemma-trial-boot-watchdog/1' or m.get('trial_watchdog_clocks')!=2000000000):raise ValueError('unknown trial watchdog ROM authority')
 origin=ROOT if archive is None else Path(archive).resolve()
 if archive is not None:
  side=json.loads((origin.parent/'consumed-source-archive.json').read_text())
  if side.get('schema')!='lemma-consumed-development-auth-source/1' or side.get('original_manifest_sha256')!=inputs.sha(build/'build.json') or side.get('inputs')!=m['source_inputs']:raise ValueError('complete ROM source archive required')
 for name,h in m['source_inputs'].items():
  p=Path(name)
  if p.is_absolute() or '..' in p.parts or (origin/p).is_symlink() or inputs.sha(origin/p)!=h:raise ValueError('changed ROM source '+name)
 for name,h in m['artifacts'].items():
  p=Path(name)
  if p.is_absolute() or '..' in p.parts or (build/p).is_symlink() or inputs.sha(build/p)!=h:raise ValueError('changed ROM artifact '+name)
 for t in m['tools'].values():
  if not t['path'].startswith('/nix/store/') or inputs.sha(t['path'])!=t['sha256']:raise ValueError('changed ROM tool')
 d=build/'component';unit=json.loads((d/'unit.json').read_text());audit(unit,(d/'program.ll').read_text(),(d/'program.opt.ll').read_text(),trial_watchdog=trial_watchdog);audit_elf((d/'image.elf').read_bytes(),base=4096,literals=LITERALS|({0x31574454414d454c,2000000000} if trial_watchdog else set()))
 return {'manifest':m,'binary':d/'rom.bin','unit':unit}
def prepare(args):
 out=args.output_dir.resolve()
 if out.exists():raise ValueError('unused prepared output required')
 trial_watchdog=getattr(args,'trial_watchdog',False)
 selected=getattr(args,'profile',inputs.EXECUTED_PROFILE)
 n=inputs.native(args.native_build,args.native_source_archive,selected);r=rom(args.rom_build,args.rom_source_archive,trial_watchdog=trial_watchdog)
 from silicon_guest_bundle import host_dependencies
 data={'schema':WATCHDOG_SCHEMA if trial_watchdog else SCHEMA,'profile':selected,'boot':'immutable Lean ROM/NV; no running image preload',
  'authentication':'HMAC-SHA-256/PUBLIC DEVELOPMENT KEY ONLY','key_id':KEY_ID,'production_identity':'OPEN','anti_rollback':'OPEN',
  'native_build':str(args.native_build.resolve()),'native_source_archive':str(args.native_source_archive.resolve()) if args.native_source_archive else None,
  'rom_build':str(args.rom_build.resolve()),'rom_source_archive':str(args.rom_source_archive.resolve()) if args.rom_source_archive else None,
  'native_manifest_sha256':inputs.sha(args.native_build/'build.json'),'rom_manifest_sha256':inputs.sha(args.rom_build/'build.json'),
  'binary_sha256':n['manifest']['binary_sha256'],'runtime_identity':n['manifest']['snapshot_identity'],'rom_sha256':inputs.sha(r['binary']),
  'image_compatibility':0x000a000300010001,'rom_configuration':WATCHDOG_CONFIG if trial_watchdog else CONFIG,'recovery_version':2,
  'paper_contract':{'version':3,'staging_offset':3584,'staging_bytes':512,'executed_refresh_offsets':[192,200,208,216,224,232]},
  'host_dependencies':host_dependencies(n['binary']),
  'host_scripts':{str(p.relative_to(ROOT)):inputs.sha(p) for p in (Path(__file__),ROOT/'scripts/development_install.py',ROOT/'scripts/lemmasim_product.py',ROOT/'scripts/product_native.py',ROOT/'scripts/product_archive.py',ROOT/'scripts/lemmasim_session.py',ROOT/'scripts/build_development_auth_boot.py',ROOT/'scripts/check_crypto.py')},
  'qualification':'prepared exact components; actual MAC rejection/install/handoff/recovery separate'}
 if trial_watchdog:data.update(boot_watchdog_contract='lemma-trial-boot-watchdog/1',trial_watchdog_clocks=2000000000)
 out.mkdir(parents=True);data['digital_discovery']=product.profile_discovery(data,out,args.dtc);sessions.write_json(out/'prepared.json',data)
 (out/'DEPENDENCIES.txt').write_text('Local source-bound development machine using PUBLIC TEST KEY00..1f. No production identity/anti-rollback or redistribution license. Existing CVW/Verilator/Nix dependency notices and physical gaps remain applicable. All image/MAC/selection/update policy executes in the Lean ROM.\n')
 return data
def prepared(path):
 path=Path(path);data=json.loads((path/'prepared.json').read_text())
 trial_watchdog=watchdog_policy(data)
 if data.get('profile') not in inputs.EXECUTED_PROFILES or data.get('key_id')!=KEY_ID or data.get('recovery_version')!=2:raise ValueError('unknown exact development authentication tuple')
 n=inputs.native(data['native_build'],data['native_source_archive'],data['profile']);r=rom(data['rom_build'],data['rom_source_archive'],trial_watchdog=trial_watchdog)
 for name,expected in [('native_manifest_sha256',inputs.sha(Path(data['native_build'])/'build.json')),('rom_manifest_sha256',inputs.sha(Path(data['rom_build'])/'build.json')),('binary_sha256',n['manifest']['binary_sha256']),('runtime_identity',n['manifest']['snapshot_identity']),('rom_sha256',inputs.sha(r['binary']))]:
  if data[name]!=expected:raise ValueError('changed prepared identity '+name)
 for name,h in data['host_scripts'].items():
  if inputs.sha(ROOT/name)!=h:raise ValueError('changed prepared host source '+name)
 for name,h in data['host_dependencies'].items():
  if inputs.sha(name)!=h:raise ValueError('changed prepared host library')
 product.validate_discovery(data,path);return data,n,r
class AuthRTL(product.ProductRTL):
 def __init__(self,args,directory):
  data,n,r=prepared(args.prepared);self.identity={'backend':'rtl','profile':data['profile'],'runtime':data['binary_sha256'],'implementation':data['runtime_identity'],'rom':data['rom_sha256'],'boot':'ROM/NV-development-auth-v1','authentication':data['authentication'],'key_id':KEY_ID,'digital_discovery':data['digital_discovery']['descriptor_sha256'],'discovery_bytes':data['digital_discovery']['dtb_bytes'],'image_compatibility':data['image_compatibility'],'paper_contract':data['paper_contract']}
  if watchdog_policy(data):self.identity.update(boot_watchdog_contract=data['boot_watchdog_contract'],trial_watchdog_clocks=data['trial_watchdog_clocks'])
  self.log=(directory/'machine.log').open('wb');self.boot_lock=None;medium=args.boot_medium
  if args.restore:
   if medium is not None or args.disk is not None or args.recovery:raise ValueError('restored private fork owns media/input')
   medium=directory/'startup-boot.raw'
   with medium.open('xb') as f:f.truncate(product.BOOT_BYTES)
  if medium is None or medium.stat().st_size!=product.BOOT_BYTES:raise ValueError('exact blank/existing BootNV capacity required')
  self.boot_lock=medium.open('r+b');fcntl.flock(self.boot_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  command=[str(n['binary']),'--rom',str(r['binary']),'--boot-medium',str(medium.resolve()),'--descriptor',str((Path(args.prepared)/'descriptor.bin').resolve()),'--host-threads',str(args.host_threads),'--session','--quiet-uart','--uart-output',str(directory/'uart.bin'),'--input-capture',str(directory/'input.events'),'--boot-io-capture',str(directory/'boot.nvio'),'--backing-capture',str(directory/'backing.io'),'--fork-directory',str(directory),'--trace-limit',str(args.trace_limit),'--deadline',str(args.timeout)]
  fault=None
  if getattr(args,'boot_write_limit',None) is not None:fault=boot_write_limit(args.boot_write_limit,args.mode,args.host_threads,bool(args.restore))
  if fault is not None:command+=['--boot-write-limit',fault]
  if args.disk is not None:command+=['--medium',str(args.disk.resolve())]
  if args.recovery:
   (directory/'initial-uart').write_bytes(b'R');command+=['--uart-input',str(directory/'initial-uart')]
  self.argv=command;self.timeout=args.timeout;self.input_kinds={'pen','uart','button','pgood','brownout','ble-rx','ble-coex'}
  if data['profile']==inputs.INTEGRATED_PROFILE:self.input_kinds.add('multimodal')
  self.process=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,start_new_session=True,bufsize=0)
  self.reader=selectors.DefaultSelector();self.reader.register(self.process.stdout,selectors.EVENT_READ);self.pending=bytearray()
  try:
   self.checkpoint_identity=self.call('inspect')['snapshot_identity']
   if self.checkpoint_identity!=data['runtime_identity']:raise ValueError('actual runtime identity differs')
  except BaseException:self.close();raise
def frame(transaction,operation,slot=0,relative=0,identity=0,payload=b''):
 if not all(type(n)==int and 0<=n<1<<64 for n in (transaction,operation,slot,relative,identity)):raise ValueError('UInt64 frame fields required')
 if transaction==0 or operation not in range(7) or (operation in (1,5) and len(payload)!=512) or (operation not in (1,5) and payload):raise ValueError('Invalid bounded version2 recovery request')
 words=[product.REQUEST,2,transaction,operation,slot,relative,identity,0,zlib.crc32(payload) if payload else 0];header=struct.pack('<9Q',*words)
 return header+struct.pack('<Q',zlib.crc32(header))+payload
class RecoveryClient(product.RecoveryClient):
 def beacon(self):
  row=self.wait(0)
  if row!={'transaction':0,'status':0,'value':CAPABILITY}:raise ValueError('version2 development ROM beacon differs')
  return row
 def send(self,operation,slot=0,relative=0,identity=0,payload=b''):
  if self.next_id>=1<<64:raise ValueError('transaction exhausted')
  tx=self.next_id;self.next_id+=1;wire=frame(tx,operation,slot,relative,identity,payload);uart=self.directory/'uart.bin';past=uart.read_bytes() if uart.exists() else b''
  if past:product.receipt(past[-40:])
  self.cursor=len(past);self.call({'action':'inject','kind':'uart','hex':wire.hex()});return self.wait(tx)
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--public-development-key',action='store_true',required=True);sub=p.add_subparsers(dest='command',required=True)
 a=sub.add_parser('prepare');a.add_argument('--profile',choices=inputs.EXECUTED_PROFILES,default=inputs.EXECUTED_PROFILE);a.add_argument('--native-build',type=Path,required=True);a.add_argument('--native-source-archive',type=Path);a.add_argument('--rom-build',type=Path,required=True);a.add_argument('--rom-source-archive',type=Path);a.add_argument('--output-dir',type=Path,required=True);a.add_argument('--dtc')
 a.add_argument('--trial-watchdog',action='store_true',help='Require the separately audited core0-boot-v0.2 trial-watchdog ROM; actual execution qualification separate')
 a=sub.add_parser('archive');a.add_argument('--prepared',type=Path,required=True);a.add_argument('--output-dir',type=Path,required=True)
 a=sub.add_parser('create-medium');a.add_argument('--boot-medium',type=Path,required=True)
 a=sub.add_parser('launch');a.add_argument('--prepared',type=Path,required=True);a.add_argument('--session-dir',type=Path,required=True);a.add_argument('--boot-medium',type=Path);a.add_argument('--disk',type=Path);a.add_argument('--restore',type=Path);a.add_argument('--recovery',action='store_true');a.add_argument('--mode',choices=['student','developer','laboratory'],default='developer');a.add_argument('--paused',action='store_true');a.add_argument('--headless',action='store_true');a.add_argument('--timeout',type=int,default=120);a.add_argument('--quantum',type=int,default=1000000);a.add_argument('--tablet',type=Path);a.add_argument('--trace-limit',type=int,default=0);a.add_argument('--host-threads',type=int,default=1)
 a.add_argument('--boot-write-limit',help='Laboratory Linux only: real scoped RLIMIT_FSIZE for writes intersecting first:past, ceiling in raw bytes; requires a supporting native build')
 for name in ('capacity','key-info','install','install-resume','tag','publish','status','boot'):
  a=sub.add_parser(name);a.add_argument('--session-dir',type=Path,required=True);a.add_argument('--timeout',type=int,default=120);a.add_argument('--cycles',type=int,default=10000000);a.add_argument('--quantum',type=int,default=100000);a.add_argument('--transaction',type=lambda x:int(x,0),default=time.time_ns());a.add_argument('--continue-recovery',action='store_true');a.add_argument('--slot',type=int,choices=[0,1],default=0);a.add_argument('--image-id',type=lambda x:int(x,0),default=0);a.add_argument('--package',type=Path);a.add_argument('--tag',type=Path)
 args=p.parse_args(argv)
 try:
  if args.command=='prepare':result=prepare(args)
  elif args.command=='archive':
   from product_archive import create
   result=create(args.prepared,args.output_dir,prepared)
  elif args.command=='create-medium':
   args.boot_medium.parent.mkdir(parents=True,exist_ok=True)
   with args.boot_medium.open('xb') as f:f.truncate(product.BOOT_BYTES);f.flush();os.fsync(f.fileno())
   result={'state':'blank raw backing; no payload/metadata/tag preinstalled','bytes':product.BOOT_BYTES}
  elif args.command=='launch':
   if not 1<=args.quantum<=1000000 or not 1<=args.timeout<=7200 or not 1<=args.host_threads<=64:raise ValueError('bounded launch required')
   args.boot_write_limit=boot_write_limit(args.boot_write_limit,args.mode,args.host_threads,bool(args.restore))
   args.backend='rtl';args.workload='product';args.profile=prepared(args.prepared)[0]['profile'];sessions.serve(args,AuthRTL,product.ProductSession);return 0
  else:
   if not 1<=args.quantum<=1000000 or not 1<=args.cycles<=2000000000 or not 1<=args.timeout<=7200:raise ValueError('bounded recovery required')
   resume_inputs=None
   if args.command=='install-resume':
    if args.package is None or args.tag is None:raise ValueError('install-resume requires opaque package and slot-specific tag')
    resume_inputs=development_install.load_package(args.package,args.tag,inputs.sha)
   c=RecoveryClient(args);beacon=None if args.continue_recovery else c.beacon();rows=[]
   if args.command=='install-resume':
    package,wire,tag=resume_inputs;product.install_extent(package,wire,c.call({'action':'inspect'})['identity'])
    result=development_install.resume(c,package,wire,tag,args.slot)
    result.update(beacon=beacon,cycles=c.used,key_scope='PUBLIC DEVELOPMENT KEY ONLY')
    print(json.dumps(result,indent=2));return 0
   if args.command=='install':
    if args.package is None or args.tag is None:raise ValueError('install requires opaque package and slot-specific tag')
    package=json.loads((args.package/'package.json').read_text());image=args.package/'image.bin'
    if package.get('status')!='PASS' or inputs.sha(image)!=package['image_sha256']:raise ValueError('changed image package')
    wire=image.read_bytes();product.install_extent(package,wire,c.call({'action':'inspect'})['identity']);identity=package['identity']
    for i in range(len(wire)//512):
     row=c.send(1,args.slot,i,identity,wire[i*512:i*512+512]);rows.append(row)
     if row['status']:raise ValueError('actual payload receipt failed '+str(row))
    row=c.send(5,args.slot,identity=identity,payload=args.tag.read_bytes());rows.append(row)
    if row['status']:raise ValueError('actual tag receipt failed '+str(row))
    rows.append(c.send(2,args.slot,identity=identity))
   elif args.command=='tag':
    if args.tag is None:raise ValueError('tag file required')
    rows.append(c.send(5,args.slot,identity=args.image_id,payload=args.tag.read_bytes()))
   else:rows.append(c.send({'capacity':0,'publish':2,'boot':3,'status':4,'key-info':6}[args.command],args.slot,identity=args.image_id))
   result={'beacon':beacon,'receipts':rows,'cycles':c.used,'key_scope':'PUBLIC DEVELOPMENT KEY ONLY'}
   if any(r['status'] for r in rows):raise ValueError('actual ROM rejection '+str(result))
  print(json.dumps(result,indent=2));return 0
 except (OSError,ValueError,RuntimeError,KeyError,TimeoutError,struct.error,subprocess.SubprocessError) as e:p.error(str(e))
if __name__=='__main__':raise SystemExit(main())
