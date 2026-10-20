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
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MAX_REQUEST = 65536
MAX_EVENTS = 1000000


class NotebookFaultObserver:
    """Bounded lifecycle/input-loss presentation, never notebook/domain policy."""
    record = re.compile(rb'K1 (00000000000000f[14]|0000000000000735) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\r?')

    def __init__(self):
        self.reset()

    def reset(self):
        self.tail = b''
        self.boundary = True
        self.descriptor = None
        self.fault = None
        self.ink_loss = None
        self.ink_loss_total = 0

    def feed(self, data):
        for byte in data:
            if byte == 10:
                match = self.record.fullmatch(self.tail) if self.boundary else None
                if match:
                    kind, descriptor, code, value, cause = match.groups()
                    if kind == b'0000000000000735':
                        reason, discarded, cumulative, sequence = (int(x,16) for x in (descriptor,code,value,cause))
                        valid = 1 <= reason <= 4 and discarded <= cumulative and self.ink_loss_total <= cumulative
                        self.ink_loss = dict(authority='compiled-guest-report',
                            contract='lemma-notebook-input-loss/1',
                            state='loss' if valid else 'malformed',
                            reason=str(reason),discarded=str(discarded),cumulative=str(cumulative),lastCapturedSequence=str(sequence))
                        if valid:
                            self.ink_loss_total = cumulative
                    if kind.endswith(b'1') and code == b'0000000000000001' and self.descriptor is None:
                        self.descriptor = descriptor
                    if (kind.endswith(b'4') and descriptor == self.descriptor and cause != b'0000000000000000'
                            and not (cause == b'0000000000000008' and code == b'0000000000000000')):
                        self.fault = dict(authority='compiled-kernel-report', descriptor=descriptor.decode(),
                            exitCode=code.decode(), data=value.decode(), cause=cause.decode(), record=self.tail.decode())
                self.tail = b''
                self.boundary = True
            elif self.boundary:
                if len(self.tail) < 89:
                    self.tail += bytes((byte,))
                else:
                    self.tail = b''
                    self.boundary = False
        return self.fault


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



def stage_checkpoint_inputs(source, manifest, destination):
    """Copy validated bytes into an exclusively owned immutable restore input set.

    Recheck the copied bytes against the already parsed manifest. A concurrent
    source replacement cannot retarget a verified restore or overwrite a medium.
    """
    source,destination=Path(source),Path(destination)
    for item in manifest['files']:
        original=source/item['path'];target=destination/item['path']
        target.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(original,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size!=item['bytes']:
                raise ValueError('Restore source changed before its immutable copy')
            with os.fdopen(fd,'rb',closefd=False) as reader, target.open('xb') as writer:
                count=0
                while block:=reader.read(1024*1024):
                    count+=len(block)
                    if count>item['bytes']:raise ValueError('Restore source grew during copy')
                    if block.count(0)==len(block):writer.seek(len(block),os.SEEK_CUR)
                    else:writer.write(block)
                if count!=item['bytes']:raise ValueError('Restore source shrank during copy')
                writer.truncate(count);writer.flush();os.fsync(writer.fileno())
            if digest(target)!=item['sha256']:
                raise ValueError('Restore source changed during immutable copy')
        finally:os.close(fd)
    checkpoint_inventory(destination,manifest)
    return destination


def startup_restore_medium(args):
    """Choose optional fast backing from verified state, never a user disk."""
    if not args.restore:
        return False
    if args.disk is not None:
        raise ValueError('A restored fork owns its checkpoint backing; omit --disk')
    if args.workload == 'service':
        return False
    if args.workload not in ('power','ble','usb'):
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
    if value.get('action') in ('warm-reset','cold-cycle','companion-retry'):return value['action'],dict(value)
    if value.get('action')!='inject':raise ValueError('Unsupported external action')
    cycle=bounded(value.get('cycle',current),current,(1<<64)-1,'Event cycle')
    kind=value.get('kind')
    if kind=='pen':
        words=value.get('words')
        if not isinstance(words,list) or len(words)!=7:raise ValueError('Pen requires time,x,y,pressure,flags,tool,buttons')
        for word,(low,high) in zip(words,((0,(1<<64)-1),(0,65535),(0,65535),(0,4095),(0,15),(0,2),(0,7))):
            bounded(word,low,high,'Pen field')
        command=f'inject {cycle} pen '+' '.join(map(str,words))
    elif kind=='multimodal':
        words=value.get('words')
        if not isinstance(words,list) or len(words)!=4:raise ValueError('Multimodal stimulus needs id,u32-code,u32-reference,quality')
        for word,(low,high) in zip(words,((0,7),(0,(1<<32)-1),(0,(1<<32)-1),(0,65535))):bounded(word,low,high,'Multimodal stimulus')
        command=f'inject {cycle} multimodal '+' '.join(map(str,words))
    elif kind=='uart':
        payload=value.get('hex','')
        if not isinstance(payload,str) or not 2<=len(payload)<=8192 or len(payload)%2 or any(c not in '0123456789abcdefABCDEF' for c in payload):
            raise ValueError('UART requires1..4096 literal hex bytes')
        if 'byte_interval_ns' in value:
            interval=bounded(value['byte_interval_ns'],1,1000000000,'UART byte interval')
            command=f'inject {cycle} uart-paced {interval} {payload}'
        else:command=f'inject {cycle} uart {payload}'
    elif kind in ('pgood','brownout','ble-rx','ble-coex'):
        level=bounded(value.get('level'),0,1,'Supply digital level')
        command=f'inject {cycle} {kind} {level}'
    elif kind=='button':
        level=bounded(value.get('level'),0,1,'Button level')
        command=f'inject {cycle} button {level}'
    else:raise ValueError('Unsupported external event')
    return command,dict(value,cycle=cycle)


def process_start_ticks(pid):
    """Linux owner identity, including the start time that distinguishes PID reuse."""
    bounded(pid, 1, (1 << 31) - 1, 'Control owner PID')
    raw = (Path('/proc') / str(pid) / 'stat').read_text()
    fields = raw[raw.rfind(') ') + 2:].split()
    return int(fields[19])


class ControlSocket:
    """A session owns its socket, including a private short path when necessary.

    The usual in-session address remains compatible with existing clients.
    A long session gets one exclusively created0700 directory, never a shared
    static socket. Its random token, full session path and live PID/start time
    bind the published address to this exact owner.
    """
    def __init__(self, directory):
        self.address = str(directory / 'machine.sock')
        self.private = None
        self.private_identity = None
        self.binding = None
        self.owner_identity = None
        self.socket_identity = None
        if len(os.fsencode(self.address)) < 104:
            return
        parent = Path('/tmp')
        candidate = os.environ.get('XDG_RUNTIME_DIR')
        if candidate:
            path = Path(candidate)
            try:
                info = path.lstat()
                if (path.is_absolute() and stat.S_ISDIR(info.st_mode) and
                        info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700 and
                        len(os.fsencode(str(path))) < 60):
                    parent = path
            except OSError:
                pass
        self.private = Path(tempfile.mkdtemp(prefix='lm-', dir=parent))
        os.chmod(self.private, 0o700)
        info = self.private.lstat()
        self.private_identity = (info.st_dev, info.st_ino)
        self.address = str(self.private / 'machine.sock')
        try:
            if len(os.fsencode(self.address)) >= 104:
                raise ValueError('Private control address exceeds Unix socket bound')
            self.binding = {'version': 1, 'session': str(directory),
                            'directory': str(self.private), 'socket': self.address,
                            'pid': os.getpid(), 'start_ticks': process_start_ticks(os.getpid()),
                            'nonce': secrets.token_hex(32)}
            fd = os.open(self.private / 'owner.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                info = os.fstat(stream.fileno())
                self.owner_identity = (info.st_dev, info.st_ino)
                json.dump(self.binding, stream, separators=(',', ':'))
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            self.close()
            raise

    def bound(self):
        info = Path(self.address).lstat()
        self.socket_identity = (info.st_dev, info.st_ino)

    def close(self):
        if self.private is not None:
            try:
                info = self.private.lstat()
            except FileNotFoundError:
                return
            if self.private_identity != (info.st_dev, info.st_ino):
                raise RuntimeError('Private control directory was replaced before cleanup')
        path = Path(self.address)
        try:
            info = path.lstat()
            if self.socket_identity == (info.st_dev, info.st_ino):
                path.unlink()
        except FileNotFoundError:
            pass
        if self.private is not None:
            owner = self.private / 'owner.json'
            try:
                info = owner.lstat()
                if self.owner_identity == (info.st_dev, info.st_ino):
                    owner.unlink()
            except FileNotFoundError:
                pass
            self.private.rmdir()


def control_binding(directory, metadata):
    """Reject a stale, replaced or cross-session private control address."""
    binding = metadata.get('control')
    if binding is None:
        if metadata.get('socket') != str(directory / 'machine.sock'):
            raise ValueError('Legacy control address does not identify this session')
        return None  # Historical and ordinary short-path manifests.
    keys = {'version', 'session', 'directory', 'socket', 'pid', 'start_ticks', 'nonce'}
    if (not isinstance(binding, dict) or set(binding) != keys or type(binding['version']) is not int or binding['version'] != 1 or
            binding['session'] != str(directory) or binding['socket'] != metadata.get('socket') or
            binding['pid'] != metadata.get('pid') or type(binding['start_ticks']) is not int or
            not isinstance(binding['nonce'], str) or len(binding['nonce']) != 64 or
            any(c not in '0123456789abcdef' for c in binding['nonce'])):
        raise ValueError('Private control manifest does not identify this session')
    private = Path(binding['directory'])
    if not private.is_absolute() or Path(binding['socket']) != private / 'machine.sock':
        raise ValueError('Private control address is outside its owned directory')
    info = private.lstat()
    owner = (private / 'owner.json').lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or
            stat.S_IMODE(info.st_mode) != 0o700 or
            not stat.S_ISREG(owner.st_mode) or owner.st_uid != os.getuid() or
            stat.S_IMODE(owner.st_mode) != 0o600 or
            json.loads((private / 'owner.json').read_text()) != binding):
        raise ValueError('Private control directory/owner binding changed')
    if process_start_ticks(binding['pid']) != binding['start_ticks']:
        raise ValueError('Private control owner exited or its PID was reused')
    endpoint = Path(binding['socket']).lstat()
    if (not stat.S_ISSOCK(endpoint.st_mode) or endpoint.st_uid != os.getuid() or
            stat.S_IMODE(endpoint.st_mode) != 0o600):
        raise ValueError('Private control socket was replaced or changed')
    return binding


def request(directory, value, timeout=120):
    directory = Path(directory).resolve()
    metadata = json.loads((directory / 'session.json').read_text())
    binding = control_binding(directory, metadata)
    if binding is not None:
        value = {**value, '_control_nonce': binding['nonce']}
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
    if binding is not None and result.get('_control_nonce') != binding['nonce']:
        raise RuntimeError('Private control response belongs to another owner')
    if result.get('ok') is not True:
        raise RuntimeError(result.get('error', 'Machine operation failed'))
    return result['result']


class RTL:
    """Machine owner; only byte/sample/lifecycle operations cross this boundary."""
    def __init__(self, args, directory):
        import silicon_guest
        if getattr(args,'native_bundle',None):
            import silicon_guest_bundle
            self.data = silicon_guest_bundle.prepared(args.native_bundle,'rtl',args.workload,args.profile)
            if getattr(args,'guest_build',None):
                if getattr(args,'guest_source_root',None) is None:
                    self.data=silicon_guest_bundle.development_guest(self.data,args.workload,directory,args.guest_build,args.mode)
                else:
                    self.data=silicon_guest_bundle.development_guest(self.data,args.workload,directory,args.guest_build,args.mode,
                                                                   source_root=args.guest_source_root)
        else:self.data = silicon_guest.prepared(args.workload, args.profile,rtl_source_root=getattr(args,'rtl_source_root',None),guest_source_root=getattr(args,'guest_source_root',None))
        self.identity = {'backend': 'rtl', 'profile': self.data['profile'],
                         'runtime': self.data['binary']['sha256'],
                         'rom': self.data['rom']['sha256'],
                         'guest': self.data['workloads'][args.workload]['image']['sha256'],
                         'dtb': self.data['workloads'][args.workload]['dtb']['sha256'],
                         'descriptor': self.data['workloads'][args.workload]['descriptor']['sha256']}
        self.usb_recovery_spec = None
        if getattr(args, 'usb_recovery', False):
            from usb_recovery import CONTRACT
            if self.data['profile'] != 'lemma-silicon-dev/0.13.0' or args.mode not in ('developer', 'laboratory'):
                raise ValueError('USB recovery requires Clocked13 Developer or Laboratory mode')
            manifest = json.loads(silicon_guest.validate(self.data['rtl_build']).read_text())
            if manifest.get('runtime_control_contracts') != {'usb_recovery': CONTRACT}:
                raise ValueError('Prepared native implementation does not admit USB recovery')
            self.identity['usb_recovery_contract'] = CONTRACT
        if self.data.get('rtl_source_archive') is not None:
            self.identity['runtime_source_archive']={key:self.data['rtl_source_archive'][key] for key in ('archive','original_receipt','native_manifest','snapshot_identity','inputs','scope')}
        override_archive=self.data.get('guest_override',{}).get('source_archive')
        if override_archive is not None:
            self.identity['development_guest_source_archive']={key:override_archive[key] for key in ('inventory','build','provenance','audit','image','configuration','source_commit','dirty_paths','inputs','scope')}
        entry = self.data['workloads'][args.workload]
        if entry.get('guest_source_archive') is not None:
            self.identity['guest_source_archive']={key:entry['guest_source_archive'][key] for key in ('archive','build','provenance','audit','source_commit','dirty_paths','inputs','scope')}
        self.log = (directory / 'machine.log').open('wb')
        command = [self.data['binary']['path'], '--image', entry['image']['path'],
                   '--rom', self.data['rom']['path'], '--load',
                   f"0x{silicon_guest.prepared_profile(self.data)['dtb_base']:x}:{entry['dtb']['path']}",
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
        ble_peer = getattr(args,'ble_peer',None)
        ble_replay = getattr(args,'ble_replay',None)
        if self.data['profile']=='lemma-silicon-dev/0.5.0':
            command += ['--ble-capture',str(directory/'ble.outcomes'),'--ble-wire-trace',str(directory/'ble-wire.csv')]
            if ble_peer is not None:
                command += ['--ble-peer',str(ble_peer.resolve()),'--ble-peer-timeout-ms',str(args.ble_peer_timeout_ms)]
                for item in args.ble_peer_arg:command += ['--ble-peer-arg',item]
                if args.ble_drop_packets:command += ['--ble-drop-packets',str(args.ble_drop_packets)]
            if ble_replay is not None:command += ['--ble-replay',str(ble_replay.resolve())]
        elif ble_peer is not None or ble_replay is not None:raise ValueError('BLE peer requires optional binding5')
        usb_prepared=getattr(args,'usb_host_prepared',None)
        if getattr(args, 'usb_recovery', False):
            command += ['--usb-recovery']
            if usb_prepared is None and not getattr(args, 'restore', None):
                raise ValueError('Live USB recovery requires a validated host and durable peer namespace')
        if self.data['profile'] in ('lemma-silicon-dev/0.6.0','lemma-silicon-dev/0.8.0','lemma-silicon-dev/0.11.0','lemma-silicon-dev/0.13.0') and getattr(args,'restore',None) and usb_prepared is not None:
            raise ValueError('Restored USB raw fork cannot launch a live host')
        if usb_prepared is not None:
            if self.data['profile'] not in ('lemma-silicon-dev/0.6.0','lemma-silicon-dev/0.8.0','lemma-silicon-dev/0.11.0','lemma-silicon-dev/0.13.0'):raise ValueError('USB packet host requires binding6')
            import lemmasim_usb
            from lemmasim_companion import peer_info
            if json.loads(usb_prepared.read_text()).get('schema') == 'lemma-usb-host-dev/4':
                import lemmasim_usb_pending
                host=lemmasim_usb_pending.validate(usb_prepared)
            else:
                host=lemmasim_usb.validate(usb_prepared)
            peer=peer_info(args.usb_peer_directory)
            if getattr(args, 'usb_recovery', False):
                from usb_recovery import binding
                self.usb_recovery_spec = (usb_prepared, args.usb_peer_directory,
                    args.usb_peer_socket, args.usb_host_state, ROOT/'sim/companion/os_io.py')
                digest, _ = binding(*self.usb_recovery_spec)
                command += ['--usb-recovery-binding', digest]
            command += ['--usb-peer',host['binary']['path'],'--usb-capture',str(directory/'usb.raw'),
                        '--usb-peer-timeout-ms',str(args.usb_peer_timeout_ms)]
            for item in (str(args.usb_peer_socket.resolve()),str(args.usb_host_state.resolve()),str(peer['writer']),str(ROOT/'sim/companion/os_io.py')):
                command += ['--usb-peer-arg',item]
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
            if args.disk is None and companion is None and usb_prepared is None and args.workload not in ('power','ble','usb') and not (self.data['profile'] in ('lemma-silicon-dev/0.6.0','lemma-silicon-dev/0.8.0','lemma-silicon-dev/0.11.0','lemma-silicon-dev/0.13.0') and getattr(args,'restore',None)):
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
        self.input_kinds={'pen','uart','button','pgood','brownout','ble-rx','ble-coex'} if self.data['profile'] in ('lemma-silicon-dev/0.5.0','lemma-silicon-dev/0.6.0','lemma-silicon-dev/0.11.0','lemma-silicon-dev/0.13.0') else {'pen','uart','button','pgood','brownout'} if self.data['profile']=='lemma-silicon-dev/0.4.0' else {'pen','uart','button'} if self.data['profile']=='lemma-silicon-dev/0.3.0' else {'pen','uart'}
        if self.data['profile']=='lemma-silicon-dev/0.14.0':self.input_kinds={'pen','uart','button','multimodal'}
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
        # Each selected binding admits only its declared container schema; the
        # exact runtime identity and CRC/state checks still apply below.
        identity=getattr(self,'identity',{})
        profile=identity.get('profile')
        versions=(10,) if profile=='lemma-silicon-dev/0.13.0' else (8,) if profile=='lemma-silicon-dev/0.11.0' else (6,) if profile in ('lemma-silicon-dev/0.6.0','lemma-silicon-dev/0.8.0','lemma-silicon-dev/0.11.0','lemma-silicon-dev/0.13.0') else (5,) if profile=='lemma-silicon-dev/0.5.0' else (3,) if profile=='lemma-silicon-dev/0.4.0' else (1,2)
        if identity.get('usb_recovery_contract') == 'lemma-usb-live-recovery/1':
            if profile != 'lemma-silicon-dev/0.13.0':
                raise ValueError('USB recovery checkpoint profile differs')
            versions = (11,)
        # LMSSRTL1's wrapper follows its 112-byte container header.
        # event_index is the first u64; cycle is the second. Session has
        # already verified the complete file's length and SHA256 inventory.
        # The runtime performs CRC/state/model validation before adoption.
        # Check the sidecar boundary here so a mismatch cannot be discovered
        # only after the live processor and medium have been replaced.
        path = Path(path)
        with path.open('rb') as stream:
            header = stream.read(128)
        if (len(header) != 128 or header[:8] != b'LMSSRTL1' or
                int.from_bytes(header[8:16], 'little') not in versions or
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
        self.restored_parent = None
        self.school_service = None
        self.notebook_lifecycle = NotebookFaultObserver()
        self.notebook_observation_path = None
        self.notebook_observation_offset = 0
        self.observe_notebook_fault = 'notebook' in getattr(args, 'workload', '')

    def notebook_epoch(self):
        self.notebook_lifecycle.reset()
        self.notebook_observation_path = None
        self.notebook_observation_offset = 0
        path = (getattr(self.machine,'directory',self.directory) if self.machine.identity.get('backend') == 'qemu' else self.directory) / (f'uart-{getattr(self.machine,"generation",0)}.bin'
            if self.machine.identity.get('backend') == 'qemu' else 'uart.bin')
        if path.is_file():
            self.notebook_observation_path = path
            self.notebook_observation_offset = path.stat().st_size
            if self.notebook_observation_offset:
                with path.open('rb') as stream:
                    stream.seek(self.notebook_observation_offset - 1)
                    self.notebook_lifecycle.boundary = stream.read(1) == b'\n'

    def observe_notebook(self):
        if not self.observe_notebook_fault:
            return
        path = (getattr(self.machine,'directory',self.directory) if self.machine.identity.get('backend') == 'qemu' else self.directory) / (f'uart-{getattr(self.machine,"generation",0)}.bin'
            if self.machine.identity.get('backend') == 'qemu' else 'uart.bin')
        if not path.is_file():
            return
        if self.notebook_observation_path != path:
            self.notebook_observation_path = path
            self.notebook_observation_offset = 0
            self.notebook_lifecycle.reset()
        size = path.stat().st_size
        if size < self.notebook_observation_offset:
            raise RuntimeError('Notebook lifecycle UART history was truncated')
        # At most64KiB per owner interval; retain the offset rather than
        # repeatedly reading or verifying the full submission/boot history.
        with path.open('rb') as stream:
            stream.seek(self.notebook_observation_offset)
            data = stream.read(65536)
        self.notebook_observation_offset += len(data)
        if self.notebook_lifecycle.feed(data) is not None:
            self.automatic = False

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
        self.observe_notebook()
        if result.get('finished'):
            self.automatic = False
        return result

    def snapshot(self, destination):
        self.ensure_capture_certain()
        if hasattr(self.machine,'checkpoint_admission'):self.machine.checkpoint_admission()
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
        if hasattr(self.machine,'checkpoint_admission'):self.machine.checkpoint_admission()
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
        staged=None;restore_source=source
        try:
            if getattr(self.machine,'native_logical2',False):
                staged=tempfile.TemporaryDirectory(prefix='restore-inputs-',dir=self.directory)
                restore_source=stage_checkpoint_inputs(source,manifest,Path(staged.name))
            if hasattr(self.machine, 'preflight_checkpoint'):
                self.machine.preflight_checkpoint(restore_source / 'machine.chk', cycle)
            result = (self.machine.restore_checkpoint(restore_source/'machine.chk',phase)
                      if hasattr(self.machine,'restore_checkpoint') else self.machine.call('restore ' + str(restore_source / 'machine.chk')))
            if result['cycle']!=cycle:raise ValueError('Snapshot metadata differs from its saved virtual cycle')
        finally:
            if staged is not None:staged.cleanup()
        self.automatic = manifest['automatic']
        self.quantum = quantum
        self.event_cursor = cursor
        self.presentation_generation += 1
        self.restored_parent = source
        # Only successful machine adoption changes interactive transport/domain
        # authority. Failed manifest, preflight or private load leaves it intact.
        post_errors=[]
        try:self.notebook_epoch()
        except OSError as error:
            post_errors.append('notebook observation unavailable after restore: '+str(error))
        if getattr(self,'school_service',None) is not None:
            try:self.school_service.invalidate()
            except Exception as error:
                self.school_service=None
                post_errors.append('school connection detached after restore: '+str(error))
        if self.disconnect_adapter:
            try:self.disconnect_adapter()
            except Exception as error:
                self.adapter=None;self.disconnect_adapter=None
                post_errors.append('external adapter detached after restore: '+str(error))
        if post_errors:self.last_error='; '.join(post_errors)
        return {'restored': str(source), 'machine': result,
                'medium': 'isolated snapshot fork', 'external_event_cursor': manifest['external_event_cursor'],
                **({'post_restore_errors':post_errors} if post_errors else {})}

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
        if action == 'school-service':
            if self.machine.identity.get('profile') not in ('lemma-silicon-dev/0.14.0','lemma-silicon-dev/0.15.0'):
                raise ValueError('ordinary school transport requires the admitted notebook device profile')
            if getattr(self,'school_service',None) is None:
                from lemmasim_school_service import SchoolService
                self.school_service=SchoolService(self)
            return self.school_service.dispatch(value)
        if action in ('run','resume','inject','warm-reset','cold-cycle','snapshot','restore','replay','companion-retry','backing-outcomes','ble-outcomes','usb-outcomes','export-usb-replay','usb-fault','usb-reconnect'):
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
                    'guest_fault':self.notebook_lifecycle.fault,
                    'guest_ink_loss':self.notebook_lifecycle.ink_loss,
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
            if value.get('kind') in ('pgood','brownout','ble-coex') and self.mode!='laboratory':raise ValueError('Supply fault inputs require Laboratory mode')
            # Admission consumes only the exact current cycle and virtual
            # phase. Keep the full post-injection observer returned by call.
            state = self.machine.clock() if hasattr(self.machine, 'clock') else self.machine.call('inspect')
            command,actual=external_command(value,state['cycle'])
            if value.get('kind') not in getattr(self.machine,'input_kinds',{'pen','uart'}):
                raise ValueError('Input is unsupported by this backend/profile')
            return self.external(actual, state, command)
        if action in ('warm-reset', 'cold-cycle'):
            if getattr(self,'school_service',None) is not None:self.school_service.invalidate()
            state = self.machine.call('inspect')
            result = self.external(value, state, action)
            if action=='cold-cycle' and getattr(self,'school_service',None) is not None:self.school_service.partial=False
            self.presentation_generation += 1
            self.notebook_epoch()
            return result
        if action == 'usb-reconnect':
            if (self.mode not in ('developer', 'laboratory') or self.automatic or
                    self.restored_parent is not None or
                    self.machine.identity.get('backend') != 'rtl' or
                    self.machine.identity.get('profile') != 'lemma-silicon-dev/0.13.0' or
                    self.machine.identity.get('usb_recovery_contract') != 'lemma-usb-live-recovery/1' or
                    getattr(self.machine, 'usb_recovery_spec', None) is None):
                raise ValueError('USB reconnect requires a paused original Clocked13 recovery owner')
            if set(value) != {'action', 'epoch', 'next_request', 'binding'}:
                raise ValueError('USB reconnect requires exact epoch/request/namespace binding')
            epoch = bounded(value['epoch'], 2, (1 << 64)-1, 'USB connection epoch')
            next_request = bounded(value['next_request'], 1, (1 << 64)-2, 'USB next request')
            from usb_recovery import binding
            digest, identity = binding(*self.machine.usb_recovery_spec)
            if value['binding'] != digest:
                raise ValueError('USB recovery process/namespace binding changed')
            state = self.machine.call('inspect')
            usb = state.get('usb', {})
            if (not usb.get('recovery') or not usb.get('terminal') or
                    usb.get('connection_epoch') != epoch-1 or
                    usb.get('next_request') != next_request or
                    usb.get('namespace_binding') != digest):
                raise ValueError('USB reconnect state/epoch/request/binding differs')
            result = self.external(value, state, f'usb-reconnect {epoch} {next_request}')
            return {'machine': result, 'connection_binding': identity,
                    'scope': 'new raw transport epoch only; real guest USB reset/control and receipt/journal recovery remain required'}
        if action in ('usb-outcomes','export-usb-replay'):
            if self.mode not in ('developer','laboratory') or self.machine.identity.get('backend')!='rtl' or self.machine.identity.get('profile') not in ('lemma-silicon-dev/0.6.0','lemma-silicon-dev/0.8.0','lemma-silicon-dev/0.11.0','lemma-silicon-dev/0.13.0'):raise ValueError('USB raw outcomes require USB6 RTL Developer or Laboratory mode')
            path=Path(value['path']).resolve()
            if any(c in str(path) for c in ('\n','\r')):raise ValueError('Outcome path contains a command delimiter')
            result=self.machine.call(action+' '+str(path))
            return {'machine':result,'outcome_tape':str(path),'scope':'captured native USB6 raw suffix only; no live peer resubmission or newly durable external commit'}
        if action == 'usb-fault':
            if self.mode != 'laboratory' or self.automatic or self.restored_parent is None:
                raise ValueError('Injected USB fault requires a paused restored Laboratory fork')
            from usb_fork_fault import validate as validate_usb_fault
            state = self.machine.call('inspect')
            fault, bridge = validate_usb_fault(value['path'], self.restored_parent,
                                                state, self.machine.identity)
            result = self.external(value, state, 'usb-outcomes ' + str(bridge))
            return {'machine': result, 'fault': fault['fault'],
                    'fault_sidecar': str(Path(value['path']).resolve()),
                    'scope': 'injected disconnect fault fork; no historical outcome or external commit claim'}
        if action=='ble-outcomes':
            if self.mode not in ('developer','laboratory') or self.machine.identity.get('profile')!='lemma-silicon-dev/0.5.0':raise ValueError('BLE outcome binding requires binding5 Developer or Laboratory mode')
            path=Path(value['path']).resolve()
            if any(c in str(path) for c in ('\n','\r')):raise ValueError('Outcome path contains a command delimiter')
            return {'machine':self.machine.call('ble-outcomes '+str(path)),'outcome_tape':str(path),'scope':'isolated resolved peer continuation from captured actual outcomes'}
        if action=='backing-outcomes':
            if self.mode not in ('developer','laboratory'):raise ValueError('Pending fork outcome binding requires Developer or Laboratory mode')
            if self.machine.identity.get('backend')!='rtl':raise ValueError('Pending fork outcome binding requires the native RTL backend')
            path=Path(value['path']).resolve()
            if any(c in str(path) for c in ('\n','\r')):raise ValueError('Outcome path contains a command delimiter')
            # Runtime validates the complete tape and inherited request before
            # rebinding. This configures isolated replay ownership; it is not
            # a raw guest input event and does not enter external.jsonl.
            result=self.machine.call('backing-outcomes '+str(path))
            return {'machine':result,'outcome_tape':str(path),
                    'scope':'isolated Pending continuation from captured outcomes; no external resubmission'}
        if action=='companion-retry':
            if self.mode not in ('developer','laboratory'):raise ValueError('Explicit pending retry requires Developer or Laboratory mode')
            state=self.machine.call('inspect')
            return self.external(value,state,'companion-retry')
        if action == 'panel':
            return self.machine.call('panel ' + str(Path(value['path']).resolve()))
        if action == 'export-medium':
            return self.machine.call('export-medium ' + str(Path(value['path']).resolve()))
        if action == 'destroy':
            self.closed = True
            return {'destroyed': True}
        raise ValueError('Unsupported lifecycle action')

    def close(self):
        if getattr(self,'school_service',None) is not None:self.school_service.close()
        self.capture.close()
        self.machine.close()


def serve(args, machine_type=None, session_type=None):
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    directory = args.session_dir.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    control = ControlSocket(directory)
    address = control.address
    lock = None
    machine = session = None
    viewer = None
    tablet = tablet_log = None
    try:
        if machine_type is None and startup_restore_medium(args):
            args=copy.copy(args)
            args.disk=directory/'startup-medium.raw'
            with args.disk.open('xb') as stream:
                stream.truncate(256*1024*1024)
                stream.flush();os.fsync(stream.fileno())
        if args.disk is not None and args.backend == 'rtl':
            lock = args.disk.resolve().open('r+b')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if machine_type is not None:
            machine = machine_type(args, directory)
        elif args.backend == 'rtl':
            machine = RTL(args, directory)
        else:
            from lemmasim_fast import Fast
            machine = Fast(args, directory)
        session = (session_type or Session)(machine, directory, args)
        if args.restore:
            session.restore(args.restore)
            if getattr(args,'usb_replay',None) is not None:
                session.dispatch({'action':'usb-outcomes','path':str(args.usb_replay.resolve())})
            if getattr(args,'profile',None) in ('lemma-silicon-dev/0.6.0','lemma-silicon-dev/0.8.0','lemma-silicon-dev/0.11.0','lemma-silicon-dev/0.13.0') and args.paused:session.automatic=False
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener, selectors.DefaultSelector() as ready:
            listener.bind(address)
            control.bound()
            os.chmod(address, 0o600)
            listener.listen(8)
            listener.setblocking(False)
            ready.register(listener, selectors.EVENT_READ)
            metadata = {'schema': 'lemmasim-live/1', 'pid': os.getpid(),
                       'socket': address, 'backend': args.backend, 'mode': args.mode,
                       'identity': machine.identity, 'argv': machine.argv,
                       'tablet': str(args.tablet) if args.tablet else None}
            if control.binding is not None:
                metadata['control'] = control.binding
            write_json(directory / 'session.json', metadata)
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
                if getattr(session,'school_service',None) is not None:session.school_service.pump()
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
                            value = json.loads(buffer.split(b'\n', 1)[0])
                            if control.binding is not None:
                                if (not isinstance(value, dict) or
                                        value.pop('_control_nonce', None) != control.binding['nonce']):
                                    raise ValueError('Private control request belongs to another session')
                            response = {'ok': True, 'result': session.dispatch(value)}
                        except Exception as error:
                            if not session.capture_uncertain:
                                session.last_error=str(error)
                            response = {'ok': False, 'error': str(error)}
                        if control.binding is not None:
                            response['_control_nonce'] = control.binding['nonce']
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
        control.close()


def initialize(args):
    """Ordinary initialization utility through the same real guest runtime."""
    import silicon_guest
    if args.backend=='qemu':import lemmasim_fast
    if args.force:raise ValueError('Matched initialization exclusively creates a new medium; --force is unsupported')
    if args.size_mib!=256:raise ValueError('The admitted development medium is exactly256MiB')
    initializer=getattr(args,'workload','initializer')
    if initializer not in ('initializer','parameterized-initializer') or (initializer=='parameterized-initializer' and args.profile!='lemma-silicon-dev/0.14.0'):raise ValueError('Initializer workload requires its exact admitted binding')
    # Fail before creating user data when preparation is stale or missing.
    if getattr(args,'native_bundle',None):
        import silicon_guest_bundle
        silicon_guest_bundle.prepared(args.native_bundle,args.backend,initializer,args.profile)
    elif args.backend=='rtl':silicon_guest.prepared(initializer,args.profile)
    else:
        import lemmasim_fast
        lemmasim_fast.prepared(initializer,args.profile)
    directory=(args.session_dir or ROOT/f'build/lemmasim/init-machine-{time.time_ns()}').resolve()
    directory.mkdir(parents=True,exist_ok=False)
    disk=args.disk.resolve();disk.parent.mkdir(parents=True,exist_ok=True)
    options=argparse.Namespace(backend=args.backend,profile=args.profile,workload=initializer,
        mode='developer',paused=True,quantum=1000000,timeout=min(args.timeout,120),
        disk=disk,memory_latency=0,fail_flush=None,events=None,trace_limit=0,
        native_bundle=getattr(args,'native_bundle',None))
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
    if metadata['identity']['profile'] in ('lemma-silicon-dev/0.14.0','lemma-silicon-dev/0.15.0'):
        def study():
            from lemmasim_school_panel import open_study
            open_study(window,directory)
        tk.Button(controls,text='Study',command=study).pack(side='left')
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
            fault=state.get('guest_fault')
            fault_text=(f" · Notebook fault (kernel cause0x{fault['cause']}, exit0x{fault['exitCode']}). Export the medium before recovery." if fault else '')
            loss=state.get('guest_ink_loss')
            loss_text=(' · Input loss report invalid; inspect the retained work.' if loss and loss['state']=='malformed' else
                f" · Input loss: {loss['discarded']} buffered samples discarded ({loss['cumulative']} total). Saved covers retained work; missing controller samples may be uncounted." if loss else '')
            status.set(f"cycle {produced['cycle']} · ticks {produced['ticks']} · " + ('running' if state['running'] else 'paused')+power_text+fault_text+loss_text)
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
