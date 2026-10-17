"""Closed version authority for the isolated arithmetic implementation.

These u64s are implementation/contract registry identities, never ELF or source
hashes. Independent full implementation preimages below bind genuine source
names/signatures/effects, complete pre/post LLVM bodies and call closure. Actual
source/tool/ELF correspondence remains in the ordinary strict artifact audit.
"""
from __future__ import annotations
import hashlib
from course_deployment import CONFIGURATIONS as LEGACY_COURSE_CONFIGURATIONS
from course_await_deployment import CONFIGURATIONS as COURSE_AWAIT_CONFIGURATIONS
COURSE_CONFIGURATIONS=LEGACY_COURSE_CONFIGURATIONS+COURSE_AWAIT_CONFIGURATIONS
import json
import re
from core0_common import Core0Error

FIELD = 'arithmetic_array_execution_identity'
VERSION = 'lemma-arithmetic-execution-identity-v4'
REGISTRY = {
 'contract_version': VERSION,
 'implementation': {'name':'lemma-isolated-arithmetic-array-v1','id':0x0005000100000001},
 'lowering': {'name':'core0-user-v0.5/lemma-managed-array-v1','id':0x0005000000000001},
 'runtime': {'name':'lemma-owned-arena-array-graph-v1','id':0x0001000300000001},
 'resources': {'name':'lemma-arithmetic-array-resource-v1','id':0x000300000000001f,
               'heap_objects':31,'maximum_elements':6,'semantic_budgets':[0,8],'deadline_ticks':10000000},
}
CONFIGURATIONS = frozenset(COURSE_CONFIGURATIONS) | frozenset(('lemmasim-silicon-array-bulk-notebook','lemmasim-silicon-array-bulk-initialize','lemmasim-silicon-array-arithmetic-oom-development'))
ROOT = 'Lemma.Services.Arithmetic.ServerV5.main'
PROTOCOL = 'Lemma.Services.Arithmetic.ProtocolV5.'
# Independently inspected source-bound genuine User5 Arithmetic probe binds
# this one closed software deployment. Complete declaration headers/attributes,
# bodies, real helpers and calls participate. No implementation authority comes
# from a target catalog self-report or an artifact supplied expected digest.
EXPECTED = {'catalog': 'e58514b42d69b086dda6781c536c431fb19cce070d78200a56c71bf1a5ed5ca2', 'pre_bytes': '35cec6f34d2e94d44999f36a42fd181f7a82b988608c063e93255e02d42ea51a', 'post_bytes': 'd68bdf3fd294734b8aa9a544b19061bec60e7da9ffb7ef7fa4a24a8a936fd61c'}



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
 has_v5=any(canonical(row.get('source','')).startswith(PROTOCOL) for row in rows)
 if not has_v5:
  require(FIELD not in unit, 'Legacy arithmetic acquired new execution-version authority')
  return None
 require(selected(unit) and unit.get('contract_version')=='core0-user-v0.5',
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
          'Lemma.Mathematics.ManagedArraySubmissionAction.check',
          'Lemma.User.Runtime.ManagedArray.emptyWithCapacity',
          'Lemma.User.Runtime.Arena.allocate'}<=set(sources),
         'Arithmetic execution closure omitted protocol, genuine array payload or real heap')
 payload={'functions':sorted([{'source':source,'args':row.get('args'),
   'effects':sorted(row.get('effects',[]))} for source,row in zip(sources,rows)],key=lambda row:row['source']),
   'loops':unit.get('used_loops'), 'execution_ops':unit.get('used_execution_ops'),
   'device_ops':unit.get('used_device_ops'), 'managed_array':unit.get('managed_array')}
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
 require(not re.search(r'^\s*@',ir,re.MULTILINE),
         'Arithmetic array implementation acquired unreviewed global state')
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
 stage='post_bytes' if optimized else 'pre_bytes'
 require(EXPECTED[stage] is not None and digest==EXPECTED[stage],
         'Arithmetic complete emitted implementation/call graph differs from implementation version')
 return {'contract_version':VERSION,'registry':REGISTRY,'catalog_sha256':catalog,
         'emitted_preimage_sha256':digest,'optimized':optimized,'complete_calls':closure,
         'scope':'Closed implementation-version authority; IDs are not artifact digests or proof-kernel completion'}
