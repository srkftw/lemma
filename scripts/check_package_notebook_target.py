#!/usr/bin/env python3
"""Validate genuine selected package Notebook artifacts and decisive negatives.

No compilation, target process, document recovery or guest result is performed.
The actual compiler-produced unit/IR and original producer hashes are required.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from core0_common import Core0Error
import package_notebook_target as target


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise Core0Error(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--producer-dir', type=Path, required=True)
    parser.add_argument('--component-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'retained output refused')
    start = time.monotonic()
    report = {'status': 'FAIL', 'scope': 'genuine selected artifact/metadata/guard negatives; whole-image audit/CPU/durability NOT_RUN'}
    try:
        original = json.loads((args.producer_dir / 'result.json').read_text())
        require(original.get('status') == 'PASS_GENUINE_SELECTED_ROLE_LLVM', 'actual producer not successful')
        require(digest(args.producer_dir / 'result.json') == target.PRODUCER_AUTHORITY['producer_result_sha256'],
                'mixed original producer receipt')
        root = Path(__file__).resolve().parents[1]
        for name, value in original['source_inputs'].items():
            require(digest(root / name) == value, 'original producer source changed: ' + name)
        artifact = args.producer_dir / 'notebook/users/notebook'
        for name, value in target.PRODUCER_AUTHORITY['actual_artifacts'].items():
            require(digest(artifact / name) == value, 'original compiler artifact changed: ' + name)
        unit = json.loads((artifact / 'unit.json').read_text())
        irs = {False: (artifact / 'program.ll').read_text(), True: (artifact / 'program.opt.ll').read_text()}
        positives = [target.validate(irs[opt], unit, optimized=opt) for opt in (False, True)]
        require([p['owned_functions'] for p in positives] == [189, 189], 'unexpectedly empty owned closure')
        negatives = []

        def rejects(name, ir, changed, opt=False):
            try:
                target.validate(ir, changed, optimized=opt)
            except Core0Error as error:
                negatives.append({'name': name, 'reason': str(error)})
                return
            raise Core0Error('actual artifact mutation admitted: ' + name)

        for field, value in [('contract_version', 'core0-user-v0.1'), ('configuration', 'lemmasim-silicon-closure-bulk-notebook'),
                             ('image_key', 'arithmetic'), ('image_id', True), ('boot_role', 'course-installer'),
                             ('used_device_ops', [{'stable_id': 'device.host-policy'}]), ('used_execution_ops', [])]:
            changed = copy.deepcopy(unit); changed[field] = value
            rejects('metadata-' + field, irs[False], changed)
        for field, value in [('source', 'Lemma.Applications.Notebook.mainClosureBulk'), ('args', ['u64', 'u64']), ('id', 2)]:
            changed = copy.deepcopy(unit); changed['roots'][0][field] = value
            rejects('exact-root-' + field, irs[False], changed)
        changed = copy.deepcopy(unit); changed['software_deployment']['contract_version'] = 'lemma-clone-package-v1'
        rejects('wrong-software-contract', irs[False], changed)
        owner = 'Lemma.Applications.Notebook.packageReadEOF'
        rows = target._rows(unit); row = rows[owner]
        changed = copy.deepcopy(unit); changed['functions'] = [f for f in changed['functions'] if f['symbol'] != row['symbol']]
        rejects('missing-EOF-owner', irs[False], changed)
        changed = copy.deepcopy(unit); changed['functions'].append(copy.deepcopy(row))
        rejects('duplicate-EOF-owner', irs[False], changed)
        changed = copy.deepcopy(unit)
        next(f for f in changed['functions'] if f['symbol'] == row['symbol'])['effects'] = []
        rejects('removed-checked-EOF-effects', irs[False], changed)
        changed = copy.deepcopy(unit)
        a = next(f for f in changed['functions'] if f['symbol'] == row['symbol'])
        b = next(f for f in changed['functions'] if target.canonical(f['source']) == 'Lemma.Applications.Notebook.cancelPackageRead')
        a['symbol'], b['symbol'] = b['symbol'], a['symbol']
        rejects('swapped-read-cancel-owner', irs[False], changed)
        # These exact source-owned constants/guards identify independent properties;
        # whole body pins catch every resulting instruction or operand change.
        mutations = [('private-context-address', 'Lemma.Applications.Notebook.packageContext', r'\bi64 3391488\b', 'i64 3395584'),
                     ('partial-allocation-bound', 'Lemma.Applications.Notebook.pumpPackageWork', r'\bi64 (%[^ ,\n]+), 12\b', r'i64 \1, 11'),
                     ('monotonic-read-floor', 'Lemma.Applications.Notebook.packageReadFloor', r'\bicmp ult i64\b', 'icmp ule i64'),
                     ('observational-no-Saved-read', 'Lemma.Applications.Notebook.packageReadComplete', r'\bi64 32, i64 2\b', 'i64 32, i64 1'),
                     ('bounded-request-reservation', 'Lemma.Applications.Notebook.beginPackageRead', r'\bi64 (%[^ ,\n]+), 257\b', r'i64 \1, 256')]
        for name, source, pattern, replacement in mutations:
            symbol = rows[source]['symbol']; body = target._bodies(irs[False])[symbol]
            mutated, count = re.subn(pattern, replacement, body, count=1)
            require(count == 1 and mutated != body, 'negative did not reach actual named guard: ' + name)
            rejects(name, irs[False].replace(body, mutated, 1), unit)
        eof = target._bodies(irs[False])[rows[owner]['symbol']]
        response = rows['Lemma.Services.Store.Client.responseField']['symbol']
        call = re.search(r'(%[-\w.]+) = call \{ i64, i64 \} @' + re.escape(response) +
                         r'\(i64 %[-\w.]+, i64 56\)', eof)
        require(call is not None, 'actual EOF response-count call missing')
        value = re.search(r'(%[-\w.]+) = extractvalue \{ i64, i64 \} ' + re.escape(call[1]) + r', 1', eof)
        require(value is not None, 'actual EOF response-count extraction missing')
        count_guard = r'icmp eq i64 ' + re.escape(value[1]) + r', 0\b'
        mutated, hits = re.subn(count_guard, 'icmp eq i64 ' + value[1] + ', 1', eof)
        require(hits == 1, 'negative did not identify exactly the actual EOF count-zero guard')
        rejects('EOF-actual-reply-count-zero', irs[False].replace(eof, mutated, 1), unit)
        # Same-body extra incoming caller must fail independently of body pins.
        symbol = rows[owner]['symbol']
        extra = 'define { i64, i64 } @lemma_extra_package_caller() {\nentry:\n  %v = call { i64, i64 } @' + symbol + '(i64 5)\n  ret { i64, i64 } %v\n}\n'
        changed = copy.deepcopy(unit); changed['functions'].append({'source': 'Lemma.Applications.Notebook.extraPackageCaller',
            'symbol': 'lemma_extra_package_caller', 'args': [], 'effects': ['checked-access', 'virtual-read', 'virtual-write', 'syscall']})
        rejects('additional-private-incoming-caller', irs[False] + extra, changed)
        # Real component metadata is not a selected production unit. No relabeling
        # or fabricated prospective unit creates the positive artifact authority.
        component = json.loads((args.component_dir / 'component/unit.json').read_text())
        rejects('original-component-is-not-production', (args.component_dir / 'component/program.ll').read_text(), component)
        # Actual Kernel producer contains no unique Notebook implementation.
        kernel = json.loads((args.producer_dir / 'kernel/unit.json').read_text())
        require(target.contract(kernel) is None, 'non-Notebook acquired package authority')
        installer_file = root / 'build/kernel/task006-course-await-workspace-a2/target/build/kernel/notebook/users/course/unit.json'
        require(installer_file.is_file(), 'actual retained InstallerAwait unit required for shared-library absence')
        installer = json.loads(installer_file.read_text())
        require(any(target.canonical(row['source']).startswith('Lemma.Courses.PackageTarget.') for row in installer['functions']) and
                target.contract(installer) is None, 'shared actual Installer package library received Notebook authority')
        escaped = copy.deepcopy(installer); escaped['functions'].append(copy.deepcopy(rows[owner]))
        rejects('Notebook-private-family-on-actual-Installer', irs[False], escaped)
        report.update(status='PASS_GENUINE_PACKAGE_NOTEBOOK_ARTIFACT_GUARDS', owned_functions=189,
                      positives=['actual-selected-pre', 'actual-selected-post', 'actual-kernel-absence'],
                      negatives=negatives, private_layout=target.PRIVATE_LAYOUT,
                      original_producer=target.PRODUCER_AUTHORITY,
                      helper_sha256=digest(root / 'scripts/package_notebook_target.py'))
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        report['seconds'] = time.monotonic() - start
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(report['status'], len(report['negatives']), report['seconds'])


if __name__ == '__main__':
    main()
