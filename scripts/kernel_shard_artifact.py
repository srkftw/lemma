#!/usr/bin/env python3
"""Bounded data-only transport of retained kernel shard evidence.

The archive preserves regular-file modes that Actions artifact ZIP transport
normalizes. It supplies no compilation, execution, audit or acceptance result.
Only the declared top-level ephemeral cache is omitted.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile

SCHEMA = "lemma-kernel-shard-artifact/1"
EXTRACTION_SCHEMA = "lemma-kernel-shard-extraction/1"
BLOCK = 512


class ArtifactError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    members: int = 50_000
    file_bytes: int = 128 * 1024 * 1024
    total_bytes: int = 1024 * 1024 * 1024
    archive_bytes: int = 2 * 1024 * 1024 * 1024

    def __post_init__(self):
        if any(type(value) is not int or value <= 0 for value in vars(self).values()):
            raise ArtifactError("artifact limits must be positive integers")


DEFAULT_LIMITS = Limits()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_name(name: str) -> str:
    if (not isinstance(name, str) or not name or "\\" in name or "\x00" in name
            or name.startswith("/") or any(part in ("", ".", "..") for part in name.split("/"))
            or PurePosixPath(name).as_posix() != name):
        raise ArtifactError("archive name is not a canonical relative file path")
    return name


def _path(root: Path, value: Path) -> Path:
    value = Path(value)
    if ".." in value.parts:
        raise ArtifactError("artifact path contains parent traversal")
    path = value if value.is_absolute() else root / value
    if not path.is_relative_to(root / "build") or path == root / "build":
        raise ArtifactError("artifact paths must remain inside this repository's build directory")
    for parent in [*reversed(path.parents), path]:
        if parent.is_relative_to(root) and parent.is_symlink():
            raise ArtifactError("artifact path contains a symlink")
    return path


def _shard(root: Path, value: Path, optimization: str) -> Path:
    if optimization not in ("O0", "O2"):
        raise ArtifactError("artifact optimization must be O0 or O2")
    path = _path(root, value)
    base = root / "build/kernel"
    if (not path.is_relative_to(base) or len(path.relative_to(base).parts) < 3
            or path.parts[-2:] != ("shards", optimization)):
        raise ArtifactError("shard must be an isolated build/kernel campaign/shards/optimization directory")
    return path


def _unused(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise ArtifactError("refusing to replace an existing artifact or extraction destination")


def _regular(path: Path) -> os.stat_result:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ArtifactError("artifact input is not a regular file")
    return info


def _parents(root: Path, parent: Path) -> None:
    if parent != root / "build":
        _path(root, parent)
    elif parent.is_symlink():
        raise ArtifactError("artifact parent contains a symlink")
    parent.mkdir(parents=True, exist_ok=True)
    if parent != root / "build":
        _path(root, parent)


def _write_json(path: Path, value: dict) -> None:
    try:
        with path.open("x") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
    except FileExistsError as error:
        raise ArtifactError("refusing to replace an existing receipt") from error


def _read_json(path: Path) -> dict:
    _regular(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ArtifactError("artifact manifest is too large")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ArtifactError("duplicate artifact manifest key")
            value[key] = item
        return value
    value = json.loads(path.read_text(), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ArtifactError("artifact manifest must be an object")
    return value


def _validate_files(files: dict, limits: Limits) -> tuple[int, int]:
    if not isinstance(files, dict) or not 0 < len(files) <= limits.members:
        raise ArtifactError("artifact file count is empty or exceeds its bound")
    total = 0
    for name, item in files.items():
        _relative_name(name)
        if name.split("/")[0] == "cache":
            raise ArtifactError("ephemeral cache cannot enter retained shard transport")
        if (not isinstance(item, dict) or set(item) != {"sha256", "size", "mode"}
                or not isinstance(item["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
                or type(item["size"]) is not int or not 0 <= item["size"] <= limits.file_bytes
                or type(item["mode"]) is not int or not 0 <= item["mode"] <= 0o777):
            raise ArtifactError("artifact file digest, size or ordinary permission mode is invalid")
        total += item["size"]
        if total > limits.total_bytes:
            raise ArtifactError("artifact total file bytes exceed their bound")
        if any(parent.as_posix() in files for parent in PurePosixPath(name).parents if parent.as_posix() != "."):
            raise ArtifactError("archive file name conflicts with a directory prefix")
    if total <= 0 or "result.json" not in files:
        raise ArtifactError("retained shard transport requires nonempty bytes and its result.json")
    return len(files), total


def inventory(root: Path, shard: Path, *, limits: Limits = DEFAULT_LIMITS) -> dict:
    files, total = {}, 0
    for directory, dirs, names in os.walk(shard, followlinks=False):
        current = Path(directory)
        dirs[:] = sorted(name for name in dirs if current != shard or name != "cache")
        for name in dirs:
            if not stat.S_ISDIR((current / name).lstat().st_mode):
                raise ArtifactError("retained shard contains a symlink or special directory")
        for name in sorted(names):
            path = current / name
            relative = path.relative_to(shard).as_posix()
            if relative == "cache":
                continue
            info = _regular(path)
            if info.st_mode & 0o7000:
                raise ArtifactError("special permission bits are outside shard transport")
            if info.st_size > limits.file_bytes or len(files) >= limits.members:
                raise ArtifactError("artifact member count or file size exceeds its bound")
            files[relative] = {"sha256": sha256(path), "size": info.st_size, "mode": stat.S_IMODE(info.st_mode)}
            total += info.st_size
            if total > limits.total_bytes:
                raise ArtifactError("artifact total file bytes exceed their bound")
    _validate_files(files, limits)
    return files


def pack(*, root: Path, shard_dir: Path, optimization: str, archive: Path,
         receipt: Path, limits: Limits = DEFAULT_LIMITS) -> dict:
    root = Path(root).resolve()
    shard_dir = _shard(root, shard_dir, optimization)
    if not shard_dir.is_dir():
        raise ArtifactError("retained shard directory is missing")
    archive, receipt = _path(root, archive), _path(root, receipt)
    if archive == receipt or archive.is_relative_to(shard_dir) or receipt.is_relative_to(shard_dir):
        raise ArtifactError("archive and receipt must be distinct and outside the producer shard")
    _unused(archive); _unused(receipt)
    files = inventory(root, shard_dir, limits=limits)
    count, total = _validate_files(files, limits)
    tar_bytes = sum(BLOCK + ((item["size"] + BLOCK - 1) // BLOCK) * BLOCK for item in files.values()) + 2 * BLOCK
    tar_bytes = ((tar_bytes + tarfile.RECORDSIZE - 1) // tarfile.RECORDSIZE) * tarfile.RECORDSIZE
    if tar_bytes > limits.archive_bytes:
        raise ArtifactError("artifact archive bytes exceed their bound")
    _parents(root, archive.parent); _parents(root, receipt.parent)
    created = False
    try:
        with archive.open("xb") as stream:
            created = True
            with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as output:
                for name, item in sorted(files.items()):
                    path = shard_dir / name
                    _regular(path)
                    with path.open("rb") as source:
                        info = tarfile.TarInfo(name)
                        info.size, info.mode, info.mtime = item["size"], item["mode"], 0
                        info.uid = info.gid = 0
                        output.addfile(info, source)
                    if sha256(path) != item["sha256"] or stat.S_IMODE(path.stat().st_mode) != item["mode"]:
                        raise ArtifactError("producer file changed while packing")
            if stream.tell() > limits.archive_bytes:
                raise ArtifactError("artifact archive bytes exceed their bound")
        if inventory(root, shard_dir, limits=limits) != files:
            raise ArtifactError("producer shard changed while packing")
        value = {"schema": SCHEMA, "optimization": optimization,
                 "source_shard_dir": str(shard_dir.relative_to(root)),
                 "archive_sha256": sha256(archive), "archive_bytes": archive.stat().st_size,
                 "file_count": count, "file_bytes": total, "files": files,
                 "excluded": ["cache/"], "transport": "regular files in uncompressed USTAR; data only",
                 "helper_sha256": sha256(Path(__file__))}
        _write_json(receipt, value)
        return value
    except BaseException:
        if created:
            archive.unlink(missing_ok=True)
        raise


def _manifest(root: Path, manifest: Path, optimization: str, limits: Limits) -> dict:
    value = _read_json(manifest)
    expected = {"schema", "optimization", "source_shard_dir", "archive_sha256", "archive_bytes",
                "file_count", "file_bytes", "files", "excluded", "transport", "helper_sha256"}
    if (set(value) != expected or value.get("schema") != SCHEMA or value.get("optimization") != optimization
            or not isinstance(value.get("source_shard_dir"), str)
            or value.get("excluded") != ["cache/"]
            or value.get("transport") != "regular files in uncompressed USTAR; data only"
            or value.get("helper_sha256") != sha256(Path(__file__))
            or not isinstance(value.get("archive_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", value["archive_sha256"]) is None
            or type(value.get("archive_bytes")) is not int or not 0 < value["archive_bytes"] <= limits.archive_bytes):
        raise ArtifactError("artifact manifest schema, source helper, optimization or archive bound differs")
    _shard(root, Path(value["source_shard_dir"]), optimization)
    count, total = _validate_files(value["files"], limits)
    if type(value["file_count"]) is not int or type(value["file_bytes"]) is not int or (value["file_count"], value["file_bytes"]) != (count, total):
        raise ArtifactError("artifact manifest file totals differ")
    return value


def _scan_tar(archive: Path, files: dict, limits: Limits, *, destination: Path | None = None) -> None:
    """Read fixed USTAR records; never call tar extraction or execute contents."""
    seen, total = set(), 0
    with archive.open("rb") as stream:
        while True:
            header = stream.read(BLOCK)
            if len(header) != BLOCK:
                raise ArtifactError("artifact tar is truncated or has no end marker")
            if not any(header):
                if stream.read(BLOCK) != bytes(BLOCK):
                    raise ArtifactError("artifact tar requires two zero end markers")
                while chunk := stream.read(64 * 1024):
                    if any(chunk):
                        raise ArtifactError("artifact tar has trailing data")
                break
            if header[156:157] not in (tarfile.REGTYPE, tarfile.AREGTYPE):
                raise ArtifactError("artifact tar contains a link, directory or special member")
            if header[257:263] != b"ustar\0" or header[263:265] != b"00":
                raise ArtifactError("artifact tar must use fixed USTAR headers")
            try:
                member = tarfile.TarInfo.frombuf(header, "utf-8", "strict")
            except (tarfile.HeaderError, UnicodeError, ValueError) as error:
                raise ArtifactError("artifact tar header is malformed") from error
            name = _relative_name(member.name)
            if name in seen:
                raise ArtifactError("artifact tar contains a duplicate file name")
            if name not in files or member.linkname or member.pax_headers or member.mode & ~0o777:
                raise ArtifactError("artifact tar has undeclared files, links or special permission bits")
            item = files[name]
            if member.size != item["size"] or member.mode != item["mode"] or not 0 <= member.size <= limits.file_bytes:
                raise ArtifactError("artifact tar file size or permission differs from its manifest")
            seen.add(name); total += member.size
            if len(seen) > limits.members or total > limits.total_bytes:
                raise ArtifactError("artifact tar count or byte bound exceeded")
            digest, left, output = hashlib.sha256(), member.size, None
            try:
                if destination is not None:
                    path = destination / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    output = path.open("xb")
                while left:
                    chunk = stream.read(min(left, 64 * 1024))
                    if not chunk:
                        raise ArtifactError("artifact tar file contents are truncated")
                    digest.update(chunk); left -= len(chunk)
                    if output is not None:
                        output.write(chunk)
                if output is not None:
                    output.flush()
                    os.fchmod(output.fileno(), member.mode)
            finally:
                if output is not None:
                    output.close()
            if digest.hexdigest() != item["sha256"]:
                raise ArtifactError("artifact tar file bytes differ from its manifest")
            padding = (-member.size) % BLOCK
            if stream.read(padding) != bytes(padding):
                raise ArtifactError("artifact tar file padding is truncated or nonzero")
    if seen != set(files) or total != sum(item["size"] for item in files.values()):
        raise ArtifactError("artifact tar file inventory is incomplete")


def unpack(*, root: Path, optimization: str, archive: Path, manifest: Path,
           destination: Path, receipt: Path, limits: Limits = DEFAULT_LIMITS) -> dict:
    root = Path(root).resolve()
    destination = _shard(root, destination, optimization)
    archive, manifest, receipt = (_path(root, path) for path in (archive, manifest, receipt))
    _unused(destination); _unused(receipt)
    value = _manifest(root, manifest, optimization, limits)
    source = _shard(root, Path(value["source_shard_dir"]), optimization)
    if receipt in (archive, manifest) or receipt.is_relative_to(destination) or receipt.is_relative_to(source):
        raise ArtifactError("extraction receipt must be distinct and outside both producer and destination")
    if archive.is_relative_to(destination) or manifest.is_relative_to(destination):
        raise ArtifactError("extraction inputs cannot be inside their unused destination")
    info = _regular(archive)
    if info.st_size != value["archive_bytes"] or info.st_size > limits.archive_bytes or sha256(archive) != value["archive_sha256"]:
        raise ArtifactError("artifact archive byte size or SHA256 differs")
    _scan_tar(archive, value["files"], limits)
    _parents(root, destination.parent); _parents(root, receipt.parent)
    created = None
    try:
        destination.mkdir(mode=0o755)
        created = destination.stat()
        _scan_tar(archive, value["files"], limits, destination=destination)
        if sha256(archive) != value["archive_sha256"]:
            raise ArtifactError("artifact archive changed while extracting")
        result = {"schema": EXTRACTION_SCHEMA, "optimization": optimization,
                  "source_shard_dir": value["source_shard_dir"], "destination": str(destination.relative_to(root)),
                  "archive_sha256": value["archive_sha256"], "manifest_sha256": sha256(manifest),
                  "file_count": value["file_count"], "file_bytes": value["file_bytes"],
                  "helper_sha256": sha256(Path(__file__)),
                  "scope": "retained data materialization with original file modes; no new target execution"}
        _write_json(receipt, result)
        return result
    except BaseException:
        if created is not None and destination.exists() and not destination.is_symlink():
            current = destination.stat()
            if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                shutil.rmtree(destination)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="operation", required=True)
    create = sub.add_parser("pack", allow_abbrev=False)
    restore = sub.add_parser("unpack", allow_abbrev=False)
    for command in (create, restore):
        command.add_argument("--optimization", choices=("O0", "O2"), required=True)
        command.add_argument("--archive", type=Path, required=True)
        command.add_argument("--receipt", type=Path, required=True)
    create.add_argument("--shard-dir", type=Path, required=True)
    restore.add_argument("--manifest", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        common = dict(root=root, optimization=args.optimization, archive=args.archive, receipt=args.receipt)
        result = (pack(**common, shard_dir=args.shard_dir) if args.operation == "pack" else
                  unpack(**common, manifest=args.manifest, destination=args.destination))
        print(json.dumps({key: value for key, value in result.items() if key != "files"}, sort_keys=True))
        return 0
    except (ArtifactError, OSError, ValueError, tarfile.TarError) as error:
        print(f"SHARD ARTIFACT FAIL: {error}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
