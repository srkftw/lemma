"""Strict artifact observer for same-Action Surface bulk borrow/group v1.

Pins are from real ordinary Kernel4 declarations and complete checked LLVM/O2
objects under the retained100-input component seal. Actual finite Action
comparison preserves all retained effects; removed duplicate metadata reads
have an explicitly limited fault contract. This is an audit, not a compiler
proof, target interpreter, host renderer or guest timing claim.
"""
from __future__ import annotations
import hashlib
import re
from core0_common import Core0Error

CAP = 'Lemma.Kernel.Capability.'
COPY = 'Lemma.Kernel.Memory.UserCopy.'
PAPER = 'Lemma.Drivers.Paper.'
DEVICE = 'Lemma.Platform.LemmaSim.DeviceService.'
NOTEBOOK = 'Lemma.Platform.LemmaSim.NotebookKernel.'

# Genuine LLVM20 O2 derives nonoverflowing additions from the new bounded
# descriptor result. Each complete caller body changes only that one add flag.
DESCRIPTOR_DIRECT_POST_CALLER_PINS = {
    'Lemma.Kernel.Process.validateFrame': 'b37bdf8b7d913f2b1a4dfc1cc6abc269919b02fcfb97ffef34e262d57d6c11de',
    'Lemma.Kernel.Task.capture': '4dfc90ac413d381dbdfdb37c2eecc4e2fdbe72b702503b99bedfaca5828f149e',
}

CALLERS = {
    CAP+'requireActiveAt': {CAP+'lookupEntryAt'},
    CAP+'lookupEntryAt': {CAP+'lookupAt'},
    CAP+'lookupAt': {DEVICE+'authorizeAt'},
    COPY+'checkedBorrowedBase': {COPY+'copyFromUserAt'},
    COPY+'copyFromUserAt': {DEVICE+'uploadBulkAt'},
    PAPER+'uploadWordBlockAt': {PAPER+'uploadWordsAt'},
    PAPER+'uploadWordTailAt': {PAPER+'uploadWordsAt'},
    PAPER+'uploadWordsAt': {PAPER+'uploadOffsetAt'},
    PAPER+'uploadOffsetAt': {DEVICE+'bulkUploadStepAt'},
    DEVICE+'authorizeAt': {DEVICE+'surfaceV2At'},
    DEVICE+'bulkUploadStepAt': {DEVICE+'uploadBulkAt'},
    DEVICE+'uploadBulkAt': {DEVICE+'surfaceV2At'},
    DEVICE+'surfaceV2At': {NOTEBOOK+'deviceCallBulkAt'},
    NOTEBOOK+'deviceCallBulkAt': {NOTEBOOK+'dispatchBulk'},
}


def canonical(source):
    return re.sub(r'^_private\..*?\.[0-9]+\.', '', source)


def normalized_body(text, names):
    """Rebind exact catalog symbols, including LLVM inlined exit labels.

    No instructions, operands, suffixes or guards are removed. LLVM embeds a
    callee's reachability-dependent symbol in these labels; the one-to-one
    catalog mapping preserves every definition/reference and its exact suffix.
    Unknown labels receive no rewriting.
    """
    rebound = re.sub(r'@([^ (]+)', lambda m: '@'+names.get(m[1], m[1]), text)
    rebound = re.sub(r'(?<![-A-Za-z0-9_.$])([-A-Za-z0-9_.$]+)(?=\.exit(?:[0-9.:,\]\s]|$))',
                     lambda m: names.get(m[1], m[1]), rebound)
    return ' '.join(rebound.split())


def validate_if_present(ir, unit, *, optimized):
    sources = {canonical(row['source']) for row in unit.get('functions', [])}
    if not FAMILY & sources:
        return None
    # A partial selected family must fail inside validate, not return None.
    return validate(ir, unit, optimized=optimized)


def validate(ir, unit, *, optimized):
    from audit_kernel import (_ir_definition_body, _local_arithmetic,
                              _local_call_arguments, _local_checked_result)
    from audit_device import _line_functions
    entries = unit.get('functions', [])
    rows = {canonical(row['source']): row for row in entries}
    if len(rows) != len(entries):
        raise Core0Error('Surface critical borrow has duplicate canonical sources')
    if unit.get('role') != 'kernel' or unit.get('contract_version', unit.get('profile')) != 'core0-kernel-v0.4':
        raise Core0Error('Surface critical borrow escaped its exact Kernel4 profile')
    if not set(SIGNATURES) <= rows.keys():
        raise Core0Error('Surface critical borrow complete authority family absent')
    names = {row['symbol']: source for source, row in rows.items()}
    if len(names) != len(rows):
        raise Core0Error('Surface critical borrow has duplicate symbols')
    phase = 'post' if optimized else 'pre'
    observed = {}
    descriptor_cohort = None

    def body(source):
        result = _ir_definition_body(ir, rows[source]['symbol'])
        if result is None:
            raise Core0Error('Surface critical borrow actual body missing: '+source)
        return result

    from task_entry_borrow import DESCRIPTOR_DIRECT_PINS, validate_registry_borrow
    base = 'Lemma.Kernel.Memory.AddressSpace.base'
    if hashlib.sha256(normalized_body(body(base), names).encode()).hexdigest() == DESCRIPTOR_DIRECT_PINS[phase]:
        descriptor_cohort = validate_registry_borrow(ir, rows, names, phase)
        if not descriptor_cohort:
            raise Core0Error('Surface direct descriptor lacks its complete count authority')

    for source, (arguments, effects) in SIGNATURES.items():
        row = rows[source]
        if row['args'] != arguments or row['effects'] != effects:
            raise Core0Error('Surface critical borrow signature/effects differ: '+source)
        normalized = normalized_body(body(source), names)
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        expected = PINS[phase][source]
        if descriptor_cohort:
            if source == base:
                expected = DESCRIPTOR_DIRECT_PINS[phase]
            elif optimized:
                expected = DESCRIPTOR_DIRECT_POST_CALLER_PINS.get(source, expected)
        if digest != expected:
            raise Core0Error('Surface critical borrow complete checked body differs: '+source+'/'+phase)
        observed[source] = digest

    incoming = {source: set() for source in CALLERS}
    lines = ir.splitlines()
    owners = _line_functions(lines)
    for index, line in enumerate(lines):
        for target in re.findall(r'\bcall\b[^\n]*?@([-A-Za-z0-9_.$]+)\(', line):
            source = names.get(target, target)
            if source in incoming:
                incoming[source].add(names.get(owners[index], owners[index]))
    if incoming != CALLERS:
        raise Core0Error('Surface critical borrow acquired missing/additional private caller authority')

    block = body(PAPER+'uploadWordBlockAt')
    if optimized:
        # Exactly eight actual load/fence/store/fence groups. LLVM's stronger
        # store alignments are justified by the exact bounded staging offsets;
        # complete pins bind those addresses and every dominating guard.
        operations = [line.strip() for line in block.splitlines()
                      if re.search(r'\b(load|store) volatile\b|call void @core0_io_fence\(\)', line)]
        if len(operations) != 32:
            raise Core0Error('Surface critical borrow eight-pair effect inventory differs')
        for index in range(8):
            read, before, write, after = operations[index*4:index*4+4]
            match = re.fullmatch(r'(%[-\w.]+) = load volatile i64, ptr %[-\w.]+, align 8', read)
            if match is None or before != 'call void @core0_io_fence()' or after != before:
                raise Core0Error('Surface critical borrow original load/fence order differs')
            if re.fullmatch(r'store volatile i64 '+re.escape(match[1])+r', ptr %[-\w.]+, align (8|16|32|64)', write) is None:
                raise Core0Error('Surface critical borrow substitutes word/width/fence order')
    else:
        context_constant = 'Lemma.Kernel.Memory.AddressSpace.userContextOffset'
        if context_constant not in rows or body(context_constant).strip() != 'entry:\n  ret i64 2048':
            raise Core0Error('Surface critical borrow actual saved-context constant differs')
        constants = {rows[context_constant]['symbol']: 2048}
        def calls(owner, callee):
            return _local_call_arguments(body(owner), rows[callee]['symbol'])

        if calls(DEVICE+'surfaceV2At', DEVICE+'authorizeAt') != ['i64 %arg0, i64 %arg1, i64 %arg2, i64 0'] or \
                calls(DEVICE+'surfaceV2At', DEVICE+'uploadBulkAt') != ['i64 %arg0, i64 %arg1, i64 %arg4, i64 %arg5']:
            raise Core0Error('Surface critical borrow descriptor/cap/pointer/count operands differ')
        if calls(CAP+'lookupAt', CAP+'lookupEntryAt') != ['i64 %arg0, i64 %arg1, i64 %arg2']:
            raise Core0Error('Surface critical borrow capability handle/base mapping differs')
        if calls(COPY+'copyFromUserAt', COPY+'scratch') != ['i64 %arg2, i64 %arg3, i64 %arg4'] or \
                calls(COPY+'copyFromUserAt', COPY+'checkedBorrowedBase') != ['i64 %arg0, i64 %arg1, i64 1']:
            raise Core0Error('Surface critical borrow fresh scratch/range admission differs')
        device = body(NOTEBOOK+'deviceCallBulkAt')
        args = calls(NOTEBOOK+'deviceCallBulkAt', DEVICE+'surfaceV2At')
        if len(args) != 1:
            raise Core0Error('Surface critical borrow selected device call absent')
        fields = args[0].split(', ')
        arithmetic = _local_arithmetic(device, constants)
        if len(fields) != 7 or fields[0] != 'i64 %arg0' or arithmetic.get(fields[1][4:]) != ('sub', '%arg1', 2048):
            raise Core0Error('Surface critical borrow is not derived from fresh captured context')
        read = rows['Lemma.Kernel.Memory.Access.read64']['symbol']
        for field, offset in zip(fields[2:], (80,88,96,104,112)):
            reads = _local_call_arguments(device, read)
            found = [a for a in reads if arithmetic.get(a[4:]) == ('add', '%arg1', offset)]
            if len(found) != 1 or field != 'i64 '+_local_checked_result(device, read, found[0])[1]:
                raise Core0Error('Surface critical borrow substitutes original syscall argument')
        dispatcher = body(NOTEBOOK+'dispatchBulk')
        capture = rows['Lemma.Kernel.Task.capture']['symbol']
        capture_args = _local_call_arguments(dispatcher, capture)
        # Interrupt capture is unchanged; syscall capture is the second genuine
        # occurrence. Full pins bind both complete guards and effect order.
        if len(capture_args) != 2:
            raise Core0Error('Surface critical borrow original trap captures differ')
        context = _local_checked_result(dispatcher, capture, capture_args[1])[1]
        arithmetic = _local_arithmetic(dispatcher, constants)
        lookup_args = calls(NOTEBOOK+'dispatchBulk', 'Lemma.Kernel.Memory.AddressSpace.lookupAt')
        if len(lookup_args) != 1:
            raise Core0Error('Surface critical borrow checked executable-PC lookup absent')
        fields = lookup_args[0].split(', ')
        if len(fields) != 3 or arithmetic.get(fields[0][4:]) != ('sub', context, 2048) or fields[2] != 'i64 4':
            raise Core0Error('Surface critical borrow executable permission/captured base differs')
        words = body(PAPER+'uploadWordsAt')
        if not re.search(r'icmp ule i32 %[-\w.]+, 8$', words, re.M) or not re.search(r'icmp ule i32 %[-\w.]+, 7$', words, re.M):
            raise Core0Error('Surface critical borrow block/tail budgets differ')
        if not re.search(r'icmp ult i32 %arg0, 8$', block, re.M):
            raise Core0Error('Surface critical borrow private block bound absent')
        reads = _local_call_arguments(block, read)
        if len(reads) != 8:
            raise Core0Error('Surface critical borrow does not retain exactly eight checked source reads')
        arithmetic = _local_arithmetic(block, {})
        first = ('add', '%arg3', ('mul', ('mul', ('zext32', '%arg0'), 8), 8))
        for index, args in enumerate(reads):
            expected = first if index == 0 else ('add', first, index*8)
            if arithmetic.get(args[4:]) != expected:
                raise Core0Error('Surface critical borrow original increasing word stride differs')
            value = _local_checked_result(block, read, args)[1]
            # The two declared device intervals each have a guarded success
            # store in pre-IR. O2 proves the exact private staging interval and
            # leaves one fenced store, independently checked above.
            if len(re.findall(r'store volatile i64 '+re.escape(value)+r', ptr %[-\w.]+, align 8', block)) != 2:
                raise Core0Error('Surface critical borrow pre-IR staging stores substitute source value')
    return {'contract_version': 'lemma-surface-bulk-critical-borrow-v1',
            **({'descriptor_direct_loads': 'lemma-descriptor-direct-loads-v1',
                'registry_count_borrow': descriptor_cohort} if descriptor_cohort else {}),
            'body_identities': observed, 'phase': phase,
            'scope': 'Genuine checked source/body/caller and ordered physical/PIO grouping audit; no temporal fault or guest timing claim'}
FAMILY = frozenset(['Lemma.Drivers.Paper.uploadOffsetAt',
 'Lemma.Drivers.Paper.uploadWordBlockAt',
 'Lemma.Drivers.Paper.uploadWordTailAt',
 'Lemma.Drivers.Paper.uploadWordsAt',
 'Lemma.Kernel.Capability.lookupAt',
 'Lemma.Kernel.Capability.lookupEntryAt',
 'Lemma.Kernel.Capability.requireActiveAt',
 'Lemma.Kernel.Memory.UserCopy.checkedBorrowedBase',
 'Lemma.Kernel.Memory.UserCopy.copyFromUserAt',
 'Lemma.Platform.LemmaSim.DeviceService.authorizeAt',
 'Lemma.Platform.LemmaSim.DeviceService.bulkUploadStepAt',
 'Lemma.Platform.LemmaSim.DeviceService.surfaceV2At',
 'Lemma.Platform.LemmaSim.DeviceService.uploadBulkAt',
 'Lemma.Platform.LemmaSim.NotebookKernel.deviceCallBulkAt'])
SIGNATURES = {'Lemma.Drivers.Paper.uploadOffsetAt': (['u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                        ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read']),
 'Lemma.Drivers.Paper.uploadWordBlockAt': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                           ['checked-access', 'mmio-write', 'io-order', 'physical-read']),
 'Lemma.Drivers.Paper.uploadWordTailAt': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                          ['checked-access', 'mmio-write', 'io-order', 'physical-read']),
 'Lemma.Drivers.Paper.uploadWordsAt': (['u64', 'u64'], ['checked-access', 'mmio-write', 'io-order', 'physical-read']),
 'Lemma.Kernel.Capability.headerAt': (['u64', 'u64'], ['checked-access', 'physical-read']),
 'Lemma.Kernel.Capability.lookupAt': (['u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read']),
 'Lemma.Kernel.Capability.lookupEntryAt': (['u64', 'u64', 'u64'], ['checked-access', 'physical-read']),
 'Lemma.Kernel.Capability.requireActiveAt': (['u64', 'u64'], ['checked-access', 'physical-read']),
 'Lemma.Kernel.Loader.validateExpandedStackAt': (['u64'], ['checked-access', 'physical-read']),
 'Lemma.Kernel.Memory.AddressSpace.base': (['u64'], ['checked-access', 'physical-read']),
 'Lemma.Kernel.Memory.AddressSpace.lookupAt': (['u64', 'u64', 'u64'], ['checked-access', 'physical-read']),
 'Lemma.Kernel.Memory.Frames.resolvePurpose': (['u64', 'u64', 'u64'], ['checked-access', 'physical-read']),
 'Lemma.Kernel.Memory.UserCopy.checkedBorrowedBase': (['u64', 'u64', 'u64'], []),
 'Lemma.Kernel.Memory.UserCopy.checkedLookupAt': (['u64', 'u64', 'u64'], ['checked-access', 'physical-read']),
 'Lemma.Kernel.Memory.UserCopy.copyFromUserAt': (['u64', 'u64', 'u64', 'u64', 'u64'],
                                                 ['checked-access', 'physical-read', 'physical-write']),
 'Lemma.Kernel.Memory.UserCopy.scratch': (['u64', 'u64', 'u64'], ['checked-access', 'physical-read']),
 'Lemma.Kernel.Process.validateFrame': (['u64'], ['checked-access', 'physical-read']),
 'Lemma.Kernel.Process.validateStackAt': (['u64'], ['checked-access', 'physical-read']),
 'Lemma.Kernel.Task.capture': (['u64', 'u64'], ['checked-access', 'physical-read', 'physical-write']),
 'Lemma.Kernel.Task.contextAt': (['u64', 'u64', 'u64'], ['checked-access', 'physical-read', 'physical-write']),
 'Lemma.Kernel.Task.copyStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                ['checked-access', 'physical-read', 'physical-write']),
 'Lemma.Platform.LemmaSim.DeviceService.authorizeAt': (['u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read']),
 'Lemma.Platform.LemmaSim.DeviceService.bulkUploadStepAt': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                                            ['checked-access',
                                                             'mmio-read',
                                                             'mmio-write',
                                                             'io-order',
                                                             'physical-read']),
 'Lemma.Platform.LemmaSim.DeviceService.bulkValidateStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                                            ['checked-access', 'physical-read']),
 'Lemma.Platform.LemmaSim.DeviceService.surfaceV2At': (['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                                       ['checked-access',
                                                        'mmio-read',
                                                        'mmio-write',
                                                        'io-order',
                                                        'physical-read',
                                                        'physical-write']),
 'Lemma.Platform.LemmaSim.DeviceService.uploadBulkAt': (['u64', 'u64', 'u64', 'u64'],
                                                        ['checked-access',
                                                         'mmio-read',
                                                         'mmio-write',
                                                         'io-order',
                                                         'physical-read',
                                                         'physical-write']),
 'Lemma.Platform.LemmaSim.NotebookKernel.deviceCallBulkAt': (['u64', 'u64', 'u64', 'u64'],
                                                             ['checked-access',
                                                              'mmio-read',
                                                              'mmio-write',
                                                              'io-order',
                                                              'machine-state',
                                                              'physical-read',
                                                              'physical-write',
                                                              'firmware-call']),
 'Lemma.Platform.LemmaSim.NotebookKernel.dispatchBulk': (['u64', 'u64', 'u64'],
                                                         ['checked-access',
                                                          'mmio-read',
                                                          'mmio-write',
                                                          'io-order',
                                                          'machine-state',
                                                          'interrupt-state',
                                                          'physical-read',
                                                          'physical-write',
                                                          'firmware-call',
                                                          'address-space',
                                                          'wait-state'])}
PINS = {'post': {'Lemma.Drivers.Paper.uploadOffsetAt': 'f031596f0baf1227a1695e488a05d06832ccab1bf2b61b2a082d9132c2c93f09',
          'Lemma.Drivers.Paper.uploadWordBlockAt': '27699a7fd855c4db5dfa97e7c83f255679e4e7fdf9b68a56b2888792e2c1b315',
          'Lemma.Drivers.Paper.uploadWordTailAt': '308808b6ee16b167a9912de11d245dc115703e0bb5c8aff36aad90d544a6d5c4',
          'Lemma.Drivers.Paper.uploadWordsAt': 'fa336e4c4cf4db90833df5e451e5a2d8924810fdf4a586d375b7abf80b1ec701',
          'Lemma.Kernel.Capability.headerAt': '4f16af824096b451f0af17ed5dcda95fe78bce867eccb155791a828e83dd1779',
          'Lemma.Kernel.Capability.lookupAt': '8160c608b5573df4e25e01abc223dd1446ee0932d8b3f2d83f615a23b6e4c1f9',
          'Lemma.Kernel.Capability.lookupEntryAt': '836728fb3428e6c49456afdd54c5af21881424217917e2aab0e4ccd707b8779f',
          'Lemma.Kernel.Capability.requireActiveAt': 'b5a3e9c7d7cc18f97489d8d23af439e276405dbaa6049398e7c409cf0e39c831',
          'Lemma.Kernel.Loader.validateExpandedStackAt': 'e7f88b0a00ed0c99fa8d1e0e3b196d471052e5fb80221a44ba03f3530007f1a1',
          'Lemma.Kernel.Memory.AddressSpace.base': 'd5563c74bf564f2eb3f2dcdebebef7948a6c19fd296a64281f8225c65ab1528a',
          'Lemma.Kernel.Memory.AddressSpace.lookupAt': '9272294f91fafd6ec874091dfa7af4292daef012267651aed19fc631def7472d',
          'Lemma.Kernel.Memory.Frames.resolvePurpose': 'a830c7e0ba8b4e594a068fa4a2b1976fa69cdc4d39d5e2a44760ce7c8161f576',
          'Lemma.Kernel.Memory.UserCopy.checkedBorrowedBase': '2b064920cb5c688ef3892fe8b8b208c4781f7eea2f7b60ad0058570b9d35c9f7',
          'Lemma.Kernel.Memory.UserCopy.checkedLookupAt': '7cea6a98579a09a66a1639c29aed937d90df4e129b778dcabe672f82afa25664',
          'Lemma.Kernel.Memory.UserCopy.copyFromUserAt': '93ee5f4b0bbe7e85d7c20fd07530002c1789b38ea79f0a73a4ece112fafe9110',
          'Lemma.Kernel.Memory.UserCopy.scratch': 'ed71984b26928d2e9b5b6b9e2e110bdd3f1b8b65370ee879f149f9c452faada9',
          'Lemma.Kernel.Process.validateFrame': 'bc618ec1d30439d5929ba5a61df50a59b46cd5cf62f70f0a86df6d99ba47af65',
          'Lemma.Kernel.Process.validateStackAt': '2645d330d094be976b94cdb9143491d9d0185266cc9ac360da64c39b5f98bafe',
          'Lemma.Kernel.Task.capture': 'a2b56962506e07f8597cd954e2137f015cfe319004322947d719d3a73b5d7e66',
          'Lemma.Kernel.Task.contextAt': 'f15e99b531051616f53b9a268f6d67fbcd90ba890c7c9ee6d22e709ba26a3af5',
          'Lemma.Kernel.Task.copyStep': '2461fdce87ac644eeccf5d5242c892d646a9ee928df4a389adb84c061c4e14f2',
          'Lemma.Platform.LemmaSim.DeviceService.authorizeAt': '16a868ede0eb1bc77b8794daa9034de23d1521a1f27a73fa004e3e77c8a011d6',
          'Lemma.Platform.LemmaSim.DeviceService.bulkUploadStepAt': 'bd20bac028204dde8526f76a07f6b61c06c5499f5d65d9a60e56b3864d30d0ed',
          'Lemma.Platform.LemmaSim.DeviceService.bulkValidateStep': '2ddf5d79d1a39c4ca48ff2cfc0a46a59a2c4eab2c457d0289673597d3559b665',
          'Lemma.Platform.LemmaSim.DeviceService.surfaceV2At': 'fc5b49bf048d84502f801912d09023cb6c6fe9b684fd32e85244a3e86aea4d9e',
          'Lemma.Platform.LemmaSim.DeviceService.uploadBulkAt': '36243537fa97ad0573021f0e00913968c1d8a8bb7d46b8fe9ffba125a904fb60',
          'Lemma.Platform.LemmaSim.NotebookKernel.deviceCallBulkAt': 'a402dc2c90b5dbf466b59bd285d25e24cc15605f5437562bde95decd75d555b3',
          'Lemma.Platform.LemmaSim.NotebookKernel.dispatchBulk': 'c5b566fc1de6f79fcb23817adfbc9af9b4fdd002e4d6f301a976e6e3bb4d479a'},
 'pre': {'Lemma.Drivers.Paper.uploadOffsetAt': '5addf926b29014ce5b5ef98f46f86f7114b9cf3d6ff7bb093f79eef0cdadbd00',
         'Lemma.Drivers.Paper.uploadWordBlockAt': '7842023e67f146913fa47a70b8035a988ec772f661e716d4e3b42a7fa1f51d85',
         'Lemma.Drivers.Paper.uploadWordTailAt': 'e76d96d9e2d4e2d308f35e9531c1769b3b767fe5f172d5d4cdf5ba7d4eaebbf5',
         'Lemma.Drivers.Paper.uploadWordsAt': '804604573028b762379330f4533416f45ddd5c7644bb479f7620dcd32bdc01a0',
         'Lemma.Kernel.Capability.headerAt': '0a7841873e00edb3bfed0e46c0dfc465b65496b027dd2f7f1b88c2723fd0f6a5',
         'Lemma.Kernel.Capability.lookupAt': 'cf5f153df85552b92585d247e704c15542663c2118fd23ca0f2cedf37c7bc7ad',
         'Lemma.Kernel.Capability.lookupEntryAt': 'c483fd9495a93da2b60e10c47be6c23f120c9b917f92631231d46bb98d6d0f90',
         'Lemma.Kernel.Capability.requireActiveAt': '662bcf603c8328d4dbe6e04c984efce784cff87077b5ebd896d1505fa0e8cf40',
         'Lemma.Kernel.Loader.validateExpandedStackAt': '576b4bbeb29f9b4e780f31c41cfd1f6f5271c4c71dbdf841128a5ebfcd872647',
         'Lemma.Kernel.Memory.AddressSpace.base': '4036fb8f591d05541c064b11aa8d2da086d7e6cdea80ed674091303339537f73',
         'Lemma.Kernel.Memory.AddressSpace.lookupAt': '9ebe4b8edb954a7a0dd87a8c66b7b7d870ab868431acc4b7e75a818d6f8d8e75',
         'Lemma.Kernel.Memory.Frames.resolvePurpose': '99dc881018d7a6e94ee4fc7f76f9d4102edca366dd3ab7d29a1e88f2c81cbb3a',
         'Lemma.Kernel.Memory.UserCopy.checkedBorrowedBase': '3878f3c84cb3f05130a7f59dfc4a215af4bbcce98c9bd75a2cf2af206b2ff9b5',
         'Lemma.Kernel.Memory.UserCopy.checkedLookupAt': '812c4149e4c72b0a537f61e875e1ca2beb69fabefd9e2c4510bbb9b4ff31cd0f',
         'Lemma.Kernel.Memory.UserCopy.copyFromUserAt': '881701222823f7bab7856fe5dbc39c9d0a8768eb374f7e499d698fc2a8bdd0c9',
         'Lemma.Kernel.Memory.UserCopy.scratch': 'ae43b5d7ed8ffe6e96966c095abf7ec886a956f612b17eb52d4e9c0220ccad59',
         'Lemma.Kernel.Process.validateFrame': '51bbba57b5c3b9c8afa3338052747759db718466220779f3496cc96c1b20e273',
         'Lemma.Kernel.Process.validateStackAt': '1239a29f98a78b96d30c1a60d852e7f839a2f59c9da32a61edd02404fdf50afa',
         'Lemma.Kernel.Task.capture': '5fc2e25706054e64ee0abe9066e14ae60527b360058c7896f58e576de3fd2c51',
         'Lemma.Kernel.Task.contextAt': 'c8d649cbe854346fe0797e4a7ae0a6a6e09b128552ff0c0a02b61d981ee679a8',
         'Lemma.Kernel.Task.copyStep': 'd7b0756dbdbaebdda97ac706adf2dfc938b4cdd06d341fa7dbc2b33735e35147',
         'Lemma.Platform.LemmaSim.DeviceService.authorizeAt': '583a854590f1f019c14bb363260bfc09a4ba430a7344b3e738081c5550b4d12b',
         'Lemma.Platform.LemmaSim.DeviceService.bulkUploadStepAt': '581d4031d2ad0094e588b4c8d8982acacf9fa08a89ab6896e13bb49cfbd03ce1',
         'Lemma.Platform.LemmaSim.DeviceService.bulkValidateStep': '75d9fb2fdc1b137eeb0f5ad628327357edd070089eab48cc96e7a45b8764b520',
         'Lemma.Platform.LemmaSim.DeviceService.surfaceV2At': 'fe8ff0bf05dc7d11bcdacf217d838d52d040c5d623030019a71b00ea61d1d217',
         'Lemma.Platform.LemmaSim.DeviceService.uploadBulkAt': '835c3cfd8db52a9a12381f4d4e4daba36cd0068079bc8de300724134abcc2767',
         'Lemma.Platform.LemmaSim.NotebookKernel.deviceCallBulkAt': '2174093c88627d73275dd268522624741bef1af19fb984a8db9d624eb6b57728',
         'Lemma.Platform.LemmaSim.NotebookKernel.dispatchBulk': '17a927c358d9c5d4c16a58553c1da918d537c5ffac17d3198703c356d63d0a19'}}
