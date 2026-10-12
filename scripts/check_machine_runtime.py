#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real RTL checkpoint continuation, with existing independent guest oracles.

This checker neither writes machine state nor implements guest/device transitions.
It drives the lifecycle interface, observes real in-flight operations, restores
isolated forks, and compares complete suffix output and exact final checkpoints.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import struct
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'conformance/silicon'))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def validate_build(directory):
    from silicon_compute import source_manifest, prepare
    report = json.loads((directory / 'build.json').read_text())
    dep = ROOT / 'build/silicon/deps/cvw'
    prepare(dep)
    current = source_manifest(dep, report['profile'])
    if any(report.get(key) != value for key, value in current.items()):
        raise ValueError('RTL build consumed inputs differ from current sources')
    binary = directory / 'obj/lemma-rtl'
    if sha(binary) != report['binary_sha256'] or '--savable' not in report['build_options']['verilator']:
        raise ValueError('RTL checkpoint executable identity/serialization differs')
    header = report['runtime_identity_header']
    if sha(header['path']) != header['sha256']:
        raise ValueError('RTL implementation identity header changed')
    return binary, report


def validate_guest(directory):
    build = json.loads((directory / 'build.json').read_text())
    audit = json.loads((directory / 'audit.json').read_text())
    provenance = json.loads((directory / 'provenance.json').read_text())
    image = sha(directory / 'image.elf')
    audited_image = audit.get('image_sha256', audit.get('hashes', {}).get('image.elf'))
    if audit.get('status') not in ('PASS', 'pass') or audited_image != image:
        raise ValueError('Guest image lacks matching strict audit')
    artifacts = provenance.get('artifacts', audit.get('hashes', {}))
    if not artifacts or artifacts.get('image.elf') != image:
        raise ValueError('Guest provenance omits the exact linked image identity')
    for name, digest in artifacts.items():
        path = directory / name
        if not path.is_file() or sha(path) != digest:
            raise ValueError('Historical guest artifact changed: ' + name)
    commit = provenance.get('source_commit', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or audit.get('source_commit') != commit:
        raise ValueError('Historical guest source commit is absent or inconsistent')
    if subprocess.check_output(['git', 'rev-parse', commit + '^{commit}'], cwd=ROOT,
                               text=True).strip() != commit:
        raise ValueError('Historical guest source revision is unavailable')
    entries = provenance.get('source_inputs')
    if isinstance(entries, list):
        sources = {row['path']: row['sha256'] for row in entries}
        if len(sources) != len(entries):
            raise ValueError('Duplicate guest source identity')
    elif isinstance(entries, dict):
        sources = entries
    else:
        raise ValueError('Guest lacks consumed-source identities')
    if not sources:
        raise ValueError('Guest consumed-source inventory is empty')
    dirty = {line[3:] for line in provenance.get('dirty_paths', [])}
    revisions = {}
    generated = {}
    for name, digest in sources.items():
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('Malformed guest consumed-source identity: ' + name)
        if name.startswith('.lake/'):
            # Historical .olean bytes are not silently compared with current
            # .lake outputs. Their retained identity must be accounted for by
            # a genuine elaboration invocation and an exact source identity.
            rows = [row for row in provenance.get('elaborated_inputs', [])
                    if row.get('olean') == name and row.get('olean_sha256') == digest
                    and sources.get(row.get('source')) == row.get('source_sha256')
                    and row.get('source') in row.get('generation_command', [])]
            if len(rows) != 1:
                raise ValueError('Unaccounted historical generated input: ' + name)
            generated[name] = {'sha256': digest, 'source': rows[0]['source'],
                               'scope': 'retained elaboration/audit identity; original olean bytes unavailable'}
            continue
        result = subprocess.run(['git', 'show', commit + ':' + name], cwd=ROOT,
                                capture_output=True)
        if result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == digest:
            revisions[name] = commit
            continue
        if name not in dirty:
            raise ValueError('Consumed input differs from original clean source: ' + name)
        # The original monitor build records a dirty compilation. Recover its
        # exact recorded bytes from immutable subsequent Git blobs; never treat
        # its nominal commit or today's changed target tree as those bytes.
        candidates = subprocess.check_output(['git', 'log', '--all', '--format=%H', '--', name],
                                             cwd=ROOT, text=True).splitlines()
        for candidate in candidates:
            result = subprocess.run(['git', 'show', candidate + ':' + name], cwd=ROOT,
                                    capture_output=True)
            if result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == digest:
                revisions[name] = candidate
                break
        else:
            raise ValueError('Original dirty consumed-source bytes unavailable: ' + name)
    closures = provenance.get('target_module_closures', {})
    for unit, closure in closures.items():
        if not closure or any(sources.get(name) != digest for name, digest in closure.items()):
            raise ValueError('Guest module closure differs from consumed inputs: ' + unit)
    if not closures and not generated:
        raise ValueError('Guest lacks an accounted target elaboration/module closure')
    return {'build': sha(directory / 'build.json'), 'audit': sha(directory / 'audit.json'),
            'image': image, 'provenance': sha(directory / 'provenance.json'),
            'compilation_source': commit, 'consumed_source_revisions': revisions,
            'generated_input_identities': generated,
            'scope': 'validated historical guest bytes; this run is not fresh target compilation',
            'configuration': build.get('configuration')}


class Session:
    def __init__(self, binary, guest, rom, directory, extra=()):
        self.directory = directory
        directory.mkdir()
        self.log = (directory / 'process.log').open('wb')
        self.argv = [str(binary), '--image', str(guest / 'image.elf'), '--rom', str(rom),
                     '--session', '--quiet-uart', '--deadline', '600',
                     '--uart-output', str(directory / 'uart.bin'),
                     '--fork-directory', str(directory),
                     '--panel-output', str(directory / 'panel.pgm'),
                     '--report', str(directory / 'host-report.json'), *map(str, extra)]
        self.process = subprocess.Popen(self.argv, cwd=ROOT, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.log,
                                        start_new_session=True)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.rows = []

    def call(self, command, *, failure=False):
        start = time.monotonic()
        self.process.stdin.write((command + '\n').encode())
        self.process.stdin.flush()
        if not self.selector.select(610):
            raise RuntimeError('Machine command timed out')
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('Machine exited without lifecycle response')
        result = json.loads(line)
        self.rows.append({'command': command, 'seconds': time.monotonic() - start,
                          'response': result})
        if (result.get('ok') is True) == failure:
            raise RuntimeError('Unexpected lifecycle response: ' + line.decode())
        return result.get('result', result)

    def close(self):
        try:
            if self.process.poll() is None:
                self.call('destroy')
                self.process.wait(timeout=10)
            if self.process.returncode:
                raise RuntimeError('Machine exited with failure')
        finally:
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
            self.selector.close()
            self.log.close()
            (self.directory / 'commands.json').write_text(json.dumps(
                {'argv': self.argv, 'rows': self.rows, 'exit_code': self.process.returncode}, indent=2) + '\n')


def equal_observation(a, b):
    # Isolated backing ownership/path changes on restore; no guest/device/time field
    # is removed or normalized. The complete final checkpoint is also compared.
    external = {'isolated_medium', 'private_medium_path'}
    return {k: v for k, v in a.items() if k not in external} == {
        k: v for k, v in b.items() if k not in external}


def suffix(session, checkpoint, cycles, label):
    before = len((session.directory / 'uart.bin').read_bytes())
    first = session.call(f'run {cycles}')
    first_uart = (session.directory / 'uart.bin').read_bytes()[before:]
    first_file = session.directory / (label + '-direct.chk')
    session.call('snapshot ' + str(first_file))
    restored = session.call('restore ' + str(checkpoint))
    if not restored['isolated_medium']:
        raise ValueError('Restore did not isolate its medium')
    before = len((session.directory / 'uart.bin').read_bytes())
    second = session.call(f'run {cycles}')
    second_uart = (session.directory / 'uart.bin').read_bytes()[before:]
    second_file = session.directory / (label + '-fork.chk')
    session.call('snapshot ' + str(second_file))
    if not equal_observation(first, second) or first_uart != second_uart or sha(first_file) != sha(second_file):
        raise ValueError('Exact continuation mismatch at ' + label)
    return {'status': 'PASS', 'initial': restored, 'final': second,
            'uart_suffix_sha256': hashlib.sha256(second_uart).hexdigest(),
            'final_checkpoint_sha256': sha(second_file),
            'suffix_cycles': second['cycle'] - restored['cycle']}


def observer_controls(args, binary, out):
    results = {}
    for name, cutoff, marker in [('cycle-cutoff', 50, 'not emitted'),
                                 ('uart-marker', 500000, 'READY\n')]:
        session = Session(binary, args.monitor, args.rom, out / ('control-' + name),
                          ['--fail-flush', '7', '--observer-cycle', str(cutoff),
                           '--uart-stop-hex', marker.encode().hex()])
        try:
            session.call('run 12')
            checkpoint = session.directory / 'pending.chk'
            session.call('snapshot ' + str(checkpoint))
            expected = session.call('run 500000')
        finally:
            session.close()
        other = Session(binary, args.monitor, args.rom, out / ('control-fork-' + name),
                        ['--fail-flush', '99', '--observer-cycle', '1000000',
                         '--uart-stop-hex', b'different observer'.hex()])
        try:
            loaded = other.call('restore ' + str(checkpoint))
            resumed = other.call('run 500000')
            if loaded['fail_flush'] != 7 or not equal_observation(expected, resumed):
                raise ValueError('Snapshot did not restore fault/observer configuration')
            if name == 'cycle-cutoff' and resumed['cycle'] != cutoff:
                raise ValueError('Restored observer cycle cutoff was not enforced')
            if name == 'uart-marker' and (resumed['cycle'] >= cutoff or
                    not (other.directory / 'uart.bin').read_bytes().endswith(marker.encode())):
                raise ValueError('Restored UART marker was not enforced')
            results[name] = {'status': 'PASS', 'loaded': loaded, 'final': resumed}
        finally:
            other.close()
    return results


def monitor(args, binary, out):
    identity = validate_guest(args.monitor)
    session = Session(binary, args.monitor, args.rom, out / 'monitor',
                      ['--uart-input', args.monitor_input, '--memory-latency', '3'])
    try:
        pending = session.call('run 12')
        if pending['memory_pending'] != 1 or pending['memory_wait'] != 1 or pending['dma_outstanding'] != 1:
            raise ValueError('No observed outstanding CPU memory request at checkpoint')
        checkpoint = session.directory / 'pending.chk'
        session.call('snapshot ' + str(checkpoint))
        result = suffix(session, checkpoint, 10000000, 'cpu-memory')
        if not result['final']['finished'] or result['final']['finish_code'] != 0x5555:
            raise ValueError('Real monitor did not complete its guest protocol')
        # Each identical suffix executes every request. Observe one whole copy
        # using the existing independent arithmetic/trap/timer oracle.
        full = (session.directory / 'uart.bin').read_bytes()
        if len(full) % 2 or full[:len(full)//2] != full[len(full)//2:]:
            raise ValueError('Monitor suffix transcript is not two exact copies')
        observation = session.directory / 'oracle'
        observation.mkdir()
        (observation / 'uart.bin').write_bytes(full[:len(full)//2])
        session.close()
        shutil.copyfile(session.directory / 'host-report.json', observation / 'host-report.json')
        from monitor_observations import observe
        result['independent_monitor'] = observe(observation)
        result['guest_identity'] = identity
        # Fail-closed parser checks leave the live continuation unmodified.
        malformed = []
        check_session = Session(binary, args.monitor, args.rom, out / 'malformed')
        try:
            before = check_session.call('inspect')
            for name, offset, replacement in [('stale-identity',16,b'!'),
                                               ('oversized-wrapper',80,struct.pack('<Q',2**63)),
                                               ('checksum',104,b'!')]:
                bad = check_session.directory / (name + '.chk')
                shutil.copyfile(checkpoint, bad)
                with bad.open('r+b') as f:
                    f.seek(offset); f.write(replacement)
                failure = check_session.call('restore ' + str(bad), failure=True)
                after = check_session.call('inspect')
                if before != after:
                    raise ValueError('Rejected checkpoint mutated current machine')
                malformed.append({'case':name, 'error':failure['error']})
            truncated = check_session.directory / 'truncated.chk'
            truncated.write_bytes(checkpoint.read_bytes()[:112])
            malformed.append({'case':'truncated', 'error':check_session.call(
                'restore ' + str(truncated), failure=True)['error']})
            check_session.call('run 0', failure=True)
            check_session.call('run 20')
            check_session.call('inject 19 uart 00', failure=True)
        finally:
            check_session.close()
        result['malformed'] = malformed
        return result
    finally:
        if session.process.poll() is None:
            session.close()


def devices(args, binary, out):
    identity = validate_guest(args.devices)
    medium = out / 'device-medium.raw'
    with medium.open('xb') as f:
        f.write(bytes(range(256)) * 2)
        f.truncate(512*524288)
    medium_before = sha(medium)
    session = Session(binary, args.devices, args.rom, out / 'devices',
                      ['--load', '0x87e00000:' + str(args.devices/'platform.dtb'),
                       '--descriptor', args.devices/'descriptor.bin', '--medium', medium,
                       '--events', args.device_events])
    result = {'guest_identity':identity}
    try:
        session.call('run 7000000')
        for _ in range(1000):
            status = session.call('run 500')
            if status['paper_busy']:
                break
        else:
            raise ValueError('No actual accepted paper update observed')
        pending = session.directory / 'paper-pending.chk'
        session.call('snapshot ' + str(pending))
        result['paper'] = suffix(session, pending, 200000, 'paper')
        if result['paper']['initial']['paper_busy'] != 1 or result['paper']['final']['paper_busy'] != 0:
            raise ValueError('Paper checkpoint did not span guest cancellation')
        # Continue the restored machine; search a narrow bounded real guest
        # DMA window. No host edits to descriptors, queues or RAM are permitted.
        current = session.call('inspect')['cycle']
        if current < 24150000:
            session.call('run ' + str(24150000-current))
        for _ in range(40000):
            status = session.call('run 10')
            if status['block_state'] == 9:
                break
        else:
            raise ValueError('No actual block read payload DMA observed')
        pending = session.directory / 'block-pending.chk'
        session.call('snapshot ' + str(pending))
        result['block'] = suffix(session, pending, 500000, 'block-dma')
        if result['block']['initial']['block_state'] != 9 or result['block']['final']['block_state'] != 0:
            raise ValueError('Block snapshot did not span DMA completion')
        exported = session.directory / 'fork-durable.raw'
        session.call('export-medium ' + str(exported))
        if sha(exported) != medium_before or sha(medium) != medium_before:
            raise ValueError('Snapshot fork changed its unrelated durable backing')
        result['isolated_backing'] = 'PASS'
        # A different process begins with unrelated, deliberately different
        # durable bytes. Restoring cannot replace or mutate that backing file.
        unrelated = out / 'unrelated-medium.raw'
        with unrelated.open('xb') as f:
            f.write(b'unrelated user notebook medium\0')
            f.truncate(512*524288)
        unrelated_before = sha(unrelated)
        other = Session(binary, args.devices, args.rom, out / 'unrelated-fork',
                        ['--medium', unrelated])
        try:
            loaded = other.call('restore ' + str(pending))
            if not loaded['isolated_medium']:
                raise ValueError('Fresh-process restore retained unrelated backing ownership')
            other.call('run 500000')
            exported = other.directory / 'snapshot-owned-durable.raw'
            other.call('export-medium ' + str(exported))
            if sha(unrelated) != unrelated_before or sha(exported) != medium_before:
                raise ValueError('Fresh-process fork changed unrelated durable medium')
            result['unrelated_backing'] = {'status': 'PASS',
                'original_sha256': unrelated_before, 'snapshot_durable_sha256': sha(exported)}
        finally:
            other.close()
        return result
    finally:
        session.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--rtl-build', type=Path, required=True)
    p.add_argument('--monitor', type=Path, required=True)
    p.add_argument('--monitor-input', type=Path, required=True)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--devices', type=Path)
    p.add_argument('--device-events', type=Path)
    p.add_argument('--work-dir', type=Path, required=True)
    a = p.parse_args()
    if bool(a.devices) != bool(a.device_events):
        p.error('--devices and --device-events are required together')
    out = a.work_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    result = {'status':'FAIL', 'scope':'same-backend exact current digital subset; no cross-backend or cold-recovery claim'}
    try:
        binary, build = validate_build(a.rtl_build.resolve())
        result['binary_sha256'] = sha(binary)
        result['build_sha256'] = sha(a.rtl_build/'build.json')
        result['implementation_identity'] = build['snapshot_identity']
        result['observer_sha256'] = sha(__file__)
        result['monitor'] = monitor(a, binary, out)
        result['observer_controls'] = observer_controls(a, binary, out)
        if a.devices:
            result['devices'] = devices(a, binary, out)
        result['status'] = 'PASS'
    except BaseException as e:
        result['error'] = str(e)
        raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(out/'result.json')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as e:
        print('machine runtime: '+str(e), file=sys.stderr)
        sys.exit(1)
