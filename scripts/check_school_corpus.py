#!/usr/bin/env python3
"""Read-only archive extraction and independent observation of Lean catalogue IO.

This host tool conveys bytes, invokes the maintained Lean importer/compiler, and
checks source identity/order. It implements no curriculum or school decisions.
Original PDFs/text and extracted records remain under the ignored work directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    hashing = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            hashing.update(chunk)
    return hashing.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--curriculum-binary", type=Path, default=ROOT / ".lake/build/bin/school-curriculum")
    parser.add_argument("--catalogue-member", default="MyMathTextbooks/Curriculum.json")
    parser.add_argument("--outline-member", default="MyMathTextbooks/mathCurriculum.pdf")
    parser.add_argument("--expected-catalogue-sha256")
    parser.add_argument("--expected-outline-sha256")
    parser.add_argument("--search", default="binomial")
    parser.add_argument("--changed-catalogue", type=Path, default=ROOT / "fixtures/school/catalogue.json")
    args = parser.parse_args()
    archive = args.archive.resolve()
    binary = args.curriculum_binary.resolve()
    work = args.work_dir.resolve()
    if work.exists():
        parser.error("work directory already exists; preserve retained observations and use a new path")
    if not archive.is_file() or archive.stat().st_size > 2147483648:
        parser.error("archive must be an existing regular file no larger than 2GiB")
    if not binary.is_file():
        parser.error("native hosted curriculum binary is unavailable; run the pinned Lake build first")
    work.mkdir(parents=True)
    steps = []
    initial_stat = archive.stat()
    archive_digest = digest(archive)
    report = {"schema": "lemma-school-corpus-observation/1", "status": "FAIL",
              "archive": str(archive), "archiveBytes": initial_stat.st_size,
              "archiveSha256": archive_digest, "binary": str(binary), "binarySha256": digest(binary),
              "executionEnvironment": "native hosted Lean; upstream host Lean runtime, not a target service",
              "sourceBoundary": "Original archive opened read-only; selected ordinary file members only",
              "steps": steps}

    def execute(name, command, *, parse_json=False):
        started = time.monotonic()
        run = subprocess.run([str(value) for value in command], cwd=ROOT, capture_output=True, text=True, timeout=300)
        (work / (name + ".stdout")).write_text(run.stdout, encoding="utf-8")
        (work / (name + ".stderr")).write_text(run.stderr, encoding="utf-8")
        steps.append({"name": name, "command": [str(value) for value in command],
                      "exitCode": run.returncode, "seconds": time.monotonic() - started})
        if run.returncode:
            raise RuntimeError(f"{name} failed: {run.stderr[-2000:]}")
        return json.loads(run.stdout) if parse_json else run.stdout

    try:
        names = execute("archive-members", ["tar", "--zstd", "-tf", archive]).splitlines()
        verbose = execute("archive-inventory", ["tar", "--zstd", "-tvf", archive]).splitlines()
        selected = [args.catalogue_member, args.outline_member]
        for member in selected:
            path = Path(member)
            if path.is_absolute() or ".." in path.parts or names.count(member) != 1:
                raise RuntimeError("missing, duplicate or unsafe selected archive member")
            entries = [line for line in verbose if line.endswith(" " + member)]
            if len(entries) != 1 or not entries[0].startswith("-"):
                raise RuntimeError("selected archive member is not an ordinary file")
        execute("extract-selected", ["tar", "--zstd", "-xf", archive, "-C", work, "--", *selected])
        source = work / args.catalogue_member
        outline = work / args.outline_member
        catalogue_digest, outline_digest = digest(source), digest(outline)
        if args.expected_catalogue_sha256 and catalogue_digest != args.expected_catalogue_sha256:
            raise RuntimeError("actual catalogue bytes differ from requested expected identity")
        if args.expected_outline_sha256 and outline_digest != args.expected_outline_sha256:
            raise RuntimeError("actual outline bytes differ from requested expected identity")
        report.update({"catalogueSha256": catalogue_digest, "catalogueBytes": source.stat().st_size,
                       "outlineSha256": outline_digest, "outlineBytes": outline.stat().st_size,
                       "archiveMemberCount": len(names)})
        school = work / "school"
        cli = [binary, "catalogue"]
        imported = execute("import", [*cli, "import", school, "owner-math", source], parse_json=True)
        if imported["manifest"]["sourceDigest"] != catalogue_digest:
            raise RuntimeError("Lean importer source identity differs from independent host SHA256")
        originals = json.loads(source.read_text(encoding="utf-8"))
        revision = Path(imported["directory"])
        rows = [json.loads(line) for line in (revision / "records.jsonl").read_text(encoding="utf-8").splitlines()]
        if not originals or len(rows) != len(originals) or imported["manifest"]["records"] != len(originals):
            raise RuntimeError("observed imported record count differs from actual source")
        if [row["original"] for row in rows] != originals or [row["position"] for row in rows] != list(range(len(originals))):
            raise RuntimeError("import changed an original source string or source position")
        if any(row["originalUtf8Sha256"] != hashlib.sha256(row["original"].encode()).hexdigest() for row in rows):
            raise RuntimeError("a preserved original string digest differs")
        if (revision / "source.json").read_bytes() != source.read_bytes():
            raise RuntimeError("import did not preserve the exact source bytes")
        repeated = execute("reimport", [*cli, "import", school, "owner-math", source], parse_json=True)
        if not repeated["reused"] or repeated["directory"] != imported["directory"]:
            raise RuntimeError("identical source did not reuse its immutable revision")
        page = execute("search", [*cli, "search", school, "owner-math", catalogue_digest, args.search, 0, 5], parse_json=True)
        if not page["records"]:
            raise RuntimeError("requested search has no source records; choose a useful query explicitly")
        position = page["records"][0]["record"]["position"]
        lookup = execute("lookup", [*cli, "lookup", school, "owner-math", catalogue_digest, position], parse_json=True)
        if lookup["record"]["original"] != originals[position]:
            raise RuntimeError("source lookup differs from exact original")
        changed = execute("changed-fixture", [*cli, "import", school, "owner-math", args.changed_catalogue], parse_json=True)
        if changed["manifest"]["sourceDigest"] == catalogue_digest or not (revision / "source.json").exists():
            raise RuntimeError("changed fixture failed to preserve distinct revision history")
        final_stat = archive.stat()
        if (final_stat.st_size, final_stat.st_mtime_ns, final_stat.st_mode) != (initial_stat.st_size, initial_stat.st_mtime_ns, initial_stat.st_mode) or digest(archive) != archive_digest:
            raise RuntimeError("original archive changed during observation")
        source_inputs = ["scripts/check_school_corpus.py", "Lemma/School/Catalogue.lean", "Lemma/School/Digest.lean", "Lemma/School/CurriculumMain.lean", "lean-toolchain", "flake.lock"]
        report.update({"status": "PASS", "recordCount": len(originals), "distinctStrings": len(set(originals)),
                       "everyOriginalAndPositionCompared": True, "everyOriginalDigestCompared": True,
                       "idempotentReimport": True, "changedRevisionDigest": changed["manifest"]["sourceDigest"],
                       "realRevisionRetained": True, "searchMatchCount": page["matchCount"], "firstLookup": lookup,
                       "originalArchiveUnchanged": True, "maximumChildRssKiB": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                       "memoryScope": "maximum RSS across tar and native hosted Lean children; independent Python oracle memory excluded",
                       "inputs": {path: digest(ROOT / path) for path in source_inputs}})
    except Exception as error:
        report["error"] = str(error)
        (work / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1
    (work / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
