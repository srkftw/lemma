#!/usr/bin/env python3
"""Archive an audited USB guest's complete consumed source bytes for reuse.

Copies build inputs only. Never installs software into a running device or
interprets/reconstructs user documents. Existing outputs fail closed.
"""
import argparse
import json
from pathlib import Path
import shutil
import time
from build_kernel import source_inputs
from silicon_guest import guest_source_archive, sha, identified
from silicon_profile import configuration_profile

ROOT = Path(__file__).resolve().parents[1]


def archive(build, source_root, output):
    build, source_root, output = (Path(p).resolve() for p in (build, source_root, output))
    if output.exists(): raise ValueError('use an unused source archive output')
    provenance = json.loads((build / 'provenance.json').read_text())
    metadata = json.loads((build / 'build.json').read_text())
    audit = json.loads((build / 'audit.json').read_text())
    expected = provenance.get('source_inputs')
    if (audit.get('status') != 'PASS' or not isinstance(expected, dict) or not expected or
            source_inputs(source_root) != expected):
        raise ValueError('complete original source inventory or successful audit differs')
    output.mkdir(parents=True)
    started = time.monotonic(); report = {'status':'FAIL','scope':__doc__, 'packager':identified(__file__)}
    try:
        source = output / 'consumed-source-root'; source.mkdir()
        for name,digest in expected.items():
            path = Path(name)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise ValueError('escaping consumed source path')
            original = source_root / path
            if original.is_symlink() or sha(original) != digest:
                raise ValueError('changed or symlinked consumed input: ' + name)
            target = source / path; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            if sha(target) != digest: raise ValueError('copied input differs: ' + name)
        sidecar = {'schema':'lemma-usb-guest-source-archive/1', 'source_inputs':expected,
            **{key:provenance.get(key) for key in ('source_commit','dirty_paths','tools','lean_source_realization')},
            'provenance_sha256':sha(build/'provenance.json'), 'build_sha256':sha(build/'build.json'),
            'image_sha256':sha(build/'image.elf')}
        (output/'consumed-source-archive.json').write_text(json.dumps(sidecar,indent=2)+'\n')
        checked = guest_source_archive(build,source,metadata['configuration'],metadata['optimization'],
                                       configuration_profile(metadata['configuration']))
        report.update(status='PASS_COMPLETE_ORIGINAL_GUEST_SOURCE_ARCHIVE',inputs=len(expected),admission=checked)
    except BaseException as error:
        report['error']=repr(error)
        raise
    finally:
        report['seconds']=time.monotonic()-started
        (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return source


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--source-root',type=Path,default=ROOT)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    print(archive(args.build,args.source_root,args.output_dir))

if __name__=='__main__':main()
