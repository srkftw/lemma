#!/usr/bin/env python3
"""Laboratory POSIX file-size fault for a paused, private canonical fork.

This changes the owned native host process's soft RLIMIT_FSIZE. Actual pwrite
outcomes still pass through BackingPlatform capture; no guest result is forced.
The external fault is not a portable machine checkpoint field. Replay uses
recorded outcomes, and live forks need an explicitly supplied environment.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import sys

from lemmasim_session import request
from supervise_usb_notebook import descendants, identity

# Launcher wrapper -> actual executable. Both belong to the same pinned Nix
# derivation. Matching a process name or only the wrapper is insufficient.
QUALIFIED_QEMU = {
    '97ab475eda8da56508c99601c4331cc2b802a7f4f52ac8aace720964a8aaddf7': frozenset({
        '298840d9388c59ba93050f0fa9d4be905619b2d1cc5e14bc044ad6a2a7731090',
    }),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def qemu_private_medium(session, native):
    """Read the current owned VM's actual arguments and writable backing FD.

    The live owner's initial argv can predate a QEMU restore, which replaces
    the VM process. Only its actual privately copied migration medium is
    admitted. This does not qualify cached-state continuation.
    """
    proc = Path('/proc', str(native['pid']))
    argv = (proc / 'cmdline').read_bytes().decode().split('\0')
    require(not any(arg.startswith(('lemma-fast-block.backing-replay=',
                                   'lemma-fast-block.companion-')) for arg in argv),
            'certain live local backing without outcome replay required')
    values = [argv[i + 1].removeprefix('lemma-fast-block.medium=')
              for i in range(len(argv) - 1) if argv[i] == '-global' and
              argv[i + 1].startswith('lemma-fast-block.medium=')]
    require(len(values) == 1, 'one actual QEMU local medium required')
    medium = Path(values[0])
    require(not medium.is_symlink(), 'private backing path must not be a symlink')
    medium = medium.resolve()
    require(medium.parent.parent == session and
            re.fullmatch(r'machine-fork-[1-9][0-9]*-[0-9]+', medium.parent.name) and
            medium.name == 'durable.raw', 'owned QEMU migration fork required')
    stat = medium.stat()
    require(medium.is_file() and stat.st_uid == os.getuid() and stat.st_nlink == 1,
            'own regular private backing without hard links required')
    writable = False
    for fd in (proc / 'fd').iterdir():
        try:
            actual = fd.stat()
            flags = re.search(r'(?m)^flags:\s+([0-7]+)$',
                              (proc / 'fdinfo' / fd.name).read_text())
            if ((actual.st_dev, actual.st_ino) == (stat.st_dev, stat.st_ino) and
                    flags is not None and int(flags[1], 8) & os.O_ACCMODE == os.O_RDWR):
                writable = True
        except FileNotFoundError:
            continue
    require(writable and identity(native['pid']) == native,
            'actual owned QEMU writable medium differs')
    return medium


def owned_native(session, *, restoring=False):
    require(sys.platform == 'linux' and hasattr(resource, 'prlimit'), 'Linux prlimit required')
    session = Path(session).resolve()
    manifest_path = session / 'session.json'
    require(not manifest_path.is_symlink() and manifest_path.stat().st_uid == os.getuid(),
            'own session metadata required')
    manifest = json.loads(manifest_path.read_text())
    backend = manifest['backend']
    require(manifest['mode'] == 'laboratory' and backend in ('rtl', 'qemu'),
            'native Laboratory session required')
    observed = request(session, {'action': 'inspect'}, 120)
    state = observed['machine']
    require(observed['identity']['profile'] == 'lemma-silicon-dev/0.3.0' and
            not observed['running'], 'paused private canonical fork required')
    # Clearing a fault must remain possible after a capture error. Replaying a
    # tape bypasses live POSIX I/O, so admitting a new file fault there would
    # misleadingly claim an environment effect that cannot reach the device.
    if not restoring:
        require(not observed.get('capture_uncertain') and
                not observed.get('external_adapters') and
                '--backing-replay' not in manifest['argv'],
                'certain live backing without external adapters or outcome replay required')
    if backend == 'rtl':
        require(state['isolated_medium'], 'paused private canonical fork required')
        medium = Path(state['private_medium_path'])
        require(not medium.is_symlink(), 'private backing path must not be a symlink')
        medium = medium.resolve()
        require(medium.is_relative_to(session) and medium.is_file(),
                'own private backing required')
    else:
        require(observed['identity']['runtime'] in QUALIFIED_QEMU and
                state['storage']['backend'] == 'lemma-fast-block/3',
                'fast file-limit capture implementation is not qualified')
        if not restoring:
            require(state['storage']['backing_poisoned'] == 0,
                    'certain live backing without capture poison required')
    expected = Path(manifest['argv'][0]).resolve()
    matches = []
    for child in descendants(manifest['pid']):
        path = Path('/proc', str(child['pid']))
        try:
            executable = (path / 'exe').resolve(strict=True)
        except FileNotFoundError:
            continue
        if path.stat().st_uid == os.getuid():
            if backend == 'rtl' and executable == expected:
                matches.append(child)
            elif backend == 'qemu' and hashlib.sha256(executable.read_bytes()).hexdigest() in \
                    QUALIFIED_QEMU[observed['identity']['runtime']]:
                matches.append(child)
    require(len(matches) == 1, 'one owned native process required')
    native = matches[0]
    require(hashlib.sha256(expected.read_bytes()).hexdigest() == observed['identity']['runtime'],
            'actual native executable differs from live identity')
    # The immutable runtime used for this operation must be the version with
    # per-thread SIGXFSZ capture. Other runtimes are not silently admitted.
    if backend == 'qemu':
        qemu_private_medium(session, native)
    else:
        require(state['snapshot_identity'] ==
            '600e93eb1981b3eb5432840c0fd8e169b4d5cfd04f89e8164450d1c70b159bba',
            'file-limit capture implementation is not qualified')
    return session, native, observed


def apply(session, limit, token_path):
    require(type(limit) is int and 0 <= limit <= 1 << 30, 'bounded byte limit required')
    token_path = Path(token_path).absolute()
    require(not token_path.exists() and not token_path.is_symlink() and
            not any(p.is_symlink() for p in token_path.parents), 'unused regular token path required')
    session, native, before = owned_native(session)
    previous = resource.prlimit(native['pid'], resource.RLIMIT_FSIZE)
    require(previous[1] == resource.RLIM_INFINITY or limit <= previous[1], 'hard limit cannot be raised')
    token = {'schema': 'lemma-native-file-limit/1', 'session': str(session),
             'native': native, 'previous': list(previous), 'applied_soft': limit,
             'cycle': before['machine']['cycle'], 'state': 'pending',
             'scope': 'External host resource fault; actual outcomes are captured by the machine'}
    token_path.parent.mkdir(parents=True, exist_ok=True)
    # Persist the reversible intent before the syscall. A pending token can
    # safely reconcile either old or applied limits after an interrupted client.
    with token_path.open('x') as out:
        out.write(json.dumps(token, indent=2) + '\n'); out.flush(); os.fsync(out.fileno())
    directory = os.open(token_path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    try:
        require(identity(native['pid']) == native, 'native process changed')
        resource.prlimit(native['pid'], resource.RLIMIT_FSIZE, (limit, previous[1]))
        after = request(session, {'action': 'inspect'}, 120)
        require(after['machine'] == before['machine'] and not after['running'],
                'fault admission requires exclusive paused control')
        token['state'] = 'applied'
    except BaseException:
        if identity(native['pid']) == native and resource.prlimit(native['pid'], resource.RLIMIT_FSIZE) == (limit, previous[1]):
            resource.prlimit(native['pid'], resource.RLIMIT_FSIZE, previous)
        raise
    return token


def restore(token):
    require(token.get('schema') == 'lemma-native-file-limit/1', 'unsupported fault token')
    _, native, before = owned_native(token['session'], restoring=True)
    require(native == token['native'], 'fault token belongs to another process')
    previous = tuple(token['previous'])
    current = resource.prlimit(native['pid'], resource.RLIMIT_FSIZE)
    require(current in (previous, (token['applied_soft'], previous[1])), 'another resource policy superseded this fault')
    if current != previous:
        resource.prlimit(native['pid'], resource.RLIMIT_FSIZE, previous)
    after = request(token['session'], {'action': 'inspect'}, 120)
    require(after['machine'] == before['machine'] and not after['running'], 'restore requires exclusive paused control')
    return {'restored': True, 'cycle': after['machine']['cycle'], 'native': native}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    a = sub.add_parser('apply'); a.add_argument('--session-dir', type=Path, required=True)
    a.add_argument('--bytes', type=int, required=True); a.add_argument('--token', type=Path, required=True)
    a = sub.add_parser('restore'); a.add_argument('--token', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = (apply(args.session_dir, args.bytes, args.token) if args.action == 'apply'
                  else restore(json.loads(args.token.read_text())))
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    main()
