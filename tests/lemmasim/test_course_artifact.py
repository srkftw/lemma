"""Closed artifact mutation checks for pure scalar course presentation."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests/kernel'))
from audit_kernel import (LEMMASIM_BACKEND_JUMP_TABLES, validate_backend_jump_tables,
                          _jump_assembly_guard)
from core0_common import Core0Error
from test_backend_jump_tables import fixture


def course_fixture(source):
    data = fixture()
    role, count, args, effects, cases = LEMMASIM_BACKEND_JUMP_TABLES[source]
    data['unit'] = dict(role=role, configuration='lemmasim-silicon-power-notebook',
        image_key='notebook', functions=[dict(source=source, symbol='fw', args=args, effects=effects)])
    data['section_text'] = data['section_text'].replace('000028 00 A', f'{count*8:06x} 00 A')
    data['rodata'] = bytes(count*8)
    minimum = min(cases)
    targets = ['.LBB0_1' if minimum+i in cases else '.LBB0_2' for i in range(count)]
    for field, companion in [('relocation_text', False), ('companion_relocations', True)]:
        data[field] = data[field].split("Relocation section '.rela.rodata'", 1)[0]
        data[field] += "Relocation section '.rela.rodata' at offset 0:\n"
        for index, target in enumerate(targets):
            symbol, value = (4, 36) if target == '.LBB0_1' else (6, 40)
            data[field] += (f'{index*8:08x} {symbol:08x}00000002 R_RISCV_64 {value:08x} '
                           + (target if companion else '.L0') + ' + 0\n')
    data['assembly'] = data['assembly'].split('.LJTI0_0:\n', 1)[0].replace(
        'addi a1, a1, -1', f'addi a1, a1, -{minimum}' if minimum else 'mv a1, a0').replace(
        'li a2, 4', f'li a2, {count-1}')
    data['assembly'] += '.LJTI0_0:\n' + ''.join(' .quad '+target+'\n' for target in targets)
    data['optimized_ir'] = ('define i64 @fw('+', '.join('i64 %arg'+str(i) for i in range(len(args)))+') {\n'
        'entry:\n switch i64 %arg0, label %default [\n'
        + ''.join(' i64 '+str(value)+', label %good\n' for value in cases)
        + ']\ndefault:\n ret i64 32\ngood:\n ret i64 48\n}\n')
    return data


def panel_mask_fixture():
    assembly = '''owner:
 addi sp, sp, -16
 sd ra, 8(sp)
 li a5, 7
 bltu a5, a0, .LBB0_2
 slli a0, a0, 3
.Lpcrel_hi0:
 auipc a5, %pcrel_hi(.LJTI0_0)
 addi a5, a5, %pcrel_lo(.Lpcrel_hi0)
 add a0, a0, a5
 ld a5, 0(a0)
 andi a0, a4, 7
 jr a5
.LBB0_1:
 li a0, 48
 j .LBB0_3
.LBB0_2:
 li a0, 32
.LBB0_3:
 ld ra, 8(sp)
 addi sp, sp, 16
 ret
 .size owner, .-owner
'''
    return dict(assembly=assembly, symbol='owner', table='.LJTI0_0',
        targets=['.LBB0_1']*8, count=8, minimum=0,
        source='Lemma.Courses.Arithmetic.panelCharacter',
        configuration='lemmasim-silicon-power-notebook', image_key='notebook')


class CourseArtifactBoundaries(unittest.TestCase):
    def test_only_exact_pure_owners_domains_and_notebook_image(self):
        for name, count in [('character',19), ('answerCharacter',25), ('panelCharacter',8)]:
            data = course_fixture('Lemma.Courses.Arithmetic.'+name)
            report = validate_backend_jump_tables(**data)
            self.assertEqual(report['jump_table_bytes'], count*8)
            for field, value in [('source', 'Lemma.Courses.Arithmetic.other'),
                                 ('args', ['u64']), ('effects', ['virtual-write'])]:
                bad = copy.deepcopy(data);bad['unit']['functions'][0][field] = value
                with self.assertRaises(Core0Error):validate_backend_jump_tables(**bad)
            for field, value in [('configuration','normal'), ('role','kernel'), ('image_key','store')]:
                bad = copy.deepcopy(data);bad['unit'][field] = value
                with self.assertRaises(Core0Error):validate_backend_jump_tables(**bad)
            bad = copy.deepcopy(data);bad['optimized_ir'] = bad['optimized_ir'].replace('i64 2, label', 'i64 99, label')
            with self.assertRaises(Core0Error):validate_backend_jump_tables(**bad)
            bad = copy.deepcopy(data);bad['rodata'] = b'\x01'+bad['rodata'][1:]
            with self.assertRaises(Core0Error):validate_backend_jump_tables(**bad)

    def test_mask_preserves_the_bound_loaded_target_only_in_exact_course(self):
        data = panel_mask_fixture();result = _jump_assembly_guard(**data)
        self.assertEqual(result['target_preserving_mask']['preserved_target_register'], 'a5')
        self.assertTrue(result['guard_dominates_load'])
        for key, value in [('source','Lemma.Ink.Surface.glyph'), ('image_key','store'),
                           ('configuration','normal'), ('count',9), ('minimum',1)]:
            bad = dict(data);bad[key] = value
            with self.assertRaises(Core0Error):_jump_assembly_guard(**bad)
        for before, after in [('andi a0, a4, 7','andi a5, a4, 7'),
                              ('andi a0, a4, 7','andi a0, a4, 15'),
                              ('li a5, 7','li a5, 8'),
                              ('ld a5, 0(a0)','ld a5, 8(a0)'),
                              ('bltu a5, a0','bltu a0, a5')]:
            bad = dict(data);bad['assembly'] = data['assembly'].replace(before, after)
            with self.assertRaises(Core0Error):_jump_assembly_guard(**bad)


if __name__ == '__main__':unittest.main()
