#!/usr/bin/env python3
"""Independent exact assessment authority. Never imported by tutor.py.
Challenge/delay/resource/scoring definitions are fixed before intervention;
submission scoring is independent of policy/inference and physiology.
This executable synthetic corpus does not establish human educational benefit.
"""
import argparse,hashlib,json,random,sys
from fractions import Fraction
from pathlib import Path

VERSION='lemma-independent-assessment/1'
FAMILIES=('retention','transfer','assumptions-counterexample','definition-classification','unfamiliar-resource')

def challenge(seed,learner,session,family,start=0):
    if family not in FAMILIES:raise ValueError('unknown assessment family')
    rng=random.Random(f'{seed}:{learner}:{session}:{family}')
    a,b,c,d=[rng.randint(1,19) for _ in range(4)]
    public={'schema':VERSION,'learner':learner,'session':session,'family':family,
        'challenge':hashlib.sha256(f'{seed}:{learner}:{session}:{family}'.encode()).hexdigest(),
        'unlock_tick':start+600 if family=='retention' else start+60,
        'study_budget_ticks':600,'permitted_resources':['original-ink','standardized-resource'] if family=='unfamiliar-resource' else ['original-ink'],
        'tutor_permitted':False,'weight':1,'score_range':[0,1]}
    if family=='retention':public.update(kind='rational',operands=[a,b,c,d],prompt=f'Independently add {a}/{b} and {c}/{d}.')
    elif family=='transfer':public.update(kind='polynomial',operands=[a,b,c,d],prompt=f'Independently expand ({a}*x+{b})*({c}*x+{d}). Submit constant, linear, quadratic coefficients.')
    elif family=='assumptions-counterexample':public.update(kind='counterexample',operands=[],prompt='The claim says (x+y)^2=x^2+y^2 for all rational x,y. Supply a rational counterexample and both sides. State whether y=0 makes the identity true.')
    elif family=='definition-classification':public.update(kind='definition',operands=[a,b],prompt=f'A proper positive fraction has numerator smaller than denominator. Classify {a}/{b}, and give numerator/denominator for a proper example.')
    else:public.update(kind='unfamiliar',operands=[a,b,c,d],resource='Define a diamond b = a + 2*b for rationals. Parentheses specify evaluation order.',prompt=f'Using only this new resource calculate ({a} diamond {b}) diamond ({c} diamond {d}).')
    return public

def score(challenge,submission,now,assistance):
    if challenge.get('schema')!=VERSION or now<challenge['unlock_tick']:raise ValueError('assessment locked or unknown')
    if assistance.get('tutor_during_challenge') or assistance.get('solution_exposure'):return {'score':None,'outcome':'CONTAMINATED','reason':'challenge independence violated'}
    kind=challenge['kind'];v=challenge['operands'];correct=False
    def q(value):
        if not isinstance(value,list) or len(value)!=2 or any(type(x) is not int or abs(x)>1000000 for x in value) or value[1]==0:raise ValueError('bounded rational format')
        return Fraction(*value)
    if kind=='rational':correct=q(submission['answer'])==Fraction(v[0],v[1])+Fraction(v[2],v[3])
    elif kind=='polynomial':correct=submission['coefficients']==[v[1]*v[3],v[0]*v[3]+v[1]*v[2],v[0]*v[2]]
    elif kind=='counterexample':
        x,y=q(submission['x']),q(submission['y'])
        correct=(x+y)**2!=x*x+y*y and q(submission['lhs'])==(x+y)**2 and q(submission['rhs'])==x*x+y*y and submission['y_zero_valid'] is True
    elif kind=='definition':
        example=q(submission['proper_example'])
        correct=submission['classification']==(v[0]<v[1]) and 0<example<1
    elif kind=='unfamiliar':correct=q(submission['answer'])==v[0]+2*v[1]+2*(v[2]+2*v[3])
    else:raise ValueError('unsupported assessment domain')
    return {'schema':VERSION,'challenge':challenge['challenge'],'family':challenge['family'],
        'score':int(correct),'outcome':'EXACT_RESTRICTED' if correct else 'INVALID',
        'evaluator':'python-Fraction-independent-host-oracle/1','general_proof_kernel':'UNIMPLEMENTED',
        'assistance_scope':assistance,'submission':submission,'observed_tick':now,
        'educational_benefit':'UNVERIFIED','human_data':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['challenge','score']);p.add_argument('--seed',default='public-development');p.add_argument('--learner',default='synthetic-learner');p.add_argument('--session',default='held-out-0');p.add_argument('--family',choices=FAMILIES,default='retention');p.add_argument('--now',type=int,default=600);a=p.parse_args()
    if a.operation=='challenge':result=challenge(a.seed,a.learner,a.session,a.family)
    else:
        payload=json.load(sys.stdin);result=score(payload['challenge'],payload['submission'],a.now,payload['assistance'])
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
