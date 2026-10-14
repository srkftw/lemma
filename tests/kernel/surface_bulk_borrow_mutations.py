"""Negative-only mutations of actual checked Surface critical-borrow IR.

No positive program is constructed here. The caller supplies complete genuine
pre/post artifacts and metadata; every mutation must reject independently.
"""
from __future__ import annotations
import copy
import re

from surface_bulk_borrow import (CAP, COPY, PAPER, DEVICE, NOTEBOOK,
                                 FAMILY, SIGNATURES, canonical)


def corpus(ir, unit, *, optimized):
    from audit_kernel import _ir_definition_body
    rows = {canonical(row['source']): row for row in unit['functions']}
    mutations = []

    def change(label, source, old, new):
        body = _ir_definition_body(ir, rows[source]['symbol'])
        if body is None or body.count(old) != 1:
            raise AssertionError('actual mutation site absent/nonunique: '+label)
        mutations.append((label, ir.replace(body, body.replace(old, new, 1), 1), unit))

    # Bind every complete authority body independently, including legacy
    # initial admission helpers relied upon by this new private borrow.
    for source in SIGNATURES:
        body = _ir_definition_body(ir, rows[source]['symbol'])
        match = re.search(r'(?m)^\s*ret \{ i64, i64 \} (%[-\w.]+)$', body)
        if match is None:
            raise AssertionError('actual checked result return absent: '+source)
        change('complete-result-'+source, source, match[0], '  ret { i64, i64 } zeroinitializer')
    for source in sorted(FAMILY):
        absent = copy.deepcopy(unit)
        absent['functions'] = [row for row in absent['functions'] if canonical(row['source']) != source]
        mutations.append(('missing-family-'+source, ir, absent))
    for field, value in [('role', 'user'), ('contract_version', 'core0-kernel-v0.3')]:
        wrong = copy.deepcopy(unit); wrong[field] = value
        mutations.append(('wrong-'+field, ir, wrong))
    wrong = copy.deepcopy(unit)
    wrong['functions'].append(copy.deepcopy(wrong['functions'][0]))
    mutations.append(('duplicate-canonical-source', ir, wrong))
    for source in (COPY+'copyFromUserAt', PAPER+'uploadOffsetAt', DEVICE+'surfaceV2At'):
        wrong = copy.deepcopy(unit)
        row = next(row for row in wrong['functions'] if canonical(row['source']) == source)
        row['args'] = row['args'][:-1]
        mutations.append(('wrong-signature-'+source, ir, wrong))
        wrong = copy.deepcopy(unit)
        row = next(row for row in wrong['functions'] if canonical(row['source']) == source)
        row['effects'] = []
        mutations.append(('missing-effects-'+source, ir, wrong))

    if optimized:
        source = 'Lemma.Kernel.Memory.AddressSpace.lookupAt'
        body = _ir_definition_body(ir, rows[source]['symbol'])
        exit_label = re.search(r'[-A-Za-z0-9_.$]+\.exit[0-9]+\.sink\.split', body)
        if exit_label is None:
            raise AssertionError('actual inlined exit-label mutation site absent')
        changed = body.replace(exit_label[0], exit_label[0]+'.tampered')
        mutations.append(('inlined-exit-suffix-changed', ir.replace(body, changed, 1), unit))
        block = _ir_definition_body(ir, rows[PAPER+'uploadWordBlockAt']['symbol'])
        reads = re.findall(r'(?m)^\s*(%[-\w.]+) = load volatile i64, ptr %[-\w.]+, align 8$', block)
        stores = re.findall(r'(?m)^\s*store volatile i64 (%[-\w.]+), ptr %[-\w.]+, align (?:8|16|32|64)$', block)
        if len(reads) != 8 or stores != reads:
            raise AssertionError('actual optimized eight read/store values absent')
        for index, value in enumerate(reads):
            token = 'store volatile i64 '+value+','
            change('substituted-word-'+str(index), PAPER+'uploadWordBlockAt', token, 'store volatile i64 0,')
        lines = block.splitlines()
        fences = [i for i, line in enumerate(lines) if line.strip() == 'call void @core0_io_fence()']
        if len(fences) != 16:
            raise AssertionError('actual optimized fences absent')
        for index, site in enumerate(fences):
            # Remove one exact indexed fence; repeat tokens are deliberately
            # selected by line position instead of an ambiguous string replace.
            altered = lines[:site]+lines[site+1:]
            mutations.append(('missing-fence-'+str(index), ir.replace(block, '\n'.join(altered)+'\n', 1), unit))
        change('ninth-block-admitted', PAPER+'uploadWordBlockAt', 'icmp ult i32 %arg0, 8', 'icmp ult i32 %arg0, 9')
        change('weakened-source-alignment', PAPER+'uploadWordBlockAt', 'and i64 %arg3, 7', 'and i64 %arg3, 3')
    else:
        change('ninth-block-admitted', PAPER+'uploadWordBlockAt', 'icmp ult i32 %arg0, 8', 'icmp ult i32 %arg0, 9')
        change('wrong-executable-permission', NOTEBOOK+'dispatchBulk',
               ', i64 4)', ', i64 1)')
        change('eighth-tile-admitted', DEVICE+'uploadBulkAt', 'icmp ult i64 7, %arg3', 'icmp ult i64 8, %arg3')
        change('unaligned-pointer-admitted', DEVICE+'uploadBulkAt', 'urem i64 %arg2, 4096', 'urem i64 %arg2, 8')
        change('copy-prefix-shortened', DEVICE+'uploadBulkAt', 'add i64 256,', 'add i64 248,')
        change('wrong-source-owner', DEVICE+'uploadBulkAt', 'i64 1, i64 %action.call.value11, i64 1',
               'i64 2, i64 %action.call.value11, i64 1')

    # Additional real caller authority in a genuine existing primitive body.
    # The family owner pins remain unchanged, so closure checking is necessary.
    source = 'Lemma.Kernel.Memory.Access.read8'
    owner = rows[source]['symbol']; body = _ir_definition_body(ir, owner)
    target = rows[PAPER+'uploadWordsAt']['symbol']
    match = re.search(r'(?m)^\s*ret \{ i64, i64 \} %[-\w.]+$', body)
    if match is None:
        raise AssertionError('actual primitive caller mutation site absent')
    inserted = '  %borrow.extra = call { i64, i64 } @'+target+'(i64 2181038080, i64 64)\n'+match[0]
    mutations.append(('extra-private-caller', ir.replace(body, body.replace(match[0], inserted, 1), 1), unit))
    return mutations


def header_corpus(ir, unit):
    """Negative-only actual pre-IR cases for the conditional header caller.

    The historical header and managed routes retain their original checker.
    The selected third route must be admitted through the complete private
    family, with exact operands; every other header caller still rejects.
    """
    from audit_kernel import _ir_definition_body
    rows = {canonical(row['source']): row for row in unit['functions']}
    mutations = []
    target = rows[CAP+'headerAt']['symbol']
    source = CAP+'requireActiveAt'
    body = _ir_definition_body(ir, rows[source]['symbol'])
    token = '@'+target+'(i64 %arg0, i64 %arg1)'
    if body is None or body.count(token) != 1:
        raise AssertionError('actual borrowed header argument site absent/nonunique')
    for label, altered in [('descriptor-substituted', '(i64 %arg1, i64 %arg1)'),
                           ('base-substituted', '(i64 %arg0, i64 0)')]:
        mutations.append(('header-'+label,
                          ir.replace(body, body.replace(token, '@'+target+altered), 1), unit))
    for source in sorted(FAMILY):
        absent = copy.deepcopy(unit)
        absent['functions'] = [row for row in absent['functions']
                               if canonical(row['source']) != source]
        mutations.append(('header-missing-family-'+source, ir, absent))
    for field, value in [('role', 'user'), ('contract_version', 'core0-kernel-v0.3')]:
        wrong = copy.deepcopy(unit); wrong[field] = value
        mutations.append(('header-wrong-'+field, ir, wrong))
    for source in (CAP+'headerAt', CAP+'requireActiveAt', NOTEBOOK+'dispatchBulk',
                   'Lemma.Kernel.Task.capture'):
        body = _ir_definition_body(ir, rows[source]['symbol'])
        match = re.search(r'(?m)^\s*ret \{ i64, i64 \} %[-\w.]+$', body)
        if match is None:
            raise AssertionError('actual header authority return absent: '+source)
        altered = body.replace(match[0], '  ret { i64, i64 } zeroinitializer', 1)
        mutations.append(('header-authority-body-'+source, ir.replace(body, altered, 1), unit))
    source = 'Lemma.Kernel.Memory.Access.read8'
    body = _ir_definition_body(ir, rows[source]['symbol'])
    match = re.search(r'(?m)^\s*ret \{ i64, i64 \} %[-\w.]+$', body)
    if match is None:
        raise AssertionError('actual extra header caller site absent')
    inserted = '  %header.extra = call { i64, i64 } @'+target+'(i64 8258, i64 2181308416)\n'+match[0]
    mutations.append(('header-extra-caller', ir.replace(body, body.replace(match[0], inserted, 1), 1), unit))
    return mutations
