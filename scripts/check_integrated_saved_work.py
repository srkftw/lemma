#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independent offline linked-index/raw-work observation for a canonical stroke.

Page-header identity can remain unchanged after Save. The page index must
publish the new immutable raw chunk, whose complete nine-word samples must
match the declared controller stimulus. No bytes enter the running guest.
"""
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'conformance/lemmasim'))
from store_oracle import recover
from inspect_notebook import inspect_page,MAGIC


def qualify(before_bytes,after_bytes,samples,namespace=1,page=1):
    if len(samples)!=3 or any(len(row)!=9 for row in samples):
        raise ValueError('three complete raw samples required')
    _,frontier,before=recover(before_bytes)
    _,committed,after=recover(after_bytes)
    root=(namespace,1);index=(namespace,256+page)
    if root not in before or root not in after or index not in before or index not in after:
        raise ValueError('committed page root/index missing')
    old=inspect_page(before[index].payload,index[1]);new=inspect_page(after[index].payload,index[1])
    if committed<frontier+3 or after[index].payload==before[index].payload:
        raise ValueError('Save lacks a new committed linked index')
    if len(new)!=len(old)+1 or new[:-1]!=old:
        raise ValueError('Save did not preserve and append one indexed stroke')
    object_id,stroke,visible=new[-1];raw=after.get((namespace,object_id))
    if raw is None or not visible or (namespace,object_id) in before:
        raise ValueError('new visible immutable raw artifact missing')
    payload=raw.payload
    if len(payload)!=128+len(samples)*72:
        raise ValueError('raw artifact length differs from declared sample count')
    header=struct.unpack_from('<16Q',payload)
    if header[:5]!=(MAGIC,1,3,page,stroke) or header[6]!=len(samples):
        raise ValueError('raw artifact identity/count differs from index')
    actual=[struct.unpack_from('<9Q',payload,128+i*72) for i in range(len(samples))]
    if actual!=[tuple(row) for row in samples]:
        raise ValueError('complete raw sample provenance differs from original stimulus')
    if not frontier<raw.sequence<after[index].sequence<after[root].sequence<=committed:
        raise ValueError('artifact-before-index-before-root commit order missing')
    for key,record in before.items():
        if key not in (root,index) and (key not in after or after[key].payload!=record.payload):
            raise ValueError('prior immutable work changed')
    return {'frontier_before':frontier,'frontier_after':committed,
            'namespace':namespace,'page':page,'index_object':index[1],
            'raw_object':object_id,'stroke':stroke,'raw_samples':len(actual),
            'complete_sample_fields_equal':True,'artifact_before_reference':True,
            'index_changed':True,'root_header_changed':after[root].payload!=before[root].payload,
            'prior_work_preserved':True,'scope':'independent offline durable linked work; no pixel or reset observation'}
