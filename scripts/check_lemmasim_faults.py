#!/usr/bin/env python3
"""Real notebook block-fault and cold-recovery campaign, with independent observers.

Uses the maintained native launch path and device fault filter. No host recovery
feeds a running guest. Each operation starts on a fresh copy of acknowledged
media and every fault is checked, then cold booted in a new QEMU process.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import shutil
import struct
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from check_crash_workflow import check as check_fault, plan, baseline_export as read_baseline_export
from check_notebook_workflow import check_cold, committed_bytes, guest_events
from notebook_input import generate
from store_oracle import recover


def load_launch():
    loader = importlib.machinery.SourceFileLoader('lemma_fault_native_launch', str(ROOT / 'scripts/lemmasim'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, result: dict) -> None:
    if path.exists():
        raise ValueError('refusing to replace retained fault evidence: ' + str(path))
    path.write_text(json.dumps(result, indent=2) + '\n')


def raw_fixture(out: Path, operation: str) -> tuple[Path, Path]:
    """Raw controller samples: one new stroke or the ordinary Save tool tap."""
    raw, manifest = generate('basic', 1650, 2200, 200000000, 1000000, 200000000)
    if operation == 'append':
        # Keep exactly the initial release and first writing action. Move the
        # source device samples to a clear page region; no ink/pixels are made.
        action = next(item for item in manifest['actions'] if item['kind'] == 'stroke')
        raw = raw[:action['last_sequence'] * 72]
        rows = [list(struct.unpack_from('<9Q', raw, offset)) for offset in range(0, len(raw), 72)]
        for row in rows[1:]:
            row[3] = (1000 * 65535 + 2198) // 2199
        raw = b''.join(struct.pack('<9Q', *row) for row in rows)
        manifest['actions'] = [dict(action, name='crash append')]
    else:
        # Button 7 is the guest Save/checkpoint control, reached solely via FIFO.
        x = (7 * 2 + 1) * (1650 // 8) // 2
        xraw, yraw = (x * 65535 + 1648) // 1649, (64 * 65535 + 2198) // 2199
        rows = [(1, 200000000, 32768, 32768, 0, 2, 1, 0, 1),
                (2, 210000000, xraw, yraw, 2048, 3, 1, 0, 1),
                (3, 211000000, xraw, yraw, 0, 2, 1, 0, 1)]
        raw = b''.join(struct.pack('<9Q', *row) for row in rows)
        manifest['actions'] = [{'kind': 'tool', 'name': 'save/checkpoint',
                                'first_sequence': 2, 'last_sequence': 3}]
    manifest.update(workflow='crash-' + operation, input_samples=len(raw) // 72,
                    input_sha256=hashlib.sha256(raw).hexdigest(),
                    first_tick=rows[0][1], last_tick=rows[-1][1],
                    expected={'acknowledged_baseline_preserved': True,
                              'new_operation': 'absent or wholly valid after admitted fault'})
    manifest.pop('sample_interval_ticks', None)
    manifest.pop('action_gap_ticks', None)
    manifest['timing_policy'] = 'absolute serialized sample timestamps in 10 MHz guest ticks'
    input_path, manifest_path = out / (operation + '.bin'), out / (operation + '.json')
    input_path.write_bytes(raw)
    write_json(manifest_path, manifest)
    return input_path, manifest_path


def campaign(metadata: dict, qemu: Path | str, baseline_disk: Path | str,
             baseline_export: Path | str, baseline_serial: Path | str,
             out: Path | str, *, deadline_seconds: float | None = None,
             remaining: Callable[[], float] | None = None) -> dict:
    expires = time.monotonic() + deadline_seconds if deadline_seconds is not None else None
    def bounded_timeout(limit: float) -> float:
        budget = min(limit, expires - time.monotonic()) if expires is not None else limit
        if remaining is not None:
            budget = min(budget, remaining())
        if budget <= 0:
            raise TimeoutError('overall fault campaign deadline expired')
        return budget
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    baseline_disk, baseline_export, baseline_serial = (Path(path).resolve()
        for path in (baseline_disk, baseline_export, baseline_serial))
    baseline_visible = baseline_serial.parent / 'visible.ppm'
    original_hash = digest(baseline_disk)
    exported, notebook = read_baseline_export(baseline_export)
    states = [row for row in guest_events(baseline_serial) if row[0] in (0x421, 0x423, 0x424)]
    if original_hash != exported['image_sha256'] or not notebook.chunks or not states or states[-1][:2] != (0x421, exported['committed_sequence']):
        raise ValueError('fault campaign requires the exact acknowledged notebook baseline')
    if (1, 1) not in notebook.pages or not baseline_visible.is_file():
        raise ValueError('fault baseline needs notebook-1/page-1 and its actual visible output')
    metadata = dict(metadata, qemu=dict(metadata['qemu'], path=str(Path(qemu).resolve())))
    if digest(Path(metadata['qemu']['path'])) != metadata['qemu']['sha256']:
        raise ValueError('fault QEMU identity differs from supplied build metadata')
    native = load_launch()
    results = []
    summary = {'schema_version': 1, 'status': 'RUNNING',
               'scope': 'actual RV64 notebook device faults and new-process cold recovery; exact candidate qualification is caller-owned',
               'baseline_image_sha256': original_hash, 'baseline_sequence': exported['committed_sequence'],
               'guest_sha256': digest(Path(metadata['notebook']['path'])),
               'qemu_sha256': metadata['qemu']['sha256'],
               'harness_sha256': {str(path.relative_to(ROOT)): digest(path) for path in (
                   Path(__file__).resolve(), ROOT / 'scripts/lemmasim',
                   ROOT / 'conformance/lemmasim/check_crash_workflow.py',
                   ROOT / 'conformance/lemmasim/store_oracle.py')}, 'cases': results}
    try:
        inputs = {operation: raw_fixture(out, operation) for operation in ('append', 'checkpoint')}
        references = {}
        for operation in ('append', 'checkpoint'):
            directory = out / ('a' if operation == 'append' else 'c')
            directory.mkdir()
            disk = directory / 'disk.raw'
            shutil.copyfile(baseline_disk, disk)
            launched = native.launch(metadata, disk, directory / 'r', headless=True,
                                     raw=inputs[operation][0], timeout=bounded_timeout(120), until_commits=1)
            if launched['status'] != 'OBSERVED_GUEST_WORKFLOW_BOUNDARY' or launched.get('document_report', {}).get('status') != 'SAVED':
                raise ValueError(operation + ' reference failed to reach a genuine guest Saved boundary')
            observed = plan(disk, directory / 'r/media.jsonl', baseline_export)
            write_json(directory / 'plan.json', observed)
            references[operation] = (directory, observed)
        append_cases = references['append'][1]['cases']
        ink = [case for case in append_cases if case.get('record_object', 0) > 65536]
        catalog = [case for case in append_cases if case.get('record_object') == 1]
        payload = next(case for case in ink if case['phase'] == 'payload')
        publication = next(case for case in ink if case['phase'] == 'publication')
        final_flush = next(case for case in catalog if case['phase'] == 'publication')
        checkpoint_cases = references['checkpoint'][1]['cases']
        segment = next(case for case in checkpoint_cases if case['phase'] == 'checkpoint-segment')
        root = next(case for case in checkpoint_cases if case['phase'] == 'checkpoint-root')
        selected = [
            ('payload-before', payload, 'cut-before-flush'),
            ('payload-after', payload, 'cut-after-flush'),
            ('publication-before', publication, 'cut-before-flush'),
            ('publication-after', publication, 'cut-after-flush'),
            ('final-flush-before', final_flush, 'cut-before-flush'),
            ('final-flush-after', final_flush, 'cut-after-flush'),
            ('torn-publication', publication, 'tear-flush'),
            ('torn-payload', payload, 'tear-flush'),
            ('failed-final-flush', final_flush, 'fail-flush'),
            ('checkpoint-segment-before', segment, 'cut-before-flush'),
            ('checkpoint-segment-after', segment, 'cut-after-flush'),
            ('checkpoint-root-before', root, 'cut-before-flush'),
            ('checkpoint-root-after', root, 'cut-after-flush'),
            ('checkpoint-root-torn', root, 'tear-flush'),
            ('checkpoint-root-failed', root, 'fail-flush'),
        ]
        baseline_page = notebook.payloads[1, 257]
        reference_page = recover((references['append'][0] / 'disk.raw').read_bytes())[2][1, 257].payload
        for index, (name, template, fault) in enumerate(selected, 1):
            print('Actual fault workflow: ' + name, flush=True)
            directory = out / f'f{index:02d}'
            directory.mkdir()
            disk = directory / 'fault.raw'
            shutil.copyfile(baseline_disk, disk)
            case = dict(template, fault=fault)
            case_path = directory / 'case.json'
            write_json(case_path, case)
            operation = template['operation']
            launched = native.launch(metadata, disk, directory / 'r', headless=True,
                                     raw=inputs[operation][0], timeout=bounded_timeout(75),
                                     faults={fault: template['ordinal']}, mode='laboratory')
            if fault != 'fail-flush' and (launched['status'] != 'MODELED_POWER_CUT' or launched['returncode'] != 86):
                raise ValueError(name + ': actual modeled power cut did not exit at device boundary')
            if not launched['process_reaped']:
                raise ValueError(name + ': device process was not reaped')
            observed = check_fault(baseline_export, baseline_serial, disk,
                                   directory / 'r/serial.bin', inputs[operation][0], inputs[operation][1],
                                   directory / 'r/devices.jsonl', directory / 'r/media.jsonl', case_path)
            write_json(directory / 'crash-observation.json', observed)
            current_page = recover(disk.read_bytes())[2][1, 257].payload
            if current_page == baseline_page:
                expected_visible = baseline_visible
            elif current_page == reference_page:
                expected_visible = references['append'][0] / 'r/visible.ppm'
            else:
                raise ValueError(name + ': unexpected partial page publication')
            cold_disk = directory / 'cold.raw'
            shutil.copyfile(disk, cold_disk)
            cold_run = native.launch(metadata, cold_disk, directory / 'c', headless=True,
                                     timeout=bounded_timeout(120), until_ready=True)
            if cold_run['status'] != 'OBSERVED_GUEST_WORKFLOW_BOUNDARY' or not cold_run['process_reaped']:
                raise ValueError(name + ': cold new-process guest did not reach completed page readiness')
            cold = check_cold(disk, cold_disk, expected_visible, directory / 'c/visible.ppm',
                              directory / 'c/serial.bin', directory / 'c/devices.jsonl')
            write_json(directory / 'cold-observation.json', cold)
            results.append({'name': name, 'directory': directory.name, 'status': 'PASS', 'fault': fault,
                            'ordinal': template['ordinal'], 'phase': template['phase'],
                            'recovered_sequence': observed['recovered_sequence'],
                            'recovered_generation': observed['recovered_generation'],
                            'fault_media_sha256': digest(disk),
                            'cold_document_sha256': cold['committed_document_sha256'],
                            'cold_visible_sha256': cold['visible_pixels_sha256']})
        if len(results) != len(selected) or digest(baseline_disk) != original_hash:
            raise ValueError('incomplete fault corpus or original baseline changed')
        if any(digest(ROOT / path) != expected for path, expected in summary['harness_sha256'].items()):
            raise ValueError('fault harness sources changed during this campaign')
        summary.update(status='PASS', fault_count=len(results), references={operation: {
            'disk_sha256': digest(directory / 'disk.raw'), 'plan_sha256': digest(directory / 'plan.json')}
            for operation, (directory, _) in references.items()})
    except BaseException as error:
        summary.update(status='FAIL', error=str(error))
        raise
    finally:
        summary['baseline_unchanged'] = digest(baseline_disk) == original_hash
        write_json(out / 'result.json', summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('metadata', 'qemu', 'baseline-disk', 'baseline-export', 'baseline-serial', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        result = campaign(json.loads(args.metadata.read_text()), args.qemu, args.baseline_disk,
                          args.baseline_export, args.baseline_serial, args.output)
    except Exception as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({'status': result['status'], 'fault_count': result['fault_count'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
