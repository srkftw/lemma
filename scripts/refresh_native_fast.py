#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Package the current validated fast runtime with an unchanged native guest pair.

The base supplies the complete audited guest/RTL closure. The ordinary fast
preparation supplies a newly built runtime and its actual source/host-library
closure. Both guest roles must match byte for byte before any output is made.
This creates a new immutable development bundle, never edits the base and never
executes target instructions or changes user media.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil

import lemmasim_fast as fast
from silicon_guest import ROOT, sha
from silicon_guest_bundle import (SCHEMA_WITH_SOFTWARE_DEPLOYMENT, host_dependencies,
                                  inventory, prepared, read_json)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def refresh(base, output, expected_fast):
    base, output = base.resolve(), output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT/'build'), 'unused task-owned output required')
    manifest = read_json(base/'bundle.json')
    require(manifest.get('schema') == SCHEMA_WITH_SOFTWARE_DEPLOYMENT and
            manifest.get('profile') == 'lemma-silicon-dev/0.3.0', 'require canonical versioned guest deployment')
    base_sha = sha(base/'bundle.json')
    profile = manifest['profile']
    sealed = {}
    for role in ('notebook', 'initializer'):
        prepared(base, 'rtl', role, profile)
        archived = prepared(base, 'qemu', role, profile)
        current = fast.prepared(role, profile)
        require(current['qemu']['sha256'] == expected_fast, 'unexpected prepared fast binary')
        old = {k: v['sha256'] for k, v in archived['workloads'][role].items()}
        new = {k: v['sha256'] for k, v in current['workloads'][role].items()}
        require(old == new, 'fast preparation changes the audited '+role+' guest closure')
        sealed[role] = current
    require(sealed['notebook'] == sealed['initializer'], 'fast roles use different runtime preparations')
    current = sealed['notebook']
    preparation = fast.prepared_path(profile)
    preparation_sha = sha(preparation)
    result = copy.deepcopy(manifest)
    output.mkdir(parents=True)
    for name in manifest['files']:
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base/name, target)
        target.chmod(0o755 if manifest['files'][name]['executable'] else 0o644)

    def add(source, destination, expected, executable=False):
        source = Path(source).resolve()
        require(sha(source) == expected, 'consumed refresh input changed: '+str(source))
        target = output/destination
        if target.exists():
            require(sha(target) == expected, 'conflicting refresh archive destination')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(0o755 if executable else 0o644)
        require(sha(target) == expected and sha(source) == expected, 'input changed during refresh copy')
        result['origins'].setdefault(str(source), {})[expected] = destination
        return {'path': destination, 'sha256': expected}

    for name, digest in current['sources'].items():
        add(ROOT/name, 'backend-sources/'+digest, digest)
    backend = copy.deepcopy(current)
    backend['workloads'] = copy.deepcopy(manifest['backends']['qemu']['workloads'])
    for key in ('qemu', 'derivation'):
        item = current[key]
        backend[key] = add(item['path'], 'runtime/qemu/'+item['sha256']+'/'+Path(item['path']).name,
                           item['sha256'], key == 'qemu')
    result['backends']['qemu'] = backend
    result['host_dependencies']['qemu'] = host_dependencies(current['qemu']['path'])
    source_record = add(preparation, 'backend-manifests/'+preparation_sha+'.json', preparation_sha)
    result['runtime_refresh'] = {'schema': 'lemma-native-fast-refresh/1',
        'base_manifest_sha256': base_sha, 'fast_preparation': source_record,
        'scope': 'new validated host runtime; exact unchanged audited guest pair and RTL; no new guest compilation or execution'}
    notice = output/'DEPENDENCIES.txt'
    notice.write_text(notice.read_text()+'Fast-runtime refresh preserves the original dependency notices; exact new QEMU sources, derivation and external Nix libraries are recorded in bundle.json. Archived fast preparation is provenance, not a runtime dependency on its original guest-archive path.\n')
    result['files'] = {str(p.relative_to(output)): {'sha256': sha(p), 'bytes': p.stat().st_size,
                       'executable': os.access(p, os.X_OK)}
                       for p in sorted(output.rglob('*')) if p.is_file()}
    require(sha(base/'bundle.json') == base_sha, 'base manifest changed during refresh')
    inventory(base, manifest)
    require(sha(preparation) == preparation_sha and all(fast.prepared(role, profile) == sealed[role]
            for role in sealed), 'prepared fast closure changed during refresh')
    (output/'bundle.json').write_text(json.dumps(result, indent=2)+'\n')
    for backend_name in ('rtl', 'qemu'):
        for role in ('notebook', 'initializer'):
            prepared(output, backend_name, role, profile)
    return output/'bundle.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-bundle', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--expected-fast-sha256', required=True)
    args = parser.parse_args()
    print(refresh(args.base_bundle, args.output_dir, args.expected_fast_sha256))


if __name__ == '__main__':
    main()
