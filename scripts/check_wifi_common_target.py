#!/usr/bin/env python3
"""Capture a genuine Kernel8 whole image and its ordinary full artifact audit.

This host wrapper keeps the complete before/after source inventory and copies
its exact bytes. It uses the existing Lean/LLVM builder and auditor unchanged.
No CPU, device transaction or compiler correctness proof follows from this run.
"""
from __future__ import annotations

import argparse
import fcntl
import shutil
import time
from pathlib import Path

from audit_kernel import audit
from build_kernel import build, source_inputs
from core0_common import sha256, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.work_dir.resolve()
    if not out.is_relative_to(root / 'build/kernel') or out.exists():
        parser.error('an unused build/kernel subdirectory is required')
    out.mkdir()
    shutil.copyfile(__file__, out / 'runner.py')
    started = time.monotonic()
    result = {'status': 'FAIL', 'scope': 'genuine complete Kernel8 build/ordinary full artifact audit; CPU NOT_RUN',
              'command_timeout_seconds': 300, 'observer_sha256': sha256(out / 'runner.py')}
    try:
        with (root / 'build/task006-lake.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            before = source_inputs(root)
            if not before:
                raise RuntimeError('empty consumed-source corpus')
            archive = out / 'consumed-source-root'
            archive.mkdir()
            for name, digest in before.items():
                relative = Path(name)
                if relative.is_absolute() or '..' in relative.parts:
                    raise RuntimeError('source path escapes its archive owner')
                source = root / relative
                if sha256(source) != digest:
                    raise RuntimeError('source moved before capture: ' + name)
                destination = archive / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            result['source_inputs'] = before
            write_json(out / 'source-inputs.json', before)
            build(root=root, output_dir=out / 'target', opt_level='O2', stage='supervisor',
                  configuration='lemmasim-silicon-wifi-common-probe', timeout_seconds=300)
            result['build'] = 'PASS'
            result['build_seconds'] = time.monotonic() - started
            audit(root=root, output_dir=out / 'target', timeout_seconds=300)
            if source_inputs(root) != before:
                raise RuntimeError('source inputs moved during whole build/audit')
            result.update(status='PASS_WHOLE_AUDIT_ONLY', source_count=len(before),
                          elf_sha256=sha256(out / 'target/image.elf'),
                          build_sha256=sha256(out / 'target/build.json'),
                          audit_sha256=sha256(out / 'target/audit.json'))
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        result['wall_seconds'] = time.monotonic() - started
        write_json(out / 'result.json', result)
    print(result['status'], result['wall_seconds'])


if __name__ == '__main__':
    main()
