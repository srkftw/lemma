# SPDX-License-Identifier: Apache-2.0
"""Integrated15 source admission; actual guest/RTL execution is separate."""
from pathlib import Path
import copy
import json
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import silicon_profile as binding
import lemmasim_fast
import product_native


class IntegratedProfile(unittest.TestCase):
    def test_unchanged_base_descriptor_and_explicit_extensions(self):
        current=binding.profile('lemma-silicon-dev/0.15.0')
        product=binding.profile('lemma-silicon-dev/0.10.0')
        # Descriptor ABI11 advertises the unchanged Product10 base. New
        # extension/clocked PHY details are discovered through DTB/MMIO.
        self.assertEqual(binding.descriptor(current,1234),binding.descriptor(product,1234))
        self.assertEqual((current['clock_hz'],current['devices']['pen']['fifo'],current['pen_ihp_sram']),(100000000,256,1))
        self.assertEqual(current['plic_sources'],19)
        self.assertEqual(current['devices']['multimodal']['irq'],19)
        self.assertEqual(current['devices']['boot_nv']['irq'],17)
        self.assertEqual(current['devices']['usb']['irq'],16)
        dts=binding.dts(current)
        for value in ('lemma,multimodal-v1','lemma,usb-device-clocked-v2','lemma,boot-nv-v1','lemma,power-v2','lemma,paper-v3'):
            self.assertIn(value,dts)
        self.assertEqual(current['paper_stage_offset'],3584)
        self.assertLessEqual(current['devices']['usb']['base']+current['devices']['usb']['span'],current['devices']['paper']['base']+current['paper_stage_offset'])

    def test_generated_authorities_preserve_legacy(self):
        for version in range(1,16):
            profile=binding.profile(f'lemma-silicon-dev/0.{version}.0')
            path=ROOT/'Lemma/Platform/Silicon'/(binding.binding_namespace(profile)+'.lean')
            self.assertEqual(path.read_text(),binding.lean_text(profile))
            self.assertEqual(binding.constants(profile)['pen_ihp_sram'],int(version==15))

    def test_capacity_address_and_authority_mutants_fail(self):
        original=binding.profile('lemma-silicon-dev/0.15.0')
        changes=(lambda p:p.update(pen_ihp_sram=0),
                 lambda p:p['devices']['pen'].update(fifo=128),
                 lambda p:p['devices']['usb'].update(irq=19),
                 lambda p:p['devices']['multimodal'].update(base=0x10012000),
                 lambda p:p.update(paper_stage_offset=2048),
                 lambda p:p['descriptor'].update(abi=4),
                 lambda p:p.update(usb_phy_version=1))
        for change in changes:
            candidate=copy.deepcopy(original);change(candidate)
            with self.subTest(candidate=candidate):
                with patch.object(Path,'read_text',return_value=json.dumps(candidate)):
                    with self.assertRaises(ValueError):binding.profile('lemma-silicon-dev/0.15.0')

    def test_fast_union_rejected_before_any_build(self):
        from types import SimpleNamespace
        with self.assertRaisesRegex(ValueError,'not implemented'):
            lemmasim_fast.build(SimpleNamespace(profile='lemma-silicon-dev/0.15.0'))

    def test_product10_image_abi_retained_explicitly(self):
        self.assertEqual(product_native.PROFILES[product_native.INTEGRATED_PROFILE],product_native.PROFILES[product_native.EXECUTED_PROFILE])

if __name__=='__main__':unittest.main()
