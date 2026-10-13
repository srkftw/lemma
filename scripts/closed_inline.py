"""Independent pre-LLVM-O2 provenance for two opt-in checked optimizations.

This does not compile target code. It admits exactly catalogued literal bodies
and the existing closed physical access guards before ordinary pinned LLVM
inlining. Historical units have no catalog and may not acquire alwaysinline.
"""
from __future__ import annotations
import hashlib,re
from core0_common import Core0Error

CONFIGURATIONS={'lemmasim-silicon-product-notebook','lemmasim-silicon-usb-notebook','lemmasim-silicon-usb-initialize',
 'lemmasim-silicon-power-notebook','lemmasim-silicon-power-initialize',
 'lemmasim-silicon-power-arithmetic-oom-development',
 'lemmasim-silicon-power-arithmetic-fault-development',
 'lemmasim-silicon-power-arithmetic-stall-development'}
USER_CONFIGURATIONS={'lemmasim-silicon-managed-notebook','lemmasim-silicon-managed-initialize',
 'lemmasim-silicon-sums-notebook','lemmasim-silicon-sums-initialize','lemmasim-silicon-sums-arithmetic-oom-development'} | set(('lemmasim-silicon-bulk-notebook', 'lemmasim-silicon-bulk-initialize', 'lemmasim-silicon-product-bulk-notebook', 'lemmasim-silicon-usb-bulk-notebook', 'lemmasim-silicon-usb-bulk-initialize', 'lemmasim-silicon-usb-next-bulk-notebook', 'lemmasim-silicon-usb-next-bulk-initialize', 'lemmasim-silicon-product-next-bulk-notebook'))
BYTES_CONFIGURATIONS={"lemmasim-silicon-bytes-bulk-notebook","lemmasim-silicon-bytes-bulk-initialize","lemmasim-silicon-bytes-arithmetic-oom-development"}
ARRAY_CONFIGURATIONS={"lemmasim-silicon-array-bulk-notebook","lemmasim-silicon-array-bulk-initialize","lemmasim-silicon-array-arithmetic-oom-development"}
STRING_CONFIGURATIONS={"lemmasim-silicon-string-bulk-notebook","lemmasim-silicon-string-bulk-initialize","lemmasim-silicon-string-arithmetic-oom-development"}
USER_CONFIGURATIONS |= BYTES_CONFIGURATIONS | ARRAY_CONFIGURATIONS | STRING_CONFIGURATIONS
CONFIGURATIONS |= USER_CONFIGURATIONS
USER_WRAPPER='lemma-checked-user-word-wrapper-v1'
USER_WORD={
 'execution.virtual-read64':(['u64'],['checked-access','virtual-read'],
  'fd0af723e70f7ca76d98cf1f44a4ebe002fc8a152ece17c2bc8a829032527061'),
 'execution.virtual-write64':(['u64','u64'],['checked-access','virtual-write'],
  '1a63f9b776b46fff6eee8d4c8dcb31518a8dac7f22c2a256d0618b2bd21c83af'),
}
FIELD='checked_inline'
LITERAL='lemma-closed-literals-v1'
WRAPPER='lemma-checked-primitive-wrapper-v1'
TYPES={'u8':('i8','zeroext ',8),'u32':('i32','signext ',32),'u64':('i64','',64)}
PHYSICAL={
 'execution.physical-read8':('read8',['u64'],['checked-access','physical-read']),
 'execution.physical-read64':('read64',['u64'],['checked-access','physical-read']),
 'execution.physical-write8':('write8',['u64','u64'],['checked-access','physical-write']),
 'execution.physical-write64':('write64',['u64','u64'],['checked-access','physical-write']),
}
# Complete guard/result preimages from the source-qualified existing canonical
# kernel-v0.4 lowering. The six physical intervals, width/alignment/error order,
# volatile accesses and exact checked return all participate in these digests.
# This inventory is independent of the newly emitted optimization catalog.
PHYSICAL_PREIMAGE={
 'read8':'ffe4e3c9988d07d56b7510a892e64d0b9edc5731fd29a79f81219b8783674a7f',
 'read64':'b6d20fb781f9919c9f77b62f71912303888dd79062a9fa2feff018f31a297a16',
 'write8':'63a269b22df10c734cb9ed91c691d068f4bbe1a6dcef60e9bed8a45248c4deae',
 'write64':'fe977f053367ff57a971af0bd4b534e65bf9fff45ed59f327af94b9c29938a06',
}

def require(condition,message):
 if not condition: raise Core0Error(message)

def selected(unit):return unit.get('configuration') in CONFIGURATIONS

def catalog(unit):
 if not selected(unit):
  require(FIELD not in unit,'historical unit acquired checked-inline authority')
  return None
 # Historical artifacts of the same machine configuration used noinline.
 # Absence grants no authority; validate() rejects every uncatalogued attribute.
 if FIELD not in unit:return None
 c=unit.get(FIELD)
 keys={'literal_contract','wrapper_contract','literals','wrappers'}
 if unit.get('configuration') in USER_CONFIGURATIONS:keys|={'user_wrapper_contract','user_wrappers'}
 require(isinstance(c,dict) and set(c)==keys and c['literal_contract']==LITERAL and c['wrapper_contract']==WRAPPER,
  'checked-inline contract/catalog absent or malformed')
 if 'user_wrappers' in c:
  require(c['user_wrapper_contract']==USER_WRAPPER and isinstance(c['user_wrappers'],list),
   'checked user-word contract/catalog malformed')
 require(isinstance(c['literals'],list) and isinstance(c['wrappers'],list),'checked-inline row arrays malformed')
 by={r['symbol']:r for r in unit['functions']};seen=set()
 for r in c['literals']:
  require(isinstance(r,dict) and set(r)=={'source','symbol','type','value'},'literal catalog row keys differ')
  f=by.get(r.get('symbol'));require(f is not None and r['source']==f['source'] and f['args']==[] and f['effects']==[],
   'literal catalog is not its zero-argument pure source')
  require(r['type'] in TYPES and type(r['value']) is int and 0<=r['value']<2**TYPES[r['type']][2],
   'literal value/type differs or wraps outside declared width')
  require(r['symbol'] not in seen,'checked-inline source/symbol is duplicated');seen.add(r['symbol'])
 for r in c['wrappers']:
  require(isinstance(r,dict) and set(r)=={'source','symbol','operation'},'wrapper catalog row keys differ')
  f=by.get(r.get('symbol'));op=PHYSICAL.get(r.get('operation'))
  require(unit['role']=='kernel' and unit['contract_version'] in {'core0-kernel-v0.4','core0-kernel-v0.6'} and
   f is not None and op is not None and r['source']==f['source'] and (f['args'],f['effects'])==op[1:],
   'wrapper source/signature/effects/authority differs')
  require(any(o['stable_id']==r['operation'] and o['primitive_symbol'] is None and o['returnkind']=='word'
   for o in unit['used_execution_ops']),'wrapper operation is absent from genuine operation closure')
  require(r['symbol'] not in seen,'checked-inline source/symbol is duplicated');seen.add(r['symbol'])
 for r in c.get('user_wrappers',[]):
  require(isinstance(r,dict) and set(r)=={'source','symbol','operation'},'user-word catalog row keys differ')
  f=by.get(r.get('symbol'));op=USER_WORD.get(r.get('operation'))
  require(unit['role']=='user' and (unit['contract_version'] in {'core0-user-v0.2','core0-user-v0.3'} or unit['contract_version']=='core0-user-v0.4' and unit.get('configuration') in BYTES_CONFIGURATIONS or unit['contract_version']=='core0-user-v0.5' and unit.get('configuration') in ARRAY_CONFIGURATIONS or unit['contract_version']=='core0-user-v0.6' and unit.get('configuration') in STRING_CONFIGURATIONS) and
   unit.get('image_key') in {'notebook','arithmetic'} and f is not None and op is not None and
   r['source']==f['source'] and (f['args'],f['effects'])==op[:2],
   'user-word source/signature/effects/authority differs')
  require(any(o['stable_id']==r['operation'] and o['primitive_symbol'] is None and o['returnkind']=='word'
   for o in unit['used_execution_ops']),'user-word operation absent from genuine closure')
  require(r['symbol'] not in seen,'checked-inline source/symbol is duplicated');seen.add(r['symbol'])
 return c

def _body(ir,symbol):
 from audit_kernel import _ir_definition_body
 return '\n'.join(x.split(';',1)[0].strip() for x in _ir_definition_body(ir,symbol).splitlines() if x.split(';',1)[0].strip())

def _headers(ir):
 return {m[1]:m[0] for m in re.finditer(r'^define [^\n]*@([A-Za-z0-9_.$-]+)\([^\n]*\)[^\n]*\{$',ir,re.M)}

def validate(ir,unit,*,optimized):
 c=catalog(unit);headers=_headers(ir)
 if optimized:
  groups={m[1]:m[2] for m in re.finditer(r'^attributes #(\d+) = \{([^\n]*)\}$',ir,re.M)}
  actual=set()
  for sym,header in headers.items():
   tokens=header+' '+ ' '.join(groups.get(g,'') for g in re.findall(r'#(\d+)',header))
   if re.search(r'\balwaysinline\b',tokens):actual.add(sym)
  expected=set() if c is None else {r['symbol'] for r in c['literals']+c['wrappers']+c.get('user_wrappers',[])}
  require(actual<=expected,'optimized function acquired uncatalogued alwaysinline authority')
  # The trusted preIR audit qualified eligibility and complete guard preimages.
  # The ordinary artifact auditor still checks every optimized memory operation,
  # executable provenance, closed calls and dependency/stack obligations.
  return {'contracts':[] if c is None else [LITERAL,WRAPPER],
    'literal_functions':0 if c is None else len(c['literals']),
    'physical_wrappers':0 if c is None else len(c['wrappers']),
    'scope':'ordinary pinned LLVM optimization of independently audited preIR; no compiler correctness or cycle proof'}
 actual={s for s,h in headers.items() if re.search(r'\balwaysinline\b',h)}
 if c is None:
  require(not actual,'uncatalogued historical alwaysinline function')
  return {'contracts':[],'literal_functions':0,'physical_wrappers':0}
 expected={r['symbol'] for r in c['literals']+c['wrappers']+c.get('user_wrappers',[])}
 require(actual==expected,'alwaysinline function inventory differs from checked catalog')
 literal_expected=set()
 for f in unit['functions']:
  if f['args'] or f['effects']:continue
  body=_body(ir,f['symbol']);m=re.fullmatch(r'entry:\nret (i8|i32|i64) ([0-9]+)',body)
  if m:literal_expected.add(f['symbol'])
 require({r['symbol'] for r in c['literals']}==literal_expected,'literal catalog omitted or invented a closed literal')
 for r in c['literals']:
  ty,ext,_=TYPES[r['type']];sym=r['symbol']
  require(headers.get(sym)=='define '+ext+ty+' @'+sym+'() nounwind alwaysinline {' and
   _body(ir,sym)=='entry:\nret '+ty+' '+str(r['value']),
   'literal preIR is not exactly its typed value return')
 wrapper_expected=set()
 if unit['role']=='kernel':
  for f in unit['functions']:
   if any((f['args'],f['effects'])==op[1:] for op in PHYSICAL.values()) and \
       hashlib.sha256(_body(ir,f['symbol']).encode()).hexdigest() in PHYSICAL_PREIMAGE.values():
    wrapper_expected.add(f['symbol'])
 require({r['symbol'] for r in c['wrappers']}==wrapper_expected,'wrapper catalog omitted or invented a checked one-operation body')
 for r in c['wrappers']:
  op,args,_=PHYSICAL[r['operation']];sym=r['symbol']
  require(headers.get(sym)=='define { i64, i64 } @'+sym+'('+', '.join('i64 %arg'+str(i) for i in range(len(args)))+') nounwind alwaysinline {',
   'wrapper ABI/attribute differs')
  digest=hashlib.sha256(_body(ir,sym).encode()).hexdigest()
  require(digest==PHYSICAL_PREIMAGE[op],'wrapper changed complete physical interval/alignment/error/volatile/result guard')
 user_expected=set()
 if unit['role']=='user' and (unit['contract_version'] in {'core0-user-v0.2','core0-user-v0.3'} or unit['contract_version']=='core0-user-v0.4' and unit.get('configuration') in BYTES_CONFIGURATIONS or unit['contract_version']=='core0-user-v0.5' and unit.get('configuration') in ARRAY_CONFIGURATIONS or unit['contract_version']=='core0-user-v0.6' and unit.get('configuration') in STRING_CONFIGURATIONS) and unit.get('configuration') in USER_CONFIGURATIONS:
  for f in unit['functions']:
   if any((f['args'],f['effects'])==op[:2] and hashlib.sha256(_body(ir,f['symbol']).encode()).hexdigest()==op[2]
          for op in USER_WORD.values()):user_expected.add(f['symbol'])
 require({r['symbol'] for r in c.get('user_wrappers',[])}==user_expected,
  'user-word catalog omitted or invented a checked one-operation body')
 for r in c.get('user_wrappers',[]):
  args,_,digest=USER_WORD[r['operation']];sym=r['symbol']
  require(headers.get(sym)=='define { i64, i64 } @'+sym+'('+', '.join('i64 %arg'+str(i) for i in range(len(args)))+') nounwind alwaysinline {',
   'user-word wrapper ABI/attribute differs')
  require(hashlib.sha256(_body(ir,sym).encode()).hexdigest()==digest,
   'user-word changed complete unsigned range/alignment/error/volatile/result guard')
 # Functions outside the two precisely selected sets retain their exact original
 # external inspectable call boundaries, including every ownership/policy Action.
 for sym,header in headers.items():
  if sym not in expected:require(' nounwind noinline "disable-tail-calls"="true" {' in header,
   'noneligible policy/body acquired changed call-boundary attributes')
 result={'contracts':[LITERAL,WRAPPER],'literal_functions':len(c['literals']),
  'physical_wrappers':len(c['wrappers']),'complete_physical_preimages':PHYSICAL_PREIMAGE}
 if 'user_wrappers' in c:result.update(user_word_wrappers=len(c['user_wrappers']),user_word_contract=USER_WRAPPER)
 return result
