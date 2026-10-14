"""Role and authority isolation for the installed-package notebook deployment.

These are host admission checks; they do not establish guest execution.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import (image_specs,kernel_contract,managed_fields,
                         software_deployment_fields,validate_user_image_catalog)
from build_kernel import (configuration_roots,managed_policy,
                          ARRAY_NOTEBOOK_CONFIGURATIONS,SUMS_NOTEBOOK_CONFIGURATIONS)
from core0_common import Core0Error
from silicon_guest_bundle import development_configuration
from silicon_profile import configuration_profile


class PackageClosureCatalog(unittest.TestCase):
    def test_selected_roles_and_old_profiles_remain_distinct(self):
        for configuration,boot in (
            ('lemmasim-silicon-package-closure-entry2-bulk-notebook','siliconPackageClosureEntry2Boot'),
            ('lemmasim-silicon-package-closure-entry2-bulk-initialize','siliconPackageClosureEntry2InitializeMedium')):
            with self.subTest(configuration=configuration):
                rows=list(image_specs(configuration))
                self.assertEqual([(r['key'],r['id'],r['source'],r['boot_role']) for r in rows],[
                    ('store',1,'Lemma.Services.Store.ServerAwait.main','store-server'),
                    ('notebook',2,'Lemma.Applications.Notebook.mainPackageClosureBulk','notebook'),
                    ('arithmetic',3,'Lemma.Services.Arithmetic.ServerV7.main','arithmetic-server'),
                    ('course',4,'Lemma.Courses.PackageInstaller.mainAwait','course-installer')])
                self.assertEqual(configuration_profile(configuration),'lemma-silicon-dev/0.3.0')
                self.assertEqual(kernel_contract(configuration),'core0-kernel-v0.4')
                self.assertEqual(managed_policy(configuration),'lemma-notebook-arithmetic-v1')
                self.assertEqual(configuration_roots(configuration)['kernel'],(
                    ('Lemma.Platform.LemmaSim.NotebookKernel.'+boot,()),
                    ('Lemma.Platform.LemmaSim.NotebookKernel.dispatchBulk',('u64','u64','u64'))))
                self.assertNotIn(configuration,ARRAY_NOTEBOOK_CONFIGURATIONS)
                self.assertNotIn(configuration,SUMS_NOTEBOOK_CONFIGURATIONS)
        self.assertEqual(image_specs('lemmasim-silicon-course-await-bulk-notebook')[2]['source'],
                         'Lemma.Services.Arithmetic.ServerV5.main')
        self.assertEqual(image_specs('lemmasim-silicon-closure-entry2-bulk-notebook')[0]['source'],
                         'Lemma.Services.Store.Server.main')

    def test_image_catalog_cannot_swap_roles_or_borrow_another_profile(self):
        configuration='lemmasim-silicon-package-closure-entry2-bulk-notebook'
        rows=list(image_specs(configuration))
        value={'schema_version':1,'contract_version':'lemma-user-image-catalog-v1',
               'configuration':configuration,'stage':'supervisor','image_count':4,'images':rows,
               **managed_fields(configuration),**software_deployment_fields(configuration)}
        validate_user_image_catalog(value)
        for changed in (rows[:3],rows[:2]+[rows[3],rows[2]],
                        rows[:2]+[{**rows[2],'source':'Lemma.Services.Arithmetic.ServerV5.main'}]+rows[3:],
                        [{**rows[0],'source':'Lemma.Services.Store.Server.main'}]+rows[1:],
                        rows[:1]+[{**rows[1],'source':'Lemma.Applications.Notebook.mainClosureBulk'}]+rows[2:],
                        rows[:3]+[{**rows[3],'source':'Lemma.Courses.PackageInstaller.main'}]):
            with self.subTest(changed=changed),self.assertRaises(Core0Error):
                validate_user_image_catalog({**value,'images':changed})
        for role,profile in (('arithmetic','core0-user-v0.5'),('notebook','core0-user-v0.7'),
                             ('course','core0-user-v0.2')):
            wrong=deepcopy(value);wrong['software_deployment']['user_profiles'][role]=profile
            with self.subTest(role=role),self.assertRaises(Core0Error):
                validate_user_image_catalog(wrong)

    def test_installer_authority_is_exact_and_local_owner_only(self):
        for workload,configuration in (
            ('notebook','lemmasim-silicon-package-closure-entry2-bulk-notebook'),
            ('initializer','lemmasim-silicon-package-closure-entry2-bulk-initialize')):
            for mode in ('developer','laboratory'):
                self.assertEqual(development_configuration('lemma-silicon-dev/0.3.0',workload,configuration,mode),configuration)
            for profile,mode in (('lemma-silicon-dev/0.3.0','student'),
                                 ('lemma-silicon-dev/0.13.0','developer')):
                with self.assertRaises(ValueError):
                    development_configuration(profile,workload,configuration,mode)
        for unknown in ('lemmasim-silicon-package-closure-bulk-notebook',
                        'lemmasim-silicon-package-closure-entry2-bulk-any',
                        'lemmasim-silicon-package-closure-entry2-bulk-initializer'):
            with self.assertRaises(Core0Error):configuration_roots(unknown)


if __name__=='__main__':unittest.main()
