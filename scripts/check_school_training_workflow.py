#!/usr/bin/env python3
"""Publish/select/rollback real configured Lean training and consume RV64 results.

The driver transports declared work and observes real processes. Lean owns
feature preparation, admission, numerical training, assessment and selection.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time

from check_school_job_worker import check_production
from check_school_worker import observe
from core0_common import Core0Error, repo_root, sha256, write_json
from school_provider_runner import configure
from lemmasim_school import school_call
from lemmasim_school_service import SchoolService


def protected_assist_consumer(output, school, binary, call):
    """Existing committed target results affect the real protected help API.

    The ASK and prior independent written work are explicitly synthetic fixture
    inputs. The numerical job, parameter/result provenance, principal admission,
    immutable help packet and model rollback are actual maintained operations.
    """
    token = secrets.token_hex(32)
    call("admission-issue", learner="learner", tokenHash=hashlib.sha256(token.encode()).hexdigest())
    reservations = []
    for _ in range(2):
        item = socket.socket(); item.bind(("127.0.0.1", 0)); reservations.append(item)
    ports = [item.getsockname()[1] for item in reservations]
    for item in reservations: item.close()
    log = (output/"protected-help-service.log").open("xb")
    process = subprocess.Popen([sys.executable, "scripts/school_transport.py", "--binary", str(binary.resolve()),
        str(school), "run", "--port", str(ports[0]), "--client-port", str(ports[1])],
        cwd=repo_root(), stdout=log, stderr=log, start_new_session=True)
    endpoint = f"http://127.0.0.1:{ports[1]}/v1/client"
    transcript = []
    def client(op, **fields):
        request = dict(op=op, **fields)
        result = SchoolService.exchange((endpoint, token), request)
        transcript.append(dict(principal="admitted learner", request=request, result=result))
        write_json(output/"protected-help-commands.json", transcript)
        return result
    def owner(op, version):
        return school_call(binary, school, dict(op=op, version=version, school="configured-review", actor="owner"),
            output, f"help-{op}-{version}", f"http://127.0.0.1:{ports[0]}/v1/command")
    try:
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            if process.poll() is not None: raise Core0Error("protected help authority exited before readiness")
            try:
                transport = json.loads((school/"transport.json").read_text())
                if transport["pid"] == process.pid and transport["clientPort"] == ports[1]: break
            except (OSError, ValueError, KeyError): pass
            time.sleep(.02)
        else: raise Core0Error("protected help authority readiness10s bound")
        def help_packet(session, sequence):
            ask = dict(session=41, consent=7, revision=3, object=0x504b000000000001, sequence=sequence,
                       source=1, edition=1, task_id=4, cutoff=100, now=120, deadline=1000, grants=1, modality=1)
            client("join", course=1, revision=1, session=session, guestSession=41, lifetimeMs=60000, ask=ask)
            return ask, client("assist", session=session, ask=ask)
        ask, chosen = help_packet("selected-rv64-help", 1)
        if chosen["selector"]["mechanism"] != "committed-rv64-selector":
            raise Core0Error("actual committed target suggestion did not affect protected assistance")
        if chosen["selector"]["job"] != "configured-first" or chosen["selector"]["model"] != 9001:
            raise Core0Error("protected assistance consumed another model/job")
        packet = bytes.fromhex(chosen["package_hex"])
        if b"Review this hint, then try practice. " not in packet:
            raise Core0Error("numerical action was not included in actual bounded help package")
        observed = dict(admittedBytes=1, wireBytes=2, packetSHA256=hashlib.sha256(packet).hexdigest())
        delivered = client("delivery-observe", decision=chosen["decision"], sequence=1,
            observer="synthetic-protected-receipt-fixture", kind="transport", observation=observed)
        owner("model-rollback", 9002)
        retry = client("assist", session="selected-rv64-help", ask=ask)
        if retry["package_hex"] != chosen["package_hex"] or retry["selector"] != chosen["selector"] or not retry["reused"]:
            raise Core0Error("model rollback changed an already committed help packet on lost-ACK retry")
        repeated = client("delivery-observe", decision=chosen["decision"], sequence=1,
            observer="synthetic-protected-receipt-fixture", kind="transport", observation=observed)
        if repeated["commitSequence"] != delivered["commitSequence"]:
            raise Core0Error("typed delivery retry duplicated its original commit")
        _, baseline = help_packet("rolled-back-baseline", 2)
        if baseline["selector"]["mechanism"] != "authored-baseline" or baseline["package_hex"] == chosen["package_hex"]:
            raise Core0Error("stale model suggestion did not fall back to authored help")
        if b"Review this hint, then try practice. " in bytes.fromhex(baseline["package_hex"]):
            raise Core0Error("stale numerical advice remained in baseline help")
        owner("model-rollback", 9001)
        _, reselected = help_packet("reselected-rv64-help", 3)
        if reselected["selector"]["mechanism"] != "committed-rv64-selector":
            raise Core0Error("explicit model reselection did not restore eligible committed advice")
        return dict(result="PASS", selector=chosen["selector"], packetSHA256=hashlib.sha256(packet).hexdigest(),
            rollbackRetryBytesIdentical=True, staleModelUsesAuthoredBaseline=True,
            reselectedAdvice=True, deliveryRetryCommit=delivered["commitSequence"],
            transcriptSha256=sha256(output/"protected-help-commands.json"),
            syntheticTransportObservation=True,
            scope="Actual admitted protected HTTP help packet, with explicitly synthetic ASK/independent work/raw receipt fixtures. No device transport, guest rendering, visible delivery or educational benefit claim.")
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=3)
        log.close()


def check(args):
    root = repo_root()
    observed_sources = {name: sha256(root/name) for name in (
        "scripts/check_school_training_workflow.py", "scripts/check_school_job_worker.py",
        "scripts/check_school_worker.py", "scripts/school_provider_runner.py",
        "scripts/lemmasim_school.py", "scripts/lemmasim_school_service.py",
        "scripts/school_transport.py", "scripts/school_target.py", "scripts/core0_common.py",
        "scripts/build_actions.py", "scripts/build_school.py")}
    check_production(args.production, args.binary, args.curriculum)
    output = args.work_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    school = output / "authority"
    clock = 0
    commands = []
    def call(op, *, expected_error=None, **fields):
        request = {"op": op, "school": "configured-review", "actor": "owner", "now": clock, **fields}
        process = subprocess.run([str(args.binary.resolve()), str(school), json.dumps(request)], cwd=root,
                                 capture_output=True, timeout=20)
        reply = json.loads(process.stdout)
        commands.append(dict(request=request, reply=reply, exitCode=process.returncode))
        write_json(output / "commands.json", commands)
        if expected_error:
            if reply.get("ok") or expected_error not in reply.get("error", ""):
                raise Core0Error("expected admission rejection: " + str(reply))
            return reply
        if process.returncode or not reply.get("ok"):
            raise Core0Error("actual school command failed: " + str(reply))
        return reply["result"]
    call("init", deployment="configured-review-local", clockModel="controlled-ms")
    unit = json.loads(subprocess.check_output([str(args.curriculum.resolve()), "fixture"], cwd=root))
    unit["course"]["identity"] = "1"
    call("publish", definition=unit, policy=1)
    call("enroll", learner="learner", course=1, revision=1)
    missing = call("recommendation-input", actor="learner", id="missing", course=1, revision=1, activity="coefficients")["record"]["data"]
    if missing["presenceMask"] != 0:
        raise Core0Error("absent independent assessment was fabricated as present")
    call("job-submit", job="must-use-baseline", **{"class": "interactive"}, artifacts=[], input={
        "kind": "school-linear-worker/1", "preparation": "missing", "learner": "learner", "course": 1,
        "revision": 1, "activity": "coefficients", "features": missing["features"], "presenceMask": 0},
        expected_error="retain authored baseline")
    training = args.training_dir.resolve()
    releases = {}
    for version, name, config, checkpoint in ((9001, "configured", "school-configuration.json", "configured-checkpoint.json"),
                                              (9002, "configured-v2", "school-configuration-v2.json", "configured-v2-checkpoint.json")):
        release = call("training-publish", directory=str(training/name), dataset=str(training/"permitted-dataset"),
                       checkpoint=str(training/checkpoint), configuration=str(training/config), reusable=True,
                       rights="CC0 generated numeric fixture; explicitly permitted synthetic configuration; no private learner data")
        releases[version] = release["record"]
    call("model-select", version=9001)
    work = call("work-upload", actor="learner", hex=b"For every natural t, expand both squares; my first draft omits the 2t term.".hex())
    call("attempt", actor="learner", id="independent-written-work", course=1, revision=1,
         activity="reason", values=[0, 1, 1, 2, 1], observationArtifact=work["digest"])
    assessment = call("human-assess", attempt="independent-written-work", version=1, previousSequence=0,
                      disposition="needs-revision", comment="Retain the cross term and justify every equality over the stated domain.",
                      criteria=["not-met", "met"])
    clock = 604800100  # Explicit controlled one-week scheduling fixture; no retention claim.
    prepared = call("recommendation-input", actor="learner", id="review-input", course=1, revision=1, activity="coefficients")["record"]["data"]
    if prepared["presenceMask"] != 3 or prepared["features"] != [1024, 1024]:
        raise Core0Error("actual independent human assessment did not prepare expected bounded features")
    if prepared["evidence"][0]["assessmentSequence"] != assessment["assessment"]["sequence"]:
        raise Core0Error("prepared features lost their distinct human assessment source")
    image_digest = call("artifact-put", path=str(args.image.resolve()))["digest"]
    available = [image_digest, *{digest for release in releases.values() for digest in release["artifacts"]}]
    # The provider helper supplies declarations; the actual processes below
    # supply their independent observed READY/inference evidence.
    def provider_call(op, **fields):
        fields.pop("now", None)
        return call(op, **fields)
    configure(provider_call, args.image.resolve(), available, ["configured-rv64"], now=clock)
    results = []
    def run_job(version, job):
        params = json.loads((training/("configured" if version == 9001 else "configured-v2")/"parameters.json").read_text())
        parameter_digest = releases[version]["data"]["artifact"]
        declared = dict(kind="school-linear-worker/1", requestId=version, model=version, parameters=parameter_digest,
                        imageSha256=image_digest, features=prepared["features"], presenceMask=3,
                        learner="learner", course=1, revision=1, activity="coefficients", preparation="review-input")
        call("job-submit", job=job, **{"class": "interactive"}, input=declared, artifacts=[parameter_digest, image_digest])
        lease = call("job-lease", job=job, worker="configured-rv64", duration=60000)["record"]["data"]
        target = output/job
        observed = observe(args.image.resolve(), target, [dict(name=job, job=job, requestId=version,
            words=[lease["generation"], lease["fence"], version, *params["quantized"], *prepared["features"], 3])])
        actual = observed["results"][0]
        stream = (target/"requests.bin").read_bytes()
        frame = target/"request-frame.bin"
        frame.write_bytes(stream[:16+stream[6]])
        evidence = [call("artifact-put", path=str(path.resolve()))["digest"] for path in
                    (args.image.parent/"worker-audit.json", target/"execution.json", frame, target/"requests.bin", target/"responses.bin")]
        response = call("artifact-put", path=str((target/f"response-{version}.json").resolve()))["digest"]
        call("job-complete", job=job, worker="configured-rv64", generation=lease["generation"], fence=lease["fence"],
             result=response, evidenceArtifacts=evidence, origin="actual unchanged freestanding RV64 worker")
        suggestion = call("suggest", learner="learner", course=1, revision=1, activity="coefficients", job=job)
        results.append(dict(version=version, scoreQ20=actual["scoreQ20"], suggestion=suggestion,
                            responseSha256=response, executionSha256=sha256(target/"execution.json")))
    run_job(9001, "configured-first")
    call("model-select", version=9002)
    run_job(9002, "configured-second")
    call("model-rollback", version=9001, reason="operator selected previous immutable release after fixed-split comparison")
    call("suggest", learner="learner", course=1, revision=1, activity="coefficients", job="configured-second", expected_error="selected release")
    call("suggest", learner="learner", course=1, revision=1, activity="coefficients", job="configured-first")
    models = call("models")
    if models["selection"]["data"]["version"] != 9001 or len(models["models"]) != 2:
        raise Core0Error("rollback lost immutable model history or selected the wrong release")
    if results[0]["scoreQ20"] == results[1]["scoreQ20"]:
        raise Core0Error("independently trained configurations did not change actual target inference")
    assistance = protected_assist_consumer(output, school, args.binary, call)
    check_production(args.production, args.binary, args.curriculum)
    for name, digest in observed_sources.items():
        if sha256(root/name) != digest:
            raise Core0Error("consumed workflow source changed during execution: "+name)
    report = dict(schema="lemma-school-training-workflow/1", result="PASS", modelVersions=[9001, 9002],
                  selectedAfterRollback=9001, missingIndependentEvidence="authored baseline; numerical job rejected",
                  preparation=prepared, results=results, commandsSha256=sha256(output/"commands.json"),
                  protectedAssistance=assistance,
                  production=dict(path=str(args.production), sha256=sha256(args.production)),
                  training=dict(path=str(training/"training-evidence.json"), sha256=sha256(training/"training-evidence.json")),
                  imageSha256=sha256(args.image), runnerSha256=sha256(Path(__file__)),
                  sourceInputs=observed_sources,
                  freshReused="Existing genuine hosted Lean training parameters/checkpoints/dataset and audited byte-identical RV64 worker image reused; two new actual RV64 QEMU executions, new authority commits and protected assistance packets.",
                  scope="actual hosted Lean publication/assessment/selection and fresh unchanged RV64 inference; synthetic permitted dataset, independent-work/ASK/raw receipt fixtures and controlled review clock; no guest presentation or educational-effect claim")
    write_json(output/"workflow.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work-dir", "production", "binary", "curriculum", "image", "training-dir"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    report = check(args)
    print(json.dumps({"result": report["result"], "scoresQ20": [row["scoreQ20"] for row in report["results"]],
                      "selectedAfterRollback": 9001, "receipt": str(args.work_dir/"workflow.json")}))


if __name__ == "__main__":
    main()
