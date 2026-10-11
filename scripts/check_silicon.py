#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Short RTL acceptance. Literal bus checks are separate from guest execution.

Uses immutable prepared tools and records observed process results; no timeout
or missing corpus can become a success. Existing failed directories are retained.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def command(argv, log, seconds):
    started = time.monotonic()
    with log.open('wb') as output:
        process = subprocess.Popen(argv, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=seconds)
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
            raise
    record = {'argv': argv, 'exit_code': code, 'seconds': time.monotonic()-started,
              'log': str(log.relative_to(ROOT)), 'log_sha256': sha(log)}
    if code:
        print(log.read_text(errors='replace')[-6000:], file=sys.stderr)
        raise RuntimeError(f'command failed {code}; retained {log}')
    return record

def devices(out, timeout, jobs):
    source_names = ['sim/rtl/lemma_pen.sv','sim/rtl/lemma_paper.sv','sim/rtl/lemma_block.sv','sim/rtl/lemma_register_ram.sv',
                    'conformance/silicon/Devices.sv','scripts/check_silicon.py',
                    'tooling/silicon/sim.nix','flake.lock']
    before = {p: sha(ROOT/p) for p in source_names}
    obj = out/'obj';obj.mkdir()
    build = ['verilator','--binary','--timing','-j',str(jobs),'-Wno-fatal','--top-module','Devices',
             '--Mdir',str(obj),*(str(ROOT/p) for p in source_names if p.endswith('.sv'))]
    records = [command(['nix-shell',str(ROOT/'tooling/silicon/sim.nix'),'--run',shlex.join(build)],
                       out/'build.log',timeout)]
    records.append(command([str(obj/'VDevices')],out/'simulation.log',30))
    text = (out/'simulation.log').read_text()
    expected = ['PEN stable-head overflow exact-ack resync watchdog reset PASS',
                'PAPER latch Busy invalid-command bounds interrupted-reset PASS',
                'BLOCK descriptors DMA payload used-ring flush error bounds reset PASS',
                'RAM 4096-byte register implementation distinct sparse windows strobes faults PASS']
    if any(text.count(marker)!=1 for marker in expected):
        raise RuntimeError('Missing or duplicate independent device observations')
    if before != {p: sha(ROOT/p) for p in source_names}:
        raise RuntimeError('RTL/device inputs changed during observation')
    return {'status':'PASS','source_inputs':before,'commands':records,
            'scope':'literal external MMIO/DMA stimuli on real RTL; not guest acceptance C or notebook durability',
            'observations':expected}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lane',choices=['devices','monitor','monitor-input','initializer','notebook','cold','failed-flush','input'],required=True)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--timeout',type=float,default=300)
    parser.add_argument('--jobs',type=int,default=2)
    parser.add_argument('--disk',type=Path)
    parser.add_argument('--capture',type=Path)
    parser.add_argument('--fixture',type=Path)
    parser.add_argument('--before-disk',type=Path)
    parser.add_argument('--before-capture',type=Path)
    parser.add_argument('--first-cycle',type=int,default=100000000)
    parser.add_argument('--gap-cycles',type=int,default=50000000)
    args=parser.parse_args();out=args.work_dir.resolve()
    if out.exists():parser.error('Use a new output path; retained failures cannot be overwritten')
    if not 1<=args.timeout<=1800:parser.error('timeout must be bounded1..1800 seconds')
    if not 1<=args.jobs<=8:parser.error('jobs must be bounded1..8')
    out.mkdir(parents=True)
    report={'schema':'lemma-silicon-acceptance/0.1.0','status':'FAIL','lane':args.lane,
            'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
    try:
        if args.lane=='devices':report.update(devices(out,args.timeout,args.jobs))
        elif args.lane in ('monitor','monitor-input'):
            sys.path.insert(0,str(ROOT/'conformance/silicon'))
            from monitor_observations import fixture,observe
            if args.lane=='monitor-input':report.update(fixture(out))
            else:
                if args.capture is None:raise ValueError('monitor observations require --capture')
                report.update(observe(args.capture))
        else:
            sys.path.insert(0,str(ROOT/'conformance/silicon'))
            from notebook_observations import fixture,short_session,cold,failed_flush,initialized
            if args.lane=='input':
                fixture(out,args.first_cycle,args.gap_cycles)
                report.update(status='INPUT_ONLY',scope='raw external fixture generated; no execution claim')
            else:
                if args.disk is None or args.capture is None:
                    raise ValueError('observations require --disk and --capture')
                if args.lane=='initializer':report.update(initialized(args.disk,args.capture))
                elif args.lane=='notebook':
                    if args.fixture is None:raise ValueError('notebook observations require --fixture')
                    report.update(short_session(args.disk,args.capture,args.fixture))
                else:
                    if args.before_disk is None:raise ValueError('comparison requires --before-disk')
                    if args.lane=='cold':
                        if args.before_capture is None:raise ValueError('cold comparison requires --before-capture')
                        report.update(cold(args.before_disk,args.disk,args.before_capture,args.capture))
                    else:report.update(failed_flush(args.before_disk,args.disk,args.capture))
        return 0
    except (ValueError,KeyError,RuntimeError,OSError,subprocess.SubprocessError) as error:
        report['error']=str(error);print(f'Silicon acceptance FAIL: {error}',file=sys.stderr);return 1
    finally:
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':sys.exit(main())
