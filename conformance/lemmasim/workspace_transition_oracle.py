"""Offline observation only; never supplies state or decisions to a guest."""
def require(value, message):
    if not value:
        raise ValueError(message)


def observe_transition(before, after, kind):
    """Require exact old evidence/package provenance/ordered learner prefixes."""
    old, new = before['document'], after['document']
    require((before['namespace'], before['page']) == (after['namespace'], after['page']),
            'workspace transition changed namespace/page')
    count = old['attempts']
    require(count <= new['attempts'] <= 8, 'attempt count regressed/overflowed')
    require(new['history'][:count] == old['history'], 'old mathematical history changed')
    require(new['execution']['history'][:count] == old['execution']['history'][:count],
            'old execution identity history changed')
    require(after['history'][:count] == before['history'][:count],
            'old package provenance history changed')
    events = old['learner']['events']
    require(new['learner']['events'][:len(events)] == events, 'ordered learner-event prefix changed')
    require(new['revision'] >= old['revision'], 'submission revision regressed')
    if kind == 'edit':
        require(new['attempts'] == count and new['revision'] > old['revision'] and
                new['outcome'] == 0 and new['evidence_revision'] == 0 and
                new['execution']['active'] == {'origin': 'Unknown'},
                'actual edit retained applicability or manufactured an attempt')
    elif kind == 'known-check':
        require(new['attempts'] == count + 1 and new['outcome'] in (1, 2, 3, 4, 5) and
                new['execution']['active']['origin'] == 'IsolatedClosure' and
                after['history'][count]['origin'] == 'InstalledPackage' and
                after['current'] == after['history'][count] and after['applicable_package_selection'],
                'actual known-package reply is not current revision-bound Protocol7 evidence')
    elif kind == 'unknown-check':
        require(new['attempts'] == count + 1 and after['history'][count] == {'origin': 'Unknown'} and
                after['current'] == {'origin': 'Unknown'} and
                new['execution']['active']['origin'] == 'IsolatedClosure',
                'builtin reply acquired package provenance or bypassed Protocol7')
    elif kind == 'learner':
        require(new['attempts'] == count and len(new['learner']['events']) > len(events),
                'hint/review control did not record an ordered learner event')
    elif kind == 'cold':
        require(before == after, 'independent cold workspace bytes/semantics differ')
    else:
        raise ValueError('undeclared observation transition')
    return {'status': 'PASS', 'kind': kind, 'old_attempts': count, 'new_attempts': new['attempts'],
            'old_events': len(events), 'new_events': len(new['learner']['events']),
            'old_history_and_package_and_execution_prefixes_exact': True}
