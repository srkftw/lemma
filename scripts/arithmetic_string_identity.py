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

FIELD = 'arithmetic_string_execution_identity'
VERSION = 'lemma-arithmetic-execution-identity-v5'
REGISTRY = {
 'contract_version': VERSION,
 'implementation': {'name':'lemma-isolated-arithmetic-string-v1','id':0x0006000100000001},
 'lowering': {'name':'core0-user-v0.6/lemma-managed-string-v1','id':0x0006000000000001},
 'runtime': {'name':'lemma-owned-arena-string-graph-v1','id':0x0001000400000001},
 'resources': {'name':'lemma-arithmetic-string-resource-v1','id':0x000400000000001f,
               'heap_objects':31,'maximum_utf8_bytes':40,'semantic_budgets':[0,8],'deadline_ticks':10000000},
}
CONFIGURATIONS = frozenset(('lemmasim-silicon-string-bulk-notebook','lemmasim-silicon-string-bulk-initialize','lemmasim-silicon-string-arithmetic-oom-development'))
ROOT = 'Lemma.Services.Arithmetic.ServerV6.main'
PROTOCOL = 'Lemma.Services.Arithmetic.ProtocolV6.'
# Independently inspected source-bound genuine User6 Arithmetic probe binds
# this one closed software deployment. Complete declaration headers/attributes,
# bodies, real helpers and calls participate. No implementation authority comes
# from a target catalog self-report or an artifact supplied expected digest.
EXPECTED = {'catalog': 'b0b092d9c677cf256c46d25b3061f5bed5115c0f4777b42aa1498f5c9d515a4f', 'pre_bytes': '17f4bacf35ebdf15ef8f7114025143f883bab9563a5ec55e00532d0071537e6e', 'post_bytes': '3f34c294a0e72a0e723adfc27968bce80bd58daaf142dcac6a4e7a33d57c0677'}



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
 has_v6=any(canonical(row.get('source','')).startswith(PROTOCOL) for row in rows)
 if not has_v6:
  require(FIELD not in unit, 'Legacy arithmetic acquired new execution-version authority')
  return None
 require(selected(unit) and unit.get('contract_version')=='core0-user-v0.6',
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
          'Lemma.Mathematics.ManagedStringSubmissionAction.check',
          'Lemma.User.Runtime.ManagedString.fromByteArray',
          'Lemma.User.Runtime.Arena.allocate'}<=set(sources),
         'Arithmetic execution closure omitted protocol, genuine String payload or real heap')
 payload={'functions':sorted([{'source':source,'args':row.get('args'),
   'effects':sorted(row.get('effects',[]))} for source,row in zip(sources,rows)],key=lambda row:row['source']),
   'loops':unit.get('used_loops'), 'execution_ops':unit.get('used_execution_ops'),
   'device_ops':unit.get('used_device_ops'), 'managed_string':unit.get('managed_string')}
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
         'Arithmetic String implementation acquired unreviewed global state')
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


# Source-bound ordinary Notebook dispatch produced by LLVM20 O2 for the
# explicitly selected String deployment. Exact typed/effectful owner bodies,
# caller word reads, status propagation, callees, switch domains and defaults
# are pinned. The generic machine scanner still independently closes each
# table's bounds, relocations, code targets and byte extent.
NOTEBOOK_JUMPS = {
 'Lemma.Applications.Notebook.pollArithmetic': (['u64']*4,['checked-access','io-order','virtual-read','user-syscall','privilege-transition'],[2,3,4,5,6],'19b91f50d6277c63b6f546634d96eecacb20e81fbb78726a73fbae6fac07f1f7'),
 'Lemma.Documents.Mathematics.clearExecution': (['u64'],['checked-access','virtual-read','virtual-write'],[3,4,5,6,7],'26306216263fa263aaa07c8a4bc249752c172ee99e286955c8eccb4026416794'),
 'Lemma.Applications.Notebook.completeArithmetic': (['u64']*5,['checked-access','virtual-read','virtual-write'],[2,3,4,5,6],'b17684dd06af6d4800bc41b6b50e7d735c9eb9c921be7b6838674417b6027915'),
 'Lemma.Applications.Notebook.createArithmetic': (['u64']*2,['checked-access','virtual-read','virtual-write'],[2,3,4,5,6],'84151f114f07649ef6a95d2d942c7b3f8f86bbb464542a2105fb4b0deebdf01a'),
 'Lemma.Mathematics.ExecutionIdentityV5.validateSlot': (['u64']*3,['checked-access','virtual-read'],[2,3,4,5,6],'3fb373adabc05142f37390ef44d8672523544cb765e326ada1dbbf3e6784b0ab'),
 'Lemma.Applications.Notebook.upgradeArithmetic': (['u64']*2,['checked-access','virtual-read','virtual-write'],[2,3,4,5,6],'5373a087031100ad6255d0d2050386886606829696f7c5e3f9f27593dff02008'),
 'Lemma.Applications.Notebook.callArithmetic': (['u64']*4,['checked-access','io-order','virtual-read','virtual-write','user-syscall','privilege-transition'],[2,3,4,5,6],'9da74e435780878b51ed6ae88cd7a2ce6724bbf8eb493172d2b9890d42e9eb24'),
}

def notebook_jump_spec(ir,unit,source,symbol):
 if source not in NOTEBOOK_JUMPS:return None
 # The new ordinary scalar selection is also present in the common
 # Notebook source compiled for its old User1/User2 deployments. Genuine
 # source-bound exports independently reproduced all seven exact owner bodies
 # and signatures under both profiles. This grants no managed String/runtime
 # authority to either profile; only their existing bounded scalar switches.
 from lemmasim_readonly import DOCUMENT4_NOTEBOOK_PROFILES
 expected=DOCUMENT4_NOTEBOOK_PROFILES.get(unit.get('configuration'))
 require(expected is not None and unit.get('role')=='user'
   and unit.get('image_key')=='notebook' and unit.get('contract_version')==expected,
   'String Notebook dispatch escaped its exact Notebook deployment/image/profile')
 rows=unit.get('functions',[]);selected=[r for r in rows if canonical(r.get('source',''))==source]
 args,effects,cases,digest=NOTEBOOK_JUMPS[source]
 require(len(selected)==1 and selected[0].get('symbol')==symbol
   and selected[0].get('args')==args and selected[0].get('effects')==effects,
   'String Notebook dispatch source/signature/effects differs')
 from audit_kernel import _ir_definition_body
 body=_ir_definition_body(ir,symbol)
 require(isinstance(body,str) and body,'String Notebook dispatch actual owner absent')
 names={r['symbol']:canonical(r['source']) for r in rows}
 rebound=re.sub(r'@([^ (]+)',lambda m:'@'+names.get(m[1],m[1]),body)
 normalized=' '.join(' '.join(line.split(';',1)[0].strip() for line in rebound.splitlines()).split())
 require(hashlib.sha256(normalized.encode()).hexdigest()==digest,
   'String Notebook dispatch complete checked body/default/callee differs')
 domains=[sorted(int(v) for v in re.findall(r'i\d+ (-?\d+), label',block))
   for block in re.findall(r'switch i\d+ [^\n]+\[([^]]+)\]',body,re.S)]
 require(domains==[cases],'String Notebook dispatch exact switch domain differs')
 return ('user',5,args,effects,cases)
