"""Protocol/mutation fixtures only, never labelled actual U-mode evidence."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import create_autospec

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from core0_common import Core0Error
from run_kernel import Session
from check_kernel_user import check, mix, satp, USER_STATUS


class UserCheckerFailures(unittest.TestCase):
    def session(self, directory, arguments=(7,), changes=None):
        session=create_autospec(Session,instance=True)
        session.image=directory/'image.elf'
        (directory/'user-text.bin').write_bytes(bytes(128))
        session.binding={'configuration':'normal','stage':'supervisor','startup_case':'normal',
                         'task_kernel_stack':{'pages':4,'bytes':16384,'construction':'owned-physically-contiguous-four','base_owned_task_frames':19},
                         'elf':{'user':{'exit_ecall_pc':0x10020,'function_ranges':{'_user_start':{'base':0x10000,'bytes':128}}}}}
        kernel_root=0x82000000;root=0x8200d000
        records=[(0xa,0x87e00000,1,512,0x82000000),
                 (0xc0,0x534543414c4c0001,0x1b1b1f1818,0xb1ff,0x1446),
                 (0xc1,2,3,1,0),(0xc2,17,22,22,123456),(0xd3,kernel_root,satp(kernel_root),500,0)]
        for argument in arguments:
            records.extend([(0xdf,0x8000000000000001,0x10004,USER_STATUS,satp(root)),
                            (0xd1,8,0x10020,USER_STATUS,satp(root)),(0xd2,0,mix(argument),480,500)])
        if changes is not None:changes(records)
        session.record.side_effect=records
        session.command.side_effect=[(0xd0,524+index*512,root,0x10000,128) for index in range(len(arguments))]
        return session
    def test_real_session_method_signatures_and_fresh_arguments_are_preserved(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            session=self.session(Path(temporary),arguments=(0,7,2**64-1))
            report=check(session,arguments=(0,7,2**64-1))
            self.assertEqual(report['fresh_user_runs'],3)
            self.assertEqual(report['actual_user_supervisor_notifications'],3)
            self.assertEqual([call.args for call in session.command.call_args_list],[(1,0,0,0,0),(1,7,0,0,0),(1,2**64-1,0,0,0)])
    def test_kernel_satp_user_origin_pc_and_frame_recovery_tampering_rejects(self):
        for row,column,value in [(4,2,0),(5,1,8),(5,3,0x200000120),(6,1,9),(6,2,0x10024),
                                 (6,3,0x200000120),(6,4,satp(0x82000000)),(7,2,0),(7,3,484),(7,4,499)]:
            with self.subTest(row=row,column=column),tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
                def mutate(records):
                    values=list(records[row]);values[column]=value;records[row]=tuple(values)
                with self.assertRaises(Core0Error):check(self.session(Path(temporary),changes=mutate),arguments=(7,))
    def test_nonowned_roots_duplicate_descriptors_and_empty_arguments_reject(self):
        with self.assertRaises(Core0Error):satp(0x80200000)
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            session=self.session(Path(temporary),arguments=(0,7))
            session.command.side_effect=[(0xd0,524,0x8200d000,0x10000,128)]*2
            with self.assertRaises(Core0Error):check(session,arguments=(0,7))
            with self.assertRaises(Core0Error):check(session,arguments=())


if __name__=='__main__':unittest.main(verbosity=2)
