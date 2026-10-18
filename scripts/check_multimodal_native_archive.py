#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact0.14 source/archive corruption admission; no new machine execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from multimodal_native_bundle import prepared_archive,PROFILE
from silicon_guest_bundle import read_json

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True);a=p.parse_args()
    origin=a.bundle.resolve();out=a.work_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    start=time.monotonic();report={'schema':'lemma-multimodal-native-archive-check/1','result':'FAIL','scope':__doc__,'cases':[]}
    def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    try:
        prepared_archive(origin,'qemu','notebook',PROFILE);report['bundle_sha256']=sha(origin/'bundle.json')
        private=out/'private';shutil.copytree(origin,private,copy_function=os.link)
        # Mutation targets become independent copies before any write.
        meta=private/'bundle.json';raw=meta.read_bytes();meta.unlink();meta.write_bytes(raw)
        manifest=read_json(meta);name=next(iter(manifest['sources']));source=private/'source'/name;source_raw=source.read_bytes();source.unlink();source.write_bytes(source_raw)
        def check():return prepared_archive(private,'qemu','notebook',PROFILE)
        check()
        def rejected(label,change,undo,validator=check):
            try:
                change()
                try:validator()
                except (ValueError,OSError,KeyError) as e:report['cases'].append({'case':label,'result':'REJECTED','reason':str(e)})
                else:raise ValueError('Corrupt archive accepted: '+label)
            finally:undo()
        rejected('changed original source byte',lambda:source.write_bytes(source_raw+b'\n'),lambda:source.write_bytes(source_raw))
        rejected('missing original source',source.unlink,lambda:source.write_bytes(source_raw))
        rejected('symlinked original source',lambda:(source.unlink(),source.symlink_to(origin/'source'/name)),lambda:(source.unlink(),source.write_bytes(source_raw)))
        extra=private/'unlisted';rejected('unlisted file',lambda:extra.write_bytes(b'x'),extra.unlink)
        bad=json.loads(raw);bad['backends']['qemu']['cpu']='unsupported-cpu';rejected('wrong CPU contract',lambda:meta.write_text(json.dumps(bad)),lambda:meta.write_bytes(raw))
        bad=json.loads(raw);bad['profile']='lemma-silicon-dev/0.15.0';rejected('successor relabel',lambda:meta.write_text(json.dumps(bad)),lambda:meta.write_bytes(raw))
        bad=json.loads(raw);bad['configurations']['notebook']='lemmasim-silicon-power-notebook';rejected('different notebook configuration',lambda:meta.write_text(json.dumps(bad)),lambda:meta.write_bytes(raw))
        rejected('no inherited RTL authority',lambda:None,lambda:None,lambda:prepared_archive(private,'rtl','notebook',PROFILE))
        check();report['result']='PASS'
    except BaseException as e:report['error']=str(e);raise
    finally:
        report['elapsed_seconds']=time.monotonic()-start;report['observer_sha256']=sha(__file__);report['validator_sha256']=sha(Path(__file__).with_name('multimodal_native_bundle.py'));(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('result','cases','elapsed_seconds')},indent=2))
if __name__=='__main__':main()
