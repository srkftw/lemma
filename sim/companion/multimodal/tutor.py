#!/usr/bin/env python3
"""Owner-local open tutor orchestration. JSON lines in; untrusted proposals out.
No notebook, framebuffer, checker, grant or assessment state is owned here.
The default real inference backend is existing local Ollama, without downloads.
Actual model output is retained in the receipt; malformed output fails closed.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,os,struct,sys,time,urllib.request
from pathlib import Path

SCHEMA='lemma-tutor-proposal/2'
ACTIONS=('explanation','worked-example','counterexample','hint','exercise-choice','clarification','pacing','review','silence')
SYSTEM='''You are an untrusted mathematics tutor for an open workbook. You may propose assistance, never change grants, checker results, original student work, or assessment definitions. Use only the supplied public current task and authorized history. Never infer understanding from physiology. Return exactly one JSON object: {"action": one of ["explanation","worked-example","counterexample","hint","exercise-choice","clarification","pacing","review","silence"], "text": at most196characters of original ASCII mathematics guidance, "claims": [{"domain":"Q" or "Q[x]", "statement":text}]} . When the student asks for silence, use silence and empty text. When they ask for a hint, give a hint without revealing the final answer. When the question is ambiguous, ask clarification. Work with the actual supplied parameters; do not identify fixtures. No Markdown fences.'''

class Rejected(ValueError):pass
class InferenceRejected(Rejected):
    def __init__(self,message,receipt):super().__init__(message);self.receipt=receipt
FORMAT={'type':'object','properties':{'action':{'type':'string','enum':list(ACTIONS)},
    'text':{'type':'string','maxLength':196},'claims':{'type':'array','items':{'type':'object',
        'properties':{'domain':{'type':'string','enum':['Q','Q[x]']},'statement':{'type':'string'}},
        'required':['domain','statement'],'additionalProperties':False}}},
    'required':['action','text','claims'],'additionalProperties':False}

def digest(data):return hashlib.sha256(data).hexdigest()
def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':')).encode()

def rpc(endpoint,path,obj=None,timeout=180):
    data=None if obj is None else canonical(obj)
    request=urllib.request.Request(endpoint+path,data=data,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=timeout) as response:
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise Rejected('inference response too large')
    return json.loads(raw)

def presentation_text(raw_text, claims, action):
    if not isinstance(raw_text,str) or not raw_text.isascii() or len(raw_text)>196:
        raise Rejected('model text must be ASCII and within196 characters; no truncation')
    if action=='silence':
        if raw_text or claims:raise Rejected('silence must have no text or claims')
        return '',{'schema':'lemma-tutor-presentation/1','annotation':'POLICY_SELECTED_SILENCE','checking':'NOT_APPLICABLE'}
    prefix='UNVERIFIED ASSISTANCE - CHECKING PENDING: ' if claims else 'UNVERIFIED ASSISTANCE: '
    text=prefix+raw_text
    if len(text)>256:raise Rejected('annotated presentation exceeds256 characters')
    return text,{'schema':'lemma-tutor-presentation/1','annotation':prefix,'max_model_ascii':196,'max_rendered_ascii':256,
        'input_sha256':digest(raw_text.encode()),'rendered_sha256':digest(text.encode()),
        'checking':'PENDING_UNCONNECTED_TO_V8' if claims else 'NO_DECLARED_FORMAL_CLAIMS'}

def public_request(request):
    required=('session','consent','revision','object','sequence','cutoff','now','deadline','source','edition','task_id','task','question','grants')
    if any(key not in request for key in required):raise Rejected('missing document/action context')
    for key in required[:10]+('source','edition','task_id','grants'):
        if type(request[key]) is not int or not 0<=request[key]<=0xfffffffffffffffe:raise Rejected('invalid scalar '+key)
    if not request['session'] or not request['consent'] or not request['revision'] or not request['object'] or not request['sequence']:raise Rejected('zero identity')
    if request['cutoff']>request['now'] or request['deadline']<request['now']:raise Rejected('future context or expired question')
    if not isinstance(request['question'],str) or not 0<len(request['question'])<=4096:raise Rejected('question length')
    task=request['task']
    if set(task)!= {'kind','a','b','c','d'} or task['kind'] not in ('rational-sum','polynomial-product'):raise Rejected('unsupported public task')
    if any(type(task[k]) is not int or not -99<=task[k]<=99 for k in ('a','b','c','d')):raise Rejected('task range')
    if task['kind']=='rational-sum' and (task['b']<=0 or task['d']<=0):raise Rejected('denominator')
    observations=[]
    for observation in request.get('observations',[]):
        if set(observation)-{'stream','capture_end','consent','representation','value','quality','origin','execution'}:raise Rejected('unknown observation field')
        if observation.get('capture_end',request['now']+1)>request['cutoff']:raise Rejected('future observation')
        if observation.get('consent')!=request['consent']:raise Rejected('stale observation grant')
        if observation.get('stream') not in request.get('transmit_streams',[]):raise Rejected('ungranted observation stream')
        if observation.get('origin') not in ('SYNTHETIC','MEASURED'):raise Rejected('missing origin')
        observations.append(observation)
    # Do not pass unrecognized caller keys, solutions, hidden scenario labels,
    # assessment records or pending future observations to the policy/model.
    history=request.get('delivered_history',[])
    if not isinstance(history,list) or len(history)>32:raise Rejected('history window')
    for event in history:
        if not isinstance(event,dict) or set(event)-{'kind','tick','outcome','independent_score','action','delivered_frames','session','consent'}:raise Rejected('unadmitted history field')
        if event.get('tick',request['cutoff']+1)>request['cutoff']:raise Rejected('future history')
        if event.get('session')!=request['session'] or event.get('consent')!=request['consent']:raise Rejected('stale history domain')
    return {'task':task,'question':request['question'],'cutoff':request['cutoff'],'observations':observations,
            'history':history}

class Tutor:
    def __init__(self,endpoint,model,policy=None):
        if endpoint not in ('http://127.0.0.1:11434','http://localhost:11434'):raise Rejected('reference inference is owner-local only')
        self.endpoint,self.model=endpoint,model
        tags=rpc(endpoint,'/api/tags')['models']
        selected=next((m for m in tags if m['name']==model),None)
        if selected is None:raise Rejected('model is absent; this command never downloads it')
        details=rpc(endpoint,'/api/show',{'model':model})
        self.identity={'backend':'ollama-local','model':model,'digest':selected['digest'],
                       'template_sha256':digest(details.get('template','').encode()),
                       'license_sha256':digest(details.get('license','').encode()),
                       'parameters':details.get('parameters',''),'system_sha256':digest(SYSTEM.encode())}
        self.policy=None if policy is None else json.loads(Path(policy).read_text())
        self.last={}
    def propose(self,request):
        context=public_request(request)
        key=(request['session'],request['consent'])
        if request['sequence']<=self.last.get(key,0):raise Rejected('duplicate proposal request')
        start=time.monotonic()
        instruction=SYSTEM
        policy_receipt=None
        if self.policy is not None:
            from policy import infer
            choice,policy_receipt=infer(self.policy,context)
            instruction+=' The frozen learned presentation policy selected '+choice+'. Respect silence and explicit student requests.'
        raw=rpc(self.endpoint,'/api/chat',{'model':self.model,'stream':False,'format':FORMAT,
            'messages':[{'role':'system','content':instruction},{'role':'user','content':json.dumps(context,sort_keys=True)}],
            'options':{'temperature':0,'seed':72820,'num_predict':384,'num_ctx':4096},'keep_alive':'5m'})
        content=raw.get('message',{}).get('content','')
        self.last_inference={'raw_response':content,'model':self.identity,'seconds':time.monotonic()-start,'request_sha256':digest(canonical(context))}
        try:answer=json.loads(content)
        except Exception as error:raise InferenceRejected('malformed inference JSON',self.last_inference) from error
        if set(answer)!={'action','text','claims'} or answer['action'] not in ACTIONS:raise InferenceRejected('malformed inference proposal',self.last_inference)
        raw_text=answer['text']
        text=raw_text
        if not isinstance(text,str) or len(text)>2048 or not text.isascii():raise InferenceRejected('unsupported inferred text format',self.last_inference)
        if answer['action']=='silence' and text:raise InferenceRejected('silence has content',self.last_inference)
        if not isinstance(answer['claims'],list) or len(answer['claims'])>8:raise InferenceRejected('claim count',self.last_inference)
        for claim in answer['claims']:
            if set(claim)!= {'domain','statement'} or claim['domain'] not in ('Q','Q[x]') or not isinstance(claim['statement'],str):raise InferenceRejected('unsupported claim',self.last_inference)
        try:text,presentation=presentation_text(raw_text,answer['claims'],answer['action'])
        except Rejected as error:raise InferenceRejected(str(error),self.last_inference) from error
        modality=0 if answer['action']=='silence' else request.get('modality',1)
        if modality not in (0,1,2,3) or request['grants']&modality!=modality:raise Rejected('presentation permission absent')
        words=[2,request['session'],request['consent'],request['revision'],request['object'],request['sequence'],
               request['cutoff'],request['now'],request['deadline'],modality,ACTIONS.index(answer['action']),modality,
               1 if answer['claims'] else 0,len(text.encode()),0,2,int(self.identity['digest'].split(':')[-1][:16],16),
               request['source'],request['edition'],request['task_id'],1,0,0,0]
        self.last[key]=request['sequence']
        return {'schema':SCHEMA,'action':answer['action'],'text':text,'model_text':raw_text,'presentation_transform':presentation,'claims_requiring_check':answer['claims'],
            'mathematical_authority':'NONE_UNTRUSTED_ASSISTANCE','packet_hex':struct.pack('<24Q',*words).hex(),
            'context':{k:request[k] for k in ('session','consent','source','edition','task_id','revision','object','sequence','cutoff','deadline')},
            'inference':{**self.identity,'request_sha256':digest(canonical(context)),'raw_response':content,
                'raw_response_sha256':digest(content.encode()),'seconds':time.monotonic()-start,
                'eval_count':raw.get('eval_count'),'eval_duration_ns':raw.get('eval_duration'),'policy':policy_receipt},
            'delivery':'GENERATED_ONLY_REQUIRES_GUEST_ACCEPTANCE'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--endpoint',default='http://127.0.0.1:11434');p.add_argument('--model',default='qwen2.5:7b');p.add_argument('--policy',type=Path);p.add_argument('--speech',action='store_true');p.add_argument('--espeak',type=Path);p.add_argument('--pcm-rate',type=int,default=48000);a=p.parse_args()
    tutor=Tutor(a.endpoint,a.model,a.policy)
    print(json.dumps({'schema':'lemma-tutor-ready/2','inference':tutor.identity}),flush=True)
    for line in sys.stdin:
        try:
            if len(line)>2_000_000:raise Rejected('request too large')
            request=json.loads(line)
            proposal=tutor.propose(request)
            if a.speech and proposal['action']!='silence':
                if request.get('modality',1)&2==0:raise Rejected('speech permission absent')
                from speech import synthesize
                pcm,receipt=synthesize(proposal['text'],a.espeak,a.pcm_rate)
                proposal['pcm_base64']=base64.b64encode(pcm).decode()
                proposal['audio']=receipt
                words=list(struct.unpack('<24Q',bytes.fromhex(proposal['packet_hex'])))
                words[14]=len(pcm)//2
                proposal['packet_hex']=struct.pack('<24Q',*words).hex()
            print(json.dumps(proposal,separators=(',',':')),flush=True)
        except Exception as error:
            print(json.dumps({'schema':'lemma-tutor-rejected/2','reason':str(error),'delivery':'NONE','inference':getattr(error,'receipt',None)}),flush=True)
if __name__=='__main__':main()
