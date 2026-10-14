#!/usr/bin/env python3
"""Actual emitted-corpus failures for same-Action IPC Receive/Reply borrowing."""
import argparse,copy,json,re,time
from pathlib import Path
from audit_kernel import _ir_definition_body
from core0_common import Core0Error,sha256,write_json
from ipc_call_borrow import validate_ipc_call_borrow

def main():
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--component',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();started=time.monotonic();base=args.component.resolve()
    out=args.output.resolve();root=Path(__file__).resolve().parents[1]
    if out.exists() or not out.is_relative_to(root/'build/kernel'):parser.error('unused build/kernel report required')
    report={'status':'FAIL','scope':'exact genuine emitted-corpus source/ABI/caller failures; no guest timing or whole-image execution claim'}
    try:
        unit=json.loads((base/'production-unit.json').read_text());ir=(base/'production.ll').read_text()
        report['artifacts']={name:sha256(base/name) for name in ('production-unit.json','production.ll','production.opt.ll','production.o')}
        report['observer_sources']={name:sha256(root/'scripts'/name) for name in ('check_ipc_rpc_guards.py','ipc_rpc_borrow.py','ipc_call_borrow.py','audit_kernel.py','core0_common.py')}
        positive=validate_ipc_call_borrow(unit,ir)
        if len(positive.get('rpc_borrow',{}).get('pinned_genuine_shapes',{}))!=16:raise Core0Error('complete actual Receive/Reply corpus required')
        rows={re.sub(r'^_private\..*?\.[0-9]+\.','',r['source']):r for r in unit['functions']}
        negative=[]
        def reject(label,metadata,code):
            try:validate_ipc_call_borrow(metadata,code)
            except Core0Error as error:negative.append({'case':label,'rejection':str(error)});return
            raise Core0Error('actual corpus mutation was accepted: '+label)
        altered=copy.deepcopy(unit);altered['role']='user';reject('wrong role',altered,ir)
        altered=copy.deepcopy(unit)
        next(r for r in altered['functions'] if r['source']==rows['Lemma.Kernel.IPCStorage.completeAt']['source'])['effects'].append('firmware-call')
        reject('new borrowed storage effect',altered,ir)
        altered=copy.deepcopy(unit)
        next(r for r in altered['functions'] if r['source']==rows['Lemma.Kernel.IPC.replyLocal']['source'])['args'][0]='u8'
        reject('changed descriptor ABI',altered,ir)
        for source,old,new,label in (
                ('Lemma.Kernel.IPC.receiveWithLimit','i64 %arg1','i64 %arg0','wrong fresh descriptor'),
                ('Lemma.Kernel.IPC.receiveHeadAt','i64 %arg1','i64 0','changed checked transaction'),
                ('Lemma.Kernel.IPCStorage.queueCopyToUserAt','UserCopy.validateWrite','UserCopy.validateRead','lost write preflight')):
            symbol=rows[source]['symbol'];body=_ir_definition_body(ir,symbol)
            if old.startswith('UserCopy.'):
                old=rows['Lemma.Kernel.Memory.'+old]['symbol'];new=rows['Lemma.Kernel.Memory.'+new]['symbol']
            if old not in body:raise Core0Error('actual targeted mutation anchor absent')
            reject(label,unit,ir.replace(body,body.replace(old,new,1),1))
        altered=copy.deepcopy(unit);missing=rows['Lemma.Kernel.IPCStorage.takeAt']['source']
        altered['functions']=[r for r in altered['functions'] if r['source']!=missing]
        reject('incomplete borrowed closure',altered,ir)
        target=rows['Lemma.Kernel.IPCStorage.completeAt']['symbol']
        rogue='ipc_rpc_unapproved_caller'
        altered=copy.deepcopy(unit);altered['functions'].append({'source':'Lemma.Kernel.Unapproved.borrow',
            'symbol':rogue,'args':['u64']*7,'effects':['checked-access','physical-read','physical-write']})
        arguments=', '.join('i64 %arg'+str(i) for i in range(7))
        call='\ndefine { i64, i64 } @'+rogue+'('+arguments+') nounwind noinline "disable-tail-calls"="true" {\nentry:\n  %r = call { i64, i64 } @'+target+'('+arguments+')\n  ret { i64, i64 } %r\n}\n'
        reject('unapproved additional helper caller',altered,ir+call)
        report.update(status='PASS_GENUINE_IPC_RPC_BORROW_GUARDS',positive=positive,negative_cases=negative)
    except BaseException as error:report['error']=repr(error);raise
    finally:report['wall_seconds']=time.monotonic()-started;write_json(out,report)
    print(report['status'],len(report['negative_cases']))
if __name__=='__main__':main()
