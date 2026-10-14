"""Closed ordinary User7 math closure provenance; no target execution/oracle."""
from __future__ import annotations
import re
from core0_common import Core0Error
from closure_deployment import CONFIGURATIONS,SOFTWARE_DEPLOYMENT
FIELD='managed_closure'
PREFIX='Lemma.Mathematics.ManagedClosureSubmission.'
ENTRY=PREFIX+'compareFiveSix'
GENERATED=ENTRY+'.__lemma_managed_closure_v07.'
REVISION='5045d0056413266e57c625dcd7c365b10e377c52'
# Actual genuinely elaborated owner IR and adapter were independently reviewed
# before these immutable version preimages were installed.
EXPECTED_IR={'Lemma.Mathematics.ManagedClosureSubmission.apply': 'def Lemma.Mathematics.ManagedClosureSubmission.apply (x_1 : obj) '
                                                     '(x_2 : u64) : u64 :=\n'
                                                     '  let x_3 : tobj := box x_2;\n'
                                                     '  let x_4 : obj := app x_1 x_3;\n'
                                                     '  let x_5 : u64 := unbox x_4;\n'
                                                     '  dec x_4;\n'
                                                     '  ret x_5',
 'Lemma.Mathematics.ManagedClosureSubmission.compareFiveSix': 'def '
                                                              'Lemma.Mathematics.ManagedClosureSubmission.compareFiveSix '
                                                              '(x_1 : u64) (x_2 : u64) : u64 :=\n'
                                                              '  let x_3 : u64 := 1;\n'
                                                              '  let x_4 : u64 := UInt64.land x_1 x_3;\n'
                                                              '  let x_5 : tobj := box x_4;\n'
                                                              '  let x_6 : tobj := box x_1;\n'
                                                              '  let x_7 : tobj := box x_2;\n'
                                                              '  let x_8 : obj := pap '
                                                              'Lemma.Mathematics.ManagedClosureSubmission.select._boxed '
                                                              'x_5 x_6 x_7;\n'
                                                              '  let x_9 : u64 := UInt64.xor x_4 x_3;\n'
                                                              '  let x_10 : tobj := box x_9;\n'
                                                              '  let x_11 : tobj := box x_1;\n'
                                                              '  let x_12 : tobj := box x_2;\n'
                                                              '  let x_13 : obj := pap '
                                                              'Lemma.Mathematics.ManagedClosureSubmission.select._boxed '
                                                              'x_10 x_11 x_12;\n'
                                                              '  let x_14 : u64 := '
                                                              'Lemma.Mathematics.ManagedClosureSubmission.compareProducts '
                                                              'x_4 x_8 x_13;\n'
                                                              '  ret x_14',
 'Lemma.Mathematics.ManagedClosureSubmission.compareProducts': 'def '
                                                               'Lemma.Mathematics.ManagedClosureSubmission.compareProducts '
                                                               '(x_1 : u64) (x_2 : obj) (x_3 : obj) : u64 :=\n'
                                                               '  let x_4 : u64 := 0;\n'
                                                               '  let x_5 : u8 := UInt64.decEq x_1 x_4;\n'
                                                               '  case x_5 : u8 of\n'
                                                               '  Bool.false →\n'
                                                               '    let x_6 : u64 := 5;\n'
                                                               '    let x_7 : u64 := '
                                                               'Lemma.Mathematics.ManagedClosureSubmission.apply x_2 '
                                                               'x_6;\n'
                                                               '    let x_8 : u64 := 6;\n'
                                                               '    let x_9 : u64 := '
                                                               'Lemma.Mathematics.ManagedClosureSubmission.apply x_3 '
                                                               'x_8;\n'
                                                               '    let x_10 : u8 := UInt64.decEq x_7 x_9;\n'
                                                               '    case x_10 : u8 of\n'
                                                               '    Bool.false →\n'
                                                               '      let x_11 : u64 := 2;\n'
                                                               '      ret x_11\n'
                                                               '    Bool.true →\n'
                                                               '      let x_12 : u64 := 1;\n'
                                                               '      ret x_12\n'
                                                               '  Bool.true →\n'
                                                               '    let x_13 : u64 := 6;\n'
                                                               '    let x_14 : u64 := '
                                                               'Lemma.Mathematics.ManagedClosureSubmission.apply x_2 '
                                                               'x_13;\n'
                                                               '    let x_15 : u64 := 5;\n'
                                                               '    let x_16 : u64 := '
                                                               'Lemma.Mathematics.ManagedClosureSubmission.apply x_3 '
                                                               'x_15;\n'
                                                               '    let x_17 : u8 := UInt64.decEq x_14 x_16;\n'
                                                               '    case x_17 : u8 of\n'
                                                               '    Bool.false →\n'
                                                               '      let x_18 : u64 := 2;\n'
                                                               '      ret x_18\n'
                                                               '    Bool.true →\n'
                                                               '      let x_19 : u64 := 1;\n'
                                                               '      ret x_19',
 'Lemma.Mathematics.ManagedClosureSubmission.product': 'def Lemma.Mathematics.ManagedClosureSubmission.product (x_1 : '
                                                       'u64) (x_2 : u64) : u64 :=\n'
                                                       '  let x_3 : u64 := UInt64.mul x_1 x_2;\n'
                                                       '  ret x_3',
 'Lemma.Mathematics.ManagedClosureSubmission.select': 'def Lemma.Mathematics.ManagedClosureSubmission.select (x_1 : '
                                                      'u64) (x_2 : u64) (x_3 : u64) (x_4 : u64) : u64 :=\n'
                                                      '  let x_5 : u64 := 0;\n'
                                                      '  let x_6 : u8 := UInt64.decEq x_1 x_5;\n'
                                                      '  case x_6 : u8 of\n'
                                                      '  Bool.false →\n'
                                                      '    let x_7 : u64 := '
                                                      'Lemma.Mathematics.ManagedClosureSubmission.product x_3 x_4;\n'
                                                      '    ret x_7\n'
                                                      '  Bool.true →\n'
                                                      '    let x_8 : u64 := '
                                                      'Lemma.Mathematics.ManagedClosureSubmission.product x_2 x_4;\n'
                                                      '    ret x_8'}
SIGNATURES={'Lemma.Mathematics.ManagedClosureSubmission.apply': '(UInt64 → UInt64) → UInt64 → UInt64',
 'Lemma.Mathematics.ManagedClosureSubmission.compareFiveSix': 'UInt64 → UInt64 → UInt64',
 'Lemma.Mathematics.ManagedClosureSubmission.compareProducts': 'UInt64 → (UInt64 → UInt64) → (UInt64 → UInt64) → '
                                                               'UInt64',
 'Lemma.Mathematics.ManagedClosureSubmission.product': 'UInt64 → UInt64 → UInt64',
 'Lemma.Mathematics.ManagedClosureSubmission.select': 'UInt64 → UInt64 → UInt64 → UInt64 → UInt64'}
EXPECTED_ADAPTERS=[{'adapter': 'Lemma.Mathematics.ManagedClosureSubmission.select._boxed',
  'captures': 3,
  'genuine_ir': 'def Lemma.Mathematics.ManagedClosureSubmission.select._boxed (x_1 : obj) (x_2 : obj) (x_3 : obj) (x_4 '
                ': obj) : obj :=\n'
                '  let x_5 : u64 := unbox x_1;\n'
                '  dec x_1;\n'
                '  let x_6 : u64 := unbox x_2;\n'
                '  dec x_2;\n'
                '  let x_7 : u64 := unbox x_3;\n'
                '  dec x_3;\n'
                '  let x_8 : u64 := unbox x_4;\n'
                '  dec x_4;\n'
                '  let x_9 : u64 := Lemma.Mathematics.ManagedClosureSubmission.select x_5 x_6 x_7 x_8;\n'
                '  let x_10 : obj := box x_9;\n'
                '  ret x_10',
  'owner': 'Lemma.Mathematics.ManagedClosureSubmission.select',
  'owner_signature': 'UInt64 → UInt64 → UInt64 → UInt64 → UInt64'}]

def require(value,message):
 if not value:raise Core0Error(message)
def canonical(source):return re.sub(r'^_private\..*?\.[0-9]+\.','',source)
def allowed(unit):return unit.get('role')=='user' and unit.get('image_key')=='arithmetic' and unit.get('configuration') in CONFIGURATIONS

def contract(unit):
 generated=[r for r in unit.get('functions',[]) if '.__lemma_managed_closure_v07.' in r.get('source','')]
 if unit.get('contract_version')!='core0-user-v0.7':
  require(FIELD not in unit and not generated,'Historical profile acquired Closure authority');return None
 require(allowed(unit),'User7 closure escaped its exact isolated Arithmetic deployment')
 require(unit.get('software_deployment')==SOFTWARE_DEPLOYMENT,'Closure software deployment differs')
 require(not any(k in unit for k in ('managed_records','managed_sums','managed_bytes','managed_array','managed_string',
   'arithmetic_execution_identity','arithmetic_sums_execution_identity','arithmetic_bytes_execution_identity',
   'arithmetic_array_execution_identity','arithmetic_string_execution_identity')),'Closure deployment impersonates another implementation authority')
 c=unit.get(FIELD)
 require(isinstance(c,dict) and set(c)=={'contract_version','compiler_revision','allocator','entry','maximum_captures',
   'maximum_targets','slots','payload_bytes','cookie','initializer_policy','lifetime','functions','adapters','dispatcher'},'Closure catalog fields malformed')
 require(c['contract_version']=='lemma-managed-closure-v1' and c['compiler_revision']==REVISION and c['allocator']=='lemma-owned-arena-v1'
   and c['entry']==ENTRY and c['maximum_captures']==4 and c['maximum_targets']==8 and c['slots']==31
   and c['payload_bytes']==64 and c['cookie']==str(0x31534c4341524d4c),'Closure actual layout/source/resource bounds differ')
 require(c['initializer_policy']=='reject static/persistent boxes and closures' and
   c['lifetime']=='real owned scalar boxes; generational parent/environment; retain/release/reclamation','Closure ownership/static policy differs')
 require(c['adapters']==EXPECTED_ADAPTERS,'Genuine Closure adapter/owner/full64 capture IR differs')
 functions={r['source']:r for r in unit['functions']};seen=set()
 require(isinstance(c['functions'],list) and len(c['functions'])==5,'Closure ordinary source inventory empty/malformed')
 for row in c['functions']:
  require(isinstance(row,dict) and set(row)=={'source','source_signature','generated_source','symbol','genuine_ir','checked_action'},'Closure ordinary source fields differ')
  source=row['source'];require(source in EXPECTED_IR and source not in seen,'Closure ordinary source omitted/duplicated');seen.add(source)
  f=functions.get(GENERATED+source)
  require(f is not None and row['generated_source']==GENERATED+source and row['symbol']==f['symbol'] and
    row['source_signature']==SIGNATURES[source] and row['genuine_ir']==EXPECTED_IR[source],'Closure genuine source/signature/compiled correspondence differs')
  argc=4 if source.endswith('.select') else 3 if source.endswith('.compareProducts') else 2
  require(f['args']==['u64']*argc and set(f['effects'])<={'checked-access','virtual-read','virtual-write','user-syscall','privilege-transition','io-order'},'Closure handles escaped scalar checked ABI/effects')
  require(isinstance(row['checked_action'],str) and 0<len(row['checked_action'])<=262144,'Source-derived Closure checked Action absent')
 d=c['dispatcher'];f=functions.get(GENERATED+'__apply')
 require(isinstance(d,dict) and set(d)=={'source','symbol','checked_action'} and f is not None and
   d['source']==GENERATED+'__apply' and d['symbol']==f['symbol'] and f['args']==['u64']*2 and
   isinstance(d['checked_action'],str) and 0<len(d['checked_action'])<=262144,'Closure finite checked dispatcher correspondence absent')
 require({r['source'] for r in generated}=={GENERATED+s for s in EXPECTED_IR}|{GENERATED+'__apply'},'Uncatalogued generated Closure function')
 required={'Lemma.User.Runtime.ManagedClosure.'+n for n in ('create','box','unbox','code','arity','capture','finish','release','abort')}|{'Lemma.User.Runtime.Arena.allocate'}
 require(required<={canonical(n) for n in functions},'Real Closure full64 allocation/environment/dispatch/reclamation omitted')
 return c

def validate(ir,unit,*,optimized):
 c=contract(unit)
 if c is None:return None
 from audit_kernel import _ir_definition_body,parse_definitions_and_calls
 names={r['source']:r['symbol'] for r in unit['functions']};runtime='Lemma.User.Runtime.ManagedClosure.';arena='Lemma.User.Runtime.Arena.'
 calls={PREFIX+'product':set(),PREFIX+'select':{GENERATED+PREFIX+'product'},
   PREFIX+'apply':{runtime+'box',runtime+'unbox',runtime+'release',arena+'release',GENERATED+'__apply'},
   PREFIX+'compareProducts':{GENERATED+PREFIX+'apply',runtime+'release'},
   ENTRY:{runtime+'box',runtime+'create',runtime+'release',arena+'release',GENERATED+PREFIX+'compareProducts'},
   '__apply':{runtime+n for n in ('code','arity','capture','unbox','finish','abort')}|{GENERATED+PREFIX+'select'}}
 observed={}
 for source,allowed_calls in calls.items():
  generated=GENERATED+source;body=_ir_definition_body(ir,names[generated]);require(body is not None,'Closure generated LLVM body absent')
  actual=parse_definitions_and_calls(body)[2];expected={names[n] for n in allowed_calls}
  require(actual<=expected,'Generated Closure escaped its checked source/runtime call closure')
  if not optimized:
   require(actual==expected,'Closure real box/environment/application/reclamation call omitted')
   require(not re.search(r'\b(?:load|store|alloca|getelementptr|inttoptr|ptrtoint)\b',body),'Closure generator bypasses checked storage/runtime')
  observed[source]=sorted(actual)
 return {'contract_version':'lemma-managed-closure-v1','ordinary_sources':sorted(EXPECTED_IR),
   'genuine_adapters':EXPECTED_ADAPTERS,'maximum_captures':4,'actual_math_captures':3,'slots':31,
   'ordinary_peak_objects':9,'generated_calls':observed,
   'scope':'Actual ordinary owned full64 scalar closures/finite checked CFG dispatcher; no general runtime/proof-kernel completion'}
