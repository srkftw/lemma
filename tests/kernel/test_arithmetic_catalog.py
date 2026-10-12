"""Exact isolated arithmetic deployment admission and historical registry bounds."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from audit_kernel import image_specs,kernel_contract,managed_fields,validate_user_image_catalog
from build_kernel import ARITHMETIC_CONFIGURATIONS,ARITHMETIC_DEVELOPMENT_CONFIGURATIONS,configuration_roots,managed_policy
from silicon_profile import configuration_profile
from core0_common import Core0Error
class ArithmeticCatalog(unittest.TestCase):
    def test_canonical_and_only_exact_lab_names_select_three_images(self):
        for config in ARITHMETIC_CONFIGURATIONS:
            rows=image_specs(config)
            self.assertEqual([r['key'] for r in rows],['store','notebook','arithmetic'])
            self.assertEqual(rows[-1]['source'],'Lemma.Services.Arithmetic.Server.main')
            self.assertEqual(rows[-1]['boot_role'],'arithmetic-server')
            self.assertEqual(managed_policy(config),'lemma-notebook-arithmetic-v1')
            self.assertEqual(managed_fields(config)['managed_policy'],'lemma-notebook-arithmetic-v1')
            self.assertEqual(configuration_profile(config),'lemma-silicon-dev/0.3.0')
            self.assertEqual(kernel_contract(config),'core0-kernel-v0.4')
    def test_lab_root_cannot_be_freeform_or_escape_ordinary_catalog(self):
        for config,root in zip(ARITHMETIC_DEVELOPMENT_CONFIGURATIONS,('arithmeticOOMBoot','arithmeticFaultBoot','arithmeticStallBoot')):
            self.assertEqual(configuration_roots(config)['kernel'][0][0],'Lemma.Platform.LemmaSim.NotebookKernel.'+root)
        for config in ('lemmasim-silicon-power-arithmetic-any-development','lemmasim-silicon-power-arithmetic-oom','arithmetic-stall-development'):
            with self.assertRaises(Core0Error):configuration_roots(config)
        self.assertEqual([r['key'] for r in image_specs('lemmasim-notebook')],['store','notebook'])
        self.assertEqual(managed_policy('lemmasim-notebook'),'lemma-notebook-v1')
        self.assertEqual([r['key'] for r in image_specs('lemmasim-isolation-development')],['store','notebook','isolation'])
    def test_missing_swapped_or_wrong_math_authority_catalog_rejects(self):
        config='lemmasim-silicon-power-notebook'
        value={'schema_version':1,'contract_version':'lemma-user-image-catalog-v1','configuration':config,'stage':'supervisor','image_count':3,'images':list(image_specs(config)),**managed_fields(config)}
        validate_user_image_catalog(value)
        for images in (value['images'][:2],list(reversed(value['images'])),[*value['images'][:2],{**value['images'][2],'boot_role':'store-server'}]):
            with self.assertRaises(Core0Error):validate_user_image_catalog({**value,'images':images})
if __name__=='__main__':unittest.main()
