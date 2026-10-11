#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host-only, bounded synthesis/layout of the exact RTL sources supplied.

No simulation memory adapter or replacement black boxes are accepted as cells.
Outputs are deliberately retained on failure; an existing output is never reused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "tooling/silicon/physical-lock.json"


class CommandFailure(RuntimeError):
    def __init__(self, message: str, record: dict):
        super().__init__(message)
        self.record = record


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quoted(path: Path | str) -> str:
    value = str(path)
    if any(c in value for c in ('"', '\n', '\r')):
        raise ValueError("Unsupported quote/newline in synthesis path")
    return '"' + value + '"'


def slang_token(value: Path | str) -> str:
    # read_slang receives Yosys's original command tail; quotes remain literal.
    value = str(value)
    if any(c.isspace() or c in '\";\\' for c in value):
        raise ValueError("Whitespace/quotes in read_slang paths are unsupported")
    return value


def run(argv: list[str], output: Path, deadline: float, stdin: Path | None = None) -> dict:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RuntimeError("Physical-flow deadline exhausted")
    started = time.monotonic()
    timed_out = False
    interrupted = None
    with output.open("wb") as log:
        input_stream = stdin.open("rb") if stdin else None
        process = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True, stdin=input_stream)
        def request_stop(number, frame):
            nonlocal interrupted
            interrupted = number
            raise InterruptedError("Physical-flow cancellation")
        previous_handlers = {number: signal.signal(number, request_stop)
                             for number in (signal.SIGINT, signal.SIGTERM)}
        try:
            code = process.wait(timeout=remaining)
        except (subprocess.TimeoutExpired, InterruptedError):
            timed_out = interrupted is None
            for number in previous_handlers:
                signal.signal(number, signal.SIG_IGN)
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            code = process.returncode
        finally:
            for number, handler in previous_handlers.items():
                signal.signal(number, handler)
        if input_stream:
            input_stream.close()
    result = {"argv": argv, "exit_code": code,
              "seconds": round(time.monotonic() - started, 3), "log": str(output),
              "log_sha256": sha(output), "timed_out": timed_out}
    if stdin:
        result.update({"stdin": str(stdin), "stdin_sha256": sha(stdin)})
    if interrupted is not None:
        result["interrupted_signal"] = interrupted
        raise CommandFailure(f"Canceled: {argv[0]}; retained {output}", result)
    if timed_out:
        raise CommandFailure(f"Deadline exceeded: {argv[0]}; retained {output}", result)
    if code:
        print(output.read_text(errors="replace")[-6000:], file=sys.stderr)
        raise CommandFailure(f"Command exited {code}: {argv[0]}; retained {output}", result)
    return result


def inspect_netlist(path: Path, top: str, mapped: bool) -> dict:
    data = json.loads(path.read_text())
    modules = data["modules"]
    if top not in modules or not modules[top].get("cells"):
        raise RuntimeError("Empty or missing synthesis top")
    if modules[top].get("memories"):
        raise RuntimeError("Residual memory objects after register-memory synthesis")
    cells = modules[top]["cells"]
    types: dict[str, int] = {}
    for cell in cells.values():
        kind = cell["type"]
        types[kind] = types.get(kind, 0) + 1
        if "latch" in kind.lower() or "dlatch" in kind.lower():
            raise RuntimeError(f"Unexpected inferred latch: {kind}")
        if mapped:
            if not kind.startswith("sg13g2_") or kind not in modules:
                raise RuntimeError(f"Unresolved/unmapped cell: {kind}")
        elif not kind.startswith("$_"):
            raise RuntimeError(f"Unresolved cell or memory after generic synthesis: {kind}")
    return {"cells": len(cells), "cell_types": types,
            "inferred_memory_bits": 0, "unresolved_cells": [], "latches": 0,
            "storage_scope": "Any RTL arrays have been lowered into included register cells"}


def lvs_matches(report: str) -> bool:
    # Netgen can report a unique topological match and subsequently list
    # property errors. Matching subcells also do not certify the top level.
    # The pinned Netgen prints an optional additional period-only line.
    final = re.split(r"(?:^|\n)Final result:\s*", report)
    return len(final) == 2 and re.fullmatch(
        r"Circuits match uniquely\.\s*(?:\.\s*)?", final[1]) is not None


def layout_reports(out: Path, *, global_route: bool = False) -> dict:
    prefix = "global-" if global_route else ""
    summary = "global-route-summary.json" if global_route else "layout-summary.json"
    result = json.loads((out / summary).read_text())
    for kind in ("setup", "hold"):
        report = (out / f"{prefix}{kind}-summary.rpt").read_text()
        direction = "max" if kind == "setup" else "min"
        slack = re.fullmatch(r"worst slack " + direction + r" ([-+0-9.]+)\s*", report)
        if not slack:
            raise RuntimeError(f"Missing {prefix}{kind} timing estimate")
        value = float(slack.group(1))
        result[f"{kind}_worst_slack_ns"] = value
        result[f"{kind}_timing"] = "MET" if value >= 0 else "VIOLATED"
    return result


def router_drc(count: str) -> dict:
    if not re.fullmatch(r"[0-9]+\s*", count):
        raise RuntimeError("Missing or malformed detailed-router violation count")
    violations = int(count)
    return {"status": "PASS" if violations == 0 else "FAIL", "violations": violations,
            "scope": "Detailed-router geometric checks; separate from process DRC"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top")
    ap.add_argument("--manifest", type=Path, help="Ordered source/include manifest from silicon_compute.py manifest")
    ap.add_argument("--source", action="append", default=[])
    ap.add_argument("--file-list", type=Path)
    ap.add_argument("--include", action="append", default=[])
    ap.add_argument("--define", action="append", default=[])
    ap.add_argument("--parameter", action="append", default=[], help="Integer top parameter, for example REGISTER_RAM=1")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--reuse", type=Path, help="Reuse validated unchanged generic/mapped outputs from a passing result")
    ap.add_argument("--pdk", type=Path, default=ROOT / "build/silicon/deps/ihp-open-pdk")
    ap.add_argument("--map", action="store_true", dest="mapping")
    ap.add_argument("--map-effort", choices=("normal", "bounded"), default="normal",
                    help="normal ABC optimization or bounded structural standard-cell mapping")
    ap.add_argument("--layout", action="store_true")
    ap.add_argument("--process-checks", action="store_true", help="After layout, attempt Magic process DRC and Netgen transistor LVS")
    ap.add_argument("--clock", default="clk")
    ap.add_argument("--clock-ns", type=float, default=10)
    ap.add_argument("--deadline", type=float, default=1800)
    args = ap.parse_args()
    out = args.output_dir.resolve()
    if out.exists():
        ap.error("Use an unused output directory; retained evidence must not be overwritten")
    if args.deadline <= 0 or args.clock_ns <= 0:
        ap.error("Deadline and clock period must be positive")
    if args.process_checks and not args.layout:
        ap.error("--process-checks requires --layout")
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*=[0-9]+", p) for p in args.parameter):
        ap.error("Top parameters must be name=unsigned_decimal_integer")
    sources = list(args.source)
    if args.manifest:
        manifest = json.loads(args.manifest.read_text())
        sources += manifest["sources"]
        args.include += manifest["include_dirs"]
        if not args.top:
            args.top = manifest["top"]
    if args.file_list:
        sources += [line.strip() for line in args.file_list.read_text().splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
    paths = [Path(p).resolve() for p in sources]
    if not paths or any(not p.is_file() for p in paths):
        ap.error("A nonempty corpus of actual RTL files is required")
    if not args.top or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", args.top):
        ap.error("Invalid RTL top identifier")
    out.mkdir(parents=True)
    deadline = time.monotonic() + args.deadline
    header_paths = sorted({p.resolve() for d in args.include for pattern in ("*.vh", "*.svh")
                           for p in Path(d).rglob(pattern)})
    input_paths = list(dict.fromkeys(paths + header_paths))
    recipes = {name: (ROOT / f"tooling/silicon/{name}.tcl").read_text()
               for name in ("layout", "process", "extract")}
    result = {"schema": "lemma-silicon-physical-result/0.1.0", "status": "FAIL",
              "top": args.top, "source_commit": subprocess.check_output(
                  ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "dirty_paths": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines(),
              "source_inputs": {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT)
                                else str(p): sha(p) for p in input_paths},
              "defines": args.define, "parameters": args.parameter, "includes": args.include,
              "recipe_sha256": sha(Path(__file__)),
              "eda_recipe_sha256": sha(ROOT / "tooling/silicon/eda.nix"),
              **{f"{name}_recipe_sha256": hashlib.sha256(text.encode()).hexdigest()
                 for name, text in recipes.items()},
              "physical_lock_sha256": sha(LOCK), "commands": [],
              "mapping_profile": "sg13g2-register-cells-ties/0.1.0" if args.map_effort == "normal"
                                 else "sg13g2-register-cells-ties-bounded/0.1.0",
              "scope": "RTL slice only; no external memory/media/panel model synthesized",
              "drc": "NOT_RUN", "lvs": "NOT_RUN", "foundry_signoff": "UNVERIFIED"}
    try:
        yosys = shutil.which("yosys")
        if not yosys:
            raise RuntimeError("Yosys missing: use nix-shell tooling/silicon/eda.nix")
        result["tools"] = {"yosys_path": yosys,
                           "yosys_version": subprocess.check_output([yosys, "-V"], text=True).strip()}
        expected_yosys = json.loads(LOCK.read_text())["tools"]["yosys"]
        actual_yosys = re.search(r"Yosys\s+([0-9.]+)", result["tools"]["yosys_version"])
        if not actual_yosys or actual_yosys.group(1) != expected_yosys:
            raise RuntimeError("Yosys must match the pinned version")
        previous = None
        if args.reuse:
            previous = json.loads((args.reuse / "result.json").read_text())
            if (previous["status"] != "PASS" or previous["source_inputs"] != result["source_inputs"]
                    or previous["top"] != args.top or previous.get("defines", []) != args.define
                    or previous.get("parameters", []) != args.parameter
                    or previous.get("includes", []) != args.include
                    or previous["tools"]["yosys_path"] != result["tools"]["yosys_path"]
                    or previous["tools"]["yosys_version"] != result["tools"]["yosys_version"]):
                raise RuntimeError("Reuse requires a passing result with unchanged source, configuration, tool and physical pins")
            def copy_checked(name):
                artifact = args.reuse / name
                if sha(artifact) != previous["artifacts"][name]:
                    raise RuntimeError(f"Changed cached synthesis artifact: {name}")
                shutil.copyfile(artifact, out / name)
            copy_checked("generic.json")
            copy_checked("generic.v")
            result["reused_synthesis"] = {"result": str((args.reuse / "result.json").resolve()),
                                          "result_sha256": sha(args.reuse / "result.json")}
        frontend = "read_slang --top " + args.top + " --single-unit "
        frontend += " ".join("-I" + slang_token(Path(p).resolve()) for p in args.include) + " "
        frontend += " ".join("-D" + slang_token(p) for p in args.define) + " "
        frontend += " ".join("-G" + slang_token(p) for p in args.parameter) + " "
        frontend += " ".join(slang_token(p) for p in paths)
        generic = out / "generic.ys"
        generic.write_text(frontend + "\n" + f"synth -top {args.top} -flatten -noabc\n" +
                           "check -assert\n" + f"write_json {quoted(out / 'generic.json')}\n" +
                           f"write_verilog -noattr {quoted(out / 'generic.v')}\nstat\n")
        if previous is None:
            result["commands"].append(run([yosys, "-s", str(generic)], out / "generic.log", deadline))
        result["generic"] = inspect_netlist(out / "generic.json", args.top, False)
        if args.mapping or args.layout:
            pin = json.loads(LOCK.read_text())["pdk"]["revision"]
            pdk = args.pdk.resolve()
            revision = subprocess.check_output(["git", "-C", str(pdk), "rev-parse", "HEAD"], text=True).strip()
            if revision != pin or subprocess.check_output(["git", "-C", str(pdk), "status", "--porcelain"], text=True).strip():
                raise RuntimeError("PDK must match the exact clean inspected revision")
            std = pdk / "ihp-sg13g2/libs.ref/sg13g2_stdcell"
            lib = std / "lib/sg13g2_stdcell_typ_1p20V_25C.lib"
            collateral = [lib, std / "lef/sg13g2_tech.lef", std / "lef/sg13g2_stdcell.lef"]
            result["pdk"] = {"revision": revision, "collateral": {str(p.relative_to(pdk)): sha(p) for p in collateral},
                             "corner": "typical 1.20 V 25 C"}
            mapping = out / "mapping.ys"
            abc = f"abc -liberty {quoted(lib)}\n"
            if args.map_effort == "bounded":
                abc_script = out / "mapping.abc"
                # Standard structural hashing and technology mapping, without
                # the default SAT sweeping/logic rewriting of a large core.
                abc_script.write_text("strash; &get -n; &nf; &put\n")
                abc = f"abc -liberty {quoted(lib)} -script {quoted(abc_script)}\n"
            mapping.write_text(f"read_json {quoted(out / 'generic.json')}\n" +
                               f"read_liberty -lib {quoted(lib)}\n" +
                               f"dfflibmap -liberty {quoted(lib)}\n" +
                               abc +
                               "hilomap -hicell sg13g2_tiehi L_HI -locell sg13g2_tielo L_LO\n" +
                               "clean\ncheck -assert\n" +
                               f"write_json {quoted(out / 'mapped.json')}\n" +
                               f"write_verilog -noattr -noexpr {quoted(out / 'mapped.v')}\n" +
                               f"stat -liberty {quoted(lib)}\n")
            if previous and "mapped" in previous and previous.get("mapping_profile") == result["mapping_profile"]:
                if previous["pdk"] != result["pdk"]:
                    raise RuntimeError("Mapped output collateral identity changed")
                for name in ("mapped.json", "mapped.v", "mapping.log"):
                    copy_checked(name)
            else:
                result["commands"].append(run([yosys, "-s", str(mapping)], out / "mapping.log", deadline))
            result["mapped"] = inspect_netlist(out / "mapped.json", args.top, True)
            area = re.findall(r"Chip area for module.*?:\s*([0-9.]+)", (out / "mapping.log").read_text())
            if not area:
                raise RuntimeError("Mapping did not report cell area")
            result["mapped"]["cell_area_um2"] = float(area[-1])
            result["mapped"]["memory_implementation"] = "Explicit register logic; no RAM black boxes"
            if args.layout:
                openroad = shutil.which("openroad")
                if not openroad:
                    raise RuntimeError("OpenROAD missing for requested layout")
                result["tools"]["openroad_path"] = openroad
                result["tools"]["openroad_version"] = subprocess.check_output([openroad, "-version"], text=True).strip()
                # TCL is intentionally a small inspectable slice recipe, not a new flow framework.
                layout = out / "layout.tcl"
                layout.write_text(f"set pdk {{{std}}}\nset out {{{out}}}\n" +
                                  f"set top {args.top}\nset clock_port {args.clock}\nset clock_ns {args.clock_ns}\n" +
                                  recipes["layout"])
                result["commands"].append(run([openroad, "-exit", "-no_init", str(layout)], out / "layout.log", deadline))
                result["layout"] = layout_reports(out)
                result["router_drc"] = router_drc((out / "router-drc-count.txt").read_text())
                result["drc"] = "NOT_RUN; router checks reported separately"
                result["lvs"] = "NOT_RUN; no GDS/extracted-transistor comparison"
                if args.process_checks:
                    magic, netgen = shutil.which("magic"), shutil.which("netgen")
                    if not magic or not netgen:
                        raise RuntimeError("Magic/Netgen missing for requested process checks")
                    result["tools"]["magic_path"] = magic
                    result["tools"]["magic_version"] = subprocess.check_output([magic, "--version"], text=True).strip()
                    result["tools"]["netgen_path"] = netgen
                    check = out / "process.tcl"
                    check.write_text(f"set pdk {{{pdk / 'ihp-sg13g2'}}}\nset out {{{out}}}\nset top {args.top}\n" +
                                     recipes["process"])
                    extra = [std / "gds/sg13g2_stdcell.gds", std / "cdl/sg13g2_stdcell.cdl"]
                    result["pdk"]["process_collateral"] = {str(p.relative_to(pdk)): sha(p) for p in extra}
                    result["commands"].append(run([magic, "-dnull", "-noconsole", "-rcfile", str(
                        pdk / "ihp-sg13g2/libs.tech/magic/ihp-sg13g2.magicrc")], out / "process.log", deadline, check))
                    violations = int((out / "process-drc-count.txt").read_text().strip())
                    result["drc"] = {"status": "PASS" if violations == 0 else "FAIL", "violations": violations,
                                     "scope": "Magic public beta SG13G2 process rules; not foundry signoff"}
                    # Extract a fresh import of the actual streamed GDS. The
                    # pinned Magic crashes if extraction follows drc(full)
                    # selection, including on an original public inverter.
                    extract = out / "extract.tcl"
                    extract.write_text(f"set out {{{out}}}\nset top {args.top}\n" +
                                       recipes["extract"])
                    result["commands"].append(run([magic, "-dnull", "-noconsole", "-rcfile", str(
                        pdk / "ihp-sg13g2/libs.tech/magic/ihp-sg13g2.magicrc")], out / "extract.log", deadline, extract))
                    lvs = out / "lvs.tcl"
                    # Supply original transistor cells to the Verilog reader,
                    # retaining named pin associations instead of guessing CDL order.
                    lvs.write_text(f"set reference [readnet spice {{{std / 'cdl/sg13g2_stdcell.cdl'}}}]\n" +
                                   f"readnet verilog {{{out / 'routed.v'}}} $reference\n" +
                                   f"lvs {{{out / 'extracted.spice'} {args.top}}} " +
                                   f"[list {args.top} $reference] " +
                                   f"{{{pdk / 'ihp-sg13g2/libs.tech/netgen/ihp-sg13g2_setup.tcl'}}} " +
                                   f"{{{out / 'lvs.rpt'}}} -json\n")
                    result["commands"].append(run([netgen, "-batch", "source", str(lvs)], out / "lvs.log", deadline))
                    report = (out / "lvs.rpt").read_text()
                    match = lvs_matches(report)
                    result["lvs"] = {"status": "PASS" if match else "FAIL",
                                     "scope": "Extracted layout vs original public transistor cells + synthesized circuit"}
                    if violations or not match:
                        raise RuntimeError("Process checks failed; retain DRC/LVS reports separately from completed layout")
                if result["router_drc"]["violations"]:
                    raise RuntimeError("Detailed router reported violations; retain completed layout and separate process checks")
        for p, before in zip(input_paths, result["source_inputs"].values()):
            if sha(p) != before:
                raise RuntimeError("RTL source changed during synthesis; rerun with stable inputs")
        result["status"] = "PASS"
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, CommandFailure):
            result["commands"].append(exc.record)
        result["error"] = str(exc)
        print(str(exc), file=sys.stderr)
    if (out / "global-route-summary.json").is_file():
        try:
            result["global_route_checkpoint"] = layout_reports(out, global_route=True)
        except (OSError, ValueError, RuntimeError) as exc:
            result["global_route_checkpoint_error"] = str(exc)
    result["artifacts"] = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*"))
                           if p.is_file() and p.name != "result.json"}
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "result": str(out / "result.json")}, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
