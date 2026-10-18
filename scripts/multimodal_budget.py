#!/usr/bin/env python3
"""Checked synthetic reference arithmetic and bounded development admission.

This is host-only admission accounting, never a source of sample values or
application policy. A feasible arithmetic budget does not establish controller
throughput, guest mappings, physical RAM or measured consumer performance.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import json
from pathlib import Path

SCHEMA = 'lemma-multimodal-resource-budget/1'
POOL = 32 * 1024 * 1024
# Independent authorities: rows reproduce multiplicities, not asserted totals.
BASE = {
    'eeg': (8, 500, 4), 'ppg': (2, 200, 4), 'fnirs': (16, 2, 20, 4),
    'optical-reference': (16, 20, 4), 'microphones': (2, 48000, 4),
    'motion': (6, 1000, 4), 'pen': (240, 72),
}
OPTICS = {
    'economy': {'eyes': (2, 160, 120, 60, 1), 'face': (320, 240, 15, 1)},
    'stress': {'eyes': (2, 320, 240, 120, 1), 'face': (640, 480, 30, 1)},
}
EXTENSIONS = {'depth-derived': (160, 120, 30, 5), 'flow-events': (4, 250000, 8),
              'flow-correlations': (4, 64, 20, 8)}


def product(factors):
    result = 1
    for value in factors:
        if type(value) is not int or not 0 < value <= (1 << 32):
            raise ValueError('invalid bounded resource factor')
        result *= value
        if (1 << 63) <= result:
            raise ValueError('resource arithmetic overflow')
    return result


def ceil_fraction(value):
    return (value.numerator + value.denominator - 1) // value.denominator


def reference(mode, extensions=False):
    if mode not in OPTICS or type(extensions) is not bool:
        raise ValueError('unsupported workload')
    rows = {name: product(values) for name, values in {**BASE, **OPTICS[mode]}.items()}
    if extensions:
        rows.update({name: product(values) for name, values in EXTENSIONS.items()})
    upstream = sum(rows.values())
    return {'schema': SCHEMA, 'origin': 'SYNTHETIC', 'scope': 'reference arithmetic only',
            'mode': mode, 'extensions': extensions, 'bytes_per_second': rows,
            'upstream_payload_Bps': upstream, 'downstream_pcm_Bps': product((2, 48000, 4)),
            'two_second_payload_bytes': 2 * upstream,
            'fnirs_pairs': {'superficial': 4, 'longer-separation': 12, 'wavelengths': 2,
                            'effective_per_wavelength_channel_Hz': 20}}


def account(mode, extensions, *, window_ms, upstream_bps, downstream_bps, frame_bytes=128,
            payload_bytes=4096, retransmission_percent=10):
    if (type(window_ms) is not int or not 1 <= window_ms <= 2000 or
        any(type(x) is not int or x <= 0 for x in (upstream_bps, downstream_bps, frame_bytes, payload_bytes)) or
        type(retransmission_percent) is not int or not 0 <= retransmission_percent <= 100):
        raise ValueError('invalid resource request')
    value = reference(mode, extensions)
    window = Fraction(window_ms, 1000)
    up, down = value['upstream_payload_Bps'], value['downstream_pcm_Bps']
    # Frame has192-byte provenance/control descriptor, header128, AEAD tag16,
    # link CRC4 and bounded10% retransmit reserve. No encryption double-count.
    overhead = frame_bytes + 192 + 16 + 4
    def wire(payload):
        return ceil_fraction(Fraction(payload) * Fraction(payload_bytes + overhead, payload_bytes) *
                             Fraction(100 + retransmission_percent, 100))
    wire_up, wire_down = wire(up), wire(down)
    optical_source = 640 * 480 * 2 if mode == 'economy' else 1280 * 720 * 2
    ring = ceil_fraction((up + down) * window)
    descriptors = ceil_fraction(Fraction(ring, payload_bytes)) * 192
    # Explicit no-alias windows: prepared/device/completed ownership. Source
    # frames and software crops remain separate, not claimed extra cameras.
    memory = {
        'legacy_notebook_and_service_reserve': 8 * 1024 * 1024,
        'stream_payload_rings': ring, 'ownership_and_provenance_descriptors': descriptors,
        'link_encryption_retransmit_window': ceil_fraction((wire_up + wire_down) * window),
        'source_readout_double_buffer': optical_source,
        'crop_copy_window': ceil_fraction((value['bytes_per_second']['eyes'] + value['bytes_per_second']['face']) * window),
        'inference_tensor_reserve': 4 * 1024 * 1024,
        'raw_tof_histogram_double_buffer': 160 * 120 * 32 * 2 * 2 if extensions else 0,
        'flow_lag_accumulators': 4 * 64 * 8 if extensions else 0,
        'archive_index_reserve': 0, # routine raw retention is disabled
        'replay_state_reserve': 512 * 1024,
    }
    total = sum(memory.values())
    # Bus cost includes writes, consumption, optical copies and downstream DMA.
    bus_Bps = 2 * (up + down) + 2 * (value['bytes_per_second']['eyes'] + value['bytes_per_second']['face'])
    failures = []
    if 8 * wire_up > upstream_bps: failures.append('upstream-wire-capacity')
    if 8 * wire_down > downstream_bps: failures.append('downstream-wire-capacity')
    if POOL < total: failures.append('owned-memory-pool')
    value.update(window_ms=window_ms, wire_upstream_Bps=wire_up, wire_downstream_Bps=wire_down,
                 requested_link={'upstream_bps': upstream_bps, 'downstream_bps': downstream_bps,
                                 'binding': 'supplied accounting ceiling, not a fabricated USB controller'},
                 memory_bytes=memory, owned_pool_bytes=POOL, total_memory_bytes=total,
                 owned_frames=ceil_fraction(Fraction(total, 4096)), bus_payload_service_Bps=bus_Bps,
                 cpu_service_cycles='UNMEASURED', mapping_capacity='UNVERIFIED_FOR_BULK_WORKLOAD',
                 real_time_factor='UNMEASURED', arithmetic_feasible=not failures, rejection_reasons=failures,
                 result='RESOURCE_FEASIBLE_PENDING_EXECUTION' if not failures else 'REJECT',
                 admitted_profile_mode='converter-debug100 only; full reference streams NOT_ADMITTED',
                 raw_retention='disabled', exact_replay='unavailable without authorized retained payloads')
    return value


def main():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--mode', choices=tuple(OPTICS), default='economy')
    p.add_argument('--extensions', action='store_true')
    p.add_argument('--window-ms', type=int, default=100)
    p.add_argument('--upstream-bps', type=int, default=12000000)
    p.add_argument('--downstream-bps', type=int, default=12000000)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    result = account(args.mode, args.extensions, window_ms=args.window_ms,
                     upstream_bps=args.upstream_bps, downstream_bps=args.downstream_bps)
    data = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output:
        if args.output.exists(): p.error('output must be unused')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data)
    else: print(data, end='')
    return 0 if result['arithmetic_feasible'] else 1


if __name__ == '__main__': raise SystemExit(main())
