"""Host regression checks for distinct discovery and fail-closed RTL launch."""
from pathlib import Path
import importlib.machinery, json, struct, sys, tempfile, unittest
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import silicon_profile as binding
import silicon_guest
import audit_kernel
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

if __name__=='__main__':unittest.main()
