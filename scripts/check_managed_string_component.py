#!/usr/bin/env python3
"""Observe genuine String component artifacts; no execution or production grant."""
import argparse,copy,hashlib,json,re,struct,sys
from pathlib import Path
from core0_common import Core0Error,write_json,sha256
REVISION='5045d0056413266e57c625dcd7c365b10e377c52'
ROOTS={'Lemma.Mathematics.ManagedStringSubmission.compareFiveSix':8,
       'Lemma.Mathematics.ManagedStringSubmission.roundtrip':8,
       'Lemma.Compiler.Test.ManagedString.utf8':5}
PINS={'genuine_ir': 'caf36922ba5fdbc9ba1d731c7c14b6811cb724532dbda3047035d5c3e61b8515', 'pre': 'e9cc14f907b77a6eb9405b499addff3a69b9dfc59c5b4f2ca786a26ea931fa3e', 'post': '1b4ebea0aae7458677ad7570e415b2d5a50fa4213948a7c7276fbb686689a8b9', 'text': '4ee0fe50fbda3dd36175a8728a0af340f2971cc24e9caf4c44bb02808c65e3bd'}
POOL=[0x3152545352414d4c,0x3159544252414d4c,0x3154504f5254534c,0x31414e4552414d4c,0x31414e4552414d4c,0x3152545352414d4c,0x3159544252414d4c,0x3152545352414d4c,0x3159544252414d4c,0x3154504f5254534c,0x3154504f5254534c,0x3154504f5254534c,0x31414e4552414d4c,0x3152545352414d4c,0x3159544252414d4c]
def require(value,message):
 if not value:raise Core0Error(message)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def mapping(text):
 rows=text.splitlines();names={}
 for row in rows:
  m=re.fullmatch(r'source=([^;]+);llvm=([A-Za-z0-9_]+)',row)
  require(m is not None and m[1] not in names and m[2] not in names.values(),'Malformed/duplicate source correspondence')
  names[m[1]]=m[2]
 require(len(names)==104,'Complete genuine component function inventory differs')
 return names
def catalog(c):
 require(set(c)=={'contract','profile','compiler_revision','maximum_utf8_bytes','allocator','slots','genuine_ir','actual_ir_mutations','historical_profiles_rejected'},'String component catalog malformed')
 require(c['contract']=='lemma-managed-string-v1' and c['profile']=='core0-user-v0.6' and c['compiler_revision']==REVISION and c['maximum_utf8_bytes']==40 and c['allocator']=='lemma-owned-arena-v1' and c['slots']==31 and c['historical_profiles_rejected']==22,'String component bounds/profile/runtime differ')
 rows=c['genuine_ir'];require(len(rows)==3 and {r['root']:len(r['genuine_ir']) for r in rows}==ROOTS,'Genuine ordinary String roots/closure missing')
 require(digest(rows)==PINS['genuine_ir'],'Actual upstream ownership/type/call/constructor IR differs')
 mutations=c['actual_ir_mutations'];require(len(mutations)==11 and {r['mutation'] for r in mutations}==set(range(1,12)) and all(r['actual_changed_nodes']>0 and r['rejected'] for r in mutations),'Real compiler IR mutation rejections missing')
 return {'genuine_ir_sha256':PINS['genuine_ir'],'ordinary_functions':sum(ROOTS.values()),'historical_profiles_rejected':22,'actual_ir_mutations':11}
def llvm_digest(ir,names):
 definitions=list(re.finditer(r'^define[^\n]*@([A-Za-z0-9_]+)\([^\n]*\)[^\n]*\{\n(.*?)^\}',ir,re.M|re.S))
 require(len(definitions)==len(names) and {m[1] for m in definitions}==set(names.values()),'LLVM complete source closure missing/duplicated')
 require(re.findall(r'^declare[^@\n]*@([^ (]+)',ir,re.M)==['lemma_exec_syscall'],'String component acquired foreign runtime/helper')
 require(set(re.findall(r'\bcall[^@\n]*@([^ (]+)\(',ir))<=set(names.values())|{'lemma_exec_syscall'},'Call closure escaped maintained Lean functions')
 require(not re.search(r'^\s*@',ir,re.M),'Component acquired global state/static strings')
 reverse={symbol:source for source,symbol in names.items()}
 rows=[]
 for m in definitions:
  body=re.sub(r'@([A-Za-z0-9_.$]+)',lambda r:'@'+reverse.get(r[1],r[1]),m[0])
  body=' '.join('\n'.join(line.split(';',1)[0] for line in body.splitlines()).split())
  rows.append((reverse[m[1]],body))
 contract=sorted(line.strip() for line in ir.splitlines() if re.match(r'^(?:target (?:datalayout|triple)|attributes #|declare )',line))
 return digest({'bodies':sorted(rows),'module':contract})
def llvm(ir,names,optimized):
 d=llvm_digest(ir,names);require(d==PINS['post' if optimized else 'pre'],'Complete String/UTF8/lifetime/width/status LLVM preimage differs')
 generated=[source for source in names if '.__lemma_managed_string_v06.' in source]
 require(len(generated)==21,'Generated ordinary closure differs')
 for name in ('validateUTF8','fromByteArray','toByteArray','release','getSome','releaseOption','append','retain'):
  require('Lemma.User.Runtime.ManagedString.'+name in names,'Real String runtime helper absent: '+name)
 return {'optimized':optimized,'definitions':len(names),'complete_preimage_sha256':d,'undefined':['lemma_exec_syscall']}
def elf(data,names):
 require(len(data)>=64 and data[:7]==b'\x7fELF\x02\x01\x01','Missing RV64 little-endian ELF')
 h=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
 require(h[1:4]==(1,243,1) and h[7]==0 and h[8]==64 and h[11]==64 and h[12]==10 and h[13]<10,'Object architecture/header/section count differs')
 require(h[6]+h[12]*64<=len(data),'Truncated section inventory')
 ss=[struct.unpack_from('<IIQQQQIIQQ',data,h[6]+i*64) for i in range(10)]
 def contents(s):
  require(s[4]+s[5]<=len(data),'Truncated ELF section');return data[s[4]:s[4]+s[5]]
 def string(table,index):
  require(index<len(table) and b'\0' in table[index:],'Invalid ELF string');return table[index:].split(b'\0',1)[0].decode('ascii')
 labels=contents(ss[h[13]]);sections={string(labels,s[0]):s for s in ss}
 require(set(sections)=={'','.strtab','.text','.rela.text','.rodata.cst8','.stack_sizes','.rela.stack_sizes','.note.GNU-stack','.riscv.attributes','.symtab'},'Object acquired runtime/data/unknown sections')
 text=sections['.text'];require(text[1:3]==(1,6) and text[5]==14704 and text[8]==4,'Real RV64IM text geometry differs')
 require(hashlib.sha256(contents(text)).hexdigest()==PINS['text'],'Complete RV64 text differs')
 pool=sections['.rodata.cst8'];require(pool[1:3]==(1,18) and pool[9]==8 and pool[5]==120,'Cookie-only merged constant geometry differs')
 require([struct.unpack_from('<Q',contents(pool),i)[0] for i in range(0,120,8)]==POOL,'Object cookie/layout constants differ')
 require(b'rv64i2p1_m2p0_zicsr2p0_zifencei2p0_zmmul1p0\0' in contents(sections['.riscv.attributes']),'Actual object ISA attributes differ')
 symbols=sections['.symtab'];require(symbols[9]==24 and symbols[5]%24==0 and symbols[6]<10,'Malformed symbol table')
 strings=contents(ss[symbols[6]]);globals_=set();undefined=set()
 for i in range(0,symbols[5],24):
  name,info,other,index,value,size=struct.unpack_from('<IBBHQQ',data,symbols[4]+i);label=string(strings,name)
  if info>>4==1:
   require(other==0,'Unreviewed ELF symbol visibility')
   if index==0:undefined.add(label)
   else:require(index==2 and (info&15)==2 and value+size<=text[5],'Global object symbol outside code');globals_.add(label)
 require(globals_==set(names.values()) and undefined=={'lemma_exec_syscall'},'Object source/global/undefined inventory differs')
 return {'text_bytes':text[5],'text_sha256':PINS['text'],'cookie_words':15,'globals':len(globals_),'undefined':sorted(undefined)}
def check(path):
 c=json.loads((path/'catalog.json').read_text());names=mapping((path/'symbols.txt').read_text());pre=(path/'program.ll').read_text();post=(path/'program.opt.ll').read_text();obj=(path/'program.o').read_bytes()
 baseline={'catalog':catalog(c),'pre':llvm(pre,names,False),'post':llvm(post,names,True),'object':elf(obj,names)};rejects=[]
 def reject(label,fn):
  try:fn()
  except (Core0Error,KeyError,ValueError,struct.error) as e:rejects.append({'name':label,'error':str(e)});return
  raise Core0Error('Actual artifact mutation accepted: '+label)
 changed=copy.deepcopy(c);changed['maximum_utf8_bytes']=41;reject('bound41',lambda:catalog(changed))
 changed=copy.deepcopy(c);changed['genuine_ir'][0]['genuine_ir'][0]['genuine_ir']+='\nchanged';reject('genuine_source_changed',lambda:catalog(changed))
 for optimized,ir in [(False,pre),(True,post)]:
  from audit_kernel import _ir_definition_body
  for source in ('Lemma.User.Runtime.ManagedString.utf8Step','Lemma.User.Runtime.ManagedString.releaseOption','Lemma.User.Runtime.ManagedString.toByteArray','Lemma.User.Runtime.Arena.release'):
   body=_ir_definition_body(ir,names[source]);require(body is not None,'Actual lifetime/UTF8 body mutation anchor absent')
   changed=ir.replace(body,body+'\n  %unreviewed_semantic_change = add i64 40, 1',1)
   reject(('post' if optimized else 'pre')+'_'+source,lambda changed=changed,optimized=optimized:llvm(changed,names,optimized))
  reject(('post' if optimized else 'pre')+'_foreign_runtime',lambda ir=ir,optimized=optimized:llvm(ir.replace('@lemma_exec_syscall','@lean_string_to_utf8'),names,optimized))
 changed=bytearray(obj);changed[64]^=1;reject('changed_instruction',lambda:elf(changed,names))
 return {'status':'PASS','scope':'Genuine ordinary String/UTF8/Option component only; isolated RV64 execution and production authority separate','artifacts':{n:sha256(path/n) for n in ('catalog.json','symbols.txt','program.ll','program.opt.ll','program.o')},'baseline':baseline,'rejected_actual_mutations':rejects}
def main():
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();require(not a.output.exists(),'Result exists');r=check(a.directory);write_json(a.output,r);print('MANAGED_STRING_COMPONENT_AUDIT:PASS',len(r['rejected_actual_mutations']),'actual artifacts; isolated execution separate')
if __name__=='__main__':
 try:main()
 except (Core0Error,OSError,ValueError,KeyError,struct.error) as e:print('MANAGED_STRING_COMPONENT_AUDIT:FAIL',e,file=sys.stderr);raise SystemExit(1)
