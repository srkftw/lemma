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

def reset_identity(capture: Path, workload: str, retained: Path | None=None, events: Path | None=None) -> dict:
    identity=json.loads((capture/'input.json').read_text())
    initial=identity.get('initial_medium')
    inputs={} if events is None else {'events':{'path':str(events.resolve()),
                                               'sha256':hashlib.sha256(events.read_bytes()).hexdigest()}}
    if identity.get('transport')!='lemma-silicon-events/1' or identity.get('profile')!='lemma-silicon-dev/0.1.0' or \
       identity.get('workload')!=workload or identity.get('reset_cycles')!=8 or identity.get('clock_hz')!=100000000 or \
       identity.get('ram_initialization')!='zero external RAM plus exact ELF and DTB loads' or identity.get('inputs')!=inputs or \
       not isinstance(initial,dict) or not isinstance(initial.get('path'),str) or \
       hashlib.sha256(Path(initial['path']).read_bytes()).hexdigest()!=initial.get('sha256') or \
       (retained is not None and initial['sha256']!=hashlib.sha256(retained.read_bytes()).hexdigest()):
        raise ValueError('execution omitted retained-medium-only architectural reset identity')
    return identity

def session_spec(session: str):
    if session=='undo-redo':return 13,[3,4,7],512
    if session=='brush-width':return 11,[6,7],1024
    raise ValueError('unknown notebook observation session')

def validate_fixture(manifest: dict, events: Path, session: str='undo-redo') -> list:
    count,buttons,_=session_spec(session)
    if not isinstance(manifest,dict) or any(manifest.get(k)!=v for k,v in {
        'schema':'lemma-silicon-notebook-input/1','profile':'lemma-silicon-dev/0.1.0',
        'geometry':[512,640],'pressure_maximum':4095,'clock_hz':100000000,
        'timebase_hz':10000000}.items()):
        raise ValueError('missing or changed external fixture binding')
    if manifest.get('session','undo-redo')!=session:
        raise ValueError('fixture session differs from requested observation')
    samples=manifest.get('raw_samples')
    if not isinstance(samples,list) or len(samples)!=count or any(
        not isinstance(row,(list,tuple)) or len(row)!=9 or any(type(n) is not int or n<0 for n in row)
        or row[0]!=index+1 or row[8]!=1 for index,row in enumerate(samples)):
        raise ValueError('malformed raw sample identity')
    encoded=''.join(f'{row[1]*10} pen '+ ' '.join(map(str,row[1:8]))+'\n' for row in samples).encode()
    if events.read_bytes()!=encoded or hashlib.sha256(encoded).hexdigest()!=manifest.get('event_sha256'):
        raise ValueError('external samples do not encode captured ingress')
    actions=manifest.get('actions')
    if not isinstance(actions,list) or len(actions)!=len(buttons)+1 or \
       any(not isinstance(row,dict) for row in actions) or \
       [row.get('kind') for row in actions]!=['stroke']+['tool']*len(buttons) or \
       [row.get('button') for row in actions[1:]]!=buttons or \
       [row.get('first_sequence') for row in actions]!=[2]+list(range(8,count+1,2)) or \
       [row.get('last_sequence') for row in actions]!=[7]+list(range(9,count+1,2)) or \
       any(actions[0].get(k)!=v for k,v in {'namespace':1,'page':1,'raw_samples':6,'brush_q8':512}.items()):
        raise ValueError('fixture lacks exact stroke/edit/save operations')
    return samples

def fixture(directory: Path, first_cycle: int, gap_cycles: int, session: str='undo-redo') -> dict:
    """One pressure-varying stroke, declared edit and explicit Save; raw ports only."""
    _,buttons,_=session_spec(session)
    if first_cycle < 10 or gap_cycles < 10:
        raise ValueError('positive bounded cycle schedule required')
    stream = Input(512, 640, first_cycle // 10, 50000, gap_cycles // 10)
    stream.sample(256, 160, 0, False)
    stream.stroke('rtl-short', 1, 1, 6, 230)
    if buttons[0]==6:stream.tool(6,'select width4')
    else:
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
            'timebase_hz':10000000, 'session':session}
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

def document_payloads(records: dict, expected: list, session: str, sequence: int) -> dict:
    """Literal document-v1/page-v2 observations independent of the guest codecs."""
    _,_,brush=session_spec(session)
    document=records.get((1,1));page_record=records.get((1,257))
    if document is None or document.kind!=1 or document.payload!=struct.pack('<8Q',MAGIC,1,1,1,brush,0,0,0):
        raise ValueError('committed document root did not retain the declared brush edit')
    chunks=[]
    for (namespace,object_id),record in records.items():
        if namespace!=1 or object_id<=0x10000:continue
        data=record.payload
        if record.kind!=1 or len(data)!=128+6*72:
            raise ValueError('unexpected short-session chunk kind or length')
        words=struct.unpack_from('<16Q',data)
        if words[:4]!=(MAGIC,1,3,1) or words[4]<=0 or \
           words[5:]!=(0,6,512,1,65535,65535,4095,512,640,3,0):
            raise ValueError('short-session chunk identity, lifecycle or calibration differs')
        current=[struct.unpack_from('<9Q',data,128+i*72) for i in range(6)]
        chunks.append((record,words,current))
    if len(chunks)!=1 or join_chunks([(words,current) for _,words,current in chunks])!=expected:
        raise ValueError('guest retained raw samples differ from external stroke')
    chunk,words,_=chunks[0]
    if set(records)!={(1,1),(1,257),(1,chunk.object_id)}:
        raise ValueError('short session retained unexpected document objects')
    if page_record is None or page_record.kind!=1 or len(page_record.payload)!=168:
        raise ValueError('missing committed packed page index')
    page=page_record.payload
    if struct.unpack_from('<16Q',page)!=(MAGIC,2,2,1,1,1,1,0,0,0,0,0,0,0,0,0) or \
       struct.unpack_from('<3Q',page,128)!=(chunk.object_id,words[4],1) or \
       struct.unpack_from('<2Q',page,152)!=(1,words[4]):
        raise ValueError('page entry/edit did not retain the exact visible stroke identity')
    if not chunk.sequence<page_record.sequence<document.sequence==sequence:
        raise ValueError('committed chunk/page/root ordering differs')
    return {'brush_q8':brush,'stroke_id':words[4],'chunk_object':chunk.object_id}

def explicit_save(states: list, sequence: int) -> tuple:
    """Require the guest's final object-zero Pending -> Saved confirmation."""
    if not states or states[-1]!=(0x421,sequence,1,1,0):
        raise ValueError('missing final explicit Save confirmation')
    pending=None
    for row in states[:-1]:
        if row[0]==0x423 and row[2:]==(1,1,0):pending=row
        elif row[0]==0x424:pending=None
        elif row[0]==0x421 and row[4]==0:pending=None
    # Initial notebook creation can also report object zero. It does not
    # substitute for the final explicitly requested Inspect acknowledgement.
    final=states[-1]
    if pending is None or final[1]<pending[1]:
        raise ValueError('stale or regressed explicit Save confirmation')
    return final

def short_session(disk: Path, capture: Path, fixture_file: Path, session: str='undo-redo') -> dict:
    stats=completed_capture(capture)
    identity=reset_identity(capture,'notebook',events=capture/'input.events')
    initial,initial_sequence,initial_records=recover(Path(identity['initial_medium']['path']).read_bytes())
    if initial.generation!=1 or initial_sequence!=0 or initial_records:
        raise ValueError('short session did not start from the declared empty formatted medium')
    manifest=json.loads(fixture_file.read_text());samples=validate_fixture(manifest,capture/'input.events',session)
    stroke=manifest['actions'][0]
    expected=[tuple(row) for row in samples[stroke['first_sequence']-1:stroke['last_sequence']]]
    if len(expected)!=6 or len({row[4] for row in expected[:-1]})<3:
        raise ValueError('missing independent pressure-varying stroke fixture')
    root,sequence,records=recover(disk.read_bytes())
    document=document_payloads(records,expected,session,sequence)
    events_uart=guest_events(capture/'uart.bin')
    states=[row for row in events_uart if row[0] in (0x421,0x423,0x424)]
    saved=[row for row in states if row[0]==0x421]
    if not any(row[0]==0x420 for row in events_uart) or len(saved)<3 or \
       not states or states[-1][0]!=0x421 or saved[-1][1]!=sequence:
        raise ValueError('missing final guest durability acknowledgement after edits')
    confirmation=explicit_save(states,sequence)
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
    if pixels[y*width+x]>=128 or 'ink' not in phases:
        raise ValueError('actual completed controller output did not show the retained stroke')
    if session=='undo-redo' and ['ink','white','ink'] not in [phases[i:i+3] for i in range(len(phases)-2)]:
        raise ValueError('actual controller output did not show stroke/undo/redo')
    if stats['pen_ingress']!=len(samples) or stats['flushes']<3 or stats['panel_completed']<=0 or \
       stats['privilege_cycles'][0]<=0 or stats['privilege_cycles'][1]<=0:
        raise ValueError('raw ingress, medium FLUSH or genuine S/U execution absent')
    return {'status':'PASS','store_generation':root.generation,'committed_sequence':sequence,
            'session':session,**document,'retained_raw_samples':len(expected),'saved_observations':saved,
            'explicit_save_confirmation':confirmation,
            'controller_point_history':history,'controller_phases':phases,
            'scope':'observed existing Lean notebook stroke/'+session+'/save through RTL; cold reopen separate'}

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
