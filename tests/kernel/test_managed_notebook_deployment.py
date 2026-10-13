"""Profile authority checks; these fixtures establish no guest execution."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from core0_common import Core0Error
from managed_records import contract,SOFTWARE_DEPLOYMENT
from silicon_profile import configuration_profile
from silicon_guest import configurations

class ManagedNotebookAuthority(unittest.TestCase):
 def unit(self):
  return {'contract_version':'core0-user-v0.2','role':'user','image_key':'notebook',
   'configuration':'lemmasim-silicon-managed-notebook','software_deployment':copy.deepcopy(SOFTWARE_DEPLOYMENT),
   'functions':[]}
 def test_exact_notebook_empty_record_closure_has_no_allocator_authority(self):
  self.assertIsNone(contract(self.unit()))
  for addition in ('catalog','generated'):
   unit=self.unit()
   if addition=='catalog':unit['managed_records']={}
   else:unit['functions']=[{'source':'Lemma.Mathematics.ManagedRational.compareFiveSix.__lemma_managed_v02.make'}]
   with self.assertRaises(Core0Error):contract(unit)
 def test_v2_profile_does_not_authorize_other_images_or_legacy_deployments(self):
  for key,value in [('image_key','store'),('role','kernel'),
   ('configuration','lemmasim-silicon-power-notebook'),('configuration','lemmasim-silicon-full-notebook')]:
   unit=self.unit();unit[key]=value
   with self.assertRaises(Core0Error):contract(unit)
  unit=self.unit();unit['software_deployment']['user_profiles']['store']='core0-user-v0.2'
  with self.assertRaises(Core0Error):contract(unit)
 def test_new_software_selection_keeps_actual_canonical_hardware_and_legacy_default(self):
  selections=configurations('lemma-silicon-dev/0.3.0')
  self.assertEqual(selections['notebook'],'lemmasim-silicon-power-notebook')
  self.assertEqual(selections['managed-notebook'],'lemmasim-silicon-managed-notebook')
  self.assertEqual(configuration_profile(selections['managed-notebook']),'lemma-silicon-dev/0.3.0')
  self.assertEqual(configuration_profile(selections['managed-initializer']),'lemma-silicon-dev/0.3.0')

if __name__=='__main__':unittest.main()
