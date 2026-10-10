"""Closed artifact provenance for LemmaSim's bounded scalar literal lookups.

This inspects real LLVM and object bytes. It is not target policy or a compiler
correctness proof. Historical profiles continue through their original auditor.
"""
from __future__ import annotations
import re
import struct
import hashlib
from core0_common import Core0Error

CONFIGURATIONS = {'lemmasim-bringup', 'lemmasim-notebook', 'lemmasim-initialize', 'lemmasim-isolation-development'}
DTB_LITERALS = {
    1: '', 2: 'cpus', 3: 'soc', 4: 'lemma-paper@10010000', 5: 'lemma-pen@10011000',
    6: 'virtio_mmio@10001000', 7: 'interrupt-controller@c000000', 8: 'clint@2000000',
    9: 'serial@10000000', 10: 'rtc@101000',
    **{code: f'virtio_mmio@1000{code-9}000' for code in range(11,18)},
    32: 'compatible', 33: 'reg', 34: 'interrupts', 35: 'interrupt-parent',
    36: 'phandle', 37: 'timebase-frequency', 38: 'lemma,abi-version',
    39: 'lemma,width', 40: 'lemma,height', 41: 'lemma,max-x', 42: 'lemma,max-y',
    43: 'lemma,pressure-max', 44: 'lemma,descriptor', 45: '#address-cells',
    46: '#size-cells', 47: '#interrupt-cells', 48: 'riscv,ndev',
    49: 'interrupt-controller', 50: 'interrupts-extended', 51: 'clock-frequency',
    52: 'ranges', 64: 'lemma,paper-v1', 65: 'lemma,pen-v1', 66: 'virtio,mmio',
    67: 'sifive,plic-1.0.0\0riscv,plic0', 68: 'sifive,clint0\0riscv,clint0',
    69: 'ns16550a', 70: 'google,goldfish-rtc', 71: 'simple-bus',
}
DTB_BYTES = {code: value.encode('ascii') + b'\0' for code,value in DTB_LITERALS.items()}
WORD_CODES = [4,5,6,7,*range(11,18),37,38,43,49,50,67,68,70]
PREFIX = 'Lemma.Platform.LemmaSim.'
# Independent visible rows for the guest-authored bounded font. These are
# packed here rather than imported from the production Lean lookup.
FONT_ROWS = {
    'A':'010101111101101', 'D':'110101101101110', 'E':'111100110100111',
    'F':'111100110100100', 'G':'111100101101111', 'H':'101101111101101',
    'I':'111010010010111', 'L':'100100100100111', 'N':'101111111111101',
    'O':'111101101101111', 'P':'111101111100100', 'R':'110101110101101',
    'S':'111100111001111', 'U':'101101101101111', 'V':'101101101101010',
    'W':'101101101111111', 'Y':'101101010010010', '0':'111101101101111',
    '1':'010110010010111', '2':'111001111100111', '3':'111001111001111',
    '4':'101101111001001', '5':'111100111001111', '6':'111100111101111',
    '7':'111001010010010', '8':'111101111101111', '9':'111101111001111',
}

def canonical_specs():
    lengths = [len(DTB_BYTES.get(code,b'')) for code in range(1,72)]
    words = [list(struct.unpack('<' + str((len(DTB_BYTES[code])+7)//8) + 'Q',
                               DTB_BYTES[code].ljust((len(DTB_BYTES[code])+7)//8*8,b'\0')))
             for code in WORD_CODES]
    fields = [0]*32
    for key,value in {0:1280132179,1:1,2:256,4:0x80000000,5:0x8000000,
       6:0x82000000,7:0x2000000,8:10000000,9:0x10010000,10:4096,11:12,
       12:0x10011000,13:4096,14:13,15:0x10001000,16:4096,17:1,
       22:0x2000000,23:0xc000000,24:0x10000000,25:0x101000,
       28:0x80000000,29:0x2000000,30:0x87e00000,31:0x200000}.items():
        fields[key]=value
    letters=[int(FONT_ROWS[chr(code)],2) if chr(code) in FONT_ROWS else 0
             for code in range(48,90)]
    return {
      PREFIX+'DescriptorDTB.literalLength': ('kernel',['u64'],[],[lengths]),
      PREFIX+'DescriptorDTB.literalWord': ('kernel',['u64','u64'],[],words),
      PREFIX+'DescriptorDTB.requiredFlags': ('kernel',['u64'],[],[[255,255,15,1011,515,31]]),
      PREFIX+'DescriptorDTB.expectedIRQ': ('kernel',['u64'],[],[[12,13,1,None,None,10,11]]),
      PREFIX+'DescriptorDTB.expectedBase': ('kernel',['u64'],[],[[0x10010000,0x10011000,0x10001000,0xc000000,0x2000000,0x10000000,0x101000]]),
      PREFIX+'DescriptorDTB.expectedSpan': ('kernel',['u64'],[],[[0x600000,0x10000,0x100]]),
      PREFIX+'Descriptor.expected': ('kernel',['u64'],[],[fields]),
      'Lemma.Ink.Surface.letter': ('user',['u64'],[],[letters]),
      'Lemma.Applications.Notebook.statusCharacter': ('user',['u64']*5,[],
             [list(map(ord,text)) for text in ['SAVED','PENDING','FAILED','READ ONLY']]),
    }

# Closed normalized bodies of the pinned optimizer's four hardware primitives.
# Their pre-optimization range/alignment checks are also inspected below; these
# fingerprints pin the otherwise complex optimized pointer-PHI/mask transform.
DEVICE_BODY_DIGESTS = {
 'read64': ('a02c03847558e4154b49e8fae68d6bbdbe35380b90d9c2a79cfa3d9c819cb474', 'ea81725512b4c63280c993cebbd3f81b0cf771f26f1457151fc47aac47c63ac9'),
 'read32': ('80c06eeb898a093c0894371838b30c02f4853c5b2ba13ccd747ca846eb347eef', 'cc6cf56426abe421df95ac1d4800f3f5cb8c554bf03a35eca4cefe855a079b89'),
 'write32': ('a9c450a0bbdc45f0dafe60fec3e5a9bb0133ad2ed3f138569115f09e8c3814ba', '7ca1f1478a316664648ce52b96ddb6cf681e578c99930006cf0ae5501a66ff75'),
 'write64': ('f80d937bfcae448dba30e2ec6b51eaa9d76db6b2ff8544366f91ed798cd2f6dc', 'cc11d117f7e5d9a281b2091def205363f37ea2de68e8ead8475c67d098da4229'),
}

def validate_devices(ir: str, unit: dict, optimized: bool) -> tuple[set[int],list[dict]]:
    from audit_kernel import _ir_definition_body, _line_functions
    if unit.get('configuration') not in CONFIGURATIONS: return set(),[]
    if unit['role']!='kernel':
        if any(row['stable_id'].startswith('lemmasim.device-') for row in unit['used_execution_ops']):
            raise Core0Error('Lemmasim hardware operation reached user authority')
        return set(),[]
    sites=set();observed=[];owners=_line_functions(ir.splitlines())
    for row in unit['functions']:
        if not row['source'].startswith(PREFIX+'IO.'): continue
        operation=row['source'].rsplit('.',1)[1]
        if operation not in DEVICE_BODY_DIGESTS: raise Core0Error('Unknown Lemmasim hardware source')
        write=operation.startswith('write');bits=int(operation[-2:]);width=bits//8
        if row['args']!=(['u64','u64'] if write else ['u64']) or row['effects']!=['checked-access','mmio-write' if write else 'mmio-read','io-order']:
            raise Core0Error('Lemmasim hardware source signature/effects differs')
        body='\n'.join(line.split(';',1)[0].strip() for line in _ir_definition_body(ir,row['symbol']).splitlines() if line.split(';',1)[0].strip())
        if not optimized:
            regions=[(0x10001000,0x10001200),(0xc000004,0xc000038),(0xc002080,0xc002084),(0xc201000,0xc201008)] if width==4 else [(0x10010000,0x10011000),(0x10011000,0x10012000)]
            lower=[int(value) for value in re.findall(r'icmp uge i64 %arg0, (\d+)',body)]
            upper=[int(value) for value in re.findall(r'icmp ule i64 %arg0, (\d+)',body)]
            if lower!=[start for start,end in regions] or upper!=[end-width for start,end in regions] or len(re.findall(r'and i64 %arg0, '+str(width-1)+r'$',body,re.M))!=1:
                raise Core0Error('Lemmasim device primitive range/alignment authority differs')
        digest=hashlib.sha256(body.encode()).hexdigest()
        if digest!=DEVICE_BODY_DIGESTS[operation][int(optimized)]:
            raise Core0Error('Lemmasim device primitive closed guard/pointer/fence/result CFG differs: '+operation)
        located={i for i,line in enumerate(ir.splitlines()) if owners[i]==row['symbol'] and re.search(r'\b(?:load|store) volatile i'+str(bits)+r'\b',line)}
        if len(located)!=(1 if optimized else 4 if width==4 else 2):
            raise Core0Error('Lemmasim device primitive volatile access inventory differs')
        sites|=located;observed.append(dict(source=row['source'],function=row['symbol'],width_bytes=width,
             direction='write' if write else 'read',access_sites=len(located),body_sha256=digest,
             optimized=optimized,scope='closed pinned lowering/provenance; not a compiler correctness proof'))
    return sites,observed

def validate_lookup(ir: str, unit: dict) -> tuple[set[int],list[dict],set[str]]:
    from audit_kernel import (_ir_definition_body, _line_functions, _structured_ir_blocks,
                              _structured_successors, _structured_reachable)
    if unit.get('configuration') not in CONFIGURATIONS:
        raise Core0Error('Lemmasim readonly admission requires its exact selected configuration')
    specs=canonical_specs();by_symbol={row['symbol']:row for row in unit['functions']}
    globals_=[line.strip() for line in ir.splitlines() if re.match(r'^\s*@',line)]
    known=[];sites=set();removed=set();owners=_line_functions(ir.splitlines())
    for global_line in globals_:
        match=re.fullmatch(r'@(switch\.table\.([A-Za-z0-9_.$-]+?)(?:\.(\d+))?) = private unnamed_addr constant \[(\d+) x i64\] \[(.*?)\], align 8',global_line)
        if match is None: continue  # original kernel whitelist will reject it
        table,symbol,suffix,count,raw=match.groups();count=int(count)
        row=by_symbol.get(symbol)
        if row is None: continue
        source=re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])
        spec=specs.get(source)
        if spec is None: continue
        role,args,effects,tables=spec
        if (unit['role'],row['args'],row['effects'])!=(role,args,effects):
            raise Core0Error('Lemmasim literal source/signature/effects differs: '+source)
        index=int(suffix) if suffix is not None else 0
        if index>=len(tables): raise Core0Error('Lemmasim literal table suffix exceeds exact inventory')
        values=[None if value=='poison' else int(value) for value in re.findall(r'i64 (poison|-?\d+)',raw)]
        expected=tables[index]
        if values!=expected or len(values)!=count or len(re.findall(r'@'+re.escape(table)+r'(?![A-Za-z0-9_.$-])',ir))!=2:
            raise Core0Error('Lemmasim literal content/global use inventory differs: '+source)
        body='\n'.join(line.split(';',1)[0].rstrip() for line in _ir_definition_body(ir,symbol).splitlines())
        blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks)
        # The inherited local CFG helper intentionally recognizes branches.
        # These pinned lookup owners also have scalar i64 switch selection;
        # model every edge explicitly so a bound cannot be "proved" by omitting
        # a route through a switch. Unknown switch forms fail closed.
        for block,lines in blocks.items():
            starts=[i for i,line in enumerate(lines) if line.startswith('switch ')]
            if not starts: continue
            if len(starts)!=1 or lines[-1]!=']':
                raise Core0Error('Literal owner has an unrecognized switch terminator')
            start=starts[0]
            head=re.fullmatch(r'switch i64 %[A-Za-z0-9_.$-]+, label %([A-Za-z0-9_.$-]+) \[',lines[start])
            rows=[re.fullmatch(r'i64 (-?\d+), label %([A-Za-z0-9_.$-]+)',line)
                  for line in lines[start+1:-1]]
            if head is None or not rows or any(row is None for row in rows) or len({row[1] for row in rows})!=len(rows):
                raise Core0Error('Literal owner switch cases are malformed or repeated')
            targets=(head[1],*(row[2] for row in rows))
            if any(target not in blocks for target in targets):
                raise Core0Error('Literal owner switch targets an unknown block')
            successors[block]=targets
        geps=re.findall(r'(%[A-Za-z0-9_.$-]+) = getelementptr inbounds nuw \['+str(count)+r' x i64\], ptr @'+re.escape(table)+r', i64 0, i64 (%[A-Za-z0-9_.$-]+)',body)
        if len(geps)!=1: raise Core0Error('Lemmasim literal lacks one exact typed pointer derivation')
        pointer,operand=geps[0]
        argument,shift={
            PREFIX+'DescriptorDTB.literalLength':('%arg0',-1), PREFIX+'DescriptorDTB.literalWord':('%arg1',0),
            PREFIX+'DescriptorDTB.requiredFlags':('%arg0',-1), PREFIX+'DescriptorDTB.expectedIRQ':('%arg0',-1),
            PREFIX+'DescriptorDTB.expectedBase':('%arg0',-1), PREFIX+'DescriptorDTB.expectedSpan':('%arg0',-4),
            PREFIX+'Descriptor.expected':('%arg0',0), 'Lemma.Ink.Surface.letter':('%arg0',-48),
            'Lemma.Applications.Notebook.statusCharacter':('%arg1',0),
        }[source]
        if shift:
            if len(re.findall(re.escape(operand)+r' = add i64 '+re.escape(argument)+', '+str(shift)+r'$',body,re.M))!=1:
                raise Core0Error('Lemmasim literal index differs from its exact source coordinate')
        elif operand!=argument: raise Core0Error('Lemmasim literal index is not its exact source argument')
        loads=re.findall(r'(%[A-Za-z0-9_.$-]+) = load i64, ptr '+re.escape(pointer)+r', align 8',body)
        if len(loads)!=1 or len(re.findall(re.escape(pointer)+r'(?![A-Za-z0-9_.$-])',body))!=2:
            raise Core0Error('Lemmasim readonly pointer escapes its single load')
        load=loads[0];load_block=next(block for block,lines in blocks.items() if any(line.startswith(load+' = load') for line in lines))
        guarded_operand=operand;guarded_type='i64'
        conversion=re.search(re.escape(operand)+r' = zext(?: nneg)? i32 (%[A-Za-z0-9_.$-]+) to i64',body)
        if conversion: guarded_operand=conversion[1];guarded_type='i32'
        guards=[]
        for block,lines in blocks.items():
            for line in lines:
                bound=re.fullmatch(r'(%[A-Za-z0-9_.$-]+) = icmp ult '+guarded_type+' '+re.escape(guarded_operand)+', '+str(count),line)
                if bound and re.fullmatch(r'br i1 '+re.escape(bound[1])+r', label %[A-Za-z0-9_.$-]+, label %[A-Za-z0-9_.$-]+',lines[-1]):
                    true,false=successors[block];without={name:targets for name,targets in successors.items()};without[block]=(false,)
                    if not _structured_reachable(without,'entry',load_block) and _structured_reachable(successors,true,load_block): guards.append(block)
        if len(guards)!=1: raise Core0Error('Lemmasim table load lacks a dominating exact unsigned bound: '+source+' '+table)
        if source.endswith('expectedIRQ'):
            hole=blocks.get('switch.hole_check')
            if hole!=['%switch.maskindex = trunc nuw i64 %switch.tableidx to i8','%switch.shifted = lshr i8 103, %switch.maskindex','%switch.lobit = trunc i8 %switch.shifted to i1','br i1 %switch.lobit, label %switch.lookup, label %if.else.13']:
                raise Core0Error('Lemmasim poisoned IRQ holes lack their exact exclusion mask')
        if source.endswith('literalWord'):
            guard=guards[0];code=WORD_CODES[index]
            if len(re.findall(r'i64 '+str(code)+r', label %'+re.escape(guard)+r'(?![A-Za-z0-9_.$-])',body))!=1:
                raise Core0Error('FDT word table is not bound to its exact literal code')
        if source.endswith('statusCharacter'):
            # Each word belongs to one declared save state; the default state
            # is read-only. A valid index bound alone cannot certify that bind.
            branch = re.search(r'switch i64 %arg0, label %([A-Za-z0-9_.$-]+) \[\s*'
                r'i64 0, label %([A-Za-z0-9_.$-]+)\s*'
                r'i64 1, label %([A-Za-z0-9_.$-]+)\s*'
                r'i64 2, label %([A-Za-z0-9_.$-]+)\s*\]', body)
            if branch is None:
                raise Core0Error('Notebook status words lack the exact save-state selection')
            selected=branch[index+2] if index<3 else branch[1]
            if not _structured_reachable(successors,selected,load_block):
                raise Core0Error('Notebook status word is not reached by its declared save state')
            for other in [branch[1],branch[2],branch[3],branch[4]]:
                if other!=selected and _structured_reachable(successors,other,load_block):
                    raise Core0Error('Notebook status word is reachable from a different save state')
        located={i for i,line in enumerate(ir.splitlines()) if owners[i]==symbol and line.strip().startswith(load+' = load')}
        if len(located)!=1: raise Core0Error('Lemmasim literal load inventory differs')
        sites|=located;removed.add(global_line)
        known.append(dict(source=row['source'],function=symbol,global_=table,values=values,
            element_bits=64,alignment_bytes=8,index_bound=count,guarded_loads=1,readonly=True,guard=guards[0]))
        known[-1]['global']=known[-1].pop('global_')
    for source,spec in specs.items():
        if any(re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])==source for row in unit['functions']):
            present=[row for row in known if re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])==source]
            if len(present)!=len(spec[3]): raise Core0Error('Lemmasim exact reachable table inventory incomplete: '+source)
    return sites,known,removed

def validate_object(section_text: str, symbol_text: str, relocation_text: str,
                    section_bytes: dict[str,bytes], tables: list[dict], object_file: str) -> dict:
    """Every optimized literal owns exact local object bytes, without relocation."""
    sections={match[1]:match[2] for match in re.finditer(r'(?m)^\s*\[\s*(\d+)\]\s+(\S+)\s+',section_text)}
    for name,raw in section_bytes.items():
        flags,entry_size=('AM','20') if name=='.rodata.cst32' else ('A','00')
        section=re.findall(r'(?m)^\s*\[\s*\d+\]\s+'+re.escape(name)+r'\s+PROGBITS\s+0+\s+[0-9a-f]+\s+([0-9a-f]+)\s+'+entry_size+r'\s+'+flags+r'\s+0\s+0\s+8\s*$',section_text)
        if len(section)!=1 or int(section[0],16)!=len(raw) or name=='.rodata.cst32' and len(raw)%32:
            raise Core0Error('Lemmasim literal section readonly flags/alignment/extent differs')
    rows=[line.split() for line in symbol_text.splitlines() if len(line.split())==8 and line.split()[3]=='OBJECT' and line.split()[6]!='UND']
    expected={'.L'+row['global'] for row in tables}
    if {row[-1] for row in rows}!=expected or len(rows)!=len(tables):
        raise Core0Error('Lemmasim readonly object-symbol inventory differs')
    observed=[];extents=[]
    for table in tables:
        row=next(row for row in rows if row[-1]=='.L'+table['global']);offset,size=int(row[1],16),int(row[2]);section=sections.get(row[6]);raw=section_bytes.get(section,b'')
        values=[0 if value is None else value & ((1<<64)-1) for value in table['values']]
        if row[4:6]!=['LOCAL','DEFAULT'] or section not in {'.rodata','.rodata.cst32'} or size!=len(values)*8 or offset%8 or offset+size>len(raw) or raw[offset:offset+size]!=struct.pack('<'+str(len(values))+'Q',*values):
            raise Core0Error('Lemmasim literal object extent/bytes/section differs')
        if any(previous==section and offset<end and begin<offset+size for previous,begin,end in extents):
            raise Core0Error('Lemmasim literal object extents overlap')
        extents.append((section,offset,offset+size));current=None
        for line in relocation_text.splitlines():
            heading=re.search(r"Relocation section '([^']+)'",line)
            if heading: current=heading[1]
            relocation=re.match(r'\s*([0-9a-f]+)\s+[0-9a-f]+\s+(R_RISCV_[A-Z0-9_]+)\s',line)
            if relocation and current=='.rela'+section and int(relocation[1],16)<offset+size and offset<int(relocation[1],16)+(8 if relocation[2].endswith('64') else 4):
                raise Core0Error('Lemmasim literal bytes contain a relocation')
        observed.append(dict(source=table['source'],symbol=row[-1],section=section,offset=offset,bytes=size,
            values=values,sha256=hashlib.sha256(raw[offset:offset+size]).hexdigest(),relocations=[]))
    for section,raw in section_bytes.items():
        if section=='.rodata': continue  # shared with independently checked local jump tables
        occupied=bytearray(len(raw))
        for name,begin,end in extents:
            if name==section: occupied[begin:end]=b'\1'*(end-begin)
        if any(byte for byte,owned in zip(raw,occupied) if not owned):
            raise Core0Error('Unaccounted nonzero Lemmasim merged literal bytes')
    return dict(object=object_file,readonly_tables=observed)


def validate_linked_literals(section_text: str, symbol_text: str, text: bytes,
                             text_base: int, tables: list[dict]) -> list[dict]:
    """Bind every admitted object literal to the final RX image's actual bytes."""
    sections={match[1]:match[2] for match in re.finditer(r'(?m)^\s*\[\s*(\d+)\]\s+(\S+)\s+',section_text)}
    rows=[line.split() for line in symbol_text.splitlines() if len(line.split())==8 and line.split()[3]=='OBJECT' and line.split()[6]!='UND']
    if len(rows)!=len(tables) or {row[-1] for row in rows}!={table['symbol'] for table in tables}:
        raise Core0Error('Lemmasim final literal object inventory differs')
    observed=[];extents=[]
    for table in tables:
        row=next(row for row in rows if row[-1]==table['symbol']);address,size=int(row[1],16),int(row[2]);offset=address-text_base
        expected=struct.pack('<'+str(len(table['values']))+'Q',*table['values'])
        if row[4:6]!=['LOCAL','DEFAULT'] or sections.get(row[6])!='.text' or size!=table['bytes'] or address%8 or offset<0 or offset+size>len(text) or text[offset:offset+size]!=expected:
            raise Core0Error('Lemmasim final RX literal bytes/extent/ownership differs')
        if any(offset<end and begin<offset+size for begin,end in extents):
            raise Core0Error('Lemmasim final literal extents overlap')
        extents.append((offset,offset+size));observed.append(dict(symbol=row[-1],address=address,bytes=size,
            source=table['source'],sha256=hashlib.sha256(expected).hexdigest(),writable=False))
    return observed
