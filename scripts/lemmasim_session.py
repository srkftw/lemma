#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Persistent machine transport and presentation. All notebook work stays in RV64.

One owner thread advances the machine and accepts external samples between bounded
intervals. The Unix socket carries lifecycle controls, never notebook operations.
"""
from __future__ import annotations
import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import selectors
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
MAX_REQUEST = 65536
MAX_EVENTS = 1000000


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def write_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def bounded(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{label} must be {minimum}..{maximum}')
    return value


def checkpoint_inventory(source, manifest):
    """Validate the complete bounded file set before choosing/applying backing."""
    files = manifest.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= 16:
        raise ValueError('Missing or oversized checkpoint inventory')
    names = set()
    total_bytes = 0
    for item in files:
        if not isinstance(item,dict) or set(item)!={'path','bytes','sha256'}:
            raise ValueError('Malformed checkpoint file identity')
        name = item['path']
        if not isinstance(name, str) or name in names or not name or Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('Invalid checkpoint path')
        if not isinstance(item['sha256'],str) or len(item['sha256'])!=64 or any(c not in '0123456789abcdef' for c in item['sha256']):
            raise ValueError('Malformed checkpoint checksum')
        path = source / name
        names.add(name)
        if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
            raise ValueError('Missing or symlinked checkpoint state')
        bounded(item['bytes'], 1, 768 * 1024 * 1024, 'Checkpoint bytes')
        total_bytes += item['bytes']
        if total_bytes > 1024 * 1024 * 1024:
            raise ValueError('Checkpoint exceeds aggregate resource bound')
        if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise ValueError('Checkpoint length/checksum mismatch')
    if 'machine.chk' not in names:
        raise ValueError('Missing machine state')
    return names


def startup_restore_medium(args):
    """Choose optional fast backing from verified state, never a user disk."""
    if not args.restore:
        return False
    if args.disk is not None:
        raise ValueError('A restored fork owns its checkpoint backing; omit --disk')
    if args.workload == 'service':
        return False
    if args.workload != 'power':
        return True
    if args.backend == 'rtl':
        # Its exact container owns the optional backing, including its presence.
        return False
    source = Path(args.restore).resolve()
    path = source / 'snapshot.json'
    with path.open('rb') as stream:
        wire = stream.read(MAX_REQUEST + 1)
    if len(wire) > MAX_REQUEST:
        raise ValueError('Snapshot manifest exceeds its bound')
    manifest = json.loads(wire)
    if not isinstance(manifest, dict) or manifest.get('schema') != 'lemmasim-session/1':
        raise ValueError('Unsupported snapshot manifest')
    names = checkpoint_inventory(source, manifest)
    if names not in ({'machine.chk', 'clock.json'}, {'machine.chk', 'clock.json', 'durable.raw'}):
        raise ValueError('Power checkpoint inventory differs from required fast state')
    if 'durable.raw' in names and (source / 'durable.raw').stat().st_size != 256 * 1024 * 1024:
        raise ValueError('Power checkpoint medium length differs')
    return 'durable.raw' in names


def external_command(value, current):
    if not isinstance(value,dict):raise ValueError('External request must be an object')
    if value.get('action') in ('warm-reset','cold-cycle'):return value['action'],dict(value)
    if value.get('action')!='inject':raise ValueError('Unsupported external action')
    cycle=bounded(value.get('cycle',current),current,(1<<64)-1,'Event cycle')
    kind=value.get('kind')
    if kind=='pen':
        words=value.get('words')
        if not isinstance(words,list) or len(words)!=7:raise ValueError('Pen requires time,x,y,pressure,flags,tool,buttons')
        for word,(low,high) in zip(words,((0,(1<<64)-1),(0,65535),(0,65535),(0,4095),(0,15),(0,2),(0,7))):
            bounded(word,low,high,'Pen field')
        command=f'inject {cycle} pen '+' '.join(map(str,words))
    elif kind=='uart':
        payload=value.get('hex','')
        if not isinstance(payload,str) or not 2<=len(payload)<=8192 or len(payload)%2 or any(c not in '0123456789abcdefABCDEF' for c in payload):
            raise ValueError('UART requires1..4096 literal hex bytes')
        command=f'inject {cycle} uart {payload}'
    elif kind=='button':
        level=bounded(value.get('level'),0,1,'Button level')
        command=f'inject {cycle} button {level}'
    else:raise ValueError('Unsupported external event')
    return command,dict(value,cycle=cycle)


def request(directory, value, timeout=120):
    directory = Path(directory).resolve()
    metadata = json.loads((directory / 'session.json').read_text())
    wire = json.dumps(value, separators=(',', ':')).encode() + b'\n'
    if len(wire) > MAX_REQUEST:
        raise ValueError('Session request exceeds 64 KiB')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(metadata['socket'])
        connection.sendall(wire)
        response = bytearray()
        while b'\n' not in response:
            part = connection.recv(4096)
            if not part:
                raise RuntimeError('Session closed without a response')
            response += part
            if len(response) > MAX_REQUEST:
                raise ValueError('Oversized session response')
    result = json.loads(response.split(b'\n', 1)[0])
    if result.get('ok') is not True:
        raise RuntimeError(result.get('error', 'Machine operation failed'))
    return result['result']


class RTL:
    """Machine owner; only byte/sample/lifecycle operations cross this boundary."""
    def __init__(self, args, directory):
        import silicon_guest
        self.data = silicon_guest.prepared(args.workload, args.profile)
        self.identity = {'backend': 'rtl', 'profile': self.data['profile'],
                         'runtime': self.data['binary']['sha256'],
                         'rom': self.data['rom']['sha256'],
                         'guest': self.data['workloads'][args.workload]['image']['sha256'],
                         'dtb': self.data['workloads'][args.workload]['dtb']['sha256'],
                         'descriptor': self.data['workloads'][args.workload]['descriptor']['sha256']}
        entry = self.data['workloads'][args.workload]
        self.log = (directory / 'machine.log').open('wb')
        command = [self.data['binary']['path'], '--image', entry['image']['path'],
                   '--rom', self.data['rom']['path'], '--load',
                   f"0x{silicon_guest.profile(self.data['profile'])['dtb_base']:x}:{entry['dtb']['path']}",
                   '--session', '--quiet-uart', '--uart-output', str(directory / 'uart.bin'),
                   '--input-capture', str(directory / 'input.events'),
                   '--fork-directory',str(directory),
                   '--trace-limit', str(args.trace_limit), '--deadline', str(args.timeout)]
        replay = getattr(args, 'backing_replay', None)
        if replay is not None:
            if not args.restore:
                raise ValueError('Backing outcome replay requires --restore into an isolated fork')
            command += ['--backing-replay', str(replay.resolve())]
        else:
            command += ['--backing-capture', str(directory / 'backing.io')]
        if args.memory_latency:
            command += ['--memory-latency', str(args.memory_latency)]
        if args.fail_flush:
            command += ['--fail-flush', str(args.fail_flush)]
        companion = getattr(args, 'companion', None)
        if companion is not None:
            import lemmasim_companion
            peer = lemmasim_companion.peer_info(companion)
            prepared = lemmasim_companion.validate(args.companion_prepared)
            command += ['--companion-client', prepared['binaries']['companion-client']['path'],
                        '--companion-socket', str(args.companion_socket.resolve()),
                        '--companion-state', str(args.companion_state.resolve()),
                        '--companion-writer', str(peer['writer']),
                        '--companion-helper', str(ROOT/'sim/companion/os_io.py')]
        if args.workload != 'service':
            if args.disk is None and companion is None and args.workload != 'power':
                raise ValueError('This workload requires an existing --disk or companion backing')
            command += ['--descriptor', entry['descriptor']['path']]
            if args.disk is not None:
                command += ['--medium', str(args.disk.resolve())]
        if args.events:
            command += ['--events', str(args.events.resolve())]
        self.process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.log,
                                        start_new_session=True, bufsize=0)
        self.reader = selectors.DefaultSelector()
        self.reader.register(self.process.stdout, selectors.EVENT_READ)
        self.pending = bytearray()
        self.timeout = args.timeout
        self.argv = command
        self.input_kinds={'pen','uart','button'} if self.data['profile']=='lemma-silicon-dev/0.3.0' else {'pen','uart'}
        # The first operation validates that the actual executable supports the
        # runtime interface; an old prepared harness cannot become a session.
        try:self.checkpoint_identity=self.call('inspect')['snapshot_identity']
        except BaseException:
            if self.process.poll() is None:os.killpg(self.process.pid,signal.SIGKILL)
            self.process.wait(timeout=5);self.reader.close();self.log.close()
            raise

    def call(self, command):
        if '\n' in command or '\r' in command or len(command.encode()) > MAX_REQUEST:
            raise ValueError('Invalid runtime command')
        self.process.stdin.write(command.encode() + b'\n')
        self.process.stdin.flush()
        until = time.monotonic() + self.timeout + 5
        while b'\n' not in self.pending:
            remaining = until - time.monotonic()
            if remaining <= 0 or not self.reader.select(remaining):
                raise TimeoutError('Machine interval exceeded its host resource deadline')
            part = os.read(self.process.stdout.fileno(), 4096)
            if not part:
                raise RuntimeError('RTL runtime exited: see machine.log')
            self.pending += part
            if len(self.pending) > MAX_REQUEST:
                raise RuntimeError('Runtime response exceeds its bound')
        line, _, self.pending = self.pending.partition(b'\n')
        value = json.loads(line)
        if value.get('ok') is False or 'error' in value:
            raise RuntimeError(value.get('error', 'RTL operation failed'))
        return value.get('result', value)

    def preflight_checkpoint(self, path, expected_cycle):
        # LMSSRTL1/v1's wrapper follows its 112-byte container header.
        # event_index is the first u64; cycle is the second. Session has
        # already verified the complete file's length and SHA256 inventory.
        # The runtime performs CRC/state/model validation before adoption.
        # Check the sidecar boundary here so a mismatch cannot be discovered
        # only after the live processor and medium have been replaced.
        path = Path(path)
        with path.open('rb') as stream:
            header = stream.read(128)
        if (len(header) != 128 or header[:8] != b'LMSSRTL1' or
                int.from_bytes(header[8:16], 'little') != 1 or
                header[16:80] != self.checkpoint_identity.encode('ascii')):
            raise ValueError('Unsupported RTL checkpoint boundary format or identity')
        wrapper_bytes = int.from_bytes(header[80:88], 'little')
        model_bytes = int.from_bytes(header[88:96], 'little')
        if (wrapper_bytes < 16 or not 0 < model_bytes <= 64 * 1024 * 1024 or
                112 + wrapper_bytes + model_bytes != path.stat().st_size):
            raise ValueError('Invalid RTL checkpoint boundary lengths')
        if int.from_bytes(header[120:128], 'little') != expected_cycle:
            raise ValueError('Snapshot metadata differs from its saved virtual cycle')

    def close(self):
        try:
            if self.process.poll() is None:
                self.call('destroy')
                self.process.wait(timeout=5)
        finally:
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=5)
            self.reader.close()
            self.log.close()


class Session:
    def __init__(self, machine, directory, args):
        self.machine, self.directory = machine, directory
        self.mode = args.mode
        self.automatic = not args.paused
        self.quantum = args.quantum
        self.event_count = 0
        self.event_cursor = 0
        self.closed = False
        self.capture = (directory / 'external.jsonl').open('x')
        self.started = time.monotonic()
        self.run_seconds = 0.0
        self.run_cycles = 0
        self.adapter = None
        self.disconnect_adapter = None
        self.last_error = None
        self.capture_uncertain = False
        self.presentation_generation = 0

    def ensure_capture_certain(self):
        if self.capture_uncertain:
            raise RuntimeError('External admission is uncertain; inspect/export or destroy this session')

    def capture_failed(self, error):
        # Neither a lost backend response nor a failed capture write proves
        # that no external event reached the machine. Keep the attempted row
        # and stop this timeline; its cursor cannot safely be advanced/reused.
        self.capture_uncertain = True
        self.automatic = False
        self.last_error = 'External admission is uncertain: ' + str(error)

    def external(self, value, state, command):
        self.ensure_capture_certain()
        wire = json.dumps({'admission': 'pending', 'ordinal': self.event_count, 'cursor': self.event_cursor, 'cycle': state['cycle'],
                           'virtual_ns': state.get('virtual_ns'), 'request': value}, separators=(',', ':')) + '\n'
        try:
            position = self.capture.tell()
        except (OSError, ValueError) as error:
            self.capture_failed(error)
            raise
        if self.event_count >= MAX_EVENTS or position + len(wire.encode()) > 256 * 1024 * 1024:
            raise ValueError('External event capture exhausted; start a new session')
        # Reserve and flush the complete pending record before device mutation.
        # JSON's ASCII escaping makes stream positions equal to byte offsets.
        try:
            if self.capture.write(wire) != len(wire):
                raise OSError('Incomplete pending external capture write')
            self.capture.flush()
        except (OSError, ValueError) as error:
            self.capture_failed(error)
            raise
        try:
            result = self.machine.call(command)
            # Both markers occupy seven bytes. Change only the admission field;
            # the raw sample, admission phase and row boundaries stay untouched.
            self.capture.seek(position + len('{"admission":"'))
            if self.capture.write('applied') != len('applied'):
                raise OSError('Incomplete external admission acknowledgement')
            self.capture.flush()
            self.capture.seek(position + len(wire))
        except BaseException as error:
            self.capture_failed(error)
            raise
        self.event_count += 1
        self.event_cursor += 1
        return result

    def run(self, cycles):
        self.ensure_capture_certain()
        started = time.monotonic()
        try:
            before = (self.machine.clock() if hasattr(self.machine,'clock') else self.machine.call('inspect'))['cycle']
            result = self.machine.call(f'run {cycles}')
        except (RuntimeError,OSError,ValueError) as error:
            self.automatic=False;self.last_error=str(error)
            raise
        self.run_seconds += time.monotonic() - started
        self.run_cycles += result['cycle'] - before
        if result.get('finished'):
            self.automatic = False
        return result

    def snapshot(self, destination):
        self.ensure_capture_certain()
        destination = Path(destination).resolve()
        destination.mkdir(parents=True, exist_ok=False)
        result = self.machine.call('snapshot ' + str(destination / 'machine.chk'))
        files = [{'path': str(p.relative_to(destination)), 'bytes': p.stat().st_size,
                  'sha256': digest(p)} for p in sorted(destination.rglob('*')) if p.is_file()]
        if not files:
            raise RuntimeError('Runtime produced no checkpoint')
        write_json(destination / 'snapshot.json',
                   {'schema': 'lemmasim-session/1', 'identity': self.machine.identity,
                    'boundary': getattr(self.machine, 'boundary', 'completed RTL rising edge; no drain, flush or reset'),
                    'automatic': self.automatic, 'quantum': self.quantum,
                    'external_event_cursor': self.event_cursor,
                    'capture_start_ordinal': self.event_count,
                    'virtual_cycle': result['cycle'],
                    'virtual_ns':result.get('virtual_ns'),
                    'medium_policy': 'restore owns isolated checkpoint bytes; source medium is never overwritten',
                    'files': files})
        return {'snapshot': str(destination), 'machine': result}

    def restore(self, source):
        self.ensure_capture_certain()
        source = Path(source).resolve()
        if (source / 'snapshot.json').stat().st_size > MAX_REQUEST:
            raise ValueError('Snapshot manifest exceeds its bound')
        manifest = json.loads((source / 'snapshot.json').read_text())
        if not isinstance(manifest, dict):
            raise ValueError('Snapshot manifest must be an object')
        if manifest.get('schema') != 'lemmasim-session/1' or manifest.get('identity') != self.machine.identity:
            raise ValueError('Snapshot machine/implementation/guest identity mismatch')
        if type(manifest.get('automatic')) is not bool:
            raise ValueError('Missing snapshot pacing state')
        quantum = bounded(manifest.get('quantum'), 1, 1000000, 'Quantum')
        cursor = bounded(manifest.get('external_event_cursor'), 0, MAX_EVENTS, 'External cursor')
        cycle=bounded(manifest.get('virtual_cycle'),0,(1<<64)-1,'Snapshot cycle')
        phase=None
        if hasattr(self.machine,'restore_checkpoint'):
            phase=bounded(manifest.get('virtual_ns'),0,(1<<63)-1,'Snapshot virtual phase')
            if (phase*self.machine.clock_hz+999999999)//1000000000!=cycle:
                raise ValueError('Snapshot cycle and virtual phase disagree')
        names = checkpoint_inventory(source, manifest)
        if names!=getattr(self.machine,'checkpoint_files',{'machine.chk'}):
            raise ValueError('Checkpoint inventory differs from required backend state')
        if hasattr(self.machine, 'preflight_checkpoint'):
            self.machine.preflight_checkpoint(source / 'machine.chk', cycle)
        if self.disconnect_adapter:
            self.disconnect_adapter()
        result = (self.machine.restore_checkpoint(source/'machine.chk',phase)
                  if hasattr(self.machine,'restore_checkpoint') else self.machine.call('restore ' + str(source / 'machine.chk')))
        if result['cycle']!=cycle:raise ValueError('Snapshot metadata differs from its saved virtual cycle')
        self.automatic = manifest['automatic']
        self.quantum = quantum
        self.event_cursor = cursor
        self.presentation_generation += 1
        return {'restored': str(source), 'machine': result,
                'medium': 'isolated snapshot fork', 'external_event_cursor': manifest['external_event_cursor']}

    def replay(self, source, capture, until, until_ns=None):
        """Replay admitted external requests at their original owner boundaries."""
        self.ensure_capture_certain()
        source, capture = Path(source).resolve(), Path(capture).resolve()
        if capture == (self.directory/'external.jsonl').resolve():
            raise ValueError('Replay requires a closed capture copy outside the live session')
        if capture.stat().st_size > 256*1024*1024:
            raise ValueError('Replay capture exceeds256MiB')
        if (source/'snapshot.json').stat().st_size>MAX_REQUEST:raise ValueError('Snapshot manifest exceeds its bound')
        manifest=json.loads((source/'snapshot.json').read_text())
        if not isinstance(manifest,dict):raise ValueError('Snapshot manifest must be an object')
        if manifest.get('schema')!='lemmasim-session/1' or manifest.get('identity')!=self.machine.identity:
            raise ValueError('Replay machine/implementation/guest identity mismatch')
        start=bounded(manifest.get('capture_start_ordinal'),0,MAX_EVENTS,'Capture ordinal')
        phased=hasattr(self.machine,'run_until_ns')
        if until_ns is not None and not phased:raise ValueError('Nanosecond replay endpoints require the fast backend')
        if until_ns is not None:
            until_ns=bounded(until_ns,0,(1<<63)-1,'Replay final nanoseconds')
            until=(until_ns*self.machine.clock_hz+999999999)//1000000000
        else:
            until=bounded(until,0,(1<<64)-1,'Replay final cycle')
            if phased:until_ns=bounded(until*1000000000//self.machine.clock_hz,0,(1<<63)-1,'Replay final nanoseconds')
        rows=[]
        expected=bounded(manifest.get('external_event_cursor'),0,MAX_EVENTS,'External cursor')
        previous=bounded(manifest.get('virtual_cycle'),0,(1<<64)-1,'Snapshot cycle')
        if until<previous:raise ValueError('Replay final cycle precedes snapshot')
        previous_ns=None
        if phased:
            previous_ns=bounded(manifest.get('virtual_ns'),0,(1<<63)-1,'Snapshot virtual phase')
            if (previous_ns*self.machine.clock_hz+999999999)//1000000000!=previous:
                raise ValueError('Snapshot cycle and virtual phase disagree')
            if until_ns<previous_ns:raise ValueError('Replay endpoint precedes snapshot virtual phase')
        # Validate a bounded, unambiguous timeline before changing the machine.
        previous_ordinal = -1
        with capture.open() as stream:
            for index,line in enumerate(stream):
                if index>=MAX_EVENTS or len(line)>MAX_REQUEST: raise ValueError('Replay record bound exceeded')
                row=json.loads(line)
                if not isinstance(row,dict):raise ValueError('Replay record must be an object')
                if 'admission' in row and row['admission'] != 'applied':
                    raise ValueError('Replay capture contains an uncertain external admission')
                bounded(row.get('ordinal'),0,MAX_EVENTS,'Event ordinal')
                if row['ordinal'] <= previous_ordinal:
                    raise ValueError('Replay capture ordinals are not strictly increasing')
                previous_ordinal = row['ordinal']
                bounded(row.get('cursor'),0,MAX_EVENTS,'Event cursor')
                bounded(row.get('cycle'),0,(1<<64)-1,'Admission cycle')
                if row['ordinal']<start: continue
                if row['cursor']!=expected: raise ValueError('Capture contains another restored timeline; select a bounded suffix')
                if row['cycle']<previous:raise ValueError('Replay admission cycles are not monotone')
                if phased:
                    phase=bounded(row.get('virtual_ns'),0,(1<<63)-1,'External admission phase')
                    if phase<previous_ns or (phase*self.machine.clock_hz+999999999)//1000000000!=row['cycle']:
                        raise ValueError('Replay cycle and virtual phase disagree')
                    previous_ns=phase
                external_command(row['request'],row['cycle'])
                if row['request'].get('action')=='inject' and row['request'].get('kind') not in getattr(self.machine,'input_kinds',{'pen','uart'}):
                    raise ValueError('Replay input is unsupported by this backend')
                previous=row['cycle']
                expected+=1
                if (row['virtual_ns']<=until_ns if phased else row['cycle']<=until):rows.append(row)
        self.restore(source)
        self.automatic=False
        count=0
        for row in rows:
            if phased:
                self.run_clock(row['virtual_ns'])
                admitted=dict(row['request']);admitted.pop('source',None)
                self.dispatch(admitted);count+=1
                continue
            now=self.machine.call('inspect')['cycle']
            if row['cycle']<now: raise ValueError('Replay admission precedes current virtual cycle')
            if row['cycle']>now: self.run(row['cycle']-now)
            admitted=dict(row['request'])
            # Ownership metadata identifies a live adapter connection, not a
            # device field. Recorded ingress is supplied by this replay owner.
            admitted.pop('source',None)
            self.dispatch(admitted);count+=1
        now=self.machine.call('inspect')['cycle']
        if until<now: raise ValueError('Replay final cycle precedes state boundary')
        if phased:self.run_clock(until_ns)
        elif until>now: self.run(until-now)
        return {'replayed_events':count,'machine':self.machine.call('inspect'),
                'scope':'same-backend external input continuation; no automatic cross-backend equivalence claim'}

    def run_clock(self, ns):
        self.ensure_capture_certain()
        started=time.monotonic()
        try:
            before=self.machine.clock()
            if ns<before['virtual_ns']:raise ValueError('Replay admission precedes current virtual phase')
            # Keep each delegated interval within the ordinary one-billion-
            # cycle resource bound, even for a long closed capture suffix.
            result=before
            span=1000000000*1000000000//self.machine.clock_hz
            while result['virtual_ns']<ns:
                result=self.machine.run_until_ns(min(ns,result['virtual_ns']+span))
                if result['virtual_ns']>ns:raise ValueError('Fast replay could not reach its exact recorded phase')
                if result.get('finished') and result['virtual_ns']<ns:raise ValueError('Guest ended before replay phase')
        except (RuntimeError,OSError,ValueError) as error:
            self.automatic=False;self.last_error=str(error);raise
        self.run_seconds+=time.monotonic()-started
        self.run_cycles+=result['cycle']-before['cycle']
        return result

    def dispatch(self, value):
        if not isinstance(value, dict):
            raise ValueError('Session request must be an object')
        action = value.get('action')
        if action in ('run','resume','inject','warm-reset','cold-cycle','snapshot','restore','replay'):
            self.ensure_capture_certain()
        if value.get('source')=='tablet' and (not self.adapter or not self.adapter().get('tablet',{}).get('connected')):
            raise ValueError('Live tablet is disconnected; use recorded replay or reconnect explicitly')
        if action == 'clock':
            # Raw external samples need the observed device time, not panel
            # hashes or a formatted register dump. Fast.clock retains its exact
            # virtual phase and actual local MTIME; RTL's existing observer is
            # cheap and supplies the completed rising-edge cycle and ticks.
            fast_clock = hasattr(self.machine, 'clock')
            state = self.machine.clock() if fast_clock else self.machine.call('inspect')
            result = {key: state[key] for key in ('backend', 'cycle', 'ticks', 'finished')}
            if fast_clock:
                result.update(state)
            return {'machine': result, 'running': self.automatic}
        if action == 'inspect':
            result = self.machine.call('inspect')
            return {'machine': result, 'running': self.automatic, 'identity': self.machine.identity,
                    'external_adapters': self.adapter() if self.adapter else {},
                    'presentation_generation':self.presentation_generation,
                    'capture_uncertain':self.capture_uncertain,
                    'last_failed_operation':self.last_error,
                    'performance': {'run_seconds': self.run_seconds, 'requested_cycles': self.run_cycles,
                                    'cycles_per_second': self.run_cycles / self.run_seconds if self.run_seconds else None}}
        if action == 'pause':
            self.automatic = False
            return self.machine.call('pause')
        if action == 'resume':
            self.automatic = True
            return self.machine.call('inspect')
        if action == 'run':
            return self.run(bounded(value.get('cycles'), 1, 1000000000, 'Cycles'))
        if action == 'snapshot':
            return self.snapshot(value['path'])
        if action == 'restore':
            return self.restore(value['path'])
        if action == 'replay':
            return self.replay(value['snapshot'],value['capture'],value.get('until_cycle'),value.get('until_ns'))
        if action == 'inject':
            # Admission consumes only the exact current cycle and virtual
            # phase. Keep the full post-injection observer returned by call.
            state = self.machine.clock() if hasattr(self.machine, 'clock') else self.machine.call('inspect')
            command,actual=external_command(value,state['cycle'])
            if value.get('kind') not in getattr(self.machine,'input_kinds',{'pen','uart'}):
                raise ValueError('Input is unsupported by this backend/profile')
            return self.external(actual, state, command)
        if action in ('warm-reset', 'cold-cycle'):
            state = self.machine.call('inspect')
            result = self.external(value, state, action)
            self.presentation_generation += 1
            return result
        if action == 'panel':
            return self.machine.call('panel ' + str(Path(value['path']).resolve()))
        if action == 'export-medium':
            return self.machine.call('export-medium ' + str(Path(value['path']).resolve()))
        if action == 'destroy':
            self.closed = True
            return {'destroyed': True}
        raise ValueError('Unsupported lifecycle action')

    def close(self):
        self.capture.close()
        self.machine.close()


def serve(args):
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    directory = args.session_dir.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    address = str(directory / 'machine.sock')
    if len(os.fsencode(address)) >= 104:
        raise ValueError('Session path too long for Unix socket (choose a shorter directory)')
    lock = None
    machine = session = None
    viewer = None
    tablet = tablet_log = None
    try:
        if startup_restore_medium(args):
            args=copy.copy(args)
            args.disk=directory/'startup-medium.raw'
            with args.disk.open('xb') as stream:
                stream.truncate(256*1024*1024)
                stream.flush();os.fsync(stream.fileno())
        if args.disk is not None and args.backend == 'rtl':
            lock = args.disk.resolve().open('r+b')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.backend == 'rtl':
            machine = RTL(args, directory)
        else:
            from lemmasim_fast import Fast
            machine = Fast(args, directory)
        session = Session(machine, directory, args)
        if args.restore:
            session.restore(args.restore)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener, selectors.DefaultSelector() as ready:
            listener.bind(address)
            os.chmod(address, 0o600)
            listener.listen(8)
            listener.setblocking(False)
            ready.register(listener, selectors.EVENT_READ)
            write_json(directory / 'session.json', {'schema': 'lemmasim-live/1', 'pid': os.getpid(),
                       'socket': address, 'backend': args.backend, 'mode': args.mode,
                       'identity': machine.identity, 'argv': machine.argv,
                       'tablet': str(args.tablet) if args.tablet else None})
            print(f'Persistent machine: {directory}', flush=True)
            if args.tablet:
                tablet_log=(directory/'tablet.log').open('wb')
                tablet=subprocess.Popen([sys.executable,str(ROOT/'scripts/lemmasim_tablet.py'),
                    '--device',str(args.tablet),'--session-dir',str(directory),
                    '--record',str(directory/'tablet-raw.jsonl')],stdout=tablet_log,stderr=tablet_log,
                    start_new_session=True)
                session.adapter=lambda:{'tablet':{'device':str(args.tablet),'connected':tablet.poll() is None,
                                                  'exit_code':tablet.poll(),'capture':'tablet-raw.jsonl','log':'tablet.log'}}
                def disconnect():
                    if tablet.poll() is None:
                        tablet.terminate()
                        try:tablet.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(tablet.pid,signal.SIGKILL);tablet.wait(timeout=5)
                # OS handles and unadmitted host samples belong to the external
                # world. Restore disconnects them; recorded replay supplies the
                # exact remaining admitted inputs instead of a live tablet.
                session.disconnect_adapter=disconnect
            if not args.headless:
                viewer = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'view', str(directory)])
            clients = {}
            while not session.closed:
                for key, _ in ready.select(0 if session.automatic else 0.25):
                    if key.fileobj is listener:
                        client, _ = listener.accept()
                        client.setblocking(False)
                        if len(clients) >= 8:
                            client.close()
                        else:
                            clients[client] = (bytearray(), time.monotonic())
                            ready.register(client, selectors.EVENT_READ)
                        continue
                    client = key.fileobj
                    buffer, opened = clients[client]
                    try:
                        part = client.recv(4096)
                    except OSError:
                        ready.unregister(client)
                        clients.pop(client)
                        client.close()
                        continue
                    buffer += part
                    if not part or len(buffer) > MAX_REQUEST:
                        ready.unregister(client)
                        clients.pop(client)
                        client.close()
                        continue
                    if b'\n' in buffer:
                        try:
                            response = {'ok': True, 'result': session.dispatch(json.loads(buffer.split(b'\n', 1)[0]))}
                        except Exception as error:
                            if not session.capture_uncertain:
                                session.last_error=str(error)
                            response = {'ok': False, 'error': str(error)}
                        client.settimeout(3)
                        try:
                            client.sendall(json.dumps(response, separators=(',', ':')).encode() + b'\n')
                        except OSError:
                            pass  # A departed external client cannot kill the machine.
                        ready.unregister(client)
                        clients.pop(client)
                        client.close()
                for client, (_, opened) in list(clients.items()):
                    if time.monotonic() - opened > 5:
                        ready.unregister(client)
                        clients.pop(client)
                        client.close()
                if session.automatic and not session.closed:
                    try:session.run(session.quantum)
                    except (ValueError,OSError,RuntimeError):
                        pass  # The failed interval pauses; inspection remains usable.
            for client in clients:
                client.close()
    finally:
        if tablet is not None and tablet.poll() is None:
            tablet.terminate()
            try:tablet.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(tablet.pid,signal.SIGKILL);tablet.wait(timeout=5)
        if tablet_log is not None:tablet_log.close()
        if viewer is not None and viewer.poll() is None:
            viewer.terminate()
            try:viewer.wait(timeout=5)
            except subprocess.TimeoutExpired:
                viewer.kill();viewer.wait(timeout=5)
        if session is not None:
            session.close()
        elif machine is not None:
            machine.close()
        if lock is not None:
            lock.close()
        Path(address).unlink(missing_ok=True)


def initialize(args):
    """Ordinary initialization utility through the same real guest runtime."""
    import silicon_guest
    if args.force:raise ValueError('Matched initialization exclusively creates a new medium; --force is unsupported')
    if args.size_mib!=256:raise ValueError('The admitted development medium is exactly256MiB')
    # Fail before creating user data when preparation is stale or missing.
    if args.backend=='rtl':silicon_guest.prepared('initializer',args.profile)
    else:
        import lemmasim_fast
        lemmasim_fast.prepared('initializer',args.profile)
    directory=(args.session_dir or ROOT/f'build/lemmasim/init-machine-{time.time_ns()}').resolve()
    directory.mkdir(parents=True,exist_ok=False)
    disk=args.disk.resolve();disk.parent.mkdir(parents=True,exist_ok=True)
    options=argparse.Namespace(backend=args.backend,profile=args.profile,workload='initializer',
        mode='developer',paused=True,quantum=1000000,timeout=min(args.timeout,120),
        disk=disk,memory_latency=0,fail_flush=None,events=None,trace_limit=0)
    machine=session=lock=None
    result={'status':'FAIL','scope':'guest initialization, not host formatting','medium':str(disk)}
    started=time.monotonic()
    try:
        with disk.open('xb') as stream:
            stream.truncate(256*1024*1024);stream.flush();os.fsync(stream.fileno())
        if args.backend=='rtl':
            lock=disk.open('r+b');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            machine=RTL(options,directory)
        else:machine=lemmasim_fast.Fast(options,directory)
        session=Session(machine,directory,options)
        result['identity']=machine.identity
        uart=directory/('uart.bin' if args.backend=='rtl' else 'uart-0.bin')
        acknowledgement=re.compile(rb'^K1 000000000000041f ([0-9a-f]{16}) 0000000000000000 0000000000000000 0000000000000000$',re.MULTILINE)
        while time.monotonic()-started<args.timeout:
            state=session.run(options.quantum)
            if uart.stat().st_size>8*1024*1024:raise ValueError('Initialization UART exceeded its bound')
            found=acknowledgement.search(uart.read_bytes())
            if found:
                if found[1] != b'0000000000000000':
                    raise RuntimeError('Guest rejected durable initialization with status ' + found[1].decode())
                result.update(status='ACKNOWLEDGED_GUEST_INITIALIZATION',guest_ack=found[0].decode(),
                              cycle=state['cycle'],elapsed_seconds=time.monotonic()-started,
                              medium_sha256=digest(disk))
                print(f'Guest acknowledged durable initialization: {disk} (observations: {directory})')
                return result
            if state.get('finished'):raise RuntimeError('Guest ended before acknowledging initialization')
        raise TimeoutError('Guest did not acknowledge initialization before the resource deadline')
    except BaseException as error:
        result.update(error=str(error),elapsed_seconds=time.monotonic()-started)
        raise
    finally:
        if session:session.close()
        elif machine:machine.close()
        if lock:lock.close()
        write_json(directory/'result.json',result)


def _sample_pointer(directory, x, y, contact, width, height, scale):
    state = request(directory, {'action': 'clock'})['machine']
    # Explicitly synthetic mouse pressure; no tablet capability or gesture
    # interpretation is added by this raw pointer transport.
    words = [state['ticks'], max(0, min(65535, x * scale * 65535 // (width - 1))),
             max(0, min(65535, y * scale * 65535 // (height - 1))), 2047 if contact else 0,
             7 if contact else 6, 1, 0]
    return request(directory, {'action': 'inject', 'kind': 'pen', 'words': words})


def view(directory):
    """Raw synthetic pointer bridge + controller-produced pixels, no host ink."""
    import tkinter as tk
    from tkinter import filedialog, messagebox
    directory = Path(directory).resolve()
    metadata = json.loads((directory / 'session.json').read_text())
    from silicon_profile import profile
    width, height = profile(metadata['identity']['profile'])['geometry']
    scale = max(1, (height + 799) // 800)
    view_width, view_height = (width + scale - 1) // scale, (height + scale - 1) // scale
    window = tk.Tk()
    window.title(f"LemmaSim — {metadata['backend']} {metadata['mode']}")
    controls = tk.Frame(window)
    controls.pack(fill='x')
    status = tk.StringVar(value='Virtual time is authoritative; host speed controls pacing')
    tk.Label(window, textvariable=status).pack(fill='x')
    canvas = tk.Canvas(window, width=view_width, height=view_height, background='white')
    canvas.pack()
    held = False
    frame = None
    last_hash = None
    last_panel = None

    def operation(value):
        try:
            return request(directory, value)
        except Exception as error:
            messagebox.showerror('Machine operation', str(error))

    def save():
        name = filedialog.asksaveasfilename(title='New checkpoint directory')
        if name:
            operation({'action': 'snapshot', 'path': name})

    def restore():
        name = filedialog.askdirectory(title='Checkpoint directory')
        if name:
            operation({'action': 'restore', 'path': name})

    for label, action in [('Pause', 'pause'), ('Resume', 'resume'), ('Warm reset', 'warm-reset'), ('Cold cycle', 'cold-cycle')]:
        tk.Button(controls, text=label, command=lambda a=action: operation({'action': a})).pack(side='left')
    tk.Button(controls, text='Snapshot', command=save).pack(side='left')
    tk.Button(controls, text='Restore', command=restore).pack(side='left')
    if metadata['identity']['profile']=='lemma-silicon-dev/0.3.0':
        # A physical-style level bridge. Guest policy decides whether an edge
        # requests suspend, fails Busy, or wakes the retained machine.
        power_button=tk.Button(controls,text='Power button')
        power_button.bind('<ButtonPress-1>',lambda _:operation({'action':'inject','kind':'button','level':1}))
        power_button.bind('<ButtonRelease-1>',lambda _:operation({'action':'inject','kind':'button','level':0}))
        power_button.pack(side='left')

    def sample(event, contact):
        _sample_pointer(directory, event.x, event.y, contact, width, height, scale)

    def down(event):
        nonlocal held
        held = True
        sample(event, True)

    def move(event):
        sample(event, held)

    def up(event):
        nonlocal held
        held = False
        sample(event, False)

    if not metadata.get('tablet'):
        canvas.bind('<ButtonPress-1>', down)
        canvas.bind('<B1-Motion>', move)
        canvas.bind('<ButtonRelease-1>', up)
        canvas.bind('<Motion>', lambda e: sample(e, False) if not held else None)

    def refresh():
        nonlocal frame, last_hash, last_panel
        try:
            state = request(directory, {'action': 'inspect'})
            produced=state['machine']
            power=produced.get('devices',{}).get('power',produced.get('power'))
            power_text=(' · power SUSPENDED' if power['state']==1 else ' · power RUN') if power else ''
            if power and power.get('error'):
                power_text+=' · '+{1:'suspend Busy',2:'invalid power access'}.get(power['error'],'power error '+str(power['error']))
            status.set(f"cycle {produced['cycle']} · ticks {produced['ticks']} · " + ('running' if state['running'] else 'paused')+power_text)
            paper=produced.get('devices',{}).get('paper',{})
            panel=(state.get('presentation_generation',0),paper.get('visible_sha256',produced.get('panel_completed')))
            if panel != last_panel:
                path = directory / 'view.pgm'
                request(directory, {'action': 'panel', 'path': str(path)})
                current_hash = digest(path)
                if current_hash != last_hash:
                    frame = tk.PhotoImage(file=str(path))
                    if scale > 1:
                        frame = frame.subsample(scale, scale)
                    canvas.delete('frame')
                    canvas.create_image(0, 0, anchor='nw', image=frame, tags='frame')
                    last_hash = current_hash
                last_panel=panel
            window.after(500, refresh)
        except Exception as error:
            status.set(str(error))
            window.after(1000, refresh)

    window.protocol('WM_DELETE_WINDOW', lambda: (operation({'action': 'destroy'}), window.destroy()))
    refresh()
    window.mainloop()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'view':
        view(sys.argv[2])
    else:
        raise SystemExit('Use scripts/lemmasim session')
