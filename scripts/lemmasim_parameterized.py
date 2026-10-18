#!/usr/bin/env python3
"""Admit a runtime parameterized task to the real isolated Lean checker.

Owner-local integrity-only UART framing. Requests and replies cross the existing
course consumer and kernel IPC; no host verdict or document mutation is issued.
The returned checker outcome applies to the complete immutable submission only.
"""
import argparse, hashlib, json, struct, sys, time, zlib
from pathlib import Path
from lemmasim_session import request as control
from lemmasim_tutor import ROOT, ROW, uart_path, source_inventory, tool_inventory, sha
from multimodal_deployment import PARAMETERIZED_CONFIGURATIONS

MAGIC=0x324b4843414d454c

def frame(payload):
    if len(payload)!=192:raise ValueError('complete192-byte task envelope required')
    words=struct.unpack('<24Q',payload)
    if words[0]!=2 or words[1]==0 or words[2]==0 or not 1<=words[18]<=0x7ffffffffffffffe:raise ValueError('invalid version/source/edition/request framing')
    return struct.pack('<8Q',MAGIC,2,1,words[1],words[2],192,words[18],zlib.crc32(payload))+payload

def completion(data,transaction,scope):
    rows=[]
    for m in ROW.finditer(data):
        tag,*words=(int(v,16) for v in m.group(1).split())
        if tag==0x72b and words[0]==transaction:rows.append(words)
        elif tag==0x72c and rows:
            if words!=scope:raise ValueError('actual guest completion has another source/edition/object/revision')
            if len(rows)!=1:raise ValueError('repeated actual checker completion')
            request,status,outcome,reserved=rows[0]
            if reserved!=0 or status!=0 or outcome not in range(1,6):raise ValueError('guest rejected runtime task or malformed checker outcome')
            return {'request':request,'status':status,'outcome':outcome,'scope':words,
                    'authority':'separately linked exact checker; not a notebook Verified grant'}
    return None

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session-dir',type=Path,required=True);p.add_argument('--request',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True)
    p.add_argument('--wait-cycles',type=int,default=100000000,help='bounded total machine cycles after byte admission, zero admits only');p.add_argument('--expected-outcome',type=int,choices=range(1,6));a=p.parse_args()
    out=a.work_dir.resolve();directory=a.session_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'build'):p.error('unused retained build output required')
    if not 0<=a.wait_cycles<=1000000000:p.error('wait cycles must be0..1e9')
    out.mkdir(parents=True);report={'status':'FAIL','scope':__doc__};started=time.monotonic()
    try:
        sources=source_inventory();sources['scripts/lemmasim_parameterized.py']=sha(Path(__file__).resolve())
        for name in ('Lemma/Services/Arithmetic/ClientV8.lean','Lemma/Services/Arithmetic/ProtocolV8.lean','Lemma/Services/Arithmetic/ServerV8.lean','Lemma/Multimodal/Parameterized.lean','Lemma/Courses/PackageInstaller.lean'):
            sources[name]=sha(ROOT/name)
        report.update(source_inputs=sources,tools=tool_inventory())
        for name,expected in sources.items():
            data=(ROOT/name).read_bytes()
            if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('source changed before archive')
            target=out/'consumed-source-root'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        metadata=json.loads((directory/'session.json').read_text());identity=metadata.get('identity',{})
        if metadata.get('schema')!='lemmasim-live/1' or metadata.get('mode') not in ('developer','laboratory') or identity.get('profile')!='lemma-silicon-dev/0.14.0':raise ValueError('exact owner-local Multimodal14 session required')
        argv=metadata.get('argv',[]);flag='-kernel' if metadata.get('backend')=='qemu' else '--image'
        if argv.count(flag)!=1:raise ValueError('actual guest image missing')
        image=Path(argv[argv.index(flag)+1]);build=json.loads((image.parent/'build.json').read_text())
        if build.get('configuration') not in PARAMETERIZED_CONFIGURATIONS or sha(image)!=identity.get('guest'):raise ValueError('exact parameterized guest required')
        observed=control(directory,{'action':'inspect'},timeout=60)
        if observed.get('identity')!=identity or observed.get('running') is not False:raise ValueError('pause exact session before task admission')
        uart=uart_path(directory,metadata);initial=uart.read_bytes();report['initial_uart_sha256']=hashlib.sha256(initial).hexdigest()
        if metadata.get('backend')=='qemu' and observed.get('machine',{}).get('devices',{}).get('uart_ingress',{}).get('enabled') is not True:raise ValueError('actual raw UART disabled')
        payload=a.request.read_bytes();packet=frame(payload);words=struct.unpack('<24Q',payload);transaction=words[18];scope=[words[1],words[2],words[3],words[5]]
        if completion(initial,transaction,scope) is not None:raise ValueError('request already completed; choose fresh increasing request')
        (out/'request.bin').write_bytes(payload);(out/'uart-command.bin').write_bytes(packet)
        report['identity']=identity;report['configuration']=build['configuration'];report['guest_build_sha256']=sha(image.parent/'build.json')
        cycle=observed.get('machine',{}).get('cycle')
        if type(cycle) is not int or cycle<0:raise ValueError('actual virtual cycle missing')
        report['admission']=control(directory,{'action':'inject','kind':'uart','cycle':cycle,'hex':packet.hex()},timeout=60)
        used=0;result=None
        while used<a.wait_cycles:
            step=min(1000000,a.wait_cycles-used);control(directory,{'action':'run','cycles':step},timeout=60);used+=step
            captured=uart.read_bytes()
            if not captured.startswith(initial):raise ValueError('UART history changed while awaiting checker')
            result=completion(captured[len(initial):],transaction,scope)
            if result is not None:break
            if time.monotonic()-started>60:raise ValueError('bounded60-second checker observation deadline')
        (out/'uart.log').write_bytes(uart.read_bytes())
        report.update(status='CHECKER_COMPLETED' if result else 'RAW_TASK_ADMITTED',completion=result,advanced_cycles=used,transport='OWNER_LOCAL_INTEGRITY_ONLY')
        if a.wait_cycles and result is None:raise ValueError('no actual checker completion within original cycle budget')
        if a.expected_outcome is not None and (result is None or result['outcome']!=a.expected_outcome):raise ValueError('independent expected outcome differs from actual guest result')
    except BaseException as error:report.update(status='FAIL',error=repr(error))
    if report.get('source_inputs'):
        report['consumed_inputs_unchanged']=all(sha(ROOT/name)==digest for name,digest in report['source_inputs'].items())
        if report['consumed_inputs_unchanged'] is not True:report.update(status='FAIL',source_guard_error='complete input changed')
    report['seconds']=time.monotonic()-started;(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k) for k in ('status','completion','error','seconds')}));return int(report['status']=='FAIL')
if __name__=='__main__':raise SystemExit(main())
