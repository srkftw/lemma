"""Exact additive kernel artifact pins for the metadata-read refinement.

Historical complete authorities stay immutable. This selects a separately
captured successor catalog; the caller still checks every pre/post body,
global and caller edge against that successor. No target behavior runs here.
"""
import hashlib
import json
import re
from pathlib import Path

from core0_common import Core0Error
from paper_next import canonical

VERSION = 'lemma-kernel-pool-read-refinement/1'
AUTHORITY = Path(__file__).resolve().parents[1] / 'tooling/kernel-pool-read-target-authority.json'
GETTERS = frozenset(('Lemma.Kernel.Objects.getGeneric', 'Lemma.Kernel.IPCStorage.getGeneric'))
CONFIGURATIONS = {
    **{f'lemmasim-silicon-usb-clocked-{stem}-bulk-{suffix}': name
       for stem, name in (
           ('package-entry2', 'package-entry2'), ('reader-entry2', 'companion-reader'),
           ('retry', 'usb-recovery'), ('package-retry', 'package-companion'),
           ('closure-retry', 'usb-closure-recovery'))
       for suffix in ('notebook', 'initialize')},
    'lemmasim-silicon-product-course-reader-bulk-notebook': 'product-reader',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def refined_role(unit, previous, authority_path, role_key):
    """Select only the exact new kernel; old artifacts use their original pins."""
    if unit.get('role') != 'kernel':
        return previous
    present = GETTERS & {canonical(row['source']) for row in unit.get('functions', [])}
    if not present:
        return previous
    configuration = unit.get('configuration')
    expected_name = CONFIGURATIONS.get(configuration)
    expected_role = 'kernel-init' if str(configuration).endswith('-initialize') else 'kernel'
    if (present != GETTERS or expected_name is None or role_key != expected_role or
            Path(authority_path).name != expected_name + '-target-authority.json'):
        raise Core0Error('Pool-read refinement escaped its exact kernel/deployment')
    authority = json.loads(AUTHORITY.read_text())
    if (set(authority) != {'schema', 'configurations'} or authority['schema'] != VERSION or
            set(authority['configurations']) != set(CONFIGURATIONS)):
        raise Core0Error('Pool-read refinement complete configuration inventory differs')
    entry = authority['configurations'][configuration]
    if (set(entry) != {'predecessor_authority', 'predecessor_authority_sha256',
                       'role_key', 'cohort', 'previous_role_sha256', 'role'} or
            entry['predecessor_authority'] != Path(authority_path).name or
            entry['predecessor_authority_sha256'] != hashlib.sha256(Path(authority_path).read_bytes()).hexdigest() or
            entry['previous_role_sha256'] != digest(previous) or entry['role_key'] != role_key):
        raise Core0Error('Pool-read refinement exact predecessor authority differs')
    registry = expected_name in ('usb-recovery', 'usb-closure-recovery')
    if entry['cohort'] != ('registry1-descriptor1-pool-read1' if registry else 'pool-read1'):
        raise Core0Error('Pool-read refinement exact algorithm cohort differs')
    successor = entry['role']
    if not isinstance(successor, dict) or successor.get('catalog_sha256') != digest(unit):
        raise Core0Error('Pool-read refinement complete typed/effect/root catalog differs')
    old_count = previous.get('pre_function_count', previous.get('function_count'))
    if (type(old_count) is not int or
            any(successor.get(phase + '_function_count') != old_count + (4 if registry else 2) for phase in ('pre', 'post')) or
            any(not isinstance(successor.get(phase + '_sha256'), str) or
                re.fullmatch('[0-9a-f]{64}', successor[phase + '_sha256']) is None
                for phase in ('pre', 'post'))):
        raise Core0Error('Pool-read refinement complete corpus pins/counts differ')
    return successor
