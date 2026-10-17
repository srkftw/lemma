"""Closed artifact admission for supervised Product10 course images.

Only genuine exported catalogs and LLVM are audited here. The target owns
health, confirmation and watchdog commands. Historical authorities remain exact.
"""
import hashlib
import json
import re
from pathlib import Path

from core0_common import Core0Error
from paper_next import canonical
from product_reader_deployment import (
    WATCHDOG_CONFIGURATION, WATCHDOG_SOFTWARE_DEPLOYMENT,
    WATCHDOG_BOOT_ROOT, WATCHDOG_DISPATCH_ROOT, BOOT_ROOT, DISPATCH_ROOT,
)

VERSION = 'lemma-product-trial-watchdog-target/1'
AUTHORITY = Path(__file__).resolve().parents[1] / 'tooling/trial-watchdog-target-authority.json'
PREDECESSORS = (
    'product-reader-target-authority.json', 'kernel-pool-read-target-authority.json',
    'authored-hint-publication-target-authority-v2.json',
)
PREFIX = 'Lemma.Platform.LemmaSim.TrialWatchdogKernel.'
ADDED_FUNCTIONS = frozenset(
    PREFIX + name for name in ('completed', 'boot', 'dispatch', 'finish', 'disarmIfHealthy')
) | frozenset('Lemma.Boot.TrialWatchdog.' + name for name in (
    'contextPolicy', 'contextTimeout', 'policyMagic', 'timeoutClocks', 'invalidContext')
) | frozenset('Lemma.Drivers.PowerSafety.' + name for name in (
    'disarm', 'result', 'command', 'write')
) | {'Lemma.Platform.Silicon.BindingSafety.power_watchdog_command_offset'}


def validate_shared_pre(actual, wanted):
    require(set(wanted['added_functions']) == ADDED_FUNCTIONS and
            ADDED_FUNCTIONS <= actual['functions'].keys(),
            'Trial watchdog added declaration inventory differs')
    shared = {source: row for source, row in actual['functions'].items() if source not in ADDED_FUNCTIONS}
    require(wanted['shared_pre_function_count'] == len(shared) == 1302 and
            wanted['shared_pre_functions_sha256'] == digest(shared),
            'Trial watchdog changed an existing kernel function body/signature/effect')



def require(value, message):
    if not value:
        raise Core0Error(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def authority(unit, key):
    require(unit.get('configuration') == WATCHDOG_CONFIGURATION and
            unit.get('software_deployment') == WATCHDOG_SOFTWARE_DEPLOYMENT,
            'Trial watchdog exact Product10 software tuple differs')
    wanted = json.loads(AUTHORITY.read_text())
    require(set(wanted) == {'schema', 'predecessors', 'roles'} and
            wanted['schema'] == VERSION and set(wanted['roles']) == {'kernel', 'notebook'} and
            wanted['predecessors'] == {name: hashlib.sha256(AUTHORITY.with_name(name).read_bytes()).hexdigest()
                                       for name in PREDECESSORS},
            'Trial watchdog complete predecessor/role authority differs')
    row = wanted['roles'][key]
    require(row.get('catalog_sha256') == digest(unit),
            'Trial watchdog complete typed/effect/root catalog differs: ' + key)
    return row


def semantics(ir, unit):
    """Independent ordered calls and checked completion gate, before LLVM O2."""
    from audit_kernel import _ir_definition_body, _local_call_arguments, validate_checked_call_gate
    rows = {canonical(row['source']): row for row in unit['functions']}

    def body(source):
        require(source in rows, 'Trial watchdog semantic owner missing: ' + source)
        return _ir_definition_body(ir, rows[source]['symbol'])

    def calls(owner, target):
        require(target in rows, 'Trial watchdog semantic callee missing: ' + target)
        return _local_call_arguments(body(owner), rows[target]['symbol'])

    require(calls(WATCHDOG_BOOT_ROOT, BOOT_ROOT) == [''] and
            calls(WATCHDOG_DISPATCH_ROOT, DISPATCH_ROOT) == ['i64 %arg0, i64 %arg1, i64 %arg2'] and
            calls(WATCHDOG_DISPATCH_ROOT, PREFIX + 'disarmIfHealthy') == [''],
            'Trial watchdog omits or duplicates maintained boot/dispatch/health gate')
    validate_checked_call_gate(body(WATCHDOG_DISPATCH_ROOT), rows[DISPATCH_ROOT]['symbol'],
                               rows[PREFIX + 'disarmIfHealthy']['symbol'])
    require(calls(PREFIX + 'finish', 'Lemma.Drivers.PowerSafety.disarm') == [''] and
            calls(PREFIX + 'finish', 'Lemma.Drivers.Power.read') == ['i64 120'] and
            calls('Lemma.Drivers.PowerSafety.disarm', 'Lemma.Drivers.PowerSafety.command') == ['i64 3'],
            'Trial watchdog lacks actual disarm command or armed-state verification')
    validate_checked_call_gate(body(PREFIX + 'finish'), rows['Lemma.Drivers.PowerSafety.disarm']['symbol'],
                               rows['Lemma.Drivers.Power.read']['symbol'])
    for target, owner in ((PREFIX + 'finish', PREFIX + 'disarmIfHealthy'),
                          (PREFIX + 'disarmIfHealthy', WATCHDOG_DISPATCH_ROOT),
                          ('Lemma.Drivers.PowerSafety.disarm', PREFIX + 'finish')):
        incoming = {source for source in rows if calls(source, target)}
        require(incoming == {owner}, 'Trial watchdog private completion acquired another caller')
    from audit_kernel import validate_boolean_gate
    health = body(PREFIX + 'disarmIfHealthy')
    read = re.escape(rows['Lemma.Kernel.Memory.Access.read64']['symbol'])
    results = re.findall(r'(%[-A-Za-z0-9_.$]+) = call \{ i64, i64 \} @' + read + r'\(i64 [^\n]+\)', health)
    require(len(results) == 5, 'Trial watchdog exact private read inventory differs')
    values = []
    for result in results:
        value = re.findall(r'(%[-A-Za-z0-9_.$]+) = extractvalue \{ i64, i64 \} ' + re.escape(result) + r', 1', health)
        require(len(value) == 1, 'Trial watchdog read result is not authoritative')
        values.append(value[0])
    def scalar(source):
        value = re.findall(r'(%[-A-Za-z0-9_.$]+) = call i64 @' + re.escape(rows[source]['symbol']) + r'\(\)', health)
        require(len(value) == 1, 'Trial watchdog constant call differs')
        return value[0]
    expected = [(values[0], '1', False),
                (values[1], scalar('Lemma.Boot.TrialWatchdog.policyMagic'), True),
                (values[2], scalar('Lemma.Boot.TrialWatchdog.timeoutClocks'), True),
                (values[3], '3', True), (values[4], '0', True)]
    for value, rhs, success in expected:
        cmp = re.findall(r'(%[-A-Za-z0-9_.$]+) = icmp eq i64 ' + re.escape(value) + r', ' + re.escape(rhs) + r'$', health, re.M)
        require(len(cmp) == 1, 'Trial watchdog marker/timeout/phase/status comparison differs')
        validate_boolean_gate(health, cmp[0], rows[PREFIX + 'finish']['symbol'], success_when_true=success)
    return {'independent_watchdog': True, 'confirmation_barrier_authority': 'BootHealthExecuted phase3/status0',
            'actual_disarm_command': 3, 'actual_armed_read_offset': 120,
            'scope': 'Compiled authority only; actual ROM/health/reset execution is separately required'}
