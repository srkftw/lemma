#!/usr/bin/env python3
"""Validate the actual audited USB guest archive and private corruptions.

This is source/artifact admission, not new compilation or guest execution.
"""
import argparse,json,shutil,time
from pathlib import Path
import silicon_guest as guest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--guest-build',type=Path,required=True)
    p.add_argument('--guest-source-root',type=Path,required=True)
    p.add_argument('--work-dir',type=Path,required=True)
    a=p.parse_args();build=a.guest_build.resolve();origin=a.guest_source_root.resolve();out=a.work_dir.resolve()
    if out.exists() or not out.is_relative_to(guest.ROOT/'build'):raise ValueError('Use an unused owned build output')
    out.mkdir(parents=True);started=time.monotonic();report={'schema':'lemma-guest-source-archive-check/1','status':'FAIL','scope':__doc__,'cases':[]}
    config=json.loads((build/'build.json').read_text())['configuration']
    def check(b,r):return guest.guest_source_archive(b,r,config,'O2','lemma-silicon-dev/0.6.0')
    try:
        report['original']=check(build,origin)
        private=out/'private';root=private/'consumed-source-root';shutil.copytree(origin,root)
        sidecar=private/'consumed-source-archive.json';shutil.copyfile(origin.parent/sidecar.name,sidecar)
        raw=sidecar.read_bytes();metadata=json.loads(raw)
        def validate():return check(build,root)
        validate()
        def rejected(label,change,undo,validator=validate):
            try:
                change()
                try:validator()
                except (ValueError,OSError) as e:report['cases'].append({'case':label,'status':'REJECTED','reason':str(e)})
                else:raise ValueError('Corrupt guest archive accepted: '+label)
            finally:undo()
        key=next(iter(metadata['source_inputs']));item=root/key;original=item.read_bytes()
        rejected('changed actual source byte',lambda:item.write_bytes(original+b'\n'),lambda:item.write_bytes(original))
        rejected('missing actual source file',lambda:item.unlink(),lambda:item.write_bytes(original))
        rejected('symlinked source file',lambda:(item.unlink(),item.symlink_to(origin/key)),lambda:(item.unlink(),item.write_bytes(original)))
        extra=root/'unlisted-source';rejected('unlisted actual source file',lambda:extra.write_bytes(b'x'),lambda:extra.unlink())
        bad=json.loads(raw);del bad['source_inputs'][key]
        rejected('omitted declared input',lambda:sidecar.write_text(json.dumps(bad)),lambda:sidecar.write_bytes(raw))
        bad=json.loads(raw);bad['tools']['lean']['version']='wrong'
        rejected('wrong original tool version',lambda:sidecar.write_text(json.dumps(bad)),lambda:sidecar.write_bytes(raw))
        rejected('duplicate metadata keys',lambda:sidecar.write_text('{"schema":1,"schema":2}'),lambda:sidecar.write_bytes(raw))
        # Hardlink immutable artifacts into a private build. The mutated audit and
        # image are independent copies; the original artifacts are never written.
        copied=out/'guest';shutil.copytree(build,copied,ignore=shutil.ignore_patterns('consumed-source-root'),copy_function=lambda s,d: __import__('os').link(s,d))
        for name in ('audit.json','image.elf'):
            target=copied/name;target.unlink();shutil.copyfile(build/name,target)
        target=copied/'audit.json';audit_raw=target.read_bytes();bad=json.loads(audit_raw);bad['status']='FAIL'
        rejected('failed strict audit',lambda:target.write_text(json.dumps(bad)),lambda:target.write_bytes(audit_raw),lambda:check(copied,root))
        target=copied/'image.elf';image_raw=target.read_bytes()
        rejected('changed actual RV64 image byte',lambda:target.write_bytes(bytes([image_raw[0]^1])+image_raw[1:]),lambda:target.write_bytes(image_raw),lambda:check(copied,root))
        validate();report['status']='PASS';report['inputs']=report['original']['inputs']
    except BaseException as e:report['error']=str(e);raise
    finally:
        report['host_seconds']=time.monotonic()-started;report['observer_sha256']=guest.sha(__file__);report['validator_sha256']=guest.sha(guest.__file__)
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'inputs':report['inputs'],'rejected':len(report['cases']),'host_seconds':report['host_seconds']}))
if __name__=='__main__':main()
