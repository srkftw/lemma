"""Independent closed Array production admission; no target execution oracle."""
import re
from core0_common import Core0Error
FIELD='managed_array'
CONFIGURATIONS=frozenset(('lemmasim-silicon-array-bulk-notebook','lemmasim-silicon-array-bulk-initialize','lemmasim-silicon-array-arithmetic-oom-development'))
ENTRY='Lemma.Mathematics.ManagedArraySubmission.compareFiveSix'
PREFIX='Lemma.Mathematics.ManagedArraySubmission.'
GENERATED=ENTRY+'.__lemma_managed_array_v05.'
SOFTWARE_DEPLOYMENT={'contract_version':'lemma-managed-array-bulk-deployment-v1',
 'silicon_profile':'lemma-silicon-dev/0.3.0',
 'user_profiles':{'store':'core0-user-v0.1','notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.5'}}
# Installed only after independent inspection of the real immutable compiler
# output. Empty identities deliberately reject an unqualified production build.
EXPECTED_IR={'Lemma.Mathematics.ManagedArraySubmission.read': 'def Lemma.Mathematics.ManagedArraySubmission.read (x_1 : @& obj) (x_2 : u64) : u64 :=\n  let x_3 : tobj := UInt64.toNat x_2;\n  let x_4 : tobj := Lemma.Mathematics.ManagedArraySubmission.read._boxed_const_1;\n  let x_5 : tobj := Array.get!InternalBorrowed ◾ x_4 x_1 x_3;\n  dec x_3;\n  let x_6 : u64 := unbox x_5;\n  ret x_6', 'Lemma.Mathematics.ManagedArraySubmission.changed': 'def Lemma.Mathematics.ManagedArraySubmission.changed (x_1 : obj) (x_2 : u64) (x_3 : u64) : obj :=\n  let x_4 : tobj := UInt64.toNat x_2;\n  let x_5 : tobj := box x_3;\n  let x_6 : obj := Array.set! ◾ x_1 x_4 x_5;\n  dec x_4;\n  ret x_6', 'Lemma.Mathematics.ManagedArraySubmission.payload': 'def Lemma.Mathematics.ManagedArraySubmission.payload (x_1 : u64) (x_2 : u64) (x_3 : u64) : obj :=\n  let x_4 : tobj := UInt64.toNat x_1;\n  let x_5 : obj := Array.emptyWithCapacity ◾ x_4;\n  dec x_4;\n  let x_6 : tobj := box x_2;\n  let x_7 : obj := Array.push ◾ x_5 x_6;\n  let x_8 : tobj := box x_3;\n  let x_9 : obj := Array.push ◾ x_7 x_8;\n  ret x_9', 'Lemma.Mathematics.ManagedArraySubmission.compareFiveSix': 'def Lemma.Mathematics.ManagedArraySubmission.compareFiveSix (x_1 : u64) (x_2 : u64) : u64 :=\n  let x_3 : u64 := 2;\n  let x_4 : obj := Lemma.Mathematics.ManagedArraySubmission.payload x_3 x_1 x_2;\n  let x_5 : u64 := 0;\n  inc x_4;\n  let x_6 : obj := Lemma.Mathematics.ManagedArraySubmission.changed x_4 x_5 x_1;\n  let x_7 : u64 := Lemma.Mathematics.ManagedArraySubmission.read x_4 x_5;\n  dec x_4;\n  let x_8 : u64 := 1;\n  let x_9 : u64 := Lemma.Mathematics.ManagedArraySubmission.read x_6 x_8;\n  dec x_6;\n  let x_10 : u64 := 6;\n  let x_11 : u64 := UInt64.mul x_7 x_10;\n  let x_12 : u64 := 5;\n  let x_13 : u64 := UInt64.mul x_9 x_12;\n  let x_14 : u8 := UInt64.decEq x_11 x_13;\n  case x_14 : u8 of\n  Bool.false →\n    ret x_3\n  Bool.true →\n    ret x_8'}
EXPECTED_DEFAULT_IR='def Lemma.Mathematics.ManagedArraySubmission.read._boxed_const_1 : tobj :=\n  let x_1 : u64 := 0;\n  let x_2 : tobj := box x_1;\n  ret x_2'
SIGNATURES={PREFIX+'payload':'UInt64 → UInt64 → UInt64 → Array UInt64',
 PREFIX+'read':'Array UInt64 → UInt64 → UInt64',
 PREFIX+'changed':'Array UInt64 → UInt64 → UInt64 → Array UInt64',
 ENTRY:'UInt64 → UInt64 → UInt64'}

def require(value,message):
 if not value:raise Core0Error(message)
def software_deployment_for(configuration):
 require(configuration in CONFIGURATIONS,'Unknown exact Array deployment')
 return SOFTWARE_DEPLOYMENT
def allowed(unit):
 return unit.get('role')=='user' and unit.get('image_key')=='arithmetic' and unit.get('configuration') in CONFIGURATIONS

def contract(unit):
 generated=[row for row in unit.get('functions',[]) if '.__lemma_managed_array_v05.' in row.get('source','')]
 if unit.get('contract_version')!='core0-user-v0.5':
  require(FIELD not in unit and not generated,'Historical profile acquired Array authority');return None
 require(allowed(unit),'Array User5 escaped its exact isolated Arithmetic deployment')
 require(unit.get('software_deployment')==SOFTWARE_DEPLOYMENT,'Array software deployment differs')
 require(not any(name in unit for name in ('managed_records','managed_sums','managed_bytes','arithmetic_execution_identity','arithmetic_sums_execution_identity','arithmetic_bytes_execution_identity')),'Array deployment impersonates older implementation authority')
 c=unit.get(FIELD)
 require(isinstance(c,dict) and set(c)=={'contract_version','compiler_revision','allocator','entry','maximum_elements','element_bits','slots','array_payload_bytes','array_cookie','element_layout','get_out_of_bounds','set_out_of_bounds','functions','default_initializers'},'Array catalog malformed')
 require(c['contract_version']=='lemma-managed-array-v1' and c['compiler_revision']=='5045d0056413266e57c625dcd7c365b10e377c52' and c['allocator']=='lemma-owned-arena-v1' and c['entry']==ENTRY and c['maximum_elements']==6 and c['element_bits']==64 and c['slots']==31 and c['array_payload_bytes']==64 and c['array_cookie']==str(0x31595252414d4c),'Array exact source/runtime/layout/bounds differ')
 require(c['element_layout']=='owned generational boxTag1/length8/fullUInt64' and c['get_out_of_bounds']=='controlled-panic236; no mathematical default' and c['set_out_of_bounds']=='controlled-panic236; consume parent/element, preserve retained aliases','Array lifetime/panic semantics differ')
 rows=c['functions'];require(isinstance(rows,list) and len(rows)==4 and set(EXPECTED_IR)==set(SIGNATURES),'Array ordinary closure absent/unqualified')
 functions={row['source']:row for row in unit['functions']};seen=set()
 for row in rows:
  require(isinstance(row,dict) and set(row)=={'source','source_signature','generated_source','symbol','genuine_ir','checked_action'},'Array source trace fields differ')
  source=row['source'];require(source in SIGNATURES and source not in seen,'Array source inventory differs');seen.add(source)
  function=functions.get(GENERATED+source)
  require(function is not None and row['generated_source']==GENERATED+source and row['symbol']==function['symbol'] and row['source_signature']==SIGNATURES[source],'Array generated identity/signature differs')
  require(function['args']==['u64']*(3 if source.endswith(('.payload','.changed')) else 2) and set(function['effects'])<={'checked-access','virtual-read','virtual-write','user-syscall','privilege-transition','io-order'},'Array scalar ABI/effects escaped checked handles')
  require(row['genuine_ir']==EXPECTED_IR[source],'Array genuine allocation/box/borrow/COW/release IR differs')
  require(isinstance(row['checked_action'],str) and 0<len(row['checked_action'])<=262144,'Array source-derived checked action missing')
 require({row['source'] for row in generated}=={row['generated_source'] for row in rows},'Uncatalogued generated Array function')
 defaults=c['default_initializers'];owner=PREFIX+'read';name=owner+'._boxed_const_1'
 require(defaults==[{'source':name,'owner_source':owner,'owner_source_signature':SIGNATURES[owner],'genuine_ir':EXPECTED_DEFAULT_IR,'value_bits':64,'literal_value':0,'use_policy':'unobservable borrowed-get default; controlled-panic236'}] and EXPECTED_DEFAULT_IR is not None,'Array genuine owner-bound derived default differs')
 required={'Lemma.User.Runtime.ManagedArray.emptyWithCapacity','Lemma.User.Runtime.ManagedArray.box','Lemma.User.Runtime.ManagedArray.push','Lemma.User.Runtime.ManagedArray.getBorrowed','Lemma.User.Runtime.ManagedArray.unbox','Lemma.User.Runtime.ManagedArray.set','Lemma.User.Runtime.ManagedArray.retain','Lemma.User.Runtime.ManagedArray.release','Lemma.User.Runtime.Arena.allocate'}
 require(required<={re.sub(r'^_private\..*?\.[0-9]+\.','',name) for name in functions},'Array real full64 graph allocation/access/reclamation closure missing')
 return c

def validate(ir,unit,*,optimized):
 c=contract(unit)
 if c is None:return None
 from audit_kernel import _ir_definition_body,parse_definitions_and_calls
 names={row['source']:row['symbol'] for row in unit['functions']};runtime='Lemma.User.Runtime.ManagedArray.'
 allowed_calls={PREFIX+'payload':{runtime+'natural',runtime+'emptyWithCapacity',runtime+'box',runtime+'push',runtime+'release'},
 PREFIX+'read':{runtime+'natural',runtime+'getBorrowed',runtime+'unbox'},
 PREFIX+'changed':{runtime+'natural',runtime+'box',runtime+'set',runtime+'release'},
 ENTRY:{GENERATED+PREFIX+'payload',GENERATED+PREFIX+'changed',GENERATED+PREFIX+'read',runtime+'retain',runtime+'release'}}
 observed={}
 for row in c['functions']:
  source=row['source'];body=_ir_definition_body(ir,row['symbol']);require(body is not None,'Array generated LLVM missing')
  calls=parse_definitions_and_calls(body)[2];expected={names[name] for name in allowed_calls[source]}
  require(calls<=expected,'Array generated calls escaped checked graph/runtime')
  if not optimized:
   require(calls==expected,'Array real graph/box/borrow/retain/release call missing')
   require(not re.search(r'\b(?:load|store|alloca|getelementptr|inttoptr|ptrtoint)\b',body),'Array generator bypasses checked runtime')
   if source==ENTRY:
    require(len(re.findall(r'call \{ i64, i64 \} @'+re.escape(names[runtime+'release'])+r'\(',body))==8,'Array two normal root releases and six error-cleanup releases differ')
  observed[source]=sorted(calls)
 return {'contract_version':'lemma-managed-array-v1','ordinary_sources':sorted(SIGNATURES),'element_bits':64,'maximum_elements':6,'slots':31,'generated_calls':observed,'scope':'Genuine ordinary Array UInt64/COW/full64 boxes with actual graph RC/OOM; no general runtime or proof-kernel completion'}
