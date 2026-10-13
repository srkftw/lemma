#!/usr/bin/env python3
"""Raw pipe fixture; performs no USB, backing or guest protocol policy."""
import sys,time
mode=sys.argv[1]
if mode=='oversized':print('x'*161,flush=True)
elif mode=='two':sys.stdout.write('FIRST\nSECOND\n');sys.stdout.flush()
elif mode=='nul':sys.stdout.buffer.write(b'A\x00B\n');sys.stdout.buffer.flush()
elif mode=='normal':
    print('FIRST',flush=True)
    if sys.stdin.readline()!='ONE\n':raise SystemExit(3)
    print('SECOND',flush=True)
    if sys.stdin.readline()!='TWO\n':raise SystemExit(4)
    time.sleep(2)
elif mode!='stall':raise SystemExit(2)
time.sleep(2)
