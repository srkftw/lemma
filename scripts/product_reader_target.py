"""Fail-closed artifact authority for the additive Product10 course deployment.

Only audits genuine exported catalogs and LLVM. No guest policy runs here.
The complete original caller/global/body corpus and exact old shared Paper3
bodies remain load-bearing; connected ROM/health/course results are separate.
"""
import hashlib
import json
import re
from pathlib import Path
from core0_common import Core0Error
from paper_next import canonical, normalized
from product_reader_deployment import CONFIGURATIONS, SOFTWARE_DEPLOYMENT, BOOT_ROOT, DISPATCH_ROOT

VERSION='lemma-product-course-reader-target/1'
AUTHORITY=Path(__file__).resolve().parents[1]/'tooling/product-reader-target-authority.json'
PREFIX='Lemma.Platform.LemmaSim.NotebookKernel.'
# Context changes only in these original helpers after the exact Product10
# physical-guard lowering. All pre-bodies and all independent data-flow,
# caller, ordered-access and failure checks remain unchanged.
POST_HELPERS={
 'Lemma.Kernel.Memory.UserCopy.'+name for name in ('copyWord','copyWordGenericBlockStep','copyWordBlockStep')
}|{
 'Lemma.Kernel.Memory.Frames.resolveRegistry8192',
 'Lemma.Kernel.Memory.AddressSpace.validateRegistry8192Step',
 'Lemma.Kernel.Task.entryContextV2','Lemma.Kernel.Task.entryDispatchesV2',
 'Lemma.Kernel.Scheduler.entryV2','Lemma.Kernel.Task.findStep','Lemma.Kernel.Task.table',
 'Lemma.Kernel.Memory.AddressSpace.base','Lemma.Kernel.Memory.AddressSpace.validateRegistryStep',
 'Lemma.Kernel.Memory.AddressSpace.validateRegistryGenericStep',
 'Lemma.Kernel.Memory.Frames.resolvePurpose','Lemma.Kernel.Memory.Frames.resolve',
 'Lemma.Kernel.Process.validateStackAt','Lemma.Kernel.Loader.validateExpandedStackAt'}

def post_helper_pin(unit,source,original):
    if not selected(unit) or source not in POST_HELPERS:return original
    wanted=authority(unit,'kernel')
    require(set(wanted.get('physical_inline_helper_post_sha256',{}))==POST_HELPERS,
            'Product course exact post-LLVM helper cohort differs')
    return wanted['physical_inline_helper_post_sha256'][source]


def require(value,message):
    if not value:raise Core0Error(message)

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def selected(unit):return unit.get('configuration') in CONFIGURATIONS

def authority(unit,key):
    require(selected(unit) and unit.get('software_deployment')==SOFTWARE_DEPLOYMENT,
            'Product course exact software/hardware tuple differs')
    wanted=json.loads(AUTHORITY.read_text())
    require(wanted.get('schema')==VERSION and set(wanted.get('roles',{}))=={'kernel','notebook'} and
            wanted.get('reader_artifact_sha256')==hashlib.sha256(AUTHORITY.with_name('reader-notebook-target-authority.json').read_bytes()).hexdigest(),
            'Product course authority schema/complete predecessor differs')
    from kernel_pool_read_target import refined_role
    row=refined_role(unit,wanted['roles'][key],AUTHORITY,key)
    from authored_hint_target import refined as hint_refined
    if key == 'notebook': row=hint_refined(unit,row,AUTHORITY,key)
    require(row.get('catalog_sha256')==digest(unit),'Product course complete original catalog differs: '+key)
    return row

def kernel_semantics(ir,unit):
    from audit_kernel import _ir_definition_body,_local_call_arguments,validate_checked_call_gate
    rows={canonical(row['source']):row for row in unit['functions']}
    def calls(owner,target):
        require(owner in rows and target in rows,'Product course semantic declaration missing')
        return _local_call_arguments(_ir_definition_body(ir,rows[owner]['symbol']),rows[target]['symbol'])
    constructor=PREFIX+'constructProductCourseReader';step=PREFIX+'productCourseReaderStep'
    require(calls(constructor,'Lemma.Kernel.Memory.AddressSpace.configureProductExecuted')==['i64 10'] and
            calls(constructor,'Lemma.Kernel.Process.initProduct')==[''] and
            calls(constructor,'Lemma.Kernel.Task.prepareManagedProduct')==[
                'i64 0, i64 0','i64 1, i64 2','i64 2, i64 0','i64 3, i64 0'],
            'Product course four actual product loader/isolation operands differ')
    require(calls(BOOT_ROOT,'Lemma.Platform.LemmaSim.Descriptor.validateBindingExecuted')==['i64 10'],
            'Product course exact FDT/binding10 selection differs')
    require(len(calls(constructor,'Lemma.Kernel.Objects.createEndpoint'))==6 and
            len(calls(constructor,PREFIX+'grant'))==13 and
            len(calls(constructor,'Lemma.Kernel.Task.activateManaged'))==4 and
            len(calls(constructor,'Lemma.Platform.LemmaSim.BootHealthExecuted.configure'))==1,
            'Product course exact endpoint/grant/activation/health inventory differs')
    require(calls(step,PREFIX+'acceptPendingModernExecuted')==['i64 10'] and
            calls(step,'Lemma.Platform.LemmaSim.BootHealthExecuted.step')==[''] and
            calls(step,'Lemma.Kernel.Scheduler.stepEntryV2')==[''],
            'Product course scheduler omits real Product10 health/entry path')
    for target in ('Lemma.Platform.LemmaVM.ConsoleDevice.initialize14',
                   'Lemma.Kernel.Memory.Frames.init','Lemma.Drivers.Paper.initializeExecuted',
                   'Lemma.Drivers.Pen.initialize',constructor):
        require(calls(BOOT_ROOT,target)==[''],'Product course actual boot transaction count/operand differs: '+target)
    require(not any('initializeMedium' in source or source in (
            'Lemma.Platform.LemmaSim.NotebookKernel.bootCourseSelectedEntryV2',
            'Lemma.Platform.LemmaSim.NotebookKernel.bootModernExecuted') for source in rows),
            'Product course acquired alternate boot/format authority')
    return {'roles':4,'capability_grants':13,'endpoints':6,'binding':10,
            'ordinary_format_path':False,'health_and_entry_v2':True}

def validate_kernel(ir,unit,*,optimized):
    from usb_recovery_target import corpus
    from paper_executed import EXPECTED,POST_BODIES
    require(unit.get('role')=='kernel' and unit.get('contract_version')=='core0-kernel-v0.7' and
            [(canonical(x['source']),x['id'],x['args'])for x in unit.get('roots',[])]==[
                (BOOT_ROOT,1,[]),(DISPATCH_ROOT,2,['u64']*3)],
            'Product course exact Kernel7 root/dispatch differs')
    require(len(unit.get('checked_inline',{}).get('wrappers',[]))==4,
            'Product course requires all four checked physical wrapper catalog entries')
    wanted=authority(unit,'kernel');phase='post' if optimized else 'pre'
    actual=corpus(ir,unit)
    require(len(actual['functions'])==wanted[phase+'_function_count'] and digest(actual)==wanted[phase+'_sha256'],
            'Product course complete kernel caller/global/body corpus differs: '+phase)
    rows={canonical(row['source']):row for row in unit['functions']};names={r['symbol']:s for s,r in rows.items()}
    shared={source:spec for source,spec in EXPECTED.items() if source in rows}
    historical_boot={PREFIX+name for name in ('bootModernExecuted','constructModernExecuted',
        'modernExecutedStep','modernProductExecutedStep','modernUSBExecutedStep','siliconProductExecutedBoot')}
    require(set(shared)==set(EXPECTED)-historical_boot and len(shared)==110,
            'Product course exact shared Paper3/BootNV/health inventory differs')
    for source,(args,effects,pin)in shared.items():
        require((rows[source]['args'],rows[source]['effects'])==(args,effects),'Product course shared Paper3 signature differs')
        if optimized and source not in POST_BODIES:continue
        expected=(wanted['physical_inline_token_post_sha256'] if source.endswith('.tokenStepExecuted') else POST_BODIES[source]) if optimized else pin
        require(hashlib.sha256(normalized(ir,rows[source],names).encode()).hexdigest()==expected,
                'Product course changed shared Paper3/health body: '+source)
    return {'contract_version':VERSION,'phase':phase,'functions':len(actual['functions']),
            'complete_corpus_sha256':digest(actual),'shared_paper3_declarations':len(shared),
            'semantics':None if optimized else kernel_semantics(ir,unit),
            'scope':'Complete artifact only; actual full-image/ROM/Ready/health/course execution separate'}

def validate_entry(ir,unit,*,optimized):
    from task_entry_borrow import validate_component
    report=validate_kernel(ir,unit,optimized=optimized)
    return {**validate_component(ir,unit,optimized=optimized),'product_course_deployment':report}
