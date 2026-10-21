#!/usr/bin/env python3
"""Transport a local Lean school's published bytes to the actual LemmaSim guest.

School enrollment, authorization and tutoring policy execute in lemma-school.
This adapter copies current guest ASK records and opaque published package bytes
through the existing UART installer. It never creates ink/documents, recovers a
journal, decides curriculum policy or reports panel delivery from an API result.
The supported trust boundary is the local OS owner in Developer/Laboratory mode.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from lemmasim_session import request as control
from lemmasim_course import frame
from lemmasim_tutor import ROW, ask_context, uart_path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def school_call(executable, school_root, request, directory, label, endpoint=None):
    """No semantic fallback: a rejected or unavailable Lean authority fails."""
    encoded_request = json.dumps(request,separators=(',',':')).encode()
    if len(encoded_request)>1048576:
        raise ValueError('school request exceeds the authority byte bound')
    (directory / (label + '-request.json')).write_text(json.dumps(request, indent=2) + '\n')
    if endpoint is not None:
        selected=urllib.parse.urlsplit(endpoint)
        if selected.scheme!='http' or selected.hostname not in ('127.0.0.1','::1','localhost') or selected.username or selected.password or selected.query or selected.fragment or selected.path!='/v1/command':
            raise ValueError('school endpoint must be the explicit loopback http /v1/command development service')
        class RefuseRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*unused):
                raise ValueError('school transport refuses redirects')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),RefuseRedirect())
        with opener.open(urllib.request.Request(endpoint,data=encoded_request,headers={'Content-Type':'application/json'}),timeout=120) as response:
            output=response.read(33554433)
            if response.status!=200 or len(output)>33554432:
                raise ValueError('school HTTP response status/byte bound rejected')
        exit_code=0; errors=b''
    else:
        command = [sys.executable,str(ROOT/'scripts/school_transport.py'),'--binary',str(executable),str(school_root),encoded_request.decode()]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=120)
        output=result.stdout; errors=result.stderr; exit_code=result.returncode
    (directory / (label + '-stdout.json')).write_bytes(output)
    (directory / (label + '-stderr.log')).write_bytes(errors)
    try:
        response = json.loads(output)
    except (ValueError, UnicodeError) as error:
        raise ValueError('Lean school returned no valid JSON result; retained ' + label) from error
    if exit_code or response.get('ok') is not True:
        raise ValueError('Lean school rejected request: ' + str(response.get('error', 'nonzero process result')))
    if not isinstance(response.get('result'), dict):
        raise ValueError('Lean school result must be an object')
    return response['result']


def actual_session(directory):
    metadata = json.loads((directory / 'session.json').read_text())
    if metadata.get('schema') != 'lemmasim-live/1' or metadata.get('mode') not in ('developer', 'laboratory'):
        raise ValueError('local owner Developer/Laboratory session required')
    if metadata.get('identity', {}).get('profile') != 'lemma-silicon-dev/0.14.0':
        raise ValueError('the current bridge requires the admitted Multimodal14 guest profile')
    observed = control(directory, {'action': 'inspect'}, timeout=120)
    if observed.get('identity') != metadata.get('identity') or observed.get('running') is not False:
        raise ValueError('pause the exact admitted guest before transporting school bytes')
    flag = '-kernel' if metadata.get('backend') == 'qemu' else '--image'
    argv = metadata.get('argv', [])
    if argv.count(flag) != 1:
        raise ValueError('actual guest image identity unavailable')
    image = Path(argv[argv.index(flag) + 1])
    build = json.loads((image.parent / 'build.json').read_text())
    if build.get('configuration') not in ('lemmasim-silicon-multimodal-notebook', 'lemmasim-silicon-multimodal-parameterized-notebook'):
        raise ValueError('admitted course/ASK-capable guest required')
    if sha(image) != metadata['identity'].get('guest'):
        raise ValueError('actual guest bytes changed')
    return metadata, observed, uart_path(directory, metadata)


def send_package(directory, observed, payload, transaction):
    if not 128 <= len(payload) <= 32768:
        raise ValueError('Lean school package is outside the existing raw transport bound')
    identity, edition = struct.unpack_from('<2Q', payload, 24)
    crc = struct.unpack_from('<Q', payload, 80)[0]
    packet = frame(1, identity, edition, len(payload), transaction, crc) + payload
    machine = observed.get('machine', {})
    cycle = machine.get('cycle')
    ingress = machine.get('devices', {}).get('uart_ingress', {})
    if type(cycle) is not int or cycle < 0 or ingress.get('enabled') is not True or len(packet) > 65536 - ingress.get('pending', 65536):
        raise ValueError('paused guest has insufficient admitted raw UART capacity')
    boundaries = []
    for offset in range(0, len(packet), 4096):
        boundaries.append(control(directory, {'action': 'inject', 'kind': 'uart', 'cycle': cycle,
                                             'hex': packet[offset:offset+4096].hex()}, timeout=120))
    return dict(identity=identity, edition=edition, crc32=crc, command_bytes=len(packet),
                package_sha256=hashlib.sha256(payload).hexdigest(), boundaries=boundaries)


def execute(args, out):
    directory = args.session_dir.resolve()
    executable = args.school_executable.resolve()
    if args.school_endpoint is None and not executable.is_file():
        raise ValueError('build the actual Lean school executable before using the bridge')
    metadata, observed, uart = actual_session(directory)
    captured = uart.read_bytes()
    report = dict(schema='lemma-school-client-transport/1', action=args.action,
                  guest_identity=metadata['identity'], school_authority=(dict(endpoint=args.school_endpoint) if args.school_endpoint else dict(executable=str(executable),sha256=sha(executable))),
                  session_metadata_sha256=sha(directory / 'session.json'), initial_uart_sha256=hashlib.sha256(captured).hexdigest(),
                  security='OWNER_LOCAL_INTEGRITY_ONLY', guest_school_credential='explicit school-session/1 and assistance/3 binding; hosted authority resolves principal/enrollment; no remote authentication')
    common = dict(school=args.school, actor=args.actor, course=args.course, revision=args.revision)
    clock = {} if args.now is None else {'now':args.now}
    if args.action == 'submit':
        if not args.attempt or not args.activity or args.values is None or args.task_id is None:
            raise ValueError('submit requires explicit attempt/activity/values/task-id from the learner interaction')
        values = json.loads(args.values)
        rows = [[int(value, 16) for value in match.group(1).split()] for match in ROW.finditer(captured)]
        replies = [row for row in rows if row[0] == 0x455]
        if not args.teacher_review and (not replies or replies[-1][3] != 0):
            raise ValueError('the actual guest has no completed successful checker transport receipt')
        raw_path = out / 'guest-uart.bin'; raw_path.write_bytes(captured)
        receipt = None
        if args.teacher_review:
            if args.work_artifact is None or not args.work_artifact.is_file():
                raise ValueError('teacher review requires an explicit opaque work artifact')
            work_path=args.work_artifact.resolve()
        else:
            reply = replies[-1]
            receipt = dict(source=args.course, edition=args.revision, task_id=args.task_id,
                request=reply[1], document_revision=reply[2], transport_status=reply[3], outcome=reply[4],
                guest_identity=metadata['identity'], uart_sha256=report['initial_uart_sha256'],
                scope='owner-local actual guest UART observation; explicit typed values supplied separately; no handwriting recognition')
            work_path=raw_path
        artifact = school_call(executable, args.school_root, dict(op='work-put', **common, path=str(work_path), **clock), out, 'work-put',args.school_endpoint)
        checked = {} if receipt is None else {'guestReceipt':receipt}
        response = school_call(executable, args.school_root, dict(op='attempt', **common, **clock,
            id=args.attempt, activity=args.activity, values=values, **({'reviewId':args.review_id} if args.review_id else {}), **checked,
            observationArtifact=artifact['digest']), out, 'attempt',args.school_endpoint)
        report.update(status='SCHOOL_ATTEMPT_RECORDED', result=response, guest_receipt=receipt,
            work_artifact_sha256=sha(work_path),
            receipt=('Opaque work artifact and explicit typed metadata retained for Lean authority/teacher review; no guest mathematical verdict claimed' if receipt is None else
                'Actual guest checker observation and explicit typed submission retained; hosted Lean comparison is a separate result'))
        return report
    if args.action == 'receipts':
        tags = []
        for match in ROW.finditer(captured):
            values = [int(value, 16) for value in match.group(1).split()]
            if values[0] in (0x4b1, 0x721, 0x722, 0x723, 0x724, 0x725, 0x726, 0x727):
                tags.append(values)
        report.update(status='OBSERVED_GUEST_UART', raw_records=tags,
                      receipt='Raw guest outcomes only. 725 is raster acceptance; panel completion and all-body pixel comparison are separate.')
        if args.decision:
            if not args.receipt_sequence or not any(row[0] == 0x725 and row[1] == args.receipt_sequence for row in tags):
                raise ValueError('an explicit matching guest raster acceptance sequence is required for a school delivery record')
            report['school_delivery_record'] = school_call(executable, args.school_root, dict(op='delivery', **common,
                decision=args.decision, stage='guest-accepted', receipt=dict(uart_sha256=report['initial_uart_sha256'], sequence=args.receipt_sequence, records=tags)), out, 'delivery',args.school_endpoint)
        return report
    context = None
    if args.action in ('join', 'help'):
        context = ask_context(captured)
        (out / 'guest-ask.json').write_text(json.dumps(context, indent=2) + '\n')
    if args.action == 'join':
        lifetime = {'lifetimeMs':args.lifetime_ms} if args.expires is None else {'expires':args.expires}
        response = school_call(executable, args.school_root, dict(op='join', **common, session=args.session,
            guestSession=context['session'], **lifetime, **clock, ask=context), out, 'join',args.school_endpoint)
        encoded = response.get('package_hex')
        if not isinstance(encoded,str) or len(encoded)>65536:
            raise ValueError('bounded explicit JOIN invitation missing from school authority')
        payload = bytes.fromhex(encoded); (out/'package.lcp').write_bytes(payload)
        latest = control(directory,{'action':'inspect'},timeout=120)
        if latest.get('identity') != metadata['identity'] or latest.get('running') is not False or latest.get('machine',{}).get('cycle') != observed['machine']['cycle'] or ask_context(uart.read_bytes()) != context:
            raise ValueError('guest ASK changed before invitation admission')
        admission = send_package(directory,latest,payload,args.transaction)
        report.update(status='RAW_SCHOOL_JOIN_COMMAND_ADMITTED', school_result={key:value for key,value in response.items() if key!='package_hex'},
            raw_admission=admission,actual_guest_context=context,
            receipt='Invitation bytes admitted only. Run guest to durable install, then explicitly tap JOIN and observe727; no guest enrollment acceptance inferred from school response')
        return report
    if args.action == 'review':
        if not args.review_id:
            raise ValueError('review requires the original scheduled review identifier')
        response = school_call(executable, args.school_root, dict(op='review-open', **common, id=args.review_id, **clock), out, 'review-open',args.school_endpoint)
        encoded = response.get('package_hex')
        if not isinstance(encoded, str) or len(encoded) > 65536:
            raise ValueError('bounded original review publication bytes missing')
        (out / 'package.lcp').write_bytes(bytes.fromhex(encoded))
        report.update(status='SCHOOL_DUE_REVIEW_SELECTED', school_result={key: value for key, value in response.items() if key != 'package_hex'},
            receipt='Original due publication selected by Lean authority; use the guest COURSE/LOAD/node controls and observe completed pixels to establish opening')
        return report
    if args.action == 'help':
        response = school_call(executable, args.school_root, dict(op='assist', **common, session=args.session,
            policy=args.policy, **clock, ask=context), out, 'assist',args.school_endpoint)
    else:
        response = school_call(executable, args.school_root, dict(op='client-course', **common), out, 'client-course',args.school_endpoint)
    encoded = response.get('package_hex')
    if not isinstance(encoded, str) or len(encoded) > 65536:
        raise ValueError('bounded opaque package_hex missing from Lean authority response')
    try:
        payload = bytes.fromhex(encoded)
    except ValueError as error:
        raise ValueError('Lean authority returned malformed transport bytes') from error
    (out / 'package.lcp').write_bytes(payload)
    latest = control(directory, {'action': 'inspect'}, timeout=120)
    if latest.get('identity') != metadata['identity'] or latest.get('running') is not False or latest.get('machine', {}).get('cycle') != observed['machine']['cycle']:
        raise ValueError('actual paused guest changed during school request')
    if context is not None and ask_context(uart.read_bytes()) != context:
        raise ValueError('guest ASK changed during school request')
    admission = send_package(directory, latest, payload, args.transaction)
    report.update(status='RAW_SCHOOL_COMMAND_ADMITTED', school_result={k: v for k, v in response.items() if k != 'package_hex'},
                  actual_guest_context=context, raw_admission=admission,
                  receipt='No Installed, visible or mathematical receipt. Run the actual guest, observe 4b1, then use its LOAD control and compare completed controller pixels.')
    if args.action == 'help' and response.get('decision'):
        report['school_delivery_record'] = school_call(executable, args.school_root, dict(op='delivery', **common,
            decision=response['decision'], stage='transport-admitted', receipt=admission), out, 'delivery',args.school_endpoint)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'join', 'help', 'submit', 'review', 'receipts'))
    for key in ('school-root', 'session-dir', 'work-dir'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--school-executable', type=Path, default=ROOT / '.lake/build/bin/school')
    parser.add_argument('--school-endpoint',help='Existing loopback http://127.0.0.1:PORT/v1/command authority; unchanged JSON transport')
    for key in ('school', 'actor'):
        parser.add_argument('--' + key, required=True)
    for key in ('course', 'revision'):
        parser.add_argument('--' + key, type=int, required=True)
    parser.add_argument('--session', default='lemmasim-school-session')
    for key, default in (('policy', 1), ('transaction', 1), ('lifetime-ms',3600000)):
        parser.add_argument('--' + key, type=int, default=default)
    parser.add_argument('--now',type=int); parser.add_argument('--expires',type=int)
    parser.add_argument('--decision')
    parser.add_argument('--receipt-sequence', type=int)
    parser.add_argument('--attempt'); parser.add_argument('--activity'); parser.add_argument('--values')
    parser.add_argument('--task-id', type=int); parser.add_argument('--review-id')
    parser.add_argument('--teacher-review',action='store_true'); parser.add_argument('--work-artifact',type=Path)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'build'):
        parser.error('unused ignored build work directory required')
    out.mkdir(parents=True)
    started = time.monotonic()
    try:
        report = execute(args, out)
    except BaseException as error:
        report = dict(schema='lemma-school-client-transport/1', status='FAIL', error=repr(error))
    report['seconds'] = time.monotonic() - started
    report['bridge_sha256'] = sha(__file__)
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report.get(key) for key in ('status', 'error', 'seconds', 'receipt')}))
    return 1 if report['status'] == 'FAIL' else 0


if __name__ == '__main__':
    raise SystemExit(main())
