from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_lemmasim_capacity import construction, CAPACITY
from audit_kernel import weighted_stack_graph, validate_stack_entries
from core0_common import Core0Error


class CapacityAuditFailures(unittest.TestCase):
    def test_missing_ownership_construction_cannot_certify_capacity(self):
        with self.assertRaises(Core0Error):
            construction({'functions':[]}, '')

    def test_usable_capacity_excludes_both_sentinel_reservations_and_vector(self):
        self.assertEqual(CAPACITY, 4 * 4096 - 2 * 16)
        unit={'role':'kernel','roots':[{'source':'boot','symbol':'root'},
                                      {'source':'dispatch','symbol':'trap'}]}
        graph={'weighted_frame_chains':{'root':{'bytes':0,'chain':['root']},
                                       'trap':{'bytes':8080-288,'chain':['trap']}}}
        entries=validate_stack_entries(unit,graph,capacities={'boot':61440,'kernel-trap':CAPACITY},vector_bytes=288)
        self.assertEqual(entries[1]['total_bytes'],8080)
        self.assertEqual(entries[1]['margin_bytes'],8272)
        graph['weighted_frame_chains']['trap']['bytes']=CAPACITY-288
        with self.assertRaises(Core0Error):
            validate_stack_entries(unit,graph,capacities={'boot':61440,'kernel-trap':CAPACITY},vector_bytes=288)

    def test_unknown_machine_boundary_cannot_be_assigned_zero_stack(self):
        ir='define i64 @root() {\nentry:\n  %v = call i64 @unaccounted()\n  ret i64 %v\n}\ndeclare i64 @unaccounted()\n'
        with self.assertRaises(Core0Error):
            weighted_stack_graph(ir,{'root':16},{})


if __name__=='__main__':
    unittest.main()
