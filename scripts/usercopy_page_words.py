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


def validate_if_present(ir, unit, *, optimized):
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
        return validate(ir, unit, optimized=optimized)
    return None


def validate(ir, unit, *, optimized):
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
        if digest != PINS[phase][suffix]:
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
    if optimized:
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
    if not optimized:
        access = 'Lemma.Kernel.Memory.Access.'
        required = {access+'read64', access+'write64', 'Lemma.User.ABI.kernelFatal',
                    'Lemma.Kernel.Memory.Frames.pool', 'Lemma.Kernel.Memory.Frames.expandedPoolLimit'}
        if not required <= rows.keys():
            raise Core0Error('page-word actual primitive/constant closure absent')
        reads = rows[access+'read64']['symbol']
        writes = rows[access+'write64']['symbol']
        fatal = rows['Lemma.User.ABI.kernelFatal']['symbol']
        for suffix in ('copyWordGenericBlockStep', 'copyWordBlockStep'):
            text = body(BASE+suffix)
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
        page = body(BASE+'copyPageWords')
        if not re.search(r'icmp ule i32 %[-\w.]+, 64$', page, re.M) or not re.search(r'icmp ule i32 %[-\w.]+, 7$', page, re.M):
            raise Core0Error('page-word exact64-block/7-word-tail budgets absent')
        if len(_local_call_arguments(page, rows[BASE+'copyWordBlockStep']['symbol'])) != 1 or len(_local_call_arguments(page, rows[BASE+'copyWordTailStep']['symbol'])) != 1:
            raise Core0Error('page-word block/tail callback inventory differs')
        for suffix in ('copyFromPages', 'copyToPages'):
            if len(_local_call_arguments(body(BASE+suffix), rows[BASE+'copyPageWords']['symbol'])) != 2:
                raise Core0Error('page-word ordered two-span callback inventory differs')
        operations = {'block_words': 8, 'ordered_checked_accesses': 16,
                      'maximum_blocks': 64, 'maximum_tail_words': 7,
                      'first_page_before_second': True, 'no_new_primitive_or_effect': True}
    return {'contract_version': 'lemma-user-copy-page-word-artifact-v1', 'phase': phase,
            'complete_shapes': observed, 'private_callers': {s: sorted(c) for s,c in incoming.items()},
            'operations': operations,
            'scope': 'Genuine complete checked pre/post artifact shapes and actual ordered accesses; finite Action equivalence separate, no compiler-correctness/guest-speed claim'}
