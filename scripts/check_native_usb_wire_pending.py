#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual audited Wire initializer, two generated PHYs and private Pending suffixes.

This links the original source-bound Machine objects. It observes guest-issued
transactions and generated phases; it never initializes controller state.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from check_native_power import ROOT, sha, run
from check_guest_usb_notebook import copy_opaque_peer
from lemmasim_usb_pending import validate as validate_host
from lemmasim_companion import validate as validate_companion
from silicon_guest import native_source_archive
from silicon_guest_bundle import prepared
from supervise_usb_notebook import alive, descendants


PROFILE = 'lemma-silicon-dev/0.11.0'
WORKLOAD = 'usb-wire-bulk-initializer'
CASES = {'startup', 'reset', 'physical-send', 'physical-receive',
         'physical-chip-send', 'physical-guard', 'owned-receive',
         'owned-submit', 'domain-reset'}


def run_fixture(arguments, log, seconds, maximum_rss_kib=4194304):
    """Bound and reap the fixture's separately grouped raw-I/O children."""
    known = {}
    supervision = {'status': 'FAIL', 'host_seconds_bound': seconds,
                   'maximum_tree_rss_kib': maximum_rss_kib,
                   'peak_tree_rss_kib': 0, 'automatic_restart': False}
    started = time.monotonic()
    with log.open('xb') as stream:
        child = subprocess.Popen(list(map(str, arguments)), cwd=ROOT,
            stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + seconds
        supervision.update(pid=child.pid, absolute_monotonic_deadline=deadline)
        try:
            while child.poll() is None:
                current = descendants(child.pid)
                for item in current:
                    known[(item['pid'], item['start_ticks'])] = item
                rss = 0
                for item in current:
                    if alive(item):
                        try:
                            status = (Path('/proc') / str(item['pid']) / 'status').read_text()
                            match = re.search(r'^VmRSS:\s*(\d+) kB$', status, re.M)
                            if match:
                                rss += int(match.group(1))
                        except (FileNotFoundError, ProcessLookupError):
                            pass
                supervision['peak_tree_rss_kib'] = max(supervision['peak_tree_rss_kib'], rss)
                if rss > maximum_rss_kib:
                    raise RuntimeError('predeclared native Wire fixture memory bound exceeded')
                if time.monotonic() >= deadline:
                    raise TimeoutError('predeclared native Wire fixture deadline')
                time.sleep(.05)
            child.wait(timeout=10)
            if child.returncode:
                raise subprocess.CalledProcessError(child.returncode, arguments)
            supervision['status'] = 'PASS'
        except BaseException as error:
            supervision['error'] = repr(error)
            raise
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
            # A raw adapter deliberately owns its process group. Kill only
            # captured start-time identities, then reap adopted descendants.
            for item in known.values():
                if alive(item):
                    try:
                        os.kill(item['pid'], signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            until = time.monotonic() + 5
            while time.monotonic() < until:
                for item in known.values():
                    try:
                        os.waitpid(item['pid'], os.WNOHANG)
                    except ChildProcessError:
                        pass
                if not any(alive(item) for item in known.values()):
                    break
                time.sleep(.01)
            for item in known.values():
                if alive(item):
                    try:
                        os.kill(item['pid'], signal.SIGKILL)
                        os.waitpid(item['pid'], 0)
                    except (ProcessLookupError, ChildProcessError):
                        pass
            survivors = [item for item in known.values() if alive(item)]
            supervision.update(returncode=child.returncode,
                host_seconds=time.monotonic() - started,
                owned_children=list(known.values()), owned_survivors=survivors)
            if survivors:
                supervision.update(status='FAIL', cleanup_error='owned child survived cleanup')
            log.with_suffix('.supervision.json').write_text(json.dumps(supervision, indent=2) + '\n')
            if survivors:
                raise RuntimeError('owned native Wire fixture child survived cleanup')
    return list(known.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('rtl-build', 'rtl-source-root', 'native-bundle', 'host-prepared',
                 'formatted-peer', 'formatted-outbox', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--profile', choices=(PROFILE, 'lemma-silicon-dev/0.13.0'), default=PROFILE)
    parser.add_argument('--workload', choices=('usb-clocked-package-entry2-bulk-initializer',),
                        help='explicit current EntryV2 initializer; Clocked13 only')
    args = parser.parse_args()
    selected_profile = args.profile
    workload = 'usb-clocked-bulk-initializer' if selected_profile == 'lemma-silicon-dev/0.13.0' else WORKLOAD
    if args.workload:
        if selected_profile != 'lemma-silicon-dev/0.13.0':
            parser.error('EntryV2 initializer requires Clocked13')
        workload = args.workload
    out = args.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'build'):
        parser.error('unused owned output under build required')
    out.mkdir(parents=True)
    started = time.monotonic()
    peer = peer_log = None
    result = {'schema': 'lemma-usb-wire-pending-evidence/1', 'status': 'FAIL',
        'scope': 'Actual audited RV64 Wire initializer and two independent generated PHYs; observational startup, reset, symbol, EOP guard, owned receive/submit cuts and private exact captured suffixes. No privately live peer continuation, standards-MAC timing, cross-backend or QEMU cache claim.',
        'bounds': {'target_cycles': 70000000, 'fixture_host_seconds': 1800,
                   'external_host_response_timeout_ms': 60000,
                   'maximum_fixture_tree_rss_kib': 4194304,
                   'maximum_owned_apparent_bytes': 12000000000},
        'profile': selected_profile,
        'workload': workload,
        'fixed_phy_clocks': ({'host_ppm':2500,'chip_ppm':-2500,'host_phase':7,'chip_phase':38}
                             if selected_profile == 'lemma-silicon-dev/0.13.0' else None),
        'external_process_policy': 'restored forks have no USB process; strict implementation-bound checksum/prefix/horizon tape only'}
    try:
        # Linux host-only harness: orphaned grandchildren become ours to reap.
        # This changes no machine/controller state and affects no other agent.
        if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0):
            raise OSError(ctypes.get_errno(), 'host fixture subreaper setup')
        machine, _, native_archive = native_source_archive(
            args.rtl_build, args.rtl_source_root, selected_profile)
        guest = prepared(args.native_bundle, 'rtl', workload, selected_profile)
        entry = guest['workloads'][workload]
        if guest['binary']['sha256'] != machine['binary_sha256']:
            raise ValueError('Guest bundle and original native binary differ')
        host = validate_host(args.host_prepared)
        legacy = json.loads(Path(host['legacy_prepared']['path']).read_text())
        companion = Path(legacy['companion_prepared']['path'])
        validate_companion(companion)
        writer = copy_opaque_peer(args.formatted_peer.resolve(), out / 'peer',
                                  args.formatted_outbox.resolve(), out / 'outbox')
        if writer != 83:
            raise ValueError('Fixture writer namespace differs')
        socket = out / 'peer.sock'
        peer_argv = [os.sys.executable, str(ROOT / 'scripts/lemmasim'),
                    'companion', 'serve', '--prepared', str(companion),
                    '--directory', str(out / 'peer'), '--socket', str(socket)]
        peer_log = (out / 'peer.log').open('xb')
        peer = subprocess.Popen(peer_argv, cwd=ROOT, stdout=peer_log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + 15
        while not socket.exists():
            if peer.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('Independent hosted Lean peer did not start')
            time.sleep(.01)
        version = subprocess.check_output(['verilator', '-V'], text=True, timeout=10)
        roots = set(re.findall(r'^\s*VERILATOR_ROOT\s*=\s*(\S+)\s*$', version, re.M))
        if len(roots) != 1:
            raise ValueError('Ambiguous Verilator root')
        prefix = Path(roots.pop())
        obj = args.rtl_build.resolve() / 'obj'
        names = ['machine_runtime.o', 'backing_io.o', 'backing_io_posix.o',
                 'backing_peer.o', 'ble_peer_transport.o', 'usb_transport.o',
                 'verilated.o', 'verilated_save.o', 'verilated_threads.o',
                 'verilated_dpi.o', 'Vlemma_soc__ALL.a']
        source = ROOT / 'tests/lemmasim/native_usb_wire_pending.cpp'
        inputs = {str(obj / name): sha(obj / name) for name in names}
        inputs[str(source)] = sha(source)
        binary = out / 'test'
        run(['c++', '-O2', '-std=c++17', '-Wall', '-Wextra', '-Werror',
             '-DUSB_CLOCKED_TEST='+str(int(selected_profile == 'lemma-silicon-dev/0.13.0')),
             '-I', args.rtl_source_root.resolve() / 'sim/rtl/host', '-I', obj,
             '-isystem', prefix / 'include', '-isystem', prefix / 'include/vltstd',
             source, *[obj / name for name in names], '-pthread', '-o', binary],
            out / 'compile.log', 60)
        arguments = [binary, out, entry['image']['path'], guest['rom']['path'],
                     entry['dtb']['path'], entry['descriptor']['path'],
                     host['binary']['path'], socket, out / 'outbox',
                     ROOT / 'sim/companion/os_io.py']
        result.update(native_archive=native_archive, guest_bundle=guest['native_bundle'],
            identity={'native': machine['binary_sha256'],
                      'implementation': machine['snapshot_identity'],
                      'guest': entry['image']['sha256'], 'rom': guest['rom']['sha256'],
                      'dtb': entry['dtb']['sha256'], 'descriptor': entry['descriptor']['sha256']},
            host_prepared={'path': str(args.host_prepared.resolve()),
                           'sha256': sha(args.host_prepared)},
            fixture_sha256=sha(source), test_binary_sha256=sha(binary),
            compiled_inputs=inputs, peer_argv=peer_argv,
            fixture_argv=[str(value) for value in arguments])
        result['owned_fixture_children'] = run_fixture(arguments, out / 'run.log', 1800)
        log = (out / 'run.log').read_text()
        if not log.endswith('PASS real RV64 USB Wire startup/reset/physical-symbol/guard and owned receive/submit Pending snapshots; private exact captured native suffixes\n'):
            raise ValueError('Missing actual native property result')
        rows = [json.loads(line) for line in log.splitlines() if line.startswith('{')]
        if len(rows) != len(CASES) or {row['case'] for row in rows} != CASES:
            raise ValueError('Required actual boundary missing or duplicated')
        for label in CASES:
            for left, right in ((label + '.snap', label + '-restored.snap'),
                                (label + '-final.snap', label + '-replay.snap')):
                if sha(out / left) != sha(out / right):
                    raise ValueError('Authoritative native suffix differs: ' + label)
        for path, digest in inputs.items():
            if sha(path) != digest:
                raise ValueError('Compiled property input changed: ' + path)
        native_source_archive(args.rtl_build, args.rtl_source_root, selected_profile)
        prepared(args.native_bundle, 'rtl', workload, selected_profile)
        result.update(status='PASS', cases=rows,
            files={path.name: {'bytes': path.stat().st_size, 'sha256': sha(path)}
                   for path in sorted(out.iterdir())
                   if path.suffix in ('.snap', '.tape', '.log', '.raw', '.uart')})
    except BaseException as error:
        result['error'] = repr(error)
    finally:
        if peer is not None and peer.poll() is None:
            os.killpg(peer.pid, signal.SIGTERM)
            try:
                peer.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(peer.pid, signal.SIGKILL)
                peer.wait(timeout=5)
        if peer_log is not None:
            peer_log.close()
        result['host_seconds'] = time.monotonic() - started
        files = [path.stat() for path in out.rglob('*')
                 if path.is_file() and not path.is_symlink()]
        result['owned_disk'] = {'apparent_bytes': sum(path.st_size for path in files),
                                'allocated_bytes': sum(path.st_blocks * 512 for path in files)}
        if result['owned_disk']['apparent_bytes'] > result['bounds']['maximum_owned_apparent_bytes']:
            result.update(status='FAIL', error='Owned property output exceeded declared storage bound')
        result['observer_sha256'] = sha(__file__)
        supervision = out / 'run.supervision.json'
        if supervision.exists():
            result['fixture_supervision'] = {'path': str(supervision), 'sha256': sha(supervision)}
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
