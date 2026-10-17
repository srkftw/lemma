#!/usr/bin/env python3
"""Actual original native USB closure and fail-closed archive mutation checks.

This validates source/artifact identity, not fresh target compilation or guest execution.
All mutations occur in private copies; the original native binary/archive remain unchanged.
"""
import argparse,json,shutil,time
from pathlib import Path
import silicon_guest as guest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rtl-build',type=Path,required=True)
    p.add_argument('--rtl-source-root',type=Path,required=True)
    p.add_argument('--work-dir',type=Path,required=True)
    p.add_argument('--profile',choices=('lemma-silicon-dev/0.6.0','lemma-silicon-dev/0.8.0','lemma-silicon-dev/0.11.0'),default='lemma-silicon-dev/0.6.0')
    a=p.parse_args();build=a.rtl_build.resolve();origin=a.rtl_source_root.resolve();out=a.work_dir.resolve()
    if out.exists() or not out.is_relative_to(guest.ROOT/'build'):raise ValueError('Use an unused owned build output')
    out.mkdir(parents=True);started=time.monotonic();report={'schema':'lemma-native-source-archive-check/1','status':'FAIL','scope':__doc__,'cases':[]}
    profile=a.profile
    try:
        _,sources,evidence=guest.native_source_archive(build,origin,profile);report['original']=evidence
        private=out/'private';root=private/'consumed-source-root';shutil.copytree(origin,root)
        sidecar=private/'consumed-source-archive.json';receipt=private/'consumed-runtime-receipt.json'
        shutil.copyfile(origin.parent/sidecar.name,sidecar);shutil.copyfile(origin.parent/receipt.name,receipt)
        def validate():return guest.native_source_archive(build,root,profile)
        validate()
        def rejected(label,change,undo,validator=validate):
            try:
                change()
                try:validator()
                except (ValueError,OSError) as e:report['cases'].append({'case':label,'status':'REJECTED','reason':str(e)})
                else:raise ValueError('Corrupt archive accepted: '+label)
            finally:undo()
            validate()
        raw=sidecar.read_bytes();s=json.loads(raw);key=next(iter(s['source_inputs']))
        item=root/key;original=item.read_bytes()
        rejected('changed actual source byte',lambda:item.write_bytes(original+b'\n'),lambda:item.write_bytes(original))
        rejected('missing actual source file',lambda:item.unlink(),lambda:item.write_bytes(original))
        rejected('symlinked source',lambda:(item.unlink(),item.symlink_to(origin/key)),lambda:(item.unlink(),item.write_bytes(original)))
        extra=root/'unlisted-source';rejected('unlisted actual source',lambda:extra.write_bytes(b'x'),lambda:extra.unlink())
        bad=json.loads(raw);del bad['source_inputs'][key]
        rejected('omitted declared consumed input',lambda:sidecar.write_text(json.dumps(bad)),lambda:sidecar.write_bytes(raw))
        bad=json.loads(raw);bad['source_inputs']['surprise']='0'*64
        rejected('extra declared consumed input',lambda:sidecar.write_text(json.dumps(bad)),lambda:sidecar.write_bytes(raw))
        bad=json.loads(raw);bad['snapshot_identity']='0'*64
        rejected('wrong original runtime identity',lambda:sidecar.write_text(json.dumps(bad)),lambda:sidecar.write_bytes(raw))
        rejected('duplicate metadata keys',lambda:sidecar.write_text('{"schema":"first","schema":"second"}'),lambda:sidecar.write_bytes(raw))
        receipt_raw=receipt.read_bytes();bad=json.loads(receipt_raw);del bad['rtl_sources'][next(iter(bad['rtl_sources']))]
        rejected('incomplete original preparation receipt',lambda:receipt.write_text(json.dumps(bad)),lambda:receipt.write_bytes(receipt_raw))
        # A relocatable copy of the original binary is still bound to the exact
        # original manifest. Alter only that private binary, never the live file.
        copied=out/'native';(copied/'obj').mkdir(parents=True)
        shutil.copyfile(build/'build.json',copied/'build.json');shutil.copyfile(build/'obj/lemma-rtl',copied/'obj/lemma-rtl')
        relocated=json.loads(receipt_raw);relocated['rtl_build']['path']=str(copied/'build.json');relocated['binary']['path']=str(copied/'obj/lemma-rtl');receipt.write_text(json.dumps(relocated))
        guest.native_source_archive(copied,root,profile)
        binary=copied/'obj/lemma-rtl'
        with binary.open('r+b') as stream:
            byte=stream.read(1);stream.seek(0);stream.write(bytes([byte[0]^1]))
        try:guest.native_source_archive(copied,root,profile)
        except (ValueError,OSError) as e:report['cases'].append({'case':'changed actual native executable byte','status':'REJECTED','reason':str(e)})
        else:raise ValueError('Changed native executable accepted')
        receipt.write_bytes(receipt_raw);validate()
        report['status']='PASS';report['inputs']=len(sources)
    except BaseException as e:
        report['error']=str(e);raise
    finally:
        report['host_seconds']=time.monotonic()-started;report['observer_sha256']=guest.sha(__file__);report['validator_sha256']=guest.sha(guest.__file__)
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'inputs':report['inputs'],'rejected':len(report['cases']),'host_seconds':report['host_seconds']}))

if __name__=='__main__':main()
