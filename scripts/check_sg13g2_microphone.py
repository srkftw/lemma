#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual public-process HBT microphone first-stage operating tests.

No microphone transducer, ADC, extracted layout, safety or whole-device claim.
Original model bytes include all inactive-corner include dependencies.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import resource
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = '5e6d592e4002946a4616f798c357f0f3c06cf3b6'
MODEL_PREFIX = 'ihp-sg13g2/libs.tech/ngspice/models/'


def require(value, why):
    if not value:
        raise RuntimeError(why)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pdk', type=Path, required=True)
    p.add_argument('--ngspice', type=Path, required=True)
    p.add_argument('--work-dir', type=Path, required=True)
    args = p.parse_args()
    out, pdk, ngspice = (v.resolve() for v in (args.work_dir, args.pdk, args.ngspice))
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    (out / 'models').mkdir()
    started = time.monotonic()
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 << 20, 128 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    circuit = ROOT / 'engineering/multimodal/microphone-preamp-sg13g2.cir'
    report = {'schema': 'lemma-process-microphone-first-stage/1', 'status': 'FAIL',
              'scope': __doc__, 'process_revision': REVISION,
              'source_inputs': {str(v.relative_to(ROOT)): sha(v) for v in (circuit, Path(__file__).resolve())},
              'tools': {'ngspice': {'path': str(ngspice), 'sha256': sha(ngspice)}},
              'models': {}, 'cases': [], 'bounds': {'whole_seconds': 120, 'each_seconds': 10,
                  'AS_bytes': 1 << 30, 'file_bytes': 128 << 20},
              'remaining': ['microphone MEMS/material/process and assembly',
                  'qualified low-noise ADC and converter/controller connection',
                  'passive component/process binding and board interconnect',
                  'layout/DRC/LVS/extraction/mismatch characterization',
                  'pad/ESD/power isolation and physical safety qualification']}
    try:
        pending, seen = ['cornerHBT.lib'], set()
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            require(re.fullmatch(r'[A-Za-z0-9_]+\.lib', name), 'unbounded model include')
            raw = subprocess.check_output(['git', '-C', str(pdk), 'show',
                REVISION + ':' + MODEL_PREFIX + name], timeout=10)
            target = out / 'models' / name
            target.write_bytes(raw)
            report['models'][name] = {'sha256': sha(target), 'bytes': len(raw)}
            seen.add(name)
            # Preserve non-UTF8 model bytes verbatim. Only ASCII directives are
            # decoded here; the public model includes a Latin1 micro symbol.
            pending.extend(re.findall(r'(?im)^\s*\.include\s+(\S+)', raw.decode('latin1')))
        require(len(seen) == 4, 'unexpected original HBT include closure')
        license_bytes = subprocess.check_output(['git', '-C', str(pdk), 'show', REVISION + ':LICENSE'], timeout=10)
        (out / 'models/LICENSE').write_bytes(license_bytes)
        report['model_license_sha256'] = sha(out / 'models/LICENSE')
        version = subprocess.check_output([str(ngspice), '--version'], text=True, timeout=10)
        require('ngspice-45' in version, 'unqualified ngspice version')
        (out / 'version.txt').write_text(version)
        report['tools']['ngspice']['version_sha256'] = sha(out / 'version.txt')
        design = circuit.read_text()

        def simulate(name, supply, temp, corner, *, reverse=False, power_cycle=False, overload=False):
            require(time.monotonic() - started < 110, 'whole prospective runtime budget exhausted')
            directory = out / name
            directory.mkdir()
            # Relative paths keep original model-local include resolution.
            shutil.copytree(out / 'models', directory / 'models')
            (directory / 'preamp.cir').write_text(design)
            supply_text = (f'PWL(0 {supply} 4m {supply} 4.001m 0 7m 0 7.001m {supply} 16m {supply})'
                           if power_cycle else str(supply))
            ports = 'outn outp' if reverse else 'outp outn'
            input_text = 'SIN(0 1m 1000)'
            if overload:
                values = [(i * .00001, (.05 if i < 400 else .001) * math.sin(2 * math.pi * i / 100))
                          for i in range(1601)]
                input_text = 'PWL(' + ' '.join(f'{t:.9g} {v:.9g}' for t, v in values) + ')'
            transient_end = '.1' if power_cycle else '.016'
            bench = f'''SG13G2 process microphone first-stage {name}
.lib models/cornerHBT.lib {corner}
.include preamp.cir
.temp {temp}
Vdd vdd 0 {supply_text}
Vin input 0 {input_text} AC 1
Xpreamp input vdd {ports} 0 lemma_mic_preamp
.control
set noaskquit
set wr_vecnames
set wr_singlescale
op
print v(outp) v(outn) i(Vdd)
ac dec 20 20 20000
let difference = v(outp)-v(outn)
wrdata ac.dat difference
noise v(outp,outn) Vin dec 20 20 20000
setplot noise2
print onoise_total
tran 1u {transient_end}
wrdata transient.dat v(input) v(outp) v(outn) v(vdd)
quit
.endc
.end
'''
            (directory / 'bench.cir').write_text(bench)
            t = time.monotonic()
            result = subprocess.run([str(ngspice), '-b', 'bench.cir'], cwd=directory,
                                    capture_output=True, text=True, timeout=10)
            log = result.stdout + result.stderr
            (directory / 'ngspice.log').write_text(log)
            require(result.returncode == 0 and not re.search(r'(?im)^\s*(warning|error|fatal)\b', log),
                    'actual simulator failed or warned: ' + name)
            ac = [[float(x) for x in line.split()] for line in (directory / 'ac.dat').read_text().splitlines()[1:]]
            require(len(ac) == 61 and all(math.isfinite(x) for row in ac for x in row), 'incomplete/nonfinite AC sweep')
            at1k = min(ac, key=lambda row: abs(row[0] - 1000))
            gain = math.hypot(at1k[1], at1k[2])
            noise = float(re.search(r'(?m)^onoise_total = ([-+\deE.]+)', log)[1])
            transient = [[float(x) for x in line.split()] for line in (directory / 'transient.dat').read_text().splitlines()[1:]]
            require(len(transient) >= 16000 and all(math.isfinite(x) for row in transient for x in row),
                    'incomplete/nonfinite actual transient')
            # Independent sine correlation on an integer number of input
            # periods; no use of the circuit's gain equation or model internals.
            settled = [row for row in transient if (.096 if power_cycle else .012) <= row[0] <= float(transient_end)]
            correlation = sum((row[2] - row[3]) * row[1] for row in settled) / sum(row[1] ** 2 for row in settled)
            observed = {'name': name, 'supply_V': supply, 'temperature_C': temp, 'model_corner': corner,
                'gain_near_1kHz': gain, 'real_gain_near_1kHz': at1k[1],
                'transient_gain': correlation, 'output_noise_Vrms_20Hz_20kHz': noise,
                'seconds': time.monotonic() - t, 'log_sha256': sha(directory / 'ngspice.log'),
                'bench_sha256': sha(directory / 'bench.cir'), 'transient_sha256': sha(directory / 'transient.dat'),
                'ac_sha256': sha(directory / 'ac.dat')}
            if reverse:
                require(at1k[1] < -2 and correlation < -2, 'reversed physical wiring negative did not expose polarity')
                observed['status'] = 'EXPECTED_POLARITY_REJECTION'
            else:
                require(2 < at1k[1] < 25 and 2 < correlation < 25 and 0 < noise < .001,
                        'operating gain/noise window failure: ' + name)
                require(all(-.01 < row[2] < supply + .01 and -.01 < row[3] < supply + .01 for row in transient),
                        'output rail excursion: ' + name)
                if power_cycle:
                    off = [row for row in transient if .006 <= row[0] <= .0069]
                    require(off and max(abs(row[2]) + abs(row[3]) for row in off) < .01,
                            'power-off output did not fall to declared inactive range')
                    observed['power_off_max_output_V'] = max(max(abs(row[2]), abs(row[3])) for row in off)
                    observed['post_restore_availability_delay_s'] = .089
                if overload:
                    overloaded = [row for row in transient if .001 <= row[0] <= .004]
                    overload_gain = sum((row[2] - row[3]) * row[1] for row in overloaded) / sum(row[1] ** 2 for row in overloaded)
                    require(0 < overload_gain < .95 * correlation,
                            'declared overload did not exercise actual nonlinear compression')
                    observed['overload_gain'] = overload_gain
                    observed['overload_input_peak_V'] = .05
                observed['status'] = 'PASS_PROCESS_MODEL_OPERATING_WINDOW'
            report['cases'].append(observed)

        for corner in ('hbt_typ', 'hbt_bcs', 'hbt_wcs'):
            for temp in (-20, 27, 85):
                for supply in (1.1, 1.2, 1.3):
                    simulate(f'{corner}-{temp}-{supply}', supply, temp, corner)
        simulate('power-cycle', 1.2, 27, 'hbt_typ', power_cycle=True)
        simulate('overload-recovery', 1.2, 27, 'hbt_typ', overload=True)
        simulate('reversed-wiring-negative', 1.2, 27, 'hbt_typ', reverse=True)
        require(all(sha(ROOT / name) == value for name, value in report['source_inputs'].items()), 'source drift')
        report['status'] = 'PASS_PROCESS_MODEL_MICROPHONE_FIRST_STAGE'
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        report['seconds'] = time.monotonic() - started
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report.get('error'), report['seconds'])
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
