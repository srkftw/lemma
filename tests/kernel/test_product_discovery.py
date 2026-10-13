"""Fail-closed product aperture and discovery checks on genuine LLVM artifacts."""
import copy
import json
from pathlib import Path
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from core0_common import Core0Error
from lemmasim_readonly import validate_lookup,validate_devices
from audit_kernel import (validate_sim_geometry_body,validate_sim_binding_body,
                          validate_dtb_pair_body,_jump_leaf_pair)

class ProductDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((ROOT/'tests/kernel/fixtures/product-discovery-generated.json').read_text())

    def symbol(self,suffix):
        return next(row['symbol'] for row in self.data['unit']['functions'] if row['source'].endswith('.'+suffix))

    def test_genuine_complete_schema_and_new_aperture(self):
        rows=validate_lookup(self.data['optimized_ir'],self.data['unit'])[1]
        self.assertEqual(len(rows),45)
        self.assertEqual({row['literal_schema'] for row in rows},{'boot-nv-v1'})
        irq=next(row for row in rows if row['source'].endswith('.expectedIRQ'))
        self.assertEqual(irq['values'][-2:],[16,17])
        for optimized,key in [(False,'ir'),(True,'optimized_ir')]:
            self.assertEqual(len(validate_devices(self.data[key],self.data['unit'],optimized)[1]),4)

    def test_exact_holes_literals_and_index_bounds(self):
        original=self.data['optimized_ir']
        for old,new in [('lshr i32 245887','lshr i32 245879'),
                        ('lshr i16 12775','lshr i16 16383'),
                        ('lshr i16 12799','lshr i16 16383'),
                        ('i64 16, i64 17], align 8','i64 16, i64 16], align 8'),
                        ('icmp ult i64 %switch.tableidx, 78','icmp ult i64 %switch.tableidx, 79'),
                        ('i64 8062, i64 16254, i64 32638','i64 8062, i64 16254, i64 65534')]:
            changed=original.replace(old,new,1)
            self.assertNotEqual(changed,original)
            with self.subTest(old=old),self.assertRaises(Core0Error):
                validate_lookup(changed,self.data['unit'])

    def test_product_hardware_authority_cannot_be_relabelled_as_legacy(self):
        for cfg,profile in [('lemmasim-silicon-usb-link-probe','core0-kernel-v0.6'),
                            ('lemmasim-silicon-managed-notebook','core0-kernel-v0.4')]:
            unit=copy.deepcopy(self.data['unit'])
            unit.update(configuration=cfg,contract_version=profile)
            with self.subTest(cfg=cfg),self.assertRaises(Core0Error):
                validate_devices(self.data['ir'],unit,False)
        changed=self.data['ir'].replace('268510200','268510208')
        self.assertNotEqual(changed,self.data['ir'])
        with self.assertRaises(Core0Error):validate_devices(changed,self.data['unit'],False)

    def test_complete_binding_geometry_and_leaf_bodies(self):
        for suffix,check in [('geometry',validate_sim_geometry_body),
                             ('expectedBinding',validate_sim_binding_body),
                             ('leafProperty',validate_dtb_pair_body)]:
            symbol=self.symbol(suffix)
            self.assertEqual(len(check(self.data['optimized_ir'],self.data['unit'],symbol)),64)
            text=self.data['optimized_ir'];start=text.index('@'+symbol+'(');end=text.index('\n}',start)
            body=text[start:end]
            changed=re.sub(r'i64 (\d+)',lambda m:'i64 '+str(int(m[1])+1),body,count=1)
            self.assertNotEqual(changed,body)
            with self.subTest(suffix=suffix),self.assertRaises(Core0Error):
                check(text[:start]+changed+text[end:],self.data['unit'],symbol)

    def test_four_machine_transfers_have_own_exact_domains(self):
        symbol=self.symbol('leafProperty');source='Lemma.Platform.LemmaSim.DescriptorDTB.leafProperty'
        assembly=self.data['assembly'];cfg=self.data['unit']['configuration']
        result=_jump_leaf_pair(assembly,symbol,source,cfg)
        self.assertEqual([len(targets) for targets in result.values()],[15,14,21,25])
        # Change the actual NV-property table guard, preserving its pointer/JR.
        function=assembly[assembly.index(symbol+':'):]
        guard=re.search(r'li\s+([a-z][0-9]+), 24\n',function)
        self.assertIsNotNone(guard)
        changed=assembly.replace(guard[0],guard[0].replace('24','25'),1)
        with self.assertRaises(Core0Error):_jump_leaf_pair(changed,symbol,source,cfg)

    def test_legacy_parsers_can_share_literals_without_new_hardware_authority(self):
        unit=copy.deepcopy(self.data['unit'])
        unit.update(configuration='lemmasim-silicon-managed-notebook',contract_version='core0-kernel-v0.4')
        self.assertEqual(len(validate_lookup(self.data['optimized_ir'],unit)[1]),45)
        with self.assertRaises(Core0Error):validate_devices(self.data['ir'],unit,False)
