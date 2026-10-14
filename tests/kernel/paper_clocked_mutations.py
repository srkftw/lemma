"""Quarantined mutations supplied only with a genuine Clocked kernel corpus."""
from copy import deepcopy
import re
from core0_common import Core0Error
from paper_next import canonical
from paper_clocked import validate,literal_aliases
from audit_kernel import _ir_definition_body
from lemmasim_readonly import validate_lookup

def exercise(pre,post,unit):
    validate(pre,unit,optimized=False);validate(post,unit,optimized=True)
    rows={canonical(row['source']):row for row in unit['functions']};results=[]
    def reject(label,ir,u,optimized,check=validate):
        try:
            if check is validate:check(ir,u,optimized=optimized)
            else:check(ir,u)
        except Core0Error as error:results.append({'mutation':label,'status':'REJECTED','reason':str(error)})
        else:raise AssertionError('accepted actual-artifact mutant: '+label)
    def body_change(ir,suffix,old,new):
        selected=[row for source,row in rows.items() if source.endswith(suffix)]
        assert len(selected)==1,suffix
        body=_ir_definition_body(ir,selected[0]['symbol']);assert old in body,(suffix,old)
        assert ir.count(body)==1
        return ir.replace(body,body.replace(old,new,1))
    for field,value in [('configuration','lemmasim-silicon-usb-wire-bulk-notebook'),('contract_version','core0-kernel-v0.7'),('role','user')]:
        u=deepcopy(unit);u[field]=value;reject('wrong-'+field,pre,u,False)
    u=deepcopy(unit);u['functions'].append(deepcopy(u['functions'][0]));reject('duplicate-source',pre,u,False)
    u=deepcopy(unit);u['functions']=[r for r in u['functions'] if not canonical(r['source']).endswith('.clockedStep')];reject('missing-scheduler',pre,u,False)
    u=deepcopy(unit);next(r for r in u['functions'] if canonical(r['source']).endswith('.leafPropertyClocked'))['effects'].append('mmio-write');reject('broadened-effects',pre,u,False)
    u=deepcopy(unit);u['functions'].append({'source':'Lemma.Boot.ProductExecuted.nvBase','symbol':'forged_nv','args':[],'effects':[]});reject('product-NV-authority',pre,u,False)
    facts=[(0,256),(2,512),(48000000,1024),(12000000,2048),(1,4096),(100000000,8192),(1,16384),(128,32768),(67,65536)]
    for value,flag in facts:
        old='i64 '+str(value)+', i64 '+str(flag)
        reject('wrong-property-value-'+str(flag),body_change(pre,'.leafPropertyClocked',old,'i64 '+str(value+1)+', i64 '+str(flag)),unit,False)
    reject('decoded-boundary-duplicate-flag',body_change(pre,'.leafPropertyClocked','i64 0, i64 256','i64 0, i64 128'),unit,False)
    reject('wrong-scheduler-binding',body_change(pre,'.clockedUSBStep','i64 13','i64 11'),unit,False)
    reject('wrong-features',body_change(pre,'.geometryClocked',', 15',', 31'),unit,False)
    for extent in (3,4):
        old='icmp ult i64 %arg1, '+str(extent)
        ir=body_change(post,'.literalWordClocked',old,'icmp ult i64 %arg1, '+str(extent+1))
        reject('unsigned-bound-'+str(extent),ir,unit,True)
        reject('independent-unsigned-bound-'+str(extent),ir,unit,True,validate_lookup)
    aliases=literal_aliases(post,unit)
    for extent in (3,4):
        pools=[line for line in post.splitlines() if any('@'+name+' =' in line for name in aliases) and '['+str(extent)+' x i64]' in line]
        assert pools
        line=pools[0];value=re.search(r'i64 (-?\d+)',line)[1]
        changed=line.replace('i64 '+value,'i64 '+str(int(value)+1),1)
        ir=post.replace(line,changed,1)
        reject('UTF8-content-'+str(extent),ir,unit,True)
        reject('independent-UTF8-content-'+str(extent),ir,unit,True,validate_lookup)
        ir=post.replace(line,line.replace('['+str(extent)+' x i64]','['+str(extent+1)+' x i64]',1),1)
        reject('UTF8-extent-'+str(extent),ir,unit,True)
    identity=rows['Lemma.Platform.LemmaSim.DescriptorDTB.clockedUSBIdentity']['symbol']
    line=next(line for line in post.splitlines() if line.startswith('@switch.table.'+identity+' ='))
    ir=post.replace(line,line.replace('i64 48000000','i64 24000000',1),1)
    reject('actual-readonly-identity-value',ir,unit,True)
    reject('independent-readonly-identity-value',ir,unit,True,validate_lookup)
    reject('independent-readonly-identity-value',body_change(post,'.clockedUSBIdentity','icmp ult i64 %arg0, 6','icmp ult i64 %arg0, 7'),unit,True,validate_lookup)
    target=rows['Lemma.Platform.LemmaSim.NotebookKernel.clockedStep']['symbol']
    u=deepcopy(unit);u['functions'].append({'source':'Lemma.Kernel.UntrustedBorrow','symbol':'forged_borrow','args':[],'effects':[]})
    ir=pre+'\ndefine { i64, i64 } @forged_borrow() {\nentry:\n %x = call { i64, i64 } @'+target+'(i64 13)\n ret { i64, i64 } %x\n}\n'
    reject('unauthorized-caller',ir,u,False)
    return results

def backend_exercise(assembly,backend,unit):
    """Actual generated branch guards; mutated text never enters the backend."""
    from audit_kernel import _jump_assembly_guard
    result=[]
    selected=[r for r in backend['jump_tables'] if 'Clocked' in canonical(r['source'])]
    assert len(selected)==4
    for row in selected:
        symbol=row['function'];table=row['symbol'];targets=[e['target_label'] for e in row['entries']]
        count=row['guard']['bound'];minimum=row['guard']['minimum']
        def check(text,n=count):
            return _jump_assembly_guard(text,symbol,table,targets,n,minimum,source=canonical(row['source']),configuration=unit['configuration'])
        check(assembly)
        body=re.search(r'(?m)^'+re.escape(symbol)+r':.*?^\.Lfunc_end\d+:',assembly,re.S)[0]
        mutations=[('extent',assembly,count+1)]
        address=body.index('%pcrel_hi('+table+')')
        for label,old,new in [('signed-bound','bltu','blt'),('scale','slli','srli')]:
            sites=list(re.finditer(r'\b'+old+r'\b',body[:address]));assert sites
            site=sites[-1]
            changed=body[:site.start()]+new+body[site.end():]
            mutations.append((label,assembly.replace(body,changed,1),count))
        # Change only the indexed jump target load, not unrelated caller spills.
        load=re.search(r'(?m)^\s*ld\s+\w+, 0\(\w+\)',body[address:])
        assert load
        begin,end=address+load.start(),address+load.end()
        changed=body[:begin]+load[0].replace('ld','lw',1)+body[end:]
        mutations.append(('target-width',assembly.replace(body,changed,1),count))
        for label,text,n in mutations:
            try:check(text,n)
            except Core0Error as error:result.append({'source':canonical(row['source']),'mutation':label,'status':'REJECTED','reason':str(error)})
            else:raise AssertionError('accepted actual backend guard mutant: '+row['source']+'/'+label)
    return result
