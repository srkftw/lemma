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

def device_build(build, tool_file, log, timeout):
    # Resolve and hash the actual pinned host executables in the same Nix shell
    # which executes Verilator. These host identities never enter the RV64 link.
    query = "\n".join([
        "import hashlib,json,os,shutil,subprocess",
        "from pathlib import Path",
        "tools={}",
        "for name in ('verilator','make','c++'):",
        "    found=shutil.which(name)",
        "    if not found:raise RuntimeError('Missing host tool '+name)",
        "    path=Path(found).resolve()",
        "    tools[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),",
        "                 'version':subprocess.check_output([found,'--version'],text=True).splitlines()[0]}",
        "path=Path(tools['verilator']['path']).with_name('verilator_bin')",
        "tools['verilator_bin']={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),",
        "                        'version':subprocess.check_output([str(path),'--version'],text=True).splitlines()[0]}",
        f"Path({str(tool_file)!r}).write_text(json.dumps(tools,indent=2)+'\\n')",
        f"argv={build!r}",
        "os.execvp(argv[0],argv)"])
    record = command(['nix-shell',str(ROOT/'tooling/silicon/sim.nix'),'--run',
                      shlex.join(['python3','-c',query])],log,timeout)
    tools = json.loads(tool_file.read_text())
    if set(tools) != {'verilator','verilator_bin','make','c++'}:
        raise RuntimeError('Incomplete RTL host-tool inventory')
    for value in tools.values():
        if not value['path'].startswith('/nix/store/') or not value['version'] or sha(value['path']) != value['sha256']:
            raise RuntimeError('RTL host-tool identity changed')
    record['effective_argv'] = build
    return record, tools

def devices(out, timeout, jobs):
    source_names = ['sim/rtl/lemma_pen.sv','sim/rtl/lemma_paper.sv','sim/rtl/lemma_block.sv','sim/rtl/lemma_register_ram.sv',
                    'conformance/silicon/Devices.sv','conformance/silicon/BlockProtocol.sv',
                    'conformance/silicon/PenBanks.sv','conformance/silicon/PaperSequencer.sv','scripts/check_silicon.py',
                    'tooling/silicon/sim.nix','flake.lock']
    before = {p: sha(ROOT/p) for p in source_names}
    obj = out/'obj';obj.mkdir()
    build = ['verilator','--binary','--timing','-j',str(jobs),'-Wno-fatal','--top-module','Devices',
             '--Mdir',str(obj),*(str(ROOT/p) for p in source_names if p.endswith('.sv'))]
    built, tools = device_build(build,out/'tools.json',out/'build.log',timeout)
    records = [built,command([str(obj/'VDevices')],out/'simulation.log',30)]
    protocol_obj = out/'protocol-obj';protocol_obj.mkdir()
    protocol_build = ['verilator','--binary','--timing','-j',str(jobs),'-Wno-fatal',
                      '--top-module','BlockProtocol','--Mdir',str(protocol_obj),
                      str(ROOT/'sim/rtl/lemma_block.sv'),str(ROOT/'conformance/silicon/BlockProtocol.sv')]
    built, protocol_tools = device_build(protocol_build,out/'protocol-tools.json',out/'protocol-build.log',timeout)
    records.extend([built,command([str(protocol_obj/'VBlockProtocol')],out/'protocol-simulation.log',30)])
    if tools != protocol_tools:
        raise RuntimeError('RTL host-tool closure changed between literal workloads')
    pen_obj = out/'pen-obj';pen_obj.mkdir()
    pen_build = ['verilator','--binary','--timing','-j',str(jobs),'-Wno-fatal',
                 '--top-module','PenBanks','--Mdir',str(pen_obj),
                 str(ROOT/'sim/rtl/lemma_pen.sv'),str(ROOT/'conformance/silicon/PenBanks.sv')]
    built, pen_tools = device_build(pen_build,out/'pen-tools.json',out/'pen-build.log',timeout)
    records.extend([built,command([str(pen_obj/'VPenBanks')],out/'pen-simulation.log',30)])
    if tools != pen_tools:
        raise RuntimeError('RTL host-tool closure changed for banked FIFO workload')
    paper_obj = out/'paper-obj';paper_obj.mkdir()
    paper_build = ['verilator','--binary','--timing','-j',str(jobs),'-Wno-fatal',
                   '--top-module','PaperSequencer','--Mdir',str(paper_obj),
                   str(ROOT/'sim/rtl/lemma_paper.sv'),str(ROOT/'conformance/silicon/PaperSequencer.sv')]
    built, paper_tools = device_build(paper_build,out/'paper-tools.json',out/'paper-build.log',timeout)
    records.extend([built,command([str(paper_obj/'VPaperSequencer')],out/'paper-simulation.log',30)])
    if tools != paper_tools:
        raise RuntimeError('RTL host-tool closure changed for digital paper workload')
    text = (out/'simulation.log').read_text()
    expected = ['PEN stable-head overflow exact-ack resync watchdog reset PASS',
                'PAPER banked aperture 32 lane-width cases and 4 boundary rejections PASS',
                'PAPER latch Busy invalid-command bounds interrupted-reset PASS',
                'BLOCK descriptors DMA payload used-ring flush error bounds reset PASS',
                'RAM 4096-byte register implementation distinct sparse windows strobes faults PASS']
    protocol_expected = ['BLOCK-PROTOCOL DMA/media backpressure reset/error quiescence queue stability PASS',
                         'BLOCK-PROTOCOL simultaneous completion/error IRQ ACK event precedence PASS',
                         'BLOCK-PROTOCOL normal flush and 12 independent cases PASS']
    protocol_text = (out/'protocol-simulation.log').read_text()
    pen_expected = ['PEN-BANKS full-capacity all-fields two-wrap and ingress bypass PASS',
                    'PEN-BANKS refill backpressure reset cancellation and watchdog head PASS']
    pen_text = (out/'pen-simulation.log').read_text()
    paper_expected = ['PAPER-SEQUENCER immutable 3-phase row/source clocks backpressure powerdown PASS',
                      'PAPER-SEQUENCER invalid mode reset retained panel and scan error abort PASS']
    paper_text = (out/'paper-simulation.log').read_text()
    if (any(text.count(marker)!=1 for marker in expected)
            or any(protocol_text.count(marker)!=1 for marker in protocol_expected)
            or any(pen_text.count(marker)!=1 for marker in pen_expected)
            or any(paper_text.count(marker)!=1 for marker in paper_expected)):
        raise RuntimeError('Missing or duplicate independent device observations')
    if before != {p: sha(ROOT/p) for p in source_names}:
        raise RuntimeError('RTL/device inputs changed during observation')
    binaries = {str(path.relative_to(ROOT)):sha(path) for path in (obj/'VDevices',protocol_obj/'VBlockProtocol',pen_obj/'VPenBanks',paper_obj/'VPaperSequencer')}
    return {'status':'PASS','source_inputs':before,'commands':records,'tool_inputs':tools,'compiled_binaries':binaries,
            'scope':'literal external MMIO/DMA stimuli on real RTL; not guest acceptance C or notebook durability',
            'observations':expected+protocol_expected+pen_expected+paper_expected}

def host_deadline_options(binary):
    """Actual compiled argument handling; no guest boot or timeout-pass claim."""
    from silicon_guest import MAX_RUN_SECONDS
    rows=[]
    for seconds in (1, MAX_RUN_SECONDS, 0, MAX_RUN_SECONDS+1):
        argv=[str(binary),'--deadline',str(seconds)]
        result=subprocess.run(argv,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        # Accepted deadlines reach the required-image check. Rejected deadlines
        # fail at argument validation, before any target image can be loaded.
        expected=('RTL adapter: development boot requires --image and --rom\n' if 1<=seconds<=MAX_RUN_SECONDS else
                  f'RTL adapter: deadline must be1..{MAX_RUN_SECONDS}seconds\n')
        if result.returncode!=1 or result.stdout or result.stderr.decode()!=expected:
            raise RuntimeError('Compiled RTL deadline handling disagrees with the launcher')
        rows.append({'argv':argv,'exit_code':result.returncode,'stdout':'','stderr':expected})
    return rows

def power_control(out, timeout, jobs):
    from silicon_profile import constants, profile
    names = ('sim/rtl/lemma_power.sv', 'conformance/silicon/PowerControl.sv',
             'sim/profiles/lemma-silicon-dev-0.3.0.json', 'scripts/silicon_profile.py',
             'scripts/check_silicon.py', 'tooling/silicon/sim.nix', 'flake.lock')
    before = {name: sha(ROOT/name) for name in names}
    fields = constants(profile('lemma-silicon-dev/0.3.0'))
    binding = out/'lemma_silicon_binding.sv'
    binding.write_text('package lemma_silicon_binding;\n'+''.join(
        f"localparam logic [63:0] {name.upper()} = 64'h{value:016x};\n"
        for name, value in fields.items())+'endpackage\n')
    obj = out/'obj'; obj.mkdir()
    argv = ['verilator', '--binary', '--timing', '-j', str(jobs), '-Wno-fatal',
            '--top-module', 'PowerControl', '--Mdir', str(obj), str(binding),
            str(ROOT/'sim/rtl/lemma_power.sv'), str(ROOT/'conformance/silicon/PowerControl.sv')]
    built, tools = device_build(argv, out/'tools.json', out/'build.log', timeout)
    executed = command([str(obj/'VPowerControl')], out/'simulation.log', 30)
    expected = ['POWER six independent BUSY sources malformed MMIO no false completion PASS',
                'POWER raw edge guest decision exact cancel wake and W1C precedence PASS',
                'POWER warm held-button epoch retention and cold control reset PASS']
    if any((out/'simulation.log').read_text().count(marker) != 1 for marker in expected):
        raise RuntimeError('Missing or duplicate independent power observations')
    if before != {name: sha(ROOT/name) for name in names}:
        raise RuntimeError('Power inputs changed during execution')
    return {'status': 'PASS', 'source_inputs': before, 'tool_inputs': tools,
            'commands': [built, executed], 'compiled_binary_sha256': sha(obj/'VPowerControl'),
            'generated_binding_sha256': sha(binding), 'observations': expected,
            'scope': 'literal power circuitry; guest cooperative suspend, session checkpoints and physical power remain separate'}

def bus_dependency(deps=None):
    from silicon_compute import prepare
    dep=Path(deps).resolve() if deps is not None else ROOT/'build/silicon/deps/cvw'
    if deps is not None and (not dep.is_dir() or not (dep/'.git').exists()):
        raise ValueError('Explicit --deps requires an existing CVW Git checkout')
    prepare(dep)
    return dep

def bus_lanes(out, timeout, jobs, deps=None):
    from silicon_compute import source_manifest
    dep=bus_dependency(deps);manifest=source_manifest(dep)
    bench=ROOT/'conformance/silicon/BusLanes.sv'
    before={**manifest['sha256'],**manifest['configuration_includes'],
            str(bench):sha(bench),str(Path(__file__)):sha(__file__),
            str(ROOT/manifest['host_adapter']['path']):manifest['host_adapter']['sha256'],
            str(ROOT/'scripts/silicon_guest.py'):sha(ROOT/'scripts/silicon_guest.py')}
    for name in ('scripts/silicon_compute.py','tooling/silicon/apply_cvw.py',
                 'tooling/silicon/sim.nix','tooling/silicon/dependencies.json','flake.lock'):
        before[str(ROOT/name)]=sha(ROOT/name)
    (out/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n')
    obj=out/'obj';obj.mkdir()
    build=['verilator','--binary','--timing','-j',str(jobs),'-Wno-fatal','--top-module','BusLanes',
           '--Mdir',str(obj),*['-I'+d for d in manifest['include_dirs']],*manifest['sources'],str(bench)]
    records=[command(['nix-shell',str(ROOT/'tooling/silicon/sim.nix'),'--run',shlex.join(build)],out/'build.log',timeout)]
    records.append(command([str(obj/'VBusLanes')],out/'simulation.log',30))
    expected=['BUS actual CVW replicated SW QueueNum and MMIO byte/half/word/double lanes PASS',
              'PAPER registered MMIO AHB error retention single completion reset cancellation PASS',
              'ARB held CPU/DMA owner payload backpressure terminal errors reset quiescence PASS',
              'DMA narrow reads adjacent bytes write strobes ready backpressure CPU resume PASS']
    if any((out/'simulation.log').read_text().count(marker)!=1 for marker in expected):
        raise RuntimeError('Missing or duplicate actual bus-lane observations')
    host=out/'host'
    records.append(command(['python3','scripts/silicon_compute.py','build','--output-dir',str(host),
                            '--jobs',str(jobs),'--deps',str(dep)],out/'host-build.log',timeout))
    host_options=host_deadline_options(host/'obj/lemma-rtl')
    if before!={p:sha(p) for p in before}:raise RuntimeError('Bus-lane inputs changed during observation')
    return {'status':'PASS','source_inputs':before,'commands':records,'observations':expected,
            'host_build_sha256':sha(host/'build.json'),'host_binary_sha256':sha(host/'obj/lemma-rtl'),
            'host_deadline_options':host_options,
            'scope':'literal data-phase/ready stimuli on actual compute/SoC/block RTL with hart reset; not guest execution'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deps',type=Path,help='Existing immutable CVW dependency checkout for bus-lanes; validated by normal source admission')
    parser.add_argument('--lane',choices=['devices','power','bus-lanes','guest-devices','device-input','monitor','monitor-input','initializer','notebook','cold','failed-flush','input'],required=True)
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
    parser.add_argument('--session',choices=['undo-redo','brush-width'],default='undo-redo')
    args=parser.parse_args();out=args.work_dir.resolve()
    if args.deps is not None and args.lane!='bus-lanes':parser.error('--deps is admitted only for bus-lanes')
    if out.exists():parser.error('Use a new output path; retained failures cannot be overwritten')
    if not 1<=args.timeout<=1800:parser.error('timeout must be bounded1..1800 seconds')
    if not 1<=args.jobs<=8:parser.error('jobs must be bounded1..8')
    out.mkdir(parents=True)
    report={'schema':'lemma-silicon-acceptance/0.1.0','status':'FAIL','lane':args.lane,
            'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
    try:
        if args.lane=='devices':report.update(devices(out,args.timeout,args.jobs))
        elif args.lane=='power':report.update(power_control(out,args.timeout,args.jobs))
        elif args.lane=='bus-lanes':report.update(bus_lanes(out,args.timeout,args.jobs,args.deps))
        elif args.lane in ('guest-devices','device-input'):
            sys.path.insert(0,str(ROOT/'conformance/silicon'))
            from device_observations import fixture,observe
            if args.lane=='device-input':
                fixture(out)
                report.update(status='INPUT_ONLY',scope='303 raw external device events; no execution claim')
            else:
                if args.capture is None:raise ValueError('guest device observations require --capture')
                report.update(observe(args.capture))
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
                fixture(out,args.first_cycle,args.gap_cycles,args.session)
                report.update(status='INPUT_ONLY',scope='raw external fixture generated; no execution claim')
            else:
                if args.disk is None or args.capture is None:
                    raise ValueError('observations require --disk and --capture')
                if args.lane=='initializer':report.update(initialized(args.disk,args.capture))
                elif args.lane=='notebook':
                    if args.fixture is None:raise ValueError('notebook observations require --fixture')
                    report.update(short_session(args.disk,args.capture,args.fixture,args.session))
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
