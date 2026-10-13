"""Host regression checks for distinct discovery and fail-closed RTL launch."""
from pathlib import Path
import importlib.machinery, json, struct, sys, tempfile, unittest
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import silicon_profile as binding
import silicon_guest
import audit_kernel
import check_silicon
from core0_common import Core0Error
from unittest import mock

class BindingTests(unittest.TestCase):
    def test_generated_lean_is_exact_and_qemu_profile_unchanged(self):
        p=binding.profile()
        self.assertEqual((ROOT/'Lemma/Platform/Silicon/Binding.lean').read_text(),binding.lean_text(p))
        qemu=json.loads((ROOT/'sim/profiles/lemmasim-virt-0.1.0.json').read_text())
        self.assertEqual(qemu['profile'],'lemmasim-virt/0.1.0')
        self.assertEqual(qemu['devices']['rtc']['base'],0x101000)
        self.assertEqual(p['clock_hz']//p['timebase_hz'],10)
        self.assertGreaterEqual(p['geometry'][0],512)

    def test_silicon_does_not_advertise_absent_devices(self):
        full=binding.dts(binding.profile(),True)
        compute=binding.dts(binding.profile(),False)
        for absent in ('rtc@','pci@','flash@','fw-cfg','virtio_mmio@10002000'):
            self.assertNotIn(absent,full)
        self.assertIn('lemma,silicon-dev-v1',full)
        self.assertIn('lemma,diagnostic-uart-v1',full)
        self.assertIn('clock-frequency = <100000000>',full)
        self.assertNotIn('ns16550a',full)
        for device in ('lemma-paper@','lemma-pen@','virtio_mmio@'):
            self.assertIn(device,full)
            self.assertNotIn(device,compute)

    def test_descriptor_is_distinct_and_checksummed(self):
        values=struct.unpack('<32Q',binding.descriptor(binding.profile(),2048))
        self.assertEqual(values[1],2)
        self.assertEqual(values[25],0)
        self.assertEqual(values[21],3)
        self.assertEqual(values[7],0x400000)
        self.assertEqual((binding.profile()['frame_count'],binding.profile()['frame_quota']),(1024,128))
        self.assertEqual(values[3],sum(v for i,v in enumerate(values) if i!=3)&((1<<64)-1))

    def test_device_probe_admission_is_exact_and_development_only(self):
        scopes=('Lemma.Platform.Silicon.Development.DeviceEntry',
                'Lemma.Platform.Silicon.Development.DeviceProbe')
        self.assertEqual(audit_kernel.development_modules('lemmasim-silicon-devices','kernel'),scopes)
        self.assertEqual(audit_kernel.development_modules('normal','kernel'),())
        for configuration in ('lemmasim-notebook','lemmasim-silicon-notebook'):
            self.assertEqual(audit_kernel.development_modules(configuration,'kernel'),
                             ('Lemma.Platform.LemmaSim.NotebookKernel',))
        with mock.patch.object(audit_kernel,'configuration_development_modules',
                               return_value=scopes+('Lemma.Platform.Silicon.Development.Unknown',)):
            with self.assertRaisesRegex(Core0Error,'exact audited module catalog'):
                audit_kernel.development_modules('lemmasim-silicon-devices','kernel')

    def test_prepared_artifact_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bytes';path.write_bytes(b'original')
            identity=silicon_guest.identified(path)
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'changed or missing'):
                silicon_guest.validate(identity)

    def test_binary_uart_marker_and_bounds_fail_closed(self):
        args=SimpleNamespace(cycles=1,trace_limit=0,timeout=5,uart_stop=None,
            uart_stop_hex='ff000d',stop_after_panel=None,fail_flush=None)
        self.assertEqual(silicon_guest.bounded_options(args)['uart_stop_hex'],'ff000d')
        args.uart_stop_hex='0'
        with self.assertRaisesRegex(ValueError,'whole bytes'):silicon_guest.bounded_options(args)
        args.uart_stop_hex='xx'
        with self.assertRaisesRegex(ValueError,'hexadecimal'):silicon_guest.bounded_options(args)
        args.uart_stop_hex=None;args.cycles=0
        with self.assertRaisesRegex(ValueError,'cycles'):silicon_guest.bounded_options(args)

    def test_backend_timeout_limits_remain_finite_and_distinct(self):
        args=SimpleNamespace(cycles=1,trace_limit=0,timeout=silicon_guest.MAX_RUN_SECONDS)
        self.assertEqual(silicon_guest.bounded_options(args)['timeout'],7200)
        args.timeout=7201
        with self.assertRaisesRegex(ValueError,'1..7200'):
            silicon_guest.bounded_options(args)
        loader=importlib.machinery.SourceFileLoader('silicon_timeout_launcher',str(ROOT/'scripts/lemmasim'))
        launcher=loader.load_module()
        for backend,seconds in (('qemu','3601'),('rtl','7201')):
            with self.subTest(backend=backend),mock.patch.object(sys,'argv',
                    ['lemmasim','run','--backend',backend,'--timeout',seconds]), \
                    mock.patch.object(silicon_guest,'run') as run:
                with self.assertRaises(SystemExit) as rejected:launcher.main()
                self.assertEqual(rejected.exception.code,2);run.assert_not_called()
        with mock.patch.object(sys,'argv',['lemmasim','run','--backend','rtl','--timeout','7200']), \
                mock.patch.object(silicon_guest,'run') as run:
            self.assertEqual(launcher.main(),0)
            self.assertEqual(run.call_args.args[0].timeout,7200)

    def test_compiled_deadline_observer_rejects_adapter_disagreement(self):
        def actual(argv,**kwargs):
            seconds=int(argv[-1])
            error=(b'RTL adapter: development boot requires --image and --rom\n' if 1<=seconds<=7200 else
                   b'RTL adapter: deadline must be1..7200seconds\n')
            return SimpleNamespace(returncode=1,stdout=b'',stderr=error)
        with mock.patch.object(check_silicon.subprocess,'run',side_effect=actual):
            self.assertEqual(len(check_silicon.host_deadline_options(Path('fixture-host'))),4)
        for failed in (SimpleNamespace(returncode=0,stdout=b'',stderr=b''),
                       SimpleNamespace(returncode=1,stdout=b'',stderr=b'RTL adapter: deadline must be1..3600seconds\n')):
            with self.subTest(result=failed),mock.patch.object(check_silicon.subprocess,'run',return_value=failed):
                with self.assertRaisesRegex(RuntimeError,'disagrees'):
                    check_silicon.host_deadline_options(Path('fixture-host'))

    def test_raw_ram_snapshot_rejects_outside_and_unbounded_ranges(self):
        self.assertEqual(silicon_guest.ram_dump_range('0x82000000:1048576'),(0x82000000,1048576))
        self.assertEqual(silicon_guest.ram_dump_range('0x87ffffff:1'),(0x87ffffff,1))
        for spec in ('0x7fffffff:1','0x88000000:1','0x87ffffff:2','0x82000000:0',
                     '0x82000000:1048577','0x82000000:-1','0x82000000:1:elsewhere','x:1',True):
            with self.subTest(spec=spec),self.assertRaises(ValueError):silicon_guest.ram_dump_range(spec)
        args=SimpleNamespace(cycles=1,trace_limit=0,timeout=5,block_trace=1)
        with self.assertRaisesRegex(ValueError,'boolean'):silicon_guest.bounded_options(args)

    def test_diagnostic_outputs_are_regenerated_and_inventoried(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);image=directory/'image';image.write_bytes(b'host fixture only')
            data={'profile':'lemma-silicon-dev/0.1.0','binary':{'path':'fixture-rtl'},'rom':{'path':'fixture-rom'},
                  'workloads':{'service':{'image':{'path':str(image)},'dtb':{'path':'fixture-dtb'}}}}
            def launched(argv,**kwargs):
                self.assertIn('--block-trace',argv)
                self.assertEqual(argv[argv.index('--ram-dump')+1],f'2181038080:4:{directory/"ram.bin"}')
                (directory/'ram.bin').write_bytes(b'raw!');(directory/'block.csv').write_text('literal observations')
                process=mock.Mock();process.wait.return_value=0;process.poll.return_value=0;return process
            options=silicon_guest.bounded_options(SimpleNamespace(cycles=10,trace_limit=0,timeout=5,
                       observer_cycle=10,ram_dump='0x82000000:4',block_trace=True))
            with mock.patch.object(silicon_guest.subprocess,'Popen',side_effect=launched):
                result=silicon_guest.execute(data,'service',directory,options,{},None)
            self.assertEqual(result['status'],'STOPPED_BY_PROTOCOL')
            self.assertEqual(result['outputs']['ram.bin'],silicon_guest.sha(directory/'ram.bin'))
            self.assertEqual(result['outputs']['block.csv'],silicon_guest.sha(directory/'block.csv'))

if __name__=='__main__':unittest.main()
