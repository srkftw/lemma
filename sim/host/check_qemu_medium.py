#!/usr/bin/env python3
"""Independent literal stable/volatile observations through real VirtIO queues.

Qtest constructs hardware requests solely in this test machine's RAM. This is
not a guest driver, notebook, journal implementation or notebook acceptance.
"""
import argparse,base64,json,os,socket,struct,subprocess,tempfile,time
from pathlib import Path

class DeviceMachine:
    def __init__(self,binary,output,disk,**faults):
        self.output=output;output.mkdir();self.wire=[];self.channel=None;self.process=None
        self.directory=tempfile.TemporaryDirectory(prefix='lemma-medium-')
        endpoint=Path(self.directory.name)/'qtest.sock'
        self.out=(output/'qemu.stdout').open('wb');self.err=(output/'qemu.stderr').open('wb')
        graph={'driver':'lemma-durable','node-name':'medium','file':{'driver':'raw','file':{'driver':'file','filename':str(disk.resolve()),'cache':{'no-flush':False}}},'trace-file':str((output/'media.trace').resolve()),**faults}
        self.argv=[str(binary),'-machine','lemmasim-virt','-m','128M','-smp','1','-accel','qtest','-cpu','rv64','-bios','none','-nodefaults','-display','none','-global','virtio-mmio.force-legacy=false','-blockdev',json.dumps(graph),'-device','virtio-blk-device,drive=medium,bus=virtio-mmio-bus.0,werror=report,rerror=report','-qtest',f'unix:{endpoint},server=on,wait=off']
        self.process=subprocess.Popen(self.argv,stdout=self.out,stderr=self.err)
        deadline=time.monotonic()+15
        try:
            while True:
                if self.process.poll() is not None:raise RuntimeError('QEMU exited during startup; inspect qemu.stderr')
                try:
                    self.channel=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.channel.settimeout(5);self.channel.connect(str(endpoint));break
                except (FileNotFoundError,ConnectionRefusedError):
                    self.channel.close();self.channel=None
                    if time.monotonic()>deadline:raise TimeoutError('qtest readiness')
                    time.sleep(.01)
            self.index=0;self.transport_init()
        except BaseException:
            self.close();raise
    def transact(self,text):
        self.channel.sendall((text+'\n').encode());line=b''
        while not line.endswith(b'\n'):
            part=self.channel.recv(4096)
            if not part:raise EOFError('QEMU stopped before request completion')
            line+=part
        self.wire.append({'sent':text,'received':line.decode().strip()})
        if not line.startswith(b'OK'):raise RuntimeError(line.decode())
        return line.split()[1:]
    def read(self,addr,width='l'):return int(self.transact(f'read{width} {addr:#x}')[0],0)
    def write(self,addr,value,width='l'):self.transact(f'write{width} {addr:#x} {value:#x}')
    def memory(self,addr,value):self.transact(f'b64write {addr:#x} {len(value)} '+base64.b64encode(value).decode())
    def transport_init(self):
        b=0x10001000
        assert (self.read(b),self.read(b+4),self.read(b+8))==(0x74726976,2,2),'actual modern VirtIO block identity'
        self.write(b+0x70,0);self.write(b+0x70,1);self.write(b+0x70,3)
        self.write(b+0x14,1);assert self.read(b+0x10)&1,'VERSION_1 offered'
        self.write(b+0x14,0);assert self.read(b+0x10)&512,'FLUSH offered'
        self.write(b+0x24,1);self.write(b+0x20,1)
        self.write(b+0x24,0);self.write(b+0x20,512)
        self.write(b+0x70,11);assert self.read(b+0x70)&8,'FEATURES_OK accepted'
        self.write(b+0x30,0);assert self.read(b+0x34)>=8
        self.write(b+0x38,8)
        for low,high,addr in [(0x80,0x84,0x81000000),(0x90,0x94,0x81001000),(0xa0,0xa4,0x81002000)]:self.write(b+low,addr);self.write(b+high,0)
        self.memory(0x81001000,bytes(32));self.memory(0x81002000,bytes(80))
        self.write(b+0x44,1);self.write(b+0x70,15)
    def request(self,kind,sector=0,payload=None,expect_cut=False,defer=False):
        # VirtIO1.2 fixed little-endian header and split descriptor layout.
        header=struct.pack('<IIQ',kind,0,sector)
        self.memory(0x81003000,header)
        self.memory(0x81005000,b'\xff')
        if payload is not None:self.memory(0x81004000,payload)
        if kind==4:
            descriptors=struct.pack('<QIHH',0x81003000,16,1,2)+bytes(16)+struct.pack('<QIHH',0x81005000,1,2,0)
        else:
            descriptors=struct.pack('<QIHH',0x81003000,16,1,1)+struct.pack('<QIHH',0x81004000,512,1|(2 if kind==0 else 0),2)+struct.pack('<QIHH',0x81005000,1,2,0)
        self.memory(0x81000000,descriptors)
        self.write(0x81001004+(self.index%8)*2,0,'w');self.index=(self.index+1)%65536
        self.write(0x81001002,self.index,'w');self.write(0x10001050,0)
        if defer:return self.index
        return self.completion(expect_cut)
    def completion(self,expect_cut=False):
        deadline=time.monotonic()+10
        try:
            while self.read(0x81002002,'w')!=self.index:
                if time.monotonic()>deadline:raise TimeoutError('VirtIO completion')
                time.sleep(.001)
            status=self.read(0x81005000,'b')
            self.write(0x10001064,self.read(0x10001060))
            if expect_cut:raise AssertionError('faulted flush unexpectedly completed')
            return status
        except (EOFError,BrokenPipeError,ConnectionResetError):
            if not expect_cut:raise
            code=self.process.wait(timeout=5)
            assert code==86,f'power-cut exit code {code}'
            return 'POWER_CUT'
    def read_sector(self,sector=0):
        assert self.request(0,sector)==0
        encoded=self.transact('b64read 0x81004000 512')[0]
        return base64.b64decode(encoded)
    def close(self):
        if self.channel:self.channel.close();self.channel=None
        if self.process and self.process.poll() is None:self.process.kill()
        if self.process:self.process.wait(timeout=5)
        self.out.close();self.err.close();self.directory.cleanup()
        (self.output/'hardware-observations.json').write_text(json.dumps({'argv':self.argv,'wire':self.wire},indent=2)+'\n')
    def __enter__(self):return self
    def __exit__(self,*_):self.close()

def stable(disk,sector=0):
    with disk.open('rb') as f:f.seek(sector*512);return f.read(512)
def initialize(disk,value=bytes(512)):
    with disk.open('xb') as f:f.truncate(256*1024*1024);f.seek(0);f.write(value);f.flush();os.fsync(f.fileno())

def main():
    p=argparse.ArgumentParser();p.add_argument('--qemu',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);observations=[]
    try:
        disk=a.output/'volatile.raw';initialize(disk)
        with DeviceMachine(a.qemu,a.output/'volatile',disk) as m:
            assert m.request(1,payload=b'A'*512)==0
            assert m.read_sector()==b'A'*512
            assert stable(disk)==bytes(512),'ordinary completion must remain volatile'
        with DeviceMachine(a.qemu,a.output/'cold-reopen',disk) as m:
            assert m.read_sector()==bytes(512),'cold power cut loses completed unflushed writes'
            assert m.request(1,payload=b'B'*512)==0 and m.request(4)==0
            assert stable(disk)==b'B'*512,'completed flush must reach stable host image'
        observations.append('write completion volatile; cold cut drops overlay; flush persists')
        for name,option,expected in [('failed-flush','fail-flush',b'B'*512),('cut-before','cut-before-flush',b'B'*512),('cut-after','cut-after-flush',b'C'*512),('torn-sector','tear-flush',b'C'*256+b'B'*256)]:
            disk=a.output/(name+'.raw');initialize(disk,b'B'*512)
            with DeviceMachine(a.qemu,a.output/name,disk,**{option:1}) as m:
                assert m.request(1,payload=b'C'*512)==0
                status=m.request(4,expect_cut=option!='fail-flush')
                assert status==(1 if option=='fail-flush' else 'POWER_CUT')
                assert stable(disk)==expected,name+' literal stable bytes'
            observations.append(name+': '+str(status)+'; exact stable bytes observed')
        disk=a.output/'full.raw';initialize(disk)
        with DeviceMachine(a.qemu,a.output/'pending-full',disk,**{'pending-sectors':1}) as m:
            assert m.request(1,payload=b'D'*512)==0
            assert m.request(1,1,b'E'*512)==1
            assert m.read_sector()==b'D'*512 and m.read_sector(1)==bytes(512)
        observations.append('pending exhaustion rejects next request and preserves existing bytes')
        disk=a.output/'delay.raw';initialize(disk)
        with DeviceMachine(a.qemu,a.output/'virtual-delay',disk,**{'delay-write-ns':3000000000}) as m:
            # Literal timer boundary: no used entry / status write before3s.
            index=m.request(1,payload=b'F'*512,defer=True)
            assert m.read(0x81002002,'w')!=index and m.read(0x81005000,'b')==255
            m.transact('clock_step 2999999999')
            assert m.read(0x81002002,'w')!=index and m.read(0x81005000,'b')==255
            m.transact('clock_step 1')
            assert m.completion()==0
            assert stable(disk)==bytes(512),'delayed completion still volatile'
            assert m.request(1,payload=b'G'*512)==0,'delay is one shot'
            assert m.read_sector()==b'G'*512
        trace=(a.output/'virtual-delay/media.trace').read_text().splitlines()
        begin=[row.split() for row in trace if ' write-delay-begin ' in row]
        end=[row.split() for row in trace if ' write-delay-end ' in row]
        assert len(begin)==len(end)==1 and begin[0][2:4]==end[0][2:4]==['0','512']
        assert int(end[0][0])-int(begin[0][0])==3000000000
        assert not any(' write-delay-drained ' in row for row in trace)
        observations.append('one-shot actual VirtIO write remains pending until literal virtual3s timer; used/status untouched before boundary')
        disk=a.output/'delay-drain.raw';initialize(disk)
        with DeviceMachine(a.qemu,a.output/'virtual-delay-drain',disk,**{'delay-write-ns':3000000000}) as m:
            index=m.request(1,payload=b'H'*512,defer=True)
            assert m.read(0x81002002,'w')!=index
            # Actual VirtIO reset drains hardware before discarding its queue.
            # Virtual time remains0: a reset must explicitly unblock this wait.
            m.write(0x10001070,0)
            m.index=0;m.transport_init()
            assert m.read_sector()==b'H'*512 and stable(disk)==bytes(512)
        trace=(a.output/'virtual-delay-drain/media.trace').read_text().splitlines()
        assert sum(' write-delay-drained ' in row for row in trace)==1
        begin=next(row.split() for row in trace if ' write-delay-begin ' in row)
        end=next(row.split() for row in trace if ' write-delay-end ' in row)
        assert begin[2:4]==end[2:4]==['0','512'] and int(end[0])-int(begin[0])<3000000000
        observations.append('actual VirtIO reset drains/unblocks delayed request explicitly; no virtualtimer hang or false full-delay observation')
        (a.output/'result.json').write_text(json.dumps({'status':'PASS','scope':'actual device-only medium/VirtIO observations; no guest journal/notebook claim','observations':observations},indent=2)+'\n')
    except BaseException as e:
        (a.output/'result.json').write_text(json.dumps({'status':'FAIL','error':repr(e),'observations':observations},indent=2)+'\n');raise
if __name__=='__main__':main()
