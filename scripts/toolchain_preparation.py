"""Share checked immutable toolchain preparation through the local action cache.

The result is validated version/source metadata, never guest acceptance. Original
commands remain in the producer receipt; a current admission is one explicit
route, rather than a fabricated replay of those commands.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path
import re
import subprocess
import time

from action_cache import (ActionCache, ADMISSION_SCHEMA, RECEIPT_SCHEMA,
                          SCHEMA as CACHE_SCHEMA, _digest, _json, source_provenance)
from core0_common import Core0Error, sha256, write_json

SCHEMA = 'lemma-toolchain-preparation/1'
FILES = ('flake.nix', 'flake.lock', 'tooling/toolchain-lock.json',
         'scripts/toolchain_preparation.py')
VERSIONS = {'lean': '4.34.1', 'lake': '5.0.0-src', 'opt': '20.1.8', 'llc': '20.1.8',
            'clang': '20.1.8', 'ld.lld': '20.1.8', 'qemu-system-riscv64': '11.1.1', 'dtc': '1.8.1'}
TOOLS = (*VERSIONS, 'nix', 'llvm-objcopy', 'llvm-readelf', 'llvm-nm', 'llvm-objdump')


def _recipe():
    import build_kernel
    fresh = getattr(build_kernel, '_realize_toolchain_fresh', build_kernel.realize_toolchain)
    return {'schema': SCHEMA,
            'fresh_implementation_sha256': hashlib.sha256(inspect.getsource(fresh).encode()).hexdigest(),
            'source_validator_sha256': hashlib.sha256(inspect.getsource(build_kernel.validate_lean_source_realization).encode()).hexdigest(),
            'uint_source_sha256': build_kernel.LEAN_UINT_SOURCE_SHA256,
            'source_expression': build_kernel.LEAN_SOURCE_EXPRESSION}


def _identities(tools):
    # Do not run --version while looking up a reusable version-check result.
    # Nix store paths plus current executable bytes identify the actual tools.
    identities = {}
    for name in TOOLS:
        invoked = Path(tools[name])
        path = invoked.resolve(strict=True)
        if not invoked.is_absolute() or path.parts[:3] != ('/', 'nix', 'store'):
            raise Core0Error('preparation reuse requires immutable Nix tool: ' + name)
        identities[name] = {'path': str(path), 'invoked_as': str(invoked), 'sha256': sha256(path)}
    return identities


def _closure(tools, identities, root):
    stores = sorted({str(Path(*Path(item['path']).parts[:4])) for item in identities.values()})
    argv = [tools['nix'], 'path-info', '--recursive', '--json', *stores]
    started = time.monotonic()
    result = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=60, check=True)
    info = json.loads(result.stdout)
    if not isinstance(info, dict) or not info or not set(stores) <= set(info):
        raise Core0Error('toolchain preparation immutable closure is incomplete')
    closure = {}
    for path, item in info.items():
        if (not path.startswith('/nix/store/') or not isinstance(item, dict) or
                not isinstance(item.get('narHash'), str) or type(item.get('narSize')) is not int or
                not isinstance(item.get('references'), list) or not set(item['references']) <= set(info)):
            raise Core0Error('toolchain preparation immutable closure is malformed')
        closure[path] = {'narHash': item['narHash'], 'narSize': item['narSize'],
                         'references': sorted(item['references'])}
    return closure, {'argv': argv, 'cwd': str(root), 'returncode': 0,
                     'elapsed_seconds': time.monotonic() - started,
                     'stdout': result.stdout, 'stderr': result.stderr}


def _context(action):
    identities, closure = action.get('tools'), action.get('tool_dependencies')
    if not isinstance(identities, dict) or set(identities) != set(TOOLS) or not isinstance(closure, dict) or not closure:
        raise Core0Error('toolchain preparation tool/dependency closure differs')
    stores = set()
    for item in identities.values():
        if (not isinstance(item, dict) or set(item) != {'path', 'invoked_as', 'sha256'} or
                not all(isinstance(item[k], str) for k in item) or
                Path(item['path']).parts[:3] != ('/', 'nix', 'store') or
                not Path(item['invoked_as']).is_absolute() or re.fullmatch('[0-9a-f]{64}', item['sha256']) is None):
            raise Core0Error('toolchain preparation executable identity differs')
        stores.add(str(Path(*Path(item['path']).parts[:4])))
    if not stores <= set(closure):
        raise Core0Error('toolchain preparation omits an executable store closure')
    for path, item in closure.items():
        if (not isinstance(path, str) or Path(path).parts[:3] != ('/', 'nix', 'store') or len(Path(path).parts) != 4 or
                not isinstance(item, dict) or set(item) != {'narHash', 'narSize', 'references'} or
                not isinstance(item['narHash'], str) or re.fullmatch(r'sha256-[A-Za-z0-9+/]{43}=', item['narHash']) is None or
                type(item['narSize']) is not int or item['narSize'] <= 0 or not isinstance(item['references'], list) or
                any(not isinstance(ref, str) for ref in item['references']) or
                item['references'] != sorted(set(item['references'])) or not set(item['references']) <= set(closure)):
            raise Core0Error('toolchain preparation dependency NAR evidence differs')


def _validate(result, pin, identities, rows):
    from build_kernel import validate_lean_source_realization, LEAN_UINT_SOURCE_SHA256, LEAN_SOURCE_EXPRESSION
    if not isinstance(result, dict) or set(result) != {'schema', 'versions', 'lean_source_realization'} or result['schema'] != SCHEMA:
        raise Core0Error('toolchain preparation result is incompatible')
    if pin.get('status') != 'pinned' or not isinstance(rows, list) or len(rows) != len(VERSIONS) + 2:
        raise Core0Error('toolchain preparation lacks complete actual command evidence')
    expected = [[identities[name]['invoked_as'], '--version'] for name in VERSIONS]
    expected += [[identities['nix']['invoked_as'], 'build', '--no-link', '--print-out-paths', '--impure', '--expr', LEAN_SOURCE_EXPRESSION],
                 [identities['nix']['invoked_as'], 'path-info', '--json', pin['tools']['lean']['source_path']]]
    if any(not isinstance(row, dict) or row.get('argv') != argv or row.get('cwd') != '.' or
           row.get('returncode') != 0 or not isinstance(row.get('stdout'), str) or
           not isinstance(row.get('stderr'), str) or 'route' in row
           for row, argv in zip(rows, expected)):
        raise Core0Error('toolchain preparation original command order/arguments differ')
    versions = result['versions']
    if not isinstance(versions, dict) or set(versions) != set(VERSIONS):
        raise Core0Error('toolchain preparation version inventory differs')
    for (name, version), row in zip(VERSIONS.items(), rows):
        if versions[name] != {'path': identities[name]['invoked_as'], 'version': row['stdout'].strip()} or version not in row['stdout']:
            raise Core0Error('toolchain preparation original version observation differs: ' + name)
    for name, key in (('lean','lean'), ('lake','lean'), ('llc','llvm'), ('opt','llvm'),
                      ('llvm-objcopy','llvm'), ('llvm-readelf','llvm'), ('llvm-nm','llvm'),
                      ('llvm-objdump','llvm'), ('ld.lld','lld'), ('qemu-system-riscv64','qemu')):
        if not identities[name]['path'].startswith(pin['tools'][key]['store_path'] + '/'):
            raise Core0Error('toolchain preparation tool differs from pinned store: ' + name)
    if not identities['clang']['path'].startswith(pin['tools']['llvm']['outputs']['clang_unwrapped']['store_path'] + '/'):
        raise Core0Error('toolchain preparation Clang differs from pinned unwrapped output')
    realization = validate_lean_source_realization(pin['tools']['lean'], rows[-2]['stdout'], json.loads(rows[-1]['stdout']))
    uint = Path(realization['source_path']) / 'src/Init/Data/UInt/Basic.lean'
    if not uint.is_file() or sha256(uint) != LEAN_UINT_SOURCE_SHA256:
        raise Core0Error('toolchain preparation realized UInt source is missing or changed')
    realization.update(uint_source=str(uint), uint_source_sha256=LEAN_UINT_SOURCE_SHA256)
    if result['lean_source_realization'] != realization:
        raise Core0Error('toolchain preparation source result differs from original observations')
    return result['versions'], realization


def prepare(root, tools, invoke, *, output_dir, cache_dir=None, fresh=False, produce):
    root, output_dir = Path(root).resolve(), Path(output_dir).resolve()
    commands = invoke.command_rows
    pin = json.loads((root / 'tooling/toolchain-lock.json').read_text())
    identities = _identities(tools)
    closure, observed = _closure(tools, identities, root)
    action = {'schema': SCHEMA, 'recipe': _recipe(), 'tools': identities,
              'tool_dependencies': closure, 'cwd': str(root),
              'scope': 'fixed immutable Lean source and tool validation; no target production'}
    _context(action)
    source = Path(pin['tools']['lean']['source_path']) / 'src/Init/Data/UInt/Basic.lean'
    cache = ActionCache(root, cache_dir, fresh=fresh or not source.is_file())
    target = output_dir / 'toolchain-preparation.json'

    def producer(workspace):
        start = len(commands)
        versions, realization = produce()
        rows = copy.deepcopy(commands[start:])
        result = {'schema': SCHEMA, 'versions': versions, 'lean_source_realization': realization}
        # Even if a mutable flake changed during Nix evaluation, only the
        # snapshot's exact fixed-output source/NAR/UInt result is admissible.
        frozen_pin = json.loads(workspace.inputs['tooling/toolchain-lock.json'].read_text())
        _validate(result, frozen_pin, identities, rows)
        write_json(workspace.outputs['toolchain.json'], result)
        del commands[start:]
        return {'commands': rows}

    receipt = cache.run(action, {name: root / name for name in FILES},
                        {'toolchain.json': target}, producer, provenance=source_provenance(root),
                        validator={'schema': SCHEMA, 'identity_observation': observed})
    result = json.loads(target.read_text())
    value = _validate(result, pin, identities, receipt['producer']['executed']['commands'])
    path = output_dir / 'toolchain-admission.json'
    write_json(path, receipt)
    commands.append({'route': SCHEMA, 'admission': path.name, 'admission_sha256': sha256(path),
                     'result': target.name, 'result_sha256': sha256(target)})
    write_json(output_dir / 'commands.json', commands)
    print(f"TOOLCHAIN {receipt['status']}: {receipt['reason']}", flush=True)
    return value


def admitted_commands(row, *, root, output_dir, source_root=None):
    root, output_dir = Path(root), Path(output_dir)
    source_root = Path(source_root or root)
    if (not isinstance(row, dict) or set(row) != {'route', 'admission', 'admission_sha256', 'result', 'result_sha256'} or
            row.get('route') != SCHEMA or row.get('admission') != 'toolchain-admission.json' or
            row.get('result') != 'toolchain-preparation.json'):
        raise Core0Error('toolchain preparation route is malformed')
    receipt_path, target = output_dir / row['admission'], output_dir / row['result']
    for path, digest in ((receipt_path, row['admission_sha256']), (target, row['result_sha256'])):
        if path.is_symlink() or not path.is_file() or sha256(path) != digest:
            raise Core0Error('toolchain preparation retained artifact is missing or changed')
    receipt = json.loads(receipt_path.read_text())
    producer = receipt.get('producer', {})
    request = producer.get('request', {})
    if (receipt.get('schema') != ADMISSION_SCHEMA or receipt.get('status') not in {'fresh', 'reused'} or
            producer.get('schema') != RECEIPT_SCHEMA or producer.get('result') != 'success' or
            request.get('schema') != CACHE_SCHEMA or _digest(_json(producer)) != receipt.get('producer_receipt_id') or
            _digest(_json(request)) != receipt.get('action_key') or producer.get('action_key') != receipt.get('action_key') or
            producer.get('outputs') != receipt.get('outputs') or request.get('output_names') != ['toolchain.json'] or
            producer.get('input_archive_sha256') != _digest(_json(request.get('inputs')))):
        raise Core0Error('toolchain preparation admission and producer differ')
    action = request['action']
    if (action.get('schema') != SCHEMA or action.get('recipe') != _recipe() or
            action.get('cwd') != producer.get('provenance', {}).get('checkout') or
            not isinstance(action.get('cwd'), str) or not Path(action['cwd']).is_absolute() or
            set(action.get('tools', {})) != set(TOOLS) or set(request['inputs']) != set(FILES)):
        raise Core0Error('toolchain preparation recipe/dependency inventory differs')
    _context(action)
    for name, item in request['inputs'].items():
        path = source_root / name
        if (not isinstance(item, dict) or set(item) != {'sha256', 'size', 'executable'} or
                type(item.get('executable')) is not bool or path.is_symlink() or not path.is_file() or
                sha256(path) != item.get('sha256') or path.stat().st_size != item.get('size')):
            raise Core0Error('toolchain preparation consumed source changed: ' + name)
    outputs = receipt['outputs']
    if set(outputs) != {'toolchain.json'} or outputs['toolchain.json'].get('sha256') != sha256(target) or outputs['toolchain.json'].get('size') != target.stat().st_size:
        raise Core0Error('toolchain preparation admitted result inventory differs')
    rows = producer.get('executed', {}).get('commands')
    pin = json.loads((source_root / 'tooling/toolchain-lock.json').read_text())
    _validate(json.loads(target.read_text()), pin, action['tools'], rows)
    return [{**command, 'admitted_route': receipt['status'], 'preparation_route': SCHEMA}
            for command in rows]
