#!/usr/bin/env python3
"""Observe a paused native cold-recovery boundary without advancing the CPU.

A clean reopen needs Ready and completed redraw, not a new Save receipt. This
observer never resets, restores, drains, initializes, or supplies guest state.
It preserves the prior campaign result and exports into an unused directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from check_notebook_workflow import committed_bytes, guest_events, visible_pixels
from check_canonical_pen_pixels import expected_stroke
from check_companion_pending import timed_records
from lemmasim_session import request


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cold_boundary(records, machine):
    """No new journal publication is required to reopen acknowledged bytes."""
    ready = [r for r in records if r[0] == 0x420]
    redraw = [r for r in records if r[0] == 0x425]
    require(len(ready) == 1 and ready[0][1:4] == (1650 | (2200 << 32), 1, 1),
            'cold Ready geometry/view absent or contradictory')
    require(redraw and ready[0][4] > 0 and redraw[-1][1] == ready[0][4],
            'Ready does not name the actual full redraw')
    require(machine['panel_completed'] >= ready[0][4] and
            machine['panel_sequence'] == ready[0][4] and
            not machine['paper_busy'] and not machine['panel_pending_pixels'],
            'named full controller redraw has not completed')
    require(not machine['finished'] and not machine['block_state'] and
            not machine['memory_pending'] and not machine['dma_outstanding'],
            'cold device work is failed or still pending')
    backing = machine['backing_io']
    require(backing['phase'] == 2 and backing['completed'] == backing['next_id'] - 1
            and not backing['poisoned'] and not backing['orphan'] and
            not backing['fork_suspended'] and backing['observed_write'] ==
            backing['durable_barrier'] == 0 and machine['flushes'] == 0,
            'cold backing reads are unresolved or recovery published writes')
    require(not any(r[0] in (0x41f, 0x423, 0x424) for r in records),
            'cold reopen formatted, republished, or failed')
    return ready[0][4]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('session', 'retained-result', 'samples', 'native-bundle',
                 'acknowledged-medium', 'acknowledged-panel', 'raw-input', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused owned output')
    out.mkdir(parents=True)
    started = time.monotonic()
    report = {'schema': 'lemma-retained-cold-observer/1', 'status': 'FAIL',
              'scope': __doc__, 'prior_result': {'path': str(args.retained_result),
                                                'sha256': sha(args.retained_result)}}
    try:
        prior = json.loads(args.retained_result.read_text())
        bundle = json.loads((args.native_bundle / 'bundle.json').read_text())
        # Bind the explanation to consumed source bytes, never current sources.
        notebook = args.native_bundle / 'source/Lemma/Applications/Notebook.lean'
        require(sha(notebook) == bundle['sources']['Lemma/Applications/Notebook.lean'],
                'consumed Notebook source changed')
        text = notebook.read_text()
        guard = '.bind (if create = 1 then savePage 1 else .done 0 0)'
        require(text.count(guard) == 1 and text.index(guard) < text.index(
            'CapabilityConsole.record console 0x420 geometry 1 1 accepted'),
            'consumed clean-load publication guard differs')
        h = bundle['backends']['rtl']['rtl_sources'][str(ROOT / 'sim/host/backing_io.h')]
        source = args.native_bundle / 'backend-sources' / h
        require(sha(source) == h and
                'Idle=0, Pending=1, Completed=2, Cancelled=3' in source.read_text(),
                'consumed backing phase semantics changed')
        report['consumed_sources'] = {'Notebook.lean': sha(notebook), 'backing_io.h': h}
        before = request(args.session, {'action': 'inspect'}, 60)
        require(before['running'] is False and before['machine'] == prior['last'] and
                before['identity'] == prior['identity'], 'retained paused boundary changed')
        rows = guest_events(args.session / 'uart.bin')
        sequence = cold_boundary(rows, before['machine'])
        outcomes, pending = timed_records(args.session / 'backing.io')
        require(pending is None and len(outcomes) == before['machine']['backing_io']['completed']
                and all(r[0][2] == 0 and r[0][6] == 0 for r in outcomes),
                'captured recovery includes missing/failed/non-read outcomes')
        first = None
        for line in args.samples.open():
            row = json.loads(line)
            if row['machine']['panel_completed'] >= sequence:
                first = row
                break
        require(first is not None and first['seconds'] < prior['plan']['deadline_seconds']
                and first['machine']['cycle'] < prior['plan']['cycles'],
                'full redraw was not recorded within the original bounds')
        for action, name in (('panel', 'retained.ppm'), ('export-medium', 'retained.raw')):
            request(args.session, {'action': action, 'path': str(out / name)}, 60)
        after = request(args.session, {'action': 'inspect'}, 60)
        require(after == before, 'observational exports changed the machine')
        panel = visible_pixels(out / 'retained.ppm')
        require(panel == visible_pixels(args.acknowledged_panel),
                'complete recovered controller pixels differ from acknowledged view')
        samples = json.loads(args.raw_input.read_text())['events'][1:4]
        expected, points = expected_stroke(samples, panel[0], panel[1])
        require(panel[2] == expected, 'independent complete stroke pixels differ')
        acknowledged = committed_bytes(args.acknowledged_medium)
        require(committed_bytes(out / 'retained.raw') == acknowledged,
                'acknowledged objects were changed or lost')
        require(sha(args.acknowledged_medium) == sha(out / 'retained.raw'),
                'clean cold recovery changed the backing medium')
        report.update(status='PASS_CORRECTED_RETAINED_OBSERVER', identity=before['identity'],
                      unchanged_boundary=before['machine'], completed_successful_reads=len(outcomes),
                      recorded_full_redraw_boundary={'cycle': first['machine']['cycle'],
                                                    'host_seconds': first['seconds']},
                      stale_expectation='original observer required a new0x421 Save on a clean load',
                      guest_records=rows, acknowledged_sequence=acknowledged[0],
                      acknowledged_objects=acknowledged[1], full_pixels=panel[0] * panel[1],
                      independent_black_points=points, pixel_sha256=hashlib.sha256(panel[2]).hexdigest(),
                      artifacts={str(p): sha(p) for p in (args.raw_input, args.samples,
                         args.acknowledged_medium, args.acknowledged_panel, out / 'retained.raw',
                         out / 'retained.ppm', args.session / 'uart.bin', args.session / 'backing.io')})
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        report['observer_sha256'] = sha(__file__)
        report['observation_host_seconds'] = time.monotonic() - started
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('status', 'recorded_full_redraw_boundary',
                                           'completed_successful_reads', 'full_pixels')}))


if __name__ == '__main__':
    main()
