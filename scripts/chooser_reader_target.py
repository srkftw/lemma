"""Exact canonical Reader20 artifacts; guest Lean owns the edition chooser."""
import hashlib
import json
from pathlib import Path
from core0_common import Core0Error
from paper_next import canonical
from chooser_reader_deployment import CONFIGURATIONS, NOTEBOOK_ROOT, SOFTWARE_DEPLOYMENT

VERSION = 'lemma-course-chooser-notebook-artifact/1'
AUTHORITY = Path(__file__).resolve().parents[1] / 'tooling/chooser-reader-target-authority.json'
PREDECESSOR = AUTHORITY.with_name('reader-notebook-target-authority.json')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require(value, message):
    if not value:
        raise Core0Error(message)


def candidate(unit):
    return any(canonical(row.get('source', '')) == NOTEBOOK_ROOT for row in unit.get('functions', []))


def contract(unit):
    if not candidate(unit):
        return None
    require(unit.get('configuration') in CONFIGURATIONS and
            (unit.get('role'), unit.get('image_key'), unit.get('image_id'), unit.get('contract_version')) ==
            ('user', 'notebook', 2, 'core0-user-v0.2') and unit.get('used_device_ops') == [] and
            unit.get('software_deployment') == SOFTWARE_DEPLOYMENT, 'Reader20 escaped its exact canonical User2 deployment')
    require([{k: r.get(k) for k in ('source', 'id', 'args')} for r in unit.get('roots', [])] ==
            [{'source': NOTEBOOK_ROOT, 'id': 1, 'args': ['u64']}], 'Reader20 exact root/ABI differs')
    require({r.get('stable_id') for r in unit.get('used_execution_ops', [])} == {
        'execution.virtual-read8', 'execution.virtual-read64', 'execution.virtual-write8',
        'execution.virtual-write64', 'execution.syscall'}, 'Reader20 acquired execution authority')
    loops = unit.get('used_loops', [])
    require(len(loops) == 1 and loops[0].get('stable_id') == 'action.loop' and
            canonical(loops[0].get('callback', '')) == 'Lemma.Applications.Notebook.chooserReaderStep',
            'Reader20 selected loop differs')
    wanted = json.loads(AUTHORITY.read_text())
    from authored_hint_target import refined as hint_refined
    wanted = hint_refined(unit, wanted, AUTHORITY)
    catalogs = wanted.get('catalog_sha256_by_configuration', {})
    require(wanted.get('schema') == VERSION and wanted.get('package_notebook_version') == 20 and
            wanted.get('predecessor_sha256') == hashlib.sha256(PREDECESSOR.read_bytes()).hexdigest() and
            set(catalogs) == set(CONFIGURATIONS) and catalogs[unit['configuration']] == digest(unit),
            'Reader20 complete genuine predecessor/catalog differs')
    return 'canonical', wanted


def validate(ir, unit, *, optimized):
    found = contract(unit)
    if found is None:
        return None
    _, wanted = found
    from package_companion_target import complete_corpus
    phase = 'post' if optimized else 'pre'
    actual = complete_corpus(ir, unit, optimized=optimized)
    require(len(actual['functions']) == wanted[phase + '_function_count'] and digest(actual) == wanted[phase + '_sha256'],
            'Reader20 complete bodies/globals/callers differ: ' + phase)
    semantics = None
    if not optimized:
        from reader_notebook_target import semantics as reader_semantics
        semantics = reader_semantics(ir, unit, step='chooserReaderStep', work='readerPackageWork')
        from audit_kernel import _ir_definition_body, _local_call_arguments
        rows = {canonical(r['source']): r for r in unit['functions']}
        prefix = 'Lemma.Applications.Notebook.'
        owner = _ir_definition_body(ir, rows[prefix + 'readerPackageWork']['symbol'])
        require(len(_local_call_arguments(owner, rows[prefix + 'readerPrepareSelection']['symbol'])) == 1,
                'Reader20 lost its actual empty-selection guard')
        guard = _ir_definition_body(ir, rows[prefix + 'readerPrepareSelection']['symbol'])
        require(len(_local_call_arguments(guard, rows['Lemma.Courses.BrowseHistory.location']['symbol'])) == 1,
                'Reader20 omitted full owner/history validation')
    return {'contract_version': 'lemma-installed-package-notebook/20', 'artifact_contract_version': VERSION,
            'software_scope': 'canonical', 'package_notebook_version': 20, 'phase': phase,
            'function_count': len(actual['functions']), 'complete_corpus_sha256': digest(actual),
            'semantics': semantics, 'scope': 'Complete genuine artifact; fresh browser/CPU workflow qualified separately'}
