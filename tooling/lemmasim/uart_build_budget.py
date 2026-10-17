#!/usr/bin/env python3
"""Bound the actual local Nix UART backend compile/link process tree.

Runs inside the builder, so daemon-owned compilers are included. No guest runs.
"""
import ctypes
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time

TIME = 2400
RSS = 6 << 30
AVAILABLE = 2 << 30
DISK = 12 << 30
PAGE = os.sysconf('SC_PAGE_SIZE')


def process(pid):
    try:
        text = Path('/proc', str(pid), 'stat').read_text()
        fields = text[text.rfind(')')+2:].split()
        return (int(fields[1]), int(fields[19]), fields[0],
                int(Path('/proc', str(pid), 'statm').read_text().split()[1])*PAGE)
    except (OSError, ValueError, IndexError):
        return None


tracked = {}


def family():
    rows = {int(p.name): row for p in Path('/proc').iterdir()
            if p.name.isdecimal() and (row := process(int(p.name)))}
    owned = {os.getpid()} | {pid for pid, start in tracked.items()
                            if pid in rows and rows[pid][1] == start}
    while True:
        children = {pid for pid, row in rows.items() if row[0] in owned}
        if children <= owned:
            break
        owned |= children
    for pid in owned - {os.getpid()}:
        if pid in rows:
            tracked[pid] = rows[pid][1]
    return {pid: row for pid, row in rows.items()
            if tracked.get(pid) == row[1]}


def disk():
    total = largest = 0
    for p in Path('.').rglob('*'):
        try:
            if not p.is_symlink() and p.is_file():
                n = p.stat().st_size
                total += n
                largest = max(largest, n)
        except FileNotFoundError:
            pass  # Make may rename/remove an owned temporary between samples.
    return total, largest


def interrupted(signum, frame):
    raise InterruptedError('builder interrupted: '+str(signum))


if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0):
    raise RuntimeError('Linux build child subreaper unavailable')
resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
resource.setrlimit(resource.RLIMIT_FSIZE, (2 << 30, 2 << 30))
signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)
start = time.monotonic()
report = {'status': 'FAIL', 'scope': __doc__, 'peak_tree_rss_bytes': 0,
          'minimum_available_bytes': None, 'peak_source_and_build_bytes': 0,
          'maximum_generated_file_bytes': 0,
          'bounds': {'seconds': TIME, 'tree_rss_bytes': RSS,
                     'minimum_available_bytes': AVAILABLE, 'owned_disk_bytes': DISK,
                     'per_child_address_space_bytes': 2 << 30,
                     'per_file_bytes': 2 << 30, 'compile_jobs': 2}}
p = subprocess.Popen(['make', '-C', 'build', '-j2', 'qemu-system-riscv64',
                      'trace/trace-events-all', 'qemu-gmo'], start_new_session=True)
last_disk = start - 5
try:
    while p.poll() is None:
        now = time.monotonic()
        rss = process(os.getpid())[3] + sum(row[3] for row in family().values()
                                          if row[2] != 'Z')
        available = next(int(line.split()[1])*1024
                         for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))
        report['peak_tree_rss_bytes'] = max(report['peak_tree_rss_bytes'], rss)
        report['minimum_available_bytes'] = min(report['minimum_available_bytes'] or available,
                                                 available)
        if now-last_disk >= 5:
            total, largest = disk()
            report['peak_source_and_build_bytes'] = max(report['peak_source_and_build_bytes'], total)
            report['maximum_generated_file_bytes'] = max(report['maximum_generated_file_bytes'], largest)
            last_disk = now
        if (now-start >= TIME or rss > RSS or available < AVAILABLE or
                report['peak_source_and_build_bytes'] > DISK or
                report['maximum_generated_file_bytes'] > 2 << 30):
            raise RuntimeError('predeclared compile time/RSS/available/disk/file bound')
        time.sleep(.1)
    if p.returncode:
        raise RuntimeError('actual make failed: '+str(p.returncode))
    report['status'] = 'PASS_HOST_UART_BACKEND_COMPILE_ONLY'
except BaseException as error:
    report['error'] = repr(error)
    raise
finally:
    if report['status'].startswith('PASS') and any(row[2] != 'Z' for row in family().values()):
        report['status'] = 'FAIL'
        report['error'] = 'make exited with live owned descendants'
    until = time.monotonic()+30
    while True:
        remaining = family()
        live = {pid: row for pid, row in remaining.items() if row[2] != 'Z'}
        for pid, row in live.items():
            if (current := process(pid)) and current[1] == row[1]:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        if p.poll() is None:
            try:
                p.wait(timeout=.1)
            except subprocess.TimeoutExpired:
                pass
        if p.returncode is not None:
            while True:
                try:
                    reaped, _ = os.waitpid(-1, os.WNOHANG)
                    if not reaped:
                        break
                except ChildProcessError:
                    break
        if not family() or time.monotonic() >= until:
            break
        time.sleep(.05)
    report.update(seconds=time.monotonic()-start, owned_survivors=family())
    if report['owned_survivors'] or report['seconds'] > TIME:
        report['status'] = 'FAIL'
    print('LEMMA_UART_BUILD_RESOURCES '+json.dumps(report, sort_keys=True), flush=True)
if report['status'] != 'PASS_HOST_UART_BACKEND_COMPILE_ONLY':
    raise SystemExit(1)
