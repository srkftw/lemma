"""Actual Lean principal resolution; no caller-selected identity or host paths."""
import hashlib
import json
import os
import secrets
import subprocess
import sys
import unittest
import test_authority as harness


class Admission(unittest.TestCase):
    setUpClass=classmethod(harness.Authority.setUpClass.__func__)
    setUp=harness.Authority.setUp
    command=harness.Authority.command
    call=harness.Authority.call
    publish=harness.Authority.publish
    enroll=harness.Authority.enroll

    def issue(self,principal):
        token=secrets.token_hex(32)
        self.call("admission-issue",learner=principal,tokenHash=hashlib.sha256(token.encode()).hexdigest())
        return token

    def client(self,token,op,**fields):
        error=fields.pop("error",None)
        return self.call("client",token=token,command=dict(op=op,**fields),error=error)

    def test_two_principals_replay_revocation_and_path_separation(self):
        self.enroll("alice");self.enroll("bob")
        alice=self.issue("alice");bob=self.issue("bob")
        courses=self.client(alice,"course-catalogue",actor="owner",school="wrong")
        self.assertEqual(courses["courses"][0]["course"],1)
        self.client(alice,"work-put",path="/etc/passwd",error="outside bounded")
        self.client(alice,"publish",path="/etc/passwd",error="host paths")
        self.client(alice,"enroll",learner="alice",course=1,revision=1,error="grant denied")
        digest=self.client(alice,"work-upload",hex=b"Alice's original reasoning".hex())["digest"]
        fields=dict(course=1,revision=1,activity="reason",id="alice-attempt",values=[0,0,0,0,0],observationArtifact=digest)
        self.client(bob,"attempt",**dict(fields,id="bob-stolen"),error="not owned")
        self.client(alice,"attempt",actor="owner",**fields)
        self.client(alice,"attempt",actor="owner",**fields)
        progress=self.client(alice,"progress")
        self.assertEqual(len(progress["attempts"]),1)
        self.assertEqual(progress["attempts"][0]["actor"],"alice")
        self.assertEqual(self.client(bob,"progress")["attempts"],[])
        self.client(bob,"progress",learner="alice",error="grant denied")
        self.assertNotIn(alice,(self.root/"state.json").read_text())
        self.call("admission-revoke",tokenHash=hashlib.sha256(alice.encode()).hexdigest())
        self.client(alice,"progress",error="revoked")
        self.assertEqual(self.client(bob,"progress")["attempts"],[])

    def test_same_credential_can_teach_only_with_scope_and_revoke_takes_effect(self):
        self.enroll("alice")
        token=self.issue("teacher")
        self.client(token,"review-queue",learner="alice",error="grant denied")
        self.call("grant",subject="teacher",action="review",resource="alice")
        self.assertEqual(self.client(token,"review-queue",learner="alice")["attempts"],[])
        self.call("grant",subject="teacher",action="review",resource="alice",revoked=True)
        self.client(token,"review-queue",learner="alice",error="grant denied")
        self.client(token,"publish",definition=self.unit,policy=1,error="grant denied")
        self.call("grant",subject="teacher",action="publish",resource="school")
        self.assertTrue(self.client(token,"publish",definition=self.unit,policy=1)["reused"])

    def test_lost_help_acknowledgement_reuses_exact_context_until_cancelled(self):
        self.enroll("alice"); token=self.issue("alice")
        ask=harness.Authority.ask(self)
        self.client(token,"join",course=1,revision=1,session="alice-guest",guestSession=41,lifetimeMs=10000,ask=ask)
        first=self.client(token,"assist",session="alice-guest",ask=ask)
        second=self.client(token,"assist",session="alice-guest",ask=ask)
        self.assertEqual(first["package_hex"],second["package_hex"])
        self.assertEqual(first["decision"],second["decision"])
        self.assertTrue(second["reused"])
        self.client(token,"cancel-session",session="alice-guest")
        self.client(token,"assist",session="alice-guest",ask=ask,error="cancelled")

    def test_pair_uses_private_os_random_handoff_and_no_raw_token_in_stdout(self):
        self.enroll("alice")
        credential=self.base/"alice.json"
        result=subprocess.run([sys.executable,str(harness.REPO/"scripts/school_transport.py"),"--binary",str(harness.BINARY),
            str(self.root),"pair","--school","school-a","--actor","owner","--learner","alice","--to",str(credential)],
            capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        handoff=json.loads(credential.read_text())
        self.assertEqual(credential.stat().st_mode & 0o777,0o600)
        self.assertEqual(len(bytes.fromhex(handoff["token"])),32)
        self.assertNotIn(handoff["token"].encode(),result.stdout+result.stderr)
        self.assertEqual(len(self.client(handoff["token"],"course-catalogue")["courses"]),1)

if __name__=="__main__":unittest.main()
