#!/usr/bin/env python3
"""Bounded actual guest device observation; this is not notebook acceptance."""
from __future__ import annotations
import argparse, hashlib, json, os, re, selectors, signal, subprocess, time
from pathlib import Path

RECORD = re.compile(rb'K1(?: [0-9a-f]{16}){5}\n')
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def argv(qemu,image,disk,raw=None,trace=None):
    args=[str(qemu),'-machine','lemmasim-virt','-m','128M','-smp','1','-cpu','rv64,smrnmi=false,smdbltrp=false',
          '-accel','tcg','-nodefaults','-bios','none','-kernel',str(image),'-display','none','-monitor','none','-serial','stdio',
          '-rtc','base=2026-10-10T00:00:00,clock=vm','-global','virtio-mmio.force-legacy=false',
          '-drive',f'if=none,id=lemma-disk,file={disk},format=raw,cache=directsync',
          '-device','virtio-blk-device,drive=lemma-disk,bus=virtio-mmio-bus.0,werror=report,rerror=report']
    if raw:args+=['-global',f'lemma-paper-pen.raw-input={raw}']
    if trace:args+=['-global',f'lemma-paper-pen.trace-file={trace}']
    return args

def observe(qemu,image,out,timeout=30,raw=None):
    if not 0<timeout<=300:raise ValueError('timeout must be1..300seconds')
    out.mkdir(parents=True,exist_ok=False);disk=(out/'disk.raw').resolve()
    with disk.open('xb') as stream:stream.truncate(256*1024*1024)
    command=argv(qemu.resolve(),image.resolve(),disk,raw.resolve() if raw else None)
    result={'schema_version':1,'status':'FAIL','scope':'guest-device-bringup-only','argv':command,
            'guest_image_sha256':digest(image),'qemu_sha256':digest(qemu),'timeout_seconds':timeout}
    output=bytearray();errors=bytearray();process=None;started=time.monotonic();records=[]
    try:
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        selector=selectors.DefaultSelector()
        for stream,name in ((process.stdout,'output'),(process.stderr,'errors')):
            os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,name)
        while time.monotonic()-started<timeout:
            for key,_ in selector.select(.1):
                chunk=os.read(key.fileobj.fileno(),65536)
                if not chunk:selector.unregister(key.fileobj)
                elif key.data=='output':output.extend(chunk)
                else:errors.extend(chunk)
            if b'K1 0000000000000404 ' in output:
                records=[tuple(int(x,16) for x in item.split()[1:]) for item in RECORD.findall(output)]
                if not any(r[0]==0x405 and r[1]==524288 for r in records):raise ValueError('disk capacity witness missing')
                if [r[1] for r in records if r[0]==0x401]!=[1,5]:raise ValueError('read/flush completions differ')
                if sum(r[0]==0x406 and r[1]==1 for r in records)<2:raise ValueError('real SEIP source1 notifications missing')
                if errors:raise ValueError('QEMU stderr present')
                result.update(status='PASS',observed='actual read and flush completion through PLIC/S trap/Lean driver',records=records)
                break
            if process.poll() is not None:raise ValueError('QEMU exited before observation protocol')
            if len(output)>4*1024*1024:raise ValueError('diagnostic output limit exceeded')
        else:raise TimeoutError('bounded observation deadline expired')
    except Exception as error:result['error']=str(error)
    finally:
        if process is not None:
            stopped=process.poll() is None
            if stopped:os.killpg(process.pid,signal.SIGKILL)
            tail,err=process.communicate(timeout=5);output.extend(tail);errors.extend(err)
            result['cleanup']={'explicit_host_stop':stopped,'reaped':process.poll() is not None,'returncode':process.returncode}
        (out/'serial.bin').write_bytes(output);(out/'stderr.bin').write_bytes(errors)
        result.update(elapsed_seconds=time.monotonic()-started,artifacts={n:digest(out/n) for n in ('serial.bin','stderr.bin','disk.raw')})
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,required=True)
    parser.add_argument('--image',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--timeout',type=float,default=30);parser.add_argument('--raw-input',type=Path)
    args=parser.parse_args()
    try:result=observe(args.qemu,args.image,args.output_dir,args.timeout,args.raw_input)
    except (OSError,ValueError) as error:print(f'FAIL: {error}');return 1
    print(json.dumps({k:result[k] for k in ('status','scope','observed','error') if k in result}))
    return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
