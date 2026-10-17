"""Quarantined mutations of a supplied genuine Wire compiler corpus.

No LLVM fixture is imported into a target backend or treated as a successful
source compilation. The ordinary qualifier must supply actual exported files.
"""
from copy import deepcopy
import re
from core0_common import Core0Error
from paper_next import canonical
from paper_wire import validate
from audit_kernel import _ir_definition_body
from lemmasim_readonly import validate_lookup


def exercise(pre, post, unit):
    validate(pre,unit,optimized=False)
    validate(post,unit,optimized=True)
    rows={canonical(row['source']):row for row in unit['functions']}
    results=[]
    def reject(label,ir,u,optimized,check=validate):
        try:
            if check is validate:check(ir,u,optimized=optimized)
            else:check(ir,u)
        except Core0Error as error:
            results.append({'mutation':label,'status':'REJECTED','reason':str(error)})
        else:raise AssertionError('accepted actual-artifact mutant: '+label)
    def body_change(ir,suffix,old,new):
        selected=[row for source,row in rows.items() if source.endswith(suffix)]
        assert len(selected)==1,suffix
        body=_ir_definition_body(ir,selected[0]['symbol'])
        assert old in body,(suffix,old)
        changed=body.replace(old,new,1)
        assert ir.count(body)==1
        return ir.replace(body,changed)
    for field,value in [('configuration','lemmasim-silicon-usb-next-bulk-notebook'),
                        ('contract_version','core0-kernel-v0.7'),('role','user')]:
        u=deepcopy(unit);u[field]=value;reject('wrong-'+field,pre,u,False)
    u=deepcopy(unit);u['functions'].append(deepcopy(u['functions'][0]));reject('duplicate-source',pre,u,False)
    u=deepcopy(unit);u['functions']=[r for r in u['functions'] if not canonical(r['source']).endswith('.wireStep')];reject('missing-scheduler',pre,u,False)
    u=deepcopy(unit);r=next(r for r in u['functions'] if canonical(r['source']).endswith('.leafPropertyWire'));r['effects'].append('mmio-write');reject('broadened-effects',pre,u,False)
    u=deepcopy(unit);u['functions'].append({'source':'Lemma.Boot.ProductExecuted.nvBase','symbol':'forged_nv','args':[],'effects':[]});reject('product-NV-authority',pre,u,False)
    for suffix,old,new,label in [('.leafPropertyWire','i64 0, i64 256','i64 0, i64 128','decoded-boundary-duplicate-flag'),
            ('.wireUSBStep','i64 11','i64 10','wrong-scheduler-binding'),
            ('.geometryWire',', 15',', 31','wrong-features'),
            ('.leafPropertyWire','i64 48000000','i64 24000000','wrong-sample-rate'),
            ('.leafPropertyWire','i64 12000000','i64 6000000','wrong-bit-rate')]:
        reject(label,body_change(pre,suffix,old,new),unit,False)
    reject('unsigned-index-bound',body_change(post,'.literalWordWire','icmp ult i64 %arg1, 3','icmp ult i64 %arg1, 4'),unit,True)
    reject('independent-unsigned-index-bound',body_change(post,'.literalWordWire','icmp ult i64 %arg1, 3','icmp ult i64 %arg1, 4'),unit,True,validate_lookup)
    pool='i64 7525563774295434604'
    assert pool in post
    mutated=post.replace(pool,'i64 7525563774295434605',1)
    reject('UTF8-content',mutated,unit,True)
    reject('independent-UTF8-content',mutated,unit,True,validate_lookup)
    # An extra ordinary kernel caller must not borrow new device authority.
    target=rows['Lemma.Platform.LemmaSim.NotebookKernel.wireStep']['symbol']
    u=deepcopy(unit);u['functions'].append({'source':'Lemma.Kernel.UntrustedBorrow','symbol':'forged_borrow','args':[],'effects':[]})
    ir=pre+'\ndefine { i64, i64 } @forged_borrow() {\nentry:\n %x = call { i64, i64 } @'+target+'(i64 11)\n ret { i64, i64 } %x\n}\n'
    reject('unauthorized-caller',ir,u,False)
    return results
