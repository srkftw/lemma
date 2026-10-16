"""Exact artifact authority for recovery16's joined guest input/Save path.

This host audit never edits a document, reconciles a receipt or grants a result.
The ordinary Lean compiler produces every target body being checked here.
"""
import hashlib
import json
import re
from pathlib import Path

from core0_common import Core0Error
from package_companion_deployment import CONFIGURATIONS, SOFTWARE_DEPLOYMENT
from paper_next import canonical

ROOT = 'Lemma.Applications.Notebook.mainRecoverablePackageNumberPad'
VERSION = 'lemma-companion-number-entry-artifact/1'
AUTHORITY = Path(__file__).resolve().parents[1] / 'tooling/companion-number-pad-target-authority.json'
PREVIOUS = AUTHORITY.with_name('dirty-batch-notebook-target-authority.json')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def candidate(unit):
    rows = unit.get('functions', [])
    if (not isinstance(rows, list) or any(not isinstance(row, dict) or
            not isinstance(row.get('source'), str) for row in rows)):
        raise Core0Error('Number-entry recovery function map is malformed')
    return any(canonical(row['source']) == ROOT for row in rows)


def contract(unit):
    if not candidate(unit):
        return None
    from package_entry2_target import selected as entry2_selected, notebook_contract
    if entry2_selected(unit): return notebook_contract(unit)
    if (unit.get('configuration') not in CONFIGURATIONS or unit.get('role') != 'user' or
            unit.get('image_key') != 'notebook' or unit.get('image_id') != 2 or
            unit.get('contract_version') != 'core0-user-v0.2' or unit.get('used_device_ops') != [] or
            unit.get('software_deployment') != SOFTWARE_DEPLOYMENT):
        raise Core0Error('Number-entry recovery escaped its exact USB13/User2/four-role deployment')
    if [{k: row.get(k) for k in ('source', 'id', 'args')} for row in unit.get('roots', [])] != [
            {'source': ROOT, 'id': 1, 'args': ['u64']}]:
        raise Core0Error('Number-entry recovery root/ABI differs')
    if not AUTHORITY.is_file():
        raise Core0Error('Number-entry recovery complete genuine artifact authority missing')
    authority = json.loads(AUTHORITY.read_text())
    previous = json.loads(PREVIOUS.read_text())
    expected_predecessors = {
        'canonical15': digest(previous['number_entry_pad_repaint_v1']),
        'companion11': digest(previous['course_save_v1']['deployments']['companion']),
    }
    if (authority.get('schema') != VERSION or authority.get('package_notebook_version') != 16 or
            authority.get('predecessors') != expected_predecessors or
            set(authority.get('catalog_sha256_by_configuration', {})) != set(CONFIGURATIONS) or
            authority['catalog_sha256_by_configuration'][unit['configuration']] != digest(unit)):
        raise Core0Error('Number-entry recovery exact predecessors/catalog differ')
    if {row.get('stable_id') for row in unit.get('used_execution_ops', [])} != {
            'execution.virtual-read8', 'execution.virtual-read64', 'execution.virtual-write8',
            'execution.virtual-write64', 'execution.syscall'}:
        raise Core0Error('Number-entry recovery acquired undeclared execution authority')
    loops = unit.get('used_loops', [])
    if (len(loops) != 1 or loops[0].get('stable_id') != 'action.loop' or
            canonical(loops[0].get('callback', '')) != 'Lemma.Applications.Notebook.numericRecoverableStep'):
        raise Core0Error('Number-entry recovery actual guest loop differs')
    return 'companion', authority


def semantics(ir, unit):
    from audit_kernel import _ir_definition_body
    from package_companion_target import semantic_guards
    rows = {canonical(row['source']): row for row in unit['functions']}
    prefix = 'Lemma.Applications.Notebook.'

    def calls(owner, target, *, required=True):
        if target not in rows and not required:
            return []
        if owner not in rows or target not in rows:
            raise Core0Error('Number-entry recovery semantic owner absent: ' + owner + '/' + target)
        return re.findall(r'call \{ i64, i64 \} @' + re.escape(rows[target]['symbol']) + r'\(([^\n]*)\)',
                          _ir_definition_body(ir, rows[owner]['symbol']))

    # The inherited complete recovery decoder/receipt/publication paths remain
    # required in addition to the joined input and actual rendering callers.
    semantic_guards(ir, unit)
    edges = [
        ('numericRecoverableInputSample', 'numericInputSample'),
        ('numericRecoverableInputSample.retainedInput', 'numericMarkPadOverdraw'),
        ('numericRecoverableInputSample.retainedInput', 'packageRetainedInputSample'),
        ('numericRecoverableStep', 'packageRecoverablePumpSave'),
        ('numericRecoverableStep', 'numericPumpPad'),
        ('numericRecoverableStep', 'numericPumpCancelledRedraw'),
        ('numericRecoverableStep', 'pumpRefreshRestoredBatched'),
        ('drainNumericRecoverableInput.drainStep', 'numericRecoverableInputSample'),
        ('numericInputSample.acceptSample', 'numericPadPress'),
        ('numericPadPress', 'numericPublishAligned'),
        ('numericPublishAligned', 'savePackageWorkspace'),
        ('savePackageWorkspace', 'startSave'),
    ]
    for owner, target in edges:
        if len(calls(prefix + owner, prefix + target)) != 1:
            raise Core0Error('Number-entry recovery lost actual joined path: ' + owner + '/' + target)
    if calls(prefix + 'numericMarkPadOverdraw', prefix + 'packagePut') != ['i64 200, i64 1']:
        raise Core0Error('Retained offline ink lost conservative pad invalidation')
    for target in ('startSave', 'reportCommitState', 'numericPublishAligned', 'packageCheck'):
        if calls(prefix + 'numericMarkPadOverdraw', prefix + target, required=False):
            raise Core0Error('Pad invalidation acquired publication/checking authority')
    return {'original_recovery_and_numeric_paths_joined': True,
            'scope': 'Complete genuine bodies/callers plus explicit source/IR edges; guest execution remains separate'}


def validate(ir, unit, *, optimized):
    found = contract(unit)
    if found is None:
        return None
    _, wanted = found
    from package_companion_target import complete_corpus
    phase = 'post' if optimized else 'pre'
    actual = complete_corpus(ir, unit, optimized=optimized)
    if len(actual['functions']) != wanted[phase + '_function_count'] or digest(actual) != wanted[phase + '_sha256']:
        raise Core0Error('Number-entry recovery complete body/global/caller corpus differs: ' + phase)
    return {'contract_version': 'lemma-installed-package-notebook/16',
            'artifact_contract_version': VERSION, 'software_scope': 'companion',
            'package_notebook_version': 16, 'phase': phase,
            'function_count': len(actual['functions']), 'complete_corpus_sha256': digest(actual),
            'semantics': None if optimized else semantics(ir, unit),
            'scope': 'Genuine complete artifact; peer durability/controller/CPU qualification separate'}
