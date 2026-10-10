#!/usr/bin/env python3
"""Compare retained observations from a real cold guest reopening."""
import argparse
import json
import struct
from pathlib import Path

from check_notebook_workflow import check_cold


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before-disk', 'after-disk', 'before-visible', 'after-visible',
                 'cold-serial', 'cold-devices', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('refusing to overwrite retained cold comparison')
    try:
        result = check_cold(args.before_disk, args.after_disk, args.before_visible,
                            args.after_visible, args.cold_serial, args.cold_devices)
    except (ValueError, OSError, KeyError, struct.error) as error:
        result = {'schema_version': 1, 'status': 'FAIL', 'error': str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'committed_sequence', 'committed_document_sha256', 'error') if key in result}))
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
