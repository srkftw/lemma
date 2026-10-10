"""Host-only cold dependency ordering guards; no Lean/LLVM/QEMU run is mocked as a target pass."""
from __future__ import annotations
import sys,tempfile,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import build_core0,build_device_suite,build_trap_suite,build_timer_suite,build_monitor
from core0_common import Core0Error
DEPENDENCY=Path('Lemma/Platform/LemmaVM/ConsoleDevice.lean')
CLIENT=Path('examples/foundation/DeviceConformanceSupport.lean')
DRIVERS=(build_device_suite,build_trap_suite,build_timer_suite,build_monitor)
class ExportBoundary(Exception): pass
class ConsoleDependencyTests(unittest.TestCase):
    def invoke_driver(self,driver,root,build_lean):
        kwargs=dict(root=root,output_dir=root/'build/core0/mock',opt_level='O0',build_lean=build_lean)
        if driver is build_device_suite:
            return driver.build_device_suite(**kwargs,suite_id=1,source_seed=2,runtime_seed=3)
        if driver is build_trap_suite:return driver.build_trap_suite(**kwargs)
        if driver is build_timer_suite:return driver.build_timer_suite(**kwargs)
        return driver.build_monitor_image(**kwargs)
    def fixture(self,driver):
        temporary=tempfile.TemporaryDirectory();root=Path(temporary.name)
        for source in (Path('examples/core0/Positive.lean'),DEPENDENCY,*driver.ELABORATION_SOURCES,driver.EXPORT_SOURCE):
            path=root/source;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('-- host ordering fixture '+str(source)+'\n')
        self.assertFalse((root/'.lake').exists())
        return temporary,root
    def precompile(self,root,commands,mode):
        def invoke(_rows,argv,**_):
            commands.append(tuple(argv))
            if tuple(argv)==('lake','build'):return None  # Library default deliberately does not realize this new module.
            if '-o' not in argv:raise ExportBoundary()
            output=root/argv[argv.index('-o')+1];source=Path(argv[-1]);output.parent.mkdir(parents=True,exist_ok=True)
            if source==CLIENT:
                needed=root/'.lake/build/lib/lean'/DEPENDENCY.with_suffix('.olean')
                if not needed.is_file() or not needed.stat().st_size:raise Core0Error('missing ConsoleDevice dependency before client')
            if source==DEPENDENCY and mode=='missing':return None
            output.write_bytes(b'' if source==DEPENDENCY and mode=='empty' else b'host-olean-fixture:'+str(source).encode())
        return invoke
    def test_cold_dependency_precedes_every_client_and_is_hashed_before_export(self):
        for driver in DRIVERS:
            for build_lean in (False,True):
                with self.subTest(driver=driver.__name__,build_lean=build_lean):
                    temporary,root=self.fixture(driver)
                    with temporary:
                        calls=[]
                        with mock.patch.object(build_core0,'require_tools',return_value={}),mock.patch.object(build_core0,'_invoke',side_effect=self.precompile(root,calls,'ok')),mock.patch.object(build_core0,'sha256',wraps=build_core0.sha256) as hashed:
                            with self.assertRaises(ExportBoundary):self.invoke_driver(driver,root,build_lean)
                        sources=[Path(c[-1]) for c in calls if '-o' in c]
                        self.assertEqual(sources.count(DEPENDENCY),1)
                        self.assertLess(sources.index(DEPENDENCY),sources.index(CLIENT))
                        dep_command=next(c for c in calls if '-o' in c and Path(c[-1])==DEPENDENCY)
                        expected=root/'.lake/build/lib/lean'/DEPENDENCY.with_suffix('.olean')
                        self.assertEqual(dep_command,('lake','env','lean','-o',str(expected.relative_to(root)),str(DEPENDENCY)))
                        hashed_paths=[Path(c.args[0]) for c in hashed.call_args_list]
                        self.assertIn(root/DEPENDENCY,hashed_paths);self.assertIn(expected,hashed_paths)
                        self.assertTrue(expected.is_file() and expected.stat().st_size>0)
                        self.assertEqual(Path(calls[-1][-1]),root/driver.EXPORT_SOURCE)
    def test_missing_or_empty_dependency_output_rejects_before_client_and_export(self):
        for driver in DRIVERS:
            for mode in ('missing','empty'):
                with self.subTest(driver=driver.__name__,mode=mode):
                    temporary,root=self.fixture(driver)
                    with temporary:
                        calls=[]
                        with mock.patch.object(build_core0,'require_tools',return_value={}),mock.patch.object(build_core0,'_invoke',side_effect=self.precompile(root,calls,mode)):
                            with self.assertRaisesRegex(Core0Error,'nonempty olean'):self.invoke_driver(driver,root,False)
                        self.assertFalse(any('-o' in c and Path(c[-1])==CLIENT for c in calls))
                        self.assertFalse(any('-o' not in c and c[:3]==('lake','env','lean') for c in calls))
if __name__=='__main__':unittest.main()
