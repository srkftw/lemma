#!/usr/bin/env python3
"""Bounded source-bound hosted school checks; target/client receipts are separate."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from build_school import inputs
from build_actions import lean_source_inputs
from core0_common import repo_root, sha256


def run_owned(command, *, root, output, environment, log_name, timeout):
    """Reuse the admitted action worker for deadline and descendant ownership.

    This is fresh validation, never cache production/reuse. The worker writes
    its result only after stopping/reaping its owned process tree, including
    separate-session authorities created by interruption fixtures.
    """
    read_fd, write_fd = os.pipe()
    try:
        with (output/(log_name+".owner")).open("xb") as lease, (output/log_name).open("x") as log:
            wrapper=[sys.executable,str(root/"scripts/action_worker.py"),"--lease-fd",str(lease.fileno()),
                     "--result-fd",str(write_fd),"--parent-pid",str(os.getpid()),"--timeout",str(timeout),"--",*command]
            worker=subprocess.Popen(wrapper,cwd=root,env=environment,stdout=log,stderr=subprocess.STDOUT,
                                    pass_fds=(lease.fileno(),write_fd))
            os.close(write_fd);write_fd=-1
            worker.wait()
            raw=os.read(read_fd,4097)
        if worker.returncode or len(raw)>4096 or not raw:
            raise RuntimeError("validation ownership worker failed without a bounded result")
        receipt=json.loads(raw)
        (output/(log_name+".ownership.json")).write_text(json.dumps(receipt,indent=2)+"\n")
        return receipt
    finally:
        os.close(read_fd)
        if write_fd!=-1:os.close(write_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--host-timeout", type=int, default=300,
                        help="prospective host corpus bound60..900s; default300, never extends a running deadline")
    args = parser.parse_args()
    if not 60 <= args.host_timeout <= 900:
        parser.error("host-timeout must be60..900seconds")
    root = repo_root()
    output = args.work_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    producer = json.loads(args.production.read_text())
    source = inputs(root)
    consumed = dict(source)
    # The independently executed Action tests import guest modules outside the
    # hosted executable closure. Bind those real transitive Lean inputs too.
    test_roots = sorted((root / "tests/school").glob("*.lean"))
    for name, path in lean_source_inputs(root, test_roots).items():
        consumed[name] = sha256(path)
    for folder in ("tests/school", "fixtures/school", "examples/school"):
        for path in sorted((root / folder).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                consumed[str(path.relative_to(root))] = sha256(path)
    for name in ("scripts/check_school.py", "scripts/school_transport.py", "scripts/lemmasim_school.py", "scripts/action_worker.py"):
        consumed[name] = sha256(root / name)
    report = {"schema": "lemma-school-host-validation/1", "result": "FAIL",
              "sourceInputs": consumed, "commands": [], "productionReceipt": str(args.production.resolve()),
              "productionReceiptSha256": sha256(args.production),
              "limits":{"hostSeconds":args.host_timeout,"clientSeconds":120,"tutorSelectionSeconds":120,"cleanup":"existing action_worker subreaper owns each command until descendants reaped"},
              "scope": "hosted school semantics, authoring, importer fixtures, consent, client validators, local recovery; actual RV64/client/real-corpus receipts remain separate"}
    start = time.monotonic()
    try:
        if producer.get("result") != "PASS" or producer.get("sourceInputs") != source:
            raise RuntimeError("host producer does not bind the current consumed source")
        environment = dict(os.environ)
        for name, record in producer["binaries"].items():
            if sha256(Path(record["path"])) != record["sha256"]:
                raise RuntimeError("pinned hosted executable changed")
            environment["LEMMA_SCHOOL_TEST_BINARY" if name == "school" else "LEMMA_SCHOOL_TEST_CURRICULUM"] = record["path"]
        primitive = producer.get("hostPrimitives", {}).get("school_fs_barrier.py")
        if not primitive or sha256(Path(primitive["path"])) != primitive["sha256"]:
            raise RuntimeError("pinned storage barrier primitive missing or changed")
        environment["LEMMA_SCHOOL_FS_BARRIER"] = primitive["path"]
        environment["LEMMA_SCHOOL_FS_PYTHON"] = sys.executable
        commands = [
            ([sys.executable, "-m", "unittest", "discover", "-s", "tests/school", "-v"], "host.log", args.host_timeout),
            (["lake", "env", "lean", "--run", "tests/school/Client.lean"], "client-validation.log", 120),
            (["lake", "env", "lean", "--run", "tests/school/TutorSelection.lean"], "tutor-selection.log", 120),
            (["lake", "env", "lean", "--run", "tests/school/RemoteEvents.lean"], "remote-events.log", 120),
        ]
        for command, log_name, timeout in commands:
            began = time.monotonic()
            owned=run_owned(command,root=root,output=output,environment=environment,log_name=log_name,timeout=timeout)
            text = (output / log_name).read_text()
            report["commands"].append({"command": command, "exitCode": owned.get("returncode"),
                                       "ownership":owned,"ownershipReceipt":log_name+".ownership.json",
                                       "log": log_name, "logSha256": sha256(output / log_name),
                                       "elapsedSeconds": time.monotonic() - began})
            if owned.get("kind")!="completed" or owned.get("returncode")!=0:
                raise RuntimeError("actual validation failed: " + log_name)
            if log_name == "host.log":
                matched = re.search(r"Ran (\d+) tests?", text)
                if not matched or int(matched.group(1)) == 0 or re.search(r"skipped[= ]", text):
                    raise RuntimeError("host suite must be nonempty and unskipped")
                report["hostTests"] = int(matched.group(1))
        for name, digest in consumed.items():
            if sha256(root / name) != digest:
                raise RuntimeError("consumed validation input changed: " + name)
        report["result"] = "PASS"
    except Exception as error:
        report["error"] = str(error)
    report["elapsedSeconds"] = time.monotonic() - start
    (output / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"result": report["result"], "receipt": str(output / "validation.json"),
                      "error": report.get("error")}))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
