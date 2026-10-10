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
from notebook_input import generate, Input
from check_notebook_workflow import check, check_cold
from inspect_notebook import inspect
from check_readonly_media import check as check_readonly
from check_notebook_isolation import check as check_isolation

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
    destination = ROOT / 'build/kernel' / f'{out.name}-{configuration}-{optimization}'
    command(['python3', 'scripts/build_kernel.py', '--configuration', configuration,
             '--stage', 'supervisor', '--opt-level', optimization, '--output-dir', str(destination),
             '--timeout', '300'], out / f'{configuration}-{optimization}-build.log', 1200)
    command(['python3', 'scripts/audit_kernel.py', str(destination)],
            out / f'{configuration}-{optimization}-audit.log', 300)
    require_pass(destination / 'audit.json')
    if configuration in ('lemmasim-notebook', 'lemmasim-isolation-development'):
        command(['python3', 'scripts/audit_lemmasim_capacity.py', '--build', str(destination),
                 '--output', str(destination / 'capacity.json')],
                out / f'{configuration}-{optimization}-capacity.log', 120)
        require_pass(destination / 'capacity.json')
    return {'path': str(destination / 'image.elf'), 'sha256': sim.sha(destination / 'image.elf'),
            'build_sha256': sim.sha(destination / 'build.json'), 'audit_sha256': sim.sha(destination / 'audit.json'),
            'artifacts': sim.guest_artifact_identity(destination / 'image.elf',
                require_capacity=configuration in ('lemmasim-notebook', 'lemmasim-isolation-development'))}

def workflow(metadata, initial, name, geometry, out, timeout, *, observe_owned_memory=False):
    directory = out / name
    directory.mkdir()
    width, height = map(int, geometry.split('x'))
    raw, manifest = generate(name, width, height, 200000000, 100000, 200000000)
    input_file, manifest_file = directory / 'input.bin', directory / 'input.json'
    input_file.write_bytes(raw)
    sim.write_json(manifest_file, manifest)
    disk = directory / 'disk.raw'
    shutil.copyfile(initial, disk)
    memory = None
    if observe_owned_memory:
        from check_owned_memory import Observation
        memory = Observation(sim, directory / 'run', directory / 'owned-memory', metadata)
        with memory:
            result = sim.launch(metadata, disk, directory / 'run', headless=True, geometry=geometry,
                                raw=input_file, timeout=timeout, until_ingress=manifest['input_samples'], mode='laboratory')
        memory.require_observed()
    else:
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
    view = manifest['expected']['final_view']
    navigation = None
    navigation_count = None
    if (view['namespace'], view['page']) != (1, 1):
        # Normal cold boot opens page1. Navigate through the genuine toolbar;
        # no host-selected page command or application-memory change is used.
        stream = Input(width, height, 1000000000, 100000, 600000000)
        stream.sample(width // 2, 160, 0, False)
        if view['namespace'] == 2:
            stream.tool(0, 'open notebook2')
        for page in range(2, view['page'] + 1):
            stream.tool(2, f'open recovered page{page}')
        import struct
        navigation = directory / 'cold-navigation.bin'
        navigation.write_bytes(b''.join(struct.pack('<9Q', *event) for event in stream.events))
        navigation_count = len(stream.events)
        sim.write_json(directory / 'cold-navigation.json', {'schema_version': 1,
                       'clock_hz': 10000000, 'actions': stream.actions,
                       'input_samples': navigation_count, 'input_sha256': sim.sha(navigation),
                       'expected_view': view, 'policy': 'absolute raw FIFO timestamps; no host sleeps or page commands'})
    reopened = sim.launch(metadata, cold, directory / 'cold-run', headless=True, geometry=geometry,
                          raw=navigation, timeout=180 if navigation is None else 3000,
                          until_ready=navigation is None, until_ingress=navigation_count,
                          until_view=None if navigation is None else (view['namespace'], view['page']),
                          mode='laboratory')
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
            'cold_observation': str(directory / 'cold.json'), 'cold_sha256': sim.sha(directory / 'cold.json'),
            **({'owned_memory_observation': str(directory / 'owned-memory/result.json'),
                'owned_memory_sha256': sim.sha(directory / 'owned-memory/result.json')} if memory else {})}

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

def readonly_media(metadata, baseline, out):
    observations = []
    for name in ('unknown-nonempty', 'damaged-roots'):
        directory = out / name
        directory.mkdir()
        disk = directory / 'disk.raw'
        if name == 'unknown-nonempty':
            with disk.open('xb') as stream:
                stream.truncate(16 * 1024 * 1024)
                stream.seek(0)
                stream.write(b'UNKNOWN NONEMPTY MEDIUM: DO NOT FORMAT')
        else:
            shutil.copyfile(baseline, disk)
            # Damage both independent publication identities. Keep the rest of
            # this actual acknowledged notebook intact for refusal observation.
            with disk.open('r+b') as stream:
                for offset in (0, 512):
                    stream.seek(offset)
                    stream.write(bytes(8))
        initial_hash = sim.sha(disk)
        result = sim.launch(metadata, disk, directory / 'run', headless=True,
                            timeout=180, until_ready=True, mode='laboratory')
        if result['status'] != 'OBSERVED_GUEST_WORKFLOW_BOUNDARY' or not result['process_reaped']:
            raise ValueError('failed mount did not reach a bounded guest read-only display')
        observation = check_readonly(disk, initial_hash, directory / 'run/serial.bin',
                                      directory / 'run/devices.jsonl', directory / 'run/media.jsonl',
                                      directory / 'run/visible.ppm')
        sim.write_json(directory / 'observation.json', observation)
        observations.append({'case': name, 'observation': str(directory / 'observation.json'),
                             'sha256': sim.sha(directory / 'observation.json')})
    return observations

def isolation(metadata, baseline, out):
    directory = out / 'isolation'
    directory.mkdir()
    selected = dict(metadata, notebook=image('lemmasim-isolation-development', 'O2', out))
    # The additional faulting User client must use the exact same production
    # notebook/store objects; the kernel only changes the declared deployment.
    ordinary = Path(metadata['notebook']['path']).parent
    probed = Path(selected['notebook']['path']).parent
    for role in ('store', 'notebook'):
        if sim.sha(ordinary / f'users/{role}/program.o') != sim.sha(probed / f'users/{role}/program.o'):
            raise ValueError('isolation deployment changed the ordinary application/service object')
    raw, manifest = generate('basic', 1650, 2200, 200000000, 100000, 200000000)
    input_file = directory / 'input.bin'
    input_file.write_bytes(raw)
    sim.write_json(directory / 'input.json', manifest)
    before_hash = sim.sha(baseline)
    disk = directory / 'disk.raw'
    shutil.copyfile(baseline, disk)
    faults = {'delay-after-ns': 40000000000, 'delay-write-ns': 3000000000}
    sim.write_json(directory / 'identity.json', dict(selected, fault_inputs=faults,
                                                   baseline_media_sha256=before_hash))
    run = directory / 'run'
    result = sim.launch(selected, disk, run, headless=True, raw=input_file, timeout=300,
                        until_ingress=manifest['input_samples'], faults=faults, mode='laboratory')
    if result['status'] != 'OBSERVED_GUEST_WORKFLOW_BOUNDARY' or not result['process_reaped']:
        raise ValueError('faulting-client deployment did not continue to genuine Saved ink')
    observed = check_isolation(baseline, disk, run / 'serial.bin', run / 'devices.jsonl',
                               run / 'media.jsonl', run / 'visible.ppm', input_file, directory / 'input.json')
    sim.write_json(directory / 'observation.json', observed)
    if observed['status'] != 'PASS' or sim.sha(baseline) != before_hash:
        raise ValueError('isolation observation rejected or changed the original baseline')
    return {'observation': str(directory / 'observation.json'),
            'sha256': sim.sha(directory / 'observation.json'), 'guest_sha256': selected['notebook']['sha256'],
            'production_user_objects_identical': True}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clean', action='store_true', required=True,
                        help='require new output paths; never deletes retained evidence')
    parser.add_argument('--work-dir', type=Path, default=ROOT / f'build/lemmasim/acceptance-{time.time_ns()}')
    parser.add_argument('--qemu', type=Path, help='prepared separately identified LemmaSim QEMU; default uses scripts/lemmasim build result')
    parser.add_argument('--lane', choices=('full', 'writing'), default='full')
    parser.add_argument('--with-o0', action='store_true', help='also compile/audit and cold-reopen the O0 notebook in the writing lane')
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
              'with_o0': args.with_o0 or args.lane == 'full',
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
        closure = sim.backend_identity(qemu, timeout=remaining(60))
        result['qemu_closure'] = closure
        command(['python3', '-m', 'unittest', 'discover', '-s', 'tests/lemmasim', '-v'], out / 'host-tests.log', 180)
        # The kernel and user notebook are separately linked modules. Build the
        # complete fixture import roots explicitly before invoking lean; a warm
        # project cache must not supply otherwise missing user/compiler objects.
        command(['lake', 'build', 'Lemma.Platform.LemmaSim.NotebookKernel',
                 'Lemma.Applications.Notebook', 'Lemma.Compiler.CFGLower'],
                out / 'lean-host-build.log', 1200)
        command(['lake', 'env', 'lean', 'tests/kernel/BulkCopyAndDeadline.lean'],
                out / 'BulkCopyAndDeadline.log', 180)
        command(['lake', 'env', 'python3', 'conformance/lemmasim/check_store_cache.py',
                 '--output', str(out / 'store-cache')], out / 'store-cache.log', 300)
        require_pass(out / 'store-cache/result.json')
        for fixture in ('NotebookReads', 'NotebookGlyphs', 'NotebookCapacity', 'NotebookInputDrain', 'SurfaceStatus',
                        'PaperRecovery', 'RasterizerReference', 'PacketCopies', 'InkHeaders'):
            command(['lake', 'env', 'lean', f'tests/ink/{fixture}.lean'],
                    out / f'{fixture}.log', 180)
        command(['python3', 'sim/host/check_qemu_devices.py', '--qemu', str(qemu), '--output', str(out / 'devices')], out / 'devices.log', 180)
        require_pass(out / 'devices/result.json')
        command(['python3', 'sim/host/check_qemu_medium.py', '--qemu', str(qemu), '--output', str(out / 'medium')], out / 'medium.log', 180)
        require_pass(out / 'medium/result.json')
        metadata = {'schema_version': 1, 'commit': before['commit'], 'core': 'lemma-one-core/0.1.0',
                    'source_tree': before['tree'], 'profile': 'lemmasim-virt/0.1.0',
                    'profile_sha256': sim.sha(ROOT / 'sim/profiles/lemmasim-virt-0.1.0.json'),
                    'qemu_closure': closure, 'qemu': closure['binary'],
                    **{key: closure[key] for key in ('backend_sources', 'qemu_recipe_sha256',
                                                     'qemu_patch_sha256', 'flake_lock_sha256')}}
        sim.validate_backend_identity(metadata)
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
        if args.lane == 'full' or args.with_o0:
            o0 = dict(metadata, notebook=image('lemmasim-notebook', 'O0', out))
            o0_out = out / 'O0'
            o0_out.mkdir()
            result['cases'].append(workflow(o0, initial, 'basic', '1650x2200', o0_out, 300))
        if args.lane == 'full':
            result['cases'].append(workflow(metadata, initial, 'editing', '1650x2200', out, 600))
            result['isolation'] = isolation(metadata, out / 'editing/disk.raw', out)
            result['readonly_media'] = readonly_media(metadata, out / 'basic/disk.raw', out)
            second = out / 'second-geometry'
            second.mkdir()
            result['cases'].append(workflow(metadata, initial, 'basic', '1404x1872', second, 180))
            for loss in ('loss-overflow', 'loss-disconnect', 'loss-watchdog'):
                result['cases'].append(workflow(metadata, initial, loss, '1650x2200', out, 300))
            result['replay'] = notebook_replay(metadata, initial, out)
            from check_lemmasim_native import campaign as native_campaign
            result['native_pointer'] = native_campaign(metadata, initial, out / 'native-pointer',
                timeout=120, deadline_callback=remaining,
                gtk=bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')))
            from check_lemmasim_faults import campaign
            baseline = out / 'basic'
            result['faults'] = campaign(metadata, qemu, baseline / 'disk.raw', baseline / 'committed',
                                        baseline / 'run/serial.bin', out / 'faults', remaining=lambda: remaining(14400))
            if result['faults'].get('status') != 'PASS':
                raise ValueError('Notebook hardware fault campaign failed')
            from check_lemmasim_publication_negative import campaign as publication_negative
            result['publication_negative'] = publication_negative(metadata, qemu, baseline / 'disk.raw',
                baseline / 'committed', baseline / 'run/serial.bin', out / 'publication-negative',
                before['commit'], remaining=lambda: remaining(14400))
            if result['publication_negative'].get('status') != 'PASS':
                raise ValueError('Compiled publication-barrier regression was not observed and rejected')
            from check_lemmasim_input_negative import campaign as input_negative
            result['input_negative'] = input_negative(metadata, qemu, initial,
                out / 'input-negative', before['commit'], remaining=lambda: remaining(14400))
            if result['input_negative'].get('status') != 'PASS':
                raise ValueError('Compiled pen-loss regression was not observed and rejected')
            result['cases'].append(workflow(metadata, initial, 'workload', '1650x2200', out, 3000,
                                          observe_owned_memory=True))
        if source() != before or sim.sha(qemu) != result['qemu_sha256']:
            raise ValueError('Source/backend changed during campaign')
        result['status'] = 'PASS'
        result['remaining_task_acceptance'] = ['inherited required CI/regressions',
                                              'draft publication and retained offline evidence']
    except BaseException as error:
        result['error'] = str(error)
    finally:
        sim.write_json(out / 'result.json', result)
    print(json.dumps({key: result[key] for key in ('status', 'lane', 'task004_complete', 'error') if key in result}))
    return 0 if result['status'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
