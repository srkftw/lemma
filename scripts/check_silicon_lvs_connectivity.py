#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify the explicit connectivity-only Magic adapter on real process geometry.

Original inverter W/L and bulk terminals must match its original CDL. Deliberate
width and bulk mutations must fail. This is not a whole-design DRC/LVS result.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path
import resource
import shutil
import time

from silicon_enclosure import require
from silicon_synth import CommandFailure, ROOT, lvs_matches, run, sha



def sram_parent_preflight(args):
    """Compare only the reviewed actual-parent-connected zero-default SRAM leaf."""
    import silicon_lvs_alias as lvs_alias
    from silicon_lvs_alias import coldec2_zero_defaults, require_coldec2_defaults
    revision = '5e6d592e4002946a4616f798c357f0f3c06cf3b6'
    out = args.work_dir.resolve()
    extraction = args.sram_parent_extraction.resolve()
    pdk = args.pdk.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    started = time.monotonic()
    resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 << 20, 128 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    report = {'schema': 'lemma-connected-sram-default-only-leaf/1', 'status': 'FAIL',
        'scope': 'Actual selected-layout child plus literal parent bridge; original seven-cell CDL and explicit PSP NRS/NRD zero defaults. No general parameter LVS, full SRAM/SoC LVS, process DRC or resistor waiver.',
        'bounds': {'whole_seconds': 30, 'each_seconds': 3, 'AS_bytes': 2 << 30},
        'commands': [], 'cases': [], 'model_relation_negatives': []}
    try:
        actual, producer = extraction / 'extracted.spice', extraction / 'result.json'
        require(sha(producer) == '672d363d61342bf8110c445cd155ca0dd081194741876dd7cf69f7ca99df459b',
                'only the reviewed selected-layout extraction context is admitted')
        context = json.loads(producer.read_text())
        require(context['source_seal_equal'] and context['power_grid'] == 'CONNECTED_CORE_GRID_ONLY_NO_IR_EM',
                'original extraction source or power context differs')
        require(sha(actual) == context['transistor_extraction']['sha256'] ==
                'd8bc294f9b85b13daeaa5ccceb987e3a89db2a545efa0e1e1f661151210d942d',
                'actual connected extraction differs')
        originals = {}
        for target, source in [('original.cdl', 'ihp-sg13g2/libs.ref/sg13g2_sram/cdl/RM_IHPSG13_1P_256x64_c2_bm_bist.cdl'),
                ('original-PSP103_module.include', 'ihp-sg13g2/libs.tech/verilog-a/psp103/PSP103_module.include'),
                ('original-PSP-release-notes.txt', 'ihp-sg13g2/libs.tech/verilog-a/psp103/releasenotesPSP103.8.2.txt'),
                ('PDK-LICENSE', 'LICENSE')]:
            path = out / target
            path.write_bytes(subprocess.check_output(['git', '-C', str(pdk), 'show', revision + ':' + source], timeout=3))
            originals[target] = path
        require(sha(originals['original.cdl']) == '2418a6da4dce973b751ba0cd296ecd1482b7cf6bcd67b12b13fa99bc49f85563' and
                sha(originals['original-PSP103_module.include']) == 'cc9f02e72fda8c907f9e6befe0dcdc2ff1dc13e45fb2f48263935c06317d3197',
                'original CDL/model identity differs')
        setup = pdk / 'ihp-sg13g2/libs.tech/netgen/ihp-sg13g2_setup.tcl'
        require(sha(setup) == '9981101e0bbe9d8f6af656f03475d0d00fb7507559645e85e4d9d5f704b3878e', 'original setup differs')
        netgen = Path(shutil.which('netgen') or '').resolve()
        require(netgen.is_file(), 'actual Netgen required')
        inputs = [Path(__file__).resolve(), Path(lvs_alias.__file__).resolve(), ROOT / 'scripts/silicon_synth.py',
                  actual, producer, setup, netgen, *originals.values()]
        report['source_inputs'] = {str(p): sha(p) for p in inputs}
        archive = out / 'source-archive'
        archive.mkdir()
        for source in (Path(__file__).resolve(), Path(lvs_alias.__file__).resolve(), ROOT / 'scripts/silicon_synth.py'):
            shutil.copyfile(source, archive / source.name)
        (archive / 'manifest.json').write_text(json.dumps(report['source_inputs'], indent=2) + '\n')
        report['model_rights'] = 'Original PSP copyright and CMC release terms retained alongside the unmodified module; root PDK Apache licence is separate. No design-specific or manufacturing rights qualification.'
        text = actual.read_text()
        target = 'RM_IHPSG13_1P_COLDEC2'
        child = re.search(r'^\.subckt ' + target + r'\b.*?^\.ends\b[^\n]*', text, re.M | re.S)[0]
        header = re.match(r'[^\n]*(?:\n\+[^\n]*)*', child)[0]
        ports = header.replace('\n+', ' ').split()[2:]
        literal = re.search(r'^XRM_IHPSG13_1P_COLDEC2_0 [^\n]*(?:\n\+[^\n]*)*', text, re.M)[0]
        arguments = literal.replace('\n+', ' ').split()[1:-1]
        require(len(ports) == len(arguments) == 186 and not re.search(r'^R\S+', child, re.M), 'child context differs')
        bridge = dict(zip(ports, arguments))
        require(bridge['VDD'] == bridge['VDD_uq0'] == 'VDD' and bridge['VSS'] == 'VSS', 'literal supply bridge differs')
        blocks = {m[1]: m[0] for m in re.finditer(r'^\.SUBCKT (\S+)[^\n]*(?:\n|$).*?^\.ENDS[^\n]*',
                                               originals['original.cdl'].read_text(), re.M | re.S)}
        seen = set()
        def visit(name):
            if name in seen:
                return
            seen.add(name)
            block = blocks[name]
            require(not re.search(r'^R\S+', block, re.M), 'resistor model outside reviewed scope')
            for line in re.sub(r'\n\+\s*', ' ', block).splitlines():
                if line.startswith('X'):
                    visit(line.split()[-1])
        reference_top = 'RM_IHPSG13_256x64_c2_1P_COLDEC2'
        visit(reference_top)
        require(seen == {reference_top, 'RSC_IHPSG13_DFNQMX2IX1', 'RSC_IHPSG13_FILLCAP4', 'RSC_IHPSG13_FILLCAP8',
                         'RSC_IHPSG13_INVX2', 'RSC_IHPSG13_NAND2X2', 'RSC_IHPSG13_TIEL'}, 'reference closure differs')
        reference = '\n'.join(blocks[x] for x in sorted(seen)) + '\n'
        reference_path = out / 'reference-seven-cells.cdl'
        reference_path.write_text(reference)
        model = originals['original-PSP103_module.include'].read_text()
        refports = re.match(r'[^\n]*(?:\n\+[^\n]*)*', blocks[reference_top])[0].replace('\n+', ' ').split()[2:]
        require(len(refports) == 18 and set(refports) <= set(ports), 'reference pins differ')
        reverse = {bridge[x]: x for x in refports}
        require(len(reverse) == 18, 'parent connection aliases distinct functional pins')
        wired = [reverse.get(x, x) for x in arguments]
        original_child = child
        child = coldec2_zero_defaults(original_child, reference, model)
        def verify(raw, derived):
            require_coldec2_defaults(raw, derived, reference, model)
        controls = [
            ('reference_NRS_nonzero', lambda: coldec2_zero_defaults(original_child, re.sub(r'(?i)(\bnrs\s*=)0\b', r'\g<1>1', reference, count=1), model)),
            ('reference_NRD_nonzero', lambda: coldec2_zero_defaults(original_child, re.sub(r'(?i)(\bnrd\s*=)0\b', r'\g<1>1', reference, count=1), model)),
            ('raw_NRS_present', lambda: coldec2_zero_defaults(original_child.replace(' w=', ' nrs=0 w=', 1), reference, model)),
            ('raw_NRD_nonzero', lambda: coldec2_zero_defaults(original_child.replace(' w=', ' nrd=1 w=', 1), reference, model)),
            ('unknown_parameter', lambda: coldec2_zero_defaults(original_child.replace(' w=', ' unknown=0 w=', 1), reference, model)),
            ('derived_NRS_nonzero', lambda: verify(original_child, child.replace(' nrs=0', ' nrs=1', 1))),
            ('derived_NRD_nonzero', lambda: verify(original_child, child.replace(' nrd=0', ' nrd=1', 1))),
            ('omitted_NRS_default', lambda: verify(original_child, child.replace(' nrs=0', '', 1))),
            ('omitted_NRD_default', lambda: verify(original_child, child.replace(' nrd=0', '', 1))),
            ('wrong_PSP_NRS_default', lambda: coldec2_zero_defaults(original_child, reference, re.sub(r'(`IPRnb\(NRS\s*,)0\.0', r'\g<1>1.0', model, count=1))),
            ('wrong_PSP_NRD_default', lambda: coldec2_zero_defaults(original_child, reference, re.sub(r'(`IPRnb\(NRD\s*,)0\.0', r'\g<1>1.0', model, count=1)))]
        for name, control in controls:
            try:
                control()
            except ValueError as error:
                report['model_relation_negatives'].append({'case': name, 'status': 'REJECTED_BEFORE_NETGEN', 'reason': str(error)})
            else:
                raise ValueError('model relation accepted negative: ' + name)
        (out / 'actual-child.spice').write_text(original_child + '\n')
        (out / 'literal-parent-call.txt').write_text(literal + '\n')
        report['context'] = {'child_pins': 186, 'layout_MOS': 503, 'reference_cells': sorted(seen),
                             'literal_parent_supply_bridge': {x: bridge[x] for x in ('VDD', 'VDD_uq0', 'VSS')}}
        variants = [('connected', child, wired, True)]
        for name, net in [('deleted_parent_bridge', 'separate_unconnected_parent_supply'), ('retargeted_parent_bridge', 'VSS')]:
            changed = wired.copy()
            changed[ports.index('VDD_uq0')] = net
            variants.append((name, child, changed, False))
        changed = wired.copy()
        a, b = ports.index('BIST_ADDR<0>'), ports.index('BIST_ADDR<1>')
        changed[a], changed[b] = changed[b], changed[a]
        variants.append(('swapped_parent_bits', child, changed, False))
        changed = wired.copy()
        changed[ports.index('VDD')] = 'VSS'
        variants.append(('retargeted_primary_supply', child, changed, False))
        line = re.search(r'^M\S+ [^\n]+sg13_lv_pmos[^\n]*', child, re.M)[0]
        fields = line.split()
        require(fields[4] in ('VDD', 'VDD_uq0'), 'bulk mutation target differs')
        fields[4] = 'VSS'
        variants.append(('wrong_device_bulk', child.replace(line, ' '.join(fields), 1), wired, False))
        width = re.search(r'(?m)^(M\S+ [^\n]*?\bw=)([\d.]+)u', child)
        require(width is not None, 'width mutation target missing')
        wrong = child[:width.start(2)] + str(float(width[2]) * .5) + child[width.end(2):]
        variants.append(('wrong_device_width', wrong, wired, False))
        for name, body, values, expected in variants:
            raw = re.sub(r' nrs=0 nrd=0(?=\n|$)', '', body)
            verify(raw, body)
            wrapper = '\n.subckt lemma_connected_coldec ' + ' '.join(refports) + '\nXactual ' + ' '.join(values) + ' ' + target + '\n.ends lemma_connected_coldec\n'
            data, script = out / (name + '.spice'), out / (name + '.tcl')
            data.write_text(body + '\n' + wrapper)
            (out / (name + '.source.spice')).write_text(raw + '\n' + wrapper)
            script.write_text(f'set reference [readnet spice {{{reference_path}}}]\nlvs {{{data} lemma_connected_coldec}} [list {reference_top} $reference] {{{setup}}} {{{out / (name + ".rpt")}}} -json\n')
            record = run([str(netgen), '-batch', 'source', str(script)], out / (name + '.log'), min(started + 30, time.monotonic() + 3))
            report['commands'].append(record)
            matches = lvs_matches((out / (name + '.rpt')).read_text())
            report['cases'].append({'case': name, 'matches': matches, 'expected': expected, 'report_sha256': sha(out / (name + '.rpt'))})
            require(matches == expected, 'actual connected comparison/negative differs: ' + name)
        report['fresh_reused_boundary'] = 'Reused original source-bound transistor extraction; fresh literal-parent/default relation and seven actual Netgen comparisons. Original NRS mutation false negative is independently covered, not relabeled.'
        report['status'] = 'PASS_ZERO_DEFAULT_ONLY_PARENT_CONNECTED_SRAM_LEAF_AND17_NEGATIVES'
    except BaseException as error:
        report.update(error=repr(error))
        if isinstance(error, CommandFailure):
            report['commands'].append(error.record)
    finally:
        report['source_seal_equal'] = all(sha(Path(path)) == value for path, value in report.get('source_inputs', {}).items())
        if not report['source_seal_equal']:
            report['status'] = 'FAIL'
        report['seconds'] = time.monotonic() - started
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report.get('error'), report['seconds'])
    return 0 if report['status'].startswith('PASS_') else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdk', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--sram-parent-extraction', type=Path, help='Reviewed source-bound selected-layout extraction directory; compare its literal-parent-connected COLDEC2 zero-default-only leaf with17 negatives, never full SRAM LVS')
    args = parser.parse_args()
    if args.sram_parent_extraction is not None:
        return sram_parent_preflight(args)
    out, pdk = args.work_dir.resolve(), args.pdk.resolve() / 'ihp-sg13g2'
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    started = time.monotonic()
    resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 << 20, 64 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    report = {'schema': 'lemma-connectivity-only-extraction-preflight/1', 'status': 'FAIL',
              'scope': __doc__, 'commands': [], 'cases': [],
              'bounds': {'whole_seconds': 90, 'each_seconds': 20, 'AS_bytes': 2 << 30}}
    try:
        magic, netgen = (Path(shutil.which(name) or '').resolve() for name in ('magic', 'netgen'))
        require(magic.is_file() and netgen.is_file(), 'actual Magic and Netgen required')
        std = pdk / 'libs.ref/sg13g2_stdcell'
        setup = pdk / 'libs.tech/netgen/ihp-sg13g2_setup.tcl'
        inputs = [Path(__file__).resolve(), ROOT / 'scripts/silicon_synth.py',
                  ROOT / 'tooling/silicon/extract.tcl', magic, netgen,
                  std / 'gds/sg13g2_stdcell.gds', std / 'cdl/sg13g2_stdcell.cdl', setup]
        inputs += sorted(path for path in (pdk / 'libs.tech/magic').rglob('*') if path.is_file())
        report['source_inputs'] = {str(path): sha(path) for path in inputs}

        def invoke(argv, name, stdin=None):
            try:
                record = run(argv, out / (name + '.log'),
                             min(started + 90, time.monotonic() + 20), stdin)
            except CommandFailure as error:
                report['commands'].append(error.record)
                raise
            report['commands'].append(record)

        recipe = (ROOT / 'tooling/silicon/extract.tcl').read_text().replace(
            '    gds read $out/layout.gds', f'    gds read {{{std / "gds/sg13g2_stdcell.gds"}}}')
        script = out / 'extract.tcl'
        script.write_text(f'set out {{{out}}}\nset top sg13g2_inv_1\nset connectivity_only_extraction 1\n' + recipe)
        invoke([str(magic), '-dnull', '-noconsole', '-rcfile',
                str(pdk / 'libs.tech/magic/ihp-sg13g2.magicrc')], 'extract', script)
        original = (out / 'extracted.spice').read_text()
        for name, before, after, expected in (
                ('original', '', '', True),
                ('wrong-width', 'w=0.74u', 'w=0.37u', False),
                ('wrong-bulk', 'M1000 Y A VDD VDD', 'M1000 Y A VDD VSS', False)):
            require(not before or original.count(before) == 1, 'mutation no longer targets real device')
            data = out / (name + '.spice')
            data.write_text(original.replace(before, after) if before else original)
            comparison = out / (name + '.tcl')
            comparison.write_text(f'''set reference [readnet spice {{{std / 'cdl/sg13g2_stdcell.cdl'}}}]
lvs {{{data} sg13g2_inv_1}} [list sg13g2_inv_1 $reference] {{{setup}}} {{{out / (name + '.rpt')}}} -json
''')
            invoke([str(netgen), '-batch', 'source', str(comparison)], name)
            matches = lvs_matches((out / (name + '.rpt')).read_text())
            report['cases'].append({'name': name, 'matches': matches, 'expected': expected,
                                    'report_sha256': sha(out / (name + '.rpt'))})
            require(matches == expected, 'original/device negative comparison differs')
        report['status'] = 'PASS_TRANSISTOR_GEOMETRY_AND_BULK_CONTROLS_ONLY'
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        report['source_seal_equal'] = all(sha(Path(path)) == digest
                                         for path, digest in report.get('source_inputs', {}).items())
        if not report['source_seal_equal']:
            report['status'] = 'FAIL'
        report['seconds'] = time.monotonic() - started
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report.get('error'), report['seconds'])
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
