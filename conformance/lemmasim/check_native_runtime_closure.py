#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Observe actual native launch with only the declared Nix runtime visible.

Linux user/mount namespaces are mandatory. This neither imports the NAR nor
changes the parent store/settings. It tests registered runtime visibility,
not clean-host installation, Python/Tk packaging, licensing or cold recovery.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            result.update(chunk)
    return result.hexdigest()


def child(specification):
    spec = json.loads(Path(specification).read_text())
    directory = Path(spec['directory'])
    alias = directory / 'original-store'
    alias.mkdir()
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mount.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                           ctypes.c_ulong, ctypes.c_char_p]
    libc.umount2.argtypes = [ctypes.c_char_p, ctypes.c_int]

    def mount(source, target, kind, flags, options=None):
        values = [str(value).encode() if value is not None else None
                  for value in (source, target, kind)]
        if libc.mount(*values, flags, options) != 0:
            raise OSError(ctypes.get_errno(), 'private namespace mount failed')

    # All imports and shared objects required by this observer are loaded
    # before hiding the store. The subprocesses see only the listed paths.
    json.dumps({'warm_encoder': True})
    original_flags = os.statvfs('/nix/store').f_flag
    require(original_flags & os.ST_RDONLY, 'original store must be read-only')
    mount('/nix/store', alias, None, 4096)  # MS_BIND
    mount('tmpfs', '/nix/store', 'tmpfs', 6, b'size=2097152,mode=0755')
    for name in spec['paths']:
        target = Path(name)
        require(target.parent == Path('/nix/store'), 'non-store visibility path')
        target.mkdir()
        mount(alias / target.name, target, None, 4096)
        # Bind inherits the original read-only mount and its locked protection
        # flags. Verify them; do not attempt to relax/remount those flags in a
        # user namespace (an earlier driver failed EPERM at that remount).
        protected = os.ST_RDONLY | os.ST_NOSUID | os.ST_NODEV | os.ST_NOEXEC
        require(os.statvfs(target).f_flag & protected == original_flags & protected,
                'runtime bind lost original mount protections')
    require(libc.umount2(str(alias).encode(), 0) == 0, 'store alias unmount failed')
    alias.rmdir()
    observed = []
    for command in spec['commands']:
        begun = time.monotonic()
        try:
            result = subprocess.run(command['argv'], input=command.get('stdin', '').encode(),
                                    capture_output=True, timeout=45,
                                    env={'PATH': '/nonexistent', 'HOME': str(directory),
                                         'LC_ALL': 'C'})
            row = {'returncode': result.returncode,
                   'stdout': result.stdout.decode(errors='replace'),
                   'stderr': result.stderr.decode(errors='replace')}
        except OSError as error:
            row = {'launch_errno': error.errno, 'error': str(error)}
        require(len(json.dumps(row)) < 65536, 'runtime probe output bound')
        row.update(name=command['name'], seconds=time.monotonic() - begun)
        observed.append(row)
    print(json.dumps({'paths_visible': len(spec['paths']), 'observations': observed}))


def check(bundle, export_result, output):
    require(not output.exists(), 'unused output directory required')
    output.mkdir(parents=True)
    started = time.monotonic()
    report = {'schema': 'lemma-native-runtime-visibility/1', 'status': 'FAIL',
              'scope': __doc__, 'producer_sha256': sha(__file__)}
    try:
        manifest = json.loads((bundle / 'bundle.json').read_text())
        receipt = json.loads(export_result.read_text())
        if receipt.get('schema') == 'lemma-local-native-distribution/2':
            exported = receipt['host_runtime_archive']
        else:
            require(receipt.get('status') == 'PASS_ACTUAL_COMPLETE_REGISTERED_NATIVE_RUNTIME_EXPORT',
                    'unsupported runtime export receipt')
            exported = receipt
        require(manifest.get('profile') == 'lemma-silicon-dev/0.3.0', 'canonical profile required')
        nar = export_result.parent / exported['path']
        require(sha(nar) == exported['sha256'], 'actual exported NAR differs')
        qemu = manifest['backends']['qemu']['qemu']
        rtl = manifest['backends']['rtl']['binary']
        for item in (qemu, rtl):
            require(sha(bundle / item['path']) == item['sha256'], 'actual backend differs')
        notebook = manifest['backends']['rtl']['workloads']['notebook']
        guest, rom = bundle / notebook['image']['path'], bundle / manifest['backends']['rtl']['rom']['path']
        dtb = bundle / notebook['dtb']['path']
        descriptor = bundle / notebook['descriptor']['path']
        require(sha(guest) == notebook['image']['sha256'] and
                sha(rom) == manifest['backends']['rtl']['rom']['sha256'], 'guest/reset ROM differs')
        require(sha(dtb) == notebook['dtb']['sha256'] and
                sha(descriptor) == notebook['descriptor']['sha256'], 'device description differs')
        old_paths = sorted({str(Path(*Path(path).parts[:4]))
                            for group in manifest['host_dependencies'].values() for path in group})
        commands = [{'name': 'qemu-wrapper-actual-version',
                     'argv': [str(bundle / qemu['path']), '--version']}]
        results = {}
        for name, paths in [('original-wrapper-only', old_paths),
                            ('complete-runtime', exported['complete_requisites'])]:
            directory = output / name
            directory.mkdir()
            selected = list(commands)
            if name == 'complete-runtime':
                selected.append({'name': 'actual-RTL-guest-million-clocks',
                                 'argv': [str(bundle / rtl['path']), '--image', str(guest),
                                          '--rom', str(rom), '--load', '0x87e00000:' + str(dtb),
                                          '--descriptor', str(descriptor),
                                          '--uart-output', str(directory / 'actual-uart.bin'),
                                          '--session', '--quiet-uart',
                                          '--host-threads', '0'],
                                 'stdin': 'run 1000000\ninspect\ndestroy\n'})
            spec = directory / 'specification.json'
            spec.write_text(json.dumps({'directory': str(directory), 'paths': paths,
                                        'commands': selected}, indent=2) + '\n')
            process = subprocess.Popen(['unshare', '--user', '--map-root-user', '--mount',
                                        '--propagation', 'private', '--fork', sys.executable,
                                        str(Path(__file__).resolve()), '_child', str(spec)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True)
            try:
                stdout, stderr = process.communicate(timeout=90)
            except BaseException:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate(timeout=10)
                raise
            (directory / 'stdout.log').write_bytes(stdout)
            (directory / 'stderr.log').write_bytes(stderr)
            require(process.returncode == 0, 'namespace probe failed: ' + name)
            results[name] = json.loads(stdout)
        old = results['original-wrapper-only']['observations'][0]
        require(old.get('returncode', -1) != 0, 'original missing runtime was not exposed')
        current = results['complete-runtime']['observations']
        require(current[0].get('returncode') == 0 and 'QEMU emulator version' in current[0]['stdout'],
                'complete QEMU output closure does not launch')
        require(current[1].get('returncode') == 0, 'actual RTL guest failed in declared closure')
        rows = [json.loads(line) for line in current[1]['stdout'].splitlines()]
        require(rows and all(row.get('ok') is True for row in rows) and
                all(row['result']['cycle'] == 1000000 and row['result']['retired'] > 0 and
                    row['result']['finished'] is False for row in rows),
                'actual isolated-visibility guest did not execute exact million clocks')
        require(time.monotonic() - started < 180, 'prospective whole observer180s bound')
        report.update(status='PASS_ACTUAL_RUNTIME_VISIBILITY_OLD_CLOSURE_REJECTED',
                      observations=results, runtime_archive_sha256=sha(nar),
                      bundle_manifest_sha256=sha(bundle / 'bundle.json'),
                      guest_sha256=sha(guest), exact_RTL_clocks=1000000,
                      limitation='Namespace visibility uses the existing listed store contents; no NAR import, fresh host, notebook Ready or cold-recovery claim.')
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        report['seconds'] = time.monotonic() - started
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    if sys.argv[1:2] == ['_child']:
        child(sys.argv[2])
    else:
        parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
        parser.add_argument('--bundle', type=Path, required=True)
        parser.add_argument('--export-result', type=Path, required=True)
        parser.add_argument('--output-dir', type=Path, required=True)
        args = parser.parse_args()
        result = check(args.bundle.resolve(), args.export_result.resolve(), args.output_dir.resolve())
        print(result['status'], result['seconds'])
