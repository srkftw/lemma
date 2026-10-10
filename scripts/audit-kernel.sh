#!/usr/bin/env bash
set -euo pipefail
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$(dirname -- "$script_dir")"
exec python3 scripts/audit_kernel.py "$@"
