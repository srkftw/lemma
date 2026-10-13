"""Closed five-binding jump-table observer tests; fixtures are host data only."""
import copy
import unittest
from test_backend_jump_tables import fixture
from audit_kernel import validate_backend_jump_tables
from core0_common import Core0Error

def binding_fixture():
    data=fixture()
    data['unit']={'role':'kernel','configuration':'lemmasim-silicon-ble-link-probe','functions':[{'source':'Lemma.Platform.LemmaSim.Descriptor.expectedBinding','symbol':'fw','args':['u64','u64'],'effects':[]}]}
    data['assembly']=data['assembly'].replace('a1','a0')
    data['optimized_ir']='define i64 @fw(i64 %arg0, i64 %arg1) {\nentry:\n switch i64 %arg0, label %default [\n'+''.join(' i64 '+str(i)+', label %good\n' for i in range(1,6))+']\ndefault:\n ret i64 0\ngood:\n ret i64 1\n}\n'
    return data
class DescriptorBindingJump(unittest.TestCase):
    def test_exact_five_bindings_and_unsigned_guard(self):
        report=validate_backend_jump_tables(**binding_fixture())
        self.assertEqual(report['jump_table_bytes'],40)
        self.assertEqual(report['jump_tables'][0]['guard']['minimum'],1)
    def test_extra_binding_signed_guard_and_wrong_coordinate_rejected(self):
        for field,old,new in [('optimized_ir','i64 5, label','i64 6, label'),('assembly','bltu a2','blt a2'),('assembly','addi a0, a0, -1','addi a0, a0, -2')]:
            data=binding_fixture();data[field]=data[field].replace(old,new)
            with self.subTest(field=field,new=new),self.assertRaises(Core0Error):validate_backend_jump_tables(**data)
    def test_pure_source_role_signature_is_closed(self):
        for field,new in [('source','Other.expectedBinding'),('args',['u64']),('effects',['mmio-write'])]:
            data=binding_fixture();data['unit']['functions'][0][field]=new
            with self.subTest(field=field),self.assertRaises(Core0Error):validate_backend_jump_tables(**data)
        for role in ['user','firmware']:
            data=binding_fixture();data['unit']['role']=role
            with self.assertRaises(Core0Error):validate_backend_jump_tables(**data)
