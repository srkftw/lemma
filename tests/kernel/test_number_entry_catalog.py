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
if __name__=='__main__':unittest.main()
