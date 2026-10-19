#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Admit immutable IHP functional SRAM models for the selected real macro path.

The PDK checkout can be sparse. Read the exact pinned Git objects without
changing it or downloading inputs. The models remain upstream bytes; this is
functional digital simulation, not a PVT or manufacturing qualification.
"""
import hashlib
import json
import subprocess
from pathlib import Path
from action_cache import write_if_changed

ROOT = Path(__file__).resolve().parents[1]
REVISION = '5e6d592e4002946a4616f798c357f0f3c06cf3b6'
MACRO = 'RM_IHPSG13_1P_256x64_c2_bm_bist'
FILES = ('ihp-sg13g2/libs.ref/sg13g2_sram/verilog/' + MACRO + '.v',
         'ihp-sg13g2/libs.ref/sg13g2_sram/verilog/RM_IHPSG13_1P_core_behavioral_bm_bist.v')


def materialize(destination, pdk=None):
    pdk = Path(pdk) if pdk is not None else ROOT / 'build/silicon/deps/ihp-open-pdk'
    lock = json.loads((ROOT / 'tooling/silicon/physical-lock.json').read_text())
    if lock['pdk']['revision'] != REVISION:
        raise ValueError('Unadmitted SRAM PDK revision')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    outputs = []
    identities = {}
    for name in (*FILES, 'LICENSE'):
        raw = subprocess.check_output(['git', '-C', str(pdk), 'show', REVISION + ':' + name], timeout=30)
        output = destination / Path(name).name
        write_if_changed(output, raw)
        identities[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        if name != 'LICENSE':
            outputs.append(output)
    return outputs, {'repository': lock['pdk']['repository'], 'revision': REVISION,
                     'macro': MACRO, 'instances': 3, 'define': 'FUNCTIONAL',
                     'inputs': identities, 'qualification': 'upstream functional model only; PVT/timing/physical qualification separate'}
