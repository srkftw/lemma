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
    if len(payload) != 832:
        raise ValueError('mathematical record length differs')
    words = struct.unpack('<104Q', payload)
    if words[:4] != (MAGIC, 1, IDENTITY, namespace) or object_id != 0x8000 + words[4]:
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
    if any(words[22:32]):
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
    return {'format': 'lemma-mathematical-submission/1', 'namespace': namespace,
            'page': words[4], 'revision': words[5], 'goal': words[6],
            'answer': list(words[7:12]), 'outcome': words[12], 'evidence_revision': words[13],
            'budget': words[17], 'attempts': attempts, 'hints': hints, 'history': history}
