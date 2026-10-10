#!/usr/bin/env python3
"""Observe the actual QEMU MMIO models/PLIC with literal boundary expectations.
This hardware check does not certify compiled guest drivers or a notebook.
"""
import argparse,json,os,socket,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--qemu',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
q=None;channel=None;qmp_channel=None;qmp_stream=None;wire=[]
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
def assert_visible_pattern(path):
    magic,geometry,maximum,pixels=path.read_bytes().split(b'\n',3)
    assert (magic,geometry,maximum)==(b'P6',b'1650 2200',b'255')
    assert len(pixels)==1650*2200*3
    # Multirow and opposite-corner asymmetry catches host surface row padding;
    # a constant region at row0 cannot detect a skewed display blit.
    expected={(0,0):0,(1,0):255,(0,1):255,(1,1):0,(0,2):0,(1,2):0,
              (2,2):255,(1648,2198):255,(1649,2198):0,
              (1648,2199):0,(1649,2199):255,(1647,2199):255}
    for (x,y),gray in expected.items():
        offset=(y*1650+x)*3
        assert pixels[offset:offset+3]==bytes([gray])*3,('controller visible pixel',x,y,gray,list(pixels[offset:offset+3]))
def qmp(command,arguments=None):
    request={'execute':command}
    if arguments is not None:request['arguments']=arguments
    qmp_stream.write(json.dumps(request).encode()+b'\n');qmp_stream.flush()
    while True:
        response=json.loads(qmp_stream.readline())
        if 'error' in response:raise RuntimeError(response['error'])
        if 'return' in response:return response['return']
try:
    with tempfile.TemporaryDirectory(prefix='lemma-qtest-') as d:
        endpoint=Path(d)/'qtest.sock'
        control=Path(d)/'qmp.sock'
        with (a.output/'qemu.stdout').open('wb') as out,(a.output/'qemu.stderr').open('wb') as err:
            # Qtest never executes instructions. TCG-specific CPU options are
            # exercised by the separate actual guest boot, not this hardware test.
            command=[str(a.qemu),'-machine','lemmasim-virt','-m','128M','-smp','1','-accel','qtest','-cpu','rv64','-bios','none','-nodefaults','-display','none','-qtest',f'unix:{endpoint},server=on,wait=off','-qmp',f'unix:{control},server=on,wait=off','-global',f'lemma-paper-pen.raw-output={a.output.resolve()}/raw.bin']
            q=subprocess.Popen(command,stdout=out,stderr=err)
            deadline=time.monotonic()+20
            while not endpoint.exists():
                if q.poll() is not None:raise RuntimeError('QEMU exited before device check')
                if time.monotonic()>deadline:raise TimeoutError('QEMU qtest socket readiness')
                time.sleep(.02)
            channel=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);channel.settimeout(10);channel.connect(str(endpoint))
            qmp_channel=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);qmp_channel.settimeout(10);qmp_channel.connect(str(control))
            qmp_stream=qmp_channel.makefile('rwb');json.loads(qmp_stream.readline());qmp('qmp_capabilities')
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
            for off,value in [(64,0),(72,0),(80,2),(88,3),(96,3),(2048,0x37f00f),(104,1),
                              (64,1648),(72,2198),(80,2),(88,2),(96,2),(2048,0x0ff0),(104,1),
                              (120,0),(128,0),(136,1650),(144,2200),(152,1),(112,1),(104,2)]:write(base+off,value)
            assert read(base+16)&1
            write(base+112,2);write(base+104,2)
            assert read(base+24)==4 and read(base+16)&1
            transact('clock_step 25000000')
            assert not read(base+16)&1 and read(base+160)==1
            assert read(0x0c001000)&(1<<12)
            write(base+168,1);assert not read(base+16)&6
            # Exercise the real QEMU input adapter, independently of raw-file
            # fixtures; all samples are explicitly synthetic pointer input.
            transact('clock_step 75000000')
            events=[{'type':'abs','data':{'axis':'x','value':32767}},
                    {'type':'abs','data':{'axis':'y','value':0}},
                    {'type':'btn','data':{'button':'left','down':False}}]
            qmp('input-send-event',{'device':'lemma-hardware','events':events})
            qmp('input-send-event',{'device':'lemma-hardware','events':[{'type':'btn','data':{'button':'left','down':True}}]})
            head=[read(pen+256+i*8) for i in range(9)]
            assert head==[1,1000000,65535,0,2047,7,1,0,2],('actual pointer head',head)
            qmp('input-send-event',{'device':'lemma-hardware','events':[{'type':'btn','data':{'button':'left','down':False}}]})
            assert [read(pen+256+i*8) for i in range(9)]==head,'head stays immutable during next input'
            write(pen+88,1);assert read(pen+256)==2 and read(pen+296)==6
            write(pen+88,2);assert read(pen+32)==0
            raw=(a.output/'raw.bin').read_bytes()
            import struct
            records=[list(struct.unpack('<9Q',raw[i:i+72])) for i in range(0,len(raw),72)]
            assert records==[[1,1000000,65535,0,0,6,1,0,1],[2,1000000,65535,0,2047,7,1,0,1],[3,1000000,65535,0,0,6,1,0,1]],'all bridge ingress retained'
            state=json.loads(qmp('qom-get',{'path':'/machine/lemma-hardware','property':'device-state'}))
            assert state['pen']['count']==0 and state['paper']['completed']==1
            qmp('screendump',{'filename':str((a.output/'controller-visible.ppm').resolve())})
            assert_visible_pattern(a.output/'controller-visible.ppm')
            # Invalid geometry leaves prior target/visible pixels intact. A reset
            # during refresh cancels its timer but retains completed panel state.
            write(base+136,0);write(base+112,2);write(base+104,2)
            assert read(base+24)==3 and read(base+160)==1
            write(base+168,1);write(base+136,2);write(base+104,2)
            assert read(base+16)&1
            write(base+176,1);assert read(base+16)==8 and read(base+112)==2
            transact('clock_step 25000000');assert read(base+160)==1
            qmp('screendump',{'filename':str((a.output/'controller-after-reset.ppm').resolve())})
            assert (a.output/'controller-visible.ppm').read_bytes()==(a.output/'controller-after-reset.ppm').read_bytes()
            # Recovery is a full Gray4 quality refresh from newly uploaded guest
            # target data. This literal hardware fixture uses the reset-white RAM.
            for off,value in [(120,0),(128,0),(136,1650),(144,2200),(152,2),(112,3),(104,2)]:write(base+off,value)
            transact('clock_step 25000000');assert read(base+16)==2 and read(base+160)==3
            write(base+168,3);assert read(base+16)==0
            # Fill actual FIFO without ACK, then cross its limit. Loss preserves
            # only its immutable head and requires release before fresh contact.
            qmp('input-send-event',{'device':'lemma-hardware','events':[{'type':'btn','data':{'button':'left','down':True}}]})
            loss_head=[read(pen+256+i*8) for i in range(9)]
            for _ in range(256):qmp('input-send-event',{'device':'lemma-hardware','events':[{'type':'btn','data':{'button':'left','down':True}}]})
            assert read(pen+16)&2 and read(pen+32)==1
            assert [read(pen+256+i*8) for i in range(9)]==loss_head
            epoch=read(pen+40);write(pen+96,epoch)
            qmp('input-send-event',{'device':'lemma-hardware','events':[{'type':'btn','data':{'button':'left','down':True}}]});assert read(pen+32)==0
            qmp('input-send-event',{'device':'lemma-hardware','events':[{'type':'btn','data':{'button':'left','down':False}}]});assert read(pen+32)==0
            qmp('input-send-event',{'device':'lemma-hardware','events':[{'type':'btn','data':{'button':'left','down':True}}]});assert read(pen+32)==1
            recovered_state=json.loads(qmp('qom-get',{'path':'/machine/lemma-hardware','property':'device-state'}))
            # Actual FDT generation is captured separately in the result.
            result={'status':'PASS','scope':'actual QEMU device/PLIC boundary and synthetic pointer ingress observations only; no guest notebook/manual GUI claim','argv':command,'descriptor':desc,'device_state':state,'recovered_device_state':recovered_state,'raw_ingress':records,'trace':wire}
            (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
except BaseException as error:
    (a.output/'result.json').write_text(json.dumps({'status':'FAIL','error':str(error),'trace':wire},indent=2)+'\n')
    raise
finally:
    if qmp_stream:qmp_stream.close()
    if qmp_channel:qmp_channel.close()
    if channel:channel.close()
    if q and q.poll() is None:q.terminate()
    if q:
        try:q.wait(timeout=5)
        except subprocess.TimeoutExpired:q.kill();q.wait(timeout=5)
