#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Admit the exact unselected327 clock-M3 two-instance AP input to real routing.

The selected padded30 implementation is unchanged. This consumes original
baseline PA, original guides and a separately sealed two-reference correction;
no new PA, GRT, resizer, placement or grid generation is admitted here.
"""
import json
from pathlib import Path
from silicon_enclosure import require
from silicon_synth import ROOT, sha

DIRECTORY = ROOT / 'build/silicon/task009-two-preferred-AP-a1'
SEAL = ROOT / 'build/silicon/task009-two-preferred-AP-seal-a1/result.json'
SEAL_SHA = '94cab20b1e21fad65ad845d7f255885c8e37be3bee37c8d7e1c703ba6132540f'
CANDIDATE_SHA = '9e3a45ccf1980a6e662bfaa69e560c99a0858fdb414848cc922b7e4dc107b5ed'
GUIDES = ROOT / 'build/silicon/task009-capacity-clock3-route-a1/route.guide'
GUIDES_SHA = '3b49b6110badf23a2c163960efb569fc48548af4435dcf2da18089fdb0a4e4f0'
EXPORT = ROOT / 'build/silicon/task009-opendb-access-export-a1/lemma_ap_export.so'
EXPORT_SHA = '2e260331ab2f50eb06b4f2d4cefb0f248ecddeaeaae30ae8c06f9aa5ab68095a'
CORE_SHA = 'ada97e26cd2f192265ed3b217fa00c67b5e009c4ea23b1f7b38f69beacccaaca'

class PrefixComplete(Exception):
    """The bounded actual prefix ended without entering detailed routing."""

def admit(directory):
    directory = Path(directory).resolve()
    require(directory == DIRECTORY and sha(SEAL) == SEAL_SHA, 'exact reviewed two-preference producer/seal required')
    result = json.loads(SEAL.read_text())
    require(result['status'] == 'PASS_SCOPED_TWO_PREFERENCE_METADATA_BINARY_RELATIONS_NEGATIVES_AND_SOURCE_SEAL'
            and result['source_seal_equal'] and not result['selected_layout_changed'], 'source-sealed unselected preference input required')
    for name, digest in result['source_inputs'].items():
        require(sha(Path(name)) == digest, 'preference input differs: ' + name)
    require(sha(directory / 'candidate.odb') == CANDIDATE_SHA and
            sha(GUIDES) == GUIDES_SHA and sha(EXPORT) == EXPORT_SHA, 'candidate/guide/exporter identity')
    require(result['serialization_relation'] == {'AP4_reverse_refs_before': 0,
        'AP4_reverse_refs_appended': [32023, 32330], 'AP4_reverse_vector_offset': 4672028,
        'preferred_word_offsets': [2115620, 2130663], 'other_bytes_identical': True, 'ODB_length_delta': 8}, 'exact two-reference binary relation')
    pinned = Path('/nix/store/pi9m3br8ni97dfybd24lldfa185py07x-source')
    snapshot_source = [pinned / v for v in ('src/drt/src/dr/FlexDR.cpp', 'src/drt/src/TritonRoute.tcl', 'src/drt/src/io/io.cpp', 'src/utl/include/utl/ScopedTemporaryFile.h')]
    require('logger_->debugCheck(DRT, "snapshot", 1)' in snapshot_source[0].read_text() and
            'drt_iter{}.odb' in snapshot_source[0].read_text() and
            '[-snapshot_dir dir]' in snapshot_source[1].read_text(), 'pinned supported closed-iteration snapshot binding')
    return {'geometry': directory / 'candidate.odb', 'metadata': directory / 'metadata.json',
            'guides': GUIDES, 'exporter': EXPORT, 'seal': SEAL,
            'inputs': [SEAL, GUIDES, EXPORT] + snapshot_source + [Path(p) for p in result['source_inputs']]}

def require_recipe(args):
    if getattr(args, 'preferred_access_from', None):
        require(args.capacity_launch_buffer_from and args.routed_eco_from and
                args.clock_min_routing_layer == 'Metal3' and args.detail_route_iterations == 8 and
                args.host_memory_gib == 6 and not args.selected_implementation,
                'retained two-preference routing requires exact unselected327 clockM3/8iter/default6GiB source')
    require(not getattr(args, 'preferred_access_preflight_only', False) or
            getattr(args, 'preferred_access_from', None), 'prefix-only mode requires the exact retained access input')

def require_tcl(text):
    """Consequential guard on the actual consumed legacy-compatible Tcl branch."""
    snippets = [
        'if {[info exists retained_access_guides]} {\n    read_guides $retained_access_guides',
        'file copy $retained_access_guides $out/route.guide',
        '} else {\n    global_route -guide_file $out/route.guide',
        'load $retained_access_exporter Lemmaap',
        'if {$stage eq "before-route"} {',
        'if {$expected ne $actual} {error "Retained original AP metadata/pattern/preference changed"}',
        'exec $retained_access_python $retained_access_writer_check --before $retained_access_metadata --after $out/preferred-$stage.json --output $out/preferred-writer-relation.json',
        'lemma_check_retained_access before-route',
        'lappend retained_access_route_flags -no_pin_access',
        'set_debug_level DRT snapshot 1',
        'detailed_route_debug -snapshot_dir $out/route-snapshots',
        'detailed_route {*}$retained_access_route_flags -output_drc $out/route.drc -drc_report_iter_step 1',
        'if {[info exists retained_access_guides]} {lemma_check_retained_access after-route}',
        'if {[info exists preferred_access_probe_only] && $preferred_access_probe_only == 1}',
    ]
    require(all(text.count(s) == 1 for s in snippets), 'retained preference/guide/no-PA/snapshot Tcl consumer changed')
    branch = text[text.index('if {[info exists retained_access_guides]} {\n    read_guides'):text.index('if {![info exists detail_route_iterations]}')]
    require(branch.count('global_route ') == 1 and branch.index('} else {') < branch.index('global_route '), 'retained branch cannot recompute guides')
    require('pin_access ' not in text and text.count('-no_pin_access') == 1, 'retained route must not regenerate or disable access data')

def check_final_access(output, admitted):
    """Final public records and AP4 reverse refs must retain the admitted input."""
    import struct
    output = Path(output)
    from silicon_access_writer import relation
    require((output / 'preferred-before-route.json').read_bytes() == admitted['metadata'].read_bytes(),
            'actual pre-route AP/pattern/preference records changed')
    writer = relation(json.loads(admitted['metadata'].read_text()),
                      json.loads((output / 'preferred-after-route.json').read_text()))
    require(writer == json.loads((output / 'preferred-writer-relation.json').read_text()), 'actual final writer relation differs')
    ids = json.loads((DIRECTORY / 'apply.json').read_text())['AP4_owner_serialization_ids']
    prefix = struct.pack('<iiIIIII', 2880, 820, *(ids[k] for k in ('layer_id', 'lib_id', 'master_id', 'mpin_id', 'bpin_id'))) + bytes([0, 0, 0, 0, 1, 0])
    records = []
    for path in (admitted['geometry'], output / 'routed.odb'):
        raw = path.read_bytes()
        require(raw.count(prefix) == 1, 'ambiguous final AP4 record')
        at = raw.index(prefix) + len(prefix)
        require(struct.unpack_from('<I', raw, at)[0] == 2, 'final AP4 reverse count')
        record = raw[at:at + 12]
        require(record == struct.pack('<III', 2, 32023, 32330), 'final AP4 reverse ITerm refs')
        records.append(record)
    require(records[0] == records[1], 'router changed reverse references')
    return {'status': 'PASS_ORIGINAL_AP_METADATA_PATTERNS_ALL_PREFERENCES_AND_AP4_REVERSE_REFS_PRESERVED',
            'APs': 11123, 'patterns': 495, 'ITerms': 45104, 'BPins': 668,
            'pinned_writer_relation': writer,
            'input_ODB_sha256': CANDIDATE_SHA, 'final_ODB_sha256': sha(output / 'routed.odb')}
