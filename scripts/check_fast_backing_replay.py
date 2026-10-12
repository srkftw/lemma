#!/usr/bin/env python3
"""Real notebook I/O suffix against a private LMIOLOG2 consumer.

Predeclared observation relation: exact submitted/accepted I/O bytes/times,
raw inputs, guest UART suffix, acknowledged objects and full controller pixels.
This does not assert QEMU cached-state or complete migration-state equivalence.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import time

from check_companion_pending import timed_records
from check_live_notebook import (Checker, Input, ROOT, committed_bytes, generate,
                                observe_workflow, require, sha, visible_pixels)
from lemmasim_fast import copy_new


def captured_entries(path, first_id):
    """Independent wire extraction, after complete CRC/identity validation."""
    import struct
    rows, pending = timed_records(path)
    require(pending is None, 'replay corpus contains unresolved external work')
    raw=Path(path).read_bytes();position=72;output=raw[:72];ids=[]
    while position<len(raw):
        tag,n=struct.unpack_from('<2Q',raw,position)
        operation=struct.unpack_from('<Q',raw,position+16)[0]
        if operation>=first_id:
            output+=raw[position:position+16+n]
            if tag==1:ids.append(operation)
        position+=16+n
    require(ids and ids==list(range(first_id,ids[-1]+1)), 'nonempty contiguous captured suffix required')
    return output,[row for row in rows if row[0][0]>=first_id]


def qemu_memory(owner_pid):
    """Read actual Linux process counters, independently of machine state."""
    pending=[owner_pid]
    while pending:
        pid=pending.pop();base=Path('/proc')/str(pid)
        try:
            executable=os.readlink(base/'exe')
            if Path(executable).name in ('qemu-system-riscv64','.qemu-system-riscv64-wrapped'):
                fields={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in (base/'status').read_text().splitlines() if ':' in line}
                return {'pid':pid,'rss_kib':int(fields['VmRSS'].split()[0]),'peak_rss_kib':int(fields['VmHWM'].split()[0])}
            pending += [int(value) for value in (base/'task'/str(pid)/'children').read_text().split()]
        except (FileNotFoundError,ProcessLookupError):continue
    raise ValueError('actual QEMU process resource observer found no owned machine')


class ReplayChecker(Checker):
    profile='lemma-silicon-dev/0.3.0'
    def __init__(self,args):
        super().__init__(args)
        self.report.update(schema='lemmasim-fast-backing-replay-observations/1',
            scope=__doc__, checkpoint_relation='exact admitted backing I/O and user outputs only; QEMU cached-state hole remains open')
        self.report['observer_sources'][str(Path(__file__).relative_to(ROOT))]=sha(__file__)
        self.replay_arguments=None

    def launch(self,args,**kwargs):
        args=list(args)
        if self.replay_arguments is not None and args and args[0]=='session':
            at=args.index('--disk');del args[at:at+2]
            args+=['--restore',str(self.replay_arguments[0]),'--backing-replay',str(self.replay_arguments[1])]
        return super().launch(args,**kwargs)

    def execute(self):
        self.report['source_medium']={'path':str(self.args.disk.resolve()),'sha256':sha(self.args.disk)}
        disk=self.directory/'private-live.raw'
        copy_new(self.args.disk,disk)
        live=self.session('live',disk);self.report['identity']=live.identity;self.report['boot']=live.boot()
        _,fixture=generate('basic',1650,2200,0,100000,0)
        stream=Input(1650,2200,live.inspect()['machine']['ticks']+10000,100000,0)
        stream.sample(825,160,0,False);live.admit(stream.events);live.settle(stream.events[-1][1])
        source_uart=live.directory/'uart-0.bin';source_raw=live.directory/'input-0.bin'
        uart_start=source_uart.stat().st_size;raw_start=source_raw.stat().st_size
        before=live.inspect()['machine'];first_id=before['storage']['backing_next_id']
        snapshot=live.snapshot('before-ink')
        require(live.inspect()['machine']==before, 'observational snapshot changed exposed machine state')
        for action in fixture['actions']:
            start=len(stream.events);stream.tick=live.inspect()['machine']['ticks']+10000
            if action['kind']=='stroke':stream.stroke(action['name'],1,1,action['raw_samples'],2200//3 if action['name']=='a' else 1100)
            else:stream.tool(action['button'],action['name'])
            live.admit(stream.events[start:]);live.settle(stream.events[-1][1])
        panel,medium=live.export('live-final');endpoint=live.inspect()['machine']['virtual_ns']
        self.report['live_resources']=qemu_memory(live.process.pid)
        self.report['workflow']=observe_workflow(medium,source_raw,source_uart,panel,stream,fixture['expected'])
        external=self.directory/'closed-external.jsonl';shutil.copyfile(live.directory/'external.jsonl',external)
        captured=self.directory/'selected.io';wire,rows=captured_entries(live.directory/'backing-0.io',first_id);captured.write_bytes(wire)
        expected_uart=source_uart.read_bytes()[uart_start:];expected_raw=source_raw.read_bytes()[raw_start:]
        self.report['suffix']={'first_id':first_id,'outcomes':len(rows),'start_ns':before['virtual_ns'],'end_ns':endpoint,
                               'log_sha256':sha(captured),'external_sha256':sha(external)}
        live.close();self.sessions.remove(live)
        # Remove the only mutable live medium. The original input is never
        # passed to the replay process; the checkpoint contains private bytes.
        disk.unlink();self.replay_arguments=(snapshot,captured)
        replay=self.session('replay',snapshot/'durable.raw')
        started=time.monotonic()
        replay.control({'action':'replay','snapshot':str(snapshot),'capture':str(external),'until_ns':endpoint})
        replay_panel,replay_medium=replay.export('replay-final')
        directories=sorted(replay.directory.glob('machine-fork-*'))
        require(directories,'missing private replay fork');active=directories[-1]
        actual_capture=next(active.glob('backing-*.io'));actual_wire,actual_rows=captured_entries(actual_capture,first_id)
        require(actual_wire==wire and actual_rows==rows,'recorded request/outcome bytes or accepted boundaries differ')
        require(next(active.glob('input-*.bin')).read_bytes()==expected_raw,'actual raw replay suffix differs')
        require(next(active.glob('uart-*.bin')).read_bytes()==expected_uart,'actual guest UART suffix differs')
        require(committed_bytes(replay_medium)==committed_bytes(medium),'acknowledged exact object bytes differ')
        require(visible_pixels(replay_panel)==visible_pixels(panel),'complete controller pixels differ')
        self.report['replay_resources']=qemu_memory(replay.process.pid)
        self.report['replay']={'status':'PASS','host_seconds':time.monotonic()-started,'accepted_io_exact':True,
                               'guest_uart_suffix_exact':True,'raw_ingress_suffix_exact':True,
                               'acknowledged_objects_exact':True,'controller_pixels_exact':True,
                               'source_mutable_medium_removed':True,'private_fork':str(active),
                               'capture_sha256':sha(actual_capture)}
        replay.close();self.sessions.remove(replay);self.report['status']='PASS'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disk',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=120);p.add_argument('--boot-seconds',type=int,default=40)
    p.add_argument('--action-seconds',type=int,default=20);p.add_argument('--deadline',type=int,default=600)
    args=p.parse_args();args.durable_suffix_from=None;args.checkpoint_relation='not-complete-cached-state-equivalence';checker=ReplayChecker(args)
    try:checker.execute()
    except BaseException as error:checker.report['error']=str(error);raise
    finally:
        for session in reversed(checker.sessions):session.close()
        checker.commands.close();checker.report['host_seconds']=time.monotonic()-checker.started
        checker.report['allocated_artifact_bytes']=sum(path.stat().st_blocks*512 for path in checker.directory.rglob('*') if path.is_file())
        (checker.directory/'result.json').write_text(json.dumps(checker.report,indent=2,default=str)+'\n')
    print(json.dumps(checker.report,indent=2,default=str))


if __name__=='__main__':main()
