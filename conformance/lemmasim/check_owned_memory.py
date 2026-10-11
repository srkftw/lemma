"""Read-only observations of the actual LemmaSim allocator and owned registries.

This is an evidence observer, not a guest allocator/recovery implementation. It
never pauses the CPU or writes guest memory. Periodic reads rotate one64 KiB
ownership slice; ready/final reads retain all four slices and bounded descriptor
pages. Maximum observed allocation is not a whole-run high-water proof.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import threading
import time

COUNT = 8192
FRAME_BYTES = 4096
POOL = 0x82000000
CONFIGURATION = 0x804006A0
ACCOUNTING = 0x80400100
RECORDS = 0x80401000
TASK_HANDLE = 0x80400728
ROW_BYTES = 32
READ_LIMIT = 65536
PERIOD_SECONDS = 30
MASK = (1 << 64) - 1
ADDRESS_SPACE_MAGIC = 0x31534150414D454C


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_configuration(configuration: tuple[int, ...]) -> None:
    if configuration != (8192, 8192, 4):
        raise ValueError('unknown observed allocator count/quota/stack configuration')


def decode_rows(data: bytes, *, amount: int = COUNT) -> list[tuple[int, ...]]:
    if len(data) != amount * ROW_BYTES or not 0 < amount <= COUNT:
        raise ValueError('incomplete or oversized ownership row observation')
    rows = list(struct.iter_unpack('<4Q', data))
    for owner, purpose, pins, generation in rows:
        if owner in (0, MASK):
            if purpose or pins:
                raise ValueError('free/retired frame has a purpose or live mapping count')
        elif not (1 <= purpose <= 5 and 0 < generation <= MASK // COUNT):
            raise ValueError('live frame has invalid purpose/generation')
    return rows


def check_accounting(configuration: tuple[int, ...], before: int, after: int,
                     data: bytes) -> dict:
    check_configuration(configuration)
    if not 0 <= before <= COUNT or not 0 <= after <= COUNT:
        raise ValueError('observed free count is outside the configured pool')
    rows = decode_rows(data)
    owners = Counter(row[0] for row in rows)
    if before != after or before != owners.get(0, 0):
        raise ValueError('ownership rows contradict observed free accounting; snapshot may cross publication')
    live = [row for row in rows if row[0] not in (0, MASK)]
    return {'free_frames': before, 'allocated_or_retired_frames': COUNT - before,
            'allocated_or_retired_bytes': (COUNT - before) * FRAME_BYTES,
            'live_owned_frames': len(live), 'retired_frames': owners.get(MASK, 0),
            'owner_frame_counts': {str(key): value for key, value in owners.items()},
            'owned_purpose_frame_counts': {str(key): value for key, value in Counter(row[1] for row in live).items()},
            'owned_mapping_count': sum(row[2] for row in live), 'accounting_consistent': True}


def resolve(rows: list[tuple[int, ...]], handle: int, owner: int, purpose: int,
            *, unpinned: bool = False) -> int:
    if not handle or len(rows) != COUNT:
        raise ValueError('invalid handle/ownership observation')
    index, generation = handle % COUNT, handle // COUNT
    actual_owner, actual_purpose, pins, actual_generation = rows[index]
    if not generation or (actual_owner, actual_purpose, actual_generation) != (owner, purpose, generation):
        raise ValueError('observed handle has stale generation, owner, or purpose')
    if unpinned and pins:
        raise ValueError('kernel descriptor/registry metadata frame is mapped')
    return POOL + index * FRAME_BYTES


def descriptor_context(data: bytes, handle: int, rows: list[tuple[int, ...]]) -> dict:
    if len(data) != FRAME_BYTES:
        raise ValueError('incomplete descriptor observation')
    word = lambda offset: struct.unpack_from('<Q', data, offset)[0]
    owner = word(24)
    if (word(0), word(8), word(16), word(32)) != (ADDRESS_SPACE_MAGIC, 2, handle, 1):
        raise ValueError('unknown/unpublished address-space descriptor')
    if not 1 < owner < MASK or not 13 <= word(40) <= 32 or word(48) > 1024:
        raise ValueError('descriptor owner/table/leaf count is out of bounds')
    if (word(80), word(88), word(1408)) != (1024, 32, 8):
        raise ValueError('expanded registry capacity/count differs')
    root = resolve(rows, word(56), owner, 2)
    if word(56) != word(128) or word(64) != root or word(72) != (1 << 63) | (root >> 12):
        raise ValueError('descriptor root/translation contradicts owned root')
    registry = []
    for index in range(8):
        registry_handle, physical = word(1424 + index * 16), word(1432 + index * 16)
        if physical != resolve(rows, registry_handle, owner, 1, unpinned=True):
            raise ValueError('registry directory physical address contradicts its owned handle')
        registry.append({'handle': registry_handle, 'physical': physical})
    if len({entry['physical'] for entry in registry}) != 8:
        raise ValueError('duplicated registry page')
    return {'handle': handle, 'physical': resolve(rows, handle, 1, 1, unpinned=True),
            'owner': owner, 'table_frames': word(40), 'mapped_leaf_rows': word(48),
            'leaf_capacity': word(80), 'root': root, 'registry': registry}


def check_leaf_registry(context: dict, pages: list[bytes], rows: list[tuple[int, ...]]) -> dict:
    if len(pages) != 8 or any(len(page) != FRAME_BYTES for page in pages):
        raise ValueError('incomplete expanded leaf registry observation')
    entries = list(struct.iter_unpack('<4Q', b''.join(pages)))[:context['mapped_leaf_rows']]
    addresses = set()
    purposes = Counter()
    # Leaf registry v2 words are VA, owned handle, exact PTE, permissions.
    for va, handle, recorded, permissions in entries:
        if not 0x10000 <= va < 0x40000000 or va % FRAME_BYTES or va in addresses:
            raise ValueError('invalid/duplicated live user leaf VA')
        addresses.add(va)
        owner, purpose, pins, generation = rows[handle % COUNT]
        allowed = permissions == 5 if purpose == 3 else permissions in (1, 3) if purpose == 4 else permissions == 3 if purpose == 5 else False
        if not allowed or not pins:
            raise ValueError('user leaf purpose/permissions/pins differ')
        physical = resolve(rows, handle, context['owner'], purpose)
        expected = (physical >> 12) << 10 | 0x51 | permissions << 1 | (0x80 if permissions & 2 else 0)
        if recorded != expected:
            raise ValueError('registry PTE differs from its owned frame/permissions')
        purposes[purpose] += 1
    return {'observed_live_leaf_rows': len(entries), 'live_leaf_purposes': dict(purposes),
            'registry_pages_sha256': [hashlib.sha256(page).hexdigest() for page in pages],
            'scope': 'owned registry metadata cross-check; not an independent whole Sv39 walk proof'}


def source_path_observations(metadata: dict) -> dict:
    """Selected real pre-optimization call closures, not a whole-program proof."""
    directory = Path(metadata['notebook']['path']).parent / 'users/notebook'
    unit_path, ir_path = directory / 'unit.json', directory / 'program.ll'
    unit, ir = json.loads(unit_path.read_text()), ir_path.read_text()
    names = {row['symbol']: re.sub(r'^_private\..*?\.[0-9]+\.', '', row['source']) for row in unit['functions']}
    sections = re.split(r'(?=^define )', ir, flags=re.M)
    graph = {}
    for section in sections:
        match = re.match(r'define [^\n]*@(\w+)\(', section)
        if match:
            graph[match[1]] = set(re.findall(r'\bcall [^\n]*?@(\w+)\(', section)) & names.keys()
    by_source = {source: symbol for symbol, source in names.items()}
    forbidden = {'Lemma.Applications.Notebook.loadPage', 'Lemma.Applications.Notebook.redraw',
                 'Lemma.Applications.Notebook.renderLoadedChunk', 'Lemma.User.Syscall.allocatePage'}
    observations = []
    for source in ('Lemma.Applications.Notebook.appendRaw', 'Lemma.Applications.Notebook.renderPair'):
        if source not in by_source:
            raise ValueError('selected normal sample source is absent from the genuine guest closure')
        pending, seen = [by_source[source]], set()
        while pending:
            symbol = pending.pop()
            if symbol in seen:
                continue
            if symbol not in graph:
                raise ValueError('selected normal sample declaration has no emitted definition')
            seen.add(symbol)
            pending.extend(graph.get(symbol, ()))
        reached = {names[symbol] for symbol in seen}
        if reached & forbidden:
            raise ValueError('normal sample closure reaches page-history loading or allocation')
        observations.append({'source': source, 'reachable_functions': len(seen),
                             'forbidden_page_load_allocation_sources_absent': sorted(forbidden)})
    return {'scope': 'selected normal raw append/raster call closures only; toolbar/page-load behavior is separate',
            'unit_sha256': sha(unit_path), 'pre_ir_sha256': sha(ir_path), 'observations': observations,
            'address_space_lookup_limit': 1024, 'lookup_limit_is_not_document_history': True}


class Observation:
    def __init__(self, sim, run: Path, output: Path, metadata: dict):
        self.sim, self.run, self.output, self.metadata = sim, Path(run), Path(output), metadata
        self.output.mkdir(exist_ok=False)
        self.original_qmp = sim.qmp
        self.observer_sha256 = sha(Path(__file__))
        self.started = time.monotonic()
        self.samples, self.errors = [], []
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.last_periodic = 0.0
        self.read_serial = 0
        self.slice_index = 0
        self.final = False
        self.socket = None
        self.source_paths = source_path_observations(metadata)

    def read(self, address: int, size: int, label: str) -> bytes:
        if not 0 < size <= READ_LIMIT:
            raise ValueError('physical observer read exceeds64 KiB')
        self.read_serial += 1
        path = self.output / f'{self.read_serial:04d}-{label}.bin'
        self.original_qmp(self.socket, 'pmemsave', {'val': address, 'size': size, 'filename': str(path.resolve())})
        data = path.read_bytes()
        if len(data) != size:
            raise ValueError('incomplete actual physical RAM read')
        return data

    def words(self, address: int, amount: int, label: str) -> tuple[int, ...]:
        return struct.unpack('<' + 'Q' * amount, self.read(address, amount * 8, label))

    def snapshot(self, label: str, *, full: bool) -> None:
        with self.lock:
            try:
                config = self.words(CONFIGURATION, 3, 'configuration')
                check_configuration(config)
                before = self.words(ACCOUNTING, 1, 'free-before')[0]
                ticks = self.words(0x0200BFF8, 1, 'guest-clock')[0]
                if not ticks or self.samples and ticks < self.samples[-1]['guest_timer_ticks']:
                    raise ValueError('missing/backward observed monotonic guest time')
                if not 0 <= before <= COUNT:
                    raise ValueError('free count outside observed pool')
                start = 0 if full else self.slice_index * READ_LIMIT
                data = b''.join(self.read(RECORDS + offset, READ_LIMIT, 'ownership')
                                for offset in range(start, COUNT * ROW_BYTES if full else start + READ_LIMIT, READ_LIMIT))
                sample = {'label': label, 'wall_seconds': time.monotonic() - self.started,
                          'guest_timer_ticks': ticks, 'clock_hz': 10000000, 'configuration': list(config),
                          'free_frames': before, 'observed_allocated_or_retired_bytes': (COUNT - before) * FRAME_BYTES,
                          'ownership_rows_sha256': hashlib.sha256(data).hexdigest(),
                          'ownership_slice_bytes': len(data), 'ownership_slice_start_index': start // ROW_BYTES}
                if full:
                    rows = decode_rows(data)
                    table_handle = self.words(TASK_HANDLE, 1, 'task-table-handle')[0]
                    table = self.read(resolve(rows, table_handle, 1, 1, unpinned=True), FRAME_BYTES, 'task-table')
                    descriptors = []
                    for index in range(8):
                        handle, state = struct.unpack_from('<2Q', table, index * 512)
                        if not state:
                            if handle:
                                raise ValueError('free task row retains a descriptor')
                            continue
                        if state not in (2, 3, 4, 5):
                            raise ValueError('snapshot crosses task construction/teardown')
                        physical = resolve(rows, handle, 1, 1, unpinned=True)
                        context = descriptor_context(self.read(physical, FRAME_BYTES, 'descriptor'), handle, rows)
                        context['task_state'] = state
                        pages = [self.read(entry['physical'], FRAME_BYTES, 'leaf-registry')
                                 for entry in context['registry']]
                        context.update(check_leaf_registry(context, pages, rows))
                        descriptors.append(context)
                    if not descriptors:
                        raise ValueError('ready workload contains no live owned address spaces')
                    sample['address_spaces'] = descriptors
                    after = self.words(ACCOUNTING, 1, 'free-after')[0]
                    sample.update(check_accounting(config, before, after, data))
                else:
                    decode_rows(data, amount=READ_LIMIT // ROW_BYTES)
                    sample['slice_scope'] = 'one rotating ownership slice; no whole-array consistency claim'
                    self.slice_index = (self.slice_index + 1) % 4
                self.samples.append(sample)
                self.last_periodic = time.monotonic()
                if label == 'final-before-process-reap':
                    self.final = True
            except Exception as error:
                self.errors.append({'label': label, 'wall_seconds': time.monotonic() - self.started, 'error': str(error)})
                self.stop.set()
            self.write()

    def write(self, terminal: bool = False) -> dict:
        ready = any(row['label'] in ('guest-ready', 'guest-ready-at-final-boundary') for row in self.samples)
        result = {'schema_version': 1, 'status': ('OBSERVED' if ready and self.final and not self.errors else 'FAIL') if terminal else 'OBSERVING',
                  'scope': 'actual readonly allocator observations; observed maximum is not a whole-run high-water proof or whole-program memory proof',
                  'observer_sha256': self.observer_sha256, 'guest_sha256': self.metadata['notebook']['sha256'],
                  'pool': [POOL, POOL + COUNT * FRAME_BYTES], 'frame_bytes': FRAME_BYTES,
                  'maximum_read_bytes': READ_LIMIT, 'periodic_seconds': PERIOD_SECONDS,
                  'samples': self.samples, 'errors': self.errors, 'final_before_reap_observed': self.final,
                  'min_observed_free_frames': min((row['free_frames'] for row in self.samples), default=None),
                  'max_observed_allocated_or_retired_bytes': max((row['observed_allocated_or_retired_bytes'] for row in self.samples), default=None),
                  'selected_source_path_review': self.source_paths}
        temporary = self.output / 'result.new.json'
        temporary.write_text(json.dumps(result, indent=2) + '\n')
        temporary.replace(self.output / 'result.json')
        return result

    def monitor(self) -> None:
        process, serial = self.run / 'process.json', self.run / 'serial.bin'
        while not self.stop.wait(1):
            try:
                if self.socket is None:
                    if not process.exists():
                        continue
                    self.socket = Path(json.loads(process.read_text())['qmp_socket'])
                if not self.socket.exists() or not serial.exists():
                    continue
                if not self.samples:
                    if not self.sim.document_observations(serial).get('ready'):
                        continue
                    self.snapshot('guest-ready', full=True)
                elif time.monotonic() - self.last_periodic >= PERIOD_SECONDS:
                    self.snapshot('periodic', full=False)
            except Exception as error:
                with self.lock:
                    self.errors.append({'label': 'monitor', 'error': str(error)})
                    self.write()
                self.stop.set()

    def qmp(self, socket, command, arguments=None):
        if command == 'quit':
            self.socket = Path(socket)
            # A short cold boot may reach Ready and quit between monitor turns.
            # Read its actual report and retain a separately labelled physical
            # snapshot before the final snapshot instead of inventing an early
            # Ready observation or silently accepting a missing observation.
            if not any(row['label'] in ('guest-ready', 'guest-ready-at-final-boundary') for row in self.samples):
                if self.sim.document_observations(self.run / 'serial.bin').get('ready'):
                    self.snapshot('guest-ready-at-final-boundary', full=True)
            self.snapshot('final-before-process-reap', full=True)
        return self.original_qmp(socket, command, arguments)

    def __enter__(self):
        self.sim.qmp = self.qmp
        self.thread = threading.Thread(target=self.monitor, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(5)
        self.sim.qmp = self.original_qmp
        if self.thread.is_alive():
            self.errors.append({'label': 'monitor-shutdown', 'error': 'readonly observer did not stop within5s'})
        self.write(terminal=True)

    def require_observed(self) -> dict:
        result = self.write(terminal=True)
        if result['status'] != 'OBSERVED':
            raise ValueError('workload lacks complete consistent ready/final owned-memory observations')
        return result
