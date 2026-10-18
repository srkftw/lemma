#!/usr/bin/env python3
"""Fresh canonical QEMU writing, Save, cold recovery and failed-FLUSH checks.

Development integration of an explicitly supplied guest build and validated
native bundle. The maintained public session executes every guest/device cycle;
maintained independent observers check original raw inputs and durable pixels.
The initial medium must come from actual guest initialization. This command
copies its bytes privately; it never compiles, synthesizes a document, restores
machine state, or replaces independent cold recovery with replay.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import shutil
import signal
import struct
import sys
import time

from action_cache import process_identity
from check_live_notebook import (Checker, Input, PublicSession, generate, observe_workflow,
                                 recover, require, root_slot, sha)

ROOT = Path(__file__).resolve().parents[1]


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class ObservedSession(PublicSession):
    def __init__(self, checker, name, disk, fail_flush=None):
        super().__init__(checker, name, disk, fail_flush)
        try:
            self.owner = process_identity(self.process.pid)
            state = self.inspect()['machine']
            require(state['cycle'] == 0, 'every integration phase requires an independent fresh guest instance')
            checker.report.setdefault('machine_instances', []).append(
                {'name': name, 'directory': str(self.directory), 'identity': self.identity,
                 'owner': self.owner, 'initial_cycle': state['cycle'], 'fail_flush': fail_flush})
        except BaseException:
            super().close()
            raise

    def close(self):
        super().close()
        require(self.process.poll() is not None, 'public session child was not reaped')
        entry = {'session': str(self.directory), 'owner': self.owner,
                 'process_reaped': True, 'returncode': self.process.returncode}
        self.checker.closed_sessions[str(self.directory)] = entry


class IncrementalNotebook(Checker):
    profile = 'lemma-silicon-dev/0.3.0'
    backend = 'qemu'

    def __init__(self, args):
        super().__init__(args)
        self.report.update(
            schema='lemma-incremental-notebook/1', started_at=timestamp(),
            scope='Fresh canonical-profile QEMU raw writing, explicit Save, independent cold '
                  'recovery and failed first FLUSH with another independent cold guest. '
                  'Development integration only; production freshness is reported by the '
                  'supplied build action receipts, independently of these new executions.',
            backend=self.backend, no_snapshot=True, no_replay=True,
            compilation='not performed; explicitly supplied guest artifact',
            execution='new public machine instances with private byte-copied media',
            fixture=self.args.workflow,
            normal_boot_diagnostic={'tag': 0xd3, 'source': 'Lemma/Kernel/Process.lean',
                                    'meaning': 'successful Process.initialize; 0xd4 is a fault'})
        helpers = ('scripts/check_incremental_notebook.py', 'scripts/action_cache.py', 'scripts/lemmasim',
                   'scripts/lemmasim_session.py', 'sim/native/run_local.py',
                   'conformance/lemmasim/math_oracle.py')
        for name in helpers:
            self.report['observer_sources'][name] = sha(ROOT / name)
        self.target_inputs = {}
        self.closed_sessions = {}

    def session(self, name, disk, fail_flush=None):
        session = ObservedSession(self, name, disk, fail_flush)
        self.sessions.append(session)
        return session

    def check_sources(self):
        require(time.monotonic() < self.deadline, 'campaign host resource deadline')
        for name, expected in self.report['observer_sources'].items():
            require(sha(ROOT / name) == expected, 'observer/launcher source changed: ' + name)
        for name, expected in self.target_inputs.items():
            require(sha(self.guest_source / name) == expected, 'supplied guest source changed: ' + name)
        if hasattr(self, 'initial_sha'):
            require(sha(Path(self.args.initial_medium)) == self.initial_sha,
                    'original initial medium changed')
        if hasattr(self, 'guest_sha'):
            require(sha(self.guest_build / 'image.elf') == self.guest_sha,
                    'supplied compiled guest changed')

    def execute(self):
        initial = Path(self.args.initial_medium).resolve()
        require(initial.is_file() and initial.stat().st_size == 256 * 1024 * 1024,
                'provide an actual guest-initialized 256 MiB canonical medium')
        self.initial_sha = sha(initial)
        self.report['initial_medium'] = {'path': str(initial), 'sha256': self.initial_sha,
                                        'bytes': initial.stat().st_size,
                                        'scope': 'opaque original bytes copied privately; no host document generation'}
        self.guest_build = Path(self.args.guest_build).resolve()
        self.guest_source = Path(self.args.guest_source_root or ROOT).resolve()
        provenance = json.loads((self.guest_build / 'provenance.json').read_text())
        build = json.loads((self.guest_build / 'build.json').read_text())
        require(build.get('status') == 'BUILT', 'supplied guest build is not successful')
        require(provenance.get('source_commit') and isinstance(provenance.get('source_inputs'), dict)
                and provenance['source_inputs'], 'supplied guest source provenance is incomplete')
        self.target_inputs = provenance['source_inputs']
        self.guest_sha = sha(self.guest_build / 'image.elf')
        self.report.update(source_commit=provenance['source_commit'], source_inputs=self.target_inputs,
                           guest_source_root=str(self.guest_source),
                           guest_artifact={'path': str(self.guest_build / 'image.elf'),
                                           'sha256': self.guest_sha,
                                           'configuration': build.get('configuration'),
                                           'optimization': build.get('optimization'),
                                           'provenance_sha256': sha(self.guest_build / 'provenance.json'),
                                           'build_sha256': sha(self.guest_build / 'build.json'),
                                           'action_journal': str(self.guest_build / 'actions.json')})
        self.check_sources()
        disk = self.directory / 'notebook.raw'
        shutil.copyfile(initial, disk)
        require(sha(initial) == self.initial_sha == sha(disk), 'initial medium changed during private copy')
        image = disk.read_bytes()
        root, sequence, records = recover(image)
        require(sequence == 0 and not records and
                root_slot(image[:512], len(image) // 512) == root_slot(image[512:1024], len(image) // 512) == root,
                'basic/editing fixture requires actual durable empty guest roots, not an existing document')
        del image
        self.report['initial_medium']['validated_roots'] = 'both acknowledged empty roots; sequence zero'
        live = self.session('live', disk)
        self.report['identity'] = live.identity
        require(live.inspect()['machine']['cycle'] == 0, 'a fresh live guest instance is required')
        self.report['boot'] = live.boot()
        width, height = 1650, 2200
        _, fixture = generate(self.args.workflow, width, height, 0, 100000, 0)
        stream = Input(width, height, live.inspect()['machine']['ticks'] + 10000, 100000, 0)
        stream.sample(width // 2, 160, 0, False)
        live.admit(stream.events)
        live.settle(stream.events[-1][1])
        for action in fixture['actions']:
            self.check_sources()
            action_started = time.monotonic()
            before = live.inspect()['machine']
            stream.tick = before['ticks'] + 10000
            first = len(stream.events)
            if action['kind'] == 'stroke':
                stream.stroke(action['name'], action['page'], action['namespace'], action['raw_samples'],
                              height // 2 if action['name'] in ('b', 'd') else height // 3,
                              action['brush_q8'])
            else:
                stream.tool(action['button'], action['name'])
            live.admit(stream.events[first:])
            after = live.settle(stream.events[-1][1])
            interaction = {'name': action['name'], 'host_seconds': time.monotonic() - action_started,
                           'virtual_seconds': (after['virtual_ns'] - before['virtual_ns']) / 1000000000,
                           'last_sample_to_settled_ns': after['virtual_ns'] - stream.events[-1][1] * 100,
                           'initial_cycle': before['cycle'], 'final_cycle': after['cycle'],
                           'initial_paper_completed': before['devices']['paper']['completed'],
                           'final_paper_completed': after['devices']['paper']['completed']}
            self.report['interactions'].append(interaction)
            print(json.dumps({'interaction': interaction}), flush=True)
        (self.directory / 'input.bin').write_bytes(b''.join(struct.pack('<9Q', *row) for row in stream.events))
        (self.directory / 'input.json').write_text(json.dumps(
            {'profile': self.profile, 'geometry': [width, height], 'actions': stream.actions,
             'expected': fixture['expected']}, indent=2) + '\n')
        panel, medium = live.export('acknowledged')
        self.report['workflow'] = observe_workflow(
            medium, live.directory / 'input-0.bin', live.directory / 'uart-0.bin',
            panel, stream, fixture['expected'])
        self.report['workflow'].update(durable_sha256=sha(medium), controller_pixels_sha256=sha(panel))
        live.close()
        self.sessions.remove(live)
        self.check_sources()
        self.cold_recovery(medium, panel)
        self.check_sources()
        self.failed_barrier(medium, panel)
        self.check_sources()
        self.report['status'] = 'PASS'

    def close(self):
        cleanup = []
        for session in list(self.sessions):
            try:
                session.close()
                cleanup.append({'session': str(session.directory), 'process_reaped': session.process.poll() is not None,
                                'returncode': session.process.returncode})
            except BaseException as error:
                self.report.update(status='FAIL', cleanup_error=f'{type(error).__name__}: {error}')
            finally:
                self.sessions.remove(session)
        self.report.update(cleanup=list(self.closed_sessions.values()), interrupted_cleanup=cleanup, finished_at=timestamp(),
                           max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                           children_max_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
        self.commands.flush()
        self.report['commands'] = {'path': str(self.directory / 'commands.jsonl'),
                                  'sha256': sha(self.directory / 'commands.jsonl')}
        super().close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--work-dir', type=Path, required=True, help='Unused retained evidence directory')
    parser.add_argument('--native-bundle', required=True, help='Existing validated native QEMU bundle')
    parser.add_argument('--guest-build', required=True, help='Explicit current canonical notebook build')
    parser.add_argument('--guest-source-root', help='Exact source root for the supplied guest, if archived')
    parser.add_argument('--initial-medium', required=True, help='Actual guest-initialized empty 256 MiB medium')
    parser.add_argument('--workflow', choices=('basic', 'editing'), default='basic')
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--boot-seconds', type=int, default=30)
    parser.add_argument('--action-seconds', type=int, default=30)
    parser.add_argument('--deadline', type=int, default=1200)
    args = parser.parse_args(argv)
    require(1 <= args.timeout <= 300 and 1 <= args.boot_seconds <= 30 and
            1 <= args.action_seconds <= 30 and 1 <= args.deadline <= 1200,
            'declared development bounds exceed timeout300/boot30/action30/deadline1200')
    require(not args.work_dir.exists(), 'retain earlier results; an unused output directory is required')
    for name in ('native_bundle', 'guest_build', 'initial_medium', 'guest_source_root'):
        if getattr(args, name, None):
            setattr(args, name, str(Path(getattr(args, name)).resolve()))
    args.durable_suffix_from = None
    args.checkpoint_relation = 'exact-container'
    checker = IncrementalNotebook(args)
    def interrupted(signum, _frame):
        raise InterruptedError(f'campaign interrupted by signal {signum}')
    previous_term = signal.signal(signal.SIGTERM, interrupted)
    previous_alarm = signal.signal(signal.SIGALRM, interrupted)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, args.deadline)
    try:
        checker.execute()
    except BaseException as error:
        checker.report.update(status='FAIL', error=f'{type(error).__name__}: {error}')
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        checker.close()
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGALRM, previous_alarm)
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
    print(json.dumps({key: checker.report[key] for key in ('status', 'error') if key in checker.report}), flush=True)
    return 0 if checker.report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
