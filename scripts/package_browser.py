#!/usr/bin/env python3
"""Pack an existing exact browser machine and its local launcher; no rebuild."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time

from lemmasim_browser import validated_bundle

ROOT = Path(__file__).resolve().parents[1]
NOTICE = '''Local prepared development distribution. No redistribution license is granted.
Project-wide redistribution licensing remains unresolved. Preserve the original
bundle/DEPENDENCIES.txt, source identities and upstream notices. RV64 guest
software is the audited Lean-authored image; Python and Wasm host runtimes do
not enter that image. The native build helper produced these images. This is
not a browser-local compiler or a production authenticated boot distribution.
Physical conformance, complete digital device support and full course/browser
acceptance are separate obligations. Packaging bytes establishes none of them.
'''
README = '''# Local LemmaSim browser machine

Python3.10 or later and a browser with WebAssembly and OPFS synchronous worker
access are required. Launch after extraction, from any working directory:

```sh
python3 /path/to/extracted/serve.py --verify-only
python3 /path/to/extracted/serve.py --port 8787
```

Open http://127.0.0.1:8787/ in your browser. The launcher binds loopback only,
serves the original inventoried machine files and needs no repository, Nix,
Lean, LLVM, network download or Python package installation. Verify-only checks
the distribution and the original complete browser bundle. Checksums detect
changed bytes; they do not authenticate a sender.

Create a new named medium through the real Lean guest initializer, or import
an exported raw medium under a new name and Open it for guest cold recovery.
Keep the same port: browser storage belongs to its origin. Save succeeds only
after the actual guest/backing barrier. OPFS flush does not guarantee physical
power-loss durability, retention against eviction or persistence in private
browsing. Export backing bytes regularly; beforeunload is not a save mechanism.

Student, Developer and Laboratory run the same RV64 guest and permissions.
Developer/Laboratory expose raw input, inspection, bounded runs, checkpoint
export/restore into private forks and offline outcome replay. Restoring a
checkpoint is continuation; Open from raw backing is cold recovery. A bounded
prefix or a packaging check is not Notebook Ready or complete course acceptance.
Changing machines while a selected file loads cancels that selection; choose it
again in the new machine. Import destinations and installation transactions
belong to the original selection, even if their fields are edited during loading.
Stop the server with Ctrl-C. The server does not send documents or other data
to a remote service. See NOTICE.txt and bundle/DEPENDENCIES.txt for limitations.
'''


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package(source, destination, archive=None):
    source, _ = validated_bundle(source)
    destination = Path(destination).absolute()
    if (destination.exists() or destination.is_relative_to(source)
            or any(p.is_symlink() for p in destination.parents)):
        raise ValueError('Unused non-symlinked output directory required')
    if archive is not None:
        archive = Path(archive).absolute()
        if (archive.exists() or archive.is_relative_to(destination) or archive.is_relative_to(source)
                or any(p.is_symlink() for p in archive.parents)):
            raise ValueError('Unused archive path outside distribution required')
    started = time.monotonic()
    source_manifest = digest(source / 'bundle.json')
    destination.mkdir(parents=True)
    shutil.copytree(source, destination / 'bundle', symlinks=False)
    (destination / 'tools').mkdir()
    inputs = {}
    for original, installed in [('scripts/lemmasim_browser.py', 'tools/lemmasim_browser.py'),
                                ('scripts/silicon_guest_bundle.py', 'tools/silicon_guest_bundle.py'),
                                ('scripts/usb_closure_recovery_deployment.py', 'tools/usb_closure_recovery_deployment.py'),
                                ('scripts/package_companion_deployment.py', 'tools/package_companion_deployment.py'),
                                ('scripts/package_entry2_deployment.py', 'tools/package_entry2_deployment.py'),
                                ('scripts/companion_reader_deployment.py', 'tools/companion_reader_deployment.py'),
                                ('scripts/chooser_reader_deployment.py', 'tools/chooser_reader_deployment.py'),
                                ('sim/browser/serve_local.py', 'serve.py')]:
        inputs[original] = digest(ROOT / original)
        shutil.copyfile(ROOT / original, destination / installed)
        if digest(destination / installed) != inputs[original]:
            raise ValueError('Launcher source changed during packaging')
    (destination / 'NOTICE.txt').write_text(NOTICE)
    (destination / 'README.md').write_text(README)
    validated_bundle(destination / 'bundle')
    if digest(destination / 'bundle/bundle.json') != source_manifest:
        raise ValueError('Original machine manifest changed')
    files = {p.relative_to(destination).as_posix(): {'sha256': digest(p), 'bytes': p.stat().st_size}
             for p in sorted(destination.rglob('*')) if p.is_file()}
    if sum(row['bytes'] for row in files.values()) > 1 << 30:
        raise ValueError('Distribution exceeds one GiB')
    manifest = {'schema': 'lemma-local-browser-distribution/1',
                'scope': 'Prepared exact machine and standalone local launch; no new guest acceptance claim',
                'source_bundle_sha256': source_manifest,
                'producer': {'path': 'scripts/package_browser.py', 'sha256': digest(Path(__file__))},
                'host_launcher_inputs': inputs, 'files': files}
    (destination / 'package.json').write_text(json.dumps(manifest, indent=2) + '\n')
    # Exercise the extracted entry point, not a producer-only observer.
    command = [os.sys.executable, '-I', str(destination / 'serve.py'), '--verify-only']
    observed = subprocess.run(command, cwd=destination.parent, capture_output=True, timeout=120)
    if observed.returncode:
        raise ValueError('Extracted launcher failed: ' + observed.stderr.decode(errors='replace')[:8192])
    if observed.stdout != b'PASS_LOCAL_BROWSER_DISTRIBUTION_BYTES\n' or observed.stderr:
        raise ValueError('Standalone launch verification differs')
    if any(digest(ROOT / name) != value for name, value in inputs.items()):
        raise ValueError('Consumed launcher source changed')
    result = {'status': 'PASS_PREPARED_LOCAL_BROWSER_DISTRIBUTION',
              'directory': str(destination), 'manifest_sha256': digest(destination / 'package.json'),
              'source_bundle_sha256': source_manifest, 'files': len(files),
              'bytes': sum(row['bytes'] for row in files.values()),
              'standalone_verification': observed.stdout.decode().strip()}
    if archive is not None:
        archive.parent.mkdir(parents=True, exist_ok=True)
        # Only relative, verified regular files enter the archive. Fixed tar
        # metadata avoids host usernames, modes and timestamps in extraction.
        with archive.open('xb') as stream, gzip.GzipFile(fileobj=stream, mode='wb',
                filename='', mtime=0) as compressed, tarfile.open(fileobj=compressed, mode='w') as tar:
            for name in sorted([*files, 'package.json']):
                path = destination / name
                info = tarfile.TarInfo('lemmasim-browser/' + name)
                info.size = path.stat().st_size
                info.mode = 0o644
                with path.open('rb') as data:
                    tar.addfile(info, data)
        result['archive'] = {'path': str(archive), 'sha256': digest(archive),
                             'bytes': archive.stat().st_size}
    result['seconds'] = time.monotonic() - started
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(package(args.bundle, args.output_dir, args.archive), indent=2))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, 'Browser packaging failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
