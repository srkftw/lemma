"""Closed execution-version metadata boundaries, never target compilation."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import arithmetic_execution_identity as identity
from core0_common import Core0Error


class ArithmeticExecutionIdentity(unittest.TestCase):
    def unit(self):
        return {'role':'user','image_key':'arithmetic','contract_version':'core0-user-v0.2',
                'configuration':'lemmasim-silicon-managed-notebook',
                'functions':[{'source':identity.V2+'reply','symbol':'f','args':[], 'effects':[]}],
                identity.FIELD:copy.deepcopy(identity.REGISTRY)}

    def test_exact_named_registry_and_no_self_attested_hash(self):
        unit=self.unit()
        self.assertEqual(identity.contract(unit),identity.REGISTRY)
        self.assertNotIn('sha256',str(identity.REGISTRY))
        for key in ('implementation','lowering','runtime','resources'):
            changed=copy.deepcopy(unit);changed[identity.FIELD][key]['id']+=1
            with self.assertRaises(Core0Error):identity.contract(changed)
        changed=copy.deepcopy(unit);changed[identity.FIELD]['resources']['heap_objects']=32
        with self.assertRaises(Core0Error):identity.contract(changed)
        changed=copy.deepcopy(unit);changed[identity.FIELD]['resources']['deadline_ticks']+=1
        with self.assertRaises(Core0Error):identity.contract(changed)

    def test_legacy_and_client_units_cannot_acquire_version_authority(self):
        legacy=self.unit();legacy['functions']=[];legacy.pop(identity.FIELD)
        self.assertIsNone(identity.contract(legacy))
        legacy[identity.FIELD]=copy.deepcopy(identity.REGISTRY)
        with self.assertRaises(Core0Error):identity.contract(legacy)
        client=self.unit();client['image_key']='notebook';client.pop(identity.FIELD)
        self.assertIsNone(identity.contract(client))
        client[identity.FIELD]=copy.deepcopy(identity.REGISTRY)
        with self.assertRaises(Core0Error):identity.contract(client)

    def test_wrong_role_profile_configuration_and_missing_catalog_reject(self):
        for key,value in [('role','kernel'),('contract_version','core0-user-v0.1'),
                          ('configuration','lemmasim-notebook')]:
            changed=self.unit();changed[key]=value
            with self.assertRaises(Core0Error):identity.contract(changed)
        changed=self.unit();changed.pop(identity.FIELD)
        with self.assertRaises(Core0Error):identity.contract(changed)
        with self.assertRaises(Core0Error):identity.catalog_inventory(self.unit())

    def test_both_emitted_variants_have_separate_required_preimages(self):
        self.assertEqual(len(set(identity.EXPECTED.values())),5)
        self.assertTrue(all(len(value)==64 for value in identity.EXPECTED.values()))
        self.assertEqual(identity.canonical('_private.Lemma.Services.Arithmetic.Server.0.Lemma.Services.Arithmetic.Server.processV2'),
                         'Lemma.Services.Arithmetic.Server.processV2')


if __name__=='__main__':unittest.main()
