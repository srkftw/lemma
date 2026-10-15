#!/usr/bin/env python3
"""Launch a prepared, extracted local browser machine using Python's stdlib."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def verify_package(root):
    root = Path(root).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('Distribution path contains a symlink')
    manifest = root / 'package.json'
    if manifest.is_symlink():
        raise ValueError('Symlinked distribution manifest')
    data = json.loads(manifest.read_text())
    if data.get('schema') != 'lemma-local-browser-distribution/1':
        raise ValueError('Unsupported local browser distribution')
    files = data.get('files')
    if not isinstance(files, dict) or not 6 <= len(files) <= 4096:
        raise ValueError('Incomplete distribution inventory')
    total = 0
    for name, item in files.items():
        if (not isinstance(name, str) or not name or name != Path(name).as_posix()
                or Path(name).is_absolute() or any(x in ('.', '..', '') for x in name.split('/'))):
            raise ValueError('Invalid distribution path')
        if (not isinstance(item, dict) or set(item) != {'sha256', 'bytes'}
                or not isinstance(item['sha256'], str)
                or not re.fullmatch('[a-f0-9]{64}', item['sha256'])
                or type(item['bytes']) is not int or not 0 <= item['bytes'] <= 1 << 30):
            raise ValueError('Invalid distribution identity')
        path = root / name
        if (any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file()
                or path.stat().st_size != item['bytes']):
            raise ValueError('Missing or changed distribution file: ' + name)
        total += item['bytes']
        if total > 1 << 30:
            raise ValueError('Distribution exceeds one GiB')
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Changed distribution bytes: ' + name)
    required = {'serve.py', 'tools/lemmasim_browser.py', 'tools/silicon_guest_bundle.py',
                'bundle/bundle.json', 'README.md', 'NOTICE.txt'}
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if (not required <= files.keys() or actual != files.keys() | {'package.json'}
            or any(p.is_symlink() for p in root.rglob('*'))):
        raise ValueError('Incomplete, unlisted or symlinked distribution content')
    if data.get('source_bundle_sha256') != files['bundle/bundle.json']['sha256']:
        raise ValueError('Distribution contradicts its original machine manifest')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).absolute().parent
    try:
        if not 1024 <= args.port <= 65535:
            raise ValueError('Port must be1024..65535')
        verify_package(root)
        # Validation precedes importing packaged Python. No checkout, Lean,
        # LLVM, Nix or downloaded module is used at launch.
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(root / 'tools'))
        from lemmasim_browser import local_server, validated_bundle
        validated_bundle(root / 'bundle')
        if args.verify_only:
            print('PASS_LOCAL_BROWSER_DISTRIBUTION_BYTES', flush=True)
            return
        server = local_server(root / 'bundle', args.port)
        print('Local browser machine: http://127.0.0.1:' + str(server.server_port) + '/', flush=True)
        try:
            server.serve_forever(poll_interval=.25)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        parser.exit(1, 'Local browser launch failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
