import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_kernel import optimizer_intrinsics, validate_notebook_loss_intrinsic
from core0_common import Core0Error


class NotebookLossIntrinsicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((Path(__file__).with_name('fixtures') / 'notebook_loss_intrinsic.json').read_text())

    def check(self, ir=None, unit=None, optimized=True):
        return validate_notebook_loss_intrinsic(
            self.fixture['ir']['post' if optimized else 'pre'] if ir is None else ir,
            self.fixture['unit'] if unit is None else unit,
            optimized=optimized, optimization='O2')

    def test_genuine_pre_and_post_counter(self):
        self.assertIsNone(self.check(optimized=False)['intrinsic'])
        self.assertEqual(self.check()['intrinsic'], 'llvm.uadd.sat.i64')
        self.assertEqual(self.check()['bits'], 64)
        self.assertFalse(self.check()['foreign_runtime'])

    def test_only_the_named_notebook_owner_selects_intrinsic(self):
        self.assertIn('llvm.uadd.sat.i64', optimizer_intrinsics(self.fixture['unit']))
        for field, value in [('role', 'kernel'), ('image_key', 'store')]:
            unit = copy.deepcopy(self.fixture['unit']); unit[field] = value
            with self.subTest(field=field):
                self.assertNotIn('llvm.uadd.sat.i64', optimizer_intrinsics(unit))
                with self.assertRaises(Core0Error): self.check(unit=unit)

    def test_wrong_counter_operand_or_width_rejected(self):
        ir = self.fixture['ir']['post']
        for bad in [ir.replace('i64 %action.call.value21, i64 %bin48', 'i64 %action.call.value15, i64 %bin48'),
                    ir.replace('llvm.uadd.sat.i64', 'llvm.uadd.sat.i32'),
                    ir.replace('llvm.uadd.sat.i64', 'llvm.usub.sat.i64')]:
            with self.subTest(mutation=bad[-80:]):
                with self.assertRaises(Core0Error): self.check(ir=bad)

    def test_wrong_pre_overflow_condition_or_published_field_rejected(self):
        ir = self.fixture['ir']['pre']
        for before, after in [('icmp ult i64 %bin42, %bin48', 'icmp ugt i64 %bin42, %bin48'),
                              ('(i64 32, i64 %if.result57)', '(i64 40, i64 %if.result57)')]:
            self.assertIn(before, ir)
            with self.subTest(mutation=before):
                with self.assertRaises(Core0Error): self.check(ir=ir.replace(before, after), optimized=False)

    def test_extra_intrinsic_owner_or_early_declaration_rejected(self):
        extra = '\ndefine i64 @unexpected(i64 %x) {\n %y = call i64 @llvm.uadd.sat.i64(i64 %x, i64 1)\n ret i64 %y\n}\n'
        with self.assertRaises(Core0Error): self.check(ir=self.fixture['ir']['post'] + extra)
        with self.assertRaises(Core0Error): self.check(ir=self.fixture['ir']['pre'] + '\ndeclare i64 @llvm.uadd.sat.i64(i64, i64)\n', optimized=False)

    def test_changed_effects_and_duplicate_source_rejected(self):
        unit = copy.deepcopy(self.fixture['unit'])
        owner = next(r for r in unit['functions'] if r['source'].endswith('.multimodalRawLoss'))
        owner['effects'] = []
        with self.assertRaises(Core0Error): self.check(unit=unit)
        unit = copy.deepcopy(self.fixture['unit']); unit['functions'].append(copy.deepcopy(unit['functions'][0]))
        with self.assertRaises(Core0Error): self.check(unit=unit)


class NotebookReceiptLossIntrinsicTests(NotebookLossIntrinsicTests):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((Path(__file__).with_name('fixtures') / 'notebook_loss_receipt2.json').read_text())

    def test_receipt_invalidation_precedes_loss(self):
        for optimized in (False, True):
            result = self.check(optimized=optimized)
            self.assertEqual(result['contract_version'], 'lemma-notebook-loss-saturation/2')
            self.assertEqual(result['first_invalidation_address'], 3410688)

    def test_wrong_counter_operand_or_width_rejected(self):
        ir = self.fixture['ir']['post']
        for before, after in [('i64 %action.call.value28, i64 %bin55', 'i64 %action.call.value10, i64 %bin55'),
                              ('llvm.uadd.sat.i64', 'llvm.uadd.sat.i32')]:
            self.assertIn(before, ir)
            with self.assertRaises(Core0Error): self.check(ir=ir.replace(before, after))

    def test_wrong_pre_overflow_condition_or_published_field_rejected(self):
        ir = self.fixture['ir']['pre']
        self.assertIn('add i64 %call0, 2816', ir)
        for before, after in [('add i64 %call0, 2816', 'add i64 %call0, 2824'),
                              ('ret i64 3407872', 'ret i64 3407880'),
                              ('icmp ult i64 %bin49, %bin55', 'icmp ugt i64 %bin49, %bin55'),
                              ('(i64 32, i64 %if.result64)', '(i64 40, i64 %if.result64)')]:
            self.assertIn(before, ir)
            with self.assertRaises(Core0Error): self.check(ir=ir.replace(before, after), optimized=False)

    def test_missing_or_wrong_first_invalidation_rejected(self):
        ir = self.fixture['ir']['post']
        clear = '  store volatile i64 0, ptr inttoptr (i64 3410688 to ptr), align 256\n'
        self.assertIn(clear, ir)
        for bad in (ir.replace(clear, ''), ir.replace(clear, clear.replace('3410688', '3410696'))):
            with self.assertRaises(Core0Error): self.check(ir=bad)

    def test_receipt_marker_cannot_select_legacy_body(self):
        unit = copy.deepcopy(self.fixture['unit'])
        unit['functions'] = [row for row in unit['functions'] if not row['source'].endswith('.deferredSaved')]
        for optimized in (False, True):
            with self.assertRaises(Core0Error): self.check(unit=unit, optimized=optimized)

    def test_receipt_marker_requires_pure_zero_argument_definition(self):
        for field, value in [('args', ['u64']), ('effects', ['virtual-read'])]:
            unit = copy.deepcopy(self.fixture['unit'])
            marker = next(row for row in unit['functions'] if row['source'].endswith('.deferredSaved'))
            marker[field] = value
            with self.assertRaises(Core0Error): self.check(unit=unit)


if __name__ == '__main__': unittest.main()
