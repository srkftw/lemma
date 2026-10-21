#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the exact required physical power interface, without changing signals.

Run assess inside the pinned OpenROAD Python interpreter. This checks actual
OpenDB terminals and exact Verilog bytes, not process DRC, LVS or timing.
"""
from pathlib import Path
import hashlib
import json
import time

EXPECTED = {'VDDlogic': 'POWER', 'VDDARRAY': 'POWER', 'VSS': 'GROUND'}


def signal_bytes(text, reloaded_power=False):
    suffix = '    wdata,\n    VDDlogic,\n    VDDARRAY,\n    VSS);'
    # OpenROAD reserializes physical BTerms before vector ports after read_db.
    # Admit only its exact three-name header, retaining every connection below.
    prefix = '    write,\n    VDDlogic,\n    VDDARRAY,\n    VSS,\n    addr,'
    if reloaded_power and text.count(prefix) == 1 and suffix not in text:
        text = text.replace(prefix, '    write,\n    addr,')
    elif text.count(suffix) == 1 and not reloaded_power:
        text = text.replace(suffix, '    wdata);')
    else:
        raise ValueError('Expected exact three added physical PG ports')
    for name in EXPECTED:
        line = ' inout ' + name + ';\n'
        if text.count(line) != 1:
            raise ValueError('Expected exact physical PG declaration: ' + name)
        text = text.replace(line, '')
    return text


def assess(prior, current, output):
    import odb
    started = time.monotonic()
    prior, current, output = map(Path, (prior, current, output))

    def ports(path):
        db = odb.dbDatabase.create()
        odb.read_db(db, str(path.resolve()))
        result = {}
        for term in db.getChip().getBlock().getBTerms():
            shapes = sorted((box.getTechLayer().getName(), box.xMin(), box.yMin(), box.xMax(), box.yMax())
                            for pin in term.getBPins() for box in pin.getBoxes())
            result[term.getName()] = {'type': term.getSigType(), 'io': term.getIoType(),
                                     'net': term.getNet().getName(), 'shapes': shapes}
        return result

    before, after = ports(prior / 'routed.odb'), ports(current / 'routed.odb')
    if set(after) - set(before) != set(EXPECTED) or set(before) - set(after):
        raise ValueError('Physical PG integration added/deleted an unexpected port')
    if any(before[key] != after[key] for key in before):
        raise ValueError('Original port type/net/geometry changed')
    for name, kind in EXPECTED.items():
        actual = after[name]
        if (actual['type'], actual['io'], actual['net']) != (kind, 'INOUT', name) or not actual['shapes']:
            raise ValueError('Required physical PG port binding differs: ' + name)
    if signal_bytes((current / 'routed.v').read_text()) != (prior / 'routed.v').read_text():
        raise ValueError('Physical PG integration changed remaining Verilog bytes')
    inputs = [Path(__file__), prior / 'routed.odb', current / 'routed.odb', prior / 'routed.v', current / 'routed.v']
    report = {'schema': 'lemma-pen-required-PG-ports/1',
              'status': 'PASS_EXACT_THREE_PG_PORTS_ORIGINAL_SIGNALS_PRESERVED',
              'scope': __doc__, 'original_ports': len(before),
              'added_ports': {name: after[name] for name in EXPECTED},
              'inputs': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
              'seconds': time.monotonic() - started}
    output.write_text(json.dumps(report, indent=2) + '\n')
    return report
