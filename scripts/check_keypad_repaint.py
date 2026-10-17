#!/usr/bin/env python3
"""Qualify static keypad reuse, raw overdraw repair and independent cold ink recovery.

All input is real raw pen traffic. Independent exported bytes and pixels are
observers; they never supply guest documents, results or durability receipts.
The inherited complete number-entry case retains its original bounds.
"""
import argparse,filecmp,json,os,resource,shutil,struct
from pathlib import Path
from check_number_entry_workflow import NumberEntryWorkflow
from check_course_math_workflow import Input,decode,require,visible_pixels,T,sha
from course_pixel_oracle import annotation_pixels,label_matches
from number_pad_reference import pad_matches

class KeypadRepaintWorkflow(NumberEntryWorkflow):
    def raw(self,s,stream,x,y):
        if not hasattr(self,'streams'):self.streams={}
        self.streams[s]=stream
        return super().raw(s,stream,x,y)

    def execute(self):
        super().execute()
        self.report.update(status='RUNNING',schema='lemma-keypad-repaint-workflow/1',
            number_entry_prefix_cycles=self.cycles,number_entry_prefix_phases=len(self.report['phases']),
            extra_scope='Raw stroke crosses static keypad; next actual key repairs it; closing reveals retained ink; independent CPU cold recovers all acknowledged bytes and pixels')
        self.progress()
        s=self.sessions[0];stream=self.streams[s]
        before=self.checkpoint_record(s,'before-pad-overdraw')
        baseline=visible_pixels(before[0]);old=s.inspect()['machine']
        require(before[3]['document']['answer'][:2]==[5,6] and before[3]['document']['outcome']==1,'original verified5/6 predecessor required')
        require(len(stream.events)==4 and stream.events[-2][5]==8,'expected single cold COURSE plus real disconnect/resync ingress')
        stream.tick=old['ticks']+10000;first=len(stream.events)
        stream.sample(430,380,2048,True);stream.sample(600,240,2048,True);stream.sample(600,240,0,False)
        ingress=stream.events[first:];s.admit(ingress)
        # The known flags8 loss advances the controller epoch, retains next
        # sequence3, and rejects its following resync release. These exact
        # identities are declared before examining the persisted stroke.
        controller=[(row[0]-2,*row[1:8],2) for row in ingress]
        require([r[0]for r in controller]==[3,4,5],'new ingress identity declaration differs')
        oldacks=len([r for r in self.rows(s)if r[0]==1057])
        self.phase(s,'raw-stroke-overdraws-keypad-Saved',300000000,
            lambda st:self.idle(st)and self.saved(s)and len([r for r in self.rows(s)if r[0]==1057])>oldacks and st['ticks']>=ingress[-1][1]+200000)
        damaged=self.checkpoint_record(s,'pad-overdraw')
        require(damaged[2]==before[2],'raw ink changed mathematics/workspace bytes')
        samples=[];brushes=[]
        for r in damaged[4].values():
            if len(r.payload)>=128 and struct.unpack_from('<Q',r.payload)[0]==3552018807646930252 and struct.unpack_from('<Q',r.payload,16)[0]==3:
                brushes.append(struct.unpack_from('<Q',r.payload,56)[0]);count=struct.unpack_from('<Q',r.payload,48)[0]
                samples.extend(struct.unpack_from('<9Q',r.payload,128+i*72)for i in range(count))
        require(all(tuple(r)in samples for r in controller)and brushes and all(b==512 for b in brushes),'actual durable raw fields/brush differ from declared controller input')
        expected=annotation_pixels(baseline,controller,512);actual=visible_pixels(damaged[0])
        require(actual[:2]==expected[:2]and actual[2][160*1650*3:]==expected[2][160*1650*3:],'complete writing-plane pixels differ from independent raw stroke')
        require(not pad_matches(damaged[0],False),'stroke did not exercise static pad damage')
        self.click(s,stream,'numeric-0-after-raw-overdraw',640,340,mutation=True)
        repaired=self.checkpoint_record(s,'pad-repaired')
        require(repaired[3]['document']['answer'][:2]==[5,60]and repaired[3]['document']['outcome']==0,'actual key did not edit selected denominator and invalidate evidence')
        T.observe_transition(damaged[3],repaired[3],'edit')
        require(pad_matches(repaired[0],False),'next key reused damaged keypad pixels')
        require(label_matches(repaired[0],'UNCHECKED',24,260)and label_matches(repaired[0],'N 05 D 60 C0 00 C1 00 C2 00',24,200),'edited numbers/current applicability pixels differ')
        _,_,rp=visible_pixels(repaired[0]);ep=expected[2]
        for y in range(160,2200):
            for x in range(1650):
                if (x<416 and (y<320 or 640<=y<760))or(448<=x<832 and y<360):continue
                at=(y*1650+x)*3
                require(rp[at:at+3]==ep[at:at+3],'key repair changed unrelated controller pixel')
        _,tick=self.raw(s,stream,320,140);old=s.inspect()['machine']['panel_completed']
        self.phase(s,'close-course-reveals-underlying-pad-ink',500000000,
            lambda st:self.idle(st)and self.saved(s)and st['panel_completed']>old and st['ticks']>=tick+25000000)
        closed=self.checkpoint_record(s,'overdraw-closed')
        original=visible_pixels(self.directory/'closed-final.ppm');underlying=annotation_pixels(original,controller,512);observed=visible_pixels(closed[0])
        require(observed[:2]==underlying[:2]and observed[2][160*1650*3:]==underlying[2][160*1650*3:],'course closure lost raw ink beneath repaired pad')
        s.close();self.sessions.remove(s)
        disk=self.directory/'overdraw-cold-input.raw';shutil.copyfile(closed[1],disk)
        cold=self.session('overdraw-cold',disk);require(cold.inspect()['machine']['cycle']==0,'new independent CPU must start atreset')
        p=self.directory/'overdraw-cold-observed.ppm'
        def recovered(st):
            if not self.idle(st)or not any(r[0]==1056 for r in self.rows(cold)):return False
            cold.control({'action':'panel','path':str(p)})
            return visible_pixels(p)==observed
        self.phase(cold,'overdraw-independent-cold-all-pixels',1000000000,recovered)
        cp,cm=cold.export('overdraw-cold-final')
        require(visible_pixels(cp)==observed and filecmp.cmp(cm,closed[1],shallow=False),'independent cold lost acknowledged pixels/medium')
        require({k:r.payload for k,r in self.record(cm)[2].items()}=={k:r.payload for k,r in closed[4].items()},'cold lost acknowledged objects')
        stream=Input(1650,2200,cold.inspect()['machine']['ticks']+10000,100000,0)
        body=decode(self.packages[0])['nodes'][2]['body']
        panel=self.click(cold,stream,'cold-reopen-after-pad-repair',320,140,text=body)
        require(pad_matches(panel,False),'cold did not reconstruct keypad')
        reopened=self.checkpoint_record(cold,'overdraw-cold-reopened')
        require(reopened[2]==closed[2]and filecmp.cmp(reopened[1],closed[1],shallow=False),'reopen changed acknowledged workspace/medium')
        require(sha(self.args.disk)==self.original_medium_sha256,'original input medium changed')
        self.report.update(status='PASS_GUEST_KEYPAD_STATIC_DIRTY_INK_COLD',raw_controller_samples=controller,
            pad_overdraw_observed=True,next_key_reconstructed_pad=True,retained_ink_under_overlay=True,
            independent_extra_cold={'all_controller_pixels_exact':True,'all_medium_bytes_exact':True,'all_objects_exact':True})

def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--disk',type=Path,required=True);p.add_argument('--package',action='append',type=Path,required=True)
    p.add_argument('--native-bundle',required=True);p.add_argument('--guest-build',required=True)
    p.add_argument('--guest-source-root',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True)
    a=p.parse_args();a.disk=a.disk.resolve();a.package=[x.resolve()for x in a.package]
    require(not a.work_dir.exists(),'unused output required');a.timeout=120;a.deadline=900;a.checkpoint_relation='independent cold only';a.durable_suffix_from=None
    os.environ['LEAN_NUM_THREADS']='2';resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30))
    actor=KeypadRepaintWorkflow(a)
    try:actor.execute()
    except BaseException as e:actor.report.update(status='FAIL',error=repr(e));raise
    finally:actor.close()
    print(actor.report['status'],actor.cycles,actor.report['elapsed_seconds'])
if __name__=='__main__':main()
