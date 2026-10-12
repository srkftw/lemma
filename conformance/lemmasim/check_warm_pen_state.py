#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual selected-profile pen reset, MTIME watchdog and exact state checks.

A genuine Lean probe boots normally. Raw debugger MMIO and an isolated
Laboratory clock mutation inspect circuitry directly; guest warm-pen and
clock-write instruction qualification remain separate.
"""
import argparse,json,hashlib,signal,traceback,sys,struct,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'conformance/lemmasim'))
from check_counter_state import Machine,sha,require
from lemmasim_fast import prepared
from silicon_guest import verify_guest_build
from check_fast_state_equivalence import compare,layout,parse_json,section_payload
PROFILE='lemma-silicon-dev/0.3.0'
REVIEWED_CURRENT='927bef771d31134b73b76a2c219d1717144feec6986b07df5c58ef85d08ad6e5'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--guest-build',type=Path,help='strict current genuine Lean power probe; defaults to prepared power guest');p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--timeout',type=int,default=60);p.add_argument('--deadline',type=int,default=240);a=p.parse_args()
require(1<=a.timeout<=300 and 1<=a.deadline<=900,'host deadline outside supported bounds')
OUT=a.output_dir.resolve();OUT.mkdir(exist_ok=False);PEN=0x10011000
prepared_data=prepared('power',PROFILE);a.binary=Path(prepared_data['qemu']['path'])
require(sha(a.binary)==REVIEWED_CURRENT,'current prepared binary lacks this checker exact reviewed identity')
GUEST=(a.guest_build or Path(prepared_data['workloads']['power']['image']['path']).parent).resolve()
build=json.loads((GUEST/'build.json').read_text());verify_guest_build(GUEST,'lemmasim-silicon-power-probe',build['optimization'])
audit=json.loads((GUEST/'audit.json').read_text());require(audit['image_sha256']==sha(GUEST/'image.elf'),'audited ELF changed')
NAMES={16:'status',24:'error',32:'count',40:'epoch',48:'lost',256:'head_sequence',264:'head_time',320:'head_epoch'}
result={'status':'FAIL','scope':'actual host raw controller/debug-MMIO qualification with current source-bound genuine Lean power probe, not guest warm-pen instruction qualification','predeclared_relation':{'ticks':'MTIME=floor(absolute ns/100)-floor(reset ns/100)','watchdog':'ten million actual MTIME ticks; exact aligned absolute deadline','state':'all serialized bytes exact except two existing independently source-proven host elapsed-time statistics','hardware_reset':'full pen FIFO/head/sequence/error/loss/timestamps reset, epoch1','software_reset':'RESET1 preserves immutable old head and enters loss/resync with epoch+1'},'candidate':{'path':str(a.binary.resolve()),'sha256':sha(a.binary)},'prepared':{'path':'build/lemmasim/fast-prepared-0.3.0.json','sha256':sha(ROOT/'build/lemmasim/fast-prepared-0.3.0.json')},'guest':{n:sha(GUEST/n) for n in ['image.elf','platform.dtb','audit.json']},'observer_sha256':sha(Path(__file__)),'checks':{},'all_processes_reaped':False}
machines=[]
def pen(m):
 d={}
 for off,name in NAMES.items():
  b=m.rsp.command(f'm{PEN+off:x},8');require(len(b)==16 and not b.startswith(b'E'),'raw pen MMIO read failed');d[name]=int.from_bytes(bytes.fromhex(b.decode()),'little')
 return d
def memwrite(m,address,value,size=8):
 require(m.rsp.command(f'M{address:x},{size:x}:'+value.to_bytes(size,'little').hex())==b'OK','raw debug MMIO write failed')
def event(m,flags):
 state=m.state();delivery=state['ns']+8;t=state['registers']['time'];m.qmp.execute('qom-set',{'path':'/machine/lemma-hardware','property':'external-event','value':f'{delivery} {t} 100 200 50 {flags} 1 0'});s=m.run(delivery)
 return {'delivery':delivery,'time':t,'flags':flags,'state':s,'pen':pen(m)}
def new(name):
 m=Machine(a.binary.resolve(),GUEST,OUT/name,a.timeout);machines.append(m);return m
def decode(data):
 meta=parse_json(data[layout(data)['metadata_start']:]);ds=[d for d in meta['devices'] if d.get('name')=='lemma-paper-pen/1'];require(len(ds)==1 and ds[0]['version']==3,'private successor schema missing')
 fields=ds[0]['fields'];expected=[('width','uint32 equal',4),('height','uint32 equal',4),('pressure_max','uint32 equal',4),('frame_bytes','uint32 equal',4),('pen','struct',18523),('paper','struct',1054),('power_enabled','bool',1),('power','struct',56),('pen_clock_origin_ns','uint64',8)]
 require([(f['name'],f['type'],f['size']) for f in fields[:9]]==expected,'private origin wire schema mismatch')
 off,_=section_payload(data,b'lemma-paper-pen/1',3);origin=off+sum(v[2] for v in expected[:-1]);penoff=off+16
 require([(f['name'],f['type'],f['size']) for f in fields[-4:]]==[(n,'timer',8) for n in ['timer','input_timer','pen_timer','run_timer']],'timer wire schema mismatch')
 timer_offset=off+sum(f['size']*f.get('array_len',1) for f in fields[:-2])
 return {'offset':origin,'origin':int.from_bytes(data[origin:origin+8],'big'),'last_time_offset':penoff+18523-16,'deadline_offset':penoff+18523-8,'watchdog_timer_ns':int.from_bytes(data[timer_offset:timer_offset+8],'big',signed=True)}
def checkpoint(m,name):
 path=OUT/(name+'.chk');m.snapshot(path);d=path.read_bytes();s=decode(d);return path,d,s
def exact(left,right):
 r=compare(left,right);require(r['status']=='PASS','unauthorized full checkpoint mismatch');return r
def reject(path,name):
 m=new('negative-'+name);error=None
 try:m.restore(path)
 except RuntimeError as e:error=str(e)
 require(error is not None,'malformed/stale checkpoint admitted');return {'error':error,'checkpoint_sha256':sha(path)}
def alarm(s,f):raise TimeoutError('bounded warm-pen diagnostic deadline')
signal.signal(signal.SIGALRM,alarm);signal.alarm(a.deadline);started=time.monotonic()
try:
 m=new('nonempty');m.run(1200000040);contact=event(m,1);require(contact['pen']['count']==1 and contact['pen']['head_time']==12000000,'prewarm independentcontactadmission')
 reset=m.warm();r=pen(m);require(r=={'status':0,'error':0,'count':0,'epoch':1,'lost':0,'head_sequence':0,'head_time':0,'head_epoch':0},'nonempty hardware reset did not clear pen')
 require(reset['registers']['time']==0,'warm MTIME not zero');contact=event(m,1);require(contact['time']==0 and contact['pen']['count']==1 and contact['pen']['epoch']==1 and contact['pen']['head_sequence']==1 and contact['pen']['lost']==0,'postwarm TIME0 contact not admitted normally')
 path,raw,clock=checkpoint(m,'warm-contact');require(clock['origin']==1200000000,'aligned fractional pen clock origin');result['checks']['hardware_reset_nonempty']={'state':reset,'pen':r,'contact':contact,'private_clock':clock}
 f=new('warm-contact-fork');f.restore(path);require(f.state()==m.state() and pen(f)==pen(m),'warm nonzero-origin restore changed state');m.run(1300000048);f.run(1300000048);_,l,_=checkpoint(m,'warm-contact-final-original');_,r,_=checkpoint(f,'warm-contact-final-replayed');result['checks']['warm_contact_exact']=exact(l,r)
 n=new('blank-watchdog');n.run(1200000040);reset=n.warm();require(pen(n)['epoch']==1 and pen(n)['lost']==0 and pen(n)['status']==0,'blank hardware reset did not clear pen');n.run(1300000040)
 # Host raw-controller observation only: suppress the pen PLIC priority after
 # genuine guest boot, so its driver cannot consume the pending FIFO head.
 memwrite(n,0x0c000034,0,4);contact=event(n,1);require(contact['time']==1000000 and contact['pen']['count']==1 and contact['pen']['lost']==0,'warm contact prematurely lost')
 expected_deadline=2300000000;n.run(expected_deadline-8);before=pen(n);require(before['count']==1 and before['lost']==0 and before['epoch']==1,'watchdog fired before actual ten-million ticks')
 path,raw,clock=checkpoint(n,'watchdog-prefix');require(clock['origin']==1200000000,'watchdog origin changed');g=new('watchdog-fork');g.restore(path)
 first=n.run(expected_deadline);second=g.run(expected_deadline);after=pen(n);require(after['lost']==1 and after['epoch']==2 and after['status']==7 and after['error']==0 and after['head_time']==1000000,'watchdog failed at actual ten-million ticks')
 require(first==second and pen(g)==after,'watchdog restored continuation differs');_,l,_=checkpoint(n,'watchdog-final-original');_,r,_=checkpoint(g,'watchdog-final-replayed');result['checks']['fractional_watchdog']={'reset':reset,'contact':contact,'before':before,'after':after,'deadline_ns':expected_deadline,'state':first,'exact_state':exact(l,r)}
 # Software RESET1 remains loss/resync; it is not hardware reset.
 h=new('software-loss');h.run(1200000040);contact=event(h,1);memwrite(h,PEN+104,1);lost=pen(h);require(lost['status']==7 and lost['epoch']==2 and lost['lost']==1 and lost['head_time']==12000000,'software RESET1 semantics changed');memwrite(h,PEN+96,2);release=event(h,2);resync=event(h,1);require(release['pen']['status']==4 and resync['pen']['count']==1 and resync['pen']['epoch']==2 and resync['pen']['head_sequence']==2,'software loss/resync semantics changed');result['checks']['software_loss_preserved']={'lost':lost,'release':release,'resync':resync}
 # Explicit isolated Laboratory clock mutation tests deadline saturation near
 # the signed-clock limit; no user/guest time travel claim is made.
 large=new('large-clock');large.run(100000000);path,raw,clock=checkpoint(large,'large-clock-base')
 info=layout(raw);near=((1<<63)-1-1000000)&~7;count=struct.unpack('>q',raw[info['icount']+8:info['icount']+16])[0]
 b=bytearray(raw);b[info['icount']:info['icount']+8]=(near-(count<<3)).to_bytes(8,'big',signed=True);p=OUT/'laboratory-near-clock.chk';p.write_bytes(b)
 large.restore(p);require(large.state()['ns']==near,'laboratory isolated icount mutation did not set declared clock')
 huge_time=(1<<64)-1-10000000;large.qmp.execute('qom-set',{'path':'/machine/lemma-hardware','property':'external-event','value':f'{near+8} {huge_time} 100 200 50 1 1 0'});large.run(near+8)
 observed=pen(large);require(observed['count']==1 and observed['lost']==0 and observed['error']==0 and observed['head_time']==huge_time,'saturated deadline fabricated contact loss')
 path,raw,clock=checkpoint(large,'large-clock-contact');require(clock['watchdog_timer_ns']==(1<<63)-1,'huge deadline did not saturate to signed clock bound');large.run(near+800);require(pen(large)['lost']==0,'saturated watchdog manufactured loss')
 result['checks']['near_clock_saturation']={'scope':'host Laboratory isolated migration-clock mutation, not guest-issued clock-change qualification','virtual_ns':near,'sample_time':huge_time,'pen':observed,'private_clock':clock,'after':pen(large)}
 path,raw,clock=checkpoint(m,'negative-prefix');mut=[]
 for name,value in [('unaligned',1200000001),('future',1300000100),('overflow',(1<<64)-1)]:
  b=bytearray(raw);b[clock['offset']:clock['offset']+8]=value.to_bytes(8,'big');p=OUT/(name+'.chk');p.write_bytes(b);mut.append({'name':name,**reject(p,name)})
 b=bytearray(raw);b[clock['deadline_offset']:clock['deadline_offset']+8]=(999).to_bytes(8,'big');p=OUT/'inconsistent-deadline.chk';p.write_bytes(b);mut.append({'name':'inconsistent-deadline',**reject(p,'inconsistent-deadline')})
 p=OUT/'truncated.chk';p.write_bytes(raw[:clock['offset']+4]);mut.append({'name':'truncated',**reject(p,'truncated')})
 payload,_=section_payload(raw,b'lemma-paper-pen/1',3);b=bytearray(raw);b[payload-4:payload]=(2).to_bytes(4,'big');stale=OUT/'unsupported-device-v2.chk';stale.write_bytes(b);mut.append({'name':'unsupported-device-v2',**reject(stale,'unsupported-device-v2')})
 result['checks']['negative_state']=mut;result['status']='PASS'
except BaseException as e:result['error']=repr(e);result['traceback']=traceback.format_exc();raise
finally:
 for m in reversed(machines):m.close()
 result['all_processes_reaped']=all(m.process.poll() is not None for m in machines);result['elapsed_s']=time.monotonic()-started;signal.alarm(0);(OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'error':result.get('error'),'elapsed_s':result['elapsed_s']}))
