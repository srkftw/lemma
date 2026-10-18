#!/usr/bin/env python3
"""Execute or admit one source/tool-bound ordinary kernel host prerequisite.

This receipt covers host unittest execution only. It cannot replace Lake builds,
RV64 execution, source negatives, optimization coverage or fresh qualification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import shutil
import subprocess
import sys
import time

from action_cache import is_process_alive, process_identity
from core0_common import Core0Error, sha256, write_json

SCHEMA = 'lemma-kernel-host-prerequisite/1'
CORPUS = ('-m', 'unittest', 'discover', '-s', 'tests/kernel', '-v')
SCOPE = 'ordinary kernel host prerequisite only; no target qualification reused'


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def read_json(path):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise Core0Error('duplicate prerequisite JSON key')
            result[name] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def git_identity():
    candidate = shutil.which('git')
    if candidate is None:
        raise Core0Error('host prerequisite requires immutable Nix Git')
    path = Path(candidate).resolve(strict=True)
    if (not path.is_relative_to('/nix/store') or path.parent.name != 'bin'
            or path.name != 'git' or len(path.parts) < 6):
        raise Core0Error('host prerequisite rejects mutable/non-Nix Git; use pinned nix shell Git')
    environment = {'PATH': str(path.parent), 'LANG': 'C', 'LC_ALL': 'C',
                   'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
    version = subprocess.run([str(path), '--version'], env=environment,
                             check=True, capture_output=True, timeout=15)
    return {'path': str(path), 'sha256': sha256(path),
            'version': version.stdout.decode().strip(), 'store_path': str(path.parent.parent)}


def git_command(root, *args, check=True):
    identity = git_identity()
    # Inventory commands consume only the selected immutable Git and local
    # repository configuration, never global aliases, preload or host PATH.
    environment = {'PATH': str(Path(identity['path']).parent), 'LANG': 'C', 'LC_ALL': 'C',
                   'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
    return subprocess.run([identity['path'], *args], cwd=root, env=environment,
                          capture_output=True, check=check, timeout=30)


def git(root, *args):
    return git_command(root, *args).stdout


def inventory(root):
    """Complete reviewed repository inputs; ignored build/evidence outputs excluded."""
    root = Path(root).resolve()
    names = sorted(set(os.fsdecode(name) for name in
                       git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0') if name))
    if not names or not any(name.startswith('tests/kernel/test_') for name in names):
        raise Core0Error('host prerequisite corpus/source inventory is empty')
    result = {}
    for name in names:
        path = root / name
        if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink():
            raise Core0Error('host prerequisite input escapes or is a symlink: ' + name)
        if not path.exists():
            result[name] = {'deleted': True}
        elif not path.is_file():
            raise Core0Error('host prerequisite input is not a regular file: ' + name)
        else:
            result[name] = {'sha256': sha256(path), 'mode': path.stat().st_mode & 0o777}
    return result


def python_identity(root):
    pin_path = root / 'tooling/toolchain-lock.json'
    pin = read_json(pin_path)['auxiliary_tools']['python']
    executable = Path(sys.executable).resolve()
    if (pin.get('verified') is not True or pin.get('version') != platform.python_version()
            or not executable.is_relative_to(Path(pin['store_path']).resolve())):
        raise Core0Error('host prerequisite requires the pinned Python interpreter')
    return {'invoked_as': sys.executable, 'path': str(executable), 'sha256': sha256(executable),
            'version': sys.version, 'pin': pin, 'pin_file_sha256': sha256(pin_path)}


def environment_identity():
    python = Path(sys.executable).resolve(strict=True)
    if not python.is_relative_to('/nix/store'):
        raise Core0Error('host prerequisite requires immutable Nix Python')
    git = git_identity()
    # Reviewed corpus subprocess tools: canonical Python and Git only. An
    # external helper on inherited PATH is absent and must fail execution.
    paths = sorted({str(python.parent), str(Path(git['path']).parent)})
    return {'PATH': os.pathsep.join(paths), 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
            'TZ': 'UTC', 'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONNOUSERSITE': '1', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}


def count_tests(log):
    data = Path(log).read_text(errors='replace')
    found = re.findall(r'^Ran ([0-9]+) tests? in [^\n]+$', data, re.M)
    passed = list(re.finditer(r'^OK$', data, re.M))
    summary = re.search(r'^Ran [0-9]+ tests? in [^\n]+$', data, re.M)
    # Expected negative fixtures may flush ordinary stdout after the runner's
    # stderr summary. Its unique standalone OK and exit status remain binding.
    if (len(found) != 1 or int(found[0]) <= 0 or len(passed) != 1
            or summary is None or passed[0].start() <= summary.end()
            or re.search(r'\.\.\. skipped\b|\bskipped=|^FAILED\b', data, re.M)):
        raise Core0Error('host corpus is empty, skipped, malformed or failing')
    return int(found[0])


def source_identity(root):
    return {'checkout': str(root), 'commit': git(root, 'rev-parse', 'HEAD').decode().strip(),
            'tree': git(root, 'rev-parse', 'HEAD^{tree}').decode().strip(),
            'inputs': inventory(root)}


def stop_owned(process):
    """Bound teardown to the current child identity; no historical PID signals."""
    if process.poll() is None:
        owner = process_identity(process.pid)
        if is_process_alive(owner):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    process.wait(timeout=10)


def produce(root, output_dir, *, timeout=900):
    root, output_dir = Path(root).resolve(), Path(output_dir).resolve()
    if (not output_dir.is_relative_to(root / 'build') or output_dir == root / 'build'
            or output_dir.exists() or not 0 < timeout <= 900):
        raise Core0Error('host prerequisite needs an unused build subdirectory and timeout at most900s')
    relative = output_dir.relative_to(root).as_posix()
    ignored = git_command(root, 'check-ignore', '--quiet', relative, check=False)
    if ignored.returncode != 0:
        raise Core0Error('prerequisite outputs must be ignored compilation-independent paths')
    before, tool, git_tool, environment = source_identity(root), python_identity(root), git_identity(), environment_identity()
    output_dir.mkdir(parents=True)
    home, temporary = output_dir / 'home', output_dir / 'tmp'
    home.mkdir(); temporary.mkdir()
    actual_environment = {**environment, 'HOME': str(home), 'TMPDIR': str(temporary)}
    log = output_dir / 'kernel-host.log'
    argv = [tool['path'], *CORPUS]
    receipt = {'schema': SCHEMA, 'status': 'FAIL', 'source': before, 'tool': tool, 'git_tool': git_tool,
               'environment': environment, 'execution_environment': actual_environment,
               'host': {'system': platform.system(), 'machine': platform.machine()},
               'recipe_sha256': sha256(Path(__file__)), 'argv': argv, 'cwd': str(root),
               'output_directory': str(output_dir), 'started_at': now(), 'timeout_seconds': timeout,
               'scope': SCOPE}
    started, process = time.monotonic(), None
    try:
        with log.open('xb') as stream:
            process = subprocess.Popen(argv, cwd=root, env=actual_environment,
                                       stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            receipt['owner'] = process_identity(process.pid)
            try:
                receipt['returncode'] = process.wait(timeout=timeout)
            except BaseException:
                stop_owned(process)
                raise
        if receipt['returncode'] != 0:
            raise Core0Error('ordinary kernel host suite failed; see ' + str(log))
        receipt['test_count'] = count_tests(log)
        after = source_identity(root)
        if ({key: after[key] for key in ("checkout", "inputs")} !=
                {key: before[key] for key in ("checkout", "inputs")} or
                python_identity(root) != tool or git_identity() != git_tool or environment_identity() != environment):
            raise Core0Error('prerequisite source/tool/environment changed during execution')
        receipt['status'] = 'PASS'
    except BaseException as error:
        receipt['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        receipt.update(completed_at=now(), elapsed_seconds=time.monotonic() - started,
                       log={'name': log.name, 'sha256': sha256(log)} if log.exists() else None,
                       process_reaped=process is not None and process.poll() is not None)
        receipt['producer_receipt_id'] = hashlib.sha256(encoded(receipt)).hexdigest()
        write_json(output_dir / 'receipt.json', receipt)
    return receipt


def validate(root, receipt_path):
    root, receipt_path = Path(root).resolve(), Path(receipt_path).resolve()
    receipt = read_json(receipt_path)
    required = {'schema', 'status', 'source', 'tool', 'git_tool', 'environment', 'execution_environment',
                'host', 'recipe_sha256', 'argv', 'cwd', 'output_directory', 'started_at',
                'timeout_seconds', 'scope', 'owner', 'returncode', 'test_count', 'completed_at',
                'elapsed_seconds', 'log', 'process_reaped', 'producer_receipt_id'}
    if (not isinstance(receipt, dict) or set(receipt) != required
            or type(receipt.get('test_count')) is not int or receipt['test_count'] <= 0
            or receipt.get('scope') != SCOPE):
        raise Core0Error('host prerequisite receipt is malformed or incompatible')
    identifier = receipt.get('producer_receipt_id')
    payload = {key: value for key, value in receipt.items() if key != 'producer_receipt_id'}
    if (receipt.get('schema') != SCHEMA or receipt.get('status') != 'PASS'
            or receipt.get('returncode') != 0 or receipt.get('process_reaped') is not True
            or not isinstance(identifier, str) or hashlib.sha256(encoded(payload)).hexdigest() != identifier
            or receipt.get('argv') != [str(Path(sys.executable).resolve()), *CORPUS] or receipt.get('cwd') != str(root)
            or receipt.get('recipe_sha256') != sha256(Path(__file__))):
        raise Core0Error('host prerequisite is malformed, failed or incompatible')
    current_source = source_identity(root)
    recorded_source = receipt.get('source', {})
    # The reviewed host corpus uses Git only in isolated fixtures. HEAD/tree
    # identify its original producer; exact files and checkout are test inputs.
    if ({key: recorded_source.get(key) for key in ('checkout', 'inputs')} !=
            {key: current_source[key] for key in ('checkout', 'inputs')} or receipt.get('tool') != python_identity(root) or receipt.get('git_tool') != git_identity()
            or receipt.get('environment') != environment_identity()
            or receipt.get('host') != {'system': platform.system(), 'machine': platform.machine()}):
        raise Core0Error('host prerequisite source/tool/checkout/environment differs')
    original = Path(receipt['output_directory'])
    if not original.is_relative_to(root / 'build'):
        raise Core0Error('host prerequisite original private output escapes build')
    expected_environment = {**environment_identity(), 'HOME': str(original / 'home'), 'TMPDIR': str(original / 'tmp')}
    if receipt.get('execution_environment') != expected_environment:
        raise Core0Error('host prerequisite original environment was uncontrolled')
    log_info = receipt.get('log')
    if not isinstance(log_info, dict) or log_info.get('name') != 'kernel-host.log':
        raise Core0Error('host prerequisite log identity is missing')
    log = receipt_path.parent / 'kernel-host.log'
    if log.is_symlink() or sha256(log) != log_info.get('sha256') or count_tests(log) != receipt.get('test_count'):
        raise Core0Error('host prerequisite actual nonempty test log changed')
    return {'execution': 'validated-reuse', 'route': SCHEMA,
            'producer_receipt_id': identifier, 'receipt': str(receipt_path), 'receipt_sha256': sha256(receipt_path),
            'original_argv': receipt['argv'], 'original_cwd': receipt['cwd'],
            'original_started_at': receipt['started_at'], 'original_completed_at': receipt['completed_at'],
            'original_source_commit': recorded_source['commit'], 'original_source_tree': recorded_source['tree'],
            'test_count': receipt['test_count'], 'original_log': str(log), 'original_log_sha256': sha256(log),
            'validator_sha256': sha256(Path(__file__)), 'scope': receipt['scope']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('mode', choices=('produce', 'validate'))
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--timeout', type=float, default=900)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'produce':
            if args.output_dir is None: parser.error('produce requires --output-dir')
            output = args.output_dir if args.output_dir.is_absolute() else args.root / args.output_dir
            result = produce(args.root, output, timeout=args.timeout)
            print(json.dumps({'status': result['status'], 'test_count': result['test_count'],
                              'receipt': str(output / 'receipt.json'), 'producer_receipt_id': result['producer_receipt_id']}))
        else:
            if args.receipt is None: parser.error('validate requires --receipt')
            result = validate(args.root, args.receipt)
            print(json.dumps(result, sort_keys=True))
    except (Core0Error, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('HOST PREREQUISITE FAIL: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
