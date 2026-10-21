#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare real16550 legacy polling and opt-in flow/1 backpressure.

Raw external bytes are explicit synthetic stimuli. This observes actual QEMU
queues, UART capacity, reset cancellation and normal guest receive callbacks;
it does not claim a course install, throughput or canonical RTL timing.
"""
from pathlib import Path
import argparse, hashlib, json, os, signal, subprocess, time
from lemmasim_fast import QMP, CPU


def main(a):
    out = a.output_dir.resolve(); out.mkdir(exist_ok=False)
    start = time.monotonic(); deadline = start + a.timeout
    report = {'schema':'lemma-raw-uart-flow-boundaries/1','result':'FAIL',
              'scope':__doc__,'limits':{'whole_seconds':a.timeout},'cases':{}}
    report['inputs'] = {str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (Path(__file__), a.qemu, a.guest, a.dtb)}
    live = []
    def require(value, text):
        if not value: raise AssertionError(text)
    def launch(flow):
        d = out / ('flow' if flow else 'legacy'); d.mkdir()
        disk = d/'medium.raw'
        with disk.open('xb') as f: f.truncate(268435456)
        argv = [str(a.qemu.resolve()),'-machine','lemma-silicon-fast','-cpu',CPU,
                '-m','128M','-smp','1','-bios','none','-kernel',str(a.guest.resolve()),
                '-dtb',str(a.dtb.resolve()),'-display','none','-monitor','none',
                '-serial','file:'+str(d/'uart.bin'),'-S','-no-shutdown',
                '-icount','shift=3,align=off,sleep=off','-global',
                'lemma-fast-block.medium='+str(disk),'-qmp',
                'unix:'+str(d/'qmp.sock')+',server=on,wait=off']
        log=(d/'machine.log').open('xb')
        p=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        q=QMP(d/'qmp.sock',p,10); live.append((p,q,log))
        def get(k): return q.execute('qom-get',{'path':'/machine/lemma-hardware','property':k})
        def put(k,v): return q.execute('qom-set',{'path':'/machine/lemma-hardware','property':k,'value':v})
        def state(): return json.loads(get('raw-uart-state'))
        def run(until):
            put('run-until',str(until)); q.execute('cont')
            while q.execute('query-status')['running']:
                require(time.monotonic()<deadline,'original whole deadline')
                time.sleep(.005)
        put('enable-raw-uart','lemma-raw-uart/1')
        require(get('raw-uart-flow-version')=='lemma-raw-uart-flow/1','flow contract')
        if flow: put('enable-raw-uart-flow','lemma-raw-uart-flow/1')
        require(state()['flow']==flow,'selection identity')
        put('external-uart-paced','0 10 '+('00'*64))
        run(4000)
        full=state()
        require(full['pending']>0 and full['serial_can_receive']==0,'actual UART not full')
        require(full['blocked']==flow and full['timer_pending'] != flow,'backpressure boundary')
        before=state(); observed=json.loads(get('execution-state'))
        require(state()==before and observed==json.loads(get('execution-state')),'observer mutates state')
        # New queued arrivals cannot recreate the poll storm while blocked.
        put('external-uart-paced','5000 1000 aabb')
        run(8000); later=state()
        require(later['delivered']==full['delivered'],'full UART accepted a byte')
        if flow:
            require(later['poll_calls']==full['poll_calls'],'blocked arrival rearmed polling')
        else:
            require(later['poll_calls']>full['poll_calls']+100,'legacy polling comparison absent')
        q.execute('system_reset'); reset=state()
        require(reset['pending']==0 and not reset['blocked'] and not reset['timer_pending'],'reset left pending admission')
        require(reset['canceled']==full['pending']+2 and reset['flow']==flow,'reset accounting/identity')
        # A normal future admission waits for its exact declared first due time.
        now=int(get('virtual-time')); due=now+1000
        put('external-uart-paced',str(due)+' 100000 '+('00'*32))
        # The native run boundary may overshoot by one 8ns instruction.
        run(due-16); early=state()
        require(early['delivered']==reset['delivered'],'early byte delivery')
        run(due+12); first=state()
        require(first['delivered']==reset['delivered']+1,'first due byte not delivered')
        # Actual maintained guest initialization frees the receiver through RBR
        # and/or FCR. The flow must resume through those real callbacks.
        if flow: run(4000000000)
        received=state()
        if flow:
            require(received['delivered']>first['delivered'] and received['wakeups']>0,
                    'normal guest receive readiness did not resume blocked bytes')
        return {'full':full,'after_blocked_admission':later,'reset':reset,
                'before_due':early,'first_due':first,'guest_receive':received,
                'execution_observer':observed}
    try:
        report['cases']['legacy']=launch(False)
        report['cases']['flow']=launch(True)
        require(report['cases']['flow']['full']['poll_calls']<10,'flow retry storm')
        report['result']='PASS'
    except BaseException as error:
        report['error']=repr(error)
    finally:
        for p,q,log in live:
            try:
                if p.poll() is None: q.execute('quit')
            except BaseException: pass
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
            q.close();log.close()
        report['owned_processes_reaped']=all(p.poll() is not None for p,q,log in live)
        report['elapsed_seconds']=time.monotonic()-start
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['result'],report.get('error',''))
    if report['result']!='PASS':raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('qemu','guest','dtb','output-dir'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--timeout',type=int,default=180)
    main(parser.parse_args())
