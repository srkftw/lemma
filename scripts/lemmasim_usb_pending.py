#!/usr/bin/env python3
"""Additive hosted Lean USB policy4; no objects enter the freestanding image."""
from pathlib import Path
import argparse
import json
import os
import subprocess

from lemmasim_companion import sha, peer_info
from lemmasim_usb import validate as validate_legacy

ROOT = Path(__file__).resolve().parents[1]
SOURCES = tuple(ROOT / name for name in ('sim/usb/USBPendingPolicy.lean',
    'sim/usb/pending_main.c', 'scripts/lemmasim_usb_pending.py'))
DEPENDENCIES = ('Protocol', 'HostIO', 'ClientPolicy', 'USBPacket', 'USBHost')
OBJECTS = tuple(n + suffix for n in DEPENDENCIES for suffix in ('.c', '.olean')) + \
          ('USBPendingPolicy.c', 'USBPendingPolicy.olean', 'USBPendingPolicy.o',
           'USBHostLibrary.o', 'pending_main.o')
RECIPE = {'USBHostLibrary': ['-O2', '-Dmain=lemma_usb_legacy_program_main',
                           '-Drun_main=lemma_usb_legacy_run_main',
                           '-D_lean_main=lemma_usb_legacy_lean_main'],
          'policy': ['-O2'], 'entry': ['-O2', '-Wall', '-Wextra', '-Werror']}


def legacy_inputs(prepared, record):
    companion = Path(record['companion_prepared']['path'])
    compiled = json.loads(companion.read_text())
    expected = {str(companion.parent/(n+'.o')): compiled['generated_host_objects'][n+'.o']
                for n in ('Protocol', 'HostIO', 'ClientPolicy')}
    expected[str(prepared.parent/'USBPacket.o')] = record['objects']['USBPacket.o']
    for path, digest in expected.items():
        if sha(path) != digest: raise ValueError('policy3 linked object identity changed')
    return expected, compiled


def build(output, legacy_prepared):
    output, legacy_prepared = Path(output).resolve(), Path(legacy_prepared).resolve()
    if output.exists() or not output.is_relative_to(ROOT / 'build'):
        raise ValueError('policy4 build must use an unused owned output')
    legacy = validate_legacy(legacy_prepared)
    output.mkdir(parents=True)
    before = {str(p.relative_to(ROOT)): sha(p) for p in SOURCES}
    compiler = legacy['host_tools']['lean']['path']
    leanc = legacy['host_tools']['leanc']['path']
    companion = Path(legacy['companion_prepared']['path']).parent
    inputs, companion_record = legacy_inputs(legacy_prepared, legacy)
    environment = dict(os.environ, LEAN_PATH=str(output))
    commands = []
    # Re-elaborate the imported interfaces from their maintained sources. Their
    # generated C must also equal the genuine policy3 producer's recorded C;
    # no unchecked cached .olean can supply a new interface or body.
    for module in DEPENDENCIES:
        source_root = ROOT / ('sim/companion' if module in DEPENDENCIES[:3] else 'sim/usb')
        command = [compiler, '-R', str(source_root), '-o', str(output/(module+'.olean')),
                   '-c', str(output/(module+'.c')), str(source_root/(module+'.lean'))]
        subprocess.run(command, cwd=ROOT, env=environment, check=True, timeout=120)
        commands.append(command)
        expected = companion_record['generated_host_objects'][module+'.c'] if \
                   module in DEPENDENCIES[:3] else legacy['objects'][module+'.c']
        if sha(output/(module+'.c')) != expected:
            raise ValueError('re-elaborated policy3 dependency C differs from original producer')
    later = [[compiler, '-R', str(ROOT / 'sim/usb'), '-o', str(output/'USBPendingPolicy.olean'),
                 '-c', str(output/'USBPendingPolicy.c'), str(ROOT/'sim/usb/USBPendingPolicy.lean')],
                [leanc, *RECIPE['policy'], '-c', str(output/'USBPendingPolicy.c'),
                 '-o', str(output/'USBPendingPolicy.o')],
                [leanc, *RECIPE['USBHostLibrary'], '-c', str(output/'USBHost.c'),
                 '-o', str(output/'USBHostLibrary.o')],
                [leanc, *RECIPE['entry'], '-c', str(ROOT/'sim/usb/pending_main.c'),
                 '-o', str(output/'pending_main.o')],
                [leanc, *[str(companion/(n+'.o')) for n in ('Protocol', 'HostIO', 'ClientPolicy')],
                 str(legacy_prepared.parent/'USBPacket.o'), str(output/'USBHostLibrary.o'),
                 str(output/'USBPendingPolicy.o'), str(output/'pending_main.o'),
                 '-o', str(output/'usb-pending-host')]]
    for command in later:
        subprocess.run(command, cwd=ROOT, env=environment, check=True, timeout=120)
        commands.append(command)
    if before != {str(p.relative_to(ROOT)): sha(p) for p in SOURCES}:
        raise ValueError('policy4 sources changed during build')
    validate_legacy(legacy_prepared)
    result = {'schema': 'lemma-usb-host-dev/4', 'policy_version': 'lemma-usb-pending-policy/4',
              'raw_interface': 'USBHOST/2 PACKET_BYTES_DEV',
              'maximum_operation_wait_clocks': 100000000,
              'uncertainty_backpressure_quantum': 100000, 'fragment_quantum': 1000,
              'malformed_error_retries': 3,
              'scope': 'hosted Lean policy only; target objects and runtime unchanged',
              'sources': before, 'legacy_prepared': {'path': str(legacy_prepared),
                    'sha256': sha(legacy_prepared)}, 'host_tools': legacy['host_tools'],
              'recipe': RECIPE, 'commands': commands, 'legacy_link_inputs': inputs,
              'objects': {n: sha(output/n) for n in OBJECTS},
              'binary': {'path': str(output/'usb-pending-host'),
                         'sha256': sha(output/'usb-pending-host')}, 'target_objects_added': []}
    (output/'prepared.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2)); return result


def validate(prepared):
    prepared = Path(prepared).resolve(); result = json.loads(prepared.read_text())
    required = ('lemma-usb-host-dev/4', 'lemma-usb-pending-policy/4',
                'USBHOST/2 PACKET_BYTES_DEV', 100000000, 100000, 1000, 3)
    actual = tuple(result.get(key) for key in ('schema', 'policy_version', 'raw_interface',
        'maximum_operation_wait_clocks', 'uncertainty_backpressure_quantum',
        'fragment_quantum', 'malformed_error_retries'))
    if actual != required or result.get('sources') != {
        str(p.relative_to(ROOT)): sha(p) for p in SOURCES}:
        raise ValueError('policy4 source or declared semantic identity changed')
    legacy = result['legacy_prepared']; path = Path(legacy['path'])
    if sha(path) != legacy['sha256']: raise ValueError('policy3 dependency identity changed')
    original = validate_legacy(path)
    inputs, _ = legacy_inputs(path, original)
    if result.get('host_tools') != original['host_tools'] or \
       result.get('legacy_link_inputs') != inputs:
        raise ValueError('policy4 complete linked input or tool closure changed')
    if result.get('recipe') != RECIPE or set(result.get('objects', {})) != set(OBJECTS):
        raise ValueError('policy4 recipe or object closure changed')
    for name, digest in result['objects'].items():
        if sha(prepared.parent/name) != digest: raise ValueError('policy4 object identity changed')
    for tool in result['host_tools'].values():
        if sha(tool['path']) != tool['sha256']: raise ValueError('policy4 host tool identity changed')
    binary = Path(result['binary']['path'])
    if binary != prepared.parent/'usb-pending-host' or not os.access(binary, os.X_OK) or \
       sha(binary) != result['binary']['sha256'] or result.get('target_objects_added') != []:
        raise ValueError('policy4 host binary or target boundary changed')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    build_parser = commands.add_parser('build')
    build_parser.add_argument('--legacy-prepared', type=Path, required=True)
    build_parser.add_argument('--output-dir', type=Path, required=True)
    host_parser = commands.add_parser('host')
    for name in ('prepared', 'directory', 'socket', 'state'):
        host_parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == 'build': return build(args.output_dir, args.legacy_prepared)
    record = validate(args.prepared); peer = peer_info(args.directory)
    executable = record['binary']['path']
    os.execv(executable, [executable, str(args.socket.resolve()), str(args.state.resolve()),
                        str(peer['writer']), str(ROOT/'sim/companion/os_io.py')])


if __name__ == '__main__': main()
