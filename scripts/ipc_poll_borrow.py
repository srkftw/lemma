"""Closed same-Action IPC borrowing admission for genuine checked kernel IR.

Public helpers retain independent fresh descriptor/base validation. The Task
borrow requires every live row, ownership, error and completion witness below.
This audits generated artifacts; it does not execute or interpret target code.
"""
import hashlib
import re
from audit_kernel import (
    _ir_definition_body, _local_checked_result, _local_call_arguments,
    _local_closed_calls, _local_selected_failed_gate, _local_arithmetic,
    _structured_ir_blocks, _structured_successors, _structured_reachable,
    parse_definitions_and_calls, validate_failed_call_gate,
    validate_boolean_gate, validate_call_precedes, validate_capability_base_borrow,
    _local_pinned_shapes,
)
from core0_common import Core0Error

IPC_POLL_BORROW_SHAPES_V1 = {
    'Lemma.Kernel.IPCStorage.pendingAt': '782d15e083e8cb7f4f2891bf06241d7fc225b50a4da23b680271934f095e9ca8',
    'Lemma.Kernel.IPCStorage.pending': '5eeb7baf29e420e8f5839b3ec635104b58cdf5dddcb494c1f82303f2b78d4242',
    'Lemma.Kernel.IPC.pollAt': 'e2575819d3f5d4de50d1fbcc843046da97b222c9786b59cb1a91d6f1f6b90e11',
    'Lemma.Kernel.IPC.poll': '49717fc2e560e29058b4d562ef27196615c6942771768c986fa160fe7a66c8be',
    'Lemma.Kernel.Task.pollIPCStep': 'b1f72f496dc02e89d33676cbb34db7d3bf7e555cb4d5fd1fad64da15c596b0bf',
}


def _poll_shapes(ir, names, selected=None):
    reverse = {symbol: source for source, symbol in names.items()}
    result = {}
    for source, expected in IPC_POLL_BORROW_SHAPES_V1.items():
        if selected is not None and source not in selected:
            continue
        body = _ir_definition_body(ir, names[source])
        rebound = re.sub(r'@([^ (]+)', lambda m: '@' + reverse.get(m[1], m[1]), body)
        digest = hashlib.sha256(' '.join(rebound.split()).encode()).hexdigest()
        if digest != expected:
            raise Core0Error('IPC polling borrow differs from pinned genuine body: ' + source)
        result[source] = digest
    return result


def _poll_exact_callers(ir, names, helper, expected):
    observed = {source for source, symbol in names.items()
                if names[helper] in parse_definitions_and_calls(_ir_definition_body(ir, symbol))[2]}
    if observed != expected:
        raise Core0Error('IPC polling borrow caller inventory differs: ' + helper)
    return sorted(observed)


def _poll_prefix(body, base_symbol, helper_symbol, readonly_symbols, read_symbol, reads):
    """Only two enumerated checked reads intervene on paths entering pollAt.

    Failed branches which terminate without entering the protected helper do not
    grant authority. The actual helper path is checked block-by-block and also
    pinned as a whole; neither an unchecked pointer nor a persisted cache is
    admitted by this routine.
    """
    blocks = _structured_ir_blocks(body)
    successors = _structured_successors(blocks)
    origins = [(label, i) for label, lines in blocks.items() for i, line in enumerate(lines)
               if re.search(r'\bcall\s+[^@\n]*@' + re.escape(base_symbol) + r'\(', line)]
    targets = [(label, i) for label, lines in blocks.items() for i, line in enumerate(lines)
               if re.search(r'\bcall\s+[^@\n]*@' + re.escape(helper_symbol) + r'\(', line)]
    if len(origins) != 1 or len(targets) != 1:
        raise Core0Error('IPC polling prefix needs one fresh base and one pollAt')
    start, start_index = origins[0]
    end, end_index = targets[0]
    actual_reads = []
    prefix_blocks = []
    for label, lines in blocks.items():
        if not (_structured_reachable(successors, start, label) and
                _structured_reachable(successors, label, end)):
            continue
        first = start_index + 1 if label == start else 0
        last = end_index if label == end else len(lines)
        selected = lines[first:last]
        prefix_blocks.append(label)
        for line in selected:
            if re.search(r'\b(store|atomicrmw|cmpxchg|fence)\b', line):
                raise Core0Error('IPC polling fresh-base prefix mutates authoritative state')
            called = parse_definitions_and_calls(line)[2]
            if not called <= readonly_symbols:
                raise Core0Error('IPC polling fresh-base prefix schedules or calls an unapproved helper')
            actual_reads.extend(re.findall(r'call \{ i64, i64 \} @' + re.escape(read_symbol) + r'\(([^\n]*)\)', line))
    if actual_reads != reads:
        raise Core0Error('IPC polling prefix changed its exact epoch/transaction read order')
    return {'blocks': prefix_blocks, 'checked_reads': actual_reads}


def validate_ipc_poll_borrow(unit, ir):
    """Five exact kernel helpers and their same-Action authority witnesses."""
    rows = {}
    for row in unit['functions']:
        source = re.sub(r'^_private\..*?\.[0-9]+\.', '', row['source'])
        if source in rows:
            raise Core0Error('IPC polling borrow has duplicate normalized source declarations')
        rows[source] = row
    n = {source: row['symbol'] for source, row in rows.items()}
    t = 'Lemma.Kernel.Task.'
    p = 'Lemma.Kernel.IPC.'
    s = 'Lemma.Kernel.IPCStorage.'
    a = 'Lemma.Kernel.Memory.AddressSpace.base'
    x = 'Lemma.Kernel.Memory.Access.read64'
    required = set(IPC_POLL_BORROW_SHAPES_V1) | {a, x}
    required |= {t + name for name in ('lookupRecord', 'findStep', 'table', 'completeBlocked', 'failed', 'fatal',
        'stride', 'stateOffset', 'managedOffset', 'waitEpochOffset', 'waitTransactionOffset',
        'runnable', 'blocked', 'dying')}
    required |= {p + name for name in ('failed', 'fatal', 'word', 'pollWaiting')}
    required |= {s + name for name in ('failed', 'fatal', 'equalWord', 'get', 'metadataOffset',
        'magic', 'stateOffset', 'stateIdle', 'stateReserved', 'stateWaiting', 'stateReady',
        'nextTransactionOffset', 'transactionOffset', 'operationOffset', 'endpointOffset',
        'callOperation', 'maxTransaction')}
    required.add('Lemma.User.IPCABI.wouldBlock')
    if unit.get('role') != 'kernel' or not required <= n.keys():
        raise Core0Error('IPC polling borrow lacks its closed kernel inventory')
    read_effects = {'checked-access', 'physical-read'}
    poll_effects = read_effects | {'io-order', 'machine-state', 'physical-write', 'firmware-call'}
    expected_rows = [(s+'pendingAt', ['u64']*2, read_effects),
                     (s+'pending', ['u64'], read_effects),
                     (p+'pollAt', ['u64']*2, poll_effects),
                     (p+'poll', ['u64'], poll_effects),
                     (t+'pollIPCStep', ['u32']*2+['u64']*5, poll_effects),
                     (t+'lookupRecord', ['u64'], read_effects)]
    for source, args, effects in expected_rows:
        if rows[source].get('args') != args or set(rows[source].get('effects', [])) != effects:
            raise Core0Error('IPC polling borrow changed helper signature/effects: ' + source)
        signature = ', '.join(('i32 signext ' if kind == 'u32' else 'i64 ') + '%arg'+str(i)
                              for i, kind in enumerate(args))
        if re.search(r'^define \{ i64, i64 \} @'+re.escape(n[source])+r'\('+re.escape(signature)+
                     r'\) nounwind noinline "disable-tail-calls"="true" \{', ir, re.M) is None:
            raise Core0Error('IPC polling borrow changed emitted helper signature: ' + source)

    pending_callers = {s+'pending',p+'pollAt'}
    if s+'prepareAt' in n:
        from ipc_call_borrow import validate_ipc_call_borrow
        pending_callers |= set(validate_ipc_call_borrow(unit,ir)['additional_pending_callers'])
    callers = {
        s+'pendingAt': _poll_exact_callers(ir, n, s+'pendingAt', pending_callers),
        p+'pollAt': _poll_exact_callers(ir, n, p+'pollAt', {p+'poll', t+'pollIPCStep'}),
    }
    # Do not broaden lookupRecord globally: only this five-body guard admits
    # the new caller, while existing capture/lookups retain their own guard.
    lookup_callers = {source for source, symbol in n.items()
                      if n[t+'lookupRecord'] in parse_definitions_and_calls(_ir_definition_body(ir, symbol))[2]}
    if t+'pollIPCStep' not in lookup_callers or not lookup_callers <= ({t+'lookup', t+'contextAt', t+'pollIPCStep'} | _entry2_lookup_record_callers(unit,ir)):
        raise Core0Error('IPC polling borrow has an unvalidated lookupRecord caller')
    callers[t+'lookupRecord'] = sorted(lookup_callers)

    constants = {t+'stride':512, t+'stateOffset':8, t+'managedOffset':120,
                 t+'waitEpochOffset':128, t+'waitTransactionOffset':136,
                 s+'metadataOffset':3648, s+'magic':0x31435049414d454c,
                 s+'stateOffset':24, s+'nextTransactionOffset':48,
                 s+'transactionOffset':40, s+'operationOffset':32, s+'endpointOffset':56}
    for source, value in constants.items():
        if re.fullmatch(r'\s*entry:\s*ret i64 '+str(value)+r'\s*', _ir_definition_body(ir,n[source])) is None:
            raise Core0Error('IPC polling borrow changed scalar storage authority: '+source)
    scalar_constants = {n[source]: value for source, value in constants.items()}
    gates = []
    for wrapper, helper, failed, allowed in (
        (s+'pending', s+'pendingAt', s+'failed', {s+'failed'}),
        (p+'poll', p+'pollAt', p+'failed', {p+'failed',p+'fatal'})):
        gates.append({'source': wrapper, **validate_capability_base_borrow(
            _ir_definition_body(ir,n[wrapper]), n[a], n[helper], n[failed],
            _ir_definition_body(ir,n[failed]), {n[source] for source in allowed})})
    body = _ir_definition_body(ir,n[s+'pendingAt'])
    values = _local_arithmetic(body, scalar_constants)
    root = ('add','%arg1',3648)
    actual_equal = [tuple(values.get(arg[4:], int(arg[4:]) if arg[4:].isdecimal() else arg[4:])
                          for arg in args.split(', '))
                    for args in _local_call_arguments(body,n[s+'equalWord'])]
    if actual_equal != [(root, constants[s+'magic']), (('add',root,8),1), (('add',root,16),'%arg0')]:
        raise Core0Error('IPC pendingAt lost magic/version/current descriptor witnesses')
    actual_reads = [values.get(args[4:],args[4:]) for args in _local_call_arguments(body,n[s+'get'])]
    if actual_reads != [('add',root,offset) for offset in (24,48,40,32,56)]:
        raise Core0Error('IPC pendingAt changed its five live state/sequence/protocol reads')
    _local_closed_calls(body,{n[source] for source in required if source.startswith(s) and source not in {s+'pending',s+'pendingAt'}})
    body = _ir_definition_body(ir,n[p+'pollAt'])
    _local_checked_result(body,n[s+'pendingAt'],'i64 %arg0, i64 %arg1')
    _local_closed_calls(body,{n[source] for source in (s+'pendingAt',p+'failed',p+'fatal',p+'word',p+'pollWaiting',
        s+'stateOffset',s+'stateIdle',s+'transactionOffset',s+'stateReady',s+'stateWaiting','Lemma.User.IPCABI.wouldBlock')})
    for target in (p+'word',p+'pollWaiting'):
        gates.append(validate_failed_call_gate(body,n[s+'pendingAt'],n[target],n[p+'failed'],_ir_definition_body(ir,n[p+'failed'])))

    body = _ir_definition_body(ir,n[t+'pollIPCStep'])
    values = _local_arithmetic(body,scalar_constants)
    row = ('add','%arg3',('mul',('zext32','%arg0'),512))
    reads = _local_call_arguments(body,n[x])
    if [values.get(args[4:],args[4:]) for args in reads] != [('add',row,8),('add',row,120),row,('add',row,128),('add',row,136)]:
        raise Core0Error('IPC polling changed its five live task row reads')
    _, descriptor = _local_checked_result(body,n[x],reads[2])
    _, checked_row = _local_checked_result(body,n[t+'lookupRecord'],'i64 '+descriptor)
    _, base = _local_checked_result(body,n[a],'i64 '+descriptor)
    if _local_call_arguments(body,n[p+'pollAt']) != ['i64 '+descriptor+', i64 '+base]:
        raise Core0Error('IPC polling substitutes the fresh descriptor/base pair')
    gates.append(validate_failed_call_gate(body,n[t+'lookupRecord'],n[a],n[t+'failed'],_ir_definition_body(ir,n[t+'failed'])))
    gates.append(validate_failed_call_gate(body,n[a],n[p+'pollAt'],n[t+'failed'],_ir_definition_body(ir,n[t+'failed'])))
    matches = [(cmp,rhs) for cmp,rhs in re.findall(r'(%[A-Za-z0-9_.$-]+) = icmp eq i64 '+re.escape(checked_row)+r', ([^\n]+)$',body,re.M)
               if values.get(rhs,rhs) == row]
    if len(matches) != 1:
        raise Core0Error('IPC polling does not bind lookupRecord to this exact live table row')
    gates.append(validate_boolean_gate(body,matches[0][0],n[p+'pollAt']))
    for args in reads:
        gates.append(_local_selected_failed_gate(body,n[x],args,n[p+'pollAt'],n[t+'failed'],_ir_definition_body(ir,n[t+'failed'])))
    prefix = _poll_prefix(body,n[a],n[p+'pollAt'],{n[source] for source in
        (x,t+'failed',t+'stride',t+'waitEpochOffset',t+'waitTransactionOffset')},n[x],reads[3:])
    _, epoch = _local_checked_result(body,n[x],reads[3])
    _, transaction = _local_checked_result(body,n[x],reads[4])
    completion = _local_call_arguments(body,n[t+'completeBlocked'])
    if len(completion) != 1 or len(parts:=completion[0].split(', ')) != 5 or \
       values.get(parts[0][4:],parts[0][4:]) != row or parts[1:] != ['i64 '+descriptor,'i64 '+epoch,'i64 '+transaction,'i64 %arg4']:
        raise Core0Error('IPC polling changed the original completeBlocked authority tuple')
    gates.append(validate_call_precedes(body,n[p+'pollAt'],n[t+'completeBlocked']))
    _local_closed_calls(body,{n[source] for source in required if source.startswith(t)}|{n[x],n[a],n[p+'pollAt'],n['Lemma.User.IPCABI.wouldBlock']})
    # The standalone polling closure need not reach Task.capture. Its fresh
    # live-row lookup therefore retains the complete independent scanner pins
    # here too; mere helper spelling never establishes descriptor authority.
    lookup_shapes = _local_pinned_shapes(ir,n,(t+'findStep',t+'lookupRecord'))
    return {'version':'lemma-ipc-poll-borrow-v1','callers':callers,'gates':gates,
            'fresh_prefix':prefix,'pinned_shapes':_poll_shapes(ir,n),
            'lookup_pinned_shapes':lookup_shapes,
            'scope':'same nonpreemptible Action; fresh descriptor and checked live row, no cache or mutation before pollAt; original completion tail'}


def _poll_rows(unit):
    rows={}
    for row in unit['functions']:
        source=re.sub(r'^_private\..*?\.[0-9]+\.', '',row['source'])
        if source in rows:raise Core0Error('IPC helper has duplicate source identity')
        rows[source]=row
    return rows,{source:row['symbol'] for source,row in rows.items()}


def validate_ipc_pending_public(unit,ir):
    """Independent ordinary fresh public wrapper, also valid without pollAt."""
    rows,n=_poll_rows(unit);s='Lemma.Kernel.IPCStorage.'
    a='Lemma.Kernel.Memory.AddressSpace.base'
    required={a}|{s+name for name in ('pending','pendingAt','failed','fatal','equalWord','get',
        'metadataOffset','magic','stateOffset','stateIdle','stateReserved','stateReady',
        'nextTransactionOffset','transactionOffset','operationOffset','endpointOffset','callOperation','maxTransaction')}
    if unit.get('role')!='kernel' or not required<=n.keys():
        raise Core0Error('IPC public pending helper lacks its exact fresh wrapper inventory')
    for source,args in ((s+'pending',['u64']),(s+'pendingAt',['u64']*2)):
        if rows[source].get('args')!=args or set(rows[source].get('effects',[]))!={'checked-access','physical-read'}:
            raise Core0Error('IPC pending helper signature/effects differ')
        signature=', '.join('i64 %arg'+str(i) for i in range(len(args)))
        if re.search(r'^define \{ i64, i64 \} @'+re.escape(n[source])+r'\('+re.escape(signature)+
                     r'\) nounwind noinline "disable-tail-calls"="true" \{',ir,re.M) is None:
            raise Core0Error('IPC pending emitted ABI differs')
    observed={source for source,symbol in n.items() if n[s+'pendingAt'] in
              parse_definitions_and_calls(_ir_definition_body(ir,symbol))[2]}
    allowed = {s+'pending','Lemma.Kernel.IPC.pollAt'}
    call_borrow = None
    if s+'prepareAt' in n:
        from ipc_call_borrow import validate_ipc_call_borrow
        call_borrow = validate_ipc_call_borrow(unit,ir)
        allowed |= set(call_borrow['additional_pending_callers'])
    if s+'pending' not in observed or not observed<=allowed:
        raise Core0Error('IPC pendingAt caller lacks ordinary fresh wrapper or has unapproved borrow')
    gate=validate_capability_base_borrow(_ir_definition_body(ir,n[s+'pending']),n[a],n[s+'pendingAt'],
        n[s+'failed'],_ir_definition_body(ir,n[s+'failed']),{n[s+'failed']})
    constants={s+'metadataOffset':3648,s+'magic':0x31435049414d454c,s+'stateOffset':24,
        s+'nextTransactionOffset':48,s+'transactionOffset':40,s+'operationOffset':32,s+'endpointOffset':56}
    for source,value in constants.items():
        if re.fullmatch(r'\s*entry:\s*ret i64 '+str(value)+r'\s*',_ir_definition_body(ir,n[source])) is None:
            raise Core0Error('IPC pending helper storage authority constant differs')
    body=_ir_definition_body(ir,n[s+'pendingAt']);values=_local_arithmetic(body,{n[k]:v for k,v in constants.items()})
    root=('add','%arg1',3648)
    equals=[tuple(values.get(arg[4:],int(arg[4:]) if arg[4:].isdecimal() else arg[4:]) for arg in args.split(', '))
            for args in _local_call_arguments(body,n[s+'equalWord'])]
    if equals!=[(root,constants[s+'magic']),(('add',root,8),1),(('add',root,16),'%arg0')]:
        raise Core0Error('IPC pending helper dropped its current magic/version/descriptor check')
    if [values.get(args[4:],args[4:]) for args in _local_call_arguments(body,n[s+'get'])]!=[('add',root,k) for k in (24,48,40,32,56)]:
        raise Core0Error('IPC pending helper changed live protocol fields or read order')
    _local_closed_calls(body,{n[source] for source in required if source.startswith(s) and source not in {s+'pending',s+'pendingAt'}})
    return {'helper':s+'pendingAt','callers':sorted(observed),'fresh_public_wrapper':gate,'call_borrow':call_borrow,
        'pinned_shapes':_poll_shapes(ir,n,{s+'pendingAt',s+'pending'}),
        'scope':'ordinary pending validates its own descriptor/base; no Task or pollAt requirement'}


def validate_ipc_poll_public(unit,ir):
    """Public poll independently validates a fresh base; Task needs more below."""
    pending=validate_ipc_pending_public(unit,ir)
    rows,n=_poll_rows(unit);p='Lemma.Kernel.IPC.';s='Lemma.Kernel.IPCStorage.'
    a='Lemma.Kernel.Memory.AddressSpace.base'
    required={a}|{p+name for name in ('poll','pollAt','failed','fatal','word','pollWaiting')}|{s+name for name in
        ('pendingAt','stateOffset','transactionOffset','stateIdle','stateReady','stateWaiting')}|{'Lemma.User.IPCABI.wouldBlock'}
    if not required<=n.keys():raise Core0Error('IPC public poll lacks its helper and pending witnesses')
    effects={'checked-access','physical-read','physical-write','io-order','machine-state','firmware-call'}
    for source,args in ((p+'poll',['u64']),(p+'pollAt',['u64']*2)):
        if rows[source].get('args')!=args or set(rows[source].get('effects',[]))!=effects:
            raise Core0Error('IPC public poll helper signature/effects differ')
        signature=', '.join('i64 %arg'+str(i) for i in range(len(args)))
        if re.search(r'^define \{ i64, i64 \} @'+re.escape(n[source])+r'\('+re.escape(signature)+
                     r'\) nounwind noinline "disable-tail-calls"="true" \{',ir,re.M) is None:
            raise Core0Error('IPC public poll emitted ABI differs')
    observed={source for source,symbol in n.items() if n[p+'pollAt'] in
              parse_definitions_and_calls(_ir_definition_body(ir,symbol))[2]}
    if p+'poll' not in observed or not observed<={p+'poll','Lemma.Kernel.Task.pollIPCStep'}:
        raise Core0Error('IPC pollAt caller lacks public fresh wrapper or has unapproved borrow')
    gate=validate_capability_base_borrow(_ir_definition_body(ir,n[p+'poll']),n[a],n[p+'pollAt'],n[p+'failed'],
        _ir_definition_body(ir,n[p+'failed']),{n[p+'failed'],n[p+'fatal']})
    body=_ir_definition_body(ir,n[p+'pollAt'])
    _local_checked_result(body,n[s+'pendingAt'],'i64 %arg0, i64 %arg1')
    _local_closed_calls(body,{n[source] for source in required if source not in {a,p+'poll',p+'pollAt'}})
    gates=[validate_failed_call_gate(body,n[s+'pendingAt'],n[target],n[p+'failed'],_ir_definition_body(ir,n[p+'failed']))
           for target in (p+'word',p+'pollWaiting')]
    return {'helper':p+'pollAt','callers':sorted(observed),'pending':pending,'fresh_public_wrapper':gate,'gates':gates,
        'pinned_shapes':_poll_shapes(ir,n,{p+'pollAt',p+'poll'}),
        'scope':'public poll validates its own base; Task borrow grants no authority until full five-body guard'}


def _entry2_lookup_record_callers(unit,ir):
    from task_entry_borrow import validate_if_present
    selected=validate_if_present(ir,unit,optimized=False)
    return ({'Lemma.Kernel.Task.entryContextV2','Lemma.Kernel.Task.entryDispatchesV2'}
            if selected is not None else set())


def task_lookup_record_allowed_callers(unit, ir):
    """Capture hook extends only an actual fully witnessed Task→pollAt edge.

    A pending-only or public-poll-only reachable subgraph remains legitimate;
    presence of a helper name alone never broadens Task.lookupRecord authority.
    """
    _,n=_poll_rows(unit)
    pending='Lemma.Kernel.IPCStorage.pendingAt';poll='Lemma.Kernel.IPC.pollAt';task='Lemma.Kernel.Task.pollIPCStep'
    old={'Lemma.Kernel.Task.lookup','Lemma.Kernel.Task.contextAt'}
    old |= _entry2_lookup_record_callers(unit,ir)
    if pending in n:validate_ipc_pending_public(unit,ir)
    if poll in n:validate_ipc_poll_public(unit,ir)
    if poll in n and task in n and n[poll] in parse_definitions_and_calls(_ir_definition_body(ir,n[task]))[2]:
        validate_ipc_poll_borrow(unit,ir)
        return old|{task}
    return old


def validate_reachable_helpers(unit, ir):
    """Validate every reachable additive helper without enlarging legacy authority."""
    _, names = _poll_rows(unit)
    pending = 'Lemma.Kernel.IPCStorage.pendingAt'
    poll = 'Lemma.Kernel.IPC.pollAt'
    task = 'Lemma.Kernel.Task.pollIPCStep'
    if pending not in names and poll not in names:
        return None
    report = {'version': 'lemma-ipc-poll-borrow-v1',
              'pending': validate_ipc_pending_public(unit, ir)}
    if poll in names:
        report['poll'] = validate_ipc_poll_public(unit, ir)
        if task in names and names[poll] in parse_definitions_and_calls(
                _ir_definition_body(ir, names[task]))[2]:
            report['task'] = validate_ipc_poll_borrow(unit, ir)
    return report
