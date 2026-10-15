"""Strict real same-Action entry authority, never a target interpreter.
Complete pins derive from genuine ordinary selected role exports; exact boot
arguments and incoming callers keep this borrow private. Historical configurations
retain their original route. Linked execution and cycle gains remain separate.
"""
import hashlib,re
from core0_common import Core0Error
from surface_bulk_borrow import normalized_body
from paper_next import canonical
SIGNATURES={'Lemma.Kernel.Task.entryContextV2': (['u64'], ['checked-access', 'physical-read', 'physical-write']), 'Lemma.Kernel.Task.entryDispatchesV2': (['u64'], ['checked-access', 'physical-read']), 'Lemma.Kernel.Scheduler.entryV2': (['u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'privilege-transition']), 'Lemma.Kernel.Scheduler.stepEntryV2': ([], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'interrupt-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'privilege-transition', 'wait-state']), 'Lemma.Kernel.Task.lookupRecord': (['u64'], ['checked-access', 'physical-read']), 'Lemma.Kernel.Task.findStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read']), 'Lemma.Kernel.Task.table': ([], ['checked-access', 'physical-read']), 'Lemma.Kernel.Task.failed': (['u8'], []), 'Lemma.Kernel.Scheduler.failed': (['u8'], []), 'Lemma.Kernel.Memory.AddressSpace.base': (['u64'], ['checked-access', 'physical-read']), 'Lemma.Kernel.Memory.AddressSpace.validateRegistry': (['u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read']), 'Lemma.Kernel.Memory.AddressSpace.validateRegistryStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read']), 'Lemma.Kernel.Memory.AddressSpace.validateRegistryGenericStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read']), 'Lemma.Kernel.Memory.Frames.resolvePurpose': (['u64', 'u64', 'u64'], ['checked-access', 'physical-read']), 'Lemma.Kernel.Memory.Frames.resolve': (['u64', 'u64'], ['checked-access', 'physical-read']), 'Lemma.Kernel.Memory.Frames.resolveValid': (['u64', 'u64'], []), 'Lemma.Kernel.Memory.Frames.runtimeCount': ([], ['checked-access', 'physical-read']), 'Lemma.Kernel.Process.validateStackAt': (['u64'], ['checked-access', 'physical-read']), 'Lemma.Kernel.Loader.validateExpandedStackAt': (['u64'], ['checked-access', 'physical-read'])}
PINS={'pre': {'Lemma.Kernel.Task.entryContextV2': '829f8289ccab93ff2b3b1360e6d558300bf6bc0eaa821a737544c0c88d3a166a', 'Lemma.Kernel.Task.entryDispatchesV2': '5b64fc73b786c209e61fd8e8bcf917bd7e20155e53b6e334dcd5d6398338b108', 'Lemma.Kernel.Scheduler.entryV2': '00a0d3367b4d90d3702821ee8f29bd4cb1eefc6888310e23b8a08b5d19ef09eb', 'Lemma.Kernel.Scheduler.stepEntryV2': '845402d0d60ab2567c62a61a1cb95826fc807a25d3bc079eab56689a52ac69ec', 'Lemma.Kernel.Task.lookupRecord': 'c37a6226e4724171df44737aaef87a59cbd4165048ecdaf86950dbc80628cf1e', 'Lemma.Kernel.Task.findStep': '9670f690a926604dab388501d947d87b6b86e0d5d99792f1430f8efe5dc459a8', 'Lemma.Kernel.Task.table': 'd0d37ff63270ceff9db8c88bf1ee97e946b9c59083d4c0844137de3427e5ac2d', 'Lemma.Kernel.Task.failed': '020d096e7004ebd3fec13c5b6288a9795d58ea44b24c70d88cdd69273f72c288', 'Lemma.Kernel.Scheduler.failed': '020d096e7004ebd3fec13c5b6288a9795d58ea44b24c70d88cdd69273f72c288', 'Lemma.Kernel.Memory.AddressSpace.base': '4036fb8f591d05541c064b11aa8d2da086d7e6cdea80ed674091303339537f73', 'Lemma.Kernel.Memory.AddressSpace.validateRegistry': 'bb0f45abc4cf1566e3046d3371226ad6f1cf7af7b37e6808aefd7b54915a7c69', 'Lemma.Kernel.Memory.AddressSpace.validateRegistryStep': 'cdc16aa4742c04f17bc813d4e97b38e8903bab7e35cab4cff9a48fd5836f28fa', 'Lemma.Kernel.Memory.AddressSpace.validateRegistryGenericStep': '19131713ad9c17bf6f62b7fc483e0f558502efebcea3610bfcd3651559113973', 'Lemma.Kernel.Memory.Frames.resolvePurpose': '99dc881018d7a6e94ee4fc7f76f9d4102edca366dd3ab7d29a1e88f2c81cbb3a', 'Lemma.Kernel.Memory.Frames.resolve': '0a4a0fcfe8e2c57bbd250a7438f43e7dddbed03f58f9fd912a3e6cad75dc0dc6', 'Lemma.Kernel.Memory.Frames.resolveValid': 'afbd96535432465428e2aa10da37e5ef3ac50a4e5b120c88c782438a70e5149d', 'Lemma.Kernel.Memory.Frames.runtimeCount': 'b7d0ef58121b169dcb18934f75a6a2ec18f0ffce8b0d5f7ee7cfbe157b9ec47f', 'Lemma.Kernel.Process.validateStackAt': '1239a29f98a78b96d30c1a60d852e7f839a2f59c9da32a61edd02404fdf50afa', 'Lemma.Kernel.Loader.validateExpandedStackAt': '576b4bbeb29f9b4e780f31c41cfd1f6f5271c4c71dbdf841128a5ebfcd872647'}, 'post': {'Lemma.Kernel.Task.entryContextV2': '7ddf56cb603098ecc13d3453d6e7e98df9db6df71103fca867604b55acd0f30b', 'Lemma.Kernel.Task.entryDispatchesV2': 'ec1bd26b4a7d669ef2256d6c83b499dd84918c377c823f931526144429e4c3eb', 'Lemma.Kernel.Scheduler.entryV2': 'f2eb01155fe408908103e1a4ec874adf18795dc6c1e6670fc8dfa56972a5c4ca', 'Lemma.Kernel.Scheduler.stepEntryV2': 'dc82706f68dede583c31bbd2a1f4c58c5f0764b335047935755d1dd2123829da', 'Lemma.Kernel.Task.lookupRecord': '82d7eabfc77960b648d9d8e1c09ee964e7f92baba3990e62a6e505c2b6263178', 'Lemma.Kernel.Task.findStep': 'd78de699434554571f0caffd9f3ba898e601eef5da9f2fc6d547939e290f1736', 'Lemma.Kernel.Task.table': '623369ed3d6a3eae64f8962cccba326ea9870cb5152de72ea710d91d95f2d48b', 'Lemma.Kernel.Task.failed': 'e28625dd8e778884a50467a8a413b3b0b3b06f160a6efbe788235d7b5b325b8e', 'Lemma.Kernel.Scheduler.failed': 'e28625dd8e778884a50467a8a413b3b0b3b06f160a6efbe788235d7b5b325b8e', 'Lemma.Kernel.Memory.AddressSpace.base': 'd5563c74bf564f2eb3f2dcdebebef7948a6c19fd296a64281f8225c65ab1528a', 'Lemma.Kernel.Memory.AddressSpace.validateRegistry': 'c247c2e5a630c4e1e37be1a059ee59c52fb79df9f66f97dcb81407eb9041b60d', 'Lemma.Kernel.Memory.AddressSpace.validateRegistryStep': '6e1eee90b2bf62b4f6f4fea90fbe8a7aca0aa3a459cf9c1003c5d6cfc9471f8d', 'Lemma.Kernel.Memory.AddressSpace.validateRegistryGenericStep': '044dc484ba9a880335007e1040d3dfe11ef241e4c18b9d00affb102e6503ddab', 'Lemma.Kernel.Memory.Frames.resolvePurpose': 'a830c7e0ba8b4e594a068fa4a2b1976fa69cdc4d39d5e2a44760ce7c8161f576', 'Lemma.Kernel.Memory.Frames.resolve': '5991c4ca195e4496e85de50cb99ef04c215a0936fd650b27ea0dfa6c9f07c797', 'Lemma.Kernel.Memory.Frames.resolveValid': '2403faf8f2ade4100f0a8fc7cb78de149bcec085aa6072827c3881f49eb36d50', 'Lemma.Kernel.Memory.Frames.runtimeCount': 'fe5e1ecb964cfbd18e1bf6301c2716d52324bff2a4f54defe33389826d980c67', 'Lemma.Kernel.Process.validateStackAt': '2645d330d094be976b94cdb9143491d9d0185266cc9ac360da64c39b5f98bafe', 'Lemma.Kernel.Loader.validateExpandedStackAt': 'e7f88b0a00ed0c99fa8d1e0e3b196d471052e5fb80221a44ba03f3530007f1a1'}}

FAMILY=('Lemma.Kernel.Task.entryContextV2','Lemma.Kernel.Task.entryDispatchesV2',
        'Lemma.Kernel.Scheduler.entryV2','Lemma.Kernel.Scheduler.stepEntryV2')
REGISTRY_BORROW_SOURCES=('Lemma.Kernel.Memory.Frames.resolveRegistry8192',
 'Lemma.Kernel.Memory.AddressSpace.validateRegistry8192Step')
REGISTRY_BORROW_PINS={
 'pre':{REGISTRY_BORROW_SOURCES[0]:'a9deee61033f7f1004b712ed52398605eea30b4b360e3be19d8575d3b8577f7f',
        REGISTRY_BORROW_SOURCES[1]:'8725124868881a1f08537416a2f42bf1d6708bd072ee3a323e6c4243220f5fff',
        'Lemma.Kernel.Memory.AddressSpace.validateRegistry':'65965736fb73d436a8d25b5a80a55a94b5e6c07982ce9339b73981e33c14864b'},
 'post':{REGISTRY_BORROW_SOURCES[0]:'500cc4d7998f92d1d522e1c93feedd6ef97469e5bef21eb23efd7a251145b798',
         REGISTRY_BORROW_SOURCES[1]:'9ba1dd9537b982a913480f8c02593ccb9b7d8203c7b6e2706adc004bedc8d40b',
         'Lemma.Kernel.Memory.AddressSpace.validateRegistry':'1671c9c7515be795b9625fd124872691a19fcb665f1f357de382214ec4aebc02'}}

def validate_registry_borrow(ir,rows,names,phase):
 """A complete genuine count-borrow cohort; old artifacts keep their old pins."""
 from audit_kernel import _ir_definition_body,_local_call_arguments
 present=set(REGISTRY_BORROW_SOURCES)&set(rows)
 if not present:return {}
 require(present==set(REGISTRY_BORROW_SOURCES),'partial owned registry-count borrow family')
 for source,args in zip(REGISTRY_BORROW_SOURCES,(['u64']*2,['u32']*2+['u64']*5)):
  row=rows[source];require(row['args']==args and row['effects']==['checked-access','physical-read'],
      'registry-count borrow changed signature or acquired mutation effects')
  body=_ir_definition_body(ir,row['symbol'])
  require(body is not None and hashlib.sha256(normalized_body(body,names).encode()).hexdigest()==REGISTRY_BORROW_PINS[phase][source],
      'complete owned registry-count body differs: '+source+'/'+phase)
 for target,caller in zip(REGISTRY_BORROW_SOURCES,(REGISTRY_BORROW_SOURCES[1],
                         'Lemma.Kernel.Memory.AddressSpace.validateRegistry')):
  incoming={source for source,row in rows.items()
            if _local_call_arguments(_ir_definition_body(ir,row['symbol']),rows[target]['symbol'])}
  require(incoming=={caller},'owned registry-count borrow acquired another/missing caller')
 return {'contract_version':'lemma-owned-registry-count-borrow-v1','body_count':3,
         'count_authority':'fresh runtimeCount=8192 in the same protected Action',
         'live_checks':'per-frame owner/generation/purpose, recorded physical, duplicates and pins'}
CONFIGURATIONS={'lemmasim-silicon-closure-entry2-bulk-notebook':'Lemma.Platform.LemmaSim.NotebookKernel.siliconClosureEntry2Boot',
 'lemmasim-silicon-closure-entry2-bulk-initialize':'Lemma.Platform.LemmaSim.NotebookKernel.siliconClosureEntry2InitializeMedium'}
BOOT_SIGNATURES={'Lemma.Platform.LemmaSim.NotebookKernel.powerStepEntryV2': ([], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'interrupt-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'privilege-transition', 'wait-state']), 'Lemma.Platform.LemmaSim.NotebookKernel.bootSelectedEntryV2': (['u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'interrupt-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'instruction-sync', 'privilege-transition', 'wait-state', 'may-diverge']), 'Lemma.Platform.LemmaSim.NotebookKernel.siliconClosureEntry2Boot': ([], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'interrupt-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'instruction-sync', 'privilege-transition', 'wait-state', 'may-diverge']), 'Lemma.Platform.LemmaSim.NotebookKernel.siliconClosureEntry2InitializeMedium': ([], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'interrupt-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'instruction-sync', 'privilege-transition', 'wait-state', 'may-diverge'])}
BOOT_PINS={'pre': {'Lemma.Platform.LemmaSim.NotebookKernel.powerStepEntryV2': '1b662c233aa336337d7625e7da1d2ed78e2d69b8353574e005ad020cc4f619bb', 'Lemma.Platform.LemmaSim.NotebookKernel.bootSelectedEntryV2': '2eac08fff51e17065ddb1afe6ea2e99ab8eb7c8137f9cf2ded0cf6b7b70b9373', 'Lemma.Platform.LemmaSim.NotebookKernel.siliconClosureEntry2Boot': '73253f81650747eb8e104e4619f654d6f8b4540a23ab606a1cf43f71b3edf3b2', 'Lemma.Platform.LemmaSim.NotebookKernel.siliconClosureEntry2InitializeMedium': '8e9f658fb1425f44871b9e53082203fa732a1aab384cef10e3fbe7ac05f4880d'}, 'post': {'Lemma.Platform.LemmaSim.NotebookKernel.powerStepEntryV2': '11f44a257e3d88c586bd2973397d482f5f79823a39ba7665e0e104087d47a5ad', 'Lemma.Platform.LemmaSim.NotebookKernel.bootSelectedEntryV2': '5249284d45bcb46fe54257a5fbfa17f2110a0f6186c65bb215b9c25c9add61e7', 'Lemma.Platform.LemmaSim.NotebookKernel.siliconClosureEntry2Boot': '80f45ce263a79a1cf1131dfc9f574585e0dc9c53c09caff9b3eeb8c64b689fad', 'Lemma.Platform.LemmaSim.NotebookKernel.siliconClosureEntry2InitializeMedium': '78a33395d2799d2da08e33357929dbc8adf98e1f093ab4d2b722fd3a11e56aa5'}}
BOOT_FAMILY=set(BOOT_SIGNATURES)
from package_closure_deployment import (CONFIGURATIONS as PACKAGE_CONFIGURATIONS,
 SOFTWARE_DEPLOYMENT as PACKAGE_SOFTWARE_DEPLOYMENT, BOOT_ROOTS as PACKAGE_BOOT_ROOTS)
CONFIGURATIONS.update({c:'Lemma.Platform.LemmaSim.NotebookKernel.'+root for c,root in PACKAGE_BOOT_ROOTS.items()})
PACKAGE_BOOT='Lemma.Platform.LemmaSim.NotebookKernel.bootCourseSelectedEntryV2'
PACKAGE_SIGNATURES={PACKAGE_BOOT:BOOT_SIGNATURES['Lemma.Platform.LemmaSim.NotebookKernel.bootSelectedEntryV2'],
 **{CONFIGURATIONS[c]:BOOT_SIGNATURES['Lemma.Platform.LemmaSim.NotebookKernel.siliconClosureEntry2Boot'] for c in PACKAGE_CONFIGURATIONS}}
BOOT_SIGNATURES.update(PACKAGE_SIGNATURES)
BOOT_FAMILY.update(PACKAGE_SIGNATURES)
# Separately inspected genuine selected normal/initializer Kernel4 exports.
# Both roles retain the19 original entry bodies and the exact power loop;
# their new boot invokes constructCourse with unchanged checked operands.
PACKAGE_BOOT_PINS={
 'pre':{PACKAGE_BOOT:'e80cb1a1e9ace7819254201cac7d2ea7cbbc8b1fbb98cfee498e74d973ca599d',
  'Lemma.Platform.LemmaSim.NotebookKernel.siliconPackageClosureEntry2Boot':'07dd441f69c7c58c2cc6896040bfc1b28c84b39e355c10507e928a1c4bec445c',
  'Lemma.Platform.LemmaSim.NotebookKernel.siliconPackageClosureEntry2InitializeMedium':'71510a49ba5878be2e0e5bb5f639ae24f8b58a37d2e6a3b5075c253c79299932'},
 'post':{PACKAGE_BOOT:'b290c168de9d3c49efc2a05a5ae18d8c507e0b96d0115d9587483cd74e7af59a',
  'Lemma.Platform.LemmaSim.NotebookKernel.siliconPackageClosureEntry2Boot':'aba981d00fe617fc91b648e63de4e3cb28eddc5cbf2a17fc55b7906f16a22622',
  'Lemma.Platform.LemmaSim.NotebookKernel.siliconPackageClosureEntry2InitializeMedium':'318c94308281be376c69585bb2cd1ec56328a0d0970e9bf7f56add9e5f2bcb1b'}}

def boot_source(configuration):
 return PACKAGE_BOOT if configuration in PACKAGE_CONFIGURATIONS else 'Lemma.Platform.LemmaSim.NotebookKernel.bootSelectedEntryV2'

def require(ok,message):
 if not ok:raise Core0Error(message)

def checked_entry_data_flow(body,rows,*,optimized):
 from audit_kernel import _local_call_arguments,_local_checked_result,validate_failed_call_gate,_ir_definition_body,validate_boolean_gate,validate_call_precedes
 context=rows[FAMILY[0]]['symbol'];dispatch=rows[FAMILY[1]]['symbol']
 require(_local_call_arguments(body,context)==['i64 %arg0'] and _local_call_arguments(body,dispatch)==['i64 %arg0'],
         'Entry2 original descriptor operands/call count differ')
 result=_local_checked_result(body,context,"i64 %arg0")
 require(result is not None,'Entry2 checked context result missing')
 # Extract the genuine returned context SSA value, never a caller integer.
 call=re.search(r'(%[-\w.]+) = call \{ i64, i64 \} @'+re.escape(context)+r'\(i64 %arg0\)',body)
 require(call is not None,'Entry2 original complete context call absent')
 value=re.search(r'(%[-\w.]+) = extractvalue \{ i64, i64 \} '+re.escape(call[1])+r', 1',body)
 require(value is not None,'Entry2 source-derived context value missing')
 ctx=value[1]
 failed=rows['Lemma.Kernel.Scheduler.failed']['symbol']
 failedbody=rows['_genuine_ir']['ir']
 if optimized:
  helper=_ir_definition_body(failedbody,failed)
  require(re.fullmatch(r'\s*entry:\s*%cmp0 = icmp ne i8 %arg0, 0\s*ret i1 %cmp0\s*',helper) is not None,
          'Entry2 optimized exact nonzero failure scalar differs')
  status=re.search(r'(%[-\w.]+) = extractvalue \{ i64, i64 \} '+re.escape(call[1])+r', 0',body)
  require(status is not None,'Entry2 original status extraction missing')
  narrow=re.search(r'(%[-\w.]+) = trunc(?: nuw)?(?: nsw)? i64 '+re.escape(status[1])+r' to i8',body)
  require(narrow is not None,'Entry2 original status narrowing missing')
  failed_call=re.search(r'(%[-\w.]+) = call zeroext i1 @'+re.escape(failed)+r'\(i8 zeroext '+re.escape(narrow[1])+r'\)',body)
  require(failed_call is not None,'Entry2 failure scalar substituted context status')
  # CFG parsing removes only LLVM comments, including optimizer predecessor
  # annotations; all instructions, operands, labels and edges stay literal.
  cfg_body='\n'.join(line.split(';',1)[0] for line in body.splitlines())
  status_gate=validate_boolean_gate(cfg_body,failed_call[1],dispatch,success_when_true=False)
  validate_call_precedes(body,context,dispatch)
 else:
  status_gate=validate_failed_call_gate(body,context,dispatch,failed,
     _ir_definition_body(failedbody,failed))
 if optimized:
  root=re.search(r'(%[-\w.]+) = add(?: nsw)? i64 '+re.escape(ctx)+r', -1984\b',body)
  require(root is not None,'Entry2 exact descriptor-root address from checked context differs')
  pointer=re.search(r'(%[-\w.]+) = inttoptr i64 '+re.escape(root[1])+r' to ptr',body)
  require(pointer is not None,'Entry2 root pointer correspondence differs')
  loaded=re.search(r'(%[-\w.]+) = load volatile i64, ptr '+re.escape(pointer[1])+r', align 8',body)
  require(loaded is not None,'Entry2 original checked volatile root read absent')
  entry=re.search(r'call i64 @lemma_exec_enter_user\(i64 '+re.escape(ctx)+r'\)',body)
  require(entry is not None,'Entry2 typed U-entry substituted its checked context')
  after=body[entry.end():]
  require(re.search(re.escape(ctx)+r'(?![-\w.])',after) is None,
          'Entry2 borrowed context escapes typed U-entry boundary')
  # The returned root word can occur only before entry. The post-entry root is
  # independently loaded from fixed kernel state, as in the legacy continuation.
  require(re.search(re.escape(loaded[1])+r'(?![-\w.])',after) is None,
          'Entry2 borrowed root escapes typed U-entry boundary')
 return {'checked_context':ctx,'root_offset_from_context':-1984,'borrow_ends':'before typed enterUser'}

def validate_component(ir,unit,*,optimized):
 from audit_kernel import _ir_definition_body,_local_call_arguments
 require(unit.get('role')=='kernel' and unit.get('contract_version',unit.get('profile'))=='core0-kernel-v0.4',
         'Entry2 borrowed authority escaped Kernel4')
 entries=unit.get('functions',[]);rows={canonical(x['source']):x for x in entries}
 require(len(rows)==len(entries) and set(SIGNATURES)<=set(rows),'Entry2 complete authority family missing/duplicated')
 names={x['symbol']:s for s,x in rows.items()};require(len(names)==len(rows),'Entry2 duplicate symbols')
 phase='post' if optimized else 'pre';bodies={}
 registry=validate_registry_borrow(ir,rows,names,phase)
 for source,(args,effects) in SIGNATURES.items():
  require(rows[source]['args']==args and rows[source]['effects']==effects,'Entry2 exact signature/effects differ')
  body=_ir_definition_body(ir,rows[source]['symbol']);require(body is not None,'Entry2 actual body missing')
  expected=REGISTRY_BORROW_PINS[phase].get(source,PINS[phase][source]) if registry else PINS[phase][source]
  require(hashlib.sha256(normalized_body(body,names).encode()).hexdigest()==expected,
          'Entry2 complete original checked body differs: '+source+'/'+phase);bodies[source]=body
 for target,caller in zip(FAMILY[:3],(FAMILY[2],FAMILY[2],FAMILY[3])):
  incoming=set()
  for source,row in rows.items():
   body=_ir_definition_body(ir,row['symbol']);require(body is not None,'Entry2 actual caller body absent')
   if _local_call_arguments(body,rows[target]['symbol']):incoming.add(source)
  require(incoming=={caller},'Entry2 borrowed authority acquired another/missing caller')
 for source in FAMILY[:2]:
  b=bodies[source]
  require(_local_call_arguments(b,rows['Lemma.Kernel.Task.lookupRecord']['symbol'])==['i64 %arg0'],
          'Entry2 original task-record lookup operand/count differs')
 basecalls=_local_call_arguments(bodies[FAMILY[0]],rows['Lemma.Kernel.Memory.AddressSpace.base']['symbol'])
 require(basecalls==['i64 %arg0'],'Entry2 first complete descriptor validation absent/duplicated/substituted')
 require(not _local_call_arguments(bodies[FAMILY[1]],rows['Lemma.Kernel.Memory.AddressSpace.base']['symbol']),
         'Entry2 dispatch helper reacquired descriptor instead of local authority')
 gate_rows=dict(rows);gate_rows['_genuine_ir']={'ir':ir}
 flow=checked_entry_data_flow(bodies[FAMILY[2]],gate_rows,optimized=optimized)
 return {'contract_version':'lemma-scheduler-entry-borrow-v2','body_count':len(SIGNATURES),'phase':phase,'data_flow':flow,
         **({'registry_count_borrow':registry} if registry else {}),
         'scope':'Component only; actual production boot/cfg admission separately required'}

def validate_if_present(ir,unit,*,optimized):
 sources={canonical(row.get('source','')) for row in unit.get('functions',[])}
 selected=unit.get('role')=='kernel' and unit.get('configuration') in CONFIGURATIONS
 if not selected and not sources.intersection(set(FAMILY)|BOOT_FAMILY):return None
 require(selected and unit.get('contract_version')=='core0-kernel-v0.4' and unit.get('schema_version')==1 and
         unit.get('managed_policy')=='lemma-notebook-arithmetic-v1' and unit.get('artifact_category')=='development-kernel-unit',
         'Entry2 exact selected configuration/profile/metadata authority differs')
 from closure_deployment import ENTRY2_SOFTWARE_DEPLOYMENT
 deployment=PACKAGE_SOFTWARE_DEPLOYMENT if unit.get('configuration') in PACKAGE_CONFIGURATIONS else ENTRY2_SOFTWARE_DEPLOYMENT
 require(unit.get('software_deployment')==deployment,
         'Entry2 exact software/hardware/user profile tuple differs')
 require([(canonical(x['source']),x['id'],x['args']) for x in unit.get('roots',[])]==
         [(CONFIGURATIONS[unit['configuration']],1,[]),('Lemma.Platform.LemmaSim.NotebookKernel.dispatchBulk',2,['u64']*3)],
         'Entry2 selected root/caller pair differs')
 component=validate_component(ir,unit,optimized=optimized)
 boot=validate_boot(ir,unit,optimized=optimized)
 return {**component,'selected_configuration':unit['configuration'],'boot':boot,
         'scope':'Actual selected complete entry/boot bodies and exhaustive incoming authority; no linked image, connected execution or cycle gain claim'}


def validate_boot_operations(ir,unit):
 from audit_kernel import _ir_definition_body,_local_call_arguments
 rows={canonical(row['source']):row for row in unit['functions']}
 root=CONFIGURATIONS[unit['configuration']]
 boot=boot_source(unit['configuration'])
 power='Lemma.Platform.LemmaSim.NotebookKernel.powerStepEntryV2'
 step=FAMILY[3]
 needed={root,boot,power,step}
 require(needed<=rows.keys(),'Entry2 boot operation closure missing')
 def calls(owner,target):
  return _local_call_arguments(_ir_definition_body(ir,rows[owner]['symbol']),rows[target]['symbol'])
 mode=int(unit['configuration'].endswith('-initialize'))
 require(calls(root,boot)==['i64 '+str(mode)+', i64 0, i64 3, i64 0'],
         'Entry2 exact initialization/isolation/hardware/arithmetic root operands differ')
 require(calls(power,step)==[''] and calls(boot,power)==[''],
         'Entry2 actual scheduler/power loop operand/count differs')
 if unit['configuration'] in PACKAGE_CONFIGURATIONS:
  constructor='Lemma.Platform.LemmaSim.NotebookKernel.constructCourse'
  require(constructor in rows and calls(boot,constructor)==['i64 %arg0, i64 %arg1, i64 %arg2, i64 %arg3'],
          'Package Entry2 four-role construction operands/count differ')
 return {'initialization':mode,'isolation':0,'binding':3,'arithmetic_mode':0,
         'typed_entry':'single privately checked Task/Scheduler Action','no_cross_syscall_cache':True}


def validate_boot(ir,unit,*,optimized):
 from audit_kernel import _ir_definition_body,_local_call_arguments
 entries=unit['functions'];rows={canonical(row['source']):row for row in entries}
 require(len(rows)==len(entries),'Entry2 selected duplicate source inventory')
 root=CONFIGURATIONS[unit['configuration']]
 selected_boot=boot_source(unit['configuration'])
 common={selected_boot,
         'Lemma.Platform.LemmaSim.NotebookKernel.powerStepEntryV2'}
 expected=common|{root}
 require(BOOT_FAMILY & set(rows)==expected,'Entry2 selected boot family missing/foreign sibling')
 names={row['symbol']:source for source,row in rows.items()}
 require(len(names)==len(rows),'Entry2 selected duplicate symbol inventory')
 phase='post' if optimized else 'pre'
 observed={}
 for source in sorted(expected):
  arguments,effects=BOOT_SIGNATURES[source];row=rows[source]
  require(row['args']==arguments and row['effects']==effects,'Entry2 exact boot signature/effects differ')
  body=_ir_definition_body(ir,row['symbol']);require(body is not None,'Entry2 actual selected boot body absent')
  digest=hashlib.sha256(normalized_body(body,names).encode()).hexdigest()
  pins=PACKAGE_BOOT_PINS[phase] if source in PACKAGE_SIGNATURES else BOOT_PINS[phase]
  require(digest==pins.get(source),'Entry2 complete selected boot body differs: '+source+'/'+phase)
  observed[source]=digest
 callers={FAMILY[3]:{'Lemma.Platform.LemmaSim.NotebookKernel.powerStepEntryV2'},
          'Lemma.Platform.LemmaSim.NotebookKernel.powerStepEntryV2':{selected_boot},
          selected_boot:{root},root:set()}
 actual={target:set() for target in callers}
 for source,row in rows.items():
  body=_ir_definition_body(ir,row['symbol']);require(body is not None,'Entry2 selected actual caller body absent')
  for target in actual:
   if _local_call_arguments(body,rows[target]['symbol']):actual[target].add(source)
 require(actual==callers,'Entry2 selected borrowed entry/boot incoming closure differs')
 operations=validate_boot_operations(ir,unit)
 return {'complete_shapes':observed,'incoming':{s:sorted(v) for s,v in actual.items()},'operations':operations}
