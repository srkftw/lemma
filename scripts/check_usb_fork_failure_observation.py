#!/usr/bin/env python3
"""Observe retained Wire11 unsuccessful autosave and blocked toolbar bytes.

This executes no CPU or peer and does not change the original terminal FAIL.
It qualifies only the actual failed raw-chunk Save, complete FAILED scene and
absence of a new explicit retry, explained by the exact archived guest policy.
"""
import argparse
import json
from pathlib import Path
import struct

from check_guest_usb_link import ROOT, require, sha, guest_events
from check_guest_usb_notebook import materialize_observation, expected_stroke, empty_pixels
from check_notebook_workflow import visible_pixels
from silicon_guest_bundle import prepared
from store_oracle import recover
from usb_fork_fault import validate, file_record, private_files, PROFILE, chain


def failed_rows(rows):
    require(rows == [(0x423, 12, 1, 1, 65548), (0x424, 227, 1, 1, 65548)],
            'retained unsuccessful autosave has unexpected Pending/Failed/Saved or explicit effects')


def expected_failed_scene(raw, pen):
    _,sequence,objects=recover(raw)
    require(sequence == 11 and {key:value.sequence for key,value in objects.items()} ==
            {(1,1):11,(1,257):8,(1,258):10,(1,65539):3},'acknowledged journal object identity changed')
    original=objects[(1,65539)].payload
    require(len(original)==344,'old raw chunk shape')
    samples=[struct.unpack_from('<9Q',original,128+72*i) for i in range(3)]
    _,old=expected_stroke(samples)
    require(len(pen)==6 and all(len(row)==9 for row in pen) and
            [row[6]&1 for row in pen]==[0,1,1,0,1,0], 'retained raw contact/release order changed')
    # Native raw capture has eight fields: cycle, pen, tick,x,y,p,f,e,aux.
    raw_samples=[(i+1,*row[2:],1) for i,row in enumerate(pen)]
    _,new=expected_stroke(raw_samples[1:4])
    require(pen[4][3:6]==[54527,1908,2048] and pen[5][3:6]==[54527,1908,0],
            'later actual toolbar input is not Save down/up')
    expected=bytearray(empty_pixels(1650,2200,status='FAILED'))
    for x,y in old+new:expected[(y*1650+x)*3:(y*1650+x)*3+3]=bytes(3)
    return bytes(expected),old,new


def observe(args):
    out=args.work_dir.resolve();require(not out.exists() and out.is_relative_to(ROOT/'build'),'unused retained observation output')
    out.mkdir(parents=True);report={'schema':'lemma-wire-unsuccessful-save-observation/1','status':'FAIL',
        'scope':__doc__,'cpu_cycles_executed':0,'peer_processes_started':0,'new_explicit_store_attempt':False}
    try:
        source=args.workflow.resolve(); result=json.loads((source/'result.json').read_text())
        supervision=json.loads(source.with_name(source.name+'.supervision').joinpath('supervision.json').read_text())
        require(result['status']=='FAIL' and result['owned_children_reaped'] is True and
                supervision['status']=='FAIL' and supervision['cause']=='explicit cancellation' and
                supervision['owned_survivors']==[], 'original failed fixture is not retained and cleaned up')
        state=result['initial_machine'];identity=result['identity']
        fault_path=Path(result['fault']['path']);require(sha(fault_path)==result['fault']['sha256'],'fault admission input changed')
        fault,bridge=validate(fault_path,Path(result['parent_snapshot']['path']).parent,state,identity)
        require(result['parent_snapshot']==file_record(Path(fault['parent_snapshot']['path'])/'snapshot.json'),
                'retained parent metadata differs')
        parent=Path(fault['parent_snapshot']['path'])
        admitted=source/'admitted-before-edge/machine.chk'
        require(sha(admitted)==sha(parent/'machine.chk'),'before-edge admission changed authoritative checkpoint')
        detached=result['actual_detach']; require(detached['cycle']==state['cycle']+1 and
            detached['usb']['connected']==detached['usb']['configured']==0 and detached['usb']['terminal']==1 and
            detached['usb']['pending_command']==0 and detached['usb']['accepted_rows']==state['usb']['accepted_rows']+1 and
            detached['usb']['accepted_hash']==chain(f"{state['cycle']} 2 {state['usb']['pending_command']} USB process disconnected read\n".encode(),state['usb']['accepted_hash']),
            'actual scheduled EOF did not produce precisely one controller detach')
        milestone=result['milestones']['fault-fork/disconnected-raw-ink'];last=result['failure_machine']
        require(milestone['cycle']==2810000001 and milestone['target_cycles']==40000000 and
                milestone['host_seconds']<=7200 and last['cycle']==2855000001 and
                last['panel_completed']==milestone['machine']['panel_completed']==14 and
                last['paper_busy']==last['event_queue']==last['pen_queue']==last['panel_pending_pixels']==0,
                'retained failed-scene/completion boundary changed')
        rows=guest_events(source/'fault-fork/uart.bin');failed_rows(rows)
        external=[json.loads(line) for line in (source/'fault-fork/external.jsonl').read_text().splitlines()]
        require(len(external)==7 and all(row['admission']=='applied' and row['ordinal']==i and
            row['cursor']==14+i for i,row in enumerate(external)) and
            external[0]['request']=={'action':'usb-fault','path':str(fault_path)}, 'actual external admission cursor differs')
        pen=[]
        for line in (source/'fault-fork/input.events').read_text().splitlines():
            fields=line.split();require(len(fields)==9 and fields[1]=='pen','actual raw pen text shape')
            pen.append([int(fields[0]),'pen',*[int(value) for value in fields[2:]]])
        require([row['request']['words'] for row in external[1:]]==[row[2:] for row in pen] and
            [row['request']['cycle'] for row in external[1:]]==[row[0] for row in pen] and
            all(row['cycle']==state['cycle']+1 for row in external[1:5]) and
            all(row['cycle']==milestone['cycle'] for row in external[5:]), 'actual raw ink/toolbar admission bytes differ')
        bd=Path(fault['acknowledged_boundary']['path']).parent
        expected,old,new=expected_failed_scene((bd/'acknowledged.raw').read_bytes(),pen)
        width,height,actual=visible_pixels(source/'fault-fork/observed.ppm')
        require((width,height)==(1650,2200) and actual==expected,'complete FAILED controller pixels differ')
        private=Path(fault['private_directory']);capture=json.loads(Path(fault['capture']['path']).read_text())
        after=private_files(private);require(after==capture['before']==capture['after']==fault['private_files'],
                'observed private medium/receipt/outbox bytes changed')
        raw=out/'after-failed-autosave.raw';materialize_observation(private/'peer',raw)
        require(sha(raw)==sha(bd/'acknowledged.raw'),'actual observed durable bytes differ; no rollback assumed')
        bundle=Path(fault['native_bundle']['path']).parent;prepared(bundle,'rtl','usb-wire-bulk-notebook',PROFILE)
        policy=bundle/'source/Lemma/Applications/Notebook.lean';text=policy.read_text()
        # These exact qualified source clauses explain the retained observer
        # mistake; they do not replace the actual UART/pixel/input observation.
        require('.bind (reportCommitState 0x424 status.toUInt64 object)' in text and
            text.count('if 2 ≤ status then .done 0 0 else')==2 and
            'private def toolbar (button : UInt64)' in text and
            'private def inputSample : Action' in text, 'archived Failed/status/toolbar policy differs')
        report.update(status='PASS_OBSERVED_UNSUCCESSFUL_AUTOSAVE_AND_BLOCKED_TOOLBAR',
            original_failure={'path':str(source/'result.json'),'sha256':sha(source/'result.json'),'status':'FAIL'},
            original_supervision=file_record(source.with_name(source.name+'.supervision')/'supervision.json'),
            identity=identity,fault=file_record(fault_path),actual_raw_chunk_save=rows,
            unsuccessful_autosave=milestone,actual_toolbar_admitted_but_blocked=True,
            all_3630000_failed_pixels_equal=True,new_saved_records=0,observed_durable_bytes=file_record(raw),
            private_receipt_bytes_equal=True,rollback_assumed=False,guest_policy=file_record(policy),
            source_explanation='Failed stores error status in field1; status>=2 rejects new contacts and toolbar before Store issue',
            input_files={str(path.resolve()):sha(path) for path in
                (source/'result.json',source/'failure-snapshot/snapshot.json',source/'failure-snapshot/machine.chk',
                 source/'fault-fork/uart.bin',source/'fault-fork/input.events',source/'fault-fork/external.jsonl',
                 source/'fault-fork/observed.ppm',bridge)},old_black_pixels=old,new_black_pixels=new)
    except BaseException as error:report['error']=repr(error)
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return 0 if report['status'].startswith('PASS_') else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workflow','work-dir'):p.add_argument('--'+name,type=Path,required=True)
    return observe(p.parse_args())


if __name__=='__main__':raise SystemExit(main())
