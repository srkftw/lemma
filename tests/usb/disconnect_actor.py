#!/usr/bin/env python3
"""Raw process boundary fixture, with no USB or storage protocol policy."""
import sys,time
mode=sys.argv[1]
if mode=='closed':raise SystemExit(0)
print('USBHOST/2 PACKET_BYTES_DEV',flush=True)
if sys.stdin.readline()!='OPEN\n':raise SystemExit(3)
print('RESET 5000000',flush=True)
if sys.stdin.readline()!='RESET_DONE\n':raise SystemExit(4)
print('RECV',flush=True)
time.sleep(.1 if mode=='pending-exit' else 30)
