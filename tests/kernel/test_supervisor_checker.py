"""Failure-input tests only; these fixtures do not establish guest execution."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from core0_common import Core0Error
from check_kernel_supervisor import validate_positive_records, validate_machine_origin_trace, check


def records():
    return [(0xa,0x87e00000,1,512,0x82000000),
            (0xc0,0x534543414c4c0001,0x1b1b1f1818,0xb1ff,0x1446),
            (0xc1,2,3,1,0),(0xc2,17,22,22,123456)]


class SupervisorCheckerFailures(unittest.TestCase):
    def test_exact_four_record_protocol_is_required(self):
        self.assertEqual(validate_positive_records(records())['actual_irq_delta'],1)
        for value in [[],records()[:-1],records()+[records()[0]],[(False,*records()[0][1:]),*records()[1:]]]:
            with self.assertRaises(Core0Error):validate_positive_records(value)
    def test_boot_csr_irq_and_rejection_tampering_fails(self):
        for row,column,value in [(0,2,0),(0,1,0x80000000),(1,1,0),(1,2,0),(1,3,0),
                                 (2,2,2),(2,3,0),(2,4,1),(3,1,0),(3,2,0),(3,3,0),(3,4,0)]:
            with self.subTest(row=row,column=column):
                bad=[list(r) for r in records()];bad[row][column]=value
                with self.assertRaises(Core0Error):validate_positive_records([tuple(r) for r in bad])
    def test_positive_checker_cannot_use_a_development_or_bootstrap_image(self):
        class Fixture:
            def record(self):raise AssertionError('unqualified image must not read records')
        for config,stage,case in [('frames-development','supervisor','normal'),('normal','bootstrap-m','normal'),('machine-origin-development','bootstrap-m','machine-origin-probe')]:
            session=Fixture();session.binding={'configuration':config,'stage':stage,'startup_case':case}
            with self.assertRaises(Core0Error):check(session)
    def test_actual_machine_ecall_trace_is_bound_to_audited_pc(self):
        # Exact formatting observed from the pinned QEMU, including its shorter
        # prefixed PC. This is a parser regression, not execution evidence.
        line='riscv_cpu_do_interrupt: hart:0, async:0, cause:000000000000000b, epc:0x800001a4, tval:0x0000000000000000, desc=machine_ecall\n'
        self.assertEqual(validate_machine_origin_trace(line,expected_pc=0x800001a4)['cause'],11)
        for changed in ['',line+line,line.replace('hart:0','hart:1'),line.replace('async:0','async:1'),
                        line.replace('000000000000000b','0000000000000009'),line.replace('800001a4','800001a8'),
                        line.replace('tval:0x0000000000000000','tval:0x0000000000000001'),line.replace('machine_ecall','supervisor_ecall')]:
            with self.assertRaises(Core0Error):validate_machine_origin_trace(changed,expected_pc=0x800001a4)


if __name__=='__main__':unittest.main(verbosity=2)
