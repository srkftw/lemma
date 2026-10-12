# SPDX-License-Identifier: Apache-2.0
"""Offline acceptance of the quarantined Lean device probe on actual RTL.

Literal expectations describe the versioned external fixture, not a simulator
implementation. No instructions, MMIO replies, journal data or pixels are made.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'conformance/silicon'))
from notebook_observations import completed_capture,guest_events

PAPER=(0x40e,1,171,4,6)
PEN=(0x40f,1,2,2,3)
POSITIVE=((0x402,257,20000,22000,0),(0x402,258,21000,23000,0))

def raw_events() -> bytes:
    # 256 FIFO entries, one overflow, 43 dropped contacts in the loss epoch.
    # A later release permits resynchronization; the new contact and release
    # receive the next two sequence numbers without reusing discarded identity.
    text=''.join(f'{1000+n*10} pen {100+n} 10000 12000 1000 3 1 0\n' for n in range(300))
    text+='60000000 pen 6000000 20000 22000 0 2 1 0\n'
    text+='60500000 pen 6050000 20000 22000 1800 3 1 0\n'
    text+='61000000 pen 6100000 21000 23000 0 2 1 0\n'
    return text.encode()

def fixture(directory: Path) -> dict:
    raw=raw_events();(directory/'events.txt').write_bytes(raw)
    report={'schema':'lemma-silicon-device-input/1','profile':'lemma-silicon-dev/0.1.0',
            'sample_count':303,'events_sha256':hashlib.sha256(raw).hexdigest(),
            'physical_input':'SYNTHETIC_RECORDED','clock_hz':100000000,'timebase_hz':10000000,
            'scope':'raw overflow/resynchronization fixture; expectations are not execution results'}
    (directory/'fixture.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

def identified(item: dict) -> Path:
    if not isinstance(item,dict) or set(item)!={'path','sha256'} or not isinstance(item['path'],str):
        raise ValueError('missing captured artifact identity')
    path=Path(item['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
        raise ValueError('captured artifact identity differs')
    return path

def binding(capture: Path) -> dict:
    identity=json.loads((capture/'input.json').read_text())
    if any(identity.get(key)!=value for key,value in {
        'schema_version':1,'transport':'lemma-silicon-events/1','profile':'lemma-silicon-dev/0.1.0',
        'workload':'devices','reset_cycles':8,'clock_hz':100000000,
        'ram_initialization':'zero external RAM plus exact ELF and DTB loads'}.items()):
        raise ValueError('capture lacks the actual silicon device reset binding')
    inputs=identity.get('inputs')
    if not isinstance(inputs,dict) or set(inputs)!={'events'} or \
       identified(inputs['events']).resolve()!=(capture/'input.events').resolve() or \
       (capture/'input.events').read_bytes()!=raw_events():
        raise ValueError('capture does not contain the exact 303 raw external events')
    # A compiled-but-rejected image cannot supply a device acceptance result.
    prepared=identity.get('prepared',{})
    if not isinstance(prepared,dict) or prepared.get('profile')!='lemma-silicon-dev/0.1.0':
        raise ValueError('captured prepared binding differs')
    workloads=prepared.get('workloads',{})
    if not isinstance(workloads,dict) or not isinstance(workloads.get('devices'),dict):
        raise ValueError('missing captured device workload')
    entry=workloads['devices']
    image=identified(entry.get('image'));audit=json.loads(identified(entry.get('audit')).read_text())
    if (audit.get('status'),audit.get('configuration'),audit.get('stage'),audit.get('image_sha256'))!= \
       ('PASS','lemmasim-silicon-devices','supervisor',hashlib.sha256(image.read_bytes()).hexdigest()):
        raise ValueError('captured device image lacks its matching strict PASS audit')
    for key in ('binary','rom','rom_audit','rtl_build'):
        identified(prepared.get(key))
    identified(identity.get('initial_medium'))
    return identity

def observe(capture: Path) -> dict:
    stats=completed_capture(capture);binding(capture)
    rows=guest_events(capture/'uart.bin')
    if [row for row in rows if row[0]==0x40e]!=[PAPER] or \
       [row for row in rows if row[0]==0x40f]!=[PEN] or rows.index(PAPER)>=rows.index(PEN):
        raise ValueError('literal guest paper/pen negative probe observations absent or duplicated')
    start=[row for row in rows if row[0]==0x400]
    done=[row for row in rows if row[0]==0x404]
    if len(start)!=1 or start[0][2:]!=(1024,4,0) or start[0][1]==0 or \
       len(done)!=1 or done[0][2:]!=(4,1024,0) or not 0<done[0][1]<1024:
        raise ValueError('actual isolated device task or configured capacity observation absent')
    if not rows.index(PEN)<rows.index(start[0])<rows.index(done[0]):
        raise ValueError('device probe/task/block completion ordering differs')
    blocks=[row for row in rows if row[0]==0x401]
    if blocks!=[(0x401,1,0,0,0),(0x401,5,0,0,0)]:
        raise ValueError('actual guest block read/FLUSH completion sequence absent')
    if not rows.index(start[0])<rows.index(blocks[0])<rows.index(blocks[1])<rows.index(done[0]):
        raise ValueError('guest block completion ordering differs')
    positive=[row for row in rows if row[0]==0x402]
    if positive!=list(POSITIVE) or rows.index(POSITIVE[0])<=rows.index(PEN):
        raise ValueError('post-loss raw sequence/position observations differ')
    irqs=[row for row in rows if row[0]==0x406]
    if not {1,13}<={row[1] for row in irqs} or any(
        row[1] not in (1,12,13) or row[2]!=0x8000000000000009 or row[3]!=start[0][1] or
        not 0x1000000<=row[4]<0x1080000 or row[4]%4 for row in irqs):
        raise ValueError('actual block/pen SEIP with isolated User PC absent or malformed')
    for key in ('pen_accepted','panel_aborted','timer_traps','traps'):
        if type(stats.get(key)) is not int or stats[key]<0:
            raise ValueError('missing or malformed hardware count '+key)
    if stats.get('finished') is not False or stats.get('explicit_observer_stop') is not True or \
       stats['pen_ingress']!=303 or stats['pen_accepted']!=258 or stats['flushes']!=1 or \
       stats['media_requests']<2 or stats['panel_completed']!=0 or stats['panel_aborted']<1 or \
       any(stats['privilege_cycles'][privilege]<=0 for privilege in (0,1,3)) or \
       stats['timer_traps']<1 or stats['traps']<stats['timer_traps']+2:
        raise ValueError('actual ingress, abort, DMA/FLUSH or M/S/U hardware observations absent')
    # The reset must cancel the actual accepted sequence without an optical
    # completion. This is independent of the guest's status-register report.
    panel=(capture/'panel.events').read_text().splitlines()
    if len(panel)!=2 or panel[0]!='cycle,event,sequence,x,y,gray':
        raise ValueError('missing or extra controller interrupted-update events')
    fields=panel[1].split(',')
    if len(fields)!=6 or not fields[0].isdigit() or int(fields[0])<=0 or \
       fields[1:]!=['abort','1','0','0','0'] or stats['panel_aborted']!=1:
        raise ValueError('controller did not abort the accepted sequence1 exactly once')
    return {'status':'PASS','paper_probe':PAPER,'pen_probe':PEN,'raw_events':303,
            'positive_pen_observations':positive,'block_completions':blocks,
            'supervisor_external_interrupts':irqs,'hardware':stats,
            'scope':'quarantined compiled Lean device probe, actual isolated task, pen loss/resync and block DMA/FLUSH on RTL; not notebook durability'}
