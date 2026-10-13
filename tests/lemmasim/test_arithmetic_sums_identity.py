"""New named sums registry stays separate from every historical authority."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import arithmetic_execution_identity as old
import arithmetic_sums_identity as identity
from core0_common import Core0Error

class ArithmeticSumsIdentity(unittest.TestCase):
    def unit(self):
        return {'role':'user','image_key':'arithmetic','contract_version':'core0-user-v0.3',
          'configuration':'lemmasim-silicon-sums-notebook',
          'functions':[{'source':identity.PROTOCOL+'reply','symbol':'f','args':[],'effects':[]}],
          identity.FIELD:copy.deepcopy(identity.REGISTRY)}
    def test_exact_distinct_registry_and_complete_immutable_preimages(self):
        self.assertEqual(identity.contract(self.unit()),identity.REGISTRY)
        self.assertNotEqual(identity.REGISTRY['implementation'],old.REGISTRY['implementation'])
        self.assertNotEqual(identity.REGISTRY['lowering'],old.REGISTRY['lowering'])
        self.assertNotEqual(identity.REGISTRY['runtime'],old.REGISTRY['runtime'])
        self.assertEqual(identity.REGISTRY['resources'],old.REGISTRY['resources'])
        self.assertEqual(len(set(identity.EXPECTED.values())),3)
        self.assertTrue(all(isinstance(value,str) and len(value)==64 for value in identity.EXPECTED.values()))
        for key in ('implementation','lowering','runtime','resources'):
            unit=self.unit();unit[identity.FIELD][key]['id']+=1
            with self.assertRaises(Core0Error):identity.contract(unit)
    def test_historical_profile_old_protocol_and_client_have_no_new_authority(self):
        for key,value in [('contract_version','core0-user-v0.2'),('configuration','lemmasim-silicon-managed-notebook'),('image_key','notebook')]:
            unit=self.unit();unit[key]=value
            with self.assertRaises(Core0Error):identity.contract(unit)
        unit=self.unit();unit['functions'][0]['source']=old.V2+'reply'
        with self.assertRaises(Core0Error):identity.contract(unit)
        unit.pop(identity.FIELD);self.assertIsNone(identity.contract(unit))
        unit=self.unit();unit['image_key']='notebook';unit.pop(identity.FIELD)
        self.assertIsNone(identity.contract(unit))
    def test_empty_source_closure_cannot_self_attest_registry(self):
        with self.assertRaises(Core0Error):identity.catalog_inventory(self.unit())

if __name__=='__main__':unittest.main()
