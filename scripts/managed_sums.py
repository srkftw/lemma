"""Closed production sums admission; host artifact audit only, no guest oracle."""
import re
from core0_common import Core0Error
FIELD='managed_sums'
CONFIGURATIONS=frozenset({'lemmasim-silicon-sums-notebook','lemmasim-silicon-sums-initialize','lemmasim-silicon-sums-arithmetic-oom-development'})
ENTRY='Lemma.Mathematics.ManagedResult.compareFiveSix'
PREFIX='Lemma.Mathematics.ManagedResult.'
GENERATED=ENTRY+'.__lemma_managed_sums_v03.'
SOFTWARE_DEPLOYMENT={'contract_version':'lemma-managed-sums-deployment-v1',
 'silicon_profile':'lemma-silicon-dev/0.3.0',
 'user_profiles':{'store':'core0-user-v0.1','notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.3'}}
EXPECTED_IR={'Lemma.Mathematics.ManagedResult.outcome': 'def Lemma.Mathematics.ManagedResult.outcome (x_1 : @& obj) : u64 :=\n  case x_1 : obj of\n  Lemma.Mathematics.ManagedResult.Comparison.equal →\n    let x_2 : u64 := sproj[0, 0] x_1;\n    let x_3 : u64 := sproj[0, 8] x_1;\n    let x_4 : u64 := 6;\n    let x_5 : u64 := UInt64.mul x_2 x_4;\n    let x_6 : u64 := 5;\n    let x_7 : u64 := UInt64.mul x_3 x_6;\n    let x_8 : u8 := UInt64.decEq x_5 x_7;\n    case x_8 : u8 of\n    Bool.false →\n      let x_9 : u64 := 2;\n      ret x_9\n    Bool.true →\n      let x_10 : u64 := 1;\n      ret x_10\n  Lemma.Mathematics.ManagedResult.Comparison.unequal →\n    let x_11 : u64 := sproj[0, 0] x_1;\n    let x_12 : u64 := 0;\n    let x_13 : u8 := UInt64.decEq x_11 x_12;\n    case x_13 : u8 of\n    Bool.false →\n      let x_14 : u64 := 2;\n      ret x_14\n    Bool.true →\n      let x_15 : u64 := 1;\n      ret x_15', 'Lemma.Mathematics.ManagedResult.compare': 'def Lemma.Mathematics.ManagedResult.compare (x_1 : u64) (x_2 : u64) : obj :=\n  let x_3 : u64 := 6;\n  let x_4 : u64 := UInt64.mul x_1 x_3;\n  let x_5 : u64 := 5;\n  let x_6 : u64 := UInt64.mul x_2 x_5;\n  let x_7 : u8 := UInt64.decEq x_4 x_6;\n  case x_7 : u8 of\n  Bool.false →\n    let x_8 : u64 := UInt64.sub x_4 x_6;\n    let x_9 : obj := ctor_1.0.8[Lemma.Mathematics.ManagedResult.Comparison.unequal];\n    sset x_9[0, 0] : u64 := x_8;\n    ret x_9\n  Bool.true →\n    let x_10 : obj := ctor_0.0.16[Lemma.Mathematics.ManagedResult.Comparison.equal];\n    sset x_10[0, 0] : u64 := x_1;\n    sset x_10[0, 8] : u64 := x_2;\n    ret x_10', 'Lemma.Mathematics.ManagedResult.compareFiveSix': 'def Lemma.Mathematics.ManagedResult.compareFiveSix (x_1 : u64) (x_2 : u64) : u64 :=\n  let x_3 : obj := Lemma.Mathematics.ManagedResult.compare x_1 x_2;\n  let x_4 : u64 := Lemma.Mathematics.ManagedResult.outcome x_3;\n  dec x_3;\n  ret x_4'}

def require(value,message):
 if not value:raise Core0Error(message)

def allowed(unit):
 return unit.get('role')=='user' and unit.get('image_key')=='arithmetic' and unit.get('configuration') in CONFIGURATIONS

def notebook_allowed(unit):
 return unit.get('role')=='user' and unit.get('image_key')=='notebook' and unit.get('configuration') in CONFIGURATIONS

def contract(unit):
 generated=[row for row in unit.get('functions',[]) if '.__lemma_managed_sums_v03.' in row.get('source','')]
 if unit.get('contract_version')!='core0-user-v0.3':
  require(FIELD not in unit and not generated,'Historical profile acquired sums authority')
  return None
 require(allowed(unit),'Managed sums User3 escaped exact isolated Arithmetic deployment')
 require(unit.get('software_deployment')==SOFTWARE_DEPLOYMENT,'Managed sums software deployment differs')
 require('managed_records' not in unit and 'arithmetic_execution_identity' not in unit,'Sums deployment impersonated historical record authority')
 c=unit.get(FIELD)
 require(isinstance(c,dict) and set(c)=={'contract_version','compiler_revision','allocator','entry','shapes','functions'},'Managed sums catalog malformed')
 require(c['contract_version']=='lemma-managed-sums-v1' and c['compiler_revision']=='5045d0056413266e57c625dcd7c365b10e377c52' and c['allocator']=='lemma-owned-arena-v1' and c['entry']==ENTRY,'Sums lowering/runtime/entry differs')
 require(c['shapes']==[{'source':PREFIX+'Comparison','id':1,'constructors':[{'source':PREFIX+'Comparison.equal','tag':0,'bytes':24},{'source':PREFIX+'Comparison.unequal','tag':1,'bytes':16}]}],'Sums genuine constructor/type/tag/layout catalog differs')
 rows=c['functions'];require(isinstance(rows,list) and len(rows)==3,'Sums source closure size differs')
 functions={row['source']:row for row in unit['functions']}
 seen=set()
 for row in rows:
  require(isinstance(row,dict) and set(row)=={'source','generated_source','symbol','genuine_ir','checked_action'},'Sums compiler trace fields differ')
  original=row.get('source');require(original in EXPECTED_IR and original not in seen,'Sums ordinary source closure differs');seen.add(original)
  generated_name=GENERATED+original;function=functions.get(generated_name)
  require(function is not None and row['generated_source']==generated_name and row['symbol']==function['symbol'],'Sums generated identity escaped genuine source closure')
  require(function['args']==(['u64'] if original.endswith('.outcome') else ['u64','u64']) and set(function['effects'])<={'checked-access','virtual-read','virtual-write','user-syscall','privilege-transition','io-order'},'Sums generated signature/authority differs')
  require(row['genuine_ir']==EXPECTED_IR[original],'Sums genuine IR differs from declared tags/cases/layouts/borrowing/release')
  require(isinstance(row['checked_action'],str) and 0<len(row['checked_action'])<=262144,'Sums checked action trace absent')
 require(seen==set(EXPECTED_IR) and {row['source'] for row in generated}=={row['generated_source'] for row in rows},'Uncatalogued generated sum function')
 required={'Lemma.User.Runtime.ManagedSums.allocate','Lemma.User.Runtime.ManagedSums.constructorTag','Lemma.User.Runtime.ManagedSums.readField','Lemma.User.Runtime.ManagedSums.writeField','Lemma.User.Runtime.Arena.release','Lemma.User.Runtime.Arena.ensure'}
 require(required<=set(functions),'Sums complete real arena/tag/access/reclamation closure missing')
 return c

def validate(ir,unit,*,optimized):
 c=contract(unit)
 if c is None:return None
 from audit_kernel import _ir_definition_body,parse_definitions_and_calls
 names={row['source']:row['symbol'] for row in unit['functions']}
 allowed_calls={
  PREFIX+'compare':{'Lemma.User.Runtime.ManagedSums.allocate','Lemma.User.Runtime.ManagedSums.writeField','Lemma.User.Runtime.Arena.release'},
  PREFIX+'outcome':{'Lemma.User.Runtime.ManagedSums.constructorTag','Lemma.User.Runtime.ManagedSums.readField'},
  ENTRY:{GENERATED+PREFIX+'compare',GENERATED+PREFIX+'outcome','Lemma.User.Runtime.Arena.release'},
 }
 observed={}
 for row in c['functions']:
  original=row['source'];body=_ir_definition_body(ir,row['symbol'])
  require(body is not None,'Sums generated LLVM missing')
  calls=parse_definitions_and_calls(body)[2]
  require(calls<={names[name] for name in allowed_calls[original]},'Sums lowered calls escaped real tagged arena/reclamation closure')
  if not optimized:
   require(calls=={names[name] for name in allowed_calls[original]},'Sums generated helper or real release omitted')
   require(not re.search(r'\b(?:load|store|alloca|getelementptr|inttoptr|ptrtoint)\b',body),'Sums generator bypassed checked runtime')
   if original.endswith('.compare'):
    alloc=re.findall(r'call \{ i64, i64 \} @'+re.escape(names['Lemma.User.Runtime.ManagedSums.allocate'])+r'\(i64 1, i64 ([01]), i64 (16|24)\)',body)
    require(sorted(alloc)==[('0','24'),('1','16')],'Sums actual tag/payload allocation differs')
    writes=re.findall(r'call \{ i64, i64 \} @'+re.escape(names['Lemma.User.Runtime.ManagedSums.writeField'])+r'\(i64 (%[^, ]+), i64 1, i64 ([01]), i64 (16|24), i64 (8|16), i64 ([^,)]+)\)',body)
    require(len(writes)==3 and sorted((tag,size,index) for _,tag,size,index,_ in writes)==[('0','24','16'),('0','24','8'),('1','16','8')],'Sums field initialization/type/tag/index differs')
    pair=[row for row in writes if row[1]=='0']
    require(pair[0][0]==pair[1][0] and {row[4] for row in pair}=={'%arg0','%arg1'},'Equal constructor payload is not the actual submitted operands')
   if original.endswith('.outcome'):
    require(len(re.findall(r'call \{ i64, i64 \} @'+re.escape(names['Lemma.User.Runtime.ManagedSums.constructorTag'])+r'\(i64 %arg0, i64 1, i64 2, i64 35\)',body))==1,'Sum case omitted exact bounded constructor/layout admission')
    reads=re.findall(r'call \{ i64, i64 \} @'+re.escape(names['Lemma.User.Runtime.ManagedSums.readField'])+r'\(i64 %arg0, i64 1, i64 ([01]), i64 (16|24), i64 (8|16)\)',body)
    require(sorted(reads)==[('0','24','16'),('0','24','8'),('1','16','8')],'Sum projections omitted exact tag/payload bounds')
  observed[original]=sorted(calls)
 return {'contract_version':'lemma-managed-sums-v1','ordinary_sources':sorted(EXPECTED_IR),
  'constructor_bytes':[24,16],'generated_calls':observed,
  'scope':'Genuine ordinary sums/cases/borrowing/projections and real heap/reclamation; complete implementation authority audited separately'}
