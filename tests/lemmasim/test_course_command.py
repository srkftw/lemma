"""Raw command frame and exact deployment admission, not guest durability."""
import copy,struct,sys,tempfile,unittest,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from lemmasim_course import frame,send
from check_course_guest import Machine
from check_course_cold import admitted_writer, capture_failure
from core0_common import sha256
from unittest.mock import patch
from types import SimpleNamespace
from silicon_guest_bundle import development_configuration

class CourseCommand(unittest.TestCase):
 def test_literal_wire_frame_and_limits(self):
  wire=frame(1,65535,0xffffffff,32768,7,0xffffffff)
  self.assertEqual(len(wire),64)
  self.assertEqual(struct.unpack('<8Q',wire),(0x31504b43414d454c,1,1,65535,0xffffffff,32768,7,0xffffffff))
  self.assertEqual(struct.unpack('<8Q',frame(2,1,2,0,15,0))[-2:],(15,0))
  for args in ((1,0,1,128,1,0),(1,1,0,128,1,0),(1,1,1,32769,1,0),
               (1,1,1,128,0,0),(2,1,1,0,16,0),(3,1,1,1,1,0),(3,1,1,0,1,1<<32)):
   with self.subTest(args=args),self.assertRaises(ValueError):frame(*args)
 def test_exact_local_authority_and_historical_mode(self):
  course='lemmasim-silicon-course-bulk-notebook'
  for mode in ('developer','laboratory'):
   self.assertEqual(development_configuration('lemma-silicon-dev/0.3.0','notebook',course,mode),course)
  with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.3.0','notebook',course,'student')
  with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.3.0','initializer',course,'developer')
  with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.2.0','notebook',course,'developer')
  ordinary='lemmasim-silicon-array-bulk-notebook'
  self.assertEqual(development_configuration('lemma-silicon-dev/0.3.0','notebook',ordinary,'student'),ordinary)

class CompanionCourseCommand(unittest.TestCase):
 def fixture(self,root,configuration,profile):
  build=root/'guest';build.mkdir();image=build/'image.elf';image.write_bytes(b'host admission fixture, never executed')
  (build/'build.json').write_text(json.dumps({'configuration':configuration}))
  session=root/'session';session.mkdir();(session/'session.json').write_text(json.dumps({
   'schema':'lemmasim-live/1','mode':'developer','backend':'rtl',
   'identity':{'profile':profile,'guest':hashlib.sha256(image.read_bytes()).hexdigest()},
   'argv':['machine','--image',str(image)]}))
  package=root/'untrusted.lcp';raw=bytearray(128);struct.pack_into('<2Q',raw,24,1,2);struct.pack_into('<Q',raw,80,17);package.write_bytes(raw)
  return SimpleNamespace(session_dir=session,command='course-install',package=package,transaction=7,cycle=None),bytes(raw)
 def test_exact_companion_pair_transports_untrusted_bytes_without_receipt(self):
  for suffix in ('notebook','initialize'):
   with self.subTest(suffix=suffix),tempfile.TemporaryDirectory() as temporary:
    args,raw=self.fixture(Path(temporary),'lemmasim-silicon-usb-clocked-package-retry-bulk-'+suffix,'lemma-silicon-dev/0.13.0')
    with patch('lemmasim_course.request',return_value={'admitted':True}) as request:
     result=send(args)
    self.assertEqual(result['status'],'RAW_COMMAND_ADMITTED');self.assertIn('No persistence receipt',result['receipt'])
    packet=bytes.fromhex(request.call_args.args[1]['hex'])
    self.assertEqual(packet,frame(1,1,2,128,7,17)+raw)
    self.assertEqual(args.package.read_bytes(),raw)
 def test_foreign_hardware_and_three_role_image_cannot_gain_installer_authority(self):
  for configuration,profile in [
   ('lemmasim-silicon-usb-clocked-package-retry-bulk-notebook','lemma-silicon-dev/0.3.0'),
   ('lemmasim-silicon-package-closure-entry2-bulk-notebook','lemma-silicon-dev/0.13.0'),
   ('lemmasim-silicon-usb-clocked-closure-retry-bulk-notebook','lemma-silicon-dev/0.13.0')]:
   with self.subTest(configuration=configuration,profile=profile),tempfile.TemporaryDirectory() as temporary:
    args,_=self.fixture(Path(temporary),configuration,profile)
    with patch('lemmasim_course.request') as request,self.assertRaises(ValueError):send(args)
    request.assert_not_called()

class CourseCommandBudgets(unittest.TestCase):
 def test_each_command_gets_the_declared_budget_from_actual_admission(self):
  machine=Machine.__new__(Machine);limits=[]
  machine.until=lambda predicate,limit:limits.append(limit)
  machine.directory=Path('/not-used-by-mocked-observer')
  matching=[(0x4b1,1,7,0,0)]
  with patch('check_course_guest.rows',return_value=matching):
   machine.cycles=56000000
   self.assertEqual(machine.outcome(0,1,0,100000000),matching[0])
   machine.cycles=135000000
   self.assertEqual(machine.outcome(0,1,0,100000000),matching[0])
  self.assertEqual(limits,[156000000,235000000])
 def test_invalid_or_overflowing_command_budget_rejects_before_run(self):
  machine=Machine.__new__(Machine);machine.cycles=0
  machine.until=lambda *_:self.fail('invalid budget ran the machine')
  for budget in (0,100000001,True):
   with self.assertRaises(ValueError):machine.outcome(0,1,0,budget)
  machine.cycles=(1<<64)-1
  with self.assertRaises(ValueError):machine.outcome(0,1,0,1)

class CourseColdAdmission(unittest.TestCase):
 def test_failure_reuses_same_boundary_and_never_creates_a_third_snapshot(self):
  from types import SimpleNamespace
  machine=SimpleNamespace(directory=Path('/unit-only-session'))
  state={'cycle':100,'retired':27,'event_queue':0}
  latest=Path('/unit-only-loaded-edition2')
  with patch('check_course_cold.request',return_value={'machine':state}) as request:
   observation,count=capture_failure(machine,Path('/unit-only-work'),2,latest,state)
   self.assertEqual(count,2);self.assertEqual(observation['snapshot']['snapshot'],str(latest))
   self.assertEqual(request.call_count,1)
  with patch('check_course_cold.request',return_value={'machine':dict(state,cycle=101)}) as request:
   observation,count=capture_failure(machine,Path('/unit-only-work'),2,latest,state)
   self.assertEqual(count,2);self.assertIn('snapshot_error',observation)
   self.assertEqual(request.call_count,1)
  with patch('check_course_cold.request',side_effect=[{'machine':dict(state,cycle=101)},TimeoutError('ambiguous checkpoint reply')]) as request:
   observation,count=capture_failure(machine,Path('/unit-only-work'),1,latest,state)
   self.assertEqual(count,2);self.assertIn('ambiguous checkpoint reply',observation['snapshot_error'])
   self.assertEqual(request.call_count,2)

 def test_only_exact_acknowledged_artifacts_and_medium_admit(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);medium=(root/'actual.raw').resolve();packages=[];installed=[]
   for edition in (1,2):
    package=root/f'edition{edition}.lcp';raw=bytearray(128);struct.pack_into('<Q',raw,80,0xabcd+edition);package.write_bytes(raw);packages.append(package)
    installed.append({'artifact_sha256':sha256(package),'outcome':[0x4b1,1,edition,1+(edition<<16),0xabcd+edition],
     'command':{'edition':edition},'cycle':edition*100})
   receipt={'status':'FAIL','installed':installed,'preflight_rejections':{},'commands':[['lemmasim','--disk',str(medium)]]}
   self.assertEqual([item['outcome'][2] for item in admitted_writer(receipt,packages,medium)],[1,2])
   negatives=[]
   value=copy.deepcopy(receipt);value['status']='PASS';negatives.append(value)
   value=copy.deepcopy(receipt);value['installed'][1]['outcome'][2]=3;negatives.append(value)
   value=copy.deepcopy(receipt);value['installed'][0]['artifact_sha256']='0'*64;negatives.append(value)
   value=copy.deepcopy(receipt);value['commands'][0][-1]=str(root/'other.raw');negatives.append(value)
   value=copy.deepcopy(receipt);value.pop('preflight_rejections');negatives.append(value)
   for value in negatives:
    with self.assertRaises(ValueError):admitted_writer(value,packages,medium)

if __name__=='__main__':unittest.main()
