#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay a captured real partial pwrite through the guest's Failed Save path.

The selected setup cut and every admitted raw/run request are reused verbatim.
Only the isolated LMIOLOG2 backing consumer supplies external outcomes. This
checks exact recorded I/O, guest suffix and pixels, not arbitrary QEMU cached
state continuation, physical power loss or exact RTL timing.
"""
import argparse,json,resource,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'conformance/lemmasim')]
from check_partial_write_save import Case
from check_live_notebook import require,sha,visible_pixels,guest_events
from check_companion_pending import timed_records
from store_oracle import recover


class ReplayCase(Case):
    def __init__(self,args):
        super().__init__(args);self.replay_arguments=None
        self.report.update(schema='lemma-real-partial-write-replay/1',scope=__doc__,resource_limit_scope='No fault injection or live backing limit; consume actual captured requests/completions against a private checkpoint fork.')

    def launch(self,args,**kwargs):
        # Record the actual public launch command through Checker.launch.
        args=list(args)
        if self.replay_arguments is not None and args and args[0]=='session':
            at=args.index('--disk');del args[at:at+2]
            args+=['--restore',str(self.replay_arguments[0]),'--backing-replay',str(self.replay_arguments[1])]
        return super().launch(args,**kwargs)

    def execute(self):
        source=Path(self.args.source_case).resolve();observer=Path(self.args.source_observer).resolve()
        require(source.is_relative_to(ROOT/'build')and observer.is_relative_to(ROOT/'build'),'retained task evidence required')
        m=json.loads((source/'result.json').read_text());qualification=json.loads(observer.read_text())
        require(qualification['status']=='PASS_RETAINED_REAL_PARTIAL_PWRITE_FAILED_SAVE_COLD'and qualification['original_actor']['sha256']==sha(source/'result.json'),'independently qualified actual fault/cold source required')
        require(m['identity']['backend']=='qemu'and m['identity']['profile']==self.profile,'selected functional profile differs')
        cut=source/'ready-cut';tape=Path(m['fault_owner']['fresh_tape']);wire=tape.read_bytes();expected_io,pending=timed_records(tape)
        require(pending is None and expected_io and expected_io[-1][0][5:]==(128,27),'recorded actual short-write/EFBIG outcome required')
        expected_raw=(tape.parent/'input-1.bin').read_bytes();expected_uart=(tape.parent/'uart-1.bin').read_bytes()
        rows=[json.loads(x)for x in (source/'commands.jsonl').read_text().splitlines()]
        live=[x['request']for x in rows if isinstance(x,dict)and x.get('session')==str(source/'live')]
        starts=[i for i,x in enumerate(live)if x.get('action')=='restore'and x.get('path')==str(cut)]
        require(len(starts)==1,'unambiguous selected private setup required')
        requests=[x for x in live[starts[0]+1:]if x['action']in('inject','run')]
        require(requests and sum(x['action']=='inject'for x in requests)==3 and sum(x.get('cycles',0)for x in requests)<=100000000,'selected100M suffix request bound')
        self.report['source']={'actor':{'path':str(source/'result.json'),'sha256':sha(source/'result.json')},'qualification':{'path':str(observer),'sha256':sha(observer)},'tape':{'path':str(tape),'sha256':sha(tape)},'commands_sha256':sha(source/'commands.jsonl'),'requests':requests}
        self.replay_arguments=(cut,tape);s=self.session('replay',cut/'durable.raw')
        require(s.identity==m['identity'],'actual replay guest/runtime differs');initial=self.state(s)
        require(initial['cycle']==m['phases'][0]['functional_units'],'selected cut origin differs')
        self.report['identity']=s.identity;began=time.monotonic()
        for request in requests:
            require(time.monotonic()<self.deadline,'original300s replay bound');s.control(request)
        final=self.state(s);expected_final=sum(x['functional_units']for x in m['phases'][:3]);require(final['cycle']==expected_final,'exact selected final cycle differs')
        panel,medium=s.export('replayed-failed');forks=list(s.directory.glob('machine-fork-*'));require(len(forks)==1,'single private replay fork required');active=forks[0]
        tapes=list(active.glob('backing-*.io'));raws=list(active.glob('input-*.bin'));uarts=list(active.glob('uart-*.bin'));require(len(tapes)==len(raws)==len(uarts)==1,'complete isolated suffix capture required')
        actual_io,active_pending=timed_records(tapes[0]);require(active_pending is None and actual_io==expected_io and tapes[0].read_bytes()==wire,'exact requests/outcomes/accepted completion times differ')
        require(raws[0].read_bytes()==expected_raw and uarts[0].read_bytes()==expected_uart,'exact raw ingress or guest UART suffix differs')
        require(visible_pixels(panel)==visible_pixels(source/'failed.ppm'),'complete Failed/provisional ink display differs')
        require(medium.read_bytes()==(source/'failed.raw').read_bytes()and recover(medium.read_bytes())[1:]==recover((source/'before.raw').read_bytes())[1:],'observed unacknowledged prefix/prior exact records differ')
        actual_launch=json.loads((s.directory/'session.json').read_text())['argv'];require([x for x in actual_launch if x.startswith('lemma-fast-block.medium=')]==['lemma-fast-block.medium='+str(active/'durable.raw')]and 'lemma-fast-block.replay-private=on'in actual_launch and 'lemma-fast-block.backing-replay='+str(tape)in actual_launch,'replay launch did not bind isolated medium/recorded outcomes')
        require(not any(x[0]==0x421 for x in guest_events(uarts[0])),'recorded failed write manufactured Saved')
        require(all(sha(ROOT/n)==h for n,h in self.inputs.items()),'consumed host input changed')
        self.report.update(status='PASS_RECORDED_REAL_PARTIAL_PWRITE_GUEST_SUFFIX',host_sources_unchanged=True,functional_units=final['cycle']-initial['cycle'],initial_cycle=initial['cycle'],final_cycle=final['cycle'],replay_seconds=time.monotonic()-began,accepted_io_exact=True,raw_ingress_exact=True,guest_uart_exact=True,controller_all_pixels=3630000,backing_all_bytes=268435456,private_fork=str(active),observed_backing_sha256=sha(medium),scope_limit='Selected originally restored Ready setup and identical public run/admission boundaries only. QEMU logical cached state/complete arbitrary continuation and exact RTL remain open. No original medium or peer is supplied to replay adapter.')


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);p.add_argument('--source-case',required=True);p.add_argument('--source-observer',required=True);p.add_argument('--native-bundle',required=True);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--deadline',type=int,default=300);a=p.parse_args();require(1<=a.deadline<=300,'original300s bound');a.timeout=120;a.durable_suffix_from=None;a.checkpoint_relation='selected-recorded-I/O-and-guest-output-only';resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30));actor=ReplayCase(a)
    try:actor.execute()
    except BaseException as error:actor.report.update(status='FAIL',error=repr(error));raise
    finally:actor.close()
    print(actor.report['status'],actor.report['elapsed_seconds'])
if __name__=='__main__':main()
