#!/usr/bin/env python3
"""Actual fresh canonical RTL Ready, immutable media and complete pixels.

Uses an already paused, freshly launched public session. No reset, restore,
format, journal mutation or completion drain is performed. The bounded PC
diagnostic is a different interface; its shorter limits remain unchanged.
"""
import argparse
import json
from pathlib import Path
import re
import time

from core0_common import sha256
from lemmasim_session import request
from silicon_guest_bundle import prepared
from supervise_usb_notebook import descendants
from check_live_notebook import visible_pixels


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session-dir',type=Path,required=True)
    p.add_argument('--native-bundle',type=Path,required=True)
    p.add_argument('--disk',type=Path,required=True)
    p.add_argument('--reference-pixels',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--cycles',type=int,default=2000000000)
    p.add_argument('--deadline',type=int,default=7200)
    p.add_argument('--quantum',type=int,default=1000000)
    args = p.parse_args()
    require(1 <= args.cycles <= 2000000000 and 1 <= args.deadline <= 7200 and
            100000 <= args.quantum <= 10000000 and
            (args.cycles+args.quantum-1)//args.quantum <= 4096, 'Invalid cold resource bounds')
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();last=None
    result={'schema':'lemma-canonical-cold/1','status':'RUNNING','scope':__doc__,
            'bounds':{'cycles':args.cycles,'deadline_seconds':args.deadline,'quantum':args.quantum,
                      'native_rss_limit_kib':524288},'observer_sha256':sha256(Path(__file__))}
    try:
        disk=args.disk.resolve();reference=args.reference_pixels.resolve()
        require(disk.is_file() and disk.stat().st_size==268435456,'Require actual256MiB initialized medium')
        expected=reference.read_bytes()
        require(len(expected)==len(b'P6\n1650 2200\n255\n')+1650*2200*3 and
                expected.startswith(b'P6\n1650 2200\n255\n'),'Require complete canonical reference pixels')
        medium_hash=sha256(disk)
        meta=json.loads((args.session_dir/'session.json').read_text())
        admitted=prepared(args.native_bundle,'rtl','notebook','lemma-silicon-dev/0.3.0')
        before=request(args.session_dir,{'action':'inspect'},120);last=before['machine']
        require(not before['running'] and last['cycle']==last['retired']==0 and
                not last['isolated_medium'],'Require untouched fresh CPU, not a restored fork')
        require(before['identity']['backend']=='rtl' and before['identity']['profile']=='lemma-silicon-dev/0.3.0',
                'Require the actual canonical RTL binding')
        argv=meta['argv']
        require('--restore' not in argv and '--events' not in argv and '--medium' in argv and
                Path(argv[argv.index('--medium')+1]).resolve()==disk,'Cold launch medium/restore policy differs')
        image=Path(argv[argv.index('--image')+1]).resolve()
        require(image==Path(admitted['workloads']['notebook']['image']['path']).resolve() and
                before['identity']['guest']==admitted['workloads']['notebook']['image']['sha256'] and
                sha256(image)==before['identity']['guest'] and
                Path(argv[0]).resolve()==Path(admitted['binary']['path']).resolve(),
                'Actual executable or loaded guest differs from immutable audited bundle')
        pid=meta['pid'];start_token=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[19]
        result.update(identity=before['identity'],actual_launch=argv,input_medium_sha256=medium_hash,
                      reference_pixels_sha256=sha256(reference),initial=last,process_tree_peak_rss_kib=0,
                      native_bundle_sha256=sha256(args.native_bundle/'bundle.json'))
        serial=args.session_dir/'uart.bin'
        ready=False
        with (out/'progress.jsonl').open('x') as trace:
            while last['cycle'] < args.cycles:
                require(time.monotonic()-started<args.deadline,'Original cold host deadline exceeded')
                require(not last['finished'],'Guest finished without canonical Ready')
                amount=min(args.quantum,args.cycles-last['cycle'])
                call=time.monotonic();nxt=request(args.session_dir,{'action':'run','cycles':amount},120)
                require(nxt['cycle']==last['cycle']+amount,'Machine did not execute exact requested interval')
                last=nxt
                require(time.monotonic()-started<args.deadline,'Machine interval finished after cold deadline')
                raw=serial.read_bytes() if serial.exists() else b''
                require(len(raw)<=2097152,'UART bound exceeded')
                rows=[tuple(int(x,16) for x in m) for m in re.findall(
                    rb'K1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})',raw)]
                require(not any(r[0] in (0x41f,0x423,0x424,0xd4,0xf4) for r in rows),
                        'Cold guest formatted, failed recovery or faulted')
                require(last['flushes']==0 and last['backing_io']['observed_write']==0 and
                        last['backing_io']['durable_barrier']==0,'Cold recovery wrote/published storage')
                require(Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[19]==start_token,
                        'Native process identity changed')
                # The session owner is Python. Include its actual RTL child;
                # measuring only the owner would understate machine memory.
                tree=descendants(pid)
                rss=sum(int(re.search(r'^VmRSS:\s+(\d+) kB$',
                    Path(f'/proc/{item["pid"]}/status').read_text(),re.M)[1]) for item in tree)
                result['process_tree_peak_rss_kib']=max(result['process_tree_peak_rss_kib'],rss)
                require(rss<=524288,'Native cold RSS bound exceeded')
                require(time.monotonic()-started<args.deadline,'Ready observation finished after cold deadline')
                trace.write(json.dumps({'cycle':last['cycle'],'host_seconds':time.monotonic()-started,
                    'call_seconds':time.monotonic()-call,'rss_kib':rss,'retired':last['retired'],
                    'pc':last['pc'],'privilege':last['privilege'],'backing':last['backing_io'],
                    'panel_completed':last['panel_completed'],'paper_busy':last['paper_busy']})+'\n');trace.flush()
                require(trace.tell()<=16777216,'Cold trace bound exceeded')
                publications=[r for r in rows if r[0]==0x425]
                ready=(any(r[0]==0x420 for r in rows) and bool(publications) and
                       last['paper_busy']==last['block_state']==0 and
                       last['panel_completed']==publications[-1][1]>0)
                if ready:
                    result.update(ready_cycle=last['cycle'],ready_host_seconds=time.monotonic()-started,
                                  actual_guest_rows=rows)
                    break
        require(ready,'No actual complete Ready within original cycle bound')
        pixels=out/'controller.ppm';request(args.session_dir,{'action':'panel','path':str(pixels)},120)
        require(visible_pixels(pixels)==visible_pixels(reference),
                'Complete controller pixels differ from acknowledged reference')
        require(sha256(disk)==medium_hash,'Cold recovery changed input bytes')
        snapshot=request(args.session_dir,{'action':'snapshot','path':str(out/'ready-checkpoint')},120)
        require(snapshot['machine']==last,'Observational snapshot altered Ready boundary')
        result.update(status='PASS_COLD_READY_MEDIA_AND_ALL_PIXELS',complete_pixels=3630000,
                      medium_unchanged=True,snapshot_after_actual_cold_only=snapshot['snapshot'])
    except (OSError,ValueError,RuntimeError,KeyError) as error:
        result.update(status='FAIL',error=str(error))
    finally:
        result.update(last=last,host_seconds=time.monotonic()-started)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
    return 0 if result['status']=='PASS_COLD_READY_MEDIA_AND_ALL_PIXELS' else 1


if __name__=='__main__':
    raise SystemExit(main())
