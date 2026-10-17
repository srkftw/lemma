#!/usr/bin/env python3
"""Only raw host byte transport and filesystem primitives; no peer protocol policy."""
import argparse
import os
from pathlib import Path
import socket
import struct

MAX_WIRE = 1048576 + 72

def read_exact(stream, size):
    result = bytearray()
    while len(result) < size:
        part = stream.recv(size-len(result))
        if not part:
            raise OSError('disconnected raw transport')
        result.extend(part)
    return bytes(result)

def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='op',required=True)
    q=s.add_parser('sync');q.add_argument('path',type=Path)
    q=s.add_parser('sync-directory');q.add_argument('path',type=Path)
    q=s.add_parser('truncate');q.add_argument('path',type=Path);q.add_argument('length',type=int)
    q=s.add_parser('replace');q.add_argument('source',type=Path);q.add_argument('destination',type=Path)
    q=s.add_parser('pread');q.add_argument('path',type=Path);q.add_argument('offset',type=int);q.add_argument('length',type=int)
    q=s.add_parser('wire');q.add_argument('socket');q.add_argument('hex')
    a=p.parse_args()
    if a.op in ('sync','sync-directory'):
        fd=os.open(a.path,os.O_RDONLY|(os.O_DIRECTORY if a.op=='sync-directory' else 0))
        try:os.fsync(fd)
        finally:os.close(fd)
    elif a.op=='truncate':
        if not 8<=a.length<=64*1024*1024:raise ValueError('raw truncation bound')
        with a.path.open('r+b') as stream:stream.truncate(a.length);stream.flush();os.fsync(stream.fileno())
    elif a.op=='replace':
        with a.source.open('rb') as stream:os.fsync(stream.fileno())
        os.replace(a.source,a.destination)
        fd=os.open(a.destination.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    elif a.op=='pread':
        if not 0<=a.offset<=268435456 or not 1<=a.length<=1048576 or a.offset+a.length>268435456:raise ValueError('raw read bound')
        fd=os.open(a.path,os.O_RDONLY)
        try:data=os.pread(fd,a.length,a.offset)
        finally:os.close(fd)
        if len(data)!=a.length:raise OSError('short raw read')
        print(data.hex())
    else:
        if len(a.hex)>2*MAX_WIRE:raise ValueError('raw wire bound')
        wire=bytes.fromhex(a.hex)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as stream:
            stream.settimeout(2);stream.connect(a.socket)
            stream.sendall(struct.pack('<I',len(wire))+wire)
            size=struct.unpack('<I',read_exact(stream,4))[0]
            if not 1<=size<=MAX_WIRE:raise ValueError('raw response bound')
            print(read_exact(stream,size).hex())
if __name__=='__main__':main()
