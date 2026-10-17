"""Closed Package/User2 inlining of two genuinely elaborated Surface callbacks.

No target code is interpreted here. Complete source-owned pre/post bodies and
independent loop/access/fault gates qualify only this existing LLVM policy.
"""
from __future__ import annotations
import hashlib
import re
from core0_common import Core0Error
from package_closure_deployment import CONFIGURATIONS, SOFTWARE_DEPLOYMENT, NOTEBOOK_ROOT

FIELD = 'surface_word_inline'
VERSION = 'lemma-surface-word-inline-v1'
POLICY = 'two-checked-callbacks-internal-LLVM-O2'
PREFIX = '_private.Lemma.Ink.Surface.0.Lemma.Ink.Surface.'
CALLBACKS = (PREFIX + 'tileLoadWordStep', PREFIX + 'bulkCopyWord')
CALLERS = ('Lemma.Ink.Surface.loadTile', PREFIX + 'bulkPrepareStep')
GATHER = PREFIX + 'gatherWord'
ARGS = ['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64']
EFFECTS = ['checked-access', 'virtual-read', 'virtual-write']


def require(value, message):
    if not value:
        raise Core0Error(message)


def catalog(unit):
    require(isinstance(unit, dict), 'Surface-word unit is not a map')
    if FIELD not in unit:
        return None
    from package_companion_deployment import ALL_CONFIGURATIONS as JOINED, SOFTWARE_DEPLOYMENT as JOINED_SOFTWARE, USER_ROOTS
    joined=unit.get('configuration') in JOINED
    selected_root=USER_ROOTS['notebook'][1] if joined else NOTEBOOK_ROOT
    from dirty_batch_notebook_target import numeric_candidate, numeric_contract, numeric_root
    if numeric_candidate(unit):
        numeric_contract(unit)
        selected_root=numeric_root(unit)
    from reader_deployment import CONFIGURATIONS as READER, SOFTWARE_DEPLOYMENT as READER_SOFTWARE
    from product_reader_deployment import ALL_CONFIGURATIONS as PRODUCT_READER, software_deployment_for as product_reader_software
    from chooser_reader_deployment import CONFIGURATIONS as CHOOSER, SOFTWARE_DEPLOYMENT as CHOOSER_SOFTWARE
    from package_companion_deployment import software_deployment_for as package_software
    if joined: JOINED_SOFTWARE=package_software(unit['configuration'])
    selected_software=CHOOSER_SOFTWARE if unit.get('configuration') in CHOOSER else product_reader_software(unit['configuration']) if unit.get('configuration') in PRODUCT_READER else READER_SOFTWARE if unit.get('configuration') in READER else JOINED_SOFTWARE if joined else SOFTWARE_DEPLOYMENT
    require(unit.get('configuration') in CONFIGURATIONS + JOINED + READER + PRODUCT_READER + CHOOSER and
            unit.get('role') == 'user' and unit.get('contract_version') == 'core0-user-v0.2' and
            type(unit.get('schema_version')) is int and unit.get('schema_version') == 2 and unit.get('artifact_category') == 'development-user-unit' and
            unit.get('managed_policy') == 'lemma-notebook-arithmetic-v1' and
            unit.get('software_deployment') == selected_software and
            unit.get('image_key') == 'notebook' and type(unit.get('image_id')) is int and unit.get('image_id') == 2 and
            unit.get('boot_role') == 'notebook', 'Surface-word authority escaped Package Notebook/User2')
    roots = unit.get('roots')
    require(isinstance(roots, list) and len(roots) == 1 and isinstance(roots[0], dict) and
            set(roots[0]) == {'source', 'symbol', 'id', 'args'} and roots[0].get('source') == selected_root and
            type(roots[0].get('id')) is int and roots[0].get('id') == 1 and roots[0].get('args') == ['u64'], 'Surface-word selected root differs')
    rows = unit.get('functions')
    require(isinstance(rows, list) and rows and all(isinstance(r, dict) and isinstance(r.get('source'), str) and
            isinstance(r.get('symbol'), str) for r in rows),
            'Surface-word function inventory missing')
    by = {r.get('source'): r for r in rows}
    require(len(by) == len(rows) and len({r.get('symbol') for r in rows}) == len(rows) and
            all(isinstance(r.get('symbol'), str) and re.fullmatch(r'[A-Za-z0-9_.$]+', r['symbol']) for r in rows),
            'Surface-word source/symbol inventory not one-to-one')
    require(selected_root in by and roots[0]['symbol'] == by[selected_root]['symbol'] and
            by[selected_root].get('args') == ['u64'], 'Surface-word root is not its genuine declaration')
    c = unit[FIELD]
    require(isinstance(c, dict) and set(c) == {'contract_version', 'policy', 'callbacks'} and
            c['contract_version'] == VERSION and c['policy'] == POLICY and
            isinstance(c['callbacks'], list) and len(c['callbacks']) == 2, 'Surface-word catalog differs')
    for r, source, caller in zip(c['callbacks'], CALLBACKS, CALLERS):
        require(isinstance(r, dict) and set(r) == {'source', 'symbol', 'args', 'effects', 'caller', 'budget', 'count'} and
                r['source'] == source and r['caller'] == caller and r['args'] == ARGS and r['effects'] == EFFECTS and
                type(r['budget']) is int and r['budget'] == 64 and type(r['count']) is int and r['count'] == 64,
                'Surface-word callback source/signature/closed iteration differs')
        require(source in by and all(by[source].get(k) == r[k] for k in ('source', 'symbol', 'args', 'effects')) and
                caller in by and by[caller].get('effects') == EFFECTS,
                'Surface-word catalog is not its genuine declaration/caller')
    require(by[CALLERS[0]].get('args') == ['u64'] * 4 and by[CALLERS[1]].get('args') == ARGS and
            GATHER in by and by[GATHER].get('args') == ['u64'] and
            by[GATHER].get('effects') == ['checked-access', 'virtual-read'], 'Surface-word dependency signature differs')
    return c


def removed_symbols(unit):
    """Caller must first validate the actual optimized IR; never a general exemption."""
    c = catalog(unit)
    return set() if c is None else {r['symbol'] for r in c['callbacks']}


def _bodies(ir):
    rows = re.findall(r'^(define[^\n]*@([A-Za-z0-9_.$-]+)\([^\n]*\).*?^})', ir, re.M | re.S)
    require(len(rows) == len({r[1] for r in rows}), 'Surface-word duplicate LLVM owner')
    return {symbol: body for body, symbol in rows}


def normalized_body(body, ir, names):
    # Rebind exact source owners and full attribute groups, never discard an
    # instruction, operand, error edge or attribute. Group numbers are module-local.
    groups = dict(re.findall(r'^attributes #(\d+) = \{([^\n]*)\}$', ir, re.M))
    def group(match):
        require(match[1] in groups, 'Surface-word attribute group absent')
        return '#{' + groups[match[1]].strip() + '}'
    body = re.sub(r'#(\d+)', group, body)
    body = re.sub(r'@([A-Za-z0-9_.$-]+)', lambda m: '@' + names.get(m[1], m[1]), body)
    for symbol, source in sorted(names.items(), key=lambda row: -len(row[0])):
        body = re.sub(r'(?<![-A-Za-z0-9_.$])' + re.escape(symbol) + r'(?=\.exit(?:[0-9.:,\]\s]|$))', source, body)
    return ' '.join(' '.join(line.split(';', 1)[0] for line in body.splitlines()).split())


def _post_safety(ir, unit):
    """Independent finite CFG/dataflow gates, also tested without body pins."""
    from audit_core0 import _structured_ir_blocks, _structured_successors, _structured_reachable
    rows = {r['source']: r for r in unit['functions']}
    bodies = _bodies(ir)
    symbols = {s: rows[s]['symbol'] for s in (*CALLBACKS, *CALLERS, GATHER)}
    require(all(symbols[s] not in bodies for s in CALLBACKS), 'Surface-word optimized callback remains')
    load = bodies[symbols[CALLERS[0]]]
    def blocks_of(body):
        return _structured_ir_blocks('\n'.join(line.split(';', 1)[0].rstrip()
                                              for line in body.splitlines()[1:-1]))

    def ordered(block, lines):
        require(all(block.count(line) == 1 for line in lines),
                'Surface-word ordered primitive/dataflow line absent or duplicated')
        require([block.index(line) for line in lines] == sorted(block.index(line) for line in lines),
                'Surface-word primitive/address/check order differs')

    blocks = blocks_of(load)
    edges = _structured_successors(blocks)
    required = (
        '%indvars.iv = phi i64 [ 0, %action.if.then.0 ], [ %indvars.iv.next, %action.fold.latch.10 ]',
        '%indvars.iv.next = add nuw nsw i64 %indvars.iv, 1',
        '%exitcond13.not = icmp eq i64 %indvars.iv.next, 64',
        '%udiv51.i = lshr i64 %indvars.iv, 1',
        '%bin8.i = mul i64 %bin7.i, %udiv41',
        '%urem17.i = shl nuw nsw i64 %indvars.iv, 3',
        '%bin19.i = and i64 %urem17.i, 8',
        '%bin29.i = add nuw nsw i64 %urem17.i, 132352',
        'store volatile i64 %action.call.value24.i, ptr %execution.mem.0.pointer.4.i.i, align 8',
        '%action.call.value24.i = extractvalue { i64, i64 } %action.call.result21.i, 1',
        '%cmp25.i = icmp eq i64 %action.call.status-word22.i, 0',
        '%action.result.status-word36.i = and i64 %action.call.status-word22.i, 255',
    )
    require(all(sum(line.strip() == expected for line in load.splitlines()) == 1 for expected in required),
            'Surface-word full tile loop/address/value/status differs')
    require(len(re.findall(r' = call \{ i64, i64 \} @' + re.escape(symbols[GATHER]) + r'\(i64 %bin20.i\)', load)) == 1 and
            len(re.findall(r'store volatile i64 ', load)) == 1,
            'Surface-word gather/write cardinality differs')
    branch = 'br i1 %cmp25.i, label %' + symbols[CALLBACKS[0]] + '.exit.thread, label %' + symbols[CALLBACKS[0]] + '.exit'
    require(branch in blocks['action.fold.body.9'], 'Surface-word first read error branch differs')
    ordered(blocks['action.fold.body.9'], [
        '%bin7.i = add nuw nsw i64 %udiv51.i, %lshr2.i',
        '%bin8.i = mul i64 %bin7.i, %udiv41',
        '%bin14.i = add nuw nsw i64 %bin9.i, %bin19.i',
        '%bin20.i = add i64 %bin14.i, %bin8.i',
        '%action.call.result21.i = call { i64, i64 } @' + symbols[GATHER] + '(i64 %bin20.i)',
        '%action.call.status-word22.i = extractvalue { i64, i64 } %action.call.result21.i, 0',
        '%cmp25.i = icmp eq i64 %action.call.status-word22.i, 0', branch])
    ordered(blocks[symbols[CALLBACKS[0]] + '.exit.thread'], [
        '%bin29.i = add nuw nsw i64 %urem17.i, 132352',
        '%action.call.value24.i = extractvalue { i64, i64 } %action.call.result21.i, 1',
        '%execution.mem.0.pointer.4.i.i = inttoptr i64 %bin29.i to ptr',
        'store volatile i64 %action.call.value24.i, ptr %execution.mem.0.pointer.4.i.i, align 8',
        'br label %action.fold.latch.10'])
    require(blocks['action.fold.latch.10'][-1] ==
            'br i1 %exitcond13.not, label %action.if.merge.2, label %action.fold.body.9' and
            '%action.result.partial42 = insertvalue { i64, i64 } poison, i64 %action.result.status-word41, 0' in blocks['action.if.merge.2'] and
            '%action.if.status39 = phi i64 [ 0, %action.fold.latch.10 ], [ %action.result.status-word36.i, %' + symbols[CALLBACKS[0]] + '.exit ], [ 0, %action.fold.latch.18 ], [ %action.fold.callback-status-word32, %action.fold.body.17 ]' in blocks['action.if.merge.2'],
            'Surface-word full tile exit/status prefix differs')
    without = dict(edges); without['action.fold.body.9'] = (symbols[CALLBACKS[0]] + '.exit',)
    require(not _structured_reachable(without, 'entry', symbols[CALLBACKS[0]] + '.exit.thread'),
            'Surface-word store reachable after failed gather')
    copy = bodies[symbols[CALLERS[1]]]
    blocks = blocks_of(copy)
    edges = _structured_successors(blocks)
    required = (
        '%indvars.iv = phi i64 [ 0, %action.if.then.146 ], [ %indvars.iv.next, %action.fold.latch.153 ]',
        '%indvars.iv.next = add nuw nsw i64 %indvars.iv, 1',
        '%exitcond176.not = icmp eq i64 %indvars.iv.next, 64',
        '%11 = shl nuw nsw i64 %indvars.iv, 3',
        '%bin3.i = add nuw nsw i64 %11, 132352',
        '%bin296 = shl nuw nsw i64 %cast0, 9',
        '%bin297 = add nuw nsw i64 %bin296, 1089792',
        '%invariant.op = add nuw nsw i64 %bin296, 1024256',
        '%.reass = add nuw nsw i64 %invariant.op, %11',
        '%bin11.i = add nuw nsw i64 %bin297, %11',
        '%execution.mem.0.loaded.5.i.i = load volatile i64, ptr %execution.mem.0.pointer.4.i6.i, align 8',
        '%or.cond.i.i = icmp samesign ult i64 %.reass, 1073676281',
        'store volatile i64 %execution.mem.0.loaded.5.i.i, ptr %execution.mem.0.pointer.4.i.i, align 8',
        '%action.fold.status308 = phi i64 [ 0, %action.fold.latch.153 ], [ 7, %action.fold.body.152 ]',
    )
    require(all(sum(line.strip() == expected for line in copy.splitlines()) == 1 for expected in required),
            'Surface-word copy loop/read/value/error bound differs')
    require(blocks['action.fold.body.152'][-1] == 'br i1 %or.cond.i.i, label %action.fold.latch.153, label %action.fold.outcome.156' and
            len(re.findall(r'\bload volatile i64,', copy)) == 1,
            'Surface-word ordered read/check/write prefix differs')
    ordered(blocks['action.fold.body.152'], [
        '%bin3.i = add nuw nsw i64 %11, 132352',
        '%execution.mem.0.pointer.4.i6.i = inttoptr i64 %bin3.i to ptr',
        '%execution.mem.0.loaded.5.i.i = load volatile i64, ptr %execution.mem.0.pointer.4.i6.i, align 8',
        '%.reass = add nuw nsw i64 %invariant.op, %11',
        '%or.cond.i.i = icmp samesign ult i64 %.reass, 1073676281',
        'br i1 %or.cond.i.i, label %action.fold.latch.153, label %action.fold.outcome.156'])
    ordered(blocks['action.fold.latch.153'], [
        '%bin11.i = add nuw nsw i64 %bin297, %11',
        '%execution.mem.0.pointer.4.i.i = inttoptr i64 %bin11.i to ptr',
        'store volatile i64 %execution.mem.0.loaded.5.i.i, ptr %execution.mem.0.pointer.4.i.i, align 8',
        '%indvars.iv.next = add nuw nsw i64 %indvars.iv, 1',
        '%exitcond176.not = icmp eq i64 %indvars.iv.next, 64',
        'br i1 %exitcond176.not, label %action.fold.outcome.156, label %action.fold.body.152'])
    require('%action.result.status-word323 = and i64 %action.if.status321, 255' in blocks['action.if.merge.14'] and
            '%action.result.partial324 = insertvalue { i64, i64 } poison, i64 %action.result.status-word323, 0' in blocks['action.if.merge.14'],
            'Surface-word copy return status differs')
    without = dict(edges); without['action.fold.body.152'] = ('action.fold.outcome.156',)
    require(not _structured_reachable(without, 'action.fold.body.152', 'action.fold.latch.153'),
            'Surface-word copy write reachable on failed range')
    gather = bodies[symbols[GATHER]]
    blocks = blocks_of(gather); edges = _structured_successors(blocks)
    require(len(re.findall(r'\bload volatile i64,', gather)) == 3 and not re.search(r'\b(?:store|call)\b', gather),
            'Surface-word gather acquired or lost a primitive')
    ordered(blocks['entry'], ['%urem1 = and i64 %arg0, 7', '%cmp3 = icmp eq i64 %urem1, 0',
        'br i1 %cmp3, label %execution.mem.0.lookup.1.i19, label %action.if.else.4'])
    ordered(blocks['execution.mem.0.lookup.1.i19'], ['%0 = add i64 %arg0, -65536',
        '%or.cond.i20 = icmp ult i64 %0, 1073676281',
        'br i1 %or.cond.i20, label %execution.mem.0.access.4.i21, label %action.if.merge.5'])
    ordered(blocks['execution.mem.0.access.4.i21'], ['%execution.mem.0.pointer.4.i22 = inttoptr i64 %arg0 to ptr',
        '%execution.mem.0.loaded.5.i23 = load volatile i64, ptr %execution.mem.0.pointer.4.i22, align 8',
        'br label %action.if.merge.5'])
    ordered(blocks['action.if.else.4'], ['%bin11 = and i64 %arg0, -8', '%1 = add i64 %bin11, -65536',
        '%or.cond.i8 = icmp ult i64 %1, 1073676281',
        'br i1 %or.cond.i8, label %action.if.then.9, label %action.if.merge.5'])
    ordered(blocks['action.if.then.9'], ['%execution.mem.0.pointer.4.i10 = inttoptr i64 %bin11 to ptr',
        '%execution.mem.0.loaded.5.i11 = load volatile i64, ptr %execution.mem.0.pointer.4.i10, align 8',
        '%2 = add nsw i64 %bin11, -65528', '%or.cond.i = icmp samesign ult i64 %2, 1073676281',
        'br i1 %or.cond.i, label %action.if.then.15, label %action.if.merge.5'])
    ordered(blocks['action.if.then.15'], ['%bin21 = add nuw nsw i64 %bin11, 8',
        '%execution.mem.0.pointer.4.i = inttoptr i64 %bin21 to ptr',
        '%execution.mem.0.loaded.5.i = load volatile i64, ptr %execution.mem.0.pointer.4.i, align 8',
        '%bin30 = shl nuw nsw i64 %urem1, 3', '%lshr32 = lshr i64 %execution.mem.0.loaded.5.i11, %bin30',
        '%bin37 = sub nsw i64 0, %bin30', '%shift.count38 = and i64 %bin37, 56',
        '%shl39 = shl i64 %execution.mem.0.loaded.5.i, %shift.count38', '%bin40 = or i64 %shl39, %lshr32',
        'br label %action.if.merge.5'])
    require('%action.if.status45 = phi i64 [ 0, %action.if.then.15 ], [ 7, %action.if.then.9 ], [ 0, %execution.mem.0.access.4.i21 ], [ 7, %execution.mem.0.lookup.1.i19 ], [ 7, %action.if.else.4 ]' in blocks['action.if.merge.5'] and
            '%action.if.value46 = phi i64 [ %bin40, %action.if.then.15 ], [ 0, %action.if.then.9 ], [ %execution.mem.0.loaded.5.i23, %execution.mem.0.access.4.i21 ], [ 0, %execution.mem.0.lookup.1.i19 ], [ 0, %action.if.else.4 ]' in blocks['action.if.merge.5'],
            'Surface-word gather first-fault/full-word result differs')
    for block, failed in [('execution.mem.0.lookup.1.i19', 'execution.mem.0.access.4.i21'),
                          ('action.if.else.4', 'action.if.then.9'), ('action.if.then.9', 'action.if.then.15')]:
        without = dict(edges); without[block] = ('action.if.merge.5',)
        require(not _structured_reachable(without, 'entry', failed), 'Surface-word gather load reachable after failed bound')
    return {'tile_loop_iterations': 64, 'copy_loop_iterations': 64,
            'tile_write_after_successful_gather': True, 'copy_read_before_checked_write': True,
            'gather_aligned_and_two_word_fault_prefix': True,
            'volatile_element_bits': 64, 'constant_tile_span': [0x20500, 0x20700],
            'write_range_error': 7, 'hardware_permission_and_faults': 'unchanged actual volatile instructions'}


def validate(ir, unit, *, optimized):
    c = catalog(unit)
    if c is None:
        return None
    rows = {r['source']: r for r in unit['functions']}
    names = {r['symbol']: r['source'] for r in unit['functions']}
    bodies = _bodies(ir)
    phase = 'post' if optimized else 'pre'
    observed = {}
    for source, expected in BODY_PINS[phase].items():
        symbol = rows[source]['symbol']
        require(symbol in bodies, 'Surface-word required definition absent: ' + source)
        digest = hashlib.sha256(normalized_body(bodies[symbol], ir, names).encode()).hexdigest()
        require(digest == expected, 'Surface-word complete checked body differs: ' + source + '/' + phase)
        observed[source] = digest
    headers = {}
    if not optimized:
        for r in c['callbacks']:
            header = bodies[r['symbol']].splitlines()[0]
            expected = 'define internal { i64, i64 } @' + r['symbol'] + '(' + ', '.join(
                ('i32 signext ' if i < 2 else 'i64 ') + '%arg' + str(i) for i in range(7)) + ') nounwind {'
            require(header == expected, 'Surface-word selected internal header differs')
            incoming = sorted(names[owner] for owner, body in bodies.items()
                              if re.search(r'\bcall\s+[^\n]*@' + re.escape(r['symbol']) + r'\(', body))
            require(incoming == [r['caller']], 'Surface-word exhaustive callback callers differ')
            headers[r['symbol']] = header
    safety = _post_safety(ir, unit) if optimized else {'source_complete_loops_and_fault_paths': True}
    return {'contract_version': VERSION, 'phase': phase, 'callbacks': c['callbacks'],
            'headers': headers, 'complete_body_identities': observed, 'safety': safety,
            'removed_symbols': sorted(removed_symbols(unit)) if optimized else []}


# Immutable original ordinary-source compiler diagnostic. Full attribute values
# participate; artifact-provided hashes never constitute observer authority.
BODY_PINS = {'pre': {'_private.Lemma.Ink.Surface.0.Lemma.Ink.Surface.tileLoadWordStep': 'c20d11b24ef983df56a5c3f928b5040e1d7469bacd85b6c73bb82045151e5346', '_private.Lemma.Ink.Surface.0.Lemma.Ink.Surface.bulkCopyWord': 'f2fbbb8874b676f448b812b9146b41c90c249d0371401bcdfbc13569779dbd21', 'Lemma.Ink.Surface.loadTile': '640cb41c43123ebb3fce4664b6dacc34f33711967c33a86a321f2e39807071e4', '_private.Lemma.Ink.Surface.0.Lemma.Ink.Surface.bulkPrepareStep': 'b6d2c5d55bbc6ea99cde0306147bf7a36780b7d09b042de3aee1eabacfb1753f', '_private.Lemma.Ink.Surface.0.Lemma.Ink.Surface.gatherWord': '7a178f5d3d8951c201ac4ea2f8ebadeb2e279f19f85dd98ebcfc8b151f0ee504'}, 'post': {'Lemma.Ink.Surface.loadTile': 'f043dd7569831e050d1303ae1c3432d4af24bc563cfb16340f2742be17353f01', '_private.Lemma.Ink.Surface.0.Lemma.Ink.Surface.bulkPrepareStep': 'd3fb0d5ac60b27131d288931e25000e261dbf9fc04dc79a6c6fdb83d82586abc', '_private.Lemma.Ink.Surface.0.Lemma.Ink.Surface.gatherWord': 'de1aad17805324c1e66ae8d2ee8bdb5cc17fce1a0ca4470fe7c732066a017d0d'}}
