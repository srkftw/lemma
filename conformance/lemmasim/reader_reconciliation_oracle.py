"""Independent passive Reader19 lost-ACK/offline-ink record observation.

This finite Source23 case expects reader24, raw25, page26 and root27. It never
supplies a recovered record, drawing, acknowledgment or policy to a guest.
"""
import struct

from inspect_notebook import inspect_page

MAGIC = 0x314B4E49414D454C
READER = (1, 0x5244000000000001)
WORKSPACE = (1, 0x504B000000000001)
PAGE = (1, 257)
ROOT = (1, 1)
RAW = (1, 65561)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def observe(before, held, final, samples, sequence):
    """Check all source objects and every byte of the three appended objects."""
    require(sequence == 27, 'raw25/page26/root27 publication sequence required')
    require(len(samples) == 3 and all(len(row) == 9 for row in samples),
            'three complete independently captured raw samples required')
    require(READER not in before and set(held) == set(before) | {READER},
            'held reader24 is the only unacknowledged source addition')
    require(all(held[key] == record for key, record in before.items()),
            'unacknowledged reader changed an original object')
    reader = held[READER]
    require(reader.sequence == reader.transaction == 24 and len(reader.payload) == 128,
            'exact held reader24 identity/extent required')
    require(set(final) == set(held) | {RAW} and final[READER] == reader,
            'reader was replaced/duplicated or unexpected objects appeared')
    require(all(final[key] == record for key, record in before.items()
                if key not in (PAGE, ROOT)), 'original package/workspace/ink changed')
    require(final[ROOT].payload == before[ROOT].payload,
            'root content changed without a page/brush action')
    require([(final[key].sequence, final[key].transaction, final[key].sector)
             for key in (RAW, PAGE, ROOT)] ==
            [(25, 25, reader.sector + 3), (26, 26, reader.sector + 6),
             (27, 27, reader.sector + 9)],
            'three exact contiguous journal publications required')
    require(all(final[key].kind == 1 for key in (RAW, PAGE, ROOT)),
            'publication is not a live record')
    raw = final[RAW].payload
    require(len(raw) == 344 and struct.unpack_from('<16Q', raw) ==
            (MAGIC, 1, 3, 1, 24, 0, 3, 512, 1, 65535, 65535, 4095,
             1650, 2200, 3, 0), 'raw chunk header/style/lifecycle differs')
    actual = [struct.unpack_from('<9Q', raw, 128 + 72 * i) for i in range(3)]
    require(actual == samples, 'exact admitted offline samples differ')
    require(sum(record.payload == raw for record in final.values()) == 1,
            'raw chunk duplicated')
    old, new = before[PAGE].payload, final[PAGE].payload
    old_header, new_header = struct.unpack_from('<16Q', old), struct.unpack_from('<16Q', new)
    require(old_header[1] == new_header[1] == 2 and old_header[5] == old_header[6],
            'declared compact page with complete prior edit history required')
    expected_header = list(old_header)
    for field in (4, 5, 6):
        expected_header[field] += 1
    require(tuple(expected_header) == new_header and
            inspect_page(new, 257) == inspect_page(old, 257) + [(RAW[1], 24, 1)],
            'page did not append precisely one visible raw stroke')
    old_edits = old[128 + old_header[4] * 24:]
    new_edits = new[128 + new_header[4] * 24:]
    require(new_edits == old_edits + struct.pack('<2Q', 1, 24),
            'page edit history lost, duplicated or changed')
    return {'reader_sequence': 24, 'raw_sequence': 25, 'page_sequence': 26,
            'root_sequence': 27, 'exact_raw_samples': 3,
            'all_original_nonpage_objects_equal': True,
            'root_content_equal': True, 'exact_appended_page_and_history': True}
