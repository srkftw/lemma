"""Negative-only cases over the retained genuine Task004 Kernel3 LLVM.

No positive compiler AST or LLVM program is constructed. The qualifier supplies
the actual complete CI unit and emitted pre/post bodies; operation mutations
also exercise the independent checked-call gates without the body-pin layer.
"""
from __future__ import annotations
import copy
import re


def corpus(ir, unit):
    from audit_kernel import _ir_definition_body
    from paper_next import canonical
    from usercopy_page_words import BASE, ARGUMENTS
    rows = {canonical(row['source']): row for row in unit['functions']}
    cases = []
    for field, value in [('configuration', 'lemmasim-initialize' if unit['configuration']=='lemmasim-notebook' else 'lemmasim-notebook'),
                         ('managed_policy', 'lemma-notebook-v2'),
                         ('contract_version', 'core0-kernel-v0.4'),
                         ('schema_version', 2), ('role', 'user')]:
        wrong = copy.deepcopy(unit); wrong[field] = value
        cases.append(('metadata-'+field, ir, wrong))
    wrong = copy.deepcopy(unit); wrong['checked_inline'] = {}
    cases.append(('claimed-checked-inlining', ir, wrong))
    wrong = copy.deepcopy(unit); wrong['roots'][0]['source'] += '.other'
    cases.append(('wrong-exact-root', ir, wrong))
    for suffix in ARGUMENTS:
        wrong = copy.deepcopy(unit)
        wrong['functions'] = [row for row in wrong['functions']
                              if canonical(row['source']) != BASE+suffix]
        cases.append(('missing-'+suffix, ir, wrong))
    for suffix, label, altered in operation_corpus(ir, unit):
        body = _ir_definition_body(ir, rows[BASE+suffix]['symbol'])
        cases.append((suffix+'/'+label, ir.replace(body, altered, 1), unit))
    return cases


def operation_corpus(ir, unit):
    from audit_kernel import _ir_definition_body
    from paper_next import canonical
    from usercopy_page_words import BASE
    rows = {canonical(row['source']): row for row in unit['functions']}
    read = rows['Lemma.Kernel.Memory.Access.read64']['symbol']
    write = rows['Lemma.Kernel.Memory.Access.write64']['symbol']
    cases = []
    for suffix in ('copyWord', 'copyWordGenericBlockStep', 'copyWordBlockStep'):
        body = _ir_definition_body(ir, rows[BASE+suffix]['symbol'])
        writes = re.findall(r'(?m)^.*call \{ i64, i64 \} @'+re.escape(write)+r'\(.*$', body)
        comparisons = re.findall(r'(?m)^.*icmp eq i64 %action\.call\.status-word[0-9]+, 0$', body)
        expected = 1 if suffix == 'copyWord' else 8
        if len(writes) != expected or len(comparisons) != expected*2:
            raise AssertionError('actual Kernel3 checked pair/status sites absent')
        for index, line in enumerate(writes):
            changed = re.sub(r', i64 %[-\w.]+\)$', ', i64 0)', line)
            if line == changed:
                raise AssertionError('actual Kernel3 written-value site absent')
            cases.append((suffix, 'word-value-'+str(index), body.replace(line, changed, 1)))
        for index, line in enumerate(comparisons):
            cases.append((suffix, 'zero-status-'+str(index),
                          body.replace(line, line.replace(', 0', ', 1'), 1)))
        first = re.search(r'@'+re.escape(read)+r'\(i64 %[-\w.]+\)', body)
        if first is None:
            raise AssertionError('actual first read site absent')
        cases.append((suffix, 'read-address', body.replace(first[0], '@'+read+'(i64 0)', 1)))
        cases.append((suffix, 'pair-order', body.replace('@'+read+'(', '@'+write+'(', 1)))
        if suffix != 'copyWord':
            first_shift = re.search(r'shl(?: nuw)?(?: nsw)? i64 %[-\w.]+, 6', body)
            if first_shift is None:
                raise AssertionError('actual64-byte block stride site absent')
            cases.append((suffix, 'block-stride', body.replace(first_shift[0], first_shift[0][:-1]+'5', 1)))
        final = re.search(r'select i1 %[-\w.]+, i64 0, i64 255', body)
        if final is None:
            raise AssertionError('actual final checked outcome site absent')
        cases.append((suffix, 'final-fatal', body.replace(final[0], final[0][:-3]+'0', 1)))
    return cases
