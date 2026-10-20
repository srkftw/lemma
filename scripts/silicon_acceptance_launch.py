#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""One source-bound acceptance launch ECO on the completed powered pen layout.

Run in the pinned OpenROAD Python interpreter. This proves the exact one-buffer
endpoint relation and unchanged placement, ports, power shapes and obstructions.
It does not prove process DRC, routed connectivity, parasitics or timing.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from silicon_buffered_pins import buffer_kind

SOURCE_ODB = '92c0e300a753a500d79ea4799e30953887bb98baf5b8972863a7580505be95bc'
LIBERTY = '7677a8918689f452e80405ad16a83e744709342574f2aedcc507c2758986b396'
INSTANCE = 'task009_accept_launch'
DRIVER = ('_08961_', 'Y')
OLD_NET = '_03226_'
NEW_NET = 'task009_accept_driver'
LOCATION = (558720, 260820)


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(block):
    terms, instances, ports = {}, {}, {}
    for inst in block.getInsts():
        instances[inst.getName()] = (inst.getMaster().getName(), inst.getOrient(), tuple(inst.getLocation()))
        for term in inst.getITerms():
            terms[(inst.getName(), term.getMTerm().getName())] = (
                term.getNet().getName() if term.getNet() else None,
                sorted((layer.getName(), box.xMin(), box.yMin(), box.xMax(), box.yMax())
                       for layer, box in term.getGeometries()))
    for term in block.getBTerms():
        ports[term.getName()] = (term.getNet().getName(), term.getIoType(), term.getSigType(),
            sorted((box.getTechLayer().getName(), box.xMin(), box.yMin(), box.xMax(), box.yMax())
                   for pin in term.getBPins() for box in pin.getBoxes()))
    power = []
    for name in ('VDDlogic', 'VDDARRAY', 'VSS'):
        for wire in block.findNet(name).getSWires():
            for box in wire.getWires():
                if box.isVia():
                    via = box.getBlockVia() or box.getTechVia()
                    x, y = box.getViaXY()
                    for shape in via.getBoxes():
                        power.append((name, shape.getTechLayer().getName(), shape.xMin() + x,
                                      shape.yMin() + y, shape.xMax() + x, shape.yMax() + y))
                else:
                    power.append((name, box.getTechLayer().getName(), box.xMin(), box.yMin(), box.xMax(), box.yMax()))
    obstructions = sorted((box.getBBox().getTechLayer().getName(), box.getBBox().xMin(),
                           box.getBBox().yMin(), box.getBBox().xMax(), box.getBBox().yMax())
                          for box in block.getObstructions())
    return terms, instances, ports, Counter(power), obstructions


def relation(before, block, liberty):
    after = snapshot(block)
    need(buffer_kind('sg13g2_buf_8', Path(liberty).read_text()) == ('X', 0), 'original Lib buffer function differs')
    expected = before[0].copy()
    expected[DRIVER] = (NEW_NET, before[0][DRIVER][1])
    need({key: value for key, value in after[0].items() if key[0] != INSTANCE} == expected,
         'old terminal net or geometry changed')
    need({key: value for key, value in after[1].items() if key != INSTANCE} == before[1],
         'old master, placement or orientation changed')
    need(after[2:] == before[2:], 'physical port, power shape or obstruction changed')
    added = block.findInst(INSTANCE)
    need(added and added.getMaster().getName() == 'sg13g2_buf_8' and
         tuple(added.getLocation()) == LOCATION and added.getOrient() == before[1][DRIVER[0]][1],
         'launch master/site/orientation differs')
    actual = {pin.getMTerm().getName(): pin.getNet().getName() if pin.getNet() else None for pin in added.getITerms()}
    need(actual == {'A': NEW_NET, 'X': OLD_NET, 'VDD': 'VDDlogic', 'VSS': 'VSS'}, 'launch signal or supply binding differs')
    need({(pin.getInst().getName(), pin.getMTerm().getName()) for pin in block.findNet(NEW_NET).getITerms()} ==
         {DRIVER, (INSTANCE, 'A')} and not list(block.findNet(NEW_NET).getBTerms()), 'launch input net has extra endpoints')
    need(len(after[0]) == len(before[0]) + 4 and len(after[1]) == len(before[1]) + 1,
         'unexpected new cell or terminal')
    return {'old_terminals': len(before[0]), 'physical_ports': len(before[2]),
            'exact_PG_shapes': sum(before[3].values()), 'exact_obstructions': len(before[4]),
            'buffer_function': 'original Liberty X=A/positive_unate', 'site_DBU': list(LOCATION)}


def prepare(source, liberty, output):
    import odb
    started = time.monotonic()
    source, liberty, output = map(Path, (source, liberty, output))
    need(sha(source) == SOURCE_ODB and sha(liberty) == LIBERTY, 'reviewed layout/Lib source differs')
    output.mkdir()
    db = odb.dbDatabase.create()
    odb.read_db(db, str(source))
    block = db.getChip().getBlock()
    before = snapshot(block)
    need(len(before[0]) == 43648 and len(before[2]) == 668, 'completed46 source endpoints differ')
    driver = block.findInst(DRIVER[0])
    need(driver.getMaster().getName() == 'sg13g2_nand4_1' and driver.findITerm('Y').getNet().getName() == OLD_NET,
         'measured NAND4 driver differs')
    master = next((lib.findMaster('sg13g2_buf_8') for lib in db.getLibs() if lib.findMaster('sg13g2_buf_8')), None)
    need(master and master.getWidth() == 6240 and master.getHeight() == 3780, 'original buf8 geometry differs')
    added = odb.dbInst_create(block, master, INSTANCE)
    added.setOrient(driver.getOrient())
    added.setLocation(*LOCATION)
    added.setPlacementStatus('PLACED')
    newnet = odb.dbNet_create(block, NEW_NET)
    driver.findITerm('Y').disconnect()
    driver.findITerm('Y').connect(newnet)
    for pin, net in [('A', NEW_NET), ('X', OLD_NET), ('VDD', 'VDDlogic'), ('VSS', 'VSS')]:
        added.findITerm(pin).connect(block.findNet(net))
    wire = block.findNet(OLD_NET).getWire()
    if wire:
        odb.dbWire_destroy(wire)
    result = relation(before, block, liberty)
    negatives = []
    for pin, wrong, correct in [('A', 'VSS', NEW_NET), ('VDD', 'VSS', 'VDDlogic')]:
        term = added.findITerm(pin)
        term.disconnect()
        term.connect(block.findNet(wrong))
        try:
            relation(before, block, liberty)
        except ValueError:
            negatives.append('wrong_' + pin + '_binding_rejected')
        else:
            raise ValueError('negative accepted: ' + pin)
        term.disconnect()
        term.connect(block.findNet(correct))
    relation(before, block, liberty)
    odb.write_db(db, str(output / 'unrouted.odb'))
    odb.write_def(block, str(output / 'unrouted.def'))
    result.update(status='PASS_EXACT_ORIGINAL_LIB_LAUNCH_PRECURSOR_NOT_ROUTED', negatives=negatives,
                  source_ODB_sha256=sha(source), Liberty_sha256=sha(liberty),
                  unrouted_ODB_sha256=sha(output / 'unrouted.odb'), seconds=time.monotonic() - started)
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def assess(source, current, liberty, output):
    import odb
    source, current, liberty, output = map(Path, (source, current, liberty, output))
    need(sha(source) == SOURCE_ODB and sha(liberty) == LIBERTY, 'reviewed source differs')
    old = odb.dbDatabase.create()
    new = odb.dbDatabase.create()
    odb.read_db(old, str(source))
    odb.read_db(new, str(current))
    result = relation(snapshot(old.getChip().getBlock()), new.getChip().getBlock(), liberty)
    result.update(status='PASS_EXACT_ONE_BUFFER_ENDPOINT_POWER_GEOMETRY_RELATION',
                  scope=__doc__, source_ODB_sha256=sha(source), current_ODB_sha256=sha(current), Liberty_sha256=sha(liberty))
    output.write_text(json.dumps(result, indent=2) + '\n')
    return result
