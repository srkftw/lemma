#!/usr/bin/env python3
"""Qualify eight genuine backlog catalogs/LLVM and actual NumberPad machine code.

This is host artifact inspection, separate from connected raw-device execution.
The independent semantic negatives mutate actual emitted, verified LLVM.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import resource
import time

from audit_kernel import (_ir_definition_body, _jump_assembly_function,
                          validate_unit, validate_ir)
from build_core0 import LLC_ARGUMENTS
from core0_common import Core0Error, require_tools, run_bounded
from dirty_batch_notebook_target import NUMERIC_CHARACTER, numeric_jump_relation, numeric_validate
import notebook_control_backlog_target as B
from paper_next import canonical

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--semantic-only', action='store_true',
                        help='Run exact canonical pre-LLVM and scoped-owner semantic negatives only; no all-eight/machine-code qualification claim')
    args = parser.parse_args()
    out = args.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'build'):
        parser.error('an unused ignored build output is required')
    out.mkdir(parents=True)
    start = time.monotonic()
    resource.setrlimit(resource.RLIMIT_AS, (16 << 30, 16 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    report = {'status': 'FAIL', 'scope': __doc__, 'phases': [], 'machine_relations': [],
              'negatives': [], 'commands': [], 'bounds': {'whole_seconds': 1200, 'command_seconds': 180}}
    inputs = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for directory in ('scripts', 'tooling') for p in (ROOT / directory).rglob('*')
              if p.is_file() and p.suffix in ('.py', '.json') and '__pycache__' not in p.parts}
    report['observer_inputs'] = inputs

    def bound():
        B.require(time.monotonic() - start < 1200, 'original 1200s artifact deadline')

    def run(label, argv):
        bound()
        result = run_bounded(argv, cwd=ROOT, timeout_seconds=min(180, 1200 - (time.monotonic() - start)))
        (out / (label + '.log')).write_bytes(result.stdout + result.stderr)
        report['commands'].append({'label': label, 'argv': list(result.argv),
                                   'seconds': result.elapsed_seconds, 'returncode': result.returncode})
        B.require(result.returncode == 0, 'actual tool failed: ' + label)

    def relation(unit, ir, asm):
        symbol = next(r['symbol'] for r in unit['functions'] if canonical(r['source']) == NUMERIC_CHARACTER)
        code, labels = _jump_assembly_function(asm, symbol)
        tables = re.findall(r'%pcrel_hi\((\.LJTI[^)]+)\)', repr(code))
        B.require(len(tables) == 1, 'actual NumberPad table inventory differs')
        table = tables[0]
        declarations = re.findall(r'(?m)^' + re.escape(table) + r':\n((?:\s*\.quad\s+\.LBB\d+_\d+\s*\n)+)', asm)
        B.require(len(declarations) == 1, 'actual NumberPad table definition differs')
        targets = re.findall(r'\.quad\s+(\.LBB\d+_\d+)', declarations[0])
        return numeric_jump_relation(ir, unit, asm, symbol, table, targets, code, labels)

    try:
        tools = require_tools(('llc', 'opt'))
        for cfg in (() if args.semantic_only else sorted(B.CONFIGURATIONS)):
            directory = args.capture / cfg / 'users/notebook'
            unit = json.loads((directory / 'unit.json').read_text())
            validate_unit(unit, 'user', configuration=cfg, image_key='notebook')
            for phase, filename in (('pre', 'program.ll'), ('post', 'program.opt.ll')):
                bound()
                ir = (directory / filename).read_text()
                numeric = numeric_validate(ir, unit, optimized=phase == 'post')
                generic = validate_ir(ir, unit, optimized=phase == 'post', optimization='O2')
                report['phases'].append({'configuration': cfg, 'phase': phase,
                                         'complete_sha256': numeric['complete_corpus_sha256'],
                                         'generic': generic})
            asm_path = out / (cfg + '.s')
            run(cfg + '-llc', [tools['llc'], *[('-filetype=asm' if x == '-filetype=obj' else x)
                                             for x in LLC_ARGUMENTS], '-stack-size-section', '-O2',
                              str(directory / 'program.opt.ll'), '-o', str(asm_path)])
            got = relation(unit, ir, asm_path.read_text())
            B.require(len(got['all_cells']) == 25, 'all NumberPad table cells must remain checked')
            report['machine_relations'].append({'configuration': cfg, 'all25_cells': True,
                                                'complete_owner_sha256': got['machine_sha256']})
            (out / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')
        cfg = 'lemmasim-silicon-package-chooser-bulk-notebook'
        directory = args.capture / cfg / 'users/notebook'
        unit = json.loads((directory / 'unit.json').read_text())
        ir = (directory / 'program.ll').read_text()
        numeric_validate(ir, unit, optimized=False)
        rows = {canonical(r['source']): r for r in unit['functions']}
        mutations = [
            ('wrong-capacity', B.PREFIX + 'capacity', 'ret i64 8', 'ret i64 7'),
            ('wrong-context-argument-order', B.PREFIX + 'push', 'i64 %arg2)', 'i64 %arg3)'),
            ('context-equality-inverted', B.NOTEBOOK + 'pumpBookTap',
             'icmp eq i64 %action.call.value64, %action.call.value23',
             'icmp ne i64 %action.call.value64, %action.call.value23'),
            ('dequeue-bypassed', B.NOTEBOOK + 'pumpBookTap',
             '@' + rows[B.PREFIX + 'pop']['symbol'] + '(',
             '@' + rows[B.PREFIX + 'count']['symbol'] + '('),
        ]
        for name, owner, old, new in mutations:
            body = _ir_definition_body(ir, rows[owner]['symbol'])
            B.require(body.count(old) == 1, 'actual mutation site absent: ' + name)
            marker = re.search(r'^define [^\n]*@' + re.escape(rows[owner]['symbol']) +
                               r'\([^\n]*\)[^\n]*\{\n', ir, re.M)
            B.require(marker is not None and ir[marker.end():marker.end() + len(body)] == body,
                      'actual mutation body is not at the exact declared owner: ' + name)
            bad = ir[:marker.end()] + body.replace(old, new, 1) + ir[marker.end() + len(body):]
            from usb_recovery_target import corpus
            original_functions = corpus(ir, unit)['functions']
            bad_functions = corpus(bad, unit)['functions']
            B.require({s for s in original_functions if original_functions[s] != bad_functions[s]} == {owner},
                      'mutation escaped its sole declared LLVM owner: ' + name)
            filename = out / (name + '.ll')
            filename.write_text(bad)
            run(name + '-verify', [tools['opt'], '-passes=verify', '-disable-output', str(filename)])
            try:
                B.semantics(bad, unit)
            except Core0Error as error:
                report['negatives'].append({'name': name, 'owner': owner,
                                            'sole_changed_owner_verified': True,
                                            'valid_llvm': True, 'reason': str(error)})
            else:
                raise Core0Error('independent semantic mutation admitted: ' + name)
        bad = copy.deepcopy(unit)
        bad['configuration'] = 'lemmasim-silicon-package-closure-entry2-bulk-notebook'
        try:
            B.entry(bad)
        except Core0Error as error:
            report['negatives'].append({'name': 'outside-eight-configurations', 'reason': str(error)})
        else:
            raise Core0Error('backlog authority escaped its exact deployments')
        bound()
        report['status'] = ('PASS_BACKLOG4_SCOPED_OWNER_LLVM_NEGATIVES_AND_DEPLOYMENT_REJECTION'
                            if args.semantic_only else
                            'PASS_BACKLOG16_COMPLETE_PHASES8_MACHINE_OWNERS5_INDEPENDENT_NEGATIVES')
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        report['seconds'] = time.monotonic() - start
        report['peak_RSS_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        report['observer_inputs_equal'] = all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h
                                              for name, h in inputs.items())
        if not report['observer_inputs_equal']:
            report['status'] = 'FAIL'
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], report['seconds'])
    if report['status'] == 'FAIL':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
