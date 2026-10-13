"""Independent bounded artifact checks for the genuine integrity-only boot ROM.

This is a compiler/link-closure audit. Actual controller transactions, recovery
and physical nonvolatile qualification are separate obligations.
"""
import re,struct
from core0_common import Core0Error

ROOT='Lemma.Boot.Recovery.entry'
CONFIGURATION='lemmasim-silicon-product-boot'
REQUIRED={ROOT,'Lemma.Boot.Product.boot','Lemma.Boot.Product.transaction',
 'Lemma.Boot.Product.loadImage','Lemma.Boot.Product.bootRecord',
 'Lemma.Boot.Product.publishMetadata','Lemma.Boot.Product.finishInstall',
 'Lemma.Boot.Product.establishRecoveryImage','Lemma.Boot.Recovery.writeImageSector',
 'Lemma.Boot.Recovery.publishImage','Lemma.Boot.Recovery.receiveFrame',
 'Lemma.Boot.Recovery.receivePayload','Lemma.Boot.Recovery.imageStatus','Lemma.Boot.Product.crcBit'}
HELPERS={'Lemma.Kernel.Memory.Access.'+n for n in ('read8','read64','write8','write64')}
HELPERS|={'Lemma.Platform.LemmaSim.IO.read64','Lemma.Platform.LemmaSim.IO.write64'}
STATUS={f'Lemma.Core0.Memory.Status.{name}':value for name,value in
 [('iterationStop',10),('budgetExceeded',9),('rxTimeout',12),('txTimeout',11),('lineError',13)]}
INTRINSICS={'llvm.fshl.i64':'i64(i64,i64,i64)',
 'llvm.umax.i4':'i4(i4,i4)','llvm.umin.i64':'i64(i64,i64)'}
LITERALS={'Lemma.Boot.Product.metadataMagic':0x31444d42414d454c,
 'Lemma.Boot.Product.imageMagic':0x31474d49414d454c,
 'Lemma.Boot.Product.contextMagic':0x31585443414d454c,
 'Lemma.Boot.Recovery.responseMagic':0x3154504345524d4c,
 'Lemma.Boot.Recovery.requestMagic':0x31564f4345524d4c}

def validate_unit(unit,pre,optimized):
 expected={'schema_version':1,'contract_version':'core0-boot-v0.1',
  'configuration':CONFIGURATION,'role':'boot','root':ROOT,
  'rom_base':4096,'rom_bytes':65536,'stack_floor':0x81fd0000,'stack_top':0x82000000,
  'integrity':'CRC32/ISO-HDLC; no authentication or anti-rollback guarantee',
  'recovery_transport':'lemma-local-uart-recovery-v1; integrity-only, bounded owner-local transport; authentication OPEN',
  'backend_dispatch':'lemma-boot-direct-branches-v1'}
 if any(unit.get(k)!=v for k,v in expected.items()):raise Core0Error('boot ROM manifest contract differs')
 if set(unit)!=set(expected)|{'entry_symbol','functions','used_execution_ops','used_device_ops'}:raise Core0Error('unexpected boot ROM manifest authority')
 rows=unit.get('functions')
 if not isinstance(rows,list) or not rows:raise Core0Error('empty boot function corpus')
 sources={};symbols={}
 for row in rows:
  if not isinstance(row,dict) or set(row)!={'source','symbol','args','effects'}:raise Core0Error('malformed boot function provenance')
  source,symbol=row['source'],row['symbol']
  if not isinstance(source,str):raise Core0Error('malformed boot source identity')
  private=re.fullmatch(r'_private\.Lemma\.Boot\.(Product|Recovery)\.[0-9]+\.(Lemma\.Boot\.\1\.[A-Za-z_0-9]+)',source)
  if private:source=private[2]
  if not (source.startswith(('Lemma.Boot.Product.','Lemma.Boot.Recovery.')) or source in HELPERS or source in STATUS):raise Core0Error('foreign boot function source')
  if not isinstance(symbol,str) or not re.fullmatch(r'lemma_product_boot_core0_(?:scalar|action)_[0-9]+',symbol):raise Core0Error('unexpected boot lowering symbol')
  if source in sources or symbol in symbols:raise Core0Error('duplicate boot function authority')
  if not isinstance(row['args'],list) or any(x not in ('u8','u32','u64','bool') for x in row['args']):raise Core0Error('unexpected boot ABI')
  effects={'checked-access','physical-read','physical-write','mmio-read','mmio-write','io-order'}
  if not isinstance(row['effects'],list) or len(row['effects'])!=len(set(row['effects'])) or any(x not in effects for x in row['effects']):raise Core0Error('unexpected boot effects')
  if source in STATUS and (row['args'] or row['effects']):raise Core0Error('status literal has unexpected authority')
  sources[source]=row;symbols[symbol]=source
 if not REQUIRED<=sources.keys() or unit.get('entry_symbol')!=sources[ROOT]['symbol'] or sources[ROOT]['args']!=[]:raise Core0Error('missing real boot/recovery/installer closure')
 ops=unit.get('used_execution_ops')
 if not isinstance(ops,list) or len(ops)!=len(set(ops)) or set(ops)!={'lemmasim.device-read64','lemmasim.device-write64','execution.physical-write64','execution.physical-read64','execution.physical-write8'}:raise Core0Error('boot primitive scope differs')
 device=unit.get('used_device_ops')
 if not isinstance(device,list) or len(device)!=len(set(device)) or set(device)!={'uart.read-status','uart.read-byte','uart.write-byte','uart.enable-reset-fifo'}:raise Core0Error('boot recovery UART boundary differs')
 for source,value in STATUS.items():
  if source in sources:
   symbol=re.escape(sources[source]['symbol'])
   if not re.search(r'(?m)^define internal zeroext i8 @'+symbol+r'\(\) nounwind "no-jump-tables"="true" \{\nentry:\n  ret i8 '+str(value)+r'\n\}',pre):raise Core0Error('boot status constant body differs')
 for source,value in LITERALS.items():
  row=sources.get(source)
  if row is None or row['args'] or row['effects']:raise Core0Error('missing closed boot readonly literal source')
  if not re.search(r'(?m)^define internal i64 @'+re.escape(row['symbol'])+r'\(\) nounwind "no-jump-tables"="true" \{\nentry:\n  ret i64 '+str(value)+r'\n\}',pre):raise Core0Error('boot readonly literal body differs')
 for label,ir in [('checked',pre),('optimized',optimized)]:
  if ' asm ' in ir or re.search(r'(?m)^@',ir):raise Core0Error('unaccounted boot code/data construction')
  if re.search(r'\b(?:invoke|landingpad|resume|callbr|indirectbr)\b',ir):raise Core0Error('foreign boot exception/dispatch state')
  if re.search(r'\bcall\s+[^\n]*%[A-Za-z_][A-Za-z_0-9]*\(',ir):raise Core0Error('unaccounted indirect boot call')
  definitions=re.findall(r'(?m)^define\s+[^\n]*@([A-Za-z_0-9.$]+)\(',ir)
  if len(definitions)!=len(set(definitions)) or not definitions or not set(definitions)<=symbols.keys():raise Core0Error('boot function LLVM provenance differs')
  if label=='checked' and set(definitions)!=symbols.keys():raise Core0Error('checked boot closure omitted a genuine function')
  if label=='checked':
   headers=re.findall(r'(?m)^define[^\n]*$',ir)
   if any(header.count('"no-jump-tables"="true"')!=1 for header in headers):raise Core0Error('ROM direct-branch lowering contract missing')
  declared={}
  for result,name,params in re.findall(r'(?m)^declare\s+(void|i[0-9]+)\s+@([^ (]+)\(([^)]*)\)',ir):
   if name in declared:raise Core0Error('duplicate boot primitive declaration')
   declared[name]=result+'('+re.sub(r'\s+','',params)+')'
  if declared.pop('core0_io_fence',None)!='void()':raise Core0Error('missing real boot I/O fence')
  if label=='checked' and declared:raise Core0Error('unaccounted checked boot runtime')
  if any(INTRINSICS.get(k)!=v for k,v in declared.items()):raise Core0Error('unknown optimized boot intrinsic')
  if not re.search(r'(?m)^define[^\n]*@'+re.escape(sources[ROOT]['symbol'])+r'\(\)',ir):raise Core0Error('missing actual boot entry body')
 return {'genuine_functions':len(rows),'optimized_functions':len(re.findall(r'(?m)^define ',optimized)),
  'runtime_helpers':['core0_io_fence'],'llvm_intrinsics':sorted(declared),
  'authentication':'OPEN','anti_rollback':'OPEN'}

def validate_elf(wire,rom):
 if len(wire)<64 or wire[:7]!=b'\x7fELF\x02\x01\x01':raise Core0Error('boot image must be ELF64 little endian')
 e=struct.unpack_from('<16sHHIQQQIHHHHHH',wire)
 if e[1]!=2 or e[2]!=243 or e[3]!=1 or e[4]!=4096 or e[7]!=0 or e[8]!=64 or e[9]!=56:raise Core0Error('boot ELF type/ISA/entry differs')
 offset,count=e[5],e[10]
 if count==0 or offset>len(wire) or count>(len(wire)-offset)//56:raise Core0Error('invalid boot ELF program headers')
 loads=[]
 for i in range(count):
  kind,flags,start,virtual,physical,files,memory,alignment=struct.unpack_from('<IIQQQQQQ',wire,offset+i*56)
  if kind==1:
   if flags!=5 or virtual!=4096 or physical!=4096 or files!=memory or not 0<files<=65536 or start>len(wire)-files or alignment!=4096:raise Core0Error('immutable boot load envelope differs')
   loads.append(wire[start:start+files])
 if loads!=[rom] or len(rom)%4:raise Core0Error('ROM bytes differ from the sole immutable RX load segment')
 shoff,shsize,shcount,strindex=e[6],e[11],e[12],e[13]
 if shsize!=64 or not shcount or strindex>=shcount or shoff>len(wire) or shcount>(len(wire)-shoff)//64:raise Core0Error('missing boot section provenance')
 sections=[struct.unpack_from('<IIQQQQIIQQ',wire,shoff+i*64) for i in range(shcount)]
 names=sections[strindex]
 if names[4]>len(wire)-names[5]:raise Core0Error('boot section name bounds differ')
 strings=wire[names[4]:names[4]+names[5]];allocated={}
 for section in sections:
  start=strings.find(b'\0',section[0])
  if section[0]>=len(strings) or start<0:raise Core0Error('boot section name malformed')
  name=strings[section[0]:start].decode('ascii')
  if section[2]&2:
   if name not in ('.text','.rodata') or name in allocated or section[1]!=1 or section[4]>len(wire)-section[5]:raise Core0Error('unaccounted allocated ROM section')
   allocated[name]=section
 if set(allocated)!={'.text','.rodata'}:raise Core0Error('missing closed ROM code/readonly separation')
 text,rodata=allocated['.text'],allocated['.rodata']
 # LLVM emits a deduplicated SHF_ALLOC|SHF_MERGE pool of five 8-byte
 # entries. It has no writable or executable section permission.
 if text[2]!=6 or text[3]!=4096 or text[5]%4 or text[8]!=4 or rodata[2]!=18 or rodata[3]!=(text[3]+text[5]+7)&~7 or rodata[8]!=8 or rodata[9]!=8 or rodata[5]!=40:raise Core0Error('ROM code/readonly flags or placement differ')
 values=struct.unpack_from('<5Q',wire,rodata[4])
 if len(set(values))!=5 or set(values)!=set(LITERALS.values()):raise Core0Error('unaccounted linked ROM readonly literal pool')
 if any(rom[text[5]:rodata[3]-4096]) or rodata[3]-4096+rodata[5]!=len(rom):raise Core0Error('unaccounted ROM alignment or trailing bytes')
 return {'entry':4096,'load_bytes':len(rom),'rom_envelope_bytes':65536,'permissions':'RX',
  'readonly_contract':'lemma-boot-readonly-magic-v1','readonly_bytes':40,'readonly_sources':sorted(LITERALS)}
