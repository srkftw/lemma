#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""A real canonical notebook warm-reset, new writing/Save and cold reopen.

Host-only raw stimulus and offline observations. Warm readiness must come from
new UART bytes and a new completed controller redraw. Sample timestamps follow
actual MTIME; independently timestamped delivery follows monotone session time.
No historical timestamp is added to new samples to hide stale controller state.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import shutil
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_live_notebook import (Checker, Input, guest_events, idle, require, sha,
                                 visible_pixels)
from store_oracle import recover

RECORD = re.compile(rb'^K1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\r?$', re.M)


def suffix_records(path, offset):
    """Only complete records entirely after the pre-operation byte boundary."""
    data = Path(path).read_bytes()
    require(type(offset) is int and 0 <= offset <= len(data), 'UART output shrank across reset')
    return [tuple(int(word, 16) for word in row) for row in RECORD.findall(data[offset:])]


def dark_contact(panel, x, y):
    width, height, pixels = visible_pixels(panel)
    require((width, height) == (1650, 2200), 'controller geometry differs')
    require(2 <= x < width-2 and 2 <= y < height-2, 'contact observation outside panel')
    return any(pixels[(py*width+px)*3:(py*width+px)*3+3] == bytes(3)
               for py in range(y-2, y+3) for px in range(x-2, x+3))


class WarmChecker(Checker):
    profile = 'lemma-silicon-dev/0.3.0'
    backend = 'qemu'

    def __init__(self, args):
        require(args.disk.is_file() and args.disk.stat().st_size == 256*1024*1024,
                'provide an actual acknowledged 256 MiB medium')
        super().__init__(args)
        self.report['bounds']['disk'] = str(args.disk.resolve())
        self.report.update(schema='lemmasim-canonical-warm-notebook/1',
            scope='Actual Lean canonical notebook warm reset, raw pen resynchronization, '
                  'explicit Save and new durable-only cold reopen; ELF-preload development boot, '
                  'not whole-machine completion or physical qualification.',
            medium_source={'path': str(args.disk.resolve()), 'sha256': sha(args.disk)},
            raw_inputs=[], clock_relation='Delivery uses monotone session cycles; every raw sample '
                'timestamp uses actual 10MHz MTIME at the paused admission boundary. Warm reset '
                'must handle the reset MTIME domain without adding the old time to raw samples.')
        self.report['observer_sources'][str(Path(__file__).relative_to(ROOT))] = sha(__file__)
        self.report['normal_boot_diagnostic'] = {'tag':0xd3,
            'source':'Lemma/Kernel/Process.lean', 'source_sha256':sha(ROOT/'Lemma/Kernel/Process.lean'),
            'meaning':'successful Process.initialize reports root, satp and remaining frames; d4 reports a fault'}
        self.report['readiness_observation_quantum_cycles'] = 25000000
        self.report['readiness_observation_relation'] = ('250ms readiness observations; every guest/device cycle '
            'executes. This qualifies fresh boot records and display completion, not10ms boot latency.')

    def admit(self, session, stream, boundary=None):
        state = session.inspect()['machine'] if boundary is None else boundary
        base_tick, base_cycle = state['ticks'], state['cycle']
        for row in stream.events:
            require(row[1] >= base_tick, 'new raw sample timestamp predates its actual MTIME admission')
            request = {'action':'inject', 'kind':'pen',
                       'cycle':base_cycle+(row[1]-base_tick)*10,
                       'words':list(row[1:8])}
            self.report['raw_inputs'].append(request)
            session.control(request)
        return base_cycle+(stream.events[-1][1]-base_tick)*10

    def new_ready(self, session, uart_offset, cause):
        uart = session.directory/'uart-0.bin'
        completed_at_boundary = session.inspect()['machine']['devices']['paper']['completed']
        def ready(state):
            rows = suffix_records(uart, uart_offset)
            require(not any(row[0] in (0x41f, 0x424, 0xd4) for row in rows),
                    'new guest boot formatted, failed persistence or faulted')
            causes = [index for index, row in enumerate(rows) if row[0] == 0x442 and row[1] == cause]
            notebooks = [index for index, row in enumerate(rows) if row[0] == 0x420]
            return (causes and notebooks and min(causes) < min(notebooks) and idle(state)
                    and state['devices']['paper']['completed'] > completed_at_boundary)
        start = time.monotonic()
        state = session.wait(ready, self.args.boot_seconds, quantum=25000000)
        return {'state':state, 'records':suffix_records(uart, uart_offset),
                'host_seconds':time.monotonic()-start, 'uart_start_byte':uart_offset,
                'paper_completed_at_boundary':completed_at_boundary}

    def execute(self):
        disk = self.directory/'notebook.raw'
        with self.args.disk.open('rb') as source, disk.open('xb') as destination:
            shutil.copyfileobj(source, destination, 1024*1024)
        root, sequence, records = recover(disk.read_bytes())
        require(sequence > 0 and records, 'source medium has no independently readable acknowledged objects')
        self.report['source_records'] = {'sequence':sequence, 'generation':root.generation,
                                         'objects':len(records)}
        live = self.session('live', disk)
        self.report['identity'] = live.identity
        self.report['cold_boot'] = self.new_ready(live, 0, 1)
        # Declared ordinary idle execution ages the MTIME domain beyond the
        # one-second contact watchdog before reset. The shorter Loader boot
        # must not accidentally hide stale-time or watchdog-origin behavior.
        aged_before = live.inspect()['machine']
        live.run(200000000)
        aged_after = live.wait(idle, self.args.action_seconds)
        self.report['prewarm_clock_age'] = {'requested_cycles':200000000,
                                           'before':aged_before, 'after':aged_after}
        initial_panel, initial_medium = live.export('before-held')
        durable_before = sha(initial_medium)
        require(durable_before == self.report['medium_source']['sha256'],
                'ordinary cold open changed the acknowledged medium')

        # A release is consumed first. The sole subsequent queued input is an
        # actual held contact, so count1/head_sequence proves the pending head.
        state = live.inspect()['machine']
        release = Input(1650, 2200, state['ticks']+10000, 100000, 0)
        release.sample(1100, 1600, 0, False)
        delivery = self.admit(live, release, state)
        live.run(delivery-state['cycle']+100000)
        live.wait(idle, self.args.action_seconds, quantum=100000)
        state = live.inspect()['machine']
        require(state['devices']['pen']['loss'] == 0, 'release did not leave a controller ready for contact admission')
        contact = Input(1650, 2200, state['ticks']+10000, 100000, 0)
        contact.sample(1100, 1600, 2048, True)
        delivery = self.admit(live, contact, state)
        # Fast inspection reports ceil(virtual_ns/10), while a bounded run
        # advances from the actual nanosecond phase. Reach the absolute raw
        # delivery boundary rather than stopping a partial cycle before it.
        remaining_cycles = (delivery*10-state['virtual_ns']+9)//10
        live.run(remaining_cycles)
        pending = live.inspect()['machine']
        self.report['held_cutpoint'] = {'state':pending, 'before':state,
                                       'sample':contact.events[0],
                                       'delivery_cycle':delivery,
                                       'requested_cycles':remaining_cycles,
                                       'before_phase_ns':state['virtual_ns']%10,
                                       'after_phase_ns':pending['virtual_ns']%10}
        require(pending['devices']['pen']['count'] == 1 and
                pending['devices']['pen']['head_sequence'] > 0 and
                not pending['devices']['pen']['resync'],
                'held contact was not paused at its real queued controller head')
        uart = live.directory/'uart-0.bin'
        uart_offset = uart.stat().st_size
        live.control({'action':'warm-reset'})
        self.report['warm_immediate'] = live.inspect()['machine']
        self.report['warm_boot'] = self.new_ready(live, uart_offset, 2)
        warm = live.inspect()['machine']
        require(warm['devices']['power']['reset_cause'] == 2, 'actual controller warm cause missing')
        warm_panel, warm_medium = live.export('after-warm')
        require(sha(warm_medium) == durable_before,
                'warm reset secretly published the queued contact or flushed storage')
        require(visible_pixels(warm_panel) == visible_pixels(initial_panel),
                'queued unconsumed held input survived the genuine warm redraw')

        # All new timestamps are deliberately in the reset MTIME domain.
        # Delivery stays in the monotone external-event clock domain.
        writing = Input(1650, 2200, warm['ticks']+10000, 100000, 0)
        writing.sample(825, 160, 0, False)
        writing.stroke('after actual warm reset', 1, 1, 6, 1700)
        first = writing.events[1]
        x,y = first[2]*1649//65535, first[3]*2199//65535
        require(not dark_contact(warm_panel, x, y), 'selected new stroke contact was already dark before writing')
        completed_before = warm['devices']['paper']['completed']
        probe = self.directory/'new-contact.ppm'
        delivery = self.admit(live, writing, warm)
        def rendered(state):
            if not idle(state) or state['cycle'] < delivery+20000000 or state['devices']['paper']['completed'] <= completed_before:
                return False
            live.control({'action':'panel', 'path':str(probe)})
            return dark_contact(probe, x, y)
        new_ink = live.wait(rendered, self.args.action_seconds, quantum=1000000)
        self.report['new_ink'] = {'state':new_ink, 'contact':[x,y],
                                  'controller_pixels_sha256':sha(probe)}

        # Separate Save from writing so its new UART acknowledgements and new
        # controller completion cannot be satisfied by the old stroke update.
        state = live.inspect()['machine']
        completed_before_save = state['devices']['paper']['completed']
        save_offset = uart.stat().st_size
        save = Input(1650, 2200, state['ticks']+10000, 100000, 0)
        save.tool(7, 'explicit Save after warm reset')
        save_delivery = self.admit(live, save, state)
        def saved(state):
            rows = suffix_records(uart, save_offset)
            require(not any(row[0] == 0x424 for row in rows), 'post-warm persistence failed')
            acknowledgements = [row for row in rows if row[0] in (0x421, 0x423, 0x424)]
            return (any(row[0] == 0x423 for row in acknowledgements) and acknowledgements
                    and acknowledgements[-1][0] == 0x421 and idle(state)
                    and state['cycle'] >= save_delivery+20000000
                    and state['devices']['paper']['completed'] > completed_before_save)
        saved_state = live.wait(saved, self.args.action_seconds, quantum=1000000)
        saved_panel, saved_medium = live.export('saved-after-warm')
        _, saved_sequence, _ = recover(saved_medium.read_bytes())
        save_rows = suffix_records(uart, save_offset)
        acknowledged = [row for row in save_rows if row[0] == 0x421]
        require(acknowledged and acknowledged[-1][1] == saved_sequence and saved_sequence > sequence,
                'new Save acknowledgement differs from the actual durable sequence')
        require(sha(saved_medium) != durable_before and dark_contact(saved_panel, x, y),
                'post-warm acknowledged Save has no new durable bytes or controller ink')
        raw = (live.directory/'input-0.bin').read_bytes()
        require(len(raw)%72 == 0, 'truncated actual raw input capture')
        observed = [struct.unpack_from('<9Q', raw, offset)[1:8] for offset in range(0, len(raw), 72)]
        require(observed == [tuple(row['words']) for row in self.report['raw_inputs']],
                'raw device boundary normalized or lost admitted sample fields')
        self.report['save'] = {'state':saved_state, 'new_guest_records':save_rows,
                              'sequence':saved_sequence, 'durable_sha256':sha(saved_medium),
                              'paper_completed_before':completed_before_save}
        (self.directory/'warm-new-uart.bin').write_bytes(uart.read_bytes()[uart_offset:])
        live.close(); self.sessions.remove(live)

        # The new process receives only the durable bytes, never old RAM/state.
        cold_disk = self.directory/'cold-input.raw'; shutil.copyfile(saved_medium, cold_disk)
        cold = self.session('new-cold', cold_disk)
        self.report['cold_identity'] = cold.identity
        self.report['new_cold_boot'] = self.new_ready(cold, 0, 1)
        cold_panel, cold_medium = cold.export('new-cold')
        require(visible_pixels(cold_panel) == visible_pixels(saved_panel),
                'new durable-only cold recovery differs at one or more controller pixels')
        require(sha(cold_medium) == sha(saved_medium),
                'new cold recovery changed acknowledged durable bytes')
        require(not any(row[0] in (0x41f,0x423,0x424) for row in guest_events(cold.directory/'uart-0.bin')),
                'new cold guest formatted, republished or failed')
        cold.close(); self.sessions.remove(cold)
        require(sha(self.args.disk) == self.report['medium_source']['sha256'],
                'test overwrote the source user medium')
        self.report['cold_recovery'] = {'status':'PASS', 'every_controller_pixel_exact':True,
            'durable_bytes_exact':True, 'durable_sha256':sha(cold_medium),
            'controller_pixels_sha256':sha(cold_panel)}
        self.report['status'] = 'PASS'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--disk', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=270,
                        help='Machine-operation deadline; public transport adds at most30seconds')
    parser.add_argument('--boot-seconds', type=int, default=30)
    parser.add_argument('--action-seconds', type=int, default=30)
    parser.add_argument('--deadline', type=int, default=900)
    args = parser.parse_args()
    require(1 <= args.timeout <= 270 and 1 <= args.boot_seconds <= 60 and
            1 <= args.action_seconds <= 60 and 1 <= args.deadline <= 900,
            'invalid bounded warm-reset campaign')
    args.checkpoint_relation = 'exact-container'
    args.durable_suffix_from = None
    checker = WarmChecker(args)
    try:
        checker.execute()
    except BaseException as error:
        checker.report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        checker.close()
        print(json.dumps({key:checker.report[key] for key in ('status','error') if key in checker.report}))


if __name__ == '__main__':
    main()
