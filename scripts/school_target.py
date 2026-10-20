"""Source/LLVM authority for the actual four-role School composition.

Pins are collected from genuine exports. They bind complete pre/post bodies,
roots, effects and call closure. Collection is not execution evidence.
"""
from pathlib import Path
import json
import re
from core0_common import Core0Error
from paper_next import canonical
from school_deployment import CONFIGURATIONS, USER_ROOTS, INTEGRATED_CONFIGURATIONS, BOOT_ROOTS, software_deployment_for
VERSION='lemma-school-target-authority/1'
ROOT=Path(__file__).resolve().parents[1]
AUTHORITY=ROOT/'tooling/school-target-authority.json'
ROLES=('firmware','kernel','store','notebook','arithmetic','course')
def selected(unit):return unit.get('configuration') in CONFIGURATIONS
def require(value,message):
    if not value:raise Core0Error('School: '+message)
def catalog(unit):
    from multimodal_target import role_key
    key=role_key(unit);configuration=unit.get('configuration')
    require(selected(unit) and unit.get('software_deployment')==software_deployment_for(configuration),'configuration/software tuple differs')
    rows=unit.get('functions');require(isinstance(rows,list) and rows,'empty genuine source catalog')
    names={canonical(row.get('source','')):row for row in rows}
    require(len(names)==len(rows) and len({row.get('symbol') for row in rows})==len(rows),'duplicate source/symbol')
    roots=[(canonical(row.get('source','')),row.get('id'),row.get('args')) for row in unit.get('roots',[])]
    if key=='kernel':
        if configuration in INTEGRATED_CONFIGURATIONS:
            from integrated_deployment import BOOT_ROOT,DISPATCH_ROOT
            expected=[(BOOT_ROOT,1,[]),(DISPATCH_ROOT,2,['u64']*3)];profile='core0-kernel-v0.10'
        else:
            prefix='Lemma.Platform.LemmaSim.NotebookKernel.'
            expected=[(prefix+BOOT_ROOTS[configuration],1,[]),(prefix+'dispatchMultimodalBulk',2,['u64']*3)];profile='core0-kernel-v0.9'
        require(unit.get('contract_version')==profile and roots==expected,'kernel root/profile differs')
    elif key!='firmware':
        source,identifier,profile=USER_ROOTS[key]
        require((unit.get('image_id'),unit.get('contract_version'))==(identifier,profile) and roots==[(source,1,['u64'])] and unit.get('used_device_ops')==[],'isolated root/profile/device authority differs')
    return key,names

def warm_send_semantics(ir, rows):
    """Reviewed warm overlay path; complete pre/post pins remain mandatory.

    Follow actual checked LLVM values rather than recognizing function names.
    Source guards separately bind the structured rejection paths and layout.
    """
    from audit_kernel import _ir_definition_body, _local_call_arguments, _local_checked_result
    n='Lemma.Applications.Notebook.';memory='Lemma.User.Memory.';workspace='Lemma.Courses.PackageWorkspace.'
    def body(name):
        require(name in rows,'warm SEND source absent: '+name)
        return _ir_definition_body(ir,rows[name]['symbol'])
    def calls(owner,target):
        require(target in rows,'warm SEND target absent: '+target)
        return _local_call_arguments(body(owner),rows[target]['symbol'])
    def value(owner,target,args):return _local_checked_result(body(owner),rows[target]['symbol'],args)[1]
    var=r'%[A-Za-z0-9_.$-]+'
    def scalar(owner,target,args=''):
        require(target in rows,'warm SEND scalar absent: '+target)
        found=re.findall('('+var+r') = call i64 @'+re.escape(rows[target]['symbol'])+r'\('+re.escape(args)+r'\)',body(owner))
        require(found,'warm SEND scalar value absent: '+target)
        return found
    def add(owner,left,right):
        found=re.findall('('+var+r') = add i64 '+re.escape(left)+', '+re.escape(right)+r'$',body(owner),re.M)
        require(len(found)==1,'warm SEND exact address addition differs')
        return found[0]
    def read_at(owner,base,offset):
        found=[]
        for pointer in scalar(owner,base):
            match=re.findall('('+var+r') = add i64 '+re.escape(pointer)+', '+str(offset)+r'$',body(owner),re.M)
            for address in match:found.append(value(owner,memory+'read64','i64 '+address))
        require(len(found)==1,'warm SEND exact source address differs: '+base+'/'+str(offset))
        return found[0]
    def compare(owner,predicate,left,right):
        found=re.findall('('+var+r') = icmp '+predicate+' i64 '+re.escape(left)+', '+re.escape(right)+r'$',body(owner),re.M)
        require(len(found)==1 and re.search(r'br i1 '+re.escape(found[0])+r', label %[^,]+, label %[^\n]+',body(owner)),
                'warm SEND original-context comparison differs: '+predicate+' '+left+'/'+right)
    source=n+'schoolSendSource';attempt=n+'schoolSendAttempt';wrapper=n+'schoolSend'
    require(calls(wrapper,attempt)==[''] and calls(attempt,source)==[''],'warm SEND wrapper/attempt/source route differs')
    source_body=body(source)
    require(calls(source,memory+'write64')==[],'warm SEND source helper wrote outside its private scratch')
    scratch_store=n+'schoolSendSource.store';writes=[]
    for offset,argument in ((16,0),(24,1),(32,3),(40,2)):
        matches=[]
        for base in scalar(scratch_store,n+'packageBindingScratch'):
            found=re.findall('('+var+r') = add i64 '+re.escape(base)+', '+str(offset)+r'$',body(scratch_store),re.M)
            matches+=found
        require(len(matches)==1,'warm SEND scratch address differs')
        writes.append('i64 '+matches[0]+', i64 %arg'+str(argument))
    require(calls(scratch_store,memory+'write64')==writes,'warm SEND scratch publication changed tuple or ownership')
    value(wrapper,attempt,'')
    attempt_call=re.findall('('+var+r') = call \{ i64, i64 \} @'+re.escape(rows[attempt]['symbol'])+r'\(\)',body(wrapper))
    status_word=re.findall('('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(attempt_call[0])+r', 0$',body(wrapper),re.M)
    status=re.findall('('+var+r') = trunc i64 '+re.escape(status_word[0])+r' to i8$',body(wrapper),re.M) if len(status_word)==1 else []
    require(len(status)==1 and calls(wrapper,n+'schoolQueueFailure')==['i8 zeroext '+status[0]],'warm SEND rejection lost original status')
    ns=value(source,n+'get','i64 72');page=value(source,n+'get','i64 80')
    bases=scalar(source,n+'packageWorkspace')
    require(calls(source,workspace+'validate')==['i64 '+bases[0]+', i64 '+ns+', i64 '+page],
            'warm SEND escaped current namespace/page validation')
    loaded=read_at(source,n+'packageBytes',24);compare(source,'eq',loaded,'60001')
    fields={offset:value(source,n+'tutorGet','i64 '+str(offset)) for offset in (112,96,104,24,16,0,48,56,64,88)}
    current_revision_calls=calls(source,'Lemma.Documents.Mathematics.field')
    require(len(current_revision_calls)==1 and current_revision_calls[0].endswith(', i64 40'),'warm SEND current mathematical revision differs')
    revision=value(source,'Lemma.Documents.Mathematics.field',current_revision_calls[0])
    obj=scalar(source,workspace+'object','i64 '+page)
    require(len(obj)==1,'warm SEND page object differs')
    comparisons=[('eq',fields[112],'1'),('eq',ns,fields[96]),('eq',page,fields[104]),
                 ('eq',fields[24],obj[0]),('ult','0',fields[16]),('ule',fields[16],revision),
                 ('eq',fields[0],read_at(source,n+'schoolContext',80)),
                 ('eq',fields[48],read_at(source,n+'schoolContext',88)),
                 ('eq',fields[56],read_at(source,n+'schoolContext',96)),
                 ('eq',fields[48],'60000'),('eq',fields[48],'60001')]
    for predicate,left,right in comparisons:compare(source,predicate,left,right)
    # Known workspace provenance compares all three original values. A source
    # overlay cannot become a publication, nor substitute its CRC or task.
    selection=scalar(source,workspace+'selection')
    selected=[]
    for offset in (16,24,32):
        candidates=[]
        for base in bases:
            for select in selection:
                start=re.findall('('+var+r') = add i64 '+re.escape(base)+', '+re.escape(select)+r'$',source_body,re.M)
                for pointer in start:
                    address=re.findall('('+var+r') = add i64 '+re.escape(pointer)+', '+str(offset)+r'$',source_body,re.M)
                    for item in address:candidates.append(value(source,memory+'read64','i64 '+item))
        require(len(candidates)==1,'warm SEND known workspace source tuple differs')
        selected+=candidates
    for left,right in zip((fields[48],fields[56],fields[88]),selected):compare(source,'eq',left,right)
    stores=calls(source,n+'schoolSendSource.store')
    require(len(stores)==2 and stores[0]==', '.join('i64 '+fields[offset] for offset in (48,56,64,88)),
            'warm SEND retargeted original ASK source/edition/node/CRC')
    require(calls(attempt,'Lemma.Courses.SchoolSubmission.retry')==['',''] and len(calls(attempt,'Lemma.Courses.SchoolSubmission.start'))==1,
            'warm SEND immutable pending retry/start route differs')
    require(body(attempt).index('@'+rows['Lemma.Courses.SchoolSubmission.retry']['symbol']+'(')<body(attempt).index('@'+rows[source]['symbol']+'('),
            'warm SEND validates new context before immutable pending retry')
    # Checking kind remains the present work selection, with the resolved source
    # scratch tuple; original ASK is never a proof/checking-selection binding.
    args=calls(attempt,n+'schoolWorkKind')
    require(len(args)==1,'warm SEND current work kind absent')
    scratch={offset:read_at(attempt,n+'packageBindingScratch',offset) for offset in (16,24,32,40)}
    revisions=[argument for argument in calls(attempt,'Lemma.Documents.Mathematics.field') if argument.endswith(', i64 40')]
    require(len(revisions)==1 and args[0].split(', ')[0]=='i64 '+value(attempt,'Lemma.Documents.Mathematics.field',revisions[0]),'warm SEND checking kind lost current revision')
    require(args[0].split(', ')[1:]==['i64 '+scratch[offset] for offset in (16,24,40,32)],'warm SEND kind/source tuple retargeted')
    return {'original_ASK_offsets':[48,56,64,88,96,104,112],'known_workspace_checks':['source','edition','CRC'],
            'current_work_kind':True,'immutable_pending_retry_first':True,'scope':'exact checked LLVM value flow plus separately reviewed source guards and complete body pins'}

def semantics(ir,unit):
    from audit_kernel import _ir_definition_body,_local_call_arguments
    key,rows=catalog(unit)
    if key=='kernel':
        if unit['configuration'] in INTEGRATED_CONFIGURATIONS:
            from integrated_target import semantics as old_semantics
            from integrated_deployment import SOFTWARE_DEPLOYMENT
            cfg='lemmasim-silicon-integrated-notebook'
        else:
            from multimodal_target import semantics as old_semantics
            from multimodal_deployment import SOFTWARE_DEPLOYMENT
            cfg='lemmasim-silicon-multimodal-initialize' if unit['configuration'].endswith('-initialize') else 'lemmasim-silicon-multimodal-notebook'
        return old_semantics(ir,{**unit,'configuration':cfg,'software_deployment':SOFTWARE_DEPLOYMENT})
    def calls(owner,target):
        require(owner in rows and target in rows,'missing semantic edge '+owner+' -> '+target)
        return _local_call_arguments(_ir_definition_body(ir,rows[owner]['symbol']),rows[target]['symbol'])
    n='Lemma.Applications.Notebook.';q='Lemma.Courses.SchoolSubmission.';p='Lemma.Courses.PackageInstaller.'
    edges=[];warm=None
    if key=='notebook':
        edges=[(n+'mainMultimodalSchool',n+'mainMultimodalConfigured'),(n+'multimodalStep',n+'schoolQueuePump'),(n+'schoolQueueInitialize',q+'initializeQueue'),(n+'schoolQueueInitialize',q+'restore'),(n+'schoolCancel',q+'cancel'),(n+'schoolQueuePump',q+'pump'),(n+'schoolQueuePump',q+'frontier'),(n+'issue',q+'suspend'),(n+'issue',q+'writerActive')]
        require(calls(n+'mainMultimodalSchool',n+'mainMultimodalConfigured')==['i64 %arg0, i64 1'],'School root must explicitly enable queue/selection')
        if n+'schoolSendSource' in rows:
            warm=warm_send_semantics(ir,rows)
            edges += [(n+'multimodalStep',n+'multimodalPumpTutor'),(n+'multimodalPumpTutor',n+'multimodalControl'),(n+'multimodalControl',n+'schoolSend'),(n+'schoolSend',n+'schoolSendAttempt'),(n+'schoolSend',n+'schoolQueueFailure'),(n+'schoolSendAttempt',q+'start'),(n+'schoolSendAttempt',q+'retry'),(n+'schoolSendAttempt',n+'schoolSendSource'),(n+'schoolSendAttempt',n+'schoolWorkKind'),(n+'schoolSendSource','Lemma.Courses.PackageWorkspace.validate'),(n+'schoolSendSource','Lemma.Courses.PackageTarget.select'),(n+'schoolSendSource',n+'schoolSendSource.store')]
        else:edges += [(n+'schoolSend',q+'start'),(n+'schoolSend',q+'retry')]
    elif key=='store':
        s='Lemma.Services.Store.ServerSchool.'
        edges=[(s+'applicationAwait','Lemma.Services.Store.Server.schoolApplication'),(s+'applicationAwait','Lemma.Services.Store.ServerAwait.awaitApplication'),(s+'applicationAwait','Lemma.Services.Store.ServerRecovery.application'),(s+'stepAwait','Lemma.Services.Store.ServerRecovery.pumpRecoveryPhase'),(s+'stepAwait','Lemma.Services.Store.Server.courseService'),(s+'stepAwait','Lemma.Services.Store.ServerAwait.settleWaiters')]
    elif key=='course':
        loops=unit.get('used_loops',[])
        require(len(loops)==1 and canonical(loops[0].get('callback',''))==p+'stepSelected','selected installer loop differs')
    for owner,target in edges:require(calls(owner,target),'omitted actual call edge '+owner+' -> '+target)
    return {'role':key,'explicit_call_edges':edges,**({'warm_submission':warm} if warm is not None else {}),'scope':'complete genuine source/LLVM authority; connected UI execution remains separate'}
def authority(unit):
    from multimodal_target import digest
    key,_=catalog(unit)
    try:data=json.loads(AUTHORITY.read_text())
    except (OSError,ValueError) as error:raise Core0Error('School complete authority unavailable') from error
    require(data.get('schema')==VERSION and set(data)=={'schema','configurations'},'authority schema differs')
    cfg=unit['configuration'];require(cfg in data['configurations'],'missing configuration authority')
    roles=data['configurations'][cfg];require(set(roles)==set(ROLES),'role inventory differs')
    pin=roles[key];require(set(pin)=={'catalog_sha256','pre','post'} and pin['catalog_sha256']==digest(unit),'typed catalog differs')
    return key,pin

def validate(ir,unit,*,optimized):
    if not selected(unit):return None
    from multimodal_target import complete,digest
    key,pin=authority(unit);phase='post' if optimized else 'pre';actual=complete(ir,unit,optimized=optimized)
    require(len(actual['functions'])==pin[phase]['function_count'] and digest(actual)==pin[phase]['sha256'],'complete pre/post source corpus differs: '+key+'/'+phase)
    return {'contract_version':VERSION,'role':key,'phase':phase,'complete_corpus_sha256':digest(actual),'function_count':len(actual['functions']),'semantics':None if optimized else semantics(ir,unit)}
def readonly_lookup(ir,unit,*,optimized):
    from multimodal_target import _readonly_lookup
    return _readonly_lookup(ir,unit,optimized=optimized)

QUEUE_DISPATCH='Lemma.Courses.SchoolSubmission.activePump'
QUEUE_PHASES=[*range(17),*range(20,31),40,41,42,43,45]
QUEUE_JUMPS={QUEUE_DISPATCH:(46,QUEUE_PHASES,[]),
    'Lemma.Courses.SchoolSubmission.pump':(42,[1,3,5,7,9,11,13,15,22,26,40,42],[[46,47]]),
    'Lemma.Applications.Notebook.multimodalControl':(6,[3,4,5,6,7,8],[])}
def queue_jump_domain(ir,rows,source):
    count,cases,others=QUEUE_JUMPS[source]
    audio='Lemma.User.Multimodal.testAudio'
    if source=='Lemma.Applications.Notebook.multimodalControl' and audio in rows:
        from audit_kernel import _ir_definition_body,_local_call_arguments
        require(rows[audio]['args']==[] and _local_call_arguments(
            _ir_definition_body(ir,rows[source]['symbol']),rows[audio]['symbol'])==[''],
            'local audio test jump lacks its exact no-argument guest consumer')
        return 7,[3,4,5,6,7,8,9],[]
    return count,cases,others
def jump_spec(ir,unit,source,symbol):
    if not selected(unit) or source not in QUEUE_JUMPS:return None
    key,rows=catalog(unit)
    require(key=='notebook' and rows[source]['symbol']==symbol,'queue table escaped exact notebook owner')
    # A table count/name cannot authorize a new dispatcher. Bind the complete
    # actual optimized source corpus to the genuine producer before admitting
    # this precise phase domain; ordinary object/guard/relocation checks follow.
    validate(ir,unit,optimized=True)
    count,cases,_=queue_jump_domain(ir,rows,source)
    return ('user',count,['u64'] if source=='Lemma.Applications.Notebook.multimodalControl' else [],['checked-access','io-order','virtual-read','virtual-write','user-syscall','privilege-transition'],cases)

def jump_default(ir,unit,assembly,symbol,targets):
    import re
    from audit_kernel import _ir_definition_body
    _,rows=catalog(unit)
    owners=[name for name,row in rows.items() if row['symbol']==symbol]
    require(len(owners)==1 and owners[0] in QUEUE_JUMPS,'queue table default owner differs')
    source=owners[0];spec=jump_spec(ir,unit,source,symbol);_,cases,others=queue_jump_domain(ir,rows,source)
    body=_ir_definition_body(ir,symbol)
    switches=re.findall(r'switch i64 %[^,]+, label %([A-Za-z0-9_.$-]+) \[([^]]+)\]',body,re.S)
    decoded=[(default,sorted(int(v) for v in re.findall(r'i64 (-?\d+), label',block))) for default,block in switches]
    selected_switch=[default for default,values in decoded if values==cases]
    require(len(selected_switch)==1 and [values for _,values in decoded if values!=cases]==others,'queue table lost exact genuine phase switch/outer suspend gate')
    default=selected_switch[0]
    owner=re.search(r'(?m)^'+re.escape(symbol)+r':[^\n]*\n(.*?)^\s*\.size\s+'+re.escape(symbol)+r',',assembly,re.S)
    labels=re.findall(r'(?m)^(\.LBB\d+_\d+):[^\n]*# %'+re.escape(default)+r'\s*$',owner[1]) if owner else []
    coalesced=None
    if not labels and source=='Lemma.Courses.SchoolSubmission.pump':
        # LLVM's two no-argument normalPump calls have identical checked
        # status/zero-value returns. The backend merges their machine blocks;
        # prove that specific relation rather than accepting any local target.
        from audit_kernel import _structured_ir_blocks
        blocks=_structured_ir_blocks('\n'.join(line.split(';',1)[0] for line in body.splitlines()))
        alias='action.if.else.13';helper=rows['Lemma.Courses.SchoolSubmission.normalPump']['symbol']
        var=r'%[A-Za-z0-9_.$-]+'
        def checked_call(label):
            lines=blocks.get(label,[])
            call=re.fullmatch('('+var+r') = call \{ i64, i64 \} @'+re.escape(helper)+r'\(\)',lines[0]) if len(lines)==3 else None
            status=re.fullmatch('('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(call[1])+', 0',lines[1]) if call else None
            merge=re.fullmatch(r'br label %([A-Za-z0-9_.$-]+)',lines[2]) if status else None
            require(merge is not None,'coalesced queue fallback changed call/status/branch')
            return status[1],merge[1]
        left,merge=checked_call(default);right,peer_merge=checked_call(alias)
        returned=blocks.get(merge,[])
        require(peer_merge==merge and len(returned)==5 and '[ '+left+', %'+default+' ]' in returned[0] and '[ '+right+', %'+alias+' ]' in returned[0],'coalesced queue fallback lost checked status returns')
        phi=re.match('('+var+r') = phi i64 ',returned[0])
        mask=re.fullmatch('('+var+r') = and i64 '+re.escape(phi[1])+', 255',returned[1]) if phi else None
        partial=re.fullmatch('('+var+r') = insertvalue \{ i64, i64 \} poison, i64 '+re.escape(mask[1])+', 0',returned[2]) if mask else None
        complete=re.fullmatch('('+var+r') = insertvalue \{ i64, i64 \} '+re.escape(partial[1])+', i64 0, 1',returned[3]) if partial else None
        require(complete is not None and returned[4]=='ret { i64, i64 } '+complete[1],'coalesced queue fallback changed status mask/zero return')
        labels=re.findall(r'(?m)^(\.LBB\d+_\d+):[^\n]*# %'+re.escape(alias)+r'\s*$',owner[1]) if owner else []
        merged=re.findall(r'(?m)^(\.LBB\d+_\d+):[^\n]*# %'+re.escape(merge)+r'\s*$',owner[1]) if owner else []
        block=re.search(r'(?m)^'+re.escape(labels[0])+r':[^\n]*\n(.*?)(?=^\.LBB|^\.Lfunc_end)',owner[1],re.S) if len(labels)==1 else None
        code=[' '.join(line.split('#',1)[0].split()) for line in block[1].splitlines() if line.split('#',1)[0].strip()] if block else []
        require(len(merged)==1 and code==['call '+helper,'j '+merged[0]],'coalesced queue machine default changed actual helper/return edge')
        coalesced={'llvm_alias':alias,'helper':'Lemma.Courses.SchoolSubmission.normalPump','checked_status_mask':255,'value':0,'machine_merge':merged[0]}
    holes=[v for v in range(min(cases),max(cases)+1) if v not in cases]
    require(len(targets)==spec[1] and len(labels)==1 and all(targets[v-min(cases)]==labels[0] for v in holes),'queue table hole escaped genuine default')
    return {'contract_version':'lemma-school-queue-phase-table/1','source':source,'phase_domain':cases,'outer_switches':others,'holes':holes,'llvm_default':default,'machine_default':labels[0],**({'coalesced_checked_return':coalesced} if coalesced else {}),'scope':'complete source-pinned owner plus ordinary actual object/unsigned-guard/local relocation coverage'}

def collect(directory):
    from multimodal_target import complete,digest
    directory=Path(directory);roles={};cfg=None
    for key in ROLES:
        base=directory/key if key in ('kernel','firmware') else directory/'users'/key
        unit=json.loads((base/'unit.json').read_text());current=unit['configuration']
        require(cfg is None or cfg==current,'mixed configuration');cfg=current
        require(catalog(unit)[0]==key,'role identity differs');semantics((base/'program.ll').read_text(),unit)
        pin={'catalog_sha256':digest(unit)}
        for phase,name in (('pre','program.ll'),('post','program.opt.ll')):
            value=complete((base/name).read_text(),unit,optimized=phase=='post');pin[phase]={'function_count':len(value['functions']),'sha256':digest(value)}
        roles[key]=pin
    return {'schema':VERSION,'configurations':{cfg:roles}}
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--collect',type=Path,required=True)
    print(json.dumps(collect(p.parse_args().collect),indent=2))
