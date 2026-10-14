"""Independent host ownership/page-walk guards; no guest/cold-recovery claim."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from course_snapshot_bytes import OwnedRAM, crc64, layout_sources


class SparseBytes:
    def __init__(self, start, value):
        self.start, self.value = start, value

    def __getitem__(self, interval):
        if interval.start == self.start and interval.stop == self.start + len(self.value):
            return self.value
        raise ValueError('fixture attempted another data span')


def fixture():
    # Literal expanded-layout fixture with independent small addresses/words.
    view = OwnedRAM()
    words = {0x804006a0: 8192}
    def frame(handle, owner, purpose, pins):
        record = 0x80401000 + (handle % 8192) * 32
        words.update({record: owner, record + 8: purpose,
                      record + 16: pins, record + 24: 1})
    frame(8320, 1, 1, 0)
    descriptor = 0x82080000
    values = [0x31534150414d454c, 2, 8320, 5, 1, 11, 1, 8321,
              0x82081000, 0x8000000000082081, 1024, 32]
    for i, value in enumerate(values):
        words[descriptor + i * 8] = value
    for i in range(11):
        frame(8321 + i, 5, 2, 1)
        words[descriptor + 128 + i * 8] = 8321 + i
    words[descriptor + 1408] = 8
    for i in range(8):
        frame(8332 + i, 5, 1, 0)
        words[descriptor + 1424 + i * 16] = 8332 + i
        words[descriptor + 1432 + i * 16] = 0x8208c000 + i * 4096
    frame(8340, 5, 4, 1)
    tracked = 0x208250d7
    words.update({0x8208c000: 0x48000, 0x8208c008: 8340,
                  0x8208c010: tracked, 0x8208c018: 3,
                  0x82081000: 0x20820801, 0x82082000: 0x20820c01,
                  0x82083240: tracked})
    view.word = lambda address: words.get(address, 0)
    value = bytes(range(128))
    view.ram = SparseBytes(0x02094000, value)
    return view, words, value


class SnapshotBytes(unittest.TestCase):
    def test_exact_course_source_version_selection_rejects_swaps_and_unknown(self):
        original={
          'Lemma/Kernel/Memory/Frames.lean':'bd750645ae330e1ce3c0e7baa98478daffa34f8350dcd74ae6c83e55f0304df8',
          'Lemma/Kernel/Memory/AddressSpace.lean':'83fa78cdb9be8cb9fc7fd468b0d15a49026774fb615d46773181ce74f04b4cf8',
          'Lemma/Platform/LemmaVM/Layout.lean':'75c8daa998344f1f49652539a833781faf180586797db804b51a6ba79460d903',
          'Lemma/Courses/PackageInstaller.lean':'e766ac704d2248e5d265fb94aed91bf4daf6d7c4cdac4619d19ed0d746fb30ae'}
        awaiting={**original,'Lemma/Courses/PackageInstaller.lean':'58efcb7fd14e6377ec9292889d52a19fe288085839f18687e6aeeb0594df8830'}
        for name in ('lemmasim-silicon-course-bulk-notebook','lemmasim-silicon-course-bulk-initialize'):
            layout_sources(original,name)
            with self.assertRaises(ValueError):layout_sources(awaiting,name)
        for name in ('lemmasim-silicon-course-await-bulk-notebook','lemmasim-silicon-course-await-bulk-initialize'):
            layout_sources(awaiting,name)
            with self.assertRaises(ValueError):layout_sources(original,name)
        with self.assertRaises(ValueError):layout_sources(awaiting,'lemmasim-silicon-course-await-bulk-any')
        with self.assertRaises(ValueError):layout_sources({**awaiting,'Lemma/Kernel/Memory/Frames.lean':'0'*64},'lemmasim-silicon-course-await-bulk-notebook')

    def test_crc_published_answer_and_independent_bitwise_vectors(self):
        def bitwise(raw):
            value = 0
            for byte in raw:
                value ^= byte << 56
                for _ in range(8):
                    value = ((value << 1) ^ (0x42f0e1eba9ea3693 if value & (1 << 63) else 0)) & 0xffffffffffffffff
            return value
        self.assertEqual(crc64(b'123456789'), 0x6c40df5f0b497347)
        for raw in (b'', b'\x00\xff\x7f', bytes(range(256))):
            self.assertEqual(crc64(raw), bitwise(raw))

    def test_all_raw_bytes_and_owned_mapping(self):
        view, words, value = fixture()
        actual, maps = view.owned_bytes(8320, 0x48000, 128)
        self.assertEqual(actual, value)
        self.assertEqual(maps, [{'va': 0x48000, 'physical': 0x82094000,
                                'bytes': 128, 'handle': 8340, 'owner': 5,
                                'pte': 0x208250d7, 'permissions': 3}])

    def test_live_owner_generation_pin_and_permission_corruption(self):
        mutations = [(0x80401000 + 148 * 32, 6),
                     (0x80401000 + 148 * 32 + 24, 2),
                     (0x80401000 + 148 * 32 + 16, 0),
                     (0x8208c018, 5), (0x82083240, 0x208250c7),
                     (0x82081000, 0x20820803), (0x8208c010, 0x208254d7)]
        for address, value in mutations:
            with self.subTest(address=hex(address)):
                view, words, _ = fixture()
                words[address] = value
                with self.assertRaises(ValueError):
                    view.owned_bytes(8320, 0x48000, 128)

    def test_duplicate_and_unowned_directory_or_table_reject(self):
        for mutation in ('duplicate-va', 'wrong-directory', 'wrong-table', 'stale-descriptor'):
            with self.subTest(mutation=mutation):
                view, words, _ = fixture()
                if mutation == 'duplicate-va':
                    words[0x82080030] = 2
                    words[0x8208c020] = 0x48000
                elif mutation == 'wrong-directory':
                    words[0x82080598] = 0x82094000
                elif mutation == 'wrong-table':
                    words[0x82082000] = 0x20825001
                else:
                    words[0x80401000 + 128 * 32 + 24] = 2
                with self.assertRaises(ValueError):
                    view.owned_bytes(8320, 0x48000, 128)

    def test_physical_and_loaded_span_bounds(self):
        view = OwnedRAM()
        view.ram = memoryview(bytes(8))
        for address in (0x7ffffff8, 0x88000000, 0x80000001):
            with self.assertRaises(ValueError):
                view.word(address)
        for size in (0, 127, 32769, True):
            with self.assertRaises(ValueError):
                view.owned_bytes(8320, 0x48000, size)


if __name__ == '__main__':
    unittest.main()
