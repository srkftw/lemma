#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify the real optional SRAM storage in the maintained pen controller.

Uses published four-state IHP functional models, a pinned historical controller
and independent public-bus literal expectations. No analog/PVT, full equivalence,
route, process DRC, LVS or extracted timing result is inferred.
"""
from pathlib import Path
import argparse
import functools
import hashlib
import json
import resource
import shlex
import shutil
import subprocess
import sys
import time

from silicon_synth import ROOT, CommandFailure, run, sha, slang_token

REFERENCE = 'bbce92dc724ded15814543181c09f72f6256a8e2'
REFERENCE_SHA = '2bab7e3356a1ebfa13366c19b57de7d63a757236ee6fff749409839707f76ce3'
MACRO = 'RM_IHPSG13_1P_256x64_c2_bm_bist'
PDK_BASE = 'ihp-sg13g2/libs.ref/sg13g2_sram/'
COLLATERAL = ['LICENSE', *[PDK_BASE + name for name in (
    'doc/' + MACRO + '.txt', 'verilog/' + MACRO + '.v',
    'verilog/RM_IHPSG13_1P_core_behavioral_bm_bist.v',
    'lef/' + MACRO + '.lef', 'lib/' + MACRO + '_typ_1p20V_25C.lib',
    'gds/' + MACRO + '.gds', 'cdl/' + MACRO + '.cdl')]]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdk', type=Path, required=True,
                        help='Existing Git repository containing the pinned public PDK objects; no fetch')
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--map', action='store_true', help='Also map the same controller to three real SRAMs and pinned standard cells')
    args = parser.parse_args()
    out = args.work_dir.resolve()
    # The read_slang command tail does not unquote whitespace. Reject it before
    # any output or tool action, along with command separators and escapes.
    slang_token(out)
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    started = time.monotonic()
    deadline = started + 300
    report = {'status': 'FAIL', 'scope': __doc__, 'commands': [],
              'bounds': {'whole_seconds': 300, 'compile_seconds': 60,
                         'simulation_seconds': 30, 'process_AS_bytes': 4 << 30,
                         'file_bytes': 1 << 30}, 'reference_commit': REFERENCE}

    def invoke(argv, name, seconds):
        record = run(argv, out / (name + '.log'), min(deadline, time.monotonic() + seconds))
        report['commands'].append(record)
        return (out / (name + '.log')).read_text(errors='replace')

    try:
        lock = json.loads((ROOT / 'tooling/silicon/physical-lock.json').read_text())
        revision = lock['pdk']['revision']
        require(revision == '5e6d592e4002946a4616f798c357f0f3c06cf3b6', 'unqualified PDK revision')
        inputs = [Path(__file__).resolve(), ROOT / 'sim/rtl/lemma_pen.sv',
                  ROOT / 'conformance/silicon/PenIngress.sv', ROOT / 'conformance/silicon/PenBanks.sv',
                  ROOT / 'tooling/silicon/physical-lock.json', ROOT / 'tooling/silicon/pen-sram.nix',
                  ROOT / 'scripts/silicon_synth.py', ROOT / 'flake.lock']
        report['source_inputs'] = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
        report['tools'] = {}
        for name in ('iverilog', 'vvp'):
            found = shutil.which(name)
            require(found is not None, 'missing actual ' + name)
            binary = Path(found).resolve()
            version = subprocess.check_output([str(binary), '-V'], stderr=subprocess.STDOUT,
                                              text=True, timeout=10).splitlines()[0]
            require('13.0' in version, 'unqualified Icarus version')
            report['tools'][name] = {'path': str(binary), 'sha256': sha(binary), 'version': version}
        report['pdk_revision'] = revision
        report['collateral'] = {}
        for name in COLLATERAL:
            raw = subprocess.check_output(['git', '-C', str(args.pdk.resolve()), 'show', revision + ':' + name], timeout=10)
            target = out / 'pdk' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            report['collateral'][name] = {'sha256': sha(target), 'bytes': len(raw)}
        original = subprocess.check_output(['git', '-C', str(ROOT), 'show', REFERENCE + ':sim/rtl/lemma_pen.sv'], timeout=10)
        require(hashlib.sha256(original).hexdigest() == REFERENCE_SHA, 'historical reference differs')
        require(original.count(b'module lemma_pen #(') == 1, 'reference module count')
        (out / 'reference.sv').write_bytes(original.replace(b'module lemma_pen #(', b'module lemma_pen_reference #('))
        source = (ROOT / 'sim/rtl/lemma_pen.sv').read_text()
        (out / 'candidate.sv').write_text(source)
        vendor = [str(out / 'pdk' / PDK_BASE / 'verilog' / name) for name in
                  (MACRO + '.v', 'RM_IHPSG13_1P_core_behavioral_bm_bist.v')]
        report['status'] = 'RUNNING'
        (out / 'plan.json').write_text(json.dumps(report, indent=2) + '\n')
        iv = report['tools']['iverilog']['path']
        vvp = report['tools']['vvp']['path']

        def simulate(name, top, candidate, fixture, expected_failure=None):
            consumed = {str(p): sha(p) for p in
                        [candidate, fixture, out / 'reference.sv', *map(Path, vendor)]}
            report.setdefault('case_inputs', {})[name] = consumed
            binary = out / (name + '.vvp')
            invoke([iv, '-g2012', '-DFUNCTIONAL', '-s', top, '-o', str(binary),
                    str(candidate), str(out / 'reference.sv'), *vendor, str(fixture)], name + '-compile', 60)
            try:
                text = invoke([vvp, str(binary)], name + '-simulation', 30)
            except CommandFailure as error:
                report['commands'].append(error.record)
                require(expected_failure is not None and not error.record['timed_out'], 'unexpected simulation failure')
                text = (out / (name + '-simulation.log')).read_text()
                require(expected_failure in text, 'negative failed for a different reason')
                require(all(sha(Path(p)) == h for p, h in consumed.items()), 'negative input drift')
                return
            require(expected_failure is None, 'actual mutant survived public observation')
            markers = (['PEN-INGRESS literal full256 fields high64 sequence/time consecutive/wrap PASS',
                        'PEN-INGRESS first-edge all-fields immediate-next-edge ACK PASS',
                        'PEN-INGRESS every-edge old/new invalid full ACK reset collision PASS edges']
                       if top == 'PenIngress' else
                       ['PEN-BANKS full-capacity all-fields two-wrap and ingress bypass PASS',
                        'PEN-BANKS queued raw across both refill edges consumes one sequence PASS',
                        'PEN-BANKS refill backpressure reset cancellation and watchdog head PASS'])
            require(all(text.count(m) == 1 for m in markers), 'missing complete nonempty protocol observations')
            require(all(sha(Path(p)) == h for p, h in consumed.items()), 'protocol input drift')
            report.setdefault('observations', {})[name] = markers

        for top in ('PenIngress', 'PenBanks'):
            text = (ROOT / 'conformance/silicon' / (top + '.sv')).read_text()
            require(text.count('lemma_pen pen(') == 1, 'fixture DUT binding differs')
            fixture = out / (top + '.sv')
            fixture.write_text(text.replace('lemma_pen pen(', 'lemma_pen #(.IHP_SRAM(1)) pen('))
            simulate('sram-' + top, top, out / 'candidate.sv', fixture)
        simulate('default-register', 'PenIngress', out / 'candidate.sv', ROOT / 'conformance/silicon/PenIngress.sv')
        for name, before, after in (
                ('upper-sequence-zeroed', "wire [191:0] input_words = {{(192-$bits(ingress_entry)){1'b0}},ingress_entry};",
                 "wire [191:0] input_words = {{(192-$bits(ingress_entry)){1'b0}},ingress_entry} & {64'b0,128'hffffffffffffffffffffffffffffffff};"),
                ('address-alias128', '.A_ADDR(row_address)', ".A_ADDR({1'b0,row_address[6:0]})")):
            require(source.count(before) == 1, 'mutation no longer targets actual storage')
            mutant = out / (name + '.sv')
            mutant.write_text(source.replace(before, after))
            simulate(name, 'PenIngress', mutant, out / 'PenIngress.sv', 'external-interface difference at edge')
        bad_depth = out / 'bad-depth.sv'
        bad_depth.write_text((out / 'PenIngress.sv').read_text().replace('.IHP_SRAM(1)', '.IHP_SRAM(1),.FIFO_DEPTH(128)'))
        simulate('reject-depth128', 'PenIngress', out / 'candidate.sv', bad_depth, 'IHP SRAM requires full256 FIFO')
        if args.map:
            # Preserve the arithmetic boundary in the frontend, technology-map
            # both modules, then flatten mapped circuitry. No unknown leaf passes.
            std_name = 'ihp-sg13g2/libs.ref/sg13g2_stdcell/lib/sg13g2_stdcell_typ_1p20V_25C.lib'
            std = out / 'pdk' / std_name
            std.parent.mkdir(parents=True, exist_ok=True)
            std.write_bytes(subprocess.check_output(['git', '-C', str(args.pdk.resolve()),
                                                     'show', revision + ':' + std_name], timeout=10))
            report['collateral'][std_name] = {'sha256': sha(std), 'bytes': std.stat().st_size}
            yosys = Path(shutil.which('yosys') or '')
            require(yosys.is_file(), 'missing actual Yosys')
            yosys = yosys.resolve()
            version = subprocess.check_output([str(yosys), '-V'], text=True, timeout=10).strip()
            require('Yosys 0.69' in version, 'unqualified Yosys version')
            abc = yosys.with_name('yosys-abc')
            shell = Path(shutil.which('bash') or '').resolve()
            require(abc.is_file() and shell.is_file(), 'missing actual batch mapping dependencies')
            report['tools'].update({name: {'path': str(path), 'sha256': sha(path)}
                                    for name, path in [('yosys', yosys), ('yosys-abc', abc), ('bash', shell)]})
            report['tools']['yosys']['version'] = version
            batch = out / 'abc-batch'
            batch.write_text('#!' + str(shell) + '\nexec ' + shlex.quote(str(abc)) + ' "$@"\n')
            batch.chmod(0o700)
            runner = out / 'mapping-runner.py'
            runner.write_text('import os,sys\nos.chdir(sys.argv[1])\nos.execv(sys.argv[2],sys.argv[2:])\n')
            macro_lib = out / 'pdk' / PDK_BASE / 'lib' / (MACRO + '_typ_1p20V_25C.lib')
            script = out / 'mapping.ys'
            script.write_text(f'''read_liberty -lib {std}
read_liberty -lib {macro_lib}
read_slang --keep-hierarchy --top lemma_pen -G IHP_SRAM=1 --single-unit {out/'candidate.sv'}
hierarchy -check -top lemma_pen
synth -top lemma_pen -flatten -noabc
dfflibmap -liberty {std}
abc -exe {batch} -nocleanup -showtmp -liberty {std}
hilomap -hicell sg13g2_tiehi L_HI -locell sg13g2_tielo L_LO
setundef -undriven -zero
setattr -mod -unset keep_hierarchy
setattr -unset keep_hierarchy
flatten -noscopeinfo
hierarchy -top lemma_pen
clean
check -assert
write_verilog -noattr -noexpr {out/'mapped.v'}
write_json {out/'mapped.json'}
stat -liberty {std} -liberty {macro_lib}
''')
            report['mapping_recipe'] = {p.name: sha(p) for p in (batch, runner, script)}
            (out / 'mapping-plan.json').write_text(json.dumps(report, indent=2) + '\n')
            invoke([sys.executable, str(runner), str(out), str(yosys), '-s', str(script)], 'mapping', 180)
            modules = json.loads((out / 'mapped.json').read_text())['modules']
            top = modules['lemma_pen']
            require(top.get('cells') and not top.get('memories'), 'empty mapping or residual memories')
            types, high, low = {}, {'1'}, {'0'}
            for cell in top['cells'].values():
                kind = cell['type']
                require('latch' not in kind.lower() and
                        (kind == MACRO or kind.startswith('sg13g2_') and kind in modules), 'unknown/unmapped cell ' + kind)
                types[kind] = types.get(kind, 0) + 1
                if kind == 'sg13g2_tiehi': high.update(cell['connections']['L_HI'])
                if kind == 'sg13g2_tielo': low.update(cell['connections']['L_LO'])
            require(types.get(MACRO) == 3, 'exactly three actual SRAM macros required')
            for cell in top['cells'].values():
                if cell['type'] != MACRO: continue
                pins = cell['connections']
                require(all(x in high for p in ('A_DLY', 'A_BM') for x in pins[p]) and
                        all(x in low for p in ('A_BIST_EN', 'A_BIST_MEN', 'A_BIST_WEN', 'A_BIST_REN',
                                               'A_BIST_CLK', 'A_BIST_DIN', 'A_BIST_ADDR', 'A_BIST_BM') for x in pins[p]),
                        'actual SRAM delay/mask/BIST pins differ')
                require(len(pins['A_DOUT']) == len(pins['A_DIN']) == len(pins['A_BM']) == 64 and len(pins['A_ADDR']) == 8,
                        'actual SRAM widths differ')
            cells = top['cells']
            drivers = {bit: name for name, cell in cells.items() for port, direction in cell['port_directions'].items()
                       if direction == 'output' for bit in cell['connections'][port]}
            sources = set(top['ports']['sample_time']['bits'])
            @functools.lru_cache(None)
            def depth(bit):
                if bit in sources: return 0
                cell = cells.get(drivers.get(bit))
                if cell is None or cell['type'] in (MACRO, 'sg13g2_dfrbpq_1'): return -10000
                return 1 + max((depth(x) for port, direction in cell['port_directions'].items()
                                if direction == 'input' for x in cell['connections'][port]), default=-10000)
            depths = []
            for bit in top['netnames']['next_sequence']['bits']:
                cell = cells[drivers[bit]]
                require(cell['type'] == 'sg13g2_dfrbpq_1', 'sequence state mapping differs')
                depths.append(depth(cell['connections']['D'][0]))
            require(len(depths) == 64 and 0 <= min(depths) <= max(depths) <= 20, 'declared timestamp-to-sequence depth ceiling')
            report['mapping'] = {'cells': len(cells), 'cell_types': types,
                                 'timestamp_to_sequence_D_max_cells': max(depths), 'all64depths': depths,
                                 'mapped_verilog_sha256': sha(out / 'mapped.v'), 'mapped_json_sha256': sha(out / 'mapped.json'),
                                 'scope': 'Real physical leaf admission and graph depth only; no timing or route qualification'}
        require(all(sha(ROOT / name) == value for name, value in report['source_inputs'].items()), 'source drift')
        require(all(sha(out / 'pdk' / name) == value['sha256']
                    for name, value in report['collateral'].items()), 'collateral drift')
        report['status'] = ('PASS_MAINTAINED_PEN_PROTOCOL_AND_THREE_REAL_SRAM_MAPPING' if args.map else
                            'PASS_MAINTAINED_PEN_DEFAULT_AND_REAL_SRAM_FULL256_PROTOCOL_NEGATIVES')
    except BaseException as error:
        report.update(status='FAIL', error=repr(error))
    finally:
        report['seconds'] = time.monotonic() - started
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report.get('error'), report['seconds'])
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
