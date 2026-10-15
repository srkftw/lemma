#!/usr/bin/env python3
"""Launch the packaged native machine with its original compiled artifacts."""
import hashlib
import json
from pathlib import Path
import runpy
import sys


def verify(root):
    root = Path(root).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('Symlinked native package path')
    data = json.loads((root / 'package.json').read_text())
    if data.get('schema') != 'lemma-local-native-distribution/1':
        raise ValueError('Unsupported native distribution')
    files = data.get('files')
    if not isinstance(files, dict) or not 8 <= len(files) <= 8192:
        raise ValueError('Missing native distribution inventory')
    total = 0
    for name, row in files.items():
        if (not isinstance(name, str) or not name or Path(name).is_absolute()
                or any(p in ('.', '..', '') for p in name.split('/'))):
            raise ValueError('Invalid native package path')
        path = root / name
        if (not isinstance(row, dict) or set(row) != {'sha256', 'bytes'}
                or type(row['bytes']) is not int or not 0 <= row['bytes'] <= 1 << 30
                or any(p.is_symlink() for p in (path, *path.parents))
                or not path.is_file() or path.stat().st_size != row['bytes']):
            raise ValueError('Missing or changed native distribution file: ' + name)
        total += row['bytes']
        if total > 2 << 30 or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Native distribution byte bound/identity failed')
    required = {'run.py', 'bundle/bundle.json', 'host/scripts/lemmasim',
                'host/scripts/native_bundle_relocation.py', 'NOTICE.txt', 'README.md'}
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if (not required <= files.keys() or actual != files.keys() | {'package.json'}
            or any(p.is_symlink() for p in root.rglob('*'))
            or data.get('source_bundle_sha256') != files['bundle/bundle.json']['sha256']):
        raise ValueError('Incomplete or contradictory native distribution')
    return data


def main():
    root = Path(__file__).absolute().parent
    try:
        verify(root)
        args = sys.argv[1:]
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(root / 'host/scripts'))
        if len(args) == 3 and args[:2] == ['--verify-only', '--view-dir']:
            from native_bundle_relocation import create_view
            destination = Path(args[2]).absolute()
            if destination.is_relative_to(root):
                raise ValueError('Keep the validation view outside the immutable package')
            create_view(root / 'bundle', destination, root / 'host')
            print('PASS_NATIVE_DISTRIBUTION_BOTH_BACKENDS_AND_GUESTS_NO_CPU', flush=True)
            return
        allowed = {'session', 'init', 'session-control', 'snapshot', 'restore',
                   'session-replay', 'button', 'course-install', 'course-load', 'course-delete-probe'}
        if not args or args == ['--help']:
            print('python3 -I run.py COMMAND [ordinary LemmaSim arguments]\nCommands: ' + ', '.join(sorted(allowed)) +
                  '\nExact external Nix libraries and optional Tk remain host prerequisites.\nSession/init create a persistent sibling .bundle view; keep it with the session.')
            return
        if args[0] not in allowed or '--native-bundle' in args:
            raise ValueError('Use a supported prepared command; the packaged bundle is selected automatically')
        if args[0] in ('session', 'init'):
            option = '--session-dir' if '--session-dir' in args else '--disk' if args[0] == 'init' else None
            if option is None or args.count(option) != 1 or args.index(option) + 1 >= len(args):
                raise ValueError('A session directory (or init disk) selects the persistent bundle view')
            owner = Path(args[args.index(option) + 1]).absolute()
            if owner.is_relative_to(root):
                raise ValueError('Keep mutable sessions/media outside the immutable package')
            view = owner.with_name(owner.name + '.bundle')
            from native_bundle_relocation import create_view
            create_view(root / 'bundle', view, root / 'host')
            args += ['--native-bundle', str(view)]
        script = root / 'host/scripts/lemmasim'
        sys.argv = [str(script), *args]
        runpy.run_path(str(script), run_name='__main__')
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        raise SystemExit('Native distribution launch failed: ' + str(error))


if __name__ == '__main__':
    main()
