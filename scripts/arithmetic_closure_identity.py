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

FIELD = 'arithmetic_closure_execution_identity'
VERSION = 'lemma-arithmetic-execution-identity-v6'
REGISTRY = {
 'contract_version': VERSION,
 'implementation': {'name':'lemma-isolated-arithmetic-closure-v1','id':0x0007000100000001},
 'lowering': {'name':'core0-user-v0.7/lemma-managed-closure-v1','id':0x0007000000000001},
 'runtime': {'name':'lemma-owned-arena-closure-graph-v1','id':0x0001000500000001},
 'resources': {'name':'lemma-arithmetic-closure-resource-v1','id':0x000500000000001f,
               'heap_objects':31,'maximum_captures':4,'maximum_targets':8,'ordinary_peak_objects':9,'semantic_budgets':[0,8],'deadline_ticks':10000000},
}
# Whole ServerV8 is a new implementation identity. Its inherited closure
# lowering/runtime/resource identities and the historical V7 registry stay exact.
PARAMETERIZED_REGISTRY = {**REGISTRY,
 'contract_version':'lemma-arithmetic-execution-identity-v7',
 'implementation':{'name':'lemma-isolated-arithmetic-parameterized-closure-v1','id':0x0008000100000001},
 'parameterized':{'version':2,'request_bytes':192,'reply_bytes':192,'checker_id':0x0002000000000001}}
from multimodal_deployment import CONFIGURATIONS as MULTIMODAL_CONFIGURATIONS
from closure_deployment import ALL_CONFIGURATIONS as CLOSURE_CONFIGURATIONS
CONFIGURATIONS = frozenset(CLOSURE_CONFIGURATIONS)
ROOT = 'Lemma.Services.Arithmetic.ServerV7.main'
PROTOCOL = 'Lemma.Services.Arithmetic.ProtocolV7.'
# Independently inspected source-bound genuine User7 Arithmetic probe binds
# this one closed software deployment. Complete declaration headers/attributes,
# bodies, real helpers and calls participate. No implementation authority comes
# from a target catalog self-report or an artifact supplied expected digest.
EXPECTED = {'catalog': 'aa9615404959c146211706cb0d023457738cff5d1a492d1db2d5661aa8345fdf', 'pre_bytes': '46fb4e4cd9b6766538ce9093b1c6496fea1b89962c9892c42853e826b1321372', 'post_bytes': 'e05e9820e49cac0257fbc7a04f60505b8424f50025eafec507dc23c583f30149'}



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
 has_v7=any(canonical(row.get('source','')).startswith(PROTOCOL) for row in rows)
 if not has_v7:
  require(FIELD not in unit, 'Legacy arithmetic acquired new execution-version authority')
  return None
 require(selected(unit) and unit.get('contract_version')=='core0-user-v0.7',
         'Arithmetic execution identity escaped the exact managed isolated deployment')
 registry = PARAMETERIZED_REGISTRY if unit.get('configuration') in MULTIMODAL_CONFIGURATIONS else REGISTRY
 require(unit.get(FIELD)==registry, 'Arithmetic implementation/lowering/runtime/resource registry differs')
 if unit.get('configuration') in MULTIMODAL_CONFIGURATIONS:
  require(any(canonical(row.get('source',''))=='Lemma.Services.Arithmetic.ServerV8.main' for row in rows),
          'Parameterized implementation lacks its genuine ServerV8 root')
 return registry


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
          'Lemma.Mathematics.ManagedClosureSubmissionAction.check',
          'Lemma.User.Runtime.ManagedClosure.create',
          'Lemma.User.Runtime.Arena.allocate'}<=set(sources),
         'Arithmetic execution closure omitted protocol, genuine closure payload or real heap')
 payload={'functions':sorted([{'source':source,'args':row.get('args'),
   'effects':sorted(row.get('effects',[]))} for source,row in zip(sources,rows)],key=lambda row:row['source']),
   'loops':unit.get('used_loops'), 'execution_ops':unit.get('used_execution_ops'),
   'device_ops':unit.get('used_device_ops'), 'managed_closure':unit.get('managed_closure')}
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
         'Arithmetic closure implementation acquired unreviewed global state')
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
 if unit.get('configuration') in MULTIMODAL_CONFIGURATIONS:
  from multimodal_target import validate as validate_multimodal
  return validate_multimodal(ir,unit,optimized=optimized)
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




# Independently inspected actual User1/User2 checked source exports under pinned
# LLVM20O2. The7 exact owners below are equal under both inherited profiles;
# this only admits their bounded scalar dispatch, never closure execution in
# either historical User profile. Original6-case bodies retain old auditor pins.
NOTEBOOK_JUMPS = {'Lemma.Applications.Notebook.callArithmetic': (['u64', 'u64', 'u64', 'u64'],
                                                ['checked-access',
                                                 'io-order',
                                                 'virtual-read',
                                                 'virtual-write',
                                                 'user-syscall',
                                                 'privilege-transition'],
                                                [2, 3, 4, 5, 6, 7],
                                                'b7d67b3421e56d1f2850e7734331bf8eb51cc754d6431053d2c46529b7c140f7'),
 'Lemma.Applications.Notebook.completeArithmetic': (['u64', 'u64', 'u64', 'u64', 'u64'],
                                                    ['checked-access', 'virtual-read', 'virtual-write'],
                                                    [2, 3, 4, 5, 6, 7],
                                                    'fd154c5a76a731ad0724f5df5b1da99fbd12c52a096427a3e4c8531f3fee265c'),
 'Lemma.Applications.Notebook.createArithmetic': (['u64', 'u64'],
                                                  ['checked-access', 'virtual-read', 'virtual-write'],
                                                  [2, 3, 4, 5, 6, 7],
                                                  'ce8df41fd8b863831152b4f562bb72c67773e92b23a7a2fbe06a3d60c076e761'),
 'Lemma.Applications.Notebook.pollArithmetic': (['u64', 'u64', 'u64', 'u64'],
                                                ['checked-access',
                                                 'io-order',
                                                 'virtual-read',
                                                 'user-syscall',
                                                 'privilege-transition'],
                                                [2, 3, 4, 5, 6, 7],
                                                '5b86b1a2ca754658d2a881b043e7903e8061f977fcd7b0ad352ded74a1c70902'),
 'Lemma.Applications.Notebook.upgradeArithmetic': (['u64', 'u64'],
                                                   ['checked-access', 'virtual-read', 'virtual-write'],
                                                   [2, 3, 4, 5, 6, 7],
                                                   '1b716649c3a49f9b1359cd40de31e83de5d3359c584c8908548b4eb7204d88b6'),
 'Lemma.Documents.Mathematics.clearExecution': (['u64'],
                                                ['checked-access', 'virtual-read', 'virtual-write'],
                                                [3, 4, 5, 6, 7, 8],
                                                '904995f4c576ae667b612da4f8307ec29e32f01e3cc49662189cdf5481aa10d1'),
 'Lemma.Mathematics.ExecutionIdentityV6.validateSlot': (['u64', 'u64', 'u64'],
                                                        ['checked-access', 'virtual-read'],
                                                        [2, 3, 4, 5, 6, 7],
                                                        'c7c0890ef8ebd04c3eadcef313f5e09421b2d1412082f1523c3a170e7928feb0')}


def notebook_jump_spec(ir,unit,source,symbol):
 if source not in NOTEBOOK_JUMPS:return None
 from audit_kernel import _ir_definition_body
 body=_ir_definition_body(ir,symbol)
 require(isinstance(body,str) and body,'Closure Notebook dispatch actual owner absent')
 names={r['symbol']:canonical(r['source']) for r in unit.get('functions',[])}
 rebound=re.sub(r'@([^ (]+)',lambda m:'@'+names.get(m[1],m[1]),body)
 normalized=' '.join(' '.join(line.split(';',1)[0].strip() for line in rebound.splitlines()).split())
 args,effects,cases,digest=NOTEBOOK_JUMPS[source]
 actual=hashlib.sha256(normalized.encode()).hexdigest()
 # Original common selectors keep their separately pinned predecessor route.
 # Unknown bodies still reach the original fail-closed scanner/pin checks.
 if actual!=digest:return None
 from lemmasim_readonly import DOCUMENT4_NOTEBOOK_PROFILES
 expected=DOCUMENT4_NOTEBOOK_PROFILES.get(unit.get('configuration'))
 require(expected is not None and unit.get('role')=='user' and unit.get('image_key')=='notebook'
   and unit.get('contract_version')==expected,'Closure Notebook dispatch escaped its exact inherited deployment/image/profile')
 selected=[r for r in unit.get('functions',[]) if canonical(r.get('source',''))==source]
 require(len(selected)==1 and selected[0].get('symbol')==symbol and selected[0].get('args')==args
   and selected[0].get('effects')==effects,'Closure Notebook dispatch source/signature/effects differs')
 domains=[sorted(int(v) for v in re.findall(r'i\d+ (-?\d+), label',block))
   for block in re.findall(r'switch i\d+ [^\n]+\[([^]]+)\]',body,re.S)]
 require(domains==[cases],'Closure Notebook dispatch exact switch domain/default differs')
 return ('user',max(cases)-min(cases)+1,args,effects,cases)
