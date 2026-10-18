#!/usr/bin/env python3
"""Source-bound host/Lean companion policies, independent assessment and real
optional owner-local inference. This is component evidence, not a guest workflow.
"""
import argparse,hashlib,json,os,random,struct,subprocess,sys,time
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sim/companion/multimodal'))
import assessment,policy,protected,tutor

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def expect(c,message):
    if not c:raise ValueError(message)
def rejects(call,message):
    try:call()
    except (ValueError,KeyError):return
    raise ValueError(message)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--inference',action='store_true');p.add_argument('--model',default='qwen2.5:7b');p.add_argument('--espeak',type=Path);a=p.parse_args();out=a.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'build'):p.error('unused ignored output required')
    out.mkdir(parents=True);started=time.monotonic()
    sources=[*sorted((ROOT/'sim/companion/multimodal').glob('*.py')),*sorted((ROOT/'Lemma/Multimodal').glob('*.lean')),ROOT/'tests/multimodal/Policies.lean',ROOT/'tests/multimodal/TutorClaims.lean',ROOT/'tests/multimodal/TutorAnnotations.lean',Path(__file__)]
    report={'status':'FAIL','scope':__doc__,'commands':[],'sources':{str(p.relative_to(ROOT)):sha(p) for p in sources}}
    try:
        rng=random.Random(72820);vectors=[]
        for _ in range(40):
            x,b,y,d=[rng.randint(1,97) for _ in range(4)];q=Fraction(x,b)+Fraction(y,d)
            for n,den,expected in [(q.numerator,q.denominator,1),(q.numerator+1,q.denominator,2)]:vectors.append([1,0,x,b,y,d,n,den,0,0,0,8,expected])
        for _ in range(40):
            x,b,y,d=[rng.randint(1,97) for _ in range(4)];coeff=[0,0,0]
            for i,left in enumerate([b,x]):
                for j,right in enumerate([d,y]):coeff[i+j]+=left*right
            for delta,expected in [(0,1),(1,2)]:vectors.append([2,0,x,b,y,d,0,1,coeff[0]+delta,coeff[1],coeff[2],8,expected])
        vectors.extend([[3,0,1,2,3,4,0,1,0,0,0,8,4],[1,1,1,2,3,4,0,1,0,0,0,8,4],[1,0,1,0,3,4,0,1,0,0,0,8,2],[1,0,1,2,3,4,0,1,0,0,0,0,5]])
        vectorfile=out/'independent-task-vectors.txt';vectorfile.write_text(''.join(' '.join(map(str,v))+'\n' for v in vectors))
        env={**os.environ,'LEMMA_TASK_VECTORS':str(vectorfile)}
        def command(label,argv):
            result=subprocess.run(argv,cwd=ROOT,env=env,capture_output=True,timeout=180)
            (out/(label+'.log')).write_bytes(result.stdout+result.stderr);report['commands'].append({'argv':argv,'returncode':result.returncode})
            if result.returncode:raise ValueError('actual command failed '+label)
            return result.stdout.decode()
        command('elaborate',['lake','build','Lemma.Multimodal.Parameterized','Lemma.Multimodal.TutorAction','Lemma.Multimodal.ProtectedSession','Lemma.Multimodal.TutorPackage'])
        expect('MULTIMODAL_POLICIES:PASS' in command('lean-policies',['lake','env','lean',str(ROOT/'tests/multimodal/Policies.lean')]),'missing actual Lean policy outcomes')
        expect('TUTOR_CLAIM_KINDS:PASS' in command('lean-tutor-claims',['lake','env','lean',str(ROOT/'tests/multimodal/TutorClaims.lean')]),'unknown mathematical claim class admitted')
        expect('TUTOR_ANNOTATIONS:PASS' in command('lean-tutor-annotations',['lake','env','lean',str(ROOT/'tests/multimodal/TutorAnnotations.lean')]),'guest-visible annotation or dedicated marker policy failed')
        #Official independent published vectors, not this producer's tags.
        key=bytes.fromhex('85d6be7857556d337f4452fe42d506a80103808afb0db2fd4abff6af4149f51b')
        expect(protected.poly1305(key,b'Cryptographic Forum Research Group').hex()=='a8061dc1305136c6c22b8baf0c0127a9','host RFC8439 Poly1305')
        expect(protected.hkdf(bytes(range(13)),b'\x0b'*22,bytes(range(240,250))).hex()=='3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf','host RFC5869 HKDF')
        key=bytes(range(32));left=protected.Session(key,'tablet',1,2,3,4,5,True,b'a'*32);right=protected.Session(key,'companion',1,2,3,4,5,True,b'b'*32)
        left.accept(right.offer());right.accept(left.offer())
        for _ in range(8):left.enqueue(3,4,7,1,10,11,b'archive',True)
        rejects(lambda:left.enqueue(3,4,7,1,10,11,b'overflow',True),'unbounded channel')
        left.enqueue(0,0,7,1,11,12,b'mute')
        frame=left.next_packet();expect(right.receive(frame,7)['payload']==b'mute','bulk delayed control')
        rejects(lambda:right.receive(frame,7),'authenticated replay accepted')
        damaged=bytearray(left.next_packet());damaged[-1]^=1
        rejects(lambda:right.receive(bytes(damaged),7,True),'forged packet accepted')
        #Bad tag does not consume rx; the real unmodified sequence2 still works.
        damaged[-1]^=1;expect(right.receive(bytes(damaged),7,True)['payload']==b'archive','forgery damaged receive frontier')
        old=left.next_packet();rejects(lambda:right.receive(old,8,True),'revoked payload accepted')
        left.cancel_queued();left.enqueue(0,1,8,1,12,13,b'notebook continues');expect(right.receive(left.next_packet(),8)['payload']==b'notebook continues','revocation blocked other streams')
        left.tx=protected.MAX_SEQUENCE;left.enqueue(0,1,8,1,12,13,b'exhausted')
        rejects(left.next_packet,'nonce exhaustion wrapped')
        rejects(lambda:protected.Session(key,'tablet',1,2,3,4,5,False,b'c'*32),'deterministic live entropy admitted')
        report['protected_session']={'status':'PASS_HOST_COMPONENT','receipt':right.receipt(),'limits':'8packets/channel;4channels;4096payload;32streams','target_transport_integration':'NOT_QUALIFIED'}
        rows=policy.fixture();model=policy.train(rows);(out/'synthetic-policy.json').write_text(json.dumps(model,sort_keys=True,indent=2)+'\n')
        choice,receipt=policy.infer(model,{'history':[{'outcome':'INVALID'}]});expect(choice in policy.ACTIONS,'missing learned inference')
        rejects(lambda:policy.train([{**rows[0],'split':'held-out'}]),'held-out data used for training')
        results=[]
        for family in assessment.FAMILIES:
            c=assessment.challenge('fixed-before-policy','held-out-learner','held-out-session',family)
            rejects(lambda:assessment.score(c,{},c['unlock_tick']-1,{}),'assessment delay ignored')
            v=c['operands']
            if c['kind']=='rational':q=Fraction(v[0],v[1])+Fraction(v[2],v[3]);submission={'answer':[q.numerator,q.denominator]}
            elif c['kind']=='polynomial':submission={'coefficients':[v[1]*v[3],v[0]*v[3]+v[1]*v[2],v[0]*v[2]]}
            elif c['kind']=='counterexample':submission={'x':[1,1],'y':[1,1],'lhs':[4,1],'rhs':[2,1],'y_zero_valid':True}
            elif c['kind']=='definition':submission={'classification':v[0]<v[1],'proper_example':[1,2]}
            else:submission={'answer':[v[0]+2*v[1]+2*(v[2]+2*v[3]),1]}
            result=assessment.score(c,submission,c['unlock_tick'],{'tutor_during_challenge':False,'prior_delivered_assistance':'recorded-separately'})
            expect(result['score']==1,'independent assessment positive control')
            expect(assessment.score(c,submission,c['unlock_tick'],{'tutor_during_challenge':True})['outcome']=='CONTAMINATED','assisted answer scored independent')
            expect(assessment.score(c,submission,c['unlock_tick'],{})['outcome']=='INDEPENDENCE_UNVERIFIED','missing assistance evidence became an independent score')
            if c['kind']=='polynomial':
                rejects(lambda:assessment.score(c,{'coefficients':[float(x) for x in submission['coefficients']]},c['unlock_tick'],{'tutor_during_challenge':False}),'float coefficients admitted as exact integers')
                rejects(lambda:assessment.score(c,{'coefficients':[True,1,1]},c['unlock_tick'],{'tutor_during_challenge':False}),'Boolean coefficients admitted as exact integers')
            elif c['kind']=='definition':
                rejects(lambda:assessment.score(c,{**submission,'classification':int(submission['classification'])},c['unlock_tick'],{'tutor_during_challenge':False}),'integer classification silently substituted for Boolean')
            results.append({'challenge':c,'result':result})
        (out/'assessment.json').write_text(json.dumps(results,indent=2)+'\n');report['assessment']={'status':'PASS_SYNTHETIC_SOFTWARE','families':list(assessment.FAMILIES),'educational_benefit':'UNVERIFIED','policy_receipt':receipt}
        for claims in ([],[{'domain':'Q','statement':'pending exact checking'}]):
            raw_text='Explain the common denominator.'
            text,transform=tutor.presentation_text(raw_text,claims,'explanation')
            expect(text.startswith('UNVERIFIED ASSISTANCE') and ('CHECKING PENDING:' in text)==bool(claims) and len(text)<=256,'unverified/pending annotation absent')
            expect(transform['input_sha256']==hashlib.sha256(raw_text.encode()).hexdigest(),'model text was silently edited')
        rejects(lambda:tutor.presentation_text('x'*197,[],'hint'),'oversized model response silently truncated')
        rejects(lambda:tutor.presentation_text('speech',[],'silence'),'policy silence contains content')
        expect(tutor.presentation_text('',[],'silence')[0]=='','policy silence lost')
        request=dict(session=41,consent=7,revision=9,object=12,sequence=1,cutoff=250,now=250,deadline=1000000,source=1,edition=2,task_id=31,grants=3,modality=3,task=dict(kind='rational-sum',a=2,b=7,c=3,d=5),question='One hint please')
        context=tutor.public_request({**request,'assessment_solutions':['SECRET_DO_NOT_PASS'],'hidden_scenario_truth':'FORBIDDEN'})
        expect('SECRET_DO_NOT_PASS' not in json.dumps(context) and 'FORBIDDEN' not in json.dumps(context),'private caller fields reached inference')
        rejects(lambda:tutor.public_request({**request,'observations':[dict(stream=1,capture_end=251,consent=7,origin='SYNTHETIC')],'transmit_streams':[1]}),'future observation reached policy')
        if a.inference:
            args=[sys.executable,str(ROOT/'sim/companion/multimodal/tutor.py'),'--model',a.model]
            if a.espeak:args+=['--speech','--espeak',str(a.espeak)]
            peer=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
            try:
                ready=json.loads(peer.stdout.readline());expect(ready['schema']=='lemma-tutor-ready/2','missing runtime tutor ready')
                #Fresh operands and questions are delivered only after startup.
                tasks=[('rational-sum',[rng.randint(1,9),11,rng.randint(1,9),13],'Give one hint without the final answer.'),('polynomial-product',[2,rng.randint(1,9),1,4],'Give a short worked example for this exact product.'),('polynomial-product',[1,2,1,3],'Give a concrete counterexample to dropping both middle terms.'),('rational-sum',[7,11,2,9],'Remain silent with empty text and no claims while I solve independently.')]
                outputs=[];inputs=[]
                for i,(kind,v,question) in enumerate(tasks):
                    query={**request,'sequence':i+1,'task_id':31+i,'task':{'kind':kind,**dict(zip(['a','b','c','d'],v))},'question':question}
                    inputs.append(query);peer.stdin.write(json.dumps(query)+'\n');peer.stdin.flush();outputs.append(json.loads(peer.stdout.readline()))
                peer.stdin.close();peer.wait(timeout=30)
                (out/'inference-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n');(out/'inference-outputs.json').write_text(json.dumps([ready,*outputs],indent=2)+'\n')
                expect(all(o['schema']=='lemma-tutor-proposal/2' for o in outputs),'real inference proposal rejected')
                expect(len({o['action'] for o in outputs})>=3,'insufficient differing inferred actions')
                expect(all(o['inference']['eval_count']>0 for o in outputs),'no real model evaluation')
                report['inference']={'status':'PASS_LOCAL_ACTUAL_INFERENCE_GENERATED_ONLY','actions':[o['action'] for o in outputs],'seconds':[o['inference']['seconds'] for o in outputs],'model':ready['inference'],'guest_presentation':'NOT_ESTABLISHED_BY_COMPONENT_TEST'}
            finally:
                if peer.poll() is None:peer.kill();peer.wait(timeout=5)
        if any(sha(ROOT/name)!=h for name,h in report['sources'].items()):raise ValueError('consumed source changed')
        report['status']='PASS_COMPANION_COMPONENTS'
    except BaseException as error:report['error']=repr(error)
    report['seconds']=time.monotonic()-started;(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ('status','seconds','error')}));return 0 if report['status'].startswith('PASS') else 1
if __name__=='__main__':raise SystemExit(main())
