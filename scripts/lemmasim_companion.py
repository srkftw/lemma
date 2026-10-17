#!/usr/bin/env python3
"""Build and run the hosted-Lean development opaque backing peer.

This host transport is not a USB controller, guest companion service or finished
companion product. Guest block, notebook and recovery semantics stay in RV64.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCES=tuple(ROOT/'sim/companion'/name for name in ('Protocol.lean','HostIO.lean','Peer.lean','ClientPolicy.lean','Client.lean','os_io.py','server.py'))+(Path(__file__).resolve(),ROOT/'flake.lock')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def build(output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('use an unused companion build output')
    output.mkdir(parents=True)
    sources={str(path.relative_to(ROOT)):sha(path) for path in SOURCES}
    environment=dict(os.environ,LEAN_PATH=str(output))
    for module in ('Protocol','HostIO','ClientPolicy','Peer','Client'):
        subprocess.run(['lean','-R',str(ROOT/'sim/companion'),'-o',str(output/(module+'.olean')),'-c',str(output/(module+'.c')),str(ROOT/'sim/companion'/(module+'.lean'))],env=environment,cwd=ROOT,check=True,timeout=120)
        subprocess.run(['leanc','-O2','-c',str(output/(module+'.c')),'-o',str(output/(module+'.o'))],cwd=ROOT,check=True,timeout=120)
    for module in ('Peer','Client'):
        subprocess.run(['leanc',str(output/'Protocol.o'),str(output/'HostIO.o'),*([str(output/'ClientPolicy.o')] if module=='Client' else []),str(output/(module+'.o')),'-o',str(output/('companion-'+module.lower()))],cwd=ROOT,check=True,timeout=120)
    if sources!={str(path.relative_to(ROOT)):sha(path) for path in SOURCES}:
        raise ValueError('companion source changed during build')
    prefix=Path(subprocess.check_output(['lean','--print-prefix'],text=True).strip()).resolve()
    revision=subprocess.check_output(['lean','--githash'],text=True).strip()
    result={'schema':'lemma-companion-backing-dev/1','scope':'hosted Lean opaque backing protocol; same-owner Unix raw transport; not USB',
            'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'sources':sources,'lean_version':subprocess.check_output(['lean','--version'],text=True).strip(),
            'lean_revision':revision or None,'hosted_lean_prefix':str(prefix),
            'host_tools':{name:{'path':str(Path(shutil.which(name)).resolve()),'sha256':sha(Path(shutil.which(name)).resolve())} for name in ('lean','leanc','cc')},
            'generated_host_objects':{name:sha(output/name) for name in ('Protocol.c','HostIO.c','ClientPolicy.c','Peer.c','Client.c','Protocol.o','HostIO.o','ClientPolicy.o','Peer.o','Client.o')},
            'target_objects_added':[],
            'binaries':{name:{'path':str(output/name),'sha256':sha(output/name)} for name in ('companion-peer','companion-client')},
            'medium_bytes':268435456,'max_wire_bytes':1048576+72,'max_journal_bytes':64*1024*1024,'max_receipts':100000}
    (output/'prepared.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return result

def validate(prepared):
    result=json.loads(Path(prepared).read_text())
    if result.get('schema')!='lemma-companion-backing-dev/1':raise ValueError('unsupported companion identity')
    if result.get('sources')!={str(path.relative_to(ROOT)):sha(path) for path in SOURCES}:raise ValueError('companion sources changed; build a new prepared peer')
    for name,item in result.get('binaries',{}).items():
        path=Path(item['path'])
        if name not in ('companion-peer','companion-client') or not path.is_file() or not os.access(path,os.X_OK) or sha(path)!=item['sha256']:raise ValueError('companion executable identity')
    if set(result.get('binaries',{}))!={'companion-peer','companion-client'}:raise ValueError('companion executable set')
    return result

def initialize(directory,base=None,writer=None):
    directory=Path(directory).resolve()
    if directory.exists():raise ValueError('peer directory already exists')
    if writer is None:writer=int.from_bytes(os.urandom(8),'little') or 1
    if not 1<=writer<=2**64-1:raise ValueError('writer bound')
    directory.mkdir(mode=0o700,parents=True)
    medium=directory/'base.img'
    try:
        with medium.open('xb') as destination:
            if base:
                base=Path(base)
                if not base.is_file() or base.stat().st_size!=268435456:raise ValueError('base must be a 256MiB opaque medium')
                with base.open('rb') as source:
                    while True:
                        chunk=source.read(1024*1024)
                        if not chunk:break
                        if any(chunk):destination.write(chunk)
                        else:destination.seek(len(chunk),os.SEEK_CUR)
                destination.truncate(268435456)
            else:destination.truncate(268435456)
            destination.flush();os.fsync(destination.fileno())
        os.chmod(medium,0o400)
        manifest=directory/'peer.json'
        with manifest.open('x') as stream:
            json.dump({'schema':'lemma-companion-backing-dev/1','writer':writer,'base':str(medium),'trust':'same-owner development transport; no owner authentication'},stream,indent=2)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        descriptor=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
    except BaseException:
        # Leave this owned incomplete initialization inspectable; do not delete
        # arbitrary media or silently retry over an existing peer directory.
        raise
    print(str(directory/'peer.json'))

def peer_info(directory):
    directory=Path(directory).resolve()
    info=json.loads((directory/'peer.json').read_text())
    if info.get('schema')!='lemma-companion-backing-dev/1' or not isinstance(info.get('writer'),int) or not 1<=info['writer']<=2**64-1:raise ValueError('peer identity')
    if Path(info.get('base','')).resolve()!=directory/'base.img':raise ValueError('peer base path')
    return info

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('build');q.add_argument('--output-dir',type=Path,required=True)
    q=s.add_parser('init');q.add_argument('--directory',type=Path,required=True);q.add_argument('--base',type=Path);q.add_argument('--writer',type=int)
    for action in ('serve','client'):
        q=s.add_parser(action);q.add_argument('--prepared',type=Path,required=True);q.add_argument('--directory',type=Path,required=True);q.add_argument('--socket',type=Path,required=True)
        if action=='serve':q.add_argument('--drop-reply',type=int,default=0);q.add_argument('--exit-after-reply',type=int,default=0)
        else:q.add_argument('--state',type=Path,required=True)
    a=p.parse_args(argv)
    if a.action=='build':return build(a.output_dir)
    if a.action=='init':return initialize(a.directory,a.base,a.writer)
    prepared=validate(a.prepared);info=peer_info(a.directory)
    helper=ROOT/'sim/companion/os_io.py'
    if a.action=='client':
        os.execv(prepared['binaries']['companion-client']['path'],[prepared['binaries']['companion-client']['path'],str(a.socket.resolve()),str(a.state.resolve()),str(info['writer']),str(helper)])
    sys.path.insert(0,str(ROOT/'sim/companion'))
    from server import serve
    return serve(prepared['binaries']['companion-peer']['path'],a.directory.resolve(),info['base'],info['writer'],helper,a.socket,a.drop_reply,a.exit_after_reply)

if __name__=='__main__':
    main()
