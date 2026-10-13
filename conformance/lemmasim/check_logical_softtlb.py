#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independent bounded logical SoftTLB sidecar decoder (not whole-state proof).

No QEMU structs, raw host addresses or cache transition implementation are used.
The experiment's exact ordinary machine archive and inactive boundary are bound.
"""
from __future__ import annotations
import argparse, hashlib, json, struct
from pathlib import Path

BINDING = 'lemma-silicon-fast-softtlb/0.1.0'
MAX_BYTES = 64 * 1024 * 1024
MAX_SLOTS = 256 * 1024
U64 = (1 << 64) - 1

class Reader:
    def __init__(self, data): self.data, self.at, self.offsets = data, 0, {}
    def take(self, n):
        if n < 0 or self.at + n > len(self.data): raise ValueError('Truncated sidecar')
        value = self.data[self.at:self.at+n]; self.at += n; return value
    def word(self, label=None):
        if label is not None: self.offsets[label] = self.at
        return struct.unpack('<Q', self.take(8))[0]
    def text(self, label=None):
        n = self.word()
        if n > 1024: raise ValueError('Oversized mapping identity')
        if label is not None: self.offsets[label] = self.at
        b = self.take(n)
        if b'\0' in b: raise ValueError('Embedded identity NUL')
        return b.decode('utf-8', errors='strict')

def decode(path, machine):
    path, machine = Path(path), Path(machine)
    if path.is_symlink() or not path.is_file() or not 160 <= path.stat().st_size <= MAX_BYTES:
        raise ValueError('Unsupported sidecar file')
    data = path.read_bytes()
    if hashlib.sha256(data[:-32]).digest() != data[-32:]: raise ValueError('Sidecar checksum')
    r = Reader(data[:-32])
    if r.take(8) != b'LMTLB01\0' or r.word('schema') != 1 or r.text('binding') != BINDING:
        raise ValueError('Unsupported sidecar schema/binding')
    bound = r.take(32).hex()
    if machine.is_symlink() or not machine.is_file() or not 0 < machine.stat().st_size <= 768*1024*1024:
        raise ValueError('Unsupported machine-state file')
    sum = hashlib.sha256()
    with machine.open('rb') as stream:
        for part in iter(lambda: stream.read(1024*1024), b''): sum.update(part)
    if sum.hexdigest() != bound: raise ValueError('Wrong complete machine-state SHA256')
    boundary = r.word('boundary')
    witness = {name:r.word(name) for name in ['cpu_index','stopped','running','pending_work','halted','interrupt_request','exception_index']}
    if boundary > (1 << 63)-1 or [witness[k] for k in ['cpu_index','stopped','running','pending_work']] != [0,1,0,0]:
        raise ValueError('Unsupported inactive CPU boundary')
    if witness['halted'] > 1 or witness['interrupt_request'] > 0xffffffff or witness['exception_index'] > 0xffffffff:
        raise ValueError('Malformed pending CPU metadata')
    if [r.word(),r.word(),r.word()] != [22,12,5]: raise ValueError('Unsupported MMU/page/entry geometry')
    common = {k:r.word(k) for k in ['dirty','full_flush_count','part_flush_count','elide_flush_count']}
    if common['dirty'] >> 22: raise ValueError('Dirty MMU bits outside declared modes')
    modes, total = [], 0
    def entry(label):
        marker = r.word(label+'.marker')
        if marker == 0: return None
        if marker != 1: raise ValueError('Invalid occupied marker')
        tags = [r.word(label+'.tag'+str(i)) for i in range(3)]
        live = [x for x in tags if x != U64]
        pages = {x & (U64 ^ 4095) for x in live}
        if not live or len(pages) != 1: raise ValueError('Inconsistent comparator pages')
        if any(x & (4095 ^ 0x1c0) for x in live): raise ValueError('Unsupported fast tag flags')
        names = ['phys_addr','attrs','prot','lg_page_size','fill_flags','slow_load','slow_store','slow_code','pte_attrs','shareability','guarded']
        fields = {k:r.word(label+'.'+k) for k in names}
        if fields['phys_addr'] % 4096 or fields['attrs'] > 0xffffffff or fields['prot'] > 7 or not 0 <= fields['lg_page_size'] <= 63:
            raise ValueError('Malformed logical entry fields')
        if any(fields[k] > 255 for k in names[4:]) or fields['guarded'] > 1:
            raise ValueError('Malformed narrow logical entry fields')
        if any(fields[k] & ~31 for k in ['slow_load','slow_store','slow_code']): raise ValueError('Unsupported slow flags')
        mapping = {}
        for k in ['name','type','owner']:
            present = r.word(label+'.mapping.'+k+'.present')
            if present > 1: raise ValueError('Malformed nullable mapping identity')
            mapping[k] = r.text(label+'.mapping.'+k) if present else None
        mapping.update({k:r.word(label+'.mapping.'+k) for k in ['address_space_offset','region_offset','size_low','size_high','readonly','ram','romd','translated_offset']})
        if any(mapping[k] > 1 for k in ['readonly','ram','romd']):
            raise ValueError('Malformed mapping identity')
        mapping['page_topology_sha256'] = r.take(32).hex()
        return {'tags':tags,'virtual_page':next(iter(pages)),**fields,'mapping':mapping}
    for m in range(22):
        label = 'mode'+str(m)
        fields = {k:r.word(label+'.'+k) for k in ['capacity','large_page_addr','large_page_mask','window_begin_ns','window_max_entries','n_used_entries','vindex']}
        n = fields['capacity']; total += n
        if n < 64 or n & (n-1) or total > MAX_SLOTS: raise ValueError('Primary capacity outside declared bound')
        if fields['window_begin_ns'] > boundary or max(fields['window_max_entries'],fields['n_used_entries']) > n:
            raise ValueError('Malformed resize metadata')
        primary = [entry(label+'.primary'+str(i)) for i in range(n)]
        victim = [entry(label+'.victim'+str(i)) for i in range(8)]
        for i, e in enumerate(primary):
            if e is not None and (e['virtual_page'] >> 12) & (n-1) != i:
                raise ValueError('Primary slot comparator index mismatch')
        modes.append({**fields,'primary':primary,'victim':victim})
    if r.at != len(r.data): raise ValueError('Trailing sidecar data')
    return {'schema':1,'binding':BINDING,'archive_sha256':bound,'boundary_ns':boundary,
            'inactive_boundary':witness,'common':common,'modes':modes,'wire_offsets':r.offsets,
            'sidecar_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sidecar',type=Path);p.add_argument('machine',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args(); result=decode(a.sidecar,a.machine)
    text=json.dumps(result,indent=2)+'\n'
    if a.output:
        with a.output.open('x') as stream:stream.write(text)
    else: print(text,end='')
if __name__ == '__main__':main()
