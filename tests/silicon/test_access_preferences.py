# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from silicon_access_metadata import AccessMetadataError
from silicon_access_preference import unused_output
from silicon_preferred_route import admit, require_recipe, require_tcl
from silicon_enclosure import GeometryError


class AccessPreferenceTests(unittest.TestCase):
    def test_retained_route_cannot_escape_exact_legacy_constraints(self):
        valid = dict(preferred_access_from=Path('build/qualified'), preferred_access_preflight_only=False,
                     capacity_launch_buffer_from=Path('build/327'), routed_eco_from=Path('build/104'),
                     clock_min_routing_layer='Metal3', detail_route_iterations=8,
                     host_memory_gib=6, selected_implementation=False)
        require_recipe(SimpleNamespace(**valid))
        require_recipe(SimpleNamespace(**{**valid, 'preferred_access_preflight_only': True}))
        for key, value in [('capacity_launch_buffer_from', None), ('routed_eco_from', None),
                           ('clock_min_routing_layer', 'Metal2'), ('detail_route_iterations', 3),
                           ('host_memory_gib', 4), ('selected_implementation', True)]:
            with self.subTest(key=key), self.assertRaises(GeometryError):
                require_recipe(SimpleNamespace(**{**valid, key: value}))
        with self.assertRaises(GeometryError):
            require_recipe(SimpleNamespace(**{**valid, 'preferred_access_from': None,
                                               'preferred_access_preflight_only': True}))
        with tempfile.TemporaryDirectory() as path, self.assertRaises(GeometryError):
            admit(Path(path))

    def test_actual_consumer_cannot_recompute_PA_drop_metadata_or_snapshots(self):
        source = (Path(__file__).resolve().parents[2] / 'tooling/silicon/pen-extracted-eco.tcl').read_text()
        require_tcl(source)
        mutations = [('-no_pin_access', ''), ('set_debug_level DRT snapshot 1', 'set_debug_level DRT snapshot 0'),
                     ('detailed_route_debug -snapshot_dir $out/route-snapshots', ''),
                     ('lemma_check_retained_access before-route', ''),
                     ('lemma_check_retained_access after-route', ''),
                     ('read_guides $retained_access_guides', 'global_route -guide_file $out/route.guide'),
                     ('file copy $retained_access_guides $out/route.guide', ''),
                     ('if {$expected ne $actual}', 'if {0}'),
                     ('load $retained_access_exporter Lemmaap', ''),
                     ('-drc_report_iter_step 1', '-drc_report_iter_step 0')]
        for old, new in mutations:
            with self.subTest(mutation=old), self.assertRaises(GeometryError):
                require_tcl(source.replace(old, new))
        with self.assertRaises(GeometryError):
            require_tcl(source + '\npin_access -verbose 1\n')

    def test_output_cannot_overwrite_or_alias_source(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path); source = root / 'source.odb'; source.write_bytes(b'original')
            output = root / 'new.odb'
            unused_output(source, output)
            for forbidden in (source, root / 'same.odb', root / 'hard.odb'):
                if forbidden.name == 'same.odb':
                    forbidden.symlink_to(source)
                elif forbidden.name == 'hard.odb':
                    forbidden.hardlink_to(source)
                with self.subTest(path=forbidden.name), self.assertRaises(AccessMetadataError):
                    unused_output(source, forbidden)
            output.write_bytes(b'existing')
            with self.assertRaises(AccessMetadataError):
                unused_output(source, output)
            self.assertEqual(source.read_bytes(), b'original')


if __name__ == '__main__':
    unittest.main()
