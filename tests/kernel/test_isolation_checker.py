"""Failure fixtures and actual API signatures; no guest execution claim."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import create_autospec

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_kernel_isolation import check, ISOLATION_ARGUMENTS, TYPED_ARGUMENTS, ATTACKS, SENTINEL
from check_kernel_user import USER_STATUS, mix, satp
from core0_common import Core0Error
from run_kernel import Session


class IsolationCheckerFailures(unittest.TestCase):
    def session(self, directory, configuration='user-isolation-development', mutate=None):
        session = create_autospec(Session, instance=True)
        session.image = directory / 'image.elf'
        (directory / 'user-text.bin').write_bytes(bytes(512))
        (directory / 'user').mkdir()
        functions = [{'source': 'Lemma.User.Development.Isolation.' + suffix, 'symbol': 'lemma_user_' + suffix}
                     for suffix, _, _ in ATTACKS.values()]
        (directory / 'user/unit.json').write_text(json.dumps({'functions': functions}))
        case = {'user-isolation-development': 'none', 'user-csr-development': 'supervisor-csr', 'user-nx-development': 'execute-data',
                'user-kernel-fetch-development': 'execute-kernel', 'user-misaligned-development': 'execute-misaligned'}[configuration]
        typed_fault_pc = {'none': 0, 'supervisor-csr': 0x10080, 'execute-data': 0x20000,
                          'execute-kernel': 0x80200000, 'execute-misaligned': 0x10002}[case]
        ranges = {'_user_start': {'base': 0x10000, 'bytes': 64},
                  **{'lemma_user_' + suffix: {'base': 0x10100 + index * 32, 'bytes': 8}
                     for index, (suffix, _, _) in enumerate(ATTACKS.values())}}
        session.binding = {'configuration': configuration, 'stage': 'supervisor', 'startup_case': 'normal', 'user_startup_case': case,
                           'task_kernel_stack':{'pages':2,'bytes':8192,'construction':'owned-physically-contiguous-pair','base_owned_task_frames':17},
                           'elf': {'user': {'exit_ecall_pc': 0x10020, 'function_ranges': ranges,
                                            'quarantined_startup': {'case': case, 'fault_pc': typed_fault_pc}}}}
        kernel_root, victim_root, private, root = 0x82000000, 0x8200d000, 0x82012000, 0x8201f000
        records = [(0xa, 0x87e00000, 1, 512, 0x82000000), (0xc0, 0x534543414c4c0001, 0x1b1b1f1818, 0xb1ff, 0x1446),
                   (0xc1, 2, 3, 1, 0), (0xc2, 17, 22, 22, 123456), (0xd3, kernel_root, satp(kernel_root), 500, 0)]
        isolation = case == 'none'; baseline = 481 if isolation else 500
        if isolation: records += [(0xd5, 524, victim_root, 0x40000, private), (0xd6, 2, SENTINEL, 481, 0)]
        arguments = ISOLATION_ARGUMENTS if isolation else TYPED_ARGUMENTS
        for argument in arguments:
            if isolation and argument not in ATTACKS:
                records += [(0xd1, 8, 0x10020, USER_STATUS, satp(root)), (0xd2, 0, mix(argument), baseline - 18, baseline)]
            else:
                if isolation:
                    suffix, cause, value = ATTACKS[argument]; pc = ranges['lemma_user_' + suffix]['base']; data = 0
                else:
                    cause, pc, value, data = {'supervisor-csr': (2, 0x10080, 0, mix(argument)),
                                              'execute-data': (12, 0x20000, 0x20000, mix(argument)),
                                              'execute-kernel': (12, 0x80200000, 0x80200000, mix(argument)),
                                              'execute-misaligned': (2, 0x10002, 0, mix(argument))}[case]
                records += [(0xd4, cause, pc, value, USER_STATUS), (0xdc, cause, pc, USER_STATUS, satp(root)),
                            (0xd2, 44, data, baseline - 18, baseline)]
            if isolation: records += [(0xd7, 524, SENTINEL, 481, 0)]
        if mutate is not None: mutate(records)
        session.record.side_effect = records
        session.command.side_effect = [(0xd0, 1036 + index * 512, root, 0x10000, 512) for index in range(len(arguments))]
        return session

    def test_four_faults_each_continue_preserve_peer_and_reclaim_frames(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            session = self.session(Path(temporary)); report = check(session)
            self.assertEqual((report['actual_faults'], report['fresh_attacker_runs']), (4, 8))
            self.assertEqual([call.args for call in session.command.call_args_list], [(1, arg, 0, 0, 0) for arg in ISOLATION_ARGUMENTS])

    def test_wrong_peer_origin_pc_data_or_reclamation_rejects(self):
        for row, column, value in [(5, 4, 0x8200d000), (6, 1, 3), (6, 2, 0), (7, 1, 15), (7, 2, 0x10000),
                                   (7, 3, 0), (7, 4, 0x200000120), (8, 4, satp(0x8200d000)),
                                   (9, 2, 1), (9, 4, 480), (10, 2, 0)]:
            with self.subTest(row=row, column=column), tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
                def mutate(records):
                    values = list(records[row]); values[column] = value; records[row] = tuple(values)
                with self.assertRaises(Core0Error): check(self.session(Path(temporary), mutate=mutate))

    def test_typed_probes_require_actual_expected_faults(self):
        for configuration in ['user-csr-development', 'user-nx-development', 'user-kernel-fetch-development', 'user-misaligned-development']:
            with self.subTest(configuration=configuration), tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
                session=self.session(Path(temporary), configuration);report=check(session)
                self.assertEqual((report['actual_faults'],report['fresh_attacker_runs']), (3,3))
                self.assertEqual([call.args for call in session.command.call_args_list],[(1,arg,0,0,0) for arg in TYPED_ARGUMENTS])
            with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
                def mutate(records):
                    values = list(records[5]); values[1] = 12 if configuration in {'user-csr-development','user-misaligned-development'} else 2; records[5] = tuple(values)
                with self.assertRaises(Core0Error): check(self.session(Path(temporary), configuration, mutate))

    def test_typed_restarts_require_new_instances_and_later_recovery(self):
        for row,column,value in [(8,1,12),(10,2,mix(7)),(10,4,499),(13,4,499)]:
            with self.subTest(row=row,column=column), tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
                def mutate(records):
                    values=list(records[row]);values[column]=value;records[row]=tuple(values)
                with self.assertRaises(Core0Error):check(self.session(Path(temporary),'user-csr-development',mutate))
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            session=self.session(Path(temporary),'user-csr-development')
            session.command.side_effect=[(0xd0,1036,0x8201f000,0x10000,512)]*3
            with self.assertRaises(Core0Error):check(session)
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            with self.assertRaises(Core0Error):check(self.session(Path(temporary),'user-csr-development'),arguments=(7,))

    def test_halfword_fixture_rejects_ialign32_claim_or_wrong_observed_halfword(self):
        for column,value in [(1,0),(2,0x10088),(3,0x10002)]:
            with self.subTest(column=column), tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
                def mutate(records):
                    values=list(records[5]);values[column]=value;records[5]=tuple(values)
                with self.assertRaises(Core0Error):check(self.session(Path(temporary),'user-misaligned-development',mutate))

    def test_nonexecutable_target_irq_then_fault_is_contained_not_resumed_as_exit(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            def inject(records):
                records.insert(5, (0xdf, 0x8000000000000001, 0x80200000, USER_STATUS, satp(0x8201f000)))
            report = check(self.session(Path(temporary), 'user-kernel-fetch-development', inject))
            self.assertEqual(report['actual_user_supervisor_notifications'], 1)
            self.assertEqual(report['cases'][0]['returned_and_torn_down'][1], 44)
        for column, value in [(1, 8), (2, 0x10020), (3, 0x80200004), (4, 0x200000120)]:
            with self.subTest(column=column), tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
                def mutate(records):
                    values = list(records[5]); values[column] = value; records[5] = tuple(values)
                with self.assertRaises(Core0Error):check(self.session(Path(temporary), 'user-kernel-fetch-development', mutate))

    def test_normal_image_and_incomplete_corpus_cannot_claim_isolation(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            session = self.session(Path(temporary)); session.binding['configuration'] = 'normal'
            with self.assertRaises(Core0Error): check(session)
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            with self.assertRaises(Core0Error): check(self.session(Path(temporary)), arguments=(1, 0))


if __name__ == '__main__': unittest.main(verbosity=2)
