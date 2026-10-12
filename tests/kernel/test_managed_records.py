"""Fail-closed mutations of extracted actual ordinary-record artifacts."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from managed_records import contract,validate,PREFIX
from core0_common import Core0Error

FIXTURE=json.loads((Path(__file__).parent/'fixtures/managed-records.json').read_text())

class ManagedRecordAdmission(unittest.TestCase):
 def setUp(self):self.unit=copy.deepcopy(FIXTURE['unit']);self.ir=FIXTURE['ir']
 def test_real_extracted_pre_llvm_helper_closure(self):
  self.assertEqual(validate(self.ir,self.unit,optimized=False)['layout_bytes'],24)
 def test_legacy_generated_authority_is_rejected(self):
  self.unit['contract_version']='core0-user-v0.1'
  with self.assertRaises(Core0Error):contract(self.unit)
 def test_missing_managed_catalog_is_rejected(self):
  del self.unit['managed_records']
  with self.assertRaises(Core0Error):contract(self.unit)
 def test_missing_borrow_metadata_is_rejected(self):
  row=next(r for r in self.unit['managed_records']['functions'] if r['source']==PREFIX+'differenceFromFiveSix')
  row['genuine_ir']=row['genuine_ir'].replace('@& obj','obj')
  with self.assertRaises(Core0Error):contract(self.unit)
 def test_layout_and_real_release_are_load_bearing(self):
  self.unit['managed_records']['shapes'][0]['bytes']=16
  with self.assertRaises(Core0Error):contract(self.unit)
  self.unit=copy.deepcopy(FIXTURE['unit']);self.unit['functions']=[r for r in self.unit['functions'] if r['source']!='Lemma.User.Runtime.Arena.release']
  with self.assertRaises(Core0Error):contract(self.unit)
 def test_other_image_cannot_acquire_record_authority(self):
  self.unit['image_key']='notebook'
  with self.assertRaises(Core0Error):contract(self.unit)
 def test_cookie_field_and_helper_call_mutations_reject(self):
  for before,after in [('i64 1, i64 24','i64 2, i64 24'),('i64 24, i64 16','i64 24, i64 8')]:
   with self.subTest(mutation=after),self.assertRaises(Core0Error):validate(self.ir.replace(before,after),self.unit,optimized=False)
  r=self.unit['managed_records']['functions'][0]
  changed=self.ir.replace('@'+r['symbol']+'(', '@'+r['symbol']+'(',1).replace('entry:\n','entry:\n  %bad = call i64 @unrecorded_host_runtime()\n',1)
  with self.assertRaises(Core0Error):validate(changed,self.unit,optimized=False)
 def test_direct_field_load_cannot_bypass_arena(self):
  changed=self.ir.replace('entry:\n','entry:\n  %bad = load i64, ptr inttoptr (i64 4194304 to ptr)\n',1)
  with self.assertRaises(Core0Error):validate(changed,self.unit,optimized=False)

if __name__=='__main__':unittest.main()
