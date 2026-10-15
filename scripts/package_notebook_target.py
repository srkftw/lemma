"""Closed admission for the installed package/Doc8 Notebook User2 root.

This observer never interprets a document or creates guest evidence. Complete
source-owned pre/post bodies and caller sets are pinned from genuine selected
production exports; ordinary artifact/ISA/relocation/device audits still apply.
The separately qualified component is not a production artifact authority.
"""
from __future__ import annotations
import hashlib
import re
from core0_common import Core0Error

CONFIGURATIONS = frozenset({
    'lemmasim-silicon-package-closure-entry2-bulk-notebook',
    'lemmasim-silicon-package-closure-entry2-bulk-initialize',
})
SOFTWARE_DEPLOYMENT = {
    'contract_version': 'lemma-package-closure-entry2-bulk-deployment-v1',
    'silicon_profile': 'lemma-silicon-dev/0.3.0',
    'user_profiles': {'store': 'core0-user-v0.1', 'notebook': 'core0-user-v0.2',
                      'arithmetic': 'core0-user-v0.7', 'course': 'core0-user-v0.1'},
}
ROOT = 'Lemma.Applications.Notebook.mainPackageClosureBulk'
VERSION = 'lemma-installed-package-notebook/2'
LEGACY_VERSION = 'lemma-installed-package-notebook/1'
PRIVATE_LAYOUT = {
    'package_bytes': (0x332000, 32768), 'glyph_cache': (0x33a000, 4096),
    'workspace': (0x33b000, 3712), 'context': (0x33c000, 4096),
    'document_staging': (0x33d000, 2496),
    'record_context_offset': 128, 'incoming_offset': 256, 'outgoing_offset': 512,
    'binding_offset': 1024, 'submission_offset': 1152, 'state_offset': 2048,
    'owned_pages': 12, 'allocation_count_state_offset': 752,
    'workspace_version': 1, 'document_version': 8, 'protocol_version': 7,
    'text_panel': [24, 320, 384, 320], 'controls_panel': [24, 640, 384, 120],
    'header_panel_extension': 1, 'header_roles': [8, 9, 10, 11],
    'header_fields': [96, 104, 112, 120], 'minimum_height': 760,
    'workflow_ticks': 300000000, 'body_requests': 256, 'eof_requests': 1,
}

def require(value, message):
    if not value:
        raise Core0Error(message)

def canonical(source):
    return re.sub(r'^_private\..*?\.[0-9]+\.', '', source)

def selected(unit):
    return (unit.get('configuration') in CONFIGURATIONS and
            unit.get('role') == 'user' and unit.get('image_key') == 'notebook')

def _rows(unit):
    entries = unit.get('functions', [])
    require(isinstance(entries, list) and entries, 'Package Notebook source catalog absent')
    require(all(isinstance(row, dict) and isinstance(row.get('source'), str) and
                isinstance(row.get('symbol'), str) for row in entries),
            'Package Notebook source catalog malformed')
    rows = {canonical(row['source']): row for row in entries}
    require(len(rows) == len(entries), 'Package Notebook duplicate canonical owners')
    require(len({row['symbol'] for row in entries}) == len(entries),
            'Package Notebook duplicate LLVM symbols')
    return rows

def contract(unit):
    rows = _rows(unit)
    has_family = any(source in OWNED_NOTEBOOK for source in rows)
    if not has_family and not selected(unit):
        return None
    require(selected(unit), 'Package Notebook private authority escaped its selected deployment')
    require(unit.get('schema_version') == 2 and type(unit.get('schema_version')) is int and
            unit.get('artifact_category') == 'development-user-unit' and
            unit.get('contract_version') == 'core0-user-v0.2' and
            unit.get('image_id') == 2 and type(unit.get('image_id')) is int and
            unit.get('boot_role') == 'notebook' and
            unit.get('used_device_ops') == [] and
            unit.get('software_deployment') == SOFTWARE_DEPLOYMENT,
            'Package Notebook role/profile/device/software authority differs')
    operations = unit.get('used_execution_ops', [])
    require(isinstance(operations, list) and len(operations) == 5 and
            {row.get('stable_id') for row in operations} == {
                'execution.virtual-read8', 'execution.virtual-read64',
                'execution.virtual-write8', 'execution.virtual-write64', 'execution.syscall'} and
            {row.get('primitive_symbol') for row in operations} == {None, 'lemma_exec_syscall'},
            'Package Notebook acquired an undeclared execution boundary')
    roots = [{key: row.get(key) for key in ('source', 'id', 'args')}
             for row in unit.get('roots', [])]
    require(roots == [{'source': ROOT, 'id': 1, 'args': ['u64']}],
            'Package Notebook exact entry root/ABI differs')
    require(set(signature_set(unit)) <= set(rows), 'Package Notebook complete owned source family missing')
    corrected = COUNTER_ADDRESS_SOURCE in rows
    delta = delta_selected(unit)
    sparse = sparse_selected(unit)
    workspace = workspace_selected(unit)
    return {'contract_version': WORKSPACE_VERSION if workspace else SPARSE_VERSION if sparse else DELTA_VERSION if delta else VERSION if corrected else LEGACY_VERSION, 'root': ROOT,
            'private_layout': WORKSPACE_LAYOUT if workspace else SPARSE_LAYOUT if sparse else DELTA_LAYOUT if delta else PRIVATE_LAYOUT if corrected else {**PRIVATE_LAYOUT, 'allocation_count_state_offset': 768},
            'owned_functions': len(signature_set(unit))}

def _bodies(ir):
    matches = re.findall(r'(?ms)^define [^\n]*@([^ (]+)\([^\n]*\)[^\n]*\{\n(.*?)^\}', ir)
    require(matches and len(dict(matches)) == len(matches),
            'Package Notebook LLVM definitions absent/duplicated')
    return dict(matches)

def normalized_body(body, names):
    # Rebind only exact one-to-one source owners, including inlined exit labels.
    # Preserve every instruction, operand, label, edge and literal constant.
    body = re.sub(r'@([^ (]+)', lambda match: '@' + names.get(match[1], match[1]), body)
    body = re.sub(r'(?<![-A-Za-z0-9_.$])([-A-Za-z0-9_.$]+)(?=\.exit(?:[0-9.:,\]\s]|$))',
                  lambda match: names.get(match[1], match[1]), body)
    return ' '.join(' '.join(line.split(';', 1)[0] for line in body.splitlines()).split())

def _validate_bodies(ir, unit, *, optimized, pins, callers, layout=None, version=None, signatures=None):
    signatures = SIGNATURES if signatures is None else signatures
    rows = _rows(unit)
    names = {row['symbol']: source for source, row in rows.items()}
    bodies = _bodies(ir)
    expected = set(names)
    if optimized and 'surface_word_inline' in unit:
        from surface_word_inline import validate as validate_surface_words, removed_symbols
        require(validate_surface_words(ir, unit, optimized=True) is not None,
                'Package Notebook lost exact Surface-word source/IR authority')
        removed = removed_symbols(unit)
        require(len(removed) == 2 and removed <= expected and
                not any(names[symbol] in SIGNATURES for symbol in removed),
                'Package Notebook Surface-word removal escaped its exact two unowned library callbacks')
        expected -= removed
    require(set(bodies) == expected, 'Package Notebook LLVM/catalog owner inventory differs')
    references = {name: set(re.findall(r'@([^ (]+)\(', body)) for name, body in bodies.items()}
    observed = {}
    phase = 'post' if optimized else 'pre'
    require(set(pins[phase]) == set(signatures) == set(callers[phase]),
            'Package Notebook version authority incomplete')
    for source, (args, effects) in signatures.items():
        require(source in rows, 'Package Notebook owned declaration missing: ' + source)
        row = rows[source]
        require(row.get('args') == args and row.get('effects') == effects,
                'Package Notebook actual signature/effects differ: ' + source)
        body = bodies[row['symbol']]
        digest = hashlib.sha256(normalized_body(body, names).encode()).hexdigest()
        require(digest == pins[phase][source],
                'Package Notebook complete checked body differs: ' + source + '/' + phase)
        incoming = sorted(names[owner] for owner, refs in references.items()
                          if row['symbol'] in refs)
        require(incoming == callers[phase][source],
                'Package Notebook private caller closure differs: ' + source + '/' + phase)
        observed[source] = digest
    return {'phase': phase, 'owned_functions': len(observed), 'complete_bodies': observed,
            'exact_callers': callers[phase], 'layout': layout if layout is not None else PRIVATE_LAYOUT,
            'contract_version': version if version is not None else VERSION}

def validate(ir, unit, *, optimized):
    if contract(unit) is None:
        return None
    require(PRODUCTION_PINS is not None and PRODUCTION_CALLERS is not None,
            'Package Notebook production authority not yet independently qualified')
    corrected = COUNTER_ADDRESS_SOURCE in _rows(unit)
    pins = {key: {**values, **COUNTER_LAYOUT_V2_PINS[key]} for key, values in PRODUCTION_PINS.items()} if corrected else PRODUCTION_PINS
    layout = PRIVATE_LAYOUT if corrected else {**PRIVATE_LAYOUT, 'allocation_count_state_offset': 768}
    callers = {key: {**values, **COUNTER_LAYOUT_V2_CALLER_ADDITIONS[key]} for key, values in PRODUCTION_CALLERS.items()} if corrected else PRODUCTION_CALLERS
    version = VERSION if corrected else LEGACY_VERSION
    if delta_selected(unit):
        pins = {phase: {**{name: value for name, value in values.items() if name not in DELTA_REMOVED},
                        **DELTA_PINS[phase]} for phase, values in pins.items()}
        callers = {phase: {**{name: value for name, value in values.items() if name not in DELTA_REMOVED},
                           **DELTA_CALLERS[phase]} for phase, values in callers.items()}
        layout, version = DELTA_LAYOUT, DELTA_VERSION
    if sparse_selected(unit):
        pins = {phase: {**values, **SPARSE_PINS[phase]} for phase, values in pins.items()}
        callers = {phase: {**values, **SPARSE_CALLERS[phase]} for phase, values in callers.items()}
        layout, version = SPARSE_LAYOUT, SPARSE_VERSION
    if workspace_selected(unit):
        pins = {phase: {**values, **WORKSPACE_PINS[phase]} for phase, values in pins.items()}
        callers = {phase: {**values, **WORKSPACE_CALLERS[phase]} for phase, values in callers.items()}
        layout, version = WORKSPACE_LAYOUT, WORKSPACE_VERSION
    return _validate_bodies(ir, unit, optimized=optimized, pins=pins,
                           callers=callers, layout=layout, version=version,
                           signatures=signature_set(unit))



READONLY_SCHEMA = 'installed-package-notebook-v1'
CONTROL_SOURCE = 'Lemma.Applications.Notebook.packageControlCharacter'
CAPTURE_SOURCE = 'Lemma.Courses.PackageBinding.captureField'
# Original Lean packed labels and field offsets, independently specified here.
# None of these display/offset bytes grants checking or ownership authority.
CONTROL_WORDS = (
    (0x2020202b45444f4e, 0x2020202b454c4f52, 0x2020202b45474150),
    (0x20202b544e454449, 0x2020202b54494445, 0x2020202044414f4c),
    (0x2020454352554f53, 0x204e4f4954494445, 0x2020535448474952),
    (0x3030304920514552, 0x3030303030452030, 0x2030304e20303030),
    (0x3030492044414552, 0x3030303045203030, 0x2020202030303030),
)
CAPTURE_OFFSETS = (24, 32, 80, 0, 64, 8, 16, 24, 32, 40)


def _readonly_cfg(body):
    from audit_core0 import _structured_ir_blocks, _structured_successors
    blocks = _structured_ir_blocks('\n'.join(line.split(';', 1)[0].rstrip()
                                             for line in body.splitlines()))
    successors = _structured_successors(blocks)
    # The inherited helper handles branches. Include every admitted scalar
    # switch edge before reachability; omitted edges cannot prove dominance.
    for block, lines in blocks.items():
        starts = [i for i, line in enumerate(lines) if line.startswith('switch ')]
        if not starts:
            continue
        require(len(starts) == 1 and lines[-1] == ']', 'Package readonly switch form differs')
        start = starts[0]
        head = re.fullmatch(r'switch i64 %[-A-Za-z0-9_.$]+, label %([-A-Za-z0-9_.$]+) \[', lines[start])
        cases = [re.fullmatch(r'i64 (-?\d+), label %([-A-Za-z0-9_.$]+)', line)
                 for line in lines[start + 1:-1]]
        require(head is not None and cases and all(cases) and
                len({case[1] for case in cases}) == len(cases), 'Package readonly switch cases differ')
        targets = (head[1], *(case[2] for case in cases))
        require(all(target in blocks for target in targets), 'Package readonly switch target absent')
        successors[block] = targets
    return blocks, successors


def _readonly_load(body, blocks, pointer, *, count, operand, table_pointer):
    gep = re.findall(r'(%[-A-Za-z0-9_.$]+) = getelementptr inbounds nuw \[' + str(count) +
                     r' x i64\], ptr ' + re.escape(table_pointer) + r', i64 0, i64 ' +
                     re.escape(operand) + r'$', body, re.M)
    require(gep == [pointer], 'Package readonly typed/indexed pointer differs')
    loads = re.findall(r'(%[-A-Za-z0-9_.$]+) = load i64, ptr ' + re.escape(pointer) +
                       r', align 8$', body, re.M)
    require(len(loads) == 1 and len(re.findall(re.escape(pointer) + r'(?![-A-Za-z0-9_.$])', body)) == 2,
            'Package readonly pointer escapes its unique aligned load')
    located = [block for block, lines in blocks.items()
               if any(line.startswith(loads[0] + ' = load ') for line in lines)]
    require(len(located) == 1, 'Package readonly load block ambiguous')
    return loads[0], located[0]


def _readonly_lookup_verified(ir, unit):
    """Structural supplement; caller must first close all189 bodies/callers.

    Kept separate for independent actual-IR mutation tests, which verify the
    table/CFG checks themselves rather than merely failing a complete-body pin.
    Public admission always invokes validate before this function.
    """
    from audit_core0 import _structured_reachable
    from audit_device import _line_functions
    rows = _rows(unit); bodies = _bodies(ir); lines = ir.splitlines()
    owners = _line_functions(lines); sites = set(); tables = []; removed = set()

    def global_row(source, table, values, load, guard, selection):
        expected = '@' + table + ' = private unnamed_addr constant [' + str(len(values)) + ' x i64] [' + \
            ', '.join('i64 ' + str(value) for value in values) + '], align 8'
        require(sum(line.strip() == expected for line in lines) == 1 and
                len(re.findall('@' + re.escape(table) + r'(?![-A-Za-z0-9_.$])', ir)) == 2,
                'Package readonly exact global/content/use inventory differs: ' + table)
        symbol = rows[source]['symbol']
        located = {i for i, line in enumerate(lines)
                   if owners[i] == symbol and line.strip().startswith(load + ' = load ')}
        require(len(located) == 1, 'Package readonly physical load site differs')
        sites.update(located); removed.add(expected)
        tables.append({'source': rows[source]['source'], 'function': symbol, 'global': table,
                       'values': list(values), 'element_bits': 64, 'alignment_bytes': 8,
                       'index_bound': len(values), 'guarded_loads': 1, 'readonly': True,
                       'guard': guard, 'literal_schema': READONLY_SCHEMA, 'selection': selection})

    source = CONTROL_SOURCE; symbol = rows[source]['symbol']; body = bodies[symbol]
    blocks, successors = _readonly_cfg(body)
    require(len(re.findall(r'%udiv11 = lshr i64 %arg1, 3$', body, re.M)) == 1 and
            len(re.findall(r'%0 = icmp ult i64 %arg1, 24$', body, re.M)) == 1,
            'Package label index lacks its exact unsigned24/shift3 bound')
    branch = re.search(r'switch i64 %arg0, label %(\S+) \[\s*'
                       r'i64 0, label %(\S+)\s*i64 1, label %(\S+)\s*'
                       r'i64 2, label %(\S+)\s*i64 3, label %(\S+)\s*\]', body)
    require(branch is not None, 'Package label table lacks exact row selection')
    selected_blocks = [branch[i] for i in (2, 3, 4, 5, 1)]
    require(len(set(selected_blocks)) == 5, 'Package label row branches alias')
    base = 'switch.table.' + symbol
    names = [base, base + '.4', base + '.5', base + '.6', base + '.7']
    phi = '%' + base + '.5.sink'; joined = 'if.else.109.sink.split'
    expected_phi = phi + ' = phi ptr ' + ', '.join('[ @' + name + ', %' + block + ' ]'
                                                 for name, block in zip(names[:3], selected_blocks[:3]))
    require(sum(line == expected_phi for line in blocks.get(joined, [])) == 1 and
            len(re.findall(re.escape(phi) + r'(?![-A-Za-z0-9_.$])', body)) == 2,
            'Package label joined pointer selection/uses differ')
    group_load, group_block = _readonly_load(body, blocks, '%switch.gep15', count=3,
                                            operand='%udiv11', table_pointer=phi)
    load_specs = [(group_load, group_block)] * 3
    for ordinal, pointer in ((3, '%switch.gep18'), (4, '%switch.gep21')):
        load_specs.append(_readonly_load(body, blocks, pointer, count=3, operand='%udiv11',
                                        table_pointer='@' + names[ordinal]))
    require(len(re.findall(r' = load i64, ptr ', body)) == 3 and
            len(re.findall(r' = getelementptr ', body)) == 3,
            'Package label lookup acquired an additional pointer/load')
    without = dict(successors)
    for ordinal, block in enumerate(selected_blocks):
        load, load_block = load_specs[ordinal]
        require(block in successors and len(successors[block]) == 2,
                'Package label row has no recognized two-edge bound branch')
        expected_branch = 'br i1 %0, label %' + load_block + ', label %' + successors[block][1]
        require(blocks[block] == [expected_branch] and
                _structured_reachable(successors, 'entry', block) and
                _structured_reachable(successors, successors[block][0], load_block) and
                not _structured_reachable(successors, successors[block][1], load_block),
                'Package label row lacks its exact guarded lookup edge')
        without[block] = (successors[block][1],)
        for other, other_block in enumerate(selected_blocks):
            if other != ordinal and (ordinal >= 3 or other >= 3):
                require(not _structured_reachable(successors, other_block, load_block),
                        'Package label table reachable from another source row')
        global_row(source, names[ordinal], CONTROL_WORDS[ordinal], load, block,
                   {'row': ordinal, 'row_argument': 0, 'column_argument': 1,
                    'unsigned_column_bound': 24, 'index_shift': 3,
                    'joined_rows': [0, 1, 2] if ordinal < 3 else []})
    require(all(not _structured_reachable(without, 'entry', block) for _, block in load_specs),
            'Package label lookup has an unguarded CFG route')

    source = CAPTURE_SOURCE; symbol = rows[source]['symbol']; body = bodies[symbol]
    blocks, successors = _readonly_cfg(body); base = 'switch.table.' + symbol
    require(len(re.findall(r'%0 = icmp ult i32 %arg0, 10$', body, re.M)) == 1 and
            len(re.findall(r'%1 = zext nneg i32 %arg0 to i64$', body, re.M)) == 1,
            'Package capture field lookup lacks its exact unsigned10/index conversion')
    load, block = _readonly_load(body, blocks, '%switch.gep', count=10, operand='%1',
                                table_pointer='@' + base)
    require(blocks['entry'][-1] == 'br i1 %0, label %' + block + ', label %if.else.34' and
            len(re.findall(r' = load i64, ptr ', body)) == 1 and
            len(re.findall(r' = getelementptr ', body)) == 1,
            'Package capture field lacks exact sole bounded lookup')
    without = dict(successors); without['entry'] = ('if.else.34',)
    require(_structured_reachable(successors, 'entry', block) and
            not _structured_reachable(without, 'entry', block),
            'Package capture field lookup has an unguarded CFG route')
    global_row(source, base, CAPTURE_OFFSETS, load, 'entry',
               {'index_argument': 0, 'unsigned_bound': 10, 'package_indices': [0, 1, 2],
                'entry_indices': list(range(3, 10))})
    require(len(sites) == 4 and len(tables) == 6 and len(removed) == 6,
            'Package readonly complete physical/table inventory differs')
    return sites, tables, removed


def readonly_lookup(ir, unit):
    """Exact selected optimized Package User2 readonly supplement only."""
    if contract(unit) is None:
        return set(), [], set()
    validate(ir, unit, optimized=True)
    return _readonly_lookup_verified(ir, unit)


NOTEBOOK_JUMPS = {
    'Lemma.Courses.PackageRender.glyph': (64, [32, 33, 34, 39, 44, 46, 58, 59, 60, 62, 63, 74, 90, 95]),
    'Lemma.Applications.Notebook.packageConfigureStep': (8, list(range(8))),
    'Lemma.Courses.PackageReader.step': (6, list(range(6))),
}
GLYPH_RETURNS = {32: 0, 74: 0x124e, 90: 0x72a7, 46: 2, 44: 20, 58: 0x410,
                 59: 0x414, 39: 0x2400, 34: 0x5a00, 33: 0x2482, 63: 0x7282,
                 95: 7, 60: 0x1541, 62: 0x4454}
JUMP_MACHINE_PINS = {
    'Lemma.Courses.PackageRender.glyph': 'a49da89f4de67e5e31ab6f3be4b8a0ebdfdb3b922689dd1b98d1a27c86240287',
    'Lemma.Applications.Notebook.packageConfigureStep': '37ee0c74fa7af4807e8197ec27abdfb5da349531bc800a624aaef0ee35e788f0',
    'Lemma.Courses.PackageReader.step': '9cd9968e4ebe7e974a335e10b4381172514def67d8957b8a2aecd73b6185bdce',
}


def notebook_jump_spec(ir, unit, source, symbol):
    if source not in NOTEBOOK_JUMPS:
        return None
    require(validate(ir, unit, optimized=True) is not None,
            'Package backend table escaped the exact selected189-body authority')
    row = _rows(unit).get(source)
    require(row is not None and row['symbol'] == symbol,
            'Package backend table does not have its exact source symbol')
    count, cases = NOTEBOOK_JUMPS[source]
    body = _bodies(ir)[symbol]
    domains = [sorted(int(value) for value in re.findall(r'i\d+ (-?\d+), label', block))
               for block in re.findall(r'switch i\d+ [^\n]+\[([^]]+)\]', body, re.S)]
    require(domains == [cases], 'Package backend exact source switch domain differs')
    args, effects = SIGNATURES[source]
    require(row['args'] == args and row['effects'] == effects,
            'Package backend source signature/effects differ')
    return ('user', count, args, effects, cases)


def _normalized_jump_code(code, labels, table, names):
    normalized = []
    for operation, arguments in code:
        words = []
        for argument in arguments:
            if argument in labels:
                words.append('@' + str(labels[argument]))
            elif argument == '%pcrel_hi(' + table + ')':
                words.append('%TABLE')
            elif re.fullmatch(r'%pcrel_lo\(\.Lpcrel_hi\d+\)', argument):
                low = argument[len('%pcrel_lo('):-1]
                require(low in labels, 'Package backend low relocation label absent')
                words.append('%LOW' + str(labels[low]))
            elif argument in names:
                words.append('@' + names[argument])
            else:
                words.append(argument)
        normalized.append((operation, words))
    return normalized


def _constant_glyph_return(code, start):
    # Audit only the closed constant-construction instruction shapes emitted
    # by pinned LLVM. This is not a guest interpreter or a target runtime.
    value = 0  # the exact dispatch preloads a0=0 for the blank glyph.
    for operation, arguments in code[start:start + 4]:
        if operation == 'ret' and arguments == []:
            return value
        if operation == 'li' and arguments[0] == 'a0' and len(arguments) == 2:
            value = int(arguments[1])
        elif operation == 'lui' and arguments[0] == 'a0' and len(arguments) == 2:
            value = int(arguments[1]) << 12
        elif operation == 'addiw' and arguments[:2] == ['a0', 'a0'] and len(arguments) == 3:
            value = (value + int(arguments[2])) & 0xffffffff
            if value & 0x80000000:
                value -= 1 << 32
        elif operation == 'slli' and arguments[:2] == ['a0', 'a0'] and len(arguments) == 3:
            value <<= int(arguments[2])
        else:
            raise Core0Error('Package glyph cell does not reach an admitted constant return')
    raise Core0Error('Package glyph constant cell lacks its bounded return')


def validate_jump_relation(ir, unit, assembly, symbol, table, targets, code, labels):
    """Close all64/8/6 actual machine cells against their exact source roles.

    The ordinary caller also checks object/companion bytes, every relocation,
    local owner extent and unsigned dispatch path. No other table is admitted.
    """
    rows = _rows(unit); names = {row['symbol']: source for source, row in rows.items()}
    source = names.get(symbol)
    spec = notebook_jump_spec(ir, unit, source, symbol)
    if spec is None:
        return None
    from audit_kernel import _jump_assembly_function
    actual_code, actual_labels = _jump_assembly_function(assembly, symbol)
    require(code == actual_code and labels == actual_labels,
            'Package backend relation was supplied foreign machine instructions/labels')
    declarations = re.findall(r'(?m)^' + re.escape(table) + r':\n((?:\s*\.quad\s+\.LBB\d+_\d+\s*\n)+)', assembly)
    require(len(declarations) == 1 and
            re.findall(r'\.quad\s+(\.LBB\d+_\d+)', declarations[0]) == targets,
            'Package backend relation differs from the actual declared table cells')
    count, cases = NOTEBOOK_JUMPS[source]
    require(len(targets) == count and all(target in labels for target in targets),
            'Package backend table cell count/local target differs')
    normalized = _normalized_jump_code(code, labels, table, names)
    digest = hashlib.sha256(repr(normalized).encode()).hexdigest()
    require(digest == JUMP_MACHINE_PINS[source],
            'Package complete actual machine owner/guard/calls differ: ' + source)
    body = _bodies(ir)[symbol]
    if source.endswith('.glyph'):
        switch = re.search(r'switch i64 %if.result4, label %([^ ]+) \[([^]]+)\]', body, re.S)
        require(switch is not None, 'Package glyph exact source selector absent')
        source_targets = {int(value): block for value, block in
                          re.findall(r'i64 (-?\d+), label %([^\s]+)', switch[2])}
        require(set(source_targets) == set(GLYPH_RETURNS), 'Package glyph source case inventory differs')
        # Source-selected constants are checked independently of the whole
        # body pin; 32 reaches the phi directly from entry.
        for character, value in GLYPH_RETURNS.items():
            incoming = 'entry' if character == 32 else source_targets[character]
            require(len(re.findall(r'\[ ' + str(value) + ', %' + re.escape(incoming) + r' \]', body)) == 1,
                    'Package glyph source return constant differs')
        cells = []
        for index, target in enumerate(targets):
            character = index + 32; at = labels[target]
            if character in GLYPH_RETURNS:
                require(_constant_glyph_return(code, at) == GLYPH_RETURNS[character],
                        'Package glyph actual cell returns another source constant')
                cells.append({'character': character, 'value': GLYPH_RETURNS[character], 'target': at})
            else:
                require(at == 49, 'Package glyph hole does not reach the exact Surface-letter/missing-box fallback')
                cells.append({'character': character, 'fallback': True, 'target': at})
        require(code[13] == ('li', ['a0', '0']) and
                normalized[49:] == [('addi', ['sp', 'sp', '-16']), ('sd', ['ra', '8(sp)']),
                    ('mv', ['a0', 'a1']), ('call', ['@Lemma.Ink.Surface.letter']),
                    ('ld', ['ra', '8(sp)']), ('addi', ['sp', 'sp', '16']),
                    ('bnez', ['a0', '@32']), ('lui', ['a0', '8']),
                    ('addiw', ['a0', 'a0', '-1169']), ('ret', [])],
                'Package glyph actual default/blank/missing-box semantics differ')
        return {'schema': 'lemma-package-backend-cells/1', 'source': source,
                'all_cells': cells, 'holes': [i for i in range(32, 96) if i not in GLYPH_RETURNS],
                'lowercase_ascii': [97, 122], 'lowercase_shift': -32,
                'fallback': {'source': 'Lemma.Ink.Surface.letter', 'missing_box': 31599},
                'machine_sha256': digest}
    if source.endswith('.packageConfigureStep'):
        expected = [30, 9, 15, 18, 12, 22, 24, 20]
        require([labels[target] for target in targets] == expected,
                'Package configure actual cell/source-field mapping differs')
        source_values = [('%arg3', 'entry'), ('3392000', 'if.then.3'), ('3391744', 'if.then.6'),
                         ('%arg4', 'if.merge.5'), ('%bin11', 'if.then.12'),
                         ('%lshr14', 'if.then.15'), ('3350528', 'if.then.18'), ('32768', 'if.merge.14')]
        require(all(len(re.findall(r'\[ ' + re.escape(value) + ', %' + re.escape(block) + r' \]', body)) == 1
                    for value, block in source_values) and
                '%bin11 = and i64 %arg5, 65535' in body and '%lshr14 = lshr i64 %arg5, 16' in body,
                'Package configure source-field/identity slicing differs')
        require('[ %arg6, %execution.mem.0.lookup.1.i ]' in body,
                'Package configure ninth request-ID field/default differs')
        return {'schema': 'lemma-package-backend-cells/1', 'source': source,
                'all_targets': expected, 'fields': ['Store endpoint', 'owned outgoing+512',
                    'owned incoming+256', 'Store namespace', 'identity low16', 'edition after shift16',
                    'private package buffer', 'package resource32768'],
                'ninth_default_field': 'first request ID; checked write preserved', 'machine_sha256': digest}
    require([labels[target] for target in targets] == [34, 31, 27, 27, 37, 11],
            'Package reader actual state/call mapping differs')
    field = rows['Lemma.Courses.PackageReader.field']['symbol']
    for state, source_target, callee, arguments in (
            (0, 'action.if.then.6', rows['Lemma.Courses.PackageReader.beginPiece']['symbol'], 'i64 %arg0'),
            (1, 'action.if.then.9', rows['Lemma.Courses.PackageReader.pollPiece']['symbol'], 'i64 %arg0'),
            (2, 'action.if.then.12', field, 'i64 %arg0, i64 96'),
            (3, 'action.if.then.15', field, 'i64 %arg0, i64 96'),
            (4, 'action.if.then.18', field, 'i64 %arg0, i64 120')):
        require('i64 ' + str(state) + ', label %' + source_target in body,
                'Package reader source state edge differs')
        block = _readonly_cfg(body)[0][source_target]
        require(sum(' @' + callee + '(' + arguments + ')' in line for line in block) == 1,
                'Package reader source state invokes another operation')
    require('i64 5, label %action.if.merge.2' in body and
            '[ 94, %action.if.then.3 ]' in body and '[ 240, %action.if.else.25 ]' in body,
            'Package reader complete/error source states differ')
    return {'schema': 'lemma-package-backend-cells/1', 'source': source,
            'all_targets': [34, 31, 27, 27, 37, 11],
            'states': ['begin real READ', 'poll real READ', 'return observed bytes',
                       'return observed bytes', 'return actual error', 'canceled94'],
            'other_state_error': 240, 'machine_sha256': digest}


# All constants below derive from the original actual selected production
# export; artifact-supplied digests never establish observer authority.
OWNED_NOTEBOOK = frozenset(['Lemma.Applications.Notebook.adoptPackageStep', 'Lemma.Applications.Notebook.adoptPackageWorkspace', 'Lemma.Applications.Notebook.allocatePackage', 'Lemma.Applications.Notebook.beginPackageArithmetic', 'Lemma.Applications.Notebook.beginPackageRead', 'Lemma.Applications.Notebook.beginPackageRecordPiece', 'Lemma.Applications.Notebook.cancelPackageRead', 'Lemma.Applications.Notebook.cancelPackageRecord', 'Lemma.Applications.Notebook.cancelPackageWork', 'Lemma.Applications.Notebook.drainPackageInput', 'Lemma.Applications.Notebook.drainPackageInput.drainStep', 'Lemma.Applications.Notebook.finishOpenPackageCourse', 'Lemma.Applications.Notebook.finishOpenPackageCourse.restoreSelection', 'Lemma.Applications.Notebook.mainPackageClosureBulk', 'Lemma.Applications.Notebook.openPackageCourse', 'Lemma.Applications.Notebook.packageAllocateStep', 'Lemma.Applications.Notebook.packageBindingScratch', 'Lemma.Applications.Notebook.packageBusy', 'Lemma.Applications.Notebook.packageBusy.done', 'Lemma.Applications.Notebook.packageBytes', 'Lemma.Applications.Notebook.packageCancelInput', 'Lemma.Applications.Notebook.packageCloseState', 'Lemma.Applications.Notebook.packageConfigureStep', 'Lemma.Applications.Notebook.packageContext', 'Lemma.Applications.Notebook.packageControlByte', 'Lemma.Applications.Notebook.packageControlCharacter', 'Lemma.Applications.Notebook.packageControlPress', 'Lemma.Applications.Notebook.packageControlStep', 'Lemma.Applications.Notebook.packageControlTile', 'Lemma.Applications.Notebook.packageCourseError', 'Lemma.Applications.Notebook.packageCoursePress', 'Lemma.Applications.Notebook.packageDocumentStage', 'Lemma.Applications.Notebook.packageGet', 'Lemma.Applications.Notebook.packageGlyphs', 'Lemma.Applications.Notebook.packageHex', 'Lemma.Applications.Notebook.packageIdentityCharacter', 'Lemma.Applications.Notebook.packageIdentityStep', 'Lemma.Applications.Notebook.packageIncoming', 'Lemma.Applications.Notebook.packageInputSample', 'Lemma.Applications.Notebook.packageInputSample.acceptSample', 'Lemma.Applications.Notebook.packageInputSample.write', 'Lemma.Applications.Notebook.packageOutgoing', 'Lemma.Applications.Notebook.packagePut', 'Lemma.Applications.Notebook.packageReadComplete', 'Lemma.Applications.Notebook.packageReadEOF', 'Lemma.Applications.Notebook.packageReadFloor', 'Lemma.Applications.Notebook.packageRecord', 'Lemma.Applications.Notebook.packageState', 'Lemma.Applications.Notebook.packageStep', 'Lemma.Applications.Notebook.packageStep.drain', 'Lemma.Applications.Notebook.packageSubmitted', 'Lemma.Applications.Notebook.packageTileStep', 'Lemma.Applications.Notebook.packageToolbar', 'Lemma.Applications.Notebook.packageView', 'Lemma.Applications.Notebook.packageWorkspace', 'Lemma.Applications.Notebook.pollPackageRecordPiece', 'Lemma.Applications.Notebook.publishPackageWorkspace', 'Lemma.Applications.Notebook.pumpOpenPackageCourse', 'Lemma.Applications.Notebook.pumpPackageArithmetic', 'Lemma.Applications.Notebook.pumpPackageRead', 'Lemma.Applications.Notebook.pumpPackageRead.finish', 'Lemma.Applications.Notebook.pumpPackageRecord', 'Lemma.Applications.Notebook.pumpPackageWork', 'Lemma.Applications.Notebook.recordGet', 'Lemma.Applications.Notebook.recordPut', 'Lemma.Applications.Notebook.renderPackageControls', 'Lemma.Applications.Notebook.renderPackageIdentity', 'Lemma.Applications.Notebook.renderPackageText', 'Lemma.Applications.Notebook.savePackageWorkspace', 'Lemma.Applications.Notebook.stagePackageCompletion', 'Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Applications.Notebook.stagePackagePress', 'Lemma.Applications.Notebook.stagePackagePress.stage', 'Lemma.Applications.Notebook.startPackageRecord', 'Lemma.Applications.Notebook.stopPackageRecord', 'Lemma.Applications.Notebook.togglePackageCourse'])
SIGNATURES = {
    'Lemma.Applications.Notebook.adoptPackageStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Applications.Notebook.adoptPackageWorkspace': [[], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Applications.Notebook.allocatePackage': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.beginPackageArithmetic': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.beginPackageRead': [['u64', 'u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.beginPackageRecordPiece': [['u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.cancelPackageRead': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.cancelPackageRecord': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.cancelPackageWork': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.drainPackageInput': [['u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.drainPackageInput.drainStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.finishOpenPackageCourse': [['u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.finishOpenPackageCourse.restoreSelection': [[], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Applications.Notebook.mainPackageClosureBulk': [['u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition', 'may-diverge']],
    'Lemma.Applications.Notebook.openPackageCourse': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageAllocateStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageBindingScratch': [[], []],
    'Lemma.Applications.Notebook.packageBusy': [[], ['checked-access', 'virtual-read']],
    'Lemma.Applications.Notebook.packageBusy.done': [['u64', 'u64', 'u64', 'u64'], []],
    'Lemma.Applications.Notebook.packageBytes': [[], []],
    'Lemma.Applications.Notebook.packageCancelInput': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageCloseState': [[], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Applications.Notebook.packageConfigureStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-write']],
    'Lemma.Applications.Notebook.packageContext': [[], []],
    'Lemma.Applications.Notebook.packageControlByte': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-write']],
    'Lemma.Applications.Notebook.packageControlCharacter': [['u64', 'u64', 'u64', 'u64', 'u64'], []],
    'Lemma.Applications.Notebook.packageControlPress': [['u64', 'u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageControlStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-write']],
    'Lemma.Applications.Notebook.packageControlTile': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Applications.Notebook.packageCourseError': [['u8'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageCoursePress': [['u64', 'u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageDocumentStage': [[], []],
    'Lemma.Applications.Notebook.packageGet': [['u64'], ['checked-access', 'virtual-read']],
    'Lemma.Applications.Notebook.packageGlyphs': [[], []],
    'Lemma.Applications.Notebook.packageHex': [['u64', 'u64'], []],
    'Lemma.Applications.Notebook.packageIdentityCharacter': [['u64', 'u64', 'u64'], []],
    'Lemma.Applications.Notebook.packageIdentityStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-write']],
    'Lemma.Applications.Notebook.packageIncoming': [[], []],
    'Lemma.Applications.Notebook.packageInputSample': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageInputSample.acceptSample': [['u64', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageInputSample.write': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageOutgoing': [[], []],
    'Lemma.Applications.Notebook.packagePut': [['u64', 'u64'], ['checked-access', 'virtual-write']],
    'Lemma.Applications.Notebook.packageReadComplete': [[], ['checked-access', 'virtual-write']],
    'Lemma.Applications.Notebook.packageReadEOF': [['u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageReadFloor': [[], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Applications.Notebook.packageRecord': [[], []],
    'Lemma.Applications.Notebook.packageState': [[], []],
    'Lemma.Applications.Notebook.packageStep': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageStep.drain': [['u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageSubmitted': [[], []],
    'Lemma.Applications.Notebook.packageTileStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Applications.Notebook.packageToolbar': [['u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageView': [['u64', 'u64', 'u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.packageWorkspace': [[], []],
    'Lemma.Applications.Notebook.pollPackageRecordPiece': [['u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.publishPackageWorkspace': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.pumpOpenPackageCourse': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.pumpPackageArithmetic': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.pumpPackageRead': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.pumpPackageRead.finish': [['u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Applications.Notebook.pumpPackageRecord': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.pumpPackageWork': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.recordGet': [['u64'], ['checked-access', 'virtual-read']],
    'Lemma.Applications.Notebook.recordPut': [['u64', 'u64'], ['checked-access', 'virtual-write']],
    'Lemma.Applications.Notebook.renderPackageControls': [[], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Applications.Notebook.renderPackageIdentity': [['u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Applications.Notebook.renderPackageText': [[], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Applications.Notebook.savePackageWorkspace': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.stagePackageCompletion': [[], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Applications.Notebook.stagePackageExercise': [['u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Applications.Notebook.stagePackagePress': [['u64', 'u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.stagePackagePress.stage': [['u64', 'u64', 'u64', 'u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.startPackageRecord': [['u64', 'u64', 'u64', 'u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Applications.Notebook.stopPackageRecord': [['u8'], ['checked-access', 'virtual-write']],
    'Lemma.Applications.Notebook.togglePackageCourse': [[], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Courses.PackageBinding.applicable': [['u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageBinding.bytes': [[], []],
    'Lemma.Courses.PackageBinding.capture': [['u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageBinding.captureField': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageBinding.fieldsValid': [['u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageBinding.magic': [[], []],
    'Lemma.Courses.PackageBinding.put': [['u64', 'u64', 'u64'], ['checked-access', 'virtual-write']],
    'Lemma.Courses.PackageBinding.spanValid': [['u64'], []],
    'Lemma.Courses.PackageBinding.validate': [['u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageBinding.version': [[], []],
    'Lemma.Courses.PackageBinding.word': [['u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageFormat.crcBit': [['u64'], []],
    'Lemma.Courses.PackageFormat.crcByte': [['u64', 'u64'], []],
    'Lemma.Courses.PackageFormat.entryBytes': [[], []],
    'Lemma.Courses.PackageFormat.headerBytes': [[], []],
    'Lemma.Courses.PackageFormat.integrityFailure': [[], []],
    'Lemma.Courses.PackageFormat.magic': [[], []],
    'Lemma.Courses.PackageFormat.malformed': [[], []],
    'Lemma.Courses.PackageFormat.maximumBytes': [[], []],
    'Lemma.Courses.PackageFormat.maximumEdition': [[], []],
    'Lemma.Courses.PackageFormat.maximumEntries': [[], []],
    'Lemma.Courses.PackageFormat.maximumFieldBytes': [[], []],
    'Lemma.Courses.PackageFormat.maximumIdentity': [[], []],
    'Lemma.Courses.PackageFormat.maximumTextBytes': [[], []],
    'Lemma.Courses.PackageFormat.object': [['u64', 'u64'], []],
    'Lemma.Courses.PackageFormat.prerequisitesValid': [['u64', 'u64'], []],
    'Lemma.Courses.PackageFormat.referenceStatus': [['u64', 'u64', 'u64', 'u64', 'u64', 'u64'], []],
    'Lemma.Courses.PackageFormat.resourceLimit': [[], []],
    'Lemma.Courses.PackageFormat.selectionAbsent': [[], []],
    'Lemma.Courses.PackageFormat.spanLength': [['u64'], []],
    'Lemma.Courses.PackageFormat.spanOffset': [['u64'], []],
    'Lemma.Courses.PackageFormat.textByteValid': [['u64'], []],
    'Lemma.Courses.PackageFormat.unsupported': [[], []],
    'Lemma.Courses.PackageFormat.version': [[], []],
    'Lemma.Courses.PackageReader.accept': [['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageReader.beginPiece': [['u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Courses.PackageReader.cancel': [['u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Courses.PackageReader.clearStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-write']],
    'Lemma.Courses.PackageReader.configuration': [['u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageReader.contextBytes': [[], []],
    'Lemma.Courses.PackageReader.field': [['u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageReader.finish': [['u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageReader.issue': [['u64', 'u64', 'u64', 'u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Courses.PackageReader.maximumRequests': [[], []],
    'Lemma.Courses.PackageReader.minimum': [['u64', 'u64'], []],
    'Lemma.Courses.PackageReader.pollPiece': [['u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Courses.PackageReader.put': [['u64', 'u64', 'u64'], ['checked-access', 'virtual-write']],
    'Lemma.Courses.PackageReader.separate': [['u64', 'u64', 'u64', 'u64'], []],
    'Lemma.Courses.PackageReader.spans': [['u64', 'u64', 'u64', 'u64', 'u64'], []],
    'Lemma.Courses.PackageReader.start': [['u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageReader.step': [['u64'], ['checked-access', 'io-order', 'virtual-read', 'virtual-write', 'user-syscall', 'privilege-transition']],
    'Lemma.Courses.PackageReader.stop': [['u64', 'u64', 'u64'], ['checked-access', 'virtual-write']],
    'Lemma.Courses.PackageRender.cacheBytes': [[], []],
    'Lemma.Courses.PackageRender.clearStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-write']],
    'Lemma.Courses.PackageRender.columns': [[], []],
    'Lemma.Courses.PackageRender.glyph': [['u64'], []],
    'Lemma.Courses.PackageRender.pair': [['u64', 'u64', 'u64', 'u64'], []],
    'Lemma.Courses.PackageRender.panelWord': [['u64', 'u64', 'u64', 'u64'], []],
    'Lemma.Courses.PackageRender.pixel': [['u64', 'u64', 'u64', 'u64'], []],
    'Lemma.Courses.PackageRender.prepare': [['u64', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageRender.prepareHeader': [['u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageRender.render': [['u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageRender.renderByteStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-write']],
    'Lemma.Courses.PackageRender.renderHeaderSelected': [['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageRender.renderSelected': [['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageRender.renderStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageRender.rows': [[], []],
    'Lemma.Courses.PackageRender.separate': [['u64', 'u64', 'u64', 'u64'], []],
    'Lemma.Courses.PackageRender.textStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageTarget.crcStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageTarget.entryStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageTarget.entryTextStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageTarget.headerTextStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageTarget.reservedStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageTarget.select': [['u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageTarget.textStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageTarget.validate': [['u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageTarget.validateBody': [['u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageTarget.validateEntry': [['u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageTarget.validateSpan': [['u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageTarget.word': [['u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageWorkspace.attempts': [[], []],
    'Lemma.Courses.PackageWorkspace.bytes': [[], []],
    'Lemma.Courses.PackageWorkspace.captureSelection': [['u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageWorkspace.cloneContents': [['u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageWorkspace.copyBinding': [['u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageWorkspace.copyBindingStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageWorkspace.create': [['u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageWorkspace.equalEventsStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageWorkspace.equalHistoryStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageWorkspace.equalSubmissionStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageWorkspace.equalWordsStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageWorkspace.field': [['u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageWorkspace.inner': [[], []],
    'Lemma.Courses.PackageWorkspace.magic': [[], []],
    'Lemma.Courses.PackageWorkspace.object': [['u64'], []],
    'Lemma.Courses.PackageWorkspace.put': [['u64', 'u64', 'u64'], ['checked-access', 'virtual-write']],
    'Lemma.Courses.PackageWorkspace.selection': [[], []],
    'Lemma.Courses.PackageWorkspace.separate': [['u64', 'u64', 'u64', 'u64'], []],
    'Lemma.Courses.PackageWorkspace.shape': [['u64', 'u64', 'u64'], []],
    'Lemma.Courses.PackageWorkspace.snapshotSelection': [['u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageWorkspace.stageCompleted': [['u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageWorkspace.stageCompletedUnknown': [['u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageWorkspace.stageRefresh': [['u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageWorkspace.stageUnknownSelection': [['u64', 'u64', 'u64'], ['checked-access', 'virtual-read', 'virtual-write']],
    'Lemma.Courses.PackageWorkspace.transitionBase': [['u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageWorkspace.validate': [['u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageWorkspace.validateAttempt': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageWorkspace.validateOwned': [['u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageWorkspace.validateSelection': [['u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageWorkspace.version': [[], []],
    'Lemma.Courses.PackageWorkspace.zeroCheck': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-read']],
    'Lemma.Courses.PackageWorkspace.zeroStep': [['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'virtual-write']],
}
PRODUCTION_PINS = {
    'pre': {
        'Lemma.Applications.Notebook.adoptPackageStep': '7fdb0c40bd96aa65407d4dc1c781c0ac5b2a04f79be43f7dc9abce22f7c724e9',
        'Lemma.Applications.Notebook.adoptPackageWorkspace': '8d868c60fbc944658eb7db2c0b248bd7300843ce93484505cd41a8c19699b1d0',
        'Lemma.Applications.Notebook.allocatePackage': '24e7d7048e593e76e6c36c753b42479cef58d8f08153d88e6a1101702febaa57',
        'Lemma.Applications.Notebook.beginPackageArithmetic': '7331c66b7eed8450f50b0e4d37f1e2709153fb009c9f25adf1844c0cea3ee929',
        'Lemma.Applications.Notebook.beginPackageRead': '55d439360dbc7f180b01c72da0dc0803d4b51278380767d3c18b7b44b92f21a7',
        'Lemma.Applications.Notebook.beginPackageRecordPiece': 'f4f92ec80f0d4cf8dc91d5474de3ae24be031367de3330dcacb48f2f42ddcd2c',
        'Lemma.Applications.Notebook.cancelPackageRead': '31b84cc8e5b90845cc74eb9eb094ed6759d42e14651f590dffe0ea95e78e3af3',
        'Lemma.Applications.Notebook.cancelPackageRecord': 'd4c5df785ac1d7b70b1e80191f6f81a69e23b03d2f79b0b229f3a55c4383c10f',
        'Lemma.Applications.Notebook.cancelPackageWork': '696f5fbb647ef1a9d4558300545dc4e725da123295cf633f572685f9a6938ce2',
        'Lemma.Applications.Notebook.drainPackageInput': '2c8f96b3771eea561558262ccb4b90b2eca85c2649a5468d235607127762f123',
        'Lemma.Applications.Notebook.drainPackageInput.drainStep': '8c53584a9a897688c4b1304f217c8f19aae96086234f6c839583c64a7f556e7a',
        'Lemma.Applications.Notebook.finishOpenPackageCourse': '0ca23bb205ce8fba7e86892e7b22464b88d82f96180584091cf51b24cde30138',
        'Lemma.Applications.Notebook.finishOpenPackageCourse.restoreSelection': '7492e9de7af78e8da7e92248da80e61e160320a1e0a52fe379cfe1801e212ff2',
        'Lemma.Applications.Notebook.mainPackageClosureBulk': '0318d48be82d75b41e30cbb2034da5e6f2ea22f6bea86d344f70747d9ff1b5ea',
        'Lemma.Applications.Notebook.openPackageCourse': 'd5762b37a343c8bd38aedfb27eed87c7460ad3f51af908215632b1414f5410cf',
        'Lemma.Applications.Notebook.packageAllocateStep': 'b2795b049e5d22ae65f6d759bccbd8a7e797de03c2f5f5a126ece91da5c6cf0f',
        'Lemma.Applications.Notebook.packageBindingScratch': '6019911928aea1f7cba74c69bd7fb785b722c00a7a37ce2af0544e2cb7c684f1',
        'Lemma.Applications.Notebook.packageBusy': '3e24023e8cb637d080357507521dbb3f25be0b0d9ab5f086def874b33e173694',
        'Lemma.Applications.Notebook.packageBusy.done': '3e3cdf646dd52cf59c7904f5ae73d42908404223b6236fe667a41035349bb3b6',
        'Lemma.Applications.Notebook.packageBytes': 'fb849ba52526936b964f687dc3d062e30adf7e4bd005f903a0706c41d1638282',
        'Lemma.Applications.Notebook.packageCancelInput': '803198426cf0b88751d8f617672060c797177edb7d13d405b94fcfaf4011c0af',
        'Lemma.Applications.Notebook.packageCloseState': 'c53f9a56d9545fbb332ccfdf81ed6ca71625d9054af8ae804c7dece051eb7885',
        'Lemma.Applications.Notebook.packageConfigureStep': 'e2de3951a2da8b6500d2449d7f0843957048e098554acc8ad84eec3cb3034494',
        'Lemma.Applications.Notebook.packageContext': 'f80ebe8624a4c516f0002d0c6a19a435a26968c1c4b86601bb3894b3daf78266',
        'Lemma.Applications.Notebook.packageControlByte': '0434abbeae4869b58af9fc790ee27c8909172c168c6d6d1173a9d1bf83c33bce',
        'Lemma.Applications.Notebook.packageControlCharacter': 'a78969a4c6e8f2d83d9cf367d0fbb258990dd9175908f7ad51ad0077d6148362',
        'Lemma.Applications.Notebook.packageControlPress': '8ae216eec9831e93877fff367642d9d87c31bd74d59a8504e14a880ce72536f1',
        'Lemma.Applications.Notebook.packageControlStep': 'bc48907ced874c7d387b44de7322b31562e3fb3a9b5bbf46521dc13bce150d12',
        'Lemma.Applications.Notebook.packageControlTile': '9f11397c5393bccced013eaec45eb6db4ad131c0eee72859096456396080127e',
        'Lemma.Applications.Notebook.packageCourseError': '2388e5b7c60cd82e5da97fbb6d21d30048ae1d84a0ab57a3315f48db1f3544d6',
        'Lemma.Applications.Notebook.packageCoursePress': '91ff60d8c330562cdfdbf2b28e1f6918d38fbc0ec703b5f7c66897c40069462b',
        'Lemma.Applications.Notebook.packageDocumentStage': 'e3cf99d75d8807cd5820306a357cc2ca4d4e2e75cccc536e8837aa2b5fa5dc8a',
        'Lemma.Applications.Notebook.packageGet': 'aad1d768e1895745ba1205a893e5cb26710943ba0a13dfab2cdde3e78ecae936',
        'Lemma.Applications.Notebook.packageGlyphs': '57a1adb68cafdb6688a589ab0e77cc10572131e4ec4e51502acb10794f1cdacf',
        'Lemma.Applications.Notebook.packageHex': '61109b6a00bbbc66d1674c2b346846c3c46d00a3d17f947da41c32cc78abedb9',
        'Lemma.Applications.Notebook.packageIdentityCharacter': 'd1f271734188f9f0aba80941f0baddd027ea0865b3c62bf01447531560f510a4',
        'Lemma.Applications.Notebook.packageIdentityStep': '914c540754e867cf8fcb8d9b4c1166fbf1021eb3131b38905521cdf6630bf938',
        'Lemma.Applications.Notebook.packageIncoming': '15a9f42827ed58809afbb3885c781e2b164d9783116befadc6410d363bbaa106',
        'Lemma.Applications.Notebook.packageInputSample': 'f5c4a59af22209412bc6113e3d815057b6dd826014558d0c66c3711e815c9ca2',
        'Lemma.Applications.Notebook.packageInputSample.acceptSample': 'ba1d556911769a1c3e25de63eeaf2740f0f52b58abb36db9884eb57957f9300d',
        'Lemma.Applications.Notebook.packageInputSample.write': 'becf958c70b71749dc7cb6dc410cbccd4d346b06e8621cb35fa8ce744c26e721',
        'Lemma.Applications.Notebook.packageOutgoing': '4023de92d51d0ac00a51ff53876faf7c2cf7e9d821988db3393876578367233f',
        'Lemma.Applications.Notebook.packagePut': 'a0ecd76f6227e43d1a6b11ee1fd2618139bf7248ab065e1f55785ab492ba2893',
        'Lemma.Applications.Notebook.packageReadComplete': '1116272193e67b63a60923e08560d2c887f036a7b53d030e4203d6730b9d221e',
        'Lemma.Applications.Notebook.packageReadEOF': '7194263eaacb303814502032562d365cee79f990091e4c89427d86f5eab2ccfc',
        'Lemma.Applications.Notebook.packageReadFloor': 'f3a11e41f4b6874854e87ff7e20432741a10aa450d42ec60a17284a49cc6e952',
        'Lemma.Applications.Notebook.packageRecord': 'cd5a0e3203cbeaf57ad1acc0affae7f556f9156e4e864c87a1bb4b4cfbbfe78f',
        'Lemma.Applications.Notebook.packageState': '25c2d97ccdd7d3d79f9704a806f14beeffb8b3cfc70d68f753a70ca81bd8d1ca',
        'Lemma.Applications.Notebook.packageStep': '2b8c75ed5b20799b58cbe64ffc1daab66611239961e52e297df17ad28dec4a6f',
        'Lemma.Applications.Notebook.packageStep.drain': '1067fed9f6e64bd3473cde0c28895edb662ddab021725179e03a09d5f957528f',
        'Lemma.Applications.Notebook.packageSubmitted': '4d526695c7cc46f81d3070ba6bb2f53d522cfc6a5e2a4e250195e97faea5f3fe',
        'Lemma.Applications.Notebook.packageTileStep': 'e308bcbaa6ff02750eb98d90ad47d96adb8df69fcc68bf710d39b4d8adcbe75d',
        'Lemma.Applications.Notebook.packageToolbar': '1c26f61db20aa5cbec6e2ead8ee6e2a65b20f71bbd3639a0a9012d709c5b1d8a',
        'Lemma.Applications.Notebook.packageView': '47cba72dc41a4f15ad095d7ea969e6e1b354299f172a7d275c647a02809c8737',
        'Lemma.Applications.Notebook.packageWorkspace': '63903e61dcc94c12cc00d5a7a237fa4c0112aba045ac2ec8e9157ec9a0458954',
        'Lemma.Applications.Notebook.pollPackageRecordPiece': 'bc606f3289a88ec7404b2b5aaf6644d78b49f14758d194ab7f19cb4d1fd7f932',
        'Lemma.Applications.Notebook.publishPackageWorkspace': '65f756af046e73e695f8100e282a0c9ff1ae5146a775d0cccc2aa716f260af43',
        'Lemma.Applications.Notebook.pumpOpenPackageCourse': '3af56541d91536cf0473bef04c6aeb2cf98f1bee664e10dbefcd6e6ab2996529',
        'Lemma.Applications.Notebook.pumpPackageArithmetic': '0dc74760d444745b8a79a406de6f7db919b0b92ea2f0d1036b9e6d0df49b9421',
        'Lemma.Applications.Notebook.pumpPackageRead': '6e8c90da115b4d8437ed131254e8ab2f59fab50786fcee5128d2046f60610c38',
        'Lemma.Applications.Notebook.pumpPackageRead.finish': 'f8abc90b51728f2e15e0efea740408150c03f6f438eca05529d5826fc0af0b89',
        'Lemma.Applications.Notebook.pumpPackageRecord': '7f0e61cbc794fda3c097dbd1d29117a2cacb37459f3dc9214e0599df77f82790',
        'Lemma.Applications.Notebook.pumpPackageWork': '5c80755d422d32b89ed19463e29e846196060612ebb9e4cbaae20b2ec9d64e3f',
        'Lemma.Applications.Notebook.recordGet': 'a4a3870ce303d1b33d9fd31d99f19242bb918990140ed7a2b3cd9edc82eee2d0',
        'Lemma.Applications.Notebook.recordPut': 'e2283a14124c856b347ac2386ceac8454fc18735a3dac117360a79f67c4b7b37',
        'Lemma.Applications.Notebook.renderPackageControls': '084ac12a06ffc93ea19e08dfa0894389845b0afb6b0ddd0e046cc6a999fdc2db',
        'Lemma.Applications.Notebook.renderPackageIdentity': '73a6a92337f843c578e76849de0b3045ae784baf0dd9bee99a032f4f21d1487a',
        'Lemma.Applications.Notebook.renderPackageText': 'e0156d4fceb166bbf9dc2dd2820ac23a1c62a5a901b330f25726c2435b801641',
        'Lemma.Applications.Notebook.savePackageWorkspace': '0fd51db368298f3a8a1022e521f5a847d4d2a0f864b1b8145d2b97a89a9b26a4',
        'Lemma.Applications.Notebook.stagePackageCompletion': 'bf45b3dec25f0bfcb6a422b197d291292a9c0982a0e350266e9191ef312a2c30',
        'Lemma.Applications.Notebook.stagePackageExercise': '7c600f5ec048a4ca3d7119d85204054a5cd532b8c553bf0caa9ec71f5edde970',
        'Lemma.Applications.Notebook.stagePackagePress': '9a309e58053dd3687f38cc8f6e5fa42aea032c103252b3211ed272a07be596a0',
        'Lemma.Applications.Notebook.stagePackagePress.stage': '6c6661935aa99884e2f3db682f9a85b74ecf4b738a270e5f8cf17305f00df89b',
        'Lemma.Applications.Notebook.startPackageRecord': 'd80f9d2668983467c368c0cab831a938c1fd52205bb92e688d98ca4d8ebece6e',
        'Lemma.Applications.Notebook.stopPackageRecord': 'c980b651a3c354caa7afb06647f1331fd0d9005de690275e419c0a4ab799aa64',
        'Lemma.Applications.Notebook.togglePackageCourse': '84d73f8f95eabedb057ad496354f5926376b14eee0a97bae66c4dd3e0d1d87b0',
        'Lemma.Courses.PackageBinding.applicable': '9692690b408c78826f0dbd59af157dee729f49b4539cbe409d2627482c6b1f71',
        'Lemma.Courses.PackageBinding.bytes': 'f095663e5670debbe5ba276d6a4051ac794b52c55ce3324cb55afe0914ff79f9',
        'Lemma.Courses.PackageBinding.capture': 'bd9af8161271f7ea58d255d5487758076306ce639d6d094df97d66635088966c',
        'Lemma.Courses.PackageBinding.captureField': 'b7f783f7623b5b75c27d801c88c071eb914965e635760a8b86d56c59194f17a6',
        'Lemma.Courses.PackageBinding.fieldsValid': '647dbf315c16773f358a7330cb2baf5861d41c317c08ce6909373466ab6c370c',
        'Lemma.Courses.PackageBinding.magic': 'e0f1d8e8e60ed07952b7a924a4419a2ce0dcb4d6c8b33c97aacd18887fd910ca',
        'Lemma.Courses.PackageBinding.put': '0be53b7941d7720965c524c6d036748a7399884a3df606a6af69935da50b31be',
        'Lemma.Courses.PackageBinding.spanValid': '212f36b7ed519fee95e026bc18b872bf620983df4942f1fd1df5fd627e0fcf9b',
        'Lemma.Courses.PackageBinding.validate': '67dde0d20f00d2cec4c99005a60f73116ac6d39560fbfdf991c7af58f608109d',
        'Lemma.Courses.PackageBinding.version': 'b9963e51661245c86a7c5e0253149c979ec3a62256c38ccd8f75340e59643817',
        'Lemma.Courses.PackageBinding.word': 'a4c631d66990cfcb96ad5591924830963831a4a95e9699b9134430ae7e38379c',
        'Lemma.Courses.PackageFormat.crcBit': '54691893121f643da782c03b26c19f913565667c544da91b0879b78dc00f0763',
        'Lemma.Courses.PackageFormat.crcByte': '73fd0015a3e4b98c5e83d71d1220ccfbca9fb43492c33f682f018aa34a7ac776',
        'Lemma.Courses.PackageFormat.entryBytes': 'faf21c9faef8446a8e8a29f79552c069cf2d15aaec0fb7eb39c6ee5a90562190',
        'Lemma.Courses.PackageFormat.headerBytes': 'f095663e5670debbe5ba276d6a4051ac794b52c55ce3324cb55afe0914ff79f9',
        'Lemma.Courses.PackageFormat.integrityFailure': '6e356e0d0e62f391f46e559b1301912c33c7e4258796c2aea496b324a2661e56',
        'Lemma.Courses.PackageFormat.magic': '03e12a1712a73863b05fb3029b7248d29f1fa60e2abcfe709a32cb0c8694be3d',
        'Lemma.Courses.PackageFormat.malformed': '11f81e2b6914502570fea207e94156c1ecbe14f86cb19ca4b0c76110e40e6cda',
        'Lemma.Courses.PackageFormat.maximumBytes': '183784629e1bb69dab9cb2db837ab5995bbd88208e9c917b755c4538cdff63d9',
        'Lemma.Courses.PackageFormat.maximumEdition': 'e770fb816ccbcf70db661b0734a7e2a139cbb52a7135452ea83aad54b7c6dbd4',
        'Lemma.Courses.PackageFormat.maximumEntries': '81e6d42b25903cbfe4583f5c12e7bd7dbc8c6e63be7b4b09a2b1b0058c8fe571',
        'Lemma.Courses.PackageFormat.maximumFieldBytes': 'd3b23a2c44267aa60c934c2338aa1a1f645f1582721ec0b8091b55cdfaa65397',
        'Lemma.Courses.PackageFormat.maximumIdentity': 'ad365789346f6c47271b8300f249908bb2faddb170591ceb9baf76ed7a31678c',
        'Lemma.Courses.PackageFormat.maximumTextBytes': '2264c7af8ea8044ae6a0584e6ffbee9fb46edf7bca6ffc6ccdeaae0fab7a2ea3',
        'Lemma.Courses.PackageFormat.object': '1d2d828aba469aacf01ff40d6f0e7126784a1fded8e24f42a853146bca4d4a63',
        'Lemma.Courses.PackageFormat.prerequisitesValid': '0ebce0be37507d373b8eda2ba095adfa37eda66254b02fc38ac086240fcd707f',
        'Lemma.Courses.PackageFormat.referenceStatus': '8bbe58675bd7941cdceb029e1d0b3f9b3c44a4a07d568d3f5adf63203711a53c',
        'Lemma.Courses.PackageFormat.resourceLimit': 'c93d8c98937f7bec19117dd7a337f6cd8d1842ceb9e1d7adcf9cdd5f45e531e7',
        'Lemma.Courses.PackageFormat.selectionAbsent': 'fb227b83755f323d433cfa8227b23e5375ce5c5324aef2133c09a46ad786e51a',
        'Lemma.Courses.PackageFormat.spanLength': '7217f19d1a65290d3bf411dc4983f2ef0ef50cff4121f560c8d36145929d239d',
        'Lemma.Courses.PackageFormat.spanOffset': 'e10ff1356239f487f93744946a1d4800628e285c7a742fbfb1e4256efe12bcfb',
        'Lemma.Courses.PackageFormat.textByteValid': '2a1222395c2ab88f1ba5a868cf334024ce819d3286c32a555abff8d0d5b559a9',
        'Lemma.Courses.PackageFormat.unsupported': 'afcaacdde67e8b596551ab602aaf3d659c6f278bbac35056fd9f763da1cc819e',
        'Lemma.Courses.PackageFormat.version': 'b9963e51661245c86a7c5e0253149c979ec3a62256c38ccd8f75340e59643817',
        'Lemma.Courses.PackageReader.accept': '13a3fb273854a086aca7f0c8abc79d4bd39899b3bbbf2fdf61b49af851dfbd3c',
        'Lemma.Courses.PackageReader.beginPiece': '7ab116bb7c6c0f1c29ded98de0ac2df923da23a05da995e7013997d25e2fcf6f',
        'Lemma.Courses.PackageReader.cancel': '3ed19c93e244a2a0b278348f0530cfedca26753fb538218e3ddc51a126f2bc6a',
        'Lemma.Courses.PackageReader.clearStep': '13fcc62efd91bd58a27a12992838ae29ef050fd0f40b05397ca7d9921a038bdc',
        'Lemma.Courses.PackageReader.configuration': '5523e28ca050c4b38e32f208343eb2dc94eb65263fe7f4005578701611dcb3b8',
        'Lemma.Courses.PackageReader.contextBytes': 'f095663e5670debbe5ba276d6a4051ac794b52c55ce3324cb55afe0914ff79f9',
        'Lemma.Courses.PackageReader.field': 'a4c631d66990cfcb96ad5591924830963831a4a95e9699b9134430ae7e38379c',
        'Lemma.Courses.PackageReader.finish': '6502d1353bca05f99efa47668555ad65219da16616c472be89952fbd91af20e9',
        'Lemma.Courses.PackageReader.issue': 'f7ecb04b777e08c6ca3cf5dc3b7e05c5cf9afb94b5253a2d7ca63a6dc8bd18f5',
        'Lemma.Courses.PackageReader.maximumRequests': '278cb3fcd3d10252f6eae00119b30a35c09577e2c5be3de05980cd90bc0a6cfe',
        'Lemma.Courses.PackageReader.minimum': '64a6054eb9ba463f87379317a4dd709b5e714eb3d44f1464ded9cefe33e96127',
        'Lemma.Courses.PackageReader.pollPiece': '646ec2ed0dd35e36cf331ac5810fa6abe1ed29f5a051eb1e1d15b510faf2a127',
        'Lemma.Courses.PackageReader.put': '0be53b7941d7720965c524c6d036748a7399884a3df606a6af69935da50b31be',
        'Lemma.Courses.PackageReader.separate': '3ef7579889df1633114eec7936e7dac0d1b4e90b966f5d81412f29e16d9c951a',
        'Lemma.Courses.PackageReader.spans': '1efd0b6cf0c5f1bf1e5635e67c7a9009358122abaf0f95e8b22ef03c863aee14',
        'Lemma.Courses.PackageReader.start': '357f0f1e51266a302474d1397811803eb363664dd38d1c78d4cddf3d481f5494',
        'Lemma.Courses.PackageReader.step': '085a5cfb07cddc70598546018a1fdfdb697002ecbb348b7be8e56159838ed921',
        'Lemma.Courses.PackageReader.stop': 'bb6fd673a9571f62d2910a142acf4745c8e6c32f9e57883692bcc49186ba75a5',
        'Lemma.Courses.PackageRender.cacheBytes': '7331bb9fb1dd139d9e8225242332bbe07421d2f2ed320a6c4234bb75167149ba',
        'Lemma.Courses.PackageRender.clearStep': 'da00366779b6890066dbc96247cf783d08e535df258343ac507dd27f442e6547',
        'Lemma.Courses.PackageRender.columns': '0f382ee946e65c72290eb776fcb1d4a12606cf4f326aa1e8c5b0bcd650d8a476',
        'Lemma.Courses.PackageRender.glyph': 'a47f7e2b7155ad33a77006f802dd811be7c2286e070d1852034d2637c0aed045',
        'Lemma.Courses.PackageRender.pair': 'ebad7bc0e3f133bac986714e7a8032c2b5c2593e473c8f651b597133c831356e',
        'Lemma.Courses.PackageRender.panelWord': 'aaaae8c642044afdd97a1287f15ad7ed4123ad4419f6d124231ecb4fa48e670d',
        'Lemma.Courses.PackageRender.pixel': '90b13c95c7addd512351b7758e6c7becaf68032c9b7e69ee9e6b2845375410e7',
        'Lemma.Courses.PackageRender.prepare': 'e86205439c6b327c120c1d3ad0ad469b09924161ef41d3f7c3bc169ef797b13b',
        'Lemma.Courses.PackageRender.prepareHeader': '470094223e9741a83c190a9e50e2bdd2f1dab1dffee9c8ede7744e243b091b0b',
        'Lemma.Courses.PackageRender.render': 'c64a4a7b8aa075078dc41d10b1d74cee19f3a25bf26245feda0c31ed6a5a68fb',
        'Lemma.Courses.PackageRender.renderByteStep': '0434abbeae4869b58af9fc790ee27c8909172c168c6d6d1173a9d1bf83c33bce',
        'Lemma.Courses.PackageRender.renderHeaderSelected': '36b2a71efa4c81fcd9db8290b0d3f32e34706750efef881802e4399e8170159e',
        'Lemma.Courses.PackageRender.renderSelected': '02ae217c535da21258c563dde48500452ea1bac43084b6c8fc69eb492160d3de',
        'Lemma.Courses.PackageRender.renderStep': '5ec09c3885488335f874450b90babe68e0165bed1b20056bd3354a64a7964026',
        'Lemma.Courses.PackageRender.rows': '81e6d42b25903cbfe4583f5c12e7bd7dbc8c6e63be7b4b09a2b1b0058c8fe571',
        'Lemma.Courses.PackageRender.separate': '3ef7579889df1633114eec7936e7dac0d1b4e90b966f5d81412f29e16d9c951a',
        'Lemma.Courses.PackageRender.textStep': '2772bdc62bff980e8cd5bb5b2d5e86e4de7c4e4984667f266dc9dbb05e51afb7',
        'Lemma.Courses.PackageTarget.crcStep': 'dccfae5365763194e4b879eb1a32154dd5ff0c7073e8afc2113f4957846f7498',
        'Lemma.Courses.PackageTarget.entryStep': '67ae8280c7e16370dee38af6661b4a994cc1c584729984b2d726bc43a85cf3c0',
        'Lemma.Courses.PackageTarget.entryTextStep': '3c789640af8b6b9c012fe72c97ea3765a37a4b084455c372f4a915a5bd2f8c49',
        'Lemma.Courses.PackageTarget.headerTextStep': 'c5878990a205034c2f5fe73970f7e707b139ecfade189716dc083d7410b31fee',
        'Lemma.Courses.PackageTarget.reservedStep': 'f7f476d030c5e8041e9979d703ab688d839350c7c7e897053f9fdefc88cec033',
        'Lemma.Courses.PackageTarget.select': '4bdaa4e02ed35b072ece294ddf7867d8b0bc0047e050f83e8192de11acb13fe7',
        'Lemma.Courses.PackageTarget.textStep': 'dd8e8cc58c94986167d7d8d569279adc124ee016a255c97782466a8fd108843d',
        'Lemma.Courses.PackageTarget.validate': '600d01d3af31038c75b0fb5038392bccffebe426c9f05f3dac7238b1af887bf5',
        'Lemma.Courses.PackageTarget.validateBody': '78cb5ab27b80194b7ce153e367838a4cad87788d58831bdf192e961bb6ea87f5',
        'Lemma.Courses.PackageTarget.validateEntry': 'abaf226411279afcd1d4b6e57bbb1906700c00024fda7fb5106fd8e49a0b11a5',
        'Lemma.Courses.PackageTarget.validateSpan': '94bdd2d97237beff175c877d29486c95dbfb9169cf554cbfc522ce7c2aea6107',
        'Lemma.Courses.PackageTarget.word': 'a4c631d66990cfcb96ad5591924830963831a4a95e9699b9134430ae7e38379c',
        'Lemma.Courses.PackageWorkspace.attempts': '10c067eb8adc9d74e35214c070bd4d7683a45a6725d0a11850fb958f34b2d53a',
        'Lemma.Courses.PackageWorkspace.bytes': 'be5c643af4cbf5b552fa3d120fd7c2816dcb4cfa15b7b0ca2884c9acd7490100',
        'Lemma.Courses.PackageWorkspace.captureSelection': '3576e7709e53fe22b0ac9085a546ac3d98f60cf1dc50d1645b7bc733d44ad534',
        'Lemma.Courses.PackageWorkspace.cloneContents': '5c406f4df7991460c08e0357738f492460d9252085bbfd0f66cc33170930d869',
        'Lemma.Courses.PackageWorkspace.copyBinding': '2967e889ff42da0d08a43d03bf9c614fe348eb3f37fd32472cd027c56e282aff',
        'Lemma.Courses.PackageWorkspace.copyBindingStep': 'bcc1f88e657dfc712cd542dfc159a5fe3fac0c838c2f6ad57fa430044898252d',
        'Lemma.Courses.PackageWorkspace.create': '90959364b923ad14945cec12bcb0c4b46a7c40091d5933792770efdb2bcc0f5f',
        'Lemma.Courses.PackageWorkspace.equalEventsStep': '7d451cc0c90b90f7e8ddda753ee4a596577588a4c916afe31f8033a798d4aa3e',
        'Lemma.Courses.PackageWorkspace.equalHistoryStep': '2ba3205431a6812a64e5a713be729fe49cacf1ecd12618e755f35eb6b6ebc29c',
        'Lemma.Courses.PackageWorkspace.equalSubmissionStep': '916badd374b1c6d45a800187771046c7773899f8be87c0bfec12ac38b8de86eb',
        'Lemma.Courses.PackageWorkspace.equalWordsStep': 'fee83a91a24c217729ac154504868e2f9a1aabd123a21332435fc90e82ff0dbb',
        'Lemma.Courses.PackageWorkspace.field': 'a4c631d66990cfcb96ad5591924830963831a4a95e9699b9134430ae7e38379c',
        'Lemma.Courses.PackageWorkspace.inner': '0f7086fb89008a4c9faf19467b0f108b8e643afb180028b8e7bc8a5b1ab86138',
        'Lemma.Courses.PackageWorkspace.magic': 'c8e91c12c6586a8e1f913f74bf6cd0cd7d91c8601ce09cb735f214c61517503b',
        'Lemma.Courses.PackageWorkspace.object': '4038b660e8c2c381ab1ea337c043ac043352d91debd048b35a983b60e7ba5156',
        'Lemma.Courses.PackageWorkspace.put': '0be53b7941d7720965c524c6d036748a7399884a3df606a6af69935da50b31be',
        'Lemma.Courses.PackageWorkspace.selection': '472a211e52a180260651629064ebf75a9fc9a6e7ab54bea1c9a2388013c8c12b',
        'Lemma.Courses.PackageWorkspace.separate': 'aca7e9f17b3e07aafdbe436e6d4db2e1996ff633eafa35cf9f8b2d549ad9488e',
        'Lemma.Courses.PackageWorkspace.shape': 'aa0af714964322c7b9cace1d797ee62175baa192766b5df5ded52595f63bec69',
        'Lemma.Courses.PackageWorkspace.snapshotSelection': '8f1a7166ef1fe3c2e9eebf2460cf8295ffcb15f047a2e82ee3cebe884e959679',
        'Lemma.Courses.PackageWorkspace.stageCompleted': 'b26123375fd94c5ea212c4bccc94a59656724b9181b765294a0daf22c123d02a',
        'Lemma.Courses.PackageWorkspace.stageCompletedUnknown': 'a16e30c460966a2ec2a944c34da2777d8fca0016cf1dfb130ccf443eb9c72fae',
        'Lemma.Courses.PackageWorkspace.stageRefresh': '5f897b3f411ddefaceb4597b23e4b2776fc1f57cfff59356cd36211b552b7bd7',
        'Lemma.Courses.PackageWorkspace.stageUnknownSelection': 'fd80f0f443068d0736e07c54bb5328508d956935aac9dfe8b3180fb8e65e118a',
        'Lemma.Courses.PackageWorkspace.transitionBase': '54f87b293d50e66727f2c1ec9812fb1e2a8ae2cd20743b07894dcb20354b6913',
        'Lemma.Courses.PackageWorkspace.validate': 'd3fa89cbff186a5c1480ee1eb91955f5c506f3f12e6f2c8eae522c7bdaa67efa',
        'Lemma.Courses.PackageWorkspace.validateAttempt': 'e9f65d2ca4f4aaac9b827b9009d875fee2feaa3201a5af09953a6a43b40a9487',
        'Lemma.Courses.PackageWorkspace.validateOwned': '0c957539855ad9e8eb2689793429ebfe7bf14bc41647770e7a8d7e143be96cbf',
        'Lemma.Courses.PackageWorkspace.validateSelection': 'e99b0c65f89d041023fef2702f0bc911e4f2a9cb84d2251780647a478b54f546',
        'Lemma.Courses.PackageWorkspace.version': 'b9963e51661245c86a7c5e0253149c979ec3a62256c38ccd8f75340e59643817',
        'Lemma.Courses.PackageWorkspace.zeroCheck': 'bc78bd50179321d2fd2d659f82d7bdd7dfe180c333981c0f933132df55fd0743',
        'Lemma.Courses.PackageWorkspace.zeroStep': '46502f5062907d84af1d1b0317bbb65189c85cda7dbf8c27f2c6d7052c7b94c0',
    },
    'post': {
        'Lemma.Applications.Notebook.adoptPackageStep': 'c6d325b44a0c470dfb004817ddccc5f022e2b9d5d1b13e9131272bb72ba024e7',
        'Lemma.Applications.Notebook.adoptPackageWorkspace': '7e0e0d61d40fe905bd1f11f64fe7b0d5ac2e111eb570e3ab9a91560d9a10877f',
        'Lemma.Applications.Notebook.allocatePackage': '33e2643e8600b779a5cc6db4a4c61191d3c5a67317d68e95f1d353e31b53f7fc',
        'Lemma.Applications.Notebook.beginPackageArithmetic': '9a2b66219478937e37da5014ac28a77d39b69837e8298e6bb1180200a5914a9f',
        'Lemma.Applications.Notebook.beginPackageRead': '417c35adad475988bfdab559ae96767621d665c695f2e864ee1522b818e12f97',
        'Lemma.Applications.Notebook.beginPackageRecordPiece': 'd2815410f92af6e29d17cdef71e5966bb7ec9df63bb563f965be1a1118297769',
        'Lemma.Applications.Notebook.cancelPackageRead': 'af1c1fa013c8e9a8084807064969ee1751e75cda25dd08c93c498cd79368e13e',
        'Lemma.Applications.Notebook.cancelPackageRecord': 'd25bb167dd349dc12f375e6a5de145e64dcbdc2b06bb3b92d6613a6c6edef252',
        'Lemma.Applications.Notebook.cancelPackageWork': 'ff0f8cc518e94f91203f2b44847fee800564636c497f90d66919f58836297d3f',
        'Lemma.Applications.Notebook.drainPackageInput': 'cbdfde6adbfa6092495da409d519702253de41bed56559f7f34ca81a0c81611a',
        'Lemma.Applications.Notebook.drainPackageInput.drainStep': '086ebdd5967309fc90ef79d825b756771865375778cedd58aff71063c936b95a',
        'Lemma.Applications.Notebook.finishOpenPackageCourse': 'e68838ee608c0fe6d9fbdce987881a516954880d0be54c4a838523d06fa4ad54',
        'Lemma.Applications.Notebook.finishOpenPackageCourse.restoreSelection': '699f63d78153182d4bcfbec34331bf3c72277baf76a995ffbcc4ed135a651fb1',
        'Lemma.Applications.Notebook.mainPackageClosureBulk': 'b73eb7c881af78850f24757b72cbb32c57389d90bfd0b9e5ddd543199f939114',
        'Lemma.Applications.Notebook.openPackageCourse': '660dd34ccfe931bce50b89796a87f0c7faf4902eb0e82118dbd765e13ff49c4f',
        'Lemma.Applications.Notebook.packageAllocateStep': '8056c53cc105eb5137c715fbc251c9e280771c74fa666b29c03d669cb110ec35',
        'Lemma.Applications.Notebook.packageBindingScratch': '27d3f5ff43952dc12904b7be2f5429ecd5222b0ed91e2b07e49335910b27f45b',
        'Lemma.Applications.Notebook.packageBusy': 'dbac95f4edac51b1cfb26ea4bf1d524b7c8cf19c5f5d3f2f79fdc310710fa84b',
        'Lemma.Applications.Notebook.packageBusy.done': '2797181afeff094f1f57633e568ac143d3f19c3b761c40085a36e860e303eb74',
        'Lemma.Applications.Notebook.packageBytes': 'fb849ba52526936b964f687dc3d062e30adf7e4bd005f903a0706c41d1638282',
        'Lemma.Applications.Notebook.packageCancelInput': '543602e640c86567e9866dfc2dc0d0b38fdc0308edd81d56da2c3329b0286b35',
        'Lemma.Applications.Notebook.packageCloseState': 'ec0c6e2387a2c50be2e21a3b79601f6ba7d74f4b24324ae4561e9206980b7c36',
        'Lemma.Applications.Notebook.packageConfigureStep': 'cdea32ae15442de7c04700f8e0ece46cdeec80982ff49dc496d6b98e93a465a5',
        'Lemma.Applications.Notebook.packageContext': 'f80ebe8624a4c516f0002d0c6a19a435a26968c1c4b86601bb3894b3daf78266',
        'Lemma.Applications.Notebook.packageControlByte': '0a28ef99e5a853a5c5134444a91dbc955f9db52f2c668b72806c1c53644a88c9',
        'Lemma.Applications.Notebook.packageControlCharacter': 'efebc4397b55a9782e127d727cfcbcee48ed528d81fa809a62963eb2bd519813',
        'Lemma.Applications.Notebook.packageControlPress': '90c077babd25df022c1c0ed39fdade5351ed93773843ff1bce1f63093584f506',
        'Lemma.Applications.Notebook.packageControlStep': '40303d5616c861beb70f8c0898d88dc66ffd952e4e26a5c1a4f249ac84f9a19e',
        'Lemma.Applications.Notebook.packageControlTile': 'f929e78cd479a7f47f0422722fa47fec9ed02f7b852b3e8052177a03f6d54a4b',
        'Lemma.Applications.Notebook.packageCourseError': '446cba0fc49ad38ec9c8fbec9ecf1bf03c44ad16fef67df17bdf3995f5609264',
        'Lemma.Applications.Notebook.packageCoursePress': 'de9aafcd1b23afdb3a8e58ee0f624b9bae11c6e87ac5c0814c00f679399b5e0c',
        'Lemma.Applications.Notebook.packageDocumentStage': 'e3cf99d75d8807cd5820306a357cc2ca4d4e2e75cccc536e8837aa2b5fa5dc8a',
        'Lemma.Applications.Notebook.packageGet': '3d883c7409725ecfa877a4776f606360b06181ba656647b7ea86b52b62b1fb30',
        'Lemma.Applications.Notebook.packageGlyphs': '57a1adb68cafdb6688a589ab0e77cc10572131e4ec4e51502acb10794f1cdacf',
        'Lemma.Applications.Notebook.packageHex': 'a871d0e305606d5287a06164e7b2cdbe770440f16cd5d340ff137f996708aa80',
        'Lemma.Applications.Notebook.packageIdentityCharacter': 'd54ecd96e553646c58fd86cb46839798088a47c21961719ea03b27faefaba0dc',
        'Lemma.Applications.Notebook.packageIdentityStep': 'da0b6b63a8f81bc3aa7aef5b4c80c17cf19e03c3b2937b8f6b88e9716bfe7db1',
        'Lemma.Applications.Notebook.packageIncoming': '75f28589d179df17bf76c7410f7cdd07a99713efa2c8e5fedc289eafc638d7e5',
        'Lemma.Applications.Notebook.packageInputSample': '4e66ce1dfb1443612e1c382282441c1d25a1fc91396b598324da86babcb0ad9a',
        'Lemma.Applications.Notebook.packageInputSample.acceptSample': 'd02c4796e86f8cb05b7ed88799920606504a1ff877a1ced107b7132c2c5e159f',
        'Lemma.Applications.Notebook.packageInputSample.write': '708fba3920451edcef9f0df92f610ac062e4a8c7d6e524ec7912557ae0abd4fa',
        'Lemma.Applications.Notebook.packageOutgoing': '0f6da890c74d594eb1cccbc64d5777b825d8d89bd39b2c6fb7bd8dc659374dd1',
        'Lemma.Applications.Notebook.packagePut': '09d55bcd2016d05f70bbfead779f5ef33ef704ff1b769bc970f5a313c0c3834e',
        'Lemma.Applications.Notebook.packageReadComplete': '3729b11feee67c21e208fb77aa01cda8b08054521908230a4507bde5de7065c7',
        'Lemma.Applications.Notebook.packageReadEOF': '8b2841f80c0b55a22e2d93db41c9f1c5c8ed88ec44dc80740bded65d5720d37c',
        'Lemma.Applications.Notebook.packageReadFloor': '61e94e771c9b9bff1008b44f86de780a909d6e25649372c73e0591c93252b76d',
        'Lemma.Applications.Notebook.packageRecord': 'eb218824561ce713083aba50d1828330bf5f56ca4192f6c04930cacfe9105827',
        'Lemma.Applications.Notebook.packageState': '36ec5bbefe99c60b6585c72e0d37d6270115d95d3e1931aff7208f4d69963768',
        'Lemma.Applications.Notebook.packageStep': '68118f36a5ac687c70bbf684a21e9c368d83738abeace1ca4939e2a4a64216a6',
        'Lemma.Applications.Notebook.packageStep.drain': '21ae9a7725ba7954d00db260ed119ee55a47a89744ff8a7ae13ca63cd45d4a6d',
        'Lemma.Applications.Notebook.packageSubmitted': 'e97f7b4e373700d85d533b4d1b855775fac7bb4f00a1696b16f022859c75ee76',
        'Lemma.Applications.Notebook.packageTileStep': '919b6b2f4d70b57b0b9a15217fb1b77e128c9de4e88b473ff28d8bed0402902e',
        'Lemma.Applications.Notebook.packageToolbar': '517a11fa6036cfaff1b4e6fdafd9e43c8939d5ea1a743ed3113c756ca2e5844c',
        'Lemma.Applications.Notebook.packageView': '477bd077c0605bb8e13b21720ee4b437f5aad32ebb053edf2dfb932d4bc938d8',
        'Lemma.Applications.Notebook.packageWorkspace': '63903e61dcc94c12cc00d5a7a237fa4c0112aba045ac2ec8e9157ec9a0458954',
        'Lemma.Applications.Notebook.pollPackageRecordPiece': '2e8397cbb51af1e056ad700c8c72006c3a471ec46b0021a7c31cc425ecd11b53',
        'Lemma.Applications.Notebook.publishPackageWorkspace': '9a9a2e11a917ac100454b03ae5df7f589086d8f9214918194bc0d07cfbd5847d',
        'Lemma.Applications.Notebook.pumpOpenPackageCourse': '1cb8d397409986e89904dc600948286cf6f2cb301aa0bdd8cd961e1e459baf8a',
        'Lemma.Applications.Notebook.pumpPackageArithmetic': '1a8e599e397c675f4b990610ee827fe42ea45b484258ee9d74b3b42e55966b70',
        'Lemma.Applications.Notebook.pumpPackageRead': '3d210b48dc187e558644e4218878e06e4251afee462e26909777ba23e3f70e62',
        'Lemma.Applications.Notebook.pumpPackageRead.finish': 'ae965a3fc4f70d5558c5c0e93393154b42c240973b386f93526aa85f684124e3',
        'Lemma.Applications.Notebook.pumpPackageRecord': 'e074e09f2b544c2489f94c3ee03ed7fc07fcf547b2883c52dd2c27945d117e83',
        'Lemma.Applications.Notebook.pumpPackageWork': '27b448eace289562fca6ccc9f7a3c60ee1d4c2543388512cdfaae42ce2b5ee5f',
        'Lemma.Applications.Notebook.recordGet': '8e739ddcb8274af429ac95b62598b6ba5a4817a65be6591553e0cbcdf636df87',
        'Lemma.Applications.Notebook.recordPut': '5b9b1402caedfc32837a380cabce7aeefe6479e0c4b4a581cef17f506f6cd98a',
        'Lemma.Applications.Notebook.renderPackageControls': 'f87406844f30a576c8377879dc7b289d37d5eb69ffc723093763de74affbdaa5',
        'Lemma.Applications.Notebook.renderPackageIdentity': '84eeb176955005b21cd6554016bba69a986788a3e7e774aba76e652761cd28da',
        'Lemma.Applications.Notebook.renderPackageText': 'a704aaefae087ff7cb7b6b80459a3cca2a3e81a163ee94287c3be0a0c83166b7',
        'Lemma.Applications.Notebook.savePackageWorkspace': '87d836ef20ca53868af46717d19d50062d3ff74854d40252520f295578235fe4',
        'Lemma.Applications.Notebook.stagePackageCompletion': '1cfc97f6bd89cf67390c6b06ef7304db305e2ac77abdb4de73bf716823cf0f7b',
        'Lemma.Applications.Notebook.stagePackageExercise': '39514018921758623041822843e934d3a6fd02ff766474b080b0c96e592cff00',
        'Lemma.Applications.Notebook.stagePackagePress': '97f5f09f247a1e13b3c6450b6bbfa79849f67d678ff1a8239e2cb826ff53f330',
        'Lemma.Applications.Notebook.stagePackagePress.stage': '6790f0801114e77d1a7bb80ba60eb093c1741d3518ef1d9ba73011ff31979796',
        'Lemma.Applications.Notebook.startPackageRecord': 'a1d40d3b7ebb1e1ffc64076ab6dbb590a197f74d7ad412111fa6e565d322d3bc',
        'Lemma.Applications.Notebook.stopPackageRecord': 'da2976f7b09cb103d83013e79cd98e30cddf37f752e7b0b736646e7ad6632df6',
        'Lemma.Applications.Notebook.togglePackageCourse': '9196b8cd51d270dede61e8e32ad0bb1a8b81cf562f8434a0dd8f42e92c027911',
        'Lemma.Courses.PackageBinding.applicable': '928824c2c2de798d19d51024524cd4d8617f37af4d93a615a37b644bc1a46d3f',
        'Lemma.Courses.PackageBinding.bytes': 'f095663e5670debbe5ba276d6a4051ac794b52c55ce3324cb55afe0914ff79f9',
        'Lemma.Courses.PackageBinding.capture': 'a79a6fd68b231886ed125271e6ed1341335de8ce43cbfd746e70676903cc8fbd',
        'Lemma.Courses.PackageBinding.captureField': 'e59b8490d55be1be1f2e031f5186dfdb32caa4d4665ea5d296858608e53bd388',
        'Lemma.Courses.PackageBinding.fieldsValid': 'd1a79c3cbf75694e491617e3c23b7a75fed33275cc9138411866145290fb9821',
        'Lemma.Courses.PackageBinding.magic': 'e0f1d8e8e60ed07952b7a924a4419a2ce0dcb4d6c8b33c97aacd18887fd910ca',
        'Lemma.Courses.PackageBinding.put': 'e92333a3b49f0dea98d6dde9f5fbaa1740377f02ac65f7e11ae1fd45d75f18db',
        'Lemma.Courses.PackageBinding.spanValid': '8118e5134e1a22a38aedea3b831edc186efe2bffe93494e541c9495208e62694',
        'Lemma.Courses.PackageBinding.validate': '4a0015af78a46a17d76255b316759c9a632e85d33859e4750830f58676ce1d9f',
        'Lemma.Courses.PackageBinding.version': 'b9963e51661245c86a7c5e0253149c979ec3a62256c38ccd8f75340e59643817',
        'Lemma.Courses.PackageBinding.word': '5599e755c7ee70e89aea93fc63e5fbf1bc81fb3ccd1bcf934da416867db98677',
        'Lemma.Courses.PackageFormat.crcBit': '1b397843930b7c850b40432740e16c9961766400c8884468975495117a91152f',
        'Lemma.Courses.PackageFormat.crcByte': 'd1566a7c74629497b5c7891ffa34ff0b5724cd1192c37f71b1c042cf630e8167',
        'Lemma.Courses.PackageFormat.entryBytes': 'faf21c9faef8446a8e8a29f79552c069cf2d15aaec0fb7eb39c6ee5a90562190',
        'Lemma.Courses.PackageFormat.headerBytes': 'f095663e5670debbe5ba276d6a4051ac794b52c55ce3324cb55afe0914ff79f9',
        'Lemma.Courses.PackageFormat.integrityFailure': '8804faadd4815ea2f0d1aa5eba0ca0232f956bb094572be819d65c4adda1010e',
        'Lemma.Courses.PackageFormat.magic': '03e12a1712a73863b05fb3029b7248d29f1fa60e2abcfe709a32cb0c8694be3d',
        'Lemma.Courses.PackageFormat.malformed': '7b0ec7fae95792002d255c4b0731d8cb9239a5b8775d7399e67784116228d68a',
        'Lemma.Courses.PackageFormat.maximumBytes': '183784629e1bb69dab9cb2db837ab5995bbd88208e9c917b755c4538cdff63d9',
        'Lemma.Courses.PackageFormat.maximumEdition': 'e770fb816ccbcf70db661b0734a7e2a139cbb52a7135452ea83aad54b7c6dbd4',
        'Lemma.Courses.PackageFormat.maximumEntries': '81e6d42b25903cbfe4583f5c12e7bd7dbc8c6e63be7b4b09a2b1b0058c8fe571',
        'Lemma.Courses.PackageFormat.maximumFieldBytes': 'd3b23a2c44267aa60c934c2338aa1a1f645f1582721ec0b8091b55cdfaa65397',
        'Lemma.Courses.PackageFormat.maximumIdentity': 'ad365789346f6c47271b8300f249908bb2faddb170591ceb9baf76ed7a31678c',
        'Lemma.Courses.PackageFormat.maximumTextBytes': '2264c7af8ea8044ae6a0584e6ffbee9fb46edf7bca6ffc6ccdeaae0fab7a2ea3',
        'Lemma.Courses.PackageFormat.object': '31623aa7d861ec9b057dfd0c693dac4e181c72d5487554ae4d536773766357d1',
        'Lemma.Courses.PackageFormat.prerequisitesValid': '9c3956328d93d70ebaaef99b0034b84534264a679e3065e8d2b1aa1a959fc5d0',
        'Lemma.Courses.PackageFormat.referenceStatus': 'c94229428286068b95ca632a811d358beaf07e738fb3778a2e5b6a6ae70b9bab',
        'Lemma.Courses.PackageFormat.resourceLimit': '2dd3a7b81594b802335cdf802496ed329798fdb500b4a1d54ac43dae1b93a08d',
        'Lemma.Courses.PackageFormat.selectionAbsent': 'ebeb93976fe354f52a6a76a838a062aa1c0499798e9b9e7e70ee956115d435ad',
        'Lemma.Courses.PackageFormat.spanLength': 'a248c75e334bd25fd1070c1d07b6707a4cb600aa77849d962f52f5b622c1f46a',
        'Lemma.Courses.PackageFormat.spanOffset': 'e10ff1356239f487f93744946a1d4800628e285c7a742fbfb1e4256efe12bcfb',
        'Lemma.Courses.PackageFormat.textByteValid': '41be7d712fce75affb9da9cb244d5b7388860a40a4a9a528928340cb3274f893',
        'Lemma.Courses.PackageFormat.unsupported': '964c1dc0d797007981e0eba6b731bdf1f4fda7de37e1918630e04c285e3e9bff',
        'Lemma.Courses.PackageFormat.version': 'b9963e51661245c86a7c5e0253149c979ec3a62256c38ccd8f75340e59643817',
        'Lemma.Courses.PackageReader.accept': '309b322bb31b169607008e0a3054d3c8110e697f46c6d9d0601647ca865baf24',
        'Lemma.Courses.PackageReader.beginPiece': '5e6b52eb74b54dbab88631e999a49a8843f261055cbe3d1edef39753f39d7d22',
        'Lemma.Courses.PackageReader.cancel': '8a7abd89871165cce21918729d72026baf54c752f9671c2f5ac84154c3a77e88',
        'Lemma.Courses.PackageReader.clearStep': '32585a550cbec394a034236cd80cf3ab7446e408e9d56c919450f53b25c5968d',
        'Lemma.Courses.PackageReader.configuration': '506a8f596315d04e73e8ec9690a808fdf4b2068619160550e7d17b666c61b801',
        'Lemma.Courses.PackageReader.contextBytes': 'f095663e5670debbe5ba276d6a4051ac794b52c55ce3324cb55afe0914ff79f9',
        'Lemma.Courses.PackageReader.field': '5599e755c7ee70e89aea93fc63e5fbf1bc81fb3ccd1bcf934da416867db98677',
        'Lemma.Courses.PackageReader.finish': '3ff0cfeb945a042a46bd599d4c698aaaad8a1593fa16820990bf618ca06bd788',
        'Lemma.Courses.PackageReader.issue': 'bcc077194dec74c729f762b6ae3a63a8af76c9552615cb128cee1414bf56d08b',
        'Lemma.Courses.PackageReader.maximumRequests': '278cb3fcd3d10252f6eae00119b30a35c09577e2c5be3de05980cd90bc0a6cfe',
        'Lemma.Courses.PackageReader.minimum': '3f36e241a73e1b050b6bf8eacf1df8b31fe8eab989af368c9ffad9d77d2ae1df',
        'Lemma.Courses.PackageReader.pollPiece': 'e6a3d290fd506d1a9030e103a82c7f3d16a4a7c009f94fb2b098f134fffdcf17',
        'Lemma.Courses.PackageReader.put': 'e92333a3b49f0dea98d6dde9f5fbaa1740377f02ac65f7e11ae1fd45d75f18db',
        'Lemma.Courses.PackageReader.separate': '53f85c73edc00b8bffe3cbd7c2cee30cde55f099fba234156b66de212944f285',
        'Lemma.Courses.PackageReader.spans': '6116757fdfd6b801985b633d0a71109898871f0215b34112b0893fb087a9a6d2',
        'Lemma.Courses.PackageReader.start': 'c3e428aca39bb4659750cd01ba853c0ade49b22b4107dc03c3e85287f2444972',
        'Lemma.Courses.PackageReader.step': 'd81898bdb79c641e0619d223469308721bc202abf4d66d54f25668be703024a3',
        'Lemma.Courses.PackageReader.stop': '027d15948ffdb60cf29d54b795c92274fd69ae2345d7e1add58e7dff8a89ffc8',
        'Lemma.Courses.PackageRender.cacheBytes': '7331bb9fb1dd139d9e8225242332bbe07421d2f2ed320a6c4234bb75167149ba',
        'Lemma.Courses.PackageRender.clearStep': '2d316d07d6974b9b26a0c1d0604a21cb2c8b1491dfe15f64df3233eada98539e',
        'Lemma.Courses.PackageRender.columns': '0f382ee946e65c72290eb776fcb1d4a12606cf4f326aa1e8c5b0bcd650d8a476',
        'Lemma.Courses.PackageRender.glyph': 'a3597b6ffc8522e550eccffa0075eb7c557abddb6462e9cbceb26b90ecfd26cb',
        'Lemma.Courses.PackageRender.pair': '6b6f6835a97d68e7ebf9fa8bd6fa3e35fb7b5712d7b1d526428b47c3172fbe13',
        'Lemma.Courses.PackageRender.panelWord': '6dd845f48e23f4025f2bfc49f3dc6d6a9e7b56a7478022857590582740109361',
        'Lemma.Courses.PackageRender.pixel': '510c7f613b739a7a75451a3fc06b142dbae3039f217b03a7d16efe464cf0e11e',
        'Lemma.Courses.PackageRender.prepare': '5b0ab19615c9e45c584c7ae7105ce69b8335247e112c5ffd770828cb2904df5b',
        'Lemma.Courses.PackageRender.prepareHeader': 'e7212dff8b27f3a98dd2375a2676d12885a03e698dad6b1e274a2012eece2cbd',
        'Lemma.Courses.PackageRender.render': '29e580cf330be9b51f518bdc33b7733b50a18600a24c84ed9c64ef21c9a9c1d1',
        'Lemma.Courses.PackageRender.renderByteStep': '0a28ef99e5a853a5c5134444a91dbc955f9db52f2c668b72806c1c53644a88c9',
        'Lemma.Courses.PackageRender.renderHeaderSelected': 'e8f1c669a29c28a2f9430ae01b4a40cb8e37e43ee0c223370eabf92b6fc42a05',
        'Lemma.Courses.PackageRender.renderSelected': '20d0939fd3c6d222b38d4ed31bc46c4142212a95b3b15857ca890d242987fba7',
        'Lemma.Courses.PackageRender.renderStep': '0b67d41576a88c7131d5c3c4fc7abca010a4440e095e71e1124187a5a0c8363f',
        'Lemma.Courses.PackageRender.rows': '81e6d42b25903cbfe4583f5c12e7bd7dbc8c6e63be7b4b09a2b1b0058c8fe571',
        'Lemma.Courses.PackageRender.separate': '53f85c73edc00b8bffe3cbd7c2cee30cde55f099fba234156b66de212944f285',
        'Lemma.Courses.PackageRender.textStep': 'a28467bb45baba928b30a59af0e140ac0bade82d5158702071d2af67419acce5',
        'Lemma.Courses.PackageTarget.crcStep': '4730ae9f58f3e58a8d5f09403d791f9e2213b4272a5e0b46c9bca9ee1ef735e5',
        'Lemma.Courses.PackageTarget.entryStep': 'a807fe4ab9490404410542c65c07d3f062acce6bebfec07d443c4382a867a86c',
        'Lemma.Courses.PackageTarget.entryTextStep': 'ffcbd278e041b0d82c579187684fe1a74d5f57d9322a2ba6a503185094f6170b',
        'Lemma.Courses.PackageTarget.headerTextStep': '340515963bfb7ecb4ddcf4641a0aee0a5b325966921103b876e0b9221ce07da8',
        'Lemma.Courses.PackageTarget.reservedStep': '9efc1d5c810db8a13915f443540a1c7d7fe466dcb3324d582e67a6b64bd724b0',
        'Lemma.Courses.PackageTarget.select': 'b408d9e74f09bb8cc011bbf10a2f6915fb922a7c990a5c71cd4a76d5e087c683',
        'Lemma.Courses.PackageTarget.textStep': '49f2d83229ff0a36f67db1707710b8d628a10d55c70643443c14924a815ef09c',
        'Lemma.Courses.PackageTarget.validate': '7f08021dd0044fa352915a305dbb33600a75574824be4d0e7d4821f3553f6f35',
        'Lemma.Courses.PackageTarget.validateBody': '8a1fc63445c08a628238529669e517c1934eb3b94e6747649870b77a45d87386',
        'Lemma.Courses.PackageTarget.validateEntry': '4186eccac0606d8870385382e58a4d2cc5f2712a5d193cf1f888ad84640b1200',
        'Lemma.Courses.PackageTarget.validateSpan': '211de442eef061632bfa2d904168992099aadb37df31fc8884193faf5a008eee',
        'Lemma.Courses.PackageTarget.word': '5599e755c7ee70e89aea93fc63e5fbf1bc81fb3ccd1bcf934da416867db98677',
        'Lemma.Courses.PackageWorkspace.attempts': '10c067eb8adc9d74e35214c070bd4d7683a45a6725d0a11850fb958f34b2d53a',
        'Lemma.Courses.PackageWorkspace.bytes': 'be5c643af4cbf5b552fa3d120fd7c2816dcb4cfa15b7b0ca2884c9acd7490100',
        'Lemma.Courses.PackageWorkspace.captureSelection': '699aa987a895d69ef08c0ea8424024c6dfb31e989caf596b8ba62f9a94275f31',
        'Lemma.Courses.PackageWorkspace.cloneContents': 'b70f59ab147a3356110fd68159245f1128080c9072f0ac55d5d0d7266c4474ed',
        'Lemma.Courses.PackageWorkspace.copyBinding': '5f62ee424fe9e0bb7125f6e3803df7b98b2cf95be1641c054769f111d71f23e0',
        'Lemma.Courses.PackageWorkspace.copyBindingStep': 'cbbe9909d3a0313ddc29b17b7e5bb449563eca181e346c329b98aabe13995378',
        'Lemma.Courses.PackageWorkspace.create': 'e54bb312f346ba5611443b3f6d3a2be6b288c8ad4ccb38c5060d7d2d3d570226',
        'Lemma.Courses.PackageWorkspace.equalEventsStep': '42686d5e0b2ded75db0ccc1d702405f0ca899805f95c7db2b22c56dda022b14e',
        'Lemma.Courses.PackageWorkspace.equalHistoryStep': '0cd1404be02af390f3b491a706c6728663b1eb3cd5a6ad06e21d2397a9d54962',
        'Lemma.Courses.PackageWorkspace.equalSubmissionStep': 'e6c9a78ccc89ae6ed205b867248ed2d4e93e198f6fa4f44ddbbbbebb7688c049',
        'Lemma.Courses.PackageWorkspace.equalWordsStep': 'd8bd89276be1a098855678025a084f81ef9f1355432f3cc769d7eb7dfaaf258e',
        'Lemma.Courses.PackageWorkspace.field': '5599e755c7ee70e89aea93fc63e5fbf1bc81fb3ccd1bcf934da416867db98677',
        'Lemma.Courses.PackageWorkspace.inner': '0f7086fb89008a4c9faf19467b0f108b8e643afb180028b8e7bc8a5b1ab86138',
        'Lemma.Courses.PackageWorkspace.magic': 'c8e91c12c6586a8e1f913f74bf6cd0cd7d91c8601ce09cb735f214c61517503b',
        'Lemma.Courses.PackageWorkspace.object': '4fa54b2b461924e1e039d1560582b8b023117482a86cdf4f8fc2f2afe899d119',
        'Lemma.Courses.PackageWorkspace.put': 'e92333a3b49f0dea98d6dde9f5fbaa1740377f02ac65f7e11ae1fd45d75f18db',
        'Lemma.Courses.PackageWorkspace.selection': '472a211e52a180260651629064ebf75a9fc9a6e7ab54bea1c9a2388013c8c12b',
        'Lemma.Courses.PackageWorkspace.separate': 'a5a356faf9eca8f1d23ed88af4fd2871e35f5a4d0ebb6144a3707358c40f14a4',
        'Lemma.Courses.PackageWorkspace.shape': '0a640888a0b648d9d011a5cfd65bee536cc89b2047f7e33d5fa99ae9305bd3b5',
        'Lemma.Courses.PackageWorkspace.snapshotSelection': '7a0a1a45122bc139e3907736dfec9efc0252b9f0943769a0d16811bd9e2231a7',
        'Lemma.Courses.PackageWorkspace.stageCompleted': '7f337c9919572b800e71c01aea9aad810ec88a17fddf38cf6c24830926a52a81',
        'Lemma.Courses.PackageWorkspace.stageCompletedUnknown': '993b52427289cb417bde4808b0f8a2954e253926e1603077e490718fadbb964c',
        'Lemma.Courses.PackageWorkspace.stageRefresh': '200197ede9b37516de124b3357b507c58bb9396e316a7fe26aafa8b7704af6e3',
        'Lemma.Courses.PackageWorkspace.stageUnknownSelection': 'dc03e7f276e816d6f0663bff479ced022575e6f2e453953085d377257efc446e',
        'Lemma.Courses.PackageWorkspace.transitionBase': '48d8f741409dabae1d8e911b53b39a2a9dc26a6d5e3a1a9dd098e0c81720254e',
        'Lemma.Courses.PackageWorkspace.validate': 'e96c90310bac1f34e1e2a472721762c9e2e075916bcd2e09a3930302b439209e',
        'Lemma.Courses.PackageWorkspace.validateAttempt': 'ae8aa0308c0ca17a087cebafefe95693bb2fdaa52aa3e50e96cc029484130a79',
        'Lemma.Courses.PackageWorkspace.validateOwned': '885083446a3925ff8fdaf6c2c609ad052a818a24a282e3b8d030977899ba9b05',
        'Lemma.Courses.PackageWorkspace.validateSelection': 'b205607db3db00b16ee658d116923a60edb9a7b4ef1fd51fc4248be0e09b53b5',
        'Lemma.Courses.PackageWorkspace.version': 'b9963e51661245c86a7c5e0253149c979ec3a62256c38ccd8f75340e59643817',
        'Lemma.Courses.PackageWorkspace.zeroCheck': '3dfaa6ec7ca26ad55f89128faf59187b440711963ffc59d4625876a97d67bfbb',
        'Lemma.Courses.PackageWorkspace.zeroStep': 'ed15a240754777db786f5d5c5664e0ed53e29f9f4dbbf3c1355fb6c312cfbe64',
    },
}
PRODUCTION_CALLERS = {
    'pre': {
        'Lemma.Applications.Notebook.adoptPackageStep': ['Lemma.Applications.Notebook.adoptPackageWorkspace'],
        'Lemma.Applications.Notebook.adoptPackageWorkspace': ['Lemma.Applications.Notebook.finishOpenPackageCourse', 'Lemma.Applications.Notebook.publishPackageWorkspace'],
        'Lemma.Applications.Notebook.allocatePackage': ['Lemma.Applications.Notebook.beginPackageRead', 'Lemma.Applications.Notebook.openPackageCourse'],
        'Lemma.Applications.Notebook.beginPackageArithmetic': ['Lemma.Applications.Notebook.packageCoursePress'],
        'Lemma.Applications.Notebook.beginPackageRead': ['Lemma.Applications.Notebook.packageControlPress', 'Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.beginPackageRecordPiece': ['Lemma.Applications.Notebook.pumpPackageRecord'],
        'Lemma.Applications.Notebook.cancelPackageRead': ['Lemma.Applications.Notebook.cancelPackageWork', 'Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.cancelPackageRecord': ['Lemma.Applications.Notebook.cancelPackageWork', 'Lemma.Applications.Notebook.pumpPackageRecord'],
        'Lemma.Applications.Notebook.cancelPackageWork': ['Lemma.Applications.Notebook.packageCancelInput', 'Lemma.Applications.Notebook.packageInputSample.acceptSample', 'Lemma.Applications.Notebook.packageToolbar', 'Lemma.Applications.Notebook.togglePackageCourse'],
        'Lemma.Applications.Notebook.drainPackageInput': ['Lemma.Applications.Notebook.packageStep.drain'],
        'Lemma.Applications.Notebook.drainPackageInput.drainStep': ['Lemma.Applications.Notebook.drainPackageInput'],
        'Lemma.Applications.Notebook.finishOpenPackageCourse': ['Lemma.Applications.Notebook.pumpOpenPackageCourse'],
        'Lemma.Applications.Notebook.finishOpenPackageCourse.restoreSelection': ['Lemma.Applications.Notebook.finishOpenPackageCourse'],
        'Lemma.Applications.Notebook.mainPackageClosureBulk': [],
        'Lemma.Applications.Notebook.openPackageCourse': ['Lemma.Applications.Notebook.togglePackageCourse'],
        'Lemma.Applications.Notebook.packageAllocateStep': ['Lemma.Applications.Notebook.allocatePackage'],
        'Lemma.Applications.Notebook.packageBindingScratch': ['Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Applications.Notebook.stagePackagePress.stage'],
        'Lemma.Applications.Notebook.packageBusy': ['Lemma.Applications.Notebook.packageStep'],
        'Lemma.Applications.Notebook.packageBusy.done': ['Lemma.Applications.Notebook.packageBusy'],
        'Lemma.Applications.Notebook.packageBytes': ['Lemma.Applications.Notebook.packageAllocateStep', 'Lemma.Applications.Notebook.packageConfigureStep', 'Lemma.Applications.Notebook.packageControlPress', 'Lemma.Applications.Notebook.pumpPackageRead', 'Lemma.Applications.Notebook.renderPackageText', 'Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Applications.Notebook.stagePackagePress.stage'],
        'Lemma.Applications.Notebook.packageCancelInput': ['Lemma.Applications.Notebook.drainPackageInput.drainStep', 'Lemma.Applications.Notebook.packageInputSample', 'Lemma.Applications.Notebook.packageStep'],
        'Lemma.Applications.Notebook.packageCloseState': ['Lemma.Applications.Notebook.packageToolbar', 'Lemma.Applications.Notebook.togglePackageCourse'],
        'Lemma.Applications.Notebook.packageConfigureStep': ['Lemma.Applications.Notebook.beginPackageRead'],
        'Lemma.Applications.Notebook.packageContext': ['Lemma.Applications.Notebook.beginPackageRead', 'Lemma.Applications.Notebook.cancelPackageRead', 'Lemma.Applications.Notebook.packageBindingScratch', 'Lemma.Applications.Notebook.packageConfigureStep', 'Lemma.Applications.Notebook.packageIncoming', 'Lemma.Applications.Notebook.packageOutgoing', 'Lemma.Applications.Notebook.packageReadEOF', 'Lemma.Applications.Notebook.packageRecord', 'Lemma.Applications.Notebook.packageState', 'Lemma.Applications.Notebook.packageSubmitted', 'Lemma.Applications.Notebook.pumpPackageRead'],
        'Lemma.Applications.Notebook.packageControlByte': ['Lemma.Applications.Notebook.packageControlStep', 'Lemma.Applications.Notebook.packageIdentityStep'],
        'Lemma.Applications.Notebook.packageControlCharacter': ['Lemma.Applications.Notebook.packageControlStep'],
        'Lemma.Applications.Notebook.packageControlPress': ['Lemma.Applications.Notebook.packageInputSample.acceptSample'],
        'Lemma.Applications.Notebook.packageControlStep': ['Lemma.Applications.Notebook.renderPackageControls'],
        'Lemma.Applications.Notebook.packageControlTile': ['Lemma.Applications.Notebook.renderPackageControls'],
        'Lemma.Applications.Notebook.packageCourseError': ['Lemma.Applications.Notebook.finishOpenPackageCourse', 'Lemma.Applications.Notebook.openPackageCourse', 'Lemma.Applications.Notebook.pumpOpenPackageCourse', 'Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.packageCoursePress': ['Lemma.Applications.Notebook.packageInputSample.acceptSample'],
        'Lemma.Applications.Notebook.packageDocumentStage': ['Lemma.Applications.Notebook.pumpOpenPackageCourse', 'Lemma.Applications.Notebook.stagePackageCompletion', 'Lemma.Applications.Notebook.stagePackagePress.stage'],
        'Lemma.Applications.Notebook.packageGet': ['Lemma.Applications.Notebook.cancelPackageRead', 'Lemma.Applications.Notebook.cancelPackageWork', 'Lemma.Applications.Notebook.packageBusy', 'Lemma.Applications.Notebook.packageControlPress', 'Lemma.Applications.Notebook.packageReadEOF', 'Lemma.Applications.Notebook.pumpOpenPackageCourse', 'Lemma.Applications.Notebook.pumpPackageRead', 'Lemma.Applications.Notebook.pumpPackageRead.finish', 'Lemma.Applications.Notebook.pumpPackageWork', 'Lemma.Applications.Notebook.renderPackageControls', 'Lemma.Applications.Notebook.renderPackageText', 'Lemma.Applications.Notebook.stagePackageCompletion', 'Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Applications.Notebook.stagePackagePress.stage'],
        'Lemma.Applications.Notebook.packageGlyphs': ['Lemma.Applications.Notebook.renderPackageText'],
        'Lemma.Applications.Notebook.packageHex': ['Lemma.Applications.Notebook.packageControlCharacter', 'Lemma.Applications.Notebook.packageIdentityCharacter'],
        'Lemma.Applications.Notebook.packageIdentityCharacter': ['Lemma.Applications.Notebook.packageIdentityStep'],
        'Lemma.Applications.Notebook.packageIdentityStep': ['Lemma.Applications.Notebook.renderPackageIdentity'],
        'Lemma.Applications.Notebook.packageIncoming': ['Lemma.Applications.Notebook.cancelPackageRead', 'Lemma.Applications.Notebook.cancelPackageRecord', 'Lemma.Applications.Notebook.packageConfigureStep', 'Lemma.Applications.Notebook.packageReadEOF', 'Lemma.Applications.Notebook.packageReadFloor', 'Lemma.Applications.Notebook.pollPackageRecordPiece'],
        'Lemma.Applications.Notebook.packageInputSample': ['Lemma.Applications.Notebook.drainPackageInput.drainStep', 'Lemma.Applications.Notebook.packageStep'],
        'Lemma.Applications.Notebook.packageInputSample.acceptSample': ['Lemma.Applications.Notebook.packageInputSample'],
        'Lemma.Applications.Notebook.packageInputSample.write': ['Lemma.Applications.Notebook.packageInputSample.acceptSample'],
        'Lemma.Applications.Notebook.packageOutgoing': ['Lemma.Applications.Notebook.beginPackageRecordPiece', 'Lemma.Applications.Notebook.packageConfigureStep', 'Lemma.Applications.Notebook.packageReadEOF'],
        'Lemma.Applications.Notebook.packagePut': ['Lemma.Applications.Notebook.beginPackageArithmetic', 'Lemma.Applications.Notebook.beginPackageRead', 'Lemma.Applications.Notebook.cancelPackageRead', 'Lemma.Applications.Notebook.cancelPackageWork', 'Lemma.Applications.Notebook.finishOpenPackageCourse', 'Lemma.Applications.Notebook.finishOpenPackageCourse.restoreSelection', 'Lemma.Applications.Notebook.openPackageCourse', 'Lemma.Applications.Notebook.packageCloseState', 'Lemma.Applications.Notebook.packageControlPress', 'Lemma.Applications.Notebook.packageCourseError', 'Lemma.Applications.Notebook.packageReadComplete', 'Lemma.Applications.Notebook.packageReadEOF', 'Lemma.Applications.Notebook.packageView', 'Lemma.Applications.Notebook.publishPackageWorkspace', 'Lemma.Applications.Notebook.pumpOpenPackageCourse', 'Lemma.Applications.Notebook.pumpPackageRead.finish', 'Lemma.Applications.Notebook.pumpPackageWork', 'Lemma.Applications.Notebook.renderPackageText'],
        'Lemma.Applications.Notebook.packageReadComplete': ['Lemma.Applications.Notebook.packageReadEOF'],
        'Lemma.Applications.Notebook.packageReadEOF': ['Lemma.Applications.Notebook.pumpPackageRead'],
        'Lemma.Applications.Notebook.packageReadFloor': ['Lemma.Applications.Notebook.packageReadEOF', 'Lemma.Applications.Notebook.pumpPackageRead'],
        'Lemma.Applications.Notebook.packageRecord': ['Lemma.Applications.Notebook.recordGet', 'Lemma.Applications.Notebook.recordPut'],
        'Lemma.Applications.Notebook.packageState': ['Lemma.Applications.Notebook.packageGet', 'Lemma.Applications.Notebook.packagePut'],
        'Lemma.Applications.Notebook.packageStep': ['Lemma.Applications.Notebook.mainPackageClosureBulk'],
        'Lemma.Applications.Notebook.packageStep.drain': ['Lemma.Applications.Notebook.packageStep'],
        'Lemma.Applications.Notebook.packageSubmitted': ['Lemma.Applications.Notebook.beginPackageArithmetic', 'Lemma.Applications.Notebook.stagePackageCompletion'],
        'Lemma.Applications.Notebook.packageTileStep': ['Lemma.Applications.Notebook.renderPackageText'],
        'Lemma.Applications.Notebook.packageToolbar': ['Lemma.Applications.Notebook.packageInputSample.acceptSample'],
        'Lemma.Applications.Notebook.packageView': ['Lemma.Applications.Notebook.packageControlPress'],
        'Lemma.Applications.Notebook.packageWorkspace': ['Lemma.Applications.Notebook.adoptPackageStep', 'Lemma.Applications.Notebook.adoptPackageWorkspace', 'Lemma.Applications.Notebook.beginPackageArithmetic', 'Lemma.Applications.Notebook.finishOpenPackageCourse', 'Lemma.Applications.Notebook.finishOpenPackageCourse.restoreSelection', 'Lemma.Applications.Notebook.stagePackageCompletion', 'Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Applications.Notebook.stagePackagePress.stage'],
        'Lemma.Applications.Notebook.pollPackageRecordPiece': ['Lemma.Applications.Notebook.pumpPackageRecord'],
        'Lemma.Applications.Notebook.publishPackageWorkspace': ['Lemma.Applications.Notebook.packageControlPress', 'Lemma.Applications.Notebook.packageCoursePress', 'Lemma.Applications.Notebook.pumpPackageArithmetic'],
        'Lemma.Applications.Notebook.pumpOpenPackageCourse': ['Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.pumpPackageArithmetic': ['Lemma.Applications.Notebook.packageStep'],
        'Lemma.Applications.Notebook.pumpPackageRead': ['Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.pumpPackageRead.finish': ['Lemma.Applications.Notebook.pumpPackageRead'],
        'Lemma.Applications.Notebook.pumpPackageRecord': ['Lemma.Applications.Notebook.pumpOpenPackageCourse'],
        'Lemma.Applications.Notebook.pumpPackageWork': ['Lemma.Applications.Notebook.packageStep'],
        'Lemma.Applications.Notebook.recordGet': ['Lemma.Applications.Notebook.beginPackageRecordPiece', 'Lemma.Applications.Notebook.cancelPackageRecord', 'Lemma.Applications.Notebook.pollPackageRecordPiece', 'Lemma.Applications.Notebook.pumpOpenPackageCourse', 'Lemma.Applications.Notebook.pumpPackageRecord', 'Lemma.Applications.Notebook.startPackageRecord'],
        'Lemma.Applications.Notebook.recordPut': ['Lemma.Applications.Notebook.beginPackageRecordPiece', 'Lemma.Applications.Notebook.cancelPackageRecord', 'Lemma.Applications.Notebook.pollPackageRecordPiece', 'Lemma.Applications.Notebook.startPackageRecord', 'Lemma.Applications.Notebook.stopPackageRecord'],
        'Lemma.Applications.Notebook.renderPackageControls': ['Lemma.Applications.Notebook.packageControlPress', 'Lemma.Applications.Notebook.packageView', 'Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.renderPackageIdentity': ['Lemma.Applications.Notebook.renderPackageControls'],
        'Lemma.Applications.Notebook.renderPackageText': ['Lemma.Applications.Notebook.packageView', 'Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.savePackageWorkspace': ['Lemma.Applications.Notebook.finishOpenPackageCourse', 'Lemma.Applications.Notebook.publishPackageWorkspace'],
        'Lemma.Applications.Notebook.stagePackageCompletion': ['Lemma.Applications.Notebook.pumpPackageArithmetic'],
        'Lemma.Applications.Notebook.stagePackageExercise': ['Lemma.Applications.Notebook.packageControlPress'],
        'Lemma.Applications.Notebook.stagePackagePress': ['Lemma.Applications.Notebook.packageCoursePress'],
        'Lemma.Applications.Notebook.stagePackagePress.stage': ['Lemma.Applications.Notebook.stagePackagePress'],
        'Lemma.Applications.Notebook.startPackageRecord': ['Lemma.Applications.Notebook.openPackageCourse', 'Lemma.Applications.Notebook.pumpOpenPackageCourse'],
        'Lemma.Applications.Notebook.stopPackageRecord': ['Lemma.Applications.Notebook.beginPackageRecordPiece', 'Lemma.Applications.Notebook.cancelPackageRecord', 'Lemma.Applications.Notebook.pollPackageRecordPiece', 'Lemma.Applications.Notebook.pumpPackageRecord'],
        'Lemma.Applications.Notebook.togglePackageCourse': ['Lemma.Applications.Notebook.packageInputSample.acceptSample'],
        'Lemma.Courses.PackageBinding.applicable': ['Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.validateAttempt'],
        'Lemma.Courses.PackageBinding.bytes': ['Lemma.Courses.PackageBinding.capture', 'Lemma.Courses.PackageBinding.validate', 'Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.validateAttempt'],
        'Lemma.Courses.PackageBinding.capture': ['Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Courses.PackageWorkspace.captureSelection'],
        'Lemma.Courses.PackageBinding.captureField': ['Lemma.Courses.PackageBinding.capture'],
        'Lemma.Courses.PackageBinding.fieldsValid': ['Lemma.Courses.PackageBinding.validate'],
        'Lemma.Courses.PackageBinding.magic': ['Lemma.Courses.PackageBinding.capture', 'Lemma.Courses.PackageBinding.validate', 'Lemma.Courses.PackageWorkspace.copyBinding'],
        'Lemma.Courses.PackageBinding.put': ['Lemma.Courses.PackageBinding.capture', 'Lemma.Courses.PackageBinding.captureField'],
        'Lemma.Courses.PackageBinding.spanValid': ['Lemma.Courses.PackageBinding.fieldsValid'],
        'Lemma.Courses.PackageBinding.validate': ['Lemma.Courses.PackageBinding.applicable', 'Lemma.Courses.PackageWorkspace.validateSelection'],
        'Lemma.Courses.PackageBinding.version': ['Lemma.Courses.PackageBinding.capture', 'Lemma.Courses.PackageBinding.validate'],
        'Lemma.Courses.PackageBinding.word': ['Lemma.Courses.PackageBinding.applicable', 'Lemma.Courses.PackageBinding.capture', 'Lemma.Courses.PackageBinding.captureField', 'Lemma.Courses.PackageBinding.fieldsValid', 'Lemma.Courses.PackageBinding.validate'],
        'Lemma.Courses.PackageFormat.crcBit': ['Lemma.Courses.PackageFormat.crcByte'],
        'Lemma.Courses.PackageFormat.crcByte': ['Lemma.Courses.PackageTarget.crcStep'],
        'Lemma.Courses.PackageFormat.entryBytes': ['Lemma.Applications.Notebook.packageControlPress', 'Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageTarget.select', 'Lemma.Courses.PackageTarget.validate', 'Lemma.Courses.PackageTarget.validateEntry'],
        'Lemma.Courses.PackageFormat.headerBytes': ['Lemma.Applications.Notebook.packageControlPress', 'Lemma.Courses.PackageReader.accept', 'Lemma.Courses.PackageReader.beginPiece', 'Lemma.Courses.PackageReader.configuration', 'Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageTarget.select', 'Lemma.Courses.PackageTarget.validate', 'Lemma.Courses.PackageTarget.validateEntry'],
        'Lemma.Courses.PackageFormat.integrityFailure': ['Lemma.Courses.PackageTarget.validate', 'Lemma.Courses.PackageTarget.validateBody'],
        'Lemma.Courses.PackageFormat.magic': ['Lemma.Courses.PackageTarget.validate'],
        'Lemma.Courses.PackageFormat.malformed': ['Lemma.Courses.PackageBinding.capture', 'Lemma.Courses.PackageBinding.fieldsValid', 'Lemma.Courses.PackageBinding.validate', 'Lemma.Courses.PackageFormat.referenceStatus', 'Lemma.Courses.PackageReader.accept', 'Lemma.Courses.PackageReader.beginPiece', 'Lemma.Courses.PackageReader.cancel', 'Lemma.Courses.PackageReader.configuration', 'Lemma.Courses.PackageReader.finish', 'Lemma.Courses.PackageReader.pollPiece', 'Lemma.Courses.PackageReader.start', 'Lemma.Courses.PackageReader.step', 'Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader', 'Lemma.Courses.PackageRender.render', 'Lemma.Courses.PackageRender.renderHeaderSelected', 'Lemma.Courses.PackageRender.renderSelected', 'Lemma.Courses.PackageTarget.reservedStep', 'Lemma.Courses.PackageTarget.validate', 'Lemma.Courses.PackageTarget.validateBody', 'Lemma.Courses.PackageTarget.validateEntry', 'Lemma.Courses.PackageTarget.validateSpan', 'Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.create', 'Lemma.Courses.PackageWorkspace.equalEventsStep', 'Lemma.Courses.PackageWorkspace.equalHistoryStep', 'Lemma.Courses.PackageWorkspace.equalSubmissionStep', 'Lemma.Courses.PackageWorkspace.equalWordsStep', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown', 'Lemma.Courses.PackageWorkspace.stageRefresh', 'Lemma.Courses.PackageWorkspace.stageUnknownSelection', 'Lemma.Courses.PackageWorkspace.transitionBase', 'Lemma.Courses.PackageWorkspace.validate', 'Lemma.Courses.PackageWorkspace.validateAttempt', 'Lemma.Courses.PackageWorkspace.validateSelection', 'Lemma.Courses.PackageWorkspace.zeroCheck'],
        'Lemma.Courses.PackageFormat.maximumBytes': ['Lemma.Courses.PackageBinding.spanValid', 'Lemma.Courses.PackageReader.beginPiece', 'Lemma.Courses.PackageReader.configuration', 'Lemma.Courses.PackageReader.pollPiece', 'Lemma.Courses.PackageTarget.validate'],
        'Lemma.Courses.PackageFormat.maximumEdition': ['Lemma.Courses.PackageBinding.fieldsValid', 'Lemma.Courses.PackageReader.configuration', 'Lemma.Courses.PackageTarget.validate'],
        'Lemma.Courses.PackageFormat.maximumEntries': ['Lemma.Courses.PackageBinding.fieldsValid', 'Lemma.Courses.PackageFormat.prerequisitesValid', 'Lemma.Courses.PackageTarget.validate'],
        'Lemma.Courses.PackageFormat.maximumFieldBytes': ['Lemma.Courses.PackageBinding.spanValid', 'Lemma.Courses.PackageTarget.validateSpan'],
        'Lemma.Courses.PackageFormat.maximumIdentity': ['Lemma.Courses.PackageBinding.fieldsValid', 'Lemma.Courses.PackageReader.configuration', 'Lemma.Courses.PackageTarget.validate'],
        'Lemma.Courses.PackageFormat.maximumTextBytes': ['Lemma.Courses.PackageTarget.validate'],
        'Lemma.Courses.PackageFormat.object': ['Lemma.Applications.Notebook.packageReadEOF', 'Lemma.Courses.PackageReader.issue', 'Lemma.Courses.PackageReader.pollPiece'],
        'Lemma.Courses.PackageFormat.prerequisitesValid': ['Lemma.Courses.PackageTarget.validateEntry'],
        'Lemma.Courses.PackageFormat.referenceStatus': ['Lemma.Courses.PackageBinding.fieldsValid', 'Lemma.Courses.PackageTarget.validateEntry'],
        'Lemma.Courses.PackageFormat.resourceLimit': ['Lemma.Courses.PackageBinding.capture', 'Lemma.Courses.PackageBinding.fieldsValid', 'Lemma.Courses.PackageReader.accept', 'Lemma.Courses.PackageReader.beginPiece', 'Lemma.Courses.PackageReader.configuration', 'Lemma.Courses.PackageReader.pollPiece', 'Lemma.Courses.PackageRender.render', 'Lemma.Courses.PackageRender.renderHeaderSelected', 'Lemma.Courses.PackageRender.renderSelected', 'Lemma.Courses.PackageTarget.validate', 'Lemma.Courses.PackageTarget.validateSpan', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown'],
        'Lemma.Courses.PackageFormat.selectionAbsent': ['Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader', 'Lemma.Courses.PackageTarget.select', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted'],
        'Lemma.Courses.PackageFormat.spanLength': ['Lemma.Applications.Notebook.packageControlPress', 'Lemma.Courses.PackageBinding.spanValid', 'Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader', 'Lemma.Courses.PackageTarget.validateSpan'],
        'Lemma.Courses.PackageFormat.spanOffset': ['Lemma.Courses.PackageBinding.spanValid', 'Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader', 'Lemma.Courses.PackageTarget.validateSpan'],
        'Lemma.Courses.PackageFormat.textByteValid': ['Lemma.Courses.PackageTarget.textStep'],
        'Lemma.Courses.PackageFormat.unsupported': ['Lemma.Courses.PackageBinding.capture', 'Lemma.Courses.PackageBinding.fieldsValid', 'Lemma.Courses.PackageBinding.validate', 'Lemma.Courses.PackageFormat.referenceStatus', 'Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader', 'Lemma.Courses.PackageTarget.textStep', 'Lemma.Courses.PackageTarget.validate', 'Lemma.Courses.PackageWorkspace.create', 'Lemma.Courses.PackageWorkspace.transitionBase', 'Lemma.Courses.PackageWorkspace.validate'],
        'Lemma.Courses.PackageFormat.version': ['Lemma.Courses.PackageTarget.validate'],
        'Lemma.Courses.PackageReader.accept': ['Lemma.Courses.PackageReader.pollPiece'],
        'Lemma.Courses.PackageReader.beginPiece': ['Lemma.Courses.PackageReader.step'],
        'Lemma.Courses.PackageReader.cancel': ['Lemma.Applications.Notebook.cancelPackageRead'],
        'Lemma.Courses.PackageReader.clearStep': ['Lemma.Courses.PackageReader.start'],
        'Lemma.Courses.PackageReader.configuration': ['Lemma.Courses.PackageReader.cancel', 'Lemma.Courses.PackageReader.finish', 'Lemma.Courses.PackageReader.start', 'Lemma.Courses.PackageReader.step'],
        'Lemma.Courses.PackageReader.contextBytes': ['Lemma.Courses.PackageReader.configuration', 'Lemma.Courses.PackageReader.spans'],
        'Lemma.Courses.PackageReader.field': ['Lemma.Courses.PackageReader.accept', 'Lemma.Courses.PackageReader.beginPiece', 'Lemma.Courses.PackageReader.cancel', 'Lemma.Courses.PackageReader.configuration', 'Lemma.Courses.PackageReader.finish', 'Lemma.Courses.PackageReader.issue', 'Lemma.Courses.PackageReader.pollPiece', 'Lemma.Courses.PackageReader.start', 'Lemma.Courses.PackageReader.step'],
        'Lemma.Courses.PackageReader.finish': ['Lemma.Applications.Notebook.pumpPackageRead'],
        'Lemma.Courses.PackageReader.issue': ['Lemma.Courses.PackageReader.beginPiece'],
        'Lemma.Courses.PackageReader.maximumRequests': ['Lemma.Courses.PackageReader.beginPiece', 'Lemma.Courses.PackageReader.configuration'],
        'Lemma.Courses.PackageReader.minimum': ['Lemma.Courses.PackageReader.beginPiece'],
        'Lemma.Courses.PackageReader.pollPiece': ['Lemma.Courses.PackageReader.step'],
        'Lemma.Courses.PackageReader.put': ['Lemma.Courses.PackageReader.accept', 'Lemma.Courses.PackageReader.cancel', 'Lemma.Courses.PackageReader.clearStep', 'Lemma.Courses.PackageReader.finish', 'Lemma.Courses.PackageReader.issue', 'Lemma.Courses.PackageReader.pollPiece', 'Lemma.Courses.PackageReader.start', 'Lemma.Courses.PackageReader.stop'],
        'Lemma.Courses.PackageReader.separate': ['Lemma.Courses.PackageReader.spans'],
        'Lemma.Courses.PackageReader.spans': ['Lemma.Courses.PackageReader.configuration'],
        'Lemma.Courses.PackageReader.start': ['Lemma.Applications.Notebook.beginPackageRead'],
        'Lemma.Courses.PackageReader.step': ['Lemma.Applications.Notebook.pumpPackageRead'],
        'Lemma.Courses.PackageReader.stop': ['Lemma.Courses.PackageReader.accept', 'Lemma.Courses.PackageReader.beginPiece', 'Lemma.Courses.PackageReader.cancel', 'Lemma.Courses.PackageReader.finish', 'Lemma.Courses.PackageReader.issue', 'Lemma.Courses.PackageReader.pollPiece'],
        'Lemma.Courses.PackageRender.cacheBytes': ['Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader', 'Lemma.Courses.PackageRender.render', 'Lemma.Courses.PackageRender.renderHeaderSelected', 'Lemma.Courses.PackageRender.renderSelected'],
        'Lemma.Courses.PackageRender.clearStep': ['Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader'],
        'Lemma.Courses.PackageRender.columns': ['Lemma.Courses.PackageRender.renderStep', 'Lemma.Courses.PackageRender.textStep'],
        'Lemma.Courses.PackageRender.glyph': ['Lemma.Applications.Notebook.packageControlStep', 'Lemma.Applications.Notebook.packageIdentityStep', 'Lemma.Courses.PackageRender.textStep'],
        'Lemma.Courses.PackageRender.pair': ['Lemma.Courses.PackageRender.panelWord'],
        'Lemma.Courses.PackageRender.panelWord': ['Lemma.Applications.Notebook.packageControlStep', 'Lemma.Applications.Notebook.packageIdentityStep', 'Lemma.Courses.PackageRender.renderStep'],
        'Lemma.Courses.PackageRender.pixel': ['Lemma.Courses.PackageRender.pair'],
        'Lemma.Courses.PackageRender.prepare': ['Lemma.Courses.PackageRender.renderSelected'],
        'Lemma.Courses.PackageRender.prepareHeader': ['Lemma.Courses.PackageRender.renderHeaderSelected'],
        'Lemma.Courses.PackageRender.render': ['Lemma.Courses.PackageRender.renderHeaderSelected', 'Lemma.Courses.PackageRender.renderSelected'],
        'Lemma.Courses.PackageRender.renderByteStep': ['Lemma.Courses.PackageRender.renderStep'],
        'Lemma.Courses.PackageRender.renderHeaderSelected': ['Lemma.Applications.Notebook.renderPackageText'],
        'Lemma.Courses.PackageRender.renderSelected': ['Lemma.Applications.Notebook.renderPackageText'],
        'Lemma.Courses.PackageRender.renderStep': ['Lemma.Courses.PackageRender.render'],
        'Lemma.Courses.PackageRender.rows': ['Lemma.Courses.PackageRender.textStep'],
        'Lemma.Courses.PackageRender.separate': ['Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader', 'Lemma.Courses.PackageRender.render', 'Lemma.Courses.PackageRender.renderHeaderSelected', 'Lemma.Courses.PackageRender.renderSelected'],
        'Lemma.Courses.PackageRender.textStep': ['Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader'],
        'Lemma.Courses.PackageTarget.crcStep': ['Lemma.Courses.PackageTarget.validateBody'],
        'Lemma.Courses.PackageTarget.entryStep': ['Lemma.Courses.PackageTarget.validateBody'],
        'Lemma.Courses.PackageTarget.entryTextStep': ['Lemma.Courses.PackageTarget.validateEntry'],
        'Lemma.Courses.PackageTarget.headerTextStep': ['Lemma.Courses.PackageTarget.validateBody'],
        'Lemma.Courses.PackageTarget.reservedStep': ['Lemma.Courses.PackageTarget.validateEntry'],
        'Lemma.Courses.PackageTarget.select': ['Lemma.Courses.PackageBinding.capture'],
        'Lemma.Courses.PackageTarget.textStep': ['Lemma.Courses.PackageTarget.validateSpan'],
        'Lemma.Courses.PackageTarget.validate': ['Lemma.Courses.PackageReader.finish', 'Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader', 'Lemma.Courses.PackageTarget.select'],
        'Lemma.Courses.PackageTarget.validateBody': ['Lemma.Courses.PackageTarget.validate'],
        'Lemma.Courses.PackageTarget.validateEntry': ['Lemma.Courses.PackageTarget.entryStep'],
        'Lemma.Courses.PackageTarget.validateSpan': ['Lemma.Courses.PackageTarget.entryTextStep', 'Lemma.Courses.PackageTarget.headerTextStep'],
        'Lemma.Courses.PackageTarget.word': ['Lemma.Courses.PackageTarget.entryTextStep', 'Lemma.Courses.PackageTarget.headerTextStep', 'Lemma.Courses.PackageTarget.reservedStep', 'Lemma.Courses.PackageTarget.validate', 'Lemma.Courses.PackageTarget.validateEntry'],
        'Lemma.Courses.PackageWorkspace.attempts': ['Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.validateAttempt'],
        'Lemma.Courses.PackageWorkspace.bytes': ['Lemma.Applications.Notebook.openPackageCourse', 'Lemma.Applications.Notebook.savePackageWorkspace', 'Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.create', 'Lemma.Courses.PackageWorkspace.shape', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.transitionBase', 'Lemma.Courses.PackageWorkspace.validate'],
        'Lemma.Courses.PackageWorkspace.captureSelection': ['Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Applications.Notebook.stagePackagePress.stage'],
        'Lemma.Courses.PackageWorkspace.cloneContents': ['Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown', 'Lemma.Courses.PackageWorkspace.stageRefresh', 'Lemma.Courses.PackageWorkspace.stageUnknownSelection'],
        'Lemma.Courses.PackageWorkspace.copyBinding': ['Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted'],
        'Lemma.Courses.PackageWorkspace.copyBindingStep': ['Lemma.Courses.PackageWorkspace.cloneContents', 'Lemma.Courses.PackageWorkspace.copyBinding'],
        'Lemma.Courses.PackageWorkspace.create': ['Lemma.Applications.Notebook.pumpOpenPackageCourse'],
        'Lemma.Courses.PackageWorkspace.equalEventsStep': ['Lemma.Courses.PackageWorkspace.transitionBase'],
        'Lemma.Courses.PackageWorkspace.equalHistoryStep': ['Lemma.Courses.PackageWorkspace.transitionBase'],
        'Lemma.Courses.PackageWorkspace.equalSubmissionStep': ['Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown'],
        'Lemma.Courses.PackageWorkspace.equalWordsStep': ['Lemma.Courses.PackageWorkspace.stageCompleted'],
        'Lemma.Courses.PackageWorkspace.field': ['Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.copyBindingStep', 'Lemma.Courses.PackageWorkspace.equalEventsStep', 'Lemma.Courses.PackageWorkspace.equalHistoryStep', 'Lemma.Courses.PackageWorkspace.equalSubmissionStep', 'Lemma.Courses.PackageWorkspace.equalWordsStep', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown', 'Lemma.Courses.PackageWorkspace.stageUnknownSelection', 'Lemma.Courses.PackageWorkspace.transitionBase', 'Lemma.Courses.PackageWorkspace.validate', 'Lemma.Courses.PackageWorkspace.validateAttempt', 'Lemma.Courses.PackageWorkspace.validateOwned', 'Lemma.Courses.PackageWorkspace.validateSelection', 'Lemma.Courses.PackageWorkspace.zeroCheck'],
        'Lemma.Courses.PackageWorkspace.inner': ['Lemma.Applications.Notebook.adoptPackageWorkspace', 'Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.cloneContents', 'Lemma.Courses.PackageWorkspace.create', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown', 'Lemma.Courses.PackageWorkspace.transitionBase', 'Lemma.Courses.PackageWorkspace.validate', 'Lemma.Courses.PackageWorkspace.validateAttempt', 'Lemma.Courses.PackageWorkspace.validateSelection'],
        'Lemma.Courses.PackageWorkspace.magic': ['Lemma.Applications.Notebook.adoptPackageWorkspace', 'Lemma.Courses.PackageWorkspace.create', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown', 'Lemma.Courses.PackageWorkspace.stageRefresh', 'Lemma.Courses.PackageWorkspace.stageUnknownSelection', 'Lemma.Courses.PackageWorkspace.validate'],
        'Lemma.Courses.PackageWorkspace.object': ['Lemma.Applications.Notebook.openPackageCourse', 'Lemma.Applications.Notebook.savePackageWorkspace'],
        'Lemma.Courses.PackageWorkspace.put': ['Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.cloneContents', 'Lemma.Courses.PackageWorkspace.copyBinding', 'Lemma.Courses.PackageWorkspace.copyBindingStep', 'Lemma.Courses.PackageWorkspace.create', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown', 'Lemma.Courses.PackageWorkspace.stageRefresh', 'Lemma.Courses.PackageWorkspace.stageUnknownSelection', 'Lemma.Courses.PackageWorkspace.zeroStep'],
        'Lemma.Courses.PackageWorkspace.selection': ['Lemma.Applications.Notebook.finishOpenPackageCourse.restoreSelection', 'Lemma.Applications.Notebook.stagePackagePress.stage', 'Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageUnknownSelection', 'Lemma.Courses.PackageWorkspace.validateSelection'],
        'Lemma.Courses.PackageWorkspace.separate': ['Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.transitionBase'],
        'Lemma.Courses.PackageWorkspace.shape': ['Lemma.Courses.PackageWorkspace.create', 'Lemma.Courses.PackageWorkspace.validate'],
        'Lemma.Courses.PackageWorkspace.snapshotSelection': ['Lemma.Applications.Notebook.beginPackageArithmetic'],
        'Lemma.Courses.PackageWorkspace.stageCompleted': ['Lemma.Applications.Notebook.stagePackageCompletion'],
        'Lemma.Courses.PackageWorkspace.stageCompletedUnknown': ['Lemma.Applications.Notebook.stagePackageCompletion'],
        'Lemma.Courses.PackageWorkspace.stageRefresh': ['Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Applications.Notebook.stagePackagePress.stage'],
        'Lemma.Courses.PackageWorkspace.stageUnknownSelection': ['Lemma.Applications.Notebook.stagePackagePress.stage'],
        'Lemma.Courses.PackageWorkspace.transitionBase': ['Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown', 'Lemma.Courses.PackageWorkspace.stageRefresh', 'Lemma.Courses.PackageWorkspace.stageUnknownSelection'],
        'Lemma.Courses.PackageWorkspace.validate': ['Lemma.Applications.Notebook.adoptPackageWorkspace', 'Lemma.Applications.Notebook.beginPackageArithmetic', 'Lemma.Applications.Notebook.pumpOpenPackageCourse', 'Lemma.Applications.Notebook.savePackageWorkspace', 'Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Courses.PackageWorkspace.validateOwned'],
        'Lemma.Courses.PackageWorkspace.validateAttempt': ['Lemma.Courses.PackageWorkspace.validate'],
        'Lemma.Courses.PackageWorkspace.validateOwned': ['Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.transitionBase'],
        'Lemma.Courses.PackageWorkspace.validateSelection': ['Lemma.Courses.PackageWorkspace.validate'],
        'Lemma.Courses.PackageWorkspace.version': ['Lemma.Courses.PackageWorkspace.create', 'Lemma.Courses.PackageWorkspace.validate'],
        'Lemma.Courses.PackageWorkspace.zeroCheck': ['Lemma.Courses.PackageWorkspace.validateAttempt', 'Lemma.Courses.PackageWorkspace.validateSelection'],
        'Lemma.Courses.PackageWorkspace.zeroStep': ['Lemma.Courses.PackageWorkspace.create', 'Lemma.Courses.PackageWorkspace.stageUnknownSelection'],
    },
    'post': {
        'Lemma.Applications.Notebook.adoptPackageStep': ['Lemma.Applications.Notebook.adoptPackageWorkspace'],
        'Lemma.Applications.Notebook.adoptPackageWorkspace': ['Lemma.Applications.Notebook.finishOpenPackageCourse', 'Lemma.Applications.Notebook.publishPackageWorkspace'],
        'Lemma.Applications.Notebook.allocatePackage': ['Lemma.Applications.Notebook.beginPackageRead', 'Lemma.Applications.Notebook.openPackageCourse'],
        'Lemma.Applications.Notebook.beginPackageArithmetic': ['Lemma.Applications.Notebook.packageCoursePress'],
        'Lemma.Applications.Notebook.beginPackageRead': ['Lemma.Applications.Notebook.packageControlPress', 'Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.beginPackageRecordPiece': ['Lemma.Applications.Notebook.pumpPackageRecord'],
        'Lemma.Applications.Notebook.cancelPackageRead': ['Lemma.Applications.Notebook.cancelPackageWork', 'Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.cancelPackageRecord': ['Lemma.Applications.Notebook.cancelPackageWork', 'Lemma.Applications.Notebook.pumpPackageRecord'],
        'Lemma.Applications.Notebook.cancelPackageWork': ['Lemma.Applications.Notebook.packageCancelInput', 'Lemma.Applications.Notebook.packageInputSample.acceptSample', 'Lemma.Applications.Notebook.packageToolbar', 'Lemma.Applications.Notebook.togglePackageCourse'],
        'Lemma.Applications.Notebook.drainPackageInput': ['Lemma.Applications.Notebook.packageStep.drain'],
        'Lemma.Applications.Notebook.drainPackageInput.drainStep': ['Lemma.Applications.Notebook.drainPackageInput'],
        'Lemma.Applications.Notebook.finishOpenPackageCourse': ['Lemma.Applications.Notebook.pumpOpenPackageCourse'],
        'Lemma.Applications.Notebook.finishOpenPackageCourse.restoreSelection': ['Lemma.Applications.Notebook.finishOpenPackageCourse'],
        'Lemma.Applications.Notebook.mainPackageClosureBulk': [],
        'Lemma.Applications.Notebook.openPackageCourse': ['Lemma.Applications.Notebook.togglePackageCourse'],
        'Lemma.Applications.Notebook.packageAllocateStep': ['Lemma.Applications.Notebook.allocatePackage'],
        'Lemma.Applications.Notebook.packageBindingScratch': [],
        'Lemma.Applications.Notebook.packageBusy': ['Lemma.Applications.Notebook.packageStep'],
        'Lemma.Applications.Notebook.packageBusy.done': ['Lemma.Applications.Notebook.packageBusy'],
        'Lemma.Applications.Notebook.packageBytes': [],
        'Lemma.Applications.Notebook.packageCancelInput': ['Lemma.Applications.Notebook.drainPackageInput.drainStep', 'Lemma.Applications.Notebook.packageInputSample', 'Lemma.Applications.Notebook.packageStep'],
        'Lemma.Applications.Notebook.packageCloseState': ['Lemma.Applications.Notebook.packageToolbar', 'Lemma.Applications.Notebook.togglePackageCourse'],
        'Lemma.Applications.Notebook.packageConfigureStep': ['Lemma.Applications.Notebook.beginPackageRead'],
        'Lemma.Applications.Notebook.packageContext': [],
        'Lemma.Applications.Notebook.packageControlByte': ['Lemma.Applications.Notebook.packageControlStep', 'Lemma.Applications.Notebook.packageIdentityStep'],
        'Lemma.Applications.Notebook.packageControlCharacter': ['Lemma.Applications.Notebook.packageControlStep'],
        'Lemma.Applications.Notebook.packageControlPress': ['Lemma.Applications.Notebook.packageInputSample.acceptSample'],
        'Lemma.Applications.Notebook.packageControlStep': ['Lemma.Applications.Notebook.renderPackageControls'],
        'Lemma.Applications.Notebook.packageControlTile': ['Lemma.Applications.Notebook.renderPackageControls'],
        'Lemma.Applications.Notebook.packageCourseError': ['Lemma.Applications.Notebook.finishOpenPackageCourse', 'Lemma.Applications.Notebook.openPackageCourse', 'Lemma.Applications.Notebook.pumpOpenPackageCourse', 'Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.packageCoursePress': ['Lemma.Applications.Notebook.packageInputSample.acceptSample'],
        'Lemma.Applications.Notebook.packageDocumentStage': [],
        'Lemma.Applications.Notebook.packageGet': ['Lemma.Applications.Notebook.cancelPackageRead', 'Lemma.Applications.Notebook.cancelPackageWork', 'Lemma.Applications.Notebook.packageBusy', 'Lemma.Applications.Notebook.packageControlPress', 'Lemma.Applications.Notebook.packageReadEOF', 'Lemma.Applications.Notebook.pumpOpenPackageCourse', 'Lemma.Applications.Notebook.pumpPackageRead', 'Lemma.Applications.Notebook.pumpPackageRead.finish', 'Lemma.Applications.Notebook.pumpPackageWork', 'Lemma.Applications.Notebook.renderPackageControls', 'Lemma.Applications.Notebook.renderPackageText', 'Lemma.Applications.Notebook.stagePackageCompletion', 'Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Applications.Notebook.stagePackagePress.stage'],
        'Lemma.Applications.Notebook.packageGlyphs': [],
        'Lemma.Applications.Notebook.packageHex': ['Lemma.Applications.Notebook.packageControlCharacter', 'Lemma.Applications.Notebook.packageIdentityCharacter'],
        'Lemma.Applications.Notebook.packageIdentityCharacter': ['Lemma.Applications.Notebook.packageIdentityStep'],
        'Lemma.Applications.Notebook.packageIdentityStep': ['Lemma.Applications.Notebook.renderPackageIdentity'],
        'Lemma.Applications.Notebook.packageIncoming': [],
        'Lemma.Applications.Notebook.packageInputSample': ['Lemma.Applications.Notebook.drainPackageInput.drainStep', 'Lemma.Applications.Notebook.packageStep'],
        'Lemma.Applications.Notebook.packageInputSample.acceptSample': ['Lemma.Applications.Notebook.packageInputSample'],
        'Lemma.Applications.Notebook.packageInputSample.write': ['Lemma.Applications.Notebook.packageInputSample.acceptSample'],
        'Lemma.Applications.Notebook.packageOutgoing': [],
        'Lemma.Applications.Notebook.packagePut': ['Lemma.Applications.Notebook.beginPackageArithmetic', 'Lemma.Applications.Notebook.beginPackageRead', 'Lemma.Applications.Notebook.cancelPackageRead', 'Lemma.Applications.Notebook.cancelPackageWork', 'Lemma.Applications.Notebook.finishOpenPackageCourse', 'Lemma.Applications.Notebook.finishOpenPackageCourse.restoreSelection', 'Lemma.Applications.Notebook.openPackageCourse', 'Lemma.Applications.Notebook.packageCloseState', 'Lemma.Applications.Notebook.packageControlPress', 'Lemma.Applications.Notebook.packageCourseError', 'Lemma.Applications.Notebook.packageReadComplete', 'Lemma.Applications.Notebook.packageReadEOF', 'Lemma.Applications.Notebook.packageView', 'Lemma.Applications.Notebook.publishPackageWorkspace', 'Lemma.Applications.Notebook.pumpOpenPackageCourse', 'Lemma.Applications.Notebook.pumpPackageRead.finish', 'Lemma.Applications.Notebook.pumpPackageWork', 'Lemma.Applications.Notebook.renderPackageText'],
        'Lemma.Applications.Notebook.packageReadComplete': ['Lemma.Applications.Notebook.packageReadEOF'],
        'Lemma.Applications.Notebook.packageReadEOF': ['Lemma.Applications.Notebook.pumpPackageRead'],
        'Lemma.Applications.Notebook.packageReadFloor': ['Lemma.Applications.Notebook.packageReadEOF', 'Lemma.Applications.Notebook.pumpPackageRead'],
        'Lemma.Applications.Notebook.packageRecord': [],
        'Lemma.Applications.Notebook.packageState': [],
        'Lemma.Applications.Notebook.packageStep': ['Lemma.Applications.Notebook.mainPackageClosureBulk'],
        'Lemma.Applications.Notebook.packageStep.drain': ['Lemma.Applications.Notebook.packageStep'],
        'Lemma.Applications.Notebook.packageSubmitted': [],
        'Lemma.Applications.Notebook.packageTileStep': ['Lemma.Applications.Notebook.renderPackageText'],
        'Lemma.Applications.Notebook.packageToolbar': ['Lemma.Applications.Notebook.packageInputSample.acceptSample'],
        'Lemma.Applications.Notebook.packageView': ['Lemma.Applications.Notebook.packageControlPress'],
        'Lemma.Applications.Notebook.packageWorkspace': [],
        'Lemma.Applications.Notebook.pollPackageRecordPiece': ['Lemma.Applications.Notebook.pumpPackageRecord'],
        'Lemma.Applications.Notebook.publishPackageWorkspace': ['Lemma.Applications.Notebook.packageControlPress', 'Lemma.Applications.Notebook.packageCoursePress', 'Lemma.Applications.Notebook.pumpPackageArithmetic'],
        'Lemma.Applications.Notebook.pumpOpenPackageCourse': ['Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.pumpPackageArithmetic': ['Lemma.Applications.Notebook.packageStep'],
        'Lemma.Applications.Notebook.pumpPackageRead': ['Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.pumpPackageRead.finish': ['Lemma.Applications.Notebook.pumpPackageRead'],
        'Lemma.Applications.Notebook.pumpPackageRecord': ['Lemma.Applications.Notebook.pumpOpenPackageCourse'],
        'Lemma.Applications.Notebook.pumpPackageWork': ['Lemma.Applications.Notebook.packageStep'],
        'Lemma.Applications.Notebook.recordGet': ['Lemma.Applications.Notebook.beginPackageRecordPiece', 'Lemma.Applications.Notebook.cancelPackageRecord', 'Lemma.Applications.Notebook.pollPackageRecordPiece', 'Lemma.Applications.Notebook.pumpOpenPackageCourse', 'Lemma.Applications.Notebook.pumpPackageRecord', 'Lemma.Applications.Notebook.startPackageRecord'],
        'Lemma.Applications.Notebook.recordPut': ['Lemma.Applications.Notebook.beginPackageRecordPiece', 'Lemma.Applications.Notebook.cancelPackageRecord', 'Lemma.Applications.Notebook.pollPackageRecordPiece', 'Lemma.Applications.Notebook.startPackageRecord', 'Lemma.Applications.Notebook.stopPackageRecord'],
        'Lemma.Applications.Notebook.renderPackageControls': ['Lemma.Applications.Notebook.packageControlPress', 'Lemma.Applications.Notebook.packageView', 'Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.renderPackageIdentity': ['Lemma.Applications.Notebook.renderPackageControls'],
        'Lemma.Applications.Notebook.renderPackageText': ['Lemma.Applications.Notebook.packageView', 'Lemma.Applications.Notebook.pumpPackageWork'],
        'Lemma.Applications.Notebook.savePackageWorkspace': ['Lemma.Applications.Notebook.finishOpenPackageCourse', 'Lemma.Applications.Notebook.publishPackageWorkspace'],
        'Lemma.Applications.Notebook.stagePackageCompletion': ['Lemma.Applications.Notebook.pumpPackageArithmetic'],
        'Lemma.Applications.Notebook.stagePackageExercise': ['Lemma.Applications.Notebook.packageControlPress'],
        'Lemma.Applications.Notebook.stagePackagePress': ['Lemma.Applications.Notebook.packageCoursePress'],
        'Lemma.Applications.Notebook.stagePackagePress.stage': ['Lemma.Applications.Notebook.stagePackagePress'],
        'Lemma.Applications.Notebook.startPackageRecord': ['Lemma.Applications.Notebook.openPackageCourse', 'Lemma.Applications.Notebook.pumpOpenPackageCourse'],
        'Lemma.Applications.Notebook.stopPackageRecord': ['Lemma.Applications.Notebook.beginPackageRecordPiece', 'Lemma.Applications.Notebook.cancelPackageRecord', 'Lemma.Applications.Notebook.pollPackageRecordPiece', 'Lemma.Applications.Notebook.pumpPackageRecord'],
        'Lemma.Applications.Notebook.togglePackageCourse': ['Lemma.Applications.Notebook.packageInputSample.acceptSample'],
        'Lemma.Courses.PackageBinding.applicable': ['Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.validateAttempt'],
        'Lemma.Courses.PackageBinding.bytes': [],
        'Lemma.Courses.PackageBinding.capture': ['Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Courses.PackageWorkspace.captureSelection'],
        'Lemma.Courses.PackageBinding.captureField': ['Lemma.Courses.PackageBinding.capture'],
        'Lemma.Courses.PackageBinding.fieldsValid': ['Lemma.Courses.PackageBinding.validate'],
        'Lemma.Courses.PackageBinding.magic': [],
        'Lemma.Courses.PackageBinding.put': ['Lemma.Courses.PackageBinding.capture', 'Lemma.Courses.PackageBinding.captureField'],
        'Lemma.Courses.PackageBinding.spanValid': ['Lemma.Courses.PackageBinding.fieldsValid'],
        'Lemma.Courses.PackageBinding.validate': ['Lemma.Courses.PackageBinding.applicable', 'Lemma.Courses.PackageWorkspace.validateSelection'],
        'Lemma.Courses.PackageBinding.version': [],
        'Lemma.Courses.PackageBinding.word': ['Lemma.Courses.PackageBinding.applicable', 'Lemma.Courses.PackageBinding.capture', 'Lemma.Courses.PackageBinding.captureField', 'Lemma.Courses.PackageBinding.fieldsValid', 'Lemma.Courses.PackageBinding.validate'],
        'Lemma.Courses.PackageFormat.crcBit': ['Lemma.Courses.PackageFormat.crcByte'],
        'Lemma.Courses.PackageFormat.crcByte': ['Lemma.Courses.PackageTarget.crcStep'],
        'Lemma.Courses.PackageFormat.entryBytes': [],
        'Lemma.Courses.PackageFormat.headerBytes': [],
        'Lemma.Courses.PackageFormat.integrityFailure': [],
        'Lemma.Courses.PackageFormat.magic': [],
        'Lemma.Courses.PackageFormat.malformed': [],
        'Lemma.Courses.PackageFormat.maximumBytes': [],
        'Lemma.Courses.PackageFormat.maximumEdition': [],
        'Lemma.Courses.PackageFormat.maximumEntries': [],
        'Lemma.Courses.PackageFormat.maximumFieldBytes': [],
        'Lemma.Courses.PackageFormat.maximumIdentity': [],
        'Lemma.Courses.PackageFormat.maximumTextBytes': [],
        'Lemma.Courses.PackageFormat.object': ['Lemma.Applications.Notebook.packageReadEOF', 'Lemma.Courses.PackageReader.issue', 'Lemma.Courses.PackageReader.pollPiece'],
        'Lemma.Courses.PackageFormat.prerequisitesValid': ['Lemma.Courses.PackageTarget.validateEntry'],
        'Lemma.Courses.PackageFormat.referenceStatus': ['Lemma.Courses.PackageBinding.fieldsValid', 'Lemma.Courses.PackageTarget.validateEntry'],
        'Lemma.Courses.PackageFormat.resourceLimit': [],
        'Lemma.Courses.PackageFormat.selectionAbsent': [],
        'Lemma.Courses.PackageFormat.spanLength': ['Lemma.Applications.Notebook.packageControlPress', 'Lemma.Courses.PackageBinding.spanValid', 'Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader', 'Lemma.Courses.PackageTarget.validateSpan'],
        'Lemma.Courses.PackageFormat.spanOffset': ['Lemma.Courses.PackageBinding.spanValid', 'Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader', 'Lemma.Courses.PackageTarget.validateSpan'],
        'Lemma.Courses.PackageFormat.textByteValid': ['Lemma.Courses.PackageTarget.textStep'],
        'Lemma.Courses.PackageFormat.unsupported': [],
        'Lemma.Courses.PackageFormat.version': [],
        'Lemma.Courses.PackageReader.accept': ['Lemma.Courses.PackageReader.pollPiece'],
        'Lemma.Courses.PackageReader.beginPiece': ['Lemma.Courses.PackageReader.step'],
        'Lemma.Courses.PackageReader.cancel': ['Lemma.Applications.Notebook.cancelPackageRead'],
        'Lemma.Courses.PackageReader.clearStep': ['Lemma.Courses.PackageReader.start'],
        'Lemma.Courses.PackageReader.configuration': ['Lemma.Courses.PackageReader.cancel', 'Lemma.Courses.PackageReader.finish', 'Lemma.Courses.PackageReader.start', 'Lemma.Courses.PackageReader.step'],
        'Lemma.Courses.PackageReader.contextBytes': [],
        'Lemma.Courses.PackageReader.field': ['Lemma.Courses.PackageReader.accept', 'Lemma.Courses.PackageReader.beginPiece', 'Lemma.Courses.PackageReader.cancel', 'Lemma.Courses.PackageReader.configuration', 'Lemma.Courses.PackageReader.finish', 'Lemma.Courses.PackageReader.issue', 'Lemma.Courses.PackageReader.pollPiece', 'Lemma.Courses.PackageReader.start', 'Lemma.Courses.PackageReader.step'],
        'Lemma.Courses.PackageReader.finish': ['Lemma.Applications.Notebook.pumpPackageRead'],
        'Lemma.Courses.PackageReader.issue': ['Lemma.Courses.PackageReader.beginPiece'],
        'Lemma.Courses.PackageReader.maximumRequests': [],
        'Lemma.Courses.PackageReader.minimum': ['Lemma.Courses.PackageReader.beginPiece'],
        'Lemma.Courses.PackageReader.pollPiece': ['Lemma.Courses.PackageReader.step'],
        'Lemma.Courses.PackageReader.put': ['Lemma.Courses.PackageReader.accept', 'Lemma.Courses.PackageReader.cancel', 'Lemma.Courses.PackageReader.clearStep', 'Lemma.Courses.PackageReader.finish', 'Lemma.Courses.PackageReader.issue', 'Lemma.Courses.PackageReader.pollPiece', 'Lemma.Courses.PackageReader.start', 'Lemma.Courses.PackageReader.stop'],
        'Lemma.Courses.PackageReader.separate': ['Lemma.Courses.PackageReader.spans'],
        'Lemma.Courses.PackageReader.spans': ['Lemma.Courses.PackageReader.configuration'],
        'Lemma.Courses.PackageReader.start': ['Lemma.Applications.Notebook.beginPackageRead'],
        'Lemma.Courses.PackageReader.step': ['Lemma.Applications.Notebook.pumpPackageRead'],
        'Lemma.Courses.PackageReader.stop': ['Lemma.Courses.PackageReader.accept', 'Lemma.Courses.PackageReader.beginPiece', 'Lemma.Courses.PackageReader.cancel', 'Lemma.Courses.PackageReader.finish', 'Lemma.Courses.PackageReader.issue', 'Lemma.Courses.PackageReader.pollPiece'],
        'Lemma.Courses.PackageRender.cacheBytes': [],
        'Lemma.Courses.PackageRender.clearStep': ['Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader'],
        'Lemma.Courses.PackageRender.columns': [],
        'Lemma.Courses.PackageRender.glyph': ['Lemma.Applications.Notebook.packageControlStep', 'Lemma.Applications.Notebook.packageIdentityStep', 'Lemma.Courses.PackageRender.textStep'],
        'Lemma.Courses.PackageRender.pair': ['Lemma.Courses.PackageRender.panelWord'],
        'Lemma.Courses.PackageRender.panelWord': ['Lemma.Applications.Notebook.packageControlStep', 'Lemma.Applications.Notebook.packageIdentityStep', 'Lemma.Courses.PackageRender.renderStep'],
        'Lemma.Courses.PackageRender.pixel': ['Lemma.Courses.PackageRender.pair'],
        'Lemma.Courses.PackageRender.prepare': ['Lemma.Courses.PackageRender.renderSelected'],
        'Lemma.Courses.PackageRender.prepareHeader': ['Lemma.Courses.PackageRender.renderHeaderSelected'],
        'Lemma.Courses.PackageRender.render': ['Lemma.Courses.PackageRender.renderHeaderSelected', 'Lemma.Courses.PackageRender.renderSelected'],
        'Lemma.Courses.PackageRender.renderByteStep': ['Lemma.Courses.PackageRender.renderStep'],
        'Lemma.Courses.PackageRender.renderHeaderSelected': ['Lemma.Applications.Notebook.renderPackageText'],
        'Lemma.Courses.PackageRender.renderSelected': ['Lemma.Applications.Notebook.renderPackageText'],
        'Lemma.Courses.PackageRender.renderStep': ['Lemma.Courses.PackageRender.render'],
        'Lemma.Courses.PackageRender.rows': [],
        'Lemma.Courses.PackageRender.separate': ['Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader', 'Lemma.Courses.PackageRender.render', 'Lemma.Courses.PackageRender.renderHeaderSelected', 'Lemma.Courses.PackageRender.renderSelected'],
        'Lemma.Courses.PackageRender.textStep': ['Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader'],
        'Lemma.Courses.PackageTarget.crcStep': ['Lemma.Courses.PackageTarget.validateBody'],
        'Lemma.Courses.PackageTarget.entryStep': ['Lemma.Courses.PackageTarget.validateBody'],
        'Lemma.Courses.PackageTarget.entryTextStep': ['Lemma.Courses.PackageTarget.validateEntry'],
        'Lemma.Courses.PackageTarget.headerTextStep': ['Lemma.Courses.PackageTarget.validateBody'],
        'Lemma.Courses.PackageTarget.reservedStep': ['Lemma.Courses.PackageTarget.validateEntry'],
        'Lemma.Courses.PackageTarget.select': ['Lemma.Courses.PackageBinding.capture'],
        'Lemma.Courses.PackageTarget.textStep': ['Lemma.Courses.PackageTarget.validateSpan'],
        'Lemma.Courses.PackageTarget.validate': ['Lemma.Courses.PackageReader.finish', 'Lemma.Courses.PackageRender.prepare', 'Lemma.Courses.PackageRender.prepareHeader', 'Lemma.Courses.PackageTarget.select'],
        'Lemma.Courses.PackageTarget.validateBody': ['Lemma.Courses.PackageTarget.validate'],
        'Lemma.Courses.PackageTarget.validateEntry': ['Lemma.Courses.PackageTarget.entryStep'],
        'Lemma.Courses.PackageTarget.validateSpan': ['Lemma.Courses.PackageTarget.entryTextStep', 'Lemma.Courses.PackageTarget.headerTextStep'],
        'Lemma.Courses.PackageTarget.word': ['Lemma.Courses.PackageTarget.entryTextStep', 'Lemma.Courses.PackageTarget.headerTextStep', 'Lemma.Courses.PackageTarget.reservedStep', 'Lemma.Courses.PackageTarget.validate', 'Lemma.Courses.PackageTarget.validateEntry'],
        'Lemma.Courses.PackageWorkspace.attempts': [],
        'Lemma.Courses.PackageWorkspace.bytes': [],
        'Lemma.Courses.PackageWorkspace.captureSelection': ['Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Applications.Notebook.stagePackagePress.stage'],
        'Lemma.Courses.PackageWorkspace.cloneContents': ['Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown', 'Lemma.Courses.PackageWorkspace.stageRefresh', 'Lemma.Courses.PackageWorkspace.stageUnknownSelection'],
        'Lemma.Courses.PackageWorkspace.copyBinding': ['Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted'],
        'Lemma.Courses.PackageWorkspace.copyBindingStep': ['Lemma.Courses.PackageWorkspace.cloneContents', 'Lemma.Courses.PackageWorkspace.copyBinding'],
        'Lemma.Courses.PackageWorkspace.create': ['Lemma.Applications.Notebook.pumpOpenPackageCourse'],
        'Lemma.Courses.PackageWorkspace.equalEventsStep': ['Lemma.Courses.PackageWorkspace.transitionBase'],
        'Lemma.Courses.PackageWorkspace.equalHistoryStep': ['Lemma.Courses.PackageWorkspace.transitionBase'],
        'Lemma.Courses.PackageWorkspace.equalSubmissionStep': ['Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown'],
        'Lemma.Courses.PackageWorkspace.equalWordsStep': ['Lemma.Courses.PackageWorkspace.stageCompleted'],
        'Lemma.Courses.PackageWorkspace.field': ['Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.copyBindingStep', 'Lemma.Courses.PackageWorkspace.equalEventsStep', 'Lemma.Courses.PackageWorkspace.equalHistoryStep', 'Lemma.Courses.PackageWorkspace.equalSubmissionStep', 'Lemma.Courses.PackageWorkspace.equalWordsStep', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown', 'Lemma.Courses.PackageWorkspace.stageUnknownSelection', 'Lemma.Courses.PackageWorkspace.transitionBase', 'Lemma.Courses.PackageWorkspace.validate', 'Lemma.Courses.PackageWorkspace.validateAttempt', 'Lemma.Courses.PackageWorkspace.validateOwned', 'Lemma.Courses.PackageWorkspace.validateSelection', 'Lemma.Courses.PackageWorkspace.zeroCheck'],
        'Lemma.Courses.PackageWorkspace.inner': [],
        'Lemma.Courses.PackageWorkspace.magic': [],
        'Lemma.Courses.PackageWorkspace.object': ['Lemma.Applications.Notebook.openPackageCourse', 'Lemma.Applications.Notebook.savePackageWorkspace'],
        'Lemma.Courses.PackageWorkspace.put': ['Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.cloneContents', 'Lemma.Courses.PackageWorkspace.copyBinding', 'Lemma.Courses.PackageWorkspace.copyBindingStep', 'Lemma.Courses.PackageWorkspace.create', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown', 'Lemma.Courses.PackageWorkspace.stageRefresh', 'Lemma.Courses.PackageWorkspace.stageUnknownSelection', 'Lemma.Courses.PackageWorkspace.zeroStep'],
        'Lemma.Courses.PackageWorkspace.selection': [],
        'Lemma.Courses.PackageWorkspace.separate': ['Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.transitionBase'],
        'Lemma.Courses.PackageWorkspace.shape': ['Lemma.Courses.PackageWorkspace.create', 'Lemma.Courses.PackageWorkspace.validate'],
        'Lemma.Courses.PackageWorkspace.snapshotSelection': ['Lemma.Applications.Notebook.beginPackageArithmetic'],
        'Lemma.Courses.PackageWorkspace.stageCompleted': ['Lemma.Applications.Notebook.stagePackageCompletion'],
        'Lemma.Courses.PackageWorkspace.stageCompletedUnknown': ['Lemma.Applications.Notebook.stagePackageCompletion'],
        'Lemma.Courses.PackageWorkspace.stageRefresh': ['Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Applications.Notebook.stagePackagePress.stage'],
        'Lemma.Courses.PackageWorkspace.stageUnknownSelection': ['Lemma.Applications.Notebook.stagePackagePress.stage'],
        'Lemma.Courses.PackageWorkspace.transitionBase': ['Lemma.Courses.PackageWorkspace.stageCompleted', 'Lemma.Courses.PackageWorkspace.stageCompletedUnknown', 'Lemma.Courses.PackageWorkspace.stageRefresh', 'Lemma.Courses.PackageWorkspace.stageUnknownSelection'],
        'Lemma.Courses.PackageWorkspace.validate': ['Lemma.Applications.Notebook.adoptPackageWorkspace', 'Lemma.Applications.Notebook.beginPackageArithmetic', 'Lemma.Applications.Notebook.pumpOpenPackageCourse', 'Lemma.Applications.Notebook.savePackageWorkspace', 'Lemma.Applications.Notebook.stagePackageExercise', 'Lemma.Courses.PackageWorkspace.validateOwned'],
        'Lemma.Courses.PackageWorkspace.validateAttempt': ['Lemma.Courses.PackageWorkspace.validate'],
        'Lemma.Courses.PackageWorkspace.validateOwned': ['Lemma.Courses.PackageWorkspace.captureSelection', 'Lemma.Courses.PackageWorkspace.snapshotSelection', 'Lemma.Courses.PackageWorkspace.transitionBase'],
        'Lemma.Courses.PackageWorkspace.validateSelection': ['Lemma.Courses.PackageWorkspace.validate'],
        'Lemma.Courses.PackageWorkspace.version': [],
        'Lemma.Courses.PackageWorkspace.zeroCheck': ['Lemma.Courses.PackageWorkspace.validateAttempt', 'Lemma.Courses.PackageWorkspace.validateSelection'],
        'Lemma.Courses.PackageWorkspace.zeroStep': ['Lemma.Courses.PackageWorkspace.create', 'Lemma.Courses.PackageWorkspace.stageUnknownSelection'],
    },
}
PRODUCER_AUTHORITY = {'producer_result_sha256': '7508b98d1c6aacaf3392febef43f88033fe67190bd641f209a73966f3526fe52', 'source_count': 315, 'producer_head': 'ff48d048519bfaa78dd05466106bd1df75496789', 'actual_artifacts': {'program.ll': '677306d2bf35e56161924a328092673490c05b7d9efcc6b9879d968dd8892caa', 'program.opt.ll': '3064efc4577b0ca62bcbaaa0418002c70cdbb0930ae318e4b16237e4d00b5370', 'unit.json': '80747181cb4e4ccd8a5e4497a923fabe233aa10ff3b7ebdae6239a3e11ee6a07'}}


COUNTER_ADDRESS_SOURCE = 'Lemma.Applications.Notebook.packageAllocationAddress'
def signature_set(unit):
    # This real source-owned address declaration identifies layout2 in the
    # emitted catalog. The same catalog must match both pre/post bodies.
    signatures = {**SIGNATURES, COUNTER_ADDRESS_SOURCE: ([], [])} if COUNTER_ADDRESS_SOURCE in _rows(unit) else SIGNATURES
    if delta_selected(unit):
        signatures = {**{name: value for name, value in signatures.items() if name not in DELTA_REMOVED},
                      **DELTA_SIGNATURES}
    if sparse_selected(unit):
        signatures = {**signatures, **SPARSE_SIGNATURES}
    if workspace_selected(unit):
        signatures = {**signatures, **WORKSPACE_SIGNATURES}
    return signatures

# Derived from the separately qualified genuine complete pre/post export.
COUNTER_LAYOUT_V2_PINS = {'post': {'Lemma.Applications.Notebook.allocatePackage': '25b03c7928619e4d703693daad63a460e1950317fdc6bb93d0893c9c33faf8a4',
          'Lemma.Applications.Notebook.cancelPackageWork': '804063d13e587530ad3a4076f17d9d74fbc18da36e14a4277211936a80935216',
          'Lemma.Applications.Notebook.mainPackageClosureBulk': '67ba11f86f61796b0b596545d86423ebc2b0f02fd7117bad07e1b9489d4b11d4',
          'Lemma.Applications.Notebook.packageAllocateStep': '3753b9c1804d731b5d0b35c8c335617df7ac951e6ea9620fbe70d5f07ed95300',
          'Lemma.Applications.Notebook.packageAllocationAddress': '2698705d65c78d62222503221fa9bcf9e49b13093e96b740017fb6a87291a035',
          'Lemma.Applications.Notebook.packageBusy': 'c7761f9e0ec2fbb0f97b58e240b52c52c8bdd5df5e42cf6c84c230f26754908f',
          'Lemma.Applications.Notebook.packageCloseState': '454215d5356befa8ba32b00e7fd01d559bfb2b8cfafc3d95ece337ff276aeef2',
          'Lemma.Applications.Notebook.packageControlCharacter': '917eb8ee0a0e377c2e99c80517e69b73be29547d4d5e89eb977f7ce285712d2f',
          'Lemma.Applications.Notebook.pumpPackageWork': 'e4a43acc73e946a4f0c49a9c1b5f30ab098286135d7f5225d2ab837808d865f4'},
 'pre': {'Lemma.Applications.Notebook.allocatePackage': '71dab202c5a098ef566081c9922635a6651e5037fba97ec8456dd531a36ebe23',
         'Lemma.Applications.Notebook.cancelPackageWork': '14935c35837cefa73c31a920a55dd920c8efd1c2561f73c612915c2d7c4940a4',
         'Lemma.Applications.Notebook.mainPackageClosureBulk': '4d65240a23cc144f0ecd618284855d5b2b8361688ba8eed82b00e6d5f9bbcb7f',
         'Lemma.Applications.Notebook.packageAllocateStep': 'ebe79336d958ddc4080684aebe603963caf3175bb627807155bd55c817a1a02e',
         'Lemma.Applications.Notebook.packageAllocationAddress': '5628140255b93b3e6c97c55c7edf4c4e22988e3e58dc217a3ab324e789dd15aa',
         'Lemma.Applications.Notebook.packageBusy': '08b9718a43c66ec2e1b4b5deb5355c2e5a9cb7eab136a1edc777abbe0c46efa7',
         'Lemma.Applications.Notebook.packageCloseState': 'a75568e824ae22a141762d853dcd32c9bbdceb7159b4a5949811fb7396b705d1',
         'Lemma.Applications.Notebook.pumpPackageWork': '2f9fccf63cf702305ae0c85275fd31261505fa57c1771720a824164732036222'}}
COUNTER_LAYOUT_V2_CALLER_ADDITIONS = {'post': {'Lemma.Applications.Notebook.packageAllocationAddress': []},
 'pre': {'Lemma.Applications.Notebook.packageAllocationAddress': ['Lemma.Applications.Notebook.allocatePackage',
                                                                  'Lemma.Applications.Notebook.cancelPackageWork',
                                                                  'Lemma.Applications.Notebook.mainPackageClosureBulk',
                                                                  'Lemma.Applications.Notebook.packageAllocateStep',
                                                                  'Lemma.Applications.Notebook.packageBusy',
                                                                  'Lemma.Applications.Notebook.packageCloseState',
                                                                  'Lemma.Applications.Notebook.pumpPackageWork']}}

COUNTER_LAYOUT_V2_AUTHORITY = {'scope': 'genuine selected818-function User2 export and complete normalized source relation; whole artifact/CPU qualification separate', 'normalized_relation': {'path': 'build/courses/task006-package-counter-repair-a2/qualified-layout2-a2.json', 'sha256': '48e7850d50776bd69acaccf5fbbe3305ae120c5f7cc6a1ceb1683152a8507c5a'}, 'cohort_qualification': {'path': 'build/courses/task006-package-counter-repair-a2/cohort-qualification.json', 'sha256': '007cb8b830691e014c6ee830bf05a2e8d20d8f656ff173764bbbf24729f6b373'}, 'artifacts': {'unit.json': {'path': 'build/courses/task006-package-counter-repair-a2/users/notebook/unit.json', 'sha256': 'ffc5f5d2a618f44df2c446338e4ec5323f88c5ff4eac51811cc9a9ef36b75826'}, 'program.ll': {'path': 'build/courses/task006-package-counter-repair-a2/users/notebook/program.ll', 'sha256': '31d51bcc92e7b76de7f7cdbb49e0b76440c9205b6f9381cc5befa868f42d1b90'}, 'program.opt.ll': {'path': 'build/courses/task006-package-counter-repair-a2/users/notebook/program.opt.ll', 'sha256': 'e1283e16db1c2a21ab147ec35e01f8601f981573a8f77c1c0fab267ad89a7e00'}, 'normalized.txt': {'path': 'build/courses/task006-package-counter-repair-a2/users/notebook/normalized.txt', 'sha256': 'b55864fbcfc1cfd44b2e4a638b0ebbc419f5269736e06b181599707c7d4b00b9'}}}


# Text-delta1 is a separately qualified software cohort. Historical panel1 and
# layout1/layout2 bodies remain pinned without accepting mixed implementations.
DELTA_VERSION = 'lemma-installed-package-notebook/3'
DELTA_LAYOUT = {**PRIVATE_LAYOUT, 'text_delta_contract': 'lemma-course-text-delta/1',
                'changed_columns': 13, 'changed_rows': 10,
                'projection': 'columns-low13-rows-next10-cartesian-cover',
                'persistent_pixel_cache': False}
DELTA_REMOVED = frozenset('Lemma.Courses.PackageRender.' + name for name in
                          ('render', 'renderStep', 'renderSelected', 'renderHeaderSelected'))
DELTA_SIGNATURES = {
    'Lemma.Courses.PackageRender.' + name: (args, effects) for name, args, effects in (
        ('readByteStep', ['u32', 'u32'] + ['u64'] * 5, ['checked-access', 'virtual-read']),
        ('readWord', ['u64'], ['checked-access', 'virtual-read']),
        ('deltaStep', ['u32', 'u32'] + ['u64'] * 5, ['checked-access', 'virtual-read', 'virtual-write']),
        ('renderDelta', ['u64'] * 3, ['checked-access', 'virtual-read', 'virtual-write']),
        ('renderSelectedDelta', ['u64'] * 8, ['checked-access', 'virtual-read', 'virtual-write']),
        ('renderHeaderSelectedDelta', ['u64'] * 7, ['checked-access', 'virtual-read', 'virtual-write']))}


def delta_selected(unit):
    rows = _rows(unit)
    found = set(rows) & set(DELTA_SIGNATURES)
    if not found:
        return False
    require(found == set(DELTA_SIGNATURES) and COUNTER_ADDRESS_SOURCE in rows and
            not set(rows) & DELTA_REMOVED,
            'Package Notebook mixed/incomplete text-delta cohort')
    return True

# Exact whole-source delta cohort, qualified against prior genuine layout2.
DELTA_PINS = {'post': {'Lemma.Applications.Notebook.packageTileStep': '8bec2a41e3a79a8153d1f1a1ade2a702184db65c68922466a7b87a2813bb8bf8',
          'Lemma.Applications.Notebook.renderPackageText': '1aa597093d62c535068161db392b1111cd7f03c622d2da22f6ec47ad408803a6',
          'Lemma.Courses.PackageBinding.captureField': '603fad700e34ada7757ba206e5b1ae8026ee2f56670c79ba6fb02cd1c52432ef',
          'Lemma.Courses.PackageRender.deltaStep': 'ba09c848eb7e6da665fb0e1a4f78862ffe885faf6c21d2f9ed350689d3bf65e7',
          'Lemma.Courses.PackageRender.readByteStep': '7d6c8493fcfba9b34dda820211f284b066a2280beeb5a408fb6427a6e2300741',
          'Lemma.Courses.PackageRender.readWord': '929662f3286748520cfeada924832ef67288806373b8df3f6e7b2f60bbd3c642',
          'Lemma.Courses.PackageRender.renderDelta': '1dd81c42218c2717ac3f016b392e3a3038c19684d722f704e5aeb6d5fb9d2c36',
          'Lemma.Courses.PackageRender.renderHeaderSelectedDelta': '6a4a0db042b4526e4a70a8cc7587024666d84dc8b5983926d9cf72c2101fbf51',
          'Lemma.Courses.PackageRender.renderSelectedDelta': 'daf30a700db369264b93392e6ecb138b88ae382931bcde3ee1adb3fb10cb4240'},
 'pre': {'Lemma.Applications.Notebook.packageTileStep': 'ad59e514d12eb034fd5baf1b398832696f1e8948432b552f08266ab5d4607c12',
         'Lemma.Applications.Notebook.renderPackageText': '80f27a8a27584016c4309a8f71df2b4b6f3439f14ec384f30d9e11ded76de0d3',
         'Lemma.Courses.PackageRender.deltaStep': '056b162e987454091bed96f99b056f7b376a4082eabc3b625a2a136bae7be131',
         'Lemma.Courses.PackageRender.readByteStep': 'fdb8b15262ee6ae761635a4f40aeb25ae4526cc1779ad190d697b8cfcb00e84d',
         'Lemma.Courses.PackageRender.readWord': '74774ff6fdac7030f73e992093bd3b134f3efc2f5a923817bfd4fc9e163837a2',
         'Lemma.Courses.PackageRender.renderDelta': '7a3a7699cf8b5fbfa60b501a4064d249d63a27e861fe56651d63efbae36de237',
         'Lemma.Courses.PackageRender.renderHeaderSelectedDelta': '3aa68569190bf2860854eeed2a90925a6091f1c0581442bf0fa941365d4c703d',
         'Lemma.Courses.PackageRender.renderSelectedDelta': '9d3f3580700b6d4ce4ccefd5fda71a6bd02168a0abc5363578bd35d44f28cdd1'}}
DELTA_CALLERS = {'post': {'Lemma.Courses.PackageRender.deltaStep': ['Lemma.Courses.PackageRender.renderDelta'],
          'Lemma.Courses.PackageRender.panelWord': ['Lemma.Applications.Notebook.packageControlStep',
                                                    'Lemma.Applications.Notebook.packageIdentityStep',
                                                    'Lemma.Courses.PackageRender.deltaStep'],
          'Lemma.Courses.PackageRender.prepare': ['Lemma.Courses.PackageRender.renderSelectedDelta'],
          'Lemma.Courses.PackageRender.prepareHeader': ['Lemma.Courses.PackageRender.renderHeaderSelectedDelta'],
          'Lemma.Courses.PackageRender.readByteStep': ['Lemma.Courses.PackageRender.readWord'],
          'Lemma.Courses.PackageRender.readWord': ['Lemma.Courses.PackageRender.deltaStep'],
          'Lemma.Courses.PackageRender.renderByteStep': ['Lemma.Courses.PackageRender.deltaStep'],
          'Lemma.Courses.PackageRender.renderDelta': ['Lemma.Courses.PackageRender.renderHeaderSelectedDelta',
                                                      'Lemma.Courses.PackageRender.renderSelectedDelta'],
          'Lemma.Courses.PackageRender.renderHeaderSelectedDelta': ['Lemma.Applications.Notebook.renderPackageText'],
          'Lemma.Courses.PackageRender.renderSelectedDelta': ['Lemma.Applications.Notebook.renderPackageText'],
          'Lemma.Courses.PackageRender.separate': ['Lemma.Courses.PackageRender.prepare',
                                                   'Lemma.Courses.PackageRender.prepareHeader',
                                                   'Lemma.Courses.PackageRender.renderDelta',
                                                   'Lemma.Courses.PackageRender.renderHeaderSelectedDelta',
                                                   'Lemma.Courses.PackageRender.renderSelectedDelta']},
 'pre': {'Lemma.Courses.PackageFormat.malformed': ['Lemma.Courses.PackageBinding.capture',
                                                   'Lemma.Courses.PackageBinding.fieldsValid',
                                                   'Lemma.Courses.PackageBinding.validate',
                                                   'Lemma.Courses.PackageFormat.referenceStatus',
                                                   'Lemma.Courses.PackageReader.accept',
                                                   'Lemma.Courses.PackageReader.beginPiece',
                                                   'Lemma.Courses.PackageReader.cancel',
                                                   'Lemma.Courses.PackageReader.configuration',
                                                   'Lemma.Courses.PackageReader.finish',
                                                   'Lemma.Courses.PackageReader.pollPiece',
                                                   'Lemma.Courses.PackageReader.start',
                                                   'Lemma.Courses.PackageReader.step',
                                                   'Lemma.Courses.PackageRender.prepare',
                                                   'Lemma.Courses.PackageRender.prepareHeader',
                                                   'Lemma.Courses.PackageRender.renderDelta',
                                                   'Lemma.Courses.PackageRender.renderHeaderSelectedDelta',
                                                   'Lemma.Courses.PackageRender.renderSelectedDelta',
                                                   'Lemma.Courses.PackageTarget.reservedStep',
                                                   'Lemma.Courses.PackageTarget.validate',
                                                   'Lemma.Courses.PackageTarget.validateBody',
                                                   'Lemma.Courses.PackageTarget.validateEntry',
                                                   'Lemma.Courses.PackageTarget.validateSpan',
                                                   'Lemma.Courses.PackageWorkspace.captureSelection',
                                                   'Lemma.Courses.PackageWorkspace.create',
                                                   'Lemma.Courses.PackageWorkspace.equalEventsStep',
                                                   'Lemma.Courses.PackageWorkspace.equalHistoryStep',
                                                   'Lemma.Courses.PackageWorkspace.equalSubmissionStep',
                                                   'Lemma.Courses.PackageWorkspace.equalWordsStep',
                                                   'Lemma.Courses.PackageWorkspace.snapshotSelection',
                                                   'Lemma.Courses.PackageWorkspace.stageCompleted',
                                                   'Lemma.Courses.PackageWorkspace.stageCompletedUnknown',
                                                   'Lemma.Courses.PackageWorkspace.stageRefresh',
                                                   'Lemma.Courses.PackageWorkspace.stageUnknownSelection',
                                                   'Lemma.Courses.PackageWorkspace.transitionBase',
                                                   'Lemma.Courses.PackageWorkspace.validate',
                                                   'Lemma.Courses.PackageWorkspace.validateAttempt',
                                                   'Lemma.Courses.PackageWorkspace.validateSelection',
                                                   'Lemma.Courses.PackageWorkspace.zeroCheck'],
         'Lemma.Courses.PackageFormat.resourceLimit': ['Lemma.Courses.PackageBinding.capture',
                                                       'Lemma.Courses.PackageBinding.fieldsValid',
                                                       'Lemma.Courses.PackageReader.accept',
                                                       'Lemma.Courses.PackageReader.beginPiece',
                                                       'Lemma.Courses.PackageReader.configuration',
                                                       'Lemma.Courses.PackageReader.pollPiece',
                                                       'Lemma.Courses.PackageRender.renderDelta',
                                                       'Lemma.Courses.PackageRender.renderHeaderSelectedDelta',
                                                       'Lemma.Courses.PackageRender.renderSelectedDelta',
                                                       'Lemma.Courses.PackageTarget.validate',
                                                       'Lemma.Courses.PackageTarget.validateSpan',
                                                       'Lemma.Courses.PackageWorkspace.stageCompleted',
                                                       'Lemma.Courses.PackageWorkspace.stageCompletedUnknown'],
         'Lemma.Courses.PackageRender.cacheBytes': ['Lemma.Courses.PackageRender.prepare',
                                                    'Lemma.Courses.PackageRender.prepareHeader',
                                                    'Lemma.Courses.PackageRender.renderDelta',
                                                    'Lemma.Courses.PackageRender.renderHeaderSelectedDelta',
                                                    'Lemma.Courses.PackageRender.renderSelectedDelta'],
         'Lemma.Courses.PackageRender.columns': ['Lemma.Courses.PackageRender.deltaStep',
                                                 'Lemma.Courses.PackageRender.textStep'],
         'Lemma.Courses.PackageRender.deltaStep': ['Lemma.Courses.PackageRender.renderDelta'],
         'Lemma.Courses.PackageRender.panelWord': ['Lemma.Applications.Notebook.packageControlStep',
                                                   'Lemma.Applications.Notebook.packageIdentityStep',
                                                   'Lemma.Courses.PackageRender.deltaStep'],
         'Lemma.Courses.PackageRender.prepare': ['Lemma.Courses.PackageRender.renderSelectedDelta'],
         'Lemma.Courses.PackageRender.prepareHeader': ['Lemma.Courses.PackageRender.renderHeaderSelectedDelta'],
         'Lemma.Courses.PackageRender.readByteStep': ['Lemma.Courses.PackageRender.readWord'],
         'Lemma.Courses.PackageRender.readWord': ['Lemma.Courses.PackageRender.deltaStep'],
         'Lemma.Courses.PackageRender.renderByteStep': ['Lemma.Courses.PackageRender.deltaStep'],
         'Lemma.Courses.PackageRender.renderDelta': ['Lemma.Courses.PackageRender.renderHeaderSelectedDelta',
                                                     'Lemma.Courses.PackageRender.renderSelectedDelta'],
         'Lemma.Courses.PackageRender.renderHeaderSelectedDelta': ['Lemma.Applications.Notebook.renderPackageText'],
         'Lemma.Courses.PackageRender.renderSelectedDelta': ['Lemma.Applications.Notebook.renderPackageText'],
         'Lemma.Courses.PackageRender.separate': ['Lemma.Courses.PackageRender.prepare',
                                                  'Lemma.Courses.PackageRender.prepareHeader',
                                                  'Lemma.Courses.PackageRender.renderDelta',
                                                  'Lemma.Courses.PackageRender.renderHeaderSelectedDelta',
                                                  'Lemma.Courses.PackageRender.renderSelectedDelta']}}

# A separately bound, purely computational successor. No stored state/cache or
# memory-effect elision is authorized by the white-word shortcut.
SPARSE_VERSION = 'lemma-installed-package-notebook/4'
SPARSE_LAYOUT = {**DELTA_LAYOUT, 'white_word_contract': 'lemma-course-white-word/1',
                 'panels': ['selected-text', 'package-controls', 'mathematics']}
SPARSE_SIGNATURES = {
    'Lemma.Courses.PackageRender.sparsePanelWord': (['u64'] * 4, []),
    'Lemma.Courses.Arithmetic.panelWordSparse': (['u64'] * 5, []),
    'Lemma.Courses.Arithmetic.renderSparseStep': (['u32', 'u32'] + ['u64'] * 5,
                                               ['checked-access', 'virtual-write']),
    'Lemma.Courses.Arithmetic.renderSparse': (['u64', 'u64'],
                                            ['checked-access', 'virtual-read', 'virtual-write']),
    'Lemma.Applications.Notebook.renderPackageCourse': ([],
                                                      ['checked-access', 'virtual-read', 'virtual-write'])}


def sparse_selected(unit):
    rows = _rows(unit)
    found = set(rows) & set(SPARSE_SIGNATURES)
    if not found:
        return False
    require(found == set(SPARSE_SIGNATURES) and delta_selected(unit),
            'Package Notebook mixed/incomplete pure white-word cohort')
    return True

# Exact ordinary Lean white-word cohort, including all new presentation helpers.
SPARSE_PINS = {'post': {'Lemma.Applications.Notebook.finishOpenPackageCourse': 'c9ef8789a266eb508b4f611ca3257ce93c5e201521c4a158128218e1b54efcbd',
          'Lemma.Applications.Notebook.packageControlCharacter': 'efebc4397b55a9782e127d727cfcbcee48ed528d81fa809a62963eb2bd519813',
          'Lemma.Applications.Notebook.packageControlStep': '991ff2e9a9740c85a2a932d0ab4f139bbcb6d7d2d7f7ed07eb2b28ef767f3a81',
          'Lemma.Applications.Notebook.packageIdentityStep': '71199655130146c959c6d70293a9bcc18d68d67ede4da9ddb030594ea964dc01',
          'Lemma.Applications.Notebook.publishPackageWorkspace': '9603c1ebfc45e64a43b67039924d154cda6794ff60a84a0393ac9ec4100308b3',
          'Lemma.Applications.Notebook.renderPackageCourse': '60f4c3a4bf7ceb1278a4c89a5c04dc8f4cec802a8d7a7d574a146d0b33d2f639',
          'Lemma.Courses.Arithmetic.panelWordSparse': 'b6b0931dd51991491c0e1f2c42fd511e2e964f9a8551ec6a9cc5f0930cf592b0',
          'Lemma.Courses.Arithmetic.renderSparse': '63daa547a54d5c8ea0ba865332f0f0f1e7c1ac976c665816267901fa6d3b11b5',
          'Lemma.Courses.Arithmetic.renderSparseStep': '6fb62902c099b16139be11832859c38305ff84dddecb16203d97bcc9d9ea3808',
          'Lemma.Courses.PackageRender.deltaStep': '033260dc99922676b2cefa4475586377a0e733b1fb4602deeb4beebae909d7fa',
          'Lemma.Courses.PackageRender.sparsePanelWord': '7ec8ed74198cea2942f68c514bab4e59f13ce7e113cf9ed133199d70b8a12460'},
 'pre': {'Lemma.Applications.Notebook.finishOpenPackageCourse': '1cec606671a3265a229bf8de60c26754fffecafb1722e067fd9239e1107cda89',
         'Lemma.Applications.Notebook.packageControlStep': '9843e05be79e6e9e188d262dd0110b61d2d98ee7ba83ff7492eb50950d49a150',
         'Lemma.Applications.Notebook.packageIdentityStep': 'a5bb4e50149dc77155d5fc124bb2dc13d157f1d9e9b693d9936ab38b44e0d658',
         'Lemma.Applications.Notebook.publishPackageWorkspace': '30de2fda487dd69e48b862bc41820ff90a1edc88e2e369fb4ad2bfe394c26d88',
         'Lemma.Applications.Notebook.renderPackageCourse': '5c53c5cf7242d54b407fdb240d9eace50c4bd8fcaf45f015ba4c5467df58916c',
         'Lemma.Courses.Arithmetic.panelWordSparse': 'fa3d18de78cf67804c2843decf356b688ac5368f743f3fed6f637755be50ad35',
         'Lemma.Courses.Arithmetic.renderSparse': '709aeff89573932b09cc265563e73ef797f068d7b274bed65f48ddbaf5eedfbe',
         'Lemma.Courses.Arithmetic.renderSparseStep': '5d525518bc0c1bc4b2f8e04696b1e62385e42f227a5a14ffb0cceeb13fe84830',
         'Lemma.Courses.PackageRender.deltaStep': '4bd0011642739018f5f1cffc8b797b7a9a986d5fa236880ab82226673961e8e4',
         'Lemma.Courses.PackageRender.sparsePanelWord': 'f423e4046206590b865b31cddbe49c2e49fcdd034b56cc61a2437a81dada9c35'}}
SPARSE_CALLERS = {'post': {'Lemma.Applications.Notebook.renderPackageCourse': ['Lemma.Applications.Notebook.finishOpenPackageCourse',
                                                              'Lemma.Applications.Notebook.publishPackageWorkspace'],
          'Lemma.Courses.Arithmetic.panelWordSparse': ['Lemma.Courses.Arithmetic.renderSparseStep'],
          'Lemma.Courses.Arithmetic.renderSparse': ['Lemma.Applications.Notebook.renderPackageCourse'],
          'Lemma.Courses.Arithmetic.renderSparseStep': ['Lemma.Courses.Arithmetic.renderSparse'],
          'Lemma.Courses.PackageRender.panelWord': ['Lemma.Courses.PackageRender.sparsePanelWord'],
          'Lemma.Courses.PackageRender.sparsePanelWord': ['Lemma.Applications.Notebook.packageControlStep',
                                                          'Lemma.Applications.Notebook.packageIdentityStep',
                                                          'Lemma.Courses.Arithmetic.panelWordSparse',
                                                          'Lemma.Courses.PackageRender.deltaStep']},
 'pre': {'Lemma.Applications.Notebook.renderPackageCourse': ['Lemma.Applications.Notebook.finishOpenPackageCourse',
                                                             'Lemma.Applications.Notebook.publishPackageWorkspace'],
         'Lemma.Courses.Arithmetic.panelWordSparse': ['Lemma.Courses.Arithmetic.renderSparseStep'],
         'Lemma.Courses.Arithmetic.renderSparse': ['Lemma.Applications.Notebook.renderPackageCourse'],
         'Lemma.Courses.Arithmetic.renderSparseStep': ['Lemma.Courses.Arithmetic.renderSparse'],
         'Lemma.Courses.PackageRender.panelWord': ['Lemma.Courses.PackageRender.sparsePanelWord'],
         'Lemma.Courses.PackageRender.sparsePanelWord': ['Lemma.Applications.Notebook.packageControlStep',
                                                         'Lemma.Applications.Notebook.packageIdentityStep',
                                                         'Lemma.Courses.Arithmetic.panelWordSparse',
                                                         'Lemma.Courses.PackageRender.deltaStep']}}

# Lossless sparse workspace envelope2, complete genuine User2 source cohort5.
WORKSPACE_VERSION = 'lemma-installed-package-notebook/5'
WORKSPACE_LAYOUT = {**SPARSE_LAYOUT, 'workspace_envelope': 2,
                    'workspace_raw_read_versions': [1], 'workspace_encoded_write_version': 2,
                    'workspace_encoded_maximum_bytes': 3808,
                    'workspace_decode_private_staging': (0x332000, 3712),
                    'workspace_save_staging': (0x32a000, 4096),
                    'workspace_full_read_phase': 5}
WORKSPACE_SIGNATURES = {'Lemma.Courses.WorkspaceCodec.clearStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                            ['checked-access', 'virtual-write']),
 'Lemma.Courses.WorkspaceCodec.countStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                            ['checked-access', 'virtual-read']),
 'Lemma.Courses.WorkspaceCodec.decode': (['u64', 'u64', 'u64', 'u64', 'u64'],
                                         ['checked-access', 'virtual-read', 'virtual-write']),
 'Lemma.Courses.WorkspaceCodec.decodeStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                             ['checked-access', 'virtual-read', 'virtual-write']),
 'Lemma.Courses.WorkspaceCodec.encode': (['u64', 'u64', 'u64', 'u64'],
                                         ['checked-access', 'virtual-read', 'virtual-write']),
 'Lemma.Courses.WorkspaceCodec.encodeStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                             ['checked-access', 'virtual-read', 'virtual-write']),
 'Lemma.Courses.WorkspaceCodec.headerBytes': ([], []),
 'Lemma.Courses.WorkspaceCodec.magic': ([], []),
 'Lemma.Courses.WorkspaceCodec.maximumBytes': ([], []),
 'Lemma.Courses.WorkspaceCodec.read': (['u64', 'u64'], ['checked-access', 'virtual-read']),
 'Lemma.Courses.WorkspaceCodec.recordLength': (['u64'], ['checked-access', 'virtual-read']),
 'Lemma.Courses.WorkspaceCodec.separate': (['u64', 'u64', 'u64', 'u64'], []),
 'Lemma.Courses.WorkspaceCodec.version': ([], []),
 'Lemma.Courses.WorkspaceCodec.write': (['u64', 'u64', 'u64'], ['checked-access', 'virtual-write'])}

def workspace_selected(unit):
    rows = _rows(unit)
    found = {source for source in rows if source.startswith('Lemma.Courses.WorkspaceCodec.')}
    if not found:
        return False
    require(found == set(WORKSPACE_SIGNATURES) and sparse_selected(unit),
            'Package Notebook mixed/incomplete workspace-envelope cohort')
    return True

# Exact ordinary Lean workspace envelope cohort, including every codec helper.
WORKSPACE_PINS = {'post': {'Lemma.Applications.Notebook.cancelPackageWork': '2518571e60f1927ac5d70423257525d9818fc3e285883ab97f3a0c83879fad8b',
          'Lemma.Applications.Notebook.openPackageCourse': '8f688a7fba33ffa7376066705e3d915079dbc9618ed031136dbae013a7fd71ec',
          'Lemma.Applications.Notebook.packageBusy': '036c2517409ad27653c3287776ba7f475293cd7ec6458b2fc909e99e6a596c8d',
          'Lemma.Applications.Notebook.packageControlCharacter': '922930b41c915c42450b5a3d098efd6b3a8ed71eab6b672f9b9415c2c0cfed4b',
          'Lemma.Applications.Notebook.pumpOpenPackageCourse': '5e10f22d7d05f72a1d405fbd49e505f2e92243b3611a658c0d5f277086a06e2d',
          'Lemma.Applications.Notebook.savePackageWorkspace': '9f8ddf5cb2308c73ab89973e0d1cb84cec07d7721e237197b5cb8b5ce5931a64',
          'Lemma.Courses.PackageBinding.captureField': '893e3bc9e1e5314dd7238eb52387a1235db34fd656be74e562bc82bf6b4ade53',
          'Lemma.Courses.WorkspaceCodec.clearStep': '8ca36cec1b3cbabd20ad0ffea6fc0489f87ae096bbcb6be243a9ea75789f95bb',
          'Lemma.Courses.WorkspaceCodec.countStep': '917580262d359930493dbaa4c4f9c55301f554cfc828e0b1bf00d68e80649ba7',
          'Lemma.Courses.WorkspaceCodec.decode': '864120473f3511296777eae19f999f6e24f22e169c4ad29180dcf57e41965a96',
          'Lemma.Courses.WorkspaceCodec.decodeStep': '5bf1baf55cc935d9d7a18da6d5229971ac1fe3d3facfc0fde9811ebe25110eaf',
          'Lemma.Courses.WorkspaceCodec.encode': '6868e1dd65a18e055e152a608bd4445c08de1cf223af9c21721487fc3423e4fd',
          'Lemma.Courses.WorkspaceCodec.encodeStep': '0cc6a9b8c25e10f19105f042b2d8d71405c6c78cb7965392e6c1d29bc77c7eb8',
          'Lemma.Courses.WorkspaceCodec.headerBytes': 'd3821417ededd261ff4fed42c64dcb72babe611f178e6439e42c8275e8c350a0',
          'Lemma.Courses.WorkspaceCodec.magic': '8a9d9524b9573a246e365220aff7f59b2e2bdce42cdd09339736258276999751',
          'Lemma.Courses.WorkspaceCodec.maximumBytes': '5c84638d79927dbbcf5ce94c5fd9351073167274eaf61bd25753bc00102ec4b9',
          'Lemma.Courses.WorkspaceCodec.read': '5599e755c7ee70e89aea93fc63e5fbf1bc81fb3ccd1bcf934da416867db98677',
          'Lemma.Courses.WorkspaceCodec.recordLength': '39884f8c29c5dbe115889a5a0512fc204e8a9abe6894209bc47453f3411776c7',
          'Lemma.Courses.WorkspaceCodec.separate': '578b6998d045310b488ccd5307be855b483d75828448fa0f4570ce835d475d57',
          'Lemma.Courses.WorkspaceCodec.version': '190b92608d387b74ef344553ce04f931e877ab14721a8cebc906354671cef0a6',
          'Lemma.Courses.WorkspaceCodec.write': 'e92333a3b49f0dea98d6dde9f5fbaa1740377f02ac65f7e11ae1fd45d75f18db'},
 'pre': {'Lemma.Applications.Notebook.cancelPackageWork': '2911258bbaca4b52db8d13a30900a12488cc70f5f325093606015d161d135bb4',
         'Lemma.Applications.Notebook.openPackageCourse': '35813501e413339962ede6f9117234d3839d71c1d4b07b67d46fa70759192ea3',
         'Lemma.Applications.Notebook.packageBusy': '845b6d19785d0f484f2fc1e4aa7eae3d4d561e2ca5d42080dd61b38f3e1045e3',
         'Lemma.Applications.Notebook.pumpOpenPackageCourse': 'bd4c68624315bf4cabb3e51d2663388badae7a569fda778d50eef602558c3d5d',
         'Lemma.Applications.Notebook.savePackageWorkspace': '8ba1b1003e410ba6461a2f77b3cae99c4d472383781686fa399c8c75842d879a',
         'Lemma.Courses.WorkspaceCodec.clearStep': 'd01fd4d7c7c46a437acde9cb678441fb2fd033b02bf89acf9c7d4a94effa07d6',
         'Lemma.Courses.WorkspaceCodec.countStep': 'd31031688eaccbcdfd4ff699d97cbc631a6ceb0604326d2d2f22f535402c6c0e',
         'Lemma.Courses.WorkspaceCodec.decode': 'e67748e3f55b659966c599cb8b0c0f01d00e062dbde18f37fd2a47e4c9ba25b6',
         'Lemma.Courses.WorkspaceCodec.decodeStep': '681acaac3609cd23b6dda914270666cee5ad44c26bac8a1d4df197f6f424128e',
         'Lemma.Courses.WorkspaceCodec.encode': '154f06621734d7ea05b52288d5e5a3907ff95c22f34fb19cb2b768f7d38cb648',
         'Lemma.Courses.WorkspaceCodec.encodeStep': '800dddd619aae5e9638e7e072836b7c032cf3ebda41bee0c27f1d9541ae65373',
         'Lemma.Courses.WorkspaceCodec.headerBytes': 'd3821417ededd261ff4fed42c64dcb72babe611f178e6439e42c8275e8c350a0',
         'Lemma.Courses.WorkspaceCodec.magic': '8a9d9524b9573a246e365220aff7f59b2e2bdce42cdd09339736258276999751',
         'Lemma.Courses.WorkspaceCodec.maximumBytes': '5c84638d79927dbbcf5ce94c5fd9351073167274eaf61bd25753bc00102ec4b9',
         'Lemma.Courses.WorkspaceCodec.read': 'a4c631d66990cfcb96ad5591924830963831a4a95e9699b9134430ae7e38379c',
         'Lemma.Courses.WorkspaceCodec.recordLength': '7897fae73f2d9f6d2b7b086eff2b367fd3105bc1ae2770afaae54e06a5cdc661',
         'Lemma.Courses.WorkspaceCodec.separate': '8e3752e720e79a0beb3b269c49cd02b527763abeaa1f006bf6212884ee9893aa',
         'Lemma.Courses.WorkspaceCodec.version': '190b92608d387b74ef344553ce04f931e877ab14721a8cebc906354671cef0a6',
         'Lemma.Courses.WorkspaceCodec.write': '0be53b7941d7720965c524c6d036748a7399884a3df606a6af69935da50b31be'}}
WORKSPACE_CALLERS = {'post': {'Lemma.Courses.PackageWorkspace.object': ['Lemma.Applications.Notebook.openPackageCourse',
                                                    'Lemma.Applications.Notebook.pumpOpenPackageCourse',
                                                    'Lemma.Applications.Notebook.savePackageWorkspace'],
          'Lemma.Courses.PackageWorkspace.validate': ['Lemma.Applications.Notebook.adoptPackageWorkspace',
                                                      'Lemma.Applications.Notebook.beginPackageArithmetic',
                                                      'Lemma.Applications.Notebook.pumpOpenPackageCourse',
                                                      'Lemma.Applications.Notebook.stagePackageExercise',
                                                      'Lemma.Courses.PackageWorkspace.validateOwned',
                                                      'Lemma.Courses.WorkspaceCodec.decode',
                                                      'Lemma.Courses.WorkspaceCodec.encode'],
          'Lemma.Courses.WorkspaceCodec.clearStep': ['Lemma.Courses.WorkspaceCodec.encode'],
          'Lemma.Courses.WorkspaceCodec.countStep': ['Lemma.Courses.WorkspaceCodec.decode'],
          'Lemma.Courses.WorkspaceCodec.decode': ['Lemma.Applications.Notebook.pumpOpenPackageCourse'],
          'Lemma.Courses.WorkspaceCodec.decodeStep': ['Lemma.Courses.WorkspaceCodec.decode'],
          'Lemma.Courses.WorkspaceCodec.encode': ['Lemma.Applications.Notebook.savePackageWorkspace'],
          'Lemma.Courses.WorkspaceCodec.encodeStep': ['Lemma.Courses.WorkspaceCodec.encode'],
          'Lemma.Courses.WorkspaceCodec.headerBytes': [],
          'Lemma.Courses.WorkspaceCodec.magic': [],
          'Lemma.Courses.WorkspaceCodec.maximumBytes': [],
          'Lemma.Courses.WorkspaceCodec.read': ['Lemma.Courses.WorkspaceCodec.countStep',
                                                'Lemma.Courses.WorkspaceCodec.decode',
                                                'Lemma.Courses.WorkspaceCodec.decodeStep',
                                                'Lemma.Courses.WorkspaceCodec.encodeStep',
                                                'Lemma.Courses.WorkspaceCodec.recordLength'],
          'Lemma.Courses.WorkspaceCodec.recordLength': ['Lemma.Applications.Notebook.pumpOpenPackageCourse',
                                                        'Lemma.Courses.WorkspaceCodec.decode'],
          'Lemma.Courses.WorkspaceCodec.separate': ['Lemma.Courses.WorkspaceCodec.decode',
                                                    'Lemma.Courses.WorkspaceCodec.encode'],
          'Lemma.Courses.WorkspaceCodec.version': [],
          'Lemma.Courses.WorkspaceCodec.write': ['Lemma.Courses.WorkspaceCodec.clearStep',
                                                 'Lemma.Courses.WorkspaceCodec.decodeStep',
                                                 'Lemma.Courses.WorkspaceCodec.encode',
                                                 'Lemma.Courses.WorkspaceCodec.encodeStep']},
 'pre': {'Lemma.Applications.Notebook.packageBytes': ['Lemma.Applications.Notebook.packageAllocateStep',
                                                      'Lemma.Applications.Notebook.packageConfigureStep',
                                                      'Lemma.Applications.Notebook.packageControlPress',
                                                      'Lemma.Applications.Notebook.pumpOpenPackageCourse',
                                                      'Lemma.Applications.Notebook.pumpPackageRead',
                                                      'Lemma.Applications.Notebook.renderPackageText',
                                                      'Lemma.Applications.Notebook.stagePackageExercise',
                                                      'Lemma.Applications.Notebook.stagePackagePress.stage'],
         'Lemma.Applications.Notebook.packageWorkspace': ['Lemma.Applications.Notebook.adoptPackageStep',
                                                          'Lemma.Applications.Notebook.adoptPackageWorkspace',
                                                          'Lemma.Applications.Notebook.beginPackageArithmetic',
                                                          'Lemma.Applications.Notebook.finishOpenPackageCourse',
                                                          'Lemma.Applications.Notebook.finishOpenPackageCourse.restoreSelection',
                                                          'Lemma.Applications.Notebook.savePackageWorkspace',
                                                          'Lemma.Applications.Notebook.stagePackageCompletion',
                                                          'Lemma.Applications.Notebook.stagePackageExercise',
                                                          'Lemma.Applications.Notebook.stagePackagePress.stage'],
         'Lemma.Courses.PackageFormat.malformed': ['Lemma.Courses.PackageBinding.capture',
                                                   'Lemma.Courses.PackageBinding.fieldsValid',
                                                   'Lemma.Courses.PackageBinding.validate',
                                                   'Lemma.Courses.PackageFormat.referenceStatus',
                                                   'Lemma.Courses.PackageReader.accept',
                                                   'Lemma.Courses.PackageReader.beginPiece',
                                                   'Lemma.Courses.PackageReader.cancel',
                                                   'Lemma.Courses.PackageReader.configuration',
                                                   'Lemma.Courses.PackageReader.finish',
                                                   'Lemma.Courses.PackageReader.pollPiece',
                                                   'Lemma.Courses.PackageReader.start',
                                                   'Lemma.Courses.PackageReader.step',
                                                   'Lemma.Courses.PackageRender.prepare',
                                                   'Lemma.Courses.PackageRender.prepareHeader',
                                                   'Lemma.Courses.PackageRender.renderDelta',
                                                   'Lemma.Courses.PackageRender.renderHeaderSelectedDelta',
                                                   'Lemma.Courses.PackageRender.renderSelectedDelta',
                                                   'Lemma.Courses.PackageTarget.reservedStep',
                                                   'Lemma.Courses.PackageTarget.validate',
                                                   'Lemma.Courses.PackageTarget.validateBody',
                                                   'Lemma.Courses.PackageTarget.validateEntry',
                                                   'Lemma.Courses.PackageTarget.validateSpan',
                                                   'Lemma.Courses.PackageWorkspace.captureSelection',
                                                   'Lemma.Courses.PackageWorkspace.create',
                                                   'Lemma.Courses.PackageWorkspace.equalEventsStep',
                                                   'Lemma.Courses.PackageWorkspace.equalHistoryStep',
                                                   'Lemma.Courses.PackageWorkspace.equalSubmissionStep',
                                                   'Lemma.Courses.PackageWorkspace.equalWordsStep',
                                                   'Lemma.Courses.PackageWorkspace.snapshotSelection',
                                                   'Lemma.Courses.PackageWorkspace.stageCompleted',
                                                   'Lemma.Courses.PackageWorkspace.stageCompletedUnknown',
                                                   'Lemma.Courses.PackageWorkspace.stageRefresh',
                                                   'Lemma.Courses.PackageWorkspace.stageUnknownSelection',
                                                   'Lemma.Courses.PackageWorkspace.transitionBase',
                                                   'Lemma.Courses.PackageWorkspace.validate',
                                                   'Lemma.Courses.PackageWorkspace.validateAttempt',
                                                   'Lemma.Courses.PackageWorkspace.validateSelection',
                                                   'Lemma.Courses.PackageWorkspace.zeroCheck',
                                                   'Lemma.Courses.WorkspaceCodec.decode',
                                                   'Lemma.Courses.WorkspaceCodec.decodeStep',
                                                   'Lemma.Courses.WorkspaceCodec.encode',
                                                   'Lemma.Courses.WorkspaceCodec.recordLength'],
         'Lemma.Courses.PackageFormat.unsupported': ['Lemma.Courses.PackageBinding.capture',
                                                     'Lemma.Courses.PackageBinding.fieldsValid',
                                                     'Lemma.Courses.PackageBinding.validate',
                                                     'Lemma.Courses.PackageFormat.referenceStatus',
                                                     'Lemma.Courses.PackageRender.prepare',
                                                     'Lemma.Courses.PackageRender.prepareHeader',
                                                     'Lemma.Courses.PackageTarget.textStep',
                                                     'Lemma.Courses.PackageTarget.validate',
                                                     'Lemma.Courses.PackageWorkspace.create',
                                                     'Lemma.Courses.PackageWorkspace.transitionBase',
                                                     'Lemma.Courses.PackageWorkspace.validate',
                                                     'Lemma.Courses.WorkspaceCodec.decode',
                                                     'Lemma.Courses.WorkspaceCodec.recordLength'],
         'Lemma.Courses.PackageWorkspace.bytes': ['Lemma.Applications.Notebook.pumpOpenPackageCourse',
                                                  'Lemma.Courses.PackageWorkspace.captureSelection',
                                                  'Lemma.Courses.PackageWorkspace.create',
                                                  'Lemma.Courses.PackageWorkspace.shape',
                                                  'Lemma.Courses.PackageWorkspace.snapshotSelection',
                                                  'Lemma.Courses.PackageWorkspace.stageCompleted',
                                                  'Lemma.Courses.PackageWorkspace.transitionBase',
                                                  'Lemma.Courses.PackageWorkspace.validate',
                                                  'Lemma.Courses.WorkspaceCodec.decode',
                                                  'Lemma.Courses.WorkspaceCodec.encode',
                                                  'Lemma.Courses.WorkspaceCodec.recordLength'],
         'Lemma.Courses.PackageWorkspace.magic': ['Lemma.Applications.Notebook.adoptPackageWorkspace',
                                                  'Lemma.Applications.Notebook.pumpOpenPackageCourse',
                                                  'Lemma.Courses.PackageWorkspace.create',
                                                  'Lemma.Courses.PackageWorkspace.stageCompleted',
                                                  'Lemma.Courses.PackageWorkspace.stageCompletedUnknown',
                                                  'Lemma.Courses.PackageWorkspace.stageRefresh',
                                                  'Lemma.Courses.PackageWorkspace.stageUnknownSelection',
                                                  'Lemma.Courses.PackageWorkspace.validate',
                                                  'Lemma.Courses.WorkspaceCodec.recordLength'],
         'Lemma.Courses.PackageWorkspace.object': ['Lemma.Applications.Notebook.openPackageCourse',
                                                   'Lemma.Applications.Notebook.pumpOpenPackageCourse',
                                                   'Lemma.Applications.Notebook.savePackageWorkspace'],
         'Lemma.Courses.PackageWorkspace.validate': ['Lemma.Applications.Notebook.adoptPackageWorkspace',
                                                     'Lemma.Applications.Notebook.beginPackageArithmetic',
                                                     'Lemma.Applications.Notebook.pumpOpenPackageCourse',
                                                     'Lemma.Applications.Notebook.stagePackageExercise',
                                                     'Lemma.Courses.PackageWorkspace.validateOwned',
                                                     'Lemma.Courses.WorkspaceCodec.decode',
                                                     'Lemma.Courses.WorkspaceCodec.encode'],
         'Lemma.Courses.WorkspaceCodec.clearStep': ['Lemma.Courses.WorkspaceCodec.encode'],
         'Lemma.Courses.WorkspaceCodec.countStep': ['Lemma.Courses.WorkspaceCodec.decode'],
         'Lemma.Courses.WorkspaceCodec.decode': ['Lemma.Applications.Notebook.pumpOpenPackageCourse'],
         'Lemma.Courses.WorkspaceCodec.decodeStep': ['Lemma.Courses.WorkspaceCodec.decode'],
         'Lemma.Courses.WorkspaceCodec.encode': ['Lemma.Applications.Notebook.savePackageWorkspace'],
         'Lemma.Courses.WorkspaceCodec.encodeStep': ['Lemma.Courses.WorkspaceCodec.encode'],
         'Lemma.Courses.WorkspaceCodec.headerBytes': ['Lemma.Courses.WorkspaceCodec.decode',
                                                      'Lemma.Courses.WorkspaceCodec.decodeStep',
                                                      'Lemma.Courses.WorkspaceCodec.encode',
                                                      'Lemma.Courses.WorkspaceCodec.encodeStep',
                                                      'Lemma.Courses.WorkspaceCodec.recordLength'],
         'Lemma.Courses.WorkspaceCodec.magic': ['Lemma.Courses.WorkspaceCodec.decode',
                                                'Lemma.Courses.WorkspaceCodec.encode',
                                                'Lemma.Courses.WorkspaceCodec.recordLength'],
         'Lemma.Courses.WorkspaceCodec.maximumBytes': ['Lemma.Courses.WorkspaceCodec.decode',
                                                       'Lemma.Courses.WorkspaceCodec.encode',
                                                       'Lemma.Courses.WorkspaceCodec.recordLength'],
         'Lemma.Courses.WorkspaceCodec.read': ['Lemma.Courses.WorkspaceCodec.countStep',
                                               'Lemma.Courses.WorkspaceCodec.decode',
                                               'Lemma.Courses.WorkspaceCodec.decodeStep',
                                               'Lemma.Courses.WorkspaceCodec.encodeStep',
                                               'Lemma.Courses.WorkspaceCodec.recordLength'],
         'Lemma.Courses.WorkspaceCodec.recordLength': ['Lemma.Applications.Notebook.pumpOpenPackageCourse',
                                                       'Lemma.Courses.WorkspaceCodec.decode'],
         'Lemma.Courses.WorkspaceCodec.separate': ['Lemma.Courses.WorkspaceCodec.decode',
                                                   'Lemma.Courses.WorkspaceCodec.encode'],
         'Lemma.Courses.WorkspaceCodec.version': ['Lemma.Courses.WorkspaceCodec.encode',
                                                  'Lemma.Courses.WorkspaceCodec.recordLength'],
         'Lemma.Courses.WorkspaceCodec.write': ['Lemma.Courses.WorkspaceCodec.clearStep',
                                                'Lemma.Courses.WorkspaceCodec.decodeStep',
                                                'Lemma.Courses.WorkspaceCodec.encode',
                                                'Lemma.Courses.WorkspaceCodec.encodeStep']}}
