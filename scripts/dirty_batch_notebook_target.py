"""Complete artifact authority for the Package dirty-tile batch successor.
No guest renderer, recovery or mathematical authority is implemented here.
Historical cohorts continue through their existing independent validators.
"""
import hashlib,json,re
from pathlib import Path
from core0_common import Core0Error
from paper_next import canonical
from package_closure_deployment import CONFIGURATIONS as CANONICAL,SOFTWARE_DEPLOYMENT as CANONICAL_SOFTWARE
from package_companion_deployment import CONFIGURATIONS as COMPANION,SOFTWARE_DEPLOYMENT as COMPANION_SOFTWARE
VERSION='lemma-dirty-surface-notebook-artifact/1'
RESTORED_VERSION='lemma-restored-surface-notebook-artifact/1'
COURSE_SAVE_VERSION='lemma-course-preserving-save-notebook-artifact/1'
COURSE_SAVE_SOURCE='Lemma.Applications.Notebook.packageRequestSave'
RESTORED_ADDED=frozenset('Lemma.Applications.Notebook.'+n for n in ('restorePaperBatch','pumpRefreshRestoredBatched'))
def restored(unit):return bool(RESTORED_ADDED & {canonical(r.get('source','')) for r in unit.get('functions',[])})
def course_save(unit):return any(canonical(r.get('source',''))==COURSE_SAVE_SOURCE for r in unit.get('functions',[]))
AUTHORITY=Path(__file__).resolve().parents[1]/'tooling/dirty-batch-notebook-target-authority.json'
MARKER='Lemma.Ink.Surface.uploadIndexedBulk'
ADDED=frozenset('Lemma.Ink.Surface.'+n for n in ('indexedValidStep','indexedCopyWord','indexedPrepareStep','uploadIndexedBulk','uploadIndexedBulk.prepare'))|frozenset('Lemma.Applications.Notebook.'+n for n in ('collectDirtyIndexStep','consumeDirtyIndexStep','uploadDirtyBatch','pumpRefreshBatched'))
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def candidate(unit):return any(canonical(row.get('source',''))==MARKER for row in unit.get('functions',[]))
def contract(unit):
 if numeric_candidate(unit):return numeric_contract(unit)
 if not candidate(unit):return None
 config=unit.get('configuration');scope='canonical'if config in CANONICAL else'companion'if config in COMPANION else None
 root='Lemma.Applications.Notebook.'+('mainPackageClosureBulk'if scope=='canonical'else'mainRecoverablePackageClosureBulk')
 if scope is None or unit.get('role')!='user'or unit.get('image_key')!='notebook'or unit.get('image_id')!=2 or unit.get('contract_version')!='core0-user-v0.2' or unit.get('used_device_ops')!=[]:raise Core0Error('Dirty batch escaped exact Notebook deployment/profile')
 if unit.get('software_deployment')!=(CANONICAL_SOFTWARE if scope=='canonical'else COMPANION_SOFTWARE):raise Core0Error('Dirty batch hardware/software tuple differs')
 if [{k:r.get(k)for k in ('source','id','args')}for r in unit.get('roots',[])]!=[{'source':root,'id':1,'args':['u64']}]:raise Core0Error('Dirty batch exact root/ABI differs')
 a=json.loads(AUTHORITY.read_text());is_restored=restored(unit);is_course=course_save(unit)
 if is_course:
  if not is_restored:raise Core0Error('Course Save escaped its complete restored-surface cohort')
  a=a.get('course_save_v1',{})
 elif is_restored:a=a.get('restored_v1',{})
 version=11 if is_course else 10 if is_restored else 9
 schema=COURSE_SAVE_VERSION if is_course else RESTORED_VERSION if is_restored else VERSION
 if a.get('schema')!=schema or set(a.get('deployments',{}))!={'canonical','companion'}:raise Core0Error('Dirty batch complete genuine authority missing')
 w=a['deployments'][scope];configs=CANONICAL if scope=='canonical'else COMPANION;catalogs=w.get('catalog_sha256_by_configuration')
 if not isinstance(catalogs,dict)or set(catalogs)!=set(configs)or catalogs[config]!=digest(unit)or w.get('package_notebook_version')!=version:raise Core0Error('Dirty batch complete typed/effect/root catalog differs')
 names={canonical(r['source'])for r in unit['functions']}
 expected=(ADDED-{'Lemma.Applications.Notebook.pumpRefreshBatched'})|RESTORED_ADDED if is_restored else ADDED
 if is_course:expected=expected|{COURSE_SAVE_SOURCE}
 if not expected<=names or is_restored and 'Lemma.Applications.Notebook.pumpRefreshBatched' in names:raise Core0Error('Dirty/restored batch mixed or partial source cohort')
 return scope,w
def semantics(ir,unit,scope):
 from audit_kernel import _ir_definition_body
 from control_notebook_target import semantics as controls
 rows={canonical(r['source']):r for r in unit['functions']}
 def calls(owner,target):
  if owner not in rows or target not in rows:raise Core0Error('Dirty semantic owner absent')
  body=_ir_definition_body(ir,rows[owner]['symbol'])
  return re.findall(r'call \{ i64, i64 \} @'+re.escape(rows[target]['symbol'])+r'\(([^\n]*)\)',body)
 prefix='Lemma.Applications.Notebook.'
 expected=prefix+('packageStep'if scope=='canonical'else'packageRecoverableStep')
 pump=prefix+('pumpRefreshRestoredBatched' if restored(unit) else 'pumpRefreshBatched')
 if len(calls(expected,pump))!=1:raise Core0Error('Dirty batch missing actual selected loop call')
 if len(calls(pump,prefix+'uploadDirtyBatch'))!=1:raise Core0Error('Dirty batch missing bounded upload path')
 if restored(unit) and (len(calls(pump,prefix+'restorePaperBatch'))!=1 or len(calls(prefix+'restorePaperBatch',MARKER))!=1):raise Core0Error('Restoration lost its actual selected bounded owned upload path')
 if len(calls(prefix+'uploadDirtyBatch',MARKER))!=1 or len(calls(prefix+'uploadDirtyBatch',prefix+'consumeDirtyIndexStep'))!=1:raise Core0Error('Dirty batch missing controller/actual-prefix consumption')
 if len(calls('Lemma.Ink.Surface.indexedPrepareStep','Lemma.Ink.Surface.indexedCopyWord'))!=1:raise Core0Error('Dirty batch lost ordinary checked word callback')
 if course_save(unit):
  if len(calls(prefix+'packageToolbar',COURSE_SAVE_SOURCE))!=1:raise Core0Error('Course Save lost the actual toolbar connection')
  if calls(COURSE_SAVE_SOURCE,prefix+'issue')!=['i64 8, i64 0, i64 0, i64 0']:raise Core0Error('Course Save lost the ordinary Store status request')
  reported=calls(COURSE_SAVE_SOURCE,prefix+'reportCommitState')
  if len(reported)!=1 or not reported[0].startswith('i64 1059,'):raise Core0Error('Course Save admission must publish only Pending')
  if calls(COURSE_SAVE_SOURCE,prefix+'redraw') or calls(COURSE_SAVE_SOURCE,prefix+'packageCloseState'):raise Core0Error('Course Save closes/rebuilds the course view')
 return {'ordinary_package_batch_connected':True,'body_controls':controls(ir,unit,scope),'queue':'same16384-entry FIFO/bitmap; <=4 tiles and actual completed prefix','memory':'same owned Surface-v2 staging page; no allocator/runtime/record change'}
def validate(ir,unit,*,optimized):
 if numeric_candidate(unit):return numeric_validate(ir,unit,optimized=optimized)
 found=contract(unit)
 if found is None:return None
 scope,w=found
 from package_companion_target import complete_corpus
 phase='post'if optimized else'pre';actual=complete_corpus(ir,unit,optimized=optimized)
 if len(actual['functions'])!=w[phase+'_function_count']or digest(actual)!=w[phase+'_sha256']:raise Core0Error('Dirty batch complete body/global/caller corpus differs: '+scope+'/'+phase)
 return {'contract_version':'lemma-installed-package-notebook/'+str(w['package_notebook_version']),'artifact_contract_version':COURSE_SAVE_VERSION if course_save(unit) else RESTORED_VERSION if restored(unit) else VERSION,'software_scope':scope,'package_notebook_version':w['package_notebook_version'],'phase':phase,'function_count':len(actual['functions']),'complete_corpus_sha256':digest(actual),'semantics':None if optimized else semantics(ir,unit,scope),'scope':'Complete genuine artifact relation; no CPU/latency/durability claim'}


# Additive genuine number-entry cohort; historical validators above remain exact.
from pathlib import Path
import hashlib,json,re
from core0_common import Core0Error
from paper_next import canonical
from package_closure_deployment import CONFIGURATIONS as NUMERIC_CONFIGURATIONS, SOFTWARE_DEPLOYMENT as NUMERIC_SOFTWARE
NUMERIC_VERSION='lemma-number-entry-notebook-artifact/1'
NUMERIC_ROOT='Lemma.Applications.Notebook.mainPackageNumberPad'
NUMERIC_AUTHORITY=Path(__file__).resolve().parents[1]/'tooling/dirty-batch-notebook-target-authority.json'
def numeric_digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def numeric_candidate(unit):
 rows=unit.get('functions',[])
 if not isinstance(rows,list)or any(not isinstance(r,dict)or not isinstance(r.get('source'),str)for r in rows):raise Core0Error('Number entry candidate function map malformed')
 return any(canonical(r['source'])==NUMERIC_ROOT or canonical(r['source']).startswith(('Lemma.Courses.NumberPad.','Lemma.Documents.MathematicsEntry.'))for r in rows)
def numeric_contract(unit):
 if not numeric_candidate(unit):return None
 if unit.get('configuration')not in NUMERIC_CONFIGURATIONS or unit.get('role')!='user'or unit.get('image_key')!='notebook'or unit.get('image_id')!=2 or unit.get('contract_version')!='core0-user-v0.2' or unit.get('used_device_ops')!=[] or unit.get('software_deployment')!=NUMERIC_SOFTWARE:raise Core0Error('Number entry escaped exact canonical Notebook deployment')
 if [{k:r.get(k)for k in ('source','id','args')}for r in unit.get('roots',[])]!=[{'source':NUMERIC_ROOT,'id':1,'args':['u64']}]:raise Core0Error('Number entry root/ABI differs')
 master=json.loads(NUMERIC_AUTHORITY.read_text());a=master.get('number_entry_v1',{})
 if a.get('schema')!=NUMERIC_VERSION or a.get('package_notebook_version')!=12 or set(a.get('catalog_sha256_by_configuration',{}))!=set(NUMERIC_CONFIGURATIONS):raise Core0Error('Number entry original artifact schema differs')
 if a['catalog_sha256_by_configuration'][unit['configuration']]!=numeric_digest(unit):
  previous=a;a=master.get('number_entry_repaint_v1',{})
  if a.get('schema')!='lemma-number-entry-repaint-artifact/1' or a.get('package_notebook_version')!=13 or a.get('previous_artifact_sha256')!=numeric_digest(previous) or set(a.get('catalog_sha256_by_configuration',{}))!=set(NUMERIC_CONFIGURATIONS):raise Core0Error('Number entry repaint exact predecessor differs')
  if a['catalog_sha256_by_configuration'][unit['configuration']]!=numeric_digest(unit):
   previous=a;a=master.get('number_entry_aligned_v1',{})
   if a.get('schema')!='lemma-number-entry-aligned-artifact/1' or a.get('package_notebook_version')!=14 or a.get('previous_artifact_sha256')!=numeric_digest(previous) or set(a.get('catalog_sha256_by_configuration',{}))!=set(NUMERIC_CONFIGURATIONS)or a['catalog_sha256_by_configuration'][unit['configuration']]!=numeric_digest(unit):raise Core0Error('Number entry aligned exact predecessor/catalog differs')
 if {r.get('stable_id')for r in unit.get('used_execution_ops',[])}!={'execution.virtual-read8','execution.virtual-read64','execution.virtual-write8','execution.virtual-write64','execution.syscall'}:raise Core0Error('Number entry execution authority differs')
 return 'canonical',a

def numeric_semantics(ir,unit):
 from audit_kernel import _ir_definition_body
 rows={canonical(r['source']):r for r in unit['functions']}
 prefix='Lemma.Applications.Notebook.'
 def calls(owner,target):
  if owner not in rows or target not in rows:raise Core0Error('Number entry semantic owner absent')
  return re.findall(r'call \{ i64, i64 \} @'+re.escape(rows[target]['symbol'])+r'\(([^\n]*)\)',_ir_definition_body(ir,rows[owner]['symbol']))
 version=numeric_contract(unit)[1]['package_notebook_version']
 publisher='numericPublishAligned'if version==14 else'publishPackageWorkspace'
 for owner,target in [('numericInputSample.acceptSample','numericPadPress'),('numericPadPress',publisher),('numericStep','numericPumpPad'),('numericStep','pumpRefreshRestoredBatched'),('publishPackageWorkspace','savePackageWorkspace'),('savePackageWorkspace','startSave'),('packageToolbar','packageRequestSave'),('uploadDirtyBatch','consumeDirtyIndexStep'),('pumpRefreshRestoredBatched','restorePaperBatch'),('restorePaperBatch','Lemma.Ink.Surface.uploadIndexedBulk')]:
  target=target if target.startswith('Lemma.')else prefix+target
  if len(calls(prefix+owner,target))!=1:raise Core0Error('Number entry disconnected ordinary path: '+owner+'/'+target)
 for owner,target in [('numericPadPress','Lemma.Documents.MathematicsEntry.press'),('numericPumpPad','Lemma.Courses.NumberPad.render'),('numericPadPress.recapture','Lemma.Courses.PackageWorkspace.captureSelection')]:
  if len(calls(prefix+owner,target))!=1:raise Core0Error('Number entry lost actual guest operation')
 if version>=13:
  repair=prefix+'numericPumpCancelledRedraw'
  if len(calls(prefix+'numericStep',repair))!=1 or len(calls(repair,prefix+'pumpCancelledRedraw'))!=1 or len(calls(repair,prefix+'renderPackageCourse'))!=1:raise Core0Error('Number entry loss recovery lost its actual guest repaint path')
  if calls(repair,prefix+'startSave')or calls(repair,prefix+'reportCommitState'):raise Core0Error('Number entry loss repaint acquired persistence/acknowledgment authority')
 if version==14:
  for target in ('adoptPackageWorkspace','reportCourse','savePackageWorkspace'):
   if len(calls(prefix+publisher,prefix+target))!=1:raise Core0Error('Aligned number entry changed ordinary publication/report/Save')
  if len(calls(prefix+publisher,'Lemma.Courses.ArithmeticAligned.render'))!=1 or calls(prefix+publisher,prefix+'renderPackageCourse'):raise Core0Error('Aligned number entry lost its actual selected renderer')
 if calls(prefix+'packageRequestSave',prefix+'issue')!=['i64 8, i64 0, i64 0, i64 0']:raise Core0Error('Number entry explicit Save differs')
 return {'ordinary_guest_entry_and_storage_connected':True,'numeric_bounds':'0..99; overflow is unchanged bytes, explicit limit message','scope':'Complete source/IR authority; CPU/Store/controller qualification separate'}

def numeric_validate(ir,unit,*,optimized):
 found=numeric_contract(unit)
 if found is None:return None
 _,w=found
 from package_companion_target import complete_corpus
 phase='post'if optimized else'pre';actual=complete_corpus(ir,unit,optimized=optimized)
 if len(actual['functions'])!=w[phase+'_function_count']or numeric_digest(actual)!=w[phase+'_sha256']:raise Core0Error('Number entry complete body/global/caller corpus differs: '+phase)
 return {'contract_version':'lemma-installed-package-notebook/'+str(w['package_notebook_version']),'artifact_contract_version':w['schema'],'software_scope':'canonical','package_notebook_version':w['package_notebook_version'],'phase':phase,'function_count':len(actual['functions']),'complete_corpus_sha256':numeric_digest(actual),'semantics':None if optimized else numeric_semantics(ir,unit),'scope':'Genuine complete artifact; CPU/durability/timing qualification separate'}

NUMERIC_CHARACTER='Lemma.Courses.NumberPad.character'
NUMERIC_COLUMNS={3:67,4:76,5:82,15:48,24:66,25:65,26:67,27:75}
def numeric_jump_spec(ir,unit,source,symbol):
 if source!=NUMERIC_CHARACTER:return None
 numeric_validate(ir,unit,optimized=True)
 from audit_kernel import _ir_definition_body
 rows=[r for r in unit['functions']if canonical(r['source'])==source]
 if len(rows)!=1 or rows[0]['symbol']!=symbol or rows[0]['args']!=['u64']*3 or rows[0]['effects']!=[]:raise Core0Error('Number pad character owner/signature differs')
 body=_ir_definition_body(ir,symbol)
 switches=[sorted(int(v)for v in re.findall(r'i64 (-?\d+), label',part))for part in re.findall(r'switch i64 [^\n]+\[([^]]+)\]',body,re.S)]
 if switches!=[[4,15,26],list(NUMERIC_COLUMNS)]:raise Core0Error('Number pad actual digit/control source switches differ')
 if '%cmp41 = icmp eq i64 %arg0, 8'not in body or 'br i1 %cmp41, label %if.then.36, label %if.merge.2'not in body:raise Core0Error('Number pad control row lacks its exact dominating row8 guard')
 return ('user',25,['u64']*3,[],list(NUMERIC_COLUMNS))

def numeric_jump_relation(ir,unit,assembly,symbol,table,targets,code,labels):
 from audit_kernel import _jump_assembly_function
 from package_notebook_target import _normalized_jump_code
 numeric_jump_spec(ir,unit,NUMERIC_CHARACTER,symbol)
 if (code,labels)!=_jump_assembly_function(assembly,symbol):raise Core0Error('Number pad relation supplied foreign machine owner')
 rows=re.findall(r'(?m)^'+re.escape(table)+r':\n((?:\s*\.quad\s+\.LBB\d+_\d+\s*\n)+)',assembly)
 if len(rows)!=1 or re.findall(r'\.quad\s+(\.LBB\d+_\d+)',rows[0])!=targets or len(targets)!=25 or any(t not in labels for t in targets):raise Core0Error('Number pad actual table declarations/local cells differ')
 names={r['symbol']:canonical(r['source'])for r in unit['functions']}
 normalized=_normalized_jump_code(code,labels,table,names)
 w=numeric_contract(unit)[1]
 actual=hashlib.sha256(repr(normalized).encode()).hexdigest()
 if actual!=w.get('character_machine_sha256'):raise Core0Error('Number pad complete machine owner/guards/calls differ')
 # The actual RV64 owner checks row8, unsigned(column-3)<=24, scales8,
 # loads the exact table and preloads C=67. Every cell is checked below,
 # including holes; owner hashing alone cannot bind their target mapping.
 expected=[('li',['a2','8']),('bne',['a3','a2','@48']),('addi',['a1','a1','-3']),('li',['a0','24']),('bltu',['a0','a1','@29']),('slli',['a1','a1','3']),('auipc',['a0','%TABLE']),('addi',['a0','a0','%LOW41']),('add',['a0','a1','a0']),('ld',['a1','0(a0)']),('li',['a0','67']),('jr',['a1'])]
 if normalized[35:47]!=expected:raise Core0Error('Number pad row/index/unsigned-bound/load/preload path differs')
 cells=[]
 for index,target in enumerate(targets):
  at=labels[target];value=67
  for op,args in code[at:at+2]:
   if (op,args)==('ret',[]):break
   if op=='li'and len(args)==2 and args[0]=='a0':value=int(args[1])
   else:raise Core0Error('Number pad cell lacks bounded constant return')
  else:raise Core0Error('Number pad cell does not return within two instructions')
  column=index+3;wanted=NUMERIC_COLUMNS.get(column,32)
  if value!=wanted:raise Core0Error('Number pad machine cell differs from authored control: '+str(column))
  cells.append({'column':column,'value':value,'target_instruction':at})
 return {'schema':'lemma-number-pad-backend-cells/1','source':NUMERIC_CHARACTER,'row':8,'unsigned_column_interval':[3,27],'all_cells':cells,'hole_value':32,'machine_sha256':actual}
