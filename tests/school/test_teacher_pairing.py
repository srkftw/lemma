"""Real protected teacher invitation/enrollment with private random handoff."""
import hashlib
import json
import os
import socket
import subprocess
import sys
import unittest
import urllib.request

import test_authority as harness
import test_admission as admission


class TeacherPairing(unittest.TestCase):
    setUpClass=classmethod(harness.Authority.setUpClass.__func__)
    setUp=harness.Authority.setUp
    command=harness.Authority.command
    call=harness.Authority.call
    publish=harness.Authority.publish
    enroll=harness.Authority.enroll
    issue=admission.Admission.issue

    def test_admitted_teacher_pairs_enrolls_and_revokes_without_owner_identity(self):
        self.enroll('alice');self.enroll('bob')
        self.call('grant',subject='teacher',action='admin',resource='school')
        self.call('grant',subject='teacher',action='enroll',resource='school')
        token=self.issue('teacher')
        ports=[]
        sockets=[]
        for _ in range(2):
            sock=socket.socket();sock.bind(('127.0.0.1',0));sockets.append(sock);ports.append(sock.getsockname()[1])
        for sock in sockets:sock.close()
        teacher=self.base/'teacher.json'
        teacher.write_text(json.dumps({'schema':'lemma-school-credential/1','school':'school-a',
            'learner':'teacher','token':token,'endpoint':f'http://127.0.0.1:{ports[1]}/v1/client'}))
        teacher.chmod(0o600)
        transport=[sys.executable,str(harness.REPO/'scripts/school_transport.py'),'--binary',str(harness.BINARY),str(self.root)]
        def invoke(op,*args,private=False,success=True):
            command=[*transport,op,*args]
            if private:command += ['--credential',str(teacher)]
            else:command += ['--school','school-a','--actor','owner']
            run=subprocess.run(command,cwd=harness.REPO,capture_output=True,timeout=25)
            self.assertNotIn(token.encode(),run.stdout+run.stderr)
            self.assertNotIn(token,' '.join(command))
            self.assertEqual(run.returncode==0,success,run.stdout+run.stderr)
            return run
        invoke('start','--port',str(ports[0]),'--client-port',str(ports[1]))
        self.addCleanup(lambda:invoke('stop'))
        carol=self.base/'carol.json'
        created=invoke('pair','--learner','carol','--to',str(carol),private=True)
        self.assertEqual(carol.stat().st_mode & 0o777,0o600)
        handoff=json.loads(carol.read_text())
        self.assertEqual(handoff['endpoint'],f'http://127.0.0.1:{ports[1]}/v1/client')
        self.assertEqual(len(bytes.fromhex(handoff['token'])),32)
        self.assertNotIn(handoff['token'].encode(),created.stdout+created.stderr)
        self.assertNotIn(handoff['token'],(self.root/'state.json').read_text())
        invoke(json.dumps(dict(op='enroll',learner='carol',course=1,revision=1,actor='owner',school='wrong')),private=True)
        def learner(op):
            request=urllib.request.Request(handoff['endpoint'],data=json.dumps(dict(op=op,actor='owner')).encode(),
                headers={'Authorization':'Bearer '+handoff['token'],'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=10) as reply:return json.load(reply)
        catalogue=learner('course-catalogue')
        self.assertTrue(catalogue['ok'],catalogue)
        self.assertEqual([row['course'] for row in catalogue['result']['courses']],[1])
        invoke('revoke-pair','--token-hash',hashlib.sha256(handoff['token'].encode()).hexdigest(),private=True)
        self.assertIn('revoked',learner('progress')['error'])
        invoke(json.dumps(dict(op='grant',school='school-a',actor='owner',subject='teacher',
                               action='admin',resource='school',revoked=True)))
        denied=invoke('pair','--learner','mallory','--to',str(self.base/'denied.json'),
                      '--actor','owner',private=True,success=False)
        self.assertIn(b'grant denied',denied.stdout)
        teacher.chmod(0o644)
        rejected=invoke(json.dumps(dict(op='progress')),private=True,success=False)
        self.assertIn(b'private file',rejected.stderr)
        teacher.chmod(0o600)
        saved=teacher.read_bytes()
        for malformed in [[],dict(schema='lemma-school-credential/1',
                                  endpoint=f'http://127.0.0.1:{ports[1]}/v1/client',token=1)]:
            teacher.write_text(json.dumps(malformed))
            invoke(json.dumps(dict(op='progress')),private=True,success=False)
        teacher.write_bytes(saved)
        state=json.loads((self.root/'state.json').read_text())['payload']
        enrolled=[row for row in state['records'] if row['kind']=='enrollment' and row['data'].get('learner')=='carol']
        self.assertEqual(enrolled[0]['actor'],'teacher')
        issued=[row for row in state['records'] if row['kind']=='admission' and row['data'].get('learner')=='carol']
        self.assertEqual([row['actor'] for row in issued],['teacher','teacher'])


if __name__=='__main__':unittest.main()
