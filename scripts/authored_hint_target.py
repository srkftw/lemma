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
VERSION2 = 'lemma-authored-hint-publication-artifact/2'
AUTHORITY2 = AUTHORITY.with_name('authored-hint-publication-target-authority-v2.json')
PUBLICATION = 'Lemma.Applications.Notebook.renderPackageCourseScoped'
PREVIOUS_PUBLICATION = 'Lemma.Applications.Notebook.renderPackageCourse'
PUBLISHERS = tuple('Lemma.Applications.Notebook.' + name for name in (
    'publishPackageWorkspace', 'finishOpenPackageCourse', 'numericPumpCancelledRedraw'))
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


def scoped_publication(unit):
    return any(canonical(row['source']) == PUBLICATION for row in unit.get('functions', []))


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
    scoped = scoped_publication(unit)
    authority = json.loads((AUTHORITY2 if scoped else AUTHORITY).read_text())
    if (set(authority) != {'schema', 'configurations'} or authority['schema'] != (VERSION2 if scoped else VERSION) or
            set(authority['configurations']) != set(CONFIGURATIONS)):
        raise Core0Error('Authored hint complete configuration inventory differs')
    entry = authority['configurations'][configuration]
    fields = {'predecessor_authority', 'predecessor_authority_sha256',
              'role_key', 'previous_role_sha256', 'role'}
    if scoped:
        fields |= {'previous_hint_authority_sha256', 'previous_hint_role_sha256', 'number_pad_pool_alpha'}
        old = json.loads(AUTHORITY.read_text())
        if (old.get('schema') != VERSION or set(old.get('configurations', {})) != set(CONFIGURATIONS) or
                entry.get('previous_hint_authority_sha256') != hashlib.sha256(AUTHORITY.read_bytes()).hexdigest() or
                entry.get('previous_hint_role_sha256') != digest(old['configurations'][configuration]['role'])):
            raise Core0Error('Authored hint publication exact first artifact predecessor differs')
    if (set(entry) != fields or
            entry['predecessor_authority'] != Path(authority_path).name or
            entry['predecessor_authority_sha256'] != hashlib.sha256(Path(authority_path).read_bytes()).hexdigest() or
            entry['previous_role_sha256'] != digest(previous) or entry['role_key'] != role_key):
        raise Core0Error('Authored hint exact predecessor authority differs')
    successor = entry['role']
    if (not isinstance(successor, dict) or set(successor) != set(previous) or
            any(successor[k] != previous[k] for k in previous if k not in CHANGED_FIELDS)):
        raise Core0Error('Authored hint changed an unrelated historical contract field')
    from notebook_control_backlog_target import present as backlog_present, refined as backlog_refined
    backlog = backlog_present(unit)
    if not backlog and (('catalog_sha256' in previous and successor['catalog_sha256'] != digest(unit)) or (
            'catalog_sha256_by_configuration' in previous and
            (set(successor['catalog_sha256_by_configuration']) != set(previous['catalog_sha256_by_configuration']) or
             successor['catalog_sha256_by_configuration'].get(configuration) != digest(unit)))):
        raise Core0Error('Authored hint complete typed/effect/root catalog differs')
    for phase in ('pre', 'post'):
        if (type(previous.get(phase + '_function_count')) is not int or
                successor.get(phase + '_function_count') != previous[phase + '_function_count'] + 2 or
                not isinstance(successor.get(phase + '_sha256'), str) or
                re.fullmatch('[0-9a-f]{64}', successor[phase + '_sha256']) is None):
            raise Core0Error('Authored hint complete corpus pins/counts differ')
    if 'function_count' in previous and successor['function_count'] != previous['function_count'] + 2:
        raise Core0Error('Authored hint complete source function count differs')
    return backlog_refined(unit, successor, AUTHORITY2) if backlog else successor


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
        from notebook_control_backlog_target import semantics as backlog_semantics
        backlog_semantics(ir, unit)
        current = _ir_definition_body(ir, rows[PREFIX + 'current']['symbol'])
        if _local_call_arguments(current, rows['Lemma.Documents.Mathematics.field']['symbol']) != [
                'i64 %arg0, i64 208', 'i64 %arg0, i64 192',
                'i64 %arg0, i64 40', 'i64 %arg0, i64 48']:
            raise Core0Error('Authored hint must read event version208, count192, revision40 and goal48')
        render = _ir_definition_body(ir, rows['Lemma.Courses.ArithmeticAligned.render']['symbol'])
        if len(_local_call_arguments(render, rows[PREFIX + 'current']['symbol'])) != 1:
            raise Core0Error('Authored hint filter disconnected from actual renderer')
        if scoped_publication(unit):
            if PREVIOUS_PUBLICATION in rows or not all(source in rows for source in PUBLISHERS):
                raise Core0Error('Scoped course publication exact declaration/caller inventory differs')
            publication = _ir_definition_body(ir, rows[PUBLICATION]['symbol'])
            if (len(_local_call_arguments(publication, rows['Lemma.Courses.ArithmeticAligned.render']['symbol'])) != 1 or
                    _local_call_arguments(publication, rows['Lemma.Courses.Arithmetic.renderSparse']['symbol'])):
                raise Core0Error('Course publication bypassed the revision-bound aligned renderer')
            for source in PUBLISHERS:
                body = _ir_definition_body(ir, rows[source]['symbol'])
                if len(_local_call_arguments(body, rows[PUBLICATION]['symbol'])) != 1:
                    raise Core0Error('Actual course publisher disconnected from scoped renderer: ' + source)


def number_pad_machine(normalized, unit, assembly, symbol):
    """Rebind only two source-bound local constant names to the old machine pin.

    LLVM numbers these private labels by the declaration's ordinal. The v2
    complete catalog fixes the new owner; the authority fixes both old/new
    names. Literal data, every instruction and the old complete owner pin are
    still checked. Historical machine normalization is unchanged.
    """
    if not scoped_publication(unit):
        return normalized
    from product_reader_deployment import WATCHDOG_CONFIGURATION
    from notebook_control_backlog_target import present as backlog_present, entry as backlog_entry
    if backlog_present(unit):
        entry = backlog_entry(unit)['number_pad_pool_alpha']
    elif unit.get('configuration') == WATCHDOG_CONFIGURATION:
        from trial_watchdog_target import authority as watchdog_authority
        entry = watchdog_authority(unit, 'notebook')['number_pad_pool_alpha']
    else:
        authority = json.loads(AUTHORITY2.read_text())
        entry = authority['configurations'][unit['configuration']]['number_pad_pool_alpha']
    if (set(entry) != {'old_symbol', 'new_symbol'} or entry['new_symbol'] != symbol or
            any(re.fullmatch(r'lemma_user_notebook_core0_scalar_\d+', entry[k]) is None
                for k in ('old_symbol', 'new_symbol'))):
        raise Core0Error('Number pad local constant owner differs')
    old, new = (entry[k].rsplit('_', 1)[1] for k in ('old_symbol', 'new_symbol'))
    pools = tuple('.LCPI' + new + '_' + str(i) for i in range(2))
    words = (4123376619178973524, 4123362480213543244)
    if set(re.findall(r'(?m)^(\.LCPI' + new + r'_\d+):', assembly)) != set(pools):
        raise Core0Error('Number pad local constant inventory differs')
    result = [(operation, list(arguments)) for operation, arguments in normalized]
    for i, (label, value) in enumerate(zip(pools, words)):
        if re.findall(r'(?m)^' + re.escape(label) + r':\n\s*\.quad\s+(\d+)\b', assembly) != [str(value)]:
            raise Core0Error('Number pad authored header constant differs')
        operand = '%pcrel_hi(' + label + ')'
        sites = [(at, arg) for at, (_, args) in enumerate(result)
                 for arg, text in enumerate(args) if text == operand]
        if sites != [(20 if i == 0 else 25, 1)] or result[sites[0][0]][0] != 'auipc':
            raise Core0Error('Number pad local constant reference differs')
        at, arg = sites[0]
        result[at][1][arg] = '%pcrel_hi(.LCPI' + old + '_' + str(i) + ')'
    return result
