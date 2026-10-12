#!/usr/bin/env python3
"""Actual TCG guest and same-backend continuation observer; no guest policy."""
import argparse, hashlib, json, os, shutil, socket, struct, subprocess, time
from pathlib import Path

CPU='rv64i,m=true,s=true,u=true,mmu=true,pmp=true,sv39=true,zicsr=true,zifencei=true,zicntr=true,zihpm=false,priv_spec=v1.12.0'
p=argparse.ArgumentParser();p.add_argument('--qemu',type=Path,required=True);p.add_argument('--image',type=Path,required=True);p.add_argument('--dtb',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=float,default=90);p.add_argument('--delay-write-ns',type=int,default=20000000);p.add_argument('--trace-limit',type=int);a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=False)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
class Machine:
    def __init__(self,name,medium):
        self.directory=a.output/name;self.directory.mkdir();self.serial=0;self.events=[];self.log=(self.directory/'machine.log').open('wb')
        self.argv=[str(a.qemu.resolve()),'-machine','lemma-silicon-fast','-cpu',CPU,'-m','128M','-smp','1','-bios','none','-kernel',str(a.image.resolve()),'-dtb',str(a.dtb.resolve()),'-display','none','-monitor','none','-serial',f'file:{self.directory}/uart.bin','-qmp',f'unix:{self.directory}/qmp.sock,server=on,wait=off','-S','-no-reboot','-no-shutdown','-icount','shift=3,align=off,sleep=off','-seed','0x4c454d4d413031','-global',f'lemma-fast-block.medium={medium}','-global',f'lemma-fast-block.delay-write-ns={a.delay_write_ns}','-global',f'lemma-fast-block.trace-file={self.directory}/medium.log','-global',f'lemma-paper-pen.raw-output={self.directory}/input.bin']
        if a.trace_limit is not None:self.argv+=['-global',f'lemma-fast-block.trace-limit={a.trace_limit}','-global',f'lemma-paper-pen.trace-limit={a.trace_limit}','-global',f'lemma-paper-pen.trace-file={self.directory}/devices.log']
        self.process=subprocess.Popen(self.argv,stdout=self.log,stderr=self.log,start_new_session=True);self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.socket.settimeout(a.timeout);deadline=time.monotonic()+a.timeout
        while True:
            try:self.socket.connect(str(self.directory/'qmp.sock'));break
            except (FileNotFoundError,ConnectionRefusedError):
                if self.process.poll() is not None:raise RuntimeError('QEMU exited before QMP: '+str(self.directory/'machine.log'))
                if time.monotonic()>deadline:raise TimeoutError('QMP readiness')
                time.sleep(.01)
        self.stream=self.socket.makefile('rwb',buffering=0);json.loads(self.stream.readline());self.qmp('qmp_capabilities')
    def qmp(self,command,arguments=None):
        self.serial+=1;self.stream.write(json.dumps({'execute':command,'arguments':arguments or {},'id':self.serial}).encode()+b'\n')
        while True:
            value=json.loads(self.stream.readline(1048577))
            if 'event' in value:self.events.append(value);continue
            if value.get('id')!=self.serial:continue
            if 'error' in value:raise RuntimeError(value['error'])
            return value['return']
    def get(self,path,prop):return self.qmp('qom-get',{'path':path,'property':prop})
    def time(self):return int(self.get('/machine/lemma-hardware','virtual-time'))
    def inspect(self):return {'time_ns':self.time(),'running':self.qmp('query-status')['running'],'devices':json.loads(self.get('/machine/lemma-hardware','device-state')),'storage':json.loads(self.get('/machine/lemma-block','storage-state')),'registers':self.qmp('human-monitor-command',{'command-line':'info registers'})}
    def run(self,ns,inspect=True):
        self.qmp('qom-set',{'path':'/machine/lemma-hardware','property':'run-until','value':str(self.time()+ns)});self.qmp('cont');deadline=time.monotonic()+a.timeout
        while self.qmp('query-status')['running']:
            if time.monotonic()>deadline:raise TimeoutError('bounded virtual interval')
            time.sleep(.001)
        return self.inspect() if inspect else {'time_ns':self.time(),'storage':json.loads(self.get('/machine/lemma-block','storage-state'))}
    def dump(self,address,length,path):self.qmp('pmemsave',{'val':address,'size':length,'filename':str(path)})
    def close(self):
        if self.process.poll() is None:
            try:self.qmp('quit');self.process.wait(timeout=5)
            except Exception:self.process.kill();self.process.wait(timeout=5)
        self.stream.close();self.socket.close();self.log.close()

def self_check_not_shutdown(machine):return machine.qmp('query-status')['status']!='shutdown'

# QMP prelaunch/paused are host launch labels; the relation requires stopped
# execution, exact virtual time/registers/RAM/device state and output bytes.
machines=[];report={'status':'FAIL','scope':'real TCG Lean guest; same-backend exact continuation only','inputs':{k:{'path':str(v.resolve()),'sha256':sha(v)} for k,v in [('qemu',a.qemu),('image',a.image),('dtb',a.dtb)]}}
try:
    medium=a.output/'base.raw'
    with medium.open('xb') as f:f.truncate(256*1024*1024)
    machine=Machine('first',medium);machines.append(machine);report['argv']=machine.argv
    machine.dump(0x10010400,256,a.output/'descriptor.bin');desc=struct.unpack('<32Q',(a.output/'descriptor.bin').read_bytes());assert desc[0]==1280132179 and desc[2]==256 and desc[3]==sum(desc[:3]+desc[4:])%(1<<64)
    assert desc[26]==0x87e00000 and 40<=desc[27]<=2*1024*1024
    machine.dump(desc[26],desc[27],a.output/'loaded.dtb');assert (a.output/'loaded.dtb').read_bytes()==a.dtb.read_bytes(),'supplied DTB changed in boot RAM'
    report['descriptor']=desc
    start=time.monotonic();before=None
    # Real canonical a5 cold startup measured first transfer after1svirtual;
    # keep an explicit3s budget rather than weakening a device observation.
    for _ in range(3000):
        before=machine.run(1000000,inspect=False)
        if before['storage']['phase']==8 and before['storage']['kind']==1 and before['storage']['media_deadline_ns']>before['time_ns']:break
        assert self_check_not_shutdown(machine),'guest finished before pending storage observation'
    else:
        report['last_observation']=before
        raise AssertionError('actual guest did not reach delayed in-flight storage request')
    before=machine.inspect();report['boot_to_inflight_seconds']=time.monotonic()-start;report['checkpoint']=before
    # Two future boundary events are queued without gesture or document interpretation.
    t=machine.time();machine.qmp('qom-set',{'path':'/machine/lemma-hardware','property':'external-event','value':f'{t+1000000} 123456 12000 14000 0 6 1 0'});machine.qmp('qom-set',{'path':'/machine/lemma-hardware','property':'external-event','value':f'{t+2000000} 123457 12000 14000 2048 7 1 0'})
    before=machine.inspect();stable=sha(medium);snapshot=a.output/'machine.state';machine.qmp('lemma-save-machine',{'filename':str(snapshot)});after_save=machine.inspect();assert after_save==before,'save altered CPU/time/device/controller state';assert sha(medium)==stable,'snapshot flushed medium'
    shutil.copyfile(medium,a.output/'checkpoint-base.raw');offset=(machine.directory/'uart.bin').stat().st_size
    suffix=machine.run(100000000);suffix_bytes=(machine.directory/'uart.bin').read_bytes()[offset:];machine.dump(0x80000000,128*1024*1024,a.output/'suffix-ram.bin');first_media=sha(medium);machine.close();machines.remove(machine)
    fork=a.output/'isolated-fork.raw';shutil.copyfile(a.output/'checkpoint-base.raw',fork);restored=Machine('restored',fork);machines.append(restored);restored.qmp('lemma-load-machine',{'filename':str(snapshot)});restored_state=restored.inspect();assert restored_state==before,'loaded CPU/time/device/controller state differs'
    resumed=restored.run(100000000);restored.dump(0x80000000,128*1024*1024,a.output/'resumed-ram.bin');assert resumed==suffix,'same remaining virtual interval differs';assert (restored.directory/'uart.bin').read_bytes()==suffix_bytes,'guest UART continuation differs';assert sha(a.output/'resumed-ram.bin')==sha(a.output/'suffix-ram.bin'),'guest RAM continuation differs';assert sha(fork)==first_media,'durable continuation differs'
    observer_budgets={}
    if a.trace_limit is not None:
        # Observer counters intentionally remain outside restored device state.
        for device in ('lemma-block','lemma-hardware'):
            value=json.loads(restored.get('/machine/'+device,'trace-state'))
            assert value['rows']<=a.trace_limit and value['omitted']>0
            observer_budgets[device]=value
        for instance in (machine,restored):
            for filename in ('medium.log','devices.log'):
                assert len((instance.directory/filename).read_text().splitlines())<=a.trace_limit
    restored.close();machines.remove(restored)
    negatives={}
    bad_medium=a.output/'wrong-base.raw';shutil.copyfile(a.output/'checkpoint-base.raw',bad_medium)
    with bad_medium.open('r+b') as f:f.seek(256*1024*1024-1);f.write(b'\x01');f.flush();os.fsync(f.fileno())
    bad=Machine('bad-base',bad_medium);machines.append(bad)
    try:bad.qmp('lemma-load-machine',{'filename':str(snapshot)})
    except RuntimeError as e:negatives['changed_durable_base_rejected']=str(e)
    else:raise AssertionError('changed durable base accepted')
    bad.close();machines.remove(bad)
    truncated=a.output/'truncated.state'
    with snapshot.open('rb') as f:truncated.write_bytes(f.read(32))
    bad=Machine('truncated-state',a.output/'checkpoint-base.raw');machines.append(bad)
    try:bad.qmp('lemma-load-machine',{'filename':str(truncated)})
    except RuntimeError as e:negatives['truncated_state_rejected']=str(e)
    else:raise AssertionError('truncated state accepted')
    bad.close();machines.remove(bad)
    assert sha(a.output/'checkpoint-base.raw')==stable,'negative restore mutated snapshot base'
    report.update(status='PASS',snapshot_sha256=sha(snapshot),snapshot_bytes=snapshot.stat().st_size,stable_sha256_at_snapshot=stable,final_durable_sha256=first_media,final_state=resumed,ram_sha256=sha(a.output/'resumed-ram.bin'),uart_suffix_sha256=hashlib.sha256(suffix_bytes).hexdigest(),retained_dtb_exact=True,negative_observations=negatives,observer_budgets=observer_budgets)
except BaseException as e:
    report['error']=str(e);raise
finally:
    for m in machines:m.close()
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
