"""Closed version authority for the isolated arithmetic implementation.

These u64s are implementation/contract registry identities, never ELF or source
hashes. Independent full implementation preimages below bind genuine source
names/signatures/effects, complete pre/post LLVM bodies and call closure. Actual
source/tool/ELF correspondence remains in the ordinary strict artifact audit.
"""
from __future__ import annotations
import hashlib
import json
import re
from core0_common import Core0Error

FIELD = 'arithmetic_sums_execution_identity'
VERSION = 'lemma-arithmetic-execution-identity-v2'
REGISTRY = {
 'contract_version': VERSION,
 'implementation': {'name':'lemma-isolated-arithmetic-sums-v1','id':0x0003000100000001},
 'lowering': {'name':'core0-user-v0.3/lemma-managed-sums-v1','id':0x0003000000000001},
 'runtime': {'name':'lemma-owned-arena-sum-cookie-v1','id':0x0001000100000001},
 'resources': {'name':'lemma-arithmetic-resource-v1','id':0x000100000000001f,
               'heap_objects':31,'semantic_budgets':[0,8],'deadline_ticks':10000000},
}
CONFIGURATIONS = frozenset({'lemmasim-silicon-sums-notebook','lemmasim-silicon-sums-initialize','lemmasim-silicon-sums-arithmetic-oom-development'}) | frozenset(('lemmasim-silicon-bulk-notebook', 'lemmasim-silicon-bulk-initialize', 'lemmasim-silicon-product-bulk-notebook', 'lemmasim-silicon-usb-bulk-notebook', 'lemmasim-silicon-usb-bulk-initialize'))
ROOT = 'Lemma.Services.Arithmetic.ServerV3.main'
PROTOCOL = 'Lemma.Services.Arithmetic.ProtocolV3.'
# Independently inspected source-bound genuine User3 Arithmetic probe binds
# this one closed software deployment. Complete declaration headers/attributes,
# bodies, real helpers and calls participate. No implementation authority comes
# from a target catalog self-report or an artifact supplied expected digest.
EXPECTED = {'catalog': '92745df37120a4c86e7aa36b82c9142c87cf4dde7cabc644a548e2dc021c3f93', 'pre_sums': 'e2b8f1b5cf001590e5b8fa6a2b2bd26a49d46747fab02b2457d51d73c3c4ef90', 'post_sums': 'e30b37feea8568e3bc7cbb9d704380cbc9d8c0531b6c40688bc0d611eec2a68d'}



def require(value, message):
 if not value: raise Core0Error(message)


def canonical(source):
 return re.sub(r'^_private\..*?\.[0-9]+\.', '', source)


def selected(unit):
 return unit.get('role')=='user' and unit.get('image_key')=='arithmetic' and unit.get('configuration') in CONFIGURATIONS


def contract(unit):
 if unit.get('image_key')!='arithmetic':
  require(FIELD not in unit,'Non-Arithmetic unit acquired execution-version authority')
  return None
 rows=unit.get('functions',[])
 has_v3=any(canonical(row.get('source','')).startswith(PROTOCOL) for row in rows)
 if not has_v3:
  require(FIELD not in unit, 'Legacy arithmetic acquired new execution-version authority')
  return None
 require(selected(unit) and unit.get('contract_version')=='core0-user-v0.3',
         'Arithmetic execution identity escaped the exact managed isolated deployment')
 require(unit.get(FIELD)==REGISTRY, 'Arithmetic implementation/lowering/runtime/resource registry differs')
 return REGISTRY


def catalog_inventory(unit):
 rows=unit.get('functions')
 require(isinstance(rows,list) and rows, 'Arithmetic execution source inventory empty')
 sources=[canonical(row.get('source','')) for row in rows]
 symbols=[row.get('symbol') for row in rows]
 require(len(sources)==len(set(sources)) and len(symbols)==len(set(symbols)) and
         all(isinstance(source,str) and source for source in sources) and
         all(isinstance(symbol,str) and symbol for symbol in symbols),
         'Arithmetic execution source/symbol inventory malformed or duplicated')
 require(ROOT in sources,'Arithmetic execution root source missing')
 require(unit.get('roots')==[{'symbol':symbols[sources.index(ROOT)],'source':ROOT,'id':1,'args':['u64']}],
         'Arithmetic execution root differs')
 require({PROTOCOL+'reply',PROTOCOL+'validateRequest',
          'Lemma.Mathematics.ManagedSumSubmission.check',
          'Lemma.User.Runtime.ManagedSums.allocate',
          'Lemma.User.Runtime.Arena.allocate'}<=set(sources),
         'Arithmetic execution closure omitted protocol, genuine constructor or real heap')
 payload={'functions':sorted([{'source':source,'args':row.get('args'),
   'effects':sorted(row.get('effects',[]))} for source,row in zip(sources,rows)],key=lambda row:row['source']),
   'loops':unit.get('used_loops'), 'execution_ops':unit.get('used_execution_ops'),
   'device_ops':unit.get('used_device_ops'), 'managed_sums':unit.get('managed_sums')}
 # Generated symbol numbers and private module indices have no version meaning.
 names={symbol:source for symbol,source in zip(symbols,sources)}
 encoded=json.dumps(payload,sort_keys=True,separators=(',',':'))
 for symbol,source in sorted(names.items(),key=lambda row:-len(row[0])):
  encoded=encoded.replace(symbol,source)
 encoded=re.sub(r'_private\.[A-Za-z0-9_.]+?\.[0-9]+\.', '', encoded)
 return hashlib.sha256(encoded.encode()).hexdigest()


def llvm_inventory(ir, unit):
 from audit_kernel import parse_definitions_and_calls, _ir_definition_body
 definitions,_,_=parse_definitions_and_calls(ir)
 names={row['symbol']:canonical(row['source']) for row in unit['functions']}
 require(set(names)<=definitions, 'Arithmetic complete LLVM source closure missing')
 bodies=[]; closure={}
 for symbol in sorted(definitions):
  body=_ir_definition_body(ir,symbol)
  require(isinstance(body,str) and body, 'Arithmetic emitted body missing')
  calls=parse_definitions_and_calls(body)[2]
  closure[names.get(symbol,symbol)]=sorted(names.get(call,call) for call in calls)
  def replace(match):
   name=match.group(1)
   return '@'+names.get(name,name)
  header=re.search(r'^define[^\n]*@'+re.escape(symbol)+r'\([^\n]*\)[^\n]*\{',ir,re.MULTILINE)
  require(header is not None,'Arithmetic emitted declaration header missing')
  body=header.group(0)+'\n'+body
  body=re.sub(r'@([A-Za-z0-9_.$]+)',replace,body)
  body=' '.join('\n'.join(line.split(';',1)[0] for line in body.splitlines()).split())
  bodies.append((names.get(symbol,symbol),body))
 module_lines=[line.strip() for line in ir.splitlines() if re.match(r'^(?:target (?:datalayout|triple)|attributes #|declare )',line)]
 module_lines=[re.sub(r'@([A-Za-z0-9_.$]+)',lambda match:'@'+names.get(match.group(1),match.group(1)),line) for line in module_lines]
 encoded=json.dumps({'bodies':sorted(bodies),'module_contract':sorted(module_lines)},separators=(',',':'))
 return hashlib.sha256(encoded.encode()).hexdigest(), closure


def validate(ir, unit, *, optimized):
 if contract(unit) is None:return None
 catalog=catalog_inventory(unit)
 require(EXPECTED['catalog'] is not None and catalog==EXPECTED['catalog'],
         'Arithmetic complete genuine source/contract inventory differs from implementation version')
 digest,closure=llvm_inventory(ir,unit)
 stage='post_sums' if optimized else 'pre_sums'
 require(EXPECTED[stage] is not None and digest==EXPECTED[stage],
         'Arithmetic complete emitted implementation/call graph differs from implementation version')
 return {'contract_version':VERSION,'registry':REGISTRY,'catalog_sha256':catalog,
         'emitted_preimage_sha256':digest,'optimized':optimized,'complete_calls':closure,
         'scope':'Closed implementation-version authority; IDs are not artifact digests or proof-kernel completion'}
