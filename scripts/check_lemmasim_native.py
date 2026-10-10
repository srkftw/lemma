#!/usr/bin/env python3
"""Observe automated native pointer capture, notebook replay/cold, and reset.

All input enters QEMU's native input bridge/FIFO. The ordinary maintained
launcher owns and reaps every process; this script never writes guest memory,
renders ink, serializes notebook records, or feeds recovery results to a guest.
GTK automation is explicitly separate from manual or physical tablet testing.
"""
from __future__ import annotations
import argparse
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from check_native_ingress import check as check_ingress
from check_notebook_workflow import check, check_cold, committed_bytes, device_events, visible_pixels, guest_events
from inspect_notebook import inspect
loader = importlib.machinery.SourceFileLoader('lemmasim_native_command', str(ROOT / 'scripts/lemmasim'))
spec = importlib.util.spec_from_loader(loader.name, loader)
sim = importlib.util.module_from_spec(spec)
loader.exec_module(sim)


def endpoint(directory):
    return Path(json.loads((directory / 'process.json').read_text())['qmp_socket'])


def hardware(directory):
    return json.loads(sim.qmp(endpoint(directory), 'qom-get',
                      {'path': '/machine/lemma-hardware', 'property': 'device-state'}))


def pointer(directory, x, y, down):
    sim.qmp(endpoint(directory), 'input-send-event', {'device': 'lemma-hardware', 'events': [
        {'type': 'abs', 'data': {'axis': 'x', 'value': x}},
        {'type': 'abs', 'data': {'axis': 'y', 'value': y}},
        {'type': 'btn', 'data': {'button': 'left', 'down': down}}]})


class OwnedLaunch:
    """Coordinate input while the maintained launcher retains process ownership."""
    def __init__(self, directory, operation, timeout):
        self.directory, self.errors, self.value = directory, [], None
        self.deadline = time.monotonic() + timeout
        def work():
            try: self.value = operation()
            except BaseException as error: self.errors.append(error)
        self.thread = threading.Thread(target=work, name='owned-native-guest', daemon=True)
        self.thread.start()

    def wait(self, predicate, description, interval=.02):
        while True:
            if self.errors: raise RuntimeError(f'{description}: guest launch failed') from self.errors[0]
            if time.monotonic() >= self.deadline: raise TimeoutError(description)
            if (self.directory / 'process.json').exists():
                try:
                    if predicate(): return
                except OSError:
                    # The launcher removes its socket after reaping. Report
                    # the actual process failure rather than a missing socket
                    # from the concurrent final observation.
                    finished = self.directory / 'result.json'
                    if finished.is_file():
                        failure = json.loads(finished.read_text())
                        if failure.get('status') == 'FAIL':
                            raise RuntimeError(f'{description}: {failure.get("error", "guest failed")}')
                    raise
            if not self.thread.is_alive(): raise RuntimeError(f'{description}: guest stopped before observation')
            time.sleep(interval)

    def ready(self):
        serial = self.directory / 'serial.bin'
        if not serial.exists() or not sim.document_observations(serial)['ready']: return False
        state = hardware(self.directory)
        return state['paper']['status'] & 13 == 0 and state['pen']['count'] == 0

    def finish(self):
        self.thread.join(max(0, self.deadline - time.monotonic()) + 10)
        if self.thread.is_alive():
            raise RuntimeError('maintained launcher did not terminate/reap by its finite deadline')
        if self.errors: raise RuntimeError('maintained launcher failed') from self.errors[0]
        result = json.loads((self.directory / 'result.json').read_text())
        if not result.get('process_reaped'): raise RuntimeError('native process was not reaped')
        return result

    def abort(self):
        if self.thread.is_alive() and (self.directory / 'process.json').exists():
            try: sim.control(argparse.Namespace(run_directory=self.directory, action='power-cut'))
            except (OSError, ValueError, sim.Failure): pass
        self.thread.join(10)
        if self.thread.is_alive(): raise RuntimeError('native failed run did not reap its process')


def campaign(metadata, initial, out, *, timeout=120, deadline_callback=None, gtk=True):
    """Run fresh media copies; original input media/session remain immutable."""
    def remaining(limit):
        return deadline_callback(limit) if deadline_callback else limit
    out = Path(out).resolve(); initial = Path(initial).resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'schema_version': 1, 'status': 'FAIL', 'scope': 'automated native QEMU pointer to guest notebook; exact virtual replay and cold reopening; whole-machine reset during refresh',
              'build_identity': metadata, 'initial_media_sha256': sim.sha(initial),
              'manual_interactive_test': 'NOT_RUN', 'physical_tablet_test': 'NOT_RUN',
              'pressure_provenance': 'QEMU_MOUSE_SYNTHETIC_2047_OF_4095', 'gtk_native_window_requested': gtk,
              'capture_policy': 'host pointer samples; QEMU records their actual virtual ingress; replay reinjects no host sleeps',
              'runner_source_sha256': sim.sha(Path(__file__)),
              'ingress_observer_sha256': sim.sha(ROOT / 'conformance/lemmasim/check_native_ingress.py')}
    old_prepared, owned = sim.PREPARED, None
    try:
        sim.PREPARED = out / 'prepared.json'; sim.write_json(sim.PREPARED, metadata)
        disk = out / 'record.raw'; shutil.copyfile(initial, disk)
        session, run = out / 'session', out / 'session/run'
        record_timeout = remaining(timeout)
        owned = OwnedLaunch(run, lambda: sim.run(argparse.Namespace(disk=disk, mode='developer', fault=None,
                record=session, raw_input=None, geometry='1650x2200', headless=not gtk, timeout=record_timeout)), record_timeout)
        owned.wait(owned.ready, 'native notebook ready boundary')
        def baseline_saved():
            report = sim.document_observations(run / 'serial.bin')
            state = hardware(run)
            return (report['status'] == 'SAVED' and isinstance(report['acknowledged_sequence'], int)
                    and state['paper']['status'] & 13 == 0 and state['pen']['count'] == 0)
        owned.wait(baseline_saved, 'native initialized notebook durable Saved baseline')
        baseline_ack = sim.document_observations(run / 'serial.bin')['acknowledged_sequence']
        commands = [{'x': 6000, 'y': 8000, 'down': False}]
        commands += [{'x': 6000 + i * 400, 'y': 8000 + i * 250, 'down': True} for i in range(20)]
        commands += [{'x': 13600, 'y': 12750, 'down': False}]
        command_file = out / 'pointer-commands.json'
        sim.write_json(command_file, {'schema_version': 1, 'source': 'qmp-native-pointer',
                                    'device': 'lemma-hardware', 'commands': commands})
        for command in commands:
            pointer(run, **command)
            time.sleep(.025)
        def saved():
            report = sim.document_observations(run / 'serial.bin')
            state = hardware(run)
            return (report['status'] == 'SAVED' and report['acknowledged_sequence'] > baseline_ack
                    and (run / 'raw.bin').stat().st_size == len(commands) * 72
                    and state['paper']['status'] & 13 == 0 and state['pen']['count'] == 0)
        owned.wait(saved, 'native completed stroke durable Saved boundary')
        recorded = owned.finish(); owned = None
        if recorded['status'] != 'HOST_STOPPED_AT_DEADLINE': raise ValueError('recording did not close under the maintained replay policy')
        if gtk:
            display = recorded['argv'][recorded['argv'].index('-display') + 1]
            if display != 'gtk,zoom-to-fit=on': raise ValueError('native GTK launch did not enable the maintained viewport scaling')
        ingress, manifest = check_ingress(run / 'raw.bin', command_file, run / 'devices.jsonl')
        sim.write_json(out / 'ingress.json', ingress); sim.write_json(out / 'input.json', manifest)
        if ingress.get('status') != 'PASS' or ingress.get('captured_samples') != 22 or ingress.get('retained_stroke_samples') != 21:
            raise ValueError('independent native ingress observer rejected or changed the literal sample workload')
        workflow = check(disk, run / 'raw.bin', out / 'input.json', run / 'devices.jsonl', run / 'serial.bin', run / 'visible.ppm')
        sim.write_json(out / 'workflow.json', workflow)
        if workflow.get('status') != 'PASS' or workflow.get('retained_unique_raw_samples') != 21:
            raise ValueError('independent native notebook workflow rejected or omitted original contact/up samples')
        inspect(disk, out / 'committed')
        replay_paths = []; original_launch = sim.launch
        def remember_launch(*args, **kwargs):
            if kwargs.get('replay'): replay_paths.append(Path(args[2]))
            return original_launch(*args, **kwargs)
        sim.launch = remember_launch
        try: sim.replay(argparse.Namespace(session=session, disk_copy=out / 'replay.raw', timeout=remaining(180)))
        finally: sim.launch = original_launch
        if len(replay_paths) != 1: raise ValueError('native replay did not produce exactly one observed run')
        replay_dir = replay_paths[0]
        replay_result = json.loads((replay_dir / 'result.json').read_text())
        if replay_result.get('status') != 'REPLAY_BOUNDARY_REACHED' or replay_result.get('process_reaped') is not True:
            raise ValueError('native replay did not reach its exact boundary and reap')
        comparison = json.loads((replay_dir / 'comparison.json').read_text())
        if comparison.get('status') != 'PASS': raise ValueError('native exact replay comparison rejected')
        inspect(out / 'replay.raw', out / 'replay-committed')
        if committed_bytes(disk) != committed_bytes(out / 'replay.raw'): raise ValueError('replay committed ink/document bytes differ')
        cold = out / 'cold.raw'; shutil.copyfile(disk, cold)
        cold_run = out / 'cold-run'
        reopened = sim.launch(metadata, cold, cold_run, headless=True, until_ready=True,
                              timeout=remaining(180), mode='developer')
        if reopened['status'] != 'OBSERVED_GUEST_WORKFLOW_BOUNDARY' or reopened.get('process_reaped') is not True: raise ValueError('native cold reopen did not reach a genuine redraw')
        cold_check = check_cold(disk, cold, run / 'visible.ppm', cold_run / 'visible.ppm', cold_run / 'serial.bin', cold_run / 'devices.jsonl')
        sim.write_json(out / 'cold.json', cold_check)
        if cold_check.get('status') != 'PASS': raise ValueError('independent native cold observer rejected')
        # Reset is a separate declared Developer experiment. It must invalidate
        # an RR claim; it never mutates the original captured session or media.
        reset_disk = out / 'reset.raw'; shutil.copyfile(disk, reset_disk)
        reset_run = out / 'reset-run'; reset_timeout = remaining(timeout)
        owned = OwnedLaunch(reset_run, lambda: sim.launch(metadata, reset_disk, reset_run,
                headless=True, timeout=reset_timeout, mode='developer'), reset_timeout)
        owned.wait(owned.ready, 'reset control baseline notebook ready')
        before = hardware(reset_run)
        pointer(reset_run, 24000, 18000, False)
        pointer(reset_run, 24000, 18000, True)
        def busy():
            state = hardware(reset_run)
            if state['paper']['status'] & 1:
                sim.write_json(out / 'reset-busy.json', state)
                return True
            return False
        owned.wait(busy, 'new live stroke actual controller Busy before reset', interval=.001)
        sim.control(argparse.Namespace(run_directory=reset_run, action='reset'))
        def recovered():
            rows = guest_events(reset_run / 'serial.bin')
            state = hardware(reset_run)
            return (sum(row[0] == 0x420 for row in rows) >= 2 and state['paper']['status'] & 13 == 0
                    and state['paper']['completed'] > before['paper']['completed'] and state['pen']['count'] == 0)
        owned.wait(recovered, 'whole-machine reset interrupted refresh recovery')
        reset_result = owned.finish(); owned = None
        if reset_result.get('status') != 'HOST_STOPPED_AT_DEADLINE' or reset_result.get('process_reaped') is not True:
            raise ValueError('reset experiment did not close and reap under its declared finite policy')
        resets = [row for row in device_events(reset_run / 'devices.jsonl') if row[1] == 'device-reset' and row[2] == 8]
        if not resets: raise ValueError('reset never interrupted an actual controller refresh')
        if committed_bytes(disk) != committed_bytes(reset_disk): raise ValueError('reset lost or changed previously acknowledged document bytes')
        if visible_pixels(run / 'visible.ppm') != visible_pixels(reset_run / 'visible.ppm'):
            raise ValueError('reset full guest redraw differs from previously saved writing')
        sim.write_json(out / 'reset.json', {'schema_version': 1, 'status': 'PASS', 'scope': 'actual Developer whole-machine reset during modeled refresh; prior acknowledged bytes and pixels preserved',
                    'interrupted_reset_events': resets, 'run': str(reset_run), 'replay_claim': 'INVALIDATED_BY_DECLARED_RESET_CONTROL',
                    'process_reaped': reset_result['process_reaped'], 'disk_sha256': sim.sha(reset_disk)})
        if sim.sha(initial) != result['initial_media_sha256']: raise ValueError('native test mutated the original initial medium')
        result.update(status='PASS', retained_raw_samples=workflow['retained_unique_raw_samples'],
                      committed_sequence=workflow['committed_sequence'], record=str(session), replay=str(replay_dir),
                      cold=str(out / 'cold.json'), reset=str(out / 'reset.json'), observations=['ingress.json','workflow.json','cold.json','reset.json'])
    except BaseException as error:
        result['error'] = str(error)
        if owned is not None:
            try: owned.abort()
            except BaseException as cleanup: result['cleanup_error'] = str(cleanup)
            failed_run = owned.directory / 'result.json'
            if failed_run.is_file():
                cleanup_state = json.loads(failed_run.read_text())
                result['failed_process_reaped'] = cleanup_state.get('process_reaped')
                result['failed_process_returncode'] = cleanup_state.get('returncode')
                result['failed_process_error'] = cleanup_state.get('error')
                result['failed_run_result'] = str(failed_run)
        raise
    finally:
        sim.PREPARED = old_prepared
        sim.write_json(out / 'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--initial', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--headless-native', action='store_true', help='exercise native QMP input bridge without opening GTK; no visible frontend claim')
    args = parser.parse_args()
    if not 30 <= args.timeout <= 600: parser.error('timeout must be30..600 seconds per finite run')
    try:
        campaign(json.loads(args.prepared.read_text()), args.initial, args.output, timeout=args.timeout, gtk=not args.headless_native)
    except (OSError, ValueError, RuntimeError, TimeoutError, TypeError, KeyError, sim.Failure) as error:
        print(f'FAIL: {error}', file=sys.stderr); return 1
    print(f'PASS: automated native pointer/replay/cold/reset observations in {args.output}; manual/tablet tests NOT_RUN')
    return 0

if __name__ == '__main__': raise SystemExit(main())
