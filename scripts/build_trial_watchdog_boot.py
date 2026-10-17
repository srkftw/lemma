#!/usr/bin/env python3
"""Build the explicitly versioned, genuine Lean authenticated trial watchdog ROM.
Public development key only. Boot execution/fallback require separate evidence.
"""
import argparse
import json
from pathlib import Path
from build_development_auth_boot import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--public-development-key', action='store_true', required=True)
    args = parser.parse_args()
    result = build(args.work_dir.resolve(), trial_watchdog=True)
    print(json.dumps({k: result.get(k) for k in ('status', 'seconds', 'error')}, indent=2))
    return 0 if result['status'] == 'PASS_GENUINE_TRIAL_WATCHDOG_AUTH_ROM' else 1


if __name__ == '__main__':
    raise SystemExit(main())
