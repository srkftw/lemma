"""Independent offline mathematical-record observation; no guest authority."""
import struct
from fractions import Fraction

MAGIC = 0x314854414D4D454C
IDENTITY = 0x0001000000000001


def result(goal, n, d, p0, p1, p2, budget):
    if goal == 1:
        if d == 0:
            return 2
        if budget < 8:
            return 5
        return 1 if Fraction(n, d) == Fraction(1, 2) + Fraction(1, 3) else 2
    if goal == 2:
        if budget < 6:
            return 5
        return 1 if (p0, p1, p2) == (1, 2, 1) else 2
    return 4


def inspect(payload, namespace, object_id):
    if len(payload) not in (832,1856):
        raise ValueError('mathematical record length differs')
    words = struct.unpack('<'+str(len(payload)//8)+'Q', payload)
    version=words[1]
    if version not in (1,2) or len(payload)!=(832 if version==1 else 1856) or words[:4] != (MAGIC, version, IDENTITY, namespace) or object_id != 0x8000 + words[4]:
        raise ValueError('mathematical package/namespace/page identity differs')
    if not 1 <= words[4] <= 64 or not 1 <= words[5] <= 0x7ffffffffffffffe:
        raise ValueError('mathematical anchor/revision differs')
    goal, n, d, p0, p1, p2, outcome, evidence_revision = words[6:14]
    if goal not in (1, 2, 3) or any(value > 99 for value in (n, d, p0, p1, p2)):
        raise ValueError('unsupported goal or malformed UI operand')
    if words[14:17] != (IDENTITY, goal, 0) or words[17] not in (0, 8):
        raise ValueError('checker/environment/domain/assumption/resource identity differs')
    attempts, hints, selected, recommendation = words[18:22]
    if attempts > 8 or hints > 32 or selected not in (0, 56, 64, 72, 80, 88) or recommendation > 3:
        raise ValueError('mathematical history/UI bounds differ')
    if version==1 and any(words[22:32]):
        raise ValueError('unknown mandatory mathematical field')
    expected = result(goal, n, d, p0, p1, p2, words[17])
    if outcome == 0:
        if evidence_revision != 0:
            raise ValueError('unchecked submission retains applicable evidence')
    elif evidence_revision != words[5] or (outcome != expected and not (outcome == 5 and attempts == 8)):
        raise ValueError('current evidence differs from independent exact arithmetic')
    history = []
    for index in range(8):
        entry = words[32 + index*9:41 + index*9]
        if index >= attempts:
            if any(entry):
                raise ValueError('unused mathematical history entry differs')
            continue
        revision, goal, n, d, p0, p1, p2, outcome, budget = entry
        if not 1 <= revision <= words[5] or goal not in (1, 2, 3) or budget not in (0, 8):
            raise ValueError('history revision/domain/resource differs')
        if any(value > 99 for value in (n, d, p0, p1, p2)) or outcome != result(goal, n, d, p0, p1, p2, budget):
            raise ValueError('history differs from independent exact arithmetic')
        history.append({'revision': revision, 'goal': goal, 'answer': [n, d, p0, p1, p2],
                        'outcome': outcome, 'budget': budget})
    record={'format': 'lemma-mathematical-submission/'+str(version), 'namespace': namespace,
            'page': words[4], 'revision': words[5], 'goal': words[6],
            'answer': list(words[7:12]), 'outcome': words[12], 'evidence_revision': words[13],
            'budget': words[17], 'attempts': attempts, 'hints': hints, 'history': history}
    if version==2:
        identity,mode,count,uncertain,event_version,show_reason=words[22:28]
        if identity!=IDENTITY or mode>4 or count>64 or uncertain!=1 or event_version!=1 or show_reason>1 or any(words[28:32]):
            raise ValueError('learner policy identity/bounds/uncertainty differs')
        events=[]; observed_attempts=0; observed_hints=0; observed_mode=0
        latest=0; assisted=False
        for index in range(64):
            revision,descriptor=words[104+index*2:106+index*2]
            if index>=count:
                if revision or descriptor:raise ValueError('unused learner event differs')
                continue
            kind=descriptor&255; goal=(descriptor>>8)&255; value=(descriptor>>16)&255; attempt_index=(descriptor>>24)&255
            if not 1<=revision<=words[5] or descriptor>>32 or goal not in (1,2,3):
                raise ValueError('learner event revision/goal differs')
            if kind==1:
                if attempt_index!=observed_attempts or attempt_index>=attempts:
                    raise ValueError('learner attempt ordering differs')
                attempt=history[attempt_index]
                if (revision,goal,value)!=(attempt['revision'],attempt['goal'],attempt['outcome']):
                    raise ValueError('learner event disagrees with exact immutable attempt')
                observed_attempts+=1
            else:
                if attempt_index:raise ValueError('nonattempt learner event has attempt reference')
                if kind==2 and value==1:observed_hints+=1
                elif kind==3 and value<=4:observed_mode=value
                elif kind==4 and value==1:pass
                elif kind==5 and value==5 and attempts==8:pass
                elif kind==6 and 1<=value<=32:observed_hints+=value
                else:raise ValueError('unknown learner event')
            if kind==6:assisted=True
            if goal==words[6]:
                if kind==2:assisted=True
                if kind in (1,5):latest=value
            events.append({'revision':revision,'goal':goal,'kind':kind,'value':value,'attempt_index':attempt_index})
        if (observed_attempts,observed_hints,observed_mode)!=(attempts,hints,mode):
            raise ValueError('learner aggregates disagree with ordered events')
        if mode==4:action,reason='disabled','disabled'
        elif mode:action,reason=('practice','later','support')[mode-1],'manual'
        elif latest==1:action,reason=('practice','assisted') if assisted else ('later','exact-attempt')
        elif latest==0:action,reason='practice','no-attempt'
        elif latest==2:action,reason='practice','invalid-attempt'
        else:action,reason='support','unsupported-or-resource'
        record['learner']={'policy':'lemma-offline-review/1','mode':mode,'understanding':'uncertain',
            'recommendation':action,'reason':reason,'show_reason':bool(show_reason),'events':events}
    return record
