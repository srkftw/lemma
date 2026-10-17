#!/usr/bin/env python3
"""Qualify modern Power-v2 selection against genuinely emitted kernel LLVM.

This artifact observer never executes the target or establishes notebook Ready.
It retains the original export and tests changed identity, endpoint and gates.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
from audit_kernel import (_ir_definition_body, MODERN_NOTEBOOK_CONFIGURATIONS,
                          validate_modern_power_selection)
from core0_common import Core0Error


def qualify(directory: Path) -> dict:
    unit_path = directory / 'unit.json'
    llvm_path = directory / 'program.ll'
    unit = json.loads(unit_path.read_text())
    ir = llvm_path.read_text()
    if unit.get('configuration') not in MODERN_NOTEBOOK_CONFIGURATIONS or unit.get('role') != 'kernel':
        raise Core0Error('Expected an actual modern kernel export')
    validate_modern_power_selection(ir, unit, optimized=False)
    names = {re.sub(r'^_private\..*?\.[0-9]+\.', '', row['source']): row['symbol']
             for row in unit['functions']}
    prefix = 'Lemma.Platform.LemmaSim.'
    owner = names[prefix + 'NotebookKernel.constructModern']
    configure = names[prefix + 'PowerControl.configureSafety']
    initialize = names['Lemma.Drivers.PowerSafety.initialize']
    constructor = _ir_definition_body(ir, owner)
    body = _ir_definition_body(ir, configure)
    if constructor is None or body is None:
        raise Core0Error('Missing actual modern constructor')
    call = re.search(r'call \{ i64, i64 \} @' + re.escape(configure) + r'\(i64 1, i64 (%[-A-Za-z0-9_.$]+)\)', constructor)
    if call is None:
        raise Core0Error('Missing exact owned endpoint call')
    changes = {
        'wrong-identity-driver': ir.replace(body, body.replace('@' + initialize + '(', '@unadmitted_power_identity(', 1), 1),
        'wrong-owner-id': ir.replace(call[0], call[0].replace('(i64 1,', '(i64 2,'), 1),
        'wrong-endpoint': ir.replace(call[0], call[0].replace(call[1], '0'), 1),
        'extra-configuration-caller': ir + '\ndefine { i64, i64 } @unadmitted_power_caller() {\n'
            '  %v = call { i64, i64 } @' + configure + '(i64 1, i64 23)\n'
            '  ret { i64, i64 } %v\n}\n',
        'missing-configuration': ir.replace(constructor, constructor.replace('@' + configure + '(', '@unadmitted_configuration(', 1), 1),
    }
    # The complete cooperative driver body is pinned independently, including
    # its identity/status checks, record and failure path.
    changed_body = body.replace('i64 1090', 'i64 1091', 1)
    if changed_body == body:
        raise Core0Error('Actual cooperative record site absent')
    changes['wrong-cooperative-record'] = ir.replace(body, changed_body, 1)
    negatives = []
    for name, changed in changes.items():
        if changed == ir:
            raise Core0Error('Unchanged negative stimulus: ' + name)
        try:
            validate_modern_power_selection(changed, unit, optimized=False)
        except Core0Error as error:
            negatives.append({'name': name, 'rejection': str(error)})
        else:
            raise Core0Error('Modern Power authority mutation admitted: ' + name)
    return {'status': 'PASS', 'configuration': unit['configuration'],
            'scope': 'Actual emitted LLVM identity/owned endpoint/caller/gate observer; no target execution or Ready claim',
            'inputs': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (unit_path, llvm_path)},
            'negative_observations': negatives}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise Core0Error('Retain existing observations; use an unused output')
    result = qualify(args.unit_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('Modern Power-v2 actual LLVM observer: PASS (six changed authorities rejected)')


if __name__ == '__main__':
    main()
