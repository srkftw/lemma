#!/usr/bin/env python3
"""ROM-only product machine and opaque local recovery UART client.

The compiled Lean ROM installs, validates, selects and loads images. This host
adapter transports sectors and checks actual receipts; it never writes metadata,
guest RAM, notebook records, or authentication/controller success state.
"""
from pathlib import Path
import argparse,fcntl,json,os,selectors,signal,struct,subprocess,time,zlib
import lemmasim_session as sessions
import product_native as inputs

ROOT=Path(__file__).resolve().parents[1]
BOOT_BYTES=65544*512
REQUEST=0x31564f4345524d4c
RECEIPT=0x3154504345524d4c

def prepare(args):
 out=args.output_dir.resolve()
 if out.exists():raise ValueError('prepared output must be unused')
 n=inputs.native(args.native_build,args.native_source_archive)
 r=inputs.rom(args.rom_build,args.rom_source_archive)
 from silicon_guest_bundle import host_dependencies
 data={'schema':'lemma-product-prepared/1','profile':inputs.PROFILE,
  'boot':'immutable Lean ROM; image and DTB loaded by real BootNV transactions',
  'authentication':'OPEN integrity-only owner-local recovery','anti_rollback':'OPEN',
  'native_build':str(args.native_build.resolve()),'rom_build':str(args.rom_build.resolve()),
  'native_source_archive':str(args.native_source_archive.resolve()) if args.native_source_archive else None,
  'rom_source_archive':str(args.rom_source_archive.resolve()) if args.rom_source_archive else None,
  'native_manifest_sha256':inputs.sha(args.native_build/'build.json'),
  'rom_manifest_sha256':inputs.sha(args.rom_build/'build.json'),
  'binary_sha256':n['manifest']['binary_sha256'],'runtime_identity':n['manifest']['snapshot_identity'],
  'rom_sha256':r['manifest']['artifacts']['rom.bin'],'host_dependencies':host_dependencies(n['binary']),
  'host_scripts':{str(p.relative_to(ROOT)):inputs.sha(p) for p in (Path(__file__),ROOT/'scripts/product_native.py',ROOT/'scripts/lemmasim_session.py')},
  'qualification':'prepared exact component inputs; product boot/update acceptance separate'}
 out.mkdir(parents=True);sessions.write_json(out/'prepared.json',data)
 (out/'DEPENDENCIES.txt').write_text('Local path-bound prepared product machine. Requires the exact recorded native build/source archives and Nix loader/libraries; no redistribution license is granted. CVW20f2af74 Apache-2.0 WITH SHL-2.1 and preserved notices; Verilator5.052 LGPL-3.0-only OR Artistic-2.0. All target ROM/image policy is Lean. CRC32 integrity is not authentication or anti-rollback. Physical nonvolatile qualification OPEN.\n')
 return {'prepared':str(out),'rom':data['rom_sha256'],'native':data['binary_sha256']}

def prepared(path):
 data=json.loads((Path(path)/'prepared.json').read_text())
 if data.get('schema')!='lemma-product-prepared/1' or data.get('profile')!=inputs.PROFILE:
  raise ValueError('Unsupported product prepared machine')
 for key,build in (('native_manifest_sha256','native_build'),('rom_manifest_sha256','rom_build')):
  if inputs.sha(Path(data[build])/'build.json')!=data[key]:raise ValueError('Changed prepared original build manifest')
 n=inputs.native(data['native_build'],data['native_source_archive']);r=inputs.rom(data['rom_build'],data['rom_source_archive'])
 if (data['binary_sha256']!=n['manifest']['binary_sha256'] or data['runtime_identity']!=n['manifest']['snapshot_identity'] or data['rom_sha256']!=r['manifest']['artifacts']['rom.bin']):
  raise ValueError('Contradictory prepared product identities')
 for p,h in data['host_scripts'].items():
  if inputs.sha(ROOT/p)!=h:raise ValueError('Changed prepared product host interface')
 for p,h in data['host_dependencies'].items():
  if inputs.sha(p)!=h:raise ValueError('Changed prepared native host library')
 return data,n,r

class ProductRTL(sessions.RTL):
 def __init__(self,args,directory):
  data,n,r=prepared(args.prepared);self.identity={'backend':'rtl','profile':inputs.PROFILE,
   'runtime':data['binary_sha256'],'implementation':data['runtime_identity'],'rom':data['rom_sha256'],
   'boot':'ROM/NV-v1','authentication':'integrity-only owner-local'}
  self.log=(directory/'machine.log').open('wb');self.boot_lock=None
  medium=args.boot_medium
  if args.restore:
   if medium is not None or args.disk is not None or args.recovery:raise ValueError('Restored product fork owns both media and queued input; omit disk/boot-medium/recovery')
   # No cycles execute against this private empty startup medium. Exact restore
   # validates then replaces it with privately backed checkpoint state.
   medium=directory/'startup-boot.raw'
   with medium.open('xb') as f:f.truncate(BOOT_BYTES)
  if medium is None or medium.stat().st_size!=BOOT_BYTES:raise ValueError('Product boot medium must be exactly65544 sectors')
  self.boot_lock=medium.open('r+b');fcntl.flock(self.boot_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  command=[str(n['binary']),'--rom',str(r['binary']),'--boot-medium',str(medium.resolve()),
   '--session','--quiet-uart','--uart-output',str(directory/'uart.bin'),'--input-capture',str(directory/'input.events'),
   '--boot-io-capture',str(directory/'boot.nvio'),'--backing-capture',str(directory/'backing.io'),
   '--fork-directory',str(directory),'--trace-limit',str(args.trace_limit),'--deadline',str(args.timeout)]
  if args.disk is not None:command+=['--medium',str(args.disk.resolve())]
  if args.recovery:
   (directory/'initial-uart').write_bytes(b'R');command+=['--uart-input',str(directory/'initial-uart')]
  self.argv=command;self.timeout=args.timeout;self.input_kinds={'pen','uart','button','pgood','brownout','ble-rx','ble-coex'}
  self.process=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,start_new_session=True,bufsize=0)
  self.reader=selectors.DefaultSelector();self.reader.register(self.process.stdout,selectors.EVENT_READ);self.pending=bytearray()
  try:
   self.checkpoint_identity=self.call('inspect')['snapshot_identity']
   if self.checkpoint_identity!=data['runtime_identity']:raise ValueError('Actual native runtime differs from prepared identity')
  except BaseException:self.close();raise
 def preflight_checkpoint(self,path,expected_cycle):
  path=Path(path)
  with path.open('rb') as f:h=f.read(128)
  if len(h)!=128 or h[:8]!=b'LMSSRTL1' or int.from_bytes(h[8:16],'little')!=7 or h[16:80]!=self.checkpoint_identity.encode():raise ValueError('Product checkpoint version/runtime mismatch')
  wrapper=int.from_bytes(h[80:88],'little');model=int.from_bytes(h[88:96],'little')
  if wrapper<16 or not 0<model<=64*1024*1024 or 112+wrapper+model!=path.stat().st_size or int.from_bytes(h[120:128],'little')!=expected_cycle:raise ValueError('Product checkpoint boundary/length mismatch')
 def close(self):
  try:super().close()
  finally:
   if self.boot_lock:self.boot_lock.close();self.boot_lock=None

class ProductSession(sessions.Session):
 def dispatch(self,value):
  if isinstance(value,dict) and value.get('action') in ('boot-outcomes','export-boot-medium'):
   if self.mode not in ('developer','laboratory'):raise ValueError('Boot backing inspection requires Developer or Laboratory mode')
   self.ensure_capture_certain();p=str(Path(value['path']).resolve())
   if '\n' in p or '\r' in p:raise ValueError('Boot path contains command delimiter')
   return self.machine.call(value['action']+' '+p)
  return super().dispatch(value)

def receipt(raw):
 if len(raw)!=40:raise ValueError('Recovery receipt must have five complete words')
 magic,transaction,status,value,crc=struct.unpack('<5Q',raw)
 if magic!=RECEIPT or status>255 or crc!=zlib.crc32(raw[:32]):raise ValueError('Corrupt recovery receipt')
 return {'transaction':transaction,'status':status,'value':value}

def frame(transaction,operation,slot=0,relative=0,identity=0,payload=b''):
 for x in (transaction,operation,slot,relative,identity):
  if type(x)!=int or not 0<=x<1<<64:raise ValueError('Recovery fields require exact UInt64')
 if transaction==0 or operation not in range(5) or (operation==1 and len(payload)!=512) or (operation!=1 and payload):raise ValueError('Invalid bounded recovery request')
 words=(REQUEST,1,transaction,operation,slot,relative,identity,0,zlib.crc32(payload) if payload else 0)
 first=struct.pack('<9Q',*words);return first+struct.pack('<Q',zlib.crc32(first))+payload

class RecoveryClient:
 def __init__(self,args):
  self.directory=args.session_dir.resolve();self.timeout=args.timeout;self.quantum=args.quantum
  self.max_cycles=args.cycles;self.deadline=time.monotonic()+args.timeout;self.cursor=0;self.used=0
  self.next_id=args.transaction
  self.call({'action':'pause'})
 def call(self,request):return sessions.request(self.directory,request,min(self.timeout,120))
 def wait(self,transaction):
  uart=self.directory/'uart.bin'
  while True:
   if uart.exists() and uart.stat().st_size>16*1024*1024:raise ValueError('Recovery UART transcript exceeds its16MiB bound')
   raw=uart.read_bytes() if uart.exists() else b''
   while len(raw)-self.cursor>=40:
    row=receipt(raw[self.cursor:self.cursor+40]);self.cursor+=40
    if row['transaction']==transaction:return row
   if time.monotonic()>=self.deadline or self.used>=self.max_cycles:raise TimeoutError('Declared recovery receipt cycle/host bound exceeded; no durable acknowledgment')
   count=min(self.quantum,self.max_cycles-self.used);self.call({'action':'run','cycles':count});self.used+=count
 def beacon(self):
  row=self.wait(0)
  if row!={'transaction':0,'status':0,'value':65544}:raise ValueError('ROM recovery capacity beacon differs')
  return row
 def send(self,operation,slot=0,relative=0,identity=0,payload=b''):
  if self.next_id>=1<<64:raise ValueError('Recovery transaction identity exhausted')
  tx=self.next_id;self.next_id+=1;wire=frame(tx,operation,slot,relative,identity,payload)
  self.call({'action':'inject','kind':'uart','hex':wire.hex()})
  return self.wait(tx)

def recovery(args):
 client=RecoveryClient(args)
 # Consume the actual reset beacon before framing a new request. The UART FIFO
 # reset belongs to the ROM, so queued pre-beacon payload is never assumed safe.
 beacon=None if args.continue_recovery else client.beacon();rows=[]
 if args.command=='install':
  package=json.loads((args.package/'package.json').read_text());path=args.package/'image.bin'
  if package.get('schema')!='lemma-product-image/1' or package.get('status')!='PASS' or inputs.sha(path)!=package.get('image_sha256'):raise ValueError('Changed opaque compiled image package')
  wire=path.read_bytes()
  if not wire or len(wire)%512 or len(wire)>16*1024*1024:raise ValueError('Invalid bounded image sector payload')
  for index in range(len(wire)//512):
   row=client.send(1,args.slot,index,package['identity'],wire[index*512:index*512+512]);rows.append(row)
   if row['status']:raise RuntimeError('ROM rejected image sector: '+json.dumps(row))
  row=client.send(2,args.slot,identity=package['identity']);rows.append(row)
 elif args.command=='status':row=client.send(4,args.slot,identity=args.image_id);rows.append(row)
 elif args.command=='boot':row=client.send(3);rows.append(row)
 else:row=client.send(0);rows.append(row)
 if row['status']:raise RuntimeError('ROM returned unsuccessful recovery result: '+json.dumps(row))
 return {'beacon':beacon,'receipts':rows,'cycles':client.used,'durability':'only the actual successful target publication/status receipt acknowledges installation; CRC integrity only'}

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
 a=sub.add_parser('prepare');a.add_argument('--native-build',type=Path,required=True);a.add_argument('--native-source-archive',type=Path);a.add_argument('--rom-build',type=Path,required=True);a.add_argument('--rom-source-archive',type=Path);a.add_argument('--output-dir',type=Path,required=True)
 a=sub.add_parser('create-medium');a.add_argument('--boot-medium',type=Path,required=True)
 a=sub.add_parser('launch');a.add_argument('--prepared',type=Path,required=True);a.add_argument('--session-dir',type=Path,required=True);a.add_argument('--boot-medium',type=Path);a.add_argument('--disk',type=Path);a.add_argument('--restore',type=Path);a.add_argument('--recovery',action='store_true');a.add_argument('--mode',choices=['student','developer','laboratory'],default='student');a.add_argument('--paused',action='store_true');a.add_argument('--headless',action='store_true');a.add_argument('--timeout',type=int,default=120);a.add_argument('--quantum',type=int,default=1000000);a.add_argument('--tablet',type=Path);a.add_argument('--trace-limit',type=int,default=0)
 for name in ('capacity','install','status','boot'):
  a=sub.add_parser(name);a.add_argument('--session-dir',type=Path,required=True);a.add_argument('--timeout',type=int,default=120);a.add_argument('--cycles',type=int,default=10000000);a.add_argument('--quantum',type=int,default=100000);a.add_argument('--transaction',type=lambda x:int(x,0),default=time.time_ns());a.add_argument('--continue-recovery',action='store_true',help='An earlier owner observed the ROM beacon; supply only future framed requests after restore. Every result still requires an actual CRC-checked receipt.')
  if name in ('install','status'):a.add_argument('--slot',type=int,choices=[0,1],required=True)
  if name=='install':a.add_argument('--package',type=Path,required=True)
  if name=='status':a.add_argument('--image-id',type=lambda x:int(x,0),required=True)
 args=p.parse_args(argv)
 try:
  if args.command=='prepare':result=prepare(args)
  elif args.command=='create-medium':
   args.boot_medium.parent.mkdir(parents=True,exist_ok=True)
   with args.boot_medium.open('xb') as f:f.truncate(BOOT_BYTES);f.flush();os.fsync(f.fileno())
   result={'boot_medium':str(args.boot_medium.resolve()),'bytes':BOOT_BYTES,'state':'blank raw backing; no image or metadata preinstalled'}
  elif args.command=='launch':
   if not 1<=args.quantum<=1000000 or not 1<=args.timeout<=7200:raise ValueError('Invalid bounded session resource limits')
   args.backend='rtl';args.workload='product';args.profile=inputs.PROFILE
   sessions.serve(args,ProductRTL,ProductSession);return 0
  else:
   if not 1<=args.quantum<=1000000 or not 1<=args.cycles<=2000000000 or not 1<=args.timeout<=7200:raise ValueError('Invalid bounded recovery resource limits')
   result=recovery(args)
  print(json.dumps(result,indent=2));return 0
 except (OSError,ValueError,RuntimeError,KeyError,TimeoutError,struct.error) as e:p.error(str(e))
if __name__=='__main__':raise SystemExit(main())
