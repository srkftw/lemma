"""Closed same-Action IPC Receive/Reply base reuse; genuine source/CFG observer.

Independent Action equivalence and fault checks qualify the pinned bodies.
This helper supplies no cross-syscall, User or arbitrary Kernel alias authority.
"""
import hashlib,re
from audit_kernel import (_ir_definition_body,parse_definitions_and_calls,
    _local_checked_result,_local_arithmetic,_local_call_arguments,validate_failed_call_gate)
from core0_common import Core0Error

PINNED = {'Lemma.Kernel.IPC.receiveWithLimit': {'args': ['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                       'effects': ['checked-access',
                                                   'firmware-call',
                                                   'io-order',
                                                   'machine-state',
                                                   'physical-read',
                                                   'physical-write'],
                                       'shape': '0f3a11717deb67f28c5f34a4b5efd6d1c7e09850afbe1a7358b9417892666466'},
 'Lemma.Kernel.IPC.clearAt': {'args': ['u64', 'u64', 'u64', 'u8', 'u64'],
                              'effects': ['checked-access', 'physical-read', 'physical-write'],
                              'shape': '859691593ba39bd33bf39f507bef89c19fc041593807fd8e5940da8cbf592902'},
 'Lemma.Kernel.IPC.finishAt': {'args': ['u64', 'u64', 'u64', 'u8', 'u64'],
                               'effects': ['checked-access', 'physical-read', 'physical-write'],
                               'shape': '187474565c1dff80ad8ec3578fae6fe1fb7f88e653da493724f7e3b180361fe6'},
 'Lemma.Kernel.IPC.copyHeadAt': {'args': ['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                 'effects': ['checked-access', 'physical-read', 'physical-write'],
                                 'shape': 'd15849dd269252de7cdf0082fde6ef18b8fb23135cdf8be844b1304f8c4d9c7f'},
 'Lemma.Kernel.IPC.receiveHeadAt': {'args': ['u64', 'u64', 'u64', 'u64'],
                                    'effects': ['checked-access',
                                                'firmware-call',
                                                'io-order',
                                                'machine-state',
                                                'physical-read',
                                                'physical-write'],
                                    'shape': 'd861659cc2368b86393ff6930324d67b669949b7d1da75ba5d532b4b96c04331'},
 'Lemma.Kernel.IPC.receiveStepAt': {'args': ['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                    'effects': ['checked-access',
                                                'firmware-call',
                                                'io-order',
                                                'machine-state',
                                                'physical-read',
                                                'physical-write'],
                                    'shape': '854fdf9d58dd55b932901ea054b6cf253942054cae34346c27a63a9f75b36383'},
 'Lemma.Kernel.IPC.receivePacketAt': {'args': ['u64', 'u64', 'u64', 'u64'],
                                      'effects': ['checked-access',
                                                  'firmware-call',
                                                  'io-order',
                                                  'machine-state',
                                                  'physical-read',
                                                  'physical-write'],
                                      'shape': '63d2c3dcb17c5608a755b021273805e4b5a5df71e14828a955819e7ac3f2bc88'},
 'Lemma.Kernel.IPC.receiveResultAt': {'args': ['u64', 'u64', 'u64', 'u64'],
                                      'effects': ['checked-access', 'physical-read', 'physical-write'],
                                      'shape': '5a7ce610a5079355954e5607d6fe06e8d84eb10ebe5314102b4f698da282b358'},
 'Lemma.Kernel.IPC.beginReceiveAt': {'args': ['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                     'effects': ['checked-access',
                                                 'firmware-call',
                                                 'io-order',
                                                 'machine-state',
                                                 'physical-read',
                                                 'physical-write'],
                                     'shape': 'd50f2fab97e0c6eb296803f54ae0cdc3e3d6dda47f7f32d09bf38d8e9233ef42'},
 'Lemma.Kernel.IPC.stageReplyAt': {'args': ['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                   'effects': ['checked-access',
                                               'firmware-call',
                                               'io-order',
                                               'machine-state',
                                               'physical-read',
                                               'physical-write'],
                                   'shape': '2a455d2bbbd1dcdbee4fa36942e6e89fb2aec4f0b11df4d010ac8b302b6b2514'},
 'Lemma.Kernel.IPC.replyLocal': {'args': ['u64', 'u64', 'u64', 'u64', 'u64'],
                                 'effects': ['checked-access',
                                             'firmware-call',
                                             'io-order',
                                             'machine-state',
                                             'physical-read',
                                             'physical-write'],
                                 'shape': '0a791b84dcd4213490b673545a5ff248bfdaac9ecbee297187727c97047bec29'},
 'Lemma.Kernel.IPCStorage.queueCopyToUserAt': {'args': ['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                               'effects': ['checked-access',
                                                           'physical-read',
                                                           'physical-write'],
                                               'shape': '2cca74ef1a68d2f21b49c57f7c048a2acb2dc6d3e5818f0e8d71a75f30894abb'},
 'Lemma.Kernel.IPCStorage.completeAt': {'args': ['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                        'effects': ['checked-access', 'physical-read', 'physical-write'],
                                        'shape': 'defa53e2d875ba4c78743e7f96cb5b859c989a1ba18e282fe641869a7a57732f'},
 'Lemma.Kernel.IPCStorage.takeAt': {'args': ['u64', 'u64', 'u64'],
                                    'effects': ['checked-access', 'physical-read'],
                                    'shape': 'db8905b1aee1dd84464cc9c2b7a0817ac2881a35b71c73367bff70ce45138b9b'},
 'Lemma.Kernel.IPCStorage.finishAt': {'args': ['u64', 'u64', 'u64'],
                                      'effects': ['checked-access', 'physical-read', 'physical-write'],
                                      'shape': '69ee513c9f3452c342a3f2fac6f37b8b05fca402d327dab852aa2090dde8ac28'},
 'Lemma.Kernel.IPCStorage.abortAt': {'args': ['u64', 'u64', 'u64'],
                                     'effects': ['checked-access', 'physical-read', 'physical-write'],
                                     'shape': 'a2d55c73b488254e3c5e46e4f7606c92f04b737a7124b17523949b19c73762da'}}

P='Lemma.Kernel.IPC.'
S='Lemma.Kernel.IPCStorage.'


def validate_ipc_rpc_borrow(unit,ir):
    rows={}
    for row in unit['functions']:
        source=re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])
        if source in rows:raise Core0Error('duplicate IPC Receive/Reply source')
        rows[source]=row
    names={source:row['symbol'] for source,row in rows.items()}
    if P+'replyLocal' not in names and S+'queueCopyToUserAt' not in names:return None
    if unit.get('role')!='kernel' or not set(PINNED)<=names.keys():
        raise Core0Error('IPC Receive/Reply borrow lacks complete closed kernel path')
    reverse={symbol:source for source,symbol in names.items()};shapes={}
    for source,expected in PINNED.items():
        body=_ir_definition_body(ir,names[source])
        rebound=re.sub(r'@([^ (]+)',lambda m:'@'+reverse.get(m[1],m[1]),body)
        digest=hashlib.sha256(' '.join(rebound.split()).encode()).hexdigest()
        if (digest!=expected['shape'] or rows[source].get('args')!=expected['args'] or
                sorted(rows[source].get('effects',[]))!=expected['effects']):
            raise Core0Error('IPC Receive/Reply changed qualified body/ABI/effects: '+source)
        shapes[source]=digest
    expected={P+'beginReceiveAt':{P+'receiveWithLimit'},
        P+'receivePacketAt':{P+'beginReceiveAt'},P+'receiveStepAt':{P+'receivePacketAt'},
        P+'receiveHeadAt':{P+'receiveStepAt'},P+'copyHeadAt':{P+'receiveHeadAt'},
        S+'queueCopyToUserAt':{P+'copyHeadAt'},P+'receiveResultAt':{P+'beginReceiveAt'},
        S+'completeAt':{P+'receiveResultAt'},P+'clearAt':{P+'beginReceiveAt'},
        P+'finishAt':{P+'beginReceiveAt'},S+'abortAt':{P+'clearAt'},
        S+'finishAt':{P+'finishAt'},S+'takeAt':{S+'finishAt'},
        P+'stageReplyAt':{P+'replyLocal'}}
    callers={}
    for helper,wanted in expected.items():
        actual={source for source,symbol in names.items() if names[helper] in
            parse_definitions_and_calls(_ir_definition_body(ir,symbol))[2]}
        if actual!=wanted:raise Core0Error('IPC Receive/Reply has unapproved or absent helper caller: '+helper)
        callers[helper]=sorted(actual)
    # A dedicated component may export these exact public roots. In a whole
    # kernel only the versioned trusted-ceiling dispatcher may call them.
    for root in (P+'replyLocal',P+'receiveWithLimit'):
        actual={source for source,symbol in names.items() if names[root] in
            parse_definitions_and_calls(_ir_definition_body(ir,symbol))[2]}
        wanted={P+'dispatchWithLimit'} if P+'dispatchWithLimit' in names else set()
        if actual!=wanted:raise Core0Error('IPC Receive/Reply root escaped trusted dispatcher: '+root)
        callers[root]=sorted(actual)
    offset=names[S+'metadataOffset']
    if re.fullmatch(r'\s*entry:\s*ret i64 3648\s*',_ir_definition_body(ir,offset)) is None:
        raise Core0Error('IPC Receive/Reply metadata offset differs')
    gates=[];fresh_uses={}
    failed=names[P+'failed'];failed_body=_ir_definition_body(ir,failed)
    for root,provider,args,target,descriptor in (
            (P+'receiveWithLimit',P+'idle','i64 %arg1',P+'beginReceiveAt','%arg1'),
            (P+'replyLocal',P+'idle','i64 %arg0',P+'stageReplyAt','%arg0'),
            (P+'receiveHeadAt',P+'checkedTransaction','i64 %arg0, i64 %arg1',P+'copyHeadAt','%arg0')):
        body=_ir_definition_body(ir,names[root])
        _,metadata=_local_checked_result(body,names[provider],args)
        arithmetic=_local_arithmetic(body,{offset:3648})
        calls=_local_call_arguments(body,names[target])
        expected_count=2 if root!=P+'replyLocal' else 1
        if len(calls)!=expected_count:raise Core0Error('IPC Receive/Reply lost exact fresh base uses: '+root)
        for arguments in calls:
            values=arguments.split(', ')
            if (values[0]!='i64 '+descriptor or len(values)<2 or
                    arithmetic.get(values[1][4:])!=('sub',metadata,3648)):
                raise Core0Error('IPC Receive/Reply base/descriptor does not come from current checked metadata')
        fresh_uses[root]={'metadata':metadata,'calls':calls}
        gates.append(validate_failed_call_gate(body,names[provider],names[target],failed,failed_body))
    return {'version':'lemma-ipc-rpc-base-reuse/1','pinned_genuine_shapes':shapes,
        'exact_callers':callers,'fresh_base_uses':fresh_uses,'fresh_success_gates':gates,
        'scope':'one nonpreemptible syscall Action; protected address-space/frame closure is stable, disjoint capability rows may change only through fully checked grant/revocation; every live IPC/object/queue/UserCopy check remains fresh'}
