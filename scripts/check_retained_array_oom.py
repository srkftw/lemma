#!/usr/bin/env python3
"""Read-only qualification of a real Array OOM run whose report failed to encode.

No machine is launched, stepped, restored or contacted. Original failure remains.
Independent durable-format/raw-sample/pixel observations qualify retained outputs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct

from check_live_notebook import guest_events,require,sha,visible_pixels
from check_math_session import MathChecker
from check_arithmetic_isolation import managed_oom_artifacts
from math_oracle import inspect,ARRAY_EXECUTION_IDENTITIES
from store_oracle import recover
import silicon_guest_bundle as bundle

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('campaign','original-disk','guest-build','guest-source-root','native-bundle','work-dir'):
        parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();root=args.campaign.resolve();out=args.work_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    report={'status':'FAIL','scope':'independent read-only retained real ArrayOOM/ink/barrier/cold observations; original report serialization failure remains; no repeated guest execution'}
    try:
        failure=json.loads((root/'report-failure.json').read_text())
        require(failure['status']=='FAIL' and failure['actual_error']=='TypeError: Object of type PosixPath is not JSON serializable',
                'retained original report failure differs')
        require(sha(root/'original-check_arithmetic_isolation.py')==failure['observer_sha256'],
                'original executed observer bytes changed')
        data=bundle.prepared(args.native_bundle,'qemu','notebook','lemma-silicon-dev/0.3.0')
        archive=bundle.laboratory_guest_archive(args.guest_build,args.guest_source_root,'lemma-silicon-dev/0.3.0',
              'lemmasim-silicon-array-arithmetic-oom-development','laboratory')
        admission=managed_oom_artifacts(args.guest_build,array_payload=True)
        metadata={name:json.loads((root/name/'session.json').read_text()) for name in ('live','cold')}
        identity=metadata['live']['identity']
        require(identity==metadata['cold']['identity'] and identity['runtime']==data['qemu']['sha256'] and
                identity['guest']==archive['image']['sha256'] and
                all(identity['development_guest_source_archive'][key]==archive[key] for key in
                    ('inventory','build','provenance','audit','image','configuration','source_commit','dirty_paths','inputs','scope')),
                'actual live/cold archive/runtime/guest association differs')
        for value in metadata.values():
            require(value['mode']=='laboratory' and value['argv']!=[], 'actual Laboratory launch authority missing')
            require(not Path('/proc/'+str(value['pid'])).exists(),'original owned session is still live')
        rows={name:guest_events(root/name/'uart-0.bin') for name in ('live','cold')}
        for value in rows.values():
            require(not any(row[0] in (0x41f,0x424,0xd4,0xf4) for row in value),'format/storage/process failure in retained run')
            require([row for row in value if row[0]==0x456]==[(0x456,1,31,5,10000000)] and
                    [row for row in value if row[0]==0x45c]==[(0x45c,*ARRAY_EXECUTION_IDENTITIES)],
                    'actual User5 pressure mode or Protocol5 authority differs')
        request=[row for row in rows['live'] if row[0]==0x459]
        reply=[row for row in rows['live'] if row[0]==0x455]
        require(len(request)==len(reply)==1 and reply[0][1:3]==request[0][1:3] and reply[0][3:]==(237,0),
                'actual heap failure was not the submitted request/revision')
        require([row for row in rows['live'] if row[0]==0x454]==[(0x454,237,1,1,0)] and
                not any(row[0]==0x450 and row[3]!=0 for row in rows['live']),
                'actual resource error or evidence differs')
        documents={};records={};sequences={}
        for name in ('before-check','after-error','final','cold-notebook'):
            _,sequences[name],records[name]=recover((root/(name+'.raw')).read_bytes())
            payload=records[name][1,0x8001].payload;document=inspect(payload,1,0x8001)
            require(len(payload)==2496 and document['format']=='lemma-mathematical-submission/6' and
                    document['outcome']==0 and not document['history'] and
                    document['execution']['active']=={'origin':'Unknown'},'actual Document6 acquired mathematical evidence')
            documents[name]=payload
        require(len(set(documents.values()))==1 and sequences['after-error']==sequences['before-check'] and
                sequences['final']>sequences['after-error'] and sequences['cold-notebook']==sequences['final'],
                'OOM changed acknowledged mathematics or writing/cold commit ordering differs')
        input_bytes=(root/'live/input-0.bin').read_bytes();require(len(input_bytes)==11*72,'actual raw stimulus length differs')
        raw=[struct.unpack_from('<9Q',input_bytes,i*72) for i in range(11)]
        stored=[]
        for (namespace,key),record in records['final'].items():
            if namespace==1 and key>0x10000:
                count=struct.unpack_from('<Q',record.payload,48)[0]
                stored.extend(struct.unpack_from('<9Q',record.payload,128+i*72) for i in range(count))
        require(stored==raw[5:],'guest did not persist exact post-OOM raw ink')
        require(records['final']==records['cold-notebook'],'new cold guest changed acknowledged object bytes')
        require(visible_pixels(root/'final.ppm')==visible_pixels(root/'cold-notebook.ppm'),
                'new cold complete controller pixels differ')
        observer=MathChecker.__new__(MathChecker)
        observer.label(root/'final.ppm','SAVED',24,132);observer.label(root/'cold-notebook.ppm','SAVED',24,132)
        require([row for row in rows['live'] if row[0] in (0x421,0x423,0x424)][-1][0:2]==(0x421,sequences['final']),
                'actual guest never acknowledged the final barrier')
        require(not any(row[0] in (0x423,0x454) for row in rows['cold']) and
                (root/'cold/input-0.bin').stat().st_size==0,'cold recovery received input or republished records')
        require(sha(args.original_disk)==sha(root/'live-input.raw') or sha(args.original_disk)==
                'c79dca00a597781d134ffdc3573eb1edc01915244b9c78efb7cac1eb6c188f46',
                'original acknowledged input differs from retained predeclared source')
        report.update(status='PASS',archive=archive,identity=identity,constructor_admission=admission,
          actual_request=request[0],actual_reply=reply[0],actual_error=237,document=6,protocol=5,
          raw_ink_samples=len(stored),durable_sequences=sequences,complete_cold_pixels_equal=True,
          actual_guest_barrier_acknowledged=True,original_medium_sha256=sha(args.original_disk),
          original_report_failure=failure,host_duration='original in-memory report lost; not reconstructed from file timestamps')
    except BaseException as error:
        report['error']=str(error);raise
    finally:
        files=[path for path in root.rglob('*') if path.is_file() and path.suffix in ('.json','.bin','.ppm','.raw','.py')]
        report['retained_artifacts']={str(path.relative_to(root)):sha(path) for path in files}
        report['observer_sha256']=sha(Path(__file__))
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'work_dir':str(out)}))

if __name__=='__main__':main()
