#!/usr/bin/env python3
"""Bounded actual Notebook21 native workbook/tutor/checker observations.

The public machine receives raw pen/UART/converter input only. Lean owns course
publication, durable Store, rasterization, grants and separately linked checking.
This is scoped synthetic native functional evidence, not realtime/RTL/physical/
protected-session/general-kernel or human-learning qualification.
"""
import argparse,filecmp,hashlib,json,os,shutil,signal,struct,subprocess,sys,time,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'conformance/lemmasim'),str(ROOT/'sim/companion/multimodal')]
from check_course_math_workflow import CourseMathWorkflow,Input,require,decode,visible_pixels
from check_live_notebook import idle
from course_pixel_oracle import course_body_matches,label_matches
from store_oracle import recover
from check_canonical_pen_pixels import expected_stroke
from lemmasim_course import frame
from lemmasim_tutor import ask_context
from fractions import Fraction
import assessment

def checked_claim_fixture(published,packet_hex):
    original=decode(published);raw=bytearray(published);packet=bytearray.fromhex(packet_hex)
    require(len(packet)==192,'complete action packet for quarantined mutation')
    span=struct.unpack_from('<Q',raw,112)[0];offset,length=span&0xffffffff,span>>32
    require(length==384 and raw[offset:offset+length]==packet_hex.encode(),'actual action anchor binding')
    struct.pack_into('<Q',packet,96,2);raw[offset:offset+length]=packet.hex().encode()
    struct.pack_into('<2Q',raw,80,0,0);crc=zlib.crc32(raw);struct.pack_into('<2Q',raw,80,crc,crc^0xffffffff)
    mutated=decode(bytes(raw));require(mutated['identity']==original['identity'] and mutated['edition']==original['edition'] and mutated['nodes']==original['nodes'],'quarantined fixture changed authored content')
    return bytes(raw),crc

def admission_fault_fixture(published,packet_hex,kind,context=None):
    """Quarantined untrusted input, never a document/Store constructor.
    Preserve the actual model body and original package bytes separately. A
    fresh guest ASK can rebind the malformed test envelope to avoid unrelated
    stale-session rejection masking the marker/visible-prefix negative.
    """
    original=decode(published);raw=bytearray(published);packet=bytearray.fromhex(packet_hex)
    require(len(packet)==192,'complete original inference packet required')
    anchor=struct.unpack_from('<Q',raw,112)[0];offset,length=anchor&0xffffffff,anchor>>32
    require(length==384 and raw[offset:offset+length]==packet_hex.encode(),'original action anchor differs')
    if context is not None:
        for field,position in [('session',8),('consent',16),('revision',24),('object',32),('sequence',40),('cutoff',48),('now',56),('deadline',64),('source',136),('edition',144),('task_id',152)]:struct.pack_into('<Q',packet,position,context[field])
        struct.pack_into('<Q',raw,32,context['sequence'])
        raw[offset:offset+length]=packet.hex().encode()
    if kind=='self-checked2':
        struct.pack_into('<Q',packet,96,2);raw[offset:offset+length]=packet.hex().encode()
    elif kind=='marker-omitted':
        marker=struct.unpack_from('<Q',raw,104)[0];start,count=marker&0xffffffff,marker>>32
        require(count==24 and raw[start:start+count]==b'lemma-tutor-assistance/2','actual new marker missing from source fixture')
        raw[start:start+count]=b' '*count
    elif kind=='prefix-omitted':
        body=struct.unpack_from('<Q',raw,248)[0];start,count=body&0xffffffff,body>>32
        claim=struct.unpack_from('<Q',packet,96)[0];expected=b'UNVERIFIED ASSISTANCE: ' if claim==0 else b'UNVERIFIED ASSISTANCE - CHECKING PENDING: '
        require(claim in (0,1) and raw[start:start+len(expected)]==expected,'actual visible prefix missing from source fixture')
        raw[start:start+len(expected)]=b' '*len(expected)
    else:raise ValueError('unknown quarantined admission fault')
    struct.pack_into('<2Q',raw,80,0,0);crc=zlib.crc32(raw);struct.pack_into('<2Q',raw,80,crc,crc^0xffffffff)
    result=decode(bytes(raw));require(result['identity']==original['identity'] and len(result['nodes'])==len(original['nodes']),'fault changed source package identity/node count')
    return bytes(raw),crc

class Workflow(CourseMathWorkflow):
    profile='lemma-silicon-dev/0.14.0'
    def launch(self,args,**kw):
        args=list(args)
        if args and args[0]=='session':
            index=args.index('--workload')+1
            require(args[index]=='notebook','unexpected inherited workload')
            args[index]='parameterized-notebook'
        return super().launch(args,**kw)
    def session(self,name,disk,fail_flush=None):
        s=super().session(name,disk,fail_flush)
        original_export=s.export
        def byte_preserving_export(label):
            require(s.inspect()['running'] is False,'allocation changes require a paused owned export')
            panel,medium=original_export(label)
            self.sparsify(medium)
            return panel,medium
        s.export=byte_preserving_export
        archive=self.directory/'consumed-host-source-root'
        if not archive.exists():
            for relative,digest in self.frozen.items():
                data=(ROOT/relative).read_bytes();require(hashlib.sha256(data).hexdigest()==digest,'consumed host source changed before archive')
                target=archive/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        return s
    def allocation_tool(self,name):
        tools=self.report.setdefault('allocation_tools',{})
        if name not in tools:
            path=Path(shutil.which(name) or '').absolute();require(path.is_file(),'missing allocation tool '+name)
            result=subprocess.run([str(path),'--version'],capture_output=True,timeout=5,check=True)
            tools[name]=dict(path=str(path),resolved_binary=str(path.resolve()),sha256=sha(path),version=result.stdout.decode().splitlines()[0])
        return tools[name]['path']
    def sparse_copy(self,source,destination):
        require(not destination.exists() and destination.is_relative_to(self.directory),'owned unused sparse destination')
        identity=sha(source);size=source.stat().st_size;require(size==256*1024*1024,'historical fixed256MiB medium remains required')
        self.tool('sparse-copy-'+destination.stem,[self.allocation_tool('cp'),'--sparse=always','--reflink=never','--',str(source),str(destination)],60)
        require(destination.stat().st_size==size and sha(destination)==identity and sha(source)==identity,'allocation-only sparse copy changed full medium bytes')
        self.report.setdefault('allocation_only',[]).append(dict(action='GNUcp sparse always; reflink never',source=str(source),destination=str(destination),bytes=size,sha256=identity,allocated_bytes=destination.stat().st_blocks*512))
    def sparsify(self,path):
        require(path.is_relative_to(self.directory) and path.is_file(),'owned paused export required for sparse allocation')
        identity=sha(path);size=path.stat().st_size;before=path.stat().st_blocks*512
        require(size==256*1024*1024,'export changed historical fixed256MiB capacity')
        self.tool('sparse-export-'+path.stem,[self.allocation_tool('fallocate'),'--dig-holes','--',str(path)],60)
        require(path.stat().st_size==size and sha(path)==identity,'allocation-only hole punching changed exported bytes')
        self.report.setdefault('allocation_only',[]).append(dict(action='fallocate dig-holes on owned paused immutable export',path=str(path),bytes_before=size,bytes_after=path.stat().st_size,sha256_before=identity,sha256_after=identity,allocated_before=before,allocated_after=path.stat().st_blocks*512))
    def phase(self,s,name,cap,predicate,quantum=1_000_000):
        start=time.monotonic();first=s.inspect()['machine']['cycle']
        while True:
            self.check_sources();state=s.inspect()['machine'];rows=self.rows(s)
            require(not state['finished'] and not any(r[0] in (0x41f,0x424,0xd4,0xf4) for r in rows),'real guest fault '+name+repr(rows[-8:]))
            used=state['cycle']-first
            require(0<=used<=cap and self.cycles<=4_000_000_000 and time.monotonic()<self.deadline and time.monotonic()-start<=600,'original phase/whole limit '+name)
            if predicate(state):break
            require(used<cap,'original phase clock budget '+name)
            s.run(min(quantum,cap-used));after=s.inspect()['machine']['cycle'];require(after>state['cycle'],'no actual machine progress');self.cycles+=after-state['cycle']
        row=dict(name=name,initial_cycle=first,final_cycle=state['cycle'],execution_units=used,host_seconds=time.monotonic()-start,cycle_limit=cap,host_limit=600)
        self.report['phases'].append(row);self.progress();print(json.dumps(row),flush=True);return state
    def tool(self,label,argv,timeout=180):
        self.commands.write(json.dumps(argv)+'\n');self.commands.flush()
        result=subprocess.run(argv,cwd=ROOT,capture_output=True,timeout=min(timeout,self.deadline-time.monotonic()))
        (self.directory/(label+'.log')).write_bytes(result.stdout+result.stderr)
        require(result.returncode==0,'actual command failed '+label+'; original log retained')
    def uart_bytes(self,s,packet):
        observed=s.inspect();u=observed['machine']['devices']['uart_ingress']
        require(observed['running'] is False and u['enabled'] is True and len(packet)<=65536-u['pending'],'actual paused rawUART capacity')
        for n in range(0,len(packet),4096):s.control(dict(action='inject',kind='uart',cycle=observed['machine']['cycle'],hex=packet[n:n+4096].hex()))
    def installed(self,s,transaction,identity,edition):
        return any(r[0]==0x4b1 and r[1]==1 and r[2]==transaction and r[3]==identity|(edition<<16) for r in self.rows(s))
    def diagnostic(self,s,stream):
        for i in range(8):s.control(dict(action='inject',kind='multimodal',cycle=s.inspect()['machine']['cycle'],words=[i,100+i,10,0]))
        self.click(s,stream,'explicit-five-second-local-capture',450,140)
        self.phase(s,'all-eight-converters-guest-completions',100_000_000,lambda st:all(any(r[0]==0x711 and r[1]==i for r in self.rows(s)) for i in range(8)))
        prior_saved=sum(r[0]==0x421 for r in self.rows(s));prior_pending=sum(r[0]==0x423 for r in self.rows(s));stream.tick=s.inspect()['machine']['ticks']+10000;first=len(stream.events);stream.stroke('raw-ink-during-capture',1,1,3,1800);self.diagnostic_samples=stream.events[first:];s.admit(self.diagnostic_samples)
        panel=self.directory/'during-capture-ink.ppm';points=expected_stroke(self.diagnostic_samples)[1]
        def pen_feedback(st):
            if not idle(st) or not self.saved(s) or sum(r[0]==0x421 for r in self.rows(s))<=prior_saved:return False
            s.control({'action':'panel','path':str(panel)});w,_,pixels=visible_pixels(panel)
            return all(pixels[(y*w+x)*3:(y*w+x)*3+3]==bytes(3) for x,y in points)
        self.phase(s,'actual-Save-pending-with-raw-capture',100_000_000,lambda st:st['ticks']>=self.diagnostic_samples[-1][1] and sum(r[0]==0x423 for r in self.rows(s))>prior_pending and sum(r[0]==0x421 for r in self.rows(s))==prior_saved,quantum=10_000)
        pending=s.inspect()['machine'];old_mute=sum(r[0]==0x712 and r[1]==1 for r in self.rows(s));first_control=len(stream.events)
        # Direct ordinary raw samples at strictly increasing source ticks. The
        # selected sample spacing is independent of the Save/controller state.
        stream.tick=pending['ticks']+1;stream.sample(570,140,2048,True);stream.sample(570,140,0,False);s.admit(stream.events[first_control:])
        self.phase(s,'local-MUTE-admitted-during-Save',50_000_000,lambda st:sum(r[0]==0x712 and r[1]==1 and r[2]==0 for r in self.rows(s))>old_mute)
        self.report['mute_during_Save']={'admission_cycle':pending['cycle'],'admission_ticks':pending['ticks'],'Saved_count_at_admission':prior_saved,'raw_samples':[list(x) for x in stream.events[first_control:]],'completion_cycle':s.inspect()['machine']['cycle'],'scope':'local mute control admitted while actual Save pending; digital control only, no acoustic onset claim'}
        self.phase(s,'raw-pen-and-durable-Save-during-admitted-capture',150_000_000,pen_feedback)
        before=s.inspect()['machine'];self.click(s,stream,'local-EEG-revoke',730,140)
        start=s.inspect()['machine']['cycle'];old=[r for r in self.rows(s) if r[0]==0x711 and r[1]==0];other=len([r for r in self.rows(s) if r[0]==0x711 and r[1]==1])
        for i in range(32):s.control(dict(action='inject',kind='multimodal',cycle=s.inspect()['machine']['cycle'],words=[0,200+i,10,1]))
        s.run(5_000_000);self.cycles+=s.inspect()['machine']['cycle']-start
        require([r for r in self.rows(s) if r[0]==0x711 and r[1]==0]==old,'EEG completions survived actual local revocation')
        require(len([r for r in self.rows(s) if r[0]==0x711 and r[1]==1])>other,'revocation test did not leave another authorized stream running')
        state=s.inspect()['machine'];self.report['local_diagnostic']={'prior_state':before['devices']['multimodal'],'after_revoke_flood':state['devices']['multimodal'],'injected_revoked_stimuli':32,'payload_wipe':'source/audit invariant; no unauthorized RAM/raw snapshot exported','no_raw_upload':'guest711 carries zero value; local-only permission'}
        self.click(s,stream,'local-mute',570,140)
        self.click(s,stream,'stop-remaining-local-capture',450,140)
    def tasks(self,s):
        out=self.directory/'runtime-tasks';out.mkdir();cases=[]
        fixtures=[(1,0,[2,7,3,5],None,8),(1,0,[9,11,7,13],None,8),(1,0,[2,7,3,5],(32,35),8),(2,0,[2,3,1,4],None,8),(2,0,[11,2,3,7],(14,84,33),8),(1,0,[2,7,3,5],None,0),(1,1,[2,7,3,5],None,8)]
        expected=[1,1,2,1,2,5,4]
        for request,(kind,assumptions,v,answer,budget) in enumerate(fixtures,1):
            if kind==1:
                q=Fraction(v[0],v[1])+Fraction(v[2],v[3]);n,den=answer or (q.numerator,q.denominator);coeff=[0,0,0]
            else:
                n,den=0,1;coeff=list(answer or (v[1]*v[3],v[0]*v[3]+v[1]*v[2],v[0]*v[2]))
            words=[2,1,3,12,30+request,9,kind,assumptions,*v,n,den,*coeff,budget,request,0,41,7,0,0]
            path=out/f'request{request}.bin';path.write_bytes(struct.pack('<24Q',*words))
            before=s.inspect()['machine']['cycle'];destination=out/f'actual{request}'
            self.tool('runtime-check'+str(request),[sys.executable,str(ROOT/'scripts/lemmasim_parameterized.py'),'--session-dir',str(s.directory),'--request',str(path),'--work-dir',str(destination),'--expected-outcome',str(expected[request-1])],120)
            result=json.loads((destination/'result.json').read_text());require(result['status']=='CHECKER_COMPLETED','actual isolated IPC absent');self.cycles+=s.inspect()['machine']['cycle']-before;cases.append(result['completion'])
        self.report['runtime_parameterized_checking']={'cases':cases,'expected':expected,'oracle':'independent Python Fraction/coefficient convolution','scope':'complete independently scoped runtime submissions; does not change Notebook Verified state','single_guest_boot':True}
    def later_assessment(self,s):
        out=self.directory/'later-independent';out.mkdir()
        begin=s.inspect()['machine'];unlock=begin['ticks']+1_000_000
        self.report['independent_delay']={'source_clock':'guestmtime/10MHz','start_tick':begin['ticks'],'unlock_tick':unlock,'duration_ticks':1_000_000,'duration_seconds':0.1,'scope':'short synthetic software delay, not qualified human retention'}
        self.phase(s,'predeclared-short-independent-delay-after-Save',20_000_000,lambda st:st['ticks']>=unlock)
        c=self.assessment_plan;v=c['operands'];coeff=[v[1]*v[3],v[0]*v[3]+v[1]*v[2],v[0]*v[2]]
        words=[2,1,3,12,88,9,2,0,*v,0,1,*coeff,8,8,0,42,8,0,0];path=out/'request8.bin';path.write_bytes(struct.pack('<24Q',*words))
        before=s.inspect()['machine']['cycle'];dest=out/'actual8'
        self.tool('later-independent-actual-checker',[sys.executable,str(ROOT/'scripts/lemmasim_parameterized.py'),'--session-dir',str(s.directory),'--request',str(path),'--work-dir',str(dest),'--expected-outcome','1'],120)
        self.cycles+=s.inspect()['machine']['cycle']-before
        assistance={'tutor_during_challenge':False,'solution_exposure':False,'prior_delivered_assistance':self.report['tutor_delivery'],'submission_origin':'SYNTHETIC_SOFTWARE_FRACTION_COEFFICIENT_ORACLE'}
        scored=assessment.score(c,{'coefficients':coeff},s.inspect()['machine']['ticks'],assistance)
        require(scored['score']==1,'separate independent-assessment authority disagrees with actual bounded checker')
        self.report['later_independent_assessment']={'plan':c,'actual_checker':json.loads((dest/'result.json').read_text())['completion'],'authority_result':scored,'qualification':'synthetic software submission/short delay only; no measured learner capability or educational benefit'}
    def positive_actions(self,s,stream):
        deliveries=[];last_package=None;last_packet=None
        questions=[('hint','Please give a small hint for adding 9/11 and 7/13 without giving the final answer.',(9,11,7,13)),
            ('worked-example','Please give a complete brief worked example of adding 5/8 and 11/19.',(5,8,11,19)),
            ('counterexample','Give a counterexample using 17/23 and 13/29 to show why adding denominators is not fraction addition.',(17,23,13,29))]
        for index,(requested,question,values) in enumerate(questions,1):
            self.click(s,stream,'student-ASK-'+str(index)+'-'+requested,870,140)
            context=ask_context((s.directory/'uart-0.bin').read_bytes());out=self.directory/('actual-tutor-'+str(index))
            args=[sys.executable,str(ROOT/'scripts/lemmasim_tutor.py'),'--session-dir',str(s.directory),'--work-dir',str(out),'--question',question,'--kind','rational-sum']
            for flag,value in zip(('a','b','c','d'),values):args.extend(['--'+flag,str(value)])
            args.append('--inject');self.tool('actual-inference-publication-'+str(index),args,180)
            proposal=json.loads((out/'proposal.json').read_text());raw=(out/'assistance.lcp').read_bytes();package=decode(raw);sequence=context['sequence']
            require(proposal['action']==requested,'actual inference did not supply the explicitly requested pedagogical action; retain real response')
            self.phase(s,'guest-Store-commits-action-'+str(index),150_000_000,lambda st:idle(st) and self.installed(s,sequence,60001,sequence))
            prior_good=sum(r[0]==0x724 and r[1]==0 for r in self.rows(s));prior_accepted=sum(r[0]==0x725 for r in self.rows(s))
            self.click(s,stream,'guest-LOAD-executes-'+str(index)+'-'+requested,970,140,text=package['nodes'][0]['body'])
            require(sum(r[0]==0x724 and r[1]==0 for r in self.rows(s))==prior_good+1 and sum(r[0]==0x725 for r in self.rows(s))==prior_accepted+1 and any(r[0]==0x725 and r[1]==sequence for r in self.rows(s)),'fresh actual guest gate/acceptance absent')
            panel,medium=s.export('actual-tutor-'+str(index)+'-presented');require(course_body_matches(panel,package['nodes'][0]['body']),'independent all-body pixel oracle differs')
            _,_,records=recover(medium.read_bytes());key=(1,4850376798678024192|(60001<<32)|sequence)
            require(key in records and records[key].payload==raw,'actual immutable Store assistance bytes differ')
            deliveries.append(dict(action=proposal['action'],question=question,parameters=values,package_sha256=hashlib.sha256(raw).hexdigest(),model=proposal.get('inference'),context=context,body=package['nodes'][0]['body'],actual724=True,actual725=True,complete_body_pixels=True,paper_completed=s.inspect()['machine']['panel_completed'],audio='not requested/no audio grant; no audible claim',security='owner-local integrity-only development transport'))
            self.report['tutor_delivery']={'deliveries':deliveries,'single_guest_boot':True,'model_inference_and_presentation_times_separate':True,'mathematical_authority':'UNVERIFIED_ASSISTANCE'}
            last_package,last_packet=raw,proposal['packet_hex']
        require(len({r['action'] for r in deliveries})==3,'differing actual executed actions absent')
        return last_package,last_packet
    def corrupt_checked_claim(self,s,stream,published,packet_hex):
        self.click(s,stream,'fresh-ASK-for-untrusted-claim-negative',870,140)
        context=ask_context((s.directory/'uart-0.bin').read_bytes());out=self.directory/'negative-self-checked2';out.mkdir()
        raw,crc=admission_fault_fixture(published,packet_hex,'self-checked2',context)
        (out/'original-model.lcp').write_bytes(published);(out/'quarantined-self-checked2.lcp').write_bytes(raw);(out/'guest-context.json').write_text(json.dumps(context,indent=2)+'\n')
        seq=context['sequence'];self.uart_bytes(s,frame(1,60001,seq,len(raw),seq,crc)+raw)
        self.phase(s,'guest-Store-installs-adversarial-unverified-data',150_000_000,lambda st:idle(st) and self.installed(s,seq,60001,seq))
        accepted=sum(r[0]==0x725 for r in self.rows(s));old=sum(r[0]==0x724 and r[1]==14 for r in self.rows(s));self.raw(s,stream,970,140)
        self.phase(s,'guest-rejects-untrusted-checked-claim2',100_000_000,lambda st:idle(st) and sum(r[0]==0x724 and r[1]==14 for r in self.rows(s))>old)
        require(sum(r[0]==0x725 for r in self.rows(s))==accepted,'untrusted claim2 acquired acceptance')
        self.report['untrusted_claim_negative']={'fixture_sha256':hashlib.sha256(raw).hexdigest(),'origin':'QUARANTINED_MUTATION_OF_ACTUAL_MODEL_PACKAGE_WITH_ACTUAL_GUEST_CONTEXT','package_CRC32':crc,'actual_guest_reason':14,'new_accepted_actions':0,'scope':'guest gate rejection of mathematically checked self-claim; no publisher rejection inferred as guest evidence'}
    def admission_negatives(self,s,stream,published,packet_hex):
        results=[]
        for kind,reason in [('marker-omitted',18),('prefix-omitted',19)]:
            self.click(s,stream,'fresh-ASK-for-'+kind,870,140)
            context=ask_context((s.directory/'uart-0.bin').read_bytes());raw,crc=admission_fault_fixture(published,packet_hex,kind,context)
            out=self.directory/('negative-'+kind);out.mkdir();(out/'original-model.lcp').write_bytes(published);(out/'quarantined-frame.lcp').write_bytes(raw);(out/'guest-context.json').write_text(json.dumps(context,indent=2)+'\n')
            sequence=context['sequence'];self.uart_bytes(s,frame(1,60001,sequence,len(raw),sequence,crc)+raw)
            self.phase(s,'guest-Store-installs-'+kind,150_000_000,lambda st:idle(st) and self.installed(s,sequence,60001,sequence))
            accepted=sum(r[0]==0x725 for r in self.rows(s));old=sum(r[0]==0x724 and r[1]==reason for r in self.rows(s));self.raw(s,stream,970,140)
            self.phase(s,'guest-rejects-'+kind,100_000_000,lambda st:idle(st) and sum(r[0]==0x724 and r[1]==reason for r in self.rows(s))>old)
            require(sum(r[0]==0x725 for r in self.rows(s))==accepted,'untrusted '+kind+' acquired acceptance')
            results.append(dict(kind=kind,fixture_sha256=hashlib.sha256(raw).hexdigest(),CRC32=crc,actual_guest_reason=reason,new_accepted_actions=0,source='QUARANTINED_EXISTING_MODEL_BYTES_WITH_ACTUAL_GUEST_CONTEXT',context=context))
        self.report['admission_negatives']=results
    def execute(self):
        self.assessment_plan=assessment.challenge('fixed-native-assessment007','synthetic-heldout-learner','synthetic-heldout-session','transfer')
        (self.directory/'independent-plan-before-inference.json').write_text(json.dumps({'plan':self.assessment_plan,'virtual_delay_after_Save_ticks':1_000_000,'source_clock':'guestmtime/10MHz','delay_seconds':0.1,'qualification':'SYNTHETIC_SOFTWARE_ONLY'},indent=2)+'\n')
        package=self.args.package[0].read_bytes();p=decode(package);require(p['identity']==1 and p['edition']==3,'fresh original edition3 package required')
        _,_,original=recover(self.args.disk.read_bytes());require((1,5785718146287534081) not in original,'input must not contain a staged workspace')
        disk=self.directory/'private.raw';self.sparse_copy(self.args.disk,disk);s=self.session('first',disk)
        self.report.update(scope=__doc__,original_input_sha256=sha(self.args.disk),observer_sha256=sha(Path(__file__)),aggregate_cap=4_000_000_000)
        self.phase(s,'cold-native-Ready-and-sole-installer',1_000_000_000,lambda st:idle(st) and st['panel_completed']>0 and any(r[0]==0x420 for r in self.rows(s)) and any(r[0]==0x72d for r in self.rows(s)))
        self.uart_bytes(s,frame(1,1,3,len(package),1001,struct.unpack_from('<Q',package,80)[0])+package)
        self.phase(s,'guest-validates-and-durably-installs-original-course',150_000_000,lambda st:idle(st) and self.installed(s,1001,1,3))
        stream=Input(1650,2200,s.inspect()['machine']['ticks']+10000,100000,0)
        self.click(s,stream,'open-fresh-workbook-chooser',320,140)
        self.click(s,stream,'choose-edition2',168,670);self.click(s,stream,'choose-edition3',168,670)
        self.click(s,stream,'load-original-edition3',264,670,text=p['nodes'][0]['body'])
        self.click(s,stream,'original-node2',72,650,text=p['nodes'][1]['body']);self.click(s,stream,'original-exercise3',72,650,text=p['nodes'][2]['body'])
        self.click(s,stream,'use-original-source-anchored-exercise',360,650,mutation=True)
        self.tasks(s)
        self.diagnostic(s,stream)
        negative_source,negative_packet=self.positive_actions(s,stream)
        # Repeat the same completed proposal through its ordinary LOAD control.
        accepted=sum(r[0]==0x725 for r in self.rows(s));old_errors=sum(r[0]==0x454 for r in self.rows(s));self.raw(s,stream,970,140)
        self.phase(s,'repeated-completed-assistance-rejected',100_000_000,lambda st:idle(st) and any(r[0]==0x724 and r[1]==5 for r in self.rows(s)))
        require(sum(r[0]==0x725 for r in self.rows(s))==accepted,'completed tutor action repeated')
        self.corrupt_checked_claim(s,stream,negative_source,negative_packet)
        self.admission_negatives(s,stream,negative_source,negative_packet)
        # Ordinary original pen samples remain useful after the rejected actions.
        stream.tick=s.inspect()['machine']['ticks']+10000;first=len(stream.events);stream.stroke('post-tutor-raw-ink',1,1,3,1900);samples=stream.events[first:];s.admit(samples)
        inkpanel=self.directory/'ink-observed.ppm';points=expected_stroke(samples)[1]
        def ink(st):
            if not idle(st):return False
            s.control({'action':'panel','path':str(inkpanel)});w,_,pixels=visible_pixels(inkpanel)
            return all(pixels[(y*w+x)*3:(y*w+x)*3+3]==bytes(3) for x,y in points)
        self.phase(s,'post-error-raw-pen-feedback',300_000_000,ink)
        self.click(s,stream,'explicit-Save-after-tutor-and-ink',1370,64,mutation=True)
        # The real rejected course admission returns to ordinary notebook mode.
        # Do not toggle COURSE here: doing so would reopen a view before cold.
        home,saved=s.export('actual-Saved-home');_,seq,records=recover(saved.read_bytes())
        chunks=[]
        for record in records.values():
            b=record.payload
            if len(b)>=128 and struct.unpack_from('<3Q',b)==(0x314b4e49414d454c,1,3):
                count=struct.unpack_from('<Q',b,48)[0]
                if len(b)==128+count*72:chunks.append([struct.unpack_from('<9Q',b,128+72*i) for i in range(count)])
        require(chunks.count(samples)==1 and chunks.count(self.diagnostic_samples)==1,'original raw pen fields not durably retained exactly once')
        self.report['pen_Save']={'samples':[list(x) for x in samples],'contact_pixels':len(points),'durable_sequence':seq,'Save_receipts':[r for r in self.rows(s) if r[0]==0x421]}
        self.later_assessment(s)
        s.close();self.sessions.remove(s);coldDisk=self.directory/'cold-input.raw';self.sparse_copy(saved,coldDisk);c=self.session('cold',coldDisk)
        self.phase(c,'independent-cold-native-Ready',1_000_000_000,lambda st:idle(st) and st['panel_completed']>0 and any(r[0]==0x420 for r in self.rows(c)))
        coldpanel,coldmedium=c.export('cold-Ready');require(filecmp.cmp(saved,coldmedium,shallow=False),'independent all durable bytes changed')
        require(visible_pixels(home)==visible_pixels(coldpanel),'independent all cold home pixels changed')
        require(not any(r[0] in (0x724,0x725) for r in self.rows(c)),'cold replay repeated live tutor presentation')
        self.report.update(status='PASS_SCOPED_NATIVE_MULTIMODAL_WORKBOOK',whole_execution_units=self.cycles,independent_cold={'all_durable_bytes':saved.stat().st_size,'all_pixels':1650*2200,'no_live_tutor_repeat':True},unexecuted=['guest PCM tutor delivery','protected live session','raw imaging/ToF/photon flow qualification','sealed/checkpoint continuation on0.14','later learner educational benefit','realtime economy performance'])

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('disk','package','native-bundle','work-dir'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.disk=a.disk.resolve();a.package=[a.package.resolve()];a.native_bundle=str(a.native_bundle.resolve());a.guest_build=None;a.guest_source_root=None;a.timeout=120;a.deadline=1800;a.checkpoint_relation='independent cold only';a.durable_suffix_from=None
    if a.work_dir.exists() or not a.work_dir.resolve().is_relative_to(ROOT/'build'):p.error('unused retained build output required')
    actor=Workflow(a)
    try:actor.execute()
    except BaseException as e:actor.report.update(status='FAIL',error=repr(e));raise
    finally:
        actor.close()
        actor.report['retained_outputs']={str(path.relative_to(actor.directory)):{'bytes':path.stat().st_size,'sha256':sha(path)} for path in sorted(actor.directory.rglob('*')) if path.is_file() and path.name not in ('result.json','progress.json')}
        (actor.directory/'result.json').write_text(json.dumps(actor.report,default=str,indent=2)+'\n')
    print(actor.report['status'],flush=True)
if __name__=='__main__':raise SystemExit(main())
