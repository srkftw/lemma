#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded old/new pen interface and independent full-depth literal checks.

This finite clock corpus is not an equivalence proof or physical measurement.
The previous RTL is extracted from an immutable Git object and hash checked.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_silicon import command, device_build, sha

BASE_COMMIT = 'e2acaa7821519d03346af2ccfd0a890fdab2afd5'
BASE_SHA = 'f73a3c556e1444cfdcb380a902496af041f64d99d880507020b54ff0a5fbf2e4'

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=600)
    p.add_argument('--jobs', type=int, default=2)
    a = p.parse_args()
    if not 1 <= a.timeout <= 600 or not 1 <= a.jobs <= 4:
        p.error('Declared bounds must be timeout1..600 and jobs1..4')
    out = a.output_dir.resolve()
    out.mkdir(parents=True)
    paths = ('sim/rtl/lemma_pen.sv', 'conformance/silicon/PenIngress.sv',
             'conformance/silicon/PenBanks.sv', 'conformance/silicon/check_pen_ingress.py',
             'scripts/check_silicon.py', 'tooling/silicon/sim.nix', 'flake.lock')
    before = {name: sha(ROOT / name) for name in paths}
    r = {'status': 'FAIL', 'scope': 'bounded every-edge external-interface miter plus independent literal full-depth pen corpus; not proof, guest execution or physical closure',
         'source_inputs': before, 'reference_commit': BASE_COMMIT, 'reference_sha256': BASE_SHA,
         'plan': {'compile_seconds_per_command': a.timeout, 'simulation_seconds_per_command': 30, 'jobs': a.jobs},
         'commands': []}
    try:
        raw = subprocess.check_output(['git', 'show', BASE_COMMIT + ':sim/rtl/lemma_pen.sv'], cwd=ROOT)
        original = out / 'original.sv'; original.write_bytes(raw)
        if sha(original) != BASE_SHA or raw.count(b'module lemma_pen #(') != 1:
            raise RuntimeError('Unknown prior pen source identity')
        reference = out / 'reference.sv'
        reference.write_bytes(raw.replace(b'module lemma_pen #(', b'module lemma_pen_reference #('))
        r['reference_renamed_sha256'] = sha(reference)
        observations = []
        tools = None
        for top, sources, markers in (
            ('PenIngress', [ROOT / paths[0], reference, ROOT / paths[1]],
             ['PEN-INGRESS literal full256 fields high64 sequence/time consecutive/wrap PASS',
              'PEN-INGRESS every-edge old/new invalid full ACK reset collision PASS edges']),
            ('PenBanks', [ROOT / paths[0], ROOT / paths[2]],
             ['PEN-BANKS full-capacity all-fields two-wrap and ingress bypass PASS',
              'PEN-BANKS refill backpressure reset cancellation and watchdog head PASS'])):
            obj = out / (top + '-obj'); obj.mkdir()
            argv = ['verilator', '--binary', '--timing', '-j', str(a.jobs), '-Wno-fatal',
                    '--top-module', top, '--Mdir', str(obj), *(str(s) for s in sources)]
            record, current = device_build(argv, out / (top + '-tools.json'), out / (top + '-build.log'), a.timeout)
            r['commands'].append(record)
            if tools is not None and tools != current:
                raise RuntimeError('Tool identities changed between checks')
            tools = current
            log = out / (top + '-simulation.log')
            r['commands'].append(command([str(obj / ('V' + top))], log, 30))
            text = log.read_text()
            if any(text.count(marker) != 1 for marker in markers):
                raise RuntimeError('Missing or duplicate independent observation')
            observations += markers
            r.setdefault('binaries', {})[top] = sha(obj / ('V' + top))
        if before != {name: sha(ROOT / name) for name in paths}:
            raise RuntimeError('Consumed source changed during qualification')
        r.update(status='PASS', observations=observations, tools=tools)
    except BaseException as e:
        r['error'] = repr(e)
    (out / 'result.json').write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps({'status': r['status'], 'error': r.get('error')}), flush=True)
    return 0 if r['status'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
