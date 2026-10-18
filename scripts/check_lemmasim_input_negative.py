#!/usr/bin/env python3
"""Compile one quarantined pen-loss regression and reject its actual writing.

The sole Lean mutation retains Notebook.cancelInput's unsaved raw count. Both
guests consume the maintained disconnect fixture through the real pen device.
The independent notebook observer must accept the positive and reject the
negative's committed cancelled contact. A changed source hash, timeout, missing
input, or failed guest is never a successful negative experiment.
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
import struct
import subprocess
import sys
import time
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from check_notebook_workflow import check, check_cold, device_events
from notebook_input import generate
from store_oracle import recover

NOTEBOOK = 'Lemma/Applications/Notebook.lean'
DECLARATION = 'private def cancelInput : Action :=\n'
BEFORE = '.bind (put 112 0) fun s _ => if statusFailed s = true then .done s 0 else'
AFTER = '.bind (get 112) fun s _ => if statusFailed s = true then .done s 0 else'
REJECTIONS = frozenset((
    'completed stroke has no original pen-up',
    'unfinished stroke or duplicate raw sample beyond the declared continuation boundary',
    'raw chunk joined an unexplained input boundary',
    'unexpected retained stroke or host/application shortcut',
    'cancelled input tail or fabricated connecting line remained on actual visible paper',
))


def mutate_source(source: str) -> str:
    """Fail closed when the reviewed declaration or cancellation changes."""
    if source.count(DECLARATION) != 1:
        raise ValueError('reviewed cancelInput declaration no longer occurs once')
    start = source.index(DECLARATION) + len(DECLARATION)
    end = source.find('\n\n', start)
    if end < 0:
        raise ValueError('reviewed cancelInput declaration has no bounded end')
    body = source[start:end]
    if body.count(BEFORE) != 1 or '.bind (put 104 0)' not in body or 'put 432 1' not in body:
        raise ValueError('reviewed raw-tail cancellation boundary changed')
    return source[:start] + body.replace(BEFORE, AFTER, 1) + source[end:]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: dict) -> None:
    if path.exists():
        raise ValueError('refusing to replace retained input regression evidence: ' + str(path))
    path.write_text(json.dumps(value, indent=2) + '\n')


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=root, text=True, timeout=30).strip()


def bounded(command: list[str], cwd: Path, log: Path, timeout: float) -> None:
    with log.open('xb') as output:
        process = subprocess.Popen(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            status = process.wait(timeout=timeout)
            if status:
                raise ValueError(f'real command failed with status {status}; retained log {log}')
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def helpers_module():
    spec = importlib.util.spec_from_file_location('lemma_input_negative_helpers',
                                                ROOT / 'scripts/check_lemmasim_faults.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cancelled_records(disk: Path, raw: Path, manifest: dict, devices: Path) -> dict:
    """Independent raw-tuple observation, never a guest recovery input.

    Only actual accepted FIFO samples before the disconnect can witness this
    regression. The disconnect marker itself is rejected by the device.
    """
    loss = manifest['expected']['loss']
    payload = raw.read_bytes()
    if len(payload) % 72 or sha(raw) != manifest['input_sha256']:
        raise ValueError('cancelled-contact evidence has changed/truncated input')
    accepted = {a: (b, c) for _, event, a, b, c in device_events(devices) if event == 'pen-input'}
    expected = set()
    for ordinal in range(loss['cancelled_first_sequence'], loss['boundary_first_sequence']):
        if ordinal not in accepted:
            raise ValueError('cancelled-contact raw sample never actually entered the FIFO')
        sample = struct.unpack_from('<9Q', payload, (ordinal - 1) * 72)
        sequence, epoch = accepted[ordinal]
        expected.add((sequence, *sample[1:8], epoch))
    if len(expected) != 8:
        raise ValueError('reviewed disconnect fixture no longer contains eight partial contacts')
    root, sequence, records = recover(disk.read_bytes())
    retained, objects = set(), []
    for (namespace, object_id), record in records.items():
        data = record.payload
        if record.kind != 1 or len(data) < 128:
            continue
        header = struct.unpack_from('<16Q', data)
        if header[:3] != (0x314B4E49414D454C, 1, 3):
            continue
        if not 1 <= header[6] <= 384 or len(data) != 128 + header[6] * 72:
            raise ValueError('negative raw ink envelope is malformed beyond the reviewed regression')
        current = {struct.unpack_from('<9Q', data, 128 + i * 72) for i in range(header[6])}
        overlap = current & expected
        if overlap:
            retained.update(overlap)
            objects.append({'namespace': namespace, 'object_id': object_id, 'stroke_id': header[4],
                            'lifecycle': header[14], 'raw_samples': header[6],
                            'cancelled_raw_samples': len(overlap), 'payload_sha256': hashlib.sha256(data).hexdigest()})
    return {'schema_version': 1, 'scope': 'actual committed tuples from admitted cancelled FIFO contact',
            'committed_sequence': sequence, 'generation': root.generation,
            'expected_cancelled_samples': len(expected), 'retained_cancelled_samples': len(retained),
            'objects': objects, 'stable_media_sha256': sha(disk)}


def require_oracle_rejection(observation: dict, cancelled: dict) -> None:
    """Reject generic failures and require a real, independently stored tail."""
    if observation.get('status') != 'FAIL' or observation.get('error') not in REJECTIONS:
        raise ValueError('negative did not produce the specific independently rejected loss-boundary behavior')
    count = cancelled.get('retained_cancelled_samples')
    if type(count) is not int or not 1 <= count <= 8 or not cancelled.get('objects'):
        raise ValueError('negative did not actually persist an admitted cancelled raw sample')


def campaign(metadata: dict, qemu: Path | str, initial_disk: Path | str,
             out: Path | str, candidate_commit: str, *,
             deadline_seconds: float | None = 1800,
             remaining: Callable[[], float] | None = None) -> dict:
    expires = time.monotonic() + deadline_seconds if deadline_seconds is not None else None
    def timeout(limit: float) -> float:
        budget = min(limit, expires - time.monotonic()) if expires is not None else limit
        if remaining is not None:
            budget = min(budget, remaining())
        if budget <= 0:
            raise TimeoutError('overall input regression deadline expired')
        return budget
    output = Path(out).resolve()
    output.mkdir(parents=True, exist_ok=False)
    original_disk = Path(initial_disk).resolve()
    original_hash = sha(original_disk)
    summary = {'schema_version': 1, 'status': 'FAIL',
               'scope': 'real compiled pen-loss regression; negative guest quarantined and unqualified',
               'initial_media_sha256': original_hash, 'cases': []}
    try:
        initial_root, initial_sequence, initial_records = recover(original_disk.read_bytes())
        if initial_sequence != 0 or initial_records:
            raise ValueError('input regression requires a fresh genuinely initialized empty record medium')
        summary['initial_generation'] = initial_root.generation
        candidate = git(ROOT, 'rev-parse', candidate_commit + '^{commit}')
        summary['candidate_commit'] = candidate
        source = subprocess.check_output(['git', 'show', candidate + ':' + NOTEBOOK], cwd=ROOT,
                                         text=True, timeout=30)
        mutated = mutate_source(source)
        positive_image = Path(metadata['notebook']['path']).resolve()
        provenance = json.loads((positive_image.parent / 'provenance.json').read_text())
        if (provenance['source_commit'] != candidate or provenance['dirty_paths'] or
                provenance['source_inputs'][NOTEBOOK] != hashlib.sha256(source.encode()).hexdigest()):
            raise ValueError('positive must be genuinely built from this clean committed candidate')
        if sha(positive_image) != metadata['notebook']['sha256']:
            raise ValueError('positive guest image identity differs')
        selected_qemu = Path(qemu).resolve()
        if selected_qemu != Path(metadata['qemu']['path']).resolve() or sha(selected_qemu) != metadata['qemu']['sha256']:
            raise ValueError('host QEMU identity differs')
        summary.update(positive_guest_sha256=sha(positive_image), qemu_sha256=sha(selected_qemu))
        checkout = output / 'experimental-checkout'
        bounded(['git', 'worktree', 'add', '--detach', str(checkout), candidate], ROOT,
                output / 'worktree.log', timeout(60))
        if git(checkout, 'status', '--porcelain'):
            raise ValueError('fresh experimental checkout is not clean')
        (checkout / NOTEBOOK).write_text(mutated)
        (output / 'negative-source.patch').write_text(git(checkout, 'diff', '--', NOTEBOOK) + '\n')
        if git(checkout, 'diff', '--name-only') != NOTEBOOK:
            raise ValueError('negative changed more than its one quarantined Lean boundary')
        build = checkout / 'build/kernel/input-negative-O2'
        bounded(['nix', 'develop', '--no-write-lock-file', '--command', 'python3', 'scripts/build_kernel.py', '--fresh',
                 '--configuration', 'lemmasim-notebook', '--stage', 'supervisor', '--opt-level', 'O2',
                 '--output-dir', str(build), '--timeout', '300'], checkout,
                output / 'negative-build.log', timeout(1200))
        built = json.loads((build / 'build.json').read_text())
        negative_provenance = json.loads((build / 'provenance.json').read_text())
        if (built['status'] != 'BUILT' or negative_provenance['source_commit'] != candidate or
                negative_provenance['dirty_paths'] != [' M ' + NOTEBOOK]):
            raise ValueError('negative lacks its genuine elaboration/build provenance')
        changed = {path for path, digest in negative_provenance['source_inputs'].items()
                   if provenance['source_inputs'].get(path) != digest}
        if changed != {NOTEBOOK} or set(negative_provenance['source_inputs']) != set(provenance['source_inputs']):
            raise ValueError('negative build inputs differ beyond the one intentional Lean mutation')
        negative_image = build / 'image.elf'
        negative_metadata = dict(metadata, notebook={'path': str(negative_image), 'sha256': sha(negative_image)})
        write(output / 'negative-image.json', {'schema_version': 1, 'qualification': 'UNQUALIFIED_NEGATIVE_ONLY',
              'candidate_source_commit': candidate, 'only_altered_source': NOTEBOOK,
              'source_patch_sha256': sha(output / 'negative-source.patch'),
              'image': str(negative_image), 'image_sha256': sha(negative_image),
              'build_manifest_sha256': sha(build / 'build.json'), 'provenance_sha256': sha(build / 'provenance.json')})
        raw_bytes, manifest = generate('loss-disconnect', 1650, 2200, 200000000, 100000, 200000000)
        raw, manifest_file = output / 'input.bin', output / 'input.json'
        raw.write_bytes(raw_bytes)
        write(manifest_file, manifest)
        native = helpers_module().load_launch()
        for name, selected in (('positive', metadata), ('negative', negative_metadata)):
            directory = output / name
            directory.mkdir()
            disk = directory / 'disk.raw'
            shutil.copyfile(original_disk, disk)
            run = directory / 'run'
            process = native.launch(selected, disk, run, headless=True, geometry='1650x2200',
                                    raw=raw, until_ingress=manifest['input_samples'],
                                    timeout=timeout(300), mode='laboratory')
            if process.get('status') != 'OBSERVED_GUEST_WORKFLOW_BOUNDARY' or process.get('process_reaped') is not True:
                raise ValueError(name + ' did not reach the actual quiescent guest Saved boundary')
            try:
                observed = check(disk, raw, manifest_file, run / 'devices.jsonl',
                                 run / 'serial.bin', run / 'visible.ppm')
            except ValueError as error:
                observed = {'schema_version': 1, 'status': 'FAIL', 'error': str(error),
                            'scope': 'independent live notebook document/pixel/loss observer',
                            'artifact_sha256': {str(path): sha(path) for path in
                                (disk, raw, manifest_file, run / 'devices.jsonl', run / 'serial.bin', run / 'visible.ppm')}}
            write(directory / 'independent-workflow.json', observed)
            cancelled = cancelled_records(disk, raw, manifest, run / 'devices.jsonl')
            write(directory / 'cancelled-raw-observation.json', cancelled)
            if name == 'positive':
                if observed.get('status') != 'PASS' or cancelled['retained_cancelled_samples']:
                    raise ValueError('positive failed independent loss cancellation')
                cold = directory / 'cold.raw'
                shutil.copyfile(disk, cold)
                reopened = native.launch(selected, cold, directory / 'cold-run', headless=True,
                                         timeout=timeout(180), until_ready=True, mode='laboratory')
                if reopened.get('status') != 'OBSERVED_GUEST_WORKFLOW_BOUNDARY' or reopened.get('process_reaped') is not True:
                    raise ValueError('positive cold process did not redraw acknowledged writing')
                cold_check = check_cold(disk, cold, run / 'visible.ppm', directory / 'cold-run/visible.ppm',
                                        directory / 'cold-run/serial.bin', directory / 'cold-run/devices.jsonl')
                write(directory / 'independent-cold.json', cold_check)
                if cold_check.get('status') != 'PASS':
                    raise ValueError('positive cold observer rejected loss recovery')
            else:
                require_oracle_rejection(observed, cancelled)
            summary['cases'].append({'name': name, 'oracle_status': observed['status'],
                                     'rejection': observed.get('error'),
                                     'retained_cancelled_raw_samples': cancelled['retained_cancelled_samples'],
                                     'stable_media_sha256': sha(disk), 'process_reaped': True})
        if sha(original_disk) != original_hash:
            raise ValueError('original initialization image changed')
        summary.update(status='PASS',
                       meaning='positive cancels and cold-reopens; independent observer rejects negative actually committed cancelled contact',
                       negative_guest_sha256=sha(negative_image), source_patch_sha256=sha(output / 'negative-source.patch'))
    except BaseException as error:
        summary['error'] = str(error)
        raise
    finally:
        summary['initial_media_unchanged'] = sha(original_disk) == original_hash
        write(output / 'result.json', summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('metadata', 'qemu', 'initial', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--candidate-commit', required=True)
    parser.add_argument('--deadline', type=float, default=1800)
    args = parser.parse_args()
    try:
        result = campaign(json.loads(args.metadata.read_text()), args.qemu, args.initial,
                          args.output, args.candidate_commit, deadline_seconds=args.deadline)
    except Exception as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({'status': result['status'], 'cases': result['cases'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
