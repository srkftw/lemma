"""Independent offline mathematical-record observation; no guest authority."""
import struct
from fractions import Fraction

MAGIC = 0x314854414D4D454C
IDENTITY = 0x0001000000000001
EXECUTION_MAGIC = 0x314558454D4D454C
EXECUTION_IDENTITIES = (0x0002000100000001, 0x0002000000000001,
                        0x0001000000000001, 0x000100000000001f)
SUMS_EXECUTION_IDENTITIES = (0x0003000100000001, 0x0003000000000001,
                            0x0001000100000001, 0x000100000000001f)
BYTES_EXECUTION_IDENTITIES = (0x0004000100000001, 0x0004000000000001,
                             0x0001000200000001, 0x000200000000001f)


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
    if len(payload) not in (832,1856,2496):
        raise ValueError('mathematical record length differs')
    words = struct.unpack('<'+str(len(payload)//8)+'Q', payload)
    version=words[1]
    if version not in (1,2,3,4,5) or len(payload)!={1:832,2:1856,3:2496,4:2496,5:2496}[version] or words[:4] != (MAGIC, version, IDENTITY, namespace) or object_id != 0x8000 + words[4]:
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
    if version in (2,3,4,5):
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
    if version in (3,4,5):
        if words[232:240] != (EXECUTION_MAGIC,{3:1,4:2,5:3}[version],0,0,0,0,0,0):
            raise ValueError('execution extension header/version/reserved differs')
        def execution(slot,budget,active):
            if slot==(0,)*8:
                return {'origin':'Unknown'}
            request,implementation,lowering,runtime,resources,actual_budget,status,origin=slot
            admitted = (origin==2 and (implementation,lowering,runtime,resources)==EXECUTION_IDENTITIES) or \
                (version in (4,5) and origin==3 and (implementation,lowering,runtime,resources)==SUMS_EXECUTION_IDENTITIES) or \
                (version==5 and origin==4 and (implementation,lowering,runtime,resources)==BYTES_EXECUTION_IDENTITIES)
            if not active or not 1<=request<=0x7ffffffffffffffe or not admitted or \
                actual_budget!=budget or status!=0:
                raise ValueError('execution request/implementation/lowering/runtime/resource/status differs')
            names={2:('IsolatedManaged','lemma-isolated-arithmetic-managed-v1',
                      'core0-user-v0.2/lemma-managed-records-v1','lemma-owned-arena-v1','lemma-arithmetic-resource-v1'),
                   3:('IsolatedSums','lemma-isolated-arithmetic-sums-v1',
                      'core0-user-v0.3/lemma-managed-sums-v1','lemma-owned-arena-sum-cookie-v1','lemma-arithmetic-resource-v1'),
                   4:('IsolatedBytes','lemma-isolated-arithmetic-bytes-v1',
                      'core0-user-v0.4/lemma-managed-bytes-v1','lemma-owned-arena-bytes-cookie-v1','lemma-arithmetic-bytes-resource-v1')}
            origin_name,implementation_name,lowering_name,runtime_name,resource_name=names[origin]
            return {'origin':origin_name,'request':request,'implementation':implementation_name,
                    'lowering':lowering_name,'runtime':runtime_name,'resources':resource_name,
                    'budget':budget,'status':0}
        slots=[words[248+index*8:256+index*8] for index in range(8)]
        metadata=[execution(slot,history[index]['budget'] if index<attempts else 0,index<attempts)
                  for index,slot in enumerate(slots)]
        active=execution(words[240:248],words[17],outcome!=0)
        if active['origin']!='Unknown':
            if not history or words[240:248]!=slots[attempts-1] or \
                (history[-1]['revision'],history[-1]['goal'],history[-1]['outcome'])!=(words[5],words[6],outcome):
                raise ValueError('active execution differs from latest applicable attempt')
        record['execution']={'active':active,'history':metadata,
            'identity_kind':'closed implementation-version authority; not artifact digests'}
    return record
