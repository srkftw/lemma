# SPDX-License-Identifier: Apache-2.0
import ast
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from check_sg13g2_sample_hold import inspect, model_tree, require_model_tree


class OriginalProcessSampleHold(unittest.TestCase):
    def test_exact_tested_circuit_is_promoted_without_geometry_or_wiring_change(self):
        self.assertEqual(hashlib.sha256((ROOT/'engineering/multimodal/differential-sample-hold-sg13g2.cir').read_bytes()).hexdigest(),
                         '2b3392a517d7a2d0f59f9a255059bdc775564836ec3543cc26ca5f61c49e910a')

    def test_consumed_model_tree_rejects_changed_missing_extra_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'source'; copied=root/'case-models'
            source.mkdir(); copied.mkdir()
            for path in (source,copied): (path/'actual.lib').write_text('original model bytes')
            expected=model_tree(source); require_model_tree(copied,expected)
            (copied/'actual.lib').write_text('changed compact model')
            with self.assertRaises(RuntimeError): require_model_tree(copied,expected)
            (copied/'actual.lib').unlink()
            with self.assertRaises(RuntimeError): require_model_tree(copied,expected)
            (copied/'actual.lib').write_text('original model bytes'); (copied/'extra.lib').write_text('extra')
            with self.assertRaises(RuntimeError): require_model_tree(copied,expected)
            (copied/'extra.lib').unlink(); (copied/'empty').mkdir()
            with self.assertRaises(RuntimeError): require_model_tree(copied,expected)
            (copied/'empty').rmdir(); (copied/'actual.lib').unlink(); (copied/'actual.lib').symlink_to(source/'actual.lib')
            with self.assertRaises(RuntimeError): require_model_tree(copied,expected)

    def test_partial_or_nonfinite_waveform_never_produces_operation_pass(self):
        with self.assertRaises(RuntimeError): inspect([])
        with self.assertRaises(RuntimeError): inspect([[float('nan')]*16]*20000)

    def test_actual_nominal_and_negative_waveforms_keep_strict_observation_relation(self):
        pilot = ROOT/'build/multimodal/task009-sample-hold-pilot-a1'
        if not (pilot/'nominal/waveform.dat').exists(): self.skipTest('actual source-bound SPICE waveforms not retained')
        def rows(name):
            return [[float(x) for x in line.split()] for line in (pilot/name/'waveform.dat').read_text().splitlines()[1:]]
        nominal = rows('nominal'); counts, failed, measured = inspect(nominal)
        self.assertFalse(failed)
        self.assertTrue(all(n >= 20 for n in counts.values()))
        self.assertLess(measured['max_held_differential_error_V'], .000041)
        for name in ('continuous-track', 'crossed-held-pair'):
            self.assertTrue(inspect(rows(name))[1])
        with self.assertRaises(RuntimeError): inspect(nominal[:-100])
        changed = deepcopy(nominal); changed[1000][6] = float('nan')
        with self.assertRaises(RuntimeError): inspect(changed)
        old = ast.parse((pilot/'run.py').read_text()); new = ast.parse((ROOT/'scripts/check_sg13g2_sample_hold.py').read_text())
        function = lambda tree: next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == 'inspect')
        self.assertEqual(ast.dump(function(old), include_attributes=False), ast.dump(function(new), include_attributes=False))


if __name__ == '__main__': unittest.main()
