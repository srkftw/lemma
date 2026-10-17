#!/usr/bin/env python3
"""Bounded genuine Kernel8/Common12 guest and complete private continuation.

Inputs are immutable native and whole-guest source archives with observed build
and full-audit receipts. The host supplies clocks and raw external peer PIO only.
Guest buffers, payload generation, ownership and PLIC policy execute in Lean.
This qualifies the aligned CommonOFDM DATA prerequisite, not HE/MAC/RF or Wi-Fi6.
"""
from pathlib import Path
import argparse, hashlib, json, os, select, shutil, struct, subprocess, time, re, resource, mmap

def require(value, message):
    if not value:
        raise RuntimeError(str(message))

def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            digest.update(chunk)
    return digest.hexdigest()

def validate_inputs(native, target, rom):
    """Require complete retained source/artifact associations before an owner."""
    compiled = json.loads((native / 'result.json').read_text())
    manifest = json.loads((native / 'build.json').read_text())
    require(compiled['status'] == 'PASS_NATIVE_BUILD_ONLY', 'native build is unqualified')
    inventory = compiled['source_inventory']
    required = {'sim/rtl/lemma_soc.sv', 'sim/rtl/lemma_wifi_ofdm_data.sv',
                'sim/rtl/host/machine_runtime.cpp', 'sim/rtl/host/machine_runtime.wifi.inc.cpp',
                'sim/profiles/lemma-silicon-dev-0.12.0.json'}
    require(required <= set(inventory) and compiled['input_count'] == len(inventory),
            'native consumed-input corpus is incomplete')
    for name, digest in inventory.items():
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts, 'archive path escapes its owner')
        require(file_sha(native / 'consumed-source-root' / relative) == digest, 'native archive bytes differ: ' + name)
    binary = Path(compiled['binary']['path'])
    require(file_sha(binary) == compiled['binary']['sha256'] == manifest['binary_sha256'], 'compiled binary differs')
    require(compiled['runtime_identity'] == manifest['snapshot_identity'], 'native checkpoint identity differs')
    captured = json.loads((target.parent / 'result.json').read_text())
    audit = json.loads((target / 'audit.json').read_text())
    build = json.loads((target / 'build.json').read_text())
    configuration = 'lemmasim-silicon-wifi-common-probe'
    require(captured['status'] == 'PASS_WHOLE_AUDIT_ONLY' and audit['status'] == 'PASS' and build['status'] == 'BUILT',
            'whole target build/audit is unqualified')
    require(audit['configuration'] == build['configuration'] == configuration and audit['stage'] == 'supervisor',
            'target is not the exact Kernel8 supervisor probe')
    required = {'Lemma/Radio/WiFi/Controller.lean', 'Lemma/Radio/WiFi/Queue.lean',
                'Lemma/Platform/Silicon/Development/WiFiCommonProbe.lean', 'scripts/wifi_common.py',
                'tooling/wifi_common-authority.json'}
    require(required <= set(captured['source_inputs']) and captured['source_count'] == len(captured['source_inputs']),
            'target consumed-input corpus is incomplete')
    for name, digest in captured['source_inputs'].items():
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts, 'target archive path escapes its owner')
        require(file_sha(target.parent / 'consumed-source-root' / relative) == digest, 'target archive bytes differ: ' + name)
    require(bool(build['artifacts']), 'empty target artifact corpus')
    for name, digest in build['artifacts'].items():
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts, 'target artifact path escapes its owner')
        require(file_sha(target / relative) == digest, 'target artifact differs: ' + name)
    require(file_sha(target / 'image.elf') == captured['elf_sha256'] == audit['image_sha256'], 'audited ELF differs')
    require(json.loads((target / 'binding.json').read_text())['profile_sha256'] == manifest['profile_sha256'],
            'native and target machine bindings differ')
    require(audit['elf']['boot']['common_pmp']['base'] == 0x10013000 and
            audit['elf']['boot']['common_pmp']['bytes'] == 1024, 'wrong audited PMP aperture')
    bundle = json.loads((rom.parent.parent.parent / 'bundle.json').read_text())
    require(file_sha(rom) == bundle['backends']['rtl']['rom']['sha256'], 'reset ROM association differs')
    return compiled

def verify_cut_image(cut, target, rom, identity):
    """Read-only identity/immutable executable bytes; the backend validates CRC.

    This prevents a retained pure-codec checkpoint from being admitted as the
    Kernel8 queue workload. The entire authoritative file comparison remains
    unmasked; this observation does not modify or migrate its state.
    """
    with cut.open('rb') as stream:
        data = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            require(data[:8] == b'LMSSRTL1' and struct.unpack_from('<Q', data, 8)[0] == 9 and
                    data[16:80].decode() == identity, 'cut backend/version/identity differs')
            wrapper, logical = struct.unpack_from('<QQ', data, 80)
            require(len(data) == 112 + wrapper + logical, 'cut container length differs')
            at = 112 + (43 + 25 + 3 + 3 + 4 + 5) * 8
            for _ in range(2):
                length = struct.unpack_from('<Q', data, at)[0]
                at += 8 + length
            ram_bytes = struct.unpack_from('<Q', data, at)[0]
            at += 8
            require(ram_bytes == 134217728 and at + ram_bytes <= 112 + wrapper, 'cut RAM interval differs')
            word = lambda address: struct.unpack_from('<Q', data, at + address - 0x80000000)[0]
            require([word(0x804e0000 + offset) for offset in (0, 8, 16, 24, 48, 56)] ==
                    [0, 4, 1, 0, 0, 0x3151455546495751] and word(0x80441000) == 5,
                    'cut does not retain the genuine active four-buffer queue')
            for sequence in range(4):
                slot = 0x804e0040 + sequence * 40
                owner, handle, offset, length, seed = [word(slot + index * 8) for index in range(5)]
                record = 0x80401000 + (handle % 8192) * 32
                require((owner, offset, length, seed) == (1, 0, 16, 93) and
                        [word(record + index * 8) for index in range(4)] == [1, 4, 1, handle // 8192],
                        'cut queued owner/purpose/pin/generation differs')
                payload = at + 0x2000000 + (handle % 8192) * 4096
                require(data[payload:payload + 16] == bytes((index * 17) ^ sequence for index in range(16)),
                        'cut queued payload bytes differ')
            elf = (target / 'image.elf').read_bytes()
            require(elf[:6] == b'\x7fELF\x02\x01', 'target is not little-endian ELF64')
            table = struct.unpack_from('<Q', elf, 32)[0]
            stride, amount = struct.unpack_from('<HH', elf, 54)
            require(stride == 56 and amount > 0, 'ELF program-header corpus differs')
            executable = 0
            for index in range(amount):
                kind, flags, offset, _, physical, filesz, _, _ = struct.unpack_from('<IIQQQQQQ', elf, table + index * stride)
                if kind != 1 or not flags & 1:
                    continue
                require(0x80000000 <= physical and physical + filesz <= 0x88000000 and offset + filesz <= len(elf),
                        'executable ELF segment escapes RAM/file')
                require(data[at + physical - 0x80000000:at + physical - 0x80000000 + filesz] == elf[offset:offset + filesz],
                        'cut immutable executable bytes differ from audited Kernel8 image')
                executable += 1
            require(executable >= 2, 'missing genuine M/S executable segments')
            rom_at = at + ram_bytes
            length = struct.unpack_from('<Q', data, rom_at)[0]
            rom_at += 8
            source = rom.read_bytes()
            require(0 < len(source) <= length and data[rom_at:rom_at + len(source)] == source and
                    not any(data[rom_at + len(source):rom_at + length]), 'cut reset ROM differs')
        finally:
            data.close()

def initial_guest(root, native, target, rom, out):
    out.mkdir()
    shutil.copyfile(__file__, out / 'runner.py')

    def sha(p):
        h = hashlib.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda: f.read(1048576), b''):
                h.update(chunk)
        return h.hexdigest()

    def write(p, v):
        p.write_text(json.dumps(v, indent=2) + '\n')
    nb = json.loads((native / 'result.json').read_text())
    nm = json.loads((native / 'build.json').read_text())
    require(nb['status'] == 'PASS_NATIVE_BUILD_ONLY', "qualification invariant failed: nb['status'] == 'PASS_NATIVE_BUILD_ONLY'")
    for name, digest in nb['source_inventory'].items():
        require(sha(native / 'consumed-source-root' / name) == digest, "qualification invariant failed: sha(native / 'consumed-source-root' / name) == digest")
    binary = Path(nb['binary']['path'])
    require(sha(binary) == nb['binary']['sha256'], "qualification invariant failed: sha(binary) == nb['binary']['sha256']")
    tr = json.loads((target.parent / 'result.json').read_text())
    audit = json.loads((target / 'audit.json').read_text())
    build = json.loads((target / 'build.json').read_text())
    require(tr['status'] == 'PASS_WHOLE_AUDIT_ONLY' and audit['status'] == 'PASS' and (build['status'] == 'BUILT'), "qualification invariant failed: tr['status'] == 'PASS_WHOLE_AUDIT_ONLY' and audit['status'] == 'PASS' and (build['status'] == 'BUILT')")
    for name, digest in tr['source_inputs'].items():
        require(sha(target.parent / 'consumed-source-root' / name) == digest, "qualification invariant failed: sha(target.parent / 'consumed-source-root' / name) == digest")
    for name, digest in build['artifacts'].items():
        require(sha(target / name) == digest, 'qualification invariant failed: sha(target / name) == digest')
    require(sha(target / 'image.elf') == tr['elf_sha256'] == audit['image_sha256'], "qualification invariant failed: sha(target / 'image.elf') == tr['elf_sha256'] == audit['image_sha256']")
    require(json.loads((target / 'binding.json').read_text())['profile_sha256'] == nm['profile_sha256'], "qualification invariant failed: json.loads((target / 'binding.json').read_text())['profile_sha256'] == nm['profile_sha256']")
    old = json.loads((rom.parent.parent.parent / 'bundle.json').read_text())
    require(sha(rom) == old['backends']['rtl']['rom']['sha256'], "qualification invariant failed: sha(rom) == old['backends']['rtl']['rom']['sha256']")
    plan = {'schema': 'lemma-common-kernel8-guest/1', 'phase': 'initial genuineS CPU to first active ownedTX/pendingIQ cut', 'clock_bound': 20000000, 'host_bound_seconds': 300, 'next_suffix': {'clock_delta': 1000003, 'host_bound_seconds': 120, 'private_owners_only': True, 'unmasked_complete_state': True, 'peer_policy': 'arm16/seed93 on each real chipTXactive; immutablehead observe literal payload (j*17)^sequence for sequences0..7; ACK only external peer; after real guestRXactive/tag487 stage16literal reverse bytes ff^(j*17), submit seed127'}, 'inputs': {'native': str(native), 'native_manifest': sha(native / 'build.json'), 'runtime_identity': nb['runtime_identity'], 'binary': str(binary), 'binary_sha256': sha(binary), 'target': str(target), 'elf_sha256': sha(target / 'image.elf'), 'audit_sha256': sha(target / 'audit.json'), 'rom': str(rom), 'rom_sha256': sha(rom)}, 'first_raw_events': 'three actual peer PIOwrites at observed firstTXactive boundary:40=16,48=93,56=2; no chip MMIO', 'cut': 'firstTX with >=64 actualchip samples and pendingwire strobe; actual queueactive1/count4/livepin1 verified from readonly RAM in fullcheckpoint', 'scope': 'Common aligned20Msample DATA prerequisite; noHE/acquisition/MAC/RF/Userradio/physical claim'}
    write(out / 'plan.json', plan)
    start = time.monotonic()
    result = {'status': 'FAIL', 'plan_sha256': sha(out / 'plan.json'), 'scope': plan['scope']}
    commands = []
    p = None
    peak = 0
    stderr = (out / 'stderr.log').open('xb')

    def call(line):
        nonlocal peak
        left = 300 - (time.monotonic() - start)
        require(left > 0, 'original global300s bound')
        require(p.poll() is None, 'owner terminated')
        p.stdin.write(line + '\n')
        p.stdin.flush()
        ready, _, _ = select.select([p.stdout], [], [], left)
        require(ready, 'native transport bound')
        raw = p.stdout.readline()
        require(raw, 'native EOF')
        v = json.loads(raw)
        commands.append({'command': line, 'response': v})
        require(v['ok'], v)
        st = Path('/proc') / str(p.pid) / 'status'
        if st.exists():
            m = re.search('^VmHWM:\\s+(\\d+) kB$', st.read_text(), re.M)
            if m:
                peak = max(peak, int(m[1]))
        return v['result']

    def state_ram(path):
        with path.open('rb') as f:
            data = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            require(data[:8] == b'LMSSRTL1' and struct.unpack_from('<Q', data, 8)[0] == 9 and (data[16:80].decode() == nb['runtime_identity']), "qualification invariant failed: data[:8] == b'LMSSRTL1' and struct.unpack_from('<Q', data, 8)[0] == 9 and (data[16:80].decode() == nb['runtime_identity'])")
            wn, mn = struct.unpack_from('<QQ', data, 80)
            require(112 + wn + mn == len(data), 'qualification invariant failed: 112 + wn + mn == len(data)')
            src = (native / 'consumed-source-root/sim/rtl/host/machine_runtime.cpp').read_text()
            fields = re.findall('X\\(([^)]+)\\)', re.search('#define STATE_SCALARS\\(X\\) (.+)', src)[1])
            ble = re.findall('X\\(([^)]+)\\)', re.search('#define BLE_SCALARS\\(X\\) (.+)', src)[1])
            require(len(fields) == 43 and len(ble) == 25, 'qualification invariant failed: len(fields) == 43 and len(ble) == 25')
            at = 112 + (len(fields) + len(ble) + 3 + 3 + 4 + 5) * 8
            length = struct.unpack_from('<Q', data, at)[0]
            at += 8
            uart = bytes(data[at:at + length])
            at += length
            length = struct.unpack_from('<Q', data, at)[0]
            at += 8 + length
            n = struct.unpack_from('<Q', data, at)[0]
            at += 8
            require(n == 134217728, 'qualification invariant failed: n == 134217728')
            q = lambda address: struct.unpack_from('<Q', data, at + address - 2147483648)[0]
            observed = {'head': q(2152595456), 'count': q(2152595464), 'active': q(2152595472), 'completed': q(2152595480), 'poison': q(2152595504), 'magic': q(2152595512), 'owned': q(2151944192), 'available': q(2151678208), 'rx_handle': q(2152595712), 'slots': []}
            for i in range(4):
                slot = 2152595520 + i * 40
                owner, handle, offset, length, seed = [q(slot + j * 8) for j in range(5)]
                idx = handle % 8192
                record = 2151682048 + idx * 32
                rec = [q(record + j * 8) for j in range(4)]
                payload = bytes(data[at + 2181038080 - 2147483648 + idx * 4096:at + 2181038080 - 2147483648 + idx * 4096 + 16])
                observed['slots'].append({'owner': owner, 'handle': handle, 'offset': offset, 'length': length, 'seed': seed, 'record': rec, 'payload_hex': payload.hex()})
            data.close()
            return (observed, uart)
    try:
        argv = [str(binary), '--session', '--image', str(target / 'image.elf'), '--rom', str(rom), '--load', '0x87e00000:' + str(target / 'platform.dtb'), '--descriptor', str(target / 'descriptor.bin'), '--uart-output', str(out / 'uart.bin'), '--quiet-uart', '--trace-limit', '0', '--deadline', '300']
        write(out / 'argv.json', argv)
        p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, text=True, start_new_session=True)
        write(out / 'owner.json', {'pid': p.pid, 'argv': argv})
        state = call('inspect')
        fine = False
        while not state['wifi']['chip']['tx_active']:
            require(not state['finished'] and state['cycle'] < 20000000, state)
            text = (out / 'uart.bin').read_bytes()
            fine = fine or bool(re.search(b'K1 0000000000000485 [0-9a-f ]+\\n', text))
            state = call('run ' + str(16 if fine else min(4096, 20000000 - state['cycle'])))
        at = state['cycle']
        require(state['wifi']['chip_samples'] == 0, 'firstTX sample admitted before peerRX arm')
        rows = [f'{at} wifi-peer-pio 40 16', f'{at} wifi-peer-pio 48 93', f'{at} wifi-peer-pio 56 2']
        write(out / 'first-raw-events.json', rows)
        for row in rows:
            call('inject ' + row)
        while state['wifi']['chip_samples'] < 64 or not state['wifi']['wire_to_peer']:
            state = call('run 1')
            require(state['cycle'] < at + 2000, 'first activeTX cut bound')
        cut = out / 'active-owned-tx.chk'
        call('snapshot ' + str(cut))
        ram, uart = state_ram(cut)
        write(out / 'cut-ram-observation.json', ram)
        (out / 'cut-uart.bin').write_bytes(uart)
        require((ram['head'], ram['count'], ram['active'], ram['completed'], ram['poison'], ram['magic'], ram['owned'], ram['available']) == (0, 4, 1, 0, 0, 3553697813525780305, 5, 8187), ram)
        for seq, r in enumerate(ram['slots']):
            require((r['owner'], r['offset'], r['length'], r['seed'], r['record'][0], r['record'][1], r['record'][2], r['record'][3]) == (1, 0, 16, 93, 1, 4, 1, r['handle'] // 8192) and bytes.fromhex(r['payload_hex']) == bytes((j * 17 ^ seq for j in range(16))), r)
        require(state['privilege'] == 1 and state['wifi']['chip']['tx_active'] == 1 and (state['wifi']['peer']['rx_active'] == 1) and (state['wifi']['wire_to_peer'] == 1), state)
        write(out / 'cut-inspect.json', state)
        result.update(status='PASS_OBSERVED_GENUINE_CPU_CUT', cut=str(cut), cycle=state['cycle'], cut_sha256=sha(cut), cut_bytes=cut.stat().st_size, raw_events=rows, actual_queue_ram=ram, initial_state=state)
    except BaseException as e:
        result['error'] = repr(e)
        raise
    finally:
        if p is not None and p.poll() is None:
            try:
                call('destroy')
                p.wait(timeout=5)
            except BaseException:
                os.killpg(p.pid, 9)
                p.wait(timeout=5)
        stderr.close()
        result['wall_seconds'] = time.monotonic() - start
        result['VmHWM_kib'] = peak
        result['reaped_child_maxrss_kib'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        write(out / 'commands.json', commands)
        result['commands_sha256'] = sha(out / 'commands.json')
        write(out / 'result.json', result)
    return result

def exact_suffix(root, native, observation, out):
    out.mkdir()
    shutil.copyfile(__file__, out / 'runner.py')

    def sha(p):
        h = hashlib.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda: f.read(1048576), b''):
                h.update(chunk)
        return h.hexdigest()

    def write(p, v):
        p.write_text(json.dumps(v, indent=2) + '\n')
    ir = observation
    require(ir['status'] == 'PASS_OBSERVED_GENUINE_CPU_CUT', "qualification invariant failed: ir['status'] == 'PASS_OBSERVED_GENUINE_CPU_CUT'")
    cut = Path(ir['cut'])
    require(sha(cut) == ir['cut_sha256'], "qualification invariant failed: sha(cut) == ir['cut_sha256']")
    nb = json.loads((native / 'result.json').read_text())
    require(nb['status'] == 'PASS_NATIVE_BUILD_ONLY', "qualification invariant failed: nb['status'] == 'PASS_NATIVE_BUILD_ONLY'")
    binary = Path(nb['binary']['path'])
    require(sha(binary) == nb['binary']['sha256'], "qualification invariant failed: sha(binary) == nb['binary']['sha256']")
    for name, digest in nb['source_inventory'].items():
        require(sha(native / 'consumed-source-root' / name) == digest, "qualification invariant failed: sha(native / 'consumed-source-root' / name) == digest")
    begin = ir['cycle']
    end = begin + 1000003
    payloads = [bytes((j * 17 ^ seq for j in range(16))) for seq in range(8)]
    reverse = bytes((255 ^ j * 17 for j in range(16)))
    plan = {'schema': 'lemma-common-kernel8-exact-suffix/1', 'start_cycle': begin, 'end_cycle': end, 'delta': 1000003, 'host_bound_seconds': 120, 'initial_cut': str(cut), 'initial_sha256': sha(cut), 'runtime_identity': nb['runtime_identity'], 'binary_sha256': sha(binary), 'owners': 'two new isolated own-backend forks, original checkpoint unchanged', 'peer_rx': 'first0 alreadyarmed in inheritedstate; arm16/93 when actual chipTXactive for1..7, check each immutable16-byte head against literal expected sequence, then64=2/56=3 rawpeer W1C/headACK', 'peer_tx': 'on actualchipRXactive after all8peerheads, raw19PPIO rows24=16/32=127/16bytes/cmd56=1, seed127; noChipMMIO', 'expected_payloads': [p.hex() for p in payloads], 'reverse_payload': reverse.hex(), 'scope': 'genuine Kernel8ownedqueue/PLIC18/dataI-Q and bounded complete same-backend continuation; noHE/MAC/acquisition/RF/Userradio/physical claim'}
    write(out / 'plan.json', plan)
    start = time.monotonic()
    result = {'status': 'FAIL', 'plan_sha256': sha(out / 'plan.json'), 'scope': plan['scope']}
    commands = []
    owners = []
    peaks = {}
    packets = []
    raw_events = []

    class Owner:

        def __init__(self, name):
            self.name = name
            self.dir = out / name
            self.dir.mkdir()
            self.log = (self.dir / 'stderr.log').open('xb')
            argv = [str(binary), '--session', '--restore', str(cut), '--fork-directory', str(self.dir), '--uart-output', str(self.dir / 'uart.bin'), '--quiet-uart', '--trace-limit', '0', '--deadline', '120']
            self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True, start_new_session=True)
            owners.append(self)
            write(self.dir / 'owner.json', {'pid': self.p.pid, 'argv': argv})
            commands.append({'owner': name, 'argv': argv})

        def call(self, line):
            left = 120 - (time.monotonic() - start)
            require(left > 0, 'original global120s suffix bound')
            require(self.p.poll() is None, 'owner terminated')
            self.p.stdin.write(line + '\n')
            self.p.stdin.flush()
            ready, _, _ = select.select([self.p.stdout], [], [], left)
            require(ready, 'native transport bound')
            raw = self.p.stdout.readline()
            require(raw, 'native EOF see ' + str(self.dir / 'stderr.log'))
            v = json.loads(raw)
            commands.append({'owner': self.name, 'command': line, 'response': v})
            require(v['ok'], v)
            st = Path('/proc') / str(self.p.pid) / 'status'
            if st.exists():
                m = re.search('^VmHWM:\\s+(\\d+) kB$', st.read_text(), re.M)
                if m:
                    peaks[self.name] = max(peaks.get(self.name, 0), int(m[1]))
            return v['result']

        def snap(self, name):
            p = self.dir / (name + '.chk')
            self.call('snapshot ' + str(p))
            return p

        def close(self):
            if self.p.poll() is None:
                self.call('destroy')
                self.p.wait(timeout=5)
            self.log.close()

    def both(line):
        a = parent.call(line)
        b = fork.call(line)
        require(a == b, ('unmasked inspect mismatch', line, a, b))
        return a
    try:
        parent = Owner('private-parent')
        fork = Owner('private-fork')
        state = both('inspect')
        require(state['cycle'] == begin and state['isolated_medium'] is True and (state['wifi']['wire_to_peer'] == 1) and (state['wifi']['chip_samples'] == 64) and (state['wifi']['peer']['rx_active'] == 1), state)
        original_sha = sha(cut)
        last_armed = 0
        reverse_started = False
        finish_seen = False

        def pio(pairs):
            rows = [f"{state['cycle']} wifi-peer-pio {a} {b}" for a, b in pairs]
            raw_events.extend(rows)
            for row in rows:
                both('inject ' + row)
        while state['cycle'] < end:
            chip = state['wifi']['chip']
            peer = state['wifi']['peer']
            require(not state['finished'] and (not chip['fault']) and (not peer['fault']), state)
            if peer['head_valid'] and peer['rx_packets'] > len(packets):
                seq = len(packets)
                require(seq < 8 and peer['rx_packets'] == seq + 1 and (peer['head_length'] == 16) and (bytes.fromhex(peer['head_bytes']) == payloads[seq]), (seq, state))
                packets.append({'sequence': seq, 'cycle': state['cycle'], 'head': dict(peer)})
                pio([(64, 2), (56, 3)])
            if chip['tx_active'] and chip['tx_packets'] > last_armed:
                seq = chip['tx_packets']
                require(seq == last_armed + 1 and seq < 8 and (len(packets) == seq) and (not peer['head_valid']), ('missed aligned RX arm', state, packets))
                pio([(40, 16), (48, 93), (56, 2)])
                last_armed = seq
            if chip['rx_active'] and (not reverse_started):
                require(len(packets) == 8 and chip['tx_packets'] == 8 and (not peer['head_valid']) and (not peer['tx_active']), state)
                pio([(24, 16), (32, 127), *[(256 + 8 * j, b) for j, b in enumerate(reverse)], (56, 1)])
                reverse_started = True
            suffix = (parent.dir / 'uart.bin').read_bytes()
            finish_seen = finish_seen or bool(re.search(b'K1 0000000000000484 0000000000000008 0000000000000001 0000000000000000 0000000000000008\\n', suffix))
            amount = end - state['cycle'] if finish_seen else min(16, end - state['cycle'])
            state = both('run ' + str(amount))
        require(len(packets) == 8 and reverse_started and finish_seen and (state['cycle'] == end), state)
        require((state['wifi']['chip_samples'], state['wifi']['peer_samples'], state['wifi']['peer_pio_beats']) == (5120, 640, 59), state)
        require((state['wifi']['chip']['tx_packets'], state['wifi']['chip']['rx_packets'], state['wifi']['peer']['tx_packets'], state['wifi']['peer']['rx_packets']) == (8, 1, 1, 8), state)
        require(state['wifi']['chip']['head_valid'] == 0 and state['wifi']['peer']['head_valid'] == 0 and (state['wifi']['chip']['events'] == 0) and (state['wifi']['peer']['events'] == 1), state)
        pa = parent.snap('complete-final')
        pb = fork.snap('complete-final')
        require(sha(pa) == sha(pb) and pa.stat().st_size == pb.stat().st_size, 'complete authoritative checkpoint mismatch')
        require(sha(cut) == original_sha, 'parent checkpoint changed')
        require((parent.dir / 'uart.bin').read_bytes() == (fork.dir / 'uart.bin').read_bytes(), 'external UART suffix differs')
        with pa.open('rb') as f:
            d = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            require(d[:8] == b'LMSSRTL1' and struct.unpack_from('<Q', d, 8)[0] == 9 and (d[16:80].decode() == nb['runtime_identity']), "qualification invariant failed: d[:8] == b'LMSSRTL1' and struct.unpack_from('<Q', d, 8)[0] == 9 and (d[16:80].decode() == nb['runtime_identity'])")
            wn, mn = struct.unpack_from('<QQ', d, 80)
            require(len(d) == 112 + wn + mn, 'qualification invariant failed: len(d) == 112 + wn + mn')
            at = 112 + (43 + 25 + 3 + 3 + 4 + 5) * 8
            n = struct.unpack_from('<Q', d, at)[0]
            at += 8
            uart = bytes(d[at:at + n])
            at += n
            n = struct.unpack_from('<Q', d, at)[0]
            at += 8 + n
            n = struct.unpack_from('<Q', d, at)[0]
            at += 8
            require(n == 134217728, 'qualification invariant failed: n == 134217728')
            q = lambda address: struct.unpack_from('<Q', d, at + address - 2147483648)[0]
            ram = {'head': q(2152595456), 'count': q(2152595464), 'active': q(2152595472), 'completed': q(2152595480), 'poison': q(2152595504), 'magic': q(2152595512), 'owned': q(2151944192), 'available': q(2151678208), 'received': q(2152595720), 'rx_handle': q(2152595712)}
            require((ram['head'], ram['count'], ram['active'], ram['completed'], ram['poison'], ram['owned'], ram['available'], ram['received']) == (0, 0, 0, 8, 0, 0, 8192, 1), ram)
            for i in range(8192):
                require(q(2151682048 + i * 32) == 0 and q(2151682048 + i * 32 + 16) == 0, ('retained owner/pin', i))
            rx = ram['rx_handle'] % 8192
            copied = bytes(d[at + 2181038080 - 2147483648 + rx * 4096:at + 2181038080 - 2147483648 + rx * 4096 + 16])
            require(copied == reverse, 'owned RX RAM differs')
            ram['rx_payload_hex'] = copied.hex()
            d.close()
        records = [[int(v, 16) for v in m] for m in re.findall(b'K1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\\n', uart)]
        require([r[1] for r in records if r[0] == 1153] == list(range(8)), 'qualification invariant failed: [r[1] for r in records if r[0] == 1153] == list(range(8))')
        require([r[1] for r in records if r[0] == 1154] == list(range(1, 9)), 'qualification invariant failed: [r[1] for r in records if r[0] == 1154] == list(range(1, 9))')
        require([r[1:] for r in records if r[0] == 1158] == [[18, 1, 0, 0]] * 8 + [[18, 2, 0, 0]], 'qualification invariant failed: [r[1:] for r in records if r[0] == 1158] == [[18, 1, 0, 0]] * 8 + [[18, 2, 0, 0]]')
        require([r[1:] for r in records if r[0] == 1156] == [[8, 1, 0, 8]], 'qualification invariant failed: [r[1:] for r in records if r[0] == 1156] == [[8, 1, 0, 8]]')
        require([r[1:] for r in records if r[0] == 1159] == [[16, 127, 8, 0]], 'qualification invariant failed: [r[1:] for r in records if r[0] == 1159] == [[16, 127, 8, 0]]')
        (out / 'complete-uart.bin').write_bytes(uart)
        write(out / 'decoded-heads.json', packets)
        write(out / 'final-ram-observation.json', ram)
        write(out / 'final-inspect.json', state)
        result.update(status='PASS_GENUINE_QUEUE_IRQ_SAMPLES_EXACT_SUFFIX', end_cycle=end, start_cycle=begin, delta=1000003, full_checkpoint_sha256=sha(pa), checkpoint_bytes=pa.stat().st_size, original_checkpoint_unchanged=True, whole_RAM_owner_pin_scan=8192, peer_payloads=[p['head']['head_bytes'] for p in packets], raw_pio_events=len(raw_events), records=records, final_ram=ram, final=state)
    except BaseException as e:
        result['error'] = repr(e)
        raise
    finally:
        for owner in owners:
            if owner.p.poll() is None:
                try:
                    owner.close()
                except BaseException:
                    os.killpg(owner.p.pid, 9)
                    owner.p.wait(timeout=5)
                    owner.log.close()
        result['wall_seconds'] = time.monotonic() - start
        result['VmHWM_kib_by_owner'] = peaks
        result['reaped_children_maxrss_kib'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        write(out / 'raw-events.json', raw_events)
        write(out / 'commands.json', commands)
        result['commands_sha256'] = sha(out / 'commands.json')
        write(out / 'result.json', result)
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--native-build', type=Path, required=True)
    p.add_argument('--target-capture', type=Path, required=True)
    p.add_argument('--rom-bundle', type=Path, required=True)
    p.add_argument('--work-dir', type=Path, required=True)
    p.add_argument('--resume-observation', type=Path)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = a.work_dir.resolve()
    if not out.is_relative_to(root / 'build') or out.exists():
        p.error('an unused build subdirectory is required')
    native = a.native_build.resolve()
    target = a.target_capture.resolve() / 'target'
    rom = a.rom_bundle.resolve() / 'runtime/rtl/boot.bin'
    for directory in (native, target.parent, rom.parent):
        if not directory.is_relative_to(root / 'build'):
            p.error('immutable inputs must be owned build artifacts')
    out.mkdir()
    began = time.monotonic()
    receipt = {'status': 'FAIL', 'scope': 'genuine Common aligned DATA queue/PLIC/sample and same-backend continuation; no fullWi-Fi6 claim'}
    try:
        compiled = validate_inputs(native, target, rom)
        if a.resume_observation:
            observation = json.loads(a.resume_observation.read_text())
            require(observation.get('status') == 'PASS_OBSERVED_GENUINE_CPU_CUT', 'resume requires independently qualified actual cut')
        else:
            observation = initial_guest(root, native, target, rom, out / 'initial')
        require(0 < observation['cycle'] <= 20000000, 'resume cut escaped the original clock bound')
        cut = Path(observation['cut']).resolve()
        require(cut.is_relative_to(root / 'build') and file_sha(cut) == observation['cut_sha256'],
                'resume cut path/bytes differ')
        verify_cut_image(cut, target, rom, compiled['runtime_identity'])
        suffix = exact_suffix(root, native, observation, out / 'continuation')
        receipt.update(status=suffix['status'], initial_cycle=observation['cycle'], end_cycle=suffix['end_cycle'], initial_observation=a.resume_observation and str(a.resume_observation), suffix_result='continuation/result.json')
    except BaseException as e:
        receipt['error'] = repr(e)
        raise
    finally:
        receipt['wall_seconds'] = time.monotonic() - began
        (out / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt['status'], receipt['wall_seconds'])
if __name__ == '__main__':
    main()
