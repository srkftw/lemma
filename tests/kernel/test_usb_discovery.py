"""Independent mutations of genuine USB6 discovery and owned PIO artifacts.

Fixtures qualify the fail-closed observer. Actual RV64 transactions are separate.
"""
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
from audit_kernel import validate_sim_geometry_body,validate_sim_binding_body,validate_dtb_pair_body,validate_usb_owned_buffers,validate_usb_descriptor_lookup

class USBDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((ROOT/'tests/kernel/fixtures/usb-discovery-generated.json').read_text())
    def symbol(self,suffix):
        return next(row['symbol'] for row in self.data['unit']['functions'] if row['source'].endswith('.'+suffix))
    def test_actual_complete_literal_and_device_guards(self):
        rows=validate_lookup(self.data['optimized_ir'],self.data['unit'])[1]
        self.assertEqual(len(rows),39)
        self.assertEqual({r['literal_schema'] for r in rows},{'usb-device-packet-v1'})
        self.assertEqual(next(r for r in rows if r['source'].endswith('.expectedIRQ'))['values'],
                         [12,13,1,None,None,10,11,14,15,None,None,None,16])
        for optimized,key in [(False,'ir'),(True,'optimized_ir')]:
            self.assertEqual(len(validate_devices(self.data[key],self.data['unit'],optimized)[1]),4)
    def test_literal_identity_poison_and_exact_bound_are_load_bearing(self):
        original=self.data['optimized_ir']
        for old,new in [('lshr i32 114815','lshr i32 114807'),
                        ('lshr i16 4583','lshr i16 4095'),
                        ('lshr i16 4607','lshr i16 8191'),
                        ('i64 16], align 8','i64 15], align 8'),
                        ('icmp ult i64 %switch.tableidx, 77','icmp ult i64 %switch.tableidx, 78')]:
            with self.subTest(old=old):
                changed=original.replace(old,new,1)
                self.assertNotEqual(changed,original)
                with self.assertRaises(Core0Error):validate_lookup(changed,self.data['unit'])
    def test_closed_binding_geometry_and_property_bodies(self):
        for suffix,check in [('geometry',validate_sim_geometry_body),('expectedBinding',validate_sim_binding_body),('leafProperty',validate_dtb_pair_body)]:
            symbol=self.symbol(suffix)
            self.assertEqual(len(check(self.data['optimized_ir'],self.data['unit'],symbol)),64)
            # A literal alteration in the actual owner must not survive its full body pin.
            text=self.data['optimized_ir'];start=text.index('@'+symbol+'(');end=text.index('\n}',start)
            body=text[start:end];changed=re.sub(r'i64 (\d+)',lambda m:'i64 '+str(int(m[1])+1),body,count=1)
            self.assertNotEqual(changed,body)
            with self.subTest(suffix=suffix),self.assertRaises(Core0Error):check(text[:start]+changed+text[end:],self.data['unit'],symbol)
    def test_irq16_does_not_broaden_legacy_or_user_authority(self):
        unit=copy.deepcopy(self.data['unit']);unit['contract_version']='core0-kernel-v0.5'
        with self.assertRaises(Core0Error):validate_devices(self.data['ir'],unit,False)
        unit=copy.deepcopy(self.data['unit']);unit['configuration']='lemmasim-silicon-ble-link-probe';unit['contract_version']='core0-kernel-v0.5'
        with self.assertRaises(Core0Error):validate_devices(self.data['ir'],unit,False)
        changed=self.data['ir'].replace('201326656','201326660')
        self.assertNotEqual(changed,self.data['ir'])
        with self.assertRaises(Core0Error):validate_devices(changed,self.data['unit'],False)
    def test_owned_generation_purpose_and_copy_before_pop_remain_closed(self):
        unit=self.data['owned_unit'];ir=self.data['owned_pre_ir']
        report=validate_usb_owned_buffers(unit,ir)
        self.assertEqual((report['owner'],report['purpose'],report['pages']),(1,1,1))
        for old,new in [('i64 1, i64 1)','i64 1, i64 2)'),('i64 %arg2, i64 1)','i64 %arg2, i64 2)'),('i64 4096','i64 4097')]:
            changed=ir.replace(old,new,1);self.assertNotEqual(changed,ir)
            with self.subTest(old=old),self.assertRaises(Core0Error):validate_usb_owned_buffers(unit,changed)
        wrong=copy.deepcopy(unit);wrong['role']='user'
        with self.assertRaises(Core0Error):validate_usb_owned_buffers(wrong,ir)

    def test_actual_ep0_descriptor_bytes_and_both_bounds_are_closed(self):
        ir=self.data['usb_descriptor_optimized_ir'];unit=self.data['usb_descriptor_unit']
        sites,tables,removed=validate_usb_descriptor_lookup(ir,unit)
        self.assertEqual((len(sites),len(tables),len(removed)),(2,2,2))
        self.assertEqual([r['index_bound'] for r in tables],[3,4])
        for old,new in [('i64 4611686018460942610','i64 4611686018460942611'),
                        ('icmp ult i64 %arg1, 3','icmp ult i64 %arg1, 4'),
                        ('icmp ult i64 %arg1, 4','icmp ule i64 %arg1, 4'),
                        ('i64 0, i64 %arg1','i64 0, i64 %arg0')]:
            changed=ir.replace(old,new,1);self.assertNotEqual(changed,ir)
            with self.subTest(old=old),self.assertRaises(Core0Error):validate_usb_descriptor_lookup(changed,unit)
