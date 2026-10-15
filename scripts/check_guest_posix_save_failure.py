#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual guest Compact -> raw ink -> real POSIX partial-write failure -> cold recovery.
Instruction-clock functional evidence only; no RTL timing or cached-state equivalence.
The host supplies raw input and an OS resource limit, then observes bytes/pixels.
"""
import argparse,errno,json,os,resource,shutil,struct,sys,time
from pathlib import Path
from check_live_notebook import Checker,Input,guest_events,idle,require,sha,visible_pixels
from check_fast_backing_replay import qemu_memory
from check_companion_pending import timed_records
from lemmasim_fast import copy_new
from store_oracle import recover

INK_MAGIC=bytes.fromhex('4c454d41494e4b31')
def ink_kind(record):
    if len(record.payload)>=24 and record.payload[:8]==INK_MAGIC:
        return struct.unpack_from('<Q',record.payload,16)[0]
    return None

def observe_resumed_raw(before,after,expected):
    """Ink root1/page2/chunk3 share a magic; only kind3 carries raw samples."""
    old_raw={key:r for key,r in before.items() if ink_kind(r)==3}
    new_raw={key:r for key,r in after.items() if ink_kind(r)==3}
    added=set(new_raw)-set(old_raw)
    require(set(old_raw)<=set(new_raw) and len(added)==1,'extra/missing raw chunk after cold recovery')
    key=next(iter(added));record=new_raw[key]
    require(set(after)==set(before)|{key},'resumed writing added unrelated objects')
    require(struct.unpack_from('<Q',record.payload,8)[0]==1 and len(record.payload)==128+len(expected),
            'raw chunk version/framing differs')
    require(record.payload[128:]==expected,'acknowledged actual raw sample bytes differ')
    for old_key,old in before.items():
        if ink_kind(old) in (1,2):
            require(ink_kind(after[old_key])==ink_kind(old),'resumed writing changed Ink metadata kind')
        else:
            require(after[old_key].payload==old.payload,'resumed writing changed immutable raw/package/workspace bytes')
    return {'raw_object':key,'sample_bytes':len(expected),'previous_immutable_objects_exact':True}

class Check(Checker):
    profile='lemma-silicon-dev/0.3.0'
    def __init__(self,args):
        super().__init__(args)
        self.cycles=0;self.limited_pid=None;self.old_limit=None
        self.report.update(schema='lemma-guest-posix-save-failure/1',scope=__doc__,phases=[],
            limits={'aggregate_instruction_clock_cycles':1500000000,'cold_cycles_each':500000000,
                    'compact_cycles':300000000,'failed_ink_cycles':100000000,
                    'host_seconds':args.deadline,'address_space_bytes':4<<30,
                    'file_bytes':1<<30,'outputs_bytes':4<<30,'minimum_available_bytes':2<<30})
        self.checker_source=sha(__file__)
        shutil.copyfile(__file__,self.directory/'consumed-checker.py')
        self.report['checker_sha256']=self.checker_source
    def rows(self,s):return guest_events(s.directory/'uart-0.bin')
    def saved(self,s):
        rows=[r for r in self.rows(s) if r[0] in (0x421,0x423,0x424)]
        return bool(rows) and rows[-1][0]==0x421
    def resources(self,s):
        m=qemu_memory(s.process.pid)
        require(m['rss_kib']*1024+resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024<4<<30,'owned memory bound')
        available=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
        require(available>=2<<30,'available memory bound')
        size=sum(p.stat().st_size for p in self.directory.rglob('*') if p.is_file())
        require(size<=4<<30,'output bound')
        self.report['resources']={'qemu':m,'parent_peak_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                  'available_bytes':available,'output_bytes':size}
        return m
    def phase(self,s,name,cap,predicate,allow_failure=False):
        first=s.inspect()['machine'];start=time.monotonic()
        while True:
            now=s.inspect()['machine'];rows=self.rows(s)
            require(not now['finished'] and not any(r[0] in (0x41f,0xd4,0xf4,0x454) for r in rows),'actual guest fatal/format/course failure: '+name)
            if not allow_failure:require(not any(r[0]==0x424 for r in rows),'actual unexpected Failed: '+name)
            if predicate(now):break
            used=now['cycle']-first['cycle']
            require(used<cap and self.cycles<1500000000 and time.monotonic()<self.deadline,'prospective resource bound: '+name)
            self.resources(s)
            s.run(min(1000000,cap-used,1500000000-self.cycles))
            after=s.inspect()['machine'];require(after['cycle']>now['cycle'],'no actual instruction-clock progress')
            self.cycles+=after['cycle']-now['cycle']
        item={'name':name,'start':first['cycle'],'end':now['cycle'],'cycles':now['cycle']-first['cycle'],'host_seconds':time.monotonic()-start}
        self.report['phases'].append(item);print(json.dumps(item),flush=True);self.progress()
        return now
    def progress(self):
        (self.directory/'progress.json').write_text(json.dumps(self.report,default=str,indent=2)+'\n')
    def lift_limit(self):
        if self.limited_pid is not None:
            resource.prlimit(self.limited_pid,resource.RLIMIT_FSIZE,self.old_limit)
            self.limited_pid=None
    def execute(self):
        require(self.args.disk.stat().st_size==256<<20,'actual initialized256MiB input required')
        self.report['input']={'path':str(self.args.disk),'sha256':sha(self.args.disk)}
        disk=self.directory/'live-input.raw';copy_new(self.args.disk,disk)
        live=self.session('live',disk)
        require(live.identity['guest']==self.args.expected_guest_sha256,'unexpected actual audited guest')
        require(live.identity['runtime']==self.args.expected_runtime_sha256,'unexpected actual QEMU runtime')
        self.report['identity']=live.identity
        require(live.inspect()['machine']['cycle']==0,'new CPU did not start at reset')
        self.phase(live,'actual-newCPU-cold-Ready',500000000,
                   lambda s:idle(s) and s['devices']['paper']['completed']>=1 and any(r[0]==0x420 for r in self.rows(live)))
        initial_panel,initial_medium=live.export('initial')
        old_root,old_seq,old_records=recover(initial_medium.read_bytes())
        require(old_root.segment==0,'fixture requires actual segment0 before guest Compact')
        count=len([r for r in self.rows(live) if r[0]==0x421])
        stream=Input(1650,2200,live.inspect()['machine']['ticks']+10000,100000,0)
        stream.sample(1558,64,2048,True);stream.sample(1558,64,0,False);live.admit(stream.events)
        def compact_presented(s):
            if not (idle(s) and self.saved(live) and len([r for r in self.rows(live) if r[0]==0x421])>count and s['ticks']>=stream.events[-1][1]+200000):return False
            panel=self.directory/'compact-wait.ppm'
            live.control({'action':'panel','path':str(panel)})
            return visible_pixels(panel)==visible_pixels(initial_panel)
        self.phase(live,'raw-Compact-and-presented-guest-Saved',300000000,compact_presented)
        baseline_panel,baseline_medium=live.export('compacted')
        baseline=baseline_medium.read_bytes();root,seq,records=recover(baseline)
        require(root.segment==1 and root.checkpoint_count==len(records) and seq==old_seq,'actual guest Compact did not retain acknowledged sequence')
        require({k:(r.kind,r.payload) for k,r in records.items()}=={k:(r.kind,r.payload) for k,r in old_records.items()},'Compact changed acknowledged objects')
        offset=(root.start+root.checkpoint_tail)*512
        require((128<<20)<offset<(256<<20)-512,'append boundary not beyond capture files')
        require(baseline[offset:offset+512]==bytes(512),'next actual append sector is not blank')
        q=self.resources(live);pid=q['pid'];signals={}
        for line in (Path('/proc')/str(pid)/'status').read_text().splitlines():
            if line.split(':')[0] in ('SigIgn','SigCgt','SigBlk'):signals[line.split(':')[0]]=line.split(':')[1].strip()
        require(not (int(signals['SigIgn'],16)|int(signals['SigCgt'],16)) & (1<<24),'guest I/O case requires default SIGXFSZ disposition')
        self.old_limit=resource.prlimit(pid,resource.RLIMIT_FSIZE)
        require(offset+2<self.old_limit[1],'file limit cannot be privately restored')
        resource.prlimit(pid,resource.RLIMIT_FSIZE,(offset+2,self.old_limit[1]));self.limited_pid=pid
        before=live.inspect()['machine'];saved_before=len([r for r in self.rows(live) if r[0]==0x421])
        self.report['actual_os_fault']={'qemu_pid':pid,'signals':signals,'soft_file_bytes':offset+2,
                                       'append_offset':offset,'prior_limit':self.old_limit,'source':'real Linux prlimit, not controller failure injection'}
        first=len(stream.events);stream.tick=before['ticks']+10000
        stream.sample(1100,1900,1024,True);stream.sample(1110,1905,1216,True);stream.sample(1110,1905,0,False)
        live.admit(stream.events[first:])
        self.phase(live,'actual-raw-ink-and-unsuccessful-Save',100000000,
            lambda s:idle(s) and any(r[0]==0x424 for r in self.rows(live)) and s['ticks']>=stream.events[-1][1]+200000,True)
        require(len([r for r in self.rows(live) if r[0]==0x421])==saved_before,'guest manufactured Saved after failed pwrite')
        after=live.inspect()['machine']
        require(after['storage']['backing_durable_barrier']==before['storage']['backing_durable_barrier'],'failed append advanced durability')
        outcomes,pending=timed_records(live.directory/'backing-0.io')
        require(pending is None,'unresolved external operation after actual failure')
        failures=[list(row) for row,accepted in outcomes if row[2]==1 and row[6]==errno.EFBIG]
        require(len(failures)==1 and failures[0][3:7]==[offset,512,2,errno.EFBIG],'actual captured partial pwrite/EFBIG differs')
        self.report['captured_failure']=failures[0]
        self.lift_limit()
        fault_panel,fault_medium=live.export('failed')
        failed=fault_medium.read_bytes();differences=[i for i,(a,b) in enumerate(zip(baseline,failed)) if a!=b]
        require(differences==[offset,offset+1] and failed[offset:offset+2]==b'LM','failed write did not retain exactly the observed real prefix')
        require(recover(failed)[1]==seq and {k:(r.kind,r.payload) for k,r in recover(failed)[2].items()}=={k:(r.kind,r.payload) for k,r in records.items()},'failed append changed acknowledged objects')
        self.report['partial_effect']={'bytes':2,'offset':offset,'prior_sequence':seq,'guest_failed':True,'no_new_saved':True}
        live.close();self.sessions.remove(live)
        cold_disk=self.directory/'cold-input.raw';copy_new(fault_medium,cold_disk)
        cold=self.session('cold',cold_disk)
        require(cold.identity==self.report['identity'] and cold.inspect()['machine']['cycle']==0,'independent cold identity/reset mismatch')
        self.phase(cold,'independent-cold-after-real-partial-failure',500000000,
            lambda s:idle(s) and s['devices']['paper']['completed']>=1 and any(r[0]==0x420 for r in self.rows(cold)))
        cold_panel,cold_medium=cold.export('cold')
        require(cold_medium.read_bytes()==failed,'cold recovery changed observed unacknowledged backing')
        require(visible_pixels(cold_panel)==visible_pixels(baseline_panel),'cold failed-save recovery changed the complete acknowledged display')
        self.report['cold_recovery']={'new_cpu':True,'no_snapshot_restore':True,'full_medium_exact':True,'all_controller_pixels_exact':True,'acknowledged_objects_exact':True}
        # Recovered storage must remain writable after the rejected append.
        # Three actual samples create one raw record, page index and root.
        resumed=Input(1650,2200,cold.inspect()['machine']['ticks']+10000,100000,0)
        resumed.sample(1100,1800,1024,True);resumed.sample(1110,1805,1216,True);resumed.sample(1110,1805,0,False)
        cold.admit(resumed.events)
        self.phase(cold,'raw-writing-and-Saved-after-cold-recovery',100000000,
            lambda s:idle(s) and self.saved(cold) and any(r[0]==0x421 and r[1]==seq+3 for r in self.rows(cold)) and s['ticks']>=resumed.events[-1][1]+200000)
        _,resaved=cold.export('resaved');_,new_sequence,new_records=recover(resaved.read_bytes())
        expected=b''.join(struct.pack('<9Q',*row) for row in resumed.events)
        require(new_sequence==seq+3,'cold resumed writing did not acknowledge the complete raw/page/root publication')
        observed=observe_resumed_raw(records,new_records,expected)
        self.report['post_cold_writing']={'actual_raw_samples':3,'saved_sequence':new_sequence,'raw_bytes_exact':True,**observed}
        require(sha(__file__)==self.checker_source,'consumed checker changed during execution')
        cold.close();self.sessions.remove(cold);self.report['status']='PASS'
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--disk',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True)
    p.add_argument('--expected-guest-sha256',required=True);p.add_argument('--expected-runtime-sha256',required=True)
    p.add_argument('--deadline',type=int,default=900);a=p.parse_args()
    a.timeout=120;a.boot_seconds=10;a.action_seconds=4;a.durable_suffix_from=None;a.checkpoint_relation='not-exercised';a.native_bundle=None;a.guest_build=None
    resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30))
    actor=Check(a)
    try:actor.execute()
    except BaseException as error:actor.report['error']=repr(error);raise
    finally:
        try:actor.lift_limit()
        finally:
            for session in reversed(actor.sessions):session.close()
            actor.commands.close();actor.report['host_seconds']=time.monotonic()-actor.started;actor.progress()
            (actor.directory/'result.json').write_text(json.dumps(actor.report,default=str,indent=2)+'\n')
    print(actor.report['status'])
if __name__=='__main__':main()
