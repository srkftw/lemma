"""Connected hosted Lean teacher/review lifecycle, with real artifact bytes."""
import copy
import json
import unittest
import test_authority as harness


class ReviewLifecycle(unittest.TestCase):
    setUpClass = classmethod(harness.Authority.setUpClass.__func__)
    setUp = harness.Authority.setUp
    command = harness.Authority.command
    def call(self, op, **fields):
        if hasattr(self, "now"): fields.setdefault("now", self.now)
        return harness.Authority.call(self, op, **fields)
    publish = harness.Authority.publish
    enroll = harness.Authority.enroll
    attempt = harness.Authority.attempt

    def teacher(self):
        self.call("grant", subject="teacher", action="review", resource="learner")

    def work(self):
        path = self.base / "reason.txt"
        path.write_text("For each natural x, distribute both factors. The two x terms sum to 2*x.\n")
        return path.read_bytes(), self.call("work-put", actor="learner", path=str(path))["digest"]

    def judgment(self, attempt="response", version=1, previous=0, disposition="accepted", **extra):
        return self.call("human-assess", actor="teacher", attempt=attempt, version=version,
            previousSequence=previous, disposition=disposition, comment="The domain and both distribution steps are explicit.",
            criteria=["met", "met"], **extra)

    def test_teacher_opens_exact_work_and_versions_human_judgment(self):
        self.enroll(); self.teacher()
        raw, digest = self.work()
        self.attempt(id="response", activity="reason", observationArtifact=digest)
        queue = self.call("review-queue", actor="teacher", learner="learner", limit=1)
        self.assertEqual([x["key"] for x in queue["attempts"]], ["response"])
        opened = self.call("review-work", actor="teacher", attempt="response")
        self.assertEqual(opened["prompt"], self.unit["course"]["nodes"][5])
        self.assertEqual(opened["rubric"], self.unit["activities"][5]["assessment"])
        self.assertEqual(opened["workArtifact"], digest)
        artifact = self.call("review-artifact", actor="teacher", attempt="response")
        self.assertEqual(bytes.fromhex(artifact["hex"]), raw)
        self.call("review-work", actor="other-learner", attempt="response", error="grant denied")
        first = self.judgment()["assessment"]
        self.assertTrue(self.judgment()["reused"])
        self.judgment(version=2, previous=0, error="version conflict")
        second = self.judgment(version=2, previous=first["sequence"], disposition="clarification")["assessment"]
        self.assertGreater(second["sequence"], first["sequence"])
        feedback = self.call("feedback", actor="learner")["feedback"]
        self.assertEqual(len(feedback), 2)
        self.assertEqual(feedback[-1]["data"]["scope"].split(";")[0], "human-review/1")
        original = self.call("progress", actor="learner")["attempts"][0]
        self.assertEqual(original["data"]["outcome"], 4)
        self.assertEqual(original["data"]["checker"], "teacher-review/1")
        self.call("feedback-read", actor="other-learner", sequence=second["sequence"], error="another learner")
        self.call("grant", subject="teacher", action="review", resource="learner", revoked=True)
        self.call("review-artifact", actor="teacher", attempt="response", error="grant denied")

    def test_due_review_requires_subsequent_response_and_real_assessment(self):
        self.enroll(); self.teacher(); _,digest = self.work()
        self.attempt(id="original")
        now=86400001;self.now=now
        original=copy.deepcopy(self.call("progress",actor="learner",now=now)["attempts"][0])
        self.call("review-open",actor="learner",id="original")
        self.assertEqual(len(self.call("progress",actor="learner")["due"]),1)
        self.attempt(id="wrong",reviewId="original",error="original publication/activity")
        self.attempt(id="response",activity="later-review",reviewId="original",observationArtifact=digest)
        self.assertEqual(self.call("progress",actor="learner")["due"],[])
        row=self.call("review-work",actor="teacher",attempt="response")["attempt"]
        self.assertEqual(row["data"]["outcome"],4)
        assessed=self.judgment()["assessment"]
        self.assertEqual(self.call("progress",actor="learner")["due"],[])
        self.call("review-open",actor="learner",id="original",error="not due")
        self.judgment(version=2,previous=assessed["sequence"],disposition="needs-revision")
        self.assertEqual([r["key"] for r in self.call("progress",actor="learner")["due"]],["original"])
        self.assertEqual(self.call("progress",actor="learner")["attempts"][0],original)
        self.attempt(id="response-2",activity="later-review",reviewId="original",observationArtifact=digest)
        self.judgment(attempt="response-2")
        later=self.call("progress",actor="learner",now=now+86400001)["due"]
        self.assertEqual([r["key"] for r in later],["response-2"])
        self.assertEqual(later[0]["data"]["revision"],1)

    def test_catalogue_arbitrary_identity_pagination_and_enrollment_revocation(self):
        for identity in (802, 900):
            unit=copy.deepcopy(self.unit);unit["course"]["identity"]=str(identity)
            unit["course"]["title"] += str(identity)
            self.publish(unit)
            self.call("enroll",learner="learner",course=identity,revision=1)
        first=self.call("course-catalogue",actor="learner",limit=1)
        self.assertEqual(first["courses"][0]["course"],802);self.assertTrue(first["more"])
        second=self.call("course-catalogue",actor="learner",limit=1,after=first["next"])
        self.assertEqual(second["courses"][0]["course"],900);self.assertFalse(second["more"])
        self.call("enrollment-revoke",learner="learner",course=802,revision=1)
        self.call("client-course",actor="learner",course=802,revision=1,error="revoked")
        self.assertEqual([r["course"] for r in self.call("course-catalogue",actor="learner")["courses"]],[900])
        self.call("course-catalogue",actor="learner",limit=51,error="limit")

    def test_defer_withdraw_and_no_self_or_false_human_acceptance(self):
        self.enroll();self.teacher();self.attempt(id="response",activity="reason")
        self.call("human-assess",actor="learner",attempt="response",error="distinct reviewer")
        self.call("human-assess",actor="teacher",attempt="response",version=1,previousSequence=0,
            disposition="accepted",comment="Not yet justified",criteria=["met","unclear"],error="every original")
        self.call("review-state",actor="learner",id="response",status="deferred",due=100000000,reason="Allow more time")
        self.assertEqual(self.call("progress",actor="learner",now=86400001)["due"],[])
        self.call("review-state",actor="learner",id="response",status="withdrawn",reason="Work on another goal")
        self.assertEqual(self.call("progress",actor="learner",now=100000001)["due"],[])

if __name__ == "__main__":
    unittest.main()
