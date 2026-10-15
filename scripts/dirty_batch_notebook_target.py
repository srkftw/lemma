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
 found=contract(unit)
 if found is None:return None
 scope,w=found
 from package_companion_target import complete_corpus
 phase='post'if optimized else'pre';actual=complete_corpus(ir,unit,optimized=optimized)
 if len(actual['functions'])!=w[phase+'_function_count']or digest(actual)!=w[phase+'_sha256']:raise Core0Error('Dirty batch complete body/global/caller corpus differs: '+scope+'/'+phase)
 return {'contract_version':'lemma-installed-package-notebook/'+str(w['package_notebook_version']),'artifact_contract_version':COURSE_SAVE_VERSION if course_save(unit) else RESTORED_VERSION if restored(unit) else VERSION,'software_scope':scope,'package_notebook_version':w['package_notebook_version'],'phase':phase,'function_count':len(actual['functions']),'complete_corpus_sha256':digest(actual),'semantics':None if optimized else semantics(ir,unit,scope),'scope':'Complete genuine artifact relation; no CPU/latency/durability claim'}
