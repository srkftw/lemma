#!/usr/bin/env python3
"""Relocatable local public-development ROM machine and its host launcher.

No user media or running kernel image is included. Exact Nix-store compiler
audit tools/runtime libraries and host Python remain external requirements.
This is local preparation, not a redistribution licence or clean-host result.
"""
from contextlib import contextmanager
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
SCHEMA = 'lemma-local-auth-machine-bundle/1'
PREPARED_FILES = ('discovery.dts', 'discovery.dtb', 'descriptor.bin', 'DEPENDENCIES.txt')
COMMANDS = ('launch', 'create-medium', 'capacity', 'key-info', 'install',
            'install-resume', 'tag', 'publish', 'status', 'boot')


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            result.update(block)
    return result.hexdigest()


def member(root, name):
    if not isinstance(name, str):
        raise ValueError('invalid bundle member')
    relative = Path(name)
    if not relative.parts or relative.is_absolute() or '..' in relative.parts:
        raise ValueError('invalid bundle member')
    path = root / relative
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('missing or symlinked bundle member: ' + name)
    return path


def verify(root):
    root = Path(root).absolute()
    index = member(root, 'bundle.json')
    if index.stat().st_size > 4 << 20:
        raise ValueError('bundle inventory exceeds4MiB')
    manifest = json.loads(index.read_text())
    files = manifest.get('files')
    if (manifest.get('schema') != SCHEMA or manifest.get('user_media_included') is not False or
            not isinstance(files, dict) or not 1 <= len(files) <= 8192 or
            'run.py' not in files or 'components/prepared.json' not in files):
        raise ValueError('unsupported or incomplete bundle inventory')
    total = 0
    for name, digest in files.items():
        path = member(root, name)
        size = path.stat().st_size
        if (size > 64 << 20 or not isinstance(digest, str) or len(digest) != 64 or
                any(c not in '0123456789abcdef' for c in digest) or sha(path) != digest):
            raise ValueError('changed or oversized bundle member: ' + name)
        total += size
        if total > 256 << 20:
            raise ValueError('bundle exceeds256MiB')
    for name in PREPARED_FILES:
        if 'components/' + name not in files:
            raise ValueError('missing prepared descriptor or notices')
    actual = {str(path.relative_to(root)) for path in root.rglob('*') if path.is_file() or path.is_symlink()}
    if actual != set(files) | {'bundle.json'}:
        raise ValueError('unindexed or missing bundle files')
    return manifest


@contextmanager
def relocated(root):
    """Only four locations change; immutable component/protocol data stays exact.

    A private temporary preparation owns descriptor copies, never media. Its
    lifetime encloses the existing synchronous session server. The immutable
    bundle and its original manifest are not edited when it moves or launches.
    """
    root = Path(root).absolute()
    verify(root)
    original = json.loads((root / 'components/prepared.json').read_text())
    data = dict(original)
    for role in ('native', 'rom'):
        data[role + '_build'] = str(root / 'components' / role)
        data[role + '_source_archive'] = str(root / 'components' / (role + '-source/consumed-source-root'))
    with tempfile.TemporaryDirectory(prefix='lemma-auth-prepared-') as private:
        private = Path(private)
        (private / 'prepared.json').write_text(json.dumps(data, indent=2) + '\n')
        for name in PREPARED_FILES:
            shutil.copyfile(root / 'components' / name, private / name)
        yield private


def create(source, output):
    import lemmasim_auth as auth
    import product_archive
    root = Path(__file__).resolve().parents[1]
    output = Path(output).absolute()
    if output.exists() or output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError('unused regular bundle output required')
    # Validate the exact existing ROM/native/source tuple before copying.
    data, _, _ = auth.prepared(source)
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root, timeout=30).decode().split('\0')
    selected = {name: sha(member(root, name)) for name in filter(None, names)}
    sizes = [(root / name).stat().st_size for name in selected]
    if not 1 <= len(sizes) <= 4096 or max(sizes) > 64 << 20 or sum(sizes) > 64 << 20:
        raise ValueError('host source archive exceeds4096files/64MiB')
    if selected.get('scripts/product_bundle.py') != sha(Path(__file__)):
        raise ValueError('bundle launcher must be tracked before preparation')
    product_archive.create(source, output / 'components', auth.prepared)
    for name, digest in selected.items():
        destination = output / 'host' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, destination)
        if sha(destination) != digest:
            raise ValueError('source changed during bundle copy: ' + name)
    shutil.copyfile(Path(__file__), output / 'run.py')
    (output / 'run.py').chmod(0o755)
    files = {str(path.relative_to(output)): sha(path) for path in output.rglob('*') if path.is_file()}
    manifest = {'schema': SCHEMA, 'files': files, 'profile': data['profile'],
                'runtime_identity': data['runtime_identity'], 'rom_sha256': data['rom_sha256'],
                'source_prepared_sha256': sha(Path(source) / 'prepared.json'),
                'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, timeout=30).decode().strip(),
                'source_status': subprocess.check_output(['git', 'status', '--porcelain=v1'], cwd=root, timeout=30).decode(),
                'user_media_included': False, 'scope': __doc__,
                'external_requirements': 'Python3; exact inventoried Nix-store audit tools and native runtime libraries. No Nix export/install or clean-host claim.'}
    (output / 'bundle.json').write_text(json.dumps(manifest, indent=2) + '\n')
    verify(output)
    # A fresh interpreter ensures imported validators resolve only in the
    # packaged source root, rather than reusing this builder's module cache.
    subprocess.run([sys.executable, '-I', str(output / 'run.py'), '--verify-only'],
                   check=True, timeout=120, cwd=output)
    if any(sha(root / name) != digest for name, digest in selected.items()):
        raise ValueError('original host source changed during bundle preparation')
    return {'status': 'PASS_LOCAL_RELOCATABLE_AUTH_MACHINE_BUNDLE', 'files': len(files),
            'bytes': sum((output / name).stat().st_size for name in files),
            'runtime_identity': data['runtime_identity'], 'user_media_included': False,
            'scope': __doc__}


def bundled_main(root, argv):
    # This command does not search another checkout or silently rebuild inputs.
    verify(root)
    sys.path.insert(0, str(root / 'host/scripts'))
    import lemmasim_auth as auth
    with relocated(root) as prepared:
        auth.prepared(prepared)  # original full source/component/LLVM audits
        if argv == ['--verify-only']:
            print('PASS local ROM/native/host bundle; external pinned dependencies validated; no guest clocks')
            return 0
        if argv == ['--help'] or not argv:
            print('Use run.py --public-development-key COMMAND [existing lemmasim-auth arguments]\n'
                  'Commands: ' + ', '.join(COMMANDS) + '\n'
                  'launch uses bundled ROM/native preparation automatically; media remain external.\n'
                  'Use run.py control --session-dir DIR --request JSON [--timeout SECONDS].\n'
                  'Exact Nix-store tools/libraries remain required; no clean-host/redistribution claim.')
            return 0
        if argv[0] == 'control':
            parser = argparse.ArgumentParser(allow_abbrev=False)
            parser.add_argument('--session-dir', type=Path, required=True)
            parser.add_argument('--request', required=True)
            parser.add_argument('--timeout', type=int, default=120)
            args = parser.parse_args(argv[1:])
            if not 1 <= args.timeout <= 120:
                raise ValueError('bounded control timeout required')
            request = json.loads(args.request)
            if not isinstance(request, dict):
                raise ValueError('control request must be an object')
            print(json.dumps(auth.sessions.request(args.session_dir, request, args.timeout)))
            return 0
        if len(argv) < 2 or argv[0] != '--public-development-key' or argv[1] not in COMMANDS:
            raise ValueError('explicit public-development-key and supported command required')
        if any(arg == '--prepared' or arg.startswith('--prepared=') for arg in argv):
            raise ValueError('bundle owns its exact preparation')
        if argv[1] == 'launch':
            argv = [*argv[:2], '--prepared', str(prepared), *argv[2:]]
        result = auth.main(argv)
        return result if isinstance(result, int) else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    local = Path(__file__).resolve().parent
    if (local / 'bundle.json').is_file():
        return bundled_main(local, argv)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(create(args.prepared, args.output_dir), indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit('Product bundle failed: ' + str(error))
