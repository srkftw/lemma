"""Raw byte transport admission; mock controls do not establish guest execution."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import lemmasim_fast as fast
import lemmasim_course_fast as course

class UARTAdmission(unittest.TestCase):
    def test_recipe_closure_admits_only_explicit_profiles(self):
        with mock.patch.dict(os.environ,{'LEMMA_FAST_RAW_UART':'1'}):
            self.assertEqual(fast.qemu_recipe('lemma-silicon-dev/0.14.0').name,'qemu_uart.nix')
            closure=fast.sources('lemma-silicon-dev/0.14.0')
            for name in ('qemu.nix','qemu_uart.nix','patch_counter_clock.py','patch_uart_ingress.py','uart_build_budget.py'):
                self.assertIn('tooling/lemmasim/'+name,closure)
            with self.assertRaises(ValueError):fast.raw_uart_selected('lemma-silicon-dev/0.4.0')
        with mock.patch.dict(os.environ,{'LEMMA_FAST_RAW_UART':''}):
            self.assertEqual(fast.qemu_recipe('lemma-silicon-dev/0.14.0').name,'qemu.nix')

    def test_profile_and_guest_configuration_must_match(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);image=root/'image.elf';image.write_bytes(b'host fixture only')
            identity=dict(profile='lemma-silicon-dev/0.14.0',adapter='lemmasim-fast-adapter/5',guest=hashlib.sha256(image.read_bytes()).hexdigest())
            (root/'session.json').write_text(json.dumps(dict(schema='lemmasim-live/1',mode='developer',backend='qemu',identity=identity,argv=['-kernel',str(image)])))
            args=SimpleNamespace(session_dir=root,command='course-load',identity=7,edition=1,crc=12,node=0,cycle=None)
            (root/'build.json').write_text(json.dumps(dict(configuration=course.CANONICAL_CONFIGURATIONS[0])))
            with mock.patch.object(course,'request') as request:
                with self.assertRaisesRegex(ValueError,'exact admitted'):course.send(args)
                request.assert_not_called()
            (root/'build.json').write_text(json.dumps(dict(configuration='lemmasim-silicon-multimodal-notebook')))
            observed=dict(identity=identity,running=False,machine=dict(cycle=4,devices=dict(uart_ingress=dict(enabled=True,pending=0))))
            with mock.patch.object(course,'request',side_effect=[observed,{'accepted':True}]) as request:
                result=course.send(args)
                self.assertEqual(result['status'],'RAW_COMMAND_ADMITTED')
                self.assertEqual(request.call_args_list[1].args[1]['kind'],'uart')
