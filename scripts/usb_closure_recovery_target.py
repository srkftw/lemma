"""Separate complete artifact authority for Closure7/Doc8 recovery.

This checker inspects genuine IR and fixed source-bound authority only. It does
not implement guest recovery, invent receipts or confer mathematical authority.
Absent fresh authority is a rejection; old Sums pins are never reused as new pins.
"""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from core0_common import Core0Error
from paper_next import canonical
from usb_recovery_target import corpus, successor as inherited_recovery_source
from usb_closure_recovery_deployment import CONFIGURATIONS, SOFTWARE_DEPLOYMENT

def successor(source):
 return (source.startswith('Lemma.Notebook.RetryClosurePolicy.') or
  source.startswith('Lemma.Applications.Notebook.') and any(x in source for x in ('closureRecoverable','ClosureRecoverable','mainRecoverableClosure')) or
  source.startswith('Lemma.Platform.LemmaSim.NotebookKernel.') and 'ClosureRecovery' in source)

def semantic_guards(ir,unit):
 from audit_kernel import _ir_definition_body
 from usb_recovery_target import semantic_guards as old_semantics
 if unit.get('image_key')=='store':
  return old_semantics(ir,unit)
 rows={canonical(r['source']):r for r in unit['functions']}
 def body(name):
  if name not in rows:raise Core0Error('Closure recovery required owner absent: '+name)
  return _ir_definition_body(ir,rows[name]['symbol'])
 def calls(owner,target):
  if target not in rows:raise Core0Error('Closure recovery required callee absent: '+target)
  return re.findall(r'call\s+\{ i64, i64 \} @'+re.escape(rows[target]['symbol'])+r'\(([^\n]*)\)',body(owner))
 if unit['role']=='kernel':
  root='Lemma.Platform.LemmaSim.NotebookKernel.'
  initialization=unit['configuration'].endswith('-initialize')
  entry=root+('siliconUSBClosureRecoveryInitializeMedium' if initialization else 'siliconUSBClosureRecoveryBoot')
  if calls(entry,root+'bootRecovery')!=['i64 '+str(int(initialization))+', i64 13']:
   raise Core0Error('Closure recovery boot wrapper changed its exact initialization/hardware binding')
  if calls(root+'dispatchUSBClosureRecoveryBulk',root+'dispatchRecoveryBulk')!=['i64 13, i64 %arg0, i64 %arg1, i64 %arg2']:
   raise Core0Error('Closure recovery dispatcher changed its exact hardware binding/frame arguments')
  return {'binding':13,'initialization':int(initialization),'product_nv_authority':False,
   'scope':'Complete genuine kernel body/caller authority and exact thin wrappers; Notebook/Store outcomes are separate roles'}
 if unit['role']=='user' and unit.get('image_key')=='notebook':
  root='Lemma.Applications.Notebook.'
  finish=root+'closureRecoverableFinishRetained'
  if calls(finish,root+'startSave') or len(calls(finish,root+'finishRecord'))!=1:
   raise Core0Error('Closure recovery duplicated original publication or omitted original stage finish')
  if len(calls(root+'closureRecoverablePollRead',finish))!=1 or len(calls(root+'closureRecoverableResubmit',root+'startSave'))!=1:
   raise Core0Error('Closure recovery complete EOF/ordinary uncommitted paths differ')
  if len(calls(root+'closureRecoverableValidateRecord','Lemma.Documents.MathematicsClosure.validate'))!=1:
   raise Core0Error('Closure recovery omitted actual Doc8 staged validation')
  for owner in ('closureRecoverableRetainFailure','closureRecoverableBegin','closureRecoverableResubmit','closureRecoverableFinishRetained'):
   if len(calls(root+owner,root+'closureRecoverableValidateRecord'))!=1:
    raise Core0Error('Closure recovery staged validation caller differs: '+owner)
 return {'same_original_record_finished_once':True,'full_doc8_validation':True,
  'no_new_put_on_known_successor':True,'mount_is_saved':False,
  'scope':'Complete source/body/global/caller authority plus explicit Action outcomes; connected guest remains separate'}

def validate(ir,unit,*,optimized):
 rows=[canonical(r['source']) for r in unit.get('functions',[])]
 selected=unit.get('configuration') in CONFIGURATIONS and (unit.get('role')=='kernel' or unit.get('role')=='user' and unit.get('image_key') in ('store','notebook'))
 if not selected:
  if any(successor(s) or inherited_recovery_source(s) for s in rows):raise Core0Error('Closure recovery escaped exact configuration/role')
  return None
 role=('kernel-init' if unit['configuration'].endswith('-initialize') else 'kernel') if unit['role']=='kernel' else unit['image_key']
 version='core0-kernel-v0.6' if unit['role']=='kernel' else 'core0-user-v0.2'
 if unit.get('contract_version')!=version or unit.get('software_deployment')!=SOFTWARE_DEPLOYMENT:
  raise Core0Error('Closure recovery exact privilege/software tuple differs')
 path=Path(__file__).resolve().parents[1]/'tooling/usb-closure-recovery-target-authority.json'
 if not path.is_file():raise Core0Error('Fresh genuine complete Closure recovery authority missing')
 authority=json.loads(path.read_text())
 if authority.get('schema')!='lemma-usb-closure-recovery-target-authority/1' or set(authority.get('roles',{}))!={'kernel','kernel-init','store','notebook'}:
  raise Core0Error('Closure recovery exact authority schema/role inventory differs')
 wanted=authority['roles'][role];actual=corpus(ir,unit);phase='post' if optimized else 'pre'
 digest=hashlib.sha256(json.dumps(actual,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 if wanted.get('contract_version')!=version or len(actual['functions'])!=wanted.get('function_count') or digest!=wanted.get(phase+'_sha256'):
  raise Core0Error('Closure recovery complete signature/effect/body/global/caller inventory differs: '+role+'/'+phase)
 if unit['role']=='kernel' and any(s.startswith(('Lemma.Boot.Product','Lemma.Platform.LemmaSim.BootHealth')) or s.endswith(('.initProduct','.prepareManagedProduct','.configureProduct')) for s in rows):
  raise Core0Error('Closure recovery acquired Product/NV authority')
 semantics=None if optimized else semantic_guards(ir,unit)
 return {'contract_version':'lemma-usb-closure-recovery-target-authority/1','configuration':unit['configuration'],
  'role':role,'function_count':len(actual['functions']),'phase':phase,'complete_corpus_sha256':digest,
  'globals_sha256':actual['globals_sha256'],'callers_sha256':actual['callers_sha256'],
  'semantics':semantics,'scope':'Actual complete artifact authority; no connected CPU or USB-conformance claim'}

def readonly_request_kinds(ir,unit):
 """One genuine five-word mapping, three independently dominating bounds.

 Exact complete optimized bodies/globals are required before inspecting these
 pointer/load sites. Physical request-header reads keep ordinary access guards.
 """
 if unit.get('configuration') not in CONFIGURATIONS or unit.get('role')!='kernel':return set(),[],set()
 validate(ir,unit,optimized=True)
 from audit_kernel import _ir_definition_body,_line_functions,_structured_ir_blocks,_structured_successors,_structured_reachable
 source='Lemma.USB.Block.recoveryRequestValid'
 rows=[r for r in unit['functions'] if canonical(r['source'])==source]
 if len(rows)!=1 or (rows[0]['args'],rows[0]['effects'])!=(['u64']*6,['checked-access','physical-read']):raise Core0Error('recovery request-kind readonly owner differs')
 symbol=rows[0]['symbol'];body=_ir_definition_body(ir,symbol)
 globals_=[line for line in ir.splitlines() if line.startswith('@switch.table.'+symbol)];values=[0,1,3,3,2]
 if len(globals_)!=1:raise Core0Error('recovery request-kind complete global inventory differs')
 table=globals_[0].split(' = ',1)[0][1:]
 expected='@'+table+' = private unnamed_addr constant [5 x i64] ['+', '.join('i64 '+str(n) for n in values)+'], align 8'
 if globals_[0]!=expected:raise Core0Error('recovery request-kind immutable bytes/width/extent differ')
 blocks=_structured_ir_blocks('\n'.join(line.split(';',1)[0].rstrip() for line in body.splitlines()));graph=_structured_successors(blocks);owners=_line_functions(ir.splitlines());sites=set();loads=0
 for block,instructions in blocks.items():
  geps=[line.strip() for line in instructions if 'getelementptr' in line and '@'+table in line]
  for gep in geps:
   match=re.fullmatch(r'(%[-\w.]+) = getelementptr inbounds nuw \[5 x i64\], ptr @'+re.escape(table)+r', i64 0, i64 (%[-\w.]+)',gep)
   if match is None:raise Core0Error('recovery request-kind typed GEP/index differs')
   pointer,index=match.groups();index_def=index+' = add i64 %arg1, -1'
   guards=[]
   for label,lines in blocks.items():
    text='\n'.join(lines)
    bound=re.search(r'(%[-\w.]+) = icmp ult i64 '+re.escape(index)+r', 5',text)
    if index_def in text and bound and re.search(r'br i1 '+re.escape(bound[1])+r', label %'+re.escape(block)+r', label %[-\w.]+',text):guards.append(label)
   if len(guards)!=1:raise Core0Error('recovery request-kind exact kind-1 bound absent')
   guarded=guards[0];cut={label:tuple(target for target in targets if (label,target)!=(guarded,block)) for label,targets in graph.items()}
   if _structured_reachable(cut,'entry',block):raise Core0Error('recovery request-kind lookup has a bound bypass')
   load_lines=[line.strip() for line in instructions if re.fullmatch(r'%[-\w.]+ = load i64, ptr '+re.escape(pointer)+r', align 8',line.strip())]
   if len(load_lines)!=1:raise Core0Error('recovery request-kind sole aligned readonly load absent')
   located={i for i,line in enumerate(ir.splitlines()) if line.strip()==load_lines[0] and owners[i]==symbol}
   if len(located)!=1:raise Core0Error('recovery request-kind load site ownership differs')
   sites|=located;loads+=1
 if loads!=3 or len(re.findall('@'+re.escape(table)+r'(?![A-Za-z0-9_.$-])',ir))!=4:raise Core0Error('recovery request-kind exact three lookup uses differ')
 return sites,[{'source':source,'function':symbol,'global':table,'values':values,'element_bits':64,'alignment_bytes':8,'index_bound':5,'default':3,'guarded_loads':3,'readonly':True,'literal_schema':'usb-recovery-request-kind-v1','bytes':40,'section':'.rodata'}],{expected}
