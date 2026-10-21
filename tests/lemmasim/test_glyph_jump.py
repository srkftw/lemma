"""Independent literal boundaries for the authored O2 toolbar and footer."""
from pathlib import Path
import copy
import json
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import (_jump_assembly_guard, _jump_status_default,
                          _jump_save_default, LEMMASIM_BACKEND_JUMP_TABLES,
                          LEMMASIM_JUMP_TABLE_USER_IMAGES)
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


def save_fixture():
    # Literal six-slot trace: the unlisted phase5 points at the error epilogue.
    assembly='''owner:
 addi sp, sp, -64
 addi s3, s3, -1
 li a0, 5
 li s0, 234
 bltu a0, s3, .LBB0_8
 slli s3, s3, 3
.Lpcrel_hi0:
 auipc a0, %pcrel_hi(.LJTI0_0)
 addi a0, a0, %pcrel_lo(.Lpcrel_hi0)
 add a0, s3, a0
 ld a0, 0(a0)
 jr a0
.LBB0_2:
 j .LBB0_8
.LBB0_3:
 j .LBB0_8
.LBB0_4:
 j .LBB0_8
.LBB0_5:
 j .LBB0_8
.LBB0_7:
 j .LBB0_8
.LBB0_8: # %done
 andi a0, s0, 255
 li a1, 0
 ld ra, 56(sp)
 ld s0, 48(sp)
 ld s1, 40(sp)
 ld s2, 32(sp)
 ld s3, 24(sp)
 ld s4, 16(sp)
 ld s5, 8(sp)
 ld s6, 0(sp)
 addi sp, sp, 64
 ret
 .size owner, .-owner
'''
    body='''entry:
 %record = call { i64, i64 } @get(i64 160)
 %phase = extractvalue { i64, i64 } %record, 1
 switch i64 %phase, label %dispatch [
  i64 0, label %done
  i64 5, label %wait
 ]
wait:
 br label %done
dispatch:
 switch i64 %phase, label %done [
  i64 1, label %first
  i64 2, label %second
  i64 3, label %third
  i64 4, label %fourth
  i64 6, label %sixth
 ]
first:
 br label %done
second:
 br label %done
third:
 br label %done
fourth:
 br label %done
sixth:
 br label %done
done:
 %status = phi i64 [ 234, %dispatch ], [ 0, %first ]
 %masked = and i64 %status, 255
 %partial = insertvalue { i64, i64 } poison, i64 %masked, 0
 %complete = insertvalue { i64, i64 } %partial, i64 0, 1
 ret { i64, i64 } %complete
'''
    data=dict(assembly=assembly,symbol='owner',table='.LJTI0_0',
        targets=['.LBB0_2','.LBB0_3','.LBB0_4','.LBB0_5','.LBB0_8','.LBB0_7'],
        count=6,minimum=1,source='Lemma.Applications.Notebook.pumpSave',
        configuration='lemmasim-notebook',image_key='notebook')
    return data,body


class AuthoredSavePhaseJump(unittest.TestCase):
    def actual_resume(self):
        path=Path(__file__).resolve().parent/'fixtures/ordinary-notebook-save-phase8.json'
        data=json.loads(path.read_text())
        from audit_kernel import _ir_definition_body
        return data,_ir_definition_body(data['optimized_ir'],data['symbol'])

    def resume_default(self,data,body=None):
        from audit_kernel import _ir_definition_body
        if body is None:body=_ir_definition_body(data['optimized_ir'],data['symbol'])
        return _jump_save_default(body,data['assembly'],data['symbol'],data['targets'],
                                  [1,2,3,4,6],unit=data['unit'],optimized_ir=data['optimized_ir'])

    def test_actual_ordinary_shared_resume_preserves_error_hole(self):
        data,body=self.actual_resume()
        result=self.resume_default(data)
        self.assertEqual(result['wait_split_phases'],[0,5,8])
        self.assertEqual((result['holes'],result['default_status'],result['default_value']),([5],234,0))
        self.assertEqual(result['ordinary_shared_resume_body_sha256'],
                         data['provenance']['normalized_body_sha256'])
        # A separately supplied body cannot borrow the full module's good pin.
        with self.assertRaises(Core0Error):self.resume_default(data,body.replace('i64 216','i64 217'))

    def test_initializer_same_main_preserves_full_resume_body(self):
        data,_=self.actual_resume()
        data['unit']['configuration']='lemmasim-initialize'
        result=self.resume_default(data)
        self.assertEqual(result['wait_split_phases'],[0,5,8])
        self.assertEqual(result['ordinary_shared_resume_body_sha256'],
                         data['provenance']['normalized_body_sha256'])
        data['unit']['roots'][0]['source']='Lemma.Applications.Notebook.initializeMedium'
        with self.assertRaises(Core0Error):self.resume_default(data)

    def test_actual_resume_context_does_not_grant_another_root_or_profile(self):
        data,_=self.actual_resume()
        mutations=[lambda u:u.update(configuration='lemmasim-other'),
                   lambda u:u.update(role='kernel'),lambda u:u.update(image_key='store'),
                   lambda u:u.update(image_id=3),lambda u:u.update(contract_version='core0-user-v0.2'),
                   lambda u:u.update(used_device_ops=[{'stable_id':'device.fake'}]),
                   lambda u:u['roots'][0].update(source='Lemma.Applications.Notebook.mainMultimodalSchoolV3'),
                   lambda u:u['roots'][0].update(id=2),lambda u:u['roots'][0].update(args=[])]
        for mutate in mutations:
            changed=copy.deepcopy(data);mutate(changed['unit'])
            with self.subTest(unit=changed['unit']):
                with self.assertRaises(Core0Error):self.resume_default(changed)
        for field,value in [('args',['u64']),('effects',[])]:
            changed=copy.deepcopy(data)
            next(r for r in changed['unit']['functions'] if r['symbol']==changed['symbol'])[field]=value
            with self.assertRaises(Core0Error):self.resume_default(changed)

    def test_actual_resume_complete_body_and_machine_default_remain_closed(self):
        data,_=self.actual_resume()
        ir=data['optimized_ir']
        for old,new in [('i64 216)','i64 217)'),('i64 2, i64 0,','i64 3, i64 0,'),
                        ('i64 8, label','i64 7, label'),('i64 5, label','i64 7, label'),
                        ('[ 234, %','[ 0, %'),('i64 160)','i64 168)')]:
            self.assertIn(old,ir);changed=copy.deepcopy(data);changed['optimized_ir']=ir.replace(old,new,1)
            with self.subTest(mutation=(old,new)):
                with self.assertRaises(Core0Error):self.resume_default(changed)
        changed=copy.deepcopy(data)
        row=next(r for r in changed['unit']['functions'] if r['source'].endswith('.issue'))
        row['source']=row['source'].replace('.issue','.issueOther')
        with self.assertRaises(Core0Error):self.resume_default(changed)
        for old,new in [('li\ts0, 234','li\ts0, 0'),('andi\ta0, s0, 255','andi\ta0, s1, 255')]:
            self.assertIn(old,data['assembly']);changed=copy.deepcopy(data);changed['assembly']=changed['assembly'].replace(old,new,1)
            with self.assertRaises(Core0Error):self.resume_default(changed)

    def test_exact_phase_domain_and_local_error_hole(self):
        source='Lemma.Applications.Notebook.pumpSave'
        self.assertEqual(LEMMASIM_BACKEND_JUMP_TABLES[source],
            ('user',6,[],['checked-access','io-order','virtual-read','virtual-write',
                         'user-syscall','privilege-transition'],[1,2,3,4,6]))
        self.assertEqual(LEMMASIM_JUMP_TABLE_USER_IMAGES[source],{'notebook'})
        data,body=save_fixture()
        guard=_jump_assembly_guard(**data)
        self.assertEqual((guard['bound'],guard['minimum']),(6,1))
        default=_jump_save_default(body,data['assembly'],'owner',data['targets'],[1,2,3,4,6])
        self.assertEqual(default['holes'],[5])
        self.assertEqual((default['default_status'],default['default_value']),(234,0))
        # LLVM reuses IR block names in separately owned functions.
        other=data['assembly']+'foreign:\n.LBB1_8: # %done\n ret\n .size foreign, .-foreign\n'
        self.assertEqual(_jump_save_default(body,other,'owner',data['targets'],[1,2,3,4,6]),default)
        # LLVM can split one merge into a result reload followed by its epilogue.
        split=data['assembly'].replace(' .size owner',
            '.LBB0_10: # %done\n mv s0, a0\n j .LBB0_8\n .size owner')
        self.assertEqual(_jump_save_default(body,split,'owner',data['targets'],[1,2,3,4,6]),default)

    def test_phase_wait_split_default_and_checked_words_cannot_change(self):
        data,body=save_fixture()
        for before,after in [('i64 6, label','i64 5, label'),
                             ('i64 5, label %wait','i64 6, label %wait'),
                             ('switch i64 %phase, label %dispatch','switch i64 %other, label %dispatch'),
                             ('[ 234, %dispatch ]','[ 0, %dispatch ]'),
                             ('and i64 %status, 255','and i64 %status, 254'),
                             ('%partial, i64 0, 1','%partial, i64 1, 1')]:
            with self.assertRaises(Core0Error):
                _jump_save_default(body.replace(before,after),data['assembly'],'owner',data['targets'],[1,2,3,4,6])
        targets=list(data['targets']);targets[4]='.LBB0_2'
        with self.assertRaises(Core0Error):
            _jump_save_default(body,data['assembly'],'owner',targets,[1,2,3,4,6])

    def test_actual_error_guard_return_and_frame_are_closed(self):
        data,body=save_fixture()
        for before,after in [('li s0, 234','li s0, 0'),('li a0, 5','li a0, 6'),
                             ('addi s3, s3, -1','addi s3, s3, -2'),
                             ('bltu a0, s3, .LBB0_8','bltu a0, s3, .LBB0_2'),
                             ('andi a0, s0, 255','andi a0, s1, 255'),
                             ('li a1, 0','li a1, 1'),('ld ra, 56(sp)','ld ra, 64(sp)'),
                             ('addi sp, sp, 64','addi sp, sp, 72'),
                             ('.LBB0_8: # %done','.LBB0_8: # %first')]:
            with self.assertRaises(Core0Error):
                _jump_save_default(body,data['assembly'].replace(before,after),'owner',data['targets'],[1,2,3,4,6])
        for before,after in [('bltu a0, s3','blt a0, s3'),
                             ('ld a0, 0(a0)','ld a0, 8(a0)'),
                             ('jr a0','jr a1')]:
            changed=dict(data);changed['assembly']=data['assembly'].replace(before,after)
            with self.assertRaises(Core0Error):_jump_assembly_guard(**changed)


if __name__=='__main__':unittest.main()
