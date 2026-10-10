"""Independent literal boundaries for the authored O2 toolbar and footer."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import _jump_assembly_guard, _jump_status_default
from core0_common import Core0Error


def fixture():
    # Independent small trace of all nine explicit cases; unknown tools return0.
    assembly='''owner:
 addi sp, sp, -16
 sd ra, 8(sp)
 li a1, 8
 bltu a1, a0, .LBB0_12
 slli a0, a0, 3
.Lpcrel_hi0:
 auipc a1, %pcrel_hi(.LJTI0_0)
 addi a1, a1, %pcrel_lo(.Lpcrel_hi0)
 add a0, a0, a1
 ld a1, 0(a0)
 lui a0, 3
 addiw a0, a0, -1566
 jr a1
.LBB0_2:
 li a0, 72
 j .LBB0_9
.LBB0_3:
 li a0, 82
 j .LBB0_9
.LBB0_4:
 lui a0, 2
 addiw a0, a0, 970
 j .LBB0_10
.LBB0_5:
 li a0, 85
 j .LBB0_9
.LBB0_6:
 li a0, 83
 j .LBB0_9
.LBB0_7:
 li a0, 69
 j .LBB0_9
.LBB0_8:
 li a0, 87
 j .LBB0_9
.LBB0_11:
 li a0, 67
 j .LBB0_9
.LBB0_12:
 li a0, 0
 j .LBB0_10
.LBB0_9:
 call letter
.LBB0_10:
 ld ra, 8(sp)
 addi sp, sp, 16
 ret
 .size owner, .-owner
'''
    return dict(assembly=assembly,symbol='owner',table='.LJTI0_0',
                targets=['.LBB0_2','.LBB0_10','.LBB0_4','.LBB0_5','.LBB0_3','.LBB0_7','.LBB0_8','.LBB0_6','.LBB0_11'],
                count=9,minimum=0,source='Lemma.Ink.Surface.glyph',
                configuration='lemmasim-notebook',image_key='notebook')


class AuthoredGlyphJump(unittest.TestCase):
    def test_exact_literal_preserves_local_target(self):
        for configuration in ['lemmasim-notebook','lemmasim-initialize','lemmasim-isolation-development']:
            data=fixture();data['configuration']=configuration
            result=_jump_assembly_guard(**data)
            self.assertEqual(result['bound'],9)
            self.assertEqual(result['target_preserving_literal']['value'],0x29e2)
            self.assertEqual(result['target_preserving_literal']['preserved_target_register'],'a1')
            self.assertTrue(result['guard_dominates_load'])

    def test_exception_cannot_escape_source_image_or_profile(self):
        for key,value in [('source',None),('source','Lemma.Ink.Surface.letter'),
                          ('image_key','isolation'),('image_key','store'),
                          ('configuration','normal'),('configuration','lemmasim-bringup'),
                          ('count',7),('count',8),('count',10),('minimum',1)]:
            data=fixture();data[key]=value
            with self.assertRaises(Core0Error):_jump_assembly_guard(**data)

    def test_literal_target_guard_and_frame_mutations_fail_closed(self):
        for before,after in [
            ('lui a0, 3','lui a1, 3'),('lui a0, 3','lui a0, 4'),
            ('addiw a0, a0, -1566','addiw a1, a0, -1566'),
            ('addiw a0, a0, -1566','addiw a0, a1, -1566'),
            ('addiw a0, a0, -1566','addiw a0, a0, -1565'),
            ('jr a1','jr a0'),('jr a1','nop\n jr a1'),
            ('li a1, 8','li a1, 7'),('bltu a1, a0','blt a1, a0'),
            ('slli a0, a0, 3','slli a0, a0, 2'),
            ('bltu a1, a0, .LBB0_12','bltu a1, a0, .Lpcrel_hi0'),
            ('addi sp, sp, -16','addi sp, sp, -32'),('sd ra, 8(sp)','sd ra, 16(sp)')]:
            data=fixture();data['assembly']=data['assembly'].replace(before,after)
            with self.assertRaises(Core0Error):_jump_assembly_guard(**data)


def footer_fixture():
    assembly='''owner:
 li a5, 8
 bltu a5, a1, .LBB0_1
 li a2, 2
 beq a0, a2, .LBB0_2
 li a2, 1
 beq a0, a2, .LBB0_2
 bnez a0, .LBB0_2
 li a0, 5
 bgeu a1, a0, .LBB0_2
 slli a1, a1, 3
.Lpcrel_hi1:
 auipc a0, %pcrel_hi(.Lliteral0)
 addi a0, a0, %pcrel_lo(.Lpcrel_hi1)
 j .LBB0_2
.LBB0_1:
 addi a1, a1, -10
 bltu a5, a1, .LBB0_2
 slli a1, a1, 3
.Lpcrel_hi0:
 auipc a0, %pcrel_hi(.LJTI0_0)
 addi a0, a0, %pcrel_lo(.Lpcrel_hi0)
 add a0, a1, a0
 ld a1, 0(a0)
 li a0, 78
 jr a1
.LBB0_2:
 li a0, 32
 ret
.LBB0_3:
 addi a0, a2, 48
 ret
.LBB0_4:
 li a0, 80
 ret
.LBB0_5:
 addi a0, a3, 48
 ret
.LBB0_6:
 addi a0, a3, 48
 ret
.LBB0_7:
 li a0, 87
 ret
.LBB0_8:
 addi a0, a4, 48
 ret
.LBB0_9:
 ret
 .size owner, .-owner
'''
    targets=['.LBB0_9','.LBB0_3','.LBB0_2','.LBB0_4','.LBB0_5','.LBB0_6','.LBB0_2','.LBB0_7','.LBB0_8']
    body='''entry:
 switch i64 %arg1, label %space [
  i64 10, label %n
  i64 11, label %ns
  i64 13, label %p
  i64 14, label %tens
  i64 15, label %units
  i64 17, label %w
  i64 18, label %width
 ]
n:
 br label %done
ns:
 ret i64 48
p:
 ret i64 80
tens:
 ret i64 48
units:
 ret i64 48
w:
 ret i64 87
width:
 ret i64 48
space:
 br label %done
done:
 %result = phi i64 [ 32, %space ], [ 78, %n ]
 ret i64 %result
'''
    data=dict(assembly=assembly,symbol='owner',table='.LJTI0_0',targets=targets,count=9,minimum=10,
              source='Lemma.Applications.Notebook.statusCharacter',configuration='lemmasim-notebook',image_key='notebook')
    return data,body


class AuthoredFooterJump(unittest.TestCase):
    def test_exact_hoisted_bound_and_two_space_holes(self):
        for configuration in ['lemmasim-notebook','lemmasim-initialize','lemmasim-isolation-development']:
            data,body=footer_fixture();data['configuration']=configuration
            guard=_jump_assembly_guard(**data)
            self.assertEqual(guard['hoisted_entry_bound']['instruction'],'li a5,8')
            self.assertTrue(guard['guard_dominates_load'])
            default=_jump_status_default(body,data['assembly'],'owner',data['targets'],[10,11,13,14,15,17,18])
            self.assertEqual(default['holes'],[12,16]);self.assertEqual(default['default_value'],32)

    def test_hoisted_bound_scope_clobbers_and_bypasses_fail(self):
        for key,value in [('source','Lemma.Ink.Surface.glyph'),('source',None),('image_key','store'),
                          ('configuration','normal'),('configuration','lemmasim-bringup'),('count',8),('minimum',9)]:
            data,_=footer_fixture();data[key]=value
            with self.assertRaises(Core0Error):_jump_assembly_guard(**data)
        for before,after in [('li a5, 8','li a5, 9'),('li a2, 2','li a5, 0'),
                             ('li a2, 2','call foreign'),
                             ('bltu a5, a1, .LBB0_1','bltu a5, a1, .Lpcrel_hi0'),
                             ('addi a1, a1, -10','addi a1, a1, -9'),
                             ('bltu a5, a1, .LBB0_2','bltu a5, a1, .Lpcrel_hi0'),
                             ('bltu a5, a1, .LBB0_2','blt a5, a1, .LBB0_2')]:
            data,_=footer_fixture();data['assembly']=data['assembly'].replace(before,after)
            with self.assertRaises(Core0Error):_jump_assembly_guard(**data)

    def test_default_must_be_space_in_ir_and_actual_local_code(self):
        data,body=footer_fixture()
        for text in [body.replace('[ 32, %space ]','[ 31, %space ]'),
                     body.replace('switch i64 %arg1','switch i64 %arg0'),
                     body.replace('ret i64 %result','ret i64 78')]:
            with self.assertRaises(Core0Error):
                _jump_status_default(text,data['assembly'],'owner',data['targets'],[10,11,13,14,15,17,18])
        targets=list(data['targets']);targets[6]='.LBB0_4'
        with self.assertRaises(Core0Error):
            _jump_status_default(body,data['assembly'],'owner',targets,[10,11,13,14,15,17,18])
        with self.assertRaises(Core0Error):
            _jump_status_default(body,data['assembly'].replace('li a0, 32','li a0, 31'),'owner',data['targets'],[10,11,13,14,15,17,18])


if __name__=='__main__':unittest.main()
