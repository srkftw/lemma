"""Behavioral regression checks for consent scope identity and replay retention."""
import unittest
import test_authority as authority


class PrivacyScopes(unittest.TestCase):
    # Reuse only the transport/setup helpers, without inheriting its test corpus.
    setUp = authority.Authority.setUp
    command = authority.Authority.command
    call = authority.Authority.call
    stage = authority.Authority.stage

    def consent(self, learner, resource, version=1, **changes):
        data = dict(schema="lemma-observation-consent/1", version=version,
                    school="school-a", learner=learner, resource=resource,
                    collection=True, processing=True, upload=False, retention=True,
                    training=True, exportAllowed=False, revoked=False)
        data.update(changes)
        self.call("consent", actor=learner, consent=data)
        return data

    def observation(self, learner, source, id_, artifact):
        return dict(schema="lemma-observation/1", id=id_, executionId=id_, school="school-a",
                    learner=learner, modality="ink", sourceClass="syntheticFixture", sourceId=source,
                    acquiredAt=100, acquisitionClock="device-clock", calibration=None,
                    quality="deliberately synthetic fixture", missingness="present", artifact=artifact,
                    origin="synthetic", parentObservationIds=[], execution="live", executionAt=200,
                    executionClock="device-clock", replayOf=None)

    def test_dotted_actor_and_resource_pairs_cannot_replace_each_others_consent(self):
        digest = self.stage("synthetic scope-collision regression bytes")
        self.consent("a.b", "c")
        first = self.observation("a.b", "c", "first-acquisition", digest)
        self.call("observation-put", actor="a.b", observation=first)
        self.assertEqual(len(self.call("dataset-eligible", actor="a.b")["observations"]), 1)
        # Both names are legal; their tuple is distinct despite naive dot-joining.
        self.consent("a", "b.c", version=2, training=False)
        second = self.observation("a", "b.c", "second-acquisition", digest)
        self.call("observation-put", actor="a", observation=second)
        self.assertEqual(len(self.call("dataset-eligible", actor="a.b")["observations"]), 1)
        self.assertEqual(self.call("dataset-eligible", actor="a")["observations"], [])
        self.consent("a.b", "c", version=2, training=False)
        self.assertEqual(self.call("dataset-eligible", actor="a.b")["observations"], [])
        self.assertEqual(len(self.call("observations", actor="a")["observations"]), 1)

    def test_processing_does_not_grant_new_durable_replay_after_retention_revoked(self):
        digest = self.stage("synthetic retention regression bytes")
        self.consent("learner", "fixture-ink")
        original = self.observation("learner", "fixture-ink", "ink-original", digest)
        self.call("observation-put", actor="learner", observation=original)
        self.consent("learner", "fixture-ink", version=2, retention=False)
        replay = dict(actor="learner", id="ink-original", executionId="replay-after-retention",
                      executionAt=500, executionClock="replay-clock")
        self.call("observation-replay", **replay, error="not consented")
        self.assertEqual(self.call("dataset-eligible", actor="learner")["observations"], [])
        # Previously retained acquisition remains original, with no deletion claim.
        self.assertEqual(len(self.call("observations", actor="learner")["observations"]), 1)
        self.consent("learner", "fixture-ink", version=3)
        admitted = self.call("observation-replay", **replay)["record"]["data"]
        self.assertEqual(admitted["id"], original["id"])
        self.assertEqual(admitted["acquiredAt"], original["acquiredAt"])
        self.assertEqual(admitted["origin"], "synthetic")
