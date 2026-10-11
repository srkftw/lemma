#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independent observations of RTL transport and existing Lean notebook records.

This code only reads evidence. It never supplies records, recovery results,
pixels or MMIO responses to the running system.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from check_notebook_workflow import (check_toolbar_pixels, committed_bytes,
                                     guest_events, join_chunks)
from notebook_input import Input
from store_oracle import recover,root_slot

MAGIC = 0x314B4E49414D454C

def completed_capture(capture: Path) -> dict:
    result=json.loads((capture/'output.json').read_text())
    if result.get('status')!='STOPPED_BY_PROTOCOL' or result.get('exit_code')!=0:
        raise ValueError('capture did not complete its declared observation protocol')
    outputs=result.get('outputs')
    if not isinstance(outputs,dict) or not {'uart.bin','host-report.json','panel','panel.events'}<=outputs.keys():
        raise ValueError('capture has no actual output inventory')
    for name,digest in outputs.items():
        path=capture/name
        if path.resolve().parent!=capture.resolve() or not isinstance(digest,str) or \
           hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('capture output identity differs')
    stats=json.loads((capture/'host-report.json').read_text())
    if not isinstance(stats,dict):raise ValueError('malformed hardware observations')
    for name in ('pen_ingress','flushes','media_requests','panel_completed','volatile_sectors_discarded'):
        if type(stats.get(name)) is not int or stats[name]<0:
            raise ValueError('missing or malformed hardware count '+name)
    cycles=stats.get('privilege_cycles')
    if not isinstance(cycles,list) or len(cycles)!=4 or any(type(n) is not int or n<0 for n in cycles):
        raise ValueError('malformed actual privilege observations')
    return stats

def reset_identity(capture: Path, workload: str, retained: Path | None=None) -> dict:
    identity=json.loads((capture/'input.json').read_text())
    initial=identity.get('initial_medium')
    if identity.get('transport')!='lemma-silicon-events/1' or identity.get('profile')!='lemma-silicon-dev/0.1.0' or \
       identity.get('workload')!=workload or identity.get('reset_cycles')!=8 or identity.get('clock_hz')!=100000000 or \
       identity.get('ram_initialization')!='zero external RAM plus exact ELF and DTB loads' or identity.get('inputs')!={} or \
       not isinstance(initial,dict) or not isinstance(initial.get('path'),str) or \
       hashlib.sha256(Path(initial['path']).read_bytes()).hexdigest()!=initial.get('sha256') or \
       (retained is not None and initial['sha256']!=hashlib.sha256(retained.read_bytes()).hexdigest()):
        raise ValueError('execution omitted retained-medium-only architectural reset identity')
    return identity

def validate_fixture(manifest: dict, events: Path) -> list:
    if not isinstance(manifest,dict) or any(manifest.get(k)!=v for k,v in {
        'schema':'lemma-silicon-notebook-input/1','profile':'lemma-silicon-dev/0.1.0',
        'geometry':[512,640],'pressure_maximum':4095,'clock_hz':100000000,
        'timebase_hz':10000000}.items()):
        raise ValueError('missing or changed external fixture binding')
    samples=manifest.get('raw_samples')
    if not isinstance(samples,list) or len(samples)!=13 or any(
        not isinstance(row,(list,tuple)) or len(row)!=9 or any(type(n) is not int or n<0 for n in row)
        or row[0]!=index+1 or row[8]!=1 for index,row in enumerate(samples)):
        raise ValueError('malformed raw sample identity')
    encoded=''.join(f'{row[1]*10} pen '+ ' '.join(map(str,row[1:8]))+'\n' for row in samples).encode()
    if events.read_bytes()!=encoded or hashlib.sha256(encoded).hexdigest()!=manifest.get('event_sha256'):
        raise ValueError('external samples do not encode captured ingress')
    actions=manifest.get('actions')
    if not isinstance(actions,list) or len(actions)!=4 or \
       [row.get('kind') for row in actions]!=['stroke','tool','tool','tool'] or \
       [row.get('button') for row in actions[1:]]!=[3,4,7]:
        raise ValueError('fixture lacks stroke/undo/redo/save operations')
    return samples

def fixture(directory: Path, first_cycle: int, gap_cycles: int) -> dict:
    """One pressure-varying stroke, undo, redo, explicit Save; raw ports only."""
    if first_cycle < 10 or gap_cycles < 10:
        raise ValueError('positive bounded cycle schedule required')
    stream = Input(512, 640, first_cycle // 10, 50000, gap_cycles // 10)
    stream.sample(256, 160, 0, False)
    stream.stroke('rtl-short', 1, 1, 6, 230)
    stream.tool(3, 'undo')
    stream.tool(4, 'redo')
    stream.tool(7, 'save')
    events = directory / 'events.txt'
    events.write_text(''.join(f'{row[1]*10} pen '+ ' '.join(map(str,row[1:8]))+'\n'
                              for row in stream.events))
    data = {'schema':'lemma-silicon-notebook-input/1', 'profile':'lemma-silicon-dev/0.1.0',
            'geometry':[512,640], 'pressure_maximum':4095, 'actions':stream.actions,
            'raw_samples':stream.events, 'event_sha256':hashlib.sha256(events.read_bytes()).hexdigest(),
            'physical_input':'SYNTHETIC_RECORDED', 'clock_hz':100000000,
            'timebase_hz':10000000}
    (directory/'fixture.json').write_text(json.dumps(data,indent=2)+'\n')
    return data

def pgm(path: Path):
    data = path.read_bytes()
    header = re.match(rb'P5\s+(\d+)\s+(\d+)\s+255\s',data)
    if not header:
        raise ValueError('missing actual RTL panel PGM')
    width,height = map(int,header.groups());pixels=data[header.end():]
    if (width,height)!=(512,640) or len(pixels)!=width*height:
        raise ValueError('panel output geometry/length differs')
    return width,height,pixels

def panel_point_history(path: Path, x: int, y: int):
    """Observe a literal point across actual accepted controller completions."""
    last_cycle=-1;completed=[];visible=15;pending=None;sequence=None
    with path.open() as stream:
        if stream.readline().strip()!='cycle,event,sequence,x,y,gray':
            raise ValueError('invalid RTL controller observation header')
        for line in stream:
            words=line.strip().split(',')
            if len(words)!=6:
                raise ValueError('truncated RTL controller observation')
            cycle,event,seq,px,py,gray=words
            cycle,seq,px,py,gray=map(int,(cycle,seq,px,py,gray))
            if cycle<last_cycle or seq<=0:
                raise ValueError('backward controller time or invalid sequence')
            last_cycle=cycle
            if event=='pixel':
                if not 0<=px<512 or not 0<=py<640 or not 0<=gray<16:
                    raise ValueError('controller output outside implemented bounds')
                if sequence is not None and seq!=sequence:
                    raise ValueError('accepted update changed before completion')
                sequence=seq
                if (px,py)==(x,y):pending=gray
            elif event=='complete':
                if sequence!=seq or (completed and seq<=completed[-1][1]):
                    raise ValueError('missing pixels or unordered completion')
                if pending is not None:visible=pending
                completed.append((cycle,seq,visible));pending=None;sequence=None
            elif event=='abort':
                if sequence is not None and sequence!=seq:
                    raise ValueError('abort identity differs from accepted update')
                pending=None;sequence=None
            else:raise ValueError('unknown controller observation')
    if not completed:
        raise ValueError('no actual controller completion')
    if sequence is not None:
        raise ValueError('controller capture ends with an incomplete accepted update')
    return completed

def short_session(disk: Path, capture: Path, fixture_file: Path) -> dict:
    stats=completed_capture(capture)
    manifest=json.loads(fixture_file.read_text());samples=validate_fixture(manifest,capture/'input.events')
    stroke=manifest['actions'][0]
    expected=[tuple(row) for row in samples[stroke['first_sequence']-1:stroke['last_sequence']]]
    if len(expected)!=6 or len({row[4] for row in expected[:-1]})<3:
        raise ValueError('missing independent pressure-varying stroke fixture')
    root,sequence,records=recover(disk.read_bytes());chunks=[];page=None
    for (namespace,object_id),record in records.items():
        data=record.payload
        if namespace!=1 or record.kind==2 or len(data)<64:continue
        header=struct.unpack_from('<8Q',data)
        if header[0]!=MAGIC:raise ValueError('unknown document codec')
        if header[2]==3:
            words=struct.unpack_from('<16Q',data)
            if len(data)!=128+words[6]*72 or words[9:14]!=(65535,65535,4095,512,640):
                raise ValueError('raw chunk length/calibration differs')
            current=[struct.unpack_from('<9Q',data,128+i*72) for i in range(words[6])]
            chunks.append((words,current))
        elif header[2]==2 and object_id==257:page=data
    chunks.sort(key=lambda item:item[1][0][0]);raw=join_chunks(chunks)
    if raw!=expected:
        raise ValueError('guest retained raw samples differ from external stroke')
    if page is None:raise ValueError('missing committed page index')
    words=struct.unpack_from('<16Q',page)
    if words[1:7]!=(2,2,1,1,1,1) or len(page)!=168:
        raise ValueError('final edit history/cursor does not contain one visible stroke')
    events_uart=guest_events(capture/'uart.bin')
    states=[row for row in events_uart if row[0] in (0x421,0x423,0x424)]
    saved=[row for row in states if row[0]==0x421]
    if not any(row[0]==0x420 for row in events_uart) or len(saved)<3 or \
       not states or states[-1][0]!=0x421 or saved[-1][1]!=sequence:
        raise ValueError('missing final guest durability acknowledgement after edits')
    width,height,pixels=pgm(capture/'panel')
    rgb=bytes(value for pixel in pixels for value in (pixel,pixel,pixel))
    check_toolbar_pixels(width,height,rgb)
    x,y=expected[0][2]*511//65535,expected[0][3]*639//65535
    history=panel_point_history(capture/'panel.events',x,y)
    # The controller must visibly apply the stroke, undo it, then restore it.
    phases=[]
    for _,_,gray in history:
        phase='ink' if gray<8 else 'white'
        if not phases or phase!=phases[-1]:phases.append(phase)
    if ['ink','white','ink'] not in [phases[i:i+3] for i in range(len(phases)-2)] or pixels[y*width+x]>=128:
        raise ValueError('actual controller output did not show stroke/undo/redo')
    if stats['pen_ingress']!=len(samples) or stats['flushes']<3 or \
       stats['privilege_cycles'][0]<=0 or stats['privilege_cycles'][1]<=0:
        raise ValueError('raw ingress, medium FLUSH or genuine S/U execution absent')
    return {'status':'PASS','store_generation':root.generation,'committed_sequence':sequence,
            'retained_raw_samples':len(raw),'saved_observations':saved,
            'controller_point_history':history,'controller_phases':phases,
            'scope':'observed existing Lean notebook stroke/undo/redo/save through RTL; cold reopen separate'}

def cold(before_disk: Path, after_disk: Path, before: Path, after: Path) -> dict:
    if before.resolve()==after.resolve():raise ValueError('cold reopen requires a distinct execution capture')
    completed_capture(before);stats=completed_capture(after)
    reset_identity(after,'notebook',before_disk)
    if committed_bytes(before_disk)!=committed_bytes(after_disk):
        raise ValueError('cold boot changed/lost exact acknowledged records')
    if pgm(before/'panel')!=pgm(after/'panel'):
        raise ValueError('cold guest redraw differs from acknowledged controller output')
    observations=guest_events(after/'uart.bin')
    if not any(row[0]==0x420 for row in observations):raise ValueError('cold page ready missing')
    if not stats['media_requests'] or not stats['panel_completed'] or not stats['privilege_cycles'][0]:
        raise ValueError('cold run omitted actual device/media/User execution')
    return {'status':'PASS','exact_committed_payloads':True,'exact_controller_pixels':True,
            'scope':'new CPU reset process, retained medium only, genuine guest recovery/redraw'}

def failed_flush(before_disk: Path, failed_disk: Path, capture: Path) -> dict:
    stats=completed_capture(capture)
    if committed_bytes(before_disk)!=committed_bytes(failed_disk):
        raise ValueError('failed flush altered acknowledged committed payloads')
    rows=guest_events(capture/'uart.bin');states=[row for row in rows if row[0] in (0x421,0x423,0x424)]
    if not states or states[-1][0]!=0x424 or not any(row[0]==0x423 for row in states):
        raise ValueError('failed flush became Saved or lacked guest Pending/Failed observations')
    if not stats['flushes'] or not stats['volatile_sectors_discarded']:
        raise ValueError('failed external barrier/volatile write loss not observed')
    return {'status':'PASS','acknowledged_records_retained':True,'failed_work_not_saved':True,
            'scope':'one failed medium FLUSH; volatile writes discarded at process power-off'}

def initialized(disk: Path, capture: Path) -> dict:
    stats=completed_capture(capture)
    identity=reset_identity(capture,'initializer')
    initial=Path(identity['initial_medium']['path'])
    with initial.open('rb') as source:
        while data:=source.read(1024*1024):
            if any(data):raise ValueError('format input medium was not empty external bytes')
    image=disk.read_bytes();root,sequence,records=recover(image)
    roots=[root_slot(image[n*512:(n+1)*512],len(image)//512) for n in range(2)]
    if roots!=[root,root] or (root.generation,root.segment,root.checkpoint_count,root.checkpoint_tail,root.sequence)!=(1,0,0,0,0) or sequence!=0 or records or \
       (0x41f,0,0,0,0) not in guest_events(capture/'uart.bin') or \
       stats['flushes']!=3 or not stats['media_requests'] or not stats['privilege_cycles'][0]:
        raise ValueError('actual Lean format/root/FLUSH acknowledgement absent')
    return {'status':'PASS','generation':root.generation,'committed_sequence':sequence,
            'scope':'existing Lean initializer formatted an empty medium through RTL block DMA and external FLUSH'}
