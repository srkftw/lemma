#!/usr/bin/env python3
"""Literal fast controller DMA/media observations. No instructions or guest claims."""
import argparse,base64,json,os,socket,struct,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--qemu',type=Path,required=True);p.add_argument('--dtb',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=False)
# qtest never executes CPU instructions; TCG ISA admission is tested separately.
CPU='rv64'
medium=a.output/'medium.raw'
with medium.open('xb') as f:f.truncate(256*1024*1024)
log=(a.output/'machine.log').open('wb');endpoint=a.output/'qtest.sock';argv=[str(a.qemu.resolve()),'-machine','lemma-silicon-fast','-cpu',CPU,'-accel','qtest','-m','128M','-smp','1','-bios','none','-dtb',str(a.dtb.resolve()),'-display','none','-monitor','none','-serial','none','-qtest',f'unix:{endpoint},server=on,wait=off','-global',f'lemma-fast-block.medium={medium}'];process=subprocess.Popen(argv,stdout=log,stderr=log);channel=None;wire=[];report={'status':'FAIL','scope':'literal timer-driven DMA/media only; qtest executes no guest','argv':argv}
try:
    deadline=time.monotonic()+20
    while not endpoint.exists():
        if process.poll() is not None:raise RuntimeError('QEMU exited before qtest readiness')
        if time.monotonic()>deadline:raise TimeoutError('qtest readiness')
        time.sleep(.01)
    channel=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);channel.settimeout(10);channel.connect(str(endpoint));stream=channel.makefile('rwb',buffering=0)
    def q(text):
        stream.write(text.encode()+b'\n');line=stream.readline(1048577);wire.append([text,line.decode().strip()]);assert line.startswith(b'OK'),line;return line.split()[1:]
    def read(address,width='l'):return int(q(f'read{width} {address:#x}')[0],0)
    def write(address,value,width='l'):q(f'write{width} {address:#x} {value:#x}')
    def memory(address,data):q(f'b64write {address:#x} {len(data)} '+base64.b64encode(data).decode())
    b=0x10001000;desc=0x82000000;avail=desc+4096;used=desc+8192;header=desc+12288;data=desc+16384;status=desc+20480
    def init(descriptor=desc):
        write(b+112,0);write(b+112,3);write(b+36,0);write(b+32,512);write(b+36,1);write(b+32,1);write(b+112,11);assert read(b+112)==11
        write(b+48,0);write(b+56,8)
        for off,address in [(128,descriptor),(144,avail),(160,used)]:write(b+off,address);write(b+off+4,0)
        memory(avail,bytes(32));memory(used,bytes(80));write(b+68,1);write(b+112,15)
    index=0
    def request(kind,address=data,payload=None):
        global index
        memory(header,struct.pack('<IIQ',kind,0,0));memory(status,b'\xff')
        if payload:memory(data,payload)
        chain=struct.pack('<QIHH',header,16,1,1 if kind!=4 else 2)
        chain+=struct.pack('<QIHH',address,512,3 if kind==0 else 1,2) if kind!=4 else bytes(16)
        chain+=struct.pack('<QIHH',status,1,2,0);memory(desc,chain)
        write(avail+4+(index%8)*2,0,'w');index+=1;write(avail+2,index,'w');write(b+80,0)
        for _ in range(128):
            q('clock_step 100')
            if read(b+112)&64:return 'REJECTED'
            if read(used+2,'w')==index:return read(status,'b')
        raise TimeoutError('bounded controller completion')
    init();assert request(1,payload=b'A'*512)==0
    with medium.open('rb') as f:assert f.read(512)==bytes(512),'WRITE completion was incorrectly durable'
    assert request(0)==0;assert base64.b64decode(q(f'b64read {data:#x} 512')[0])==b'A'*512
    assert request(4)==0
    with medium.open('rb') as f:assert f.read(512)==b'A'*512,'FLUSH did not publish actual medium bytes'
    sentinel=b'Q'*512;foreign=0x80010000;memory(foreign,sentinel);assert request(0,address=foreign)=='REJECTED';assert base64.b64decode(q(f'b64read {foreign:#x} 512')[0])==sentinel,'unauthorized DMA changed protected RAM';assert read(0x0c001000)&2
    init(descriptor=foreign);write(b+80,0);assert read(b+112)&64;assert base64.b64decode(q(f'b64read {foreign:#x} 512')[0])==sentinel
    report.update(status='PASS',observations=['volatile WRITE readable before FLUSH','actual FLUSH publication','data descriptor outside frame pool rejected without memory mutation','queue descriptor outside frame pool rejected with source1 IRQ'])
except BaseException as e:report['error']=str(e);raise
finally:
    if channel:channel.close()
    if process.poll() is None:process.kill()
    process.wait(timeout=5);log.close();report['wire']=wire;(a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
