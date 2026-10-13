#!/usr/bin/env python3
"""Build the hosted-Lean decoded-packet USB host with opaque durable peer policy.

This is native development packet transport, not a physical PHY, USB class
qualification, whole-machine continuation or in-browser hosted process.
"""
from pathlib import Path
import argparse,json,os,subprocess,sys
from lemmasim_companion import build as build_companion,validate as validate_companion,sha,peer_info
ROOT=Path(__file__).resolve().parents[1]
SOURCES=tuple(ROOT/'sim/usb'/n for n in ('USBPacket.lean','USBHost.lean'))+(Path(__file__).resolve(),ROOT/'flake.lock')
def build(output):
    output=Path(output).resolve()
    if output.exists() or not output.is_relative_to(ROOT/'build'):raise ValueError('USB output must be unused under build/')
    output.mkdir(parents=True)
    before={str(p.relative_to(ROOT)):sha(p) for p in SOURCES}
    companion=build_companion(output/'companion')
    environment=dict(os.environ,LEAN_PATH=str(output)+':'+str(output/'companion'))
    for module in ('USBPacket','USBHost'):
        subprocess.run(['lean','-R',str(ROOT/'sim/usb'),'-o',str(output/(module+'.olean')),'-c',str(output/(module+'.c')),str(ROOT/'sim/usb'/(module+'.lean'))],env=environment,cwd=ROOT,check=True,timeout=120)
        subprocess.run(['leanc','-O2','-c',str(output/(module+'.c')),'-o',str(output/(module+'.o'))],check=True,timeout=120)
    subprocess.run(['leanc',*[str(output/'companion'/(n+'.o')) for n in ('Protocol','HostIO','ClientPolicy')],str(output/'USBPacket.o'),str(output/'USBHost.o'),'-o',str(output/'usb-host')],check=True,timeout=120)
    if before!={str(p.relative_to(ROOT)):sha(p) for p in SOURCES}:raise ValueError('USB host sources changed during build')
    result={'schema':'lemma-usb-host-dev/2','scope':'hosted Lean packet/control/toggle and unchanged opaque backing policy; no guest/PHY/whole-machine result','sources':before,'companion_prepared':{'path':str(output/'companion/prepared.json'),'sha256':sha(output/'companion/prepared.json')},'lean_revision':companion['lean_revision'],'host_tools':companion['host_tools'],'objects':{n:sha(output/n) for n in ('USBPacket.c','USBHost.c','USBPacket.o','USBHost.o')},'binary':{'path':str(output/'usb-host'),'sha256':sha(output/'usb-host')},'target_objects_added':[]}
    (output/'prepared.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return result

def validate(prepared):
    prepared=Path(prepared).resolve();r=json.loads(prepared.read_text())
    if r.get('schema')!='lemma-usb-host-dev/2' or r.get('sources')!={str(p.relative_to(ROOT)):sha(p) for p in SOURCES}:raise ValueError('USB host source identity changed')
    c=r['companion_prepared'];p=Path(c['path'])
    if sha(p)!=c['sha256']:raise ValueError('USB companion manifest changed')
    validate_companion(p)
    for n,digest in r['objects'].items():
        if n not in ('USBPacket.c','USBHost.c','USBPacket.o','USBHost.o') or sha(prepared.parent/n)!=digest:raise ValueError('USB host object identity')
    if set(r['objects'])!={'USBPacket.c','USBHost.c','USBPacket.o','USBHost.o'}:raise ValueError('USB host object closure')
    binary=Path(r['binary']['path'])
    if not binary.is_file() or not os.access(binary,os.X_OK) or sha(binary)!=r['binary']['sha256']:raise ValueError('USB host binary identity')
    for item in r['host_tools'].values():
        if sha(item['path'])!=item['sha256']:raise ValueError('USB host tool identity')
    return r

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('build');q.add_argument('--output-dir',type=Path,required=True)
    q=s.add_parser('host');q.add_argument('--prepared',type=Path,required=True);q.add_argument('--directory',type=Path,required=True);q.add_argument('--socket',type=Path,required=True);q.add_argument('--state',type=Path,required=True)
    a=p.parse_args()
    if a.action=='build':return build(a.output_dir)
    r=validate(a.prepared);peer=peer_info(a.directory);exe=r['binary']['path']
    os.execv(exe,[exe,str(a.socket.resolve()),str(a.state.resolve()),str(peer['writer']),str(ROOT/'sim/companion/os_io.py')])
if __name__=='__main__':main()
