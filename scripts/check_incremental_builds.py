#!/usr/bin/env python3
"""Measure real CLI compilation reuse in a private, source-bound checkout.

Run inside the pinned development environment. This campaign produces and audits
artifacts; guest scenarios remain separate required execution evidence. Source
mutations are confined to the private checkout and require exact replacements.
"""
from __future__ import annotations

import argparse
import ast
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
import time

from action_cache import is_process_alive, process_identity, source_provenance
from core0_common import Core0Error, sha256, write_json

SCHEMA = "lemma-incremental-build-campaign/1"
CONFIGURATION = "lemmasim-silicon-bytes-bulk-notebook"
TOOLS = {"lean", "lake", "opt", "llc", "clang", "ld.lld", "llvm-objcopy"}
PAYLOAD_SUFFIXES = {".ll", ".o", ".elf", ".S", ".s", ".bin", ".ld", ".map"}


class CampaignCancelled(Core0Error):
    def __init__(self, number):
        self.signal_number = number
        super().__init__("campaign cancelled by " + signal.Signals(number).name)


def _cancel_campaign(number, _frame):
    raise CampaignCancelled(number)


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          timeout=60, check=True).stdout


def source_listing(root: Path) -> list[str]:
    names = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return sorted(set(os.fsdecode(name) for name in names.split(b"\0") if name))


def snapshot_checkout(root: Path, destination: Path, log: Path) -> dict:
    """Copy all current nonignored inputs, while keeping real original Git history."""
    names = source_listing(root)
    observed = source_provenance(root)
    observed["porcelain_all"] = git(root, "status", "--porcelain=v1", "--untracked-files=all").decode()
    inventory, missing = {}, []
    for name in names:
        path = root/name
        if path.is_symlink():
            raise Core0Error("source snapshot rejects symlinks: " + name)
        if not path.exists():
            missing.append(name)
        elif not path.is_file():
            raise Core0Error("source snapshot rejects special/directory inputs: " + name)
        else:
            inventory[name] = sha256(path)
    with log.open("wb") as stream:
        subprocess.run(["git", "clone", "--shared", "--no-hardlinks", "--no-checkout", str(root), str(destination)],
                       stdout=stream, stderr=subprocess.STDOUT, timeout=120, check=True)
        subprocess.run(["git", "-C", str(destination), "checkout", "--detach", observed["commit"]],
                       stdout=stream, stderr=subprocess.STDOUT, timeout=120, check=True)
    for name in missing:
        path = destination/name
        if path.is_dir() and not path.is_symlink():
            raise Core0Error("deleted tracked file became a directory in clone: " + name)
        path.unlink(missing_ok=True)
    for name, digest in inventory.items():
        target = destination/name
        # A tracked symlink may have become a regular file in the working tree.
        # Never follow the historical checkout's link when overlaying that file.
        if target.is_symlink(): target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/name, target)
        os.chmod(target, (root/name).stat().st_mode & 0o777)
        if sha256(target) != digest:
            raise Core0Error("source changed while taking campaign snapshot: " + name)
    if source_listing(root) != names or git(root, "rev-parse", "HEAD").decode().strip() != observed["commit"]:
        raise Core0Error("source identity/file inventory changed while snapshotting")
    for name, digest in inventory.items():
        if (root/name).is_symlink() or sha256(root/name) != digest:
            raise Core0Error("source changed while snapshotting: " + name)
    if any((root/name).exists() for name in missing):
        raise Core0Error("a deleted source reappeared while snapshotting")
    return {"original": observed, "checkout": str(destination), "files": inventory,
            "deleted_tracked_files": missing,
            "inventory_sha256": hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest(),
            "git_object_storage": "shared read-only alternates; no copied working-tree outputs"}


def owned_descendants(pid: int) -> list[dict]:
    parents, identities = {}, {}
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    for path in Path("/proc").iterdir():
        if not path.name.isdigit(): continue
        try:
            fields = (path/"stat").read_text().rsplit(")", 1)[1].split()
            child = int(path.name)
            parents[child] = int(fields[1])
            identities[child] = {"pid":child,"start_ticks":fields[19],"boot_id":boot}
        except (OSError, ValueError, IndexError): continue
    found, pending = [], [pid]
    while pending:
        parent = pending.pop()
        children = [child for child, value in parents.items() if value == parent]
        pending.extend(children)
        found.extend(identities[child] for child in children)
    return found


def _identity_key(identity):
    return (identity["pid"],identity["start_ticks"],identity["boot_id"])


def _belongs_to_run(identity, baseline):
    """Verify current ancestry as well as boot/start before sending a signal.

    Campaign phases execute sequentially in their own driver process. Existing
    children and any descendants they create are explicitly outside this run.
    A subreaper retains this run's detached descendants when their parent exits.
    """
    if not is_process_alive(identity): return False
    current = identity
    for _ in range(128):
        if _identity_key(current) in baseline: return False
        if current["pid"] == os.getpid(): return True
        try:
            fields = Path(f"/proc/{current['pid']}/stat").read_text().rsplit(")",1)[1].split()
            if fields[19] != current["start_ticks"]: return False
            current = process_identity(int(fields[1]))
            if current["start_ticks"] is None: return False
        except (OSError,IndexError): return False
    return False


def _lease_worker(identity):
    try:
        arguments = Path(f"/proc/{identity['pid']}/cmdline").read_bytes().split(b"\0")
        return (process_identity(identity["pid"]) == identity and b"--lease-fd" in arguments
                and b"--result-fd" in arguments and any(arg.endswith(b"/action_worker.py") for arg in arguments))
    except OSError: return False


def _stop_logged(process, owner, baseline):
    # Stop spawning before taking the final ownership snapshot. Repeated scans
    # include descendants that detached into new process groups or were adopted.
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
    owned = {owner["pid"]:owner}
    try:
        if _belongs_to_run(owner,baseline) and not _lease_worker(owner):
            try: os.kill(owner["pid"],signal.SIGSTOP)
            except ProcessLookupError: pass
        for _ in range(5):
            added = False
            for identity in owned_descendants(os.getpid()):
                if not _belongs_to_run(identity,baseline): continue
                if identity["pid"] not in owned: added = True
                owned[identity["pid"]] = identity
                try: os.kill(identity["pid"],signal.SIGTERM if _lease_worker(identity) else signal.SIGSTOP)
                except ProcessLookupError: pass
            if not added: break
        for identity in reversed(list(owned.values())):
            if _belongs_to_run(identity,baseline):
                try: os.kill(identity["pid"],signal.SIGTERM if _lease_worker(identity) else signal.SIGKILL)
                except ProcessLookupError: pass
        process.wait(timeout=5)
        deadline = time.monotonic()+5
        while True:
            pending = []
            for identity in owned.values():
                if identity["pid"] == process.pid: continue
                # Reap only recorded owned children, never waitpid(-1).
                if process_identity(identity["pid"]) != identity: continue
                try: os.waitpid(identity["pid"],os.WNOHANG)
                except ChildProcessError: pass
                if is_process_alive(identity): pending.append(identity)
            if not pending: break
            if time.monotonic() >= deadline:
                error = Core0Error("verified campaign descendants retain cleanup ownership after cancellation: " + json.dumps(pending))
                error.cleanup_pending = pending
                raise error
            time.sleep(0.01)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK,previous_mask)


def run_logged(argv: list[str], *, cwd: Path, log: Path, timeout: float,
               env: dict[str, str]) -> dict:
    started, before = time.monotonic(), resource.getrusage(resource.RUSAGE_CHILDREN)
    if ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0) != 0:
        raise Core0Error("cannot establish campaign descendant reaping")
    baseline = {_identity_key(identity) for identity in owned_descendants(os.getpid())}
    with log.open("wb") as stream:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   start_new_session=True)
        owner = process_identity(process.pid)
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _stop_logged(process,owner,baseline)
            raise Core0Error(f"campaign command timed out; full log: {log}")
        except BaseException:
            _stop_logged(process,owner,baseline)
            raise
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"argv": argv, "cwd": str(cwd), "returncode": returncode,
            "elapsed_seconds": time.monotonic()-started, "log": str(log),
            "log_sha256": sha256(log), "owner": owner,
            "child_user_cpu_seconds": after.ru_utime-before.ru_utime,
            "child_system_cpu_seconds": after.ru_stime-before.ru_stime,
            "children_peak_rss_kib_cumulative": after.ru_maxrss}


def invocation_counts(path: Path) -> dict:
    """Count successful execve observations, including unfinished/resumed lines."""
    pattern = re.compile(r'^(?:(?:\[pid\s+)?(\d+)\]?\s+)?execve\(("(?:\\.|[^"\\])*"),\s*(\[(?:"(?:\\.|[^"\\])*"|[^\]])*\])')
    pending, calls = {}, []
    for line in path.read_text(errors="replace").splitlines():
        match = pattern.search(line)
        if match:
            pid, executable, arguments = match.groups()
            try:
                record = {"path": ast.literal_eval(executable), "argv": ast.literal_eval(arguments)}
            except (ValueError, SyntaxError) as error:
                raise Core0Error("incomplete strace argv; cannot measure invocations") from error
            if re.search(r"\)\s+=\s+0\s*$", line): calls.append(record)
            elif "<unfinished ...>" in line: pending[pid] = record
        elif "<... execve resumed>" in line:
            pid = re.match(r"^(?:\[pid\s+)?(\d+)", line)
            if pid and pid.group(1) in pending:
                record = pending.pop(pid.group(1))
                if re.search(r"=\s+0\s*$", line): calls.append(record)
    if pending:
        raise Core0Error("incomplete successful-execution trace; pending execve observations")
    by_path, by_tool, production, metadata = {}, {}, {}, {}
    for record in calls:
        name = Path(record["path"]).name
        tool = "clang" if name.startswith("clang-") else name
        if tool not in TOOLS: continue
        by_path[record["path"]] = by_path.get(record["path"], 0)+1
        by_tool[tool] = by_tool.get(tool, 0)+1
        arguments = record["argv"][1:]
        category = metadata if any(arg in {"--version", "--githash"} for arg in arguments) else production
        category[tool] = category.get(tool, 0)+1
    return {"schema": "lemma-execve-counts/1", "trace": str(path), "trace_sha256": sha256(path),
            "successful_execve_by_path": by_path, "successful_execve_by_tool": by_tool,
            "production_by_tool": production, "metadata_by_tool": metadata,
            "lake_preparations_are_separate": True}


def payload_inventory(directory: Path) -> dict[str, str]:
    result = {p.relative_to(directory).as_posix():sha256(p) for p in sorted(directory.rglob("*"))
              if p.is_file() and p.suffix in PAYLOAD_SUFFIXES
              and p.relative_to(directory).parts[0] not in {"action-source", "action-receipts"}}
    if not result or not any(name.endswith(".elf") for name in result):
        raise Core0Error("payload inventory lacks real linked ELF output")
    return result


def action_measurements(directory: Path) -> dict:
    summary = json.loads((directory/"actions.json").read_text())
    records = []
    for path in sorted((directory/"action-receipts").glob("*.json")):
        receipt = json.loads(path.read_text())
        producer = receipt.get("producer", {})
        action = producer.get("request", {}).get("action", receipt.get("action", {}))
        records.append({"receipt":str(path), "sha256":sha256(path), "status":receipt["status"],
                        "action_key":receipt.get("action_key"), "kind":action.get("kind"),
                        "reason":receipt.get("reason"), "requested_argv":receipt.get("requested_argv"),
                        "input_names": sorted(producer.get("request", {}).get("inputs", {})),
                        "materialized":receipt.get("materialized", {})})
    if not records: raise Core0Error("build emitted no action receipts")
    return {"counts":summary["counts"], "actions":records}


def campaign(args, root: Path, work: Path) -> dict:
    report = {"schema":SCHEMA, "status":"RUNNING", "scope":"artifact-production-only",
              "configuration":args.configuration, "started_at":time.time(), "phases":[],
              "functional_result":"unavailable: run new guest Save/cold-recovery and negative scenarios separately",
              "mutation_result":"unavailable: no exact mutation requested", "payload_suffixes":sorted(PAYLOAD_SUFFIXES)}
    write_json(work/"report.json", report)
    try:
        trace_tool = shutil.which(args.strace)
        if trace_tool is None: raise Core0Error("required strace tool is unavailable: " + args.strace)
        checkout = work/"checkout"
        report["source"] = snapshot_checkout(root, checkout, work/"snapshot.log")
        write_json(work/"source-snapshot.json", report["source"])
        environment = {**os.environ, "LEMMA_BUILD_FRESH":"0"}
        cache = work/"cache"
        def phase(name, *, standalone=False, fresh=False):
            output = checkout/("build/user/" if standalone else "build/kernel/")/name
            command = [sys.executable, "scripts/build_user.py" if standalone else "scripts/build_kernel.py",
                       "--configuration",args.configuration,"--opt-level","O2","--timeout",str(args.action_timeout),
                       "--cache-dir",str(cache),"--output-dir",output.relative_to(checkout).as_posix()]
            command += ["--image-key",args.image_key] if standalone else ["--stage","supervisor"]
            if fresh: command.append("--fresh")
            trace = work/f"{name}.execve.log"
            invocation = [trace_tool,"-f","-qq","-s","65535","-e","trace=execve","-o",str(trace),*command]
            print(f"INCREMENTAL {name}: {' '.join(command)}", flush=True)
            row = {"name":name,"output":str(output),"fresh_production_requested":fresh}
            report["phases"].append(row)
            write_json(work/"report.json",report)
            row["production"] = run_logged(invocation,cwd=checkout,log=work/f"{name}.build.log",timeout=args.timeout,env=environment)
            row["invocations"] = invocation_counts(trace)
            if row["production"]["returncode"]:
                raise Core0Error(f"{name} build failed; log: {row['production']['log']}")
            row["actions"] = action_measurements(output)
            row["payloads"] = payload_inventory(output)
            audit = [sys.executable,"scripts/audit_kernel.py",output.relative_to(checkout).as_posix(),"--timeout",str(args.action_timeout)]
            if not standalone: audit += ["--source-root",str(output/"action-source")]
            row["audit"] = run_logged(audit,cwd=checkout,log=work/f"{name}.audit.log",timeout=args.timeout,env=environment)
            if row["audit"]["returncode"]: raise Core0Error(f"{name} audit failed; log: {row['audit']['log']}")
            row["status"] = "PASS"
            write_json(work/"report.json",report)
            return row
        fresh = phase("fresh",fresh=True)
        warm = phase("warm")
        if fresh["payloads"] != warm["payloads"]:
            report["payload_differences"] = sorted(name for name in fresh["payloads"].keys()|warm["payloads"].keys()
                if fresh["payloads"].get(name) != warm["payloads"].get(name))
            raise Core0Error("fresh/warm deterministic payloads differ; no normalization applied")
        if warm["actions"]["counts"].get("fresh", 0):
            raise Core0Error("warm target production unexpectedly executed fresh compilation actions")
        production = warm["invocations"]["production_by_tool"]
        if any(production.get(tool,0) for tool in TOOLS-{"lake"}):
            raise Core0Error("warm trace contains actual target/compiler production invocations")
        independent = phase("standalone",standalone=True)
        if any(warm["payloads"].get(name) != digest for name,digest in independent["payloads"].items()):
            raise Core0Error("standalone notebook payload differs from kernel's separately linked image")
        if args.mutation_old is not None:
            relative = Path(args.mutation_source)
            if relative.is_absolute() or ".." in relative.parts:
                raise Core0Error("mutation source must stay inside isolated checkout")
            target = checkout/relative
            original = target.read_text()
            if original.count(args.mutation_old) != 1:
                raise Core0Error("mutation replacement must match exactly once")
            target.write_text(original.replace(args.mutation_old,args.mutation_new))
            report["mutation"] = {"source":relative.as_posix(),"before_sha256":hashlib.sha256(original.encode()).hexdigest(),
                                  "after_sha256":sha256(target),"old":args.mutation_old,"new":args.mutation_new}
            changed = phase("changed")
            if not changed["actions"]["counts"].get("fresh",0):
                raise Core0Error("relevant source mutation failed to invalidate production")
            report["mutation_result"] = "production invalidated and audited; behavioral negative remains pending"
        report.update(status="PASS",completed_at=time.time(),deterministic_payload_match=True,
                      next_action="Execute fresh guest Save/cold-recovery and controlled negative scenarios using the recorded outputs")
        write_json(work/"report.json",report)
        return report
    except BaseException as error:
        report.update(status="FAIL",completed_at=time.time(),error=str(error),
                      next_action="Inspect the first failed phase log; preserve this campaign and use an unused path for a corrected candidate")
        if isinstance(error,CampaignCancelled): report["cancellation_signal"] = error.signal_number
        if getattr(error,"cleanup_pending",None): report["cleanup_pending"] = error.cleanup_pending
        write_json(work/"report.json",report)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False,description=__doc__)
    parser.add_argument("--work-dir",type=Path,required=True)
    parser.add_argument("--timeout",type=float,default=1800,help="per production/audit phase deadline")
    parser.add_argument("--action-timeout",type=float,default=300)
    parser.add_argument("--strace",default="strace",help="actual strace executable, required")
    parser.add_argument("--configuration",default=CONFIGURATION)
    parser.add_argument("--image-key",default="notebook")
    parser.add_argument("--mutation-source",default="Lemma/Applications/Notebook.lean")
    parser.add_argument("--mutation-old")
    parser.add_argument("--mutation-new")
    args = parser.parse_args()
    if (args.mutation_old is None) != (args.mutation_new is None): parser.error("exact mutation requires both --mutation-old and --mutation-new")
    if args.mutation_old == "" or args.mutation_old == args.mutation_new and args.mutation_old is not None:
        parser.error("mutation must replace nonempty source bytes with different bytes")
    if any(not math.isfinite(value) or value <= 0 for value in (args.timeout,args.action_timeout)):
        parser.error("timeouts must be finite and positive")
    root = Path(__file__).resolve().parents[1]
    work = (root/args.work_dir).resolve()
    if not work.is_relative_to((root/"build/incremental").resolve()) or work == (root/"build/incremental").resolve():
        parser.error("work directory must be an unused build/incremental subdirectory")
    if work.exists(): parser.error("campaign work directory already exists; use an unused path")
    work.mkdir(parents=True)
    previous_signals = {number:signal.getsignal(number) for number in (signal.SIGTERM,signal.SIGINT)}
    for number in previous_signals: signal.signal(number,_cancel_campaign)
    try:
        result = campaign(args,root,work)
    except (Core0Error,OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        print(f"INCREMENTAL BUILD FAIL: {error}; report: {work/'report.json'}",file=sys.stderr)
        return 128+error.signal_number if isinstance(error,CampaignCancelled) else 1
    finally:
        for number,handler in previous_signals.items(): signal.signal(number,handler)
    print(f"INCREMENTAL PRODUCTION PASS; guest execution pending; report: {work/'report.json'}")
    for phase in result["phases"]:
        print(f"{phase['name']}: {phase['production']['elapsed_seconds']:.3f}s; actions {phase['actions']['counts']}; production execve {phase['invocations']['production_by_tool']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
