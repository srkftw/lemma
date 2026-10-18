#!/usr/bin/env python3
"""Small open trainable presentation policy, independent later-score objective.
Public synthetic training only proves pipeline operation. It cannot establish
human learning benefit or counterfactual responses of recorded humans.
"""
import argparse,hashlib,json,math,random
from pathlib import Path
ACTIONS=['explanation','worked-example','counterexample','hint','exercise-choice','clarification','pacing','review','silence']
FEATURES=['bias','prior_invalid_rate','prior_independent_score','budget_fraction','missing_fraction']

def features(context):
    history=context.get('history',[])
    invalid=sum(x.get('outcome')=='INVALID' for x in history)
    scores=[x['independent_score'] for x in history if type(x.get('independent_score')) in (int,float)]
    observations=context.get('observations',[])
    missing=sum(x.get('quality')!='VALID' for x in observations)
    return [1,invalid/max(1,len(history)),sum(scores)/max(1,len(scores)),float(context.get('budget_fraction',1)),missing/max(1,len(observations))]

def infer(model,context):
    if model.get('schema') not in ('lemma-linear-policy/1','lemma-linear-policy/2') or model.get('features')!=FEATURES or model.get('actions')!=ACTIONS:raise ValueError('policy identity')
    f=features(context)
    scores=[sum(w*x for w,x in zip(row,f)) for row in model['weights']]
    choice=max(range(len(scores)),key=lambda i:scores[i])
    return ACTIONS[choice],{'model_sha256':hashlib.sha256(json.dumps(model,sort_keys=True).encode()).hexdigest(),'features':dict(zip(FEATURES,f)),'scores':scores,'selection':ACTIONS[choice], 'objective':model['objective'],'scope':'SYNTHETIC_TRAINING_ONLY'}

def train(rows,steps=100,rate=.03):
    if not rows:raise ValueError('empty training corpus')
    seen=set();weights=[[0.0]*len(FEATURES) for _ in ACTIONS]
    for row in rows:
        if row.get('split')!='train' or row.get('origin')!='SYNTHETIC' or row.get('reward_kind')!='later-independent-assessment':raise ValueError('unadmitted training provenance')
        if not 0<=row['reward']<=1 or len(row['features'])!=len(FEATURES) or row['action'] not in ACTIONS:raise ValueError('training format')
        receipt=row.get('assessment_receipt',{})
        if receipt.get('schema')!='lemma-independent-assessment/1' or receipt.get('score')!=row['reward'] or receipt.get('evaluator')!='python-Fraction-independent-host-oracle/1' or receipt.get('outcome') not in ('EXACT_RESTRICTED','INVALID') or receipt.get('assistance_scope',{}).get('tutor_during_challenge') is not False:
            raise ValueError('reward must be the separate completed independent-assessment receipt')
        seen.add((row['learner'],row['session']))
    for _ in range(steps):
        for row in rows:
            index=ACTIONS.index(row['action']);f=row['features'];prediction=sum(a*b for a,b in zip(weights[index],f))
            error=prediction-row['reward']
            for j in range(len(f)):weights[index][j]-=rate*(error*f[j]+.001*weights[index][j])
    return {'schema':'lemma-linear-policy/2','features':FEATURES,'actions':ACTIONS,'weights':weights,
        'objective':'later-independent-assessment','data_origin':'SYNTHETIC','steps':steps,'rate':rate,
        'training_sessions':len(seen),'corpus_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),
        'educational_benefit':'UNVERIFIED','physiology_reward':False,'reward_source':'completed-independent-assessment-receipts'}

def fixture(seed=72820):
    #This host-only offline generator can call the assessment authority. Runtime
    #infer consumes only permitted features/weights and never calls this path.
    import assessment
    from fractions import Fraction
    rng=random.Random(seed);rows=[]
    for learner in range(24):
        prior=rng.random();invalid=rng.random();missing=rng.random()
        challenge=assessment.challenge(str(seed),f'train-{learner}',f'study-{learner}','retention')
        a,b,c,d=challenge['operands'];correct=Fraction(a,b)+Fraction(c,d)
        for index,action in enumerate(ACTIONS):
            #Public synthetic learner-response assumption generates a later
            #submission, not a reward. Exact authority scores the submission.
            probability=max(0,min(1,.3+prior*.3+(.25*invalid if action=='worked-example' else .2*(1-invalid) if action=='hint' else .08)-(.1 if action=='silence' else 0)))
            produced=correct if rng.random()<probability else correct+1
            submission={'answer':[produced.numerator,produced.denominator]}
            receipt=assessment.score(challenge,submission,challenge['unlock_tick'],{'tutor_during_challenge':False,'prior_delivered_assistance':action})
            rows.append({'split':'train','origin':'SYNTHETIC','reward_kind':'later-independent-assessment',
                'learner':f'train-{learner}','session':f'study-{learner}','features':[1,invalid,prior,1,missing],
                'action':action,'reward':receipt['score'],'assessment_receipt':receipt,
                'response_model':'public-synthetic-response-assumption/1','study_budget_ticks':600})
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['fixture','train','infer','rollback']);p.add_argument('--input',type=Path);p.add_argument('--output',type=Path);p.add_argument('--registry',type=Path);a=p.parse_args()
    if a.operation=='fixture':result=fixture()
    elif a.operation=='train':result=train(json.loads(a.input.read_text()))
    elif a.operation=='infer':
        payload=json.loads(a.input.read_text());choice,receipt=infer(payload['model'],payload['context']);result={'action':choice,'receipt':receipt}
    else:
        # Rollback changes only a caller-owned current-policy pointer. Frozen
        # session receipts retain their original model identity.
        model=json.loads(a.input.read_text());infer(model,{})
        if not a.registry:raise ValueError('rollback requires explicit registry')
        result={'schema':'lemma-policy-selection/1','path':str(a.input.resolve()),'sha256':hashlib.sha256(a.input.read_bytes()).hexdigest()}
        a.registry.write_text(json.dumps(result,sort_keys=True)+'\n')
    text=json.dumps(result,sort_keys=True,indent=2)+'\n'
    if a.output:
        with a.output.open('x') as f:f.write(text)
    else:print(text,end='')
if __name__=='__main__':main()
