"""Exact Integrated15 guest authority, separate from unchanged Multimodal14.

All pins come from genuine Lean exports. Collection produces candidates only;
ordinary source/tool, memory, ISA and execution audits remain independent.
"""
from __future__ import annotations
import json
from pathlib import Path
from core0_common import Core0Error
from integrated_deployment import CONFIGURATIONS, SOFTWARE_DEPLOYMENT, BOOT_ROOT, DISPATCH_ROOT
from paper_next import canonical

VERSION='lemma-integrated-target-authority/1'
ROOT=Path(__file__).resolve().parents[1]
AUTHORITY=ROOT/'tooling/integrated-target-authority.json'

def selected(unit):return unit.get('configuration') in CONFIGURATIONS

def require(value,message):
    if not value:raise Core0Error('Integrated15: '+message)

def catalog(unit):
    from school_target import selected as school_selected, catalog as school_catalog
    if school_selected(unit):return school_catalog(unit)
    from multimodal_target import role_key, user_roots
    key=role_key(unit)
    rows=unit.get('functions')
    require(selected(unit) and unit.get('software_deployment')==SOFTWARE_DEPLOYMENT,'unknown configuration/software tuple')
    require(isinstance(rows,list) and rows and all(isinstance(row,dict) for row in rows),'empty genuine function inventory')
    names={canonical(row.get('source','')):row for row in rows}
    require(len(names)==len(rows) and len({row.get('symbol') for row in rows})==len(rows),'duplicate source/symbol')
    roots=[(canonical(row.get('source','')),row.get('id'),row.get('args')) for row in unit.get('roots',[])]
    if key=='kernel':
        require(unit.get('contract_version')=='core0-kernel-v0.10' and roots==[(BOOT_ROOT,1,[]),(DISPATCH_ROOT,2,['u64']*3)],'kernel roots/profile differ')
    elif key!='firmware':
        source,identifier,profile=user_roots('lemmasim-silicon-multimodal-parameterized-notebook')[key]
        require((unit.get('image_id'),unit.get('contract_version'))==(identifier,profile) and roots==[(source,1,['u64'])] and unit.get('used_device_ops')==[],'isolated role root/profile differs')
    return key,names

def authority(unit):
    from school_target import selected as school_selected, authority as school_authority
    if school_selected(unit):return school_authority(unit)
    from multimodal_target import digest, ROLES
    key,_=catalog(unit)
    try:data=json.loads(AUTHORITY.read_text())
    except (OSError,ValueError) as error:raise Core0Error('Integrated15 genuine artifact authority unavailable') from error
    require(set(data)=={'schema','configurations'} and data['schema']==VERSION and set(data['configurations'])==set(__import__('integrated_deployment').LEGACY_CONFIGURATIONS),'authority schema/configuration differs')
    item=data['configurations'][unit['configuration']]
    require(set(item)==set(ROLES),'authority role inventory differs')
    pin=item[key]
    require(set(pin)=={'catalog_sha256','pre','post'} and pin['catalog_sha256']==digest(unit),'typed/effect/root catalog differs')
    return key,pin

def semantics(ir,unit):
    from school_target import selected as school_selected, semantics as school_semantics
    if school_selected(unit):return school_semantics(ir,unit)
    from audit_kernel import _ir_definition_body,_local_call_arguments,validate_failed_call_gate
    key,rows=catalog(unit)
    if key!='kernel':
        # Only deployment metadata changes. Reuse the exact existing source,
        # body, typed role and notebook safety authority below independently.
        from multimodal_target import SOFTWARE_DEPLOYMENT as old_software,semantics as old_semantics
        return old_semantics(ir,{**unit,'configuration':'lemmasim-silicon-multimodal-parameterized-notebook','software_deployment':old_software})
    def body(source):
        require(source in rows,'missing semantic source: '+source)
        return _ir_definition_body(ir,rows[source]['symbol'])
    def calls(owner,target):return _local_call_arguments(body(owner),rows[target]['symbol'])
    n='Lemma.Platform.LemmaSim.NotebookKernel.'
    p='Lemma.Platform.LemmaSim.IntegratedKernel.'
    edges=[(BOOT_ROOT,'Lemma.Platform.LemmaVM.ConsoleDevice.initialize14'),
      (BOOT_ROOT,'Lemma.Platform.LemmaSim.Descriptor.validateSiliconProductExecuted'),
      (BOOT_ROOT,p+'startupAuthority'),(BOOT_ROOT,'Lemma.Drivers.Multimodal.discover'),
      (BOOT_ROOT,n+'prepareIntegratedAuthorities'),(BOOT_ROOT,p+'configureAliases'),
      (BOOT_ROOT,'Lemma.Platform.LemmaSim.MultimodalService.configure'),
      (n+'prepareIntegratedAuthorities',n+'constructProductCourseReader'),
      (n+'prepareIntegratedAuthorities',n+'grantParameterizedInstaller'),
      (p+'step',n+'stepIntegratedAuthorities'),
      (n+'stepIntegratedAuthorities',n+'productCourseReaderStep'),
      (p+'configureAliases',p+'installRoot'),(p+'taskAliases',p+'installRoot'),
      (p+'installRoot',p+'ownedTable'),
      (DISPATCH_ROOT,n+'dispatchMultimodalBulk'),
      (DISPATCH_ROOT,'Lemma.Platform.LemmaSim.TrialWatchdogKernel.confirmHealthy'),
      (p+'step','Lemma.Platform.LemmaSim.TrialWatchdogKernel.confirmHealthy')]
    for owner,target in edges:require(len(calls(owner,target))==1,'omitted/repeated direct edge: '+owner+' -> '+target)
    require(len(calls(DISPATCH_ROOT,n+'dispatchProductExecutedBulk'))==2,'non69 dispatch paths differ')
    require(calls(n+'constructProductCourseReader','Lemma.Kernel.Task.prepareManagedProduct') and len(calls(n+'constructProductCourseReader','Lemma.Kernel.Task.prepareManagedProduct'))==4,'four role preparation differs')
    require(len(calls(n+'constructProductCourseReader','Lemma.Kernel.Task.activateManaged'))==4,'four role activation differs')
    for first,after in ((p+'startupAuthority',n+'prepareIntegratedAuthorities'),(n+'prepareIntegratedAuthorities',p+'configureAliases'),(p+'configureAliases','Lemma.Platform.LemmaSim.MultimodalService.configure')):
        validate_failed_call_gate(body(BOOT_ROOT),rows[first]['symbol'],rows[after]['symbol'],rows[p+'failed']['symbol'],body(p+'failed'))
    return {'role':key,'explicit_call_edges':edges,'scope':'complete genuine body authority and owned boot composition; connected execution separate'}

def validate(ir,unit,*,optimized):
    from school_target import selected as school_selected, validate as school_validate
    if school_selected(unit):return school_validate(ir,unit,optimized=optimized)
    if not selected(unit):return None
    from multimodal_target import complete,digest
    key,pin=authority(unit);phase='post' if optimized else 'pre'
    actual=complete(ir,unit,optimized=optimized)
    require(len(actual['functions'])==pin[phase]['function_count'] and digest(actual)==pin[phase]['sha256'],'complete corpus differs: '+key+'/'+phase)
    return {'contract_version':VERSION,'role':key,'phase':phase,'complete_corpus_sha256':digest(actual),'function_count':len(actual['functions']),'semantics':None if optimized else semantics(ir,unit)}

def collect(directory):
    from multimodal_target import ROLES,complete,digest
    directory=Path(directory);roles={}
    for key in ROLES:
        base=directory/key if key in ('kernel','firmware') else directory/'users'/key
        unit=json.loads((base/'unit.json').read_text());require(catalog(unit)[0]==key,'mixed roles')
        semantics((base/'program.ll').read_text(),unit)
        item={'catalog_sha256':digest(unit)}
        for phase,name in (('pre','program.ll'),('post','program.opt.ll')):
            actual=complete((base/name).read_text(),unit,optimized=phase=='post')
            item[phase]={'function_count':len(actual['functions']),'sha256':digest(actual)}
        # User/firmware bodies must still equal their existing pinned producer.
        if key!='kernel':
            from multimodal_target import AUTHORITY as old_path,SOFTWARE_DEPLOYMENT as old_software
            old_unit={**unit,'configuration':'lemmasim-silicon-multimodal-parameterized-notebook','software_deployment':old_software}
            old=json.loads(old_path.read_text())['configurations'][old_unit['configuration']][key]
            require(item['pre']==old['pre'] and item['post']==old['post'] and digest(old_unit)==old['catalog_sha256'],'unchanged isolated role/firmware predecessor differs: '+key)
        roles[key]=item
    return {'schema':VERSION,'configurations':{CONFIGURATIONS[0]:roles}}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--collect',type=Path,required=True)
    print(json.dumps(collect(parser.parse_args().collect),indent=2))


def validate_pmp(assembly,raw_machine,ranges):
    """Decode actual startup CSR bytes and each fatal mismatch branch."""
    import re,struct
    from audit_kernel import _assembly_function,_raw_function
    body=_assembly_function(assembly,'_start')
    old=['csrw pmpcfg0, zero','csrw pmpcfg2, zero']
    for i,v in enumerate([536879103,537141247,553648127,67108895,262655,51380223,67110399,67126271]):old += [f'li t0, {v}',f'csrw pmpaddr{i}, t0']
    old += ['li t0, 1953184666628331544','csrw pmpcfg0, t0']
    tail=['li t0, 67127423','csrw pmpaddr8, t0','csrr t1, pmpaddr8','bne t0, t1, lemma_machine_fatal',
          'li t0, 67130367','csrw pmpaddr9, t0','csrr t1, pmpaddr9','bne t0, t1, lemma_machine_fatal',
          'li t0, 6939','csrw pmpcfg2, t0','csrr t1, pmpcfg2','bne t0, t1, lemma_machine_fatal','sfence.vma zero, zero']
    expected=old+tail
    require(sum(body[i:i+len(expected)]==expected for i in range(len(body)-len(expected)+1))==1,'complete dual PMP assembly differs')
    words=list(struct.unpack('<'+str(ranges['_start'][1]//4)+'I',_raw_function(raw_machine,ranges,'_start')))
    csr=lambda w:((w>>20)&4095) if w&127==0x73 and (w>>12)&7 else None
    def enc(n,f,rd,rs):return n<<20|rs<<15|f<<12|rd<<7|0x73
    inventory=[(i,w) for i,w in enumerate(words) if csr(w) in {0x3a2,0x3b8,0x3b9}]
    expected_csr=[enc(0x3a2,1,0,0),enc(0x3b8,1,0,5),enc(0x3b8,2,6,0),enc(0x3b9,1,0,5),enc(0x3b9,2,6,0),enc(0x3a2,1,0,5),enc(0x3a2,2,6,0),enc(0x3b8,2,6,0),enc(0x3a2,2,6,0),enc(0x3b9,2,6,0),enc(0x3a2,2,6,0)]
    require([w for _,w in inventory]==expected_csr,'actual dual CSR inventory differs')
    begin=ranges['_start'][0];fatal=ranges['lemma_machine_fatal'][0]
    def gate(i):
        w=words[i];require(w&127==0x63 and (w>>15)&31==5 and (w>>20)&31==6,'WARL compare registers differ')
        off=(w>>31)<<12|((w>>7)&1)<<11|((w>>25)&63)<<5|((w>>8)&15)<<1
        if off&4096:off-=8192
        if (w>>12)&7==1 and begin+i*4+off==fatal:return i+1
        require((w>>12)&7==0 and off==8,'WARL mismatch branch differs')
        jump=words[i+1];require(jump&127==0x6f and (jump>>7)&31==0,'WARL mismatch lacks fatal jump')
        off=(jump>>31)<<20|((jump>>12)&255)<<12|((jump>>20)&1)<<11|((jump>>21)&1023)<<1
        if off&(1<<20):off-=1<<21
        require(begin+(i+1)*4+off==fatal,'WARL mismatch escapes fatal');return i+2
    def li(at,value):
        # Pinned assembler expands each positive constant to LUI+ADDIW.
        upper=(value+0x800)>>12;lower=value-(upper<<12)
        return words[at-2:at]==[upper<<12|5<<7|0x37,(lower&4095)<<20|5<<15|5<<7|0x1b]
    for item,value,next_item in ((1,0x0400487f,3),(3,0x040053ff,5),(5,0x1b1b,None)):
        at=inventory[item][0]
        require(li(at,value) and inventory[item+1][0]==at+1,'actual address/config value or readback ordering differs')
        after=gate(at+2)
        if next_item is None:require(words[after]==0x12000073,'dual grant omitted translation fence')
        else:require(inventory[next_item][0]==after+2,'dual grant changed next constant/write order')
    record=['li t0, 2152595936','csrr t1, pmpaddr8','sd t1, 0(t0)','csrr t1, pmpcfg2','sd t1, 8(t0)','csrr t1, pmpaddr9','sd t1, 16(t0)','csrr t1, pmpcfg2','sd t1, 24(t0)']
    require(sum(body[i:i+len(record)]==record for i in range(len(body)-len(record)+1))==1,'actual boot readback records differ')
    return {'contract_version':'lemma-integrated-pmp/1','entries':[{'entry':8,'base':0x10012000,'bytes':1024},{'entry':9,'base':0x10014000,'bytes':8192}],'permissions':'RW/NX','csr_instructions':11,'readback_fatal_branches':3}
