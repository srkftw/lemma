import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from silicon_hold_decode import require_recipe


class JointRecipe(unittest.TestCase):
    def arguments(self, **changes):
        values = dict(hold_decode_from=Path('build/qualified-joint'),
                      routed_eco_from=Path('build/actual-two-load-route'),
                      clock_min_routing_layer='Metal3', detail_route_iterations=8,
                      host_memory_gib=6, selected_implementation=False)
        values.update(changes)
        return SimpleNamespace(**values)

    def test_exact_unselected_recipe(self):
        require_recipe(self.arguments())

    def test_declared_resource_and_route_controls_cannot_drift(self):
        for changes in (dict(clock_min_routing_layer='Metal2'),
                        dict(detail_route_iterations=3), dict(host_memory_gib=4),
                        dict(routed_eco_from=None), dict(selected_implementation=True)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                require_recipe(self.arguments(**changes))

    def test_no_mixed_geometry_or_completion_recipe(self):
        for flag in ('two_load_launch_from', 'well_fill_from', 'fresh_core_power_grid',
                     'preserve_routed_netlist', 'completed_well_fill_route_from',
                     'preferred_access_from', 'group_button_bus'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                require_recipe(self.arguments(**{flag: True}))


if __name__ == '__main__':
    unittest.main()
