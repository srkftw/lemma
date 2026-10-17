"""Exact isolated User7 software/boot registry, not guest execution evidence."""
import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from closure_deployment import CONFIGURATIONS,KERNEL_ENTRIES,SOFTWARE_DEPLOYMENT
from build_kernel import configuration_roots,managed_policy,SUMS_NOTEBOOK_CONFIGURATIONS
from audit_kernel import image_specs,kernel_contract,managed_fields,software_deployment_fields,validate_user_image_catalog
from silicon_profile import configuration_profile
from core0_common import Core0Error

class ClosureCatalog(unittest.TestCase):
 def test_exact_four_names_preserve_three_isolated_roles_and_binding(self):
  self.assertEqual(CONFIGURATIONS,('lemmasim-silicon-closure-bulk-notebook',
   'lemmasim-silicon-closure-bulk-initialize','lemmasim-silicon-closure-arithmetic-oom-development',
   'lemmasim-silicon-closure-arithmetic-fault-development'))
  for configuration in CONFIGURATIONS:
   with self.subTest(configuration=configuration):
    rows=list(image_specs(configuration))
    self.assertEqual([(r['key'],r['id'],r['source'],r['boot_role']) for r in rows],[
     ('store',1,'Lemma.Services.Store.Server.main','store-server'),
     ('notebook',2,'Lemma.Applications.Notebook.mainClosureBulk','notebook'),
     ('arithmetic',3,'Lemma.Services.Arithmetic.ServerV7.main','arithmetic-server')])
    self.assertEqual(configuration_profile(configuration),'lemma-silicon-dev/0.3.0')
    self.assertEqual(kernel_contract(configuration),'core0-kernel-v0.4')
    self.assertEqual(software_deployment_fields(configuration),{'software_deployment':SOFTWARE_DEPLOYMENT})
    self.assertEqual(SOFTWARE_DEPLOYMENT['user_profiles'],{'store':'core0-user-v0.1',
     'notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.7'})
    self.assertNotIn(configuration,SUMS_NOTEBOOK_CONFIGURATIONS)
    self.assertEqual(managed_policy(configuration),'lemma-notebook-arithmetic-v1')
    self.assertEqual(configuration_roots(configuration)['kernel'],(
     ('Lemma.Platform.LemmaSim.NotebookKernel.'+KERNEL_ENTRIES[configuration],()),
     ('Lemma.Platform.LemmaSim.NotebookKernel.dispatchBulk',('u64','u64','u64'))))
 def test_missing_swapped_role_profile_and_legacy_root_reject(self):
  for configuration in CONFIGURATIONS:
   rows=list(image_specs(configuration));value={'schema_version':1,'contract_version':'lemma-user-image-catalog-v1',
    'configuration':configuration,'stage':'supervisor','image_count':3,'images':rows,
    **managed_fields(configuration),**software_deployment_fields(configuration)}
   validate_user_image_catalog(value)
   for changed in (rows[:2],list(reversed(rows)),rows[:2]+[{**rows[2],'boot_role':'notebook'}],
     rows[:2]+[{**rows[2],'source':'Lemma.Services.Arithmetic.ServerV6.main'}]):
    with self.assertRaises(Core0Error):validate_user_image_catalog({**value,'images':changed})
   wrong=copy.deepcopy(value);wrong['software_deployment']['user_profiles']['arithmetic']='core0-user-v0.6'
   with self.assertRaises(Core0Error):validate_user_image_catalog(wrong)
  for name in ('lemmasim-silicon-closure-notebook','lemmasim-silicon-closure-arithmetic-stall-development',
   'lemmasim-silicon-closure-arithmetic-any-development'):
   with self.assertRaises(Core0Error):configuration_roots(name)
if __name__=='__main__':unittest.main()
