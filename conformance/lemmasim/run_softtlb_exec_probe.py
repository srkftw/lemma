#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual Lean executable translation and self-modification checkpoint experiment.

Uses the existing machine owner and logical sidecar. Two guest-created cached
states are observed; no host PTE/instruction writes, flushes, drains or fences.
This finite experiment cannot certify arbitrary QEMU continuation.
"""
import argparse
import json
from pathlib import Path
import re
import resource
import time

from run_softtlb_probe import Machine, require, sha

SEMANTIC = ('schema', 'binding', 'boundary_ns', 'inactive_boundary', 'common', 'modes')


def semantic(cache):
    # File SHA and decoder byte offsets describe the container, rather than
    # cache semantics. Every declared slot, flag and counter remains compared.
    return {key: cache[key] for key in SEMANTIC}


def counters(machine):
    text = machine.qmp.execute('human-monitor-command', {'command-line': 'info jit'})
    fields = {}
    for name in ('TB flush count', 'TB invalidate count', 'TLB full flushes',
                 'TLB partial flushes', 'TLB elided flushes'):
        found = re.findall(r'^' + re.escape(name) + r'\s+(\d+)\s*$', text, re.M)
        require(len(found) == 1, 'Pinned JIT observation missing: ' + name)
        fields[name] = int(found[0])
    return {'counters': fields, 'raw': text}


def capture(machine, path):
    before, jit_before = machine.state(), counters(machine)
    cache = machine.save(path)
    after, jit_after = machine.state(), counters(machine)
    require(before == after, 'Snapshot mutated guest-visible state')
    require(jit_before['counters'] == jit_after['counters'], 'Snapshot flushed/invalidated original caches')
    return {'cache': cache, 'state': after, 'jit_before': jit_before, 'jit_after': jit_after,
            'machine_sha256': sha(path), 'machine_bytes': path.stat().st_size}


def execution_entry(cache, physical):
    hits = []
    for index, mode in enumerate(cache['modes']):
        for bank in ('primary', 'victim'):
            for slot, entry in enumerate(mode[bank]):
                if (entry and entry['virtual_page'] == 0x82050000 and
                        entry['tags'][2] != (1 << 64) - 1):
                    hits.append({'mode': index, 'bank': bank, 'slot': slot, 'entry': entry})
    require(hits and all(row['entry']['phys_addr'] == physical for row in hits),
            'Actual warmed executable comparator/physical mapping missing')
    return hits


def words(machine):
    text = machine.qmp.execute('human-monitor-command', {'command-line': 'xp /4gx 0x82105000'})
    rows = re.findall(r'^([0-9a-fA-F]+):\s+0x([0-9a-fA-F]{16})\s+0x([0-9a-fA-F]{16})\s*$', text, re.M)
    require(len(rows) == 2 and [int(row[0], 16) for row in rows] == [0x82105000, 0x82105010],
            'Unsupported actual guest-word observation: ' + repr(text))
    values = [int(value, 16) for row in rows for value in row[1:]]
    return dict(zip(('stale_exec', 'fenced_exec', 'unfenced_code', 'fenced_code'), values))


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--qemu', type=Path, required=True)
    p.add_argument('--guest-build', type=Path, required=True)
    p.add_argument('--dtb', type=Path, required=True)
    p.add_argument('--work-dir', type=Path, required=True)
    a = p.parse_args()
    for name in ('qemu', 'guest_build', 'dtb', 'work_dir'):
        setattr(a, name, getattr(a, name).resolve())
    a.guest_elf, a.logical, a.timeout = a.guest_build / 'image.elf', True, 120
    require(not a.work_dir.exists(), 'Unused output required')
    a.work_dir.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    started, owners = time.monotonic(), []
    report = {'status': 'RUNNING', 'scope': __doc__,
              'plan': {'first_ns': 1000000, 'modified_search_limit_ns': 400000000,
                       'modified_search_step_ns': 1000000, 'end_ns': 1000000000,
                       'whole_seconds': 600, 'interval_seconds': 120,
                       'process_AS_bytes': 4 << 30, 'file_bytes': 1 << 30,
                       'external_events': [], 'storage': 'absent, private per machine'},
              'inputs': {name: {'path': str(path), 'sha256': sha(path)} for name, path in
                         [('qemu', a.qemu), ('guest_elf', a.guest_elf), ('dtb', a.dtb),
                          ('guest_provenance', a.guest_build / 'result.json'),
                          ('observer', Path(__file__)),
                          ('owner', Path(__file__).with_name('run_softtlb_probe.py')),
                          ('decoder', Path(__file__).with_name('check_logical_softtlb.py'))]}}
    def update():
        report['seconds'] = time.monotonic() - started
        (a.work_dir / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    def own(name):
        require(time.monotonic() - started < 600, 'Prospective whole deadline')
        machine = Machine(a, a.work_dir / name)
        owners.append(machine)
        return machine
    try:
        provenance = json.loads((a.guest_build / 'result.json').read_text())
        require(provenance['status'] == 'PASS_GENUINE_LEAN_EXECUTABLE_SOFTTLB_TEST_IMAGE',
                'Genuine audited build required')
        outputs = {'image.elf', 'program.ll', 'program.opt.ll', 'program.o',
                   'startup.S', 'startup.o', 'link.ld', 'symbols.txt',
                   'normalized.txt', 'elf-audit.log', 'disassembly.log'}
        require(set(provenance['outputs']) == outputs and all(
            sha(a.guest_build / name) == digest for name, digest in provenance['outputs'].items()),
            'Original compiled/audited output closure differs')
        original = own('original')
        report['prefix'] = original.run(1000000)
        require((original.path / 'uart.bin').read_bytes() == b'W', 'First actual guest cache marker missing')
        first = a.work_dir / 'warmed.vmstate'
        report['first_capture'] = capture(original, first)
        report['first_execution_hits'] = execution_entry(report['first_capture']['cache'], 0x82103000)
        fork = own('fork-warmed')
        fork.load(first)
        report['first_restored_state'] = fork.state()
        require(report['first_restored_state'] == report['first_capture']['state'], 'First restore state differs')
        # Observe the first fixed 1ms boundary after the guest's actual code
        # store; the bounded search never imposes a clean-cache precondition.
        search_started = time.monotonic()
        for boundary in range(2000000, 400000001, 1000000):
            require(time.monotonic() - search_started < 120 and time.monotonic() - started < 600,
                    'Prospective code-store marker deadline')
            original.run(boundary)
            uart = (original.path / 'uart.bin').read_bytes()
            if b'M' in uart:
                require(uart == b'WNFM', 'Guest failed or passed selected modified-state cut')
                break
        else:
            raise TimeoutError('Guest did not reach actual code-store marker')
        report['modified_ns'] = boundary
        fork.run(boundary)
        require((fork.path / 'uart.bin').read_bytes() == b'NFM', 'Warmed fork guest execution differs')
        second = a.work_dir / 'modified.vmstate'
        report['second_capture'] = capture(original, second)
        fork_at_modified = capture(fork, a.work_dir / 'fork-at-modified.vmstate')
        require(semantic(report['second_capture']['cache']) == semantic(fork_at_modified['cache']) and
                report['second_capture']['state'] == fork_at_modified['state'],
                'Actual modified cut diverged after first restore')
        report['second_execution_hits'] = execution_entry(report['second_capture']['cache'], 0x82104000)
        modified = own('fork-modified')
        modified.load(second)
        report['second_restored_state'] = modified.state()
        require(report['second_restored_state'] == report['second_capture']['state'], 'Second restore state differs')
        update()
        finals = []
        for machine in owners:
            require(time.monotonic() - started < 600, 'Prospective whole deadline')
            execution = machine.run(1000000000)
            result = words(machine)
            require(result['stale_exec'] == 111 and result['fenced_exec'] == 222 and
                    result['unfenced_code'] in (111, 222) and result['fenced_code'] == 111,
                    'Actual compiled guest execute/fence result: ' + repr(result))
            finals.append({'name': machine.path.name, 'run': execution, 'words': result,
                           'uart_hex': (machine.path / 'uart.bin').read_bytes().hex(),
                           'capture': capture(machine, a.work_dir / (machine.path.name + '-final.vmstate'))})
        report['finals'] = finals
        expected_words, expected_state = finals[0]['words'], finals[0]['capture']['state']
        for final in finals[1:]:
            require(final['words'] == expected_words and final['capture']['state'] == expected_state and
                    semantic(final['capture']['cache']) == semantic(finals[0]['capture']['cache']),
                    'Guest output or complete declared logical state suffix differs')
        require(time.monotonic() - started < 600, 'Prospective whole deadline')
        original_uart = bytes.fromhex(finals[0]['uart_hex'])
        require(original_uart in (b'WNFMUI', b'WNFMSI') and
                bytes.fromhex(finals[1]['uart_hex']) == original_uart[1:] and
                bytes.fromhex(finals[2]['uart_hex']) == original_uart[4:], 'Actual UART suffix mismatch')
        report['status'] = 'PASS_LOGICAL_EXECUTABLE_TRANSLATION_MODIFICATION_FENCE_SUFFIXES'
        report['scope_limit'] = 'Two finite states only; total QEMU continuation remains GAP_CONFIRMED'
    except BaseException as error:
        report.update(status='FAIL', error=repr(error))
    finally:
        for machine in owners:
            machine.close()
        report['owners_reaped'] = all(machine.process.poll() is not None for machine in owners)
        update()
        print(json.dumps({key: report.get(key) for key in ('status', 'error', 'seconds', 'owners_reaped')}), flush=True)
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
