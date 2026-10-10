#!/usr/bin/env python3
"""Observe pinned QEMU native input/block replay at an exact instruction boundary.

This uses a real supplied guest; it does not create guest pixels or transactions.
The output scope remains transport-only until a notebook workflow is supplied.
"""
import argparse,hashlib,json,shutil,socket,subprocess,tempfile,time
from pathlib import Path

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()
class Machine:
    def __init__(self,qemu,image,out,disk,rr,mode):
        self.out=out;out.mkdir();self.messages=[];self.stream=None;self.channel=None
        self.dir=tempfile.TemporaryDirectory(prefix='lemma-rr-');self.endpoint=Path(self.dir.name)/'control.sock'
        medium={'driver':'lemma-durable','node-name':'medium','file':{'driver':'raw','file':{'driver':'file','filename':str(disk.resolve()),'cache':{'no-flush':False}}},'trace-file':str((out/'media.trace').resolve())}
        self.argv=[str(qemu),'-machine','lemmasim-virt','-m','128M','-smp','1','-cpu','rv64,smrnmi=false,smdbltrp=false','-accel','tcg','-seed','0x4c454d4d413031','-bios','none','-kernel',str(image.resolve()),'-nodefaults','-display','none','-monitor','none','-rtc','base=2026-10-10T00:00:00,clock=vm','-serial',f'file:{out.resolve()}/serial.bin','-qmp',f'unix:{self.endpoint},server=on,wait=off','-global','virtio-mmio.force-legacy=false','-global',f'lemma-paper-pen.trace-file={out.resolve()}/devices.trace','-global',f'lemma-paper-pen.raw-output={out.resolve()}/raw.bin','-blockdev',json.dumps(medium),'-blockdev',json.dumps({'driver':'blkreplay','image':'medium','node-name':'replay'}),'-device','virtio-blk-device,drive=replay,bus=virtio-mmio-bus.0,werror=report,rerror=report','-icount',f'shift=3,align=off,sleep=on,rr={mode},rrfile={rr.resolve()}','-S']
        self.stdout=(out/'qemu.stdout').open('wb');self.stderr=(out/'qemu.stderr').open('wb')
        self.process=subprocess.Popen(self.argv,stdout=self.stdout,stderr=self.stderr,start_new_session=True)
        try:
            until=time.monotonic()+20
            while True:
                if self.process.poll() is not None:raise RuntimeError('QEMU startup failed; inspect stderr')
                try:
                    self.channel=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.channel.settimeout(10);self.channel.connect(str(self.endpoint));break
                except (FileNotFoundError,ConnectionRefusedError):
                    self.channel.close();self.channel=None
                    if time.monotonic()>until:raise TimeoutError('QMP readiness')
                    time.sleep(.01)
            self.stream=self.channel.makefile('rwb');self.messages.append(json.loads(self.stream.readline()));self.qmp('qmp_capabilities')
        except BaseException:self.close();raise
    def qmp(self,command,args=None):
        query={'execute':command}
        if args is not None:query['arguments']=args
        self.stream.write(json.dumps(query).encode()+b'\n');self.stream.flush()
        while True:
            line=self.stream.readline()
            if not line:raise RuntimeError('QEMU QMP closed')
            answer=json.loads(line);self.messages.append(answer)
            if 'error' in answer:raise RuntimeError(answer['error'])
            if 'return' in answer:return answer['return']
    def pointer(self,x,y,down):
        self.qmp('input-send-event',{'device':'lemma-hardware','events':[{'type':'abs','data':{'axis':'x','value':x}},{'type':'abs','data':{'axis':'y','value':y}},{'type':'btn','data':{'button':'left','down':down}}]})
    def observe(self):
        info=self.qmp('query-replay');state=json.loads(self.qmp('qom-get',{'path':'/machine/lemma-hardware','property':'device-state'}))
        self.qmp('screendump',{'filename':str((self.out/'visible.ppm').resolve())})
        result={'query_replay':info,'device_state':state,'files':{name:sha(self.out/name) for name in ('devices.trace','media.trace','raw.bin','visible.ppm','serial.bin')}}
        (self.out/'observation.json').write_text(json.dumps(result,indent=2)+'\n');return result
    def close(self):
        if getattr(self,'process',None) and self.process.poll() is None:
            try:self.qmp('quit')
            except (OSError,ValueError,RuntimeError):self.process.kill()
        if getattr(self,'process',None):
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
        if self.stream:self.stream.close()
        if self.channel:self.channel.close()
        self.stdout.close();self.stderr.close();self.dir.cleanup()
        (self.out/'qmp.json').write_text(json.dumps(self.messages,indent=2)+'\n')
    def __enter__(self):return self
    def __exit__(self,*unused):self.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--qemu',type=Path,required=True);p.add_argument('--image',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);result={'status':'FAIL','scope':'actual QEMU input/block transport replay only; supplied guest workflow is independently qualified'}
    try:
        initial=a.output/'initial.raw'
        with initial.open('xb') as f:f.truncate(256*1024*1024)
        record_disk=a.output/'record.raw';replay_disk=a.output/'replay.raw';shutil.copyfile(initial,record_disk);shutil.copyfile(initial,replay_disk)
        rr=a.output/'qemu.rr'
        with Machine(a.qemu,a.image,a.output/'record',record_disk,rr,'record') as m:
            m.qmp('cont');time.sleep(.15)
            m.pointer(1000,1000,False)
            for n in range(8):m.pointer(4000+n*1700,5000+n*1900,True)
            m.pointer(19000,22000,False);time.sleep(.05)
            m.qmp('stop');original=m.observe();n=original['query_replay']['icount']
            if n<=0:raise RuntimeError('record made no executed instructions')
            if (a.output/'record/raw.bin').stat().st_size!=720:raise RuntimeError('native ingress was omitted or duplicated')
            if b' flush-durable ' not in (a.output/'record/media.trace').read_bytes():raise RuntimeError('guest supplied no completed block flush before observation')
        with Machine(a.qemu,a.image,a.output/'replay',replay_disk,rr,'replay') as m:
            m.qmp('replay-break',{'icount':n});m.qmp('cont');until=time.monotonic()+30
            while m.qmp('query-status')['running']:
                if m.process.poll() is not None:raise RuntimeError('replay ended before observation boundary')
                if time.monotonic()>until:raise TimeoutError('replay did not reach exact recorded instruction boundary')
                time.sleep(.01)
            repeated=m.observe()
            if repeated['query_replay']['icount']!=n:raise RuntimeError('replay stopped at a different instruction boundary')
        if original['device_state']!=repeated['device_state']:raise RuntimeError('replayed controller state differs')
        if original['files']!=repeated['files']:raise RuntimeError('replayed raw/event/pixel/block/serial observations differ')
        if sha(record_disk)!=sha(replay_disk):raise RuntimeError('replayed stable medium differs')
        result.update(status='PASS',icount=n,guest_sha256=sha(a.image),qemu_sha256=sha(a.qemu),rr_sha256=sha(rr),initial_media_sha256=sha(initial),final_media_sha256=sha(record_disk),observations=original)
    except BaseException as error:result['error']=str(error);raise
    finally:(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
