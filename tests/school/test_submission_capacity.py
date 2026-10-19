"""Real protected v1/v2 admission with complete multi-stroke work and limits.

The maintained Lean fixture keeps a genuine Action-produced mathematical
workspace and constructs explicit raw stimulus records. This is hosted API and
storage evidence, separate from the target queue/native/browser scenario.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
import urllib.request

import test_authority as harness
import test_admission as admission
import test_guest_submission as submission


class SubmissionCapacity(unittest.TestCase):
    setUpClass=classmethod(harness.Authority.setUpClass.__func__)
    setUp=harness.Authority.setUp
    command=harness.Authority.command
    publish=harness.Authority.publish
    enroll=harness.Authority.enroll
    issue=admission.Admission.issue
    fixture=submission.GuestSubmission.fixture

    def call(self,op,*,error=None,root=None,**fields):
        if not getattr(self,'owner_port',None):
            return harness.Authority.call(self,op,error=error,root=root,**fields)
        self.assertIsNone(root)
        return self.post(f'http://127.0.0.1:{self.owner_port}/v1/command',self.command(op,**fields),error=error)

    def post(self,endpoint,command,*,token=None,error=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        req=urllib.request.Request(endpoint,data=json.dumps(command).encode(),headers=headers)
        with urllib.request.urlopen(req,timeout=30) as reply:result=json.load(reply)
        if error:
            self.assertFalse(result['ok'],result);self.assertIn(error,result['error']);return result
        self.assertTrue(result['ok'],result)
        return result['result']

    def client(self,token,op,**fields):
        error=fields.pop('error',None)
        return self.post(f'http://127.0.0.1:{self.client_port}/v1/client',dict(op=op,**fields),token=token,error=error)

    def start_transport(self):
        held=[];ports=[]
        for _ in range(2):
            sock=socket.socket();sock.bind(('127.0.0.1',0));held.append(sock);ports.append(sock.getsockname()[1])
        for sock in held:sock.close()
        self.owner_port,self.client_port=ports
        log=(self.base/'transport.log').open('wb')
        process=subprocess.Popen([sys.executable,str(harness.REPO/'scripts/school_transport.py'),
            '--binary',str(harness.BINARY),str(self.root),'run','--port',str(ports[0]),'--client-port',str(ports[1])],
            cwd=harness.REPO,stdout=log,stderr=log,start_new_session=True)
        log.close()
        def stop():
            try:
                if process.poll() is None:self.call('stop');process.wait(timeout=5)
            finally:
                if process.poll() is None:process.terminate();process.wait(timeout=5)
        self.addCleanup(stop)
        deadline=time.monotonic()+10
        while True:
            try:self.call('status');break
            except (OSError,urllib.error.URLError):
                if time.monotonic()>=deadline:raise
                time.sleep(.05)

    def test_complete_32_and512_strokes_preserve_v1_and_enforce_total_byte_limit(self):
        self.enroll('alice');self.start_transport()
        token,base,_=self.fixture(kind=2)
        legacy=self.client(token,'guest-submit',hex=base.hex())
        self.assertEqual(legacy['outcome'],4)
        original=json.loads((self.root/'state.json').read_text())['payload']['records']
        source=self.base/'envelope-2.bin'
        directory=self.base/'capacity'
        run=subprocess.run(['lake','env','lean','--run','tests/school/SubmissionCapacity.lean',str(source),str(directory)],
            cwd=harness.REPO,capture_output=True,timeout=60)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertEqual(json.loads(run.stdout)['checks'],10)
        rows=json.loads((directory/'results.json').read_text())
        self.assertEqual([(r['chunks'],r['bytes']) for r in rows if r.get('wireVersion')==2],
                         [(32,12928),(512,126976),(9,254440)])
        receipts=[]
        work=[]
        for i,name in enumerate(['v2-32-strokes.bin','v2-512-strokes.bin','v2-nine-full.bin'],1):
            artifact=(directory/name).read_bytes()
            artifact=submission.change(submission.change(artifact,24,submission.word(base,24)+i),32,17+i)
            receipt=self.client(token,'guest-submit',hex=artifact.hex())
            self.assertEqual(receipt['outcome'],4)
            opened=self.client(token,'review-work',attempt=receipt['attempt'])
            envelope=opened['attempt']['data']['guestEnvelope']
            self.assertEqual(envelope['wireVersion'],2)
            self.assertEqual(len(envelope['chunks']),[32,512,9][i-1])
            self.assertTrue(any(not chunk['visible'] for chunk in envelope['chunks']))
            receipts.append(receipt);work.append(artifact)
        current=json.loads((self.root/'state.json').read_text())['payload']['records']
        self.assertEqual(current[:len(original)],original)
        self.assertEqual(self.client(token,'review-artifact',attempt=legacy['attempt'])['hex'],base.hex())
        replay=self.client(token,'guest-submit',hex=work[0].hex())
        self.assertTrue(replay['reused']);self.assertEqual(replay['commitSequence'],receipts[0]['commitSequence'])
        self.client(token,'guest-submit',hex=submission.change(work[0],112,121).hex(),error='different immutable work')
        self.client(token,'guest-submit',hex=(directory/'v2-over-limit.bin').read_bytes().hex(),error='1..262144')
        # The same actual shared rasterizer sees all admitted visible strokes;
        # no host handwriting implementation or false verification is involved.
        rendered=self.client(token,'review-render',attempt=receipts[0]['attempt'])
        self.assertGreater(rendered['segments'],16)
        self.assertGreater(rendered['changedPixels'],100)
        self.client(token,'cancel-session',session='guest-one')
        self.assertTrue(self.client(token,'guest-submit',hex=work[0].hex())['reused'])
        fresh=submission.change(submission.change(work[0],24,submission.word(base,24)+10),32,27)
        self.client(token,'guest-submit',hex=fresh.hex(),error='cancelled')
        attempts=self.client(token,'progress')['attempts']
        self.assertEqual(len(attempts),4)
        self.assertEqual([a['data']['revision'] for a in attempts],[1,1,1,1])
        print(json.dumps({'completeRawChunks':[32,512,9],'artifactBytes':[len(x) for x in work],
                          'visibleRenderedSegments':rendered['segments'],'changedPixels':rendered['changedPixels'],
                          'legacyArtifactUnchanged':True,'exactRetryCommitUnchanged':True}))


if __name__=='__main__':unittest.main()
