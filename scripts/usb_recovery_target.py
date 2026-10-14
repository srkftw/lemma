"""Closed artifact authority for the opt-in Clocked13 recovery software.

Genuine captured complete bodies, globals and callers bind independent Action
observations. This does not execute a journal, manufacture a peer receipt or
certify compiler correctness or connected recovery.
"""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from core0_common import Core0Error
from paper_next import canonical

CONFIGURATIONS=frozenset(('lemmasim-silicon-usb-clocked-retry-bulk-notebook','lemmasim-silicon-usb-clocked-retry-bulk-initialize'))
SOFTWARE_DEPLOYMENT={'contract_version':'lemma-usb-clocked-recovery-deployment-v1','silicon_profile':'lemma-silicon-dev/0.13.0','user_profiles':{'store':'core0-user-v0.2','notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.3'}}

def successor(source):
 return (source.startswith(('Lemma.Services.Store.ServerRecovery.','Lemma.Services.Store.RecoveryClient.','Lemma.Services.Store.RecoveryProtocol.','Lemma.Services.Store.Remount.','Lemma.Notebook.RetryPolicy.')) or
  source.startswith('Lemma.USB.Block.') and 'recovery' in source.lower() or
  source.startswith('Lemma.Platform.LemmaSim.DeviceService.') and 'recovery' in source.lower() or
  source.startswith('Lemma.Platform.LemmaSim.NotebookKernel.') and 'recovery' in source.lower() or
  source.startswith('Lemma.Applications.Notebook.') and any(x in source.lower() for x in ('recoverable','retry')))

def corpus(ir,unit):
 from audit_kernel import _ir_definition_body,parse_definitions_and_calls
 rows={canonical(r['source']):r for r in unit.get('functions',[])}
 if len(rows)!=len(unit.get('functions',[])):raise Core0Error('recovery duplicate canonical source')
 names={r['symbol']:s for s,r in rows.items()};aliases={}
 globals_=[line.split(';',1)[0].strip() for line in ir.splitlines() if line.startswith('@')]
 for line in globals_:
  raw=line.split(' = ',1)[0][1:]
  for symbol in sorted(names,key=len,reverse=True):
   prefix='switch.table.'+symbol
   if raw==prefix or raw.startswith(prefix+'.'):
    aliases[raw]='switch.table.'+names[symbol]+raw[len(prefix):];break
 def rebound(text):
  return re.sub(r'@([-A-Za-z0-9_.$]+)',lambda m:'@'+aliases.get(m[1],names.get(m[1],m[1])),text)
 functions={};edges=[]
 for source,row in rows.items():
  body=_ir_definition_body(ir,row['symbol'])
  if body is None:raise Core0Error('recovery source body absent: '+source)
  normalized=' '.join(rebound(' '.join(line.split(';',1)[0].strip() for line in body.splitlines())).split())
  functions[source]={'args':row['args'],'effects':row['effects'],'sha256':hashlib.sha256(normalized.encode()).hexdigest()}
  for called in parse_definitions_and_calls(body)[2]:edges.append((source,names.get(called,called)))
 return {'functions':functions,'globals_sha256':hashlib.sha256(json.dumps(sorted(rebound(s) for s in globals_),separators=(',',':')).encode()).hexdigest(),'callers_sha256':hashlib.sha256(json.dumps(sorted(edges),separators=(',',':')).encode()).hexdigest()}

def semantic_guards(ir,unit):
 from audit_kernel import _ir_definition_body
 rows={canonical(r['source']):r for r in unit['functions']}
 def body(name):
  if name not in rows:raise Core0Error('recovery semantic owner absent: '+name)
  return _ir_definition_body(ir,rows[name]['symbol'])
 def calls(owner,target):return re.findall(r'call\s+\{ i64, i64 \} @'+re.escape(rows[target]['symbol'])+r'\(([^\n]*)\)',body(owner))
 if unit['role']=='user' and unit.get('image_key')=='store':
  root='Lemma.Services.Store.ServerRecovery.'
  sys='Lemma.User.Syscall.call'
  if sys not in rows:raise Core0Error('recovery Store lacks real syscall boundary')
  actual=calls(root+'durabilityBarrier',sys)
  getter='Lemma.Services.Store.Remount.shadowBuffer'
  if getter not in rows or body(getter).strip()!='entry:\n  ret i64 405504':raise Core0Error('recovery barrier owned shadow buffer differs')
  values=re.findall(r'(%[-\w.]+) = call i64 @'+re.escape(rows[getter]['symbol'])+r'\(\)',body(root+'durabilityBarrier'))
  if len(values)!=1:raise Core0Error('recovery barrier buffer is not its fixed getter')
  actual=[text.replace('i64 '+values[0]+',','i64 405504,') for text in actual]
  if len(actual)!=2 or not any(re.fullmatch(r'i64 66, i64 %[-\w.]+, i64 3, i64 0, i64 0, i64 0',s) for s in actual) or not any(re.fullmatch(r'i64 66, i64 %[-\w.]+, i64 4, i64 0, i64 405504, i64 0',s) for s in actual):raise Core0Error('recovery lost actual submit/completion durability barrier')
  if len(calls(root+'shadowValidated','Lemma.Services.Store.Remount.inspect'))!=1 or len(calls(root+'shadowAdopt','Lemma.Services.Store.Remount.adopt'))!=1:raise Core0Error('recovery omitted complete shadow preflight/adoption')
 if unit['role']=='user' and unit.get('image_key')=='notebook':
  root='Lemma.Applications.Notebook.'
  if calls(root+'recoverableFinishRetained',root+'startSave') or len(calls(root+'recoverableFinishRetained',root+'finishRecord'))!=1:raise Core0Error('reconciled original record acquired duplicate publication')
  if len(calls(root+'recoverablePollRead',root+'recoverableFinishRetained'))!=1:raise Core0Error('complete matching EOF does not finish retained record once')
  if len(calls(root+'recoverableResubmit',root+'startSave'))!=1:raise Core0Error('uncommitted record lost its actual ordinary save path')
 return {'quarantine_requires_actual_receipt':True,'remount_requires_actual_barrier':True,'matching_known_successor_republished':False,'mount_is_saved':False,'scope':'complete source/body gates plus independent Action boundary observations; connected CPU/peer still separate'}

def validate(ir,unit,*,optimized):
 rows=[canonical(r['source']) for r in unit.get('functions',[])]
 selected=unit.get('configuration') in CONFIGURATIONS and (unit.get('role')=='kernel' or unit.get('role')=='user' and unit.get('image_key') in ('store','notebook'))
 if not selected:
  if any(successor(s) for s in rows):raise Core0Error('recovery policy escaped exact software deployment/role')
  return None
 role=('kernel-init' if unit['configuration'].endswith('-initialize') else 'kernel') if unit['role']=='kernel' else unit['image_key']
 version='core0-kernel-v0.6' if unit['role']=='kernel' else 'core0-user-v0.2'
 if unit.get('contract_version')!=version or unit.get('software_deployment')!=SOFTWARE_DEPLOYMENT:raise Core0Error('recovery privilege/software identity differs')
 path=Path(__file__).resolve().parents[1]/'tooling/usb-recovery-target-authority.json'
 if not path.is_file():raise Core0Error('complete genuine recovery authority missing')
 authority=json.loads(path.read_text())
 if authority.get('schema')!='lemma-usb-recovery-target-authority/1' or set(authority.get('roles',{}))!={'kernel','kernel-init','store','notebook'}:raise Core0Error('recovery authority schema/role inventory differs')
 wanted=authority['roles'][role];actual=corpus(ir,unit);phase='post' if optimized else 'pre'
 digest=hashlib.sha256(json.dumps(actual,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 if wanted.get('contract_version')!=version or len(actual['functions'])!=wanted.get('function_count') or digest!=wanted.get(phase+'_sha256'):raise Core0Error('recovery complete signature/effect/body/global/caller inventory differs: '+role+'/'+phase)
 if unit['role']=='kernel' and any(s.startswith(('Lemma.Boot.Product','Lemma.Platform.LemmaSim.BootHealth')) or s.endswith(('.initProduct','.prepareManagedProduct','.configureProduct')) for s in rows):raise Core0Error('recovery acquired product/NV authority')
 semantics=None if optimized else semantic_guards(ir,unit)
 return {'contract_version':'lemma-usb-recovery-target-authority/1','configuration':unit['configuration'],'role':role,'function_count':len(actual['functions']),'phase':phase,'complete_corpus_sha256':digest,'globals_sha256':actual['globals_sha256'],'callers_sha256':actual['callers_sha256'],'semantics':semantics,'scope':'genuine emitted complete artifact authority; connected RV64 recovery/full USB conformance not implied'}

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
