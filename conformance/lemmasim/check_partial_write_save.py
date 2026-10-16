#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real guest Save under an owned Linux file-size limit, then independent cold recovery.

The actual pwrite can change a prefix before EFBIG. Host code supplies raw pen
and a backing resource failure only; Lean constructs ink, commits and recovers.
The selected setup fork is not arbitrary cached-QEMU continuation qualification.
"""
import argparse, errno, json, os, resource, stat, struct, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'conformance/lemmasim')]
from check_live_notebook import Checker,guest_events,idle,require,sha,visible_pixels
from check_course_math_workflow import Input
from check_companion_pending import timed_records
from course_pixel_oracle import annotation_pixels
from notebook_pixels import empty_pixels
from lemmasim_fast import copy_new
from store_oracle import recover


def process_row(pid):
    try:
        text=Path('/proc',str(pid),'stat').read_text();f=text[text.rindex(')')+2:].split()
        return int(f[1]),int(f[19])
    except (OSError,ValueError,IndexError):return None


def owned_backend(parent,runtime,launcher,launcher_sha):
    """Bind descendant, running ELF and the originally admitted launcher independently."""
    require(sha(launcher)==launcher_sha,'admitted launcher changed')
    rows={int(p.name):r for p in Path('/proc').iterdir()if p.name.isdecimal()and(r:=process_row(int(p.name)))}
    require(parent in rows,'session owner disappeared');family={parent};changed=True
    while changed:
        changed=False
        for pid,row in rows.items():
            if row[0]in family and pid not in family:family.add(pid);changed=True
    matches=[]
    for pid in family-{parent}:
        try:
            exe=Path('/proc',str(pid),'exe')
            if sha(exe)==runtime and Path('/proc',str(pid),'cmdline').read_bytes().split(b'\0')[0]==os.fsencode(launcher):matches.append((pid,rows[pid]))
        except OSError:pass
    require(len(matches)==1,'owned backend executable identity is missing/ambiguous')
    return matches[0]


class Case(Checker):
    profile='lemma-silicon-dev/0.3.0'
    backend='qemu'

    def __init__(self,args):
        super().__init__(args);self.cycles=0
        self.inputs={str(p.relative_to(ROOT)):sha(p)for p in [Path(__file__),*sorted((ROOT/'scripts').glob('*.py')),ROOT/'scripts/lemmasim',*sorted((ROOT/'conformance/lemmasim').glob('*.py'))]}
        self.report.update(schema='lemma-real-partial-write-save/1',scope=__doc__,host_inputs=self.inputs,phases=[],resource_limit_scope='Only admitted owned QEMU child soft RLIMIT_FSIZE; original hard/soft limits restored before exports/close. Actual OS pwrite/EFBIG outcomes, no injected FLUSH counter.',bounds={**self.report['bounds'],'aggregate_functional_units':3000000000,'each_cold_units':1000000000,'failed_save_units':300000000,'per_process_address_bytes':4<<30,'output_bytes':8<<30})

    def state(self,s):return s.inspect()['machine']
    def rows(self,s):return guest_events(getattr(s,'uart_path',s.directory/'uart-0.bin'))
    def progress(self):(self.directory/'progress.json').write_text(json.dumps(self.report,indent=2)+'\n')

    def until(self,s,name,limit,predicate):
        initial=self.state(s)['cycle'];started=time.monotonic()
        while not predicate():
            now=self.state(s);require(time.monotonic()<self.deadline,'whole900s deadline');require(not now['finished'],'guest stopped');require(now['cycle']-initial<limit,name+' virtual bound')
            n=min(1000000,limit-(now['cycle']-initial));s.run(n);self.cycles+=self.state(s)['cycle']-now['cycle'];require(self.cycles<=3000000000,'whole3B bound')
        self.report['phases'].append({'name':name,'functional_units':self.state(s)['cycle']-initial,'seconds':time.monotonic()-started});self.progress()

    def execute(self):
        source=Path(self.args.disk).resolve();source_sha=sha(source);raw=source.read_bytes();root,sequence,records=recover(raw)
        require(root.checkpoint_count==root.checkpoint_tail==root.sequence==0 and sequence>0,'declared append-only acknowledged source required')
        last=max(records.values(),key=lambda r:r.sequence);offset=(last.sector+2+(len(last.payload)+511)//512)*512
        require(raw[offset:offset+512]==bytes(512),'next append header must be unused');limit=offset+128
        require(16384<=limit<1<<30,'prospective file-limit range');self.report['fault_plan']={'source_sha256':source_sha,'sequence':sequence,'first_append_offset':offset,'soft_file_limit':limit,'actual_partial_prefix_expected':128,'cold_policy':'Engine.incompleteTail sees no pending published checkpoint, preserves earlier index and returns Ready. No format; original acknowledged objects/pixels, including workspace/history, remain. Unacknowledged partial header stays in backing.'};self.progress()
        live=self.directory/'live.raw';copy_new(source,live);s=self.session('live',live)
        self.report['identity']=s.identity
        self.until(s,'cold-Ready',1000000000,lambda:idle(self.state(s))and self.state(s)['devices']['paper']['completed']>=1 and any(r[0]==0x420 for r in self.rows(s)))
        panel,medium=s.export('before');require(visible_pixels(panel)==visible_pixels(Path(self.args.reference_pixels))and medium.read_bytes()==raw,'actual cold reference differs')
        before=self.state(s);cut=self.directory/'ready-cut';s.control({'action':'snapshot','path':str(cut)});require(self.state(s)==before,'observational snapshot changed state')
        s.control({'action':'restore','path':str(cut)});require(self.state(s)==before,'selected private setup fork differs')
        files=list(s.directory.glob('machine-fork-*/uart-1.bin'));require(len(files)==1,'private UART suffix missing');s.uart_path=files[0]
        launcher=Path(json.loads((s.directory/'session.json').read_text())['argv'][0]);running=Path(self.args.backend_executable).resolve()
        require(running.is_file()and sha(running)==self.args.backend_executable_sha256,'predeclared running executable differs')
        require(running==launcher.resolve()or os.fsencode(running)+b'\0'in launcher.read_bytes(),'running executable absent from admitted launcher')
        pid,row=owned_backend(s.process.pid,self.args.backend_executable_sha256,launcher,s.identity['runtime']);original=resource.prlimit(pid,resource.RLIMIT_FSIZE);require(original[0]==resource.RLIM_INFINITY or original[0]>limit,'outer file ceiling too small')
        # A fresh private capture avoids applying the storage limit to a long
        # historical capture. Never truncate or rewind an evidence file.
        tapes=list(s.uart_path.parent.glob('backing-1.io'));require(len(tapes)==1 and tapes[0].stat().st_size<limit-8192,'fresh private outcome capture does not fit fault envelope')
        mapped_surfaces=[]
        for fd in Path('/proc',str(pid),'fd').iterdir():
            try:
                flags=int(next(x.split()[1]for x in Path('/proc',str(pid),'fdinfo',fd.name).read_text().splitlines()if x.startswith('flags:')),8)
                target=fd.resolve();info=fd.stat()
                if flags&3 in(1,2)and stat.S_ISREG(info.st_mode)and target.suffix!='.raw':
                    if os.readlink(fd)=='/memfd:displaysurface (deleted)':
                        # Pinned QEMU allocates fixed Pixman shared images before
                        # the cut. lemma_gfx_update writes mapped rows; this case
                        # cannot resize displays. FSIZE does not extend mappings.
                        require(info.st_size in(640*384*4,1650*2200*4),'unknown display mapping size')
                        mappings=[x.split()for x in Path('/proc',str(pid),'maps').read_text().splitlines()]
                        require(any(len(x)>=6 and x[1]=='rw-s'and int(x[4])==info.st_ino and int(x[0].split('-')[1],16)-int(x[0].split('-')[0],16)>=info.st_size for x in mappings),'fixed shared display mapping missing')
                        mapped_surfaces.append((str(fd),info.st_ino,info.st_size))
                    else:require(info.st_size<limit-8192,'another owned output already exceeds file envelope: '+str(target))
            except FileNotFoundError:pass
        stream=Input(1650,2200,before['ticks']+10000,100000,0)
        stream.sample(1000,1200,2048,True);stream.sample(1010,1210,2048,True);stream.sample(1010,1210,0,False)
        expected=annotation_pixels(visible_pixels(panel),stream.events,512)
        failed_header=empty_pixels(1650,2200,status='FAILED');failed_expected=(1650,2200,failed_header[:160*1650*3]+expected[2][160*1650*3:])
        self.report['fault_owner']={'pid':pid,'start_ticks':row[1],'running_executable':str(running),'running_executable_sha256':self.args.backend_executable_sha256,'launcher_sha256':s.identity['runtime'],'original_limits':list(original),'at_cycle':before['cycle'],'fresh_tape':str(tapes[0]),'fixed_mapped_surfaces':mapped_surfaces,'literal_raw_events':[list(x)for x in stream.events]};self.progress()
        changed=False
        try:
            require(process_row(pid)==row and sha(Path('/proc',str(pid),'exe'))==self.args.backend_executable_sha256,'owned PID/executable identity changed before limit');resource.prlimit(pid,resource.RLIMIT_FSIZE,(limit,original[1]));changed=True;s.admit(stream.events)
            self.until(s,'actual-partial-pwrite-failed-Save',300000000,lambda:any(r[0]==0x424 for r in self.rows(s)))
        finally:
            if changed:
                if process_row(pid)==row:resource.prlimit(pid,resource.RLIMIT_FSIZE,original)
                else:
                    self.report['limit_owner_exited_before_restoration']=True
                    if sys.exc_info()[0]is None:raise RuntimeError('owned backend disappeared before resource restoration')
        require(all(Path(fd).stat().st_ino==inode and Path(fd).stat().st_size==size for fd,inode,size in mapped_surfaces),'display mapping changed during file-limit fault')
        require(not any(r[0]==0x421 for r in self.rows(s))and not any(r[0]in(0x41f,0xd4,0xf4)for r in self.rows(s)),'failed write manufactured Saved/formatted/faulted')
        progress_panel=self.directory/'failed-progress.ppm'
        def completed_failed_pixels():
            if not idle(self.state(s))or self.state(s)['devices']['paper']['completed']<=before['devices']['paper']['completed']:return False
            s.control({'action':'panel','path':str(progress_panel)})
            return visible_pixels(progress_panel)==failed_expected
        remaining=300000000-(self.state(s)['cycle']-before['cycle']);require(remaining>=0,'original combined failed-Save300M bound')
        self.until(s,'failed-provisional-ink-completed-controller',remaining,completed_failed_pixels)
        failed,observed=s.export('failed');require(visible_pixels(failed)==failed_expected,'complete actual Failed/provisional-ink pixels differ')
        outcomes,pending=timed_records(tapes[0]);errors=[x for x in outcomes if x[0][-1]]
        require(pending is None and len(errors)==1 and errors[0][0][2:]==(1,offset,512,128,errno.EFBIG),'actual captured partial pwrite/EFBIG differs')
        require(outcomes[-1]==errors[0]and self.state(s)['storage']['backing_durable_barrier']==before['storage']['backing_durable_barrier'],'failed write passed a later barrier')
        changed_raw=observed.read_bytes();require(changed_raw[:offset]==raw[:offset]and changed_raw[offset+128:]==raw[offset+128:]and changed_raw[offset:offset+128]!=raw[offset:offset+128],'failed write rolled back or changed unexpected backing bytes')
        _,gotseq,got=recover(changed_raw);require(gotseq==sequence and got==records,'unacknowledged partial append entered committed record set')
        self.report['actual_failure']={'outcome':errors[0],'observed_changed_prefix_bytes':128,'sequence':gotseq,'objects_unchanged':len(got),'guest_failed':[r for r in self.rows(s)if r[0]==0x424],'guest_saved_after_fault':False,'medium_sha256':sha(observed)};self.progress()
        s.close();self.sessions.remove(s);disk=self.directory/'cold.raw';copy_new(observed,disk);cold=self.session('cold',disk);require(self.state(cold)['cycle']==0,'independent cold origin required')
        self.until(cold,'independent-cold-after-real-partial-write',1000000000,lambda:idle(self.state(cold))and self.state(cold)['devices']['paper']['completed']>=1 and any(r[0]==0x420 for r in self.rows(cold)))
        cp,cm=cold.export('cold-recovered');require(visible_pixels(cp)==visible_pixels(panel)and cm.read_bytes()==changed_raw,'cold did not recover exact prior display/observed backing')
        require(recover(cm.read_bytes())[1:]==(sequence,records)and sha(source)==source_sha and sha(live)==source_sha,'cold records/source/private ownership differ')
        self.report.update(status='PASS_REAL_PARTIAL_PWRITE_GUEST_FAILED_SAVE_COLD',functional_units=self.cycles,cold_all_pixels=3630000,cold_all_medium_bytes=268435456,source_unchanged=True,scope_limit='Actual Linux short pwrite/EFBIG and cold recovery on QEMU functional backend. Selected setup fork is not arbitrary cached-state continuation; isolated recorded guest-suffix replay and exact RTL error case remain separate. Physical power-loss persistence unqualified.')


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);p.add_argument('--disk',required=True);p.add_argument('--reference-pixels',required=True);p.add_argument('--native-bundle',required=True);p.add_argument('--backend-executable',required=True);p.add_argument('--backend-executable-sha256',required=True);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--deadline',type=int,default=900);a=p.parse_args();require(1<=a.deadline<=900,'original900s cap');a.timeout=120;a.durable_suffix_from=None;a.checkpoint_relation='selected-fault-setup-only';resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30));actor=Case(a)
    try:actor.execute();require(all(sha(ROOT/n)==h for n,h in actor.inputs.items()),'consumed host input changed');actor.report['host_sources_unchanged']=True
    except BaseException as error:actor.report.update(status='FAIL',error=repr(error));raise
    finally:actor.close()
    print(actor.report['status'],actor.report['elapsed_seconds'])
if __name__=='__main__':main()
