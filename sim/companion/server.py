#!/usr/bin/env python3
"""Same-owner raw Unix byte transport for the separate hosted-Lean peer.

No opcode, transaction, receipt, checksum or document interpretation occurs
here. Drop/exit controls select completed raw response ordinals for experiments.
"""
import argparse
import os
from pathlib import Path
import select
import signal
import socket
import struct
import subprocess
import sys

MAX_WIRE = 1048576 + 72

def recv_exact(stream, size):
    out = bytearray()
    while len(out) < size:
        part = stream.recv(size-len(out))
        if not part:
            raise OSError('raw transport disconnected')
        out.extend(part)
    return bytes(out)

def read_line(stream, timeout=10):
    if not select.select([stream], [], [], timeout)[0]:
        raise OSError('hosted peer did not return a bounded raw response')
    line = stream.readline(2*MAX_WIRE+2)
    if not line.endswith(b'\n') or len(line) > 2*MAX_WIRE+1:
        raise OSError('hosted peer output boundary')
    return bytes.fromhex(line.decode().strip())

def serve(binary, directory, base, writer, helper, path, drop_reply=0, exit_after_reply=0):
    path = Path(path).absolute()
    if path.exists():
        raise ValueError('raw socket already exists; inspect its owner before removing it')
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    child = subprocess.Popen([str(binary),str(directory),str(base),str(writer),str(helper)],
                             stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=8192)
    own_socket = False
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
            listener.bind(str(path)); own_socket = True
            os.chmod(path,0o600); listener.listen(8); listener.settimeout(1)
            print('RAW_PEER_READY '+str(path),flush=True)
            replies = 0
            while not stopped:
                if child.poll() is not None:
                    raise OSError('hosted Lean peer exited: '+str(child.returncode))
                try:
                    stream,_ = listener.accept()
                except socket.timeout:
                    continue
                with stream:
                    stream.settimeout(2)
                    if hasattr(socket,'SO_PEERCRED'):
                        _,uid,_ = struct.unpack('3i',stream.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                        if uid != os.getuid():
                            continue
                    try:
                        n = struct.unpack('<I',recv_exact(stream,4))[0]
                        if not 1 <= n <= MAX_WIRE:
                            raise ValueError('raw request resource bound')
                        raw = recv_exact(stream,n)
                        child.stdin.write(raw.hex().encode()+b'\n'); child.stdin.flush()
                        reply = read_line(child.stdout)
                        if not 1 <= len(reply) <= MAX_WIRE:
                            raise ValueError('raw response resource bound')
                        replies += 1
                        if replies != drop_reply:
                            stream.sendall(struct.pack('<I',len(reply))+reply)
                        if replies == exit_after_reply:
                            stopped = True
                    except (OSError,ValueError) as error:
                        print('raw transport error: '+str(error),file=sys.stderr,flush=True)
            return 0
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=3)
        else:
            child.wait(timeout=3)
        if own_socket:
            path.unlink(missing_ok=True)

def main():
    p=argparse.ArgumentParser()
    for name in ('binary','directory','base','helper','socket'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--writer',type=int,required=True)
    p.add_argument('--drop-reply',type=int,default=0)
    p.add_argument('--exit-after-reply',type=int,default=0)
    a=p.parse_args()
    return serve(a.binary,a.directory,a.base,a.writer,a.helper,a.socket,a.drop_reply,a.exit_after_reply)

if __name__=='__main__':
    raise SystemExit(main())
