"""Literal ELF/instruction boundary checks; actual warm reboot runs are separate."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_kernel import validate_boot_metadata_clear
from core0_common import Core0Error


class BootMetadataClearTests(unittest.TestCase):
    def fixture(self, configuration):
        expanded = configuration == 'lemmasim-notebook'
        limit = 0x80500000 if expanded else 0x80400080
        layout = {'configuration': configuration}
        symbols = {'__bss_start': 0x80400000, '__bss_end': limit,
                   '__boot_hartid': 0x80400000, '__boot_dtb': 0x80400008}
        segments = [{'virtual_address': 0x80400000, 'physical_address': 0x80400000,
                     'file_size': 0, 'memory_size': limit - 0x80400000, 'flags': 'RW'}]
        # Independent literal RV64 words: AUIPC/ADDI bounds, BGEU16, SDzero,
        # ADDI8, J-12, then hart/DTB stores only after reaching the upper bound.
        words = [0x00400297, 0xfac28293,
                 0x00500317 if expanded else 0x00400317,
                 0xfa430313 if expanded else 0x02430313,
                 0x0062f863, 0x0002b023, 0x00828293, 0xff5ff06f,
                 0x00400297, 0xf8c28293, 0x0082b023, 0x0092b423]
        text = '\n'.join(f'{0x80000054 + i * 4:08x}: {word:08x} literal' for i, word in enumerate(words))
        return layout, symbols, segments, text, {'_start': (0x80000000, 512)}

    def test_literal_legacy128_and_lemmasim_full_reserved_metadata(self):
        for configuration, amount in [('normal', 128), ('lemmasim-notebook', 1048576)]:
            observed = validate_boot_metadata_clear(*self.fixture(configuration))
            self.assertEqual(observed['bytes'], amount)
            self.assertEqual(observed['clear_loop_pc'], 0x80000064)
            self.assertEqual(observed['handoff_store_pc'], 0x8000007c)

    def test_stale_symbols_truncated_segment_initialized_or_extra_metadata_refused(self):
        fixture = self.fixture('lemmasim-notebook')
        for key, value in [('__bss_end', 0x80400080), ('__bss_start', 0x80400008),
                           ('__boot_dtb', 0x80400010), ('__boot_hartid', True)]:
            changed = deepcopy(fixture); changed[1][key] = value
            with self.subTest(symbol=key), self.assertRaises(Core0Error):
                validate_boot_metadata_clear(*changed)
        for key, value in [('memory_size', 128), ('file_size', 128), ('physical_address', 0x80401000), ('flags', 'RWE')]:
            changed = deepcopy(fixture); changed[2][0][key] = value
            with self.subTest(segment=key), self.assertRaises(Core0Error):
                validate_boot_metadata_clear(*changed)
        changed = deepcopy(fixture); changed[2].append({'virtual_address': 0x80401000,
            'physical_address': 0x80401000, 'file_size': 0, 'memory_size': 4096, 'flags': 'RW'})
        with self.assertRaises(Core0Error): validate_boot_metadata_clear(*changed)

    def test_wrong_actual_clear_bound_stride_store_branch_or_handoff_refused(self):
        fixture = self.fixture('lemmasim-notebook')
        for original, replacement in [('00500317', '00400317'), ('00828293', '01028293'),
                                      ('0002b023', '0012b023'), ('0062f863', '0062f463'),
                                      ('ff5ff06f', 'ff9ff06f'), ('0092b423', '0092b823')]:
            changed = deepcopy(fixture); changed = (*changed[:3], changed[3].replace(original, replacement), changed[4])
            with self.subTest(word=original), self.assertRaises(Core0Error):
                validate_boot_metadata_clear(*changed)
        changed = deepcopy(fixture); changed = (*changed[:3], changed[3] + '\n' + changed[3], changed[4])
        with self.assertRaises(Core0Error): validate_boot_metadata_clear(*changed)


if __name__ == '__main__': unittest.main()
