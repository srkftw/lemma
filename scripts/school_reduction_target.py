"""Narrow source and checked-LLVM gates for the closed School24 local tool.

These observers supplement genuine complete body pins and actual Action/guest
qualification. They do not compute a guest result or admit arbitrary services.
"""
from pathlib import Path
import re
from core0_common import Core0Error

ROOT=Path(__file__).resolve().parents[1]
COMPONENTS={
 'notebook':'Lemma/Applications/Notebook.lean',
 'local':'Lemma/Courses/LocalReduction.lean',
 'events':'Lemma/Documents/LocalToolEvents.lean',
 'math':'Lemma/Documents/Mathematics.lean',
 'protocol':'Lemma/Services/Arithmetic/ProtocolV9.lean',
 'client':'Lemma/Services/Arithmetic/ClientV9.lean',
 'server':'Lemma/Services/Arithmetic/ServerV9.lean',
 'reduction':'Lemma/Services/Arithmetic/ReductionV1.lean'}

def require(value,message):
 if not value:raise Core0Error('School local reduction: '+message)

def compact(value):return ' '.join(value.split())

def definition(source,name):
 matches=list(re.finditer(r'^(?:private )?def '+re.escape(name)+r'(?=\s|\()',source,re.M))
 require(len(matches)==1,'definition absent/duplicate: '+name)
 start=matches[0].start();tail=re.search(r'^(?:(?:private )?def |end )',source[matches[0].end():],re.M)
 end=matches[0].end()+tail.start() if tail else len(source)
 return compact(source[start:end])

def notebook_source(source):
 from multimodal_target import _lean_without_comments
 source=_lean_without_comments(source)
 require(definition(source,'configureSchoolMode')==compact('''private def configureSchoolMode (school : UInt64) : Action :=
 if school ≤ 2 then
 .bind (Memory.write64 schoolActivityFlag (if school = 2 then 1 else school)) fun s _ => if statusFailed s = true then .done s 0 else
 Memory.write64 reductionEnabled (if school = 2 then 1 else 0) else .done 234 0'''),
 'startup must preserve School23 and enable the tool only in mode2')
 for name,body in (
  ('mainMultimodalSchool','def mainMultimodalSchool (bootArgument : UInt64) : Action := mainMultimodalConfigured bootArgument 1'),
  ('mainMultimodalSchool24','def mainMultimodalSchool24 (bootArgument : UInt64) : Action := mainMultimodalConfigured bootArgument 2'),
  ('state','def state : UInt64 := 0x20800'),
  ('outgoing','def outgoing : UInt64 := 0x20b00'),
  ('mathematicsIO','def mathematicsIO : UInt64 := 0x32b000'),
  ('reductionEnabled','private def reductionEnabled : UInt64 := state+728'),
  ('reductionMeta','private def reductionMeta : UInt64 := mathematicsIO+512'),
  ('reductionEvent','private def reductionEvent : UInt64 := mathematicsIO+640'),
  ('reductionGet','private def reductionGet (offset : UInt64) : Action := Memory.read64 (reductionMeta+offset)'),
  ('reductionPut','private def reductionPut (offset value : UInt64) : Action := Memory.write64 (reductionMeta+offset) value')):
  require(definition(source,name)==compact(body),'exact root/layout differs: '+name)
 require('(Memory.write64 (state+728) 0)' in definition(source,'clearStep'),'legacy startup did not zero the owned BSS flag')
 require('(configureSchoolMode school)' in definition(source,'mainMultimodalConfigured'),'startup omitted exact mode initialization')
 begin=definition(source,'beginLocalReduction');pump=definition(source,'pumpLocalReduction')
 prefix=compact('''.bind (Memory.read64 reductionEnabled) fun s enabled => if statusFailed s = true then .done s 0 else if enabled = 1 then''')
 require(prefix in begin and prefix in pump,'tool start/pump lost the opt-in mode gate')
 require('if allocated = 3 then if course = 1 then if phase ||| pending ||| rawCount ||| rawPending ||| stroke = 0 then' in begin,
         'tool start lost allocation/course/idle/current-input ownership')
 require('.bind (get 176) fun s counter' in begin and 'if counter < 0x7ffffffffffffffe then' in begin and
         'nextRequest' not in begin and 'else .done 235 0' in begin,
         'tool request lost its unchanged-on-exhaustion counter gate')
 required=['Lemma.Courses.LocalReduction.request packageWorkspace mathematics mathematicsIO reductionEvent reductionMeta ns page (counter+1)',
  'fun s request => if statusFailed s = true then .done s 0 else',
  'if request < 0x7ffffffffffffffe then',
  'Lemma.Courses.LocalReduction.stagePrepared packageWorkspace mathematics packageDocumentStage mathematicsSave reductionEvent',
  'reductionPut 8 frontier','put 176 request','put 552 request','put 536 16','publishPackageWorkspace']
 require(all(fragment in begin for fragment in required) and [begin.index(fragment) for fragment in required]==sorted(begin.index(fragment) for fragment in required),
         'prepared work/request/floor/publication order differs')
 require('ClientV9.beginCall' not in begin,'tool call precedes real prepared Store commit')
 require('if phase = 16 then' in pump and 'if pending ||| status = 0 then' in pump and 'if floor < frontier then' in pump,
         'tool call lost actual successful Store frontier barrier')
 current='Lemma.Courses.LocalReduction.current packageWorkspace mathematics mathematicsIO reductionEvent ns page'
 call='Lemma.Services.Arithmetic.ClientV9.beginCall endpoint mathematicsIO request'
 require(current in pump and call in pump and pump.index('if floor < frontier then')<pump.index(current)<pump.index(call),
         'tool call lost fresh current-work/source binding')
 require('ClientV9.pollCall transaction (mathematicsIO+256) mathematicsIO request' in pump and
         'put 536 (if result = 0 then 18 else 19)' in pump and 'if result = IPCABI.wouldBlock then .done 0 0 else' in pump,
         'tool completion lost exact pending transaction or admitted status')
 require('if pending ||| rawCount ||| rawPending ||| stroke = 0 then' in pump and
         'if phase = 18 then Lemma.Courses.LocalReduction.stageApplied' in pump and
         'else Lemma.Courses.LocalReduction.stageTerminal' in pump,
         'tool reply staging lost idle ownership or success/error split')
 cancel=definition(source,'cancelArithmetic')
 require('if (if phase = 1 then true else phase = 17) = true then' in cancel and
         'IPC.cancel transaction' in cancel and 'if phase = 17 then Lemma.Services.Arithmetic.ClientV9.pollCall' in cancel and
         'put 536 0' in cancel and 'stageApplied' not in cancel,
         'cancellation must consume its owned terminal reply without applying an edit')
 require('if operation = 10 then beginLocalReduction' in definition(source,'multimodalControl'),
         'REDUCE control bypasses the guarded guest start')
 require('if 16 ≤ phase then pumpLocalReduction else' in definition(source,'pumpPackageArithmetic'),
         'local phases escaped their separately guarded pump')
 stroke=definition(source,'beginStroke')
 require('if (if phase = 1 then true else if 16 ≤ phase then if phase ≤ 19 then true else false else false) = true then cancelArithmetic else .done 0 0' in stroke and
         stroke.index('cancelArithmetic')<stroke.index('preflightChunk'),
         'ink must settle the owned tool transaction before its own Store work')
 render=definition(source,'renderReductionControl')
 require('if enabled = 1 then if 1352 ≤ width then' in render and
         '.boundedFoldU64 1080 reductionBarStep 1080' in render and
         'dirty 1280 132 1352 147' in render,'tool presentation lost mode/geometry/fixed raster bounds')
 return {'mode':2,'legacy_School_mode':1,'enabled_offset':728,'IO_windows':[
  ['request',0,144],['reply_with_IPC_header',256,240],['metadata',512,16],['event',640,128]],
  'phases':[16,17,18,19],'control':10,'raster_pixels':1080,'scope':'source admission only; complete actual LLVM pins and execution required'}

def sources(values):
 from multimodal_target import _lean_without_comments
 require(set(values)==set(COMPONENTS),'complete source inventory differs')
 src={key:_lean_without_comments(value) for key,value in values.items()}
 result=notebook_source(src['notebook'])
 p=src['protocol'];client=src['client'];local=src['local'];math=src['math']
 events=src['events']
 require(definition(events,'freshRequestID')==compact('''def freshRequestID (buffer candidate scratch : UInt64) : Action :=
  if candidate = 0 then .done 235 0 else if 0x7ffffffffffffffe < candidate then .done 235 0 else
  .bind (read buffer 192) fun s count => if s = 0 then
  .bind (read buffer 208) fun s format => if s = 0 then
  if 64 < count then .done 235 0 else
  if (if format = 1 then true else if format = 2 then true else format = 3) = true then
  .bind (write scratch 0 0) fun s _ => if s = 0 then
  .boundedFoldU64 64 freshRequestStep 64 (candidate-1) buffer count scratch format fun s greatest => if s = 0 then
  if greatest < 0x7ffffffffffffffe then .done 0 (greatest+1) else .done 235 0
  else .done s 0 else .done s 0 else .done 234 0 else .done s 0 else .done s 0'''),
  'fresh tool identity lost its full-domain bounded durable-history maximum/exhaustion guard')
 require(definition(events,'freshRequestStep')==compact('''private def freshRequestStep (i _ : UInt32) (acc buffer count scratch format : UInt64) : Action :=
  if count ≤ i.toUInt64 then .done 0 acc else
  .bind (read scratch 0) fun s skip => if s = 0 then
  if 0 < skip then .bind (write scratch 0 (skip-1)) fun s _ => .done s acc else
  let entry := buffer+832+i.toUInt64*16
  .bind (read entry 8) fun s desc => if s = 0 then
  if desc &&& 255 = 7 then
    if format = 1 then .done 234 0 else if count < i.toUInt64+4 then .done 234 0 else
    .bind (write scratch 0 3) fun s _ => .done s acc
  else if desc &&& 255 = 8 then
    if format = 3 then if count < i.toUInt64+8 then .done 234 0 else
    .bind (read entry 24) fun s request => if s = 0 then
    if request = 0 then .done 234 0 else if 0x7ffffffffffffffe < request then .done 234 0 else
    .bind (write scratch 0 7) fun s _ => if s = 0 then
    .done 0 (if acc < request then request else acc) else .done s 0
    else .done s 0 else .done 234 0
  else .done 0 acc else .done s 0 else .done s 0'''),
  'fresh tool identity lost exact kind7/8 payload skipping or full request bits')
 request=definition(local,'request')
 require('.bind (Lemma.Documents.LocalToolEvents.freshRequestID document requestID (outgoing+128)) fun s freshID => if s = 0 then' in request and
         request.count('n d freshID 0 0')==2 and
         '.bind (Lemma.Documents.LocalToolEvents.prepare event outgoing crc) fun s _ => .done s freshID' in request,
         'request/event encoding or return lost the selected fresh durable identity')
 for name,value in [('requestBytes','144'),('replyBytes','176'),('serviceIdentity','0x0001000052444331')]:
  require(definition(p,name)==f'def {name} : UInt64 := {value}','protocol identity/extent differs: '+name)
 require(definition(p,'validContext')==compact('''def validContext (source edition object node revision ns page request session policy : UInt64) : Bool :=
  if ns = 0 then false else if 2 < ns then false else
  if page = 0 then false else if 64 < page then false else
  if object = (0x504b000000000000 ||| page) then
  if revision = 0 then false else if 0x7ffffffffffffffe < revision then false else
  if request = 0 then false else if 0x7ffffffffffffffe < request then false else
  if 0x7ffffffffffffffe < session then false else if 0x7ffffffffffffffe < policy then false else
  if (if session = 0 then (if policy = 0 then true else false) else if policy = 0 then false else true) = true then
  if source = 0 then if edition ||| node = 0 then true else false else
  if source = 60000 then false else if source = 60001 then false else if 65535 < source then false else if edition = 0 then false else if 0xffffffff < edition then false else
  if node = 0 then false else if 16 < node then false else true
  else false else false'''), 'service context lost its closed namespace/page/object/source/session ranges')
 evaluate=definition(p,'evaluate')
 require('if tag = magic then if v = version then if op = 1 then if reserved0 ||| reserved1 = 0 then' in evaluate and
         'if validContext source edition object node revision ns page request session policy = true then ReductionV1.calculate n d budget' in evaluate,
         'service calculation lost version/reserved/current-context validation')
 require('if submission = request then ProtocolV9.evaluate payload else .done 234 0' in definition(src['server'],'processCopied'),
         'service lost kernel request/echo binding')
 validate=definition(client,'validate')
 require('if actual = request then' in validate and '.boundedFoldU64 18 echoStep 18' in validate and
         'if identity = ProtocolV9.serviceIdentity then' in validate and
         'if bytes = IPCABI.headerBytes+ProtocolV9.replyBytes then' in validate and
         'if kind = IPCABI.replyKind then' in validate and
         'if (if sender = 0 then false else true) = true then' in validate and
         'if authority = 0 then' in validate,
         'client lost exact header/18-word echo/service admission')
 require('if actual = expected then .done 0 acc else .done IPCABI.invalidPacket 0' in definition(client,'echoStep'),
         'reply echo comparison differs')
 require('IPC.callBegin endpoint outgoing ProtocolV9.requestBytes request Protocol.deadlineTicks' in definition(client,'beginCall') and
         'Syscall.call 67 transaction incoming IPCABI.maximumPacket 0 0' in definition(client,'pollCall'),
         'tool client lost actual per-task asynchronous IPC ownership')
 current=definition(local,'current')
 for fragment in ['same document 24 request 64','same document 32 request 72','same document 40 request 56',
                  'same document 56 request 80','same document 64 request 88',
                  'same (workspace+PackageWorkspace.selection) 16 request 24',
                  'same (workspace+PackageWorkspace.selection) 24 request 32',
                  'same (workspace+PackageWorkspace.selection) 40 request 48',
                  'same (workspace+PackageWorkspace.selection) 32 event 64']:
  require(fragment in current,'current work/source field omitted: '+fragment)
 staged=definition(local,'stageApplied')
 require('(current workspace document request event ns page)' in staged and
         'Mathematics.applyLocalTool stagedDocument event' in staged and
         staged.index('(current workspace document request event ns page)')<staged.index('Mathematics.applyLocalTool'),
         'reply edit bypasses fresh work/source admission')
 apply=definition(math,'applyLocalTool')
 require('if expected = revision then if goal = 1 then if n = oldN then if d = oldD then' in apply and
         apply.index('(revise buffer)')<apply.index('(put buffer 56 nextN)') and
         'LocalToolEvents.append buffer event' in apply and 'complete' not in apply,
         'tool application lost revision/operand binding or acquired checker completion')
 calculation=definition(src['reduction'],'calculate')
 require(definition(src['reduction'],'requiredBudget')=='def requiredBudget : UInt64 := 34' and
         definition(src['reduction'],'maximumMagnitude')=='def maximumMagnitude : UInt64 := 1000000' and
         '.boundedFoldU64 32 gcdStep 32' in calculation and 'if budget < requiredBudget then .done 235 0 else' in calculation,
         'numeric tool lost fixed iteration/resource bound')
 return result

def source_root(root=ROOT):
 return sources({key:(Path(root)/name).read_text() for key,name in COMPONENTS.items()})

def llvm_semantics(ir,rows,role):
 """Bind actual emitted values/CFG edges, beyond declaration-name presence."""
 from audit_kernel import (_ir_definition_body,_local_call_arguments,_local_checked_result,
  _structured_ir_blocks,_structured_successors,
  validate_boolean_gate,validate_checked_call_gate,validate_failed_call_gate,validate_fixed_fold)
 require(role in {'arithmetic','notebook','client','local'},'unknown emitted component role')
 var=r'%[A-Za-z0-9_.$-]+'
 reverse={row['symbol']:name for name,row in rows.items()}
 def symbol(name):
  require(name in rows,'missing genuine LLVM owner: '+name)
  return rows[name]['symbol']
 def body(name):return _ir_definition_body(ir,symbol(name))
 def calls(owner,target):return _local_call_arguments(body(owner),symbol(target))
 def one(owner,target):
  found=calls(owner,target);require(len(found)==1,'actual call count differs: '+owner+' -> '+target)
  return found[0]
 def value(owner,target,arguments):return _local_checked_result(body(owner),symbol(target),arguments)[1]
 def linear(owner,operand,seen=None):
  """Only finite add/constant-multiply/zero-extension address expressions."""
  if re.fullmatch(r'-?\d+',operand):return ({},int(operand))
  if re.fullmatch(r'%arg\d+',operand):return ({operand:1},0)
  seen=set() if seen is None else set(seen);token=(owner,operand)
  require(token not in seen,'recursive LLVM address expression');seen.add(token)
  text=body(owner)
  constant=re.findall(re.escape(operand)+r' = call i64 @([A-Za-z0-9_.$]+)\(\)$',text,re.M)
  if len(constant)==1:
   name=reverse.get(constant[0]);require(name is not None and rows[name]['args']==[] and rows[name]['effects']==[],
    'address constant acquired arguments/effects')
   scalar=body(name)
   returned=re.fullmatch(r'\s*entry:\n(?:[^:\n]*\n)*?\s*ret i64 ('+var+r'|-?\d+)\s*',scalar)
   require(returned is not None,'address scalar is not a single pure finite expression: '+name)
   fields,fixed=linear(name,returned[1],seen)
   require(not fields,'zero-argument address scalar acquired external values')
   return ({},fixed)
  add=re.findall(re.escape(operand)+r' = add i64 ([^,\n]+), ([^\n]+)$',text,re.M)
  if len(add)==1:
   left,a=linear(owner,add[0][0],seen);right,b=linear(owner,add[0][1],seen);result=dict(left)
   for key,v in right.items():result[key]=result.get(key,0)+v
   return ({key:v for key,v in result.items() if v},a+b)
  mul=re.findall(re.escape(operand)+r' = mul i64 ([^,\n]+), (\d+)$',text,re.M)
  if len(mul)==1:
   fields,constant=linear(owner,mul[0][0],seen);scale=int(mul[0][1])
   return ({key:v*scale for key,v in fields.items()},constant*scale)
  cast=re.findall(re.escape(operand)+r' = zext i32 ('+var+r') to i64$',text,re.M)
  if len(cast)==1:return linear(owner,cast[0],seen)
  require(False,'unaccounted LLVM address/value expression: '+owner+'/'+operand)
 def equal_address(owner,argument,fields,constant):
  require(argument.startswith('i64 ') and linear(owner,argument[4:])==(fields,constant),'actual LLVM address/value retargeted: '+owner)
 def gate(owner,predicate,left,right,target):
  candidates=re.findall('('+var+r') = icmp '+predicate+' i64 '+re.escape(left)+', '+re.escape(right)+r'$',body(owner),re.M)
  require(len(candidates)==1,'exact emitted work/value predicate differs: '+owner)
  return validate_boolean_gate(body(owner),candidates[0],symbol(target))
 def constant_gate(owner,left,expected,target):
  comparisons=re.findall('('+var+r') = icmp eq i64 '+re.escape(left)+r', ([^\n]+)$',body(owner),re.M)
  candidates=[]
  for comparison,operand in comparisons:
   try:actual=linear(owner,operand)
   except Core0Error:continue
   if actual==({},expected):candidates.append(comparison)
  require(len(candidates)==1,'exact emitted packet extent predicate differs: '+owner)
  return validate_boolean_gate(body(owner),candidates[0],symbol(target))
 memory='Lemma.User.Memory.';n='Lemma.Applications.Notebook.';client='Lemma.Services.Arithmetic.ClientV9.'
 local='Lemma.Courses.LocalReduction.';server='Lemma.Services.Arithmetic.ServerV9.';protocol='Lemma.Services.Arithmetic.ProtocolV9.'
 checks=[]
 def client_echo():
  checks.append(validate_fixed_fold(body(client+'validate'),symbol(client+'echoStep'),18))
  echo=client+'echoStep';reads=calls(echo,memory+'read64');require(len(reads)==2,'echo must read both actual copied words')
  equal_address(echo,reads[0],{'%arg3':1,'%arg0':8},64)
  equal_address(echo,reads[1],{'%arg4':1,'%arg0':8},0)
  actual=value(echo,memory+'read64',reads[0]);expected=value(echo,memory+'read64',reads[1])
  comparisons=re.findall('('+var+r') = icmp eq i64 '+re.escape(actual)+', '+re.escape(expected)+r'$',body(echo),re.M)
  require(len(comparisons)==1,'emitted echo compares the wrong copied words')
  echo_comparison=comparisons[0]
  blocks=_structured_ir_blocks(body(echo));successors=_structured_successors(blocks)
  branches=[label for label,lines in blocks.items() if re.fullmatch(
   r'br i1 '+re.escape(comparisons[0])+r', label %[A-Za-z0-9_.$-]+, label %[A-Za-z0-9_.$-]+',lines[-1])]
  require(len(branches)==1,'emitted echo comparison does not control admission')
  success,failure=successors[branches[0]]
  require(len(successors[success])==1 and successors[success]==successors[failure] and
   blocks[success]==['br label %'+successors[success][0]],'echo success/failure lost exact result merge')
  merge=successors[success][0];invalid='Lemma.User.IPCABI.invalidPacket'
  failures=blocks[failure]
  error=re.fullmatch('('+var+r') = call zeroext i8 @'+re.escape(symbol(invalid))+r'\(\)',failures[0]) if len(failures)==2 else None
  require(error is not None and failures[1]=='br label %'+merge and
   re.fullmatch(r'\s*entry:\s*ret i8 101\s*',body(invalid)) is not None,
   'echo mismatch must return the actual invalidPacket status')
  status=r'('+var+r') = phi i8 \[ 0, %'+re.escape(success)+r' \], \[ '+re.escape(error[1])+', %'+re.escape(failure)+r' \]'
  result=r'('+var+r') = phi i64 \[ %arg2, %'+re.escape(success)+r' \], \[ 0, %'+re.escape(failure)+r' \]'
  status_phi=[re.fullmatch(status,line) for line in blocks[merge] if re.fullmatch(status,line)]
  value_phi=[re.fullmatch(result,line) for line in blocks[merge] if re.fullmatch(result,line)]
  require(len(status_phi)==len(value_phi)==1,
   'echo must preserve its accumulator only after both copied words match')
  current_status,current_value=status_phi[0][1],value_phi[0][1]
  for arguments in reversed(reads):
   called=_local_checked_result(body(echo),symbol(memory+'read64'),arguments)[0]
   words=re.findall('('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(called)+r', 0$',body(echo),re.M)
   narrowed=re.findall('('+var+r') = trunc i64 '+re.escape(words[0] if len(words)==1 else '<missing>')+r' to i8$',body(echo),re.M)
   require(len(narrowed)==1,'echo read lost checked status propagation')
   comparisons=re.findall('('+var+r') = icmp eq i8 '+re.escape(narrowed[0])+r', 0$',body(echo),re.M)
   guards=[label for label,lines in blocks.items() if len(comparisons)==1 and re.fullmatch(
    r'br i1 '+re.escape(comparisons[0])+r', label %[A-Za-z0-9_.$-]+, label %[A-Za-z0-9_.$-]+',lines[-1])]
   require(len(guards)==1 and len(successors[merge])==1,'echo read lost one successful status guard/result join')
   failed=successors[guards[0]][1];following=successors[merge][0]
   require(blocks[failed]==['br label %'+following],'failed echo read can execute additional work')
   status_next=r'('+var+r') = phi i8 \[ '+re.escape(current_status)+', %'+re.escape(merge)+r' \], \[ '+re.escape(narrowed[0])+', %'+re.escape(failed)+r' \]'
   value_next=r'('+var+r') = phi i64 \[ '+re.escape(current_value)+', %'+re.escape(merge)+r' \], \[ 0, %'+re.escape(failed)+r' \]'
   status_phi=[re.fullmatch(status_next,line) for line in blocks[following] if re.fullmatch(status_next,line)]
   value_phi=[re.fullmatch(value_next,line) for line in blocks[following] if re.fullmatch(value_next,line)]
   require(len(status_phi)==len(value_phi)==1,'echo discarded a failed read or changed its admitted result')
   current_status,current_value=status_phi[0][1],value_phi[0][1];merge=following
  terminal='\n'.join(blocks[merge][2:])
  returned=re.fullmatch('('+var+r') = zext i8 '+re.escape(current_status)+r' to i64\n'+
   '('+var+r') = insertvalue \{ i64, i64 \} poison, i64 \1, 0\n'+
   '('+var+r') = insertvalue \{ i64, i64 \} \2, i64 '+re.escape(current_value)+r', 1\n'+
   r'ret \{ i64, i64 \} \3',terminal)
  require(returned is not None and len(re.findall(r'(?m)^\s*ret ',body(echo)))==1,
   'echo returned a different status/value instead of the actual admitted merge')
  checks.append({'echo_values_compared':True,'comparison':echo_comparison,
   'success':success,'failure':failure,'mismatch_status':101,'matched_accumulator':'%arg2'})
 def fresh_identity():
  events='Lemma.Documents.LocalToolEvents.';fresh=events+'freshRequestID';request=local+'request'
  selected=one(request,fresh).split(', ')
  require(len(selected)==3 and selected[:2]==['i64 %arg1','i64 %arg7'],
   'fresh identity must scan the current document with the actual candidate')
  equal_address(request,selected[2],{'%arg2':1},128)
  fresh_value=value(request,fresh,', '.join(selected))
  encoded=calls(request,protocol+'request')
  require(len(encoded)==2 and all(len(args.split(', '))==13 and args.split(', ')[0]=='i64 %arg2' and
   args.split(', ')[10]=='i64 '+fresh_value for args in encoded),
   'known/opaque request encoders lost the same selected fresh identity')
  checks.append(validate_checked_call_gate(body(request),symbol(fresh),symbol(protocol+'request')))
  # Follow the returned aggregate through only genuine finite i64 result joins.
  # Failure values may be zero; the only nonzero leaf is the selected identity.
  returned=re.findall(r'ret \{ i64, i64 \} ('+var+r')$',body(request),re.M)
  values=re.findall(re.escape(returned[0] if len(returned)==1 else '<missing>')+
   r' = insertvalue \{ i64, i64 \} '+var+r', i64 ('+var+r'|0), 1$',body(request),re.M)
  def leaves(operand,seen=None):
   if operand in {'0',fresh_value}:return {operand}
   seen=set() if seen is None else set(seen);require(operand not in seen,'cyclic fresh identity return join');seen.add(operand)
   phis=re.findall(re.escape(operand)+r' = phi i64 ([^\n]+)$',body(request),re.M)
   incoming=re.findall(r'\[ ('+var+r'|0), %[A-Za-z0-9_.$-]+ \]',phis[0]) if len(phis)==1 else []
   require(incoming,'unaccounted fresh identity return value')
   result=set()
   for entry in incoming:result|=leaves(entry,seen)
   return result
  require(len(values)==1 and leaves(values[0])=={'0',fresh_value},
   'local request returned a candidate or lost its selected fresh identity')
  checks.append(validate_fixed_fold(body(fresh),symbol(events+'freshRequestStep'),64))
 if role=='arithmetic':
  process=server+'processCopied';evaluate=protocol+'evaluate';read=one(process,memory+'read64')
  equal_address(process,read,{},0x20300+64+96)
  echoed=value(process,memory+'read64',read)
  checks.append(gate(process,'eq',echoed,'%arg1',evaluate))
  equal_address(process,one(process,evaluate),{},0x20300+64)
  reply=one(process,protocol+'reply').split(', ')
  require(len(reply)==4,'tool reply lost original input/output/result/status tuple')
  equal_address(process,reply[0],{},0x20300+64);equal_address(process,reply[1],{},0x20500)
  emitted=one(process,'Lemma.User.IPC.reply').split(', ')
  require(emitted[0]=='i64 %arg0' and len(emitted)==4,'tool reply changed receiver-local authority')
  equal_address(process,emitted[1],{},0x20500);equal_address(process,emitted[2],{},176)
  checks.append(validate_checked_call_gate(body(process),symbol(protocol+'reply'),symbol('Lemma.User.IPC.reply')))
  step=server+'step';receive=one(step,'Lemma.User.IPC.receive');received=value(step,'Lemma.User.IPC.receive',receive)
  routes=[(server+'processCopied',208),('Lemma.Services.Arithmetic.ServerV8.processCopied',256),('Lemma.Services.Arithmetic.ServerV7.processCopied',224)]
  tuples=[one(step,target) for target,_ in routes]
  require(len(set(tuples))==1,'service versions lost the same actual kernel authority/request binding')
  for target,extent in routes:checks.append(constant_gate(step,received,extent,target))
  checks.append(validate_fixed_fold(body(protocol+'reply'),symbol(protocol+'copyStep'),18))
  checks.append(validate_fixed_fold(body('Lemma.Services.Arithmetic.ReductionV1.calculate'),symbol('Lemma.Services.Arithmetic.ReductionV1.gcdStep'),32))
 elif role=='notebook':
  begin=n+'beginLocalReduction';pump=n+'pumpLocalReduction';request=local+'request'
  for owner,protected in ((begin,local+'request'),(pump,client+'beginCall')):
   read=one(owner,memory+'read64');equal_address(owner,read,{},0x20800+728)
   enabled=value(owner,memory+'read64',read);checks.append(constant_gate(owner,enabled,1,protected))
  fresh_identity()
  counter=value(begin,n+'get','i64 176');begin_args=one(begin,request)
  candidate=begin_args.split(', ')[-1]
  additions=re.findall('('+var+r') = add i64 '+re.escape(counter)+r', 1$',body(begin),re.M)
  require(len(additions)==1 and candidate=='i64 '+additions[0],
   'tool candidate lost the actual volatile counter increment')
  checks.append(gate(begin,'ult',counter,'9223372036854775806',request))
  request_value=value(begin,request,begin_args)
  checks.append(gate(begin,'ult',request_value,'9223372036854775806',local+'stagePrepared'))
  require(calls(begin,n+'put')==['i64 176, i64 '+request_value,'i64 552, i64 '+request_value,'i64 536, i64 16'],
   'tool counter/pending ownership lost the selected fresh request')
  for checked in (request,local+'stagePrepared'):
   checks.append(validate_failed_call_gate(body(begin),symbol(checked),symbol(n+'put'),
    symbol(n+'statusFailed'),body(n+'statusFailed')))
  floor=value(pump,n+'reductionGet','i64 8');frontier=value(pump,n+'get','i64 128')
  checks.append(gate(pump,'ult',floor,frontier,client+'beginCall'))
  checks.append(validate_failed_call_gate(body(pump),symbol(local+'current'),symbol(client+'beginCall'),
   symbol(n+'statusFailed'),body(n+'statusFailed')))
  staged=local+'stageApplied'
  require(one(staged,local+'current')=='i64 %arg0, i64 %arg1, i64 %arg4, i64 %arg5, i64 %arg7, i64 %arg8',
   'application current-work request/event/namespace/page tuple differs')
  checks.append(validate_checked_call_gate(body(staged),symbol(local+'current'),symbol('Lemma.Documents.Mathematics.applyLocalTool')))
  begun=client+'beginCall';read=one(begun,memory+'read64');equal_address(begun,read,{'%arg1':1},96)
  checks.append(gate(begun,'eq','%arg2',value(begun,memory+'read64',read),'Lemma.User.IPC.callBegin'))
  invoke=one(begun,'Lemma.User.IPC.callBegin').split(', ')
  require(invoke[:2]==['i64 %arg0','i64 %arg1'] and invoke[3]=='i64 %arg2','tool begin lost exact endpoint/buffer/request')
  equal_address(begun,invoke[2],{},144)
  client_echo()
 elif role=='client':client_echo()
 elif role=='local':fresh_identity()
 return {'role':role,'checked_value_CFG_gates':checks,'scope':'genuine pre-LLVM value/CFG checks; separate complete pre/post pins remain required; not a guest execution claim'}
