"""Complete genuine artifact authority for the four-role package/recovery4 tuple.
No target execution, recovery, durability or mathematical result runs here.
The complete pre/post bodies, globals, callers and catalog are load-bearing.
"""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from core0_common import Core0Error
from paper_next import canonical
from usb_recovery_target import corpus
from package_companion_deployment import CONFIGURATIONS,SOFTWARE_DEPLOYMENT,BOOT_ROOTS,DISPATCH_ROOT,USER_ROOTS

VERSION='lemma-package-clocked-recovery4-target/1'
AUTHORITY=Path(__file__).resolve().parents[1]/'tooling/package-companion-target-authority.json'
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def selected(unit):return unit.get('configuration') in CONFIGURATIONS
def role_key(unit):
 if unit.get('role')=='firmware':return 'firmware-init' if unit['configuration'].endswith('-initialize') else 'firmware'
 if unit.get('role')=='kernel':return 'kernel-init' if unit['configuration'].endswith('-initialize') else 'kernel'
 if unit.get('role')=='user' and unit.get('image_key') in USER_ROOTS:return unit['image_key']
 raise Core0Error('Package recovery role outside exact firmware/kernel/four-user artifact authority')
def contract(unit):
 if not selected(unit):return None
 if unit.get('software_deployment')!=SOFTWARE_DEPLOYMENT:raise Core0Error('Package recovery hardware/software tuple differs')
 if not AUTHORITY.is_file():raise Core0Error('Package recovery complete genuine authority missing')
 authority=json.loads(AUTHORITY.read_text())
 if authority.get('schema')!=VERSION or set(authority.get('roles',{}))!={'firmware','firmware-init','kernel','kernel-init',*USER_ROOTS}:raise Core0Error('Package recovery authority schema/roles differ')
 key=role_key(unit);wanted=authority['roles'][key]
 catalogs=wanted.get('catalog_sha256_by_configuration')
 if unit.get('role')=='user':
  if not isinstance(catalogs,dict) or set(catalogs)!=set(CONFIGURATIONS) or catalogs[CONFIGURATIONS[0]]!=wanted['catalog_sha256']:
   raise Core0Error('Package recovery requires both exact genuine user configuration catalogs')
  expected=catalogs[unit['configuration']]
 else:expected=wanted['catalog_sha256']
 if digest(unit)!=expected:raise Core0Error('Package recovery complete typed/effect/root catalog differs: '+key)
 return key,wanted

def semantic_guards(ir,unit):
 from audit_kernel import _ir_definition_body
 rows={canonical(r['source']):r for r in unit['functions']}
 def calls(owner,target):
  if owner not in rows or target not in rows:raise Core0Error('Package recovery semantic owner absent: '+owner+'/'+target)
  body=_ir_definition_body(ir,rows[owner]['symbol'])
  return re.findall(r'call\s+\{ i64, i64 \} @'+re.escape(rows[target]['symbol'])+r'\(([^\n]*)\)',body)
 if unit['role']=='kernel':
  root='Lemma.Platform.LemmaSim.NotebookKernel.';init=int(unit['configuration'].endswith('-initialize'))
  if calls(root+BOOT_ROOTS[unit['configuration']],root+'bootPackageRecovery')!=['i64 '+str(init)]:raise Core0Error('Package recovery boot initialization differs')
  if calls(root+DISPATCH_ROOT,root+'dispatchRecoveryBulk')!=['i64 13, i64 %arg0, i64 %arg1, i64 %arg2']:raise Core0Error('Package recovery exact Clocked13 dispatch differs')
  if len(calls(root+'constructPackageRecovery','Lemma.Platform.LemmaSim.DeviceService.configureUSBRecovery'))!=1:raise Core0Error('Package recovery missing real USB recovery controller setup')
  if any(x.startswith(('Lemma.Boot.Product','Lemma.Platform.LemmaSim.BootHealth')) for x in rows):raise Core0Error('Package recovery acquired undeclared Product/NV authority')
 elif unit.get('image_key')=='notebook':
  root='Lemma.Applications.Notebook.'
  finish=root+'packageRecoverableFinishRetained'
  if calls(finish,root+'startSave') or len(calls(finish,root+'finishRecord'))!=1:raise Core0Error('Workspace reconciliation repeats original PUT or omits finish')
  if len(calls(root+'packageRecoverablePollRead',finish))!=1:raise Core0Error('Workspace exact READ/EOF completion differs')
  if len(calls(root+'packageRecoverableValidateRecord','Lemma.Courses.WorkspaceCodec.decode'))!=1:raise Core0Error('Workspace retained validation omitted complete genuine decoder')
  for owner in ('packageRecoverableRetainFailure','packageRecoverableBegin','packageRecoverableResubmit','packageRecoverableFinishRetained'):
   if len(calls(root+owner,root+'packageRecoverableValidateRecord'))!=1:raise Core0Error('Workspace retained validation caller differs: '+owner)
 elif unit.get('image_key')=='store':
  root='Lemma.Services.Store.ServerRecoveryAwait.'
  if len(calls(root+'stepAwait','Lemma.Services.Store.ServerRecovery.pumpRecoveryPhase'))!=1 or len(calls(root+'stepAwait','Lemma.Services.Store.ServerAwait.settleWaiters'))!=1:raise Core0Error('Joined Store omitted original recovery or actual mount settlement')
 return {'exact_source_semantics':True,'scope':'Complete body/caller pins plus explicit Action/IR guards; not a compiler proof or connected durability result'}

def complete_corpus(ir,unit,*,optimized):
 from surface_word_inline import validate as validate_surface_inline
 inline=validate_surface_inline(ir,unit,optimized=optimized)
 removed=set(inline['removed_symbols']) if inline is not None and optimized else set()
 # Only the two source-checked callback eliminations already proved by the
 # unchanged Surface CFG/body/header gates are admissible. All other missing
 # definitions still reject in the original complete-corpus collector.
 filtered={**unit,'functions':[r for r in unit['functions'] if r['symbol'] not in removed]}
 actual=corpus(ir,filtered)
 if removed:actual['elided_checked_callbacks']=sorted(canonical(r['source']) for r in unit['functions'] if r['symbol'] in removed)
 return actual

def validate(ir,unit,*,optimized):
 from aligned_notebook_target import candidate as aligned_candidate, validate as validate_aligned
 if aligned_candidate(unit):return validate_aligned(ir,unit,optimized=optimized)
 found=contract(unit)
 if found is None:return None
 key,wanted=found;phase='post' if optimized else 'pre';actual=complete_corpus(ir,unit,optimized=optimized)
 if len(actual['functions'])!=wanted.get(phase+'_function_count',wanted['function_count']) or digest(actual)!=wanted[phase+'_sha256']:raise Core0Error('Package recovery complete body/global/caller corpus differs: '+key+'/'+phase)
 return {'contract_version':VERSION,'role':key,'phase':phase,'function_count':len(actual['functions']),'complete_corpus_sha256':digest(actual),'globals_sha256':actual['globals_sha256'],'callers_sha256':actual['callers_sha256'],'semantics':None if optimized else semantic_guards(ir,unit),'scope':'Actual complete artifact authority; no linked-image/CPU/USB-conformance claim'}


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
