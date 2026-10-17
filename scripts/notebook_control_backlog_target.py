"""Exact additive admission of the guest's bounded control backlog.

This inspects genuine catalogs/LLVM only. It neither queues user input nor
interprets documents on behalf of the running guest. Old authorities are exact
predecessors; all unchanged pre-LLVM bodies remain load-bearing.
"""
import hashlib
import json
import re
from pathlib import Path

from core0_common import Core0Error
from paper_next import canonical

VERSION = 'lemma-notebook-control-backlog-artifact/1'
AUTHORITY = Path(__file__).resolve().parents[1] / 'tooling/notebook-control-backlog-target-authority.json'
VERSION2 = 'lemma-notebook-control-backlog-artifact/2'
AUTHORITY2 = AUTHORITY.with_name('notebook-control-backlog-target-authority-v2.json')
HINT = 'authored-hint-publication-target-authority-v2.json'
WATCHDOG = 'trial-watchdog-target-authority.json'
CONFIGURATIONS = frozenset(
    f'lemmasim-silicon-{stem}-bulk-{suffix}'
    for stem in ('package-chooser', 'package-reader', 'usb-clocked-reader-entry2')
    for suffix in ('notebook', 'initialize')
) | {'lemmasim-silicon-product-course-reader-bulk-notebook',
     'lemmasim-silicon-product-course-watchdog-bulk-notebook'}
PREFIX = 'Lemma.Notebook.ControlBacklog.'
NOTEBOOK = 'Lemma.Applications.Notebook.'
FAMILY = frozenset(PREFIX + name for name in (
    'base', 'capacity', 'clear', 'count', 'deferFailure', 'front', 'full', 'get',
    'malformed', 'pop', 'push', 'put', 'reset', 'takeFailure'))
ADDED = FAMILY | frozenset(NOTEBOOK + name for name in (
    'applyBookTap', 'bookMathTap', 'bookInkTap', 'bufferedBookInk',
    'pumpBookControlBacklog', 'pumpBookTap', 'pumpBookTap.changed', 'queueBookTap'))
HOME_INK = NOTEBOOK + 'bufferHomeInk'
PIN_FIELDS = frozenset(('catalog_sha256', 'catalog_sha256_by_configuration',
                       'pre_function_count', 'post_function_count', 'function_count',
                       'pre_sha256', 'post_sha256'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise Core0Error(message)


def present(unit):
    return {canonical(row['source']) for row in unit.get('functions', [])
            if canonical(row['source']).startswith(PREFIX)}


def home_ink(unit):
    return any(canonical(row['source']) == HOME_INK for row in unit.get('functions', []))


def added(unit):
    return ADDED | ({HOME_INK} if home_ink(unit) else set())


def changed(unit):
    loops = unit.get('used_loops', [])
    require(len(loops) == 1 and loops[0]['stable_id'] == 'action.loop',
            'Control backlog requires the maintained single guest loop')
    loop = canonical(loops[0]['callback'])
    require(loop in {NOTEBOOK + name for name in (
        'bookmarkStep', 'readerRecoverableStep', 'chooserReaderStep')},
        'Control backlog escaped the three maintained reader loops')
    return {NOTEBOOK + 'bookmarkInputSample.acceptSample',
            NOTEBOOK + 'cancelBookmarkInput', loop}


def entry(unit):
    require(present(unit) == FAMILY and unit.get('configuration') in CONFIGURATIONS and
            (unit.get('role'), unit.get('image_key'), unit.get('image_id'), unit.get('contract_version')) ==
            ('user', 'notebook', 2, 'core0-user-v0.2'),
            'Control backlog escaped its exact eight Notebook User2 deployments')
    successor = home_ink(unit)
    authority = json.loads((AUTHORITY2 if successor else AUTHORITY).read_text())
    require(set(authority) == {'schema', 'configurations'} and authority['schema'] == (VERSION2 if successor else VERSION) and
            set(authority['configurations']) == CONFIGURATIONS,
            'Control backlog complete configuration inventory differs')
    item = authority['configurations'][unit['configuration']]
    fields = {'predecessor_authority', 'predecessor_authority_sha256',
                         'previous_role_sha256', 'role', 'number_pad_pool_alpha',
                         'changed_functions', 'added_functions',
                         'shared_pre_function_count', 'shared_pre_functions_sha256'}
    if successor:
        fields |= {'previous_backlog_authority_sha256', 'previous_backlog_role_sha256',
                   'shared_v1_pre_function_count', 'shared_v1_pre_functions_sha256', 'v1_changed_functions'}
        previous = json.loads(AUTHORITY.read_text())
        require(previous.get('schema') == VERSION and set(previous.get('configurations', {})) == CONFIGURATIONS and
                item.get('previous_backlog_authority_sha256') == hashlib.sha256(AUTHORITY.read_bytes()).hexdigest() and
                item.get('previous_backlog_role_sha256') == digest(previous['configurations'][unit['configuration']]['role']) and
                item.get('v1_changed_functions') == [NOTEBOOK + 'queueBookTap'],
                'Home ink exact backlog-v1 predecessor differs')
    require(set(item) == fields and
            set(item['changed_functions']) == changed(unit) and set(item['added_functions']) == added(unit),
            'Control backlog exact declaration delta differs')
    return item


def refined(unit, previous, predecessor):
    if not present(unit):
        return previous
    item = entry(unit)
    predecessor = Path(predecessor)
    expected = WATCHDOG if 'watchdog' in unit['configuration'] else HINT
    require(predecessor.name == expected and item['predecessor_authority'] == expected and
            item['predecessor_authority_sha256'] == hashlib.sha256(predecessor.read_bytes()).hexdigest() and
            item['previous_role_sha256'] == digest(previous),
            'Control backlog exact predecessor differs')
    successor = item['role']
    require(set(successor) == set(previous) and
            all(successor[k] == previous[k] for k in previous if k not in PIN_FIELDS),
            'Control backlog changed unrelated historical contract fields')
    for phase in ('pre', 'post'):
        require(successor[phase + '_function_count'] == previous[phase + '_function_count'] + len(added(unit)) and
                re.fullmatch('[0-9a-f]{64}', successor[phase + '_sha256']) is not None,
                'Control backlog complete corpus count/pin differs')
    if 'function_count' in previous:
        require(successor['function_count'] == previous['function_count'] + len(added(unit)),
                'Control backlog complete source count differs')
    catalogs = successor.get('catalog_sha256_by_configuration')
    require((catalogs is None or set(catalogs) == set(previous['catalog_sha256_by_configuration'])) and
            (catalogs[unit['configuration']] if catalogs is not None else successor['catalog_sha256']) == digest(unit),
            'Control backlog complete typed/effect/root catalog differs')
    return successor


def semantics(ir, unit):
    if not present(unit):
        return None
    from audit_kernel import (_ir_definition_body, _local_call_arguments,
                              validate_checked_call_gate, validate_boolean_gate)
    from usb_recovery_target import corpus
    wanted = entry(unit)
    actual = corpus(ir, unit)
    shared = {name: row for name, row in actual['functions'].items()
              if name not in added(unit) and name not in changed(unit)}
    require(added(unit) <= actual['functions'].keys() and
            len(shared) == wanted['shared_pre_function_count'] and
            digest(shared) == wanted['shared_pre_functions_sha256'],
            'Control backlog changed an existing body/signature/effect outside three input owners')
    if home_ink(unit):
        shared_v1 = {name: row for name, row in actual['functions'].items()
                     if name not in (HOME_INK, NOTEBOOK + 'queueBookTap')}
        require(len(shared_v1) == wanted['shared_v1_pre_function_count'] and
                digest(shared_v1) == wanted['shared_v1_pre_functions_sha256'],
                'Home ink changed a backlog-v1 body/signature/effect outside its one busy-input owner')
    rows = {canonical(row['source']): row for row in unit['functions']}

    def body(name):
        return _ir_definition_body(ir, rows[name]['symbol'])

    def calls(owner, target):
        return _local_call_arguments(body(owner), rows[target]['symbol'])

    for name, value in (('base', 0x20d00), ('capacity', 8), ('full', 242), ('malformed', 243)):
        width = 'i64' if name in ('base', 'capacity') else 'i8'
        require(body(PREFIX + name).strip() == 'entry:\n  ret ' + width + ' ' + str(value),
                'Control backlog fixed BSS/capacity/error differs: ' + name)
    push = PREFIX + 'push'
    require(calls(push, PREFIX + 'count') == [''] and calls(push, PREFIX + 'get') == ['i64 8'],
            'Control backlog push omitted validated count/tail')
    writes = calls(push, PREFIX + 'put')
    require(len(writes) == 10 and
            all(re.fullmatch(r'i64 %[-\w.]+, i64 %arg' + str(i), writes[i]) for i in range(8)) and
            writes[8].startswith('i64 8, ') and writes[9].startswith('i64 16, '),
            'Control backlog context order or data-before-publication differs')
    require('icmp ult i64 %arg0, 4096' in body(push) and 'icmp ult i64 %arg1, 4096' in body(push),
            'Control backlog coordinate bounds absent')
    require(calls(PREFIX + 'count', PREFIX + 'get') == ['i64 0', 'i64 8', 'i64 16'] and
            calls(PREFIX + 'pop', PREFIX + 'count') == [''] and
            calls(PREFIX + 'pop', PREFIX + 'get') == ['i64 0'] and
            [x.split(',')[0] for x in calls(PREFIX + 'pop', PREFIX + 'put')] == ['i64 0', 'i64 16'],
            'Control backlog ring validation/pop order differs')
    require(calls(PREFIX + 'reset', PREFIX + 'clear') == [''] and
            calls(PREFIX + 'reset', PREFIX + 'put') == ['i64 24, i64 0'] and
            calls(NOTEBOOK + 'cancelBookmarkInput', PREFIX + 'reset') == [''],
            'Control backlog cancellation omitted its private queue')
    pump = NOTEBOOK + 'pumpBookTap'
    require(calls(pump, PREFIX + 'front') == [''] and calls(pump, PREFIX + 'pop') == [''] and
            len(calls(pump, NOTEBOOK + 'applyBookTap')) == 1,
            'Control backlog missing actual FIFO dequeue/application')
    validate_checked_call_gate(body(pump), rows[PREFIX + 'pop']['symbol'], rows[NOTEBOOK + 'applyBookTap']['symbol'])
    require(calls(pump, NOTEBOOK + 'get') == ['i64 72', 'i64 80'] and
            calls(pump, NOTEBOOK + 'packageGet') == ['i64 160', 'i64 8'] and
            len(calls(pump, NOTEBOOK + 'pumpBookTap.changed')) == 6,
            'Control backlog omitted namespace/page/package/edition/CRC/node validation')
    # Read the actual SSA values returned by the checked calls, rather than
    # accepting six unrelated equality tests. Every saved context component
    # must equal the current one on every path to the real action.
    def returned(owner, target):
        text = body(owner)
        results = re.findall(r'(%[-\w.]+) = call \{ i64, i64 \} @' +
                             re.escape(rows[target]['symbol']) + r'\([^\n]*\)', text)
        values = []
        for result in results:
            found = re.findall(r'(%[-\w.]+) = extractvalue \{ i64, i64 \} ' +
                               re.escape(result) + r', 1$', text, re.M)
            require(len(found) == 1, 'Control backlog checked value extraction differs')
            values.append(found[0])
        return values
    reads = returned(pump, 'Lemma.User.Memory.read64')
    current = returned(pump, NOTEBOOK + 'get') + reads[8:] + returned(pump, NOTEBOOK + 'packageGet')
    require(len(reads) == 10 and len(current) == 6,
            'Control backlog exact saved/current context read inventory differs')
    for now, saved in zip(current, reads[2:8]):
        guards = re.findall(r'(%[-\w.]+) = icmp eq i64 ' + re.escape(now) +
                            r', ' + re.escape(saved) + r'$', body(pump), re.M)
        require(len(guards) == 1, 'Control backlog saved context comparison differs')
        validate_boolean_gate(body(pump), guards[0], rows[NOTEBOOK + 'applyBookTap']['symbol'])
    ink = NOTEBOOK + 'bufferedBookInk'
    require(calls(ink, NOTEBOOK + 'numericMarkPadOverdraw') == [''] and
            calls(ink, NOTEBOOK + 'beginStroke') == [''] and
            calls(ink, NOTEBOOK + 'appendRaw') == [''] and
            len(re.findall(r'call zeroext i1 @' + re.escape(rows[NOTEBOOK + 'bookInkTap']['symbol']) +
                           r'\(', body(NOTEBOOK + 'queueBookTap'))) == 1,
            'Busy ink bypasses original raw construction or writing-region guard')
    loop = next(x for x in changed(unit) if x.endswith('Step'))
    require(calls(loop, NOTEBOOK + 'pumpBookControlBacklog') == [''] and
            body(loop).index('@' + rows[NOTEBOOK + 'pumpRefreshRestoredBatched']['symbol'] + '(') <
            body(loop).index('@' + rows[NOTEBOOK + 'pumpBookControlBacklog']['symbol'] + '('),
            'Control backlog must settle the old refresh before applying one queued action')
    if home_ink(unit):
        require(rows[HOME_INK]['args'] == ['u64', 'u64'] and
                calls(NOTEBOOK + 'queueBookTap', HOME_INK) == ['i64 %arg0, i64 %arg1'] and
                calls(HOME_INK, NOTEBOOK + 'get') == ['i64 40', 'i64 56'] and
                calls(HOME_INK, ink) == [''],
                'Home ink bypassed queried geometry or the existing free raw buffer')
        px = re.findall(r'(%[-\w.]+) = call i64 @' +
                        re.escape(rows['Lemma.Ink.Geometry.pixel']['symbol']) + r'\([^\n]*\)', body(HOME_INK))
        require(len(px) == 1, 'Home ink lacks its actual calibrated screen coordinate')
        guard = re.findall(r'(%[-\w.]+) = icmp ule i64 160, ' + re.escape(px[0]) + r'$', body(HOME_INK), re.M)
        require(len(guard) == 1, 'Home ink writing/header boundary differs')
        validate_boolean_gate(body(HOME_INK), guard[0], rows[ink]['symbol'])
        incoming = {source for source in rows if calls(source, HOME_INK)}
        require(incoming == {NOTEBOOK + 'queueBookTap'}, 'Home ink acquired another caller')
    return {'unchanged_pre_functions': len(shared), 'added_functions': len(added(unit)),
            'changed_input_owners': sorted(changed(unit)), 'capacity': 8,
            'BSS_extent': [0x20d00, 0x20f20],
            'scope': 'Actual LLVM/caller guards; connected raw-input execution remains separate'}
