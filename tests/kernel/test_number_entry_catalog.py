"""Exact additive root admission; no target/compiler/CPU result is fabricated."""
import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import image_specs,MANAGED_POLICIES,validate_managed_provenance
from core0_common import Core0Error
CONFIG='lemmasim-silicon-package-closure-entry2-bulk-notebook'
ROOT='Lemma.Applications.Notebook.mainPackageNumberPad'
class NumberEntryCatalog(unittest.TestCase):
    def fixture(self,configuration=CONFIG,numeric=True):
        images=copy.deepcopy(list(image_specs(configuration)))
        if numeric:next(r for r in images if r['key']=='notebook')['source']=ROOT
        metadata={'managed_policy':MANAGED_POLICIES[configuration],'boot_roles':{r['key']:r['boot_role']for r in images}}
        return images,metadata
    def test_historical_and_additive_root_keep_exact_roles(self):
        for numeric in (False,True):
            images,m=self.fixture(numeric=numeric)
            validate_managed_provenance(m,m,configuration=CONFIG,images=images)
    def test_new_root_does_not_admit_other_image_changes(self):
        for key,value in [('module','Lemma.Courses.Arithmetic'),('id',99),('directory','users/store'),('boot_role','course-installer'),('source',ROOT+'Other')]:
            images,m=self.fixture();next(r for r in images if r['key']=='notebook')[key]=value
            with self.subTest(key=key),self.assertRaises(Core0Error):
                validate_managed_provenance(m,m,configuration=CONFIG,images=images)
    def test_new_root_does_not_widen_other_profiles_or_role_metadata(self):
        config='lemmasim-silicon-power-notebook';images,m=self.fixture(config)
        with self.assertRaises(Core0Error):validate_managed_provenance(m,m,configuration=config,images=images)
        images,m=self.fixture();bad=copy.deepcopy(m);bad['boot_roles']['notebook']='course-installer'
        with self.assertRaises(Core0Error):validate_managed_provenance(bad,m,configuration=CONFIG,images=images)

class CompanionNumberEntryCatalog(unittest.TestCase):
    CONFIGURATIONS = ('lemmasim-silicon-usb-clocked-package-retry-bulk-notebook',
                      'lemmasim-silicon-usb-clocked-package-retry-bulk-initialize')
    ROOT = 'Lemma.Applications.Notebook.mainRecoverablePackageNumberPad'

    def fixture(self, configuration, joined):
        from audit_kernel import managed_fields, software_deployment_fields
        images = copy.deepcopy(list(image_specs(configuration)))
        if joined:
            next(row for row in images if row['key'] == 'notebook')['source'] = self.ROOT
        return {'schema_version': 1, 'contract_version': 'lemma-user-image-catalog-v1',
                'configuration': configuration, 'stage': 'supervisor', 'image_count': len(images),
                'images': images, **managed_fields(configuration),
                **software_deployment_fields(configuration)}

    def test_old_and_joined_roots_retain_exact_catalog_primitive_and_managed_roles(self):
        from audit_kernel import (validate_user_image_catalog, validate_user_primitive_catalog,
                                  managed_fields, user_primitive_rows)
        for config in self.CONFIGURATIONS:
            for joined in (False, True):
                catalog = self.fixture(config, joined)
                validate_user_image_catalog(catalog, configuration=config)
                images = catalog['images']
                metadata = {'managed_policy': MANAGED_POLICIES[config],
                            'boot_roles': {row['key']: row['boot_role'] for row in images}}
                validate_managed_provenance(metadata, metadata, configuration=config, images=images)
                image = next(row for row in images if row['key'] == 'notebook')
                primitive = {'schema_version': 1, 'contract_version': 'lemma-user-execution-v1',
                             'configuration': config, 'image_key': image['key'],
                             'image_id': image['id'], 'startup_case': image['startup_case'],
                             'symbols': user_primitive_rows(image['startup_case']),
                             **managed_fields(config, image)}
                validate_user_primitive_catalog(primitive, image, configuration=config)

    def test_joined_root_cannot_widen_roles_paths_ids_or_other_deployments(self):
        from audit_kernel import validate_user_image_catalog
        for key, value in [('id', 99), ('module', 'Lemma.Courses.Arithmetic'),
                           ('source', self.ROOT+'Other'), ('directory', 'users/store'),
                           ('boot_role', 'course-installer')]:
            catalog = self.fixture(self.CONFIGURATIONS[0], True)
            next(row for row in catalog['images'] if row['key'] == 'notebook')[key] = value
            with self.subTest(key=key), self.assertRaises(Core0Error):
                validate_user_image_catalog(catalog)
        wrong = self.fixture(CONFIG, True)
        with self.assertRaises(Core0Error):
            validate_user_image_catalog(wrong)

if __name__ == "__main__":
    unittest.main()
