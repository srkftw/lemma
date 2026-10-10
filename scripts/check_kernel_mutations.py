#!/usr/bin/env python3
"""Build fresh controls and qualify four closed Task003 source mutations.

This host-only controller creates three detached checkouts of one exact clean
commit. It copies no artifacts and accepts only the existing timer and Buffer
negative protocols. Their original failed Session reports remain unchanged.
Checkouts and all failed evidence are retained, including on interruption.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import difflib
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from build_kernel import source_inputs
from check_kernel import acceptance_inputs, source_identity
import check_kernel_timer_negative as timer
import check_kernel_buffer_negative as append
from core0_common import Core0Error, load_json, repo_root, require_tools, sha256, write_json

KINDS = {
    "timer": ("tasks-development", "check_kernel_tasks.py", "check_kernel_timer_negative.py", 120, 8,
              "timer-disabled-F-v1", "missing-preemption-after-genuine-three-image-startup"),
    "append": ("service-normal", "check_kernel_buffer.py", "check_kernel_buffer_negative.py", 300, 60,
               "append-truncated-K-v1", "successful-append128-read128-final-FF-to-00"),
}
# Session starts its guest deadline only after a fresh complete artifact audit.
# Positive-control validation also runs before QEMU; retained-control/raw replay
# and owned cleanup run afterward. These finite host allowances do not extend
# any guest deadline and are still capped by Commands.remaining().
OBSERVATION_SETUP_SECONDS = 120
OBSERVATION_REPLAY_SECONDS = 60
CHECKOUTS = ("control", "timer", "append")
PROTOCOL = "kernel-source-mutations-K-v1"
NO_HASH = object()


def plan() -> tuple[tuple[str, str], ...]:
    return tuple((kind, opt) for kind in KINDS for opt in ("O0", "O2"))


def _module(kind: str):
    if kind == "timer": return timer
    if kind == "append": return append
    raise Core0Error("unknown closed source mutation")


def _paths(work: Path, kind: str, opt: str) -> dict[str, Path]:
    if (kind, opt) not in plan():
        raise Core0Error("unknown mutation/profile case")
    label = kind + "-" + opt
    roots = {name: work / "checkouts" / name for name in CHECKOUTS}
    return {"control_root": roots["control"], "mutant_root": roots[kind],
            "control_artifact": roots["control"] / "build/kernel/K-mutations" / label,
            "control_run": roots["control"] / "build/kernel/K-mutations" / (label + "-run"),
            "mutant_artifact": roots[kind] / "build/kernel/K-mutations" / label,
            "mutant_run": roots[kind] / "build/kernel/K-mutations" / (label + "-run")}


def _publish(work: Path, report: dict) -> None:
    temporary = work / "result.json.tmp"
    write_json(temporary, report)
    temporary.replace(work / "result.json")


def _proc(pid: int) -> dict | None:
    """Read PID start time as well as parent/group; reject PID reuse later."""
    try:
        fields = Path("/proc", str(pid), "stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "state": fields[0], "ppid": int(fields[1]),
                "pgid": int(fields[2]), "start": int(fields[19])}
    except (FileNotFoundError, ProcessLookupError):
        return None


def _processes() -> dict[int, dict]:
    result = {}
    for path in Path("/proc").iterdir():
        if path.name.isdecimal():
            value = _proc(int(path.name))
            if value is not None: result[value["pid"]] = value
    return result


def _descendants(processes: dict[int, dict], parent: int) -> dict[int, dict]:
    owned, parents = {}, {parent}
    while True:
        found = {pid: row for pid, row in processes.items() if row["ppid"] in parents and pid not in owned}
        if not found: return owned
        owned.update(found); parents.update(found)


class Commands:
    """Sequential commands, finite logs, and cleanup of this controller's children.

    Linux subreaping retains ownership when an interrupted command exits before
    its separately sessioned children. Pre-existing process families are excluded. First
    TERM reaches the command's own group so maintained guest contexts can unwind;
    only after a bounded grace do we kill still-owned PID/start-time identities.
    """
    def __init__(self, work: Path, report: dict, deadline: float, *, grace: float = 10):
        self.work, self.report, self.finish, self.grace = work, report, time.monotonic() + deadline, grace
        self.process = None
        self.owned: dict[int, dict] = {}
        self.baseline = {pid: row["start"] for pid, row in _descendants(_processes(), os.getpid()).items()}
        self.previous_subreaper = ctypes.c_int()
        self.libc = ctypes.CDLL(None, use_errno=True)
        if self.libc.prctl(37, ctypes.byref(self.previous_subreaper), 0, 0, 0) != 0 or self.libc.prctl(36, 1, 0, 0, 0) != 0:
            raise Core0Error("owned descendant cleanup requires Linux child subreaping")

    def remaining(self, *, reserve: float = 15) -> float:
        value = self.finish - time.monotonic() - reserve
        if value <= 0: raise Core0Error("mutation campaign exhausted its overall deadline")
        return value

    def inventory(self) -> dict[int, dict]:
        processes = _processes()
        candidates = _descendants(processes, self.process.pid) if self.process is not None else {}
        # Reparented descendants are direct children of this subreaper. We start
        # no unrelated child concurrently. An existing grandchild may become a
        # direct child when its parent exits; its PID/start identity stays excluded.
        candidates.update({pid: row for pid, row in processes.items()
                           if row["ppid"] == os.getpid() and self.baseline.get(pid) != row["start"]})
        for pid, row in candidates.items():
            if self.baseline.get(pid) == row["start"]: continue
            previous = self.owned.get(pid)
            if previous is not None and previous["start"] != row["start"]:
                raise Core0Error("owned child PID identity changed during cleanup")
            self.owned[pid] = row
        return {pid: processes[pid] for pid, row in self.owned.items()
                if pid in processes and processes[pid]["start"] == row["start"]}

    def _reap(self) -> list[dict]:
        reaped = []
        if self.process is not None and self.process.poll() is not None:
            reaped.append({"pid": self.process.pid, "returncode": self.process.returncode})
        for pid in self.owned:
            if self.process is not None and pid == self.process.pid: continue
            try:
                child, status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                continue  # Its live parent may already have reaped it.
            if child:
                reaped.append({"pid": child, "returncode": os.waitstatus_to_exitcode(status)})
        return reaped

    def cleanup(self, reason: str) -> dict:
        # Repeated host termination must not interrupt the bounded cleanup.
        previous = {number: signal.signal(number, signal.SIG_IGN)
                    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM)}
        try:
            return self._cleanup(reason)
        finally:
            for number, handler in previous.items(): signal.signal(number, handler)

    def _cleanup(self, reason: str) -> dict:
        owned = self.inventory()
        result = {"reason": reason, "owned": list(owned.values()), "term_groups": [],
                  "killed": [], "reaped": [], "remaining": []}
        if not owned: return result
        if self.process is not None and self.process.poll() is None:
            row = _proc(self.process.pid)
            if row and row["start"] == self.owned[self.process.pid]["start"] and row["pgid"] == row["pid"]:
                try:
                    os.killpg(row["pid"], signal.SIGTERM)
                    result["term_groups"].append(row["pid"])
                except ProcessLookupError: pass
        end = min(time.monotonic() + self.grace, self.finish - 3)
        while time.monotonic() < end:
            result["reaped"].extend(self._reap())
            if not self.inventory(): return result
            time.sleep(min(.05, max(0, end - time.monotonic())))
        # Inventory again immediately before each kill. No process name or
        # system-wide selector grants authority to kill an unrelated process.
        end = min(time.monotonic() + 3, self.finish)
        killed = set()
        def kill_remaining():
            for pid, row in self.inventory().items():
                current = _proc(pid)
                if current is None or current["start"] != row["start"] or current["state"] == "Z": continue
                try:
                    os.kill(pid, signal.SIGKILL)
                    if (pid, row["start"]) not in killed:
                        result["killed"].append({"pid": pid, "start": row["start"]}); killed.add((pid, row["start"]))
                except ProcessLookupError: pass
        # Even a late external signal must issue the kill, rather than skipping
        # it merely because the controller's observation deadline has elapsed.
        kill_remaining()
        result["reaped"].extend(self._reap())
        while time.monotonic() < end:
            kill_remaining()
            result["reaped"].extend(self._reap())
            if not self.inventory(): return result
            time.sleep(.02)
        result["remaining"] = list(self.inventory().values())
        return result

    def run(self, label: str, argv: list[str], cwd: Path, bound: float) -> dict:
        bound = min(bound, self.remaining())
        log = self.work / "logs" / (label + ".log")
        log.parent.mkdir(parents=True, exist_ok=True)
        row = {"label": label, "argv": argv, "cwd": str(cwd), "timeout_seconds": bound,
               "returncode": None, "log": str(log), "started_at": datetime.now(timezone.utc).isoformat()}
        self.report["commands"].append(row)
        begin = time.monotonic()
        try:
            with log.open("xb") as stream:
                self.process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                row["pid"] = self.process.pid
                self.inventory()
                try:
                    self.process.wait(timeout=bound)
                except subprocess.TimeoutExpired as error:
                    raise Core0Error("mutation command exceeded its bound: " + label) from error
                row["returncode"] = self.process.returncode
                if self.inventory():
                    raise Core0Error("mutation command left a live or unreaped owned descendant: " + label)
                if row["returncode"] != 0:
                    raise Core0Error("required mutation command failed: " + label)
        except BaseException as error:
            row["error"] = str(error)
            row["cleanup"] = self.cleanup("command-failure")
            if self.process is not None: row["returncode"] = self.process.poll()
            raise
        finally:
            row.update(elapsed_seconds=time.monotonic() - begin,
                       finished_at=datetime.now(timezone.utc).isoformat())
            if log.is_file(): row["log_sha256"] = sha256(log)
            _publish(self.work, self.report)
            self.process = None
        return row

    def close(self) -> dict:
        try:
            return self.cleanup("final-controller-sweep")
        finally:
            if self.libc.prctl(36, self.previous_subreaper.value, 0, 0, 0) != 0:
                raise Core0Error("mutation controller could not restore its child-subreaper state")


def _inventory(root: Path) -> dict:
    sources, consumers = source_inputs(root), acceptance_inputs(root)
    for value in (sources, consumers):
        if not value or any(not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                            for name, digest in value.items()):
            raise Core0Error("mutation campaign has a missing or malformed source/consumer inventory")
    return {"source_inputs": sources, "acceptance_inputs": consumers}


def _detached(root: Path) -> None:
    result = subprocess.run(("git", "symbolic-ref", "-q", "HEAD"), cwd=root, timeout=10,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 1 or result.stdout or result.stderr:
        raise Core0Error("mutation checkout is not a detached exact revision")


def _file(path: Path, expected=NO_HASH) -> str:
    if not path.is_file() or path.is_symlink():
        raise Core0Error("mandatory mutation evidence is absent or nonregular: " + str(path))
    value = sha256(path)
    if expected is not NO_HASH:
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or value != expected:
            raise Core0Error("mutation evidence changed or lacks its hash: " + str(path))
    return value


def _artifact(image: Path, *, identity: dict, sources: dict, dirty: list[str], config: str, opt: str) -> dict:
    build, provenance, audit = (load_json(image.parent / name) for name in ("build.json", "provenance.json", "audit.json"))
    for value in (build, provenance, audit):
        if (not isinstance(value, dict) or value.get("configuration") != config
                or value.get("optimization") != opt or value.get("stage") != "supervisor"):
            raise Core0Error("mutation artifact configuration/stage/optimization differs")
    if (build.get("status") != "BUILT" or audit.get("status") != "PASS"
            or build.get("provenance_sha256") != _file(image.parent / "provenance.json")
            or any(value.get("source_commit") != identity["commit"] or value.get("dirty_paths") != dirty
                   for value in (provenance, audit))
            or provenance.get("source_inputs") != sources or audit.get("image_sha256") != _file(image)):
        raise Core0Error("mutation image lacks its exact source and successful build/audit")
    artifacts = provenance.get("artifacts")
    if (not isinstance(artifacts, dict) or not artifacts or "image.elf" not in artifacts
            or build.get("artifacts") != artifacts):
        raise Core0Error("mutation compiled artifact inventory is absent or differs")
    for name, digest in artifacts.items():
        if (not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or not (image.parent / name).resolve().is_relative_to(image.parent)):
            raise Core0Error("mutation artifact inventory has an unsafe entry")
        _file(image.parent / name, digest)
    for label, value in (("build", provenance), ("audit", audit)):
        commands = value.get("commands")
        if not isinstance(commands, list) or not commands or any(type(row.get("returncode")) is not int or row["returncode"] for row in commands):
            raise Core0Error("mutation " + label + " command inventory is missing or failed")
    return {"image_sha256": _file(image), "build_sha256": _file(image.parent / "build.json"),
            "audit_sha256": _file(image.parent / "audit.json"),
            "provenance_sha256": _file(image.parent / "provenance.json"), "artifacts": artifacts}


def validate_case(row: dict, work: Path, identity: dict, sources: dict) -> dict:
    kind, opt = row.get("mutation"), row.get("optimization")
    paths = _paths(work, kind, opt)
    config, _, _, _, negative_bound, protocol, expected_failure = KINDS[kind]
    module = _module(kind)
    binding = module.source_binding(paths["mutant_root"], identity["commit"])
    if (binding["tree"] != identity["tree"] or binding["control_source_inputs"] != sources
            or row.get("configuration") != config or row.get("status") != "PASS"):
        raise Core0Error("mutation case source/configuration is not the exact selected control")
    control_path = paths["control_run"] / "result.json"
    image = paths["mutant_artifact"] / "image.elf"
    control_image = paths["control_artifact"] / "image.elf"
    control_report = load_json(control_path)
    if control_report.get("image") != str(control_image):
        raise Core0Error("mutation control refers to a reused or different image")
    artifacts = {"control": _artifact(control_image, identity=identity, sources=sources, dirty=[], config=config, opt=opt),
                 "mutant": _artifact(image, identity=identity, sources=binding["source_inputs"],
                                      dirty=[" M " + binding["mutation"]["path"]], config=config, opt=opt)}
    runners = module.runner_inputs(paths["mutant_root"])
    outer_path = paths["mutant_run"] / "result.json"
    inner_path = paths["mutant_run"] / "inner-session/result.json"
    retained = _file(inner_path)
    outer = load_json(outer_path)
    if (not isinstance(outer, dict) or outer.get("status") != "PASS" or outer.get("protocol") != protocol
            or outer.get("image") != str(image) or outer.get("timeout_seconds") != negative_bound
            or outer.get("inner_positive_checker_status") != "FAIL" or outer.get("source") != binding
            or outer.get("runner_inputs") != runners or outer.get("source_unchanged_after") is not True
            or outer.get("runners_unchanged_after") is not True
            or outer.get("observed_expected_failure") != expected_failure or outer.get("cleanup_errors")):
        raise Core0Error("mutation outer result does not qualify its exact retained inner failure")
    control = module.positive_control(control_path, binding, paths["mutant_root"], opt)
    if kind == "timer":
        failed = module.validate_failed_session(inner_path, image, binding=binding, runners=runners)
    else:
        failed = module.validate_failed_session(inner_path, image, binding=binding, runners=runners,
                                                optimization=opt, root=paths["mutant_root"])
    inner = load_json(inner_path)
    if (inner.get("image") != str(image) or inner.get("cleanup_errors")
            or failed.get("status") != "FAIL" or failed.get("sha256") != retained
            or outer.get("inner_session") != failed or outer.get("positive_control") != control):
        raise Core0Error("mutation inner FAIL/control was changed or has cleanup errors")
    expected_cleanup = {"explicit_host_stop": True, "process_group_killed": True,
                        "target_exited_before_cleanup": False, "process_reaped": True}
    if (inner.get("status") != "FAIL" or inner.get("returncode") != -9
            or inner.get("guest_live_before_cleanup") is not True or inner.get("cleanup") != expected_cleanup
            or any(type(flag) is not bool for flag in inner["cleanup"].values())
            or type(inner.get("pid")) is not int or inner["pid"] <= 0 or Path("/proc", str(inner["pid"])).exists()):
        raise Core0Error("mutation inner process was not actually live, killed and reaped")
    raw = failed.get("raw_artifacts")
    if not isinstance(raw, dict) or set(raw) != {"received.bin", "sent.bin", "stderr.bin"}:
        raise Core0Error("mutation raw corpus is incomplete")
    for name, digest in raw.items(): _file(inner_path.parent / name, digest)
    _file(inner_path, retained)
    return {"control": control, "inner_session": failed, "source": binding, "artifacts": artifacts,
            "control_result_sha256": _file(control_path), "negative_result_sha256": _file(outer_path)}


def _case_commands(paths: dict, kind: str, opt: str) -> list[tuple[str, list[str], Path, float]]:
    config, positive, negative, positive_bound, negative_bound, _, _ = KINDS[kind]
    label = kind + "-" + opt
    commands = []
    for role in ("control", "mutant"):
        root, artifact = paths[role + "_root"], paths[role + "_artifact"]
        image, output = artifact / "image.elf", paths[role + "_run"]
        commands.append((label + "-" + role + "-build",
                         [sys.executable, "scripts/build_kernel.py", "--opt-level", opt, "--stage", "supervisor",
                          "--configuration", config, "--output-dir", str(artifact), "--timeout", "300"], root, 300))
        commands.append((label + "-" + role + "-audit",
                         [sys.executable, "scripts/audit_kernel.py", str(artifact), "--timeout", "60"], root, 120))
        argv = [sys.executable, "scripts/" + (positive if role == "control" else negative),
                "--image", str(image), "--output-dir", str(output),
                "--timeout", str(positive_bound if role == "control" else negative_bound)]
        # The caller supplies the exact commit; the plan marker is never executed.
        if role == "mutant": argv += ["--positive-control", str(paths["control_run"] / "result.json"), "--expected-commit", "COMMIT"]
        guest_bound = positive_bound if role == "control" else negative_bound
        commands.append((label + "-" + role + "-observe", argv, root,
                         OBSERVATION_SETUP_SECONDS + guest_bound + OBSERVATION_REPLAY_SECONDS))
    return commands


def validate_campaign(path: Path, root: Path) -> dict:
    root, path = root.resolve(), path.resolve()
    work = path.parent
    try: relative = work.relative_to(root / "build/kernel")
    except ValueError as error: raise Core0Error("mutation evidence must be under the selected checkout build/kernel") from error
    if not relative.parts: raise Core0Error("mutation evidence cannot replace build/kernel")
    value = load_json(path)
    identity, inventory = source_identity(root), _inventory(root)
    if (not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("status") != "PASS"
            or type(value.get("schema_version")) is not int
            or value.get("protocol") != PROTOCOL or value.get("source") != identity
            or any(value.get(key) != item for key, item in inventory.items())
            or value.get("source_unchanged_after") is not True or value.get("acceptance_unchanged_after") is not True
            or type(value.get("deadline_seconds")) not in (int, float) or not 0 < value["deadline_seconds"] <= 2400
            or not math.isfinite(value["deadline_seconds"]) or value.get("cleanup_errors")
            or type(value.get("qemu_sessions")) is not int or value["qemu_sessions"] != 8
            or type(value.get("images")) is not int or value["images"] != 8
            or type(value.get("elapsed_seconds")) not in (int, float)
            or not math.isfinite(value["elapsed_seconds"]) or not 0 <= value["elapsed_seconds"] <= value["deadline_seconds"]):
        raise Core0Error("mutation aggregate lacks exact clean source, finite bounds or complete evidence")
    checkouts = value.get("checkouts")
    if not isinstance(checkouts, dict) or set(checkouts) != set(CHECKOUTS):
        raise Core0Error("mutation aggregate requires exactly three fresh checkouts")
    for name in CHECKOUTS:
        checkout = work / "checkouts" / name
        row = checkouts[name]
        if row.get("path") != str(checkout) or row.get("initial_source") != identity or row.get("initial_inventory") != inventory:
            raise Core0Error("mutation checkout initial source binding differs")
        _detached(checkout)
        if name == "control":
            if source_identity(checkout) != identity or _inventory(checkout) != inventory:
                raise Core0Error("clean control checkout changed during mutation qualification")
        else:
            bound = _module(name).source_binding(checkout, identity["commit"])
            if (bound != row.get("source") or bound["control_source_inputs"] != inventory["source_inputs"]
                    or acceptance_inputs(checkout) != inventory["acceptance_inputs"]):
                raise Core0Error("mutant checkout has another source/consumer change")
            _file(work / "mutations" / (name + ".diff"), row.get("diff_sha256"))
            source = bound["mutation"]["path"]
            original = (work / "checkouts/control" / source).read_text()
            changed = (checkout / source).read_text()
            expected_diff = "".join(difflib.unified_diff(original.splitlines(True), changed.splitlines(True),
                                                        fromfile=source, tofile=source))
            if (work / "mutations" / (name + ".diff")).read_text() != expected_diff:
                raise Core0Error("mutation review diff does not represent the canonical actual source change")
    rows = value.get("cases")
    if not isinstance(rows, list) or [(row.get("mutation"), row.get("optimization")) for row in rows] != list(plan()):
        raise Core0Error("mutation matrix is missing, reordered or duplicated")
    expected_commands = [("checkout-" + name, ["git", "worktree", "add", "--detach", str(work / "checkouts" / name), identity["commit"]], root, 60)
                         for name in CHECKOUTS]
    for row, (kind, opt) in zip(rows, plan()):
        facts = validate_case(row, work, identity, inventory["source_inputs"])
        if any(row.get(key) != item for key, item in facts.items()):
            raise Core0Error("mutation aggregate case differs from independently revalidated evidence")
        for label, argv, cwd, bound in _case_commands(_paths(work, kind, opt), kind, opt):
            expected_commands.append((label, [identity["commit"] if arg == "COMMIT" else arg for arg in argv], cwd, bound))
    commands = value.get("commands")
    if not isinstance(commands, list) or len(commands) != len(expected_commands):
        raise Core0Error("mutation command corpus is incomplete")
    for row, (label, argv, cwd, bound) in zip(commands, expected_commands):
        if (row.get("label") != label or row.get("argv") != argv or row.get("cwd") != str(cwd)
                or type(row.get("returncode")) is not int or row["returncode"] != 0 or row.get("cleanup")
                or type(row.get("timeout_seconds")) not in (int, float) or not 0 < row["timeout_seconds"] <= bound
                or type(row.get("pid")) is not int or row["pid"] <= 0 or Path("/proc", str(row["pid"])).exists()
                or row.get("log") != str(work / "logs" / (label + ".log"))):
            raise Core0Error("mutation command is unbound, failed or unreaped")
        _file(Path(row["log"]), row.get("log_sha256"))
    final = value.get("controller_cleanup")
    if not isinstance(final, dict) or final.get("remaining") or final.get("owned") or final.get("killed"):
        raise Core0Error("mutation controller did not finish with no owned children")
    return value


def check(*, root: Path, work_dir: Path, expected_commit: str, deadline: float = 2400) -> dict:
    begin = time.monotonic()
    root = root.resolve()
    requested = root / work_dir
    if requested.exists() or requested.is_symlink():
        raise Core0Error("refusing an existing mutation output path")
    work = requested.resolve()
    try: relative = work.relative_to(root / "build/kernel")
    except ValueError as error: raise Core0Error("mutation output must be a fresh build/kernel subdirectory") from error
    if (not relative.parts or work.exists() or work.is_symlink()
            or not re.fullmatch(r"[0-9a-f]{40}", expected_commit)
            or type(deadline) not in (int, float) or not math.isfinite(deadline) or not 0 < deadline <= 2400):
        raise Core0Error("mutation controller requires an unused output, exact commit and deadline at most2400seconds")
    # Before any checkout or target mutation, the invoking source is committed,
    # clean and includes this exact controller and its acceptance consumers.
    identity = source_identity(root)
    if identity["commit"] != expected_commit: raise Core0Error("mutation source HEAD differs from the requested exact commit")
    inventory = _inventory(root)
    if inventory["acceptance_inputs"].get("scripts/check_kernel_mutations.py") != sha256(Path(__file__)):
        raise Core0Error("mutation controller is not the committed selected consumer")
    require_tools(("git", "nix", "lake", "lean", "opt", "llc", "clang", "ld.lld",
                   "llvm-readelf", "llvm-objcopy", "llvm-objdump", "qemu-system-riscv64", "dtc"))
    if time.monotonic() - begin >= deadline:
        raise Core0Error("mutation campaign exhausted its deadline during clean source validation")
    work.mkdir(parents=True)
    report = {"schema_version": 1, "status": "FAIL", "protocol": PROTOCOL,
              "artifact_category": "kernel-K-source-mutation-acceptance", "source": identity, **inventory,
              "deadline_seconds": deadline, "started_at": datetime.now(timezone.utc).isoformat(),
              "commands": [], "checkouts": {}, "cases": [], "images": 0, "qemu_sessions": 0}
    _publish(work, report)
    runner, previous = None, {}
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    def interrupted(number, _):
        raise Core0Error("mutation controller interrupted by host signal " + str(number))
    try:
        remaining = deadline - (time.monotonic() - begin)
        runner = Commands(work, report, remaining)
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM): previous[number] = signal.signal(number, interrupted)
        # The one absolute budget includes TERM grace and reaping. Stop work
        # fifteen seconds before its end, preserving that finite cleanup margin.
        signal.setitimer(signal.ITIMER_REAL, max(.001, deadline - (time.monotonic() - begin) - 15))
        for name in CHECKOUTS:
            checkout = work / "checkouts" / name
            if checkout.exists() or checkout.is_symlink(): raise Core0Error("refusing an existing mutation checkout")
            runner.run("checkout-" + name, ["git", "worktree", "add", "--detach", str(checkout), expected_commit], root, 60)
            if any((checkout / name).exists() or (checkout / name).is_symlink() for name in (".lake", "build")):
                raise Core0Error("fresh detached checkout contains earlier build outputs")
            _detached(checkout)
            initial, actual = source_identity(checkout), _inventory(checkout)
            if initial != identity or actual != inventory: raise Core0Error("fresh mutation checkout differs from selected source")
            report["checkouts"][name] = {"path": str(checkout), "initial_source": initial, "initial_inventory": actual}
        for kind in ("timer", "append"):
            checkout = work / "checkouts" / kind
            module = _module(kind)
            source = checkout / (module.FIRMWARE if kind == "timer" else module.SERVER)
            original = source.read_text()
            source.write_text((module.timer_disabled_source if kind == "timer" else module.append_truncated_source)(original))
            bound = module.source_binding(checkout, expected_commit)
            if bound["control_source_inputs"] != inventory["source_inputs"]: raise Core0Error("mutation baseline differs from selected source")
            # Diff is retained for review; canonical source_binding remains the
            # authority for the exact actual mutated bytes.
            diff = work / "mutations" / (kind + ".diff")
            diff.parent.mkdir(parents=True, exist_ok=True)
            diff.write_text("".join(difflib.unified_diff(original.splitlines(True), source.read_text().splitlines(True),
                                                       fromfile=bound["mutation"]["path"], tofile=bound["mutation"]["path"])))
            report["checkouts"][kind].update(source=bound, diff_sha256=sha256(diff))
        for kind, opt in plan():
            paths = _paths(work, kind, opt)
            for label, argv, cwd, bound in _case_commands(paths, kind, opt):
                runner.run(label, [expected_commit if arg == "COMMIT" else arg for arg in argv], cwd, bound)
            row = {"mutation": kind, "optimization": opt, "configuration": KINDS[kind][0], "status": "PASS"}
            report["cases"].append(row)
            row.update(validate_case(row, work, identity, inventory["source_inputs"]))
            report["images"] += 2; report["qemu_sessions"] += 2
            _publish(work, report); runner.remaining()
        if source_identity(root) != identity or _inventory(root) != inventory:
            raise Core0Error("invoking source/acceptance consumers changed during mutation campaign")
        report.update(source_unchanged_after=True, acceptance_unchanged_after=True)
    except BaseException as error:
        report.update(error=str(error), failure_category="mutation-campaign-evidence-failure")
    finally:
        # An additional signal must not interrupt bounded cleanup and erase its
        # retained failure; every child operation still has its own finite bound.
        for number in previous: signal.signal(number, signal.SIG_IGN)
        signal.setitimer(signal.ITIMER_REAL, 0)
        if runner is not None:
            try:
                report["controller_cleanup"] = runner.close()
                if report["controller_cleanup"]["remaining"] or report["controller_cleanup"]["owned"]:
                    report.setdefault("error", "mutation controller retained unexpected owned children")
            except Exception as error:
                report.setdefault("error", str(error)); report["cleanup_errors"] = [str(error)]
        report.update(elapsed_seconds=time.monotonic() - begin, finished_at=datetime.now(timezone.utc).isoformat())
        if "error" not in report: report["status"] = "PASS"
        _publish(work, report)
    try:
        if report["status"] == "PASS":
            try:
                for number in previous: signal.signal(number, interrupted)
                remaining = deadline - (time.monotonic() - begin) - 15
                if remaining <= 0: raise Core0Error("mutation campaign exceeded its deadline before final validation")
                signal.setitimer(signal.ITIMER_REAL, remaining)
                validate_campaign(work / "result.json", root)
                if time.monotonic() - begin > deadline: raise Core0Error("mutation final validation exceeded its deadline")
            except Exception as error:
                report.update(status="FAIL", error=str(error), failure_category="mandatory-mutation-evidence")
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                report["elapsed_seconds"] = time.monotonic() - begin
                _publish(work, report)
    finally:
        for number, handler in previous.items(): signal.signal(number, handler)
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--deadline", type=float, default=2400)
    args = parser.parse_args()
    try:
        value = check(root=repo_root(), work_dir=args.work_dir, expected_commit=args.expected_commit, deadline=args.deadline)
        print(value["status"] + ": " + value.get("error", "four fresh source mutations qualified; original inner FAILs retained"))
        return 0 if value["status"] == "PASS" else 1
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        print("FAIL: " + str(error)); return 1


if __name__ == "__main__": raise SystemExit(main())
