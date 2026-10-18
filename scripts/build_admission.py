"""Pure observation of retained action evidence, separate from compilation recipes."""
from pathlib import Path
import hashlib
import json
import os
import re

from core0_common import Core0Error, sha256


def admitted_commands(rows, *, root, output_dir, source_root=None):
    """Validate the explicit action route before ordered-command auditing.

    Returned rows describe the requested ordered construction, not a claim that
    a cached command executed today. Original rows/receipts remain unchanged.
    No cache files or live producer PID are needed to audit retained evidence.
    """
    from action_cache import ADMISSION_SCHEMA, RECEIPT_SCHEMA, SCHEMA as CACHE_SCHEMA, _digest, _json
    from build_actions import SCHEMA, controlled_environment, lean_source_inputs, _imports
    normalized = []
    root, output_dir = Path(root), Path(output_dir)
    source_root = Path(source_root or root)

    def relative(name, *, dot=False):
        if (not isinstance(name, str) or not name or Path(name).is_absolute()
                or ".." in Path(name).parts or Path(name).as_posix() != name
                or (name == "." and not dot)):
            raise Core0Error("action contains an escaping or malformed logical path")
        return Path(name)

    def checked_file(path, item):
        if (not isinstance(item, dict) or set(item) != {"sha256", "size", "executable"}
                or type(item["size"]) is not int or item["size"] < 0
                or type(item["executable"]) is not bool or path.is_symlink()
                or not path.is_file() or sha256(path) != item["sha256"]
                or path.stat().st_size != item["size"]
                or bool(path.stat().st_mode & 0o111) != item["executable"]):
            raise Core0Error("action consumed/admitted file differs: " + str(path))

    def action_context(action, provenance, kind, requested):
        if (not isinstance(action, dict) or action.get("schema") != SCHEMA
                or action.get("recipe_sha256") != sha256(source_root/"scripts/build_actions.py")
                or action.get("kind") != kind):
            raise Core0Error("unknown or incompatible build action recipe")
        semantics = action["path_semantics"]
        helpers = {name: sha256(source_root/"scripts"/name) for name in
                   ("core0_common.py", "action_worker.py", "build_dependencies.py")}
        if action.get("execution_helpers") != helpers:
            raise Core0Error("action execution/dependency helper identity differs")
        python = action.get("host_python", {})
        if not isinstance(python, dict) or not Path(python.get("path", "")).is_absolute() or re.fullmatch(r"[0-9a-f]{64}", python.get("sha256", "")) is None:
            raise Core0Error("action host Python identity unavailable")
        checkout, cache = Path(semantics["checkout"]), Path(semantics["cache"])
        if (not checkout.is_absolute() or not cache.is_absolute()
                or provenance.get("checkout") != str(checkout)
                or semantics.get("execution") != "fixed relative inputs; private canonical Lean tree; no inherited search paths"):
            raise Core0Error("action original checkout/cache path semantics differ")
        expected_tools = {"lean", "lake"} if kind in {"lean-export", "lake-preparation"} else {kind}
        if kind not in {"lean-export", "lake-preparation", "opt", "llc", "clang", "ld.lld", "llvm-objcopy"} or set(action["tools"]) != expected_tools:
            raise Core0Error("action tool inventory differs from its recipe")
        for identity in action["tools"].values():
            if (set(identity) != {"path", "invoked_as", "sha256", "version_stdout", "version_stderr"}
                    or not Path(identity["path"]).is_absolute()
                    or not Path(identity["invoked_as"]).is_absolute()
                    or re.fullmatch(r"[0-9a-f]{64}", identity["sha256"]) is None):
                raise Core0Error("action tool identity is incomplete")
        primary = "lake" if kind in {"lean-export", "lake-preparation"} else kind
        if requested[0] != action["tools"][primary]["invoked_as"]:
            raise Core0Error("action tool invocation differs from requested command")
        environment = action["environment"]
        fixed = controlled_environment({})
        if (set(environment) != set(fixed) or any(environment[k] != v for k,v in fixed.items() if k != "PATH")
                or not environment["PATH"] or any(not Path(p).is_absolute() for p in environment["PATH"].split(os.pathsep))
                or any(str(Path(i["invoked_as"]).parent) not in environment["PATH"].split(os.pathsep)
                       for i in action["tools"].values())):
            raise Core0Error("action environment is uncontrolled or omits required tool paths")
        identity = json.dumps({"root": str(checkout), "tools": action["tools"], "schema": SCHEMA}, sort_keys=True).encode()
        tree = cache / "lean" / hashlib.sha256(identity).hexdigest() / "tree"
        return environment, tree, cache

    def execution(row, expected_argv, expected_cwd, expected_environment):
        if (not isinstance(row, dict) or row.get("argv") != expected_argv
                or type(row.get("returncode")) is not int or row["returncode"] != 0
                or row.get("cwd") != str(expected_cwd)
                or row.get("environment") != expected_environment):
            raise Core0Error("action original executed command, environment or working directory differs")

    for row in rows:
        if row.get("route") == "lemma-toolchain-preparation/1":
            from toolchain_preparation import admitted_commands as toolchain_commands
            normalized.extend(toolchain_commands(row, root=root, output_dir=output_dir, source_root=source_root))
            continue
        if row.get("route") != SCHEMA:
            normalized.append(row); continue
        path = output_dir / relative(row["admission"])
        if path.is_symlink() or not path.resolve().is_relative_to(output_dir.resolve()) or sha256(path) != row.get("admission_sha256"):
            raise Core0Error("action admission receipt missing, corrupt or escaping evidence")
        receipt = json.loads(path.read_text())
        requested, cwd = row["requested_argv"], row["requested_cwd"]
        relative(cwd, dot=True)
        if not isinstance(requested, list) or not requested or any(not isinstance(arg, str) for arg in requested):
            raise Core0Error("action requested command is malformed")
        if receipt.get("requested_argv") != requested or receipt.get("requested_cwd") != cwd:
            raise Core0Error("action request differs from ordered construction")
        if receipt.get("schema") == SCHEMA + "/preparation":
            action = receipt.get("action", {})
            environment, tree, _ = action_context(action, receipt.get("provenance", {}), "lake-preparation", requested)
            if (receipt.get("status") != "incremental" or requested[1:2] != ["build"]
                    or not requested[2:] or action.get("options") != {"modules": requested[2:]}):
                raise Core0Error("private Lake preparation request differs from its recipe")
            execution(receipt.get("executed"), requested, tree, environment)
            closure = lean_source_inputs(source_root, [m.replace(".", "/") + ".lean" for m in requested[2:]])
            if set(receipt["inputs"]) != set(closure):
                raise Core0Error("incomplete Lake preparation dependency closure")
            for name,digest in receipt["inputs"].items():
                if sha256(source_root/relative(name)) != digest: raise Core0Error("Lake preparation source differs: " + name)
        elif receipt.get("schema") == ADMISSION_SCHEMA:
            producer = receipt.get("producer", {})
            request = producer.get("request", {})
            if (receipt.get("status") not in {"fresh", "reused"} or producer.get("result") != "success"
                    or producer.get("schema") != RECEIPT_SCHEMA or request.get("schema") != CACHE_SCHEMA
                    or _digest(_json(producer)) != receipt.get("producer_receipt_id")
                    or _digest(_json(request)) != receipt.get("action_key")
                    or producer.get("action_key") != receipt.get("action_key")
                    or producer.get("outputs") != receipt.get("outputs")
                    or producer.get("input_archive_sha256") != _digest(_json(request.get("inputs")))):
                raise Core0Error("action producer/admission identities differ")
            action = request["action"]
            kind = action["kind"]
            environment, tree, cache = action_context(action, producer.get("provenance", {}), kind, requested)
            executed = producer.get("executed", {}).get("commands", [])
            if kind == "lean-export":
                if requested[1:3] != ["env", "lean"] or action["options"].get("arguments") != requested[3:-1]:
                    raise Core0Error("Lean action export arguments differ")
                consumer = root/relative(requested[-1])
                # Archived current output consumers are outside source archive.
                if not consumer.is_file(): consumer = output_dir / Path(requested[-1]).name
                if consumer.read_text() != action["options"]["consumer"]:
                    raise Core0Error("Lean action did not consume the requested exporter")
                options = {k:v for k,v in action["options"].items() if k not in {"consumer", "arguments"}}
                if not set(options) <= {"LEMMA_KERNEL_CONFIGURATION", "LEMMA_KERNEL_STAGE"}:
                    raise Core0Error("unknown Lean action execution environment option")
                if len(executed) != 2:
                    raise Core0Error("Lean action original command inventory differs")
                execution(executed[0], [requested[0], "build", *_imports(consumer.read_text())], tree, environment)
                execution(executed[1], [*requested[:-1], "ActionExport.lean"], tree,
                          {**environment, **options, "LEMMA_KERNEL_OUT": str(tree / "_export")})
                closure = lean_source_inputs(source_root, [m.replace(".", "/") + ".lean" for m in _imports(consumer.read_text())
                    if (source_root / (m.replace(".", "/") + ".lean")).is_file()])
                expected_inputs = {*closure, "ActionExport.lean"}
                text = consumer.read_text()
                from build_kernel import UNIT_FILES, USER_IMAGE_FILES, BOOT_FILES, MULTI_BOOT_FILES
                catalog_path = output_dir/"user-image-catalog.json"
                images = json.loads(catalog_path.read_text())["images"] if catalog_path.is_file() else []
                if "#lemma_export_boot_files" in text:
                    expected_inputs.update("_export/" + p.relative_to(output_dir).as_posix() for p in output_dir.rglob("unit.json"))
                    expected_names = list(MULTI_BOOT_FILES if images else BOOT_FILES)
                    expected_names += [f"{im['directory']}/{n}" for im in images for n in USER_IMAGE_FILES]
                elif "#lemma_export_user_catalog" in text:
                    expected_names = ["user-image-catalog.json"]
                elif "#lemma_export_unit" in text:
                    expected_names = list(UNIT_FILES)
                else:
                    match = re.search(r'#lemma_export_user_(?:image|files)\s+"([^"]+)"', text)
                    if match is None: raise Core0Error("unknown Lean exporter action")
                    image = next(im for im in images if im["key"] == match.group(1))
                    expected_names = [f"{image['directory']}/{n}" for n in (UNIT_FILES if "#lemma_export_user_image" in text else USER_IMAGE_FILES)]
                    if "#lemma_export_user_files" in text:
                        expected_inputs.add("_export/" + image["directory"] + "/unit.json")
                if sorted(expected_names) != request.get("output_names"):
                    raise Core0Error("Lean action output inventory differs from its requested exporter")
                if set(request["inputs"]) != expected_inputs:
                    raise Core0Error("incomplete Lean exporter/compiler dependency closure")
            elif action.get("options", {}).get("argv") != requested[1:]:
                raise Core0Error("LLVM action options differ from ordered request")
            else:
                if len(executed) != 1:
                    raise Core0Error("LLVM action original command inventory differs")
                actual_cwd = Path(executed[0].get("cwd", ""))
                if (actual_cwd.name != "execute" or actual_cwd.parent.parent != cache/"work"
                        or re.fullmatch(r"[0-9a-f]{32}", actual_cwd.parent.name) is None):
                    raise Core0Error("LLVM action original working directory escapes its declared private cache")
                execution(executed[0], requested, actual_cwd, environment)
                args = requested[1:]
                from build_dependencies import embedded_inputs, validate_llvm_arguments
                validate_llvm_arguments(kind, args)
                if any(arg.startswith("@") for arg in args):
                    raise Core0Error("undeclared LLVM response-file dependency")
                if kind == "llvm-objcopy":
                    expected_names, direct_inputs = [args[-1]], [args[-2]]
                else:
                    if "-o" not in args or args.index("-o") == len(args)-1:
                        raise Core0Error("LLVM action lacks its declared output option")
                    expected_names = [args[args.index("-o")+1]]
                    if kind == "ld.lld": expected_names += [a.split("=",1)[1] for a in args if a.startswith("-Map=")]
                    direct_inputs = [a for a in args if not a.startswith("-") and a not in expected_names and (root/cwd/a).is_file()]
                if sorted(expected_names) != request.get("output_names"):
                    raise Core0Error("LLVM action output inventory differs from its requested command")
                expected_inputs = set(direct_inputs)
                pending = list(direct_inputs)
                while pending:
                    name = pending.pop()
                    relative(name)
                    for dependency in embedded_inputs(root/cwd/name):
                        if dependency not in expected_inputs:
                            expected_inputs.add(dependency); pending.append(dependency)
                if not expected_inputs or set(request["inputs"]) != expected_inputs:
                    raise Core0Error("incomplete LLVM action dependency closure")
            for name,item in request["inputs"].items():
                relative(name)
                if kind == "lean-export":
                    candidate = (consumer if name == "ActionExport.lean" else
                                 output_dir/name[len("_export/"):] if name.startswith("_export/") else source_root/name)
                else: candidate = root/cwd/name
                checked_file(candidate, item)
            if (not receipt["outputs"] or sorted(receipt["outputs"]) != request.get("output_names")
                    or set(receipt["materialized"]) != set(receipt["outputs"])):
                raise Core0Error("incomplete admitted output inventory")
            for name,item in receipt["outputs"].items():
                relative(name)
                target = output_dir/relative(receipt["materialized"][name])
                expected = ((consumer.parent if "#lemma_export_unit" in consumer.read_text() else output_dir)/name
                            if kind == "lean-export" else root/cwd/name)
                if (not target.resolve().is_relative_to(output_dir.resolve()) or target.is_symlink()
                        or target != expected):
                    raise Core0Error("admitted output is corrupt or missing: " + name)
                checked_file(target, item)
        else: raise Core0Error("unknown build action admission schema")
        normalized.append({"argv": requested, "cwd": cwd, "returncode": 0,
                           "admitted_route": receipt["status"],
                           **({"host_environment":row["host_environment"]} if "host_environment" in row else {})})
    return normalized
