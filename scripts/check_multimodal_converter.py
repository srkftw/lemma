#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run generic MOS/SAR engineering fixtures; no silicon/physical qualification."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(argv, cwd, log, *, timeout=60, expected_success=True):
    start = time.monotonic()
    result = subprocess.run([str(arg) for arg in argv], cwd=cwd, capture_output=True,
                            text=True, timeout=timeout)
    log.write_text(result.stdout + result.stderr)
    observation = {'argv': [str(arg) for arg in argv], 'cwd': str(cwd),
                   'returncode': result.returncode, 'timeout_seconds': timeout, 'elapsed_seconds': time.monotonic() - start,
                   'log_sha256': sha(log)}
    log.with_suffix('.command.json').write_text(json.dumps(observation, indent=2) + '\n')
    if expected_success and re.search(r'(?im)^\s*(?:%\s*)?(?:warning|error|fatal)\b', result.stdout + result.stderr):
        raise RuntimeError('Tool warning/error: ' + str(log))
    if (result.returncode == 0) != expected_success:
        raise RuntimeError(f'Unexpected command outcome {result.returncode}: {log}')
    return observation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--source-dir', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'engineering/multimodal/sar4')
    parser.add_argument('--ngspice', required=True)
    parser.add_argument('--verilator', default='verilator')
    parser.add_argument('--yosys', required=True)
    args = parser.parse_args()
    directory, sources = args.work_dir.resolve(), args.source_dir.resolve()
    if directory.exists():
        parser.error('work directory must be unused')
    directory.mkdir(parents=True)
    names = ('sample-hold-comparator.cir', 'sar4_control.sv', 'Sar4Bench.sv', 'provenance.json', 'LICENSE')
    identities = {name: sha(sources / name) for name in names}
    identities[str(Path(__file__).resolve())] = sha(Path(__file__).resolve())
    tools = {}
    for name, requested in (('ngspice', args.ngspice), ('verilator', args.verilator),
                            ('make', 'make'), ('cxx', 'g++'), ('yosys', args.yosys)):
        path = shutil.which(requested)
        if path is None:
            raise RuntimeError('Missing tool: ' + requested)
        path = Path(path).resolve()
        version = command([path, '--version'], directory, directory / (name + '-version.log'))
        tools[name] = {'path': str(path), 'sha256': sha(path), 'version': version}
    abc = Path(tools['yosys']['path']).parent / 'yosys-abc'
    if not abc.is_file():
        raise RuntimeError('Missing Yosys ABC binary')
    tools['yosys_abc'] = {'path': str(abc), 'sha256': sha(abc)}
    (directory / 'inputs.json').write_text(json.dumps({'source_sha256': identities, 'tools': tools}, indent=2) + '\n')
    prefix = (sources / names[0]).read_text().split('.control')[0]
    assert 'Vdac dac 0 1.0\n' in prefix
    prefix = prefix.replace('Vdac dac 0 1.0\n', '')
    # Independent stimulus/reference arithmetic does not share SAR decisions.
    cases = [('center-' + str(i), .75 + (i + .5) * .025, .75, 1.15) for i in range(16)]
    cases += [('low-clip', .70, .75, 1.15), ('high-clip', 1.20, .75, 1.15),
              ('range-change', .94375, .85, 1.05)]
    rows = []
    for name, voltage, lower, upper in cases:
        case = directory / name
        case.mkdir()
        observed_prefix, replacements = re.subn(
            r'Vin input 0 PWL\([^\n]+\)',
            f'Vin input 0 PWL(0 0.8 0.1u 0.8 0.101u {voltage:.12g} 1.5u {voltage:.12g} 1.501u 0.8 12u 0.8)', prefix)
        assert replacements == 1
        parts = [observed_prefix,
                 f'Vlo vlo 0 {lower}\nVhi vhi 0 {upper}\nRbase dac vlo 80k\n']
        for bit in range(4):
            high = 1.8 if bit == 3 else 0
            parts.append(f'''Vb{bit} b{bit} 0 {high}
Vbn{bit} bn{bit} 0 {1.8 - high}
Mnh{bit} d{bit} b{bit} vhi 0 NM W=500u L=1u
Mph{bit} d{bit} bn{bit} vhi vdd PM W=1000u L=1u
Mnl{bit} d{bit} bn{bit} vlo 0 NM W=500u L=1u
Mpl{bit} d{bit} b{bit} vlo vdd PM W=1000u L=1u
Rw{bit} d{bit} dac {80000 / (2 ** bit)}
''')
        parts.append('''.control
set noaskquit
set wr_vecnames
set wr_singlescale
let resultcode = 0
stop when time=3u
tran 5n 12u
''')
        for bit in range(3, -1, -1):
            parts.append(f'''let decision{bit} = v(out)[length(v(out))-1]
let measured_dac{bit} = v(dac)[length(v(dac))-1]
let held{bit} = v(hold)[length(v(hold))-1]
print decision{bit} measured_dac{bit} held{bit}
if decision{bit} > 0.9
 let resultcode = resultcode + {2 ** bit}
else
 alter Vb{bit} 0
 alter Vbn{bit} 1.8
end
''')
            if bit:
                parts.append(f'''alter Vb{bit - 1} 1.8
alter Vbn{bit - 1} 0
stop when time={3 + 2 * (4 - bit)}u
resume
''')
        parts.append('''print resultcode
wrdata transient.dat v(input) v(hold) v(dac) v(out)
quit
.endc
.end
''')
        netlist = case / 'sar.cir'
        netlist.write_text(''.join(parts))
        invocation = command([tools['ngspice']['path'], '-b', netlist.name], case,
                             case / 'ngspice.log')
        if re.search(r'(?im)^\s*(warning|error|fatal)\b', (case / 'ngspice.log').read_text()):
            raise RuntimeError('SPICE warning/error: ' + name)
        values = {key: float(value) for key, value in re.findall(
            r'^(\w+) = ([-+\d.eE]+)$', (case / 'ngspice.log').read_text(), re.M)}
        expected = max(0, min(15, math.floor((voltage - lower) * 16 / (upper - lower))))
        trial, decisions = 0, []
        for bit in range(3, -1, -1):
            trial |= 1 << bit
            ideal = lower + trial * (upper - lower) / 16
            assert abs(values['measured_dac' + str(bit)] - ideal) < .0003
            assert abs(values['held' + str(bit)] - voltage) < .00001
            level = values['decision' + str(bit)]
            assert level < .1 or 1.7 < level < 1.9
            decision = int(level > .9)
            decisions.append(decision)
            if not decision:
                trial &= ~(1 << bit)
        assert int(values['resultcode']) == trial == expected
        rows.append({'name': name, 'input_volts': voltage, 'reference_volts': [lower, upper],
                     'expected_code': expected, 'actual_code': int(values['resultcode']),
                     'decisions_msb_first': decisions, 'measurements': values,
                     'invocation': invocation, 'netlist_sha256': sha(netlist),
                     'transient_sha256': sha(case / 'transient.dat')})
    swapped = directory / 'negative-comparator'
    swapped.mkdir()
    original = (directory / 'center-0/sar.cir').read_text()
    corrupted = original.replace('Mnleft left hold tail', 'Mnleft left dac tail').replace(
        'Mnright right dac tail', 'Mnright right hold tail')
    assert corrupted != original
    (swapped / 'sar.cir').write_text(corrupted)
    analog_negative = command([tools['ngspice']['path'], '-b', 'sar.cir'], swapped,
                              swapped / 'ngspice.log')
    incorrect = re.search(r'(?m)^resultcode = ([-+\d.eE]+)$', (swapped / 'ngspice.log').read_text())
    assert incorrect and int(float(incorrect[1])) != rows[0]['expected_code']
    # A separate actual MOS reset discharges the held voltage. That conversion
    # is invalid; its partial comparator observations are never an ADC result.
    reset = directory / 'analog-reset'
    reset.mkdir()
    text = (sources / names[0]).read_text().split('.control')[0]
    text += '''Vreset reset 0 PWL(0 0 5.5u 0 5.501u 1.8 12u 1.8)
Mreset hold reset 0 0 NM W=50u L=1u
.control
set noaskquit
set wr_vecnames
set wr_singlescale
tran 5n 12u
meas tran before_reset FIND v(hold) AT=5u
meas tran after_reset FIND v(hold) AT=6u
wrdata transient.dat v(input) v(hold) v(out) v(reset)
quit
.endc
.end
'''
    (reset / 'reset.cir').write_text(text)
    reset_command = command([tools['ngspice']['path'], '-b', 'reset.cir'], reset,
                            reset / 'ngspice.log')
    measured_reset = {key: float(value) for key, value in re.findall(
        r'(?m)^(before_reset|after_reset)\s*=\s*([-+\deE.]+)', (reset / 'ngspice.log').read_text())}
    assert abs(measured_reset['before_reset'] - 1.01) < .00001
    assert abs(measured_reset['after_reset']) < .00001
    for name in names[1:]:
        shutil.copyfile(sources / name, directory / name)
    trace_text = ''.join(format(sum(value << (3 - i) for i, value in enumerate(
        row['decisions_msb_first'])), 'x') + '\n' for row in rows)
    expected_text = ''.join(format(row['expected_code'], 'x') + '\n' for row in rows)
    (directory / 'decisions.hex').write_text(trace_text)
    (directory / 'expected.hex').write_text(expected_text)
    build = command([tools['verilator']['path'], '--binary', '--timing', '--top-module',
                     'Sar4Bench', '--Mdir', 'obj_sar', 'sar4_control.sv', 'Sar4Bench.sv'],
                    directory, directory / 'verilator-build.log', timeout=120)
    executable = directory / 'obj_sar/VSar4Bench'
    digital = command([executable], directory, directory / 'sar-rtl.log')
    synthesis = command([tools['yosys']['path'], '-Q', '-p',
        'read_verilog -sv sar4_control.sv; hierarchy -check -top sar4_control; proc; opt; check -assert; synth -top sar4_control; check -assert; stat; write_json sar4-synth.json'],
        directory, directory / 'yosys.log')
    circuit = json.loads((directory / 'sar4-synth.json').read_text())
    assert set(circuit['modules']) == {'sar4_control'}
    cells = circuit['modules']['sar4_control']['cells']
    assert cells and all(cell['type'].startswith('$_') and 'LATCH' not in cell['type'] for cell in cells.values())
    if 'PASS 19 actual transistor decision traces' not in (directory / 'sar-rtl.log').read_text():
        raise RuntimeError('Missing digital completion observation')
    negative = directory / 'negative-trace'
    negative.mkdir()
    corrupted = trace_text.splitlines()
    corrupted[7] = format(int(corrupted[7], 16) ^ 8, 'x')
    (negative / 'decisions.hex').write_text('\n'.join(corrupted) + '\n')
    (negative / 'expected.hex').write_text(expected_text)
    rejected = command([executable], negative, negative / 'run.log', expected_success=False)
    if 'actual transistor decisions produced wrong code' not in (negative / 'run.log').read_text():
        raise RuntimeError('Negative failed for an unrelated reason')
    assert {name: sha(sources / name) for name in names} == {name: identities[name] for name in names}
    assert sha(Path(__file__).resolve()) == identities[str(Path(__file__).resolve())]
    report = {'schema': 'lemma-generic-cmos-sar4-engineering/1', 'status': 'PASS',
              'scope': 'SIMULATED_ONLY generic synthetic Level1 MOS S/H/comparator/switched DAC and offline paired SAR control; no PDK, layout, ADC accuracy, physical, manufacturing, or integrated Lemma machine claim',
              'time_relation': 'analog sample aperture1us, comparator decisions3/5/7/9us; RTL one acquisition and two settling clocks per decision,1us testbench clocks; actual analog comparator decisions replayed offline, not continuous mixed-signal cosimulation',
              'source_sha256': identities, 'tools': tools, 'analog_cases': rows,
              'reset': {'measurements': measured_reset, 'invocation': reset_command,
                        'transient_sha256': sha(reset / 'transient.dat')},
              'digital_build': build, 'digital_run': digital,
              'synthesis': {'invocation': synthesis, 'cell_count': len(cells), 'json_sha256': sha(directory / 'sar4-synth.json'), 'scope': 'generic digital gates only; no process mapping, timing, layout or mixed-signal closure'},
              'swapped_comparator_negative': {'invocation': analog_negative, 'actual_wrong_code': int(float(incorrect[1])), 'expected_code': rows[0]['expected_code'], 'transient_sha256': sha(swapped / 'transient.dat')},
              'digital_executable_sha256': sha(executable), 'corrupted_comparator_trace': rejected,
              'limits': 'four-bit nominal codes, center/range/rail/reset fixtures only; no ENOB, noise/mismatch/temperature/metastability/comparator-offset or manufacturability qualification; ideal bias/reference supplies remain explicit boundaries'}
    (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS generic MOS converter:19 voltage/range cases, held-aperture/reset, actual-decision SAR control and corrupted-trace rejection')


if __name__ == '__main__':
    main()
