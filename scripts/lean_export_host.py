"""Versioned host elaboration resources, separate from target semantics.

Kernel/user Lake build and export invocations record their host worker/stack
policy. Direct Lean exports also record literal -j2. These are not OS thread or
RSS guarantees. Historical source archives retain their original commands.
"""
from pathlib import Path
import hashlib

from core0_common import Core0Error

SOURCE = "scripts/lean_export_host.py"


V1_SOURCE_SHA256 = "52e96d6d3ec2139dd6c5a12fbc824d65b121af52a81642fa2cb966757a6433fa"


def policy(version=2):
    if version == 2:
        return {"schema": "lemma-lean-export-host/2", "workers": 2,
                "argument": "-j2", "environment": {"LEAN_NUM_THREADS": "2",
                "LEAN_STACK_SIZE_KB": "65536"},
                "scope": "host Lean worker pool and stack reservation only"}
    if version != 1:
        raise Core0Error("unknown Lean export host version")
    return {"schema": "lemma-lean-export-host/1", "workers": 2,
            "argument": "-j2", "scope": "host Lean export worker pool only"}


def arguments(record):
    if record is None:
        return []
    if (type(record) is not dict or type(record.get("workers")) is not int or
            record not in (policy(1), policy(2))):
        raise Core0Error("unknown or malformed Lean export host policy")
    return ["-j2"]


def for_source(root):
    root = Path(root)
    if (root / SOURCE).is_file():
        return policy_for_digest(hashlib.sha256((root / SOURCE).read_bytes()).hexdigest())
    builder = root / "scripts/build_kernel.py"
    if not builder.is_file() or b"from lean_export_host import" in builder.read_bytes():
        raise Core0Error("current kernel source is missing its Lean export host helper")
    return None


def policy_for_digest(digest):
    if digest == V1_SOURCE_SHA256:
        return policy(1)
    if digest == hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        return policy(2)
    raise Core0Error("unknown Lean export host helper source")


def environment(record):
    arguments(record)
    return {} if record is None else record.get("environment", {}).copy()


def command(source, *, source_root):
    return ("lake", "env", "lean", *arguments(for_source(source_root)), str(source))


def validate_provenance(record, source_inputs):
    if not isinstance(source_inputs, dict):
        raise Core0Error("Lean export policy requires a complete source inventory")
    if SOURCE in source_inputs:
        if record is None:
            raise Core0Error("current Lean export host policy is missing or changed")
        arguments(record)
        if record != policy_for_digest(source_inputs[SOURCE]):
            raise Core0Error("Lean export host policy differs from consumed helper source")
    elif record is not None:
        raise Core0Error("historical source inventory cannot acquire a host policy")
    return record


def validate_commands(rows, record):
    expected = arguments(record)
    if (not isinstance(rows, list) or not rows or
            any(not isinstance(row, dict) or not isinstance(row.get("argv"), list) or
                not row["argv"] or any(not isinstance(arg, str) for arg in row["argv"])
                for row in rows)):
        raise Core0Error("malformed Lean export command corpus")
    exports = [row for row in rows if row.get("argv") and
               row["argv"][0].rsplit("/", 1)[-1] == "lake" and
               row["argv"][1:3] == ["env", "lean"]]
    if not exports or any(len(row["argv"]) != 4 + len(expected) or
                          row["argv"][3:-1] != expected or
                          not row["argv"][-1].endswith(".lean") for row in exports):
        raise Core0Error("exact Lean export host arguments differ from their policy")

    for row in rows:
        if row['argv'][0].rsplit('/', 1)[-1] == 'lake':
            wanted = environment(record)
            if wanted:
                if row.get('host_environment') != wanted:
                    raise Core0Error('Lean host worker/stack environment differs or is absent')
            elif 'host_environment' in row:
                raise Core0Error('Historical command acquired new host environment evidence')
