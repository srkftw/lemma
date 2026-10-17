"""Complete checked artifact authority for the ordinary aligned course renderer.
No guest execution, document construction or mathematical result occurs here.
Historical package1..6 and recovery4 artifacts retain their own exact authority.
"""
from pathlib import Path
import json,hashlib,re
from core0_common import Core0Error
from paper_next import canonical
from package_closure_deployment import CONFIGURATIONS as CANONICAL,SOFTWARE_DEPLOYMENT as CANONICAL_SOFTWARE
from package_companion_deployment import CONFIGURATIONS as COMPANION,SOFTWARE_DEPLOYMENT as COMPANION_SOFTWARE
VERSION='lemma-course-aligned-delta-artifact/1'
AUTHORITY=Path(__file__).resolve().parents[1]/'tooling/aligned-notebook-target-authority.json'
ADDED=frozenset('Lemma.Courses.PackageRender.'+n for n in ('alignedDeltaStep','alignedSpanWord','renderAlignedDelta','renderAlignedHeaderSelectedDelta','renderAlignedSelectedDelta'))
REMOVED=frozenset('Lemma.Courses.PackageRender.'+n for n in ('deltaStep','readWord','renderDelta','renderHeaderSelectedDelta','renderSelectedDelta'))
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def candidate(unit):
 from dirty_batch_notebook_target import candidate as dirty_candidate
 if dirty_candidate(unit):return True
 from control_notebook_target import candidate as controls_candidate
 if controls_candidate(unit):return True
 return bool(ADDED & {canonical(r.get('source','')) for r in unit.get('functions',[])})
def contract(unit):
 from dirty_batch_notebook_target import candidate as dirty_candidate,contract as dirty_contract
 if dirty_candidate(unit):return dirty_contract(unit)
 from control_notebook_target import candidate as controls_candidate,contract as controls_contract
 if controls_candidate(unit):return controls_contract(unit)
 if not candidate(unit):return None
 config=unit.get('configuration');scope='canonical' if config in CANONICAL else 'companion' if config in COMPANION else None
 if scope is None or unit.get('role')!='user' or unit.get('image_key')!='notebook' or unit.get('image_id')!=2:raise Core0Error('Aligned renderer escaped its exact Notebook User2 deployment')
 expected=CANONICAL_SOFTWARE if scope=='canonical' else COMPANION_SOFTWARE
 if unit.get('software_deployment')!=expected:raise Core0Error('Aligned renderer hardware/software tuple differs')
 authority=json.loads(AUTHORITY.read_text())
 if authority.get('schema')!=VERSION or set(authority.get('deployments',{}))!={'canonical','companion'}:raise Core0Error('Aligned renderer complete genuine authority missing')
 wanted=authority['deployments'][scope];configs=CANONICAL if scope=='canonical' else COMPANION
 catalogs=wanted.get('catalog_sha256_by_configuration')
 if not isinstance(catalogs,dict) or set(catalogs)!=set(configs) or catalogs[config]!=digest(unit):raise Core0Error('Aligned renderer complete typed/effect/root catalog differs')
 names={canonical(r['source']) for r in unit['functions']}
 if not ADDED<=names or REMOVED & names:raise Core0Error('Aligned renderer mixed/partial old/new source cohort')
 return scope,wanted

def semantics(ir,unit,scope):
 from audit_kernel import _ir_definition_body
 rows={canonical(r['source']):r for r in unit['functions']}
 def body(name):return _ir_definition_body(ir,rows[name]['symbol'])
 def calls(owner,target):return re.findall(r'call \{ i64, i64 \} @'+re.escape(rows[target]['symbol'])+r'\(([^\n]*)\)',body(owner))
 root='Lemma.Courses.PackageRender.';owner='Lemma.Applications.Notebook.renderPackageText'
 for target in ('renderAlignedSelectedDelta','renderAlignedHeaderSelectedDelta'):
  if len(calls(owner,root+target))!=1:raise Core0Error('Notebook omitted its actual selected aligned renderer')
 for owner in ('renderAlignedSelectedDelta','renderAlignedHeaderSelectedDelta'):
  if len(calls(root+owner,root+'renderAlignedDelta'))!=1:raise Core0Error('Aligned selection omitted real framebuffer renderer')
 # Complete preserved body/caller/global hashes are load-bearing below. These
 # explicit call checks separately connect that corpus to the ordinary UI.
 if scope=='companion':
  from package_companion_target import semantic_guards
  semantic_guards(ir,unit)
 return {'ordinary_Notebook_entry_connected':True,'same_384x320_Gray4_footprint':'qualified separately by real Action/scalar comparison','scope':'source/IR authority, not controller execution'}

def validate(ir,unit,*,optimized):
 from dirty_batch_notebook_target import candidate as dirty_candidate,validate as dirty_validate
 if dirty_candidate(unit):return dirty_validate(ir,unit,optimized=optimized)
 from control_notebook_target import candidate as controls_candidate,validate as controls_validate
 if controls_candidate(unit):return controls_validate(ir,unit,optimized=optimized)
 found=contract(unit)
 if found is None:return None
 scope,wanted=found
 from package_companion_target import complete_corpus
 phase='post' if optimized else 'pre';actual=complete_corpus(ir,unit,optimized=optimized)
 if len(actual['functions'])!=wanted[phase+'_function_count'] or digest(actual)!=wanted[phase+'_sha256']:raise Core0Error('Aligned renderer complete body/global/caller corpus differs: '+scope+'/'+phase)
 return {'contract_version':'lemma-installed-package-notebook/7','artifact_contract_version':VERSION,'software_scope':scope,'package_notebook_version':7,'phase':phase,'function_count':len(actual['functions']),'complete_corpus_sha256':digest(actual),'semantics':None if optimized else semantics(ir,unit,scope),'scope':'Complete genuine artifact relation; no CPU/durability/timing claim'}
