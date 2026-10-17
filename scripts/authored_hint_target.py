"""Additive artifact admission for revision-bound authored hints.

Selects exact genuine Notebook User2 exports. Historical authorities remain
immutable, and their root/effect/semantic/corpus checks still run in callers.
This host module never selects a hint or interprets a document for a guest.
"""
import hashlib
import json
import re
from pathlib import Path

from core0_common import Core0Error
from paper_next import canonical

VERSION = 'lemma-authored-hint-artifact/1'
AUTHORITY = Path(__file__).resolve().parents[1] / 'tooling/authored-hint-target-authority.json'
PREFIX = 'Lemma.Courses.HintVisibility.'
HELPERS = frozenset(PREFIX + name for name in ('current', 'eventStep'))
CONFIGURATIONS = {
    **{f'lemmasim-silicon-{stem}-bulk-{suffix}': (name, key)
       for stem, name, key in (
           ('package-closure-entry2', 'dirty-batch-notebook', 'number_entry_browse_history_v1'),
           ('usb-clocked-package-retry', 'companion-number-pad', ''),
           ('usb-clocked-package-entry2', 'package-entry2', 'notebook'),
           ('package-reader', 'reader-notebook', ''),
           ('package-chooser', 'chooser-reader', ''),
           ('usb-clocked-reader-entry2', 'companion-reader', 'notebook'))
       for suffix in ('notebook', 'initialize')},
    'lemmasim-silicon-product-course-reader-bulk-notebook': ('product-reader', 'notebook'),
}
CHANGED_FIELDS = frozenset(('catalog_sha256', 'catalog_sha256_by_configuration',
                          'pre_function_count', 'post_function_count', 'function_count',
                          'pre_sha256', 'post_sha256'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def present(unit):
    return HELPERS & {canonical(row['source']) for row in unit.get('functions', [])}


def refined(unit, previous, authority_path, role_key=''):
    found = present(unit)
    if not found:
        return previous
    configuration = unit.get('configuration')
    identity = CONFIGURATIONS.get(configuration)
    if (found != HELPERS or identity is None or identity[1] != role_key or
            Path(authority_path).name != identity[0] + '-target-authority.json' or
            (unit.get('role'), unit.get('image_key'), unit.get('image_id'), unit.get('contract_version')) !=
            ('user', 'notebook', 2, 'core0-user-v0.2')):
        raise Core0Error('Authored hint refinement escaped its exact Notebook User2 deployment')
    authority = json.loads(AUTHORITY.read_text())
    if (set(authority) != {'schema', 'configurations'} or authority['schema'] != VERSION or
            set(authority['configurations']) != set(CONFIGURATIONS)):
        raise Core0Error('Authored hint complete configuration inventory differs')
    entry = authority['configurations'][configuration]
    if (set(entry) != {'predecessor_authority', 'predecessor_authority_sha256',
                       'role_key', 'previous_role_sha256', 'role'} or
            entry['predecessor_authority'] != Path(authority_path).name or
            entry['predecessor_authority_sha256'] != hashlib.sha256(Path(authority_path).read_bytes()).hexdigest() or
            entry['previous_role_sha256'] != digest(previous) or entry['role_key'] != role_key):
        raise Core0Error('Authored hint exact predecessor authority differs')
    successor = entry['role']
    if (not isinstance(successor, dict) or set(successor) != set(previous) or
            any(successor[k] != previous[k] for k in previous if k not in CHANGED_FIELDS)):
        raise Core0Error('Authored hint changed an unrelated historical contract field')
    if ('catalog_sha256' in previous and successor['catalog_sha256'] != digest(unit)) or (
            'catalog_sha256_by_configuration' in previous and
            (set(successor['catalog_sha256_by_configuration']) != set(previous['catalog_sha256_by_configuration']) or
             successor['catalog_sha256_by_configuration'].get(configuration) != digest(unit))):
        raise Core0Error('Authored hint complete typed/effect/root catalog differs')
    for phase in ('pre', 'post'):
        if (type(previous.get(phase + '_function_count')) is not int or
                successor.get(phase + '_function_count') != previous[phase + '_function_count'] + 2 or
                not isinstance(successor.get(phase + '_sha256'), str) or
                re.fullmatch('[0-9a-f]{64}', successor[phase + '_sha256']) is None):
            raise Core0Error('Authored hint complete corpus pins/counts differ')
    if 'function_count' in previous and successor['function_count'] != previous['function_count'] + 2:
        raise Core0Error('Authored hint complete source function count differs')
    return successor


def semantics(ir, unit, *, optimized):
    """Keep read-only ownership and the real renderer call load-bearing."""
    if not present(unit):
        return
    from audit_kernel import _ir_definition_body, _local_call_arguments
    rows = {canonical(row['source']): row for row in unit['functions']}
    if present(unit) != HELPERS:
        raise Core0Error('Authored hint helper inventory differs')
    for source, args in ((PREFIX + 'current', ['u64']),
                         (PREFIX + 'eventStep', ['u32', 'u32'] + ['u64'] * 5)):
        if rows[source]['args'] != args or rows[source]['effects'] != ['checked-access', 'virtual-read']:
            raise Core0Error('Authored hint helper acquired write/foreign authority')
    if not optimized:
        current = _ir_definition_body(ir, rows[PREFIX + 'current']['symbol'])
        if _local_call_arguments(current, rows['Lemma.Documents.Mathematics.field']['symbol']) != [
                'i64 %arg0, i64 208', 'i64 %arg0, i64 192',
                'i64 %arg0, i64 40', 'i64 %arg0, i64 48']:
            raise Core0Error('Authored hint must read event version208, count192, revision40 and goal48')
        render = _ir_definition_body(ir, rows['Lemma.Courses.ArithmeticAligned.render']['symbol'])
        if len(_local_call_arguments(render, rows[PREFIX + 'current']['symbol'])) != 1:
            raise Core0Error('Authored hint filter disconnected from actual renderer')
