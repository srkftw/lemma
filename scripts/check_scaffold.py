#!/usr/bin/env python3
"""Validate planning metadata, not Core0 compilation or target execution."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

STATUSES = {'planned', 'in_progress', 'partial', 'blocked', 'failed', 'passed'}
REQUIRED = (
    'docs/overview.html', 'docs/contributor-guide.html', 'docs/ARCHITECTURE.html', 'docs/SOURCES.html',
    'docs/contracts/CORE0.html', 'docs/contracts/TARGET_ABI.html',
    'docs/contracts/LEMMA_VM.html', 'docs/contracts/TRUST_MANIFEST.html',
    'docs/plan/BUILD_ORDER.html', 'docs/plan/construction-units.json',
    'codex/prompts/001-core0-freestanding-slice.html', 'tooling/toolchain-lock.json',
    'repository.json', 'scripts/publish-github.sh',
)

def validate(root: Path) -> list[str]:
    errors = [f'Missing required scaffold file: {p}' for p in REQUIRED if not (root/p).is_file()]
    try:
        plan = json.loads((root/'docs/plan/construction-units.json').read_text())
        meta = json.loads((root/'repository.json').read_text())
        lock = json.loads((root/'tooling/toolchain-lock.json').read_text())
    except (OSError, ValueError) as exc:
        return errors + [f'Unreadable planning JSON: {exc}']
    if not all(isinstance(o, dict) for o in (plan, meta, lock)):
        return errors + ['Planning JSON roots must be objects']
    if meta.get('name') != 'lemma' or meta.get('intended_owner') != 'srkftw':
        errors.append('Unexpected repository owner/name; publishing destination needs review')
    if meta.get('intended_visibility') != 'private':
        errors.append('Initial repository visibility must remain private')
    if meta.get('default_branch') != 'main':
        errors.append('Unexpected default branch')
    if meta.get('license') is not None:
        errors.append('License selection requires an owner decision')
    for obj in (plan, meta, lock):
        if obj.get('schema_version') != 1:
            errors.append('Unrecognized metadata schema version')
    tools = lock.get('tools')
    if not isinstance(tools, dict) or not tools:
        errors.append('Toolchain inventory is missing or malformed')
    elif lock.get('status') == 'pinned':
        for name, entry in tools.items():
            if not isinstance(entry, dict) or not entry.get('revision') or not entry.get('verified'):
                errors.append(f'Pinned tool lacks a verified immutable identity: {name}')
    elif lock.get('status') != 'unresolved':
        errors.append('Toolchain status must be unresolved or pinned')
    units, gates = plan.get('units'), plan.get('gates')
    if not isinstance(units, list) or not isinstance(gates, list):
        return errors + ['Units and gates must be arrays']
    if not all(isinstance(u, dict) and isinstance(u.get('id'), str) for u in units):
        return errors + ['Each construction unit must be an object with an ID']
    ids = [u['id'] for u in units]
    expected = {f'{n}.{i}' for n in range(1,8) for i in range(1,9)} | {f'H.{i}' for i in range(1,7)}
    if len(ids) != 62 or len(ids) != len(set(ids)) or set(ids) != expected:
        errors.append('Expected exactly 56 software and six physical units with unique stable IDs')
    by_id = {u['id']: u for u in units}
    graph = {}
    for u in units:
        uid = u['id']
        if u.get('status') not in STATUSES:
            errors.append(f'Invalid status for {uid}')
        if not isinstance(u.get('required_evidence'), str) or not u['required_evidence'].strip():
            errors.append(f'Missing evidence requirement for {uid}')
        records = u.get('evidence_records')
        if not isinstance(records, list) or (u.get('status') == 'passed' and not records):
            errors.append(f'Missing/malformed evidence records for {uid}')
        deps = u.get('depends_on')
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            errors.append(f'Malformed dependencies for {uid}')
            deps = []
        for dep in deps:
            if dep not in by_id:
                errors.append(f'Unknown dependency {dep} in {uid}')
        graph[uid] = [d for d in deps if d in by_id]
    active, done = set(), set()
    def visit(uid):
        if uid in active:
            errors.append(f'Dependency cycle through {uid}')
            return
        if uid in done:
            return
        active.add(uid)
        for dep in graph.get(uid, []):
            visit(dep)
        active.remove(uid)
        done.add(uid)
    for uid in ids:
        visit(uid)
    if not all(isinstance(g, dict) for g in gates):
        return errors + ['Each gate must be an object']
    if [g.get('id') for g in gates] != [f'G{i}' for i in range(1,8)]:
        errors.append('Expected the seven ordered integration gates')
    for g in gates:
        gid = g.get('id')
        if g.get('status') not in STATUSES:
            errors.append(f'Invalid gate status: {gid}')
        members = g.get('units')
        if not isinstance(members, list) or not all(isinstance(i,str) and i in by_id for i in members):
            errors.append(f'Malformed unit list for gate {gid}')
            members = []
        if g.get('status') == 'passed':
            if not g.get('evidence_records'):
                errors.append(f'Passed gate lacks integration evidence: {gid}')
            if any(by_id[i].get('status') != 'passed' for i in members):
                errors.append(f'Passed gate has unfinished units: {gid}')
    target_root = root/'Lemma'
    forbidden = {'.c','.cc','.cpp','.cxx','.rs','.zig','.s','.S'}
    if target_root.exists():
        for p in target_root.rglob('*'):
            if p.is_file() and p.suffix in forbidden:
                errors.append(f'Maintained non-Lean target source: {p.relative_to(root)}')
    from check_documentation import validate as validate_documentation
    errors.extend(validate_documentation(root))
    return errors

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = validate(args.root.resolve())
    if errors:
        for error in errors:
            print(f'ERROR: {error}', file=sys.stderr)
        return 1
    print('Scaffold metadata valid: 7 gates, 56 software units, 6 physical units; dependency graph acyclic.')
    print('Scope: planning metadata only. Core0 compilation, RV64 boot and G1 are NOT tested here.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
