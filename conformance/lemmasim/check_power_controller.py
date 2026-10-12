#!/usr/bin/env python3
"""Independent literal Power-v1/QEMU boundary checks; qtest runs no guest."""
import argparse
import hashlib
import json
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from lemmasim_fast import QMP, CPU

POWER, PAPER, PEN = 0x10010500, 0x10010000, 0x10011000
HARDWARE = '/machine/lemma-hardware'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Probe:
    def __init__(self, qemu, dtb, directory, medium, debug=False):
        self.directory = directory
        self.sockets = tempfile.TemporaryDirectory(prefix='lemma-power-', dir='/tmp')
        sockets = Path(self.sockets.name)
        self.log = (directory / 'machine.log').open('xb')
        self.argv = [str(qemu.resolve()), '-machine', 'lemma-silicon-fast', '-cpu', CPU if debug else 'rv64',
                     '-accel', 'tcg' if debug else 'qtest', '-m', '128M', '-smp', '1', '-bios', 'none',
                     '-dtb', str(dtb.resolve()), '-display', 'none', '-monitor', 'none',
                     '-serial', 'none', '-S',
                     '-qmp', f'unix:{sockets}/qmp,server=on,wait=off',
                     '-global', f'lemma-fast-block.medium={medium}']
        self.argv += ['-gdb', f'unix:{sockets}/gdb,server=on,wait=off'] if debug else [
            '-qtest', f'unix:{sockets}/qtest,server=on,wait=off']
        self.process = subprocess.Popen(self.argv, stdout=self.log, stderr=self.log)
        self.qmp = None
        self.channel = None
        self.gdb = None
        self.wire = []
        self.gdb_wire = []
        try:
            self.qmp = QMP(sockets / 'qmp', self.process, 20)
            if debug:
                self.gdb = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.gdb.settimeout(10)
                self.gdb.connect(str(sockets / 'gdb'))
            else:
                self.channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.channel.settimeout(10)
                self.channel.connect(str(sockets / 'qtest'))
                self.stream = self.channel.makefile('rwb', buffering=0)
                self.qmp.execute('cont')
        except BaseException:
            self.close()
            raise

    def q(self, command):
        self.stream.write(command.encode() + b'\n')
        line = self.stream.readline(1048577)
        self.wire.append([command, line.decode().strip()])
        if not line.startswith(b'OK'):
            raise RuntimeError(f'qtest rejected {command}: {line!r}')
        return line.split()[1:]

    def read(self, address, width='q'):
        return int(self.q(f'read{width} {address:#x}')[0], 0)

    def debug_packet(self, command):
        # The debug-memory path returns MemTxResult failures to its caller;
        # qtest's memory commands always report OK even on a device bus error.
        payload = command.encode()
        self.gdb.sendall(b'$' + payload + b'#' + f'{sum(payload) & 255:02x}'.encode())
        for _ in range(64):
            value = self.gdb.recv(1)
            if not value:
                raise RuntimeError('GDB memory observer disconnected')
            if value == b'$':
                break
        else:
            raise RuntimeError('GDB memory reply prefix exceeds bound')
        reply = bytearray()
        while True:
            value = self.gdb.recv(1)
            if not value or len(reply) > 256:
                raise RuntimeError('bounded GDB memory reply rejected')
            if value == b'#':
                break
            reply.extend(value)
        checksum = bytearray()
        while len(checksum) < 2:
            value = self.gdb.recv(2-len(checksum))
            if not value:
                raise RuntimeError('GDB memory checksum truncated')
            checksum.extend(value)
        if int(checksum, 16) != sum(reply) & 255:
            raise RuntimeError('GDB memory reply checksum mismatch')
        self.gdb.sendall(b'+')
        self.gdb_wire.append([command, reply.decode()])
        return reply.decode()

    def write(self, address, value, width='q'):
        self.q(f'write{width} {address:#x} {value:#x}')

    def now(self):
        return int(self.qmp.execute('qom-get', {'path': HARDWARE, 'property': 'virtual-time'}))

    def step(self, ns):
        return int(self.q(f'clock_step {ns}')[0], 0)

    def state(self):
        return json.loads(self.qmp.execute('qom-get', {'path': HARDWARE, 'property': 'power-state'}))

    def devices(self):
        return json.loads(self.qmp.execute('qom-get', {'path': HARDWARE, 'property': 'device-state'}))

    def inject(self, property, value):
        self.qmp.execute('qom-set', {'path': HARDWARE, 'property': property, 'value': value})

    def save(self, path):
        self.qmp.execute('lemma-save-machine', {'filename': str(path.resolve())})

    def close(self):
        if self.qmp is not None:
            self.qmp.close()
        if self.channel is not None:
            self.stream.close()
            self.channel.close()
        if self.gdb is not None:
            self.gdb.close()
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)
        self.log.close()
        self.sockets.cleanup()


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt('bounded controller probe terminated')
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser()
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--dtb', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    medium = directory / 'durable.raw'
    with medium.open('xb') as stream:
        stream.truncate(256 * 1024 * 1024)
    report = {'status': 'FAIL', 'scope': 'literal digital Power-v1 only; qtest executes no guest',
              'qemu_sha256': digest(args.qemu), 'dtb_sha256': digest(args.dtb), 'observations': []}
    report['observer_sha256'] = digest(__file__)
    machine = fork = debug = None
    try:
        debug_dir = directory / 'bus-debug'
        debug_dir.mkdir()
        debug = Probe(args.qemu, args.dtb, debug_dir, medium, debug=True)
        report['bus_debug_argv'] = debug.argv
        assert debug.debug_packet(f'm{POWER:x},8') == '5257504c00000000'
        for address, size in [(POWER, 4), (POWER + 96, 8), (POWER + 1, 8)]:
            assert debug.debug_packet(f'm{address:x},{size:x}').startswith('E')
            assert debug.state()['error'] == 2 and debug.state()['state'] == 0
            assert debug.debug_packet(f'M{POWER + 88:x},8:0100000000000000') == 'OK'
        report['bus_debug_wire'] = debug.gdb_wire
        debug.close()
        debug = None
        machine = Probe(args.qemu, args.dtb, directory, medium)
        report['argv'] = machine.argv
        assert machine.read(POWER) == 0x4c505752
        assert machine.read(PAPER + 1024 + 8) == 4
        assert machine.read(PAPER + 1024 + 25 * 8) == POWER
        assert machine.state() == {'enabled': True, 'state': 0, 'error': 0, 'reset_cause': 1,
                                  'button_level': 0, 'events': 0, 'epoch': 0, 'wake_cause': 0}
        for address, width in [(POWER, 'l'), (POWER + 96, 'q'), (POWER + 1, 'q')]:
            machine.read(address, width)
            assert machine.read(POWER + 24) == 2
            machine.write(POWER + 88, 1)
        machine.write(POWER + 72, 3)
        assert machine.read(POWER + 24) == 2 and machine.read(POWER + 16) == 0
        machine.write(POWER + 88, 1)
        report['observations'].append('ABI4 discovery and malformed access fault without power effect')

        machine.inject('external-button', '100 1')
        machine.inject('external-button', '100 0')
        machine.step(100)
        assert machine.read(POWER + 56) == 0 and machine.read(POWER + 40) == 0
        machine.inject('external-button', '120 0')
        machine.inject('external-button', '120 1')
        machine.step(20)
        assert machine.read(POWER + 56) == 1 and machine.read(POWER + 48) == 1
        machine.inject('external-button', '130 1')
        machine.step(10)
        assert machine.read(POWER + 56) == 1
        machine.write(POWER + 80, 1)
        report['observations'].append('equal-time last raw level wins one physical edge; held level is not another edge')

        # Fill the entire external ring, then insert a new earlier boundary.
        # The pen's raw sample fields must survive ring shifts and wraparound;
        # sample TIME is deliberately independent of delivery nanoseconds.
        now = machine.now()
        for _ in range(4093):
            machine.inject('external-button', f'{now + 10} 0')
        machine.inject('external-event', f'{now + 20} 77 54321 23456 1234 2 2 5')
        machine.inject('external-button', f'{now + 5} 0')
        machine.inject('external-button', f'{now + 30} 0')
        try:
            machine.inject('external-event', f'{now + 40} 78 1 2 0 2 1 0')
        except RuntimeError as error:
            assert 'capacity4096' in str(error)
        else:
            raise AssertionError('full external queue admitted another sample')
        machine.step(5)
        assert machine.read(PEN + 32) == 0 and machine.read(POWER + 40) == 0
        machine.step(15)
        expected = [1, 77, 54321, 23456, 1234, 2, 2, 5, 1]
        assert machine.read(PEN + 32) == 1
        assert [machine.read(PEN + 256 + 8*i) for i in range(9)] == expected
        machine.write(PEN + 88, 1)
        machine.step(10)
        delivery = machine.now() + 10
        for sample_time, x in [(78, 111), (79, 222)]:
            machine.inject('external-event', f'{delivery} {sample_time} {x} 2 0 2 1 0')
        machine.step(10)
        for sequence, sample_time, x in [(2, 78, 111), (3, 79, 222)]:
            assert machine.read(PEN + 256) == sequence
            assert machine.read(PEN + 264) == sample_time and machine.read(PEN + 272) == x
            machine.write(PEN + 88, sequence)
        assert machine.read(PEN + 32) == 0
        machine.qmp.execute('stop')
        now = machine.now()
        machine.inject('external-event', f'{now + 100} 80 333 2 0 2 1 0')
        machine.inject('external-button', f'{now} 0')
        machine.qmp.execute('cont')
        machine.step(100)
        assert machine.read(PEN + 32) == 1
        assert machine.read(PEN + 256) == 4 and machine.read(PEN + 264) == 80
        assert machine.read(PEN + 272) == 333
        machine.write(PEN + 88, 4)
        report['observations'].append('bounded full ring accepts stable earlier-future insertion; wrapped raw pen fields and equal-time order preserved')

        # An invalid queue notify leaves a real controller fault IRQ even
        # though its transfer phase is IDLE. Suspend must respect that source.
        machine.write(0x10001000 + 80, 0, 'l')
        assert machine.read(0x10001000 + 112, 'l') & 64
        assert machine.read(0x10001000 + 96, 'l') == 2
        machine.write(POWER + 72, 1)
        assert machine.read(POWER + 16) == 0 and machine.read(POWER + 24) == 1
        machine.write(0x10001000 + 112, 0, 'l')
        assert machine.read(0x10001000 + 96, 'l') == 0
        report['observations'].append('real block fault/completion interrupt independently rejects suspend until controller reset')

        # One immutable two-pixel update establishes an independent paper BUSY.
        for offset, value in [(112, 1), (120, 0), (128, 0), (136, 2), (144, 1), (152, 1)]:
            machine.write(PAPER + offset, value)
        start = machine.now()
        machine.write(PAPER + 104, 2)
        machine.write(POWER + 72, 1)
        assert machine.read(POWER + 16) == 0 and machine.read(POWER + 24) == 1
        assert machine.read(PAPER + 16) & 1
        # A pure observer must leave the serialized phase untouched.
        sequence_start = ((start + 2_000_000 + 9) // 10) * 10
        machine.step(sequence_start + 50 - machine.now())
        machine.qmp.execute('stop')
        first = directory / 'phase-before-inspection.chk'
        machine.save(first)
        before = machine.devices()
        assert before['paper']['status'] & 1 and before['paper']['sequencer']['power']
        assert machine.devices() == before
        second = directory / 'phase-after-inspection.chk'
        machine.save(second)
        assert first.read_bytes() == second.read_bytes(), 'inspection changed paused private state'
        machine.qmp.execute('cont')
        machine.step(sequence_start + (11 * 2 + 7) * 10 - machine.now())
        assert machine.read(PAPER + 160) == 1 and not machine.read(PAPER + 16) & 1
        report['observations'].append('paper BUSY rejects without drain; midphase inspection preserves exact state; timer completes digital update')

        # Accepted suspend prunes future pen only, preserving the physical wake.
        now = machine.now()
        machine.inject('external-event', f'{now + 100} 5 1 2 0 2 1 0')
        machine.inject('external-button', f'{now + 200} 0')
        machine.inject('external-button', f'{now + 300} 1')
        pen_epoch = machine.read(PEN + 40)
        machine.write(POWER + 72, 1)
        assert machine.read(POWER + 16) == 1 and machine.read(POWER + 24) == 0
        assert machine.read(PEN + 40) == pen_epoch + 1 and machine.read(PEN + 32) == 0
        machine.write(POWER + 72, 1)
        assert machine.read(POWER + 24) == 1
        machine.write(POWER + 88, 1)
        suspended = directory / 'suspended.chk'
        machine.qmp.execute('stop')
        machine.save(suspended)
        assert machine.state()['state'] == 1
        fork_dir = directory / 'isolated-fork'
        fork_dir.mkdir()
        fork_medium = fork_dir / 'durable.raw'
        with fork_medium.open('xb') as stream:
            stream.truncate(256 * 1024 * 1024)
        fork = Probe(args.qemu, args.dtb, fork_dir, fork_medium)
        # qtest's externally controlled clock is fixture state, outside the
        # TCG machine's serialized clock. Set this literal fixture boundary
        # explicitly; genuine CPU/time continuation is exercised by sessions.
        fork.qmp.execute('stop')
        fork.step(machine.now())
        fork.qmp.execute('lemma-load-machine', {'filename': str(suspended.resolve())})
        assert fork.state() == machine.state() and fork.now() == machine.now()
        # A coincident pen sample observes SUSPENDED before the wake edge.
        for peer in (machine, fork):
            peer.inject('external-event', f'{now + 300} 6 1 2 0 2 1 0')
            peer.qmp.execute('cont')
            peer.step(300)
            assert peer.read(PEN + 32) == 0
            assert peer.state() == {'enabled': True, 'state': 0, 'error': 0, 'reset_cause': 1,
                                    'button_level': 1, 'events': 2, 'epoch': 2, 'wake_cause': 1}
        assert machine.devices() == fork.devices() and medium.read_bytes() == fork_medium.read_bytes()
        machine.write(POWER + 80, 2)
        machine.write(POWER + 72, 1)
        machine.write(POWER + 72, 2)
        assert machine.read(POWER + 48) == 2 and machine.read(POWER + 64) == 2
        machine.qmp.execute('system_reset')
        deadline = time.monotonic() + 10
        while machine.state()['reset_cause'] != 2:
            if time.monotonic() > deadline:
                raise TimeoutError('warm RESET completion')
            time.sleep(.001)
        assert machine.state() == {'enabled': True, 'state': 0, 'error': 0, 'reset_cause': 2,
                                  'button_level': 1, 'events': 0, 'epoch': 2, 'wake_cause': 0}
        report['observations'].append('suspend pen loss and future pruning, queued wake and same-boundary discard survive isolated VMState restore; authorized resume and warm retention')
        report['status'] = 'PASS'
    except BaseException as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        for name, peer in [('bus-debug', debug), ('original', machine), ('fork', fork)]:
            if peer is not None:
                report[name + '_wire'] = peer.wire
                report[name + '_debug_bus_wire'] = peer.gdb_wire
                peer.close()
        (directory / 'result.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
