"""Pinned three-file Nix input for a relocated guest capacity audit.

Never realize an ignored machine/source/media directory as a flake. Only the
original target build's exact toolchain pins enter the realization input.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil

from kernel_source_workspace import FILES, validate_flake_input


def command(root, directory, build, guest_build, output):
    directory = Path(directory).absolute()
    if any(path.is_symlink() for path in (directory, *directory.parents)):
        raise ValueError('Symlinked capacity toolchain directory')
    root, directory = Path(root).resolve(), directory.resolve()
    provenance = Path(guest_build).resolve() / 'provenance.json'
    if provenance.is_symlink() or not provenance.is_file() or provenance.stat().st_size > 16 << 20:
        raise ValueError('Bounded original guest provenance required')
    raw = provenance.read_bytes()
    if hashlib.sha256(raw).hexdigest() != build.get('provenance_sha256'):
        raise ValueError('Capacity toolchain guest provenance differs from its audited build')
    sources = json.loads(raw).get('source_inputs', {})
    pins = {name: sources.get(name) for name in FILES}
    for name, digest in pins.items():
        path = root / name
        if (not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None or
                path.is_symlink() or not path.is_file() or
                hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError('Capacity toolchain differs from the audited target build: ' + name)
    flake = directory / 'guest-capacity-toolchain'
    if flake.exists() or directory.is_symlink():
        raise ValueError('Unused private capacity toolchain directory required')
    flake.mkdir()
    for name in FILES:
        target = flake / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    size = validate_flake_input(flake, pins)
    argv = ['nix', 'develop', 'path:' + str(flake), '--no-write-lock-file', '--command', 'python3',
            str(root / 'scripts/audit_lemmasim_capacity.py'), '--build', str(Path(guest_build).resolve()),
            '--output', str(Path(output).resolve())]
    receipt = {'contract': 'lemma-capacity-toolchain-workspace/1', 'input_sha256': pins,
               'input_bytes': size, 'exactly_three_input_files': True, 'argv': argv,
               'scope': 'Pinned host-tool realization input only; actual capacity audit must still pass'}
    with (directory / 'guest-capacity-toolchain.json').open('x') as stream:
        stream.write(json.dumps(receipt, indent=2) + '\n')
    return argv
