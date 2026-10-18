#!/usr/bin/env python3
"""Local, fail-closed action storage for host orchestration.

The caller declares the complete compilation dependency closure and path semantics
in ``action``. A producer consumes only the supplied private input snapshot, writes
every declared output, and returns metadata about commands it actually executed.
The cache records production separately from today's admission decision. It never
claims that artifact production constitutes a functional test.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
from typing import Callable, Iterator
import uuid
from itertools import islice

SCHEMA = "lemma-action-cache/1"
RECEIPT_SCHEMA = "lemma-action-producer/1"
ADMISSION_SCHEMA = "lemma-action-admission/1"


class CacheError(RuntimeError):
    """An action or its retained result cannot be admitted."""


def _json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _regular(path: Path) -> os.stat_result:
    result = path.lstat()
    if not stat.S_ISREG(result.st_mode):
        raise CacheError(f"expected a regular, non-symlink file: {path}")
    return result


def _inventory(path: Path) -> dict:
    info = _regular(path)
    return {"sha256": file_hash(path), "size": info.st_size,
            "executable": bool(info.st_mode & 0o111)}


def _logical(name: str) -> str:
    path = Path(name)
    if (not isinstance(name, str) or not name or path.is_absolute()
            or ".." in path.parts or path.as_posix() != name or name == "."):
        raise CacheError(f"invalid logical file name: {name!r}")
    return name


def _atomic(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_if_changed(path: Path, data: bytes | str) -> bool:
    """Atomically replace generated files only when their bytes change."""
    path = Path(path)
    payload = data.encode() if isinstance(data, str) else data
    if path.is_file() and not path.is_symlink() and path.read_bytes() == payload:
        return False
    _atomic(path, payload)
    return True


def process_identity(pid: int | None = None) -> dict:
    """Linux process ownership includes boot and /proc start ticks, not PID alone."""
    pid = os.getpid() if pid is None else pid
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "start_ticks": fields[19],
                "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
    except (OSError, IndexError):
        return {"pid": pid, "start_ticks": None, "boot_id": None}


def is_process_alive(owner: dict) -> bool:
    try:
        pid = int(owner["pid"])
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        return bool(state not in {"Z", "X"} and owner.get("start_ticks") and owner.get("boot_id")
                    and process_identity(pid) == owner)
    except (OSError, IndexError, KeyError, TypeError, ValueError):
        return False


def source_provenance(root: Path) -> dict:
    """Record checkout identity without making Git history a compilation key."""
    result = {"checkout": str(Path(root).resolve())}
    for name, arguments in (("commit", ["rev-parse", "HEAD"]),
                            ("branch", ["branch", "--show-current"]),
                            ("status", ["status", "--porcelain", "--untracked-files=no"])):
        try:
            value = subprocess.run(["git", "-C", str(root), *arguments],
                                   capture_output=True, text=True, timeout=10,
                                   check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            value = None
        result[name] = value
    return result


def tool_identity(command: str) -> dict:
    """Identify the actual executable; callers also declare consumed dependencies."""
    resolved = shutil.which(str(command))
    if resolved is None:
        raise CacheError(f"required action tool is unavailable: {command}")
    executable = Path(resolved).resolve(strict=True)
    invoked_as = str(Path(resolved).absolute())
    version = subprocess.run([invoked_as, "--version"], capture_output=True,
                             timeout=15, check=True)
    return {"path": str(executable), "invoked_as": invoked_as, "sha256": file_hash(executable),
            "version_stdout": version.stdout.decode(errors="replace"),
            "version_stderr": version.stderr.decode(errors="replace")}


@dataclass(frozen=True)
class ActionWorkspace:
    directory: Path
    inputs: dict[str, Path]
    outputs: dict[str, Path]


class ActionCache:
    def __init__(self, repository_root: Path, directory: Path | None = None,
                 fresh: bool = False):
        self.repository_root = Path(repository_root).resolve()
        self.directory = Path(directory or self.repository_root / "build/action-cache").resolve()
        self.fresh = fresh
        for name in ("actions", "objects", "receipts", "locks", "work", "quarantine", "poisoned"):
            (self.directory / name).mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _lock(self, key: str, blocking: bool = True) -> Iterator[bool]:
        with (self.directory / "locks" / f"{key}.lock").open("a+b") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    @contextmanager
    def _activity(self, exclusive: bool = False) -> Iterator[bool]:
        """Protect complete running actions from storage reclamation."""
        with (self.directory / "locks" / "activity.lock").open("a+b") as stream:
            try:
                mode = fcntl.LOCK_EX | fcntl.LOCK_NB if exclusive else fcntl.LOCK_SH
                fcntl.flock(stream, mode)
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _load_entry(self, key: str, request: dict | None = None) -> tuple[dict, dict]:
        path = self.directory / "actions" / f"{key}.json"
        _regular(path)
        entry = json.loads(path.read_bytes())
        if (not isinstance(entry, dict)
                or set(entry) != {"schema", "action_key", "request", "outputs", "producer_receipt_id"}
                or entry["schema"] != SCHEMA or entry["action_key"] != key
                or not isinstance(entry["request"], dict)
                or set(entry["request"]) != {"schema", "action", "inputs", "output_names"}
                or entry["request"]["schema"] != SCHEMA
                or not isinstance(entry["request"]["action"], dict)
                or not isinstance(entry["request"]["inputs"], dict)
                or not isinstance(entry["request"]["output_names"], list)
                or _digest(_json(entry["request"])) != key
                or (request is not None and entry["request"] != request)):
            raise CacheError("incompatible or conflicting action manifest")
        outputs = entry["outputs"]
        if (not isinstance(outputs, dict) or not outputs
                or sorted(outputs) != entry["request"]["output_names"]):
            raise CacheError("incomplete action output inventory")
        receipt_id = entry["producer_receipt_id"]
        if not isinstance(receipt_id, str) or len(receipt_id) != 64 or any(
                ch not in "0123456789abcdef" for ch in receipt_id):
            raise CacheError("invalid producer receipt identity")
        receipt_path = self.directory / "receipts" / f"{receipt_id}.json"
        _regular(receipt_path)
        receipt_bytes = receipt_path.read_bytes()
        receipt = json.loads(receipt_bytes)
        if (not isinstance(receipt, dict) or _digest(receipt_bytes) != receipt_id or receipt["schema"] != RECEIPT_SCHEMA
                or receipt["action_key"] != key or receipt["request"] != entry["request"]
                or receipt["outputs"] != outputs or receipt["result"] != "success"
                or receipt["input_archive_sha256"] != _digest(_json(entry["request"]["inputs"]))):
            raise CacheError("producer receipt does not certify this action")
        for name, item in [*outputs.items(), *entry["request"]["inputs"].items()]:
            _logical(name)
            if (not isinstance(item, dict) or set(item) != {"sha256", "size", "executable"}
                    or not isinstance(item["sha256"], str) or len(item["sha256"]) != 64
                    or type(item["size"]) is not int or item["size"] < 0
                    or type(item["executable"]) is not bool
                    or any(ch not in "0123456789abcdef" for ch in item["sha256"])):
                raise CacheError("malformed output inventory")
            obj = self.directory / "objects" / item["sha256"]
            # Executability belongs to the named output; blobs store only bytes.
            actual = _inventory(obj)
            if actual["sha256"] != item["sha256"] or actual["size"] != item["size"]:
                raise CacheError(f"corrupt cached input/output: {name}")
        return entry, receipt

    def _store_blob(self, source: Path, item: dict) -> None:
        obj = self.directory / "objects" / item["sha256"]
        try:
            current = _inventory(obj)
            valid = current["sha256"] == item["sha256"] and current["size"] == item["size"]
        except (CacheError, OSError):
            valid = False
        if not valid:
            # Concurrent publication of identical content is harmless. Admission
            # hashes the object again rather than trusting its content address.
            _atomic(obj, source.read_bytes(), 0o444)

    def _quarantine(self, key: str, reason: str) -> None:
        target = self.directory / "quarantine" / f"{key}.{uuid.uuid4().hex}"
        target.mkdir()
        path = self.directory / "actions" / f"{key}.json"
        if path.exists() or path.is_symlink():
            os.replace(path, target / "action.json")
        _atomic(target / "rejection.json", _json({"reason": reason, "time": time.time()}))

    def _materialize(self, outputs: dict[str, Path], inventory: dict) -> None:
        pending = []
        try:
            for name, destination in outputs.items():
                destination = Path(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
                os.close(fd)
                temporary = Path(temporary)
                pending.append((temporary, destination))
                shutil.copyfile(self.directory / "objects" / inventory[name]["sha256"], temporary)
                os.chmod(temporary, 0o755 if inventory[name]["executable"] else 0o644)
                if _inventory(temporary) != inventory[name]:
                    raise CacheError(f"output changed during materialization: {name}")
            for temporary, destination in pending:
                os.replace(temporary, destination)
        finally:
            for temporary, _ in pending:
                temporary.unlink(missing_ok=True)

    def run(self, action: dict, inputs: dict[str, Path], outputs: dict[str, Path],
            producer: Callable[[ActionWorkspace], dict], provenance: dict | None = None,
            validator: dict | None = None) -> dict:
        with self._activity():
            return self._run(action, inputs, outputs, producer, provenance, validator)

    def _run(self, action: dict, inputs: dict[str, Path], outputs: dict[str, Path],
             producer: Callable[[ActionWorkspace], dict], provenance: dict | None,
             validator: dict | None) -> dict:
        if not isinstance(action, dict) or not action or not outputs:
            raise CacheError("actions need an explicit recipe identity and nonempty outputs")
        # A concurrently edited caller dictionary must not change a keyed request.
        action = json.loads(_json(action))
        for name in (*inputs, *outputs):
            _logical(name)
        if len({str(Path(path).resolve()) for path in outputs.values()}) != len(outputs):
            raise CacheError("output destinations must be distinct")
        work = self.directory / "work" / uuid.uuid4().hex
        work.mkdir()
        owner = process_identity()
        _atomic(work / "owner.json", _json({"owner": owner, "started_at": time.time()}))
        key = None
        try:
            snapshots = {}
            input_inventory = {}
            for name, source in sorted(inputs.items()):
                source = Path(source)
                _regular(source)
                snapshot = work / "inputs" / name
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                # Copy first, then key the actual bytes the producer will consume.
                # Edits to live source after this point cannot affect this action.
                shutil.copyfile(source, snapshot, follow_symlinks=False)
                item = _inventory(snapshot)
                executable = bool(source.stat().st_mode & 0o111)
                os.chmod(snapshot, 0o555 if executable else 0o444)
                item["executable"] = executable
                input_inventory[name] = item
                snapshots[name] = snapshot
            request = {"schema": SCHEMA, "action": action, "inputs": input_inventory,
                       "output_names": sorted(outputs)}
            key = _digest(_json(request))
            _atomic(work / "owner.json", _json({"owner": owner, "started_at": time.time(),
                                                "action_key": key}))
            with self._lock(key):
                poison = self.directory / "poisoned" / f"{key}.json"
                if poison.exists() or poison.is_symlink():
                    raise CacheError(f"action key is poisoned by conflicting production: {key}; inspect {poison}")
                prior = None
                rejection = None
                try:
                    prior = self._load_entry(key, request)
                except FileNotFoundError:
                    if (self.directory / "actions" / f"{key}.json").exists():
                        rejection = "incomplete entry: missing output or producer receipt"
                        self._quarantine(key, rejection)
                except (CacheError, OSError, ValueError, KeyError, TypeError) as error:
                    rejection = str(error)
                    self._quarantine(key, rejection)
                if prior is not None and not self.fresh:
                    entry, receipt = prior
                    self._materialize(outputs, entry["outputs"])
                    return self._admission(key, "reused", "validated complete result", entry,
                                           receipt, validator, None)
                staged = {name: work / "outputs" / name for name in outputs}
                for path in staged.values():
                    path.parent.mkdir(parents=True, exist_ok=True)
                started = time.time()
                executed = producer(ActionWorkspace(work, snapshots, staged))
                if not isinstance(executed, dict):
                    raise CacheError("producer must return actual execution metadata")
                if {name: _inventory(path) for name, path in snapshots.items()} != input_inventory:
                    raise CacheError("producer modified its declared input snapshot")
                inventory = {name: _inventory(path) for name, path in sorted(staged.items())}
                actual_files = set()
                for path in (work / "outputs").rglob("*"):
                    info = path.lstat()
                    if stat.S_ISDIR(info.st_mode):
                        continue
                    _regular(path)
                    actual_files.add(path.relative_to(work / "outputs").as_posix())
                if actual_files != set(staged):
                    raise CacheError("producer output inventory contains undeclared files")
                receipt = {"schema": RECEIPT_SCHEMA, "action_key": key, "request": request,
                           "outputs": inventory, "result": "success", "executed": executed,
                           "input_archive_sha256": _digest(_json(input_inventory)),
                           "provenance": provenance or {}, "owner": owner,
                           "started_at": started, "completed_at": time.time()}
                receipt_id = _digest(_json(receipt))
                _atomic(self.directory / "receipts" / f"{receipt_id}.json", _json(receipt), 0o444)
                if prior is not None and prior[0]["outputs"] != inventory:
                    target = self.directory / "quarantine" / f"{key}.conflict.{uuid.uuid4().hex}"
                    shutil.copytree(work, target)
                    _atomic(target / "producer.json", _json(receipt))
                    _atomic(target / "original-producer.json", _json(prior[1]))
                    for name,item in prior[0]["outputs"].items():
                        archived = target / "original-outputs" / name
                        archived.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copyfile(self.directory/"objects"/item["sha256"],archived)
                    _atomic(poison, _json({"schema":SCHEMA,"action_key":key,
                        "original_producer_receipt_id":prior[0]["producer_receipt_id"],
                        "conflicting_producer_receipt_id":receipt_id,"conflict_archive":str(target),
                        "reason":"identical declared inputs produced divergent outputs; explicit diagnosis/repair required"}))
                    raise CacheError(f"fresh action conflicts with retained result: {key}; {target}")
                for name, item in input_inventory.items():
                    self._store_blob(snapshots[name], item)
                for name, item in inventory.items():
                    self._store_blob(staged[name], item)
                entry = {"schema": SCHEMA, "action_key": key, "request": request,
                         "outputs": inventory, "producer_receipt_id": receipt_id}
                if prior is None:
                    _atomic(self.directory / "actions" / f"{key}.json", _json(entry), 0o444)
                self._materialize(outputs, inventory)
                reason = "fresh requested" if self.fresh else "no admitted result"
                if rejection:
                    reason = f"rejected: {rejection}"
                return self._admission(key, "fresh", reason, entry, receipt, validator,
                                       receipt["completed_at"] - started)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _admission(self, key: str, status: str, reason: str, entry: dict, receipt: dict,
                   validator: dict | None, elapsed: float | None) -> dict:
        return {"schema": ADMISSION_SCHEMA, "action_key": key, "status": status,
                "reason": reason, "admitted_at": time.time(),
                "producer_receipt_id": entry["producer_receipt_id"], "producer": receipt,
                "validator": validator if validator is not None else {
                    "implementation_sha256": file_hash(Path(__file__).resolve())},
                "outputs": entry["outputs"], "duration_seconds": elapsed}

    def inspect(self, limit: int = 100) -> dict:
        """Bounded inspection. It never interprets an old producer PID as live work."""
        entries = []
        if limit < 1 or limit > 10000:
            raise CacheError("inspection limit must be 1..10000")
        for path in islice((self.directory / "actions").glob("*.json"), limit):
            key = path.stem
            with self._lock(key, blocking=False) as acquired:
                if not acquired:
                    entries.append({"action_key": key, "status": "active"})
                    continue
                poison = self.directory/"poisoned"/f"{key}.json"
                if poison.exists() or poison.is_symlink():
                    entries.append({"action_key":key,"status":"poisoned",
                                    "reason":"conflicting production requires explicit diagnosis/repair"})
                    continue
                try:
                    entry, _ = self._load_entry(key)
                    entries.append({"action_key": key, "status": "valid",
                                    "outputs": entry["outputs"],
                                    "producer_receipt_id": entry["producer_receipt_id"]})
                except (CacheError, OSError, ValueError, KeyError, TypeError) as error:
                    entries.append({"action_key": key, "status": "rejected", "reason": str(error)})
        work = []
        for path in islice((self.directory / "work").iterdir(), limit):
            try:
                data = json.loads((path / "owner.json").read_bytes())
                work.append({"path": str(path), **data, "active": is_process_alive(data["owner"])})
            except (OSError, ValueError, KeyError, TypeError):
                work.append({"path": str(path), "active": False, "reason": "invalid ownership"})
        poisoned = []
        for path in islice((self.directory/"poisoned").glob("*.json"),limit):
            try:
                _regular(path)
                data = json.loads(path.read_bytes())
                poisoned.append({"action_key":path.stem,"marker":str(path),**data})
            except (CacheError,OSError,ValueError,TypeError):
                poisoned.append({"action_key":path.stem,"marker":str(path),"reason":"invalid poison marker; reuse remains forbidden"})
        return {"schema": SCHEMA, "directory": str(self.directory), "entries": entries,
                "work": work, "poisoned":poisoned, "limit": limit}

    def cleanup(self, max_entries: int = 100, older_than_seconds: float = 86400,
                pinned_keys: tuple[str, ...] = ()) -> dict:
        """Bounded eviction of ephemeral storage; pinned mappings keep their closure.

        External evidence paths are never traversed. Published claims must own
        their source archive, producer receipt and output copies independently.
        Unknown/corrupt reference metadata prevents blob reclamation.
        """
        if max_entries < 1 or max_entries > 10000 or older_than_seconds < 0:
            raise CacheError("cleanup limit must be 1..10000 and age nonnegative")
        with self._activity(exclusive=True) as acquired:
            if not acquired:
                return {"schema": SCHEMA, "removed": [], "bytes_reclaimed": 0,
                        "objects_retained": True, "reason": "active actions"}
            return self._cleanup(max_entries, older_than_seconds, pinned_keys)

    def _cleanup(self, max_entries: int, older_than_seconds: float,
                 pinned_keys: tuple[str, ...]) -> dict:
        now = time.time()
        removed = []
        reclaimed = 0
        for path in islice((self.directory / "actions").glob("*.json"), max_entries):
            if path.stem in pinned_keys or now - path.lstat().st_mtime < older_than_seconds:
                continue
            with self._lock(path.stem, blocking=False) as acquired:
                if acquired and path.exists():
                    path.unlink()
                    removed.append(str(path))
        for path in islice((self.directory / "work").iterdir(), max_entries):
            if path.is_symlink() or not path.is_dir():
                continue
            try:
                data = json.loads((path / "owner.json").read_bytes())
                if is_process_alive(data["owner"]) or now - data["started_at"] < older_than_seconds:
                    continue
            except (OSError, ValueError, KeyError, TypeError):
                continue  # Unknown ownership is not permission to delete work.
            key = data.get("action_key")
            if key:
                with self._lock(key, blocking=False) as acquired:
                    if acquired:
                        shutil.rmtree(path)
                        removed.append(str(path))
            else:
                shutil.rmtree(path)
                removed.append(str(path))
        # A bounded complete reference scan is required before deleting content.
        scan_limit = 10000
        action_paths = list(islice((self.directory / "actions").glob("*.json"), scan_limit + 1))
        receipt_paths = list(islice((self.directory / "receipts").glob("*.json"), scan_limit + 1))
        if len(action_paths) > scan_limit or len(receipt_paths) > scan_limit:
            return {"schema": SCHEMA, "removed": removed, "bytes_reclaimed": reclaimed,
                    "objects_retained": True, "reason": "reference scan limit reached"}
        try:
            retained_receipts = set()
            for path in action_paths:
                _regular(path)
                entry = json.loads(path.read_bytes())
                if entry["schema"] != SCHEMA or entry["action_key"] != path.stem:
                    raise CacheError("incompatible reference manifest")
                receipt_id = entry["producer_receipt_id"]
                if (not isinstance(receipt_id, str) or len(receipt_id) != 64
                        or any(ch not in "0123456789abcdef" for ch in receipt_id)
                        or not (self.directory / "receipts" / f"{receipt_id}.json").is_file()):
                    raise CacheError("missing producer reference metadata")
                retained_receipts.add(receipt_id)
            removed_receipts = 0
            for path in receipt_paths:
                if (removed_receipts < max_entries and path.stem not in retained_receipts
                        and now - path.lstat().st_mtime >= older_than_seconds):
                    reclaimed += path.lstat().st_size
                    path.unlink()
                    removed.append(str(path))
                    removed_receipts += 1
            referenced = set()
            for path in receipt_paths:
                if not path.exists():
                    continue
                _regular(path)
                payload = path.read_bytes()
                receipt = json.loads(payload)
                if receipt["schema"] != RECEIPT_SCHEMA or _digest(payload) != path.stem:
                    raise CacheError("corrupt producer reference metadata")
                for item in [*receipt["outputs"].values(), *receipt["request"]["inputs"].values()]:
                    digest = item["sha256"]
                    if (not isinstance(digest, str) or len(digest) != 64
                            or any(ch not in "0123456789abcdef" for ch in digest)):
                        raise CacheError("invalid blob reference")
                    referenced.add(digest)
        except (CacheError, OSError, ValueError, KeyError, TypeError) as error:
            return {"schema": SCHEMA, "removed": removed, "bytes_reclaimed": reclaimed,
                    "objects_retained": True, "reason": f"unsafe reference scan: {error}"}
        for path in islice((self.directory / "objects").iterdir(), max_entries):
            if path.name in referenced or now - path.lstat().st_mtime < older_than_seconds:
                continue
            if path.is_symlink() or not path.is_file():
                continue
            reclaimed += path.lstat().st_size
            path.unlink()
            removed.append(str(path))
        return {"schema": SCHEMA, "removed": removed, "bytes_reclaimed": reclaimed,
                "objects_retained": False, "reason": "bounded cleanup complete"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--older-than-seconds", type=float, default=86400)
    parser.add_argument("--pin-action", action="append", default=[],
                        help="preserve this action and its producer/input/output closure")
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 10000 or args.older_than_seconds < 0:
        parser.error("limit must be 1..10000 and age must be nonnegative")
    cache = ActionCache(args.root, args.cache_dir)
    result = (cache.cleanup(args.limit, args.older_than_seconds, tuple(args.pin_action)) if args.cleanup
              else cache.inspect(args.limit))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
