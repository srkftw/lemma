"""Quarantined actual Kernel3 O0 LLVM/metadata mutations.

The caller supplies genuine complete pre/post and unit artifacts. Positive
inputs come from ordinary Lean elaboration, never a fabricated AST or LLVM.
Independent checks mutate the exact read-derived stride and symbol-owned fatal
body, preserving the distinction between full pins and operation/CFG checks.
"""
from __future__ import annotations
import copy
import re
from core0_common import Core0Error
from paper_next import canonical
from audit_kernel import _ir_definition_body
import usercopy_page_words as m


def exercise(pre,post,unit):
    u=unit
    ir=post
    rows={canonical(x['source']):x for x in u['functions']}
    r={'mutations':[]}
    def reject(label,operation):
        try:operation()
        except Core0Error as error:r['mutations'].append({'case':label,'rejection':str(error)})
        else:raise AssertionError('accepted actual O0 mutation: '+label)
    m.validate(pre,u,optimized=False,optimization='O0')
    m.validate(ir,u,optimized=True,optimization='O0')
    for field,value in [('role','user'),('contract_version','core0-kernel-v0.4'),('configuration','lemmasim-initialize'),('managed_policy','lemma-notebook-v2'),('schema_version',2),('artifact_category','kernel-unit')]:
     bad=copy.deepcopy(u);bad[field]=value;reject('metadata/'+field,lambda x=bad:m.validate(ir,x,optimized=True,optimization='O0'))
    for index in [0,1]:
     bad=copy.deepcopy(u);bad['roots'][index]['source']+='.other';reject('root/'+str(index),lambda x=bad:m.validate(ir,x,optimized=True,optimization='O0'))
    bad=copy.deepcopy(u);bad['checked_inline']={};reject('claimed-inlining',lambda:m.validate(ir,bad,optimized=True,optimization='O0'))
    reject('claimed-O2',lambda:m.validate(ir,u,optimized=True,optimization='O2'))
    for short in m.ARGUMENTS:
     source=m.BASE+short;bad=copy.deepcopy(u);bad['functions']=[x for x in bad['functions'] if canonical(x['source'])!=source];reject('missing/'+short,lambda x=bad:m.validate(ir,x,optimized=True,optimization='O0'))
     bad=copy.deepcopy(u);next(x for x in bad['functions'] if canonical(x['source'])==source)['effects'].append('virtual-write');reject('effects/'+short,lambda x=bad:m.validate(ir,x,optimized=True,optimization='O0'))
     body=_ir_definition_body(ir,rows[source]['symbol']);changed=re.sub(r'ret \{ i64, i64 \} [^\n]+','ret { i64, i64 } zeroinitializer',body,count=1);assert changed!=body
     reject('returned-success/'+short,lambda x=ir.replace(body,changed,1):m.validate(x,u,optimized=True,optimization='O0'))
    # Caller mutation leaves all nine exact pinned bodies unchanged.
    source=m.BASE+'copyToUser';body=_ir_definition_body(ir,rows[source]['symbol']);callee=rows[m.BASE+'copyToPages']['symbol'];replacement=rows[m.BASE+'copyFromPages']['symbol'];changed=body.replace('@'+callee+'(', '@'+replacement+'(',1);assert changed!=body
    reject('foreign-copy-from-pages-caller',lambda:m.validate(ir.replace(body,changed,1),u,optimized=True,optimization='O0'))
    fatal=rows['Lemma.User.ABI.kernelFatal']['symbol'];body=_ir_definition_body(ir,fatal);changed=body.replace('ret i8 -1','ret i8 -2',1);assert changed!=body
    definition=re.search(r'(?ms)^define[^\n]*@'+re.escape(fatal)+r'\([^\n]*\)[^\n]*\{\n.*?^\}',ir);assert definition and definition[0].count(body)==1
    changed_ir=ir[:definition.start()]+definition[0].replace(body,changed,1)+ir[definition.end():]
    reject('actual-fatal-scalar254',lambda:m.validate(changed_ir,u,optimized=True,optimization='O0'))
    for short in m.KERNEL3_POST:
     source=m.BASE+short;body=m.operation_view(_ir_definition_body(ir,rows[source]['symbol']));block=short!='copyWord';pairs=8 if block else 1
     check=lambda text:m._kernel3_checked_pairs(text,rows,pairs=pairs,block=block,unoptimized=True)
     check(body)
     read=rows['Lemma.Kernel.Memory.Access.read64']['symbol'];write=rows['Lemma.Kernel.Memory.Access.write64']['symbol']
     reads=list(re.finditer(r'(?m)^.*call \{ i64, i64 \} @'+re.escape(read)+r'\(([^\n]*)\)$',body));writes=list(re.finditer(r'(?m)^.*call \{ i64, i64 \} @'+re.escape(write)+r'\(([^\n]*)\)$',body));assert len(reads)==len(writes)==pairs
     def replace(line,new):assert new!=line;return body.replace(line,new,1)
     for index,line in enumerate(reads):reject(short+'/read-address/'+str(index),lambda text=replace(line[0],re.sub(r'\(i64 [^)]+\)$','(i64 0)',line[0])):check(text))
     for index,line in enumerate(writes):reject(short+'/write-value/'+str(index),lambda text=replace(line[0],re.sub(r', i64 %[-\w.]+\)$',', i64 0)',line[0])):check(text))
     for index,match in enumerate(re.finditer(r'(%[-\w.]+) = icmp eq i8 (%[-\w.]+), 0',body)):
      reject(short+'/status-test/'+str(index),lambda text=replace(match[0],match[0].replace('icmp eq','icmp ne')):check(text))
      branch=re.search(r'br i1 '+re.escape(match[1])+r', label %([-\w.]+), label %([-\w.]+)',body);assert branch
      reject(short+'/status-edge/'+str(index),lambda text=replace(branch[0],'br i1 '+match[1]+', label %'+branch[2]+', label %'+branch[1]):check(text))
     for index in range(pairs):
      a,b=reads[index][0],writes[index][0];changed=body.replace(a,'NEGATIVE_SWAP_MARKER',1).replace(b,a,1).replace('NEGATIVE_SWAP_MARKER',b,1);reject(short+'/read-write-order/'+str(index),lambda text=changed:check(text))
     if block:
      definitions=dict(re.findall(r'(?m)^[ \t]*(%[-\w.]+) = ([^\n]+)$',body));seen=set();multiplications=[]
      def visit(value):
       if value in seen or value not in definitions:return
       seen.add(value);instruction=definitions[value]
       if re.fullmatch(r'mul i64 %[-\w.]+, 64',instruction):multiplications.append(instruction)
       for operand in re.findall(r'%[-\w.]+',instruction):visit(operand)
      visit(reads[0][1][4:]);assert len(multiplications)==1
      mul=multiplications[0];reject(short+'/read-derived-block-stride32',lambda text=replace(mul,mul.replace(', 64',', 32')):check(text))
     final=re.findall(r'phi i8 \[ 0, %[-\w.]+ \], \[ %[-\w.]+, %[-\w.]+ \]',body);assert final
     reject(short+'/final-status-nonzero',lambda text=replace(final[0],final[0].replace('[ 0,','[ 1,')):check(text))
    # Original bounded callback and tail budgets remain independent gates.
    source=m.BASE+'copyPageWords';body=_ir_definition_body(ir,rows[source]['symbol'])
    for bound in [64,7]:
     pattern='icmp ule i32';site=re.search(pattern+r' %[-\w.]+, '+str(bound),body);assert site
     changed=body.replace(site[0],site[0].replace(', '+str(bound),', '+str(bound+1)),1)
     reject('budget/'+str(bound),lambda text=ir.replace(body,changed,1):m.validate(text,u,optimized=True,optimization='O0'))
    return r['mutations']
