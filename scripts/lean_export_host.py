"""Versioned host elaboration resources, separate from target semantics.

Only direct kernel/user export invocations use this policy. The CLI worker
limit is recorded literally; it is not a process-thread or memory guarantee.
Historical source archives without this helper retain their original argv.
"""
from pathlib import Path

from core0_common import Core0Error

SOURCE = "scripts/lean_export_host.py"


def policy():
    return {"schema": "lemma-lean-export-host/1", "workers": 2,
            "argument": "-j2", "scope": "host Lean export worker pool only"}


def arguments(record):
    if record is None:
        return []
    if (type(record) is not dict or type(record.get("workers")) is not int or
            record != policy()):
        raise Core0Error("unknown or malformed Lean export host policy")
    return ["-j2"]


def for_source(root):
    root = Path(root)
    if (root / SOURCE).is_file():
        return policy()
    builder = root / "scripts/build_kernel.py"
    if not builder.is_file() or b"from lean_export_host import" in builder.read_bytes():
        raise Core0Error("current kernel source is missing its Lean export host helper")
    return None


def command(source, *, source_root):
    return ("lake", "env", "lean", *arguments(for_source(source_root)), str(source))


def validate_provenance(record, source_inputs):
    if not isinstance(source_inputs, dict):
        raise Core0Error("Lean export policy requires a complete source inventory")
    if SOURCE in source_inputs:
        if record is None:
            raise Core0Error("current Lean export host policy is missing or changed")
        arguments(record)
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
