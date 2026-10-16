#!/usr/bin/env python3
"""Prepare the existing native machine with an extracted host command surface.

Exact external Nix loader/libraries remain prerequisites. No machine logic,
guest artifact or original provenance is replaced to make relocation succeed.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import resource
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

from silicon_guest_bundle import prepared

ROOT = Path(__file__).resolve().parents[1]
README = '''# Local native LemmaSim development machine

Requires Linux x86-64, Python3.10+ and the exact external Nix loader/library
files inventoried in bundle/bundle.json. They are not included or downloaded.
Tk is optional for native presentation; use --headless otherwise. Original
dependency notices and unresolved redistribution licensing remain in NOTICE.txt.

No checkout or build tool is needed to execute these prepared artifacts:

```sh
python3 -I /path/to/extracted/run.py --help
python3 -I /path/to/extracted/run.py init --backend qemu --profile lemma-silicon-dev/0.3.0 --disk /outside/package/new.raw
python3 -I /path/to/extracted/run.py session --backend rtl --profile lemma-silicon-dev/0.3.0 --disk /outside/package/new.raw --session-dir /outside/package/live --mode developer --paused --headless
python3 -I /path/to/extracted/run.py session-control --session-dir /outside/package/live --request '{"action":"run","cycles":1000000}'
python3 -I /path/to/extracted/run.py snapshot --session-dir /outside/package/live --to /outside/package/cut
python3 -I /path/to/extracted/run.py course-install --session-dir /outside/package/live --package /outside/package/course.lcp --transaction 1
```

Session/init creates a persistent sibling .bundle directory and .relocation.json
receipt. Keep them with the session. Only source lookup locations are aliased;
original consumed versions, image/runtime bytes, profiles and admission checks
are preserved. The original prepared bundle remains immutable. Session-control,
snapshot, restore, replay, raw button and course commands use the same maintained
host front end and guest permissions. Supported commands forward ordinary CLI
arguments; run COMMAND --help for details. No compile/build command is provided.
Course commands select the exact RTL guest path or a negotiated canonical fast
raw UART1 bundle. Pause a Developer/Laboratory session first. Admission is not
Installed/Saved; only the actual guest receipt after its backing barrier counts.

Restoring a checkpoint creates a private continuation, not cold recovery. For a
new restored session omit --disk and supply --restore /path/to/cut. Guest Saved
still requires its real backing barrier. Keep user media and sessions outside
the immutable package, back up raw media, and close owners before copying them.
ELF preload is development boot. Product ROM/update/authentication, complete
digital support, fast timing/cached-state parity, universal native installation
and physical qualification remain separate obligations.
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qemu_output_for_launcher(outputs, launcher_sha256, store_root=Path('/nix/store')):
    """Select one exact launcher in the bounded declared output set."""
    if not 1 <= len(outputs) <= 8 or len(set(outputs)) != len(outputs):
        raise ValueError('Invalid QEMU output set')
    matches = []
    for name in outputs:
        path = Path(name)
        if path.parent != store_root:
            raise ValueError('Invalid QEMU output store path')
        candidate = path / 'bin/qemu-system-riscv64'
        if candidate.is_file() and sha(candidate) == launcher_sha256:
            matches.append(path)
    if len(matches) != 1:
        raise ValueError('Exact QEMU launcher lacks a unique original output')
    return matches[0]


def qemu_launch_root(bundle, manifest, tool):
    """Resolve the copied launcher through its original, hash-bound derivation.

    Nix makeCWrapper is itself a small ELF. Its ldd set does not include the
    executable it starts, GUI modules, schemas or other referenced runtime data.
    Export the original output's complete registered closure instead of treating
    the wrapper's loader as the full QEMU runtime.
    """
    backend = manifest['backends']['qemu']
    launcher = bundle / backend['qemu']['path']
    derivation = bundle / backend['derivation']['path']
    if (sha(launcher) != backend['qemu']['sha256'] or
            sha(derivation) != backend['derivation']['sha256'] or
            not re.fullmatch(r'[0-9a-z]{32}-[^/]+\.drv', derivation.name)):
        raise ValueError('QEMU launcher/derivation identity differs')
    original = Path('/nix/store') / derivation.name
    if not original.is_file() or sha(original) != sha(derivation):
        raise ValueError('Original QEMU derivation is unavailable or changed')
    query = subprocess.run([tool, '--query', '--outputs', str(original)],
                           capture_output=True, timeout=30, check=True)
    if len(query.stdout) > 65536 or query.stderr:
        raise ValueError('Unexpected QEMU derivation output query')
    outputs = query.stdout.decode().splitlines()
    selected = qemu_output_for_launcher(outputs, sha(launcher))
    return str(selected), {
        'launcher_sha256': sha(launcher),
        'derivation': str(original), 'derivation_sha256': sha(derivation),
        'output': str(selected),
        'scope': 'Complete registered runtime output, including wrapped executable and data; not wrapper-only ldd',
    }


def runtime_export(bundle, output):
    """Export only the existing host runtime's complete Nix store closure."""
    manifest = json.loads((bundle / 'bundle.json').read_text())
    dependencies = {}
    for backend in ('rtl', 'qemu'):
        dependencies.update(manifest['host_dependencies'][backend])
    roots = set()
    for name, digest in dependencies.items():
        path = Path(name)
        if path.parts[:3] != ('/', 'nix', 'store') or len(path.parts) < 5 or sha(path) != digest:
            raise ValueError('Host runtime dependency differs')
        roots.add(str(Path(*path.parts[:4])))
    tool = shutil.which('nix-store')
    if tool is None:
        raise ValueError('Nix store export requested but nix-store is unavailable')
    # Nix selects nix-store's CLI through argv[0]; resolving its multicall
    # symlink to `nix` changes the command rather than merely its location.
    tool = str(Path(tool).absolute())
    qemu_root, launch_closure = qemu_launch_root(bundle, manifest, tool)
    roots.add(qemu_root)
    query = subprocess.run([tool, '--query', '--requisites', *sorted(roots)],
                           capture_output=True, timeout=60, check=True)
    if len(query.stdout) > 65536 or query.stderr:
        raise ValueError('Unexpected Nix closure query output')
    paths = sorted(set(query.stdout.decode().splitlines()))
    if not roots <= set(paths) or not 1 <= len(paths) <= 256:
        raise ValueError('Incomplete or excessive runtime closure')
    total = 0
    for name in paths:
        path = Path(name)
        if path.parts[:3] != ('/', 'nix', 'store') or len(path.parts) != 4 or not path.exists():
            raise ValueError('Invalid runtime closure store path')
        for directory, _, files in os.walk(path, followlinks=False):
            total += sum(p.stat().st_size for entry in files if not (p := Path(directory) / entry).is_symlink())
        if total > 512 << 20:
            raise ValueError('Runtime export exceeds512MiB source bound')
    destination = output / 'runtime-closure.nar'
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE, (512 << 20, 512 << 20))
    with destination.open('xb') as stream:
        exported = subprocess.run([tool, '--export', *paths], stdout=stream,
                                  stderr=subprocess.PIPE, timeout=180, preexec_fn=limits)
    if exported.returncode or not 0 < destination.stat().st_size <= 512 << 20:
        raise ValueError('Actual bounded Nix runtime export failed: ' + exported.stderr.decode(errors='replace')[:4096])
    return {'format': 'nix-store-export', 'path': destination.name,
            'sha256': sha(destination), 'bytes': destination.stat().st_size,
            'store_roots': sorted(roots), 'complete_requisites': paths,
            'qemu_launch_closure': launch_closure,
            'dependency_files': dependencies, 'tool': {'path': tool, 'binary': str(Path(tool).resolve()), 'sha256': sha(tool)},
            'scope': 'Existing host runtime files only; no import, download, trust change or guest runtime linkage'}


def package(bundle, output, archive=None, include_nix_runtime=False, current_host_tools=False):
    bundle, output = Path(bundle).absolute(), Path(output).absolute()
    if output.exists() or output.is_relative_to(bundle) or any(p.is_symlink() for p in output.parents):
        raise ValueError('Unused non-symlinked output outside the source bundle required')
    if archive is not None:
        archive = Path(archive).absolute()
        if (archive.exists() or archive.is_relative_to(output) or archive.is_relative_to(bundle)
                or any(p.is_symlink() for p in archive.parents)):
            raise ValueError('Unused archive outside the source/output required')
    started = time.monotonic()
    for backend in ('rtl', 'qemu'):
        for role in ('notebook', 'initializer'):
            prepared(bundle, backend, role, 'lemma-silicon-dev/0.3.0')
    output.mkdir(parents=True)
    shutil.copytree(bundle, output / 'bundle')
    # Start with the exact compiled-source archive, then add host transport/
    # presentation tools. An overlap may never silently change a consumed input.
    shutil.copytree(bundle / 'source', output / 'host')
    inputs, host_differences = {}, {}
    selected = [p for p in (ROOT / 'scripts').rglob('*')
                if p.is_file() and (p.suffix == '.py' or p.name in ('lemmasim', 'lemmasim-course'))]
    selected += list((ROOT / 'conformance/lemmasim').rglob('*.py'))
    selected += list((ROOT / 'sim/profiles').glob('*.json'))
    for source in sorted(set(selected)):
        if source.is_symlink():
            raise ValueError('Symlinked host tool source')
        relative = source.relative_to(ROOT).as_posix()
        destination = output / 'host' / relative
        digest = sha(source)
        if destination.exists() and sha(destination) != digest:
            if not current_host_tools:
                raise ValueError('Current host tool contradicts the compiled archive: ' + relative)
            # The compiled closure remains immutable in bundle/source. Only
            # the separately inventoried host launcher receives current code.
            archived = output / 'bundle/source' / relative
            old_digest = sha(destination)
            if not archived.is_file() or sha(archived) != old_digest:
                raise ValueError('Host replacement lacks the exact retained compiled source: ' + relative)
            host_differences[relative] = {'compiled_source': 'bundle/source/' + relative,
                                        'compiled_sha256': old_digest, 'host_sha256': digest}
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if sha(destination) != digest:
            raise ValueError('Host source changed during copy')
        inputs[relative] = digest
    launcher = ROOT / 'sim/native/run_local.py'
    shutil.copyfile(launcher, output / 'run.py')
    inputs['sim/native/run_local.py'] = sha(launcher)
    runtime = runtime_export(bundle, output) if include_nix_runtime else None
    readme = README
    if runtime is not None:
        readme = readme.replace('They are not included or downloaded.',
            'The complete existing runtime closure is included in runtime-closure.nar.\n'
            'On a compatible Nix host, import it explicitly if needed:\n'
            '`nix-store --import < /path/to/extracted/runtime-closure.nar`.\n'
            'The launcher never imports or downloads automatically. Normal Nix import\n'
            'permissions are required; no trust settings or signatures are added.')
    if host_differences:
        readme += ('\nThis package explicitly selects current host launch tools. package.json\n'
                   'records every difference from the original compiled source closure.\n'
                   'The exact compiled versions remain in bundle/source; host/ is a\n'
                   'separate launch environment. No target compilation or runtime changes.\n')
    (output / 'README.md').write_text(readme)
    (output / 'NOTICE.txt').write_text((bundle / 'DEPENDENCIES.txt').read_text() +
        ('\nThe included Nix export preserves the original host runtime closure and notices.' if runtime else
         '\nExact host Nix libraries remain external.') +
        ' This local archive grants no new redistribution license.\n')
    files = {p.relative_to(output).as_posix(): {'sha256': sha(p), 'bytes': p.stat().st_size}
             for p in sorted(output.rglob('*')) if p.is_file()}
    if len(files) > 8192 or sum(row['bytes'] for row in files.values()) > 2 << 30:
        raise ValueError('Native package exceeds declared file/byte bound')
    manifest = {'schema': 'lemma-local-native-distribution/3' if host_differences else 'lemma-local-native-distribution/2',
                'scope': 'Prepared canonical machine, extracted host front end and exact source-location aliases; external Nix libraries required',
                'source_bundle_sha256': sha(bundle / 'bundle.json'),
                'producer_sha256': sha(Path(__file__)), 'host_inputs': inputs, 'files': files}
    if host_differences:
        manifest['host_tool_versions'] = {'schema': 'lemma-native-host-tool-versions/1',
            'scope': 'Current host launcher only; every original compiled source remains in the immutable bundle',
            'differences': host_differences}
    if runtime is not None:
        manifest['host_runtime_archive'] = runtime
    (output / 'package.json').write_text(json.dumps(manifest, indent=2) + '\n')
    # A relocated interpreter executes the actual ordinary four-way admission.
    with tempfile.TemporaryDirectory(prefix='lemma-native-package-check-') as directory:
        command = [sys.executable, '-I', str(output / 'run.py'), '--verify-only', '--view-dir', str(Path(directory) / 'view')]
        observed = subprocess.run(command, cwd=directory, capture_output=True, timeout=180)
        if observed.returncode or observed.stdout != b'PASS_NATIVE_DISTRIBUTION_BOTH_BACKENDS_AND_GUESTS_NO_CPU\n' or observed.stderr:
            raise ValueError('Relocated admission failed: ' + observed.stderr.decode(errors='replace')[:8192])
    if any(sha(ROOT / name) != digest for name, digest in inputs.items()):
        raise ValueError('Consumed host tool changed during preparation')
    result = {'status': 'PASS_PREPARED_EXTRACTED_NATIVE_DISTRIBUTION_NO_CPU',
              'directory': str(output), 'manifest_sha256': sha(output / 'package.json'),
              'source_bundle_sha256': manifest['source_bundle_sha256'],
              'files': len(files), 'bytes': sum(row['bytes'] for row in files.values()),
              'ordinary_both_backend_both_guest_admission': True,
              'host_dependencies': 'Exact external Nix files retained as prerequisites',
              'guest_execution': 'NOT_EXERCISED_BY_PACKAGING'}
    if runtime is not None:
        result['host_runtime_archive'] = runtime
    if archive is not None:
        archive.parent.mkdir(parents=True, exist_ok=True)
        with archive.open('xb') as stream, gzip.GzipFile(fileobj=stream, mode='wb', filename='', mtime=0) as compressed, tarfile.open(fileobj=compressed, mode='w') as tar:
            for name in sorted([*files, 'package.json']):
                path = output / name
                info = tarfile.TarInfo('lemmasim-native/' + name)
                info.size = path.stat().st_size
                info.mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
                with path.open('rb') as source:
                    tar.addfile(info, source)
        result['archive'] = {'path': str(archive), 'sha256': sha(archive), 'bytes': archive.stat().st_size}
    result['seconds'] = time.monotonic() - started
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--include-nix-runtime', action='store_true',
                        help='Include a bounded offline export of the exact existing Nix host-library closure')
    parser.add_argument('--current-host-tools', action='store_true',
                        help='Separately retain/version current host launch tools and every overlapping original compiled source')
    args = parser.parse_args()
    try:
        print(json.dumps(package(args.bundle, args.output_dir, args.archive, args.include_nix_runtime,
                                 args.current_host_tools), indent=2))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, 'Native packaging failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
