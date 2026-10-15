"""Closed artifact authority for the versioned owned-page Surface-v2 ABI.

The whole pre-LLVM bodies bind independently observed literal Action semantics,
including authorization, complete-copy preflight, all-tile validation, fresh
owner/generation/purpose checks and exact PIO/error prefixes. They do not prove
compiler correctness or establish actual notebook execution/performance.
"""
import hashlib
from course_deployment import CONFIGURATIONS as COURSE_CONFIGURATIONS
from closure_deployment import KERNEL_CONFIGURATIONS as CLOSURE_CONFIGURATIONS
from package_closure_deployment import CONFIGURATIONS as PACKAGE_CONFIGURATIONS
import re
from core0_common import Core0Error
CONFIGURATIONS=frozenset({'lemmasim-silicon-bulk-notebook',
 'lemmasim-silicon-bulk-initialize','lemmasim-silicon-product-bulk-notebook',
 'lemmasim-silicon-usb-bulk-notebook','lemmasim-silicon-usb-bulk-initialize',
 'lemmasim-silicon-bytes-bulk-notebook','lemmasim-silicon-bytes-bulk-initialize',
 'lemmasim-silicon-bytes-arithmetic-oom-development'})
ARRAY=frozenset(COURSE_CONFIGURATIONS) | frozenset({"lemmasim-silicon-array-bulk-notebook","lemmasim-silicon-array-bulk-initialize","lemmasim-silicon-array-arithmetic-oom-development"})
NEXT_CONFIGURATIONS=frozenset(('lemmasim-silicon-usb-next-bulk-notebook','lemmasim-silicon-usb-next-bulk-initialize','lemmasim-silicon-product-next-bulk-notebook'))
WIRE_CONFIGURATIONS=frozenset(('lemmasim-silicon-usb-wire-bulk-notebook','lemmasim-silicon-usb-wire-bulk-initialize'))
CONFIGURATIONS |= WIRE_CONFIGURATIONS
EXECUTED_CONFIGURATION='lemmasim-silicon-product-executed-bulk-notebook'
CONFIGURATIONS |= frozenset(CLOSURE_CONFIGURATIONS) | ARRAY | NEXT_CONFIGURATIONS | {EXECUTED_CONFIGURATION}
PRODUCT='lemmasim-silicon-product-bulk-notebook'
USB=frozenset({'lemmasim-silicon-usb-bulk-notebook','lemmasim-silicon-usb-bulk-initialize'})
BYTES=frozenset({'lemmasim-silicon-bytes-bulk-notebook','lemmasim-silicon-bytes-bulk-initialize','lemmasim-silicon-bytes-arithmetic-oom-development'})
EXPECTED = {'kernel': {'Lemma.Platform.LemmaSim.DeviceService.surfaceV2': '9c6ba9ebb6e401bd0db9d6cc8fd56d2664c123564ca93d40dc9e1dcd93c58e7a',
            'Lemma.Platform.LemmaSim.DeviceService.uploadBulk': '5d094795f8ae9b8c72e2e4b6c725fbb9d7ad19aa3306e1dd00458ed6bbaf2685',
            'Lemma.Platform.LemmaSim.DeviceService.bulkValidateStep': '75d9fb2fdc1b137eeb0f5ad628327357edd070089eab48cc96e7a45b8764b520',
            'Lemma.Platform.LemmaSim.DeviceService.bulkUploadStep': '4929036a917951f1dd84f53625c6ed1cef99046506d766ef40129bb1709838b0',
            'Lemma.Drivers.Paper.uploadOffset': '82309cc888fb0e60477b00352e6b5aec4136a71f7542bb44ef51c8e8d7a3dd02',
            'Lemma.Platform.LemmaSim.NotebookKernel.deviceCallBulk': 'f1955aa248875a725c42e9ce8eb59491b9b36b39a50d63323486f4133cf08c0e',
            'Lemma.Platform.LemmaSim.NotebookKernel.dispatchBulk': '5742297b8145f66c15dbec8536057b4bc5ff928c20fa16354921d0be25cd54c5',
            'Lemma.Platform.LemmaSim.NotebookKernel.deviceCallModernBulk': 'd28ffbe6264d914a10f7366d92b71d1bd9ae6ca69de47a38b562140150fbbf15',
            'Lemma.Platform.LemmaSim.NotebookKernel.dispatchModernBulk': 'ccd686e0e87e2a414a46f4c5e202efdc71d48f1ef14debbf78ec5065e624459b',
            'Lemma.Platform.LemmaSim.NotebookKernel.dispatchProductBulk': 'adebcc9ad123b47bfe4a86a85ac484e1edf2fd028899b057df0677a3838773fa',
            'Lemma.Platform.LemmaSim.NotebookKernel.dispatchUSBBulk': 'a6edafd1df1633aed203d8eb8be9ff915122d526473f6cd897c3cdb2280620b8'},
 'user': {'Lemma.Ink.Surface.allocateBulk': '6a2506e89ec1a74c323ba421320e9d6031a87dc43d7af9fac844d111a0538105',
          'Lemma.Ink.Surface.bulkCopyWord': 'ce5e1f87129239e65a8e53d1ee70453e9caf2e524b466eaa907adfd5806bf286',
          'Lemma.Ink.Surface.bulkPrepareStep': 'd1040f79b4cef3800f033542cec949f587ec5921e03422281e234a9f18402d8a',
          'Lemma.Ink.Surface.bulkUploadStep': 'bd38f3c4b118369edf10e3da4b634e74d22d6ab1b04e2663c8895c4169396faa',
          'Lemma.Ink.Surface.uploadAllBulk': 'c2acbef2d1ebfee4df40247c134f7d3aaa15283aa2533603cafe94e370eb38c5',
          'Lemma.Applications.Notebook.mainSumsBulk': 'aa17e16c90d673cc4996b6fadf83d01d32f98b25ef04a13e61bafbf9bc466142',
          'Lemma.Applications.Notebook.mainBytesBulk': '6cba4bcc59100add365db7e831a1d153e1008e9329f7b093ca230a05799d7a8b',
          'Lemma.Applications.Notebook.mainArrayBulk': 'aa2c27e368adc67e8ffd9899ed41237dd15195a7cf5830050d4ce5f0e596ccda'}}


def canonical(source):
 return re.sub(r'^_private\..*?\.[0-9]+\.','',source)

def validate(ir,unit,*,optimized):
 from surface_bulk_borrow import validate_if_present as validate_critical_borrow
 critical_borrow=validate_critical_borrow(ir,unit,optimized=optimized)
 if critical_borrow is not None:return critical_borrow
 if optimized or unit.get('configuration') not in CONFIGURATIONS:return None
 role=unit.get('role')
 if role=='user' and unit.get('image_key')!='notebook':return None
 if role not in EXPECTED:return None
 from audit_kernel import _ir_definition_body
 from audit_device import _line_functions
 names={row['symbol']:canonical(row['source']) for row in unit['functions']}
 by={source:symbol for symbol,source in names.items()}
 selected=dict(EXPECTED[role])
 if role=='kernel' and unit['configuration'] in WIRE_CONFIGURATIONS:
  from paper_wire import validate as validate_wire
  return validate_wire(ir,unit,optimized=optimized)
 if role=='kernel' and unit['configuration']==EXECUTED_CONFIGURATION:
  from paper_executed import validate as validate_executed
  return validate_executed(ir,unit,optimized=optimized)
 if role=='kernel' and unit['configuration'] in NEXT_CONFIGURATIONS:
  from paper_next import validate as validate_next
  return validate_next(ir,unit,optimized=optimized)
 if role=='kernel':
  modern=unit['configuration']==PRODUCT or unit['configuration'] in USB
  wrapper='dispatchProductBulk' if unit['configuration']==PRODUCT else 'dispatchUSBBulk'
  for source in list(selected):
   if '.NotebookKernel.' not in source:continue
   special='ModernBulk' in source or 'ProductBulk' in source or 'USBBulk' in source
   if special!=modern or special and ('ProductBulk' in source or 'USBBulk' in source) and not source.endswith('.'+wrapper):del selected[source]
 else:
  if unit['configuration'] in PACKAGE_CONFIGURATIONS:
   from package_notebook_target import validate as validate_package
   package = validate_package(ir, unit, optimized=False)
   if package is None: raise Core0Error('Surface-v2 Package root lacks complete source cohort')
   # Presentation3/4/6 and workspace-envelope5 retain the Surface path. The full
   # cohort gate above and the exact unchanged layout2 boot root below remain
   # mandatory; a version label alone cannot authorize a new Surface path.
   if package['contract_version'] in ('lemma-installed-package-notebook/2',
                                       'lemma-installed-package-notebook/3',
                                       'lemma-installed-package-notebook/4',
                                       'lemma-installed-package-notebook/5',
                                       'lemma-installed-package-notebook/6'):
    selected['Lemma.Applications.Notebook.mainPackageClosureBulk']='4d65240a23cc144f0ecd618284855d5b2b8361688ba8eed82b00e6d5f9bbcb7f'
   elif package['contract_version'] == 'lemma-installed-package-notebook/1':
    selected['Lemma.Applications.Notebook.mainPackageClosureBulk']='0318d48be82d75b41e30cbb2034da5e6f2ea22f6bea86d344f70747d9ff1b5ea'
   else: raise Core0Error('Surface-v2 Package source cohort is unknown')
  elif unit['configuration'] in CLOSURE_CONFIGURATIONS:
   selected['Lemma.Applications.Notebook.mainClosureBulk']='435236b7dba59e7ff115a510fce38c4157b1e8c120e07695bacfa937b9cabf82'
  for source in list(selected):
   if source.endswith('.mainArrayBulk') and unit['configuration'] not in ARRAY or source.endswith('.mainBytesBulk') and unit['configuration'] not in BYTES or source.endswith('.mainSumsBulk') and unit['configuration'] in BYTES | ARRAY | frozenset(CLOSURE_CONFIGURATIONS):del selected[source]
 observed={}
 for source,expected in selected.items():
  if source not in by:raise Core0Error('Surface-v2 source closure missing: '+source)
  body=_ir_definition_body(ir,by[source])
  if body is None:raise Core0Error('Surface-v2 actual LLVM body missing')
  rebound=re.sub(r'@([^ (]+)',lambda m:'@'+names.get(m[1],m[1]),body)
  normalized=' '.join(' '.join(line.split(';',1)[0].strip() for line in rebound.splitlines()).split())
  digest=hashlib.sha256(normalized.encode()).hexdigest()
  if digest!=expected:raise Core0Error('Surface-v2 ownership/copy/geometry/PIO/packet/root authority differs: '+source)
  observed[source]=digest
 if role=='kernel':
  target=by['Lemma.Platform.LemmaSim.DeviceService.surfaceV2']
  owner=by['Lemma.Platform.LemmaSim.NotebookKernel.'+('deviceCallModernBulk' if unit['configuration']==PRODUCT or unit['configuration'] in USB else 'deviceCallBulk')]
  lines=ir.splitlines();owners=_line_functions(lines)
  callers=[owners[i] for i,line in enumerate(lines) if re.search(r'\bcall\b[^\n]*@'+re.escape(target)+r'\(',line)]
  if callers!=[owner]:raise Core0Error('Surface-v2 acquired an additional device-call authority')
 return {'contract_version':'lemma-surface-v2','role':role,'body_identities':observed,
  'scope':'Complete genuine pre-LLVM selected ABI/ownership/PIO bodies; runtime acceptance separate'}
