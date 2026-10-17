#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare real canonical RTL evaluation schedules, without skipped clocks.

Every wrapper/generated-RTL checkpoint byte and actual guest UART byte must
match. The reference retains the old extra disabled-USB evaluation. No field
mask, timing tolerance, initialized guest state or host guest computation is used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from silicon_guest import ROOT, _read_unique_json, profile_path, run_command, sha
from silicon_guest_bundle import prepared
from check_native_usb_wire_pending import run_fixture


def require(value, message):
    if not value:
        raise ValueError(message)


def native_inputs(manifest):
    """Reconstruct the compiler input seal, without reading mutable source."""
    expected = {}

    def add(path, digest):
        path = Path(path)
        if path.is_absolute():
            path = path.relative_to(ROOT)
        require(path.parts and not any(p in ('.', '..') for p in path.parts),
                'escaping original native source')
        name = path.as_posix()
        require(name not in expected or expected[name] == digest,
                'conflicting native source digest')
        require(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest),
                'malformed native source digest')
        expected[name] = digest

    for key in ('sha256', 'configuration_includes', 'host_runtime',
                'host_toolchain_inputs', 'binding_generator_inputs'):
        require(isinstance(manifest.get(key), dict) and manifest[key],
                'missing native compiler input inventory: ' + key)
        for name, digest in manifest[key].items():
            add(name, digest)
    require(isinstance(manifest.get('sources'), list) and
            len(set(manifest['sources'])) == len(manifest['sources']) and
            set(manifest['sources']) == set(manifest['sha256']),
            'native compiler source list differs')
    for key in ('host_adapter', 'build_driver', 'upstream_patch', 'runtime_identity_header'):
        add(manifest[key]['path'], manifest[key]['sha256'])
    add(Path(manifest['host_include_dir']) / 'lemma_silicon_binding.h',
        manifest['host_binding_sha256'])
    return expected


def implementation_identity(manifest):
    identity = {key: value for key, value in manifest.items() if key not in
                ('sources', 'include_dirs', 'host_include_dir', 'runtime_identity_header',
                 'build_argv', 'build_jobs', 'binary_sha256', 'snapshot_identity')}
    identity['identity_schema'] = 'lemmasim-rtl-implementation/2'
    core = ROOT / 'build/silicon/deps/cvw'
    generated = Path(manifest['host_include_dir']) / 'lemma_silicon_binding.sv'

    def logical(path):
        path = Path(path)
        if path == generated:
            return 'generated/lemma_silicon_binding.sv'
        for base, prefix in ((core, 'core/'), (core.parent / 'cvw-patched', 'patched-core/'),
                             (ROOT, 'repository/')):
            try:
                return prefix + path.relative_to(base).as_posix()
            except ValueError:
                pass
        raise ValueError('unmapped native implementation input')

    for key in ('sha256', 'configuration_includes'):
        identity[key] = {logical(path): digest for path, digest in manifest[key].items()}
        require(len(identity[key]) == len(manifest[key]), 'duplicate logical native input')
    actual = hashlib.sha256(json.dumps(identity, sort_keys=True,
                                       separators=(',', ':')).encode()).hexdigest()
    require(actual == manifest['snapshot_identity'], 'native implementation identity differs')
    return actual


def capture_current_source(build):
    """Opt-in fresh seal, only when every compiled input still matches."""
    build = build.resolve()
    require(build.is_relative_to(ROOT / 'build'), 'native archive must be task-owned under build')
    manifest_path = build / 'build.json'
    manifest_sha = sha(manifest_path)
    manifest = _read_unique_json(manifest_path)
    require(manifest['profile'] == 'lemma-silicon-dev/0.3.0' and
            manifest['configuration'] == 'external-ram-128MiB',
            'require canonical external-RAM source binding')
    expected = native_inputs(manifest)
    implementation_identity(manifest)
    selected = profile_path(manifest['profile']).relative_to(ROOT).as_posix()
    require(sha(ROOT / selected) == manifest['profile_sha256'], 'selected profile changed')
    expected[selected] = manifest['profile_sha256']
    dependency = 'tooling/silicon/dependencies.json'
    expected[dependency] = sha(ROOT / dependency)
    source = build / 'consumed-source-root'
    sidecar = build / 'consumed-source-archive.json'
    require(not source.exists() and not sidecar.exists(), 'refuse to replace an existing source archive')
    # Reject drift before copying, then seal the exact copied and original bytes
    # again before publishing. There is no live-source fallback during execution.
    for name, digest in expected.items():
        require(not (ROOT / name).is_symlink() and sha(ROOT / name) == digest,
                'compiled native source changed: ' + name)
    temporary = build / 'consumed-source-root.pending'
    require(not temporary.exists(), 'uncompleted archive already exists')
    temporary.mkdir()
    for name, digest in expected.items():
        destination = temporary / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
        require(sha(destination) == digest and sha(ROOT / name) == digest,
                'native source changed while archiving: ' + name)
    require(sha(manifest_path) == manifest_sha and
            sha(build / 'obj/lemma-rtl') == manifest['binary_sha256'],
            'native build changed while archiving')
    temporary.rename(source)
    sidecar.write_text(json.dumps({'schema': 'lemma-original-native-component-archive/2',
        'profile': manifest['profile'], 'source_inputs': expected,
        'build_manifest_sha256': manifest_sha, 'binary_sha256': manifest['binary_sha256'],
        'runtime_identity': manifest['snapshot_identity']}, indent=2) + '\n')
    return original_native(build)


def original_native(build):
    build = build.resolve()
    manifest_path = build / 'build.json'
    manifest = _read_unique_json(manifest_path)
    sidecar = build / 'consumed-source-archive.json'
    archive = _read_unique_json(sidecar)
    source = build / 'consumed-source-root'
    require(manifest['profile'] == 'lemma-silicon-dev/0.3.0' and
            manifest['configuration'] == 'external-ram-128MiB',
            'require canonical external-RAM source binding')
    expected = native_inputs(manifest)
    implementation_identity(manifest)
    # The sole preparation-time dependency declaration is itself archived;
    # there is no fallback to the live checkout after this source seal.
    dependency = 'tooling/silicon/dependencies.json'
    expected[dependency] = archive['source_inputs'][dependency]
    schema = archive['schema']
    if schema == 'lemma-original-native-component-archive/2':
        selected = profile_path(manifest['profile']).relative_to(ROOT).as_posix()
        expected[selected] = manifest['profile_sha256']
    require(schema in ('lemma-original-native-component-archive/1',
                       'lemma-original-native-component-archive/2') and
            archive['source_inputs'] == expected and
            archive['build_manifest_sha256'] == sha(manifest_path) and
            archive['binary_sha256'] == manifest['binary_sha256'] and
            archive['runtime_identity'] == manifest['snapshot_identity'] and
            sha(build / 'obj/lemma-rtl') == manifest['binary_sha256'],
            'native archive differs from full original manifest/binary')
    actual = set()
    for path in source.rglob('*'):
        require(not path.is_symlink(), 'symlink in original native archive')
        if path.is_file():
            actual.add(path.relative_to(source).as_posix())
    require(actual == set(expected), 'original native archive missing or has unlisted files')
    for name, digest in expected.items():
        require(sha(source / name) == digest, 'original native source changed: ' + name)
    pinned = _read_unique_json(source / dependency)
    require(pinned.get('schema_version') == 1 and
            pinned.get('core', {}).get('repository') == manifest['core_repository'] and
            pinned.get('core', {}).get('revision') == manifest['core_revision'],
            'archived core dependency differs')
    if schema == 'lemma-original-native-component-archive/2':
        selected_json = _read_unique_json(source / selected)
        require(selected_json.get('profile') == manifest['profile'] and
                selected_json.get('schema_version') == 1,
                'archived selected profile namespace differs')
    require((source / Path(manifest['runtime_identity_header']['path']).relative_to(ROOT)).read_text()
            == '#pragma once\n#define LEMMA_RUNTIME_IDENTITY "' + manifest['snapshot_identity'] + '"\n',
            'compiled runtime identity header differs')
    return manifest, source, expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-build', type=Path, required=True)
    parser.add_argument('--guest-bundle', type=Path, required=True)
    parser.add_argument('--capture-current-source', action='store_true',
                        help='Create an unused complete native archive after matching every original compiler input; never overwrite an existing archive')
    parser.add_argument('--disk', type=Path)
    parser.add_argument('--resume-from', type=Path,
                        help='Qualify balanced CPU/wall comparison from an unchanged admitted held-RAM cut; no cold prefix or original medium access')
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    require(out.is_relative_to(ROOT / 'build') and not out.exists(),
            'require unused task-owned output under build')
    out.mkdir(parents=True)
    started = time.monotonic()
    result = {'schema': 'lemma-native-disabled-eval/1', 'status': 'FAIL',
        'scope': __doc__, 'bounds': {'fixture_host_seconds': 600,
            'maximum_fixture_tree_rss_kib': 3145728, 'maximum_owned_bytes': 12000000000,
            'cold_clocks': 10000000, 'pending_search_clocks': 1024,
            'exact_private_suffix_clocks': 1000003, 'memory_extra_clocks': 3},
        'relation': 'Entire same-binary checkpoint containers byte-identical at all8 cuts; no field mask; actual UART exact. Both restored forks privately backed.'}
    try:
        native, archive, inputs_seal = (capture_current_source(args.native_build)
            if args.capture_current_source else original_native(args.native_build))
        guest = prepared(args.guest_bundle, 'rtl', 'notebook', 'lemma-silicon-dev/0.3.0')
        entry = guest['workloads']['notebook']
        if args.resume_from:
            require(args.disk is None, 'retained replay never consults the original medium')
            origin = args.resume_from.resolve()
            prior = _read_unique_json(origin / 'result.json')
            source_checkpoint = origin / 'pending-ram-reference.chk'
            require(prior['status'] == 'PASS_FULL_STATE_AND_PENDING_SUFFIX' and
                    prior['native_identity'] == native['snapshot_identity'] and
                    prior['guest_identity'] == entry['image']['sha256'] and
                    prior['native_manifest_sha256'] == sha(args.native_build / 'build.json') and
                    sha(source_checkpoint) == prior['checkpoints'][source_checkpoint.name]['sha256'],
                    'original pending observation/authority/cut differs')
            medium_sha = prior['input_medium_sha256']
            result['retained_boundary'] = {'path': str(source_checkpoint),
                'sha256': sha(source_checkpoint), 'original_result_sha256': sha(origin / 'result.json'),
                'original_medium_access': False, 'input_reinjection': False}
        else:
            require(args.disk is not None and args.disk.is_file() and
                    args.disk.stat().st_size == 268435456,
                    'require original acknowledged256MiB opaque medium')
            medium_sha = sha(args.disk)
            for name in ('reference.raw', 'optimized.raw'):
                subprocess.run(['cp', '--reflink=auto', '--sparse=always',
                                str(args.disk.resolve()), str(out / name)], check=True)
                require(sha(out / name) == medium_sha, 'opaque medium copy differs')
        version_path = out / 'verilator-version.txt'
        run_command(['nix-shell', archive / 'tooling/silicon/sim.nix', '--run', 'verilator -V'],
                    timeout=30, log=version_path)
        roots = set(re.findall(r'^\s*VERILATOR_ROOT\s*=\s*(\S+)\s*$', version_path.read_text(), re.M))
        require(len(roots) == 1, 'ambiguous Verilator runtime include root')
        prefix = Path(roots.pop())
        obj = args.native_build.resolve() / 'obj'
        make_roots = set(re.findall(r'^\s*VERILATOR_ROOT\s*[:?]?=\s*(\S+)\s*$',
                                   (obj / 'Vlemma_soc.mk').read_text(), re.M))
        require(make_roots == {str(prefix)}, 'fixture header/runtime tool differs from native compiler')
        names = ['machine_runtime.o', 'backing_io.o', 'backing_io_posix.o',
                 'backing_peer.o', 'ble_peer_transport.o', 'usb_transport.o',
                 'verilated.o', 'verilated_save.o', 'verilated_threads.o',
                 'verilated_dpi.o', 'Vlemma_soc__ALL.a']
        fixture = ROOT / 'tests/lemmasim/native_disabled_eval.cpp'
        inputs = {str(obj / name): sha(obj / name) for name in names}
        inputs[str(fixture)] = sha(fixture)
        binary = out / 'test'
        argv = ['c++', '-O2', '-std=c++17', '-Wall', '-Wextra', '-Werror',
            '-I', str(archive / 'sim/rtl/host'), '-I', str(obj),
            '-I', str(archive / Path(native['host_include_dir']).relative_to(ROOT)),
            '-isystem', str(prefix / 'include'), '-isystem', str(prefix / 'include/vltstd'),
            str(fixture), *[str(obj / name) for name in names], '-pthread', '-o', str(binary)]
        run_command(['nix-shell', archive / 'tooling/silicon/sim.nix', '--run',
                     __import__('shlex').join(argv)], timeout=60, log=out / 'compile.log')
        result.update(native_manifest_sha256=sha(args.native_build / 'build.json'),
            native_identity=native['snapshot_identity'], compiled_inputs=inputs,
            fixture_binary_sha256=sha(binary), original_native_inputs=len(inputs_seal),
            guest_identity=entry['image']['sha256'], input_medium_sha256=medium_sha,
            compile_argv=argv, observer_sha256=sha(Path(__file__)))
        (out / 'plan.json').write_text(json.dumps(result, indent=2) + '\n')
        arguments = ([binary, '--resume', out, source_checkpoint] if args.resume_from else
            [binary, out, entry['image']['path'], guest['rom']['path'],
             entry['dtb']['path'], entry['descriptor']['path'], out / 'reference.raw',
             out / 'optimized.raw', '0x87e00000'])
        result['owned_processes'] = run_fixture(arguments, out / 'run.log', 600, 3145728)
        observations = json.loads((out / 'run.log').read_text())
        expected_status = ('PASS_RETAINED_SUFFIX_CPU_COMPARISON' if args.resume_from else
                           'PASS_FULL_STATE_AND_PENDING_SUFFIX')
        require(observations['status'] == expected_status and
                observations['complete_checkpoint_pairs'] == (4 if args.resume_from else 8) and
                observations['masked_fields'] == 0, 'nonempty complete paired relation missing')
        if args.resume_from:
            require(sha(source_checkpoint) == result['retained_boundary']['sha256'],
                    'original retained boundary changed')
        else:
            require(all(sha(out / name) == medium_sha for name in ('reference.raw', 'optimized.raw'))
                    and sha(args.disk) == medium_sha, 'prefix or suffix changed original acknowledged bytes')
        original_native(args.native_build)
        require(all(sha(Path(name)) == digest for name, digest in inputs.items()),
                'fixture inputs changed while executing')
        require(sum(p.stat().st_size for p in out.rglob('*') if p.is_file()) <= 12000000000,
                'predeclared disk bound exceeded')
        snapshots = {p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)}
                     for p in out.glob('*.chk')}
        result.update(status=expected_status, observed=observations,
                      checkpoints=snapshots, acknowledged_media_unchanged=True)
    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.SubprocessError,
            KeyError) as error:
        result.update(error=str(error))
    finally:
        result['host_seconds'] = time.monotonic() - started
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'])
    return 0 if result['status'] in ('PASS_FULL_STATE_AND_PENDING_SUFFIX',
                                    'PASS_RETAINED_SUFFIX_CPU_COMPARISON') else 1


if __name__ == '__main__':
    raise SystemExit(main())
