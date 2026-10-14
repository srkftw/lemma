#!/usr/bin/env python3
"""Bounded genuine Common12 owned READ512 and independent hosted-Lean peer.

Host transport supplies raw external peer PIO, clocks and opaque medium bytes.
Guest request construction, response validation and ownership remain compiled
Lean. This is CommonOFDM DATA prerequisite evidence, not Wi-Fi6 or durability.
"""
from __future__ import annotations
import argparse,json,mmap,os,re,select,shutil,signal,struct,subprocess,time
from pathlib import Path
from check_wifi_common_guest import require,file_sha

ROOT=Path(__file__).resolve().parents[1]
CONFIGURATION='lemmasim-silicon-wifi-common-read-probe'
WRITER=0x445566778899aabb
INITIAL_CYCLES=30000000
INITIAL_SECONDS=600
SUFFIX_CYCLES=2000000
SUFFIX_SECONDS=120

def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')

def validate_inputs(native,capture,rom_bundle,peer_prepared,out):
 compiled=json.loads((native/'result.json').read_text());manifest=json.loads((native/'build.json').read_text())
 require(compiled['status']=='PASS_NATIVE_BUILD_ONLY' and compiled['input_count']==len(compiled['source_inventory']), 'complete native build is unqualified')
 require({'sim/rtl/lemma_soc.sv','sim/rtl/lemma_wifi_ofdm_data.sv','sim/rtl/host/machine_runtime.wifi.inc.cpp','sim/profiles/lemma-silicon-dev-0.12.0.json'}<=set(compiled['source_inventory']), 'native12 corpus incomplete')
 for name,digest in compiled['source_inventory'].items():
  relative=Path(name);require(not relative.is_absolute() and '..' not in relative.parts,'native archive path')
  require(file_sha(native/'consumed-source-root'/relative)==digest,'native archive differs: '+name)
 binary=Path(compiled['binary']['path'])
 require(file_sha(binary)==compiled['binary']['sha256']==manifest['binary_sha256'] and compiled['runtime_identity']==manifest['snapshot_identity'],'native binary/identity differs')
 result=json.loads((capture/'result.json').read_text());target=capture/'target'
 build=json.loads((target/'build.json').read_text());audit=json.loads((target/'audit.json').read_text())
 require(result['status']=='PASS_WHOLE_AUDIT_ONLY' and build['status']=='BUILT' and audit['status']=='PASS','whole read image unqualified')
 require(build['configuration']==audit['configuration']==CONFIGURATION and audit['stage']=='supervisor','wrong read selection')
 require(result['source_count']==len(result['source_inputs']) and {'Lemma/Radio/WiFi/Block.lean','Lemma/Platform/Silicon/Development/WiFiCommonReadProbe.lean','scripts/wifi_owned_read.py','tooling/wifi-owned-read-authority.json'}<=set(result['source_inputs']),'read source corpus incomplete')
 for name,digest in result['source_inputs'].items():
  relative=Path(name);require(not relative.is_absolute() and '..' not in relative.parts,'target archive path')
  require(file_sha(capture/'consumed-source-root'/relative)==digest,'read archive differs: '+name)
 require(build['artifacts'],'empty read artifacts')
 for name,digest in build['artifacts'].items():
  relative=Path(name);require(not relative.is_absolute() and '..' not in relative.parts,'target artifact path')
  require(file_sha(target/relative)==digest,'read artifact differs: '+name)
 require(file_sha(target/'image.elf')==audit['image_sha256']==result['elf_sha256'],'read ELF differs')
 require(json.loads((target/'binding.json').read_text())['profile_sha256']==manifest['profile_sha256'],'native/read profile association differs')
 require(audit['elf']['boot']['common_pmp']['base']==0x10013000 and audit['elf']['boot']['common_pmp']['bytes']==1024,'read PMP grant differs')
 rom=rom_bundle/'runtime/rtl/boot.bin';bundle=json.loads((rom_bundle/'bundle.json').read_text())
 require(file_sha(rom)==bundle['backends']['rtl']['rom']['sha256'],'ROM association differs')
 # Narrow reuse of the independently compiled Peer binary. Client.lean and its
 # launcher are not linked into this binary; their changed whole-preparation
 # identity remains an ordinary rejection, never rewritten as unchanged.
 prepared=json.loads(peer_prepared.read_text())
 require(prepared['schema']=='lemma-companion-backing-dev/1' and prepared['target_objects_added']==[], 'not a hosted-only peer')
 peer_sources=('sim/companion/Protocol.lean','sim/companion/HostIO.lean','sim/companion/Peer.lean','sim/companion/os_io.py','flake.lock')
 archive=out/'peer-source-root';archive.mkdir()
 for name in peer_sources:
  source=ROOT/name;require(file_sha(source)==prepared['sources'][name],'actual selected peer source differs: '+name)
  destination=archive/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
 for name in ('Protocol.c','HostIO.c','Peer.c','Protocol.o','HostIO.o','Peer.o'):
  require(file_sha(peer_prepared.parent/name)==prepared['generated_host_objects'][name],'selected peer object differs: '+name)
 for tool in ('lean','leanc','cc'):
  row=prepared['host_tools'][tool];require(file_sha(Path(row['path']))==row['sha256'],'selected peer tool differs: '+tool)
 peer_row=prepared['binaries']['companion-peer'];peer=Path(peer_row['path'])
 require(file_sha(peer)==peer_row['sha256'] and os.access(peer,os.X_OK),'peer executable differs')
 write(out/'inputs.json',{'native':compiled,'target':result,'audit_sha256':file_sha(target/'audit.json'),
  'peer_prepared_sha256':file_sha(peer_prepared),'selected_peer_sources':{n:prepared['sources'][n] for n in peer_sources},
  'peer_binary':peer_row,'scope':'exact selected Peer binary closure; old whole Client/launcher preparation not requalified'})
 return binary,compiled['runtime_identity'],target,rom,peer,archive/'sim/companion/os_io.py'

class Owner:
 def __init__(self,binary,directory,target=None,rom=None,cut=None,bound=120):
  self.directory=directory;directory.mkdir();self.started=time.monotonic();self.bound=bound
  self.commands=[];self.raw=[];self.peak=0;self.log=(directory/'stderr.log').open('xb')
  argv=[str(binary),'--session','--quiet-uart','--trace-limit','0','--deadline',str(bound),'--uart-output',str(directory/'uart.bin')]
  if cut is None:argv+=['--image',str(target/'image.elf'),'--rom',str(rom),'--load','0x87e00000:'+str(target/'platform.dtb'),'--descriptor',str(target/'descriptor.bin')]
  else:argv+=['--restore',str(cut),'--fork-directory',str(directory)]
  write(directory/'argv.json',argv)
  self.process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,text=True,start_new_session=True)
  write(directory/'owner.json',{'pid':self.process.pid,'argv':argv})
 def call(self,line):
  left=self.bound-(time.monotonic()-self.started)
  require(left>0 and self.process.poll() is None,'owner bound/termination: '+str(self.directory))
  self.process.stdin.write(line+'\n');self.process.stdin.flush()
  require(select.select([self.process.stdout],[],[],left)[0],'native response timeout')
  raw=self.process.stdout.readline();require(raw,'native EOF: '+str(self.directory/'stderr.log'))
  value=json.loads(raw);self.commands.append({'command':line,'response':value});require(value['ok'],value)
  status=Path('/proc')/str(self.process.pid)/'status'
  if status.exists():
   match=re.search(r'^VmHWM:\s+(\d+) kB$',status.read_text(),re.M)
   if match:self.peak=max(self.peak,int(match[1]))
  return value['result']
 def pio(self,cycle,pairs):
  rows=[f'{cycle} wifi-peer-pio {offset} {value}' for offset,value in pairs]
  self.raw.extend(rows)
  for row in rows:self.call('inject '+row)
 def snapshot(self,name):
  path=self.directory/(name+'.chk');self.call('snapshot '+str(path));return path
 def close(self):
  try:
   if self.process.poll() is None:
    try:self.call('destroy');self.process.wait(timeout=5)
    except BaseException:os.killpg(self.process.pid,signal.SIGKILL);self.process.wait(timeout=5)
  finally:
   self.log.close();write(self.directory/'commands.json',self.commands);write(self.directory/'raw-events.json',self.raw)
   write(self.directory/'resources.json',{'wall_seconds':time.monotonic()-self.started,'VmHWM_kib':self.peak,'exit_code':self.process.returncode})

def observe_ram(path,identity):
 with path.open('rb') as stream:
  d=mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ)
  try:
   require(d[:8]==b'LMSSRTL1' and struct.unpack_from('<Q',d,8)[0]==9 and d[16:80].decode()==identity,'checkpoint version/backend differs')
   wrapper,logical=struct.unpack_from('<QQ',d,80);require(len(d)==112+wrapper+logical,'checkpoint container differs')
   at=112+(43+25+3+3+4+5)*8
   length=struct.unpack_from('<Q',d,at)[0];at+=8;uart=bytes(d[at:at+length]);at+=length
   length=struct.unpack_from('<Q',d,at)[0];at+=8+length
   length=struct.unpack_from('<Q',d,at)[0];at+=8;require(length==134217728,'RAM extent differs')
   word=lambda a:struct.unpack_from('<Q',d,at+a-0x80000000)[0]
   handle=word(0x804e0120);frame=0x82000000+(handle%8192)*4096
   record=lambda h:[word(0x80401000+(h%8192)*32+i*8) for i in range(4)]
   context=[word(frame+i*8) for i in range(13)];packet=context[8]
   observed={'handle':handle,'frame':frame,'context':context,'context_record':record(handle),
    'packet_record':record(packet) if packet else None,'queue':[word(0x804e0000+i*8) for i in (0,1,2,3,6,7)],
    'owned':word(0x80441000),'available':word(0x80400100),'terminal':word(0x804e0138),
    'request_hex':bytes(d[at+frame-0x80000000+128:at+frame-0x80000000+200]).hex(),
    'reply_hex':bytes(d[at+frame-0x80000000+768:at+frame-0x80000000+1352]).hex(),
    'result_hex':bytes(d[at+frame-0x80000000+1536:at+frame-0x80000000+2048]).hex()}
   observed['all_owner_pin_zero']=all(word(0x80401000+i*32)==0 and word(0x80401010+i*32)==0 for i in range(8192))
   return observed,uart
  finally:d.close()

def validate_resume(path,target,rom,identity):
 """Read-only admission of an actual in-flight guest checkpoint and peer reply.
 Never advances the completed request prefix or changes a saved state field.
 """
 observation=json.loads(path.read_text())
 require(observation['schema']=='lemma-owned-read-pending-observation/1' and observation['status']=='PASS_OBSERVED_GENUINE_READ_PENDING','unqualified pending read observation')
 cut=Path(observation['cut']);require(file_sha(cut)==observation['cut_sha256'] and observation['runtime_identity']==identity and file_sha(target/'image.elf')==observation['elf_sha256'],'pending source/backend association differs')
 ram,uart=observe_ram(cut,identity);require(ram==observation['ram'],'pending read RAM observation differs')
 require(ram['context'][:7]==[0x3152444d46495743,2,72,0,WRITER,4096,0] and ram['context'][7] in (0,1),'pending read context differs')
 require(ram['context_record']==[1,4,1,ram['handle']//8192] and ram['packet_record'][0:3]==[1,4,0] and ram['owned']==2 and ram['queue'][1:4]==[0,0,5],'pending ownership differs')
 state=observation['state'];require(state['cycle']==observation['cycle'] and state['wifi']['chip']['rx_active']==1 and state['wifi']['chip']['rx_packets']==0 and state['wifi']['chip']['tx_packets']==5 and state['wifi']['peer']['rx_packets']==5,'pending controller traffic differs')
 reply=Path(observation['peer_reply']);request=Path(observation['peer_request'])
 require(file_sha(reply)==observation['peer_reply_sha256'] and reply.read_bytes().hex()==observation['reply_hex'] and len(reply.read_bytes())==584,'actual independent peer reply differs')
 require(file_sha(request)==observation['peer_request_sha256'] and request.read_bytes().hex()==ram['request_hex'],'actual decoded request differs')
 # Compare every executable load segment and the reset ROM in the saved RAM.
 # Identity of headers may not substitute for these actual immutable bytes.
 with cut.open('rb') as stream:
  d=mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ)
  try:
   at=112+(43+25+3+3+4+5)*8
   for _ in range(2):n=struct.unpack_from('<Q',d,at)[0];at+=8+n
   n=struct.unpack_from('<Q',d,at)[0];at+=8;require(n==134217728,'pending RAM extent')
   elf=(target/'image.elf').read_bytes();require(elf[:6]==b'\x7fELF\x02\x01','audited RV64 ELF identity')
   phoff=struct.unpack_from('<Q',elf,32)[0];stride,amount=struct.unpack_from('<HH',elf,54);require(stride==56 and amount>0,'ELF load headers')
   executable=0
   for i in range(amount):
    kind,flags,offset,_,physical,filesz,_,_=struct.unpack_from('<IIQQQQQQ',elf,phoff+i*stride)
    if kind!=1 or not flags&1:continue
    require(0x80000000<=physical and physical+filesz<=0x88000000 and offset+filesz<=len(elf),'executable bounds')
    require(d[at+physical-0x80000000:at+physical-0x80000000+filesz]==elf[offset:offset+filesz],'pending immutable executable bytes differ');executable+=1
   require(executable>=2,'missing M/S executable segments')
   position=at+n;extent=struct.unpack_from('<Q',d,position)[0];position+=8;raw=rom.read_bytes()
   require(0<len(raw)<=extent and d[position:position+len(raw)]==raw and not any(d[position+len(raw):position+extent]),'pending reset ROM differs')
  finally:d.close()
 if ram['context'][7]==0:
  # This observed cut is in the actual IO.write64 primitive that accepted RX
  # ARM, before Controller.arm returns and the client stores its software flag.
  unit=json.loads((target/'kernel/unit.json').read_text());symbols=[r['symbol'] for r in unit['functions'] if r['source']=='Lemma.Platform.LemmaSim.IO.write64'];require(len(symbols)==1,'exact ARM store owner missing')
  shoff=struct.unpack_from('<Q',elf,40)[0];shsize,shcount=struct.unpack_from('<HH',elf,58);require(shsize==64 and shcount>0,'ELF section headers')
  sections=[struct.unpack_from('<IIQQQQIIQQ',elf,shoff+i*shsize) for i in range(shcount)];matches=[]
  for section in sections:
   if section[1]!=2:continue
   require(section[9]==24 and section[6]<len(sections),'ELF symbol table')
   strings=sections[section[6]];text=elf[strings[4]:strings[4]+strings[5]]
   for position in range(section[4],section[4]+section[5],24):
    name,info,_,_,address,size=struct.unpack_from('<IBBHQQ',elf,position)
    if info&15==2 and text[name:].split(b'\0',1)[0].decode()==symbols[0]:matches.append((address,size))
  require(len(matches)==1 and matches[0][0]<=state['pc']<sum(matches[0]),'software-uncommitted ARM cut is not in actual checked IO.write64')
 require(not re.search(b'K1 0000000000000494 ',uart),'pending request already published result')
 return observation

def peer_exchange(peer,helper,out,request,payload):
 directory=out/'opaque-peer';directory.mkdir(mode=0o700);medium=directory/'base.img'
 with medium.open('xb') as stream:stream.truncate(268435456);stream.seek(4096);stream.write(payload)
 log=(directory/'stderr.log').open('xb');argv=[str(peer),str(directory),str(medium),str(WRITER),str(helper)]
 write(directory/'argv.json',argv);started=time.monotonic()
 process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,start_new_session=True)
 try:
  output,_=process.communicate(request.hex()+'\n',timeout=30)
  require(process.returncode==0,'independent peer failed')
  lines=output.splitlines();require(len(lines)==1 and re.fullmatch('[0-9a-f]+',lines[0]),'peer did not return one encoded frame')
  reply=bytes.fromhex(lines[0]);require(len(reply)==584,'independent READ response extent differs')
  (directory/'observed-request.bin').write_bytes(request);(directory/'observed-reply.bin').write_bytes(reply)
  require((directory/'opaque.log').stat().st_size==8,'READ appended a durable record')
  write(directory/'result.json',{'status':'PASS_HOSTED_LEAN_READ_ONLY','wall_seconds':time.monotonic()-started,
   'request_sha256':file_sha(directory/'observed-request.bin'),'reply_sha256':file_sha(directory/'observed-reply.bin'),
   'base_sha256':file_sha(medium),'journal_bytes':8,'scope':'actual hosted-Lean frame decoding/read/CRC response; no durable write or guest completion claim'})
  return reply
 finally:
  if process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
  log.close()

def initial(binary,target,rom,identity,peer,helper,out,payload):
 owner=Owner(binary,out/'initial',target=target,rom=rom,bound=INITIAL_SECONDS)
 try:
  state=owner.call('inspect')
  packets=[];request=bytearray();armed_packets=0
  while state['cycle']<INITIAL_CYCLES:
   chip=state['wifi']['chip'];external=state['wifi']['peer']
   require(not state['finished'] and not chip['fault'] and not external['fault'],'machine ended/faulted')
   if external['head_valid'] and external['rx_packets']>len(packets):
    expected=min(16,72-len(request));require(expected>0 and external['head_length']==expected and external['rx_packets']==len(packets)+1,'request fragment order/extent differs')
    fragment=bytes.fromhex(external['head_bytes'])[:expected];request.extend(fragment);packets.append({'cycle':state['cycle'],'head':external})
    owner.pio(state['cycle'],[(64,2),(56,3)])
   if chip['tx_active'] and armed_packets==len(packets) and len(request)<72:
    require(chip['tx_packets']==len(packets) and not external['rx_active'] and not external['head_valid'],'not a new aligned request TX boundary')
    owner.pio(state['cycle'],[(40,min(16,72-len(request))),(48,93),(56,2)])
    armed_packets+=1
   if len(request)==72 and chip['rx_active']:
    reply=peer_exchange(peer,helper,out,bytes(request),payload)
    cut=owner.snapshot('pending-owned-read');ram,uart=observe_ram(cut,identity)
    require(ram['context'][:7]==[0x3152444d46495743,2,72,0,WRITER,4096,0] and ram['context'][7] in (0,1),'pending read context differs')
    require(ram['context_record']==[1,4,1,ram['handle']//8192] and ram['packet_record'][0:3]==[1,4,0] and ram['owned']==2,'pending ownership differs')
    require(ram['request_hex']==bytes(request).hex() and ram['queue'][1:4]==[0,0,5] and not re.search(b'K1 0000000000000494 ',uart),'delivery fabricated a read result')
    (owner.directory/'cut-uart.bin').write_bytes(uart);write(owner.directory/'cut-ram.json',ram);write(owner.directory/'decoded-request-heads.json',packets)
    observation={'schema':'lemma-owned-read-pending-observation/1','status':'PASS_OBSERVED_GENUINE_READ_PENDING','cut':str(cut),'cut_sha256':file_sha(cut),'cycle':state['cycle'],'reply_hex':reply.hex(),'ram':ram,'state':state,'runtime_identity':identity,'elf_sha256':file_sha(target/'image.elf'),'peer_reply':str(out/'opaque-peer/observed-reply.bin'),'peer_reply_sha256':file_sha(out/'opaque-peer/observed-reply.bin'),'peer_request':str(out/'opaque-peer/observed-request.bin'),'peer_request_sha256':file_sha(out/'opaque-peer/observed-request.bin')}
    write(out/'pending-observation.json',observation);validate_resume(out/'pending-observation.json',target,rom,identity)
    return observation
   started=bool(re.search(b'K1 0000000000000491 ',(owner.directory/'uart.bin').read_bytes()))
   state=owner.call('run '+str(min(16 if started else 4096,INITIAL_CYCLES-state['cycle'])))
  raise RuntimeError('original30M initial CPU limit exhausted')
 except BaseException:
  try:
   failure=owner.snapshot('failure-boundary')
   write(owner.directory/'failure-boundary.json',{'checkpoint':str(failure),'sha256':file_sha(failure),'inspect':owner.call('inspect'),'scope':'actual failed boundary; no completed READ claim'})
  except BaseException as snapshot_error:write(owner.directory/'failure-snapshot-error.json',{'error':repr(snapshot_error)})
  raise
 finally:owner.close()

def suffix(binary,identity,observation,out,mode,payload):
 cut=Path(observation['cut']);original=file_sha(cut);require(original==observation['cut_sha256'],'pending parent changed')
 owner=Owner(binary,out/mode,cut=cut,bound=SUFFIX_SECONDS);reply=bytearray.fromhex(observation['reply_hex'])
 if mode=='corrupt-crc':reply[-1]^=1
 if mode=='wrong-writer':reply[24]^=1
 end=observation['cycle']+SUFFIX_CYCLES;write(owner.directory/'plan.json',{'start':observation['cycle'],'end':end,'delta':SUFFIX_CYCLES,'host_seconds':SUFFIX_SECONDS,'mode':mode,'reply_sha256':__import__('hashlib').sha256(reply).hexdigest(),'opaque_loss':mode=='withheld','parent_sha256':original})
 try:
  state=owner.call('inspect');require(state['cycle']==observation['cycle'] and state['isolated_medium'] is True,'not exact private pending fork')
  cursor=0;packets=[];inflight=False
  while state['cycle']<end:
   chip=state['wifi']['chip'];peer=state['wifi']['peer']
   require(not state['finished'] and not chip['fault'] and not peer['fault'],'suffix machine ended/faulted')
   if inflight and not peer['tx_active'] and peer['tx_packets']==len(packets):inflight=False
   if mode!='withheld' and chip['rx_active'] and chip['rx_packets']==len(packets) and not chip['head_valid'] and not inflight and cursor<len(reply):
    length=min(16,len(reply)-cursor);part=reply[cursor:cursor+length]
    owner.pio(state['cycle'],[(24,length),(32,127),*[(256+i*8,value) for i,value in enumerate(part)],(56,1)])
    packets.append({'offset':cursor,'length':length,'cycle':state['cycle'],'bytes':part.hex()});cursor+=length;inflight=True
   uart=(owner.directory/'uart.bin').read_bytes();terminal=bool(re.search(b'K1 000000000000049[6f] ',uart))
   amount=end-state['cycle'] if terminal or mode=='withheld' else min(128,end-state['cycle'])
   state=owner.call('run '+str(amount))
  final=owner.snapshot('complete-final');ram,uart=observe_ram(final,identity)
  write(owner.directory/'final-inspect.json',state);write(owner.directory/'final-ram.json',ram);write(owner.directory/'response-fragments.json',packets)
  (owner.directory/'authoritative-uart.bin').write_bytes(uart)
  require(file_sha(cut)==original,'pending parent file modified')
  if mode in ('valid','valid-repeat'):
   require(cursor==584 and len(packets)==37 and ram['terminal']==1 and ram['context'][1]==3 and ram['context'][9]==1,'complete valid read absent withinoriginal2M')
   require(bytes.fromhex(ram['result_hex'])==payload and ram['owned']==0 and ram['available']==8192 and ram['all_owner_pin_zero'],'full owned result/release differs')
   require(state['wifi']['chip']['tx_packets']==5 and state['wifi']['chip']['rx_packets']==37 and state['wifi']['peer']['rx_packets']==5 and state['wifi']['peer']['tx_packets']==37,'actual data traffic counts differ')
   records=[[int(v,16) for v in row] for row in re.findall(b'K1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\n',uart)]
   require([r[1:] for r in records if r[0]==0x496]==[[0,5,512,0]],'guest release/result receipt differs')
   require(len([r for r in records if r[0]==0x495 and r[1]==18 and r[2]==2])==37,'real RX PLIC completion receipts differ')
   require(not any(r[0]==0x49f for r in records),'guest reported read error')
  else:
   require(ram['owned']==2 and ram['context_record'][0:3]==[1,4,1] and ram['context'][9]==0 and not re.search(b'K1 0000000000000494 ',uart),'failed/lost read published result or lost resources')
   if mode=='withheld':require(ram['terminal']==0 and ram['context'][1]==2 and ram['context'][3]==0 and ram['context'][6]==0 and state['wifi']['chip']['rx_active']==1,'loss did not remain pending')
   else:require(ram['terminal']==2 and ram['context'][6]!=0 and re.search(b'K1 000000000000049f ',uart),'corruption did not quarantine')
  result={'status':'PASS_OBSERVED_'+mode.upper().replace('-','_'),'cycle':state['cycle'],'checkpoint':str(final),'checkpoint_sha256':file_sha(final),'checkpoint_bytes':final.stat().st_size,'owned_ram':ram,'state':state,'wall_seconds':time.monotonic()-owner.started,'scope':'genuine guest/controller/sample transaction; no durable commit/notebook/HE claim'}
  write(owner.directory/'result.json',result);return result
 finally:owner.close()

def main():
 parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
 for name in ('native-build','target-capture','rom-bundle','peer-prepared','work-dir'):parser.add_argument('--'+name,type=Path,required=True)
 parser.add_argument('--resume-observation',type=Path)
 args=parser.parse_args();out=args.work_dir.resolve()
 if not out.is_relative_to(ROOT/'build/silicon') or out.exists():parser.error('unused build/silicon directory required')
 out.mkdir();shutil.copyfile(__file__,out/'runner.py');started=time.monotonic();result={'status':'FAIL','scope':'Common12 privileged owned READ512; no durable write/Notebook/HE/RF claim'}
 write(out/'plan.json',{'initial_clock_bound':INITIAL_CYCLES,'initial_host_seconds':INITIAL_SECONDS,'private_suffix_delta':SUFFIX_CYCLES,'private_suffix_host_seconds':SUFFIX_SECONDS,'modes':['valid','valid-repeat','corrupt-crc','wrong-writer','withheld'],'raw_transport':'external peer PIO only; no chip MMIO','receiver_arm':'only on actual new chip TX active boundary, max16-byte next request fragment, seed93; no cold-prefix prearm','payload_fixture':'512 opaque bytes (i*29+7)%256 at4096, remaining256MiB zero','frame_policy':'compiled guest constructs72-byte READ; independent hostedLean Peer decodes/reads/encodes584; max16-byte actual DATA chunks','scope':result['scope']})
 try:
  binary,identity,target,rom,peer,helper=validate_inputs(args.native_build.resolve(),args.target_capture.resolve(),args.rom_bundle.resolve(),args.peer_prepared.resolve(),out)
  payload=bytes((i*29+7)%256 for i in range(512))
  observation=validate_resume(args.resume_observation.resolve(),target,rom,identity) if args.resume_observation else initial(binary,target,rom,identity,peer,helper,out,payload)
  write(out/'pending-observation.json',observation)
  runs={mode:suffix(binary,identity,observation,out,mode,payload) for mode in ('valid','valid-repeat','corrupt-crc','wrong-writer','withheld')}
  require(runs['valid']['checkpoint_sha256']==runs['valid-repeat']['checkpoint_sha256'] and runs['valid']['checkpoint_bytes']==runs['valid-repeat']['checkpoint_bytes'],'complete same-input continuation differs')
  require((out/'valid/authoritative-uart.bin').read_bytes()==(out/'valid-repeat/authoritative-uart.bin').read_bytes(),'complete authoritative UART differs')
  result.update(status='PASS_GENUINE_OWNED_READ512',pending=observation,runs=runs,runtime_identity=identity,binary_sha256=file_sha(binary),elf_sha256=file_sha(target/'image.elf'),observer_sha256=file_sha(out/'runner.py'))
 except BaseException as error:result['error']=repr(error);raise
 finally:result['wall_seconds']=time.monotonic()-started;write(out/'result.json',result)
 print(result['status'],result['wall_seconds'])

if __name__=='__main__':main()
