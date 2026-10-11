#!/usr/bin/env python3
"""Compile a quarantined early-ACK store and observe its real power-loss failure.

The sole mutation removes Engine.complete's final publication flush. It never
enters the trusted checkout. Both images run raw input through actual devices;
read-only inspection follows guest 421, then maintained Laboratory controls
SIGKILL the whole process without stop/quit/cleanup flush. An independent stable
media observer must accept the positive and reject the mutated guest's ACK.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from check_crash_workflow import baseline_export, notebook, raw_provenance, retained_baseline
from check_notebook_workflow import guest_events
from store_oracle import recover

ENGINE = 'Lemma/Services/Store/Engine.lean'
BEFORE = 'if phase = 20 then request context 3 21 0'
AFTER = 'if phase = 20 then acknowledged context'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: dict) -> None:
    if path.exists():
        raise ValueError('refusing to replace retained observation: ' + str(path))
    path.write_text(json.dumps(value, indent=2) + '\n')


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=root, text=True, timeout=30).strip()


def bounded(command: list[str], cwd: Path, log: Path, timeout: float) -> None:
    with log.open('xb') as output:
        process = subprocess.Popen(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            status = process.wait(timeout=timeout)
            if status:
                raise ValueError(f'real command failed with status {status}; retained log {log}')
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def faults_module():
    spec = importlib.util.spec_from_file_location('lemma_publication_fault_helpers', ROOT / 'scripts/check_lemmasim_faults.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stable_ack(disk: Path, acknowledgement: tuple[int, ...]) -> dict:
    """Independent oracle rejection is retained as FAIL, never relabeled PASS."""
    root, sequence, records = recover(disk.read_bytes())
    ack_sequence, page, ns, stroke = acknowledgement
    if not stroke or not page or not ns:
        raise ValueError('regression requires an ordinary completed-stroke ACK')
    failure = None
    if ack_sequence > sequence:
        failure = f'guest ACK {ack_sequence} exceeds stable recovered sequence {sequence}'
    elif (ns, 1) not in records or records[ns, 1].sequence < ack_sequence:
        failure = 'guest stroke ACK precedes stable catalog publication'
    return {'schema_version': 1, 'status': 'FAIL' if failure else 'PASS',
            'scope': 'independent offline ACK versus actual stable record publication',
            'error': failure, 'guest_acknowledgement': list(acknowledgement),
            'recovered_sequence': sequence, 'recovered_generation': root.generation,
            'stable_media_sha256': sha(disk)}


def kill_at_saved(native, metadata: dict, disk: Path, output: Path, raw: Path,
                  *, timeout: float = 120) -> dict:
    result, errors = {}, []
    def launch():
        try:
            result.update(native.launch(metadata, disk, output, headless=True,
                                        raw=raw, timeout=timeout + 10, mode='laboratory'))
        except BaseException as error:
            errors.append(error)
    thread = threading.Thread(target=launch, name='lemma-guest-process-owner')
    thread.start()
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if errors:
                raise errors[0]
            if not thread.is_alive():
                raise ValueError('guest ended before the regression ACK/power-cut boundary')
            serial = output / 'serial.bin'
            if serial.exists():
                events = guest_events(serial) if b'K1 ' in serial.read_bytes() else []
                acks = [row[1:] for row in events if row[0] == 0x421]
                if acks:
                    process = json.loads((output / 'process.json').read_text())
                    socket = Path(process.get('qmp_socket', str(output / 'control.qmp')))
                    storage = json.loads(native.qmp(socket, 'qom-get',
                        {'path': '/machine/lemma-hardware', 'property': 'storage-state'}))
                    state = native.qmp(socket, 'query-status')
                    if not state['running']:
                        raise ValueError('regression boundary unexpectedly stopped; a QEMU stop can flush block nodes')
                    observation = {'schema_version': 1, 'guest_acknowledgement': list(acks[-1]),
                                   'storage': storage, 'qemu_status': state,
                                   'process_identity': process,
                                   'cut': 'maintained Laboratory whole-process SIGKILL while running; no QMP stop/quit/reset/cleanup flush'}
                    write(output.parent / 'cut-observation.json', observation)
                    native.control(SimpleNamespace(run_directory=output, action='power-cut'))
                    thread.join(timeout=10)
                    if thread.is_alive():
                        raise ValueError('launch owner did not reap the power-cut process')
                    if errors:
                        raise errors[0]
                    if result.get('status') != 'MODELED_POWER_CUT' or result.get('returncode') != -signal.SIGKILL or result.get('process_reaped') is not True:
                        raise ValueError('actual whole-process cut was not independently reaped as SIGKILL')
                    return observation
            time.sleep(.01)
        raise ValueError('guest did not report an ordinary stroke ACK before bounded deadline')
    finally:
        if thread.is_alive():
            identity_file = output / 'process.json'
            if identity_file.exists():
                identity = json.loads(identity_file.read_text())
                try:
                    actual = Path(f'/proc/{identity["pid"]}/stat').read_text().rsplit(')', 1)[1].split()[19]
                    if actual == identity.get('linux_start_ticks'):
                        os.killpg(identity['process_group'], signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except FileNotFoundError:
                    pass
            thread.join(timeout=10)
            if thread.is_alive():
                raise ValueError('failed regression could not reap its owned launch process')


def campaign(metadata: dict, qemu: Path | str, baseline_disk: Path | str,
             baseline_export_path: Path | str, baseline_serial: Path | str,
             out: Path | str, candidate_commit: str, *,
             deadline_seconds: float | None = None,
             remaining: Callable[[], float] | None = None) -> dict:
    expires = time.monotonic() + deadline_seconds if deadline_seconds is not None else None
    def bounded_timeout(limit: float) -> float:
        budget = min(limit, expires - time.monotonic()) if expires is not None else limit
        if remaining is not None:
            budget = min(budget, remaining())
        if budget <= 0:
            raise TimeoutError('overall publication regression deadline expired')
        return budget
    output = Path(out).resolve()
    output.mkdir(parents=True, exist_ok=False)
    candidate = git(ROOT, 'rev-parse', candidate_commit + '^{commit}')
    baseline_disk, baseline_export_path, baseline_serial = (Path(path).resolve()
        for path in (baseline_disk, baseline_export_path, baseline_serial))
    source = subprocess.check_output(['git', 'show', candidate + ':' + ENGINE],
                                     cwd=ROOT, text=True, timeout=30)
    positive_image = Path(metadata['notebook']['path']).resolve()
    provenance_file = positive_image.parent / 'provenance.json'
    provenance = json.loads(provenance_file.read_text())
    if provenance['source_commit'] != candidate or provenance['dirty_paths'] or provenance['source_inputs'][ENGINE] != hashlib.sha256(source.encode()).hexdigest():
        raise ValueError('positive must be genuinely built from this clean committed candidate')
    if sha(positive_image) != metadata['notebook']['sha256']:
        raise ValueError('positive guest image identity differs')
    metadata = dict(metadata, qemu=dict(metadata['qemu'], path=str(Path(qemu).resolve())))
    if sha(Path(metadata['qemu']['path'])) != metadata['qemu']['sha256']:
        raise ValueError('host QEMU identity differs')
    baseline, before = baseline_export(baseline_export_path)
    original_hash = sha(baseline_disk)
    if original_hash != baseline['image_sha256'] or not before.chunks:
        raise ValueError('regression needs the exact previously acknowledged ink baseline')
    states = [row for row in guest_events(baseline_serial) if row[0] in (0x421, 0x423, 0x424)]
    if not states or states[-1][:2] != (0x421, baseline['committed_sequence']):
        raise ValueError('baseline has no final genuine guest Saved witness')
    summary = {'schema_version': 1, 'status': 'RUNNING', 'candidate_commit': candidate,
               'scope': 'actual compiled guest publication-barrier regression; negative image unqualified and quarantined',
               'baseline_image_sha256': original_hash, 'positive_guest_sha256': sha(positive_image),
               'qemu_sha256': metadata['qemu']['sha256'], 'cases': []}
    try:
        checkout = output / 'experimental-checkout'
        bounded(['git', 'worktree', 'add', '--detach', str(checkout), candidate], ROOT, output / 'worktree.log', bounded_timeout(60))
        if git(checkout, 'status', '--porcelain'):
            raise ValueError('fresh experimental checkout is not clean')
        engine = checkout / ENGINE
        original = engine.read_text()
        if original.count(BEFORE) != 1:
            raise ValueError('exact reviewed phase20 boundary no longer occurs once')
        engine.write_text(original.replace(BEFORE, AFTER, 1))
        patch = git(checkout, 'diff', '--', ENGINE) + '\n'
        (output / 'negative-source.patch').write_text(patch)
        if git(checkout, 'diff', '--name-only') != ENGINE:
            raise ValueError('negative changed more than its single quarantined source boundary')
        build = checkout / 'build/kernel/publication-negative-O2'
        bounded(['nix', 'develop', '--no-write-lock-file', '--command', 'python3', 'scripts/build_kernel.py',
                 '--configuration', 'lemmasim-notebook', '--stage', 'supervisor', '--opt-level', 'O2',
                 '--output-dir', str(build), '--timeout', '300'], checkout, output / 'negative-build.log', bounded_timeout(1200))
        built = json.loads((build / 'build.json').read_text())
        negative_provenance = json.loads((build / 'provenance.json').read_text())
        if built['status'] != 'BUILT' or negative_provenance['source_commit'] != candidate or negative_provenance['dirty_paths'] != [' M ' + ENGINE]:
            raise ValueError('negative lacks its genuine elaboration/build provenance')
        changed = {path for path, digest in negative_provenance['source_inputs'].items()
                   if provenance['source_inputs'].get(path) != digest}
        if changed != {ENGINE} or set(negative_provenance['source_inputs']) != set(provenance['source_inputs']):
            raise ValueError('negative build inputs differ beyond the one intentional Lean mutation')
        negative_image = build / 'image.elf'
        negative_metadata = dict(metadata, notebook={'path': str(negative_image), 'sha256': sha(negative_image)})
        write(output / 'negative-image.json', {'schema_version': 1, 'qualification': 'UNQUALIFIED_NEGATIVE_ONLY',
              'candidate_source_commit': candidate, 'only_altered_source': ENGINE,
              'source_patch_sha256': sha(output / 'negative-source.patch'),
              'image': str(negative_image), 'image_sha256': sha(negative_image),
              'build_manifest_sha256': sha(build / 'build.json'), 'provenance_sha256': sha(build / 'provenance.json')})
        helpers = faults_module()
        raw, raw_manifest = helpers.raw_fixture(output, 'append')
        native = helpers.load_launch()
        for name, selected in (('positive', metadata), ('negative', negative_metadata)):
            directory = output / name
            directory.mkdir()
            disk = directory / 'disk.raw'
            shutil.copyfile(baseline_disk, disk)
            cut = kill_at_saved(native, selected, disk, directory / 'r', raw, timeout=bounded_timeout(120))
            observation = stable_ack(disk, tuple(cut['guest_acknowledgement']))
            write(directory / 'independent-ack-check.json', observation)
            _, stable_sequence, records = recover(disk.read_bytes())
            after = notebook({key: record.payload for key, record in records.items() if record.kind == 1})
            retained_baseline(before, after)
            _, admitted = raw_provenance(raw, raw_manifest, directory / 'r/devices.jsonl')
            for key, chunk in after.chunks.items():
                if key not in before.chunks and any(admitted.get(sample, (0, 0, ''))[:2] != (key[0], chunk.header[3]) for sample in chunk.samples):
                    raise ValueError(name + ': stored writing is not exact actual raw FIFO input')
            if name == 'positive':
                if observation['status'] != 'PASS' or cut['storage']['pending_sectors']:
                    raise ValueError('positive failed stable ACK preservation / pending-write boundary')
            elif observation['status'] != 'FAIL' or not observation['guest_acknowledgement'][0] > stable_sequence or not cut['storage']['pending_sectors']:
                raise ValueError('negative failed to reproduce and independently reject the real early-ACK behavior')
            summary['cases'].append({'name': name, 'oracle_status': observation['status'],
                                     'guest_ack': cut['guest_acknowledgement'][0],
                                     'stable_sequence': stable_sequence,
                                     'pending_sectors_at_cut': cut['storage']['pending_sectors'],
                                     'stable_media_sha256': sha(disk)})
        if sha(baseline_disk) != original_hash:
            raise ValueError('original acknowledged baseline changed')
        summary.update(status='PASS', meaning='positive retained its ACK; independently rejected negative actual ACK beyond stable recovery',
                       negative_guest_sha256=sha(negative_image), source_patch_sha256=sha(output / 'negative-source.patch'))
    except BaseException as error:
        summary.update(status='FAIL', error=str(error))
        raise
    finally:
        summary['baseline_unchanged'] = sha(baseline_disk) == original_hash
        write(output / 'result.json', summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('metadata', 'qemu', 'baseline-disk', 'baseline-export', 'baseline-serial', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--candidate-commit', required=True)
    args = parser.parse_args()
    try:
        result = campaign(json.loads(args.metadata.read_text()), args.qemu, args.baseline_disk,
                          args.baseline_export, args.baseline_serial, args.output, args.candidate_commit)
    except Exception as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({'status': result['status'], 'cases': result['cases'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
