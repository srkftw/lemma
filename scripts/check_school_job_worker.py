#!/usr/bin/env python3
"""Actual durable Lean school -> leased RV64 worker -> observed result -> suggestion.

All decisions are made by the maintained Lean authority. This driver invokes its
public JSON commands and conveys/observes bytes and fault schedules only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from build_actions import lean_source_inputs
from check_school_worker import observe, interrupted_job, Session, READY
from core0_common import Core0Error, repo_root, sha256, write_json
from school_provider_runner import configure as provider_configure, report as provider_report, verify_recorded_ready

def check_production(path: Path | None,binary: Path,curriculum: Path | None = None):
    if path is None:return None
    from build_school import inputs
    receipt=json.loads(path.read_text())
    if receipt.get("result")!="PASS" or receipt.get("sourceInputs")!=inputs(repo_root()):
        raise Core0Error("hosted school producer source binding no longer matches")
    if sha256(binary)!=receipt["binaries"]["school"]["sha256"]:
        raise Core0Error("school binary differs from source-bound producer")
    if curriculum and sha256(curriculum)!=receipt["binaries"]["school-curriculum"]["sha256"]:
        raise Core0Error("curriculum binary differs from source-bound producer")
    return receipt


def check(directory: Path, image: Path, parameters: Path, binary: Path, curriculum: Path,
          alternate_image: Path | None = None, training_dir: Path | None = None,
          school_source_root: Path | None = None,school_production: Path | None = None):
    root = repo_root()
    production=check_production(school_production,binary,curriculum)
    directory.mkdir(parents=True,exist_ok=False)
    school = directory/"authority"
    transcript=[]

    def command(op, *, expected_error=None, now=0, school_path=None, **fields):
        request={"op":op,"school":"worker-school","actor":"owner","now":now,**fields}
        process=subprocess.run([str(binary.resolve()),str(school_path or school),json.dumps(request)],
                               cwd=root,capture_output=True,timeout=20)
        if not process.stdout:
            raise Core0Error("Lean school returned no command response")
        result=json.loads(process.stdout)
        transcript.append({"request":request,"response":result,"exitCode":process.returncode,
                           "stderr":process.stderr.decode()})
        write_json(directory/"commands.json",transcript)
        if expected_error:
            if result.get("ok") or process.returncode==0 or expected_error not in result.get("error",""):
                raise Core0Error("authority did not reject at expected boundary: "+str(result))
            return result
        if process.returncode!=0 or not result.get("ok"):
            raise Core0Error("actual school command failed: "+str(result))
        return result["result"]

    def stage_evidence(execution_dir, request_id, actual_image, now):
        requests=(execution_dir/"requests.bin").read_bytes()
        if len(requests)<16:
            raise Core0Error("actual runtime request stream truncated")
        frame=requests[:16+requests[6]]
        frame_path=execution_dir/f"request-{request_id}.bin"
        frame_path.write_bytes(frame)
        response=json.loads((execution_dir/f"response-{request_id}.json").read_text())
        if sha256(frame_path)!=response["requestSha256"]:
            raise Core0Error("recorded request frame differs from response provenance digest")
        files=[actual_image.parent/"worker-audit.json",execution_dir/"execution.json",frame_path,
               execution_dir/"requests.bin",execution_dir/"responses.bin"]
        return [command("artifact-put",path=str(path.resolve()),now=now)["digest"] for path in files]

    def payload(path):
        state=json.loads((path/"state.json").read_text())["payload"]
        return json.loads(state) if isinstance(state,str) else state

    command("init",deployment="worker-local-a",clockModel="controlled-ms")
    definition=json.loads(subprocess.check_output([str(curriculum.resolve()),"fixture"],cwd=root,timeout=20))
    definition["course"]["identity"]="1"
    command("publish",definition=definition,policy=1,now=1)
    command("enroll",learner="learner",course=1,revision=1,now=2)
    params=json.loads(parameters.read_text())
    parameter_digest=command("artifact-put",path=str(parameters.resolve()),now=3)["digest"]
    if training_dir is None:raise Core0Error("actual training directory is required for lineage closure")
    lineage=[]
    for path,kind in [(training_dir/"dataset/manifest.json","dataset"),(training_dir/"dataset/train.jsonl","dataset"),
                      (training_dir/"dataset/evaluation.jsonl","dataset"),(training_dir/"full-checkpoint.json","checkpoint"),
                      (training_dir/"training-evidence.json","training-evidence")]:
        artifact=command("artifact-put",path=str(path.resolve()),now=3)["digest"]
        command("artifact-register",artifact=artifact,kind=kind,metadata={"scope":"synthetic owner-local numerical fixture",
                  "sourceName":path.name,"origin":"actual hosted Lean training"},now=3)
        lineage.append(artifact)
    if params["dataset"] not in lineage:raise Core0Error("registered training closure lacks exact dataset manifest")
    image_digest=command("artifact-put",path=str(image.resolve()),now=3)["digest"]
    command("artifact-register",artifact=image_digest,kind="worker-image",metadata={"profile":"core0-v0.5"},now=3)
    command("model-register",artifact=parameter_digest,artifacts=lineage,reusable=True,
            rights="Original synthetic fixture and parameters; CC0 numeric rows; no private learner records",now=4)
    command("model-select",version=params["version"],now=5)
    available=[image_digest,parameter_digest,*lineage]
    provider=provider_configure(command,image,available,["rv64-1","rv64-2","rv64-binding"],now=6)
    job="inference-real-1"
    input_data={"kind":"school-linear-worker/1","requestId":1,"model":params["version"],
                "imageSha256":sha256(image),"parameters":parameter_digest,"features":[768,512],"presenceMask":3,
                "learner":"learner","course":1,"revision":1,"activity":"coefficients"}
    command("job-submit",job=job,**{"class":"interactive"},input=input_data,artifacts=[parameter_digest,image_digest],now=100)
    command("job-lease",job=job,worker="unregistered-worker",duration=10,now=100,
            expected_error="local provider worker is not configured")
    command("node-drain",node="local",draining=True,now=100)
    command("job-lease",job=job,worker="rv64-1",duration=10,now=100,
            expected_error="local node or worker is draining")
    command("node-drain",node="local",draining=False,now=100)
    command("worker-drain",worker="rv64-1",draining=True,now=100)
    command("job-lease",job=job,worker="rv64-1",duration=10,now=100,
            expected_error="local node or worker is draining")
    command("worker-drain",worker="rv64-1",draining=False,now=100)
    first=command("job-lease",job=job,worker="rv64-1",duration=10,now=100)["record"]["data"]
    generation=first["generation"];old_fence=first["fence"]
    words=[generation,old_fence,params["version"]]+params["quantized"]+[768,512,3]
    interruption=interrupted_job(image,directory/"killed-worker",request_id=1,words=words,job=job)
    if interruption["returnCode"]!=-9:
        raise Core0Error("worker process was not actually SIGKILLed")
    interrupted_ready=verify_recorded_ready(directory/"killed-worker")
    failure_artifacts=[command("artifact-put",path=str((directory/"killed-worker"/name).resolve()),now=101)["digest"]
                       for name in ("interruption.json","requests.bin","responses.bin")]
    provider_report(command,"rv64-1",generation,available+failure_artifacts,status="offline",
                    reason="Owner observed actual QEMU SIGKILL after UART READY and a partial request; no complete inference response.",now=101)
    command("reconcile",now=101)
    reconciled_records=payload(school)["records"]
    command("reconcile",now=101)
    if payload(school)["records"]!=reconciled_records:
        raise Core0Error("repeated local provider reconciliation duplicated durable transitions")
    second=command("job-lease",job=job,worker="rv64-2",duration=60000,now=111)["record"]["data"]
    fence=second["fence"]
    if fence<=old_fence:
        raise Core0Error("durable school did not advance ownership fence")
    # A separate actual guest deliberately presents old lease data after
    # reassignment. This is late stale-ownership input, not resurrection of the
    # SIGKILLed process. The exact scope is retained in the final report.
    stale=observe(image,directory/"stale-target",[{"name":"late-stale-ownership","job":job,
                   "requestId":1,"words":words}])
    stale_path=directory/"stale-target/response-1.json"
    stale_digest=command("artifact-put",path=str(stale_path),now=112)["digest"]
    command("job-complete",job=job,worker="rv64-1",generation=generation,fence=old_fence,
            result=stale_digest,now=113,expected_error="worker or lease owner differs")
    command("job-complete",job=job,worker="rv64-2",generation=generation,fence=old_fence,
            result=stale_digest,now=113,expected_error="stale generation or lease fence")
    words=[generation,fence,params["version"]]+params["quantized"]+[768,512,3]
    execution=observe(image,directory/"current-target",[{"name":"current-trained-model-job","job":job,
                      "requestId":1,"words":words}])
    actual_path=directory/"current-target/response-1.json"
    digest=command("artifact-put",path=str(actual_path),now=114)["digest"]
    evidence_artifacts=stage_evidence(directory/"current-target",1,image,114)
    current_ready=verify_recorded_ready(directory/"current-target")
    command("node-drain",node="local",draining=True,now=114)
    command("worker-drain",worker="rv64-2",draining=True,now=114)
    completed=command("job-complete",job=job,worker="rv64-2",generation=generation,fence=fence,
                      result=digest,evidenceArtifacts=evidence_artifacts,origin="owner-local RV64-observed",now=115)
    repeated=command("job-complete",job=job,worker="rv64-2",generation=generation,fence=fence,
                     result=digest,evidenceArtifacts=evidence_artifacts,origin="owner-local RV64-observed",now=115)
    if completed.get("record",completed)!=repeated.get("record",repeated):
        raise Core0Error("retry duplicated or changed the committed result")
    if not set(evidence_artifacts)<=set(completed.get("record",completed)["artifacts"]):
        raise Core0Error("committed result did not retain its required execution/audit/raw evidence closure")
    provider_report(command,"rv64-2",generation,available+evidence_artifacts,status="ready",
                    reason="Owner observed exact UART READY and committed a completed real inference; that guest exited cleanly. Local adapter reports ready-to-launch another guest.",now=115)
    after_health=command("job-complete",job=job,worker="rv64-2",generation=generation,fence=fence,
                         result=digest,evidenceArtifacts=evidence_artifacts,origin="owner-local RV64-observed",now=115)
    if completed.get("record",completed)!=after_health.get("record",after_health):
        raise Core0Error("new reported health epoch changed an already committed exact result retry")
    command("node-drain",node="local",draining=False,now=115)
    command("worker-drain",worker="rv64-2",draining=False,now=115)
    result_sequence=completed.get("record",completed)["sequence"]
    suggestion=command("suggest",learner="learner",course=1,revision=1,activity="coefficients",job=job,now=116)["record"]
    actual=json.loads(actual_path.read_text())
    if suggestion["data"].get("scoreQ20")!=actual["scoreQ20"]:
        raise Core0Error("permitted suggestion did not consume actual committed target score")
    # These are genuine learner declarations against the actual worker-derived
    # suggestion. They must retain its immutable evidence and exact policy.
    choices=[]; choice_requests=[]
    for op,reason in (("goal-set","I choose independent coefficient reconstruction as my next goal."),
                      ("interpretation-challenge","The synthetic risk estimate does not describe my confidence."),
                      ("suggestion-override","I choose the permitted independent reconstruction instead of review.")):
        fields={"actor":"learner","learner":"learner","id":"rv64-"+op,"course":1,"revision":1,
                "policy":1,"referenceKind":"suggestion","reference":suggestion["key"],"reason":reason}
        if op=="goal-set":fields["newGoal"]="Reconstruct the distributive coefficients independently."
        row=command(op,**fields,now=116)["record"]
        original=row["data"].get("original",{})
        if (row["kind"]!="learner-choice" or row["actor"]!="learner" or
            original.get("key")!=suggestion["key"] or original.get("sequence")!=suggestion["sequence"] or
            row["data"].get("policy")!=1):
            raise Core0Error("actual suggestion choice lost ownership, policy or immutable reference")
        choices.append(row);choice_requests.append((op,fields))
    for row,(op,fields) in zip(choices,choice_requests):
        if command(op,**fields,now=117)["record"]!=row:
            raise Core0Error("later actual learner-choice retry changed its immutable record")
    learner_choices=command("learner-choices",actor="learner",learner="learner",now=117)["choices"]
    if learner_choices!=choices or [row for row in payload(school)["records"] if row["kind"]=="suggestion"]!=[suggestion]:
        raise Core0Error("learner choices changed original actual inference suggestion or were not queryable")
    # Each public command is a fresh process and reloads the durable authority.
    # A new status read therefore checks the committed result after restart.
    status=command("jobs",now=117)
    committed=[row for row in status if row["key"]==job]
    if len(committed)!=1 or committed[0]["data"]["result"]!=digest:
        raise Core0Error("fresh authority process failed to recover the committed target result")
    binding_rejections=[]
    for index,kind in enumerate(("features","model","image") if alternate_image else ("features","model")):
        number=11+index
        identity="binding-"+kind
        declared={**input_data,"requestId":number}
        command("job-submit",job=identity,**{"class":"interactive"},input=declared,artifacts=[parameter_digest,image_digest],now=118+index*5)
        lease=command("job-lease",job=identity,worker="rv64-binding",duration=60000,now=119+index*5)["record"]["data"]
        actual_words=[lease["generation"],lease["fence"],params["version"]]+params["quantized"]+[768,512,3]
        if kind=="features":actual_words[6]=512
        if kind=="model":actual_words[2]=params["version"]-1
        actual_image=alternate_image if kind=="image" else image
        observe(actual_image,directory/identity,[{"name":identity,"job":identity,"requestId":number,"words":actual_words}])
        observed_digest=command("artifact-put",path=str(directory/identity/f"response-{number}.json"),now=120+index*5)["digest"]
        evidence_refs=stage_evidence(directory/identity,number,actual_image,120+index*5)
        error="actual target input words differ" if kind=="features" else "worker response differs"
        rejected=command("job-complete",job=identity,worker="rv64-binding",generation=lease["generation"],fence=lease["fence"],
                         result=observed_digest,evidenceArtifacts=evidence_refs,now=121+index*5,expected_error=error)
        command("job-cancel",job=identity,now=122+index*5)
        binding_rejections.append({"kind":kind,"actualResponseDigest":observed_digest,"error":rejected["error"],
                                   "executionReceiptSha256":sha256(directory/identity/"execution.json")})
    # A separate real target rejects a declared oversized payload from its
    # header without receiving or accessing that payload. QEMU's documented
    # status-coded finisher returns the guest invalid-length code16.
    oversized_dir=directory/"oversized-target"
    oversized_dir.mkdir()
    oversized=Session(image,oversized_dir)
    try:
        if oversized.read(len(READY))!=READY:
            raise Core0Error("oversized target READY mismatch")
        frame=b"LMQ8"+bytes((1,1,80,0))+(1).to_bytes(8,"little")
        oversized.process.stdin.write(frame);oversized.process.stdin.flush()
        oversized.sent.extend(frame)
        oversized.process.wait(timeout=10)
        if oversized.process.returncode!=16:
            raise Core0Error("oversized target did not report exact invalid-length status16")
    finally:
        oversized.close(success=False)
    # Deliberately supplied hosted work and an effective scoped grant make the
    # reusable-package privacy checks non-vacuous. No guest verdict is invented.
    private_work=directory/"private-local-work.txt"
    private_work.write_text("Deliberately supplied local coefficient work [0,1,1,2,1]; no guest receipt.\n")
    private_work_digest=command("artifact-put",path=str(private_work),now=139)["digest"]
    command("attempt",actor="learner",id="private-local-attempt",course=1,revision=1,
            activity="coefficients",values=[0,1,1,2,1],observationArtifact=private_work_digest,now=139)
    command("grant",subject="private-reader",action="read",resource="learner",now=139)
    private_progress=command("progress",actor="private-reader",learner="learner",now=139)
    if len(private_progress["attempts"])!=1:
        raise Core0Error("source private attempt/scoped grant was not actually exercised")
    command("job-submit",job="provider-restart-probe",**{"class":"interactive"},
            input={**input_data,"requestId":901},artifacts=[parameter_digest,image_digest],now=139)
    exported=directory/"export"
    full_export=command("export",to=str(exported),now=140)
    selected_export=directory/"selected-export"
    selected_info=command("export",to=str(selected_export),throughSequence=result_sequence,now=140)
    selected_state=payload(selected_export)
    source_records=payload(school)["records"]
    if selected_state["records"]!=source_records[:result_sequence] or len(source_records)<=result_sequence:
        raise Core0Error("actual result selection did not preserve the exact committed history prefix")
    selected_refs={artifact for record in selected_state["records"] for artifact in record["artifacts"]}
    if (digest not in selected_refs or private_work_digest in selected_refs or
        any(record["kind"] in {"attempt","review","grant","suggestion","learner-choice"} for record in selected_state["records"])):
        raise Core0Error("actual result prefix lost its committed response or included later private history")
    if {path.name for path in (selected_export/"artifacts").iterdir() if path.is_file()}!=selected_refs:
        raise Core0Error("selected result export artifact closure differs from its exact records")
    command("stop",now=141)
    restored=directory/"restored-authority"
    restored_info=command("restore",school_path=restored,**{"from":str(exported)},offline=True,now=142)
    if restored_info["generation"]<=generation:raise Core0Error("restored authority did not advance execution generation")
    exported_registry=[row for row in payload(exported)["records"] if row["kind"].startswith("provider-")]
    if not exported_registry or [row for row in payload(restored)["records"] if row["kind"].startswith("provider-")]!=exported_registry:
        raise Core0Error("operational restore did not preserve the exact local provider registry history")
    command("job-lease",school_path=restored,job="provider-restart-probe",worker="rv64-2",duration=60000,now=143,
            expected_error="readiness configuration/generation is stale")
    restored_jobs=command("jobs",school_path=restored,now=143)
    if not any(r["key"]==job and r["data"].get("result")==digest for r in restored_jobs):
        raise Core0Error("restored authority lost actual committed inference")
    if command("progress",school_path=restored,actor="learner",now=143)!=private_progress:
        raise Core0Error("full operational restore lost exported actual learner progress")
    if command("learner-choices",school_path=restored,actor="learner",learner="learner",now=143)["choices"]!=choices:
        raise Core0Error("full operational restore lost the learner declarations against actual target suggestion")
    retained=[parameter_digest,image_digest,*lineage,*evidence_artifacts,digest]
    full_refs={artifact for record in payload(exported)["records"] for artifact in record["artifacts"]}
    if not set(retained+[private_work_digest])<=full_refs:
        raise Core0Error("full export omitted required inference or private work references")
    for identity in full_refs:
        restored_artifact=restored/"artifacts"/identity
        if not restored_artifact.is_file() or sha256(restored_artifact)!=identity:
            raise Core0Error("restored numerical/execution artifact closure is unresolved")
    if (restored/"state.json").stat().st_ino==(school/"state.json").stat().st_ino:
        raise Core0Error("restored mutable authority aliases original storage")
    command("job-complete",school_path=restored,job=job,worker="rv64-2",generation=generation,fence=fence,
            result=digest,evidenceArtifacts=evidence_artifacts,now=144,expected_error="stale generation or lease fence")
    command("stop",school_path=restored,now=144)
    selected_restored=directory/"selected-restored-authority"
    selected_restore=command("restore",school_path=selected_restored,**{"from":str(selected_export)},offline=True,now=142)
    selected_jobs=command("jobs",school_path=selected_restored,now=143)
    if (selected_restore["generation"]<=generation or len(selected_jobs)!=1 or selected_jobs[0]["key"]!=job or
        selected_jobs[0]["data"].get("result")!=digest or payload(selected_restored)["records"]!=selected_state["records"]):
        raise Core0Error("selected operational restore lost exact history or the actual committed target result")
    selected_progress=command("progress",school_path=selected_restored,actor="learner",now=143)
    if (selected_progress["attempts"] or selected_progress["due"] or
        command("learner-choices",school_path=selected_restored,actor="learner",learner="learner",now=143)["choices"]):
        raise Core0Error("selected restore copied later learner work outside its explicit cutoff")
    for artifact in selected_refs:
        paths=[authority/"artifacts"/artifact for authority in (school,selected_export,selected_restored)]
        if any(sha256(path)!=artifact for path in paths) or len({(path.stat().st_dev,path.stat().st_ino) for path in paths})!=3:
            raise Core0Error("selected result artifact closure is missing, altered or inode-aliased")
    if (selected_restored/"artifacts"/private_work_digest).exists():
        raise Core0Error("selected restore copied private work bytes from after its cutoff")
    command("job-complete",school_path=selected_restored,job=job,worker="rv64-2",generation=generation,fence=fence,
            result=digest,evidenceArtifacts=evidence_artifacts,now=144,expected_error="stale generation or lease fence")
    command("stop",school_path=selected_restored,now=144)
    # Reuse the real selected model release, not a publication-only fixture.
    # The definition and both consumers run the maintained Lean commands.
    definition_dir=directory/"definition-package"
    definition_info=command("definition-export",to=str(definition_dir),now=145)
    definition_path=definition_dir/"school-package.json"
    package=json.loads(definition_path.read_text())
    if (package.get("schema")!="lemma-school-package/1" or len(package.get("publications",[]))!=1 or
        len(package.get("models",[]))!=1 or package.get("selectedModel")!=params["version"]):
        raise Core0Error("reusable definition lost the actual selected trained release")
    release=package["models"][0]
    if (release["version"]!=params["version"] or release["artifact"]!=parameter_digest or
        set(release["artifacts"])!=set(lineage) or release.get("reusable") is not True or not release.get("rights")):
        raise Core0Error("actual reusable model parameter/dataset/checkpoint lineage differs")
    if any(key in package for key in ("school","deployment","operator","generation","records","grants","jobs","enrollment","attempts")):
        raise Core0Error("reusable definition contains live authority or learner state")
    public_refs={package["publications"][0]["artifact"],parameter_digest,*lineage}
    private_refs={image_digest,digest,private_work_digest,*evidence_artifacts}
    if public_refs&private_refs:
        raise Core0Error("private worker result/evidence leaked into reusable release references")
    installed=directory/"definition-authority"
    installed_school="worker-template-a";installed_owner="template-owner"
    installation=command("init-package",school_path=installed,school=installed_school,actor=installed_owner,
                         deployment="worker-template-a-local",clockModel="controlled-ms",**{"from":str(definition_dir)},now=0)
    cloned=directory/"cloned-authority";cloned_school="worker-template-b"
    clone_info=command("clone",to=str(cloned),newSchool=cloned_school,newDeployment="worker-template-b-local",now=147)
    if sha256(cloned/"definition/school-package.json")!=sha256(definition_path):
        raise Core0Error("normal clone changed the reusable typed definition")
    source_state=payload(school)
    source_kinds={row["kind"] for row in source_state["records"]}
    if not {"attempt","enrollment","grant","job","suggestion","learner-choice"}<=source_kinds:
        raise Core0Error("source privacy exclusions were not tested against actual private records")
    for destination,school_id,owner in ((installed,installed_school,installed_owner),(cloned,cloned_school,"owner")):
        status=command("status",school_path=destination,school=school_id,actor=owner,now=148)
        if (status["school"],status["deployment"])!=(school_id,school_id+"-local"):
            raise Core0Error("definition consumer retained the old deployment identity")
        if status["jobs"] or set(status["artifacts"])!=public_refs:
            raise Core0Error("definition consumer lost model closure or copied operational job data")
        progress=command("progress",school_path=destination,school=school_id,actor=owner,learner="learner",now=148)
        if progress["attempts"] or progress["due"]:
            raise Core0Error("definition consumer copied learner work/review state")
        command("progress",school_path=destination,school=school_id,actor="private-reader",learner="learner",
                now=148,expected_error="grant denied")
        command("client-course",school_path=destination,school=school_id,actor="learner",course=1,revision=1,
                now=148,expected_error="learner is not enrolled")
        state=payload(destination)
        if any(row["kind"].startswith("provider-") for row in state["records"]):
            raise Core0Error("reusable school definition copied a deployment provider node, worker, health or drain")
        if len(state["records"])!=3 or {row["kind"] for row in state["records"]}!={"publication","model","model-selection"}:
            raise Core0Error("definition consumer copied grants, enrollment, attempts, results or other live records")
        model=next(row for row in state["records"] if row["kind"]=="model")
        selection=next(row for row in state["records"] if row["kind"]=="model-selection")
        if (model["key"]!=str(params["version"]) or model["data"]["artifact"]!=parameter_digest or
            set(model["artifacts"])!={parameter_digest,*lineage} or selection["data"]["version"]!=params["version"]):
            raise Core0Error("actual parameter release or explicit model selection changed during definition installation")
    copy_roots=[school,definition_dir,installed,cloned,cloned/"definition"]
    for copied_root in copy_roots[1:]:
        if {p.name for p in (copied_root/"artifacts").iterdir() if p.is_file()}!=public_refs:
            raise Core0Error("reusable artifact directory contains missing or private bytes")
    for artifact in public_refs:
        identities=set()
        for copied_root in copy_roots:
            path=copied_root/"artifacts"/artifact
            if sha256(path)!=artifact:
                raise Core0Error("copied reusable parameter/dataset artifact bytes differ")
            identity=(path.stat().st_dev,path.stat().st_ino)
            if identity in identities:raise Core0Error("reusable model artifact copy aliases another school/package inode")
            identities.add(identity)
    state_identities={((p/"state.json").stat().st_dev,(p/"state.json").stat().st_ino) for p in (school,restored,selected_restored,installed,cloned)}
    if len(state_identities)!=5:raise Core0Error("definition/clone mutable authority inode aliases source or restore")
    preserved=command("progress",actor="learner",now=150)
    if preserved!=private_progress:raise Core0Error("definition installation changed source learner state")
    provider_status=command("provider-status",now=150)
    school_sources=school_source_root or root
    sources=lean_source_inputs(school_sources,[school_sources/"Lemma/School/Main.lean",school_sources/"Lemma/School/CurriculumMain.lean"])
    # FixtureUnit uses include_str: it is an actual compilation dependency
    # outside the ordinary import grammar, explicitly named here.
    sources["fixtures/school/Distributivity.txt"]=school_sources/"fixtures/school/Distributivity.txt"
    check_production(school_production,binary,curriculum)
    report={"schema":"lemma-school-job-worker-evidence/v1","result":"pass",
            "school":"worker-school","job":job,"generation":generation,"oldFence":old_fence,"currentFence":fence,
            "parametersDigest":parameter_digest,"actualResponseDigest":digest,
            "evidenceArtifacts":evidence_artifacts,
            "trainingLineageArtifacts":lineage,"workerImageArtifact":image_digest,
            "restoration":{"result":"pass","generation":restored_info["generation"],"resolvedRequiredArtifacts":len(full_refs),
                           "targetTrainingReceiptArtifacts":len(retained),"restoredLearnerAttempts":1,
                           "additionalPrivateWorkArtifact":private_work_digest,"export":full_export,
                           "mutableStorageAliasesOriginal":False,"preExportLease":"rejected"},
            "selectedHistory":{"result":"pass","throughSequence":result_sequence,"export":selected_info,
                               "generation":selected_restore["generation"],"resolvedRequiredArtifacts":len(selected_refs),
                               "exactCommittedRowsPreserved":True,"actualInferenceResultPreserved":True,
                               "laterPrivateWorkAndRecordsExcluded":True,"copiedArtifactInodesIndependent":True,
                               "preExportLease":"rejected","mode":"offline-authority committed-history prefix"},
            "reusableDefinition":{"result":"pass","packageSha256":sha256(definition_path),
                                  "selectedModel":params["version"],"parameterArtifact":parameter_digest,
                                  "lineageArtifacts":lineage,"resolvedArtifacts":len(public_refs),
                                  "definitionExport":definition_info,"installation":installation,"clone":clone_info,
                                  "consumerRecordKinds":["publication","model","model-selection"],
                                  "excludedSourcePrivateKinds":["attempt","enrollment","grant","job","suggestion","learner-choice"],
                                  "privateResultsAndExecutionEvidenceExcluded":True,"copiedArtifactDirectories":4,
                                  "allArtifactAndMutableInodesIndependent":True,
                                  "sourceProgressPreserved":True},
            "imageSha256":sha256(image),"schoolBinarySha256":sha256(binary),"curriculumBinarySha256":sha256(curriculum),
            "interruptReceiptSha256":sha256(directory/"killed-worker/interruption.json"),
            "currentExecutionReceiptSha256":sha256(directory/"current-target/execution.json"),
            "staleExecutionReceiptSha256":sha256(directory/"stale-target/execution.json"),
            "commandsSha256":sha256(directory/"commands.json"),"scoreQ20":actual["scoreQ20"],
            "oversizedTarget":{"declaredPayloadBytes":80,"deliveredHeaderBytes":16,
                               "guestTerminalStatus":oversized.process.returncode,"result":"rejected"},
            "bindingRejections":binding_rejections,
            "suggestion":suggestion,"learnerChoices":{"result":"pass","records":choices,
                "originalActualSuggestionRetained":True,"retryRecordsIdentical":True,
                "fullRestorePreserved":True,"selectedHistoryAndDefinitionsExcluded":True},
            "localProvider":{"configuration":provider,"finalStatus":provider_status,
                "actualInterruptedReady":interrupted_ready,"actualCompletedReady":current_ready,
                "failureArtifacts":failure_artifacts,"offlineReportedBeforeLeaseExpiry":True,
                "repeatedReconciliationRowsIdentical":True,"reportedHealthIsObservedVmReady":False,
                "admissionRejections":["unregistered worker","node draining","worker draining"],
                "activeLeaseCompletedWhileNodeAndWorkerDrained":True,
                "committedRetryAfterHealthRefreshIdentical":True,
                "operationalRegistryRecordsPreserved":len(exported_registry),
                "operationalRestoreRequiresFreshGenerationHealth":True,
                "reusableDefinitionsExcludeProviderKinds":sorted({row["kind"] for row in exported_registry}),
                "helperSha256":sha256(root/"scripts/school_provider_runner.py")},
            "sourceInputs":{name:sha256(path) for name,path in sources.items()},
            "schoolSourceRoot":str(school_sources),
            "schoolProduction":({"path":str(school_production),"sha256":sha256(school_production),
                                 "sourceInputs":production["sourceInputs"]} if production else None),
            "runnerSha256":sha256(Path(__file__)),
            "scope":"owner-local development authority; real SIGKILL/target UART/results; controlled lease clock; stale lease replay uses a separate real guest; no remote attestation or replicated authority"}
    write_json(directory/"job-worker-evidence.json",report)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--work-dir",type=Path,required=True)
    parser.add_argument("--image",type=Path,required=True)
    parser.add_argument("--parameters",type=Path,required=True)
    parser.add_argument("--binary",type=Path,default=Path(".lake/build/bin/school"))
    parser.add_argument("--curriculum",type=Path,default=Path(".lake/build/bin/school-curriculum"))
    parser.add_argument("--alternate-image",type=Path)
    parser.add_argument("--training-dir",type=Path,required=True)
    parser.add_argument("--school-source-root",type=Path)
    parser.add_argument("--school-production",type=Path)
    args=parser.parse_args()
    report=check(args.work_dir.resolve(),args.image.resolve(),args.parameters.resolve(),args.binary,args.curriculum,
                 args.alternate_image.resolve() if args.alternate_image else None,args.training_dir.resolve(),
                 args.school_source_root.resolve() if args.school_source_root else None,
                 args.school_production.resolve() if args.school_production else None)
    print(json.dumps({"result":report["result"],"job":report["job"],"scoreQ20":report["scoreQ20"],
                      "suggestion":report["suggestion"]["data"],"receipt":str(args.work_dir/"job-worker-evidence.json")},indent=2))


if __name__=="__main__":
    main()
