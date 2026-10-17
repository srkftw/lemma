#!/usr/bin/env python3
"""Observe real ordinary ByteArray IR/LLVM/RV64 component artifacts.

This is a compiler/runtime component qualification, never an isolated execution
receipt or a mathematical oracle. It has no production configuration grant.
"""
from __future__ import annotations
import argparse
import collections
import copy
import hashlib
import json
import re
import struct
import sys
from pathlib import Path
from core0_common import Core0Error, load_json, sha256, write_json

ROOT = 'Lemma.Mathematics.ManagedByteSubmission.compareFiveSix'
PREFIX = 'Lemma.Mathematics.ManagedByteSubmission.'
GENERATED = ROOT + '.__lemma_managed_bytes_v04.'
RUNTIME = 'Lemma.User.Runtime.ManagedBytes.'
IR_DIGEST = '7b8e3c536b5668ae2f813b4885507bac29959064b9e9755dfe24d0912ec1b31c'
# Complete reviewed genuine component closure, ABI, attributes and optimized
# bodies; these pins grant no production configuration or checker identity.
BODY_DIGESTS = {False:'24f74b98e7d81db54e158347df283126365a01d9b2cbea7a644058245049e7cf',
                True:'99c45aea5ba9c9ca3b9bde24e98c65dfaf0fabfebb47d3eb0cac9584e1c1faf0'}
TEXT_DIGEST = 'c34e5126ae3f4be758ad0999a2b2fc15e06e4a6eb15d283c4bd7e9f07fd1d23e'


def require(condition, message):
    if not condition:
        raise Core0Error(message)


def names(text):
    rows = text.splitlines()
    result = {}
    for row in rows:
        match = re.fullmatch(r'source=([^;]+);llvm=([A-Za-z0-9_]+)', row)
        require(match is not None, 'Malformed real source/symbol row')
        require(match[1] not in result and match[2] not in result.values(), 'Duplicate source/symbol')
        result[match[1]] = match[2]
    require(len(result) == 71 and ROOT in {source.split('.__lemma_managed_bytes_v04.')[0] for source in result},
            'Real component source inventory differs')
    return result


def definitions(ir):
    rows = list(re.finditer(r'^define[^\n]*@([A-Za-z0-9_]+)\([^\n]*\)[^\n]*\{\n(.*?)^\}', ir, re.M | re.S))
    result = {row[1]: row[2] for row in rows}
    require(len(rows) == len(result) and len(rows) > 0, 'LLVM definition inventory empty or duplicated')
    return result


def validate_catalog(catalog):
    require(set(catalog) == {'contract', 'profile', 'compiler_revision', 'root', 'maximum_payload',
                            'allocator', 'slots', 'genuine_ir', 'actual_ir_mutations'}, 'Component catalog fields differ')
    require(catalog['contract'] == 'lemma-managed-bytes-v1' and catalog['profile'] == 'core0-user-v0.4' and
            catalog['compiler_revision'] == '5045d0056413266e57c625dcd7c365b10e377c52' and
            catalog['root'] == ROOT and catalog['maximum_payload'] == 48 and catalog['slots'] == 31 and
            catalog['allocator'] == 'lemma-owned-arena-v1', 'Component source/profile/runtime contract differs')
    rows = catalog['genuine_ir']
    require(isinstance(rows, list) and len(rows) == 5 and
            {row.get('source') for row in rows} == {PREFIX + suffix for suffix in
                ('empty', 'appendWord', 'readWord', 'payload', 'compareFiveSix')} and
            all(set(row) == {'source', 'genuine_ir'} and isinstance(row['genuine_ir'], str) for row in rows),
            'Ordinary upstream IR closure differs')
    digest = hashlib.sha256(json.dumps(sorted(rows, key=lambda row: row['source']),
                                      sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    require(digest == IR_DIGEST, 'Genuine source ownership/primitive/call IR differs')
    mutations = catalog['actual_ir_mutations']
    require(isinstance(mutations, list) and len(mutations) == 4 and
            {row.get('mutation') for row in mutations} == {1, 2, 3, 4} and
            all(isinstance(row.get('actual_changed_nodes'), int) and row['actual_changed_nodes'] > 0 and
                isinstance(row.get('rejected'), str) and row['rejected'] for row in mutations),
            'Real compiler IR rejection corpus missing')


def validate_llvm(ir, mapping, optimized):
    actual = definitions(ir)
    require(set(actual) == set(mapping.values()), 'LLVM differs from complete real source inventory')
    declarations = re.findall(r'^declare [^\n]*@([^ (]+)', ir, re.M)
    require(declarations == ['lemma_exec_syscall'], 'Component acquired unknown external/helper declaration')
    calls = re.findall(r'\bcall[^@\n]*@([^ (]+)\(', ir)
    require(set(calls) <= set(actual) | {'lemma_exec_syscall'}, 'Component acquired foreign runtime call')
    require('riscv64-unknown-unknown-elf' in ir, 'LLVM target triple differs')
    reverse = {symbol: source for source, symbol in mapping.items()}
    counts = {
        'readWord': {RUNTIME+'natural': 8, RUNTIME+'get': 8},
        'appendWord': {RUNTIME+'push': 8},
        'empty': {RUNTIME+'natural': 1, RUNTIME+'emptyWithCapacity': 1},
        'payload': {GENERATED+PREFIX+'empty': 1, GENERATED+PREFIX+'appendWord': 2},
        'compareFiveSix': {GENERATED+PREFIX+'payload': 1, GENERATED+PREFIX+'readWord': 2,
                          'Lemma.User.Runtime.Arena.release': 2 if optimized else 3},
    }
    observed = {}
    for suffix, expected in counts.items():
        source = GENERATED + PREFIX + suffix
        body = actual[mapping[source]]
        require(not re.search(r'\b(load|store|alloca|getelementptr|inttoptr|ptrtoint)\b', body),
                'Ordinary ByteArray source bypassed checked runtime')
        counted = collections.Counter(reverse.get(call, call) for call in
                                      re.findall(r'\bcall[^@\n]*@([^ (]+)\(', body))
        require(dict(counted) == expected, 'Genuine ByteArray primitive/call/reclamation inventory differs: '+suffix)
        observed[suffix] = dict(counted)
    for scalar, expected in [('cookie', 0x3159544252414d4c), ('maximum', 48)]:
        require(re.search(r'\bret i64 '+str(expected)+r'\b', actual[mapping[RUNTIME+scalar]]) is not None,
                'Real byte object layout constant differs')
    alias = 'Lemma.Compiler.Test.ManagedBytes.alias2.__lemma_managed_bytes_v04.Lemma.Compiler.Test.ManagedBytes.alias'
    alias_body = actual[mapping[alias]]
    require(len(re.findall(r'\bcall[^@\n]*@'+re.escape(mapping[RUNTIME+'retain'])+r'\(', alias_body)) == 1,
            'Actual source alias omitted real reference retain')
    require(len(re.findall(r'\bcall[^@\n]*@'+re.escape(mapping['Lemma.User.Runtime.Arena.release'])+r'\(', alias_body)) == (7 if optimized else 8),
            'Actual success/failure cleanup reference accounting differs')
    complete = {row[1]:row[0] for row in re.finditer(r'^define[^\n]*@([A-Za-z0-9_]+)\([^\n]*\)[^\n]*\{\n(.*?)^\}',ir,re.M|re.S)}
    rows = []
    for source,symbol in sorted(mapping.items()):
        body = complete[symbol]
        for original,name in sorted(mapping.items(),key=lambda row:-len(row[1])):
            body = re.sub(r'@'+re.escape(name)+r'(?=[ (])','@'+original,body)
        body = '\n'.join(re.sub(r';[^\n]*','',line).strip() for line in body.splitlines()
                         if re.sub(r';[^\n]*','',line).strip())
        rows.append([source,body])
    attributes = re.findall(r'^attributes #[^\n]+$',ir,re.M)
    digest = hashlib.sha256(json.dumps([rows,attributes],separators=(',',':')).encode()).hexdigest()
    require(digest == BODY_DIGESTS[optimized], 'Complete emitted component source/ABI/status/lifetime body differs')
    return {'optimized': optimized, 'generated_calls': observed, 'source_definitions': len(actual),
            'complete_emitted_body_sha256':digest}


def validate_object(data, mapping):
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01', 'Missing or incompatible RV64 ELF')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    require(header[1:4] == (1, 243, 1) and header[7] == 0 and header[8] == 64 and
            header[11] == 64 and 0 < header[12] <= 16 and header[13] < header[12],
            'ELF object architecture/softfloat/section header differs')
    offset, size, count, string_index = header[6], header[11], header[12], header[13]
    require(offset + size*count <= len(data), 'Truncated ELF sections')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset + i*size) for i in range(count)]
    def contents(section):
        require(section[4]+section[5] <= len(data), 'Truncated ELF section bytes')
        return data[section[4]:section[4]+section[5]]
    table = contents(sections[string_index])
    def string(table, index):
        require(index < len(table) and b'\0' in table[index:], 'Invalid ELF string index')
        return table[index:].split(b'\0', 1)[0].decode('ascii')
    named = {string(table, section[0]): section for section in sections}
    require(set(named) == {'', '.strtab', '.text', '.rela.text', '.rodata.cst8',
                          '.note.GNU-stack', '.riscv.attributes', '.symtab'}, 'Unexpected object section/runtime data')
    require(named['.text'][1:3] == (1, 6) and named['.text'][5] > 0 and named['.text'][5] % 4 == 0,
            'RV64IM code section empty or flags/alignment differ')
    require(hashlib.sha256(contents(named['.text'])).hexdigest() == TEXT_DIGEST,
            'Real component machine-code body differs')
    require(named['.rodata.cst8'][1:3] == (1, 18) and named['.rodata.cst8'][9] == 8,
            'Exact LLVM merged constant pool flags/width differ')
    pool = contents(named['.rodata.cst8'])
    require(len(pool) == 40 and [struct.unpack_from('<Q', pool, i)[0] for i in range(0,40,8)] ==
            [0x3159544252414d4c,0x31414e4552414d4c,0x3159544252414d4c,0x31414e4552414d4c,0x3159544252414d4c],
            'Object byte/Arena cookie constants differ')
    attributes = contents(named['.riscv.attributes'])
    require(b'rv64i2p1_m2p0_zmmul1p0\0' in attributes, 'Actual object ISA attributes differ')
    symbols = named['.symtab']; require(symbols[9] == 24 and symbols[5] % 24 == 0 and symbols[6] < count,
                                       'Malformed real object symbol table')
    strings = contents(sections[symbols[6]])
    globals_ = set(); undefined = set(); all_symbols = []
    for i in range(0,symbols[5],24):
        name,info,other,index,value,length = struct.unpack_from('<IBBHQQ', data, symbols[4]+i)
        label = string(strings,name)
        all_symbols.append(label)
        if info >> 4 == 1:
            if index == 0: undefined.add(label)
            else:
                require(info & 15 == 2 and index == sections.index(named['.text']) and
                        value+length <= named['.text'][5] and length > 0,
                        'Object global is not genuine bounded code')
                globals_.add(label)
    require(globals_ == set(mapping.values()) and undefined == {'lemma_exec_syscall'},
            'Object linked-source/undefined runtime inventory differs')
    rela = named['.rela.text']; require(rela[9] == 24 and rela[5] % 24 == 0, 'Malformed object relocations')
    for i in range(0,rela[5],24):
        at,info,addend = struct.unpack_from('<QQq', data, rela[4]+i)
        symbol,kind = info >> 32, info & 0xffffffff
        require(at < named['.text'][5] and symbol < len(all_symbols) and addend == 0,
                'Object relocation escaped actual code/source bound')
        label = all_symbols[symbol]
        require((kind == 19 and label in globals_ | undefined) or
                (kind in (26,27) and re.fullmatch(r'\.LCPI[0-9]+_0', label)),
                'Unexpected helper/jump-table/object relocation')
    return {'architecture':'RV64IM/softfloat', 'defined_source_functions':len(globals_),
            'undefined_boundary':sorted(undefined), 'text_bytes':named['.text'][5], 'cookie_pool_bytes':len(pool)}


def check(directory, output):
    require(not output.exists(), 'Output already exists')
    catalog = load_json(directory/'catalog.json')
    mapping = names((directory/'symbols.txt').read_text())
    pre = (directory/'program.ll').read_text(); post = (directory/'program.opt.ll').read_text()
    binary = (directory/'program.o').read_bytes()
    validate_catalog(catalog)
    pre_receipt = validate_llvm(pre,mapping,False); post_receipt = validate_llvm(post,mapping,True)
    object_receipt = validate_object(binary,mapping)
    negatives = []
    def rejects(label, fn):
        try: fn()
        except (Core0Error,ValueError,struct.error,KeyError) as error:
            negatives.append({'name':label,'error':str(error)}); return
        raise Core0Error('Actual corruption admitted: '+label)
    for field,value in [('profile','core0-user-v0.3'),('slots',32),('maximum_payload',49)]:
        changed = copy.deepcopy(catalog); changed[field] = value
        rejects('wrong_'+field,lambda changed=changed: validate_catalog(changed))
    changed = copy.deepcopy(catalog); changed['genuine_ir'][0]['genuine_ir'] += '\ninc invented;'
    rejects('changed_genuine_ir',lambda:validate_catalog(changed))
    for stage,ir,optimized in [('pre',pre,False),('post',post,True)]:
        for label,source,target in [('cookie',RUNTIME+'cookie','ret i64 '+str(0x3159544252414d4c)),
                                    ('maximum',RUNTIME+'maximum','ret i64 48')]:
            symbol = mapping[source]
            body = definitions(ir)[symbol]
            require(target in body,'Actual constant mutation anchor absent')
            changed_body = body.replace(target,target+'0',1)
            changed = ir.replace(body,changed_body,1)
            rejects(stage+'_'+label,lambda changed=changed,optimized=optimized:validate_llvm(changed,mapping,optimized))
        changed = ir.replace('@'+mapping[RUNTIME+'retain']+'(', '@foreign_retain(',1)
        require(changed != ir,'Actual retain mutation anchor absent')
        rejects(stage+'_foreign_retain',lambda changed=changed,optimized=optimized:validate_llvm(changed,mapping,optimized))
    object_header = struct.unpack_from('<16sHHIQQQIHHHHHH',binary)
    text_section = struct.unpack_from('<IIQQQQIIQQ',binary,object_header[6]+2*64)
    code_at = text_section[4]
    changed_code = binary[:code_at]+b'\0\0\0\0'+binary[code_at+4:]
    for label,data in [('truncated_object',binary[:63]),('wrong_machine',binary[:18]+b'\x3e\0'+binary[20:]),
                       ('changed_machine_code',changed_code),
                       ('wrong_cookie',binary.replace(struct.pack('<Q',0x3159544252414d4c),struct.pack('<Q',0x3159544252414d4d),1))]:
        require(data != binary,'Actual object corruption anchor absent')
        rejects(label,lambda data=data:validate_object(data,mapping))
    write_json(output, {'status':'PASS','scope':'Genuine ordinary ByteArray/checked LLVM/RV64 component and real-runtime dependency inventory; no linked isolated execution or trusted implementation grant',
                        'inputs':{name:sha256(directory/name) for name in ('catalog.json','genuine-ir.json','program.ll','program.opt.ll','program.o','symbols.txt')},
                        'pre':pre_receipt,'post':post_receipt,'object':object_receipt,'actual_artifact_negatives':negatives})
    print('MANAGED_BYTES_COMPONENT:PASS',len(negatives),'actual artifact corruptions rejected; isolated execution separate')


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--directory',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); check(args.directory,args.output)

if __name__ == '__main__':
    try:main()
    except (Core0Error,OSError,ValueError,struct.error,KeyError) as error:
        print('MANAGED_BYTES_COMPONENT:FAIL',error,file=sys.stderr); raise SystemExit(1)
