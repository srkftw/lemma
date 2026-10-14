"""Read-only, pinned QEMU private-boundary inspection for Closure lab actors.

Saved is a durable-data condition. This inspector reads the real guest display
queue from a complete checkpoint; it neither renders ink nor writes guest RAM.
The separate exact visible-pixel/cold check remains mandatory.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time

READER_SHA256 = '30cc780aecc662d695bdb32d20715c854bead5172fc2bc45a54456cbe4669d35'

def require(value, message):
    if not value:
        raise ValueError(message)

def inspect_queue(session, reader, label):
    reader = Path(reader).resolve()
    require(reader.is_file() and hashlib.sha256(reader.read_bytes()).hexdigest() == READER_SHA256,
            'Require the exact immutable QEMU11.1.1 migration reader')
    snapshot = session.snapshot(label)
    manifest = json.loads((snapshot / 'snapshot.json').read_text())
    require(manifest['identity']['backend'] == 'qemu' and
            manifest['identity']['profile'] == 'lemma-silicon-dev/0.3.0',
            'Private queue inspector is qualified only for canonical QEMU Closure actors')
    directory = snapshot / 'decoded'
    directory.mkdir(exist_ok=False)
    command = [sys.executable, str(reader), '-f', str(snapshot / 'machine.chk'), '-x']
    (directory / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    with (directory / 'extract.log').open('xb') as log:
        result = subprocess.run(command, cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                                timeout=min(60, session.checker.deadline - time.monotonic()))
    require(result.returncode == 0, 'Pinned QEMU private-boundary decoder failed')
    from check_live_notebook import guest_events
    roots = [row[4] for row in guest_events(session.directory / 'uart-0.bin')
             if row[0] == 0xf1 and row[2] == 1]
    require(len(roots) == 1 and roots[0] % 4096 == 0, 'Actual Notebook address-space root absent')
    ram = directory / 'riscv_virt_board.ram'
    require(ram.is_file() and 0 < ram.stat().st_size <= 512 << 20, 'Unsupported actual RAM block')
    with ram.open('rb') as data:
        def word(physical):
            offset = physical - 0x80000000
            require(0 <= offset <= ram.stat().st_size - 8, 'Sv39 observation escaped actual RAM')
            data.seek(offset)
            return struct.unpack('<Q', data.read(8))[0]
        def translate(virtual):
            table = roots[0]
            for level in (2, 1, 0):
                pte = word(table + ((virtual >> (12 + 9 * level)) & 511) * 8)
                require(pte & 1 and not (pte & 4 and not pte & 2), 'Invalid actual Sv39 PTE')
                base = (pte >> 10) << 12
                if pte & 10:
                    require(base % (1 << (12 + 9 * level)) == 0, 'Misaligned Sv39 superpage')
                    return base | (virtual & ((1 << (12 + 9 * level)) - 1))
                table = base
            raise ValueError('Missing actual Sv39 leaf')
        offsets = (104, 112, 136, 144, 160, 336, 344, 352, 360, 432, 456, 464, 472, 480)
        words = {offset: word(translate(0x20800 + offset)) for offset in offsets}
    quiet = (all(words[offset] == 0 for offset in (104, 112, 136, 144, 160, 432, 456, 480))
             and words[336] == words[344] == 0xffff and words[352] == words[360] == 0
             and words[464] == words[472])
    result = {'schema': 'lemma-closure-display-private-boundary/1', 'quiet': quiet,
              'snapshot': str(snapshot), 'reader_sha256': READER_SHA256,
              'actual_notebook_root': roots[0], 'state_virtual_base': 0x20800,
              'actual_state_words_by_offset': words,
              'scope': 'Read-only actual Sv39/queue inspection; no host rendering or guest writes'}
    (snapshot / 'queue.json').write_text(json.dumps(result, indent=2) + '\n')
    return result
