"""Exact isolated arithmetic deployment admission and historical registry bounds."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from audit_kernel import image_specs,kernel_contract,managed_fields,software_deployment_fields,validate_user_image_catalog
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
            (('lemmasim-silicon-string-bulk-notebook','lemmasim-silicon-string-bulk-initialize',
              'lemmasim-silicon-string-arithmetic-oom-development'), 'ServerV6',3,4),
            (('lemmasim-silicon-usb-notebook','lemmasim-silicon-usb-initialize'), 'Server',6,6),
            (('lemmasim-silicon-usb-bulk-notebook','lemmasim-silicon-usb-bulk-initialize'), 'ServerV3',6,6),
            (('lemmasim-silicon-product-notebook',), 'Server',7,7),
            (('lemmasim-silicon-product-bulk-notebook',), 'ServerV3',7,7),
            (('lemmasim-silicon-usb-next-bulk-notebook','lemmasim-silicon-usb-next-bulk-initialize'), 'ServerV3',8,6),
            (('lemmasim-silicon-product-next-bulk-notebook',), 'ServerV3',9,7),
            (('lemmasim-silicon-product-executed-bulk-notebook',), 'ServerV3',10,7),
            (('lemmasim-silicon-usb-wire-bulk-notebook','lemmasim-silicon-usb-wire-bulk-initialize'), 'ServerV3',11,6),
            (('lemmasim-silicon-usb-clocked-bulk-notebook','lemmasim-silicon-usb-clocked-bulk-initialize'), 'ServerV3',13,6)]
        for names,server,profile,kernel in groups:
            for name in names:
                self.assertNotIn(name,expected)
                expected[name]=(server,profile,kernel)
        # Course installation has an independently specified fourth process;
        # historical deployments retain their exact three-image assertions.
        self.assertEqual(set(ARITHMETIC_CONFIGURATIONS),set(expected)|{
            'lemmasim-silicon-course-bulk-notebook','lemmasim-silicon-course-bulk-initialize',
            'lemmasim-silicon-course-await-bulk-notebook','lemmasim-silicon-course-await-bulk-initialize',
            'lemmasim-silicon-usb-clocked-retry-bulk-notebook','lemmasim-silicon-usb-clocked-retry-bulk-initialize',
            'lemmasim-silicon-closure-bulk-notebook','lemmasim-silicon-closure-bulk-initialize',
            'lemmasim-silicon-closure-arithmetic-oom-development',
            'lemmasim-silicon-closure-arithmetic-fault-development',
            'lemmasim-silicon-closure-entry2-bulk-notebook',
            'lemmasim-silicon-closure-entry2-bulk-initialize',
            'lemmasim-silicon-package-closure-entry2-bulk-notebook',
            'lemmasim-silicon-package-closure-entry2-bulk-initialize',
            'lemmasim-silicon-package-reader-bulk-notebook',
            'lemmasim-silicon-package-reader-bulk-initialize',
            'lemmasim-silicon-usb-clocked-closure-retry-bulk-notebook',
            'lemmasim-silicon-usb-clocked-closure-retry-bulk-initialize',
            'lemmasim-silicon-usb-clocked-package-retry-bulk-notebook',
            'lemmasim-silicon-usb-clocked-package-retry-bulk-initialize',
            'lemmasim-silicon-product-course-reader-bulk-notebook',
            'lemmasim-silicon-product-course-watchdog-bulk-notebook',
        'lemmasim-silicon-usb-clocked-package-entry2-bulk-notebook',
        'lemmasim-silicon-usb-clocked-package-entry2-bulk-initialize',
        'lemmasim-silicon-usb-clocked-reader-entry2-bulk-notebook',
        'lemmasim-silicon-usb-clocked-reader-entry2-bulk-initialize',
        'lemmasim-silicon-package-chooser-bulk-notebook',
        'lemmasim-silicon-package-chooser-bulk-initialize'})
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
    def test_trial_watchdog_keeps_four_roles_and_separate_privileged_roots(self):
        config = 'lemmasim-silicon-product-course-watchdog-bulk-notebook'
        legacy = 'lemmasim-silicon-product-course-reader-bulk-notebook'
        self.assertEqual(image_specs(config), image_specs(legacy))
        self.assertEqual([row['key'] for row in image_specs(config)],
                         ['store', 'notebook', 'arithmetic', 'course'])
        self.assertEqual(configuration_profile(config), 'lemma-silicon-dev/0.10.0')
        self.assertEqual(kernel_contract(config), 'core0-kernel-v0.7')
        self.assertEqual(configuration_roots(config)['kernel'], (
            ('Lemma.Platform.LemmaSim.TrialWatchdogKernel.boot', ()),
            ('Lemma.Platform.LemmaSim.TrialWatchdogKernel.dispatch', ('u64', 'u64', 'u64'))))
        previous = software_deployment_fields(legacy)['software_deployment']
        actual = software_deployment_fields(config)['software_deployment']
        self.assertEqual(actual, {**previous,
            'contract_version': 'lemma-package-reader-product10-watchdog-deployment-v1'})
        with self.assertRaises(Core0Error):
            configuration_roots('lemmasim-silicon-product-course-watchdog-bulk-initialize')

    def test_exact_course_names_select_guarded_store_and_independent_installer(self):
        deployment={'contract_version':'lemma-course-array-bulk-deployment-v1',
            'silicon_profile':'lemma-silicon-dev/0.3.0','user_profiles':{
                'store':'core0-user-v0.1','notebook':'core0-user-v0.2',
                'arithmetic':'core0-user-v0.5','course':'core0-user-v0.1'}}
        for config,boot in (('lemmasim-silicon-course-bulk-notebook','siliconCourseBoot'),
                            ('lemmasim-silicon-course-bulk-initialize','siliconCourseInitializeMedium')):
            with self.subTest(configuration=config):
                rows=list(image_specs(config))
                self.assertEqual([(r['key'],r['id'],r['source'],r['boot_role']) for r in rows],[
                    ('store',1,'Lemma.Services.Store.Server.courseMain','store-server'),
                    ('notebook',2,'Lemma.Applications.Notebook.mainArrayBulk','notebook'),
                    ('arithmetic',3,'Lemma.Services.Arithmetic.ServerV5.main','arithmetic-server'),
                    ('course',4,'Lemma.Courses.PackageInstaller.main','course-installer')])
                self.assertEqual(configuration_profile(config),'lemma-silicon-dev/0.3.0')
                self.assertEqual(kernel_contract(config),'core0-kernel-v0.4')
                self.assertEqual(configuration_roots(config)['kernel'][0][0],
                    'Lemma.Platform.LemmaSim.NotebookKernel.'+boot)
                self.assertEqual(managed_policy(config),'lemma-notebook-arithmetic-v1')
                self.assertEqual(software_deployment_fields(config),{'software_deployment':deployment})
                value={'schema_version':1,'contract_version':'lemma-user-image-catalog-v1',
                    'configuration':config,'stage':'supervisor','image_count':4,'images':rows,
                    'managed_policy':'lemma-notebook-arithmetic-v1','software_deployment':deployment}
                validate_user_image_catalog(value)
                for images in (rows[:3],rows[:2]+[rows[3],rows[2]],
                               rows[:3]+[{**rows[3],'boot_role':'arithmetic-server'}],
                               [{**rows[0],'source':'Lemma.Services.Store.Server.main'}]+rows[1:]):
                    with self.assertRaises(Core0Error):validate_user_image_catalog({**value,'images':images})
        for name in ('lemmasim-silicon-course-notebook','lemmasim-silicon-course-bulk-any-development'):
            with self.assertRaises(Core0Error):configuration_roots(name)
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
