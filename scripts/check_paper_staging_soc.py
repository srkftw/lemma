#!/usr/bin/env python3
"""Literal full-SoC Paper staging/decode check; no CPU or guest qualification.

The actual motherboard and controllers execute every handshake. The explicitly
replaced compute block supplies only bounded raw MMIO stimuli. Canonical pixel
capacity is retained, and the pixel oracle is independent of controller state.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import silicon_profile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_owned(argv, log, timeout):
    child = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True)
    try:
        code = child.wait(timeout=timeout)
        if code:
            raise subprocess.CalledProcessError(code, argv)
    except BaseException:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['lemma-silicon-dev/' + n for n in
                        ('0.6.0', '0.7.0', '0.8.0', '0.9.0')], required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 2 or not 30 <= args.timeout <= 600:
        parser.error('literal check permits1..2 jobs and30..600 seconds')
    out = args.work_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    result = {'schema': 'lemma-paper-staging-soc-check/1', 'status': 'FAIL',
              'profile': args.profile, 'scope': __doc__, 'commands': []}
    try:
        profile = silicon_profile.profile(args.profile)
        fields = silicon_profile.constants(profile)
        if fields['width'] != 1650 or fields['height'] != 2200:
            raise ValueError('canonical display capacity changed')
        modern = args.profile in ('lemma-silicon-dev/0.8.0', 'lemma-silicon-dev/0.9.0')
        if (fields['paper_version'], fields['paper_stage_offset']) != ((2, 3584) if modern else (1, 2048)):
            raise ValueError('staging version differs from declared binding')
        package = 'package lemma_silicon_binding;\n' + ''.join(
            f"localparam logic[63:0] {key.upper()}=64'h{value:016x};\n"
            for key, value in fields.items()) + 'endpackage\n'
        binding = out / 'binding.sv'
        binding.write_text(package)
        # Consume the real port declaration; this is a raw test fixture,
        # explicitly not a replacement CPU implementation or guest image.
        compute = ROOT / 'sim/rtl/lemma_compute.sv'
        source = compute.read_text()
        header = source[source.index('module lemma_compute'):source.index(');') + 2]
        header = header.replace(' import cvw::*;', '')
        stimulus = out / 'compute_bus_stimulus.sv'
        stimulus.write_text(header + '''
assign dev_valid=paper_collision_tb.valid;assign dev_write=paper_collision_tb.write;
assign dev_addr=paper_collision_tb.address;assign dev_size=paper_collision_tb.size;
assign dev_wdata=paper_collision_tb.data;
assign mem_valid=0;assign mem_write=0;assign mem_addr=0;assign mem_wdata=0;assign mem_strb=0;
assign uart_rx_ready=0;assign uart_tx_valid=0;assign uart_tx_data=0;
assign finish_valid=0;assign finish_code=0;assign timer_ticks=0;
assign debug_pc=0;assign debug_privilege=0;assign debug_retire=0;assign debug_trap=0;assign debug_cause=0;
endmodule
''')
        controllers = [ROOT / 'sim/rtl' / (name + '.sv') for name in
                       ('lemma_soc', 'lemma_pen', 'lemma_paper', 'lemma_block',
                        'lemma_power', 'lemma_ble_packet', 'lemma_usb_device',
                        'lemma_boot_nv', 'lemma_register_ram')]
        test = ROOT / 'tests/silicon/paper_staging_soc_tb.sv'
        inputs = [compute, test, silicon_profile.profile_path(args.profile),
                  ROOT / 'scripts/silicon_profile.py', Path(__file__), *controllers]
        result['inputs'] = {str(path.relative_to(ROOT)): sha(path) for path in inputs}
        result['generated_binding_sha256'] = sha(binding)
        result['tool'] = subprocess.check_output(['verilator', '--version'], text=True, timeout=10).strip()
        argv = ['verilator', '--binary', '--timing', '--top-module', 'paper_collision_tb',
                '-Wno-fatal', '-Wno-PINMISSING', '-j', str(args.jobs), '--Mdir', str(out / 'obj'),
                str(binding), str(stimulus), *map(str, controllers), str(test)]
        result['commands'].append(argv)
        with (out / 'build.log').open('w') as log:
            run_owned(argv, log, args.timeout)
        binary = out / 'obj/Vpaper_collision_tb'
        result['binary_sha256'] = sha(binary)
        argv = [str(binary)]
        result['commands'].append(argv)
        with (out / 'run.log').open('w') as log:
            run_owned(argv, log, 30)
        marker = ('PASS full canonical clear; actual512B' if modern else 'PASS retained legacy collision')
        if marker not in (out / 'run.log').read_text():
            raise ValueError('literal test did not report its declared scenario')
        if any(sha(ROOT / path) != digest for path, digest in result['inputs'].items()):
            raise ValueError('consumed sources changed during literal check')
        result['status'] = 'PASS'
        result['behavior'] = 'modern staging and1024 exact pixels' if modern else 'retained collision reproduction'
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        result['host_seconds'] = time.monotonic() - started
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'host_seconds': result['host_seconds']}))


if __name__ == '__main__':
    main()
