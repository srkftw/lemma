#!/usr/bin/env python3
"""Qualify Surface-v2 authority against genuine selected Lean LLVM exports.

This observes compiled ABI guards, not target execution or compiler correctness.
The untouched exports remain the positive inputs; negatives change actual bodies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audit_kernel import _ir_definition_body
from core0_common import Core0Error
import paper_bulk


def qualify(kernel: Path, notebook: Path) -> dict:
    observations = []
    identities = {}
    for role, directory in [('kernel', kernel), ('user', notebook)]:
        unit_path, ir_path = directory / 'unit.json', directory / 'program.ll'
        unit, ir = json.loads(unit_path.read_text()), ir_path.read_text()
        if unit.get('role') != role or unit.get('configuration') not in paper_bulk.CONFIGURATIONS:
            raise Core0Error('Expected actual Surface-v2 selected exports')
        positive = paper_bulk.validate(ir, unit, optimized=False)
        if not positive:
            raise Core0Error('Surface-v2 qualification did not exercise an admitted export')
        identities[role] = {'inputs': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in (unit_path, ir_path)}, 'authority': positive}
        by = {paper_bulk.canonical(row['source']): row['symbol'] for row in unit['functions']}

        def change(source: str, old: str, new: str) -> str:
            body = _ir_definition_body(ir, by[source])
            if body is None or old not in body:
                raise Core0Error('Missing actual negative stimulus: ' + source + ': ' + old)
            changed = body.replace(old, new, 1)
            return ir.replace(body, changed, 1)

        if role == 'kernel':
            prefix = 'Lemma.Platform.LemmaSim.DeviceService.'
            surface = by[prefix + 'surfaceV2']
            changes = {
                'eighth-tile-admitted': change(prefix + 'uploadBulk', 'icmp ult i64 7,', 'icmp ult i64 8,'),
                'unaligned-descriptor-admitted': change(prefix + 'uploadBulk', 'urem i64 %arg1, 4096', 'urem i64 %arg1, 8'),
                'incomplete-copy-preflight': change(prefix + 'uploadBulk', 'add i64 256,', 'add i64 248,'),
                'bounce-alias-guard-reversed': change(prefix + 'uploadBulk', 'icmp eq i64 %action.call.value11, %arg0', 'icmp ne i64 %action.call.value11, %arg0'),
                'wrong-packet-version': change(prefix + 'uploadBulk', 'icmp eq i64 %action.call.value30, 2', 'icmp eq i64 %action.call.value30, 1'),
                'tile-geometry-expanded': change(prefix + 'bulkValidateStep', 'icmp ult i64 32,', 'icmp ult i64 33,'),
                'fresh-page-purpose-changed': change('Lemma.Drivers.Paper.uploadOffset', '(i64 1, i64 %arg0, i64 1)', '(i64 1, i64 %arg0, i64 2)'),
                'extra-device-call-authority': ir + '\ndefine { i64, i64 } @unadmitted_surface_caller() {\n'
                    '  %r = call { i64, i64 } @' + surface + '(i64 1, i64 2, i64 5, i64 3, i64 7, i64 0)\n'
                    '  ret { i64, i64 } %r\n}\n',
            }
        else:
            prefix = 'Lemma.Ink.Surface.'
            root = 'Lemma.Applications.Notebook.' + ('mainBytesBulk' if unit['configuration'] in paper_bulk.BYTES else 'mainSumsBulk')
            selection = 4 if unit['configuration'] in paper_bulk.BYTES else 3
            changes = {
                'packet-overflows-page': change(prefix + 'bulkUploadStep', 'icmp ule i32 %cast8, 7', 'icmp ule i32 %cast8, 8'),
                'short-word-stride': change(prefix + 'bulkCopyWord', 'mul i64 %cast1, 8', 'mul i64 %cast1, 4'),
                'bulk-root-disables-private-mode': change(root, f'i64 %arg0, i64 {selection}, i64 1', f'i64 %arg0, i64 {selection}, i64 0'),
                'wrong-fold-budget': change(prefix + 'uploadAllBulk', 'icmp ule i32 %cast17, 2341', 'icmp ule i32 %cast17, 2342'),
            }
        for name, changed in changes.items():
            if changed == ir:
                raise Core0Error('Unchanged authority stimulus: ' + name)
            try:
                paper_bulk.validate(changed, unit, optimized=False)
            except Core0Error as error:
                observations.append({'role': role, 'name': name, 'rejection': str(error)})
            else:
                raise Core0Error('Surface-v2 authority mutation admitted: ' + name)
    return {'status': 'PASS', 'scope': 'Genuine selected pre-LLVM authority observer; no guest execution or performance claim',
            'positive': identities, 'negative_observations': observations}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-unit-dir', type=Path, required=True)
    parser.add_argument('--notebook-unit-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise Core0Error('Retain existing observations; use an unused output')
    result = qualify(args.kernel_unit_dir, args.notebook_unit_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('Surface-v2 actual LLVM observer: PASS (12 changed authorities rejected)')


if __name__ == '__main__':
    main()
