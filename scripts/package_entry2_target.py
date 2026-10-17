"""Exact ordinary artifact authority for Clocked13's EntryV2 composition.

Only source catalogs and LLVM are inspected here. Target execution, recovery,
USB transactions, mathematical authority and observed performance stay separate.
"""
from pathlib import Path
import hashlib
import json
from core0_common import Core0Error
from paper_next import canonical
from package_entry2_deployment import CONFIGURATIONS, SOFTWARE_DEPLOYMENT, BOOT_ROOTS, BOOT_SOURCE, STEP_SOURCE

VERSION = 'lemma-package-clocked-entry2-target/1'
AUTHORITY = Path(__file__).resolve().parents[1] / 'tooling/package-entry2-target-authority.json'
PREFIX = 'Lemma.Platform.LemmaSim.NotebookKernel.'
PREDECESSORS = ('package-companion-target-authority.json', 'companion-number-pad-target-authority.json')


def require(value, message):
    if not value: raise Core0Error(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def selected(unit):
    return unit.get('configuration') in CONFIGURATIONS


def contract(unit):
    if not selected(unit): return None
    require(unit.get('software_deployment') == SOFTWARE_DEPLOYMENT,
            'Package Entry2 exact hardware/software tuple differs')
    role = unit.get('role')
    if role in ('kernel', 'firmware'):
        key = role + ('-init' if unit['configuration'].endswith('-initialize') else '')
        profile = 'core0-kernel-v0.6' if role == 'kernel' else 'core0-firmware-v0.1'
    elif role == 'user' and unit.get('image_key') in SOFTWARE_DEPLOYMENT['user_profiles']:
        key = unit['image_key']; profile = SOFTWARE_DEPLOYMENT['user_profiles'][key]
    else:
        raise Core0Error('Package Entry2 role is outside the closed four-role deployment')
    require(unit.get('contract_version') == profile, 'Package Entry2 actual privilege profile differs')
    authority = json.loads(AUTHORITY.read_text())
    require(authority.get('schema') == VERSION and set(authority.get('roles', {})) == {
        'kernel', 'kernel-init', 'firmware', 'firmware-init', 'store', 'notebook', 'arithmetic', 'course'},
        'Package Entry2 complete role authority differs')
    require(authority.get('predecessors') == {
        name: hashlib.sha256(AUTHORITY.with_name(name).read_bytes()).hexdigest() for name in PREDECESSORS},
        'Package Entry2 immutable predecessor authorities differ')
    from kernel_pool_read_target import refined_role
    wanted = refined_role(unit, authority['roles'][key], AUTHORITY, key)
    from authored_hint_target import refined as hint_refined
    if key == 'notebook': wanted = hint_refined(unit, wanted, AUTHORITY, key)
    catalogs = wanted.get('catalog_sha256_by_configuration')
    expected_configs = set(CONFIGURATIONS) if role == 'user' else {unit['configuration']}
    require(isinstance(catalogs, dict) and set(catalogs) == expected_configs and
            catalogs.get(unit['configuration']) == digest(unit),
            'Package Entry2 complete original typed/effect/root catalog differs: ' + key)
    return key, wanted


def notebook_contract(unit):
    require(selected(unit) and unit.get('role') == 'user' and unit.get('image_key') == 'notebook',
            'Package Entry2 notebook authority escaped its role')
    key, wanted = contract(unit)
    require(key == 'notebook' and wanted.get('package_notebook_version') == 16,
            'Package Entry2 must retain the complete recovery16 notebook')
    return 'companion', wanted


def kernel_semantics(ir, unit):
    from audit_kernel import _ir_definition_body, _local_call_arguments
    rows = {canonical(row['source']): row for row in unit['functions']}
    def calls(owner, target):
        require(owner in rows and target in rows, 'Package Entry2 semantic declaration missing: ' + owner + '/' + target)
        return _local_call_arguments(_ir_definition_body(ir, rows[owner]['symbol']), rows[target]['symbol'])
    root = PREFIX + BOOT_ROOTS[unit['configuration']]; boot = PREFIX + BOOT_SOURCE; step = PREFIX + STEP_SOURCE
    require(calls(root, boot) == ['i64 ' + str(int(unit['configuration'].endswith('-initialize')))],
            'Package Entry2 explicit initialization operand differs')
    for target, args in (
        ('Lemma.Platform.LemmaSim.Descriptor.validateBindingClocked', ['i64 13']),
        (PREFIX + 'constructPackageRecovery', ['i64 %arg0']),
        ('Lemma.Platform.LemmaVM.ConsoleDevice.initialize14', ['']),
        ('Lemma.USB.Block.initializeRecovery', ['']),
        ('Lemma.Drivers.Paper.initializeExecuted', ['']),
        ('Lemma.Drivers.Pen.initialize', ['']),
    ):
        require(calls(boot, target) == args, 'Package Entry2 actual boot transaction differs: ' + target)
    for target, args in (
        (PREFIX + 'acceptPendingRecovery', ['i64 13']),
        ('Lemma.Platform.LemmaSim.DeviceService.deferredUSBRecovery', ['']),
        ('Lemma.Platform.LemmaSim.PowerControl.stepUSB', ['']),
        ('Lemma.Kernel.Scheduler.stepEntryV2', ['']),
    ):
        require(calls(step, target) == args, 'Package Entry2 actual controller/power/scheduler path differs: ' + target)
    require(unit.get('used_loops') == [{'stable_id': 'action.loop', 'callback': next(
        r['source'] for r in unit['functions'] if canonical(r['source']) == step)}],
        'Package Entry2 boot loop callback differs')
    require(not any(source.startswith(('Lemma.Boot.Product', 'Lemma.Platform.LemmaSim.BootHealth')) for source in rows),
            'Package Entry2 acquired Product/NV authority')
    return {'binding': 13, 'same_recovery_constructor': True, 'entry_borrow': 'same checked Scheduler Action',
            'initializer_explicit': unit['configuration'].endswith('-initialize')}


def validate_entry(ir, unit, *, optimized):
    require(selected(unit) and unit.get('role') == 'kernel', 'Package Entry2 entry authority escaped Kernel6')
    contract(unit)
    from task_entry_borrow import validate_component
    result = validate_component(ir, unit, optimized=optimized)
    if not optimized: result['boot'] = kernel_semantics(ir, unit)
    return {**result, 'selected_configuration': unit['configuration'],
            'scope': 'Complete selected artifact and original borrowed-entry gates; execution/performance separate'}
