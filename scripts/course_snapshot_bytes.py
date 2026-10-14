"""Read-only bytes from the declared canonical native2 Course installer.

This is an independent observation after a real cold Load. It never restores a
snapshot, decodes a journal, supplies memory, or decides mathematical authority.
Only the exact existing native backend and declared owned Sv39 layout qualify.
"""
import hashlib
import json
import struct
import zlib
from pathlib import Path

from core0_common import sha256

RUNTIME = '32282772a5cc60a5b52abacd05ae3bf3a952167025a5bb6a787a94e852002e77'
RAM_BASE = 0x80000000
RAM_BYTES = 128 << 20
POOL = 0x82000000
RECORDS = 0x80401000
CONFIGURATION = 0x804006a0
LOADED = 0x48000
MASK = (1 << 64) - 1
BOUND_SOURCES = {
    'Lemma/Kernel/Memory/Frames.lean': 'bd750645ae330e1ce3c0e7baa98478daffa34f8350dcd74ae6c83e55f0304df8',
    'Lemma/Kernel/Memory/AddressSpace.lean': '83fa78cdb9be8cb9fc7fd468b0d15a49026774fb615d46773181ce74f04b4cf8',
    'Lemma/Platform/LemmaVM/Layout.lean': '75c8daa998344f1f49652539a833781faf180586797db804b51a6ba79460d903',
    'Lemma/Courses/PackageInstaller.lean': 'e766ac704d2248e5d265fb94aed91bf4daf6d7c4cdac4619d19ed0d746fb30ae',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def crc64(data):
    table = []
    for byte in range(256):
        value = byte << 56
        for _ in range(8):
            value = ((value << 1) ^ (0x42f0e1eba9ea3693 if value >> 63 else 0)) & MASK
        table.append(value)
    value = 0
    for byte in data:
        value = ((value << 8) ^ table[(value >> 56) ^ byte]) & MASK
    return value


class OwnedRAM:
    """Authoritative raw RAM read through independently checked live metadata."""
    def word(self, address):
        require(len(self.ram) == RAM_BYTES, 'observer entire RAM byte span')
        require(type(address) is int and address % 8 == 0 and
                RAM_BASE <= address <= RAM_BASE + RAM_BYTES - 8,
                'observer physical word bounds/alignment')
        return struct.unpack_from('<Q', self.ram, address - RAM_BASE)[0]

    def frame(self, owner, handle, purpose, pins):
        require(type(handle) is int and 0 < owner < MASK and
                0 < handle // 8192 <= 0x007fffffffffffff,
                'observer frame owner/handle generation bound')
        index = handle % 8192
        record = RECORDS + index * 32
        require(self.word(record) == owner and self.word(record + 8) == purpose and
                self.word(record + 24) == handle // 8192,
                'observer live frame owner/purpose/generation')
        actual_pins = self.word(record + 16)
        require(actual_pins == 0 if pins == 0 else 0 < actual_pins,
                'observer live frame pin state')
        return POOL + index * 4096

    def descriptor(self, handle):
        require(self.word(CONFIGURATION) == 8192, 'observer canonical8192 frame pool')
        address = self.frame(1, handle, 1, 0)
        require(self.word(address) == 0x31534150414d454c and
                self.word(address + 8) in (2, 3) and
                self.word(address + 16) == handle and self.word(address + 32) == 1,
                'observer published generation-tagged descriptor header')
        owner = self.word(address + 24)
        require(1 < owner < MASK and self.word(address + 80) == 1024 and
                self.word(address + 48) <= 1024 and self.word(address + 1408) == 8,
                'observer User owner/expanded directory bounds')
        version = self.word(address + 8)
        count = self.word(address + 40)
        require((14 if version == 3 else 11) <= count <= 32 and
                self.word(address + 88) == (0x3353415000000020 if version == 3 else 32),
                'observer table count/layout')
        handles = [self.word(address + 128 + i * 8) for i in range(count)]
        require(handles[0] == self.word(address + 56), 'observer tracked root handle')
        tables = [self.frame(owner, table, 2, 1) for table in handles]
        require(len(set(tables)) == len(tables) and self.word(address + 64) == tables[0] and
                self.word(address + 72) == (1 << 63) | (tables[0] >> 12),
                'observer owned root/table identity and SATP')
        directories = []
        for i in range(8):
            frame = self.frame(owner, self.word(address + 1424 + i * 16), 1, 0)
            require(frame == self.word(address + 1432 + i * 16),
                    'observer directory physical/handle binding')
            directories.append(frame)
        require(len(set(directories)) == 8 and
                not set(directories) & set(tables) and address not in directories + tables,
                'observer directory/table/descriptor alias')
        rows = []
        seen = set()
        for i in range(self.word(address + 48)):
            row = directories[i // 128] + (i % 128) * 32
            va = self.word(row)
            require(va % 4096 == 0 and 0x10000 <= va < 0x40000000 and va not in seen,
                    'observer complete live-row VA uniqueness/bounds')
            seen.add(va)
            rows.append((va, self.word(row + 8), self.word(row + 16), self.word(row + 24)))
        return owner, tables, directories, rows

    def owned_bytes(self, handle, address, size):
        require(type(size) is int and 128 <= size <= 32768 and
                type(address) is int and address == LOADED,
                'observer exact owned loaded-buffer/size')
        owner, tables, directories, rows = self.descriptor(handle)
        by_page = {row[0]: row for row in rows}
        result = bytearray()
        mappings = []
        while len(result) < size:
            va = address + len(result)
            page = va & ~4095
            require(page in by_page, 'observer missing owned loaded page')
            _, leaf_handle, tracked, permissions = by_page[page]
            require(permissions == 3, 'observer loaded User RW/NX permission')
            physical = self.frame(owner, leaf_handle, 4, 1)
            require(physical not in tables + directories and
                    sum(1 for row in rows if (row[2] >> 10) * 4096 == physical) == 1,
                    'observer loaded metadata/leaf alias')
            require(tracked == ((physical >> 12) << 10) | 0xd7,
                    'observer exact U/R/W/A/D and NX tracked leaf')
            table = tables[0]
            for level in (2, 1):
                pte = self.word(table + ((va >> (12 + level * 9)) & 511) * 8)
                require(pte >> 54 == 0 and pte & 0x3ff == 1,
                        'observer exact non-leaf Sv39 permissions/reserved bits')
                table = (pte >> 10) * 4096
                require(table in tables, 'observer page walk owns each table')
            pte = self.word(table + ((va >> 12) & 511) * 8)
            require(pte == tracked, 'observer actual/tracked Sv39 leaf equality')
            count = min(size - len(result), 4096 - va % 4096)
            start = physical - RAM_BASE + va % 4096
            result += self.ram[start:start + count]
            mappings.append({'va': va, 'physical': physical + va % 4096,
                             'bytes': count, 'handle': leaf_handle, 'owner': owner,
                             'pte': tracked, 'permissions': permissions})
        require(len(result) == size, 'observer complete exact loaded byte count')
        return bytes(result), mappings


def loaded_ram(snapshot, expected_identity, implementation, source_root):
    """Validate an observational capsule and return its immutable raw RAM view."""
    snapshot = Path(snapshot)
    metadata = json.loads((snapshot / 'snapshot.json').read_text())
    require(metadata.get('schema') == 'lemmasim-session/1' and
            metadata.get('identity') == expected_identity and
            expected_identity.get('runtime') == RUNTIME and
            expected_identity.get('backend') == 'rtl' and
            expected_identity.get('profile') == 'lemma-silicon-dev/0.3.0',
            'observer exact native2 canonical identity')
    inventory_path = Path(source_root) / 'source-inputs.json'
    source_identity = expected_identity['development_guest_source_archive']['inventory']
    require(sha256(inventory_path) == source_identity['sha256'],
            'observer original whole guest source identity')
    inventory = json.loads(inventory_path.read_text())
    require(len(inventory) >= 300 and all(sha256(Path(source_root) / name) == digest
            for name, digest in inventory.items()), 'observer complete original source bytes')
    require(all(inventory.get(name) == digest for name, digest in BOUND_SOURCES.items()),
            'observer exact declared frame/descriptor/installer layout sources')
    files = metadata.get('files')
    require(type(files) is list and len(files) == 1 and files[0]['path'] == 'machine.chk',
            'observer exact native2 container file')
    path = snapshot / 'machine.chk'
    require(path.stat().st_size == files[0]['bytes'] and
            112 <= path.stat().st_size <= 768 << 20 and sha256(path) == files[0]['sha256'],
            'observer complete snapshot size/SHA256')
    raw = path.read_bytes()
    require(raw[:8] == b'LMSSRTL1' and struct.unpack_from('<Q', raw, 8)[0] == 2 and
            raw[16:80].decode('ascii') == implementation, 'observer native2 header identity')
    wn, mn, wc, mc = struct.unpack_from('<4Q', raw, 80)
    require(112 + wn + mn == len(raw) and 0 < mn <= 64 << 20,
            'observer wrapper/model complete length bounds')
    require(crc64(b'123456789') == 0x6c40df5f0b497347 and
            crc64(memoryview(raw)[112:112 + wn]) == wc and
            crc64(memoryview(raw)[112 + wn:]) == mc, 'observer complete wrapper/model CRC64')
    fields = struct.unpack_from('<43Q', raw, 112)
    require(fields[1] == metadata['virtual_cycle'], 'observer snapshot cycle boundary')
    at = 112 + (43 + 3 + 4 + 5) * 8
    for limit in (1048576, 65536):
        size = struct.unpack_from('<Q', raw, at)[0]
        at += 8
        require(size <= limit and at + size <= 112 + wn, 'observer UART/stop string bounds')
        at += size
    require(struct.unpack_from('<Q', raw, at)[0] == RAM_BYTES and
            at + 8 + RAM_BYTES <= 112 + wn, 'observer entire canonical RAM geometry')
    at += 8
    view = OwnedRAM()
    view.ram = memoryview(raw)[at:at + RAM_BYTES]
    receipt = {'snapshot': str(snapshot), 'machine_sha256': files[0]['sha256'],
               'wrapper_crc64': wc, 'model_crc64': mc,
               'ram_crc32_observed': zlib.crc32(view.ram),
               'source_inventory_sha256': source_identity['sha256'], 'cycle': fields[1]}
    return view, receipt


def observe(snapshot, expected_identity, implementation, source_root, installer, package):
    """Compare every owned loaded byte after the actual guest Load succeeded."""
    view, receipt = loaded_ram(snapshot, expected_identity, implementation, source_root)
    compared = compare_loaded(view, installer, package)
    return {'scope': 'read-only after actual cold Load; no restore, journal or mathematical authority',
            **receipt, **compared}


def compare_loaded(view, installer, package):
    expected = Path(package).read_bytes()
    actual, mappings = view.owned_bytes(installer, LOADED, len(expected))
    require(actual == expected, 'observer every loaded package byte equals publisher artifact')
    return {'installer_descriptor': installer, 'bytes': len(actual),
            'loaded_sha256': hashlib.sha256(actual).hexdigest(), 'every_byte_equal': True,
            'owned_mappings': mappings}
