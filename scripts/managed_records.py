"""Closed production admission for genuinely compiled ordinary record units.

This is an artifact auditor, never a target interpreter or mathematical oracle.
The first production closure is intentionally narrower than the checked
compiler subset. Legacy source archives have no managed-record authority.
"""
import re
from core0_common import Core0Error

FIELD='managed_records'
ENTRY='Lemma.Mathematics.ManagedRational.compareFiveSix'
PREFIX='Lemma.Mathematics.ManagedRational.'
SOURCES={PREFIX+x for x in ('make','differenceFromFiveSix','compareFiveSix')}
# Independently readable admitted source IR at the immutable Lean revision.
# This closed first production workload pins borrowing, allocation layout,
# exact scalar operations and the real decrement; no arbitrary IR string can
# grant a generated target identity. General subset qualification is separate.
EXPECTED_IR={
 PREFIX+'make': f'def {PREFIX}make (x_1 : u64) (x_2 : u64) : obj :=\n'
  f'  let x_3 : obj := ctor_0.0.16[{PREFIX}Fraction.mk];\n'
  '  sset x_3[0, 0] : u64 := x_1;\n  sset x_3[0, 8] : u64 := x_2;\n  ret x_3',
 PREFIX+'differenceFromFiveSix': f'def {PREFIX}differenceFromFiveSix (x_1 : @& obj) : u64 :=\n'
  '  let x_2 : u64 := sproj[0, 0] x_1;\n  let x_3 : u64 := sproj[0, 8] x_1;\n'
  '  let x_4 : u64 := 6;\n  let x_5 : u64 := UInt64.mul x_2 x_4;\n'
  '  let x_6 : u64 := 5;\n  let x_7 : u64 := UInt64.mul x_6 x_3;\n'
  '  let x_8 : u64 := UInt64.sub x_5 x_7;\n  ret x_8',
 PREFIX+'compareFiveSix': f'def {PREFIX}compareFiveSix (x_1 : u64) (x_2 : u64) : u64 :=\n'
  f'  let x_3 : obj := {PREFIX}make x_1 x_2;\n'
  f'  let x_4 : u64 := {PREFIX}differenceFromFiveSix x_3;\n  dec x_3;\n  ret x_4',
}
CONFIGURATIONS={'lemmasim-silicon-product-notebook','lemmasim-silicon-usb-notebook','lemmasim-silicon-usb-initialize',
 'lemmasim-silicon-power-notebook','lemmasim-silicon-power-initialize',
 'lemmasim-silicon-power-arithmetic-oom-development',
 'lemmasim-silicon-power-arithmetic-fault-development',
 'lemmasim-silicon-power-arithmetic-stall-development',
 'lemmasim-silicon-managed-notebook','lemmasim-silicon-managed-initialize'}

def require(value,message):
 if not value:raise Core0Error(message)

def allowed(unit):
 return unit.get('role')=='user' and unit.get('image_key')=='arithmetic' and unit.get('configuration') in CONFIGURATIONS

MANAGED_NOTEBOOK_CONFIGURATIONS = frozenset({
 'lemmasim-silicon-managed-notebook','lemmasim-silicon-managed-initialize'})
SUMS_NOTEBOOK_CONFIGURATIONS=frozenset({'lemmasim-silicon-sums-notebook','lemmasim-silicon-sums-initialize','lemmasim-silicon-sums-arithmetic-oom-development'})
SOFTWARE_DEPLOYMENT = {'contract_version':'lemma-managed-notebook-deployment-v1',
 'silicon_profile':'lemma-silicon-dev/0.3.0',
 'user_profiles':{'store':'core0-user-v0.1','notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.2'}}

def notebook_profile_allowed(unit):
 return (unit.get('role')=='user' and unit.get('image_key')=='notebook' and
  unit.get('configuration') in MANAGED_NOTEBOOK_CONFIGURATIONS | SUMS_NOTEBOOK_CONFIGURATIONS)

def profile_allowed(unit):
 return allowed(unit) or notebook_profile_allowed(unit)

def contract(unit):
 version=unit.get('contract_version')
 generated=[r for r in unit.get('functions',[]) if '.__lemma_managed_v02.' in r.get('source','')]
 if version!='core0-user-v0.2':
  require(FIELD not in unit and not generated,'Legacy unit acquired managed-record authority')
  return None
 if notebook_profile_allowed(unit):
  from managed_sums import SOFTWARE_DEPLOYMENT as sums_deployment
  expected=sums_deployment if unit.get('configuration') in SUMS_NOTEBOOK_CONFIGURATIONS else SOFTWARE_DEPLOYMENT
  require(unit.get('software_deployment')==expected,
   'Managed Notebook software deployment differs from its exact versioned selection')
  require(FIELD not in unit and not generated,
   'The selected Notebook acquired a managed-record closure outside its empty genuine inventory')
  return None
 require(allowed(unit),'Managed User profile escaped its exact isolated Arithmetic deployment')
 c=unit.get(FIELD)
 require(isinstance(c,dict) and set(c)=={'contract_version','compiler_revision','allocator','entry','shapes','functions'},'Managed record catalog missing or malformed')
 require(c['contract_version']=='lemma-managed-records-v1' and c['compiler_revision']=='5045d0056413266e57c625dcd7c365b10e377c52' and c['allocator']=='lemma-owned-arena-v1' and c['entry']==ENTRY,'Managed record compiler/entry/runtime identity differs')
 require(c['shapes']==[{'source':PREFIX+'Fraction','constructor':PREFIX+'Fraction.mk','id':1,'bytes':24}],'Managed source constructor/layout/cookie differs')
 rows=c['functions'];require(isinstance(rows,list) and len(rows)==3,'Managed genuine closure size differs')
 by_source={r['source']:r for r in unit['functions']}
 seen=set()
 for r in rows:
  require(isinstance(r,dict) and set(r)=={'source','generated_source','symbol','genuine_ir','checked_action'},'Managed function catalog fields differ')
  source=r.get('source');require(source in SOURCES and source not in seen,'Managed ordinary source closure differs');seen.add(source)
  generated_name=ENTRY+'.__lemma_managed_v02.'+source
  f=by_source.get(generated_name)
  require(r['generated_source']==generated_name and f is not None and r['symbol']==f['symbol'],'Managed generated name has no exact genuine source/symbol')
  require(f['args']==(['u64'] if source.endswith('.differenceFromFiveSix') else ['u64','u64']) and set(f['effects'])<= {'checked-access','virtual-read','virtual-write','user-syscall','privilege-transition','io-order'},'Managed generated function signature/authority differs')
  for key in ('genuine_ir','checked_action'):
   require(isinstance(r[key],str) and 0<len(r[key])<=262144,'Managed compiler trace missing or exceeds budget')
  require(r['genuine_ir']==EXPECTED_IR[source],'Managed genuine source IR differs from exact borrowing/layout/arithmetic/release admission')
 require(seen==SOURCES and {r['source'] for r in generated}=={r['generated_source'] for r in rows},'Uncatalogued generated managed source')
 required={'Lemma.User.Runtime.ManagedRecords.allocate','Lemma.User.Runtime.ManagedRecords.readField','Lemma.User.Runtime.ManagedRecords.writeField','Lemma.User.Runtime.Arena.release','Lemma.User.Runtime.Arena.ensure'}
 require(required<=set(by_source),'Managed closure omitted real allocation/field/lifetime helpers')
 return c

def validate(ir,unit,*,optimized):
 c=contract(unit)
 if c is None:return None
 from audit_kernel import _ir_definition_body,parse_definitions_and_calls
 names={r['source']:r['symbol'] for r in unit['functions']}
 rows={r['source']:r for r in c['functions']}
 allowed_calls={
  PREFIX+'make':{'Lemma.User.Runtime.ManagedRecords.allocate','Lemma.User.Runtime.ManagedRecords.writeField','Lemma.User.Runtime.Arena.release'},
  PREFIX+'differenceFromFiveSix':{'Lemma.User.Runtime.ManagedRecords.readField'},
  PREFIX+'compareFiveSix':{ENTRY+'.__lemma_managed_v02.'+PREFIX+'make',ENTRY+'.__lemma_managed_v02.'+PREFIX+'differenceFromFiveSix','Lemma.User.Runtime.Arena.release'},
 }
 observed={}
 for source,r in rows.items():
  body=_ir_definition_body(ir,r['symbol'])
  require(body is not None,'Managed generated LLVM function missing')
  calls=parse_definitions_and_calls(body)[2]
  require(calls<={names[n] for n in allowed_calls[source]},'Managed lowered closure escaped its catalogued allocation/borrow/release calls')
  if not optimized:
   require(calls=={names[n] for n in allowed_calls[source]},'Managed pre-optimization lifetime/helper call missing')
   require(not re.search(r'\b(?:load|store|alloca|getelementptr|inttoptr|ptrtoint)\b',body),'Generated record directly bypasses checked arena helpers')
   if source.endswith('.make'):
    require(len(re.findall(r'call \{ i64, i64 \} @'+re.escape(names['Lemma.User.Runtime.ManagedRecords.allocate'])+r'\(i64 1, i64 24\)',body))==1,'Managed constructor cookie/size/allocation differs')
    writes=re.findall(r'call \{ i64, i64 \} @'+re.escape(names['Lemma.User.Runtime.ManagedRecords.writeField'])+r'\(i64 (%[^, ]+), i64 1, i64 24, i64 (8|16), i64 (%arg[01])\)',body)
    require(len(writes)==2 and writes[0][0]==writes[1][0] and [(r[1],r[2]) for r in writes]==[('8','%arg0'),('16','%arg1')],'Managed initialized fields are not the exact source arguments/layout')
   if source.endswith('.differenceFromFiveSix'):
    reads=re.findall(r'call \{ i64, i64 \} @'+re.escape(names['Lemma.User.Runtime.ManagedRecords.readField'])+r'\(i64 %arg0, i64 1, i64 24, i64 (8|16)\)',body)
    require(reads==['8','16'],'Managed borrowed projection cookie/bounds/source differs')
  observed[source]=sorted(calls)
 return {'contract_version':c['contract_version'],'ordinary_sources':sorted(SOURCES),'layout_bytes':24,'generated_calls':observed,'scope':'Closed ordinary record provenance and real checked helper/lifetime closure; no compiler proof or semantic host oracle'}
