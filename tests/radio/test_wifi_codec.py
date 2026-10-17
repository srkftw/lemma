"""Host admission/record negatives; distinct from actual RTL/guest qualification."""
import copy,struct,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from check_guest_wifi_codec import validate_unit,validate_records,crc_diagram
from core0_common import Core0Error

class CodecAdmission(unittest.TestCase):
 def unit(self):
  source='Lemma.Platform.RiscV.Development.WiFiCodecPolicy.main';symbol='lemma_wifi_codec_core0_action_0'
  ops=[{'source_identity':'Lemma.Core0.Execution.Op.physicalWrite'+str(bits),'primitive_symbol':None,'physical':True,'write':True,'width_bytes':bits//8} for bits in (8,64)]
  return {'schema_version':1,'artifact_category':'development-wifi-codec-execution-unit','configuration':'wifi-codec-development','contract_version':'core0-firmware-v0.2','role':'firmware','roots':[{'source':source,'symbol':symbol,'args':[]}],'functions':[{'source':source,'symbol':symbol,'args':[],'effects':['physical-write']}],'used_execution_ops':ops,'used_device_ops':[],'used_loops':[]}
 def test_foreign_root_source_and_duplicate_reject(self):
  for change in ('root','source','duplicate','symbol'):
   u=self.unit()
   if change=='root':u['roots'][0]['source']='Lemma.Other.main'
   if change=='source':u['functions'][0]['source']='Foreign.C.target'
   if change=='duplicate':u['functions'].append(copy.deepcopy(u['functions'][0]))
   if change=='symbol':u['functions'][0]['symbol']='foreign_helper'
   with self.subTest(change=change),self.assertRaises(Core0Error):validate_unit(u)
 def test_added_device_loop_or_effect_reject(self):
  for change in ('device','loop','effect','extra'):
   u=self.unit()
   if change=='device':u['used_device_ops']=[{'name':'WifiPIO'}]
   if change=='loop':u['used_loops']=[{'callback':'foreign'}]
   if change=='effect':u['functions'][0]['effects']=['machine-state']
   if change=='extra':u['unexpected']=True
   with self.subTest(change=change),self.assertRaises(Core0Error):validate_unit(u)
 def test_changed_write_authority_reject(self):
  for change,value in [('primitive_symbol','host_codec'),('physical',False),('write',False),('width_bytes',4),('source_identity','Lemma.Core0.Execution.Op.mmioWrite8')]:
   u=self.unit();u['used_execution_ops'][0][change]=value
   with self.subTest(change=change),self.assertRaises(Core0Error):validate_unit(u)
 def test_empty_completion_and_truncated_records_reject(self):
  for b in (b'',bytes(1023),bytes(1024),struct.pack('<Q',0x57494649444f4e01)+bytes(1016)):
   with self.subTest(size=len(b)),self.assertRaises(Core0Error):validate_records(b)
 def test_independent_crc_primary_numerical_answer(self):
  self.assertEqual(crc_diagram(b'123456789'),0xcbf43926)
if __name__=='__main__':unittest.main()
