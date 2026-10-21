#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check actual SRAM endpoint repair against original Liberty and all physical ports.

This admits only buffer/delay/inverter paths to the same original logical
driver boundary, with equal polarity. It is not full netlist equivalence, LVS,
timing, or permission to change any BIST, supply, output, clock, or bit identity.
Run inside the pinned OpenROAD Python interpreter on separate read-only ODBs.
"""
from pathlib import Path
import hashlib
import json
import re
import time


def card(text, kind, name):
    match = re.search(r'\b' + kind + r'\s*\(\s*' + re.escape(name) + r'\s*\)\s*\{', text)
    if not match:
        raise ValueError('Missing original Liberty card: ' + name)
    start, depth = match.end(), 1
    for at in range(start, len(text)):
        depth += (text[at] == '{') - (text[at] == '}')
        if not depth:
            return text[start:at]
    raise ValueError('Unterminated original Liberty card')


def buffer_kind(kind, liberty):
    if re.fullmatch(r'sg13g2_(?:buf_\d+|dlygate4sd[123]_1)', kind):
        pin, function, sense, inverted = 'X', 'A', 'positive_unate', 0
    elif re.fullmatch(r'sg13g2_inv_\d+', kind):
        pin, function, sense, inverted = 'Y', '!(A)', 'negative_unate', 1
    else:
        return None
    cell = card(liberty, 'cell', kind)
    output = card(cell, 'pin', pin)
    actual = re.findall(r'\bfunction\s*:\s*"([^"]+)"', output)
    senses = re.findall(r'\btiming_sense\s*:\s*(\w+)', output)
    if (actual != [function] or not senses or any(x != sense for x in senses)
            or not re.search(r'direction\s*:\s*"?output"?\s*;', output)
            or not re.search(r'direction\s*:\s*"?input"?\s*;', card(cell, 'pin', 'A'))):
        raise ValueError('Original buffer function/unateness differs: ' + kind)
    return pin, inverted


def repairable_signal_input(name, direction):
    """Only original data/address/enables may acquire proved repair chains."""
    return direction == 'INPUT' and re.fullmatch(
        r'A_(?:DIN\[\d+\]|ADDR\[\d+\]|MEN|REN|WEN)', name) is not None


def assess(before_path, after_path, liberty_path, output):
    import odb
    started = time.monotonic()
    before_path, after_path, liberty_path, output = map(Path, (before_path, after_path, liberty_path, output))
    inputs = [Path(__file__), before_path, after_path, liberty_path]
    identities = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    liberty = liberty_path.read_text()
    dbs = [odb.dbDatabase.create(), odb.dbDatabase.create()]
    for db, path in zip(dbs, (before_path, after_path)):
        odb.read_db(db, str(path.resolve()))
    before, after = [db.getChip().getBlock() for db in dbs]
    kinds = {}

    def trace(net):
        buffers, inverted, seen = [], 0, set()
        for _ in range(128):
            if net is None or net.getName() in seen:
                raise ValueError('Unconnected/cyclic repair path')
            seen.add(net.getName())
            ports = [p.getName() for p in net.getBTerms() if p.getIoType() == 'INPUT']
            drivers = [p for p in net.getITerms() if p.getMTerm().getIoType() == 'OUTPUT']
            if ports:
                if len(ports) != 1 or drivers:
                    raise ValueError('Ambiguous input driver')
                return ['port', ports[0]], inverted, buffers
            if len(drivers) != 1:
                raise ValueError('Ambiguous/missing driver')
            term = drivers[0]
            inst = term.getInst()
            kind = inst.getMaster().getName()
            if kind not in kinds:
                kinds[kind] = buffer_kind(kind, liberty)
            rule = kinds[kind]
            if rule is None:
                return [inst.getName(), term.getMTerm().getName(), kind], inverted, buffers
            pin, flip = rule
            if term.getMTerm().getName() != pin:
                raise ValueError('Unexpected buffer output')
            signal_inputs = [p for p in inst.getITerms() if p.getMTerm().getSigType() == 'SIGNAL' and p.getMTerm().getIoType() == 'INPUT']
            if len(signal_inputs) != 1 or signal_inputs[0].getMTerm().getName() != 'A':
                raise ValueError('Unexpected buffer input')
            buffers.append([inst.getName(), kind, net.getName()])
            inverted ^= flip
            net = signal_inputs[0].getNet()
        raise ValueError('Repair depth bound')

    def port_map(block):
        return {p.getName(): [p.getSigType(), p.getIoType(), p.getNet().getName(), sorted(
            (b.getTechLayer().getName(), b.xMin(), b.yMin(), b.xMax(), b.yMax())
            for pin in p.getBPins() for b in pin.getBoxes())] for p in block.getBTerms()}

    expected_ports = port_map(before)
    for name, kind in [('VDDlogic', 'POWER'), ('VDDARRAY', 'POWER'), ('VSS', 'GROUND')]:
        value = expected_ports.get(name)
        if not value or value[:3] != [kind, 'INOUT', name] or not value[3]:
            raise ValueError('Original required supply port malformed: ' + name)
    def validate():
        if len(expected_ports) != 668 or port_map(after) != expected_ports:
            raise ValueError('Original668 signal/supply ports changed')
        changed, exact = [], 0
        for lane in range(3):
            a, b = [block.findInst(f'pen_sram_lane{lane}') for block in (before, after)]
            if not a or not b or len(a.getITerms()) != 349 or len(b.getITerms()) != 349:
                raise ValueError('Original SRAM terminal inventory changed')
            for ta in a.getITerms():
                name = ta.getMTerm().getName()
                tb = b.findITerm(name)
                if not tb or tb.getMTerm().getIoType() != ta.getMTerm().getIoType():
                    raise ValueError('Original SRAM terminal identity changed')
                na, nb = ta.getNet(), tb.getNet()
                old, new = na.getName() if na else None, nb.getName() if nb else None
                if old == new:
                    exact += 1
                    continue
                if not repairable_signal_input(name, ta.getMTerm().getIoType()):
                    raise ValueError('Changed BIST/supply/output/clock or unsupported pin: ' + name)
                src, dst = trace(na), trace(nb)
                if src[:2] != dst[:2]:
                    raise ValueError('Original logical driver/bit/polarity changed: ' + name)
                changed.append(dict(lane=lane, pin=name, before_net=old, after_net=new,
                                    driver=src[0], inverted=src[1], before_chain=src[2], after_chain=dst[2]))
        return exact, changed

    exact, changed = validate()
    negatives = []
    inst = after.findInst('pen_sram_lane0')
    for label, term, replacement in [
            ('literal_data_bit_swap', inst.findITerm('A_DIN[32]'), inst.findITerm('A_DIN[33]').getNet()),
            ('read_enable_driver_swap', inst.findITerm('A_REN'), inst.findITerm('A_WEN').getNet()),
            ('array_supply_retarget', inst.findITerm('VDDARRAY!'), after.findNet('VSS')),
            ('BIST_disconnect', inst.findITerm('A_BIST_DIN[32]'), None)]:
        saved = term.getNet()
        term.disconnect()
        if replacement:
            term.connect(replacement)
        try:
            validate()
            raise AssertionError('Actual negative accepted: ' + label)
        except ValueError as error:
            negatives.append(dict(case=label, result='REJECTED', reason=str(error)))
        term.disconnect()
        term.connect(saved)
    odb.dbBTerm_destroy(after.findBTerm('VDDARRAY'))
    try:
        validate()
        raise AssertionError('Actual deleted supply port accepted')
    except ValueError as error:
        negatives.append(dict(case='actual_supply_port_delete', result='REJECTED', reason=str(error)))
    report = dict(schema='lemma-sram-buffered-endpoints/1', status='PASS_ORIGINAL_LIB_BUFFERED_INPUTS_ALL668_PORTS_AND_ACTUAL_NEGATIVES',
        scope=__doc__, inputs=identities, exact_terminal_net_names=exact, changed_inputs=changed,
        buffer_functions={k: v for k, v in kinds.items() if v is not None}, negative_cases=negatives,
        source_seal_equal=all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == v for p, v in identities.items()),
        seconds=time.monotonic() - started)
    output.write_text(json.dumps(report, indent=2) + '\n')
    return report
