"""Independent host artifact observer for course-package-v1.

This observes files produced by the Lean authoring command. It is never a guest
loader, journal recovery implementation or mathematical authority.
"""
from __future__ import annotations

import struct
import zlib


class PackageError(ValueError):
    pass


def decode(image: bytes) -> dict:
    def require(condition, message):
        if not condition:
            raise PackageError(message)

    require(128 <= len(image) <= 32768, 'image resource/length bound')
    words = struct.unpack_from('<16Q', image)
    (magic, version, length, identity, edition, count, entry_bytes, entries,
     text_offset, text_bytes, crc, inverse, *anchors) = words
    require(magic == 0x315352554f434d4c and version == 1, 'magic/version')
    require(length == len(image), 'exact total length')
    require(1 <= identity <= 65535 and 1 <= edition <= 0xffffffff, 'identity/edition')
    require(1 <= count <= 16 and entry_bytes == 192 and entries == 128, 'entry layout')
    require(text_offset == 128 + count * 192 and text_bytes <= 16384 and
            text_offset + text_bytes == length, 'text layout/resources')
    require(crc <= 0xffffffff and inverse == crc ^ 0xffffffff, 'checksum pair')
    checksum_image = image[:80] + bytes(16) + image[96:]
    require(zlib.crc32(checksum_image) == crc, 'independent CRC32 integrity')
    cursor = text_offset

    def text(span, required=False):
        nonlocal cursor
        offset, size = span & 0xffffffff, span >> 32
        require(offset == cursor and size <= 512 and offset + size <= length,
                'noncanonical or unbounded text span')
        require(size != 0 or not required, 'empty required text')
        raw = image[offset:offset + size]
        require(all(value == 10 or 32 <= value <= 126 for value in raw), 'unsupported text byte')
        cursor += size
        return raw.decode('ascii')

    title, source, edition_anchor, rights = (text(span, True) for span in anchors)
    nodes = []
    for ordinal in range(count):
        row = struct.unpack_from('<24Q', image, 128 + ordinal * 192)
        (node_id, kind, goal, checker, domain, assumptions, logical, pedagogical,
         anchor, budget, *remaining) = row
        require(node_id == anchor == ordinal + 1, 'node/source identity')
        require(1 <= kind <= 4, 'unsupported node kind')
        require(logical < 1 << ordinal and pedagogical < 1 << ordinal, 'prerequisite graph')
        require(all(value == 0 for value in remaining[:4] + remaining[12:]), 'reserved words')
        if kind == 3:
            require(assumptions == 0, 'unsupported assumptions')
            if goal in (1, 2):
                require(checker == 0x0001000000000001 and domain == goal and budget == 8,
                        'pinned exact checker/domain/resource reference')
            else:
                require(goal == 3 and checker == budget == 0 and domain == 3,
                        'unsupported goal reference')
        else:
            require(goal == checker == domain == assumptions == budget == 0,
                    'presentation node acquired checker authority')
        texts = [text(span, field in (0, 1, 6) or (kind == 3 and field == 4))
                 for field, span in enumerate(remaining[4:12])]
        nodes.append(dict(identity=node_id, kind=kind, goal=goal, checker=checker,
                          domain=domain, assumptions=assumptions, budget=budget,
                          logical_prerequisites=[i for i in range(ordinal) if logical >> i & 1],
                          pedagogical_prerequisites=[i for i in range(ordinal) if pedagogical >> i & 1],
                          title=texts[0], body=texts[1], example=texts[2], worked=texts[3],
                          exercise=texts[4], hint=texts[5], source_anchor=texts[6], review=texts[7]))
    require(cursor == len(image), 'unclaimed trailing bytes')
    return dict(format='lemma-course-package/1', identity=identity, edition=edition,
                bytes=length, crc32=crc, title=title, source_anchor=source,
                edition_anchor=edition_anchor, rights_anchor=rights, nodes=nodes)
