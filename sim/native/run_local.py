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
    if data.get('schema') not in ('lemma-local-native-distribution/1', 'lemma-local-native-distribution/2',
                                'lemma-local-native-distribution/3'):
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
    if data['schema'] in ('lemma-local-native-distribution/2', 'lemma-local-native-distribution/3'):
        required |= {'host/scripts/lemmasim-course', 'host/scripts/lemmasim_course_fast.py'}
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if (not required <= files.keys() or actual != files.keys() | {'package.json'}
            or any(p.is_symlink() for p in root.rglob('*'))
            or data.get('source_bundle_sha256') != files['bundle/bundle.json']['sha256']):
        raise ValueError('Incomplete or contradictory native distribution')
    if data['schema'] == 'lemma-local-native-distribution/3':
        versions = data.get('host_tool_versions', {})
        differences = versions.get('differences')
        if (versions.get('schema') != 'lemma-native-host-tool-versions/1'
                or not isinstance(differences, dict) or not 1 <= len(differences) <= 8192):
            raise ValueError('Missing separate host tool versions')
        compiled = json.loads((root / 'bundle/bundle.json').read_text()).get('sources', {})
        for relative, row in differences.items():
            if (not isinstance(row, dict) or set(row) != {'compiled_source', 'compiled_sha256', 'host_sha256'}
                    or row['compiled_source'] != 'bundle/source/' + relative
                    or row['compiled_sha256'] == row['host_sha256']
                    or compiled.get(relative) != row['compiled_sha256']
                    or files.get(row['compiled_source'], {}).get('sha256') != row['compiled_sha256']
                    or files.get('host/' + relative, {}).get('sha256') != row['host_sha256']
                    or data.get('host_inputs', {}).get(relative) != row['host_sha256']):
                raise ValueError('Contradictory compiled/host tool versions')
        expected = {name for name, digest in compiled.items()
                    if name in data.get('host_inputs', {}) and digest != data['host_inputs'][name]}
        if set(differences) != expected:
            raise ValueError('Incomplete separate host tool versions')
    elif 'host_tool_versions' in data:
        raise ValueError('Separate host tools require native distribution3')
    return data


def main():
    root = Path(__file__).absolute().parent
    try:
        distribution = verify(root)
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
                   'session-replay', 'button', 'course-install', 'course-load', 'course-delete-probe', 'file-limit'}
        if not args or args == ['--help']:
            print('python3 -I run.py COMMAND [ordinary LemmaSim arguments]\nCommands: ' + ', '.join(sorted(allowed)) +
                  '\nExact external Nix libraries and optional Tk remain host prerequisites.\nSession/init create a persistent sibling .bundle view; keep it with the session.')
            return
        if args[0] not in allowed or '--native-bundle' in args:
            raise ValueError('Use a supported prepared command; the packaged bundle is selected automatically')
        if args[0] in ('session', 'init') and '--help' not in args:
            option = '--session-dir' if '--session-dir' in args else '--disk' if args[0] == 'init' else None
            if option is None or args.count(option) != 1 or args.index(option) + 1 >= len(args):
                raise ValueError('A session directory (or init disk) selects the persistent bundle view')
            owner = Path(args[args.index(option) + 1]).absolute()
            if owner.is_relative_to(root):
                raise ValueError('Keep mutable sessions/media outside the immutable package')
            if args[0] == 'init' and '--session-dir' not in args:
                # The ordinary front end defaults under its own source root.
                # An extracted package must stay immutable after initialization.
                args += ['--session-dir', str(owner.with_name(owner.name + '.initialize'))]
            view = owner.with_name(owner.name + '.bundle')
            from native_bundle_relocation import create_view
            create_view(root / 'bundle', view, root / 'host')
            args += ['--native-bundle', str(view)]
        course = {'course-install': 'install', 'course-load': 'load',
                  'course-delete-probe': 'delete-probe'}
        if distribution['schema'] in ('lemma-local-native-distribution/2', 'lemma-local-native-distribution/3') and args[0] in course:
            args = [course[args[0]], *args[1:]]
            script = root / 'host/scripts/lemmasim-course'
        else:
            script = root / 'host/scripts/lemmasim'
        sys.argv = [str(script), *args]
        runpy.run_path(str(script), run_name='__main__')
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        raise SystemExit('Native distribution launch failed: ' + str(error))


if __name__ == '__main__':
    main()
