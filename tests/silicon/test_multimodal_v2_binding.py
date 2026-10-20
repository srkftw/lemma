"""Versioned machine/controller admission; no controller execution claim."""
import copy,importlib.machinery,importlib.util,json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import silicon_profile as profiles
import lemmasim_fast as fast
import build_kernel
from types import SimpleNamespace
loader=importlib.machinery.SourceFileLoader('mm2_native_cli',str(ROOT/'scripts/lemmasim'))
spec=importlib.util.spec_from_loader(loader.name,loader);cli=importlib.util.module_from_spec(spec);loader.exec_module(cli)

class BindingTests(unittest.TestCase):
 def test_full_union_and_separate_subset(self):
  old=profiles.profile('lemma-silicon-dev/0.15.0');new=profiles.profile('lemma-silicon-dev/0.16.0')
  self.assertEqual({k:v for k,v in old.items() if k!='profile'},{k:v for k,v in new.items() if k not in ('profile','multimodal_controller_abi','multimodal_pcm_ring')})
  self.assertEqual(profiles.constants(new)['multimodal_controller_abi'],2)
  self.assertEqual(profiles.configuration_profile('lemmasim-silicon-integrated-pcm-school-notebook'),new['profile'])
  for n in range(1,16):self.assertEqual(profiles.constants(profiles.profile(f'lemma-silicon-dev/0.{n}.0'))['multimodal_controller_abi'],1)
 def altered(self,name,mutate):
  path=profiles.profile_path(name);data=json.loads(path.read_text());mutate(data);original=Path.read_text
  def read(p,*args,**kw):return json.dumps(data) if p==path else original(p,*args,**kw)
  with patch.object(Path,'read_text',read):
   with self.assertRaises(ValueError):profiles.profile(name)
 def test_no_removed_union_device(self):self.altered('lemma-silicon-dev/0.16.0',lambda d:d.update(usb_enabled=0))
 def test_no_unowned_second_page(self):self.altered('lemma-silicon-dev/0.16.0',lambda d:d['multimodal_pcm_ring'].update(capacity_samples=4096))
 def test_no_silent_legacy_upgrade(self):self.altered('lemma-silicon-dev/0.15.0',lambda d:d.update(multimodal_controller_abi=2))
 def test_missing_ring_contract_fails_closed(self):
  original=Path.is_file;missing=ROOT/'docs/contracts/009-multimodal-pcm-ring-v1.html'
  with patch.object(Path,'is_file',lambda p:False if p==missing else original(p)):
   with self.assertRaisesRegex(Exception,'Missing Integrated16 owned PCM dependency'):build_kernel.source_inputs(ROOT)
 def test_archived_source_does_not_acquire_new_dependency(self):
  old=ROOT/'build/task009/school23-mm-source-a6'
  if not old.is_dir():self.skipTest('optional retained local source archive')
  self.assertEqual(build_kernel.source_inputs(old),json.loads((old/'source-inputs.json').read_text()))

class SubsetTests(unittest.TestCase):
 def metadata(self):return {'profile':'lemma-silicon-dev/0.14.0','execution_binding':fast.MM2_BINDING,'multimodal_controller_abi':2,'controller_contract':'lemma-multimodal-converter/2','sources':{'sim/host/lemma_multimodal_v2.c':'fixture'}}
 def test_explicit_subset_not_checkpoint(self):
  data=self.metadata();self.assertTrue(fast.validate_execution_binding(data));self.assertFalse(fast.validate_checkpoint_binding(data))
 def test_no_false_full_union(self):
  data=self.metadata();data['profile']='lemma-silicon-dev/0.16.0'
  with self.assertRaises(ValueError):fast.validate_execution_binding(data)
 def test_no_old_checkpoint_promotion(self):
  data=self.metadata();data['checkpoint_binding']=fast.LOGICAL2_BINDING
  with self.assertRaises(ValueError):fast.validate_checkpoint_binding(data)
 def test_no_unbound_controller_metadata(self):
  data=self.metadata();del data['execution_binding']
  with self.assertRaises(ValueError):fast.validate_execution_binding(data)
 def test_snapshot_remains_guarded(self):
  instance=fast.Fast.__new__(fast.Fast);instance.mm2_subset=True
  with self.assertRaisesRegex(ValueError,'not publicly admitted'):instance.checkpoint_admission()
 def test_prepared_namespace_separate(self):
  with patch.dict(os.environ,{'LEMMA_FAST_RAW_UART':'1','LEMMA_FAST_LOGICAL2':'1','LEMMA_FAST_MM2':'1'}):self.assertEqual(fast.prepared_path('lemma-silicon-dev/0.14.0').name,'fast-uart1-mm2-prepared-0.14.0.json')

class CLISelectionTests(unittest.TestCase):
 def selection(self,**changes):
  return SimpleNamespace(**({'controller_binding':'mm2-subset','checkpoint_binding':None,
   'profile':'lemma-silicon-dev/0.14.0','command':'native-bundle-build',
   'school_deployment':True,'backend':'qemu','workload':'school-notebook',
   'mode':'student','actor':'learner'}|changes))
 def test_explicit_binding_keeps_student_authority(self):
  args=self.selection()
  with patch.dict(os.environ,{},clear=True):
   cli.select_checkpoint_binding(args)
   self.assertEqual({key:os.environ[key] for key in ('LEMMA_FAST_RAW_UART','LEMMA_FAST_LOGICAL2','LEMMA_FAST_MM2')},
    {'LEMMA_FAST_RAW_UART':'1','LEMMA_FAST_LOGICAL2':'1','LEMMA_FAST_MM2':'1'})
   self.assertEqual((args.mode,args.actor),('student','learner'))
 def test_invalid_selection_preserves_environment(self):
  cases=[{'profile':'lemma-silicon-dev/0.16.0'},{'checkpoint_binding':'native-logical2'},
   {'school_deployment':False},{'command':'build','backend':'rtl'},
   {'command':'build','workload':'notebook'},{'command':'session'}]
  for changes in cases:
   with self.subTest(changes=changes),patch.dict(os.environ,{'EXISTING':'retained'},clear=True):
    with self.assertRaises(cli.Failure):cli.select_checkpoint_binding(self.selection(**changes))
    self.assertEqual(dict(os.environ),{'EXISTING':'retained'})
 def test_both_school_preparations_select_same_binding(self):
  for workload in ('school-notebook','school-initializer'):
   with self.subTest(workload=workload),patch.dict(os.environ,{},clear=True):
    cli.select_checkpoint_binding(self.selection(command='build',workload=workload))
    self.assertEqual(os.environ['LEMMA_FAST_MM2'],'1')

if __name__=='__main__':unittest.main()
