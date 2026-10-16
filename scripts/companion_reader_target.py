"""Exact artifact authority for Reader19 and its Recovery5 composition.

This is a host audit of genuine exports. It implements no guest recovery,
package parsing, mathematical policy, ink construction or durability receipt.
"""
import hashlib
import json
from pathlib import Path
from core0_common import Core0Error
from paper_next import canonical
from companion_reader_deployment import CONFIGURATIONS, SOFTWARE_DEPLOYMENT, BOOT_ROOTS, NOTEBOOK_ROOT

VERSION = 'lemma-companion-reader-target/1'
AUTHORITY = Path(__file__).resolve().parents[1] / 'tooling/companion-reader-target-authority.json'
PREDECESSORS = ('package-entry2-target-authority.json', 'reader-notebook-target-authority.json')
PREFIX = 'Lemma.Applications.Notebook.'


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
    wanted = authority['roles'][key]
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
