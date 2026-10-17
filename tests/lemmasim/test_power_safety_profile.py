from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from silicon_profile import profile,constants,dts
from silicon_guest import configurations
from lemmasim_session import Session,external_command
class PowerSafetyProfile(unittest.TestCase):
 def test_opt_in_binding_preserves_canonical_capacity(self):
  old,new=profile('lemma-silicon-dev/0.3.0'),profile('lemma-silicon-dev/0.4.0')
  for key in ('geometry','ram_base','ram_bytes','frame_pool_base','frame_pool_bytes','frame_count','frame_quota','clock_hz','timebase_hz'):
   self.assertEqual(old[key],new[key])
  self.assertEqual(constants(old)['power_safety'],0)
  self.assertEqual((new['power_version'],new['descriptor']['abi']),(2,5))
  self.assertEqual(new['power_registers']['watchdog_timeout'],96)
  self.assertEqual(new['power_registers']['reset_epoch'],152)
  self.assertIn('lemma,power-v1',dts(old));self.assertIn('lemma,power-v2',dts(new))
  self.assertEqual(configurations(new['profile']),{'power':'lemmasim-silicon-power-safety-probe'})
 def test_supply_level_and_future_cycle_are_bounded(self):
  self.assertEqual(external_command({'action':'inject','kind':'brownout','level':1,'cycle':19},17)[0],'inject 19 brownout 1')
  for change in ({'level':2},{'level':True},{'cycle':16}):
   with self.assertRaises(ValueError):external_command(dict({'action':'inject','kind':'pgood','level':0},**change),17)
 def test_supply_fault_permission_precedes_machine_observation(self):
  for mode in ('student','developer'):
   session=Session.__new__(Session);session.mode=mode;session.capture_uncertain=False
   session.adapter=None # No machine is installed: rejected before any observation.
   with self.assertRaisesRegex(ValueError,'Laboratory'):
    session.dispatch({'action':'inject','kind':'pgood','level':0})
