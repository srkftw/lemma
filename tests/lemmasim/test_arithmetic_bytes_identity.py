"""Version-authority boundaries; genuine emitted mutation qualification is separate."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from core0_common import Core0Error
import arithmetic_bytes_identity as identity


class BytesIdentityBoundary(unittest.TestCase):
    def unit(self):
        return {'role':'user','image_key':'arithmetic','contract_version':'core0-user-v0.4',
                'configuration':'lemmasim-silicon-bytes-bulk-notebook',
                identity.FIELD:copy.deepcopy(identity.REGISTRY),
                'functions':[{'source':'Lemma.Services.Arithmetic.ProtocolV4.reply'}]}

    def test_empty_or_legacy_has_no_version_authority(self):
        self.assertIsNone(identity.contract({}))
        for image in ('notebook','arithmetic'):
            with self.subTest(image=image),self.assertRaises(Core0Error):
                identity.contract({'image_key':image,identity.FIELD:copy.deepcopy(identity.REGISTRY)})

    def test_registry_self_report_cannot_replace_emitted_implementation(self):
        unit=self.unit()
        self.assertEqual(identity.contract(unit),identity.REGISTRY)
        with self.assertRaises(Core0Error):identity.validate('',unit,optimized=False)

    def test_exact_profile_role_image_and_configuration_remain_required(self):
        for field,value in [('contract_version','core0-user-v0.3'),('role','kernel'),
                            ('image_key','notebook'),('configuration','lemmasim-silicon-sums-notebook')]:
            unit=self.unit();unit[field]=value
            with self.subTest(field=field),self.assertRaises(Core0Error):identity.contract(unit)

    def test_resource_and_runtime_authorities_are_distinct(self):
        for field in ('implementation','lowering','runtime','resources'):
            unit=self.unit();unit[identity.FIELD][field]['id']+=1
            with self.subTest(field=field),self.assertRaises(Core0Error):identity.contract(unit)

    def test_implementation_pins_cannot_be_supplied_by_the_unit(self):
        unit=self.unit();unit['expected_preimage_sha256']='0'*64
        with self.assertRaises(Core0Error):identity.validate('',unit,optimized=True)


if __name__=='__main__':unittest.main()
