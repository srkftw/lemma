from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_lemmasim_capacity import construction, CAPACITY
from audit_kernel import (weighted_stack_graph, validate_stack_entries,
                          validate_fresh_descriptor_base_call, validate_owned_task_stack)
from core0_common import Core0Error


class CapacityAuditFailures(unittest.TestCase):
    def test_ordinary_and_sim_four_page_audits_propagate_closed_helper_failure(self):
        # Ordinary audit_kernel invokes the same construction/helper checks.
        # A rejected fresh-base route must remain rejected in both bindings.
        for configuration,expanded in [('service-normal',False),('lemmasim-notebook',True)]:
            unit={'configuration':configuration,'role':'kernel','functions':[]}
            with patch('audit_lemmasim_capacity.construction',
                       side_effect=Core0Error('unchecked stack helper')) as construction_check:
                with self.assertRaisesRegex(Core0Error,'unchecked stack helper'):
                    validate_owned_task_stack({'task_kernel_stack_pages':4,
                        'task_kernel_stack_bytes':16384},unit,'retained pre-IR')
                construction_check.assert_called_once_with(unit,'retained pre-IR',**({} if expanded else {'expanded':False}))

    def test_shared_base_is_exact_fresh_success_result(self):
        body='''entry:
  %result = call { i64, i64 } @checked(i64 %arg0)
  %statusWord = extractvalue { i64, i64 } %result, 0
  %status = trunc i64 %statusWord to i8
  %base = extractvalue { i64, i64 } %result, 1
  %ok = icmp eq i8 %status, 0
  br i1 %ok, label %accepted, label %rejected
accepted:
  %validated = call { i64, i64 } @stack(i64 %base)
  ret { i64, i64 } %validated
rejected:
  ret { i64, i64 } { i64 50, i64 0 }
'''
        self.assertEqual(validate_fresh_descriptor_base_call(body,'checked','stack')['validated_base'],'%base')
        for altered in [body.replace('@stack(i64 %base)','@stack(i64 %arg0)'),
                        body.replace('@stack(i64 %base)','@stack(i64 2181038080)'),
                        body.replace('icmp eq i8 %status, 0','icmp eq i8 %status, 1'),
                        body.replace('label %accepted, label %rejected','label %rejected, label %accepted'),
                        body.replace('ret { i64, i64 } { i64 50, i64 0 }',
                            '%bypass = call { i64, i64 } @stack(i64 %base)\n  ret { i64, i64 } %bypass')]:
            with self.assertRaises(Core0Error):
                validate_fresh_descriptor_base_call(altered,'checked','stack')

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
