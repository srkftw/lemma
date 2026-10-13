#!/usr/bin/env python3
"""Observe frozen USB8 wire bytes after the retained original observer failure."""
import argparse
import json
from pathlib import Path
import struct
import time

from archive_companion_boundary import log_frames, outbox_fields
from check_guest_usb_link import decode_capture, require, sha
from check_guest_usb_notebook import recover
from check_guest_usb_store import opaque_log
from lemmasim_companion import peer_info
from silicon_guest_bundle import prepared

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workflow', 'initial-peer', 'initial-outbox', 'native-bundle', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.work_dir.resolve(); require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused owned output')
    out.mkdir(); started = time.monotonic()
    report = {'schema': 'lemma-usb8-retained-workflow-wire/1', 'status': 'FAIL',
              'scope': 'frozen actual wire/workflow observation; original campaign FAIL retained; no CPU run or cold claim'}
    try:
        original = args.workflow.resolve(); result = original / 'result.json'
        source = json.loads(result.read_text())
        supervision = original.with_name(original.name + '.supervision') / 'supervision.json'
        supervised = json.loads(supervision.read_text())
        require(source['status'] == 'FAIL' and source['error'] == "ValueError('actual hello identity')" and
                source['profile'] == 'lemma-silicon-dev/0.8.0' and supervised['status'] == 'FAIL' and
                supervised['owned_survivors'] == [] and supervised['result_sha256'] == sha(result),
                'original failure/reaped source identity differs')
        require(source['workflow'] == {'status': 'PASS', 'sequence': 11, 'generation': 1,
            'raw_samples': 3, 'strokes': 1, 'pages': 2, 'documents': [1],
            'contact_points': [['usb annotation', 330, 1200, True]],
            'explicit_save': [0x421, 11, 1, 1, 0], 'committed_objects': 4}, 'original complete workflow observation differs')
        require(source['bounds'] == {'cold_cycles': 1600000000, 'cold_host_seconds': 7200,
            'ink_cycles': 200000000, 'redraw_save_cycles': 1600000000, 'action_host_seconds': 7200}, 'original ceilings changed')
        bundle = prepared(args.native_bundle.resolve(), 'rtl', 'usb-next-bulk-notebook', 'lemma-silicon-dev/0.8.0')
        require(source['identity']['runtime'] == bundle['binary']['sha256'] and
                source['identity']['guest'] == bundle['workloads']['usb-next-bulk-notebook']['image']['sha256'],
                'actual workflow is not the complete qualified native/guest bundle')
        initial = args.initial_peer.resolve(); info = peer_info(initial)
        prior = log_frames((initial / 'opaque.log').read_bytes())
        require(info['writer'] == source['writer'] == 83 and len(prior) == 6,
                'preexisting formatted receipt state differs')
        outbox_fields((args.initial_outbox.resolve() / 'outbox').read_bytes(), 83, 6)
        # The next writer sequence is established by the independent initial
        # receipt log and outbox, before consulting the observed hello.
        raw = original / 'live/usb.raw'
        wire = decode_capture(raw, probe=False, writer=83, initial_sequence=len(prior) + 1)
        mutations = [bytes.fromhex(value) for value in wire['requests'][1:]
                     if int.from_bytes(bytes.fromhex(value)[16:24], 'little') in (1, 2)]
        actual_log = log_frames((original / 'peer/opaque.log').read_bytes())
        require(actual_log == prior + mutations and len(actual_log) == 72 and
                len(opaque_log(original / 'peer/opaque.log')) == 72,
                'actual accepted wire effects differ from durable peer receipt prefix')
        outbox_fields((original / 'outbox/outbox').read_bytes(), 83, 72)
        receipt = source['lost_ack_boundary']['receipt']
        require(sum(list(fields) == receipt for fields, _ in opaque_log(original / 'peer/opaque.log')) == 1,
                'lost-ACK reconciliation duplicated its durable effect')
        # Exact consumed Notebook source: chunk3/page4/root5; Undo page6/root7;
        # Redo page8/root9; newPage2 page10/root11. PreviousPage is a load and
        # toolbar7 issues Store.flush only, so neither rewrites a page object.
        _, sequence, records = recover((original / 'acknowledged.raw').read_bytes())
        require(sequence == 11 and {key: value.sequence for key, value in records.items()} ==
                {(1, 1): 11, (1, 257): 8, (1, 258): 10, (1, 65539): 3},
                'Saved11 acknowledged journal differs from the independent object oracle')
        uart = (original / 'live/uart.bin').read_bytes()
        require(b'K1 0000000000000421 000000000000000b 0000000000000001 0000000000000001 0000000000000000' in uart,
                'actual guest Saved11 UART receipt is absent')
        inputs = [result, supervision, raw, initial / 'opaque.log', args.initial_outbox.resolve() / 'outbox',
                  original / 'peer/opaque.log', original / 'outbox/outbox', original / 'acknowledged.raw',
                  original / 'acknowledged.ppm', original / 'live/uart.bin', original / 'live/input.events']
        report.update(status='PASS', identity=source['identity'], original_failure={'path': str(result), 'sha256': sha(result)},
            workflow=source['workflow'], milestones=source['milestones'], initial_sequence=7,
            writer=83, saved_sequence=11, high_water=72, wire=wire,
            raw_capture={'path': str(raw), 'sha256': sha(raw)},
            input_files={str(path): sha(path) for path in inputs},
            initial_receipt_state={'count': 6, 'outbox_next': 7, 'log_prefix_equal': True},
            durable_effects_equal_actual_wire=True, lost_barrier_effect_count=1,
            owned_children_reaped=True)
    except BaseException as error:
        report['error'] = repr(error)
    report.update(host_seconds=time.monotonic() - started, observer_sha256=sha(__file__),
                  wire_observer_sha256=sha(ROOT / 'scripts/check_guest_usb_link.py'))
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'result': str(out / 'result.json'), 'error': report.get('error')}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
