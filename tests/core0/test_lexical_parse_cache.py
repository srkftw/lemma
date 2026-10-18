"""Lexical cache isolation and resource bounds, separate from audit authority."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import audit_core0 as audit


IR = """declare i64 @external(i64)
define i64 @entry(i64 %arg) {
  %result = call i64 @callee(i64 %arg)
  ret i64 %result
}
"""


class LexicalParseCacheTests(unittest.TestCase):
    def setUp(self):
        audit._definition_call_sets_cached.cache_clear()

    def test_returned_mutable_sets_cannot_poison_another_observer(self):
        definitions, declarations, calls = audit.parse_definitions_and_calls(IR)
        definitions.add("untrusted")
        declarations.clear()
        calls.add("fabricated")
        self.assertEqual(audit.parse_definitions_and_calls(IR),
                         ({"entry"}, {"external"}, {"callee"}))

    def test_changed_call_and_definition_never_use_the_previous_text(self):
        audit.parse_definitions_and_calls(IR)
        changed = IR.replace("@callee", "@forbidden").replace("@entry", "@different")
        self.assertEqual(audit.parse_definitions_and_calls(changed),
                         ({"different"}, {"external"}, {"forbidden"}))
        self.assertEqual(audit.parse_definitions_and_calls(IR),
                         ({"entry"}, {"external"}, {"callee"}))

    def test_large_text_bypasses_retained_storage(self):
        text = ";" + "x" * audit._LEXICAL_PARSE_MAX_CHARS + "\n" + IR
        with patch.object(audit, "_definition_call_sets_cached",
                          side_effect=AssertionError("large text retained")):
            self.assertEqual(audit.parse_definitions_and_calls(text),
                             ({"entry"}, {"external"}, {"callee"}))

    def test_distinct_inputs_have_bounded_retained_entries(self):
        cache = audit._definition_call_sets_cached
        bound = cache.cache_info().maxsize
        for index in range(bound + 5):
            audit.parse_definitions_and_calls("; " + str(index) + "\n" + IR)
        self.assertEqual(cache.cache_info().currsize, bound)
        misses = cache.cache_info().misses
        audit.parse_definitions_and_calls("; 0\n" + IR)
        self.assertEqual(cache.cache_info().misses, misses + 1)


if __name__ == "__main__":
    unittest.main()
