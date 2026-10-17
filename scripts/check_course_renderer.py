#!/usr/bin/env python3
"""Bounded genuine Lean course renderer compatibility and LLVM/RV64 closure.

The host pixel observer compares the original scalar glyph function. Component object
inspection does not claim a linked or executed guest; use the independently
audited notebook workload for that qualification.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import time

from build_core0 import LLC_ARGUMENTS
from core0_common import Core0Error, run_bounded, sha256

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    if not 30 <= args.timeout <= 600:
        raise Core0Error('Course renderer component timeout must be30..600seconds')
    out = args.work_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'lemma-course-packed-render-component/1', 'status': 'RUNNING',
              'scope': __doc__, 'bounds': {'per_command_seconds': args.timeout}}
    inputs = [ROOT/'Lemma/Courses/Arithmetic.lean', ROOT/'tests/course/PackedRender.lean',
              Path(__file__).resolve(), ROOT/'flake.lock', ROOT/'lean-toolchain']
    report['inputs'] = {str(p.relative_to(ROOT)): sha256(p) for p in inputs}
    report['source_commit'] = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
    report['dirty_paths'] = subprocess.check_output(['git','status','--porcelain'], cwd=ROOT, text=True).splitlines()
    started = time.monotonic()

    def run(argv, log, env=None):
        result = run_bounded(argv, cwd=ROOT, timeout_seconds=args.timeout, env=env)
        (out/log).write_bytes(result.stdout + result.stderr)
        report.setdefault('commands', []).append({'argv': list(map(str,argv)), 'exit': result.returncode,
            'host_seconds': result.elapsed_seconds, 'log': log})
        if result.returncode:
            raise Core0Error('Course renderer command failed: ' + log)
        return result.stdout.decode()

    try:
        report['tools'] = {t: run([t,'--version'],t+'.version.log').strip()
                           for t in ('lean','lake','opt','llc','llvm-nm','llvm-readelf')}
        if ('4.34.1' not in report['tools']['lean'] or
                '20.1.8' not in report['tools']['opt'] or '20.1.8' not in report['tools']['llc']):
            raise Core0Error('Course renderer component needs the pinned Lean/LLVM tools')
        env = dict(os.environ, LEMMA_COURSE_RENDER_OUT=str(out/'export'))
        # Build and elaboration consume the same shared Olean tree as whole
        # guest exporters. Keep both under the established repository lock.
        (ROOT/'build').mkdir(exist_ok=True)
        with (ROOT/'build/task006-lake.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            run(['lake','build','Lemma.Courses.Arithmetic'],'build.log')
            observed = run(['lake','env','lean','--run','tests/course/PackedRender.lean'],'host.log',env)
        if ('COURSE_PACKED_RENDER:PASS 92160 words,1474560 exact scalar pixels,5 invalid geometries' not in observed or
                'COURSE_RENDER_GENUINE_LLVM:12:9:21' not in observed):
            raise Core0Error('Missing independent semantics or actual elaboration observations')
        symbols = (out/'export/symbols.txt').read_text().splitlines()
        matches = [re.fullmatch(r'source=(.+);llvm=(\w+)',row) for row in symbols]
        if len(matches) != 21 or any(m is None for m in matches):
            raise Core0Error('Genuine source symbol closure differs')
        names = {m[2] for m in matches}
        if len(names) != 21:
            raise Core0Error('Duplicate source symbol')
        llvm = (out/'export/program.ll').read_text()
        definitions = set(re.findall(r'^define[^\n]*@(\w+)\(',llvm,re.M))
        calls = set(re.findall(r'\bcall[^@\n]*@(\w+)\(',llvm))
        if definitions != names or not calls <= names or re.search(r'^declare\b',llvm,re.M):
            raise Core0Error('Course renderer acquired unknown target functions/runtime')
        run(['opt','-passes=default<O2>','-S',str(out/'export/program.ll'),'-o',str(out/'program.opt.ll')],'opt.log')
        run(['llc',*LLC_ARGUMENTS,'-O2',str(out/'program.opt.ll'),'-o',str(out/'program.o')],'llc.log')
        undefined = run(['llvm-nm','--undefined-only',str(out/'program.o')],'undefined.log')
        attributes = run(['llvm-readelf','--file-header','--arch-specific',str(out/'program.o')],'attributes.log')
        if undefined.strip() or 'RISC-V' not in attributes or 'rv64i2p1_m2p0' not in attributes:
            raise Core0Error('Course renderer object acquired unknown helper/ISA')
        defined = run(['llvm-nm','--defined-only','--extern-only','--format=posix',str(out/'program.o')],'defined.log')
        if {line.split()[0] for line in defined.splitlines()} != names:
            raise Core0Error('RV64 object lost source provenance')
        if {str(p.relative_to(ROOT)):sha256(p) for p in inputs} != report['inputs']:
            raise Core0Error('Course renderer inputs changed during qualification')
        report.update(status='PASS_GENUINE_COMPONENT', exact_word_cases=92160, exact_scalar_pixels=1474560,
            invalid_geometries=5, source_functions=21,
            glyph_lookups_per_word=2, historical_glyph_lookups_per_word=16,
            target_execution='NOT_RUN_BY_COMPONENT_CHECK', linked_image='NONE')
    except (Core0Error,OSError,ValueError) as error:
        report.update(status='FAIL',error=str(error))
    report['host_seconds'] = time.monotonic()-started
    report['artifacts'] = {str(p.relative_to(out)):{'bytes':p.stat().st_size,'sha256':sha256(p)}
                           for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'])
    return 0 if report['status'] == 'PASS_GENUINE_COMPONENT' else 1


if __name__ == '__main__':
    raise SystemExit(main())
