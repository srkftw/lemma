#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Operate the process-bound comparator with the maintained HBT preamplifier.

External clock/input/load stimuli; original public QS/NQS PSP compact models.
No ADC resolution, mismatch, extracted layout or physical qualification claim.
A model capsule explicitly reuses original compilation receipts; it is not fresh
compilation. Every parameter/source/model and producer identity is checked.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = '5e6d592e4002946a4616f798c357f0f3c06cf3b6'
PREFIX = 'ihp-sg13g2/libs.tech/'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def invoke(argv, cwd, log, deadline, seconds):
    # A previously expired deadline must never create an owned process.
    remaining = min(seconds, deadline - time.monotonic())
    require(remaining > 0, 'budget exhausted before Popen')

    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
        resource.setrlimit(resource.RLIMIT_FSIZE, (128 << 20, 128 << 20))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    started = time.monotonic()
    process = subprocess.Popen(list(map(str, argv)), cwd=cwd, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=limits)
    raw = b''
    try:
        try:
            raw = process.communicate(timeout=remaining)[0]
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            raw = process.communicate(timeout=2)[0]
            raise RuntimeError('original prospective SPICE deadline')
        require(process.returncode == 0, 'SPICE exit ' + str(process.returncode))
        return raw.decode(errors='replace'), time.monotonic() - started
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        log.write_bytes(raw)


def bind_originals(pdk, out, capsule):
    """Read immutable Git objects; do not edit the original process models."""
    manifest = {}

    def take(name):
        raw = subprocess.check_output(['git', '-C', str(pdk), 'show', REVISION + ':' + name], timeout=10)
        manifest[name] = hashlib.sha256(raw).hexdigest()
        return raw

    model_dir = out / 'models'
    model_dir.mkdir()
    pending, seen = ['cornerMOSlv.lib', 'cornerHBT.lib'], set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        require(re.fullmatch(r'[A-Za-z0-9_]+\.lib', name), 'unbounded original model include')
        raw = take(PREFIX + 'ngspice/models/' + name)
        (model_dir / name).write_bytes(raw)
        seen.add(name)
        pending.extend(re.findall(r'(?im)^\s*\.include\s+(\S+)', raw.decode('latin1')))
    va_prefix = PREFIX + 'verilog-a/psp103/'
    names = subprocess.check_output(['git', '-C', str(pdk), 'ls-tree', '-r', '--name-only',
        REVISION, va_prefix], text=True, timeout=10).splitlines()
    va = out / 'original-psp103'
    va.mkdir()
    for name in names:
        (va / Path(name).name).write_bytes(take(name))
    require(len(names) == 17 and len(seen) == 10, 'original process closure differs')
    original_std = take('ihp-sg13g2/libs.ref/sg13g2_stdcell/spice/sg13g2_stdcell.spice')
    (out / 'original-stdcells.spice').write_bytes(original_std)
    inverter = re.search(rb'(?im)^\.subckt sg13g2_inv_1 Y A VDD VSS\n.*?^\.ends\s*\n', original_std, re.S)
    require(inverter is not None, 'original inverter missing')
    (out / 'inverter-load.cir').write_bytes(inverter[0])
    (out / 'PDK-LICENSE').write_bytes(take('LICENSE'))
    require(manifest == capsule['original_files'], 'model capsule does not bind exact original closure')
    for name in ('qs', 'nqs'):
        model = capsule['models'][name]
        producer = Path(model['producer_receipt'])
        require(sha(producer) == model['producer_receipt_sha256'], 'model producer receipt changed')
        record = json.loads(producer.read_text())
        component = record['compiled_original_model']
        require(component['sha256'] == model['sha256'] and
                Path(component['path']) == Path(model['path']), 'model component identity differs')
        require(sha(model['path']) == model['sha256'], 'compiled model bytes differ')
        # The surrounding producer may have failed its later circuit test.
        # Only its completed original-model compilation component is reused.
        log = Path(model['compile_log'])
        require(sha(log) == model['compile_log_sha256'], 'original compilation log differs')
        text = log.read_text()
        require('Finished building psp103' in text and not re.search(r'(?im)^\s*(error|fatal)\b', text),
                'original model compilation did not complete')
        shutil.copyfile(model['path'], out / ('psp-' + name + '.osdi'))
    return manifest


def check_wave(rows, supply, clock_disabled=False):
    counts = {'direct_positive': 0, 'direct_negative': 0,
              'preamp_positive': 0, 'preamp_negative': 0, 'reset': 0}
    failures = []
    for row in rows:
        t, clock, mic, ip, inn, op, on, dp, dn, current = row[:10]
        phase = (t - 100e-9) % 100e-9
        checks = []
        if 20e-9 < phase < 40e-9 and clock > .9 * supply:
            if .2e-6 < t < .9e-6:
                counts['direct_positive'] += 1
                checks.append(('direct_positive', dp > .9*supply and dn < .1*supply))
            if 1.2e-6 < t < 1.9e-6:
                counts['direct_negative'] += 1
                checks.append(('direct_negative', dn > .9*supply and dp < .1*supply))
            if .65e-6 < t < .8e-6:
                counts['preamp_positive'] += 1
                checks.append(('preamp_positive', ip-inn > .001 and op > .9*supply and on < .1*supply))
            if 1.65e-6 < t < 1.9e-6:
                counts['preamp_negative'] += 1
                checks.append(('preamp_negative', inn-ip > .001 and on > .9*supply and op < .1*supply))
        if (70e-9 < phase < 90e-9 and clock < .1*supply) or clock_disabled:
            counts['reset'] += 1
            checks.append(('reset', max(op, on, dp, dn) < .1*supply))
        for name, okay in checks:
            if not okay and len(failures) < 8:
                failures.append({'check': name, 'time': t, 'values': row[:10]})
    if clock_disabled:
        require(counts['reset'] == len(rows), 'clock-off reset not checked throughout')
    else:
        for name, count in counts.items():
            if count < 20:
                failures.append({'check': name, 'error': 'missing settled observations', 'count': count})
    return counts, failures


def validate_waveform(rows):
    require(len(rows) >= 20000 and all(len(row) == 10 and math.isfinite(v)
        for row in rows for v in row), 'raw transient incomplete/nonfinite')
    require(abs(rows[0][0]) < 1e-15 and abs(rows[-1][0]-2e-6) < 1e-12,
            'raw transient did not reach the declared start/end')
    require(all(0 <= b[0]-a[0] <= 101e-12 for a, b in zip(rows, rows[1:])),
            'raw transient has a gap larger than the declared100ps maximum')


def reverse_buffer_inputs(design):
    lines = design.splitlines(keepends=True)
    selected = {}
    for index, line in enumerate(lines):
        match = re.fullmatch(r'(Xload[ pn]+ decision[ pn]+ )([^ ]+)( vdd vss sg13g2_inv_1\n?)', line)
        if match:
            selected[match[1].split()[0]] = (index, match)
    require(set(selected) == {'Xloadp', 'Xloadn'}, 'two original output buffers required')
    left, right = selected['Xloadp'], selected['Xloadn']
    require({left[1][2], right[1][2]} == {'outp', 'outn'}, 'distinct original buffer inputs required')
    lines[left[0]] = left[1][1]+right[1][2]+left[1][3]
    lines[right[0]] = right[1][1]+left[1][2]+right[1][3]
    return ''.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdk', type=Path, required=True)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--model-capsule', type=Path, required=True,
        help='Explicit source-bound original QS/NQS component compilation receipts; no implicit cache adoption')
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, help='Explicit unselected circuit under ignored build/; never selected by this command')
    args = parser.parse_args()
    out = args.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    started, deadline = time.monotonic(), time.monotonic()+180
    ngspice = args.ngspice.resolve()
    selected = ROOT / 'engineering/multimodal/clocked-comparator-sg13g2.cir'
    circuit = args.candidate.resolve() if args.candidate else selected
    if args.candidate:
        require(circuit.is_relative_to(ROOT/'build') and circuit.is_file() and circuit.stat().st_size <= 65536, 'candidate must be a bounded ignored build source')
    preamp = ROOT / 'engineering/multimodal/microphone-preamp-sg13g2.cir'
    capsule = json.loads(args.model_capsule.read_text())
    report = {'schema': 'lemma-process-clocked-comparator/1', 'status': 'FAIL',
        'scope': __doc__, 'process_revision': REVISION, 'candidate_only': args.candidate is not None,
        'selected_design': {'path': str(selected), 'sha256': sha(selected)},
        'bounds': {'whole_seconds': 180, 'each_seconds': 8, 'AS_bytes': 1 << 30,
                   'output_bytes': 512 << 20}, 'source_inputs': {
            str(p): sha(p) for p in [Path(__file__).resolve(), circuit, preamp, args.model_capsule.resolve(), ngspice]},
        'fresh': 'Actual SPICE operating runs only. Original QS/NQS compilation explicitly reused.',
        'cases': [], 'remaining': ['ADC/sample-hold/reference/SAR control binding and resolution/noise',
            'joint MOS/HBT process-corner correlation and mismatch', 'layout/DRC/LVS/PEX and power/pads',
            'microphone transducer/packaging and physical/safety qualification']}
    try:
        available = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines()
                             if x.startswith('MemAvailable:')))
        report['resource_preflight'] = {'available_kB': available,
            'free_bytes': shutil.disk_usage(out).free, 'free_inodes': os.statvfs(out).f_favail}
        require(available >= 6*1024*1024 and shutil.disk_usage(out).free > 2 << 30, 'resource floor')
        report['original_models'] = bind_originals(args.pdk.resolve(), out, capsule)
        report['model_components'] = capsule['models']
        report['rights'] = capsule['rights']
        report['adopted_inputs'] = {str(p): sha(p) for p in [*list((out/'models').iterdir()),
            out/'psp-qs.osdi', out/'psp-nqs.osdi', out/'inverter-load.cir']}
        (out/'plan.json').write_text(json.dumps(report, indent=2)+'\n')
        design = circuit.read_text()
        cases = [(f'{corner}-{temp}-{v}', corner, temp, v, 10, '')
            for corner in ('mos_tt', 'mos_ss', 'mos_ff') for temp in (-20, 27, 85) for v in (1.1, 1.2, 1.3)]
        cases += [('wrong-wire-negative', 'mos_tt', 27, 1.2, 10, 'wrong-wire'),
                  ('clock-disabled', 'mos_tt', 27, 1.2, 10, 'clock-disabled'),
                  ('100fF-load', 'mos_tt', 27, 1.2, 100, '')]
        for name, corner, temp, supply, load, control in cases:
            require(time.monotonic() < deadline, 'whole prospective budget')
            directory = out/name
            directory.mkdir()
            shutil.copytree(out/'models', directory/'models')
            for original, target in [(preamp, 'preamp.cir'), (out/'inverter-load.cir', 'inverter-load.cir')]:
                shutil.copyfile(original, directory/target)
            used = design
            if control == 'wrong-wire':
                used = reverse_buffer_inputs(used)
                require(used != design, 'wiring negative did not change source')
            (directory/'comparator.cir').write_text(used)
            cm = .935*supply/1.2
            clock = '0' if control == 'clock-disabled' else f'PULSE(0 {supply} 100n 500p 500p 49n 100n)'
            (directory/'stimulus.cir').write_text(f'''Actual process comparator {name}
.lib models/cornerMOSlv.lib {corner}
.lib models/cornerHBT.lib hbt_typ
.include inverter-load.cir
.include comparator.cir
.include preamp.cir
.temp {temp}
Vdd vdd 0 {supply}
Vclock clock 0 {clock}
Vin microphone 0 PWL(0 0 100n 0 101n 2m 850n 2m 851n -2m 2u -2m)
Xpreamp microphone vdd preamp_p preamp_n 0 lemma_mic_preamp
Xdecision preamp_p preamp_n clock vdd decisionp decisionn 0 lemma_clocked_comparator
Vdirectp directinputp 0 PWL(0 {cm+.001} 599n {cm+.001} 600n {cm+.005} 999n {cm+.005} 1000n {cm-.001} 1399n {cm-.001} 1400n {cm-.005} 2u {cm-.005})
Vdirectn directinputn 0 PWL(0 {cm-.001} 599n {cm-.001} 600n {cm-.005} 999n {cm-.005} 1000n {cm+.001} 1399n {cm+.001} 1400n {cm+.005} 2u {cm+.005})
Xdirect directinputp directinputn clock vdd directp directn 0 lemma_clocked_comparator
Cnextp decisionp 0 {load}f
Cnextn decisionn 0 {load}f
Cdirectp directp 0 {load}f
Cdirectn directn 0 {load}f
.end
''')
            (directory/'loader.cir').write_text(f'''Original models, strict process comparator run
.control
set noaskquit
set num_threads=1
set wr_vecnames
set wr_singlescale
pre_osdi {out/'psp-qs.osdi'}
pre_osdi {out/'psp-nqs.osdi'}
source stimulus.cir
tran 100p 2u 0 100p
wrdata waveform.dat v(clock) v(microphone) v(preamp_p) v(preamp_n) v(decisionp) v(decisionn) v(directp) v(directn) i(Vdd)
quit
.endc
.end
''')
            case = {'name': name, 'MOS_corner': corner, 'HBT_corner': 'hbt_typ', 'supply_V': supply,
                'temperature_C': temp, 'load_fF': load, 'control': control, 'status': 'FAIL',
                'inputs': {p.name: sha(p) for p in [directory/'loader.cir', directory/'stimulus.cir', directory/'comparator.cir']}}
            try:
                log, elapsed = invoke([ngspice, '-b', 'loader.cir'], directory, directory/'ngspice.log', deadline, 8)
                case['seconds'] = elapsed
                require(not re.search(r'(?im)^\s*(warning|error|fatal)\b|timestep too small|doAnalyses:.*failed', log), 'simulator warned/failed')
                rows = [[float(v) for v in line.split()] for line in (directory/'waveform.dat').read_text().splitlines()[1:]]
                validate_waveform(rows)
                counts, failures = check_wave(rows, supply, control == 'clock-disabled')
                case.update(rows=len(rows), observations=counts, failures=failures,
                    raw_sha256=sha(directory/'waveform.dat'), peak_supply_current_A=max(abs(row[9]) for row in rows))
                if control == 'wrong-wire':
                    require(any(x['check'].startswith(('direct_', 'preamp_')) for x in failures), 'wrong-wire mutant survived')
                    case['status'] = 'PASS_REJECTED_ACTUAL_ORIGINAL_WRONG_WIRING'
                else:
                    require(not failures, 'actual decision/reset operating limit')
                    case['status'] = 'PASS_ACTUAL_PROCESS_OPERATION'
            except Exception as error:
                case['error'] = repr(error)
            report['cases'].append(case)
            (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
            require(sum(p.stat().st_size for p in out.rglob('*') if p.is_file()) <= 512 << 20, 'output budget')
        require(len(report['cases']) == 30, 'incomplete matrix')
        require(all(x['status'].startswith('PASS_') for x in report['cases']), 'one or more actual operating limits')
        require(all(sha(p) == value for p, value in report['source_inputs'].items()), 'source drift')
        require(all(sha(p) == value for p, value in report['adopted_inputs'].items()), 'adopted model drift')
        report['status'] = ('PASS_PRIVATE' if args.candidate else 'PASS_SIMULATED') + '_PROCESS_COMPARATOR_PREAMP_MATRIX_AND_NEGATIVES'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        report['source_seal_equal'] = all(sha(p) == value for p, value in report['source_inputs'].items())
        report['seconds'] = time.monotonic()-started
        (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
        print(report['status'], report.get('error'), report['seconds'])
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
