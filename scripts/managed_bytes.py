"""Closed production bytes admission; host artifact audit only, no guest oracle."""
import re
from core0_common import Core0Error
FIELD='managed_bytes'
CONFIGURATIONS=frozenset(('lemmasim-silicon-bytes-bulk-notebook', 'lemmasim-silicon-bytes-bulk-initialize', 'lemmasim-silicon-bytes-arithmetic-oom-development'))
ENTRY='Lemma.Mathematics.ManagedByteSubmission.compareFiveSix'
PREFIX='Lemma.Mathematics.ManagedByteSubmission.'
GENERATED=ENTRY+'.__lemma_managed_bytes_v04.'
SOFTWARE_DEPLOYMENT={'contract_version':'lemma-managed-bytes-bulk-deployment-v1',
 'silicon_profile':'lemma-silicon-dev/0.3.0',
 'user_profiles':{'store':'core0-user-v0.1','notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.4'}}
def software_deployment_for(configuration):
 if configuration not in CONFIGURATIONS:raise Core0Error('Unknown exact managed bytes deployment')
 return SOFTWARE_DEPLOYMENT
EXPECTED_IR={'Lemma.Mathematics.ManagedByteSubmission.readWord': 'def Lemma.Mathematics.ManagedByteSubmission.readWord (x_1 : @& obj) (x_2 : u64) : u64 :=\n  let x_3 : tobj := UInt64.toNat x_2;\n  let x_4 : u8 := ByteArray.get! x_1 x_3;\n  dec x_3;\n  let x_5 : u64 := UInt8.toUInt64 x_4;\n  let x_6 : u64 := 1;\n  let x_7 : u64 := UInt64.add x_2 x_6;\n  let x_8 : tobj := UInt64.toNat x_7;\n  let x_9 : u8 := ByteArray.get! x_1 x_8;\n  dec x_8;\n  let x_10 : u64 := UInt8.toUInt64 x_9;\n  let x_11 : u64 := 8;\n  let x_12 : u64 := UInt64.shiftLeft x_10 x_11;\n  let x_13 : u64 := UInt64.lor x_5 x_12;\n  let x_14 : u64 := 2;\n  let x_15 : u64 := UInt64.add x_2 x_14;\n  let x_16 : tobj := UInt64.toNat x_15;\n  let x_17 : u8 := ByteArray.get! x_1 x_16;\n  dec x_16;\n  let x_18 : u64 := UInt8.toUInt64 x_17;\n  let x_19 : u64 := 16;\n  let x_20 : u64 := UInt64.shiftLeft x_18 x_19;\n  let x_21 : u64 := UInt64.lor x_13 x_20;\n  let x_22 : u64 := 3;\n  let x_23 : u64 := UInt64.add x_2 x_22;\n  let x_24 : tobj := UInt64.toNat x_23;\n  let x_25 : u8 := ByteArray.get! x_1 x_24;\n  dec x_24;\n  let x_26 : u64 := UInt8.toUInt64 x_25;\n  let x_27 : u64 := 24;\n  let x_28 : u64 := UInt64.shiftLeft x_26 x_27;\n  let x_29 : u64 := UInt64.lor x_21 x_28;\n  let x_30 : u64 := 4;\n  let x_31 : u64 := UInt64.add x_2 x_30;\n  let x_32 : tobj := UInt64.toNat x_31;\n  let x_33 : u8 := ByteArray.get! x_1 x_32;\n  dec x_32;\n  let x_34 : u64 := UInt8.toUInt64 x_33;\n  let x_35 : u64 := 32;\n  let x_36 : u64 := UInt64.shiftLeft x_34 x_35;\n  let x_37 : u64 := UInt64.lor x_29 x_36;\n  let x_38 : u64 := 5;\n  let x_39 : u64 := UInt64.add x_2 x_38;\n  let x_40 : tobj := UInt64.toNat x_39;\n  let x_41 : u8 := ByteArray.get! x_1 x_40;\n  dec x_40;\n  let x_42 : u64 := UInt8.toUInt64 x_41;\n  let x_43 : u64 := 40;\n  let x_44 : u64 := UInt64.shiftLeft x_42 x_43;\n  let x_45 : u64 := UInt64.lor x_37 x_44;\n  let x_46 : u64 := 6;\n  let x_47 : u64 := UInt64.add x_2 x_46;\n  let x_48 : tobj := UInt64.toNat x_47;\n  let x_49 : u8 := ByteArray.get! x_1 x_48;\n  dec x_48;\n  let x_50 : u64 := UInt8.toUInt64 x_49;\n  let x_51 : u64 := 48;\n  let x_52 : u64 := UInt64.shiftLeft x_50 x_51;\n  let x_53 : u64 := UInt64.lor x_45 x_52;\n  let x_54 : u64 := 7;\n  let x_55 : u64 := UInt64.add x_2 x_54;\n  let x_56 : tobj := UInt64.toNat x_55;\n  let x_57 : u8 := ByteArray.get! x_1 x_56;\n  dec x_56;\n  let x_58 : u64 := UInt8.toUInt64 x_57;\n  let x_59 : u64 := 56;\n  let x_60 : u64 := UInt64.shiftLeft x_58 x_59;\n  let x_61 : u64 := UInt64.lor x_53 x_60;\n  ret x_61', 'Lemma.Mathematics.ManagedByteSubmission.appendWord': 'def Lemma.Mathematics.ManagedByteSubmission.appendWord (x_1 : obj) (x_2 : u64) : obj :=\n  let x_3 : u8 := UInt64.toUInt8 x_2;\n  let x_4 : obj := ByteArray.push x_1 x_3;\n  let x_5 : u64 := 8;\n  let x_6 : u64 := UInt64.shiftRight x_2 x_5;\n  let x_7 : u8 := UInt64.toUInt8 x_6;\n  let x_8 : obj := ByteArray.push x_4 x_7;\n  let x_9 : u64 := 16;\n  let x_10 : u64 := UInt64.shiftRight x_2 x_9;\n  let x_11 : u8 := UInt64.toUInt8 x_10;\n  let x_12 : obj := ByteArray.push x_8 x_11;\n  let x_13 : u64 := 24;\n  let x_14 : u64 := UInt64.shiftRight x_2 x_13;\n  let x_15 : u8 := UInt64.toUInt8 x_14;\n  let x_16 : obj := ByteArray.push x_12 x_15;\n  let x_17 : u64 := 32;\n  let x_18 : u64 := UInt64.shiftRight x_2 x_17;\n  let x_19 : u8 := UInt64.toUInt8 x_18;\n  let x_20 : obj := ByteArray.push x_16 x_19;\n  let x_21 : u64 := 40;\n  let x_22 : u64 := UInt64.shiftRight x_2 x_21;\n  let x_23 : u8 := UInt64.toUInt8 x_22;\n  let x_24 : obj := ByteArray.push x_20 x_23;\n  let x_25 : u64 := 48;\n  let x_26 : u64 := UInt64.shiftRight x_2 x_25;\n  let x_27 : u8 := UInt64.toUInt8 x_26;\n  let x_28 : obj := ByteArray.push x_24 x_27;\n  let x_29 : u64 := 56;\n  let x_30 : u64 := UInt64.shiftRight x_2 x_29;\n  let x_31 : u8 := UInt64.toUInt8 x_30;\n  let x_32 : obj := ByteArray.push x_28 x_31;\n  ret x_32', 'Lemma.Mathematics.ManagedByteSubmission.empty': 'def Lemma.Mathematics.ManagedByteSubmission.empty (x_1 : u64) : obj :=\n  let x_2 : tobj := UInt64.toNat x_1;\n  let x_3 : obj := ByteArray.emptyWithCapacity x_2;\n  dec x_2;\n  ret x_3', 'Lemma.Mathematics.ManagedByteSubmission.payload': 'def Lemma.Mathematics.ManagedByteSubmission.payload (x_1 : u64) (x_2 : u64) (x_3 : u64) : obj :=\n  let x_4 : obj := Lemma.Mathematics.ManagedByteSubmission.empty x_1;\n  let x_5 : obj := Lemma.Mathematics.ManagedByteSubmission.appendWord x_4 x_2;\n  let x_6 : obj := Lemma.Mathematics.ManagedByteSubmission.appendWord x_5 x_3;\n  ret x_6', 'Lemma.Mathematics.ManagedByteSubmission.compareFiveSix': 'def Lemma.Mathematics.ManagedByteSubmission.compareFiveSix (x_1 : u64) (x_2 : u64) : u64 :=\n  let x_3 : u64 := 16;\n  let x_4 : obj := Lemma.Mathematics.ManagedByteSubmission.payload x_3 x_1 x_2;\n  let x_5 : u64 := 0;\n  let x_6 : u64 := Lemma.Mathematics.ManagedByteSubmission.readWord x_4 x_5;\n  let x_7 : u64 := 8;\n  let x_8 : u64 := Lemma.Mathematics.ManagedByteSubmission.readWord x_4 x_7;\n  dec x_4;\n  let x_9 : u64 := 6;\n  let x_10 : u64 := UInt64.mul x_6 x_9;\n  let x_11 : u64 := 5;\n  let x_12 : u64 := UInt64.mul x_8 x_11;\n  let x_13 : u8 := UInt64.decEq x_10 x_12;\n  case x_13 : u8 of\n  Bool.false →\n    let x_14 : u64 := 2;\n    ret x_14\n  Bool.true →\n    let x_15 : u64 := 1;\n    ret x_15'}


def require(value,message):
 if not value:raise Core0Error(message)

def allowed(unit):
 return unit.get('role')=='user' and unit.get('image_key')=='arithmetic' and unit.get('configuration') in CONFIGURATIONS

def contract(unit):
 generated=[row for row in unit.get('functions',[]) if '.__lemma_managed_bytes_v04.' in row.get('source','')]
 if unit.get('contract_version')!='core0-user-v0.4':
  require(FIELD not in unit and not generated,'Historical profile acquired bytes authority')
  return None
 require(allowed(unit),'Managed bytes User4 escaped exact isolated Arithmetic deployment')
 require(unit.get('software_deployment')==software_deployment_for(unit.get('configuration')),'Managed bytes software deployment differs')
 require(not any(name in unit for name in ('managed_records','managed_sums','arithmetic_execution_identity','arithmetic_sums_execution_identity')),
         'Bytes deployment impersonated historical record/sums authority')
 c=unit.get(FIELD)
 require(isinstance(c,dict) and set(c)=={'contract_version','compiler_revision','allocator','entry','maximum_payload','slots','functions'},'Managed bytes catalog malformed')
 require(c['contract_version']=='lemma-managed-bytes-v1' and c['compiler_revision']=='5045d0056413266e57c625dcd7c365b10e377c52' and c['allocator']=='lemma-owned-arena-v1' and c['entry']==ENTRY and c['maximum_payload']==48 and c['slots']==31,
         'Bytes lowering/runtime/entry/bounds differ')
 rows=c['functions'];require(isinstance(rows,list) and len(rows)==5,'Bytes ordinary source closure size differs')
 functions={row['source']:row for row in unit['functions']}
 seen=set()
 for row in rows:
  require(isinstance(row,dict) and set(row)=={'source','generated_source','symbol','genuine_ir','checked_action'},'Bytes compiler trace fields differ')
  original=row.get('source');require(original in EXPECTED_IR and original not in seen,'Bytes ordinary source closure differs');seen.add(original)
  generated_name=GENERATED+original;function=functions.get(generated_name)
  require(function is not None and row['generated_source']==generated_name and row['symbol']==function['symbol'],'Bytes generated identity escaped genuine source closure')
  arity=1 if original.endswith('.empty') else 3 if original.endswith('.payload') else 2
  require(function['args']==['u64']*arity and set(function['effects'])<={'checked-access','virtual-read','virtual-write','user-syscall','privilege-transition','io-order'},'Bytes generated signature/authority differs')
  require(row['genuine_ir']==EXPECTED_IR[original],'Bytes genuine IR differs from ordinary allocation/push/access/borrowing/release')
  require(isinstance(row['checked_action'],str) and 0<len(row['checked_action'])<=262144,'Bytes checked action trace absent')
 require(seen==set(EXPECTED_IR) and {row['source'] for row in generated}=={row['generated_source'] for row in rows},'Uncatalogued generated bytes function')
 required={'Lemma.User.Runtime.ManagedBytes.natural','Lemma.User.Runtime.ManagedBytes.emptyWithCapacity',
           'Lemma.User.Runtime.ManagedBytes.push','Lemma.User.Runtime.ManagedBytes.get',
           'Lemma.User.Runtime.Arena.release','Lemma.User.Runtime.Arena.ensure'}
 require(required<=set(functions),'Bytes complete real allocation/access/reclamation closure missing')
 return c

def validate(ir,unit,*,optimized):
 c=contract(unit)
 if c is None:return None
 from audit_kernel import _ir_definition_body,parse_definitions_and_calls
 names={row['source']:row['symbol'] for row in unit['functions']}
 runtime='Lemma.User.Runtime.ManagedBytes.'
 allowed_calls={
  PREFIX+'empty':{runtime+'natural',runtime+'emptyWithCapacity'},
  PREFIX+'appendWord':{runtime+'push'},
  PREFIX+'payload':{GENERATED+PREFIX+'empty',GENERATED+PREFIX+'appendWord'},
  PREFIX+'readWord':{runtime+'natural',runtime+'get'},
  ENTRY:{GENERATED+PREFIX+'payload',GENERATED+PREFIX+'readWord','Lemma.User.Runtime.Arena.release'},
 }
 observed={}
 for row in c['functions']:
  original=row['source'];body=_ir_definition_body(ir,row['symbol'])
  require(body is not None,'Bytes generated LLVM missing')
  calls=parse_definitions_and_calls(body)[2]
  require(calls<={names[name] for name in allowed_calls[original]},'Bytes lowered calls escaped checked allocation/access/reclamation closure')
  if not optimized:
   require(calls=={names[name] for name in allowed_calls[original]},'Bytes generated allocation/access/release omitted')
   require(not re.search(r'\b(?:load|store|alloca|getelementptr|inttoptr|ptrtoint)\b',body),'Bytes generator bypassed checked runtime')
   if original.endswith('.appendWord'):
    require(len(re.findall(r'call \{ i64, i64 \} @'+re.escape(names[runtime+'push'])+r'\(',body))==8,'Ordinary word payload is not eight real consuming byte pushes')
   if original.endswith('.readWord'):
    require(len(re.findall(r'call \{ i64, i64 \} @'+re.escape(names[runtime+'get'])+r'\(',body))==8,'Ordinary word decode omitted actual checked byte observations')
  observed[original]=sorted(calls)
 return {'contract_version':'lemma-managed-bytes-v1','ordinary_sources':sorted(EXPECTED_IR),
  'maximum_payload':48,'slots':31,'generated_calls':observed,
  'scope':'Genuine ordinary ByteArray allocation/push/access/calls and real lifetime/OOM; full implementation authority audited separately'}
