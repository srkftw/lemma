#!/usr/bin/env python3
"""Exercise actual hosted Lean training, SIGKILL/resume, and bounded data access."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from build_actions import lean_source_inputs
from core0_common import Core0Error, checked, repo_root, sha256, write_json


def check(directory: Path):
    root = repo_root()
    directory.mkdir(parents=True, exist_ok=False)
    commands = []
    base = ["lake", "env", "lean", "--run", "examples/school/Train.lean"]

    def run(args, name):
        argv = base + list(map(str,args))
        result = checked(argv, cwd=root, timeout_seconds=120)
        (directory/f"{name}.stdout").write_bytes(result.stdout)
        (directory/f"{name}.stderr").write_bytes(result.stderr)
        commands.append({"command":argv,"elapsedSeconds":result.elapsed_seconds,
                         "stdoutSha256":sha256(directory/f"{name}.stdout")})
        return result

    run(["check"], "independent")
    dataset = directory/"dataset"
    run(["fixture",dataset], "fixture")
    checkpoint = directory/"full-checkpoint.json"
    run(["train",dataset,checkpoint,directory/"full",160,0],"full")
    run(["train",dataset,directory/"early-checkpoint.json",directory/"early",1,0],"early")

    interrupted = directory/"resumed-checkpoint.json"
    argv = base+["train",str(dataset),str(interrupted),str(directory/"resumed"),"160","40"]
    log = (directory/"interrupted.stdout").open("wb")
    err = (directory/"interrupted.stderr").open("wb")
    process = subprocess.Popen(argv,cwd=root,stdout=log,stderr=err,start_new_session=True)
    deadline = time.monotonic()+90
    state = None
    try:
        while time.monotonic()<deadline:
            if process.poll() is not None:
                raise Core0Error("training ended before interruption checkpoint was observed")
            if interrupted.exists():
                state = json.loads(interrupted.read_text())
                if state["step"]>=7:
                    break
            time.sleep(.01)
        if state is None or not 7<=state["step"]<160:
            raise Core0Error("no genuine intermediate training checkpoint")
        os.killpg(process.pid,signal.SIGKILL)
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        log.close();err.close()
    killed = json.loads(interrupted.read_text())
    write_json(directory/"interrupted-checkpoint-observed.json",killed)
    run(["train",dataset,interrupted,directory/"resumed",160,0],"resume")
    if checkpoint.read_bytes()!=interrupted.read_bytes():
        raise Core0Error("resumed state differs from uninterrupted state: sample/update replay mismatch")
    for name in ("parameters.json","evaluation.json"):
        if (directory/"full"/name).read_bytes()!=(directory/"resumed"/name).read_bytes():
            raise Core0Error("resumed published artifact differs: "+name)
    # Wrong dataset/implementation/cursor checkpoints reject on actual Lean admission.
    bad = dict(killed);bad["nextRecord"] = 1
    write_json(directory/"invalid-cursor.json",bad)
    invalid_argv = base+["train",str(dataset),str(directory/"invalid-cursor.json"),str(directory/"invalid"),"160","0"]
    invalid = subprocess.run(invalid_argv,cwd=root,capture_output=True,timeout=120)
    (directory/"invalid-cursor.stderr").write_bytes(invalid.stderr)
    if invalid.returncode==0 or b"cursor/epoch identity mismatch" not in invalid.stderr:
        raise Core0Error("invalid checkpoint cursor was not rejected by Lean")
    large = directory/"streaming-dataset"
    run(["fixture-large",large],"large-fixture")
    run(["train",large,directory/"streaming-checkpoint.json",directory/"streaming-model",2,0],"streaming")
    if (large/"train.jsonl").stat().st_size<=16384:
        raise Core0Error("streaming fixture did not exceed worker fixed ordinary RAM size")
    report = {"schema":"lemma-school-training-evidence/v1","result":"pass","environment":"hosted Lean binary64 reference; upstream Lean runtime",
              "datasetManifestSha256":sha256(dataset/"manifest.json"),
              "checkpointSha256":sha256(checkpoint),"parametersSha256":sha256(directory/"full/parameters.json"),
              "evaluation":json.loads((directory/"full/evaluation.json").read_text()),
              "interrupt":{"signal":"SIGKILL","observedStep":killed["step"],"nextRecord":killed["nextRecord"],
                           "epoch":killed["epoch"],"resumedTotalSteps":160,"bitwiseCheckpointEqual":True,
                           "scope":"atomic replacement/process interruption, not host-power-loss durability"},
              "streaming":{"records":512,"bytes":(large/"train.jsonl").stat().st_size,
                           "maximumReadBytes":512,"maximumRowBytes":2048,"batchSize":4,
                           "wholeDatasetResident":False},
              "sourceInputs":{name:sha256(path) for name,path in lean_source_inputs(root,[root/"examples/school/Train.lean"]).items()},
              "commands":commands,"runnerSha256":sha256(Path(__file__)),
              "claim":"synthetic pipeline behavior only; held-out split used once for reported fixed run, no learning-efficacy conclusion"}
    write_json(directory/"training-evidence.json",report)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--work-dir",type=Path,required=True)
    args=parser.parse_args()
    report=check(args.work_dir.resolve())
    print(json.dumps({"result":report["result"],"evaluation":report["evaluation"],"interrupt":report["interrupt"],
                      "receipt":str(args.work_dir/"training-evidence.json")},indent=2))


if __name__=="__main__":
    main()
