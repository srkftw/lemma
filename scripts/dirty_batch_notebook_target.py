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
 a=json.loads(AUTHORITY.read_text())
 if a.get('schema')!=VERSION or set(a.get('deployments',{}))!={'canonical','companion'}:raise Core0Error('Dirty batch complete genuine authority missing')
 w=a['deployments'][scope];configs=CANONICAL if scope=='canonical'else COMPANION;catalogs=w.get('catalog_sha256_by_configuration')
 if not isinstance(catalogs,dict)or set(catalogs)!=set(configs)or catalogs[config]!=digest(unit)or w.get('package_notebook_version')!=9:raise Core0Error('Dirty batch complete typed/effect/root catalog differs')
 names={canonical(r['source'])for r in unit['functions']}
 if not ADDED<=names:raise Core0Error('Dirty batch partial source cohort')
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
 if len(calls(expected,prefix+'pumpRefreshBatched'))!=1:raise Core0Error('Dirty batch missing actual selected loop call')
 if len(calls(prefix+'pumpRefreshBatched',prefix+'uploadDirtyBatch'))!=1:raise Core0Error('Dirty batch missing bounded upload path')
 if len(calls(prefix+'uploadDirtyBatch',MARKER))!=1 or len(calls(prefix+'uploadDirtyBatch',prefix+'consumeDirtyIndexStep'))!=1:raise Core0Error('Dirty batch missing controller/actual-prefix consumption')
 if len(calls('Lemma.Ink.Surface.indexedPrepareStep','Lemma.Ink.Surface.indexedCopyWord'))!=1:raise Core0Error('Dirty batch lost ordinary checked word callback')
 return {'ordinary_package_batch_connected':True,'body_controls':controls(ir,unit,scope),'queue':'same16384-entry FIFO/bitmap; <=4 tiles and actual completed prefix','memory':'same owned Surface-v2 staging page; no allocator/runtime/record change'}
def validate(ir,unit,*,optimized):
 found=contract(unit)
 if found is None:return None
 scope,w=found
 from package_companion_target import complete_corpus
 phase='post'if optimized else'pre';actual=complete_corpus(ir,unit,optimized=optimized)
 if len(actual['functions'])!=w[phase+'_function_count']or digest(actual)!=w[phase+'_sha256']:raise Core0Error('Dirty batch complete body/global/caller corpus differs: '+scope+'/'+phase)
 return {'contract_version':'lemma-installed-package-notebook/9','artifact_contract_version':VERSION,'software_scope':scope,'package_notebook_version':9,'phase':phase,'function_count':len(actual['functions']),'complete_corpus_sha256':digest(actual),'semantics':None if optimized else semantics(ir,unit,scope),'scope':'Complete genuine artifact relation; no CPU/latency/durability claim'}
