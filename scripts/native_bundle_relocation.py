"""Add exact archived source-location aliases for a relocated native launcher.

Only provenance lookup locations change. Every original origin/version remains,
and ordinary bundle/guest/runtime admission still runs before execution.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil


def relocated_manifest(original, host_root):
    if (original.get('schema') not in ('lemmasim-native-bundle/2', 'lemmasim-native-bundle/3')
            or original.get('profile') != 'lemma-silicon-dev/0.3.0'):
        raise ValueError('Relocation currently requires canonical native bundle2/3')
    host_root = Path(host_root).absolute()
    if any(p.is_symlink() for p in (host_root, *host_root.parents)):
        raise ValueError('Symlinked host source location')
    origins, files = original.get('origins'), original.get('files')
    if not isinstance(origins, dict) or not origins or not isinstance(files, dict):
        raise ValueError('Missing original versioned origins')
    relatives = set(original.get('sources', {}))
    relatives.update(original.get('backends', {}).get('qemu', {}).get('sources', {}))
    if not relatives:
        raise ValueError('Missing source suffix inventory')
    result, aliases = copy.deepcopy(original), {}
    for relative in sorted(relatives):
        rel = Path(relative)
        if rel.is_absolute() or not relative or any(p in ('.', '..', '') for p in relative.split('/')):
            raise ValueError('Invalid source suffix')
        versions = {}
        for old, entries in origins.items():
            if not isinstance(old, str) or not Path(old).is_absolute() or not isinstance(entries, dict):
                raise ValueError('Malformed original versioned location')
            if Path(old).parts[-len(rel.parts):] != rel.parts:
                continue
            for digest, destination in entries.items():
                if not isinstance(destination, str) or files.get(destination, {}).get('sha256') != digest:
                    raise ValueError('Source alias lacks an original inventoried version')
                # Multiple copies of identical bytes may have different archive
                # paths. The exact digest selects the version in either case.
                versions[digest] = min(destination, versions.get(digest, destination))
        if not versions:
            raise ValueError('No original archived source suffix: ' + relative)
        location = str(host_root / rel)
        old = result['origins'].get(location, {})
        if not isinstance(old, dict) or any(h in old and old[h] != p for h, p in versions.items()):
            raise ValueError('Relocated origin conflicts with an original location')
        result['origins'][location] = {**old, **versions}
        aliases[location] = versions
    # Do not change binaries, source inventories, software contracts or any
    # original consumed location. This is not checkpoint/state migration.
    if any(result[key] != value for key, value in original.items() if key != 'origins'):
        raise ValueError('Relocation changed non-location metadata')
    if any(result['origins'][key] != value for key, value in origins.items()):
        raise ValueError('Relocation changed an original consumed version')
    return result, aliases


def create_view(bundle, destination, host_root):
    from silicon_guest_bundle import inventory, prepared, read_json
    bundle, destination = Path(bundle).absolute(), Path(destination).absolute()
    original = read_json(bundle / 'bundle.json')
    inventory(bundle, original)
    changed, aliases = relocated_manifest(original, host_root)
    if destination.exists() or destination.is_relative_to(bundle):
        raise ValueError('Unused view outside the original package required')
    if any(p.is_symlink() for p in destination.parents):
        raise ValueError('Symlinked native view destination')
    shutil.copytree(bundle, destination)
    (destination / 'bundle.json').write_text(json.dumps(changed, indent=2) + '\n')
    # Both backends and both guest roles pass the existing full preparation
    # checks. No corrected observer bypasses a failed original check.
    for backend in ('rtl', 'qemu'):
        for role in ('notebook', 'initializer'):
            prepared(destination, backend, role, original['profile'])
    digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    receipt = {'schema': 'lemma-native-source-location-alias/1', 'status': 'PASS',
               'original_manifest_sha256': digest(bundle / 'bundle.json'),
               'view_manifest_sha256': digest(destination / 'bundle.json'),
               'host_root': str(Path(host_root).absolute()), 'aliases': aliases,
               'all_original_origins_and_non_location_fields_unchanged': True,
               'ordinary_both_backend_both_guest_admission': True}
    destination.with_name(destination.name + '.relocation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt
