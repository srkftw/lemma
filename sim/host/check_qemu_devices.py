#!/usr/bin/env python3
"""Observe the actual QEMU MMIO models/PLIC with literal boundary expectations.
This hardware check does not certify compiled guest drivers or a notebook.
"""
import argparse,json,os,socket,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--qemu',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
q=None;channel=None;wire=[]
def transact(text):
    channel.sendall((text+'\n').encode());line=b''
    while not line.endswith(b'\n'):
        b=channel.recv(4096)
        if not b:raise RuntimeError('QEMU qtest channel closed')
        line+=b
    wire.append({'sent':text,'received':line.decode().strip()})
    if not line.startswith(b'OK'):raise RuntimeError(line.decode())
    return line.split()[1:]
def read(addr):return int(transact(f'readq {addr:#x}')[0],0)
def write(addr,value):transact(f'writeq {addr:#x} {value:#x}')
try:
    with tempfile.TemporaryDirectory(prefix='lemma-qtest-') as d:
        endpoint=Path(d)/'qtest.sock'
        with (a.output/'qemu.stdout').open('wb') as out,(a.output/'qemu.stderr').open('wb') as err:
            command=[str(a.qemu),'-machine','lemmasim-virt','-m','128M','-smp','1','-cpu','rv64,smrnmi=false,smdbltrp=false','-bios','none','-nodefaults','-display','none','-S','-qtest',f'unix:{endpoint},server=on,wait=off']
            q=subprocess.Popen(command,stdout=out,stderr=err)
            deadline=time.monotonic()+20
            while not endpoint.exists():
                if q.poll() is not None:raise RuntimeError('QEMU exited before device check')
                if time.monotonic()>deadline:raise TimeoutError('QEMU qtest socket readiness')
                time.sleep(.02)
            channel=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);channel.settimeout(10);channel.connect(str(endpoint))
            base=0x10010000;pen=0x10011000
            assert read(base)==1280331856 and read(base+8)==1
            assert (read(base+32),read(base+40),read(base+48))==(1650,2200,825)
            desc=[read(base+1024+i*8) for i in range(32)]
            assert desc[0:3]==[1280132179,1,256]
            assert desc[3]==sum(desc[:3]+desc[4:])%(1<<64)
            assert desc[26] and desc[27] and desc[26]==desc[30]
            # Real device reset is a raw-stream boundary and asserts actual source13.
            assert read(pen+16)&2
            assert read(0x0c001000)&(1<<13)
            write(pen+96,read(pen+40))
            assert not read(pen+16)&2
            # Controller target RAM changes only after upload; visible completion delayed.
            for off,value in [(64,0),(72,0),(80,2),(88,1),(96,1),(2048,0),(104,1),(120,0),(128,0),(136,2),(144,1),(152,1),(112,1),(104,2)]:write(base+off,value)
            assert read(base+16)&1
            write(base+112,2);write(base+104,2)
            assert read(base+24)==4 and read(base+16)&1
            transact('clock_step 25000000')
            assert not read(base+16)&1 and read(base+160)==1
            assert read(0x0c001000)&(1<<12)
            write(base+168,1);assert not read(base+16)&6
            # Actual FDT generation is captured separately in the result.
            result={'status':'PASS','scope':'actual QEMU device/PLIC boundary observations only','argv':command,'descriptor':desc,'trace':wire}
            (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
except BaseException as error:
    (a.output/'result.json').write_text(json.dumps({'status':'FAIL','error':str(error),'trace':wire},indent=2)+'\n')
    raise
finally:
    if channel:channel.close()
    if q and q.poll() is None:q.terminate()
    if q:
        try:q.wait(timeout=5)
        except subprocess.TimeoutExpired:q.kill();q.wait(timeout=5)
