"""Protected actual HTTP observations, distinct from trusted presentation evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import unittest
import urllib.request

import test_authority as harness
import test_admission as admission
import test_guest_submission as submission


class Delivery(unittest.TestCase):
    setUpClass=classmethod(harness.Authority.setUpClass.__func__)
    setUp=harness.Authority.setUp
    command=harness.Authority.command
    call=harness.Authority.call
    publish=harness.Authority.publish
    enroll=harness.Authority.enroll
    issue=admission.Admission.issue

    def start(self):
        sockets=[]
        for _ in range(2):
            item=socket.socket();item.bind(('127.0.0.1',0));sockets.append(item)
        ports=[item.getsockname()[1] for item in sockets]
        for item in sockets:item.close()
        log=(self.base/f'service-{time.monotonic_ns()}.log').open('wb')
        self.addCleanup(log.close)
        self.server=subprocess.Popen([sys.executable,str(harness.REPO/'scripts/school_transport.py'),
            '--binary',str(harness.BINARY),str(self.root),'run','--port',str(ports[0]),
            '--client-port',str(ports[1])],cwd=harness.REPO,stdout=log,stderr=log,start_new_session=True)
        self.endpoint=f'http://127.0.0.1:{ports[1]}/v1/client'
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if self.server.poll() is not None:raise RuntimeError('owned actual school transport exited; inspect service log')
            try:
                ready=json.loads((self.root/'transport.json').read_text())
                if ready['pid']==self.server.pid and ready['clientPort']==ports[1]:return
            except (OSError,ValueError,KeyError):pass
            time.sleep(0.02)
        raise RuntimeError('owned actual school transport startup8s deadline')

    def stop(self):
        server=getattr(self,'server',None)
        if server is None:return
        if server.poll() is None:
            os.killpg(server.pid,signal.SIGTERM)
            try:server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid,signal.SIGKILL);server.wait(timeout=3)
        self.server=None

    def client(self,token,op,error=None,**fields):
        request=urllib.request.Request(self.endpoint,data=json.dumps(dict(op=op,**fields)).encode(),
            headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
        with urllib.request.urlopen(request,timeout=12) as reply:response=json.load(reply)
        if error:
            self.assertFalse(response['ok'],response);self.assertIn(error,response['error']);return response
        self.assertTrue(response['ok'],response);return response['result']

    def test_original_context_partial_cancel_raw_records_and_lost_ack_restart(self):
        self.enroll('alice');self.enroll('bob')
        alice=self.issue('alice');bob=self.issue('bob');teacher=self.issue('teacher')
        self.call('grant',subject='teacher',action='admin',resource='school')
        self.call('grant',subject='teacher',action='review',resource='alice')
        self.addCleanup(self.stop);self.start()
        ask=harness.Authority.ask(self);ask.update(revision=1,object=0x504b000000000001)
        joined=self.client(alice,'join',course=1,revision=1,session='delivery-live',guestSession=41,
                           lifetimeMs=10000,ask=ask)
        invitation=bytes.fromhex(joined['package_hex']);span=submission.word(invitation,112)
        context=bytes.fromhex(invitation[span & 0xffffffff:(span & 0xffffffff)+(span>>32)].decode())
        package=bytes.fromhex(self.client(alice,'client-course',course=1,revision=1)['package_hex'])
        packagePath=self.base/'package.bin';packagePath.write_bytes(package)
        contextPath=self.base/'context.bin';contextPath.write_bytes(context)
        artifactPath=self.base/'actual-work.bin'
        fixture=subprocess.run(['lake','env','lean','--run','tests/school/SubmissionFixture.lean',
            str(packagePath),str(contextPath),str(artifactPath),'2','4'],cwd=harness.REPO,capture_output=True,timeout=40)
        self.assertEqual(fixture.returncode,0,(fixture.stdout+fixture.stderr).decode())
        artifact=artifactPath.read_bytes()
        self.assertEqual(submission.word(artifact,56),ask['revision'])
        authored=self.client(alice,'assist',session='delivery-live',ask=ask)
        decision=authored['decision']
        digest=hashlib.sha256(b'exact retained opaque packet').hexdigest()
        uart=hashlib.sha256(b'exact complete console observation').hexdigest()
        def observation(kind,payload,token=alice,**changes):
            request=dict(decision=decision,sequence=1,observer='native-owned-execution-a',kind=kind,observation=payload)
            request.update(changes)
            return self.client(token,'delivery-observe',**request)
        state=lambda:json.loads((self.root/'state.json').read_text())['payload']
        original=copy.deepcopy(next(r for r in state()['records'] if r['kind']=='decision'))
        partial=dict(admittedBytes=64,wireBytes=200,packetSHA256=digest)
        first=observation('transport',partial)
        self.assertFalse(first['reused']);self.assertIn('not guest acceptance',first['scope'])
        repeat=observation('transport',dict(reversed(list(partial.items()))))
        self.assertTrue(repeat['reused']);self.assertEqual(first['commitSequence'],repeat['commitSequence'])
        snapshot=state()['records'][:]
        observation('transport',partial,token=bob,error='principal differs')
        observation('transport',partial,sequence=2,error='sequence differs')
        observation('transport',dict(partial,admittedBytes=201),error='outside declared')
        observation('transport',dict(partial,visible=True),error='unknown delivery')
        observation('guest-raster',dict(record=[0x725,2,1,0,0],uartSHA256=uart),error='original ASK sequence')
        observation('guest-rejected',dict(record=[0x724,0,1,99,0],uartSHA256=uart),error='rejection record')
        observation('guest-rejected',dict(record=[0x724,4,1,100,0],uartSHA256=uart),error='original ASK context')
        self.assertEqual(state()['records'],snapshot)
        accepted=observation('guest-raster',dict(record=[0x725,1,1,0,0],uartSHA256=uart))
        self.assertIn('panel completion',accepted['scope'])
        rejection=observation('guest-rejected',dict(record=[0x724,4,1,ask['object'],0],uartSHA256=uart))
        self.assertIn('no presentation',rejection['scope'])
        panel=dict(cycle=500,completed=7,accepted=8,busy=1,targetSHA256='a'*64,visibleSHA256='b'*64,hashEncoding='gray4')
        controller=observation('controller-snapshot',panel)
        self.assertIn('do not establish',controller['scope'])
        observation('controller-snapshot',dict(panel,busy=2),error='not a bit')
        observation('controller-snapshot',dict(panel,completed=9),error='exceeds accepted')
        observation('controller-snapshot',dict(panel,visibleSHA256='bad'),error='SHA256')
        observation('controller-snapshot',dict(panel,bodyVisible=True),error='unknown delivery')
        cancelled=observation('cancelled',dict(reason='user-cancel'))
        self.assertEqual(cancelled['commitSequence'],observation('cancelled',dict(reason='user-cancel'))['commitSequence'])
        captured=self.client(alice,'guest-submit',hex=artifact.hex())
        reviewed=self.client(teacher,'review-work',attempt=captured['attempt'])
        exposure=reviewed['attempt']['data']['deliveryObservations']
        self.assertEqual(len(exposure),5)
        self.assertTrue(all(r['kind']=='delivery' and r['data']['schema']=='lemma-school-delivery-observation/1' for r in exposure))
        self.assertEqual(reviewed['attempt']['data']['outcome'],4)
        self.client(alice,'cancel-session',session='delivery-live')
        self.client(alice,'assist',session='delivery-live',ask=ask,error='cancelled')
        self.assertEqual(observation('transport',partial)['commitSequence'],first['commitSequence'])
        before=state();self.stop();self.start()
        self.assertEqual(observation('transport',partial)['commitSequence'],first['commitSequence'])
        after=state()
        self.assertEqual(after['generation'],before['generation']+1)
        self.assertEqual(after['records'],before['records'])
        self.assertEqual(observation('transport',partial)['commitSequence'],first['commitSequence'])
        other=observation('controller-snapshot',panel,observer='native-owned-execution-b')
        self.assertNotEqual(other['observation'],controller['observation'])
        self.client(teacher,'admission-revoke',tokenHash=hashlib.sha256(alice.encode()).hexdigest())
        observation('transport',partial,error='revoked')
        final=state();self.assertEqual(next(r for r in final['records'] if r['kind']=='decision'),original)
        rows=[r for r in final['records'] if r['kind']=='delivery']
        self.assertEqual(len(rows),6)
        self.assertTrue(all(r['data']['decision']==decision and r['data']['ask']==ask and r['data']['edition']==1 and
                            r['data']['artifact']==authored['artifact'] for r in rows))
        self.assertEqual(len([r for r in final['records'] if r['kind']=='attempt']),1)
        print(json.dumps(dict(deliveryObservations=len(rows),transportPartial=True,originalDecisionUnchanged=True,
                              exactRetryCommit=first['commitSequence'],restartGeneration=final['generation'],
                              rawRasterIsNotVisible=True,changedObserverDistinct=True,revocationEnforced=True,guestAttemptRetainsTypedObservations=len(exposure),teacherOriginalArtifactContext=True)))


    def test_replaced_join_and_unrelated_page_publication_generation_do_not_taint_work(self):
        self.enroll('alice');alice=self.issue('alice');teacher=self.issue('teacher')
        self.call('grant',subject='teacher',action='review',resource='alice')
        edition=copy.deepcopy(self.unit);edition['course']['edition']='2'
        self.call('publish',definition=edition,policy=2);self.call('enroll',learner='alice',course=1,revision=2)
        other=copy.deepcopy(self.unit);other['course']['identity']='2'
        self.call('publish',definition=other,policy=3);self.call('enroll',learner='alice',course=2,revision=1)
        self.addCleanup(self.stop);self.start()
        original=harness.Authority.ask(self);original.update(revision=1,object=0x504b000000000001)
        variants=[dict(object=0x504b000000000002),dict(session=42),dict(consent=8),dict(edition=2),dict(source=2)]
        def join(ask):
            return self.client(alice,'join',course=ask['source'],revision=ask['edition'],
                session='reused-live-context',guestSession=ask['session'],lifetimeMs=10000,ask=ask)
        for sequence,changes in enumerate(variants,1):
            ask=dict(original,sequence=sequence,**changes);join(ask)
            authored=self.client(alice,'assist',session='reused-live-context',ask=ask)
            self.client(alice,'delivery-observe',decision=authored['decision'],sequence=sequence,
                observer='unrelated-context-'+str(sequence),kind='transport',observation=dict(
                    admittedBytes=1,wireBytes=1,packetSHA256=hashlib.sha256(str(sequence).encode()).hexdigest()))
        old=json.loads((self.root/'state.json').read_text())['payload']
        self.stop();self.start()
        ask=dict(original,sequence=6);joined=join(ask)
        # No current assistance was requested. Historical authored/transport
        # reports retain their own contexts and cannot mark this artifact assisted.
        invitation=bytes.fromhex(joined['package_hex']);span=submission.word(invitation,112)
        context=bytes.fromhex(invitation[span&0xffffffff:(span&0xffffffff)+(span>>32)].decode())
        package=bytes.fromhex(self.client(alice,'client-course',course=1,revision=1)['package_hex'])
        packagePath=self.base/'current-package.bin';contextPath=self.base/'current-context.bin';artifactPath=self.base/'current-work.bin'
        packagePath.write_bytes(package);contextPath.write_bytes(context)
        fixture=subprocess.run(['lake','env','lean','--run','tests/school/SubmissionFixture.lean',
            str(packagePath),str(contextPath),str(artifactPath),'2','4'],cwd=harness.REPO,capture_output=True,timeout=40)
        self.assertEqual(fixture.returncode,0,(fixture.stdout+fixture.stderr).decode())
        captured=self.client(alice,'guest-submit',hex=artifactPath.read_bytes().hex())
        reviewed=self.client(teacher,'review-work',attempt=captured['attempt'])
        data=reviewed['attempt']['data']
        self.assertEqual(data['deliveryObservations'],[])
        self.assertFalse(data['assisted'])
        self.assertEqual(data['outcome'],4)
        after=json.loads((self.root/'state.json').read_text())['payload']
        self.assertEqual(after['records'][:len(old['records'])],old['records'])
        self.assertEqual(len([r for r in after['records'] if r['kind']=='delivery']),5)
        print(json.dumps(dict(unrelatedContexts=5,immutableHistoricalReports=True,
            currentAssistance=False,guestArtifactOutcome=4,fullOriginalJoinContext=True)))


if __name__=='__main__':unittest.main()
