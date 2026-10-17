"""Closed same-Action CallBegin descriptor reuse; source/CFG observer only.

The pinned bodies are qualified genuine kernel4 lowering, combined with explicit
caller/base/status witnesses. This is not a compiler proof or CPU timing test.
"""
import hashlib,re
from audit_kernel import _ir_definition_body,parse_definitions_and_calls,_local_checked_result,validate_failed_call_gate,_local_arithmetic
from core0_common import Core0Error

PINNED = {'Lemma.Kernel.IPC.callBeginWithLimit': {'args': ['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                         'effects': ['checked-access',
                                                     'firmware-call',
                                                     'io-order',
                                                     'machine-state',
                                                     'physical-read',
                                                     'physical-write'],
                                         'shape': '1556f164de2a8f5cd4e0c865c70d2761c79c61da72260132ac3b46dec467bacc'},
 'Lemma.Kernel.IPC.stageAt': {'args': ['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                              'effects': ['checked-access', 'physical-read', 'physical-write'],
                              'shape': 'ffc0653a0196518835ffae5185cc1fc4c31301f330e62b5ca956e37775246aa6'},
 'Lemma.Kernel.IPCStorage.commitWaitAt': {'args': ['u64', 'u64', 'u64'],
                                          'effects': ['checked-access', 'physical-read', 'physical-write'],
                                          'shape': '7a781673afe029f1f28b5d320b824e72cbd8a5b42f93d4f2c51569ebf4db1ed1'},
 'Lemma.Kernel.IPCStorage.packetAt': {'args': ['u64', 'u64', 'u64'],
                                      'effects': ['checked-access', 'physical-read'],
                                      'shape': '6545dacfd1a4c69d53bba8169946d0313247684a945987da98be2a2a7433e110'},
 'Lemma.Kernel.IPCStorage.prepareAt': {'args': ['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                       'effects': ['checked-access', 'physical-read', 'physical-write'],
                                       'shape': '872b2e85914b11a5891e4bb9263d1eee9a5ac1829d59a14e91bf488b96fa2453'},
 'Lemma.Kernel.IPCStorage.queueEnqueueAt': {'args': ['u64', 'u64', 'u64', 'u64', 'u64'],
                                            'effects': ['checked-access', 'physical-read', 'physical-write'],
                                            'shape': '47ca530ee6cffe6c8d7381337b459488300c66452b55d7241c6474274033799a'},
 'Lemma.Kernel.IPCStorage.setReplyAt': {'args': ['u64', 'u64', 'u64', 'u64'],
                                        'effects': ['checked-access', 'physical-read', 'physical-write'],
                                        'shape': '6b225c36a6967092c507e927327c95dc85bd1662821d37d577a4dc7d5c5eaf9a'},
 'Lemma.Kernel.IPCStorage.stagePayloadAt': {'args': ['u64', 'u64', 'u64', 'u64', 'u64'],
                                            'effects': ['checked-access', 'physical-read', 'physical-write'],
                                            'shape': 'b664a49cac568dc7926a81f3b3734cfb5be9059a28d047cc58de3ea3be0a7282'},
 'Lemma.Kernel.IPCStorage.transactionRowAt': {'args': ['u64', 'u64', 'u64'],
                                              'effects': ['checked-access', 'physical-read'],
                                              'shape': '4603fb26bd702058983374e65e1424190a2b84fe4bd0a41d6979a7459e7f4ac5'}}
P='Lemma.Kernel.IPC.'
S='Lemma.Kernel.IPCStorage.'


def validate_ipc_call_borrow(unit,ir):
 rows={}
 for row in unit['functions']:
  name=re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])
  if name in rows:raise Core0Error('duplicate IPC call borrow source')
  rows[name]=row
 names={s:r['symbol'] for s,r in rows.items()}
 if S+'prepareAt' not in names:return None
 if unit.get('role')!='kernel' or not set(PINNED)<=names.keys():raise Core0Error('IPC call borrow lacks complete closed kernel path')
 reverse={symbol:source for source,symbol in names.items()};shapes={}
 for source,expected in PINNED.items():
  body=_ir_definition_body(ir,names[source]);rebound=re.sub(r'@([^ (]+)',lambda m:'@'+reverse.get(m[1],m[1]),body)
  digest=hashlib.sha256(' '.join(rebound.split()).encode()).hexdigest()
  if digest!=expected['shape'] or rows[source].get('args')!=expected['args'] or sorted(rows[source].get('effects',[]))!=expected['effects']:
   raise Core0Error('IPC call borrow changed qualified genuine body/ABI/effects: '+source)
  shapes[source]=digest
 # These helpers cannot become a general borrowed pointer interface. All
 # reachable callers must be the specific pinned path above.
 expected={S+'prepareAt':{P+'callBeginWithLimit'},P+'stageAt':{P+'callBeginWithLimit'},
   S+'stagePayloadAt':{P+'stageAt'},S+'packetAt':{P+'stageAt'},
   S+'setReplyAt':{P+'callBeginWithLimit'},S+'queueEnqueueAt':{P+'callBeginWithLimit'},
   S+'commitWaitAt':{P+'callBeginWithLimit'},
   S+'transactionRowAt':{S+'stagePayloadAt',S+'packetAt',S+'setReplyAt',S+'commitWaitAt'}}
 rpc_borrow=None
 if P+'replyLocal' in names or S+'queueCopyToUserAt' in names:
  # Additional callers are admitted only after the complete new sixteen-body
  # guard establishes their fresh same-Action base witnesses and exact graph.
  from ipc_rpc_borrow import validate_ipc_rpc_borrow
  rpc_borrow=validate_ipc_rpc_borrow(unit,ir)
  expected[S+'prepareAt']|={P+'beginReceiveAt',P+'stageReplyAt'}
  expected[P+'stageAt']|={P+'stageReplyAt'}
  expected[S+'packetAt']|={P+'receiveResultAt',P+'stageReplyAt'}
  expected[S+'commitWaitAt']|={P+'beginReceiveAt'}
  expected[S+'transactionRowAt']|={S+'abortAt',S+'completeAt',S+'takeAt'}
 callers={}
 for helper,wanted in expected.items():
  actual={source for source,symbol in names.items() if names[helper] in parse_definitions_and_calls(_ir_definition_body(ir,symbol))[2]}
  if actual!=wanted:raise Core0Error('IPC call borrow helper has unapproved or absent caller: '+helper)
  callers[helper]=sorted(actual)
 body=_ir_definition_body(ir,names[P+'callBeginWithLimit'])
 _,metadata=_local_checked_result(body,names[P+'idle'],'i64 %arg1')
 offset=names[S+'metadataOffset']
 if re.fullmatch(r'\s*entry:\s*ret i64 3648\s*',_ir_definition_body(ir,offset)) is None:raise Core0Error('IPC call borrow tail offset differs')
 arithmetic=_local_arithmetic(body,{offset:3648});base_values={value for value,expr in arithmetic.items() if expr==('sub',metadata,3648)}
 if len(base_values)!=5:raise Core0Error('IPC call borrow lost five exact current base uses')
 failed=names[P+'failed'];failed_body=_ir_definition_body(ir,failed)
 gates=[]
 for helper in ['prepareAt','setReplyAt','queueEnqueueAt','commitWaitAt']:
  gates.append(validate_failed_call_gate(body,names[P+'idle'],names[S+helper],failed,failed_body))
 gates.append(validate_failed_call_gate(body,names[P+'idle'],names[P+'stageAt'],failed,failed_body))
 stage=_ir_definition_body(ir,names[P+'stageAt'])
 gates.append(validate_failed_call_gate(stage,names[S+'stagePayloadAt'],names[P+'stamp'],failed,failed_body))
 return {'version':'lemma-ipc-call-base-reuse/1','pinned_genuine_shapes':shapes,'exact_callers':callers,
  **({'rpc_borrow':rpc_borrow} if rpc_borrow is not None else {}),
  'validated_metadata':metadata,'derived_base_values':sorted(base_values),'fresh_success_gates':gates,
  'additional_pending_callers':[S+'prepareAt',S+'transactionRowAt',S+'queueEnqueueAt'],
  'scope':'same nonpreemptible syscall Action only; mutable IPC words and UserCopy/queue/object checks remain fresh; no cross-syscall or User alias'}
