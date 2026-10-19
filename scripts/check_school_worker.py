#!/usr/bin/env python3
"""Source-bound school worker audit and real post-boot QEMU wire observation.

Host arithmetic here is an independent acceptance oracle, never the school or
target inference implementation. No response is synthesized for a missing run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import struct
import subprocess
import time

from build_actions import lean_source_inputs
from core0_common import Core0Error, checked, load_json, repo_root, sha256, write_json
from audit_core0 import parse_definitions_and_calls, defined_function_symbols, parse_stack_sizes
from audit_device import validate_platform_evidence, validate_toolchain_lock

READY = b"LEMMA_SCHOOL/1\nREADY\n"
MASK = (1 << 64) - 1

# Closed LLVM20 O2 poison-sensitive instruction inventory for this versioned
# worker. Source IR contains none. Each category has an explicit range premise:
# u32->u64 shifts by three fit i64; loop indices are <=1e6; Action status is u8;
# scratch offsets <4096 are disjoint from the aligned base; response offset
# branch restricts index to [16,4111]; finisher fields occupy disjoint halves.
OPTIMIZER_FLAGS = """%bin9 = shl nuw nsw i64 %cast8, 3
%1 = zext nneg i32 %arg0 to i64
%switch.gep = getelementptr inbounds nuw [20 x i8], ptr @switch.table.core0_scalar_17, i64 0, i64 %1
%action.fold.next-index10 = add nuw nsw i32 %action.fold.index29, 1
%action.fold.callback-status7 = trunc nuw nsw i64 %action.fold.callback-status-word6 to i8
%action.fold.next-index10 = add nuw nsw i32 %action.fold.index29, 1
%action.fold.callback-status7 = trunc nuw nsw i64 %action.fold.callback-status-word6 to i8
%mem.0.address.29 = or disjoint i64 %bin7, 2155876352
%action.fold.next-index9 = add nuw i32 %action.fold.index12, 1
%action.fold.next-index11 = add nuw nsw i32 %action.fold.index39, 1
%action.fold.callback-status8 = trunc nuw nsw i64 %action.fold.callback-status-word7 to i8
%narrow = add nuw nsw i32 %arg0, -2139082768
%action.fold.next-index114 = add nuw nsw i32 %action.fold.index10610, 1
%action.fold.next-index10 = add nuw nsw i32 %action.fold.index24, 1
%action.fold.next-index23 = add nuw nsw i32 %action.fold.index156, 1
%action.fold.callback-status20.le = trunc nuw i64 %action.fold.callback-status-word19 to i8
%failure.code = or disjoint i32 %failure.status.shifted, 13107""".splitlines()


def audit(directory: Path):
    root = repo_root()
    build = load_json(directory / "build.json")
    provenance = load_json(directory / "provenance.json")
    manifest = load_json(directory / "worker-manifest.json")
    abi = load_json(directory / "worker-abi.json")
    if build.get("status") != "pass" or any(record.get("artifact_category") != "school-worker"
                                            for record in (build, provenance, manifest)):
        raise Core0Error("wrong worker build/provenance/category")
    if manifest.get("contract_version") != "core0-v0.5" or abi.get("schema") != "lemma-school-worker/v1":
        raise Core0Error("wrong preserved compiler profile or versioned worker contract")
    if manifest.get("worker_contract") != abi:
        raise Core0Error("worker contract companions differ")
    roots = manifest.get("roots", [])
    if len(roots) != 1 or roots[0].get("source") != "Lemma.School.Worker.entry" or roots[0].get("signature") != {"args": []}:
        raise Core0Error("unexpected elaborated worker root")
    for name, digest in build["artifacts"].items():
        if sha256(directory / name) != digest:
            raise Core0Error("worker build artifact changed: " + name)
    sources = {row["path"]: row["sha256"] for row in provenance["source_inputs"]}
    closure = lean_source_inputs(root, [root / "examples/school/WorkerBuild.lean"])
    closure.update({name: root/name for name in ("scripts/build_core0.py", "scripts/build_school_worker.py",
                                                "scripts/check_school_worker.py")})
    for name, path in closure.items():
        if sources.get(name) != sha256(path):
            raise Core0Error("worker consumed-source identity differs: " + name)
    functions = manifest["scalar_functions"] + manifest["action_functions"]
    symbols = {row["llvm"] for row in functions} | {"core0_main"}
    allowed_external = {"core0_io_fence"}
    ir_reports = []
    for name in ("program.ll", "program.opt.ll"):
        text = (directory / name).read_text()
        defined, declared, calls = parse_definitions_and_calls(text)
        if defined != symbols or declared != allowed_external or not calls <= symbols | allowed_external:
            raise Core0Error("unknown/missing LLVM target symbol or runtime dependency")
        flag_lines = [line.strip() for line in text.splitlines()
                      if re.search(r'\b(?:nuw|nsw|inbounds|disjoint|nneg)\b', line)]
        expected_flags = OPTIMIZER_FLAGS if name == "program.opt.ll" and build["optimization"] == "O2" else []
        if flag_lines != expected_flags or re.search(r'\basm\b', text):
            raise Core0Error("unaccounted LLVM arithmetic/pointer promise or inline assembly")
        if expected_flags and (text.count('icmp ult i32 %arg0, 20') != 1 or
            text.count('@switch.table.core0_scalar_17 = private unnamed_addr constant [20 x i8] c"LEMMA_SCHOOL/1\\0AREADY", align 1') != 1):
            raise Core0Error("optimizer table bounds/content premise changed")
        if re.search(r'\b(?:float|double|half|fp128|bfloat)\b', text):
            raise Core0Error("floating-point target operation outside integer worker profile")
        # Every direct UART access is bracketed by the preserved fence. The
        # shared lowering emits exactly LSR/RBR/THR/FCR sites in this worker.
        accesses = re.findall(r'(?m)^.*(?:load|store) volatile i8.*inttoptr \(i64 (268435\d+) to ptr\).*$' , text)
        if not accesses or not set(map(int, accesses)) <= {0x10000000, 0x10000002, 0x10000005}:
            raise Core0Error("missing or unexpected UART physical access")
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.search(r'(?:load|store) volatile i8.*inttoptr \(i64 268435', line):
                if not ("@core0_io_fence()" in lines[i-1] and "@core0_io_fence()" in lines[i+1]):
                    raise Core0Error("UART access lost immediate IO fences")
        ir_reports.append({"file": name, "definedFunctions": len(defined), "external": sorted(declared),
                           "uartSites": len(accesses), "boundedOptimizerInstructions": len(flag_lines)})
    inputs = provenance["linked_inputs"]
    if [r["path"] for r in inputs] != ["startup.o", "program.o"] or provenance["link_command"] != [
            "ld.lld", "-m", "elf64lriscv", "--no-relax", "-T", "link.ld", "-Map=image.map", "-o", "image.elf", "startup.o", "program.o"]:
        raise Core0Error("unexpected target link input/recipe")
    for row in inputs:
        if sha256(directory / row["path"]) != row["sha256"]:
            raise Core0Error("linked object identity mismatch")
    observations = {}
    for name, argv in {
        "undefined": ["llvm-nm", "--undefined-only", "image.elf"],
        "symbols": ["llvm-readelf", "--symbols", "image.elf"],
        "headers": ["llvm-readelf", "--file-header", "--program-headers", "--dynamic-table", "--relocations", "--arch-specific", "image.elf"],
        "disassembly": ["llvm-objdump", "--disassemble", "--no-show-raw-insn", "image.elf"],
        "stack": ["llvm-readelf", "--stack-sizes", "program.o"],
    }.items():
        result = checked(argv, cwd=directory, timeout_seconds=30)
        output = result.stdout.decode()
        (directory / f"audit-{name}.txt").write_text(output)
        observations[name] = output
    if observations["undefined"].strip():
        raise Core0Error("unresolved target symbols")
    actual_symbols = defined_function_symbols(observations["symbols"])
    if actual_symbols != symbols | {"_start", "core0_io_fence"}:
        raise Core0Error(f"unaccounted final functions {actual_symbols ^ (symbols | {'_start', 'core0_io_fence'})}")
    if "RISC-V" not in observations["headers"] or re.search(r'\b(?:INTERP|DYNAMIC|NEEDED|R_RISCV_)\b', observations["headers"]):
        raise Core0Error("unexpected ELF architecture, dynamic dependency or final relocation")
    arch = re.search(r'Value: (rv64[^\s]+)', observations["headers"])
    if arch and any(feature in arch.group(1).split("_") for feature in ("f2p2", "d2p2", "a2p1", "c2p0")):
        raise Core0Error("forbidden target ISA extension")
    if re.search(r'\b(?:fadd|fsub|fmul|fdiv|flw|fld|fsw|fsd|amo\w*|lr\.[wd]|sc\.[wd]|vset\w*)\b', observations["disassembly"]):
        raise Core0Error("unaccounted floating/vector/atomic target instruction")
    validate_platform_evidence(sha256(directory / "platform.dtb"), (directory / "platform.dts").read_text())
    validate_toolchain_lock(load_json(root / "tooling/toolchain-lock.json"))
    report = {"schema": "lemma-school-worker-audit/v1", "result": "pass", "profile": "core0-v0.5",
              "worker": abi["schema"], "imageSha256": sha256(directory / "image.elf"),
              "sourceInputs": {name: sha256(path) for name, path in closure.items()},
              "ir": ir_reports, "linkedInputs": inputs, "functions": len(actual_symbols),
              "stackSizes": parse_stack_sizes(observations["stack"]),
              "scope": "finite artifact audit and emulator execution; no compiler-correctness or physical-performance proof"}
    write_json(directory / "worker-audit.json", report)
    return report


def encode(request_id: int, words: list[int], *, command: int = 1, version: int = 1, flags: int = 0):
    payload = b"".join(struct.pack("<Q", x & MASK) for x in words)
    return b"LMQ8" + bytes((version, command, len(payload), flags)) + struct.pack("<Q", request_id) + payload


def reference(words):
    """Independent signed integer acceptance oracle, with no Lean evaluator call."""
    generation, fence, model, w0, w1, bias, x0, x1, mask = words
    if not all((generation, fence, model)):
        return 32, 0
    if max(abs(w0), abs(w1), abs(bias)) > 8192:
        return 30, 0
    if max(abs(x0), abs(x1)) > 1024 or mask != 3:
        return 31, 0
    return 0, w0*x0 + w1*x1 + 1024*bias


class Session:
    def __init__(self, image: Path, directory: Path):
        self.directory = directory
        self.sent = bytearray()
        self.received = bytearray()
        self.buffer = bytearray()
        self.stderr_file = (directory / "qemu-stderr.log").open("wb")
        self.argv = ["qemu-system-riscv64", "-machine", "virt,acpi=off", "-accel", "tcg", "-cpu", "rv64",
                     "-smp", "1", "-m", "128M", "-bios", "none", "-nodefaults", "-nic", "none",
                     "-display", "none", "-serial", "stdio", "-monitor", "none", "-no-reboot", "-seed", "1",
                     "-kernel", str(image.resolve())]
        self.started = time.monotonic()
        self.process = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.stderr_file, start_new_session=True)

    def read(self, count):
        deadline = time.monotonic() + 20
        while len(self.buffer) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Core0Error("worker response timeout")
            ready, _, _ = select.select([self.process.stdout], [], [], remaining)
            if ready:
                chunk = os.read(self.process.stdout.fileno(), 4096)
                if not chunk:
                    raise Core0Error("worker exited before complete response")
                self.received.extend(chunk)
                self.buffer.extend(chunk)
        result = bytes(self.buffer[:count]); del self.buffer[:count]
        return result

    def request(self, request_id, words, **options):
        started = time.monotonic()
        frame = encode(request_id, words, **options)
        self.sent.extend(frame)
        self.process.stdin.write(frame); self.process.stdin.flush()
        response = self.read(48)
        if response[:5] != b"LMS8\x01" or response[6:8] != b"\x20\0" or struct.unpack_from("<Q", response, 8)[0] != request_id:
            raise Core0Error("malformed or misrouted actual worker response")
        values = struct.unpack_from("<QQQq", response, 16)
        memory = (Path(f"/proc/{self.process.pid}/status").read_text() if Path(f"/proc/{self.process.pid}/status").exists() else "")
        hwm = re.search(r'^VmHWM:\s*(\d+) kB', memory, re.M)
        return {"status": response[5], "requestId": request_id, "generation": values[0], "fence": values[1],
                "model": values[2], "scoreQ20": values[3], "responseHex": response.hex(),
                "requestSha256": hashlib.sha256(frame).hexdigest(),
                "latencySeconds": time.monotonic()-started,
                "emulatorPeakRssKiBObserved": int(hwm.group(1)) if hwm else None}

    def close(self, success=False):
        try:
            if success:
                self.process.wait(timeout=10)
                if self.process.returncode != 0 or self.buffer:
                    raise Core0Error("worker did not finish with exact clean protocol termination")
            else:
                if self.process.poll() is None:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=5)
        finally:
            self.stderr_file.close()
            (self.directory / "requests.bin").write_bytes(self.sent)
            (self.directory / "responses.bin").write_bytes(self.received)


def observe(image: Path, directory: Path, cases: list[dict]):
    directory.mkdir(parents=True, exist_ok=False)
    audit_report = audit(image.parent)
    session = Session(image, directory)
    results = []
    try:
        if session.read(len(READY)) != READY:
            raise Core0Error("worker READY frame mismatch")
        for case in cases:
            words = case["words"]
            row = session.request(case["requestId"], words, **case.get("wire", {}))
            status, score = case.get("expected", reference(words))
            if (row["status"], row["scoreQ20"]) != (status, score):
                raise Core0Error(f"independent worker mismatch: {case['name']}: {row}")
            if status in (0,30,31,32) and (row["generation"],row["fence"],row["model"]) != tuple(words[:3]):
                raise Core0Error("target failed to echo job lease/model identity")
            row.update({"case": case["name"], "job": case.get("job", case["name"]),
                        "origin": "rv64-observed", "profile": "core0-v0.5", "numericProfile": "school-linear-q10-v1",
                        "imageSha256": sha256(image), "workerAuditSha256": sha256(image.parent / "worker-audit.json"),
                        "inputWords": [word & MASK for word in words]})
            results.append(row)
        end = session.request(999999, [], command=2)
        if end["status"] != 0:
            raise Core0Error("worker exit response failed")
        session.close(success=True)
    except BaseException:
        session.close(success=False)
        raise
    report = {"schema": "lemma-school-worker-execution/v1", "result": "pass", "backend": "QEMU TCG RV64 M-mode",
              "profile": "core0-v0.5", "command": session.argv, "imageSha256": sha256(image),
              "auditSha256": sha256(image.parent / "worker-audit.json"), "elapsedSeconds": time.monotonic()-session.started,
              "requestsSha256": sha256(directory / "requests.bin"), "responsesSha256": sha256(directory / "responses.bin"),
              "results": results, "runnerSha256": sha256(Path(__file__)),
              "sourceInputs": audit_report["sourceInputs"], "producer": {"source_commit": checked(["git","rev-parse","HEAD"],cwd=repo_root(),timeout_seconds=15).stdout.decode().strip()}}
    write_json(directory / "execution.json", report)
    for row in results:
        row["executionReceiptSha256"] = sha256(directory / "execution.json")
        write_json(directory / f"response-{row['requestId']}.json", row)
    return report


def interrupted_job(image: Path, directory: Path, *, request_id: int, words: list[int], job: str):
    """Kill a real worker after the job's partial runtime frame was delivered.

    Returns interruption evidence only. The durable school decides retry policy;
    this function never manufactures a target inference response.
    """
    directory.mkdir(parents=True, exist_ok=False)
    audit(image.parent)
    session = Session(image, directory)
    try:
        if session.read(len(READY)) != READY:
            raise Core0Error("interrupted worker READY mismatch")
        partial = encode(request_id, words)[:32]
        session.process.stdin.write(partial);session.process.stdin.flush()
        session.sent.extend(partial)
        os.killpg(session.process.pid, signal.SIGKILL)
        session.process.wait(timeout=5)
    finally:
        session.close(success=False)
    report = {"schema":"lemma-school-worker-interruption/v1","result":"observed-interruption",
              "job":job,"requestId":request_id,"generation":words[0],"fence":words[1],
              "command":session.argv,"signal":"SIGKILL","returnCode":session.process.returncode,
              "deliveredFramePrefixBytes":len(session.sent),"completeResponseObserved":False,
              "imageSha256":sha256(image),"requestsSha256":sha256(directory/"requests.bin"),
              "responsesSha256":sha256(directory/"responses.bin"),"runnerSha256":sha256(Path(__file__)),
              "scope":"real UART prefix delivered to live process before kill; durable lease owner must reconcile"}
    write_json(directory/"interruption.json",report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--alternate-parameters", type=Path)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--job", default="school-inference-1")
    parser.add_argument("--request-id", type=int, default=1)
    parser.add_argument("--generation", type=int, default=1)
    parser.add_argument("--fence", type=int, default=1)
    parser.add_argument("--feature0", type=int, default=768)
    parser.add_argument("--feature1", type=int, default=512)
    parser.add_argument("--interrupt-after-prefix", action="store_true")
    args = parser.parse_args()
    params = load_json(args.parameters)
    if params.get("schema") != "lemma-linear-parameters/v1" or params.get("profile") != "school-linear-q10-v1":
        raise Core0Error("incompatible trained parameter artifact")
    q = params["quantized"]
    prefix = [args.generation,args.fence,params["version"]]
    if args.interrupt_after_prefix:
        report = interrupted_job(args.image,args.work_dir,request_id=args.request_id,
                                 words=prefix+q+[args.feature0,args.feature1,3],job=args.job)
        print(json.dumps(report,indent=2));return
    cases = [{"name": "trained-model-job", "job": args.job, "requestId": args.request_id,
              "words": prefix + q + [args.feature0,args.feature1,3]}]
    if args.alternate_parameters:
        alternate = load_json(args.alternate_parameters)
        cases += [{"name": "different-features", "requestId": 2, "words": prefix+q+[0,0,3]},
                  {"name": "different-trained-parameters", "requestId": 3,
                   "words": [args.generation,args.fence,alternate["version"]]+alternate["quantized"]+[args.feature0,args.feature1,3]},
                  {"name": "missing-feature-fallback", "requestId": 4, "words": prefix+q+[0,0,1]},
                  {"name": "parameter-bound-rejection", "requestId": 5, "words": prefix+[8193,0,0]+[0,0,3]},
                  {"name": "feature-bound-rejection", "requestId": 6, "words": prefix+q+[1025,0,3]},
                  {"name": "signed-minimum-accumulation", "requestId": 7,
                   "words": prefix+[-8192,8192,-8192]+[1024,-1024,3]},
                  {"name": "signed-maximum-accumulation", "requestId": 8,
                   "words": prefix+[8192,8192,8192]+[1024,1024,3]},
                  {"name": "wrong-wire-version", "requestId": 9, "words": prefix+q+[0,0,3],
                   "wire": {"version": 2}, "expected": (14,0)}]
    report = observe(args.image, args.work_dir, cases)
    if args.alternate_parameters:
        values = [row["scoreQ20"] for row in report["results"][:3]]
        if values[0] == values[1] or values[0] == values[2]:
            raise Core0Error("actual runtime input/parameter variation did not change prediction")
    print(json.dumps({"result": report["result"], "cases": len(cases), "receipt": str(args.work_dir/"execution.json")},indent=2))


if __name__ == "__main__":
    main()
