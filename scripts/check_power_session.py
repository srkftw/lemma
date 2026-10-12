#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded real Lean notebook power workflow through the public machine API.

Only raw pen samples and digital button levels are injected. Guest observations,
controller pixels, actual durable files and exact checkpoints are independent
outputs. This is neither a host notebook nor physical power qualification.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import time

from check_live_notebook import (Checker, Input, ROOT, guest_events, idle,
                                 require, sha, visible_pixels)


def power(state):
    value = state['devices']['power']
    require(type(value['state']) is int and value['state'] in (0, 1),
            'missing or malformed real controller power state')
    return value


class PowerChecker(Checker):
    profile = 'lemma-silicon-dev/0.3.0'
    backend = 'qemu'

    def __init__(self, args):
        require(args.disk.is_file() and args.disk.stat().st_size == 256*1024*1024,
                'provide an actual previously acknowledged 256 MiB medium')
        super().__init__(args)
        self.report['bounds']['disk'] = str(args.disk.resolve())
        self.report.update(schema='lemmasim-guest-power-observations/1',
                           scope='actual Lean canonical notebook and cooperative digital suspend; '
                                 'ELF-preload development boot, other machine/physical gaps remain',
                           medium_source={'path': str(args.disk.resolve()), 'sha256': sha(args.disk)})
        self.report['observer_sources'][str(Path(__file__).relative_to(ROOT))] = sha(Path(__file__))
        self.report['display_poll_cycles'] = 1000000
        self.report['display_poll_relation'] = ('10 ms passive observation of the ordinary full-frame '
            'update; the declared synthetic digital scan exceeds 300 ms. Every hardware/guest cycle '
            'executes; button decisions and queued wake are observed at 1 ms.')

    def button(self, session, level, cycle=None):
        state = session.inspect()['machine']
        return session.control({'action': 'inject', 'kind': 'button',
                                'cycle': state['cycle'] if cycle is None else cycle,
                                'level': level})

    def events(self, session, tag):
        return [row for row in guest_events(session.directory/'uart-0.bin') if row[0] == tag]

    def decisions(self, session, count):
        return session.wait(lambda state: len(self.events(session, 0x440)) > count,
                            self.args.action_seconds, quantum=100000)

    def reject_malformed_power(self, session, source):
        # Individually valid container/manifest checksums cannot authorize an
        # impossible device state. Restore must reject in a disposable candidate
        # without changing the still suspended, queued-wake current machine.
        from check_fast_state_equivalence import compare_checkpoints, power_offsets
        invalid = self.directory/'invalid-power-state'
        shutil.copytree(source, invalid)
        checkpoint = invalid/'machine.chk'
        data = checkpoint.read_bytes()
        offsets = power_offsets(data)
        require(offsets is not None, 'new checkpoint has no serialized Power-v1 state')
        offset = offsets['state']
        require(struct.unpack_from('>Q', data, offset)[0] == 1, 'malformed test is not at suspended state')
        changed = bytearray(data); struct.pack_into('>Q', changed, offset, 2)
        checkpoint.write_bytes(changed)
        manifest = invalid/'snapshot.json'
        value = json.loads(manifest.read_text())
        for item in value['files']:
            if item['path'] == 'machine.chk':
                item['sha256'] = sha(checkpoint)
        manifest.write_text(json.dumps(value, indent=2)+'\n')
        before = session.inspect()['machine']
        process = self.launch(['restore', '--session-dir', str(session.directory), '--from', str(invalid)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out, err = process.communicate(timeout=min(self.args.timeout, self.deadline-time.monotonic()))
        except BaseException:
            process.kill(); process.wait(timeout=5)
            raise
        (self.directory/'invalid-power-restore.log').write_bytes(out+err)
        require(process.returncode != 0, 'impossible power state was restored')
        require(before == session.inspect()['machine'], 'rejected restore changed the current machine')
        after = session.snapshot('after-rejected-power')
        observation = compare_checkpoints(source/'machine.chk', after/'machine.chk')
        require(observation['status'] == 'PASS', 'rejected restore altered complete machine state')
        self.report['malformed_power_restore'] = {'status': 'PASS', 'field': 'power.state',
            'invalid_value': 2, 'valid_manifest_checksums': True, 'reject_exit': process.returncode,
            'complete_current_machine_unchanged': observation}

    def observe_exact(self, session, suspended):
        # Admit future physical levels while still suspended. The queued events
        # and their precise clock phase are part of the checkpoint inventory.
        cycle = session.inspect()['machine']['cycle']
        self.button(session, 0, cycle + 100000)
        self.button(session, 1, cycle + 200000)
        before = session.snapshot('suspended-queued-wake')
        self.reject_malformed_power(session, before)
        uart = session.directory/'uart-0.bin'
        offset = uart.stat().st_size
        state = session.wait(lambda state: power(state)['state'] == 0 and
                             bool(self.events(session, 0x441)), self.args.action_seconds,
                             quantum=100000)
        session.run(5000000)
        baseline = session.inspect()['machine']
        original = session.snapshot('wake-original')
        original_panel, original_medium = session.export('wake-original')
        capture = self.directory/'wake-external.jsonl'
        shutil.copyfile(session.directory/'external.jsonl', capture)
        source_hash = sha(self.disk)
        self.command(['session-replay', '--session-dir', str(session.directory),
                      '--snapshot', str(before), '--capture', str(capture),
                      '--until-ns', str(baseline['virtual_ns'])], True)
        replay = session.inspect()['machine']
        replayed = session.snapshot('wake-replayed')
        replay_panel, replay_medium = session.export('wake-replayed')
        require(baseline == replay, 'complete inspected guest/device/time state differs after wake replay')
        observer = ROOT/'conformance/lemmasim/check_fast_state_equivalence.py'
        output = self.directory/'power-state-equivalence.json'
        prepared = json.loads((ROOT/'build/lemmasim/fast-prepared-0.3.0.json').read_text())
        command = [sys.executable, str(observer), '--left', str(original/'machine.chk'),
                   '--right', str(replayed/'machine.chk'), '--qemu', prepared['qemu']['path'],
                   '--output', str(output), '--mutation-checks']
        self.commands.write(json.dumps(command)+'\n'); self.commands.flush()
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                timeout=min(self.args.timeout, self.deadline-time.monotonic()))
        require(result.returncode == 0, 'full wake checkpoint mismatch: '+result.stdout+result.stderr)
        observation = json.loads(output.read_text())
        require(observation['status'] == 'PASS', 'unsupported or unequal checkpoint state')
        require(sha(original_panel) == sha(replay_panel) and sha(original_medium) == sha(replay_medium),
                'wake replay changed controller pixels or durable bytes')
        fork = max(session.directory.glob('machine-fork-*'), key=lambda p: p.stat().st_mtime_ns)
        require(uart.read_bytes()[offset:] == (fork/'uart-1.bin').read_bytes(),
                'actual Lean wake/output suffix differs after replay')
        require(sha(self.disk) == source_hash, 'snapshot replay mutated the original durable medium')
        require(power(suspended)['state'] == 1 and power(state)['state'] == 0,
                'no actual suspended-to-running transition')
        self.report['queued_wake_replay'] = {'status': 'PASS', 'suspended': suspended,
            'final': baseline, 'checkpoint_observation': observation,
            'source_medium_unchanged': True, 'controller_pixels_exact': True,
            'guest_suffix_exact': True, 'durable_bytes_exact': True}
        return fork, replay_medium

    def execute(self):
        self.disk = self.directory/'notebook.raw'
        require(self.args.disk.is_file() and self.args.disk.stat().st_size == 256*1024*1024,
                'provide an actual previously acknowledged 256 MiB medium')
        with self.args.disk.open('rb') as source, self.disk.open('xb') as destination:
            shutil.copyfileobj(source, destination, 1024*1024)
        live = self.session('live', self.disk)
        self.report['identity'] = live.identity
        self.report['cold_boot'] = live.boot()
        cold = live.inspect()['machine']
        require(power(cold)['reset_cause'] == 1, 'cold controller reset cause missing')
        require(any(row[1:] == (1, 0, 0, 0) for row in self.events(live, 0x442)),
                'actual Lean cold reset-cause observation absent')

        # An ordinary guest page change produces the full-screen background
        # refresh. The raw button is pressed at a declared active device boundary.
        stream = Input(1650, 2200, cold['ticks']+10000, 100000, 0)
        stream.sample(825, 160, 0, False)
        stream.tool(2, 'ordinary next page')
        live.admit(stream.events)
        active = live.wait(lambda state: bool(state['devices']['paper']['status'] & 1),
                           self.args.action_seconds, quantum=1000000)
        decisions = len(self.events(live, 0x440))
        self.button(live, 1)
        rejected = self.decisions(live, decisions)
        require(self.events(live, 0x440)[-1][1:4] == (1, 196, 0),
                'guest did not reject an outstanding display suspend as BUSY')
        require(power(rejected)['state'] == 0, 'BUSY fabricated suspend completion')
        self.button(live, 0)
        live.wait(idle, self.args.action_seconds)
        self.report['busy_display'] = {'status': 'PASS', 'active': active,
                                       'decision': self.events(live, 0x440)[-1]}

        # A held contact must cross a controller loss boundary, with no implicit
        # Save, completed refresh or medium publication caused by suspend itself.
        state = live.inspect()['machine']
        contact = Input(1650, 2200, state['ticks']+10000, 100000, 0)
        contact.sample(1100, 1600, 2048, True)
        live.admit(contact.events)
        live.run(20000000)
        live.wait(idle, self.args.action_seconds)
        before_panel, before_medium = live.export('before-suspend')
        before = live.inspect()['machine']
        require(not before['devices']['pen']['resync'] and
                before['ticks'] < contact.events[-1][1] + 10000000,
                'held contact already lost or timed out before suspend')
        decisions = len(self.events(live, 0x440))
        self.button(live, 1)
        suspended = self.decisions(live, decisions)
        require(self.events(live, 0x440)[-1][1:4] == (1, 0, 1) and power(suspended)['state'] == 1,
                'raw button did not reach real Lean accepted suspend policy')
        require(suspended['devices']['pen']['epoch'] > before['devices']['pen']['epoch'] and
                suspended['devices']['pen']['resync'], 'held pen did not cross a loss/resynchronization boundary')
        live.run(5000000)
        retained = live.inspect()['machine']
        retained_panel, retained_medium = live.export('suspended')
        require(power(retained)['state'] == 1, 'timer/spurious interrupt resumed User dispatch')
        require(sha(before_panel) == sha(retained_panel) and sha(before_medium) == sha(retained_medium),
                'suspend changed retained controller pixels or durable bytes')
        require(before['storage']['flushes'] == retained['storage']['flushes'],
                'suspend secretly flushed storage')
        self.report['suspend_retention'] = {'status': 'PASS', 'before': before, 'suspended': retained,
                                          'held_contact_time': contact.events[-1][1],
                                          'panel_sha256': sha(retained_panel), 'durable_sha256': sha(retained_medium)}
        fork, durable = self.observe_exact(live, retained)

        # Resume writing through pen/paper/store, then explicit Save. This checks
        # that retaining task context is useful to the application, not just MMIO.
        state = live.inspect()['machine']
        writing = Input(1650, 2200, state['ticks']+10000, 100000, 0)
        writing.sample(1100, 1600, 0, False)
        writing.stroke('after actual wake', 2, 1, 6, 1300)
        writing.tool(7, 'explicit Save after wake')
        live.admit(writing.events)
        uart = fork/'uart-1.bin'
        live.wait(lambda state: idle(state) and state['ticks'] > writing.events[-1][1]+2000000 and
                  any(row[0] == 0x421 for row in guest_events(uart)), self.args.action_seconds)
        saved_panel, saved_medium = live.export('saved-after-wake')
        states = [row for row in guest_events(uart) if row[0] in (0x421, 0x423, 0x424)]
        require(states and states[-1][0] == 0x421 and any(row[0] == 0x423 for row in states),
                'resumed real guest has no pending-to-durable Save acknowledgement')
        require(sha(saved_medium) != sha(durable), 'post-wake Save published no new durable bytes')
        live.close(); self.sessions.remove(live)
        cold_session = self.session('new-cold', saved_medium)
        self.report['post_wake_cold_boot'] = cold_session.boot()
        cold_panel, cold_medium = cold_session.export('new-cold')
        # Cold notebook opens the recorded document root's selected page1. Move
        # to the page2 that was edited through the same raw toolbar input.
        state = cold_session.inspect()['machine']
        completed_before = state['devices']['paper']['completed']
        page = Input(1650, 2200, state['ticks']+10000, 100000, 0)
        page.sample(825, 160, 0, False); page.tool(2, 'reopen acknowledged page2')
        cold_session.admit(page.events)
        cold_session.run(200000000)
        # Pen consumption/page-selection UART can precede rasterization and
        # submission. An idle controller at that point still shows the previous
        # image. Require an actual subsequent controller completion, then idle.
        recovered = cold_session.wait(lambda state: idle(state) and
            state['devices']['paper']['completed'] > completed_before,
            self.args.action_seconds)
        page_panel, page_medium = cold_session.export('new-cold-page2')
        require(visible_pixels(page_panel) == visible_pixels(saved_panel),
                'genuine new cold recovery lost the acknowledged post-wake page')
        require(sha(cold_medium) == sha(saved_medium) == sha(page_medium),
                'cold reopen reformatted or republished the acknowledged medium')
        cold_session.close(); self.sessions.remove(cold_session)
        require(sha(self.args.disk) == self.report['medium_source']['sha256'],
                'power workflow overwrote source user data')
        self.report['resumed_save_cold'] = {'status': 'PASS', 'guest_states': states,
            'durable_sha256': sha(saved_medium), 'recovered_page_pixels_exact': True,
            'paper_completed_before_navigation': completed_before,
            'paper_completed_after_navigation': recovered['devices']['paper']['completed']}
        self.failed_barrier(saved_medium, cold_panel)
        self.report['status'] = 'PASS'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--disk', type=Path, required=True,
                        help='previously acknowledged real guest medium; copied into an exclusive test session')
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--boot-seconds', type=int, default=30)
    parser.add_argument('--action-seconds', type=int, default=30)
    parser.add_argument('--deadline', type=int, default=1800)
    args = parser.parse_args()
    require(1 <= args.timeout <= 600 and 1 <= args.boot_seconds <= 60 and
            1 <= args.action_seconds <= 60 and 1 <= args.deadline <= 3600, 'invalid bounded campaign')
    args.checkpoint_relation = 'pinned-host-time-v1'
    args.durable_suffix_from = None
    checker = PowerChecker(args)
    try:
        checker.execute()
    except BaseException as error:
        checker.report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        checker.close()
        print(json.dumps({k: checker.report[k] for k in ('status', 'error') if k in checker.report}))


if __name__ == '__main__':
    main()
