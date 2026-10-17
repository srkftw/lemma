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


def readonly_checks(ir, unit):
    sites, tables, removed = target.readonly_lookup(ir, unit)
    require(len(sites) == 4 and len(tables) == 6 and len(removed) == 6,
            'actual Package table/load inventory differs')
    negatives = []

    def reject(name, changed, *, structural=False):
        try:
            if structural:
                target._readonly_lookup_verified(changed, unit)
            else:
                target.readonly_lookup(changed, unit)
        except Core0Error as error:
            negatives.append({'name': name, 'reason': str(error),
                              'independent_structural_check': structural})
            return
        raise Core0Error('actual readonly mutation admitted: ' + name)

    # Every real table cell is independently relevant: labels remain exact and
    # capture offsets must bind the intended source field rather than a neighbor.
    for ordinal, table in enumerate(tables):
        line = next(line for line in removed if line.startswith('@' + table['global'] + ' ='))
        values = table['values']
        for index, value in enumerate(values):
            changed_values = list(values); changed_values[index] = value ^ 1
            changed_line = '@' + table['global'] + ' = private unnamed_addr constant [' + str(len(values)) + \
                ' x i64] [' + ', '.join('i64 ' + str(word) for word in changed_values) + '], align 8'
            reject('table-' + str(ordinal) + '-cell-' + str(index), ir.replace(line, changed_line, 1))
        reject('table-' + str(ordinal) + '-missing', ir.replace(line, '', 1))
        reject('table-' + str(ordinal) + '-writable', ir.replace(line, line.replace('constant', 'global'), 1))
        reject('table-' + str(ordinal) + '-alignment', ir.replace(line, line.replace('align 8', 'align 4'), 1))
        reject('table-' + str(ordinal) + '-extra-use', ir + '\n@extra_alias_' + str(ordinal) +
               ' = private constant ptr @' + table['global'] + '\n')

    rows = target._rows(unit); bodies = target._bodies(ir)

    def body_mutation(name, source, pattern, replacement):
        body = bodies[rows[source]['symbol']]
        changed, count = re.subn(pattern, replacement, body, count=1)
        require(count == 1 and changed != body, 'readonly mutation did not reach actual guard: ' + name)
        reject(name, ir.replace(body, changed, 1), structural=True)

    control = target.CONTROL_SOURCE; capture = target.CAPTURE_SOURCE
    body_mutation('control-unsigned24', control, r'icmp ult i64 %arg1, 24\b', 'icmp ule i64 %arg1, 24')
    body_mutation('control-index-shift3', control, r'lshr i64 %arg1, 3\b', 'lshr i64 %arg1, 2')
    for i, table in enumerate(tables[:5]):
        block = table['guard']; body = bodies[rows[control]['symbol']]
        match = re.search(r'(?m)^' + re.escape(block) + r':[^\n]*\n\s*(br i1 %0, label %[^,]+, label %[^\n]+)', body)
        require(match is not None, 'real control bound branch absent')
        branch = match[1]; changed = re.sub(r'br i1 %0, label %([^,]+), label %(\S+)', r'br i1 %0, label %\2, label %\1', branch)
        reject('control-row-' + str(i) + '-inverted-bound', ir.replace(body, body.replace(branch, changed, 1), 1), structural=True)
    base = 'switch.table.' + rows[control]['symbol']
    body_mutation('control-joined-phi-source', control,
                  r'\[ @' + re.escape(base) + r', %if.then.3 \]', '[ @' + base + '.4, %if.then.3 ]')
    body_mutation('control-row-selection', control, r'i64 1, label %if.then.15\b', 'i64 9, label %if.then.15')
    body_mutation('control-shared-index-coordinate', control,
                  r'(ptr %switch\.table\.[^,]+, i64 0, i64 )%udiv11\b', r'\1%arg1')
    body_mutation('control-shared-pointer-escape', control,
                  r'(%switch\.load16 = load i64, ptr %switch\.gep15, align 8)',
                  r'\1\n  %extra.load = load i64, ptr %switch.gep15, align 8')
    body_mutation('control-direct-pointer-alignment', control,
                  r'load i64, ptr %switch\.gep18, align 8', 'load i64, ptr %switch.gep18, align 4')
    body_mutation('capture-unsigned10', capture, r'icmp ult i32 %arg0, 10\b', 'icmp ult i32 %arg0, 11')
    body_mutation('capture-index-conversion', capture, r'zext nneg i32 %arg0 to i64', 'sext i32 %arg0 to i64')
    body_mutation('capture-inverted-bound', capture,
                  r'br i1 %0, label %switch.lookup, label %if.else.34',
                  'br i1 %0, label %if.else.34, label %switch.lookup')
    body_mutation('capture-index-coordinate', capture,
                  r'(ptr @switch\.table\.[^,]+, i64 0, i64 )%1\b', r'\1%cast0')
    body_mutation('capture-pointer-escape', capture,
                  r'(%switch.load = load i64, ptr %switch.gep, align 8)',
                  r'\1\n  %extra.load = load i64, ptr %switch.gep, align 8')
    # The structural supplement cannot itself be a replacement for complete
    # owner/caller authority. This otherwise unrelated actual owned-body change
    # passes its local table checks and must fail the public189-body gate.
    body = bodies[rows['Lemma.Applications.Notebook.packageContext']['symbol']]
    changed, count = re.subn(r'i64 3391488\b', 'i64 3395584', body)
    require(count == 1, 'real private context constant absent')
    changed_ir = ir.replace(body, changed, 1)
    require(len(target._readonly_lookup_verified(changed_ir, unit)[1]) == 6,
            'unrelated body mutation unexpectedly bypassed its intended public-gate test')
    reject('mandatory-complete189-body-gate', changed_ir)
    return {'tables': tables, 'physical_load_sites': sorted(sites), 'negatives': negatives}


def jump_checks(ir, unit, object_dir):
    from audit_kernel import _jump_assembly_function
    assembly = (object_dir / 'program-audit-companion.s').read_text()
    require(digest(object_dir / 'program.opt.ll') == target.PRODUCER_AUTHORITY['actual_artifacts']['program.opt.ll'] and
            digest(object_dir / 'unit.json') == target.PRODUCER_AUTHORITY['actual_artifacts']['unit.json'],
            'JTI fixture does not consume the original actual selected unit/IR')
    rows = target._rows(unit); positives = []; negatives = []

    def rejection(name, call, *, independent=False):
        try:
            call()
        except Core0Error as error:
            negatives.append({'name': name, 'reason': str(error),
                              'independent_machine_cell_relation': independent})
            return
        raise Core0Error('actual Package JTI mutation admitted: ' + name)

    for source, (count, cases) in target.NOTEBOOK_JUMPS.items():
        symbol = rows[source]['symbol']; code, labels = _jump_assembly_function(assembly, symbol)
        table = next(arguments[1][len('%pcrel_hi('):-1] for operation, arguments in code
                     if operation == 'auipc' and arguments[1].startswith('%pcrel_hi(.LJTI'))
        declaration = re.search(r'(?m)^' + re.escape(table) + r':\n((?:\s*\.quad\s+\.LBB\d+_\d+\s*\n)+)', assembly)
        require(declaration is not None, 'actual JTI table declaration missing')
        targets = re.findall(r'\.quad\s+(\.LBB\d+_\d+)', declaration[1])
        spec = target.notebook_jump_spec(ir, unit, source, symbol)
        require(spec[1] == count and spec[4] == cases and len(targets) == count,
                'actual selected source/table count differs')
        relation = target.validate_jump_relation(ir, unit, assembly, symbol, table, targets, code, labels)
        positives.append(relation)
        for field, value in [('configuration', 'lemmasim-silicon-closure-entry2-bulk-notebook'),
                             ('contract_version', 'core0-user-v0.1'), ('image_key', 'course'),
                             ('role', 'kernel')]:
            changed = copy.deepcopy(unit); changed[field] = value
            rejection(source + '/wrong-' + field,
                      lambda changed=changed: target.notebook_jump_spec(ir, changed, source, symbol))
        rejection(source + '/foreign-symbol',
                  lambda: target.notebook_jump_spec(ir, unit, source, symbol + '.foreign'))
        body = target._bodies(ir)[symbol]
        changed, hits = re.subn(r'(i\d+ )' + str(cases[0]) + r'(, label %)',
                               lambda match: match[1] + str(max(cases) + 100) + match[2], body, count=1)
        require(hits == 1, 'actual source switch first case absent')
        rejection(source + '/changed-source-case',
                  lambda: target.notebook_jump_spec(ir.replace(body, changed, 1), unit, source, symbol))
        short = targets[:-1]
        short_assembly = assembly[:declaration.start(1)] + ''.join('\t.quad\t' + name + '\n' for name in short) + assembly[declaration.end(1):]
        rejection(source + '/short-table-count',
                  lambda: target.validate_jump_relation(ir, unit, short_assembly, symbol, table, short, code, labels))
        # Mutate each genuine declared cell together with the supplied cell
        # list. This gets past declaration consistency and complete owner pins,
        # exposing the independent source/machine-cell relation itself.
        for index, old in enumerate(targets):
            other = next(value for value in targets if value != old)
            cells = list(targets); cells[index] = other
            mutated_assembly = assembly[:declaration.start(1)] + ''.join('\t.quad\t' + name + '\n' for name in cells) + assembly[declaration.end(1):]
            rejection(source + '/actual-cell-' + str(index),
                      lambda mutated_assembly=mutated_assembly, cells=cells:
                          target.validate_jump_relation(ir, unit, mutated_assembly, symbol, table, cells, code, labels),
                      independent=True)
        # One actual dispatch instruction change must fail complete machine
        # authority, even though the ordinary source LLVM is unchanged.
        changed_code = copy.deepcopy(code)
        at = next(i for i, (operation, arguments) in enumerate(code) if operation == 'slli' and arguments[-1:] == ['3'])
        changed_code[at][1][-1] = '2'
        rejection(source + '/foreign-machine-instruction-list',
                  lambda: target.validate_jump_relation(ir, unit, assembly, symbol, table, targets, changed_code, labels))
    require(len(positives) == 3 and sum(n['independent_machine_cell_relation'] for n in negatives) == 78,
            'all64glyph/8configure/6reader actual cells did not receive independent negatives')
    return {'positives': positives, 'negatives': negatives,
            'original_actual_object_sha256': digest(object_dir / 'program.o'),
            'audit_companion_sha256': digest(object_dir / 'program-audit-companion.s'),
            'scope': 'actual original object audit companion + source/cell relations; full ordinary object/JTI audit remains separate'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--producer-dir', type=Path, required=True)
    parser.add_argument('--component-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--object-dir', type=Path,
                        help='Retained original actual object/audit companion for independent JTI cell checks')
    parser.add_argument('--producer-source-root', type=Path,
                        help='Explicit complete byte-identical original producer archive; current source remains the default')
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
        source_root = root if args.producer_source_root is None else args.producer_source_root.resolve()
        if args.producer_source_root is not None:
            require(json.loads((source_root / 'source-inputs.json').read_text()) == original['source_inputs'],
                    'original producer archive has a mixed/incomplete input inventory')
        for name, value in original['source_inputs'].items():
            require((source_root / name).resolve().is_relative_to(source_root) and
                    digest(source_root / name) == value, 'original producer source changed: ' + name)
        report['original_source_authority'] = {'root': str(source_root),
            'scope': 'complete original producer bytes; source origin is preserved, current observer is separate',
            'source_count': len(original['source_inputs']), 'producer_head': original['head'],
            'input_inventory_sha256': hashlib.sha256(json.dumps(original['source_inputs'], sort_keys=True).encode()).hexdigest()}
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
        require(target.readonly_lookup((args.producer_dir / 'kernel/program.opt.ll').read_text(), kernel) == (set(), [], set()),
                'actual Kernel acquired Package readonly authority')
        require(target.readonly_lookup('', installer) == (set(), [], set()),
                'shared actual Installer library acquired Package readonly authority')
        readonly = readonly_checks(irs[True], unit)
        jumps = jump_checks(irs[True], unit, args.object_dir) if args.object_dir is not None else None
        report.update(status='PASS_GENUINE_PACKAGE_NOTEBOOK_ARTIFACT_GUARDS', owned_functions=189,
                      positives=['actual-selected-pre', 'actual-selected-post', 'actual-kernel-absence'],
                      negatives=negatives, private_layout=target.PRIVATE_LAYOUT,
                      original_producer=target.PRODUCER_AUTHORITY, readonly=readonly, jumps=jumps,
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
