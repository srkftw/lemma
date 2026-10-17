#!/usr/bin/env python3
"""Real unsuccessful autosave and blocked retry in a Wire11 EOF fault fork.

Keep the old native binary/checkpoint and opaque receipt state. Only a new
private host's actual EOF is injected at the retained stateless WAIT boundary.
No original process, medium, peer, hosted context or positive receipt is reused.
The historical guest rejects further contact while FAILED; toolbar admission
is observed separately and is not described as a newly issued Store retry.
"""
import argparse
import json
import os
from pathlib import Path
import selectors
import shlex
import signal
import subprocess
import sys
import time

from archive_companion_boundary import validate_archive_files
from check_guest_usb_link import ROOT, require, sha, guest_events, request
from check_guest_usb_notebook import (Checker, NativeUSBSession, copy_opaque_peer,
    materialize_observation, owned_resources, expected_stroke, Input, empty_pixels)
from check_usb_cold_boundary import ColdChecker
from lemmasim_usb_pending import validate as validate_host
from silicon_guest_bundle import prepared
from usb_fork_fault import (file_record, private_files, prefix, chain, validate,
                            FNV_OFFSET, PROFILE, MAX_SUFFIX, SCHEMA)


def reap(process):
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)


def source_from_bundle(bundle, name):
    metadata = json.loads((bundle / 'bundle.json').read_text())
    origin = metadata['original_repository_root'] + '/' + name
    choices = metadata['origins'][origin]
    require(len(choices) == 1, 'ambiguous original transport source')
    digest, path = next(iter(choices.items())); path = bundle / path
    require(sha(path) == digest, 'original transport source differs')
    return path


def capture(args):
    out = args.work_dir.resolve(); require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused EOF output')
    out.mkdir(parents=True); start = time.monotonic(); process = peer = None; log = peer_log = None
    report = {'schema': 'lemma-private-usb-eof/1', 'status': 'FAIL',
        'scope': 'new private hosted Lean transport EOF; no guest or logical host restoration',
        'bounds': {'whole_host_seconds': 240, 'compile_seconds': 120, 'transport_seconds': 10,
                   'max_owned_rss_kib': 4194304}, 'reply_count': 0, 'opaque_operations_issued': 0,
        'private_directory': str(out)}
    def cancelled(_signal, _frame): raise KeyboardInterrupt('explicit EOF probe cancellation')
    signal.signal(signal.SIGTERM, cancelled); signal.signal(signal.SIGINT, cancelled)
    try:
        bundle = args.native_bundle.resolve(); prepared(bundle, 'rtl', 'usb-wire-bulk-notebook', PROFILE)
        host = validate_host(args.host_prepared); legacy = json.loads(Path(host['legacy_prepared']['path']).read_text())
        bd = args.boundary.resolve(); boundary = json.loads((bd / 'boundary.json').read_text())
        validate_archive_files(bd, boundary)
        require(boundary['profile'] == PROFILE and (boundary['saved_sequence'], boundary['high_water']) == (11, 72),
                'private EOF requires acknowledged Saved11 Wire receipt state')
        copy_opaque_peer(bd / 'peer', out / 'peer', bd / 'outbox', out / 'outbox')
        report['before'] = private_files(out)
        transport = out / 'transport'; transport.mkdir()
        original_cpp = source_from_bundle(bundle, 'sim/usb/usb_transport.cpp')
        original_header = source_from_bundle(bundle, 'sim/usb/usb_transport.h')
        (transport / 'usb_transport.cpp').write_bytes(original_cpp.read_bytes())
        (transport / 'usb_transport.h').write_bytes(original_header.read_bytes())
        helper = ROOT / 'tests/lemmasim/usb_private_eof.cpp'; binary = out / 'usb-private-eof'
        command = ['g++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-I' + str(transport),
                   str(helper), str(transport / 'usb_transport.cpp'), '-o', str(binary)]
        report['compile_argv'] = ['nix-shell', str(ROOT / 'tooling/silicon/sim.nix'), '--run', shlex.join(command)]
        with (out / 'compile.log').open('xb') as compile_log:
            subprocess.run(report['compile_argv'], cwd=ROOT, stdout=compile_log, stderr=subprocess.STDOUT,
                           timeout=120, check=True)
        socket = out / 'peer.sock'; companion = Path(legacy['companion_prepared']['path'])
        peer_argv = [sys.executable, str(ROOT / 'scripts/lemmasim'), 'companion', 'serve', '--prepared', str(companion),
                     '--directory', str(out / 'peer'), '--socket', str(socket)]
        peer_log = (out / 'peer.log').open('xb')
        peer = subprocess.Popen(peer_argv, cwd=ROOT, stdout=peer_log, stderr=subprocess.STDOUT, start_new_session=True)
        until = time.monotonic() + 15
        while not socket.exists():
            require(peer.poll() is None and time.monotonic() < until, 'private persistent peer startup'); time.sleep(.01)
        argv = [str(binary), host['binary']['path'], str(socket), str(out / 'outbox'), str(boundary['writer']),
                str(ROOT / 'sim/companion/os_io.py')]
        log = (out / 'eof.log').open('xb')
        process = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        process.wait(timeout=15)
        require(process.returncode == 0, 'actual private EOF probe failed')
        lines = (out / 'eof.log').read_text().splitlines()
        require(len(lines) == 3 and lines[0] == 'REQUEST 1 USBHOST/2 PACKET_BYTES_DEV' and
                lines[1].startswith('CHILD ') and lines[2] == 'FAULT USB process disconnected read',
                'actual private EOF observation shape')
        report.update(fault=lines[2][6:], actual_request={'id': 1, 'frame': lines[0].split(' ', 2)[2]},
            peer_argv=peer_argv, probe_argv=argv, probe_pid=process.pid,
            inputs={'native_bundle': file_record(bundle / 'bundle.json'),
                    'host_prepared': file_record(args.host_prepared.resolve()),
                    'usb_transport.cpp': file_record(original_cpp), 'usb_transport.h': file_record(original_header),
                    'probe_source': file_record(helper), 'build_environment': file_record(ROOT / 'tooling/silicon/sim.nix')},
            outputs={'probe': file_record(binary), 'log': file_record(out / 'eof.log')})
        report['after'] = private_files(out)
        require(report['before'] == report['after'], 'private EOF probe changed opaque bytes or dedup state')
        report['status'] = 'PASS'
    except BaseException as error: report['error'] = repr(error)
    finally:
        reap(process); reap(peer)
        if log is not None: log.close()
        if peer_log is not None: peer_log.close()
        report.update(host_seconds=time.monotonic() - start,
                      owned_children_reaped=all(p is None or p.poll() is not None for p in (process, peer)))
        if report['host_seconds'] > 240: report.update(status='FAIL', error='whole private EOF bound')
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2)); return 0 if report['status'] == 'PASS' else 1


def create_fault(args, state, identity, out):
    parent = args.snapshot.resolve(); bundle = args.native_bundle.resolve()
    build = json.loads((bundle / 'runtime/rtl/build.json').read_text()); implementation = build['snapshot_identity']
    rows, logical = prefix(args.prefix_tape, implementation, state['cycle'])
    capture_path = args.capture.resolve(); actual = json.loads(capture_path.read_text())
    private = Path(actual['private_directory'])
    fault = {'kind': 'private-transport-eof', 'cycle': state['cycle'], 'request_id': logical['pending_command'],
             'frame': actual['fault'], 'horizon': state['cycle'] + MAX_SUFFIX}
    injected = f"{fault['cycle']} 2 {fault['request_id']} {fault['frame']}\n".encode()
    value = chain(injected, logical['accepted_hash']); horizon = fault['horizon']
    bridge = out / 'injected-disconnect.bridge'
    bridge.write_bytes(f'LMUSBRP1 {implementation}\nHORIZON {horizon}\n'.encode() + b''.join(rows) + injected +
        f'CHECKSUM {chain(f"{horizon} 3 0 HORIZON\n".encode(), value)}\n'.encode())
    sidecar = out / 'fault.json'
    data = {'schema': SCHEMA, 'scope': 'injected disconnect fault fork',
        'native_bundle': file_record(bundle / 'bundle.json'),
        'parent_snapshot': {'path': str(parent), 'manifest': file_record(parent / 'snapshot.json'),
                            'machine': file_record(parent / 'machine.chk')},
        'parent_tape': file_record(args.prefix_tape.resolve()),
        'acknowledged_boundary': file_record(args.boundary.resolve() / 'boundary.json'),
        'private_directory': str(private), 'private_files': private_files(private),
        'capture': file_record(capture_path), 'fault': fault, 'bridge': file_record(bridge)}
    sidecar.write_text(json.dumps(data, indent=2) + '\n'); validate(sidecar, parent, state, identity)
    return sidecar


class ForkSession(NativeUSBSession):
    def __init__(self, checker, args):
        self.checker, self.name = checker, 'fault-fork'; self.directory = checker.out / self.name
        self.log = (checker.out / 'fault-fork.log').open('xb'); self.view_generation = self.view = None
        self.argv = [sys.executable, str(ROOT / 'scripts/lemmasim'), 'session', '--backend', 'rtl',
            '--profile', PROFILE, '--workload', 'usb-wire-bulk-notebook', '--native-bundle',
            str(args.native_bundle.resolve()), '--restore', str(args.snapshot.resolve()), '--mode', 'laboratory',
            '--headless', '--paused', '--session-dir', str(self.directory), '--timeout', '120', '--quantum', '1000']
        self.process = subprocess.Popen(self.argv, cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        checker.sessions.append(self); until = time.monotonic() + 60
        while not (self.directory / 'session.json').exists():
            require(self.process.poll() is None and time.monotonic() < until, 'exact native private restore startup');time.sleep(.02)
        initial = self.control({'action': 'inspect'}); self.identity = initial['identity']; self.start = initial['machine']
        require(not initial['running'] and self.start['usb']['fork_suspended'], 'private restored owner did not remain suspended')


def run(args):
    require(args.expected_source_sha == sha(__file__), 'fault observer differs from supervised source')
    args.profile = PROFILE; args.rtl_source_root = args.guest_source_root = None
    args.cold_cycles = 1600000000;args.cold_deadline = 7200
    args.ink_cycles = 200000000;args.action_cycles = 1600000000;args.action_deadline = 7200
    checker = Checker(args); checker.report.update(schema='lemma-wire-unsuccessful-save-fork/1', status='RUNNING',
        scope=__doc__, input_contract='lemma-usb-fork-disconnect-fault/1', automatic_restart=False,
        observer_sha256=sha(__file__), inputs={key:file_record(getattr(args,key).resolve()) for key in ('prefix_tape','capture')})
    started = time.monotonic()
    def cancelled(_signal, _frame): raise KeyboardInterrupt('explicit supervised fork cancellation')
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    try:
        session = ForkSession(checker,args); state=session.start;begin=state['cycle']
        initial_rows=session.records();saved_count=sum(row[0]==0x421 for row in initial_rows)
        sidecar=create_fault(args,state,session.identity,checker.out)
        def rejected(value):
            before=session.machine()
            try:session.control(value)
            except RuntimeError as error: text=str(error)
            else: raise ValueError('fault negative was admitted')
            require(session.machine()==before,'rejected fault changed machine');return text
        errors=[rejected({'action':'run','cycles':1}),rejected({'action':'usb-outcomes','path':str(sidecar)})]
        original_fault=json.loads(sidecar.read_text()); negatives={}
        import copy
        for name, mutate in (
            ('request-id',lambda d:d['fault'].__setitem__('request_id',d['fault']['request_id']+1)),
            ('poll-boundary',lambda d:d['fault'].__setitem__('cycle',d['fault']['cycle']+1000)),
            ('horizon',lambda d:d['fault'].__setitem__('horizon',d['fault']['horizon']+1)),
            ('namespace',lambda d:d.__setitem__('schema','historical-usb-replay')),
            ('parent-hash',lambda d:d['parent_snapshot']['machine'].__setitem__('sha256','0'*64)),
            ('private-dedup',lambda d:d['private_files']['outbox/outbox'].__setitem__('sha256','0'*64)),
            ('EOF-reason',lambda d:d['fault'].__setitem__('frame','OPEN')),
        ):
            changed=copy.deepcopy(original_fault);mutate(changed)
            bad=checker.out/(name+'.fault.json');bad.write_text(json.dumps(changed,indent=2)+'\n')
            negatives[name]=rejected({'action':'usb-fault','path':str(bad)})
        checker.report.update(identity=session.identity,argv=session.argv,fault=file_record(sidecar),
            parent_snapshot=file_record(args.snapshot.resolve()/'snapshot.json'), initial_machine=state,
            historical_tape_rejection=errors,admission_negatives=negatives)
        session.control({'action':'usb-fault','path':str(sidecar)})
        session.control({'action':'snapshot','path':str(checker.out/'admitted-before-edge')})
        require(sha(checker.out/'admitted-before-edge/machine.chk')==sha(args.snapshot.resolve()/'machine.chk'),
                'fault admission changed guest before scheduled edge')
        errors.append(rejected({'action':'run','cycles':MAX_SUFFIX+1}))
        detached=session.control({'action':'run','cycles':1})
        require(detached['cycle']==begin+1 and detached['usb']['terminal']==1 and
                detached['usb']['connected']==detached['usb']['configured']==0 and
                detached['usb']['pending_command']==0,'captured EOF did not reach actual controller detach')
        checker.report['actual_detach']=detached;checker.update()
        boundary=json.loads((args.boundary/'boundary.json').read_text())
        from store_oracle import recover
        import struct
        _,sequence,records=recover((args.boundary/'acknowledged.raw').read_bytes())
        require(sequence==11,'old acknowledged journal identity')
        payload=records[(1,65539)].payload
        samples=[struct.unpack_from('<9Q',payload,128+72*i) for i in range(3)]
        _,old_black=expected_stroke(samples)
        stream=Input(1650,2200,session.machine()['ticks']+10000,100000,0)
        stream.sample(825,160,0,False);stream.stroke('disconnected private annotation',1,1,3,1700)
        _,new_black=expected_stroke(stream.events[1:4])
        pixels=bytearray(empty_pixels(1650,2200,status='FAILED'))
        for x,y in old_black+new_black:pixels[(y*1650+x)*3:(y*1650+x)*3+3]=bytes(3)
        session.admit(stream.events)
        ink=session.wait('disconnected-raw-ink',lambda state,rows:any(r[0]==0x424 for r in rows) and
            session.panel_matches(state,bytes(pixels)),args.ink_cycles,7200,allow_failed_save=True)
        require(sum(row[0]==0x421 for row in session.records())==saved_count,'disconnected ink manufactured Saved')
        baseline=len(session.records());stream.tick=session.machine()['ticks']+10000
        start_input=len(stream.events);stream.tool(7,'explicit disconnected Save');session.admit(stream.events[start_input:])
        toolbar_begin=session.machine()['cycle']
        def blocked(state,rows):
            return state['cycle']>=toolbar_begin+10000000 and not rows[baseline:] and \
                   session.panel_matches(state,bytes(pixels))
        failure=session.wait('blocked-retry-gesture',blocked,50000000,7200,allow_failed_save=True)
        require(sum(row[0]==0x421 for row in session.records())==saved_count,'blocked retry manufactured Saved')
        actual=json.loads(args.capture.read_text());private=Path(actual['private_directory'])
        observed=checker.out/'after-failed-save.raw';materialize_observation(private/'peer',observed)
        checker.report.update(status='PASS',raw_ink=ink,blocked_retry=failure,actual_suffix_uart=session.records(),
            all_failed_pixels_equal=True,new_saved_records=0,observed_opaque_files=private_files(private),
            observed_medium=file_record(observed),no_external_operation_reissued=True,rollback_assumed=False,
            new_explicit_store_attempt=False,toolbar_admitted_but_blocked_by_failed_policy=True,
            acknowledged_bytes_equal=sha(observed)==boundary['files']['acknowledged.raw']['sha256'],
            external_receipt_state_equal=private_files(private)==actual['after'])
        session.control({'action':'snapshot','path':str(checker.out/'failed-save-final')})
    except BaseException as error:
        checker.report.update(status='FAIL',error=repr(error))
        if checker.sessions:
            session=checker.sessions[-1]
            try:
                checker.report['failure_machine']=session.machine()
                session.control({'action':'snapshot','path':str(checker.out/'failure-snapshot')})
            except BaseException as observer:checker.report['failure_export_error']=repr(observer)
    finally:
        for session in checker.sessions:session.close()
        checker.commands.close();checker.progress.close()
        checker.report.update(host_seconds=time.monotonic()-started,
            owned_children_reaped=all(s.process.poll() is not None for s in checker.sessions))
        checker.update()
    print(json.dumps(checker.report,indent=2));return 0 if checker.report['status']=='PASS' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('capture','launch','_run'))
    for name in ('native-bundle','host-prepared','boundary','work-dir'):
        parser.add_argument('--'+name,type=Path,required=True)
    for name in ('snapshot','prefix-tape','capture'):parser.add_argument('--'+name,type=Path)
    parser.add_argument('--expected-source-sha');args=parser.parse_args()
    if args.action=='capture':return capture(args)
    require(all(getattr(args,key) is not None for key in ('snapshot','prefix_tape','capture')),'fault inputs required')
    if args.action=='_run':return run(args)
    out=args.work_dir.resolve();directory=out.with_name(out.name+'.supervision')
    require(not out.exists() and not directory.exists() and out.is_relative_to(ROOT/'build'),'unused supervised fork output')
    directory.mkdir(mode=0o700);started=time.time_ns()
    command=[sys.executable,str(Path(__file__).resolve()),'_run','--expected-source-sha',sha(__file__)]
    for name in ('native_bundle','host_prepared','boundary','work_dir','snapshot','prefix_tape','capture'):
        command+=['--'+name.replace('_','-'),str(getattr(args,name).resolve())]
    manifest={'schema':'lemma-usb-fault-fork-supervision/1','work_dir':str(out),'argv':command,
        'supervisor_sha256':sha(ROOT/'scripts/supervise_usb_notebook.py'),
        'observer_sha256':sha(ROOT/'scripts/check_guest_usb_notebook.py'),
        'base_observer_source':'scripts/check_guest_usb_notebook.py','fault_observer_sha256':sha(__file__),
        'fault_api_sha256':sha(ROOT/'scripts/usb_fork_fault.py'),'session_adapter_sha256':sha(ROOT/'scripts/lemmasim_session.py'),
        'started_unix_ns':started,'absolute_deadline_unix_ns':started+14760*1000000000,
        'whole_host_ceiling_seconds':14760,'policy':{'automatic_restart':False,
        'pause':'paused owner advanced only in explicit bounded groups; no extension',
        'cancellation':'SIGTERM supervisor; owned-child cleanup only',
        'ink':'200M/7200s','Save':'1.6B/7200s','total_cycles':MAX_SUFFIX,
        'maximum_owned_rss_kib':4194304,'maximum_owned_disk_bytes':12000000000}}
    path=directory/'manifest.json';path.write_text(json.dumps(manifest,indent=2)+'\n')
    log=(directory/'supervisor.log').open('xb')
    process=subprocess.Popen([sys.executable,str(ROOT/'scripts/supervise_usb_notebook.py'),'_run',str(path)],cwd=ROOT,
        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close()
    from supervise_usb_notebook import identity
    print(json.dumps({'supervisor':identity(process.pid),'manifest':str(path),'absolute_deadline_unix_ns':manifest['absolute_deadline_unix_ns']}));return 0


if __name__=='__main__':raise SystemExit(main())
