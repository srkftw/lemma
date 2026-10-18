#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Produce or admit the structured Lean reset ROM, before invoking its tools.

This is artifact production only. The caller independently audits the fixed
handoff words and records its current preparation/guest associations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from action_cache import ActionCache, file_hash, source_provenance, tool_identity, write_if_changed
from build_actions import (controlled_environment, fresh_requested, lean_source_inputs,
                           lean_workspace, LOADED_RECIPE_SHA256)
from core0_common import (Core0Error, require_tools, run_bounded, LOADED_SOURCE_SHA256,
                          LEASE_WORKER_SHA256)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'Lemma/Platform/Silicon/BootROM.lean'
OUTPUTS = ('boot.S', 'boot.o', 'boot.elf', 'boot.bin')
LOADED_RESET_SOURCE_SHA256 = file_hash(Path(__file__).resolve())
HOST_INPUTS = ('scripts/silicon_reset_rom.py', 'scripts/build_actions.py',
               'scripts/core0_common.py', 'scripts/action_worker.py',
               'tooling/toolchain-lock.json')


def source_inputs(root, selected_profile):
    root = Path(root).resolve()
    inputs = lean_source_inputs(root, [root / SOURCE])
    inputs.update({name: root / name for name in HOST_INPUTS})
    inputs['selected-profile.json'] = Path(selected_profile).resolve()
    return inputs


def validate_loaded_sources(inputs):
    expected = {'scripts/silicon_reset_rom.py': LOADED_RESET_SOURCE_SHA256,
                'scripts/build_actions.py': LOADED_RECIPE_SHA256,
                'scripts/core0_common.py': LOADED_SOURCE_SHA256}
    if any(file_hash(inputs[name]) != digest for name, digest in expected.items()):
        raise Core0Error('reset ROM host implementation changed after import; restart from a stable candidate')


def tool_closure(tools, pin):
    """Actual immutable tool outputs, including Lean's imported host libraries."""
    expected = {
        'lean': pin['tools']['lean']['store_path'],
        'lake': pin['tools']['lean']['store_path'],
        'clang': pin['tools']['llvm']['outputs']['clang_unwrapped']['store_path'],
        'ld.lld': pin['tools']['lld']['store_path'],
        'llvm-objcopy': pin['tools']['llvm']['store_path'],
    }
    for name, store in expected.items():
        if not Path(tools[name]).is_relative_to(store):
            raise Core0Error('reset ROM requires pinned immutable tool: ' + name)
    observed = subprocess.run([tools['nix'], 'path-info', '--recursive', '--json',
                               *sorted(set(expected.values()))],
                              check=True, capture_output=True, text=True, timeout=60)
    info = json.loads(observed.stdout)
    if not isinstance(info, dict) or not info or not set(expected.values()) <= set(info):
        raise Core0Error('reset ROM tool closure is unavailable')
    result = {}
    for path, item in info.items():
        if (not path.startswith('/nix/store/') or not isinstance(item, dict) or
                not isinstance(item.get('narHash'), str) or
                not isinstance(item.get('references'), list) or
                not set(item['references']) <= set(info)):
            raise Core0Error('reset ROM tool closure is incomplete')
        result[path] = {key: item[key] for key in ('narHash', 'narSize', 'references')}
    return result


def build(output_dir, selected_profile, *, cache_dir=None, fresh=False, root=ROOT):
    root = Path(root).resolve()
    output_dir = Path(output_dir).resolve()
    selected_profile = Path(selected_profile).resolve()
    tools = require_tools(('nix', 'lean', 'lake', 'clang', 'ld.lld', 'llvm-objcopy'))
    inputs = source_inputs(root, selected_profile)
    validate_loaded_sources(inputs)
    pin = json.loads((root / 'tooling/toolchain-lock.json').read_text())
    if pin.get('status') != 'pinned':
        raise Core0Error('reset ROM toolchain lock is not pinned')
    cache = ActionCache(root, cache_dir, fresh=fresh_requested(fresh))
    environment = controlled_environment(tools)
    action = {
        'schema': 'lemma-reset-rom-action/1',
        'recipe': 'genuine-Lean-handoff/1',
        'tools': {name: tool_identity(path) for name, path in tools.items()},
        'tool_dependencies': tool_closure(tools, pin),
        'target': 'riscv64-unknown-elf', 'abi': 'lp64',
        'isa': 'rv64im_zicsr_zifencei', 'code_model': 'medany',
        'environment': environment,
        # These paths select the actual private Lake/compiler CWD. They have
        # deliberately conservative semantics; relocation creates another key.
        'path_semantics': {'repository': str(root), 'cache': str(cache.directory)},
        'options': {'relax': False, 'text_address': '0x1000', 'entry': '_reset',
                    'binary_sections': ['.text']},
    }

    def produce(workspace):
        commands = []
        validate_loaded_sources(workspace.inputs)
        with lean_workspace(root, cache.directory, tools, workspace.inputs,
                            fresh=cache.fresh) as tree:
            if LEASE_WORKER_SHA256.get() != file_hash(workspace.inputs['scripts/action_worker.py']):
                raise Core0Error('reset ROM protected worker differs from its declared source snapshot')
            target = tree / 'build' / 'reset-rom'
            target.mkdir(parents=True, exist_ok=True)
            rows = [
                [tools['lake'], 'build', 'Lemma.Machine.Primitives',
                 'Lemma.Platform.Silicon.Binding'],
                [tools['lake'], 'env', 'lean', '-j2', '--run', SOURCE,
                 'build/reset-rom/boot.S'],
                [tools['clang'], '--target=riscv64-unknown-elf',
                 '-march=rv64im_zicsr_zifencei', '-mabi=lp64', '-mcmodel=medany',
                 '-mno-relax', '-c', 'build/reset-rom/boot.S', '-o', 'build/reset-rom/boot.o'],
                [tools['ld.lld'], '-m', 'elf64lriscv', '--no-relax', '-Ttext=0x1000',
                 '-e', '_reset', 'build/reset-rom/boot.o', '-o', 'build/reset-rom/boot.elf'],
                [tools['llvm-objcopy'], '-O', 'binary', '--only-section=.text',
                 'build/reset-rom/boot.elf', 'build/reset-rom/boot.bin'],
            ]
            for argv in rows:
                result = run_bounded(argv, cwd=tree, env=environment, timeout_seconds=300)
                command = {'argv': argv, 'cwd': str(tree), 'returncode': result.returncode,
                           'elapsed_seconds': result.elapsed_seconds,
                           'stdout': result.stdout.decode(errors='replace'),
                           'stderr': result.stderr.decode(errors='replace')}
                commands.append(command)
                if result.returncode:
                    write_if_changed(output_dir / 'production-failure.json',
                                     json.dumps({'commands': commands}, indent=2) + '\n')
                    raise Core0Error('reset ROM command failed: ' + ' '.join(argv) +
                                     '; ' + str(output_dir / 'production-failure.json'))
            for name in OUTPUTS:
                shutil.copyfile(target / name, workspace.outputs[name])
        return {'commands': commands, 'scope': 'artifact production; execution and audit separate'}

    receipt = cache.run(action, inputs, {name: output_dir / name for name in OUTPUTS},
                        produce, provenance=source_provenance(root))
    expected = {'scripts/silicon_reset_rom.py': LOADED_RESET_SOURCE_SHA256,
                'scripts/build_actions.py': LOADED_RECIPE_SHA256,
                'scripts/core0_common.py': LOADED_SOURCE_SHA256}
    if any(receipt['producer']['request']['inputs'][name]['sha256'] != digest for name, digest in expected.items()):
        raise Core0Error('reset ROM admitted host implementation differs from its loaded producer')
    write_if_changed(output_dir / 'action-admission.json', json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--profile-file', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--fresh', action='store_true')
    args = parser.parse_args()
    receipt = build(args.output_dir, args.profile_file,
                    cache_dir=args.cache_dir, fresh=args.fresh)
    print(f"Reset ROM {receipt['status']}: {receipt['reason']} ({receipt['action_key'][:16]})")


if __name__ == '__main__':
    main()
