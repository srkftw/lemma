"""Negative-only checks over genuine ordinary entry-borrow LLVM artifacts.

Call exercise with actual checked pre/post outputs, or use the artifact
runner. No fabricated positive AST/LLVM is constructed and no target executes.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from audit_kernel import _ir_definition_body
from paper_next import canonical
from core0_common import Core0Error
import task_entry_borrow as m


def exercise(pre,post,unit):
    u=unit
    rows={canonical(x['source']):x for x in u['functions']}
    r={'status':'FAIL','cases':[],'positives':[],
       'scope':'Negative-only mutations of complete genuine ordinary LLVM/correspondence; no fabricated positive compiler input'}
    for phase,file in [('pre','entry.ll'),('post','entry.opt.ll')]:
     ir=pre if phase=='pre' else post;r['positives'].append(m.validate_component(ir,u,optimized=phase=='post'))
     cases=[]
     for field,value in [('role','user'),(('contract_version' if 'contract_version' in u else 'profile'),'core0-kernel-v0.3')]:
      wrong=copy.deepcopy(u);wrong[field]=value;cases.append((field,ir,wrong))
     for source in m.SIGNATURES:
      wrong=copy.deepcopy(u);wrong['functions']=[x for x in wrong['functions'] if canonical(x['source'])!=source];cases.append(('missing/'+source,ir,wrong))
      wrong=copy.deepcopy(u);next(x for x in wrong['functions'] if canonical(x['source'])==source)['effects']=['corrupt-effect'];cases.append(('effects/'+source,ir,wrong))
      body=_ir_definition_body(ir,rows[source]['symbol']);typ='i1' if re.search(r'ret i1 ',body) else 'i64' if re.search(r'ret i64 ',body) else '{ i64, i64 }'
      changed=re.sub(r'ret '+re.escape(typ)+r' [^\n]+','ret '+typ+' zeroinitializer',body,count=1);assert changed!=body
      cases.append(('returned-success/'+source,ir.replace(body,changed,1),u))
     # Change an actual old caller to call the new context helper, leaving all
     # nineteen guarded bodies untouched; this exercises exhaustive incoming.
     oldbody=_ir_definition_body(ir,rows['Lemma.Kernel.Task.context']['symbol'])
     oldlookup=rows['Lemma.Kernel.Task.lookup']['symbol'];newlookup=rows[m.FAMILY[0]]['symbol']
     changed=oldbody.replace('@'+oldlookup+'(', '@'+newlookup+'(',1);assert changed!=oldbody
     cases.append(('additional-old-context-caller',ir.replace(oldbody,changed,1),u))
     for label,changed,unit in cases:
      try:m.validate_component(changed,unit,optimized=phase=='post')
      except Core0Error as e:r['cases'].append({'phase':phase,'layer':'complete','label':label,'rejection':str(e)})
      else:raise AssertionError('accepted actual mutation:'+phase+'/'+label)
     body=_ir_definition_body(ir,rows[m.FAMILY[2]]['symbol']);gate_rows=dict(rows);gate_rows['_genuine_ir']={'ir':ir}
     c=rows[m.FAMILY[0]]['symbol'];disp=rows[m.FAMILY[1]]['symbol']
     mut=[]
     for callee,label in [(c,'checked-context-descriptor'),(disp,'dispatch-descriptor')]:
      changed=body.replace('@'+callee+'(i64 %arg0)','@'+callee+'(i64 %arg1)',1);assert changed!=body;mut.append((label,changed))
     if phase=='post':
      changed=body.replace(', -1984',', -1976',1);assert changed!=body;mut.append(('root-offset',changed))
      ctx=re.search(r'(%[-\w.]+) = extractvalue \{ i64, i64 \} %[-\w.]+, 1',body)[1]
      changed=body.replace('@lemma_exec_enter_user(i64 '+ctx+')','@lemma_exec_enter_user(i64 %arg0)',1);assert changed!=body;mut.append(('unvalidated-entry-context',changed))
      changed=body.replace('action.if.then.30:', 'action.if.then.30:\n  %negative.escape = add i64 '+ctx+', 0',1);assert changed!=body;mut.append(('borrow-after-entry',changed))
      first=re.search(r'br i1 (%[-\w.]+), label %([-\w.]+), label %([-\w.]+)',body);changed=body.replace(first[0],'br i1 '+first[1]+', label %'+first[3]+', label %'+first[2],1);mut.append(('context-failure-edge-inverted',changed))
     for label,changed in mut:
      try:m.checked_entry_data_flow(changed,gate_rows,optimized=phase=='post')
      except Core0Error as e:r['cases'].append({'phase':phase,'layer':'independent dataflow/CFG','label':label,'rejection':str(e)})
      else:raise AssertionError('accepted independent mutation:'+phase+'/'+label)
    for cfg in ['lemmasim-silicon-closure-bulk-notebook','lemmasim-notebook','lemmasim-silicon-usb-clocked-closure-retry-bulk-notebook']:
     wrong=copy.deepcopy(u);wrong['configuration']=cfg
     try:m.validate_if_present(pre,wrong,optimized=False)
     except Core0Error as e:r['cases'].append({'layer':'selected authority','label':'wrong-config/'+cfg,'rejection':str(e)})
     else:raise AssertionError('unknown entry2 config accepted')
    r.update(status='PASS_REFINED_ENTRY_COMPLETE_AND_INDEPENDENT_MUTANTS',rejections=len(r['cases']))
    return r


def exercise_entry_callers(pre,unit,legacy_pre,legacy_unit):
    """Compose the actual stack/poll/capture caller guards over genuine units."""
    import audit_kernel as audit
    import ipc_poll_borrow as ipc
    from check_kernel_ipc_poll_borrow import mutations as polling_mutations
    report={'status':'FAIL','mutations':[]}
    def reject(label,operation,expected=None):
        try:operation()
        except Core0Error as error:
            if expected is not None and str(error)!=expected:
                raise AssertionError('wrong independent incoming rejection: '+label+': '+str(error))
            report['mutations'].append({'case':label,'rejection':str(error)})
        else:raise AssertionError('accepted genuine incoming mutation: '+label)
    report['stack']=audit.validate_fresh_descriptor_helpers(unit,pre)
    report['poll']=ipc.validate_reachable_helpers(unit,pre)
    report['capture']=audit.validate_task_capture_borrow(unit,pre)
    historical={'Lemma.Kernel.Task.lookup','Lemma.Kernel.Task.contextAt','Lemma.Kernel.Task.pollIPCStep'}
    added={'Lemma.Kernel.Task.entryContextV2','Lemma.Kernel.Task.entryDispatchesV2'}
    if ipc.task_lookup_record_allowed_callers(unit,pre)!=historical|added:
        raise AssertionError('new exact Task.lookupRecord incoming set differs')
    report['polling_body_mutants']=polling_mutations(unit,pre)
    for label,field,value in [('config','configuration','lemmasim-silicon-closure-bulk-initialize'),
                             ('profile','contract_version','core0-kernel-v0.3'),('role','role','user')]:
        wrong=copy.deepcopy(unit);wrong[field]=value
        reject('poll-authority/'+label,lambda u=wrong:ipc.validate_reachable_helpers(u,pre))
        reject('capture-authority/'+label,lambda u=wrong:audit.validate_task_capture_borrow(u,pre))
    rows={canonical(row['source']):row['symbol'] for row in unit['functions']}
    source='Lemma.Kernel.Console.record';body=_ir_definition_body(pre,rows[source])
    for helper,gate in [('Lemma.Kernel.Process.validateStackAt','stack helper has an unapproved caller'),
                        ('Lemma.Kernel.Task.lookupRecord','IPC polling borrow has an unvalidated lookupRecord caller')]:
        changed=re.sub(r'(?m)^(  ret [^\n]+)$',lambda match:
            '  %negative.incoming = call { i64, i64 } @'+rows[helper]+'(i64 0)\n'+match[1],body,count=1)
        if changed==body:raise AssertionError('actual incoming negative lacks its return anchor')
        mutated=pre.replace(body,changed,1)
        operation=(lambda ir=mutated:audit.validate_fresh_descriptor_helpers(unit,ir)) if helper.endswith('validateStackAt') else (lambda ir=mutated:ipc.validate_reachable_helpers(unit,ir))
        reject('foreign/'+helper,operation,gate)
    report['legacy_stack']=audit.validate_fresh_descriptor_helpers(legacy_unit,legacy_pre)
    report['legacy_poll']=ipc.validate_reachable_helpers(legacy_unit,legacy_pre)
    report['legacy_capture']=audit.validate_task_capture_borrow(legacy_unit,legacy_pre)
    if ipc.task_lookup_record_allowed_callers(legacy_unit,legacy_pre)!=historical:
        raise AssertionError('historical incoming Task.lookupRecord route changed')
    report['status']='PASS_GENUINE_ENTRY2_COMPOSED_STACK_POLL_CAPTURE_INCOMING_GUARDS'
    return report



def exercise_selected(pre,post,unit):
    """Complete and independent boot tests over one actual selected role."""
    u=unit
    initialization=unit['configuration'].endswith('-initialize')
    rows={canonical(x['source']):x for x in u['functions']}
    r={'mutations':[]}
    def reject(label,operation):
        try:operation()
        except Core0Error as error:r['mutations'].append({'case':label,'rejection':str(error)})
        else:raise AssertionError('accepted actual selected mutation: '+label)
    for optimized,file in [(False,'program.ll'),(True,'program.opt.ll')]:
     ir=post if optimized else pre;phase='post' if optimized else 'pre';prefix=unit['configuration']+'/'+phase+'/'
     m.validate_if_present(ir,u,optimized=optimized)
     for field,value in [('role','user'),('contract_version','core0-kernel-v0.3'),('schema_version',2),('managed_policy','lemma-notebook-v1'),('artifact_category','kernel-unit'),('configuration','lemmasim-silicon-closure-entry2-bulk-'+('notebook' if initialization else 'initialize'))]:
      bad=copy.deepcopy(u);bad[field]=value;reject(prefix+field,lambda x=bad:m.validate_if_present(ir,x,optimized=optimized))
     for field in ['contract_version','silicon_profile']:
      bad=copy.deepcopy(u);bad['software_deployment'][field]='foreign';reject(prefix+'software/'+field,lambda x=bad:m.validate_if_present(ir,x,optimized=optimized))
     for index in [0,1]:
      bad=copy.deepcopy(u);bad['roots'][index]['source']+='.other';reject(prefix+'root/'+str(index),lambda x=bad:m.validate_if_present(ir,x,optimized=optimized))
     selected=set(m.BOOT_SIGNATURES)&set(rows)
     for source in selected:
      bad=copy.deepcopy(u);bad['functions']=[x for x in bad['functions'] if canonical(x['source'])!=source];reject(prefix+'missing/'+source,lambda x=bad:m.validate_if_present(ir,x,optimized=optimized))
      bad=copy.deepcopy(u);next(x for x in bad['functions'] if canonical(x['source'])==source)['effects'].append('virtual-write');reject(prefix+'effects/'+source,lambda x=bad:m.validate_if_present(ir,x,optimized=optimized))
      body=_ir_definition_body(ir,rows[source]['symbol']);changed=re.sub(r'ret \{ i64, i64 \} [^\n]+','ret { i64, i64 } zeroinitializer',body,count=1);assert changed!=body
      reject(prefix+'returned-success/'+source,lambda x=ir.replace(body,changed,1):m.validate_if_present(x,u,optimized=optimized))
     old='Lemma.Platform.LemmaSim.NotebookKernel.step';old_step='Lemma.Kernel.Scheduler.step';body=_ir_definition_body(ir,rows[old]['symbol']);changed=body.replace('@'+rows[old_step]['symbol']+'(', '@'+rows[m.FAMILY[3]]['symbol']+'(',1);assert changed!=body
     reject(prefix+'additional-old-power-caller',lambda:m.validate_if_present(ir.replace(body,changed,1),u,optimized=optimized))
     selected_root=m.CONFIGURATIONS[u['configuration']];boot='Lemma.Platform.LemmaSim.NotebookKernel.bootSelectedEntryV2';body=_ir_definition_body(ir,rows[selected_root]['symbol'])
     original='@'+rows[boot]['symbol']+'(i64 '+str(int(initialization))+', i64 0, i64 3, i64 0)';assert original in body
     for label,arguments in [('initialization','i64 '+str(int(not initialization))+', i64 0, i64 3, i64 0'),('isolation','i64 '+str(int(initialization))+', i64 1, i64 3, i64 0'),('hardware','i64 '+str(int(initialization))+', i64 0, i64 2, i64 0'),('arithmetic','i64 '+str(int(initialization))+', i64 0, i64 3, i64 1')]:
      changed=body.replace(original,'@'+rows[boot]['symbol']+'('+arguments+')',1)
      reject(prefix+'independent-root/'+label,lambda x=ir.replace(body,changed,1):m.validate_boot_operations(x,u))
     power='Lemma.Platform.LemmaSim.NotebookKernel.powerStepEntryV2';body=_ir_definition_body(ir,rows[power]['symbol']);changed=body.replace('@'+rows[m.FAMILY[3]]['symbol']+'(', '@'+rows[old_step]['symbol']+'(',1);assert changed!=body
     reject(prefix+'independent-old-scheduler-replacement',lambda:m.validate_boot_operations(ir.replace(body,changed,1),u))
    return r['mutations']

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component',type=Path,required=True,help='Actual entry.ll/entry.opt.ll/entry-unit.json directory')
    parser.add_argument('--legacy',type=Path,required=True,help='Actual historical program.ll/program.opt.ll/unit.json directory')
    parser.add_argument('--work-dir',type=Path,required=True)
    args=parser.parse_args()
    out=args.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'build'):
        parser.error('unused ignored build output required')
    out.mkdir(parents=True)
    start=time.monotonic();r={'status':'FAIL'}
    consumed={}
    def read(path):
        data=path.read_bytes();consumed[str(path.resolve())]=hashlib.sha256(data).hexdigest()
        return data.decode()
    try:
        d=args.component.resolve();old=args.legacy.resolve()
        unit=json.loads(read(d/'entry-unit.json'))
        r=exercise(read(d/'entry.ll'),read(d/'entry.opt.ll'),unit)
        legacy=json.loads(read(old/'unit.json'))
        for optimized,file in [(False,'program.ll'),(True,'program.opt.ll')]:
            if m.validate_if_present(read(old/file),legacy,optimized=optimized) is not None:
                raise AssertionError('historical actual image unexpectedly selected Entry2')
        for name,digest in consumed.items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:
                raise AssertionError('actual mutation input changed: '+name)
        r['legacy_route']='PASS_NONE_OLD_PRE_POST'
    except BaseException as error:
        r.update(status='FAIL',error=repr(error))
    finally:
        r.update(seconds=time.monotonic()-start,helper_sha256=hashlib.sha256((ROOT/'scripts/task_entry_borrow.py').read_bytes()).hexdigest(),actual_inputs=consumed)
        (out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
    print(r['status'],r.get('rejections'),r['seconds'])
    return 0 if r['status'].startswith('PASS') else 1


if __name__=='__main__':raise SystemExit(main())
