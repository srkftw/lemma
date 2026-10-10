#!/usr/bin/env python3
"""Observe the actual compiled notebook through modeled hardware.

Run inside the pinned nix develop environment. Each candidate, build, input,
disk and result has an explicit identity. A partial lane is a scoped observation,
never the complete Task004 acceptance. Retained results are never overwritten.
"""
from __future__ import annotations
import argparse
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DEADLINE = None

def remaining(limit):
    if DEADLINE is None:
        return limit
    available = DEADLINE - time.monotonic()
    if available <= 0:
        raise ValueError("Campaign deadline expired; unfinished work is a failure")
    return min(limit, available)
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from notebook_input import generate
from check_notebook_workflow import check, check_cold
from inspect_notebook import inspect

loader = importlib.machinery.SourceFileLoader('lemmasim_command', str(ROOT / 'scripts/lemmasim'))
spec = importlib.util.spec_from_loader(loader.name, loader)
sim = importlib.util.module_from_spec(spec)
loader.exec_module(sim)
original_launch = sim.launch

def bounded_launch(*args, **kwargs):
    kwargs["timeout"] = remaining(kwargs.get("timeout") or 3600)
    return original_launch(*args, **kwargs)

sim.launch = bounded_launch

def source():
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True, timeout=30).strip()
    if git('status', '--porcelain=v1', '--untracked-files=all'):
        raise ValueError('Acceptance requires clean committed source, including the checker.')
    return {'commit': git('rev-parse', 'HEAD'), 'tree': git('rev-parse', 'HEAD^{tree}'), 'clean': True}

def command(argv, log, timeout):
    with log.open('xb') as stream:
        process = subprocess.Popen(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            code = process.wait(timeout=remaining(timeout))
            if code:
                raise ValueError(f'{argv[0]} failed with status {code}; retained {log}')
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)

def require_pass(path):
    value = json.loads(path.read_text())
    if value.get('status') != 'PASS':
        raise ValueError(f'Missing successful observation: {path}')
    return value

def image(configuration, optimization, out):
    destination = out / f'{configuration}-{optimization}'
    command(['python3', 'scripts/build_kernel.py', '--configuration', configuration,
             '--stage', 'supervisor', '--opt-level', optimization, '--output-dir', str(destination),
             '--timeout', '300'], out / f'{configuration}-{optimization}-build.log', 1200)
    command(['python3', 'scripts/audit_kernel.py', str(destination)],
            out / f'{configuration}-{optimization}-audit.log', 300)
    require_pass(destination / 'audit.json')
    if configuration == 'lemmasim-notebook':
        command(['python3', 'scripts/audit_lemmasim_capacity.py', '--build', str(destination),
                 '--output', str(destination / 'capacity.json')],
                out / f'{configuration}-{optimization}-capacity.log', 120)
        require_pass(destination / 'capacity.json')
    return {'path': str(destination / 'image.elf'), 'sha256': sim.sha(destination / 'image.elf'),
            'build_sha256': sim.sha(destination / 'build.json'), 'audit_sha256': sim.sha(destination / 'audit.json')}

def workflow(metadata, initial, name, geometry, out, timeout):
    directory = out / name
    directory.mkdir()
    width, height = map(int, geometry.split('x'))
    raw, manifest = generate(name, width, height, 200000000, 100000, 200000000)
    input_file, manifest_file = directory / 'input.bin', directory / 'input.json'
    input_file.write_bytes(raw)
    sim.write_json(manifest_file, manifest)
    disk = directory / 'disk.raw'
    shutil.copyfile(initial, disk)
    result = sim.launch(metadata, disk, directory / 'run', headless=True, geometry=geometry,
                        raw=input_file, timeout=timeout, until_ingress=manifest['input_samples'], mode='laboratory')
    if result['status'] != 'OBSERVED_GUEST_WORKFLOW_BOUNDARY' or not result['process_reaped']:
        raise ValueError(f'{name} did not reach a quiescent guest Saved boundary')
    observed = check(disk, input_file, manifest_file, directory / 'run/devices.jsonl',
                     directory / 'run/serial.bin', directory / 'run/visible.ppm')
    sim.write_json(directory / 'workflow.json', observed)
    if observed['status'] != 'PASS':
        raise ValueError(f'{name} independent workflow rejected')
    inspect(disk, directory / 'committed')
    # A real new process boots the same executable with no retained panel state.
    cold = directory / 'cold.raw'
    shutil.copyfile(disk, cold)
    reopened = sim.launch(metadata, cold, directory / 'cold-run', headless=True, geometry=geometry,
                          timeout=180, until_ready=True, mode='laboratory')
    if reopened['status'] != 'OBSERVED_GUEST_WORKFLOW_BOUNDARY' or not reopened['process_reaped']:
        raise ValueError(f'{name} cold process did not redraw its recovered document')
    observed_cold = check_cold(disk, cold, directory / 'run/visible.ppm',
                              directory / 'cold-run/visible.ppm', directory / 'cold-run/serial.bin',
                              directory / 'cold-run/devices.jsonl')
    sim.write_json(directory / 'cold.json', observed_cold)
    if observed_cold['status'] != 'PASS':
        raise ValueError(f'{name} independent cold comparison rejected')
    return {'workflow': name, 'geometry': [width, height], 'guest_sha256': metadata['notebook']['sha256'],
            'observation': str(directory / 'workflow.json'), 'sha256': sim.sha(directory / 'workflow.json'),
            'cold_observation': str(directory / 'cold.json'), 'cold_sha256': sim.sha(directory / 'cold.json')}

def notebook_replay(metadata, initial, out):
    directory = out / 'notebook-replay'
    directory.mkdir()
    disk = directory / 'record.raw'
    shutil.copyfile(initial, disk)
    raw, manifest = generate('basic', 1650, 2200, 200000000, 100000, 200000000)
    input_file = directory / 'input.bin'
    input_file.write_bytes(raw)
    sim.write_json(directory / 'input.json', manifest)
    # Use the maintained user capture/replay operations, including immutable
    # initial-media and backend identity checks and exact icount closing policy.
    original_prepared = sim.PREPARED
    sim.PREPARED = directory / 'prepared.json'
    sim.write_json(sim.PREPARED, metadata)
    try:
        sim.run(argparse.Namespace(disk=disk, mode='developer', fault=None,
                 record=directory / 'session', raw_input=input_file,
                 geometry='1650x2200', headless=True, timeout=180))
        run = directory / 'session/run'
        observed = check(disk, input_file, directory / 'input.json', run / 'devices.jsonl',
                         run / 'serial.bin', run / 'visible.ppm')
        sim.write_json(directory / 'workflow.json', observed)
        if observed['status'] != 'PASS':
            raise ValueError('Recording did not contain the substantive notebook workflow')
        replay_disk = directory / 'replay.raw'
        sim.replay(argparse.Namespace(session=directory / 'session', disk_copy=replay_disk, timeout=240))
    finally:
        sim.PREPARED = original_prepared
    return {'session': str(directory / 'session'), 'workflow_sha256': sim.sha(directory / 'workflow.json'),
            'record_media_sha256': sim.sha(disk), 'replay_media_sha256': sim.sha(replay_disk)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clean', action='store_true', required=True,
                        help='require new output paths; never deletes retained evidence')
    parser.add_argument('--work-dir', type=Path, default=ROOT / f'build/lemmasim/acceptance-{time.time_ns()}')
    parser.add_argument('--qemu', type=Path, help='prepared separately identified LemmaSim QEMU; default uses scripts/lemmasim build result')
    parser.add_argument('--lane', choices=('full', 'writing'), default='full')
    parser.add_argument('--deadline', type=int, default=14400)
    args = parser.parse_args()
    if not 60 <= args.deadline <= 43200:
        parser.error('deadline must be60..43200seconds')
    global DEADLINE
    DEADLINE = time.monotonic() + args.deadline
    out = args.work_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'schema_version': 1, 'status': 'FAIL', 'scope': 'actual guest/device notebook observations',
              'lane': args.lane, 'task004_complete': False, 'cases': [],
              'physical_conformance': 'UNVERIFIED', 'interactive_manual_test': 'NOT_RUN'}
    try:
        before = source()
        result['source'] = before
        if args.qemu is None:
            args.qemu = Path(sim.prepared()['qemu']['path'])
        if not args.qemu.is_file():
            raise ValueError('Missing prepared LemmaSim QEMU')
        qemu = args.qemu.resolve()
        result['qemu_sha256'] = sim.sha(qemu)
        command(['python3', '-m', 'unittest', 'discover', '-s', 'tests/lemmasim', '-v'], out / 'host-tests.log', 180)
        command(['python3', 'sim/host/check_qemu_devices.py', '--qemu', str(qemu), '--output', str(out / 'devices')], out / 'devices.log', 180)
        require_pass(out / 'devices/result.json')
        command(['python3', 'sim/host/check_qemu_medium.py', '--qemu', str(qemu), '--output', str(out / 'medium')], out / 'medium.log', 180)
        require_pass(out / 'medium/result.json')
        metadata = {'schema_version': 1, 'commit': before['commit'], 'core': 'lemma-one-core/0.1.0',
                    'profile': 'lemmasim-virt/0.1.0', 'qemu': {'path': str(qemu), 'sha256': sim.sha(qemu)}}
        metadata['notebook'] = image('lemmasim-notebook', 'O2', out)
        metadata['initializer'] = image('lemmasim-initialize', 'O2', out)
        sim.write_json(out / 'prepared.json', metadata)
        initial = out / 'initial.raw'
        with initial.open('xb') as stream:
            stream.truncate(256 * 1024 * 1024)
        initialized = sim.launch(metadata, initial, out / 'initialization', headless=True, initializer=True, timeout=120)
        if initialized['status'] != 'INITIALIZED' or not initialized['process_reaped']:
            raise ValueError('Missing real guest durable initialization acknowledgement')
        result['initial_media_sha256'] = sim.sha(initial)
        result['cases'].append(workflow(metadata, initial, 'basic', '1650x2200', out, 180))
        if args.lane == 'full':
            o0 = dict(metadata, notebook=image('lemmasim-notebook', 'O0', out))
            o0_out = out / 'O0'
            o0_out.mkdir()
            result['cases'].append(workflow(o0, initial, 'basic', '1650x2200', o0_out, 300))
            result['cases'].append(workflow(metadata, initial, 'editing', '1650x2200', out, 600))
            second = out / 'second-geometry'
            second.mkdir()
            result['cases'].append(workflow(metadata, initial, 'basic', '1404x1872', second, 180))
            for loss in ('loss-overflow', 'loss-disconnect', 'loss-watchdog'):
                result['cases'].append(workflow(metadata, initial, loss, '1650x2200', out, 300))
            result['replay'] = notebook_replay(metadata, initial, out)
            from check_lemmasim_faults import campaign
            baseline = out / 'basic'
            result['faults'] = campaign(metadata, qemu, baseline / 'disk.raw', baseline / 'committed',
                                        baseline / 'run/serial.bin', out / 'faults')
            if result['faults'].get('status') != 'PASS':
                raise ValueError('Notebook hardware fault campaign failed')
            result['cases'].append(workflow(metadata, initial, 'workload', '1650x2200', out, 3000))
        if source() != before or sim.sha(qemu) != result['qemu_sha256']:
            raise ValueError('Source/backend changed during campaign')
        result['status'] = 'PASS'
        result['remaining_task_acceptance'] = ['inherited required CI/regressions',
                                              'new device/namespace/faulting-client isolation',
                                              'compiled early-acknowledgement source negative',
                                              'manual native frontend observation and draft publication']
    except BaseException as error:
        result['error'] = str(error)
    finally:
        sim.write_json(out / 'result.json', result)
    print(json.dumps({key: result[key] for key in ('status', 'lane', 'task004_complete', 'error') if key in result}))
    return 0 if result['status'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
