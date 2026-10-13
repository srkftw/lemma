"""Small observer regressions from genuine retained EP0 descriptor LLVM.

Minimal authority fixtures exercise the new configuration/name admission. The
separate actual-artifact qualifier binds full units and real object bytes.
"""
import copy
import json
from pathlib import Path
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from audit_kernel import kernel_contract
from check_modern_usb_descriptors import descriptor
from core0_common import Core0Error


class ModernUSBDescriptors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data=json.loads((ROOT/'tests/kernel/fixtures/usb-discovery-generated.json').read_text())
        cls.ir=data['usb_descriptor_optimized_ir'];cls.original=data['usb_descriptor_unit']

    def unit(self,configuration='lemmasim-silicon-usb-initialize'):
        unit=copy.deepcopy(self.original)
        unit.update(configuration=configuration,contract_version=kernel_contract(configuration))
        return unit

    def renamed(self,stem):
        return re.sub(r'@switch\.table\.lemma_kernel_core0_scalar_109\.31(?![A-Za-z0-9_.$-])',
                      '@'+stem,self.ir)

    def test_only_exact_owner_suffix_can_change(self):
        for config in ('lemmasim-silicon-usb-notebook','lemmasim-silicon-usb-initialize',
                       'lemmasim-silicon-product-notebook'):
            with self.subTest(configuration=config):
                sites,tables,_=descriptor(self.renamed('switch.table.lemma_kernel_core0_scalar_109.935'),self.unit(config))
                self.assertEqual((len(sites),[row['index_bound'] for row in tables]),(2,[3,4]))
        with self.assertRaises(Core0Error):
            descriptor(self.renamed('switch.table.foreign_descriptor.935'),self.unit())

    def test_suffix_rename_does_not_relax_contents_or_bounds(self):
        renamed=self.renamed('switch.table.lemma_kernel_core0_scalar_109.935')
        for old,new in [('i64 -9223370933046083063','i64 -9223370933046083062'),
                        ('icmp ult i64 %arg1, 3','icmp ult i64 %arg1, 4'),
                        ('icmp ult i64 %arg1, 4','icmp ule i64 %arg1, 4')]:
            changed=renamed.replace(old,new,1);self.assertNotEqual(changed,renamed)
            with self.subTest(site=old),self.assertRaises(Core0Error):descriptor(changed,self.unit())

    def test_extra_executable_table_use_is_rejected(self):
        ir=self.renamed('switch.table.lemma_kernel_core0_scalar_109.935')
        ir+='\ndefine i64 @other_reader() {\nentry:\n  %p = getelementptr inbounds [4 x i64], ptr @switch.table.lemma_kernel_core0_scalar_109.935, i64 0, i64 0\n  %v = load i64, ptr %p, align 8\n  ret i64 %v\n}\n'
        with self.assertRaises(Core0Error):descriptor(ir,self.unit())

    def test_profile_role_and_configuration_are_load_bearing(self):
        for key,value in [('role','user'),('configuration','lemmasim-silicon-power-notebook'),
                          ('contract_version','core0-kernel-v0.4')]:
            unit=self.unit();unit[key]=value
            with self.subTest(field=key),self.assertRaises(Core0Error):descriptor(self.ir,unit)
        for key,value in [('source','Lemma.USB.Control.foreign'),('args',['u64']),('effects',['virtual-read'])]:
            unit=self.unit()
            row=next(row for row in unit['functions'] if row['source']=='Lemma.USB.Control.descriptorWord')
            self.assertNotEqual(row[key],value);row[key]=value
            with self.subTest(field=key),self.assertRaises(Core0Error):descriptor(self.ir,unit)

    def test_historical_probe_does_not_gain_arbitrary_suffix(self):
        descriptor(self.ir,self.original)
        with self.assertRaises(Core0Error):
            descriptor(self.renamed('switch.table.lemma_kernel_core0_scalar_109.935'),self.original)


if __name__=='__main__':unittest.main()
