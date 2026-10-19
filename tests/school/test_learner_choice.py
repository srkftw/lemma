"""Actual Lean authority learner declarations; worker suggestions tested separately.

The pure fixture explicitly labels its synthetic suggestion. No Python transition
implementation or direct snapshot injection supplies an operational suggestion.
"""
import copy
import json
import subprocess
import unittest
import test_authority as authority


class LearnerChoices(unittest.TestCase):
    setUp = authority.Authority.setUp
    command = authority.Authority.command
    call = authority.Authority.call
    publish = authority.Authority.publish
    enroll = authority.Authority.enroll
    attempt = authority.Authority.attempt

    @classmethod
    def setUpClass(cls):
        cls.unit = json.loads(subprocess.check_output([str(authority.CURRICULUM), "fixture"], cwd=authority.REPO))
        cls.unit["course"]["identity"] = "1"

    def choice(self, op="goal-set", **changes):
        data = dict(actor="learner", id="choice-1", course=1, revision=1, policy=1,
                    reason="I want to reconstruct this reasoning independently",
                    referenceKind="attempt", reference="attempt-1")
        if op == "goal-set":
            data["newGoal"] = "Explain why the middle coefficient is two"
        data.update(changes)
        return self.call(op, **data)

    def test_native_goal_challenge_retry_and_original_provenance(self):
        self.enroll()
        self.attempt()
        original = self.call("progress", actor="learner")["attempts"][0]
        first = self.choice()["record"]
        retry = self.choice(learner="learner", now=9)["record"]
        self.assertEqual(first, retry)
        challenge = self.choice("interpretation-challenge", id="challenge-1", now=10)["record"]
        choices = self.call("learner-choices", actor="learner")["choices"]
        self.assertEqual(choices, [first, challenge])
        self.assertEqual(self.call("progress", actor="learner")["attempts"], [original])
        self.assertEqual(first["actor"], "learner")
        self.assertEqual(first["data"]["policy"], original["data"]["policy"])
        self.assertEqual(first["data"]["original"]["sequence"], original["sequence"])
        self.assertEqual(first["data"]["original"]["key"], original["key"])
        self.assertEqual(first["artifacts"], original["artifacts"])
        self.choice(reason="Conflicting reuse of the same ID", now=11, error="idempotency conflict")
        self.assertEqual(len(self.call("learner-choices", actor="learner")["choices"]), 2)

    def test_read_grant_does_not_authorize_correct_write(self):
        self.enroll()
        self.attempt()
        self.choice(actor="teacher", learner="learner", error="grant denied")
        self.call("grant", subject="teacher", action="read", resource="learner")
        self.assertEqual(self.call("learner-choices", actor="teacher", learner="learner")["choices"], [])
        self.choice(actor="teacher", learner="learner", error="grant denied")
        self.call("grant", subject="teacher", action="correct", resource="learner")
        declared = self.choice(actor="teacher", learner="learner")["record"]
        self.assertEqual(declared["actor"], "teacher")
        self.assertEqual(declared["data"]["learner"], "learner")
        self.assertEqual(self.call("learner-choices", actor="learner")["choices"], [declared])
        self.call("learner-choices", actor="peer", learner="learner", error="grant denied")
        self.call("grant", subject="teacher", action="correct", resource="learner", revoked=True)
        self.choice(actor="teacher", learner="learner", error="grant denied")

    def test_exact_owner_publication_policy_and_bounded_fields(self):
        self.enroll()
        self.call("enroll", learner="peer", course=1, revision=1)
        self.attempt()
        self.choice(actor="peer", error="another learner")
        second = copy.deepcopy(self.unit)
        second["course"]["edition"] = "2"
        self.publish(second)
        self.call("enroll", learner="learner", course=1, revision=2)
        self.choice(revision=2, error="original publication differs")
        self.choice(policy=2, error="publication policy differs")
        self.choice(reference="missing", error="reference absent")
        self.choice(newGoal="x" * 513, error="1..512")
        self.choice(reason=" \n", error="1..1024")
        self.choice(reason="x" * 1025, error="1..1024")
        self.choice(changeChecker=True, error="unsupported learner choice field")
        self.choice("suggestion-override", error="suggestion reference")
        self.choice("suggestion-override", referenceKind="suggestion", error="reference absent")
        self.assertEqual(self.call("learner-choices", actor="learner")["choices"], [])

    def test_synthetic_pure_suggestion_constraints_and_immutable_history(self):
        result = subprocess.run(["lake", "env", "lean", "--run", "tests/school/LearnerChoiceMain.lean"],
                                cwd=authority.REPO, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        checks = json.loads(result.stdout)
        self.assertGreaterEqual(len(checks), 17)
        self.assertTrue(all(checks.values()), checks)
