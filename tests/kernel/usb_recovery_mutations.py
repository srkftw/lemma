"""Quarantined mutations of actual four-role Recovery-v1 artifacts only."""
from copy import deepcopy
import re
from core0_common import Core0Error
from paper_next import canonical
from usb_recovery_target import validate,semantic_guards,readonly_request_kinds
from audit_kernel import _ir_definition_body,validate_unit

def exercise(pre,post,unit):
    validate(pre,unit,optimized=False);validate(post,unit,optimized=True)
    rows={canonical(row['source']):row for row in unit['functions']};result=[]
    def reject(label,operation):
        try:operation()
        except Core0Error as error:result.append({'mutation':label,'status':'REJECTED','reason':str(error)})
        else:raise AssertionError('accepted actual recovery artifact mutation: '+label)
    def changed(ir,source,old,new):
        body=_ir_definition_body(ir,rows[source]['symbol'])
        assert body is not None and old in body and ir.count(body)==1,(source,old)
        return ir.replace(body,body.replace(old,new,1),1)
    for field,value in [('configuration','lemmasim-silicon-usb-clocked-bulk-notebook'),('contract_version','core0-user-v0.1'),('role','firmware')]:
        mutant=deepcopy(unit);mutant[field]=value
        reject('wrong-'+field,lambda m=mutant:validate(pre,m,optimized=False))
    mutant=deepcopy(unit);mutant['software_deployment']['contract_version']='lemma-managed-sums-deployment-v1'
    reject('foreign-software-deployment',lambda:validate(pre,mutant,optimized=False))
    mutant=deepcopy(unit);mutant['functions'].append(deepcopy(mutant['functions'][0]))
    reject('duplicate-source',lambda:validate(pre,mutant,optimized=False))
    for phase,ir in [('pre',pre),('post',post)]:
        # Change a real emitted body and caller independently in every role.
        from usb_recovery_target import successor
        source=next(s for s in rows if successor(s) and _ir_definition_body(ir,rows[s]['symbol']))
        body=_ir_definition_body(ir,rows[source]['symbol']);ret=re.search(r'(?m)^\s*ret ([^\n]+)$',body)
        assert ret
        replaced=body[:ret.start()]+ret[0]+'\n  unreachable'+body[ret.end():]
        reject(phase+'-changed-real-policy-body',lambda x=ir.replace(body,replaced,1),p=phase:validate(x,unit,optimized=p=='post'))
        caller=next((s,_ir_definition_body(ir,row['symbol'])) for s,row in rows.items() if re.search(r'\bcall\b.*@',_ir_definition_body(ir,row['symbol']) or ''))
        call=re.search(r'@([-A-Za-z0-9_.$]+)\(',caller[1]);assert call
        mutant=ir.replace(caller[1],caller[1].replace('@'+call[1]+'(','@ungranted_recovery_call(',1),1)
        reject(phase+'-changed-caller',lambda x=mutant,p=phase:validate(x,unit,optimized=p=='post'))
    if unit['role']=='kernel':
        source='Lemma.USB.Block.recoveryRequestValid';body=_ir_definition_body(post,rows[source]['symbol'])
        tables=[line for line in post.splitlines() if line.startswith('@switch.table.'+rows[source]['symbol'])]
        assert len(tables)==1
        table=tables[0]
        mutants=[('kind-table-byte',post.replace(table,table.replace('i64 1','i64 2',1),1)),
                 ('kind-table-width',post.replace(table,table.replace('[5 x i64]','[6 x i64]',1),1)),
                 ('kind-table-alignment',changed(post,source,'align 8','align 4'))]
        # Derive each real kind-table index from its typed GEP. Other ult
        # comparisons in this owner guard sector and physical access bounds.
        indices=re.findall(r'getelementptr inbounds nuw \[5 x i64\], ptr @[-A-Za-z0-9_.$]+, i64 0, i64 (%[-\w.]+)',body)
        assert len(indices)==3 and len(set(indices))==3
        for i,index in enumerate(indices):
            guard='icmp ult i64 '+index+', 5';assert body.count(guard)==1
            mutants.extend([('kind-unsigned-bound-'+str(i),changed(post,source,guard,'icmp ule i64 '+index+', 5')),
                            ('kind-table-extent-bound-'+str(i),changed(post,source,guard,'icmp ult i64 '+index+', 6'))])
        for label,ir in mutants:
            reject(label,lambda x=ir:readonly_request_kinds(x,unit))
        mutant=deepcopy(unit);mutant['functions'][0]['effects'].append('virtual-write')
        reject('broadened-kernel-effect',lambda:validate(pre,mutant,optimized=False))
    if unit['role']=='user' and unit['image_key']=='store':
        from managed_records import contract
        from closed_inline import validate as inline
        mutant=deepcopy(unit);mutant['managed_records']={'functions':[{'invented':'allocator'}]}
        reject('nonempty-scalar-managed-catalog',lambda:contract(mutant))
        reject('nonempty-scalar-managed-unit',lambda:validate_unit(mutant,'user',configuration=unit['configuration'],image_key='store'))
        for label,mutate in [('wrong-user-wrapper-role',lambda u:u.update(image_key='course')),('old-user-wrapper-configuration',lambda u:u.update(configuration='lemmasim-silicon-usb-clocked-bulk-notebook')),('missing-user-wrapper',lambda u:u['checked_inline']['user_wrappers'].pop())]:
            mutant=deepcopy(unit);mutate(mutant)
            reject(label,lambda m=mutant:inline(pre,m,optimized=False))
        wrapper=unit['checked_inline']['user_wrappers'][0]['symbol'];body=_ir_definition_body(pre,wrapper)
        assert 'icmp ule i64' in body
        mutant=pre.replace(body,body.replace('icmp ule i64','icmp ult i64',1),1)
        reject('different-complete-user-wrapper-preimage',lambda:inline(mutant,unit,optimized=False))
        source='Lemma.Services.Store.ServerRecovery.durabilityBarrier';sys=rows['Lemma.User.Syscall.call']['symbol']
        mutant=changed(pre,source,'@'+sys+'(','@missing_durability_barrier(')
        reject('missing-real-barrier-complete-body',lambda:validate(mutant,unit,optimized=False))
        reject('missing-real-barrier-independent-semantics',lambda:semantic_guards(mutant,unit))
    if unit['role']=='user' and unit['image_key']=='notebook':
        root='Lemma.Applications.Notebook.';source=root+'recoverableFinishRetained'
        original='@'+rows[root+'finishRecord']['symbol']+'(';replacement='@'+rows[root+'startSave']['symbol']+'('
        mutant=changed(pre,source,original,replacement)
        reject('confirmed-original-duplicate-publication',lambda:validate(mutant,unit,optimized=False))
        reject('duplicate-publication-independent-semantics',lambda:semantic_guards(mutant,unit))
        source=root+'recoverablePollRead';original='@'+rows[root+'recoverableFinishRetained']['symbol']+'('
        mutant=changed(pre,source,original,'@missing_original_stage_completion(')
        reject('missing-matching-EOF-completion',lambda:semantic_guards(mutant,unit))
    return result

def backend_exercise(assembly,backend,unit):
    """Mutate actual generated bounds/scale/entry width before any execution."""
    from audit_kernel import _jump_assembly_guard
    selected=[row for row in backend['jump_tables'] if 'Clocked' in canonical(row['source'])]
    if unit['role']!='kernel':return []
    assert len(selected)==4
    result=[]
    for row in selected:
        symbol=row['function'];table=row['symbol'];targets=[e['target_label'] for e in row['entries']];count=row['guard']['bound'];minimum=row['guard']['minimum']
        def check(text,n=count):return _jump_assembly_guard(text,symbol,table,targets,n,minimum,source=canonical(row['source']),configuration=unit['configuration'])
        check(assembly);body=re.search(r'(?m)^'+re.escape(symbol)+r':.*?^\.Lfunc_end\d+:',assembly,re.S)[0];address=body.index('%pcrel_hi('+table+')')
        mutations=[('extent',assembly,count+1)]
        for label,old,new in [('signed-bound','bltu','blt'),('scale','slli','srli')]:
            sites=list(re.finditer(r'\b'+old+r'\b',body[:address]));assert sites
            site=sites[-1];mutations.append((label,assembly.replace(body,body[:site.start()]+new+body[site.end():],1),count))
        load=re.search(r'(?m)^\s*ld\s+\w+, 0\(\w+\)',body[address:]);assert load
        begin,end=address+load.start(),address+load.end();mutations.append(('target-width',assembly.replace(body,body[:begin]+load[0].replace('ld','lw',1)+body[end:],1),count))
        for label,text,n in mutations:
            try:check(text,n)
            except Core0Error as error:result.append({'source':canonical(row['source']),'mutation':label,'status':'REJECTED','reason':str(error)})
            else:raise AssertionError('accepted actual backend guard mutation: '+label)
    return result
