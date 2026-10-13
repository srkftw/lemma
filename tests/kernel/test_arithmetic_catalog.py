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
        expected={}
        groups=[
            (('lemmasim-silicon-power-notebook','lemmasim-silicon-power-initialize',
              'lemmasim-silicon-power-arithmetic-oom-development',
              'lemmasim-silicon-power-arithmetic-fault-development',
              'lemmasim-silicon-power-arithmetic-stall-development',
              'lemmasim-silicon-managed-notebook','lemmasim-silicon-managed-initialize'), 'Server',3,4),
            (('lemmasim-silicon-sums-notebook','lemmasim-silicon-sums-initialize',
              'lemmasim-silicon-sums-arithmetic-oom-development',
              'lemmasim-silicon-bulk-notebook','lemmasim-silicon-bulk-initialize'), 'ServerV3',3,4),
            (('lemmasim-silicon-bytes-bulk-notebook','lemmasim-silicon-bytes-bulk-initialize',
              'lemmasim-silicon-bytes-arithmetic-oom-development'), 'ServerV4',3,4),
            (('lemmasim-silicon-array-bulk-notebook','lemmasim-silicon-array-bulk-initialize',
              'lemmasim-silicon-array-arithmetic-oom-development'), 'ServerV5',3,4),
            (('lemmasim-silicon-usb-notebook','lemmasim-silicon-usb-initialize'), 'Server',6,6),
            (('lemmasim-silicon-usb-bulk-notebook','lemmasim-silicon-usb-bulk-initialize'), 'ServerV3',6,6),
            (('lemmasim-silicon-product-notebook',), 'Server',7,7),
            (('lemmasim-silicon-product-bulk-notebook',), 'ServerV3',7,7)]
        for names,server,profile,kernel in groups:
            for name in names:
                self.assertNotIn(name,expected)
                expected[name]=(server,profile,kernel)
        self.assertEqual(set(ARITHMETIC_CONFIGURATIONS),set(expected))
        for config,(server,profile,kernel) in expected.items():
            with self.subTest(configuration=config):
                rows=image_specs(config)
                self.assertEqual([r['key'] for r in rows],['store','notebook','arithmetic'])
                self.assertEqual(rows[-1]['source'],'Lemma.Services.Arithmetic.'+server+'.main')
                self.assertEqual(rows[-1]['boot_role'],'arithmetic-server')
                self.assertEqual(managed_policy(config),'lemma-notebook-arithmetic-v1')
                self.assertEqual(managed_fields(config)['managed_policy'],'lemma-notebook-arithmetic-v1')
                self.assertEqual(configuration_profile(config),f'lemma-silicon-dev/0.{profile}.0')
                self.assertEqual(kernel_contract(config),f'core0-kernel-v0.{kernel}')
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
