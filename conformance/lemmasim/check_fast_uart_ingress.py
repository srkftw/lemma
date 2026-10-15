#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real canonical guest course installation through opt-in raw UART ingress.

Host-only raw transport and independent exported-byte observations. This is a
same-backend pending-input suffix check, not arbitrary QEMU cached-state or RTL
timing qualification. All publication and recovery run in the Lean RV64 guest.
"""
import argparse
import filecmp
import json
from pathlib import Path
import resource
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'conformance/lemmasim')]
from check_live_notebook import Checker, guest_events, idle, require, sha, visible_pixels
from course_package import decode
from lemmasim_course import frame
from lemmasim_fast import copy_new
from store_oracle import recover


class Case(Checker):
    profile = 'lemma-silicon-dev/0.3.0'
    backend = 'qemu'

    def __init__(self, args):
        super().__init__(args)
        self.cycles = 0
        self.report.update(schema='lemma-fast-uart-guest-conformance/1', phases=[],
                           scope=__doc__, bounds={**self.report['bounds'],
                           'aggregate_clocks': 3000000000, 'each_cold_clocks': 1000000000,
                           'each_install_or_load_clocks': 100000000,
                           'pending_snapshots': 1, 'per_process_address_bytes': 4 << 30})
        self.source_inputs = {str(p.relative_to(ROOT)): sha(p) for p in
                              [Path(__file__), *sorted((ROOT/'scripts').glob('*.py')),
                               ROOT/'scripts/lemmasim',
                               ROOT/'scripts/lemmasim-course',
                               *sorted((ROOT/'conformance/lemmasim').glob('*.py'))]}
        self.report['host_source_inputs'] = self.source_inputs
        if args.launcher:
            self.report['external_launcher'] = dict(path=str(args.launcher),
                sha256=sha(args.launcher),
                package_manifest_sha256=sha(args.launcher.parent/'package.json'))

    def launch(self, args, **kwargs):
        if not self.args.launcher:
            return super().launch(args, **kwargs)
        command = [sys.executable, '-I', str(self.args.launcher), *args]
        self.commands.write(json.dumps(command)+'\n')
        self.commands.flush()
        return subprocess.Popen(command, cwd='/tmp', **kwargs)

    def write(self):
        (self.directory/'result.json').write_text(json.dumps(self.report, default=str, indent=2)+'\n')

    def rows(self, session):
        return guest_events(getattr(session, 'uart_path', session.directory/'uart-0.bin'))

    def state(self, session):
        return session.inspect()['machine']

    def uart(self, session):
        return self.state(session)['devices']['uart_ingress']

    def run(self, session, clocks):
        require(time.monotonic() < self.deadline, 'whole host deadline')
        before = self.state(session)['cycle']
        session.run(clocks)
        self.cycles += self.state(session)['cycle'] - before
        require(self.cycles <= 3000000000, 'aggregate virtual resource bound')

    def until(self, session, name, limit, predicate):
        initial, started, steps = self.state(session)['cycle'], time.monotonic(), []
        while not predicate():
            require(self.state(session)['cycle']-initial < limit, name+' virtual deadline')
            require(not self.state(session)['finished'] and
                    not any(r[0] in (0x41f, 0xd4, 0xf4, 0x424) for r in self.rows(session)),
                    'guest fault or unsuccessful save in '+name)
            step = min(1000000, limit-(self.state(session)['cycle']-initial))
            self.run(session, step)
            steps.append(step)
        self.report['phases'].append(dict(name=name, clocks=self.state(session)['cycle']-initial,
                                         seconds=time.monotonic()-started))
        self.write()
        return steps

    def inject(self, session, payload, cycle):
        for offset in range(0, len(payload), 4096):
            session.control(dict(action='inject', kind='uart', cycle=cycle,
                                 hex=payload[offset:offset+4096].hex()))

    def equal(self, actual, expected, name):
        (self.directory/(name+'.json')).write_text(json.dumps(
            {'actual': actual, 'expected': expected}, indent=2)+'\n')
        require(actual == expected, name+' differs; both observations retained')

    def execute(self):
        raw = self.args.package.read_bytes()
        package = decode(raw)
        identity, edition, crc = (package[k] for k in ('identity', 'edition', 'crc32'))
        key = (1, 0x4350000000000000 | (identity << 32) | edition)
        packet = frame(1, identity, edition, len(raw), 1, crc)+raw
        require(self.args.package.stat().st_size <= 32768, 'bounded authored package required')
        disk = self.directory/'initialized.raw'
        # This is the ordinary actual initializer, never a host formatter.
        command = ['init', '--backend', 'qemu', '--profile', self.profile,
            '--disk', str(disk), '--session-dir', str(self.directory/'initializer'),
            '--timeout', str(self.args.timeout)]
        if self.args.native_bundle:
            command += ['--native-bundle', self.args.native_bundle]
        self.command(command)
        self.report['initializer'] = json.loads((self.directory/'initializer/result.json').read_text())
        require(self.report['initializer']['status'] == 'ACKNOWLEDGED_GUEST_INITIALIZATION'
                and self.report['initializer']['medium_sha256'] == sha(disk),
                'actual guest initializer result or medium differs')
        _, sequence, records = recover(disk.read_bytes())
        require(sequence == 0 and not records, 'guest initializer did not produce empty Store')
        capacity_disk = self.directory/'capacity.raw'
        copy_new(disk, capacity_disk)
        capacity = self.session('capacity', capacity_disk)
        for _ in range(16):
            self.inject(capacity, bytes(4096), 1000000)
        full = self.state(capacity)
        require(full['cycle'] == 0 and full['devices']['uart_ingress']['pending'] == 65536,
                'declared full external queue not reached')
        try:
            self.inject(capacity, b'x', 1000000)
        except RuntimeError as error:
            require('capacity' in str(error), 'unexpected full-queue rejection')
        else:
            raise ValueError('over-capacity input admitted')
        self.equal(self.state(capacity), full, 'capacity-rejection-no-mutation')
        require(capacity.inspect()['capture_uncertain'],
                'failed external admission was not quarantined by session capture')
        capacity.close()
        self.sessions.remove(capacity)
        self.report['bounded_queue'] = dict(bytes=65536, rejected_without_mutation=True,
                                            capture_quarantined=True, no_guest_clocks=True)
        live_disk = self.directory/'live.raw'
        copy_new(disk, live_disk)
        session = self.session('live', live_disk)
        self.report['identity'] = session.identity
        require(session.identity['adapter'] == 'lemmasim-fast-adapter/5' and
                self.state(session)['cycle'] == 0, 'actual reset raw UART backend required')
        self.inject(session, b'abc', 1000000)
        before = self.uart(session)
        require(before['pending'] == 3 and before['delivered'] == 0, 'future bytes offered early')
        session.control({'action': 'warm-reset'})
        after = self.uart(session)
        require(after['pending'] == 0 and after['canceled'] == 3 and
                after['reset_epoch'] == before['reset_epoch']+1, 'pending reset cancellation failed')
        self.report['reset'] = {'before': before, 'after': after}
        self.until(session, 'cold-Ready', 1000000000, lambda:
                   idle(self.state(session)) and self.state(session)['devices']['paper']['completed'] >= 1
                   and any(r[0] == 0x420 for r in self.rows(session)))
        before = self.state(session)
        try:
            session.control({'action': 'inject', 'kind': 'uart', 'hex': '0g'})
        except RuntimeError as error:
            require('UART requires' in str(error), 'unexpected malformed-input rejection')
        else:
            raise ValueError('malformed bytes accepted')
        self.equal(self.state(session), before, 'malformed-input-no-mutation')
        at, body = before['cycle'], packet[64:]
        half = len(body)//2
        self.inject(session, body[:half], at+10000)
        self.inject(session, body[half:], at+10000)
        self.inject(session, packet[:64], at+10)
        self.run(session, 64)
        cut = self.state(session)
        uart = cut['devices']['uart_ingress']
        require(uart['pending'] > 0 and uart['delivered'] > 0 and
                uart['serial_can_receive'] == 0 and uart['timer_pending'],
                'actual nonempty backpressured UART/frontend and external queue cut absent')
        require(not any(r[0] == 0x4b1 for r in self.rows(session)), 'installation already completed')
        checkpoint = self.directory/'pending'
        session.control({'action': 'snapshot', 'path': str(checkpoint)})
        self.equal(self.state(session), cut, 'snapshot-no-mutation')
        # Keep a privately backed negative whose outer hashes are valid. This
        # must reach the real VMState version check, not just a file checksum.
        incompatible = self.directory/'missing-required-uart-version'
        incompatible.mkdir()
        manifest = json.loads((checkpoint/'snapshot.json').read_text())
        for item in manifest['files']:
            copy_new(checkpoint/item['path'], incompatible/item['path'])
        machine = incompatible/'machine.chk'
        image = bytearray(machine.read_bytes())
        name = b'lemma-paper-pen/1'
        offset = image.find(name)
        require(offset >= 6 and image[offset-6] == 4 and image[offset-1] == len(name)
                and struct.unpack_from('>2I', image, offset+len(name)) == (0, 4),
                'pinned actual mandatory UART VMState section not found')
        struct.pack_into('>I', image, offset+len(name)+4, 3)
        machine.write_bytes(image)
        for item in manifest['files']:
            if item['path'] == 'machine.chk':
                item['sha256'] = sha(machine)
        (incompatible/'snapshot.json').write_text(json.dumps(manifest, indent=2)+'\n')
        try:
            session.control({'action': 'restore', 'path': str(incompatible)})
        except RuntimeError as error:
            require('version' in str(error) and 'lemma-paper-pen/1' in str(error),
                    'negative did not reach the actual required VMState version check')
            self.report['required_uart_state_rejection'] = str(error)
        else:
            raise ValueError('missing required UART state version accepted')
        self.equal(self.state(session), cut, 'incompatible-restore-live-unchanged')
        prefix = (session.directory/'uart-0.bin').read_bytes()
        def installed():
            return idle(self.state(session)) and self.uart(session)['pending'] == 0 and any(
                r[0] == 0x4b1 and r[1] == 1 and r[3:] == (identity | (edition << 16), crc)
                for r in self.rows(session))
        steps = self.until(session, 'actual-raw-guest-installation', 100000000, installed)
        original = self.state(session)
        require(original['storage']['backing_durable_barrier'] >
                cut['storage']['backing_durable_barrier'], 'Installed precedes actual backing barrier')
        panel, medium = session.export('original')
        require(recover(medium.read_bytes())[2][key].payload == raw, 'published package bytes differ')
        suffix = (session.directory/'uart-0.bin').read_bytes()[len(prefix):]
        original_backing = sha(live_disk)
        session.control({'action': 'restore', 'path': str(checkpoint)})
        self.equal(self.state(session), cut, 'restored-cut')
        files = list(session.directory.glob('machine-fork-*/uart-1.bin'))
        require(len(files) == 1, 'private fork UART output missing')
        session.uart_path = files[0]
        for clocks in steps:
            self.run(session, clocks)
        self.equal(self.state(session), original, 'applicable-suffix-state')
        require(session.uart_path.read_bytes() == suffix, 'actual guest UART suffix differs')
        fork_panel, fork_medium = session.export('fork')
        require(filecmp.cmp(medium, fork_medium, shallow=False) and
                visible_pixels(panel) == visible_pixels(fork_panel), 'all backing bytes/controller pixels differ')
        require(sha(live_disk) == original_backing, 'fork altered original backing')
        self.report['pending_suffix'] = dict(nonempty_uart_and_external_queue=True,
            strict_cut_and_final_states=True, exact_guest_output=True,
            whole_backing_bytes=True, all_controller_pixels=True, isolated_fork=True, steps=steps)
        session.close()
        self.sessions.remove(session)
        cold_disk = self.directory/'cold.raw'
        copy_new(medium, cold_disk)
        cold = self.session('cold', cold_disk)
        require(self.state(cold)['cycle'] == 0, 'independent cold CPU required')
        self.until(cold, 'independent-cold-Ready', 1000000000, lambda:
                   idle(self.state(cold)) and self.state(cold)['devices']['paper']['completed'] >= 1
                   and any(r[0] == 0x420 for r in self.rows(cold)))
        # A real guest load establishes that recovered package bytes can be
        # consumed through Store and the Lean package validator after reset.
        # Exercise the installed ordinary command surface, not a host-side
        # Store parser or a replacement package loader.
        command = ([sys.executable, '-I', str(self.args.launcher), 'course-load']
                   if self.args.launcher else
                   [sys.executable, str(ROOT/'scripts/lemmasim-course'), 'load']) + [
                   '--session-dir', str(cold.directory), '--identity', str(identity),
                   '--edition', str(edition), '--node', '0', '--crc', str(crc)]
        self.commands.write(json.dumps(command)+'\n')
        self.commands.flush()
        completed = subprocess.run(command, cwd='/tmp' if self.args.launcher else ROOT,
                                   capture_output=True, text=True,
                                   timeout=min(120, self.deadline-time.monotonic()), check=True)
        admission = json.loads(completed.stdout)
        require(admission['status'] == 'RAW_COMMAND_ADMITTED' and admission['operation'] == 2,
                'ordinary course command did not admit raw load')
        self.report['ordinary_cold_load_command'] = admission
        self.until(cold, 'cold-guest-package-load', 100000000, lambda:
                   idle(self.state(cold)) and any(r[0] == 0x4b2 and r[1:] ==
                       (len(raw), crc, identity, edition) for r in self.rows(cold)))
        _, reopened = cold.export('cold-reopened')
        require(recover(reopened.read_bytes())[2][key].payload == raw, 'cold package changed')
        self.report.update(status='PASS_REAL_RAW_UART_INSTALL_PENDING_FORK_COLD_LOAD',
            instruction_clocks=self.cycles,
            remaining=['full ISA/cache/timing parity and arbitrary-boundary continuation',
                       'complete USB/radio/browser/mathematical product obligations'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    frontend = parser.add_mutually_exclusive_group(required=True)
    frontend.add_argument('--native-bundle', type=Path)
    frontend.add_argument('--launcher', type=Path, help='Extracted native run.py; launches from /tmp with Python -I')
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--deadline', type=int, default=600)
    args = parser.parse_args()
    require(1 <= args.timeout <= 120 and 1 <= args.deadline <= 600, 'bounded host deadlines required')
    args.durable_suffix_from = None
    args.native_bundle = str(args.native_bundle.resolve()) if args.native_bundle else None
    args.launcher = args.launcher.resolve() if args.launcher else None
    args.checkpoint_relation = 'raw-uart-observations-and-applicable-suffix-only'
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    case = Case(args)
    try:
        case.execute()
    except BaseException as error:
        case.report.update(status='FAIL', error=repr(error))
        raise
    finally:
        cleanup_errors = []
        for session in case.sessions:
            try:
                session.close()
            except BaseException as error:
                cleanup_errors.append(repr(error))
        if cleanup_errors:
            case.report.update(status='FAIL', cleanup_errors=cleanup_errors)
        case.commands.close()
        case.report.update(seconds=time.monotonic()-case.started,
            host_sources_unchanged=all(sha(ROOT/p) == digest for p, digest in case.source_inputs.items()),
            maximum_single_child_rss_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024)
        if case.report['host_sources_unchanged'] is not True:
            case.report['status'] = 'FAIL'
        case.write()
    require(case.report['status'].startswith('PASS_'), 'actual conformance failed')


if __name__ == '__main__':
    main()
