#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded independent reproducer for the pinned setup-repair journal defect."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from silicon_synth import ROOT, CommandFailure, run, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out.exists():
        parser.error('Use an unused output directory')
    out.mkdir(parents=True)
    report = {'schema': 'lemma-openroad-journal-reproducer/1', 'status': 'FAIL',
              'scope': '34-cell tool-control-flow reproducer; no controller timing or physical closure',
              'clock_period_ns': 0.5, 'commands': []}
    try:
        tool = shutil.which('openroad')
        if not tool or not tool.startswith('/nix/store/'):
            raise RuntimeError('Use the pinned tooling/silicon/eda.nix environment')
        report['tool'] = {'path': tool, 'sha256': sha(Path(tool)),
                          'version': subprocess.check_output([tool, '-version'], text=True).strip()}
        if '26Q2' not in report['tool']['version']:
            raise RuntimeError('Unsupported OpenROAD version')
        sources = ['tooling/silicon/journal-repro.tcl', 'tooling/silicon/journal-repro.v',
                   'tooling/silicon/eda.nix', 'tooling/silicon/physical-lock.json', 'flake.lock',
                   'scripts/check_openroad_journal.py']
        report['source_inputs'] = {p: sha(ROOT/p) for p in sources}
        pdk = ROOT/'build/silicon/deps/ihp-open-pdk'
        pin = json.loads((ROOT/'tooling/silicon/physical-lock.json').read_text())['pdk']['revision']
        if subprocess.check_output(['git', '-C', str(pdk), 'rev-parse', 'HEAD'], text=True).strip() != pin:
            raise RuntimeError('Unsupported PDK revision')
        if subprocess.check_output(['git', '-C', str(pdk), 'status', '--porcelain'], text=True).strip():
            raise RuntimeError('Dirty PDK')
        std = pdk/'ihp-sg13g2/libs.ref/sg13g2_stdcell'
        report['pdk'] = {'revision': pin, 'inputs': {p: sha(std/p) for p in
            ['lef/sg13g2_tech.lef', 'lef/sg13g2_stdcell.lef', 'lib/sg13g2_stdcell_typ_1p20V_25C.lib']}}
        deadline = time.monotonic()+120
        for phase in ['LEGACY', 'WNS_PATH']:
            wrapper = out/(phase+'.tcl')
            wrapper.write_text('set env(LEMMA_JOURNAL_PHASE) '+phase+'\nsource '+str(ROOT/'tooling/silicon/journal-repro.tcl')+'\n')
            try:
                record = run([tool, '-exit', '-no_init', str(wrapper)], out/(phase+'.log'), deadline)
            except CommandFailure as failure:
                record = failure.record
            report['commands'].append(record)
        legacy, path = report['commands']
        before = (out/'LEGACY.log').read_text()
        after = (out/'WNS_PATH.log').read_text()
        if (legacy['timed_out'] or legacy['exit_code'] != -6 or
                before.count('[DEBUG RSZ-journal] journal end\n') != 2 or
                'odb::dbJournal*' not in before or 'Resizer::journalEnd()' not in before):
            raise RuntimeError('Expected double-close assertion was not reproduced')
        slacks = re.findall(r'worst slack max ([-+0-9.]+)', after)
        if (path['timed_out'] or path['exit_code'] != 0 or
                after.count('[DEBUG RSZ-journal] journal end\n') != 1 or
                len(slacks) != 2 or not float(slacks[0]) < float(slacks[1]) < 0 or
                'Removed 1 buffers.' not in after):
            raise RuntimeError('Supported path phase did not make an observed repair safely')
        if report['source_inputs'] != {p: sha(ROOT/p) for p in sources}:
            raise RuntimeError('Inputs changed during reproduction')
        report.update(status='PASS', legacy='EXPECTED_ABORT_DOUBLE_CLOSE',
                      supported_phase='WNS_PATH', before_wns_ns=float(slacks[0]),
                      after_wns_ns=float(slacks[1]), timing='VIOLATED')
    except Exception as error:
        report['error'] = str(error)
    (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'status': report['status'], 'result': str(out/'result.json')}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
