"""Closed opt-in Kernel8 artifact authority; no target policy executes here.
Body pins come from reviewed genuine source/tool-bound LLVM, not from source
at audit time. Independent ranges, UTF8 bytes and guard-use checks constrain the
new apertures/pools. This is an artifact audit, not a compiler correctness proof.
"""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from core0_common import Core0Error
from paper_next import canonical
CONFIGURATION='lemmasim-silicon-wifi-common-probe'
READ_CONFIGURATION='lemmasim-silicon-wifi-common-read-probe'
PREFIX='Lemma.Platform.LemmaSim.DescriptorDTB.'
LITERAL_TEXT={'Wire':{65:'lemma,phy-version',66:'lemma,phy-sample-hz',68:'lemma,development-mac',81:'lemma,usb-device-wire-v1'},'Common':{22:'lemma-wifi-common@10013000',82:'lemma,wifi-common-ofdm-data-v1',91:'lemma,aligned-data-only'}}

def selected(unit):return unit.get('configuration') in (CONFIGURATION,READ_CONFIGURATION) and unit.get('role')=='kernel'
def _new(source):
 return source.startswith(('Lemma.Radio.WiFi.','Lemma.Platform.Silicon.Development.WiFiCommonProbe.','Lemma.Platform.Silicon.Development.WiFiCommonReadProbe.','Lemma.Platform.Silicon.BindingWiFiCommon.')) or (source.startswith('Lemma.Platform.LemmaSim.') and 'Common' in source)
def literal_values(family,code):
 raw=LITERAL_TEXT[family][code].encode('ascii')+b'\0';raw=raw.ljust((len(raw)+7)//8*8,b'\0');words=[int.from_bytes(raw[i:i+8],'little') for i in range(0,len(raw),8)]
 # Existing Wire81's fourth all-zero NUL word is a scalar default, not a pool.
 if (family,code)==('Wire',81):
  if words[-1]!=0:raise Core0Error('Wire scalar-zero NUL word changed')
  words=words[:3]
 return words

def literal_aliases(ir,unit):
 from audit_kernel import _ir_definition_body,_line_functions
 if not selected(unit) or unit.get('contract_version')!='core0-kernel-v0.8':raise Core0Error('Common literal selection/version differs')
 rows={canonical(r['source']):r for r in unit['functions']};owners=_line_functions(ir.splitlines());result={}
 for family,texts in LITERAL_TEXT.items():
  row=rows.get(PREFIX+'literalWord'+family)
  if row is None or (row['args'],row['effects'])!=(['u64','u64'],[]):raise Core0Error('Common complete literal owner/signature missing')
  symbol=row['symbol'];body=_ir_definition_body(ir,symbol);found=[]
  pattern=r'^@(switch\.table\.'+re.escape(symbol)+r'(?:\.\d+)?) = private unnamed_addr constant \[(\d+) x i64\] \[(.*?)\], align 8$'
  for name,count,raw in re.findall(pattern,ir,re.M):
   values=[int(v) for v in re.findall(r'i64 (-?\d+)',raw)];codes=[c for c in texts if values==literal_values(family,c)]
   if len(codes)!=1 or int(count)!=len(values) or len(re.findall(r'@'+re.escape(name)+r'(?![A-Za-z0-9_.$-])',ir))!=2:raise Core0Error('Common literal bytes/extent/global use differ')
   uses=[owners[i] for i,line in enumerate(ir.splitlines()) if not line.startswith('@') and re.search(r'@'+re.escape(name)+r'(?![A-Za-z0-9_.$-])',line)]
   if uses!=[symbol] or len(re.findall(r'getelementptr inbounds nuw \['+count+r' x i64\], ptr @'+re.escape(name)+r', i64 0, i64 %arg1',body))!=1:raise Core0Error('Common literal lacks its one source-owned typed index')
   found.append(codes[0]);result[name]=family.lower()+'.literal.'+str(codes[0])
  if sorted(found)!=sorted(texts):raise Core0Error('Common complete literal pool inventory differs')
 return result

def body_normalized(ir,row,names,aliases):
 from audit_kernel import _ir_definition_body
 body=_ir_definition_body(ir,row['symbol'])
 if body is None:raise Core0Error('Common genuine emitted body missing')
 body=re.sub(r'@([^ (]+)',lambda m:'@'+aliases.get(m[1],names.get(m[1],m[1])),body)
 return ' '.join(' '.join(line.split(';',1)[0].strip() for line in body.splitlines()).split())

def authority():
 value=json.loads((Path(__file__).resolve().parents[1]/'tooling/wifi_common-authority.json').read_text())
 if value.get('schema')!='lemma-common-kernel8-authority/1' or value.get('configuration')!=CONFIGURATION or value.get('contract_version')!='core0-kernel-v0.8' or len(value.get('functions',{}))!=295:raise Core0Error('Common exact genuine authority corpus missing')
 return value['functions']

def validate(ir,unit,*,optimized):
 if unit.get('configuration')==READ_CONFIGURATION:
  from wifi_owned_read import validate as validate_read
  return validate_read(ir,unit,optimized=optimized)
 rows={canonical(r['source']):r for r in unit.get('functions',[])}
 if not selected(unit):
  if any(_new(s) for s in rows):raise Core0Error('CommonOFDM declarations escape exact Kernel8 selection')
  return None
 want=authority()
 if unit.get('contract_version')!='core0-kernel-v0.8' or len(rows)!=len(unit['functions']) or set(rows)!=set(want):raise Core0Error('Common exact295source/Kernel8 inventory differs')
 if any(s.startswith(('Lemma.Boot.Product','Lemma.Platform.LemmaSim.BootHealth','Lemma.Kernel.Process.')) or s.endswith(('.initProduct','.prepareManagedProduct','.configureProduct')) for s in rows):raise Core0Error('Common probe acquired NV/User task authority')
 aliases=literal_aliases(ir,unit) if optimized else {};names={r['symbol']:s for s,r in rows.items()};observed={}
 for source,wanted in want.items():
  row=rows[source]
  if (row['args'],row['effects'])!=(wanted['args'],wanted['effects']):raise Core0Error('Common exact signature/effect differs: '+source)
  actual=hashlib.sha256(body_normalized(ir,row,names,aliases).encode()).hexdigest()
  if actual!=wanted['post' if optimized else 'pre']:raise Core0Error('Common complete checked body differs: '+source)
  observed[source]=actual
 return {'contract_version':'lemma-common-kernel8-artifact-authority/1','configuration':CONFIGURATION,'binding':12,'descriptor_abi':13,'features':47,'common_irq':18,'aperture_base':0x10013000,'aperture_bytes':1024,'boot_nv':False,'complete_bodies':observed,'phase':'post' if optimized else 'pre','scope':'closed genuine checked artifact; live queue/IRQ/RX needs separate observation'}

def validate_devices(ir,unit,optimized):
 from audit_kernel import _ir_definition_body,_line_functions
 if not selected(unit):
  if any(r['stable_id'].startswith('lemmasim.device-') for r in unit['used_execution_ops']):raise Core0Error('Common device operation escaped Kernel8')
  return set(),[]
 validate(ir,unit,optimized=optimized);sites=set();rows=[];owners=_line_functions(ir.splitlines())
 for row in unit['functions']:
  if not row['source'].startswith('Lemma.Platform.LemmaSim.IO.'):continue
  operation=row['source'].rsplit('.',1)[1]
  if operation not in ('read32','read64','write32','write64'):raise Core0Error('Common unknown IO operation')
  width=int(operation[-2:])//8;write=operation.startswith('write');body=_ir_definition_body(ir,row['symbol'])
  if not optimized:
   regions=[(0x10001000,0x10001200),(0x0c000004,0x0c000044),(0x0c002080,0x0c002084),(0x0c201000,0x0c201008),(0x0c000048,0x0c00004c)] if width==4 else [(0x10010000,0x10011000),(0x10011000,0x10012000),(0x10013000,0x10013400)]
   lower=[int(v) for v in re.findall(r'icmp uge i64 %arg0, (\d+)',body)];upper=[int(v) for v in re.findall(r'icmp ule i64 %arg0, (\d+)',body)]
   if lower!=[a for a,b in regions] or upper!=[b-width for a,b in regions] or len(re.findall(r'and i64 %arg0, '+str(width-1)+r'$',body,re.M))!=1:raise Core0Error('Common exact range/alignment changed or gainedNV/priority17')
  located={i for i,line in enumerate(ir.splitlines()) if owners[i]==row['symbol'] and re.search(r'\b(?:load|store) volatile i'+str(width*8)+r'\b',line)}
  if len(located)!=(1 if optimized else 5 if width==4 else 3):raise Core0Error('Common volatile access inventory differs')
  sites|=located;rows.append({'source':row['source'],'function':row['symbol'],'width_bytes':width,'direction':'write' if write else 'read','access_sites':len(located),'optimized':optimized})
 if len(rows)!=4:raise Core0Error('Common complete IO lowering corpus missing')
 return sites,rows

def validate_boot_stack(layout,unit,ir):
 validate(ir,unit,optimized=False)
 return {'stage':'supervisor','user_tasks_constructed':False,'frame_count':8192,'frame_quota':8192,'scope':'exact genuine S probe boot/ownedqueue bodies; no User scheduling claim'}

def validate_pmp(assembly,raw_machine,ranges,configuration):
 """Independent entry8/raw-CSR/WARL-fatal/readback-store audit for Common12.

 This is separate from Product's BootNV authority. Its only new NAPOT interval
 is 0x10013000/1024 bytes; all historical entries and startup selectors remain
 under their existing checks. A supervisor workload is a separate observation.
 """
 import struct
 from audit_kernel import _assembly_function,_raw_function
 if configuration not in (CONFIGURATION,READ_CONFIGURATION):raise Core0Error('Common PMP escaped its exact configurations')
 body=_assembly_function(assembly,'_start')
 mentions=[line.strip() for line in assembly.splitlines() if re.search(r'\b(?:pmpaddr8|pmpcfg2)\b',line)]
 old=['csrw pmpcfg0, zero','csrw pmpcfg2, zero']
 for index,value in enumerate([536879103,537141247,553648127,67108895,262655,51380223,67110399,67126271]):
  old += [f'li t0, {value}',f'csrw pmpaddr{index}, t0']
 old += ['li t0, 1953184666628331544','csrw pmpcfg0, t0']
 tail=['li t0, 67128447','csrw pmpaddr8, t0','csrr t1, pmpaddr8',
       'bne t0, t1, lemma_machine_fatal','li t0, 27','csrw pmpcfg2, t0',
       'csrr t1, pmpcfg2','bne t0, t1, lemma_machine_fatal','sfence.vma zero, zero']
 expected=old+tail
 positions=[i for i in range(len(body)-len(expected)+1) if body[i:i+len(expected)]==expected]
 observations=['li t0, 2152595952','csrr t1, pmpaddr8','sd t1, 0(t0)','csrr t1, pmpcfg2','sd t1, 8(t0)']
 if len(positions)!=1 or sum(body[i:i+len(observations)]==observations for i in range(len(body)-len(observations)+1))!=1 or mentions!=[
   'csrw pmpcfg2, zero','csrw pmpaddr8, t0','csrr t1, pmpaddr8','csrw pmpcfg2, t0','csrr t1, pmpcfg2','csrr t1, pmpaddr8','csrr t1, pmpcfg2']:
  raise Core0Error('Common complete PMP initialization/readbacks/store ownership differs')
 start,size=ranges.get('_start',(0,0));raw=_raw_function(raw_machine,ranges,'_start')
 words=list(struct.unpack('<'+str(size//4)+'I',raw))
 csr=lambda w:((w>>20)&4095) if w&127==0x73 and (w>>12)&7 else None
 encoding=lambda number,funct,rd,rs:(number<<20)|(rs<<15)|(funct<<12)|(rd<<7)|0x73
 inventory=[(i,w) for i,w in enumerate(words) if csr(w) in {0x3a2,0x3b8}]
 wanted=[encoding(0x3a2,1,0,0),encoding(0x3b8,1,0,5),encoding(0x3b8,2,6,0),
         encoding(0x3a2,1,0,5),encoding(0x3a2,2,6,0),encoding(0x3b8,2,6,0),encoding(0x3a2,2,6,0)]
 if [w for _,w in inventory]!=wanted or words[inventory[0][0]-1]!=encoding(0x3a0,1,0,0):
  raise Core0Error('Common actual CSR operation/clear inventory differs')
 at=inventory[1][0]
 if words[at-2:at]!=[0x040052b7,0xc7f2829b] or inventory[2][0]!=at+1:
  raise Core0Error('Common actual NAPOT address/write/readback differs')
 fatal=ranges.get('lemma_machine_fatal',(None,None))[0]
 def mismatch_gate(index):
  w=words[index]
  if w&127!=0x63 or (w>>15)&31!=5 or (w>>20)&31!=6:raise Core0Error('Common actual WARL comparison lost t0/t1')
  imm=((w>>31)<<12)|(((w>>7)&1)<<11)|(((w>>25)&63)<<5)|(((w>>8)&15)<<1)
  if imm&4096:imm-=8192
  if (w>>12)&7==1 and start+index*4+imm==fatal:return index+1
  if (w>>12)&7!=0 or imm!=8:raise Core0Error('Common actual WARL mismatch escapes fatal')
  j=words[index+1]
  if j&127!=0x6f or (j>>7)&31:raise Core0Error('Common actual WARL mismatch lost fatal JAL')
  offset=((j>>31)<<20)|(((j>>12)&255)<<12)|(((j>>20)&1)<<11)|(((j>>21)&1023)<<1)
  if offset&(1<<20):offset-=1<<21
  if start+(index+1)*4+offset!=fatal:raise Core0Error('Common actual WARL mismatch targets another function')
  return index+2
 config=mismatch_gate(at+2)
 if words[config]!=0x01b00293 or inventory[3][0]!=config+1 or inventory[4][0]!=config+2:
  raise Core0Error('Common actual RW/NX configuration/readback differs')
 after=mismatch_gate(config+3)
 if words[after]!=0x12000073:raise Core0Error('Common verified grant lost global translation fence')
 address_read=inventory[5][0];config_read=inventory[6][0]
 if config_read!=address_read+2 or words[address_read+1]!=0x0062b023 or words[config_read+1]!=0x0062b423:
  raise Core0Error('Common actual CSR observations lost distinct0/8 doubleword stores')
 # Decode only the constant-LI instruction family immediately before these
 # observations, independently requiring the exact kernel-only scratch base.
 def signed(value,bits):return value-(1<<bits) if value&(1<<(bits-1)) else value
 candidates=[]
 for begin in range(max(after+1,address_read-8),address_read):
  value=None
  for i,w in enumerate(words[begin:address_read]):
   op=w&127;rd=(w>>7)&31;rs=(w>>15)&31;funct=(w>>12)&7
   if rd!=5:break
   if op==0x37 and i==0:value=signed(w&0xfffff000,32)&((1<<64)-1)
   elif op==0x13 and funct==0 and (rs==5 and value is not None or rs==0 and i==0):value=((value if rs==5 else 0)+signed(w>>20,12))&((1<<64)-1)
   elif op==0x1b and funct==0 and rs==5 and value is not None:value=signed((value+signed(w>>20,12))&0xffffffff,32)&((1<<64)-1)
   elif op==0x13 and funct==1 and w>>26==0 and rs==5 and value is not None:value=(value<<((w>>20)&63))&((1<<64)-1)
   else:break
  else:
   if value==0x804e01f0:candidates.append(begin)
 if len(candidates)!=1:raise Core0Error('Common actual observation stores lack exact scratch-base constant')
 address=0x04004c7f;bits=0
 while address&(1<<bits):bits+=1
 base=(address&~((1<<bits)-1))*4;extent=1<<(bits+3)
 if base!=0x10013000 or extent!=1024 or (27&7)!=3 or (27>>3)&3!=3 or 27&128:
  raise Core0Error('Common independently decoded NAPOT/RW/NX/unlocked scope differs')
 return {'contract_version':'lemma-common-pmp-v1','entry':8,'base':base,'bytes':extent,'permissions':'RW/NX',
         'csr_instructions':7,'readback_fatal_branches':2,'readback_ram':0x804e01f0,
         'scope':'actual checked startup grant/readback stores; live queue/IRQ qualification separate'}
