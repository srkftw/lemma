"""Complete artifact admission for genuine Reader18 notebook exports.

Host audit only. The selected Lean Actions own capture, recovery and Save.
Historical notebook authorities keep their original exact catalogs and bodies.
"""
import hashlib
import json
import re
from pathlib import Path

from core0_common import Core0Error
from paper_next import canonical
from reader_deployment import CONFIGURATIONS, NOTEBOOK_ROOT, SOFTWARE_DEPLOYMENT

VERSION = "lemma-course-reader-notebook-artifact/1"
AUTHORITY = Path(__file__).resolve().parents[1] / "tooling/reader-notebook-target-authority.json"
PREDECESSOR = AUTHORITY.with_name("dirty-batch-notebook-target-authority.json")
PREFIX = "Lemma.Applications.Notebook."
READER = "Lemma.Courses.ReaderLocation."


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def candidate(unit):
    if not isinstance(unit, dict):
        raise Core0Error("Reader18 candidate unit is not a map")
    rows = unit.get("functions", [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) or
            not isinstance(row.get("source"), str) for row in rows):
        raise Core0Error("Reader18 candidate function map malformed")
    return any(canonical(row.get("source", "")) == NOTEBOOK_ROOT or
               canonical(row.get("source", "")).startswith(READER)
               for row in rows)


def contract(unit):
    if not candidate(unit):
        return None
    configuration = unit.get("configuration")
    from product_reader_target import selected, authority
    if selected(unit):
        wanted = authority(unit, "notebook")
        if (unit.get("role"),unit.get("image_key"),unit.get("image_id"),unit.get("contract_version")) != ("user","notebook",2,"core0-user-v0.2"):
            raise Core0Error("Product Reader18 escaped exact Notebook User2")
        return "product10", wanted
    if (configuration not in CONFIGURATIONS or unit.get("role") != "user" or
            unit.get("image_key") != "notebook" or unit.get("image_id") != 2 or
            unit.get("contract_version") != "core0-user-v0.2" or
            unit.get("software_deployment") != SOFTWARE_DEPLOYMENT or
            unit.get("used_device_ops") != []):
        raise Core0Error("Reader18 escaped its exact closed Notebook User2 deployment")
    roots = [{key: row.get(key) for key in ("source", "id", "args")}
             for row in unit.get("roots", [])]
    if roots != [{"source": NOTEBOOK_ROOT, "id": 1, "args": ["u64"]}]:
        raise Core0Error("Reader18 exact root/ABI differs")
    loops = unit.get("used_loops", [])
    if (len(loops) != 1 or loops[0].get("stable_id") != "action.loop" or
            canonical(loops[0].get("callback", "")) != PREFIX + "bookmarkStep"):
        raise Core0Error("Reader18 selected loop differs")
    if {row.get("stable_id") for row in unit.get("used_execution_ops", [])} != {
            "execution.virtual-read8", "execution.virtual-read64",
            "execution.virtual-write8", "execution.virtual-write64", "execution.syscall"}:
        raise Core0Error("Reader18 acquired execution authority")
    wanted = json.loads(AUTHORITY.read_text())
    from authored_hint_target import refined as hint_refined
    wanted = hint_refined(unit, wanted, AUTHORITY)
    predecessor = json.loads(PREDECESSOR.read_text())["number_entry_browse_history_v1"]
    catalogs = wanted.get("catalog_sha256_by_configuration", {})
    if (wanted.get("schema") != VERSION or wanted.get("package_notebook_version") != 18 or
            wanted.get("reader_contract") != "lemma-course-reader-location/1" or
            wanted.get("previous_artifact_sha256") != digest(predecessor) or
            set(catalogs) != set(CONFIGURATIONS) or catalogs[configuration] != digest(unit)):
        raise Core0Error("Reader18 complete genuine authority/predecessor/catalog differs")
    return "canonical", wanted


def semantics(ir, unit, *, step="bookmarkStep", work="pumpPackageBookmarkWork"):
    from audit_kernel import _ir_definition_body
    rows = {canonical(row["source"]): row for row in unit["functions"]}

    def calls(owner, target):
        if owner not in rows or target not in rows:
            raise Core0Error("Reader18 semantic owner absent: " + owner + "/" + target)
        return re.findall(r"call \{ i64, i64 \} @" + re.escape(rows[target]["symbol"]) +
                          r"\(([^\n]*)\)", _ir_definition_body(ir, rows[owner]["symbol"]))

    edges = [
        (step, "pumpBookmarkSave"),
        (step, work),
        (step, "numericPumpPad"),
        (step, "pumpRefreshRestoredBatched"),
        (step, "bookmarkBusy"),
        ("bookmarkInputSample.acceptSample", "bookmarkToolbar"),
        ("bookmarkInputSample.acceptSample", "numericPadPress"),
        ("bookmarkInputSample.acceptSample", "cancelBookmarkWork"),
        ("bookmarkToolbar", "bookmarkRequestSave"),
        ("bookmarkToolbar", "numericToolbar"),
        ("bookmarkRequestSave", "startSave"),
        ("pumpBookmarkSave", "pumpSave"),
        ("pumpBookmarkSave", "adoptBookmark"),
        (work, "pumpBookmarkOpen"),
        (work, "validateBookmarkPackage"),
        (work, "renderPackageText"),
        ("pumpBookmarkOpen", "pumpBrowseOpenCourse"),
        ("pumpBookmarkOpen", "pumpPackageRecord"),
        ("pumpBookmarkOpen", "startPackageRecord"),
        ("pumpBookmarkOpen", "finishBookmarkLookup"),
        ("finishBookmarkLookup", "adoptBookmark"),
        ("adoptBookmark", "copyBookmarkStep"),
        ("cancelBookmarkWork", "cancelPackageRecord"),
        ("cancelBookmarkWork", "cancelPackageWork"),
        ("pumpBrowseOpenCourse", "restoreBrowseLocation"),
        ("numericPadPress", "numericPublishAligned"),
        ("numericPublishAligned", "savePackageWorkspace"),
        ("savePackageWorkspace", "startSave"),
        ("uploadDirtyBatch", "consumeDirtyIndexStep"),
        ("pumpRefreshRestoredBatched", "restorePaperBatch"),
    ]
    for owner, target in edges:
        # The two explicit fallback branches are Save outside a course and
        # every other toolbar button. Both retain the historical toolbar.
        expected = 2 if (owner, target) == ("bookmarkToolbar", "numericToolbar") else 1
        if len(calls(PREFIX + owner, PREFIX + target)) != expected:
            raise Core0Error("Reader18 disconnected actual guest path: " + owner + "/" + target)
    for owner, target in [
            (PREFIX + "bookmarkRequestSave", READER + "capture"),
            (PREFIX + "adoptBookmark", READER + "validate"),
            (PREFIX + "validateBookmarkPackage", READER + "resolve"),
            (READER + "capture", "Lemma.Courses.PackageTarget.select"),
            (READER + "resolve", "Lemma.Courses.PackageTarget.select"),
            (READER + "resolve", READER + "validate")]:
        if len(calls(owner, target)) != 1:
            raise Core0Error("Reader18 lost complete validation/publication path")
    for owner in (READER + "validate", READER + "resolve"):
        if rows[owner]["effects"] != ["checked-access", "virtual-read"]:
            raise Core0Error("Reader18 resolution acquired write/effect authority")
    for owner in (PREFIX + "finishBookmarkLookup", PREFIX + "validateBookmarkPackage",
                  READER + "capture", READER + "validate", READER + "resolve"):
        for target in ("startSave", "reportCommitState", "numericPublishAligned", "packageCheck"):
            if PREFIX + target in rows and calls(owner, PREFIX + target):
                raise Core0Error("Reader18 lookup/codec acquired mathematical/Save authority")
    return {
        "ordinary_guest_store_and_reader_connected": True,
        "reader_scope": "node only; exact package/edition/CRC/source anchor; separate object",
        "durability": "unchanged guest Store transaction and validated COMMIT response",
        "scope": "Source/LLVM artifact audit; actual guest and durability qualification separate",
    }


def validate(ir, unit, *, optimized):
    found = contract(unit)
    if found is None:
        return None
    from package_companion_target import complete_corpus
    scope, wanted = found
    phase = "post" if optimized else "pre"
    actual = complete_corpus(ir, unit, optimized=optimized)
    if (len(actual["functions"]) != wanted[phase + "_function_count"] or
            digest(actual) != wanted[phase + "_sha256"]):
        raise Core0Error("Reader18 complete body/global/caller corpus differs: " + phase)
    return {
        "contract_version": "lemma-installed-package-notebook/18",
        "artifact_contract_version": VERSION, "software_scope": scope,
        "package_notebook_version": 18, "phase": phase,
        "function_count": len(actual["functions"]), "complete_corpus_sha256": digest(actual),
        "semantics": None if optimized else semantics(ir, unit),
        "scope": "Complete genuine artifact; CPU/Store/controller qualification separate",
    }
