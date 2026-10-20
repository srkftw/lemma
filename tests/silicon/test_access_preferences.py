# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import copy
from types import SimpleNamespace
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from silicon_access_metadata import AccessMetadataError
from silicon_access_writer import relation
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
                     ('exec $retained_access_python $retained_access_writer_check', 'puts'),
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

    def test_pinned_writer_copies_only_original_BPin_APs_once(self):
        master = {'id':1, 'point_nm':[2880,820], 'owner':{'kind':'master_pin'}, 'segments':[]}
        pin = {'id':2, 'point_nm':[200,300], 'owner':{'kind':'block_pin','bterm':'addr[0]','bpin_id':7},
               'layer':'Metal2','via_groups':[], 'segments':[], 'directions':['NORTH']}
        before = {'schema':'lemma-opendb-access-export/1','block':'lemma_pen','db_units_per_micron':1000,
                  'access_points':[master,pin], 'master_pin_patterns':[{'patterns':[[1]]}],
                  'instance_terminals':[{'instance':'target','preferred':[1]}],
                  'block_terminals':[{'terminal':'addr[0]','bpin_id':7,'access':[2]},
                                     {'terminal':'empty','bpin_id':8,'access':[]}]}
        after = copy.deepcopy(before)
        after['access_points'].append({**copy.deepcopy(pin),'id':3})
        after['block_terminals'][0]['access'].append(3)
        self.assertEqual(relation(before,after)['literal_added_BPin_copies'],1)
        mutations = {
            'wrong_original_preference':lambda x:x['instance_terminals'][0]['preferred'].__setitem__(0,2),
            'wrong_shared_pattern':lambda x:x['master_pin_patterns'][0]['patterns'][0].append(2),
            'original_AP_changed':lambda x:x['access_points'][0]['point_nm'].__setitem__(0,2885),
            'clone_owner_crossed':lambda x:x['access_points'][2]['owner'].__setitem__('bpin_id',8),
            'clone_point_changed':lambda x:x['access_points'][2]['point_nm'].__setitem__(0,205),
            'clone_direction_changed':lambda x:x['access_points'][2]['directions'].append('UP'),
            'clone_segment_invented':lambda x:x['access_points'][2]['segments'].append([0,0,1,1]),
            'clone_via_changed':lambda x:x['access_points'][2]['via_groups'].append(['Via1_YY']),
            'clone_id_renumbered':lambda x:x['access_points'][2].__setitem__('id',4),
            'clone_vector_missing':lambda x:x['block_terminals'][0]['access'].pop(),
            'clone_vector_double':lambda x:x['block_terminals'][0]['access'].append(3),
            'block_owner_retargeted':lambda x:x['block_terminals'][0].__setitem__('terminal','addr[1]'),
            'unbound_extra_AP':lambda x:x['access_points'].append({**copy.deepcopy(pin),'id':4}),
            'original_AP_deleted':lambda x:x['access_points'].pop(0),
            'unknown_metadata_field':lambda x:x.__setitem__('hidden',True)}
        for label,mutate in mutations.items():
            value=copy.deepcopy(after);mutate(value)
            with self.subTest(label=label),self.assertRaises(AccessMetadataError):
                relation(before,value)
        with self.assertRaises(AccessMetadataError):
            relation(before,before)


if __name__ == '__main__':
    unittest.main()
