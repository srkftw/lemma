"""Exact artifact authority for Reader19 and its Recovery5 composition.

This is a host audit of genuine exports. It implements no guest recovery,
package parsing, mathematical policy, ink construction or durability receipt.
"""
import hashlib
import json
import re
from pathlib import Path
from core0_common import Core0Error
from paper_next import canonical
from companion_reader_deployment import CONFIGURATIONS, SOFTWARE_DEPLOYMENT, BOOT_ROOTS, NOTEBOOK_ROOT

VERSION = 'lemma-companion-reader-target/1'
AUTHORITY = Path(__file__).resolve().parents[1] / 'tooling/companion-reader-target-authority.json'
PREDECESSORS = ('package-entry2-target-authority.json', 'reader-notebook-target-authority.json')
PREFIX = 'Lemma.Applications.Notebook.'
RECOVERY_PUMP = PREFIX + 'readerRecoverableTransactionPump'
RECOVERY_CASES = [0, 1, 2, 3, 8, 9, 10, 11]
RECOVERY_MACHINE_SHA256 = '0c787246e10ddeecd2f160982d1de44aec1271d2a3b18f6102d6550dee2faad9'


def recovery_jump_spec(ir, unit, source, symbol):
    if source != RECOVERY_PUMP:
        return None
    require(selected(unit) and unit.get('role') == 'user' and unit.get('image_key') == 'notebook',
            'Reader19 recovery table escaped its selected User2 deployment')
    validate_notebook(ir, unit, optimized=True)
    from audit_kernel import _ir_definition_body
    rows = {canonical(row['source']): row for row in unit['functions']}
    row = rows[source]
    effects = ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']
    require(row['symbol'] == symbol and row['args'] == [] and row['effects'] == effects,
            'Reader19 recovery table source signature/effects differ')
    body = _ir_definition_body(ir, symbol)
    switches = re.findall(r'switch i64 [^\n]+\[([^]]+)\]', body, re.S)
    require(len(switches) == 1 and sorted(int(v) for v in re.findall(r'i64 (\d+), label', switches[0])) == RECOVERY_CASES,
            'Reader19 recovery table source phase domain differs')
    # Independently bind every admitted source phase to its actual Action.
    from package_notebook_target import _readonly_cfg
    blocks = _readonly_cfg(body)[0]
    targets = {int(v): target for v, target in re.findall(r'i64 (\d+), label %([^\s]+)', switches[0])}
    for phase, callee in ((8, 'readerRecoverablePollControl'), (9, 'readerRecoverablePollControl'),
                          (10, 'readerRecoverablePollRead'), (11, 'readerRecoverablePollRead')):
        require(sum('@' + rows[PREFIX + callee]['symbol'] + '()' in line for line in blocks[targets[phase]]) == 1,
                'Reader19 recovery source phase invokes another poll')
    transaction = rows[RECOVERY_PUMP + '.transaction']['symbol']
    for phase in (1, 2, 3):
        require(sum('@' + transaction + '(i64 ' + str(phase) + ')' in line for line in blocks[targets[phase]]) == 1,
                'Reader19 recovery source phase changes its transaction argument')
    return ('user', 12, [], effects, RECOVERY_CASES)


def recovery_jump_relation(ir, unit, assembly, symbol, table, targets, code, labels):
    recovery_jump_spec(ir, unit, RECOVERY_PUMP, symbol)
    from audit_kernel import _jump_assembly_function
    from package_notebook_target import _normalized_jump_code
    require((code, labels) == _jump_assembly_function(assembly, symbol),
            'Reader19 recovery table supplied foreign machine instructions')
    declarations = re.findall(r'(?m)^' + re.escape(table) + r':\n((?:\s*\.quad\s+\.LBB\d+_\d+\s*\n)+)', assembly)
    require(len(declarations) == 1 and re.findall(r'\.quad\s+(\S+)', declarations[0]) == targets and
            len(targets) == 12 and all(target in labels for target in targets),
            'Reader19 recovery actual table declaration/cell extent differs')
    names = {row['symbol']: canonical(row['source']) for row in unit['functions']}
    actual = _normalized_jump_code(code, labels, table, names)
    require(hashlib.sha256(repr(actual).encode()).hexdigest() == RECOVERY_MACHINE_SHA256,
            'Reader19 recovery complete machine owner/guard/calls differ')
    require(actual[10:19] == [('li', ['a0', '11']), ('bltu', ['a0', 's1', '@23']),
            ('slli', ['a0', 's1', '3']), ('auipc', ['a1', '%TABLE']),
            ('addi', ['a1', 'a1', '%LOW13']), ('add', ['a0', 'a0', 'a1']),
            ('ld', ['a0', '0(a0)']), ('mv', ['s0', 's1']), ('jr', ['a0'])],
            'Reader19 recovery unsigned bound/load/return-state relation differs')
    require([labels[target] for target in targets] == [33, 26, 28, 30, 23, 23, 23, 23, 19, 19, 21, 21],
            'Reader19 recovery actual phase/call/hole table mapping differs')
    require(actual[19:33] == [('call', ['@' + PREFIX + 'readerRecoverablePollControl']), ('j', ['@32']),
            ('call', ['@' + PREFIX + 'readerRecoverablePollRead']), ('j', ['@32']),
            ('li', ['a0', '234']), ('call', ['@' + PREFIX + 'saveFailure']), ('j', ['@32']),
            ('li', ['a0', '1']), ('j', ['@31']), ('li', ['a0', '2']), ('j', ['@31']),
            ('li', ['a0', '3']), ('call', ['@' + RECOVERY_PUMP + '.transaction']), ('mv', ['s0', 'a0'])],
            'Reader19 recovery machine poll/transaction/error semantics differ')
    return {'schema': 'lemma-reader19-recovery-backend-cells/1', 'source': RECOVERY_PUMP,
            'all_phase_targets': [labels[target] for target in targets], 'error_holes': [4, 5, 6, 7],
            'other_state_error': 234, 'machine_sha256': RECOVERY_MACHINE_SHA256}


def require(value, message):
    if not value:
        raise Core0Error(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def selected(unit):
    return unit.get('configuration') in CONFIGURATIONS


def candidate(unit):
    rows = unit.get('functions', [])
    require(isinstance(rows, list) and all(isinstance(row, dict) and
            isinstance(row.get('source'), str) for row in rows), 'Reader19 function map malformed')
    return any(canonical(row['source']) == NOTEBOOK_ROOT for row in rows)


def contract(unit):
    if not selected(unit):
        return None
    require(unit.get('software_deployment') == SOFTWARE_DEPLOYMENT,
            'Reader19 exact hardware/software tuple differs')
    role = unit.get('role')
    if role in ('kernel', 'firmware'):
        key = role + ('-init' if unit['configuration'].endswith('-initialize') else '')
        profile = 'core0-kernel-v0.6' if role == 'kernel' else 'core0-firmware-v0.1'
    elif role == 'user' and unit.get('image_key') in SOFTWARE_DEPLOYMENT['user_profiles']:
        key = unit['image_key']; profile = SOFTWARE_DEPLOYMENT['user_profiles'][key]
    else:
        raise Core0Error('Reader19 role escaped the closed four-role deployment')
    require(unit.get('contract_version') == profile, 'Reader19 privilege profile differs')
    authority = json.loads(AUTHORITY.read_text())
    require(authority.get('schema') == VERSION and set(authority.get('roles', {})) == {
        'kernel', 'kernel-init', 'firmware', 'firmware-init', 'store', 'notebook', 'arithmetic', 'course'},
        'Reader19 complete role authority differs')
    require(authority.get('predecessors') == {name: hashlib.sha256(AUTHORITY.with_name(name).read_bytes()).hexdigest()
            for name in PREDECESSORS}, 'Reader19 immutable predecessors differ')
    from kernel_pool_read_target import refined_role
    wanted = refined_role(unit, authority['roles'][key], AUTHORITY, key)
    from authored_hint_target import refined as hint_refined
    if key == 'notebook': wanted = hint_refined(unit, wanted, AUTHORITY, key)
    catalogs = wanted.get('catalog_sha256_by_configuration')
    require(isinstance(catalogs, dict) and set(catalogs) == (set(CONFIGURATIONS) if role == 'user' else {unit['configuration']})
            and catalogs.get(unit['configuration']) == digest(unit),
            'Reader19 complete genuine typed/effect/root catalog differs: ' + key)
    return key, wanted


def notebook_contract(unit):
    require(candidate(unit) and selected(unit) and (unit.get('role'), unit.get('image_key'), unit.get('image_id')) ==
            ('user', 'notebook', 2), 'Reader19 escaped its exact Notebook User2 role')
    key, wanted = contract(unit)
    require(key == 'notebook' and wanted.get('package_notebook_version') == 19,
            'Reader19 full notebook version differs')
    require([{k: row.get(k) for k in ('source', 'id', 'args')} for row in unit.get('roots', [])] ==
            [{'source': NOTEBOOK_ROOT, 'id': 1, 'args': ['u64']}], 'Reader19 exact root/ABI differs')
    require(unit.get('used_device_ops') == [] and {row.get('stable_id') for row in unit.get('used_execution_ops', [])} == {
        'execution.virtual-read8', 'execution.virtual-read64', 'execution.virtual-write8',
        'execution.virtual-write64', 'execution.syscall'}, 'Reader19 acquired execution authority')
    loops = unit.get('used_loops', [])
    require(len(loops) == 1 and loops[0].get('stable_id') == 'action.loop' and
            canonical(loops[0].get('callback', '')) == PREFIX + 'readerRecoverableStep',
            'Reader19 actual selected guest loop differs')
    return 'companion', wanted


def notebook_semantics(ir, unit):
    from audit_kernel import _ir_definition_body, _local_call_arguments
    from package_companion_target import semantic_guards
    semantic_guards(ir, unit)
    rows = {canonical(row['source']): row for row in unit['functions']}
    def calls(owner, target):
        require(owner in rows and target in rows, 'Reader19 semantic declaration missing: ' + owner + '/' + target)
        return _local_call_arguments(_ir_definition_body(ir, rows[owner]['symbol']), rows[target]['symbol'])
    edges = [
        ('readerRecoverableStep', 'readerRecoverablePumpSave'),
        ('readerRecoverableStep', 'readerPackageWork'),
        ('readerPackageWork', 'readerPrepareSelection'),
        ('readerPackageWork', 'pumpBookmarkOpen'),
        ('readerRecoverableStep', 'numericPumpPad'),
        ('readerRecoverableStep', 'pumpRefreshRestoredBatched'),
        ('readerRecoverableStep', 'readerRecoverableInputSample'),
        ('readerRecoverableInputSample', 'bookmarkInputSample'),
        ('readerRecoverableInputSample.retainedInput', 'readerRetainedInputSample'),
        ('readerRetainedInputSample.acceptSample', 'readerRecoverableToolbar'),
        ('readerRecoverableToolbar', 'readerRecoverableBegin'),
        ('readerRecoverableToolbar', 'packageRecoverableBegin'),
        ('readerRecoverablePumpSave', 'readerRecoverableTransactionPump'),
        ('readerRecoverablePumpSave', 'adoptBookmark'),
        ('readerRecoverablePollRead', 'packageRecoverableCompareStep'),
        ('readerRecoverablePollRead', 'packageRecoverableIssueEndRead'),
        ('readerRecoverablePollRead', 'readerRecoverableFinish'),
        ('readerRecoverableFinish', 'finishRecord'),
        ('bookmarkInputSample.acceptSample', 'bookmarkToolbar'),
        ('bookmarkToolbar', 'bookmarkRequestSave'),
                ('readerPackageWork', 'validateBookmarkPackage'),
        ('pumpBookmarkOpen', 'finishBookmarkLookup'),
        ('finishBookmarkLookup', 'adoptBookmark'),
    ]
    for owner, target in edges:
        require(len(calls(PREFIX + owner, PREFIX + target)) == 1,
                'Reader19 lost actual joined path: ' + owner + '/' + target)
    for owner in ('readerRecoverableRetain', 'readerRecoverableBegin', 'readerRecoverableResubmit',
                  'readerRecoverableIssueRead', 'readerRecoverableFinish'):
        require(len(calls(PREFIX + owner, PREFIX + 'readerRecoverableValidate')) == 1,
                'Reader19 retained package validation omitted: ' + owner)
    require(len(calls(PREFIX + 'readerRecoverableValidate', 'Lemma.Courses.ReaderLocation.resolve')) == 1,
            'Reader19 held record is not resolved against the complete actual package')
    require(not calls(PREFIX + 'readerRecoverableFinish', PREFIX + 'startSave'),
            'Reader19 lost-ACK reconciliation duplicated the original PUT')
    for owner, target in [
            (PREFIX + 'bookmarkRequestSave', 'Lemma.Courses.ReaderLocation.capture'),
            (PREFIX + 'adoptBookmark', 'Lemma.Courses.ReaderLocation.validate'),
            (PREFIX + 'validateBookmarkPackage', 'Lemma.Courses.ReaderLocation.resolve'),
            ('Lemma.Courses.ReaderLocation.resolve', 'Lemma.Courses.PackageTarget.select')]:
        require(len(calls(owner, target)) == 1, 'Reader19 disconnected the complete reader/package codec')
    for owner in ('Lemma.Courses.ReaderLocation.validate', 'Lemma.Courses.ReaderLocation.resolve'):
        require(rows[owner]['effects'] == ['checked-access', 'virtual-read'],
                'Reader19 location resolution acquired write authority')
    for owner in (PREFIX + 'finishBookmarkLookup', PREFIX + 'validateBookmarkPackage',
                  'Lemma.Courses.ReaderLocation.capture', 'Lemma.Courses.ReaderLocation.validate',
                  'Lemma.Courses.ReaderLocation.resolve'):
        for target in ('startSave', 'reportCommitState', 'numericPublishAligned', 'packageCheck'):
            if PREFIX + target in rows:
                require(not calls(owner, PREFIX + target), 'Reader19 lookup acquired publication/checking authority')
    return {'reader_recovery_joined': True, 'retained_source': 'exact128/fullpackage/ownedpage',
            'publication': 'ordinary COMMIT or remount barrier/new epoch/exact READ/EOF',
            'scope': 'Artifact semantics only; guest/peer execution and durability qualified separately'}


def validate_notebook(ir, unit, *, optimized):
    _, wanted = notebook_contract(unit)
    from package_companion_target import complete_corpus
    phase = 'post' if optimized else 'pre'
    actual = complete_corpus(ir, unit, optimized=optimized)
    require(len(actual['functions']) == wanted[phase + '_function_count'] and digest(actual) == wanted[phase + '_sha256'],
            'Reader19 complete bodies/globals/callers differ: ' + phase)
    return {'contract_version': 'lemma-installed-package-notebook/19', 'artifact_contract_version': VERSION,
            'software_scope': 'companion', 'package_notebook_version': 19, 'phase': phase,
            'function_count': len(actual['functions']), 'complete_corpus_sha256': digest(actual),
            'semantics': None if optimized else notebook_semantics(ir, unit),
            'scope': 'Complete genuine artifact; connected execution remains separate'}


def validate_entry(ir, unit, *, optimized):
    require(selected(unit) and unit.get('role') == 'kernel', 'Reader19 Entry2 escaped Kernel6')
    contract(unit)
    from task_entry_borrow import validate_component
    result = validate_component(ir, unit, optimized=optimized)
    if not optimized:
        from audit_kernel import _ir_definition_body, _local_call_arguments
        rows = {canonical(row['source']): row for row in unit['functions']}
        prefix = 'Lemma.Platform.LemmaSim.NotebookKernel.'
        def calls(owner, target):
            require(owner in rows and target in rows, 'Reader19 actual kernel path absent')
            return _local_call_arguments(_ir_definition_body(ir, rows[owner]['symbol']), rows[target]['symbol'])
        require(calls(prefix + BOOT_ROOTS[unit['configuration']], prefix + 'bootPackageRecoveryEntry2') ==
                ['i64 ' + str(int(unit['configuration'].endswith('-initialize')))], 'Reader19 initializer operand differs')
        for target, args in [('acceptPendingRecovery', ['i64 13']),
                             ('Lemma.Platform.LemmaSim.DeviceService.deferredUSBRecovery', ['']),
                             ('Lemma.Platform.LemmaSim.PowerControl.stepUSB', ['']),
                             ('Lemma.Kernel.Scheduler.stepEntryV2', [''])]:
            name = prefix + target if '.' not in target else target
            require(calls(prefix + 'packageRecoveryEntry2Step', name) == args,
                    'Reader19 actual controller/power/scheduler differs: ' + name)
    return {**result, 'selected_configuration': unit['configuration'], 'scope': 'Original checked Kernel6 entry; execution separate'}
