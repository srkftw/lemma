#!/usr/bin/env python3
"""Read-only, bounded resume view. Evidence is admitted explicitly, never discovered as PASS.

Routing is a conservative verification plan, not the compilation cache key. The
cache's consumed-input closure remains the authority for individual build actions.
"""
from __future__ import annotations

import argparse
from collections import Counter
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

SCHEMA = "lemma-dev-status/v1"
EVIDENCE_SCHEMA = "lemma-dev-evidence/v1"
DISPOSITIONS = ("fresh-pass", "reused", "pending", "failed", "unavailable")
EXECUTION_CONTEXT = {"backend", "profile", "scenario", "driver", "fixtures", "initial_state",
                     "input_events", "seeds", "fault_schedule", "limits_environment"}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        value = hashlib.file_digest(stream, "sha256")
    return value.hexdigest()


def load(path: Path):
    # Duplicate keys can otherwise conceal a changed input or result.
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("receipt exceeds bounded 2 MiB status inspection; inspect its focused admission instead")
    return json.loads(path.read_text(), object_pairs_hook=unique)


def git(root: Path, *arguments: str, optional=False) -> str:
    result = subprocess.run(("git", *arguments), cwd=root, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=15, check=False)
    if result.returncode:
        if optional:
            return ""
        raise ValueError(result.stderr.decode(errors="replace").strip())
    return result.stdout.decode(errors="surrogateescape").rstrip("\n")


def source_state(root: Path, since: str | None = None) -> dict:
    root = Path(git(root, "rev-parse", "--show-toplevel")).resolve()
    raw = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries = raw.split("\0") if raw else []
    dirty, index = [], 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        if len(entry) < 4:
            raise ValueError("malformed Git status")
        dirty.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            if index >= len(entries):
                raise ValueError("truncated Git rename status")
            dirty.append(entries[index])
            index += 1
    changed = set(dirty)
    if since:
        changed.update(filter(None, git(root, "diff", "--name-only", "-z", since, "HEAD", "--").split("\0")))
    common = Path(git(root, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = root / common
    identity = {"head": git(root, "rev-parse", "HEAD"), "tree": git(root, "rev-parse", "HEAD^{tree}"),
                "branch": git(root, "symbolic-ref", "--short", "HEAD", optional=True) or "DETACHED",
                "upstream": git(root, "rev-parse", "--abbrev-ref", "@{upstream}", optional=True) or None,
                "worktree_root": str(root), "git_common_dir": str(common.resolve()),
                "dirty_paths": sorted(set(dirty)), "changed_paths": sorted(changed), "since": since}
    dirty_inputs = {}
    for name in identity["dirty_paths"]:
        path = root / name
        if path.is_symlink():
            dirty_inputs[name] = {"symlink": os.readlink(path)}
        elif path.is_file():
            dirty_inputs[name] = {"sha256": digest(path), "mode": path.stat().st_mode & 0o777}
        elif not path.exists():
            dirty_inputs[name] = {"deleted": True}
        else:
            dirty_inputs[name] = {"unavailable": "non-file Git entry"}
    identity["dirty_inputs"] = dirty_inputs
    identity["worktree_content_id"] = hashlib.sha256(json.dumps(
        {"head": identity["head"], "dirty_inputs": dirty_inputs}, sort_keys=True).encode()).hexdigest()
    identity["snapshot_scope"] = "read-only current checkout observation; not a frozen qualification source"
    identity["worktree_id"] = hashlib.sha256((str(root) + "\0" + str(common.resolve())).encode()).hexdigest()
    return identity


def verification_plan(config: dict, changed: list[str]) -> dict:
    if config.get("schema") != "lemma-verification-routes/v1":
        raise ValueError("unsupported verification routing schema")
    boundaries = config["boundaries"]
    by_id = {row["id"]: row for row in boundaries}
    if len(by_id) != len(boundaries):
        raise ValueError("duplicate verification boundary")
    reasons: dict[str, set[str]] = {}
    unmatched = []
    for path in sorted(set(changed)):
        matched = [row for row in boundaries if any(fnmatch.fnmatchcase(path, pattern) for pattern in row["inputs"])]
        if not matched:
            unmatched.append(path)
        for row in matched:
            reasons.setdefault(row["id"], set()).add(path)
    pending = list(reasons)
    while pending:
        identifier = pending.pop()
        for consumer in by_id[identifier].get("affects", []):
            if consumer not in by_id:
                raise ValueError(f"unknown verification consumer: {consumer}")
            if consumer not in reasons:
                reasons[consumer] = set()
                pending.append(consumer)
            reasons[consumer].add("boundary:" + identifier)
    claims = {}
    for identifier in sorted(reasons):
        for claim in by_id[identifier].get("claims", []):
            if claim not in config["claims"]:
                raise ValueError(f"unknown required claim: {claim}")
            claims[claim] = config["claims"][claim]
    for name in config.get("baseline_claims", []):
        if name not in config["claims"]:
            raise ValueError(f"unknown baseline claim: {name}")
        claims[name] = config["claims"][name]
    if unmatched:
        claims["dependency-review"] = config["claims"]["dependency-review"]
    return {"scope": "conservative verification routing; individual cache keys use consumed inputs",
            "affected": [{"boundary": identifier, "reasons": sorted(reasons[identifier])} for identifier in sorted(reasons)],
            "unmatched_paths": unmatched, "required_claims": claims}


def bound_path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError("evidence paths must be repository relative")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("evidence path escapes worktree")
    return path


def check_inventory(root: Path, inventory: dict, label: str) -> list[str]:
    if not isinstance(inventory, dict) or not inventory:
        raise ValueError(f"missing nonempty {label} inventory")
    reasons = []
    for name, expected in sorted(inventory.items()):
        if not isinstance(expected, str) or len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
            raise ValueError(f"invalid {label} digest: {name}")
        path = bound_path(root, name)
        if not path.is_file():
            reasons.append(f"{label} missing: {name}")
        elif digest(path) != expected:
            reasons.append(f"{label} changed: {name}")
    return reasons


def assess_evidence(root: Path, path: Path, *, campaign: str | None = None) -> dict:
    row = {"path": str(path), "disposition": "unavailable", "reasons": []}
    try:
        row["sha256"] = digest(path)
        value = load(path)
        if not isinstance(value, dict):
            raise ValueError("receipt is not an object")
        row["original"] = {key: value[key] for key in ("producer", "source_commit", "started_at", "finished_at", "status", "result") if key in value}
        if value.get("schema") != EVIDENCE_SCHEMA:
            raise ValueError("unrecognized evidence; retained without an applicability claim")
        if value.get("kind") not in ("production", "execution", "validation"):
            raise ValueError("missing evidence kind")
        if not isinstance(value.get("claim"), str) or not value["claim"]:
            raise ValueError("missing claim identity")
        row.update(claim=value["claim"], kind=value["kind"], context=value.get("context"))
        producer = value.get("producer")
        if not isinstance(producer, dict) or not all(producer.get(key) for key in ("source_commit", "executed_at", "command")):
            raise ValueError("missing original producer source/time/command")
        original = value.get("receipt")
        if not isinstance(original, dict) or not original.get("path") or not original.get("sha256"):
            raise ValueError("missing original receipt identity")
        row["original_receipt"] = original
        original_path = bound_path(root, original["path"])
        if not original_path.is_file() or digest(original_path) != original["sha256"]:
            raise ValueError("original receipt missing or changed")
        original_value = load(original_path)
        if not isinstance(original_value, dict) or original_value.get("status") not in ("PASS", "FAIL", "pass", "fail"):
            raise ValueError("original receipt has no supported execution result")
        row["original_execution_result"] = original_value["status"]
        if value.get("result") != original_value["status"].upper():
            raise ValueError("assessment differs from original result")
        # Failure is retained even when its old inputs are no longer current.
        if value["result"] == "FAIL":
            row.update(disposition="failed", reasons=["original execution failed; no replacement result inferred"])
            return row
        if value["kind"] == "execution":
            context = value.get("context")
            if not isinstance(context, dict) or not EXECUTION_CONTEXT <= context.keys() or any(context[key] is None for key in EXECUTION_CONTEXT):
                raise ValueError("execution context is incomplete; scenario applicability unknown")
        reasons = check_inventory(root, value.get("inputs"), "input")
        reasons += check_inventory(root, value.get("outputs"), "output")
        validator = value.get("validator")
        if not isinstance(validator, dict):
            raise ValueError("missing current validator identity")
        reasons += check_inventory(root, validator, "validator")
        row["reasons"] = reasons
        row["disposition"] = "pending" if reasons else "reused"
        if not reasons and value.get("route") == "fresh" and campaign and value.get("campaign") == campaign:
            row["disposition"] = "fresh-pass"
        elif value.get("route") not in ("fresh", "reused", "revalidated"):
            raise ValueError("unknown admission route")
    except (OSError, ValueError, TypeError, KeyError) as error:
        row.update(disposition="unavailable", reasons=[str(error)])
    return row



def canonical_digest(value) -> str:
    return hashlib.sha256((json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()).hexdigest()


def assess_build(root: Path, directory: Path) -> dict:
    """Read a real BuildActions journal without touching the writable cache.

    Producer receipts remain embedded in the retained evidence directory, so a
    cache eviction cannot remove this assessment's original commands/identities.
    This is production-only admission and never satisfies an execution claim.
    """
    row = {"path": str(directory), "kind": "production", "disposition": "unavailable",
           "functional_result": "pending: execute the affected scenario separately", "reasons": [], "actions": []}
    hashes = {}
    def measured(path):
        path = Path(path)
        info = path.stat()
        key = (str(path.resolve()), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if key not in hashes:
            hashes[key] = digest(path)
        return hashes[key]
    def check_runtime(action):
        if action.get("recipe_sha256") != measured(root / "scripts/build_actions.py"):
            row["reasons"].append("current build action recipe differs")
        helpers = {name: measured(root / "scripts" / name) for name in
                   ("core0_common.py", "action_worker.py", "build_dependencies.py")}
        if action.get("execution_helpers") != helpers:
            row["reasons"].append("current action execution/dependency helpers differ")
        python = action.get("host_python", {})
        if (not isinstance(python, dict) or not Path(python.get("path", "")).is_absolute()
                or not isinstance(python.get("sha256"), str) or len(python["sha256"]) != 64):
            row["reasons"].append("host Python identity unavailable")
        else:
            executable = Path(python["path"])
            if not executable.is_file() or measured(executable) != python["sha256"]:
                row["reasons"].append("producer host Python unavailable/changed")
    try:
        summary = load(directory / "actions.json")
        commands = load(directory / "commands.json")
        if (summary.get("schema") != "lemma-build-actions/1" or not isinstance(commands, list)
                or not isinstance(summary.get("actions"), list) or not summary["actions"]):
            raise ValueError("missing nonempty supported action journal")
        admissions = [command for command in commands if command.get("route") == "lemma-build-actions/1"]
        if len(admissions) != len(summary["actions"]):
            raise ValueError("command and action inventory counts differ")
        counts = Counter()
        for command, declared in zip(admissions, summary["actions"]):
            receipt_path = bound_path(directory, command["admission"])
            if measured(receipt_path) != command["admission_sha256"]:
                raise ValueError("action admission receipt missing or changed")
            receipt = load(receipt_path)
            state = receipt.get("status")
            if state != declared.get("status") or state not in ("fresh", "reused", "incremental"):
                raise ValueError("action summary differs from retained admission")
            counts[state] += 1
            if state == "incremental":
                if (receipt.get("schema") != "lemma-build-actions/1/preparation"
                        or receipt.get("executed", {}).get("returncode") != 0):
                    raise ValueError("incremental Lake preparation lacks successful execution")
                check_runtime(receipt.get("action", {}))
                row["reasons"].extend(check_inventory(root, receipt.get("inputs"), "preparation input"))
                row["actions"].append({"status": state, "reason": receipt.get("reason"),
                                       "duration_seconds": receipt.get("duration_seconds")})
                continue
            if receipt.get("schema") != "lemma-action-admission/1":
                raise ValueError("unknown action admission schema")
            producer = receipt["producer"]
            request = producer["request"]
            if (producer.get("schema") != "lemma-action-producer/1" or producer.get("result") != "success"
                    or canonical_digest(producer) != receipt["producer_receipt_id"]
                    or canonical_digest(request) != receipt["action_key"]
                    or producer["action_key"] != receipt["action_key"]
                    or producer["outputs"] != receipt["outputs"]
                    or declared.get("action_key") != receipt["action_key"]):
                raise ValueError("original producer identity/result differs")
            outputs = receipt["outputs"]
            materialized = receipt.get("materialized")
            if not isinstance(materialized, dict) or set(materialized) != set(outputs) or sorted(outputs) != request["output_names"]:
                raise ValueError("incomplete materialized output inventory")
            for name, expected in outputs.items():
                target = bound_path(directory, materialized[name])
                if not target.is_file():
                    row["reasons"].append("materialized output missing: " + str(target))
                elif (measured(target) != expected["sha256"] or target.stat().st_size != expected["size"]
                      or bool(target.stat().st_mode & 0o111) != expected["executable"]):
                    row["reasons"].append("materialized output changed: " + str(target))
            action = request["action"]
            check_runtime(action)
            for name, expected in request["inputs"].items():
                # Logical generated inputs are materialized within this build;
                # compiler-host/application dependencies use current source bytes.
                if name == "ActionExport.lean":
                    target = Path(receipt["requested_argv"][-1])
                    if not target.is_absolute(): target = root / target
                elif name.startswith("_export/"):
                    target = bound_path(directory, name[len("_export/"):])
                elif (root / name).is_file():
                    target = bound_path(root, name)
                else:
                    target = bound_path(directory, name)
                if not target.is_file():
                    row["reasons"].append("production input unavailable: " + name)
                elif measured(target) != expected["sha256"]:
                    row["reasons"].append("production input changed: " + name)
            for name, identity in action["tools"].items():
                tool = Path(identity["path"])
                if not tool.is_file() or measured(tool) != identity["sha256"]:
                    row["reasons"].append("producer tool unavailable/changed: " + name)
            validator = receipt.get("validator", {})
            expected_validator = {"schema": "lemma-build-actions/1",
                                  "audit_kernel_sha256": measured(root / "scripts/audit_kernel.py"),
                                  "build_admission_sha256": measured(root / "scripts/build_admission.py")}
            if validator != expected_validator:
                row["reasons"].append("current validator differs; re-audit required")
            row["actions"].append({"action_key": receipt["action_key"], "status": state,
                                   "producer_receipt_id": receipt["producer_receipt_id"],
                                   "original_producer": producer["provenance"],
                                   "original_started_at": producer["started_at"], "original_completed_at": producer["completed_at"],
                                   "duration_seconds": receipt.get("duration_seconds"), "reason": receipt.get("reason")})
        if dict(counts) != {key: value for key, value in summary["counts"].items() if value}:
            raise ValueError("summary action counts differ from actual admissions")
        row.update(disposition="pending" if row["reasons"] else "reused", counts=dict(counts))
        row["scope"] = "validated retained production route and current file/tool/validator identities; no functional PASS"
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        row.update(disposition="unavailable", reasons=[str(error)])
    return row


def process_identity(owner: dict, *, proc_root: Path = Path("/proc")) -> dict:
    """Compare boot + PID + kernel start ticks. Never send a signal here."""
    answer = {"owner": owner, "ownership": "unverified"}
    try:
        if (not isinstance(owner, dict) or type(owner.get("pid")) is not int or owner["pid"] <= 0
                or not isinstance(owner.get("boot_id"), str) or not owner["boot_id"]
                or isinstance(owner.get("start_ticks"), bool)
                or not str(owner.get("start_ticks", "")).isdigit()):
            raise ValueError("owner lacks boot ID, PID and process start ticks")
        boot = (proc_root / "sys/kernel/random/boot_id").read_text().strip()
        if boot != owner["boot_id"]:
            return {**answer, "ownership": "abandoned", "reason": "owner boot differs"}
        stat = (proc_root / str(owner["pid"]) / "stat").read_text()
        fields = stat[stat.rfind(")") + 2:].split()
        if len(fields) < 20:
            raise ValueError("truncated process identity")
        if fields[19] != str(owner["start_ticks"]):
            return {**answer, "ownership": "abandoned", "reason": "PID reused; process start differs"}
        if fields[0] == "Z":
            return {**answer, "ownership": "abandoned", "reason": "owner is a zombie"}
        return {**answer, "ownership": "verified", "reason": "boot, PID and process start match"}
    except FileNotFoundError:
        return {**answer, "ownership": "abandoned", "reason": "owner process unavailable"}
    except (OSError, ValueError, TypeError) as error:
        return {**answer, "reason": str(error)}


def cache_jobs(cache_dir: Path, *, limit=30) -> dict:
    """Inspect cache-owned registrations only; unrelated simulator owners stay untouched."""
    directory = cache_dir / "work"
    result = {"scope": "registered cache jobs only; other simulator/browser jobs are not enumerated",
              "cache_dir": str(cache_dir), "jobs": [], "truncated": False}
    if not directory.is_dir():
        result["availability"] = "no cache job registry"
        return result
    paths = sorted(directory.glob("*/owner.json"))
    result["truncated"] = len(paths) > limit
    for path in paths[:limit]:
        try:
            value = load(path)
            row = {"registration": str(path), "action_key": value.get("action_key", "preparing-snapshot"), "started_at": value.get("started_at"),
                   **process_identity(value.get("owner", value))}
        except (OSError, ValueError, TypeError, AttributeError) as error:
            row = {"registration": str(path), "ownership": "unverified", "reason": str(error)}
        result["jobs"].append(row)
    return result



def registered_evidence(root: Path, config: dict, explicit=(), *, campaign=None) -> list[dict]:
    """Assess only reviewed registrations and explicit command-line paths."""
    registry = config.get("evidence_paths", [])
    if not isinstance(registry, list):
        raise ValueError("evidence_paths must be an explicit list")
    requested = []
    for entry in registry:
        if isinstance(entry, str):
            entry = {"path": entry}
        if (not isinstance(entry, dict) or not isinstance(entry.get("path"), str)
                or set(entry) - {"path", "claim", "kind"}):
            raise ValueError("malformed evidence registration")
        if "claim" in entry:
            specification = config["claims"].get(entry["claim"])
            if not specification or entry.get("kind") != specification["kind"]:
                raise ValueError("registered evidence claim/kind differs from routing")
        requested.append((bound_path(root, entry["path"]), entry, "registered"))
    requested.extend((path if path.is_absolute() else root / path, {}, "explicit") for path in explicit)
    seen, result = set(), []
    for path, registration, origin in requested:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        row = assess_evidence(root, path, campaign=campaign)
        row["selection"] = origin
        if registration.get("claim"):
            if row.get("claim", registration["claim"]) != registration["claim"] or row.get("kind", registration["kind"]) != registration["kind"]:
                row.update(disposition="unavailable", reasons=["receipt claim/kind differs from reviewed registration"])
            row.update(claim=registration["claim"], kind=registration["kind"])
        result.append(row)
    return result


def external_job(path: Path) -> dict:
    """An explicit active-job registration is separate from historical evidence."""
    row = {"registration": str(path), "ownership": "unverified"}
    try:
        value = load(path)
        if not isinstance(value, dict):
            raise ValueError("job receipt is not an object")
        row["receipt_sha256"] = digest(path)
        row["status"] = value.get("status", "unknown")
        row["label"] = value.get("label", value.get("action", path.name))
        row["started_at"] = value.get("started_at")
        row["limits"] = value.get("limits", value.get("bounds"))
        row["log"] = value.get("log")
        owner = value.get("owner", value)
        if value.get("status") in {"PASS", "FAIL", "COMPLETE", "COMPLETED", "SUCCESS", "CANCELLED"}:
            # Historical cleanup is not invalidated by a later recycled PID.
            row.update(ownership="inactive", owner=owner, reason="terminal receipt; no active ownership inferred")
        else:
            row.update(process_identity(owner))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        row["reason"] = str(error)
    return row


def aggregate(required: dict, evidence: list[dict]) -> dict:
    claims = []
    for name, specification in sorted(required.items()):
        matches = [row for row in evidence if row.get("claim") == name and row.get("kind") == specification["kind"]]
        states = {row["disposition"] for row in matches}
        # Retained failures cannot be erased by finding another successful receipt.
        disposition = next((state for state in ("failed", "pending", "unavailable", "fresh-pass", "reused") if state in states), "pending")
        claims.append({"claim": name, "kind": specification["kind"], "disposition": disposition,
                       "reason": "no supplied applicable receipt; omitted work is pending" if not matches else "explicit supplied receipt assessment",
                       "command": specification["command"]})
    counts = Counter(row["disposition"] for row in claims)
    return {"required_claims": claims, "counts": {key: counts[key] for key in DISPOSITIONS},
            "complete": bool(claims) and all(row["disposition"] in ("fresh-pass", "reused") for row in claims),
            "scope": "reported claims only; cached production alone never passes functional execution"}


def collect(root: Path, *, config_path: Path | None = None, evidence_paths=(), cache_dir=None,
            since=None, changed=None, campaign=None, limit=30, build_dirs=(), job_receipts=()) -> dict:
    root = root.resolve()
    config_path = config_path or root / "scripts/verification_routes.json"
    config = load(config_path)
    comparison_base = since if since is not None else config.get("comparison_base")
    if comparison_base is not None and (not isinstance(comparison_base, str) or not comparison_base):
        raise ValueError("comparison_base must be a nonempty Git revision")
    source = source_state(root, comparison_base)
    paths = source["changed_paths"] if changed is None else changed
    plan = verification_plan(config, paths)
    evidence = registered_evidence(root, config, evidence_paths, campaign=campaign)
    builds = [assess_build(root, path if path.is_absolute() else root / path) for path in build_dirs]
    jobs = cache_jobs(cache_dir or root / "build/action-cache", limit=limit)
    jobs["external"] = [external_job(path if path.is_absolute() else root / path) for path in job_receipts[:limit]]
    jobs["external_truncated"] = len(job_receipts) > limit
    summary = aggregate(plan["required_claims"], evidence)
    blockers = [f'{row["claim"]}: {row["disposition"]}' for row in summary["required_claims"] if row["disposition"] not in ("fresh-pass", "reused")]
    next_action = next((row["command"] for row in summary["required_claims"] if row["disposition"] not in ("fresh-pass", "reused")), "No changed-boundary verification pending; choose the next objective from CURRENT.md.")
    return {"schema": SCHEMA, "objective": config["objective"], "source": source, "routing": plan,
            "evidence": evidence, "builds": builds, "aggregate": summary, "active_jobs": jobs,
            "blockers": blockers, "next_action": next_action, "resource_budgets": config["resource_budgets"],
            "historical_checkpoint": config["historical_checkpoint"], "routing_identity": {"path": str(config_path), "sha256": digest(config_path)}}


def render(value: dict, limit=12) -> str:
    source, summary = value["source"], value["aggregate"]
    lines = [f'Lemma status {source["head"][:12]} on {source["branch"]} ({len(source["dirty_paths"])} dirty paths)',
             f'Objective: {value["objective"]}',
             'Affected: ' + (", ".join(row["boundary"] for row in value["routing"]["affected"]) or "none"),
             'Claims: ' + ", ".join(f'{key}={count}' for key, count in summary["counts"].items())]
    for row in summary["required_claims"][:limit]:
        lines.append(f'  {row["disposition"]}: {row["claim"]}')
    if len(summary["required_claims"]) > limit:
        lines.append("  … more claims in --json")
    jobs = value["active_jobs"]["jobs"]
    lines.append(f'Cache jobs: {len(jobs)} registered, {sum(row["ownership"] == "verified" for row in jobs)} verified live owners; other jobs not enumerated')
    for row in jobs[:limit]:
        lines.append(f'  {row["ownership"]}: {row.get("action_key", "unknown")} ({row.get("reason", "")})')
    for row in value["active_jobs"]["external"][:limit]:
        lines.append(f'Job {row["ownership"]}: {row.get("label", row["registration"])} ({row.get("reason", "")})')
    for build in value["builds"][:limit]:
        lines.append(f'Production {build["disposition"]}: {build["path"]}; actions={build.get("counts", {})}; functional=pending')
        lines.extend("  " + reason for reason in build["reasons"][:2])
    for row in value["evidence"][:limit]:
        lines.append(f'Evidence {row["disposition"]}: {row["path"]}; ' + ("; ".join(row["reasons"][:2]) or "consumed hashes match"))
    lines.extend((f'Next: {value["next_action"]}', f'History: {value["historical_checkpoint"]}',
                  "This command runs no builds/tests and writes no source or receipts."))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--since", help="route committed changes from this Git revision, overriding the objective's configured comparison_base")
    parser.add_argument("--changed", action="append", help="explicit changed path; repeat to assess a scoped candidate")
    parser.add_argument("--evidence", action="append", type=Path, default=[], help="explicit admission assessment; never scan history for PASS")
    parser.add_argument("--job-receipt", type=Path, action="append", default=[], help="explicit external active-job owner receipt; never scan unrelated processes")
    parser.add_argument("--build", type=Path, action="append", default=[], help="validate a retained build action journal; production only")
    parser.add_argument("--campaign", help="only matching explicit campaign receipts count as fresh")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--max-items", type=int, default=12)
    args = parser.parse_args(argv)
    if not 1 <= args.max_items <= 100:
        parser.error("--max-items must be between 1 and 100")
    try:
        value = collect(args.root, evidence_paths=args.evidence, cache_dir=args.cache_dir,
                        since=args.since, changed=args.changed, campaign=args.campaign, limit=args.max_items, build_dirs=args.build, job_receipts=args.job_receipt)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"STATUS UNAVAILABLE: {error}", file=sys.stderr)
        return 1
    print(json.dumps(value, indent=2, sort_keys=True) if args.json else render(value, args.max_items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
