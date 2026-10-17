"""Closed artifact observer for genuinely elaborated UserCopy page-word v1.

The retained source-derived whole initializer and independent 74-case/10108
fault-prefix Action comparison establish this narrowly selected shape. Pins
bind complete pre/post bodies, signatures/effects and helper caller closure;
the independent pre-IR checks below inspect actual ordered accesses and loops.
This is an artifact audit, not a proof or a target interpreter.
"""
from __future__ import annotations
import hashlib
import re
from core0_common import Core0Error

BASE = 'Lemma.Kernel.Memory.UserCopy.'
EFFECTS = ['checked-access', 'physical-read', 'physical-write']
CALLBACK = ['u32', 'u32'] + ['u64']*5
ARGUMENTS = {'copyWord': ['u64']*2, 'copyWordTailStep': CALLBACK,
             'copyWordGenericBlockStep': CALLBACK, 'copyWordBlockStep': CALLBACK,
             'copyPageWords': ['u64']*3, 'copyFromPages': ['u64']*5,
             'copyToPages': ['u64']*5, 'copyFromUserResult': ['u64']*6,
             'copyFromUserReusingReadPage': ['u64']*7}
# These immutable preimages are from the actual retained genuine initializer
# build; their source/effect/order was independently inspected before admission.
PINS = {'pre': {'copyWord': '9cd191ddd78134075c92e43740d5e9273f979c7b6bd66578b142144225304ffc', 'copyWordTailStep': '60902059fd6b739d319f60d889cb6e664ceaf575cb0130a7bc83b477618418c5', 'copyWordGenericBlockStep': '769b11bf78a26d7b2dc28af6aa5850dee3c74a33d942364b7425d7d36315a0d1', 'copyWordBlockStep': '7d3545c6684c4127a82eb1dfd3916c8c1aa599b7c38736615bdd0561f8bbbd8a', 'copyPageWords': '6f1eb0303f046c060c4a75a3f1167c2dc31d56cb1c494b8876f3d1b1f9c49002', 'copyFromPages': 'd74ff0f65092e6cf40d12c1af536a2aefa24e839e2b2627e7539a0ed668caa0c', 'copyToPages': 'ea27483e138c47a5412e04baf40896a6bd85d154589757511a3f0b69a1d66f4c', 'copyFromUserResult': 'ad36ed7d2e7380e2ce5aa861ee0c08649d761b85322e4eacc41a8a1629be580c', 'copyFromUserReusingReadPage': 'aece72049a56b67536d3294a7044980ac4bc0f8eef37428276fd44b0be655868'}, 'post': {'copyWord': '2e24df20cb2a386d2870430395a1ac793aadd09aa16916a272967a45f49cf7dc', 'copyWordTailStep': 'd9b263cfe267b11edf583826c9c1d542742cfd554902b9c240b40093c9f23799', 'copyWordGenericBlockStep': '9b8683643efd69686d82a058722b168bd29659d50703d1d4d86d0dde52d3ccb7', 'copyWordBlockStep': '25e248cbb76f1a88a201c9f51b696e2f58f65eb2d66b147e02f6c3bb7eb056b4', 'copyPageWords': 'ae2473f6c26e3ec76354e675a075658b20e34e7731d813d3cc3a931a69b9dd0c', 'copyFromPages': 'ddef5496096a0b6ca4f02e03c68e43e09d17ac8352ebf63c9dbd4366227e3b2c', 'copyToPages': 'f7ff62c1ca920d7476854bb1a971ce80d18a76ef15ac3acb9980694fdfbaad05', 'copyFromUserResult': '74dda3ce7b826f6342ee5cbec9e9fcd02aefb4f44faf5d1e82dc7199e04c78ff', 'copyFromUserReusingReadPage': '39e85b14583e361309db336edf8ff10958e1455467e23d1149a2d8ba3b5a0cae'}}
CALLERS = {'copyWord': {'copyWordTailStep'}, 'copyWordTailStep': {'copyPageWords'},
           'copyWordGenericBlockStep': {'copyWordBlockStep'},
           'copyWordBlockStep': {'copyPageWords'},
           'copyPageWords': {'copyFromPages', 'copyToPages', 'copyFromUserReusingReadPage'},
           'copyFromPages': {'copyFromUserResult'}, 'copyToPages': {'copyToUser'}}


# Exact retained Task004 O2 Kernel3 non-inlined alternatives. All other
# pre/post bodies retain the original immutable pins. The historical metadata
# does not claim the separately selected checked-inline lowering contract.
KERNEL3_O0_POST = {'copyWord': '3fc01ca9b198462cab50212418a5d7bac024decb6b5c99850eb3d2933d9cbad8', 'copyWordTailStep': '98004326c04acac6598a15b2f3e9e02871d3466e4a819ba3cf60665b5052206d', 'copyWordGenericBlockStep': '26a8abdd1fe07b4e0d4bbaebfab00e7415023faca09f9ba01d9d1b6a77856d54', 'copyWordBlockStep': '5377934f7a9430939653420e4b7e8d6490d58dd70c787ecbe49087e8cf43e3e8', 'copyPageWords': 'aa47c6cd695d5502e67505e483c8c74642782f20fb340af9d9932f0ca6cc3d72', 'copyFromPages': '3d31610a251eb11de90ae84eee50c901b4bf2ff5a899091ebefeed6dc0e9357b', 'copyToPages': 'a3f53dcb7033e28fe9f03f933c8bba9c856dffd1aac9643a3842440d6cd5f37a', 'copyFromUserResult': '1d66a51e1d32cdbd699fabff7a2cd4ff668ff8b20ccb4ac73b8e09cef71cb986', 'copyFromUserReusingReadPage': '69daac959c57433357b799f56682b10f026f10889e5a46ad21babb7dafa9c9db'}

KERNEL3_POST = {'copyWord': '4d27ef720a282b05999fa6a7e2b12e8dfcd0b5e8f57ea239135c46d6b743eabd', 'copyWordGenericBlockStep': 'c6c53a66388b0054f19412e2e9701681adaf75de1164aec0539d09be9d4004bc', 'copyWordBlockStep': 'c27e6ad0412ced85faea38707d733fec9b98e48fed2833633c7a94796df4191d'}


def _kernel3_checked_pairs(body, rows, *, pairs, block, unoptimized=False):
    from audit_kernel import (_local_checked_result, validate_boolean_gate,
                              _structured_ir_blocks)
    access = 'Lemma.Kernel.Memory.Access.'
    if not {access+'read64', access+'write64'} <= rows.keys():
        raise Core0Error('page-word Kernel3 physical wrapper closure absent')
    read = rows[access+'read64']['symbol']; write = rows[access+'write64']['symbol']
    if rows[access+'read64']['args'] != ['u64'] or rows[access+'write64']['args'] != ['u64','u64'] or \
       rows[access+'read64']['effects'] != ['checked-access','physical-read'] or \
       rows[access+'write64']['effects'] != ['checked-access','physical-write']:
        raise Core0Error('page-word Kernel3 checked physical wrapper metadata differs')
    calls = [(result, target, args) for result,target,args in re.findall(
        r'(%[-\w.]+) = call \{ i64, i64 \} @([-A-Za-z0-9_.$]+)\(([^\n]*)\)', body)
        if target in (read,write)]
    if len(calls) != pairs*2:
        raise Core0Error('page-word Kernel3 original checked pair count differs')
    # An independent affine operand view of the exact LLVM zext/shl/add forms.
    # It does not rewrite the complete pinned bodies or admit new instructions.
    operands = {}
    def affine(token):
        if token in operands: return operands[token]
        if re.fullmatch(r'-?[0-9]+',token): return ({},int(token))
        return ({token:1},0)
    for line in body.splitlines():
        m = re.fullmatch(r'\s*(%[-\w.]+) = zext i32 (%[-\w.]+) to i64',line)
        if m: operands[m[1]]=affine(m[2]); continue
        m = re.fullmatch(r'\s*(%[-\w.]+) = shl(?: nuw)?(?: nsw)? i64 (%[-\w.]+), 6',line)
        if m:
            terms,constant=affine(m[2]);operands[m[1]]=({k:v*64 for k,v in terms.items()},constant*64);continue
        m = re.fullmatch(r'\s*(%[-\w.]+) = mul i64 (%[-\w.]+), 64',line)
        if m:
            terms,constant=affine(m[2]);operands[m[1]]=({k:v*64 for k,v in terms.items()},constant*64);continue
        m = re.fullmatch(r'\s*(%[-\w.]+) = add(?: nuw)?(?: nsw)? i64 ([^,]+), ([^ ]+)',line)
        if m:
            left,a=affine(m[2]);right,b=affine(m[3]);combined=left.copy()
            for k,v in right.items():combined[k]=combined.get(k,0)+v
            operands[m[1]]=(combined,a+b)
    parsed='\n'.join(line.split(';',1)[0].rstrip() for line in body.splitlines())
    blocks=_structured_ir_blocks(parsed)
    owners={result:label for result,_,_ in calls for label,lines in blocks.items()
            if any(line.startswith(result+' = call ') for line in lines)}
    gates=[]
    for index in range(pairs):
        result,target,args=calls[index*2];written,write_target,write_args=calls[index*2+1]
        fields=write_args.split(', ')
        source=({'%arg3':1,'%arg0':64},index*8) if block else ({'%arg0':1},0)
        destination=({'%arg4':1,'%arg0':64},index*8) if block else ({'%arg1':1},0)
        if target != read or write_target != write or not args.startswith('i64 ') or len(fields)!=2 or \
           affine(args[4:])!=source or affine(fields[0][4:])!=destination:
            raise Core0Error('page-word Kernel3 checked pair/address/stride order differs')
        _,value=_local_checked_result(body,read,args)
        if fields[1]!='i64 '+value:
            raise Core0Error('page-word Kernel3 write substitutes the original read value')
    for index,(result,target,args) in enumerate(calls):
        statuses=re.findall(r'(%[-\w.]+) = extractvalue \{ i64, i64 \} '+re.escape(result)+r', 0$',body,re.M)
        if len(statuses)!=1:
            raise Core0Error('page-word Kernel3 checked status extraction absent')
        tested=statuses[0]; width='i64'
        if unoptimized:
            narrowed=re.findall(r'(%[-\w.]+) = trunc i64 '+re.escape(tested)+r' to i8$',body,re.M)
            if len(narrowed)!=1:raise Core0Error('page-word O0 original status narrowing absent')
            tested=narrowed[0];width='i8'
        comparisons=re.findall(r'(%[-\w.]+) = icmp eq '+width+' '+re.escape(tested)+r', 0$',body,re.M)
        if len(comparisons)!=1:
            raise Core0Error('page-word Kernel3 original zero-status test differs')
        comparison=comparisons[0]
        if index+1<len(calls):
            next_result,next_target,_=calls[index+1]
            gates.append(validate_boolean_gate(parsed,comparison,next_target,
                                               protected_scope={owners[next_result]}))
        elif unoptimized:
            fatal_source='Lemma.User.ABI.kernelFatal'
            if fatal_source not in rows or (rows[fatal_source]['args'],rows[fatal_source]['effects'])!=([],[]):
                raise Core0Error('page-word O0 fatal source metadata differs')
            fatal=rows[fatal_source]['symbol']
            branch=re.findall(r'br i1 '+re.escape(comparison)+r', label %([-\w.]+), label %([-\w.]+)',parsed)
            if len(branch)!=1:raise Core0Error('page-word O0 final status branch differs')
            yes,no=branch[0];failure='\n'.join(blocks[no])
            result=re.findall(r'(%[-\w.]+) = call zeroext i8 @'+re.escape(fatal)+r'\(\)',failure)
            if len(result)!=1:raise Core0Error('page-word O0 final actual fatal call absent')
            gates.append(validate_boolean_gate(parsed,comparison,fatal,success_when_true=False,protected_scope={no}))
            phi=r'phi i8 \[ 0, %'+re.escape(yes)+r' \], \[ '+re.escape(result[0])+r', %'+re.escape(no)+r' \]'
            if len(re.findall(phi,parsed))!=1:raise Core0Error('page-word O0 final success/fatal status phi differs')
            if block:
                values=[name for name,value in operands.items() if value==({'%arg2':1},64)]
                phi=r'phi i64 \[ '+re.escape(values[0] if len(values)==1 else 'ABSENT')+r', %'+re.escape(yes)+r' \], \[ 0, %'+re.escape(no)+r' \]'
                if len(values)!=1 or len(re.findall(phi,parsed))!=1:raise Core0Error('page-word O0 final64-byte prefix accumulator differs')
        else:
            if len(re.findall(r'select i1 '+re.escape(comparison)+r', i64 0, i64 255$',body,re.M))!=1:
                raise Core0Error('page-word Kernel3 final checked success/fatal outcome differs')
            if block:
                values=[name for name,value in operands.items() if value==({'%arg2':1},64)]
                if len(values)!=1 or len(re.findall(r'select i1 '+re.escape(comparison)+
                        r', i64 '+re.escape(values[0])+r', i64 0$',body,re.M))!=1:
                    raise Core0Error('page-word Kernel3 final64-byte prefix accumulator differs')
    return {'checked_pairs':pairs,'ordered_status_gates':gates,
            'final_status':'zero on successful last write, kernel-fatal255 otherwise',
            'scope':'Real non-inlined checked wrapper calls, exact original addresses/values/status order; primitive hardware contract audited separately'}


def validate_if_present(ir, unit, *, optimized, optimization=None):
    from paper_next import canonical
    sources = {canonical(row['source']) for row in unit.get('functions', [])}
    new_family = any(BASE+name in sources for name in CALLERS)
    surface_borrow = bool({BASE+'copyFromUserReusingReadPage',
                          'Lemma.Platform.LemmaSim.DeviceService.uploadBorrowed'} & sources)
    if new_family and unit.get('role') != 'kernel':
        raise Core0Error('page-word helper escaped kernel role')
    if new_family and surface_borrow:
        # A selected family with a missing member reaches validate and fails;
        # it cannot fall through to historical callback admission.
        return validate(ir, unit, optimized=optimized, optimization=optimization)
    return None


KERNEL3_ROOTS = {
    'lemmasim-notebook': 'Lemma.Platform.LemmaSim.NotebookKernel.boot',
    'lemmasim-initialize': 'Lemma.Platform.LemmaSim.NotebookKernel.initializeMedium',
}

def validate(ir, unit, *, optimized, optimization=None):
    from audit_kernel import (_ir_definition_body, parse_definitions_and_calls,
                              _local_arithmetic, _local_call_arguments,
                              _local_checked_result, _local_closed_calls)
    from paper_next import canonical
    entries = unit.get('functions', [])
    rows = {canonical(r['source']): r for r in entries}
    if len(rows) != len(entries):
        raise Core0Error('page-word duplicate source inventory')
    if unit.get('role') != 'kernel' or not {BASE+s for s in ARGUMENTS} <= rows.keys():
        raise Core0Error('page-word closed kernel helper inventory absent')
    names = {r['symbol']: source for source, r in rows.items()}
    phase = 'post' if optimized else 'pre'
    kernel3=unit.get('contract_version')=='core0-kernel-v0.3'
    if kernel3 and (unit.get('configuration') not in KERNEL3_ROOTS or unit.get('managed_policy')!='lemma-notebook-v1' or
                    unit.get('schema_version')!=1 or unit.get('artifact_category')!='development-kernel-unit' or
                    'checked_inline' in unit or
                    [(canonical(row['source']),row['id'],row['args']) for row in unit.get('roots',[])]!=
                    [(KERNEL3_ROOTS.get(unit.get('configuration')),1,[]),
                     ('Lemma.Platform.LemmaSim.NotebookKernel.dispatch',2,['u64','u64','u64'])]):
        raise Core0Error('page-word Kernel3 historical configuration/lowering authority differs')
    o0_post=kernel3 and optimized and optimization=='O0'
    observed = {}
    def body(source):
        result = _ir_definition_body(ir, rows[source]['symbol'])
        if result is None:
            raise Core0Error('page-word actual emitted body absent: '+source)
        return result
    for suffix, args in ARGUMENTS.items():
        source = BASE+suffix
        row = rows[source]
        if row['args'] != args or row['effects'] != EFFECTS:
            raise Core0Error('page-word exact signature/effects differ: '+source)
        normalized = ' '.join(re.sub(r'@([^ (]+)', lambda m: '@'+names.get(m[1], m[1]), body(source)).split())
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        expected=KERNEL3_O0_POST[suffix] if o0_post else KERNEL3_POST.get(suffix,PINS[phase][suffix]) if kernel3 and optimized else PINS[phase][suffix]
        if optimized:
            from product_reader_target import post_helper_pin
            expected=post_helper_pin(unit,source,expected)
        if digest != expected:
            raise Core0Error('page-word complete checked body differs: '+source+'/'+phase)
        observed[source] = digest
    incoming = {BASE+s: set() for s in CALLERS}
    for source, row in rows.items():
        emitted = _ir_definition_body(ir, row['symbol'])
        if emitted is None:
            raise Core0Error('page-word closed caller body absent: '+source)
        for called in parse_definitions_and_calls(emitted)[2]:
            target = names.get(called, called)
            if target in incoming:
                incoming[target].add(source)
    for suffix, sources in CALLERS.items():
        expected_sources = {BASE+s for s in sources}
        if suffix == 'copyFromPages' and BASE+'copyFromUserAt' in rows:
            # The mandatory Surface observer binds its complete Kernel4 family
            # and sole private caller. Every historical caller set is exact.
            expected_sources.add(BASE+'copyFromUserAt')
        if incoming[BASE+suffix] != expected_sources:
            raise Core0Error('page-word private helper caller closure differs: '+suffix)
    operations = None
    if optimized and kernel3 and not o0_post:
        gates={suffix:_kernel3_checked_pairs(body(BASE+suffix),rows,pairs=1 if suffix=='copyWord' else 8,block=suffix!='copyWord')
               for suffix in KERNEL3_POST}
        operations={'block_words':8,'ordered_checked_accesses':16,'word_bits':64,'lowering':'historical Kernel3 non-inlined checked wrappers',
                    'checked_call_gates':gates,'scope':'Complete original prebody and all9 postbodies, exact real checked call/failure prefix audit'}
    if optimized and not kernel3:
        for suffix in ('copyWordGenericBlockStep', 'copyWordBlockStep'):
            instructions = [line.strip() for line in body(BASE+suffix).splitlines()
                            if re.search(r'\b(load|store)\b', line)]
            if len(instructions) != 16:
                raise Core0Error('page-word optimized eight-pair operation inventory differs')
            for index in range(8):
                read = re.fullmatch(r'(%[-\w.]+) = load volatile i64, ptr %[-\w.]+, align 8', instructions[index*2])
                if read is None or re.fullmatch(r'store volatile i64 '+re.escape(read[1])+r', ptr %[-\w.]+, align 8', instructions[index*2+1]) is None:
                    raise Core0Error('page-word optimized volatile read/write order/value differs')
        operations = {'block_words': 8, 'ordered_volatile_accesses': 16,
                      'word_bits': 64, 'alignment_bytes': 8,
                      'scope': 'Actual optimized volatile operations; complete pins retain guards, tails and global-fault prefixes'}
    if not optimized or o0_post:
        access = 'Lemma.Kernel.Memory.Access.'
        required = {access+'read64', access+'write64', 'Lemma.User.ABI.kernelFatal',
                    'Lemma.Kernel.Memory.Frames.pool', 'Lemma.Kernel.Memory.Frames.expandedPoolLimit'}
        if not required <= rows.keys():
            raise Core0Error('page-word actual primitive/constant closure absent')
        reads = rows[access+'read64']['symbol']
        writes = rows[access+'write64']['symbol']
        fatal = rows['Lemma.User.ABI.kernelFatal']['symbol']
        for suffix in ('copyWordGenericBlockStep', 'copyWordBlockStep'):
            text = operation_view(body(BASE+suffix))
            arithmetic = _local_arithmetic(text, {})
            ordered = [(names.get(called, called), arguments)
                       for called, arguments in re.findall(r'call \{ i64, i64 \} @([-A-Za-z0-9_.$]+)\(([^\n]*)\)', text)
                       if called in (reads, writes)]
            if len(ordered) != 16:
                raise Core0Error('page-word block is not exactly eight checked read/write pairs')
            offset = ('mul', ('zext32', '%arg0'), 64)
            first = ('add', '%arg3', offset)
            destination = ('add', '%arg4', offset)
            for index in range(8):
                read_owner, read_args = ordered[index*2]
                write_owner, write_args = ordered[index*2+1]
                fields = write_args.split(', ')
                a = first if index == 0 else ('add', first, index*8)
                b = destination if index == 0 else ('add', destination, index*8)
                if read_owner != access+'read64' or write_owner != access+'write64' or len(fields) != 2 or arithmetic.get(read_args[4:]) != a or arithmetic.get(fields[0][4:]) != b:
                    raise Core0Error('page-word actual access order/word stride/address differs')
                _, value = _local_checked_result(text, reads, read_args)
                if fields[1] != 'i64 '+value:
                    raise Core0Error('page-word destination substitutes the original read value')
            allowed = {reads, writes, fatal}
            if suffix == 'copyWordBlockStep':
                allowed |= {rows[BASE+'copyWordGenericBlockStep']['symbol'],
                            rows['Lemma.Kernel.Memory.Frames.pool']['symbol'],
                            rows['Lemma.Kernel.Memory.Frames.expandedPoolLimit']['symbol']}
            _local_closed_calls(text, allowed)
        page = operation_view(body(BASE+'copyPageWords'))
        if not re.search(r'icmp ule i32 %[-\w.]+, 64$', page, re.M) or not re.search(r'icmp ule i32 %[-\w.]+, 7$', page, re.M):
            raise Core0Error('page-word exact64-block/7-word-tail budgets absent')
        if len(_local_call_arguments(page, rows[BASE+'copyWordBlockStep']['symbol'])) != 1 or len(_local_call_arguments(page, rows[BASE+'copyWordTailStep']['symbol'])) != 1:
            raise Core0Error('page-word block/tail callback inventory differs')
        for suffix in ('copyFromPages', 'copyToPages'):
            if len(_local_call_arguments(body(BASE+suffix), rows[BASE+'copyPageWords']['symbol'])) != 2:
                raise Core0Error('page-word ordered two-span callback inventory differs')
        if o0_post:
            fatal_body=_ir_definition_body(ir,fatal)
            if re.fullmatch(r'\s*entry:\s*ret i8 (?:255|-1)\s*',fatal_body) is None:raise Core0Error('page-word O0 actual fatal scalar differs')
            gates={suffix:_kernel3_checked_pairs(operation_view(body(BASE+suffix)),rows,pairs=1 if suffix=='copyWord' else 8,block=suffix!='copyWord',unoptimized=True) for suffix in KERNEL3_POST}
        operations = {'block_words': 8, 'ordered_checked_accesses': 16,
                      'maximum_blocks': 64, 'maximum_tail_words': 7,
                      'first_page_before_second': True, 'no_new_primitive_or_effect': True, **({'lowering':'historical Kernel3 O0 checked wrappers','checked_call_gates':gates} if o0_post else {})}
    return {'contract_version': 'lemma-user-copy-page-word-artifact-v1', 'phase': phase,
            'complete_shapes': observed, 'private_callers': {s: sorted(c) for s,c in incoming.items()},
            'operations': operations,
            'scope': 'Genuine complete checked pre/post artifact shapes and actual ordered accesses; finite Action equivalence separate, no compiler-correctness/guest-speed claim'}


def operation_view(body):
    # Presentation-only view for independent gates. Complete literal actual O0
    # pin hashing above removes no comments, instructions, labels or operands.
    text='\n'.join(line.split(';',1)[0].rstrip() for line in body.splitlines())
    return re.sub(r'(icmp eq i1 %[-\w.]+, )(true|false)\b',lambda m:m[1]+('1' if m[2]=='true' else '0'),text)
