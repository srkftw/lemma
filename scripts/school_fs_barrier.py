#!/usr/bin/env python3
"""Narrow hosted OS primitive: fsync one regular file or directory.

Lean chooses the paths, ordering and commit boundary. This helper has no school
records, JSON, policy, recovery, rename or acknowledgement implementation.
"""
import argparse
import json
import os
import stat


def sync_path(kind, path):
    if kind not in {"file", "directory"} or not isinstance(path, str):
        raise ValueError("unsupported barrier path or kind")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    if kind == "directory":
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        valid = stat.S_ISREG(info.st_mode) if kind == "file" else stat.S_ISDIR(info.st_mode)
        if not valid:
            raise ValueError("barrier requires the declared regular file or directory")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("file", "directory", "batch"))
    parser.add_argument("path", help="one path, or a bounded JSON array of Lean-selected kind/path pairs")
    args = parser.parse_args()
    if args.kind == "batch":
        if len(args.path.encode()) > 1048576:
            raise ValueError("barrier batch exceeds byte bound")
        entries = json.loads(args.path)
        if not isinstance(entries, list) or not 1 <= len(entries) <= 1024:
            raise ValueError("barrier batch must have 1..1024 entries")
        for entry in entries:
            if not isinstance(entry, list) or len(entry) != 2:
                raise ValueError("barrier entry must be a kind/path pair")
            sync_path(*entry)
    else:
        sync_path(args.kind, args.path)


if __name__ == "__main__":
    main()
