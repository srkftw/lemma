#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual bounded paired Lean power policy via public paused sessions.

Relation fixed before execution: raw levels/cycles and 442/443/440 fields exact;
441 cause/epoch/order exact and time lies within100000ticks of delivered wake.
Every UART byte and inspected CPU/time/device state is retained. This is a
partial power-path observation, not whole-machine or architectural equivalence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from lemmasim_session import request

PROFILE = 'lemma-silicon-dev/0.3.0'
EVENTS = [(20000000,1),(20020000,0),(20040000,1),(20060000,0)]
WAKE_TICK_BOUND = 100000


def require(value, message):
    if not value: raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1<<20),b''): h.update(data)
    return h.hexdigest()


def records(path):
    data=path.read_bytes()
    require(len(data)<=2<<20,'UART exceeded its bound')
    return [tuple(int(v,16) for v in row) for row in re.findall(
        rb'^K1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\r?$',data,re.M)]


def compare_results(paths):
    values=[json.loads(path.read_text()) for path in paths]
    require({v.get('backend') for v in values}=={'rtl','qemu'} and
            all(v.get('status')=='PASS' for v in values),'require two actual completed backend observations')
    left,right=values
    require(left['raw_events']==right['raw_events'],'paired admitted raw fields/timestamps differ')
    require(all(left['identity'][k]==right['identity'][k]
                for k in ('profile','guest','dtb','descriptor')),'paired compatible artifacts differ')
    require([r[0] for r in left['records']]==[0x442,0x443,0x440,0x441] and
            len(right['records'])==4,'power output inventory/order differs')
    for a,b in zip(left['records'],right['records']):
        if a[0]==0x441:
            require(a[:3]+a[4:]==b[:3]+b[4:],'wake cause/epoch/order differs')
            delivered=left['raw_events'][2][0]//10
            require(all(delivered<=r[3]<=delivered+WAKE_TICK_BOUND for r in (a,b)),
                    'wake observation outside predeclared service bound')
        else: require(a==b,'exact guest power fields differ')
    return {'status':'PASS','scope':'predeclared partial power relation; architectural time/counter parity unqualified',
            'inputs':[{'path':str(path),'sha256':sha(path)} for path in paths],
            'raw_events':left['raw_events'],'records':[left['records'],right['records']],
            'wake_tick_bound':WAKE_TICK_BOUND,'backend_states_retained_in_inputs':True}


class Owner:
    def __init__(self, backend, directory, timeout, restore=None):
        self.directory=directory; self.timeout=timeout
        self.log=directory.with_suffix('.owner.log').open('xb')
        command=[str(ROOT/'scripts/lemmasim'),'session','--backend',backend,'--profile',PROFILE,
            '--workload','power','--mode','laboratory','--headless','--paused',
            '--session-dir',str(directory),'--timeout',str(timeout)]
        if restore:command+=['--restore',str(restore)]
        self.command=command
        self.process=subprocess.Popen(command,cwd=ROOT,stdout=self.log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+timeout
            while not ((directory/'machine.sock').exists() and (directory/'session.json').exists()):
                require(self.process.poll() is None,'session startup failed: '+str(self.log.name))
                require(time.monotonic()<deadline,'session startup deadline')
                time.sleep(.05)
            self.initial=self.call('inspect')
        except BaseException:
            if self.process.poll() is None:self.process.terminate()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
            self.log.close()
            raise

    def call(self, action, **fields):
        return request(self.directory,{'action':action,**fields},self.timeout+5)

    def run(self, cycles):
        self.call('run',cycles=cycles)
        # The fast runtime returns its clock promptly; inspect observes the
        # complete paused device/CPU state at exactly that boundary.
        return self.call('inspect')['machine']

    def uart(self, backend):
        if backend=='rtl': return self.directory/'uart.bin'
        # Each actual QEMU restart owns a fresh byte-output file. Follow that
        # generation; never append invented bytes to an older process's UART.
        paths=list(self.directory.rglob('uart-*.bin'))
        require(1<=len(paths)<=16,'missing or oversized UART generation inventory')
        return max(paths,key=lambda path:(path.stat().st_mtime_ns,str(path)))

    def close(self):
        if self.process.poll() is None:
            try:self.call('destroy')
            except Exception:pass
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
        self.log.close()


def run_backend(backend, out, args):
    owner=fork=None; started=time.monotonic(); result={'status':'FAIL','backend':backend}
    try:
        owner=Owner(backend,out/'first',args.timeout)
        result.update(identity=owner.initial['identity'],initial=owner.initial['machine'],
                      command=owner.command,raw_events=EVENTS)
        for cycle,level in EVENTS:
            owner.call('inject',kind='button',cycle=cycle,level=level)
        state=owner.run(EVENTS[0][0])
        uart=owner.uart(backend)
        cold=records(uart)
        require((0x442,1,0,0,0) in cold and (0x443,1,0,0,0) in cold,
                'real guest did not cold boot to ready before declared arrival cycle')
        result.update(cold_records=cold,cold_state=state,cold_wall_seconds=time.monotonic()-started)
        suspended=owner.run(20000)
        power=suspended['power'] if backend=='rtl' else suspended['devices']['power']
        require((power['state'],power['epoch'],power['reset_cause'])==(1,1,1),
                'actual guest did not accept suspend at the declared cutpoint')
        checkpoint=out/'suspended'
        owner.call('snapshot',path=str(checkpoint))
        uart_offset=uart.stat().st_size
        remaining=100000
        final=owner.run(remaining)
        owner.call('snapshot',path=str(out/'original'))
        original_uart=uart.read_bytes()[uart_offset:]
        complete=records(uart)
        relevant=[row for row in complete if row[0] in (0x440,0x441,0x442,0x443)]
        require(complete==relevant,'unexpected guest record outside declared power observation inventory')
        require([r for r in relevant if r[0]==0x440]==[(0x440,1,0,1,1)],
                'guest suspend status/source/state/epoch differs')
        wakes=[r for r in relevant if r[0]==0x441]
        require(len(wakes)==1 and wakes[0][1:3]==(1,2) and wakes[0][4]==0,
                'guest wake cause/epoch/order differs')
        require(EVENTS[2][0]//10<=wakes[0][3]<=EVENTS[2][0]//10+WAKE_TICK_BOUND,
                'actual guest wake time outside predeclared delivery/service bound')
        power=final['power'] if backend=='rtl' else final['devices']['power']
        require((power['state'],power['events'],power['epoch'],power['wake_cause'])==(0,0,2,1),
                'wake did not leave guest/controller in RUN with acknowledged events')
        fork=Owner(backend,out/'fork',args.timeout,checkpoint)
        fork_initial=fork.initial['machine']
        fork_uart=fork.uart(backend)
        replay=fork.run(remaining)
        fork.call('snapshot',path=str(out/'replayed'))
        require(fork_uart.read_bytes()==original_uart,'complete genuine guest UART suffix differs')
        # These are host backing ownership labels, never simulated state.
        omit={'isolated_medium','private_medium_path'} if backend=='rtl' else set()
        require({k:v for k,v in final.items() if k not in omit}==
                {k:v for k,v in replay.items() if k not in omit},
                'complete inspected CPU/device/time continuation differs')
        if backend=='rtl':
            require(sha(out/'original/machine.chk')==sha(out/'replayed/machine.chk'),
                    'entire same-RTL model/wrapper checkpoint bytes differ')
            exact={'status':'PASS','whole_container_sha256':sha(out/'original/machine.chk')}
        else:
            prepared=json.loads((ROOT/'build/lemmasim/fast-prepared-0.3.0.json').read_text())
            exact_path=out/'exact-state.json'
            command=[sys.executable,str(ROOT/'conformance/lemmasim/check_fast_state_equivalence.py'),
                '--left',str(out/'original/machine.chk'),'--right',str(out/'replayed/machine.chk'),
                '--qemu',prepared['qemu']['path'],'--output',str(exact_path)]
            observation=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=args.timeout)
            (out/'exact-state.log').write_bytes(observation.stdout+observation.stderr)
            require(observation.returncode==0,'whole QEMU state observer rejected exact continuation')
            exact=json.loads(exact_path.read_text());require(exact['status']=='PASS','whole QEMU state differs')
        result.update(suspended=suspended,final=final,fork_initial=fork_initial,replayed=replay,
                      records=relevant,exact=exact,uart_suffix_sha256=hashlib.sha256(original_uart).hexdigest())
        # Real guest reboot observations are separate from checkpoint equality.
        for action,cause,epoch in [('warm-reset',2,2),('cold-cycle',1,0)]:
            before_uart=fork.uart(backend); offset=before_uart.stat().st_size
            fork.call('inject',kind='button',cycle=replay['cycle']+10000000,level=1)
            fork.call(action)
            reset=fork.run(args.reset_cycles)
            fork_uart=fork.uart(backend)
            if fork_uart!=before_uart:offset=0
            new=fork_uart.read_bytes()[offset:]
            (out/(action+'-uart.bin')).write_bytes(new)
            matches=[tuple(int(v,16) for v in row) for row in re.findall(
                rb'^K1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\r?$',new,re.M)]
            require((0x442,cause,epoch,0,0) in matches and (0x443,1,0,0,0) in matches,
                    'real guest reset-cause/epoch/held-level boot observation differs')
            power=reset['power'] if backend=='rtl' else reset['devices']['power']
            require((power['state'],power['epoch'],power['reset_cause'])==(0,epoch,cause),
                    'controller reset retention differs')
            result[action]={'state':reset,'guest_records':matches}
            replay=reset
        result.update(status='PASS',wall_seconds=time.monotonic()-started)
    except Exception as error:
        result.update(error=str(error),wall_seconds=time.monotonic()-started)
        if owner:
            try:result['last']=owner.call('inspect')
            except Exception as inspect_error:result['inspect_error']=str(inspect_error)
        raise
    finally:
        if fork:fork.close()
        if owner:owner.close()
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--backend',choices=['rtl','qemu','both'],default='both')
    parser.add_argument('--timeout',type=int,default=120)
    parser.add_argument('--arrival-cycle',type=int,default=20000000)
    parser.add_argument('--reset-cycles',type=int,default=20000000)
    parser.add_argument('--compare-results',type=Path,nargs=2)
    args=parser.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    global EVENTS
    require(1<=args.arrival_cycle<=100000000 and 1<=args.reset_cycles<=100000000,
            'declare bounded arrival/reset cycle intervals')
    EVENTS=[(args.arrival_cycle+offset,level) for offset,level in [(0,1),(20000,0),(40000,1),(60000,0)]]
    report={'status':'FAIL','scope':__doc__,'events':EVENTS,'wake_tick_bound':WAKE_TICK_BOUND,
            'observer_sha256':sha(__file__)}
    try:
        if args.compare_results:
            report.update(compare_results([p.resolve() for p in args.compare_results]))
            print('POWER PROBE PAIR PASS: retained actual backend observations')
            return 0
        backends=['rtl','qemu'] if args.backend=='both' else [args.backend]
        values={}
        for backend in backends:
            directory=out/backend;directory.mkdir();values[backend]=run_backend(backend,directory,args)
        if len(values)==2:
            require(all(values['rtl']['identity'][k]==values['qemu']['identity'][k]
                        for k in ('profile','guest','dtb','descriptor')),'paired artifacts differ')
            def admitted(rows):return [r if r[0]!=0x441 else (r[0],r[1],r[2],r[4]) for r in rows]
            require(admitted(values['rtl']['records'])==admitted(values['qemu']['records']),
                    'predeclared paired power observation relation differs')
        report.update(status='PASS',backends=values)
    except Exception as error:
        report['error']=str(error);print('POWER PROBE FAIL: '+str(error));return 1
    finally:(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print('POWER PROBE PASS: '+','.join(values));return 0


if __name__=='__main__':raise SystemExit(main())
