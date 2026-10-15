"""Exact ordinary Notebook cohort using aligned course-control spans1.
Historical renderer/artifact cohorts retain their existing independent pins.
"""
import hashlib,json,re
from pathlib import Path
from core0_common import Core0Error
from paper_next import canonical
from package_closure_deployment import CONFIGURATIONS as CANONICAL,SOFTWARE_DEPLOYMENT as CANONICAL_SOFTWARE
from package_companion_deployment import CONFIGURATIONS as COMPANION,SOFTWARE_DEPLOYMENT as COMPANION_SOFTWARE
VERSION='lemma-course-control-notebook-artifact/1'
AUTHORITY=Path(__file__).resolve().parents[1]/'tooling/control-notebook-target-authority.json'
ROOT='Lemma.Courses.ControlRender.'
ADDED=frozenset(ROOT+n for n in ('validGeometry','hexDigit','identityCharacter','character','bytesStep','spanStep','renderControls','renderIdentity'))
REMOVED=frozenset('Lemma.Applications.Notebook.'+n for n in ('packageHex','packageControlCharacter','packageControlByte','packageControlStep','packageIdentityCharacter','packageIdentityStep'))
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def candidate(unit):return any(canonical(r.get('source','')).startswith(ROOT)for r in unit.get('functions',[]))
def contract(unit):
 if not candidate(unit):return None
 config=unit.get('configuration');scope='canonical'if config in CANONICAL else'companion'if config in COMPANION else None
 if scope is None or unit.get('role')!='user'or unit.get('image_key')!='notebook'or unit.get('image_id')!=2:raise Core0Error('Control renderer escaped exact Notebook deployment')
 if unit.get('software_deployment')!=(CANONICAL_SOFTWARE if scope=='canonical'else COMPANION_SOFTWARE):raise Core0Error('Control renderer hardware/software tuple differs')
 a=json.loads(AUTHORITY.read_text())
 if a.get('schema')!=VERSION or set(a.get('deployments',{}))!={'canonical','companion'}:raise Core0Error('Control renderer complete genuine authority missing')
 w=a['deployments'][scope];configs=CANONICAL if scope=='canonical'else COMPANION;catalogs=w.get('catalog_sha256_by_configuration')
 if not isinstance(catalogs,dict)or set(catalogs)!=set(configs)or catalogs[config]!=digest(unit)or w.get('package_notebook_version')!=8:raise Core0Error('Control renderer complete typed/effect/root catalog differs')
 names={canonical(r['source'])for r in unit['functions']}
 if not ADDED<=names or REMOVED&names:raise Core0Error('Control renderer mixed old/new cohort')
 return scope,w

def semantics(ir,unit,scope):
 from audit_kernel import _ir_definition_body
 rows={canonical(r['source']):r for r in unit['functions']}
 for owner,target in [('Lemma.Applications.Notebook.renderPackageControls',ROOT+'renderControls'),('Lemma.Applications.Notebook.renderPackageIdentity',ROOT+'renderIdentity')]:
  body=_ir_definition_body(ir,rows[owner]['symbol'])
  if len(re.findall(r'call \{ i64, i64 \} @'+re.escape(rows[target]['symbol'])+r'\(',body))!=1:raise Core0Error('Notebook omitted actual aligned controls or identity')
 if scope=='companion':
  from package_companion_target import semantic_guards
  semantic_guards(ir,unit)
 return {'ordinary_Notebook_controls_connected':True,'footprint':'384x120, same original row locations/labels/state; actual Action qualification separate'}
def validate(ir,unit,*,optimized):
 found=contract(unit)
 if found is None:return None
 scope,w=found
 from package_companion_target import complete_corpus
 phase='post'if optimized else'pre';actual=complete_corpus(ir,unit,optimized=optimized)
 if len(actual['functions'])!=w[phase+'_function_count']or digest(actual)!=w[phase+'_sha256']:raise Core0Error('Control renderer complete body/global/caller corpus differs: '+scope+'/'+phase)
 return {'contract_version':'lemma-installed-package-notebook/8','artifact_contract_version':VERSION,'software_scope':scope,'package_notebook_version':8,'phase':phase,'function_count':len(actual['functions']),'complete_corpus_sha256':digest(actual),'semantics':None if optimized else semantics(ir,unit,scope),'scope':'Complete genuine artifact relation; no CPU/controller/durability/timing claim'}
