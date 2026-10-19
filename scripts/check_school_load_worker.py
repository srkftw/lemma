#!/usr/bin/env python3
"""Tiny declared four-worker workload through actual Lean admission and RV64 IO.

Threading supplies a fixed test schedule, not a production scheduler. School
queue/lease/capacity decisions remain entirely in Lean.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import threading
import time

from check_school_worker import Session, READY, MASK, audit, reference
from build_actions import lean_source_inputs
from core0_common import Core0Error, repo_root, sha256, write_json
from check_school_job_worker import check_production
from school_provider_runner import configure as provider_configure, report as provider_report, observe_ready


def check(directory: Path,image: Path,parameters: Path,binary: Path,training_dir: Path,school_source_root: Path | None = None,
          school_production: Path | None = None,curriculum: Path | None = None):
    root=repo_root();directory.mkdir(parents=True,exist_ok=False)
    production=check_production(school_production,binary)
    curriculum=curriculum or (Path(production["binaries"]["school-curriculum"]["path"]) if production else binary.with_name("school-curriculum"))
    check_production(school_production,binary,curriculum)
    authority=directory/"authority";commands=[]
    def call(op,*,error=None,now=0,**fields):
        request={"op":op,"school":"bounded-worker-load","actor":"owner","now":now,**fields}
        start=time.monotonic()
        process=subprocess.run([str(binary.resolve()),str(authority),json.dumps(request)],cwd=root,capture_output=True,timeout=20)
        elapsed=time.monotonic()-start
        result=json.loads(process.stdout)
        commands.append({"request":request,"response":result,"elapsedSeconds":elapsed})
        write_json(directory/"commands.json",commands)
        if error:
            if result.get("ok") or error not in result.get("error",""):
                raise Core0Error("actual admission failed to reject "+op+": "+str(result))
        elif process.returncode or not result.get("ok"):
            raise Core0Error("actual Lean command failed: "+str(result))
        return result.get("result",result),elapsed
    call("init",deployment="load-local-a",clockModel="controlled-ms",budgets={
        "maxEvents":10000,"maxArtifactBytes":8388608,"maxQueued":8,"interactiveReserve":2,
        "maxLeased":4,"maxRetries":3,"maxLeaseMs":60000})
    fixture=subprocess.check_output([str(curriculum.resolve()),"fixture"],cwd=root,timeout=20)
    definition=json.loads(fixture);definition["course"]["identity"]="1"
    write_json(directory/"learner-definition.json",definition)
    publication,_=call("publish",definition=definition,policy=1,now=1)
    expected_package=publication["record"]["data"]["artifact"]
    call("enroll",learner="learner",course=1,revision=1,now=1)
    call("attempt",actor="learner",id="learner-load-baseline",course=1,revision=1,
         activity="coefficients",values=[0,1,1,2,1],now=1)
    baseline_progress,_=call("progress",actor="learner",now=1)
    attempts=baseline_progress.get("attempts",[])
    if (len(attempts)!=1 or attempts[0]["actor"]!="learner" or attempts[0]["data"].get("outcome")!=1 or
        attempts[0]["data"].get("origin")!="deliberately supplied local work"):
        raise Core0Error("actual learner baseline did not preserve the declared hosted typed work")
    def learner_requests(phase,now):
        course,course_seconds=call("client-course",actor="learner",course=1,revision=1,now=now)
        package=bytes.fromhex(course["package_hex"])
        if (course.get("identity"),course.get("edition"),course.get("policy"))!=(1,1,1) or course.get("artifact")!=expected_package or hashlib.sha256(package).hexdigest()!=expected_package:
            raise Core0Error("enrolled learner received different immutable package bytes under worker load")
        progress,progress_seconds=call("progress",actor="learner",now=now)
        if progress!=baseline_progress:
            raise Core0Error("enrolled learner progress changed or disappeared under worker load")
        course_path=directory/f"learner-course-{phase}.json";progress_path=directory/f"learner-progress-{phase}.json"
        write_json(course_path,course);write_json(progress_path,progress)
        return {"courseSeconds":course_seconds,"progressSeconds":progress_seconds,"packageBytes":len(package),
                "packageSha256":expected_package,"courseResponseSha256":sha256(course_path),
                "progressResponseSha256":sha256(progress_path),"observedTypedAttempts":len(progress["attempts"])}
    params=json.loads(parameters.read_text())
    registered,_=call("artifact-put",path=str(parameters.resolve()),now=1);param_digest=registered["digest"]
    lineage=[]
    for path in (training_dir/"dataset/manifest.json",training_dir/"dataset/train.jsonl",training_dir/"dataset/evaluation.jsonl",
                 training_dir/"full-checkpoint.json",training_dir/"training-evidence.json"):
        registered,_=call("artifact-put",path=str(path.resolve()),now=1);lineage.append(registered["digest"])
    registered,_=call("artifact-put",path=str(image.resolve()),now=1);image_digest=registered["digest"]
    call("model-register",artifact=param_digest,artifacts=lineage,now=2)
    provider_call=lambda op,**fields:call(op,**fields)[0]
    available=[image_digest,param_digest,*lineage]
    provider=provider_configure(provider_call,image,available,[f"rv64-load-{i}" for i in range(5)]+["rv64-over-capacity"],now=3)
    def input_for(index):
        return {"kind":"school-linear-worker/1","requestId":100+index,"model":params["version"],
                "parameters":param_digest,"imageSha256":sha256(image),"features":[index*256,512],"presenceMask":3}
    call("job-submit",job="oversized-input",**{"class":"bulk"},input={"bytes":"x"*4097},artifacts=[],now=3,
         error="job input too large")
    for i in range(5):
        call("job-submit",job=f"load-{i}",**{"class":"interactive"},input=input_for(i),artifacts=[param_digest,image_digest],now=100)
    leases=[]
    for i in range(4):
        lease,_=call("job-lease",job=f"load-{i}",worker=f"rv64-load-{i}",duration=60000,now=100)
        leases.append(lease["record"]["data"])
    call("job-lease",job="load-4",worker="rv64-over-capacity",duration=60000,now=100,error="worker capacity exhausted")
    call("job-submit",job="bulk-slot",**{"class":"bulk"},input={},artifacts=[],now=101)
    call("job-submit",job="bulk-reserve-reject",**{"class":"bulk"},input={},artifacts=[],now=101,error="interactive reserve protected")
    for i in range(2):call("job-submit",job=f"reserved-{i}",**{"class":"interactive"},input={},artifacts=[],now=101)
    call("job-submit",job="queue-over-capacity",**{"class":"interactive"},input={},artifacts=[],now=101,error="queue backpressure")
    audit_report=audit(image.parent)
    ready=threading.Semaphore(0);start_gate=threading.Event();ready_observations=[None]*4
    def worker(i):
        target=directory/f"worker-{i}";target.mkdir()
        session=Session(image,target)
        try:
            if session.read(len(READY))!=READY:raise Core0Error("load worker READY mismatch")
            ready_observations[i]=observe_ready(session,target,image,f"rv64-load-{i}")
            # Hold all four actual processes at an explicit test barrier while
            # measuring control-plane status for their already leased jobs.
            os.killpg(session.process.pid,signal.SIGSTOP);ready.release()
            if not start_gate.wait(20):raise Core0Error("load start barrier timeout")
            os.killpg(session.process.pid,signal.SIGCONT)
            lease=leases[i]
            words=[lease["generation"],lease["fence"],params["version"]]+params["quantized"]+[i*256,512,3]
            row=session.request(100+i,words)
            expected=reference(words)
            if (row["status"],row["scoreQ20"])!=expected:raise Core0Error("independent concurrent target mismatch")
            row.update({"job":f"load-{i}","origin":"rv64-observed","profile":"core0-v0.5",
                        "numericProfile":"school-linear-q10-v1","imageSha256":sha256(image),
                        "workerAuditSha256":sha256(image.parent/"worker-audit.json"),
                        "inputWords":[word&MASK for word in words]})
            if session.request(999999,[],command=2)["status"]!=0:raise Core0Error("load target exit rejection")
            session.close(success=True)
        except BaseException:
            session.close(success=False);raise
        execution={"schema":"lemma-school-worker-execution/v1","result":"pass","command":session.argv,
                   "imageSha256":sha256(image),"requestsSha256":sha256(target/"requests.bin"),
                   "responsesSha256":sha256(target/"responses.bin"),"results":[row],
                   "sourceInputs":audit_report["sourceInputs"],"runnerSha256":sha256(Path(__file__))}
        write_json(target/"execution.json",execution)
        row["executionReceiptSha256"]=sha256(target/"execution.json")
        write_json(target/f"response-{100+i}.json",row)
        stream=(target/"requests.bin").read_bytes();(target/"request-frame.bin").write_bytes(stream[:16+stream[6]])
        return row
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(worker,i) for i in range(4)]
        try:
            for _ in range(4):
                if not ready.acquire(timeout=20):raise Core0Error("actual four-worker admission/startup failed")
            ready_artifacts=[]
            for i,paths in enumerate(ready_observations):
                artifacts=[]
                for path in paths:
                    artifact,_=call("artifact-put",path=str(path.resolve()),now=102);artifacts.append(artifact["digest"])
                ready_artifacts.append(artifacts)
            _,pending_latency=call("status",now=102)
            pending_learner=learner_requests("paused",102)
            started=time.monotonic();start_gate.set()
            released_learner=learner_requests("released",103)
            _,concurrent_latency=call("status",now=103)
            results=[future.result(timeout=30) for future in futures]
            execution_seconds=time.monotonic()-started
        finally:start_gate.set()
    for i,row in enumerate(results):
        target=directory/f"worker-{i}";now=104+i
        response,_=call("artifact-put",path=str(target/f"response-{100+i}.json"),now=now)
        evidence=list(ready_artifacts[i])
        for path in [image.parent/"worker-audit.json",target/"execution.json",target/"request-frame.bin",target/"requests.bin",target/"responses.bin"]:
            artifact,_=call("artifact-put",path=str(path.resolve()),now=now);evidence.append(artifact["digest"])
        complete,_=call("job-complete",job=f"load-{i}",worker=f"rv64-load-{i}",generation=row["generation"],fence=row["fence"],
                        result=response["digest"],evidenceArtifacts=evidence,origin="owner-local RV64-observed",now=now)
        if not set(evidence)<=set(complete["record"]["artifacts"]):raise Core0Error("load result lost receipt closure")
        provider_report(provider_call,f"rv64-load-{i}",provider["generation"],available+evidence,status="ready",
                        reason="Owner observed exact READY and committed inference in retained raw bytes; that guest exited cleanly. Adapter reports ready-to-launch.",now=now)
    _,after_latency=call("status",now=108)
    recovered,_=call("jobs",now=109)
    provider_status,_=call("provider-status",now=109)
    committed={row["key"]:row for row in recovered}
    for i,row in enumerate(results):
        actual=committed.get(f"load-{i}",{}).get("data",{})
        if actual.get("status")!="completed" or actual.get("result")!=sha256(directory/f"worker-{i}/response-{100+i}.json"):
            raise Core0Error("fresh authority process lost a completed actual target job")
    latencies=[row["latencySeconds"] for row in results]
    school_sources=school_source_root or root
    check_production(school_production,binary,curriculum)
    report={"schema":"lemma-school-worker-load-evidence/v1","result":"pass","concurrentWorkers":4,
            "leasedCapacity":4,"queuedCapacity":8,"interactiveReserve":2,"actualTargetJobsCompleted":4,
            "freshProcessRecoveredAllFourCompletedJobs":True,
            "rejections":["fifth active lease","bulk consumes interactive reserve","ninth queue item","4097-byte input"],
            "statusLatencySeconds":{"fourProcessesPausedAtExplicitBarrier":pending_latency,
                                    "afterConcurrentRelease":concurrent_latency,"afterCompletions":after_latency},
            "enrolledLearnerRequests":{"fourProcessesPausedAtExplicitBarrier":pending_learner,
                                       "afterConcurrentRelease":released_learner,
                                       "progressScope":"one deliberately supplied hosted typed attempt; no guest observation invented"},
            "targetRoundTripSeconds":{"minimum":min(latencies),"median":statistics.median(latencies),"maximum":max(latencies)},
            "concurrentExecutionSeconds":execution_seconds,"emulatorPeakRssKiBObserved":[r["emulatorPeakRssKiBObserved"] for r in results],
            "scoresQ20":[r["scoreQ20"] for r in results],"imageSha256":sha256(image),"schoolBinarySha256":sha256(binary),
            "localProvider":{"configuration":provider,"finalStatus":provider_status,
                "readyObservationArtifacts":ready_artifacts,"observedRealReadyWorkers":4,
                "reportedHealthIsObservedVmReady":False,"helperSha256":sha256(root/"scripts/school_provider_runner.py")},
            "curriculumBinarySha256":sha256(curriculum),"learnerDefinitionSha256":sha256(directory/"learner-definition.json"),
            "schoolSourceInputs":{name:sha256(path) for name,path in lean_source_inputs(school_sources,[school_sources/"Lemma/School/Main.lean"]).items()},
            "schoolSourceRoot":str(school_sources),
            "schoolProduction":({"path":str(school_production),"sha256":sha256(school_production),
                                 "sourceInputs":production["sourceInputs"]} if production else None),
            "runnerSha256":sha256(Path(__file__)),"commandsSha256":sha256(directory/"commands.json"),
            "scope":"tiny four-job synthetic fixture on one host; actual enrolled course/progress requests at an explicit paused barrier and after concurrent release; no sustained load, drawing/browser responsiveness, native-RISC-V or hyperscale claim"}
    write_json(directory/"load-evidence.json",report)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--work-dir",type=Path,required=True);parser.add_argument("--image",type=Path,required=True)
    parser.add_argument("--parameters",type=Path,required=True);parser.add_argument("--binary",type=Path,default=Path(".lake/build/bin/school"))
    parser.add_argument("--training-dir",type=Path,required=True)
    parser.add_argument("--school-source-root",type=Path)
    parser.add_argument("--school-production",type=Path)
    parser.add_argument("--curriculum",type=Path,help="source-bound producer curriculum executable; defaults to its receipt path")
    args=parser.parse_args();print(json.dumps(check(args.work_dir.resolve(),args.image.resolve(),args.parameters.resolve(),args.binary,args.training_dir.resolve(),
            args.school_source_root.resolve() if args.school_source_root else None,
            args.school_production.resolve() if args.school_production else None,args.curriculum),indent=2))
if __name__=="__main__":main()
