#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real notebook workflows through the public persistent LemmaSim interface.

Host-only stimulus and independent offline observations. No notebook RPC,
production recovery/codec/rasterizer, or host-generated document enters a guest.
The virtual and host bounds are declared before launching the machine. Retained
FAIL output is never overwritten, and every child has bounded teardown.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from check_notebook_workflow import (MAGIC, check_toolbar_pixels, committed_bytes,
                                     guest_events, join_chunks, visible_pixels)
from inspect_notebook import inspect_page
from notebook_input import Input, generate
from store_oracle import recover, root_slot
from lemmasim_session import request as session_request


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for part in iter(lambda: source.read(1048576), b''):
            result.update(part)
    return result.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def observe_raw_input(raw_output, stream, raw_format='binary-nine'):
    """Compare actual host admission fields without inventing device metadata.

    Native capture contains delivery cycle plus the seven raw device words.
    Sequence/epoch are subsequently compared against actual guest raw objects;
    they are not appended here to manufacture a nine-word ingress artifact.
    """
    if raw_format == 'binary-nine':
        raw = b''.join(struct.pack('<9Q', *row) for row in stream.events)
        require(Path(raw_output).read_bytes() == raw,
                'actual raw ingress differs from every original field')
    elif raw_format == 'native-seven-text':
        admitted = []
        data = Path(raw_output).read_bytes()
        require(len(data) <= 32 << 20 and data.endswith(b'\n'),
                'native input capture missing, truncated or oversized')
        for line in data.decode('ascii').splitlines():
            words = line.split()
            require(len(words) == 9 and words[1] == 'pen' and
                    all(word.isdecimal() and word.isascii() for word in words[:1] + words[2:]),
                    'unexpected native input field/shape')
            values = tuple(int(word) for word in words[:1] + words[2:])
            require(all(0 <= value < 1 << 64 for value in values),
                    'native input word overflow')
            admitted.append(values)
        require(admitted == [(row[1] * 10, *row[1:8]) for row in stream.events],
                'native raw admission differs from every original field and delivery cycle')
    else:
        raise ValueError('unknown actual raw capture format')


def observe_workflow(medium, raw_output, serial, panel, stream, expected,
                     *, raw_format='binary-nine'):
    """Compare literal raw provenance, indexes and optical contact points."""
    observe_raw_input(raw_output, stream, raw_format)
    root, sequence, records = recover(Path(medium).read_bytes())
    roots, pages, chunks = {}, {}, {}
    for (namespace, object_id), record in records.items():
        require(record.kind == 1 and len(record.payload) >= 64, 'unexpected record kind/length')
        fields = struct.unpack_from('<8Q', record.payload)
        from math_oracle import MAGIC as MATH_MAGIC, inspect as inspect_math
        if fields[0] == MATH_MAGIC:
            inspect_math(record.payload, namespace, object_id)
            continue
        require(fields[0] == MAGIC, 'unknown document envelope')
        if fields[2] == 1:
            require(fields[1] == 1 and object_id == 1 and len(record.payload) == 64,
                    'invalid document root')
            roots[namespace] = fields[3]
        elif fields[2] == 2:
            entries = inspect_page(record.payload, object_id)
            edit_offset = 12416 if fields[1] == 1 else 128 + fields[4] * 24
            edits = [struct.unpack_from('<2Q', record.payload, edit_offset + i * 16)
                     for i in range(fields[5])]
            flags = {}
            for kind, stroke in edits[:fields[6]]:
                flags[stroke] = int(kind == 1)
            require(all(flags.get(stroke) == visible for _, stroke, visible in entries),
                    'entry visibility differs from independent ordered edit replay')
            pages[namespace, fields[3]] = (entries, edits, fields[6])
        elif fields[2] == 3:
            header = struct.unpack_from('<16Q', record.payload)
            require(header[:3] == (MAGIC, 1, 3) and header[5] == header[15] == 0 and
                    1 <= header[6] <= 384 and len(record.payload) == 128 + header[6] * 72 and
                    header[8:14] == (1, 65535, 65535, 4095, stream.width, stream.height),
                    'raw envelope lost version, bounds, calibration, geometry or reserved fields')
            samples = [struct.unpack_from('<9Q', record.payload, 128 + i * 72)
                       for i in range(header[6])]
            chunks[namespace, object_id] = (header, samples)
        else:
            raise ValueError('unknown notebook object kind')
    require(roots == {int(ns): max(ids) for ns, ids in expected['pages'].items()},
            'page/document roots differ from raw navigation')
    require(set(pages) == {(int(ns), page) for ns, ids in expected['pages'].items() for page in ids},
            'page/document indexes differ from raw navigation')
    strokes, visible = {}, {}
    for (ns, page), (entries, edits, cursor) in pages.items():
        visible[ns, page] = set()
        for object_id, stroke, flag in entries:
            require((ns, object_id) in chunks, 'index references absent raw ink')
            header, samples = chunks[ns, object_id]
            require(header[3:5] == (page, stroke), 'page/stroke identity differs')
            strokes.setdefault((ns, stroke), []).append((header, samples))
            if flag:
                visible[ns, page].add(stroke)
        wanted_edits = expected.get('required_edit_history', {}).get(f'{ns}/{page}')
        if wanted_edits is not None:
            require(len(edits) == cursor == wanted_edits, 'undo/redo/erase history differs')
    observed = {identity: join_chunks(items) for identity, items in strokes.items()}
    actions = [action for action in stream.actions if action['kind'] == 'stroke']
    require(len(observed) == len(actions), 'extra or missing retained stroke')
    names = {}
    for action in actions:
        samples = stream.events[action['first_sequence'] - 1:action['last_sequence']]
        matches = [stroke for (ns, stroke), actual in observed.items()
                   if ns == action['namespace'] and actual == samples]
        require(len(matches) == 1, f"raw stroke {action['name']} not retained exactly once")
        names[action['namespace'], action['name']] = matches[0]
        require({header[7] for header, _ in strokes[action['namespace'], matches[0]]} == {action['brush_q8']},
                'brush selection lost from immutable raw stroke')
    for identity, wanted in expected['visible_strokes'].items():
        ns, page = map(int, identity.split('/'))
        require(visible[ns, page] == {names[ns, name] for name in wanted},
                'undo/redo/erase result differs')
    events = guest_events(serial)
    states = [row for row in events if row[0] in (0x421, 0x423, 0x424)]
    require(states and states[-1] == (0x421, sequence, 1, 1, 0),
            'explicit Save has no current durable acknowledgement')
    require(any(row[0] == 0x423 and row[2:] == (1, 1, 0) for row in states[:-1]),
            'explicit Save never reported its pending state')
    require(not any(row[0] in (0x41f, 0x424, 0xd4) for row in events),
            'workflow formatted, failed or faulted')
    width, height, pixels = visible_pixels(panel)
    require((width, height) == (stream.width, stream.height), 'controller geometry differs')
    check_toolbar_pixels(width, height, pixels)
    points = []
    for action in actions:
        if (action['namespace'], action['page']) != (1, 1):
            continue
        sample = stream.events[action['first_sequence'] - 1]
        x, y = sample[2] * (width - 1) // 65535, sample[3] * (height - 1) // 65535
        dark = any(pixels[(py * width + px) * 3:(py * width + px) * 3 + 3] == bytes(3)
                   for py in range(y - 2, y + 3) for px in range(x - 2, x + 3))
        require(dark == (action['name'] in expected['visible_strokes']['1/1']),
                'actual final controller pixels differ at the original contact')
        points.append([action['name'], x, y, dark])
    return {'status': 'PASS', 'sequence': sequence, 'generation': root.generation,
            'raw_samples': sum(map(len, observed.values())), 'strokes': len(strokes),
            'pages': len(pages), 'documents': sorted(roots), 'contact_points': points,
            'explicit_save': states[-1], 'committed_objects': len(records)}


class PublicSession:
    def __init__(self, checker, name, disk, fail_flush=None):
        self.checker, self.directory = checker, checker.directory / name
        args = ['session', '--backend', getattr(checker, 'backend', 'qemu'), '--profile', checker.profile,
                '--workload', 'notebook', '--headless', '--paused', '--mode', 'laboratory',
                '--session-dir', str(self.directory), '--disk', str(disk),
                '--timeout', str(checker.args.timeout)]
        if getattr(checker.args, 'native_bundle', None):
            args += ['--native-bundle', checker.args.native_bundle]
        if getattr(checker.args, 'guest_build', None):
            args += ['--guest-build', checker.args.guest_build]
        if getattr(checker.args, 'guest_source_root', None):
            args += ['--guest-source-root', str(checker.args.guest_source_root)]
        if fail_flush:
            args += ['--fail-flush', str(fail_flush), '--trace-limit', '1000']
        self.log = (checker.directory / (name + '.log')).open('xb')
        try:
            self.process = checker.launch(args, stdout=self.log, stderr=subprocess.STDOUT,
                                          start_new_session=True)
            deadline = min(checker.deadline, time.monotonic() + 60)
            while not (self.directory / 'session.json').exists():
                require(self.process.poll() is None, 'public session exited before readiness; see ' + name + '.log')
                require(time.monotonic() < deadline, 'public session socket resource deadline')
                time.sleep(0.02)
            self.identity = self.inspect()['identity']
        except BaseException:
            if hasattr(self,'process') and self.process.poll() is None:
                os.killpg(self.process.pid,signal.SIGTERM)
                try:self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid,signal.SIGKILL);self.process.wait(timeout=5)
            self.log.close()
            raise

    def control(self, value):
        # Use the same bounded public wire protocol as `session-control`.
        # Repeated observation must not launch a new interpreter per clock
        # quantum. The owning session still executes every machine operation.
        remaining = self.checker.deadline - time.monotonic()
        require(remaining > 0, 'campaign host resource deadline')
        self.checker.commands.write(json.dumps({'session': str(self.directory),
            'request': value, 'transport': 'public-unix-socket'}) + '\n')
        self.checker.commands.flush()
        return session_request(self.directory, value,
                               timeout=min(self.checker.args.timeout + 30, remaining))

    def inspect(self):
        return self.control({'action': 'inspect'})

    def run(self, cycles):
        return self.control({'action': 'run', 'cycles': cycles})

    def wait(self, predicate, budget, quantum=5000000):
        initial = self.inspect()['machine']['cycle']
        while True:
            state = self.inspect()['machine']
            if predicate(state):
                return state
            require(state['cycle'] - initial < budget * 100000000, 'declared virtual milestone bound exceeded')
            require(not state['finished'], 'guest finished before milestone')
            self.run(min(quantum, budget * 100000000 - (state['cycle'] - initial)))

    def boot(self):
        def ready(state):
            records = guest_events(self.directory / 'uart-0.bin')
            return any(row[0] == 0x420 for row in records) and idle(state)
        started = time.monotonic()
        state = self.wait(ready, self.checker.args.boot_seconds)
        return {'virtual_seconds': state['virtual_ns'] / 1000000000,
                'host_seconds': time.monotonic() - started, 'cycle': state['cycle']}

    def admit(self, rows):
        for row in rows:
            self.control({'action': 'inject', 'kind': 'pen', 'cycle': row[1] * 10,
                          'words': list(row[1:8])})

    def settle(self, final_tick):
        def ready(state):
            states = [r for r in guest_events(self.directory / 'uart-0.bin') if r[0] in (0x421, 0x423, 0x424)]
            return state['ticks'] >= final_tick + 2000000 and idle(state) and states and states[-1][0] == 0x421
        return self.wait(ready, self.checker.args.action_seconds)

    def export(self, name):
        panel, medium = self.checker.directory / (name + '.ppm'), self.checker.directory / (name + '.raw')
        self.control({'action': 'panel', 'path': str(panel)})
        self.control({'action': 'export-medium', 'path': str(medium)})
        return panel, medium

    def snapshot(self, name):
        destination = self.checker.directory / name
        self.checker.command(['snapshot', '--session-dir', str(self.directory), '--to', str(destination)], True)
        return destination

    def close(self):
        try:
            if self.process.poll() is None:
                self.control({'action': 'destroy'})
                self.process.wait(timeout=10)
        finally:
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=5)
            self.log.close()


def idle(state):
    return state['devices']['pen']['count'] == 0 and not state['devices']['paper']['status'] & 1 and state['storage']['phase'] == 0


class Checker:
    profile = 'lemma-silicon-dev/0.2.0'
    def __init__(self, args):
        self.args, self.directory = args, args.work_dir.resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.commands = (self.directory / 'commands.jsonl').open('x')
        self.sessions = []
        self.started = time.monotonic()
        self.deadline = self.started + args.deadline
        self.report = {'schema': 'lemmasim-live-notebook-observations/1', 'status': 'FAIL',
                       'scope': 'real native selected-profile subset; total digital machine and physical closure remain unfinished',
                       'profile': self.profile, 'bounds': vars(args) | {'work_dir': str(self.directory),
                           'durable_suffix_from':str(args.durable_suffix_from) if args.durable_suffix_from else None},
                       'checkpoint_relation':args.checkpoint_relation,
                       'external_input': 'synthetic raw samples, literal pressure; no physical digitizer claim',
                       'observer_sources': {str(path.relative_to(ROOT)):sha(path) for path in
                           (Path(__file__), ROOT/'conformance/lemmasim/check_notebook_workflow.py',
                            ROOT/'conformance/lemmasim/inspect_notebook.py',
                            ROOT/'conformance/lemmasim/notebook_input.py',
                            ROOT/'conformance/lemmasim/store_oracle.py')},
                       'interactions': []}
        if args.checkpoint_relation == 'pinned-host-time-v1':
            observer = ROOT/'conformance/lemmasim/check_fast_state_equivalence.py'
            self.report['observer_sources'][str(observer.relative_to(ROOT))] = sha(observer)
            proof = ROOT/'conformance/lemmasim/QEMU_STATE_EQUIVALENCE.html'
            self.report['observer_sources'][str(proof.relative_to(ROOT))] = sha(proof)
            self.report['checkpoint_relation_detail'] = ('Exact every serialized byte except timer.cpu_ticks_offset '
                'and timer.cpu_clock_offset, two pinned host elapsed-time statistics; exact virtual nanoseconds, '
                'timer/icount, CPU, RAM, device private state, admitted raw fields, guest output, controller '
                'pixels and durable bytes. Unequal original containers and every differing byte remain reported.')

    def launch(self, args, **kwargs):
        require(time.monotonic() < self.deadline, 'campaign host resource deadline')
        command = [sys.executable, str(ROOT / 'scripts/lemmasim'), *args]
        self.commands.write(json.dumps(command) + '\n'); self.commands.flush()
        return subprocess.Popen(command, cwd=ROOT, **kwargs)

    def command(self, args, json_result=False):
        process = self.launch(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            out, err = process.communicate(timeout=min(self.args.timeout + 30, self.deadline-time.monotonic()))
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)
            raise
        require(process.returncode == 0, 'public command failed: ' + out.decode(errors='replace') + err.decode(errors='replace'))
        return json.loads(out) if json_result else out.decode()

    def session(self, name, disk, fail_flush=None):
        result = PublicSession(self, name, disk, fail_flush)
        self.sessions.append(result)
        return result

    def execute(self):
        if self.args.durable_suffix_from:
            return self.durable_suffix(self.args.durable_suffix_from.resolve())
        disk = self.directory / 'notebook.raw'
        self.command(['init', '--backend', 'qemu', '--profile', self.profile, '--disk', str(disk),
                      '--session-dir', str(self.directory / 'initializer'), '--timeout', str(self.args.timeout)])
        initialized = json.loads((self.directory / 'initializer/result.json').read_text())
        image = disk.read_bytes(); root, sequence, records = recover(image)
        require(initialized['status'] == 'ACKNOWLEDGED_GUEST_INITIALIZATION' and sequence == 0 and not records and
                root_slot(image[:512], len(image)//512) == root_slot(image[512:1024], len(image)//512) == root,
                'real initializer did not produce both durable empty roots')
        self.report['initialization'] = initialized
        live = self.session('live', disk)
        self.report['identity'] = live.identity
        self.report['boot'] = live.boot()
        width, height = 1650, 2200
        _, fixture = generate('editing', width, height, 0, 100000, 0)
        stream = Input(width, height, live.inspect()['machine']['ticks'] + 10000, 100000, 0)
        stream.sample(width//2, 160, 0, False)
        live.admit(stream.events); live.settle(stream.events[-1][1])
        for index, action in enumerate(fixture['actions']):
            action_started = time.monotonic()
            before = live.inspect()['machine']
            stream.tick = live.inspect()['machine']['ticks'] + 10000
            start = len(stream.events)
            if action['kind'] == 'stroke':
                stream.stroke(action['name'], action['page'], action['namespace'], action['raw_samples'],
                              height//2 if action['name'] in ('b', 'd') else height//3, action['brush_q8'])
            else:
                stream.tool(action['button'], action['name'])
            live.admit(stream.events[start:])
            if index == 0:
                active = live.wait(lambda state: bool(state['devices']['paper']['status'] & 1),
                                   self.args.action_seconds, quantum=200000)
                pending = live.snapshot('active-paper')
                self.report['snapshot_boundary'] = active
                self.raw_offset = (live.directory/'input-0.bin').stat().st_size
                self.uart_offset = (live.directory/'uart-0.bin').stat().st_size
            after = live.settle(stream.events[-1][1])
            self.report['interactions'].append({'name':action['name'], 'host_seconds':time.monotonic()-action_started,
                'virtual_seconds':(after['virtual_ns']-before['virtual_ns'])/1000000000,
                'last_sample_to_settled_ns':after['virtual_ns']-stream.events[-1][1]*100,
                'initial_cycle':before['cycle'],'final_cycle':after['cycle'],
                'initial_paper_completed':before['devices']['paper']['completed'],
                'final_paper_completed':after['devices']['paper']['completed']})
        (self.directory/'input.bin').write_bytes(b''.join(struct.pack('<9Q', *row) for row in stream.events))
        (self.directory/'input.json').write_text(json.dumps({'profile': self.profile, 'geometry': [width,height],
             'actions': stream.actions, 'expected': fixture['expected']}, indent=2)+'\n')
        panel, medium = live.export('acknowledged')
        self.report['workflow'] = observe_workflow(medium, live.directory/'input-0.bin',
             live.directory/'uart-0.bin', panel, stream, fixture['expected'])
        self.report['workflow'].update(durable_sha256=sha(medium), controller_pixels_sha256=sha(panel))
        baseline = live.inspect()['machine']
        final_snapshot = live.snapshot('final-original')
        capture = self.directory/'original-external.jsonl'
        shutil.copyfile(live.directory/'external.jsonl', capture)
        original_medium_hash = sha(disk)
        self.command(['session-replay','--session-dir',str(live.directory),'--snapshot',str(pending),
                      '--capture',str(capture),'--until-ns',str(baseline['virtual_ns'])], True)
        replay_state = live.inspect()['machine']
        replay_snapshot = live.snapshot('final-replayed')
        replay_panel, replay_medium = live.export('replayed')
        fork = max(live.directory.glob('machine-fork-*'), key=lambda p: p.stat().st_mtime_ns)
        require(baseline == replay_state, 'same-backend replay final CPU/device/time/storage state differs')
        if self.args.checkpoint_relation == 'exact-container':
            require(sha(final_snapshot/'machine.chk') == sha(replay_snapshot/'machine.chk'),
                    'same-backend replay exact full checkpoint differs')
        else:
            observer = ROOT/'conformance/lemmasim/check_fast_state_equivalence.py'
            observation = self.directory/'checkpoint-state-equivalence.json'
            require(sha(observer) == self.report['observer_sources'][str(observer.relative_to(ROOT))],
                    'checkpoint observer changed during workload')
            prepared = json.loads((ROOT/'build/lemmasim/fast-prepared-0.2.0.json').read_text())
            command = [sys.executable,str(observer),'--left',str(final_snapshot/'machine.chk'),
                '--right',str(replay_snapshot/'machine.chk'),'--qemu',prepared['qemu']['path'],
                '--output',str(observation)]
            self.commands.write(json.dumps(command)+'\n');self.commands.flush()
            result = subprocess.run(command,cwd=ROOT,capture_output=True,text=True,
                timeout=min(self.args.timeout,self.deadline-time.monotonic()))
            self.report['checkpoint_observation'] = json.loads(observation.read_text())
            self.report['checkpoint_observer_sha256'] = sha(observer)
            require(result.returncode == 0 and self.report['checkpoint_observation']['status'] == 'PASS',
                    'pinned checkpoint state observation failed: '+result.stdout+result.stderr)
        require(sha(panel) == sha(replay_panel) and sha(medium) == sha(replay_medium),
                'same-backend replay controller output or durable bytes differ')
        require((live.directory/'input-0.bin').read_bytes()[self.raw_offset:] == (fork/'input-1.bin').read_bytes() and
                (live.directory/'uart-0.bin').read_bytes()[self.uart_offset:] == (fork/'uart-1.bin').read_bytes(),
                'same-backend replay emitted raw or guest suffix differs')
        require(sha(disk) == original_medium_hash, 'restored fork mutated original user medium')
        self.report['replay'] = {'status':'PASS','relation':self.args.checkpoint_relation,
                                'original_container_sha256':sha(final_snapshot/'machine.chk'),
                                'replayed_container_sha256':sha(replay_snapshot/'machine.chk'),
                                'cycle':replay_state['cycle'],'isolated_original_unchanged':True}
        live.close(); self.sessions.remove(live)
        self.cold_recovery(medium, panel)
        self.failed_barrier(medium, panel)
        self.report['status'] = 'PASS'

    def cold_recovery(self, medium, panel):
        cold_disk = self.directory/'cold-input.raw'; shutil.copyfile(medium, cold_disk)
        cold = self.session('cold', cold_disk)
        self.report['cold_identity'] = cold.identity
        self.report['cold_boot'] = cold.boot()
        cold_panel, cold_medium = cold.export('cold')
        require(committed_bytes(medium) == committed_bytes(cold_medium) and sha(medium) == sha(cold_medium),
                'new cold guest lost or changed acknowledged durable bytes')
        require(visible_pixels(panel) == visible_pixels(cold_panel), 'new cold guest redraw pixels differ')
        cold_events = guest_events(cold.directory/'uart-0.bin')
        require(sum(row[0] == 0x420 for row in cold_events) == 1 and
                not any(row[0] in (0x41f,0x423,0x424) for row in cold_events) and
                cold.inspect()['machine']['devices']['paper']['completed'] > 0,
                'new cold guest formatted, republished, failed, or omitted real controller redraw')
        cold.close(); self.sessions.remove(cold)
        self.report['cold_recovery'] = {'status':'PASS','exact_acknowledged_medium_and_pixels':True,
            'durable_sha256':sha(cold_medium),'controller_pixels_sha256':sha(cold_panel),
            'boot_state':'new process, original guest ELF and copied durable bytes only'}

    def durable_suffix(self, source):
        """New CPU boots using an independently rechecked actual durable run.

        This cheaper suffix retains the earlier execution's identity, including
        any FAIL. It never relabels earlier replay as passing or supplies parsed
        recovery results to a guest.
        """
        report = json.loads((source/'result.json').read_text())
        require(report.get('profile') == self.profile and report.get('workflow',{}).get('status') == 'PASS',
                'durable suffix requires an actual acknowledged workflow')
        for name in ('input.bin','input.json','live/input-0.bin','live/uart-0.bin','acknowledged.ppm'):
            require(sha(source/name) == report['artifacts'][name]['sha256'], 'changed original workflow observation')
        medium,panel = source/'acknowledged.raw',source/'acknowledged.ppm'
        require(sha(medium) == report['workflow']['durable_sha256'] and
                sha(panel) == report['workflow']['controller_pixels_sha256'], 'changed original durable/controller bytes')
        fixture = json.loads((source/'input.json').read_text())
        stream = Input(*fixture['geometry'],0,100000,0)
        raw = (source/'input.bin').read_bytes()
        require(len(raw)%72 == 0, 'truncated original raw samples')
        stream.events = [struct.unpack_from('<9Q',raw,i) for i in range(0,len(raw),72)]
        stream.actions = fixture['actions']
        observed = observe_workflow(medium,source/'live/input-0.bin',source/'live/uart-0.bin',
                                    panel,stream,fixture['expected'])
        self.report['prior_workflow'] = {'path':str(source),'original_identity':report['identity'],
            'original_status':report['status'],'original_error':report.get('error'),
            'result_sha256':sha(source/'result.json'),'independent_recheck':observed}
        if not self.args.failure_only:
            self.cold_recovery(medium,panel)
        self.failed_barrier(medium,panel)
        self.report['status'] = 'PASS'
        self.report['scope'] = ('new native failed-FLUSH and new-cold suffix only' if self.args.failure_only else
            'new native cold and failed-FLUSH suffix only') + '; earlier exact-checkpoint mismatch is retained separately'

    def failed_barrier(self, acknowledged, acknowledged_panel):
        disk = self.directory/'failed-input.raw'; shutil.copyfile(acknowledged, disk)
        failed = self.session('failed', disk, 1); failed.boot()
        stream = Input(1650,2200,failed.inspect()['machine']['ticks']+10000,100000,0)
        stream.sample(825,160,0,False);stream.stroke('failed new ink',1,1,6,1700)
        failed.admit(stream.events)
        state = failed.wait(lambda state: any(row[0] == 0x424 for row in guest_events(failed.directory/'uart-0.bin'))
                            and idle(state), self.args.action_seconds)
        # The guest's status redraw follows its failure report. Allow the same
        # predeclared 200ms settling interval as the ordinary input workflow.
        failed.run(20000000)
        failed.wait(idle, self.args.action_seconds)
        panel, medium = failed.export('failed')
        events = [row for row in guest_events(failed.directory/'uart-0.bin') if row[0] in (0x421,0x423,0x424)]
        require(events and events[-1][0:2] == (0x424,227) and not any(row[0] == 0x421 for row in events),
                'failed persistence fabricated Saved or did not expose transportFailed')
        require(sha(medium) == sha(acknowledged), 'failed first FLUSH changed acknowledged durable bytes')
        width,height,pixels = visible_pixels(panel)
        rows = {'F':('111','100','110','100','100'),'A':('010','101','111','101','101'),
                'I':('111','010','010','010','111'),'L':('100','100','100','100','111'),
                'E':('111','100','110','100','111'),'D':('110','101','101','101','110')}
        for i,char in enumerate('FAILED'):
            for y in range(15):
                for x in range(12):
                    expected = bytes([0 if x<9 and rows[char][y//3][x//3]=='1' else 255])*3
                    offset = ((132+y)*width+24+i*12+x)*3
                    require(pixels[offset:offset+3] == expected, 'guest Failed label absent from completed controller pixels')
        failed.close(); self.sessions.remove(failed)
        trace = (failed.directory/'media-0.log').read_text()
        require(' flush-failed 1 0 ' in trace and 'flush-durable' not in trace,
                'actual medium barrier failure missing or fabricated successful barrier')
        cold = self.session('failed-cold', medium)
        cold_boot = cold.boot()
        cold_panel,cold_medium = cold.export('failed-cold')
        require(sha(cold_medium) == sha(acknowledged) and
                visible_pixels(cold_panel) == visible_pixels(acknowledged_panel),
                'cold recovery after failed FLUSH lost acknowledged bytes or displayed failed provisional ink')
        require(not any(row[0] in (0x41f,0x423,0x424) for row in guest_events(cold.directory/'uart-0.bin')),
                'cold failure recovery formatted, republished or failed')
        cold.close();self.sessions.remove(cold)
        self.report['failed_flush'] = {'status':'PASS','guest_states':events,'snapshot':state,
                                     'acknowledged_medium_unchanged':True,'controller_failed_label':True,
                                     'durable_sha256':sha(medium),
                                     'new_cold_recovery':cold_boot,'failed_provisional_ink_not_recovered':True}

    def close(self):
        for session in list(self.sessions):
            try: session.close()
            except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired): pass
        self.commands.close()
        self.report['elapsed_seconds'] = time.monotonic()-self.started
        self.report['artifacts'] = {str(path.relative_to(self.directory)):{'bytes':path.stat().st_size,'sha256':sha(path)}
           for path in sorted(self.directory.rglob('*')) if path.is_file() and path.name not in ('result.json',)
           and path.suffix not in ('.raw','.chk')}
        (self.directory/'result.json').write_text(json.dumps(self.report,indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--timeout',type=int,default=300,help='Each public operation host deadline, seconds')
    parser.add_argument('--boot-seconds',type=int,default=30,help='Predeclared virtual cold readiness bound')
    parser.add_argument('--action-seconds',type=int,default=30,help='Predeclared virtual action milestone bound')
    parser.add_argument('--deadline',type=int,default=2400,help='Entire campaign host resource bound, seconds')
    parser.add_argument('--durable-suffix-from',type=Path,
                        help='Recheck an actual acknowledged workflow, then run only new cold/failure boots')
    parser.add_argument('--failure-only',action='store_true',
                        help='With --durable-suffix-from, run the failed barrier and its new cold recovery only')
    parser.add_argument('--checkpoint-relation',choices=('exact-container','pinned-host-time-v1'),
                        default='exact-container',
                        help='Predeclared checkpoint relation; named host statistics require the pinned independent observer')
    args = parser.parse_args()
    require(1<=args.timeout<=3600 and 1<=args.boot_seconds<=600 and 1<=args.action_seconds<=600 and
            1<=args.deadline<=7200,'invalid declared bounds')
    require(not args.failure_only or args.durable_suffix_from is not None,
            '--failure-only requires a source-bound actual durable workflow')
    checker = Checker(args)
    try: checker.execute()
    except BaseException as error:
        checker.report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        checker.close()
        print(json.dumps({key:checker.report[key] for key in ('status','error') if key in checker.report}))


if __name__ == '__main__':
    main()
