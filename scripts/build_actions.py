"""Conservative action boundaries for the existing Lean/LLVM build drivers.

The broad source inventory remains the admission inventory. This module only
describes compilation dependencies; audit policy is deliberately separate.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

from core0_common import Core0Error, action_lease, run_bounded, sha256, write_json

SCHEMA = "lemma-build-actions/1"
CONFIG = ("lakefile.toml", "lake-manifest.json", "lean-toolchain")
LOADED_RECIPE_SHA256 = sha256(Path(__file__))


def controlled_environment(tools, extra=None):
    # No inherited Lean search path, compiler flags, plugin, or library path.
    paths = sorted({str(Path(p).parent) for p in tools.values()})
    env = {"PATH": os.pathsep.join(paths), "LANG": "C", "LC_ALL": "C",
           "TZ": "UTC", "LEAN_NUM_THREADS": "2", "LEAN_STACK_SIZE_KB": "65536"}
    env.update(extra or {})
    return env


def _imports(text):
    """Read the standard import header, including nested Lean comments.

    Nonstandard/escaped import syntax is rejected, never silently omitted.
    The compiler itself still parses and elaborates every requested declaration.
    """
    result = []
    i, depth, cleaned = 0, 0, []
    while i < len(text):
        pair = text[i:i+2]
        if pair == "/-": depth += 1; i += 2
        elif depth and pair == "-/": depth -= 1; i += 2
        elif depth: cleaned.append("\n" if text[i] == "\n" else " "); i += 1
        elif pair == "--":
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
        elif text[i] == '"':
            cleaned.append('""'); i += 1
            while i < len(text):
                if text[i] == "\\": i += 2
                elif text[i] == '"': i += 1; break
                else: i += 1
        else: cleaned.append(text[i]); i += 1
    if depth: raise Core0Error("unterminated Lean comment in dependency input")
    header = "".join(cleaned)
    for line in header.splitlines():
        line = line.strip()
        if not line or line == "prelude": continue
        if not line.startswith("import "):
            if re.search(r"\bimport\b", line):
                raise Core0Error("unsupported Lean import header; dependency closure unavailable")
            break
        names = line[7:].split()
        if not names or any(re.fullmatch(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*", n) is None for n in names):
            raise Core0Error("unsupported Lean import header; dependency closure unavailable")
        result.extend(names)
    return result


def lean_source_inputs(root, sources):
    root = Path(root).resolve()
    manifest = json.loads((root / "lake-manifest.json").read_text())
    if manifest.get("packages") != []:
        raise Core0Error("action cache needs a declared external Lake package closure")
    result = {name: root / name for name in CONFIG}
    pending = [Path(p) if Path(p).is_absolute() else root / p for p in sources]
    while pending:
        path = pending.pop().resolve()
        name = path.relative_to(root).as_posix()
        if name in result: continue
        if name.split("/")[0].removesuffix(".lean") in {"Lean", "Init", "Std", "Lake"}:
            raise Core0Error("local source cannot override a pinned Lean namespace: " + name)
        if path.is_symlink() or not path.is_file():
            raise Core0Error("missing or foreign Lean dependency: " + name)
        result[name] = path
        for module in _imports(path.read_text()):
            imported = root / (module.replace(".", "/") + ".lean")
            if imported.is_file(): pending.append(imported)
            elif module.split(".")[0] not in {"Lean", "Init", "Std", "Lake"}:
                raise Core0Error("unknown Lean import dependency: " + module)
    return result


@contextmanager
def lean_workspace(root, cache_directory, tools, inputs, *, fresh=False):
    """Private source copy, protected Lake tree, byte-checked compiled state.

    Copy from the action's immutable inputs, never the caller's mutable .lake.
    Only this lock owner writes the source copy or Lake state. A damaged state
    inventory discards compiled dependencies, including injected foreign files.
    """
    from action_cache import tool_identity, write_if_changed
    identity = json.dumps({"root": str(Path(root).resolve()),
                           "tools": {n: tool_identity(tools[n]) for n in ("lean", "lake")},
                           "schema": SCHEMA}, sort_keys=True).encode()
    base = Path(cache_directory) / "lean" / hashlib.sha256(identity).hexdigest()
    base.mkdir(parents=True, exist_ok=True)
    with (base / "lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tree = base / "tree"
        if tree.is_symlink():
            raise Core0Error("private Lean workspace root must not be a symlink")
        tree.mkdir(exist_ok=True)
        compiled = tree / ".lake"
        metadata = base / "compiled.json"
        if metadata.is_symlink():
            raise Core0Error("private Lean compiled-state metadata must not be a symlink")
        def inventory():
            return {p.relative_to(tree).as_posix(): sha256(p) for p in sorted(compiled.rglob("*")) if p.is_file()}
        try:
            previous = json.loads(metadata.read_text())
            valid = (not compiled.is_symlink() and previous == inventory()
                     and not any(p.is_symlink() for p in compiled.rglob("*")))
        except (OSError, ValueError): valid = False
        if fresh or not valid:
            if compiled.is_symlink():
                compiled.unlink()
            elif compiled.exists():
                shutil.rmtree(compiled)
        names = set(inputs)
        for name,path in inputs.items():
            if not name.endswith(".lean"): continue
            for module in _imports(Path(path).read_text()):
                dependency = module.replace(".", "/") + ".lean"
                if dependency not in names and module.split(".")[0] not in {"Lean", "Init", "Std", "Lake"}:
                    raise Core0Error("immutable Lean snapshot omits import: " + module)
        for p in sorted(tree.rglob("*"), reverse=True):
            relative = p.relative_to(tree)
            if relative.parts[0] == ".lake": continue
            if p.is_file() and relative.as_posix() not in names: p.unlink()
        for name, path in inputs.items():
            write_if_changed(tree / name, Path(path).read_bytes())
        try:
            with action_lease(lock.fileno()):
                yield tree
        except BaseException:
            metadata.unlink(missing_ok=True)
            raise
        else:
            if metadata.is_symlink():
                raise Core0Error("private Lean compiled-state metadata must not be a symlink")
            write_json(metadata, inventory())


def fresh_requested(fresh=False):
    value = os.environ.get("LEMMA_BUILD_FRESH", "0")
    if value not in {"0", "1"}: raise Core0Error("LEMMA_BUILD_FRESH must be 0 or 1")
    return fresh or value == "1"


def retain_source(root, output, inventory):
    """Evidence owns its source copy independently of cache eviction."""
    directory = output / "action-source"
    directory.mkdir()
    for name, digest in inventory.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
        if sha256(target) != digest: raise Core0Error("source changed during snapshot: " + name)
    write_json(directory / "source-inputs.json", inventory)
    return directory


class BuildActions:
    def __init__(self, root, output, tools, timeout, commands, *, fresh=False, cache_dir=None):
        from action_cache import ActionCache, source_provenance, tool_identity
        self.root, self.output, self.tools = root, output, tools
        self.timeout, self.commands = timeout, commands
        self.cache = ActionCache(root, directory=cache_dir, fresh=fresh_requested(fresh))
        self.source = output / "action-source"
        self.provenance = source_provenance(root)
        self.provenance["source_archive"] = str(self.source)
        self.identities = {n: tool_identity(tools[n]) for n in ("lean", "lake", "opt", "llc", "clang", "ld.lld", "llvm-objcopy")}
        self.host_python = tool_identity(sys.executable)
        self.receipts = []
        self._fresh_lake = self.cache.fresh
        self.recipe_sha256 = LOADED_RECIPE_SHA256
        if sha256(Path(__file__)) != self.recipe_sha256:
            raise Core0Error("build action implementation changed after import; restart from a stable candidate")
        self.execution_helpers = {name: sha256(Path(__file__).with_name(name)) for name in
                                  ("core0_common.py", "action_worker.py", "build_dependencies.py")}
        from core0_common import LOADED_SOURCE_SHA256
        if self.execution_helpers["core0_common.py"] != LOADED_SOURCE_SHA256:
            raise Core0Error("host process helper changed after import; restart from a stable candidate")

    def _lake_context(self, inputs):
        fresh = self._fresh_lake
        self._fresh_lake = False
        return lean_workspace(self.root, self.cache.directory, self.tools, inputs, fresh=fresh)

    def _execute(self, argv, cwd, env):
        from core0_common import LEASE_WORKER_SHA256
        frozen_worker = LEASE_WORKER_SHA256.get()
        if frozen_worker is not None and frozen_worker != self.execution_helpers["action_worker.py"]:
            raise Core0Error("protected worker snapshot differs from the action's declared source")
        try:
            result = run_bounded(argv, cwd=cwd, timeout_seconds=self.timeout, env=env)
        except (Core0Error, OSError) as error:
            write_json(self.output / "action-failure.json", {"argv": list(argv), "cwd": str(cwd),
                "returncode": None, "completed": False, "error": str(error),
                "elapsed_seconds": getattr(error, "elapsed_seconds", None),
                "cleanup_pending": getattr(error, "cleanup_pending", False),
                "cleanup_worker": getattr(error, "cleanup_worker", None),
                "stdout": getattr(error, "stdout", b"").decode(errors="replace"),
                "stderr": getattr(error, "stderr", b"").decode(errors="replace"), "environment": env})
            raise
        row = {"argv": list(argv), "cwd": str(cwd), "returncode": result.returncode,
               "elapsed_seconds": result.elapsed_seconds, "stdout": result.stdout.decode(errors="replace"),
               "stderr": result.stderr.decode(errors="replace"), "environment": env}
        if result.returncode:
            write_json(self.output / "action-failure.json", row)
            raise Core0Error(f"action failed: {' '.join(argv)}\n{row['stderr']}")
        return row

    def _record(self, requested, cwd, receipt, host_environment=None):
        path = self.output / "action-receipts" / f"{len(self.receipts):04d}.json"
        write_json(path, receipt)
        self.receipts.append(receipt)
        row = {"route": SCHEMA, "requested_argv": requested,
               "requested_cwd": str(cwd.relative_to(self.root)),
               "admission": str(path.relative_to(self.output)), "admission_sha256": sha256(path)}
        if host_environment: row["host_environment"] = host_environment
        self.commands.append(row)
        write_json(self.output / "commands.json", self.commands)
        counts = {kind: sum(r["status"] == kind for r in self.receipts) for kind in ("fresh", "reused", "incremental")}
        write_json(self.output / "actions.json", {"schema": SCHEMA, "counts": counts,
                   "actions": [{k: r.get(k) for k in ("action_key", "status", "reason", "duration_seconds")} for r in self.receipts],
                   "functional_result": "unavailable: production only; execute scenarios separately"})
        print(f"ACTION {receipt['status']} {Path(requested[0]).name}: {receipt['reason']}", flush=True)

    def _closure(self, consumer=None, modules=()):
        sources = [self.source / (m.replace(".", "/") + ".lean") for m in modules]
        if consumer is not None:
            sources += [self.source / (m.replace(".", "/") + ".lean") for m in _imports(consumer.read_text())
                        if (self.source / (m.replace(".", "/") + ".lean")).is_file()]
        inputs = lean_source_inputs(self.source, sources)
        if consumer is not None: inputs["ActionExport.lean"] = consumer
        return inputs

    def invoke(self, argv, cwd=None, env=None):
        cwd = self.output if cwd is None else cwd
        requested = [self.tools.get(argv[0], argv[0]), *argv[1:]]
        tool = Path(requested[0]).name
        if tool.startswith("clang"): tool = "clang"
        if tool == "lake" and list(argv[1:2]) == ["build"]:
            modules = list(argv[2:])
            if not modules: raise Core0Error("cached Lake preparation requires explicit selected modules")
            inputs = self._closure(modules=modules)
            # Freeze this preparation too; the lock alone does not freeze the caller's checkout.
            with tempfile.TemporaryDirectory(dir=self.cache.directory / "work") as temporary:
                from action_cache import process_identity
                write_json(Path(temporary)/"owner.json", {"owner": process_identity(), "started_at": time.time(),
                    "action_key": "lake-preparation", "requested_argv": requested,
                    "reason": "prepare selected source dependencies in protected incremental Lake workspace"})
                snapshot = {}
                for name, source in inputs.items():
                    path = Path(temporary) / name; path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, path); snapshot[name] = path
                with self._lake_context(snapshot) as tree:
                    actual = self._execute(requested, tree, controlled_environment(self.tools))
            receipt = {"schema": SCHEMA + "/preparation", "status": "incremental", "reason": "protected private Lake dependency build",
                       "action": self._action("lake-preparation", ("lean", "lake"), {"modules": modules}),
                       "provenance": self.provenance,
                       "requested_argv": requested, "requested_cwd": str(cwd.relative_to(self.root)),
                       "inputs": {n: sha256(p) for n, p in inputs.items()}, "executed": actual,
                       "duration_seconds": actual["elapsed_seconds"]}
            self._record(requested, cwd, receipt, {"LEAN_NUM_THREADS": "2", "LEAN_STACK_SIZE_KB": "65536"})
            return actual["stdout"].encode()
        if tool == "lake" and list(argv[1:3]) == ["env", "lean"] and env and "LEMMA_KERNEL_OUT" in env:
            return self._lean_export(requested, cwd, env)
        if tool in {"opt", "llc", "clang", "ld.lld", "llvm-objcopy"} and list(argv[1:]) != ["--version"]:
            return self._llvm(tool, requested, cwd)
        return None

    def _action(self, kind, tools, options):
        if sha256(Path(__file__)) != self.recipe_sha256:
            raise Core0Error("build action recipe changed after campaign start")
        if any(sha256(Path(__file__).with_name(n)) != h for n,h in self.execution_helpers.items()):
            raise Core0Error("build execution helper changed after campaign start")
        return {"schema": SCHEMA, "kind": kind, "recipe_sha256": self.recipe_sha256,
                "execution_helpers": self.execution_helpers,
                "host_python": self.host_python,
                "tools": {n: self.identities[n] for n in tools}, "options": options,
                "environment": controlled_environment(self.tools),
                "path_semantics": {"checkout": str(self.root), "cache": str(self.cache.directory),
                                   "execution": "fixed relative inputs; private canonical Lean tree; no inherited search paths"}}

    def _cached(self, action, inputs, outputs, producer, requested, cwd, host=None):
        # Extra audit policy only changes admission, never compilation bytes.
        validator = {"schema": SCHEMA, "audit_kernel_sha256": sha256(self.root / "scripts/audit_kernel.py"),
                     "build_admission_sha256": sha256(self.root / "scripts/build_admission.py")}
        provenance = {**self.provenance, "requested_argv": requested, "requested_cwd": str(cwd.relative_to(self.root))}
        from action_cache import CacheError
        try:
            receipt = self.cache.run(action, inputs, outputs, producer, provenance=provenance, validator=validator)
        except CacheError as error:
            raise Core0Error("action cache rejected production: " + str(error)) from error
        receipt.update(requested_argv=requested, requested_cwd=str(cwd.relative_to(self.root)),
                       materialized={n: str(p.relative_to(self.output)) for n,p in outputs.items()})
        self._record(requested, cwd, receipt, host)
        # Cached logs are retained as producer logs; do not replay them as this execution.
        return b""

    def _lean_export(self, requested, cwd, env):
        from build_kernel import UNIT_FILES, BOOT_FILES, MULTI_BOOT_FILES, USER_IMAGE_FILES
        consumer = self.root / requested[-1]
        text = consumer.read_text()
        inputs = self._closure(consumer)
        destination = Path(env["LEMMA_KERNEL_OUT"])
        if "#lemma_export_user_catalog" in text:
            names = ["user-image-catalog.json"]
        elif "#lemma_export_unit" in text:
            names = list(UNIT_FILES)
        else:
            catalog = self.output / "user-image-catalog.json"
            images = json.loads(catalog.read_text())["images"] if catalog.is_file() else []
            if "#lemma_export_boot_files" in text:
                names = list(MULTI_BOOT_FILES if images else BOOT_FILES)
                names += [f"{im['directory']}/{n}" for im in images for n in USER_IMAGE_FILES]
                for path in sorted(self.output.rglob("unit.json")):
                    inputs["_export/" + path.relative_to(self.output).as_posix()] = path
            else:
                key = re.search(r'#lemma_export_user_(?:image|files)\s+"([^"]+)"', text).group(1)
                image = next(im for im in images if im["key"] == key)
                names = [f"{image['directory']}/{n}" for n in (UNIT_FILES if "#lemma_export_user_image" in text else USER_IMAGE_FILES)]
                if "#lemma_export_user_files" in text:
                    path = self.output / image["directory"] / "unit.json"
                    inputs["_export/" + image["directory"] + "/unit.json"] = path
        options = {k:env[k] for k in ("LEMMA_KERNEL_CONFIGURATION", "LEMMA_KERNEL_STAGE") if k in env}
        action = self._action("lean-export", ("lean", "lake"), {"consumer": text, **options, "arguments": requested[3:-1]})
        def produce(work):
            with self._lake_context(work.inputs) as tree:
                target = tree / "_export"; target.mkdir(exist_ok=True)
                modules = _imports(text)
                rows = [self._execute([self.tools["lake"], "build", *modules], tree, controlled_environment(self.tools))]
                rows.append(self._execute([*requested[:-1], "ActionExport.lean"], tree,
                    controlled_environment(self.tools, {**options, "LEMMA_KERNEL_OUT": str(target)})))
                for name, output in work.outputs.items(): shutil.copyfile(target / name, output)
            return {"commands": rows}
        return self._cached(action, inputs, {n:destination/n for n in names}, produce, requested, cwd,
                            {"LEAN_NUM_THREADS": "2", "LEAN_STACK_SIZE_KB": "65536"})

    def _llvm(self, tool, requested, cwd):
        args = requested[1:]
        from build_dependencies import embedded_inputs, validate_llvm_arguments
        validate_llvm_arguments(tool, args)
        inputs, names = {}, []
        if tool == "llvm-objcopy":
            names = [args[-1]]; inputs[args[-2]] = cwd / args[-2]
        else:
            names = [args[args.index("-o")+1]]
            if tool == "ld.lld": names += [arg.split("=",1)[1] for arg in args if arg.startswith("-Map=")]
            for arg in args:
                if not arg.startswith("-") and arg not in names and (cwd / arg).is_file(): inputs[arg] = cwd / arg
            nonfiles = {"elf64lriscv"} if tool == "ld.lld" else set()
            if any(not arg.startswith("-") and arg not in names and arg not in inputs and arg not in nonfiles for arg in args):
                raise Core0Error("missing or undeclared LLVM action input")
        pending = list(inputs)
        while pending:
            name = pending.pop()
            for dependency in embedded_inputs(inputs[name]):
                if dependency not in inputs: inputs[dependency] = cwd / dependency; pending.append(dependency)
        if any(Path(n).is_absolute() or ".." in Path(n).parts for n in (*inputs,*names)):
            raise Core0Error("LLVM cache action requires declared relative file names")
        action = self._action(tool, (tool,), {"argv": args})
        def produce(work):
            tree = work.directory / "execute"; tree.mkdir()
            for name, source in work.inputs.items():
                target = tree/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,target)
            for name in names: (tree/name).parent.mkdir(parents=True,exist_ok=True)
            row = self._execute(requested, tree, controlled_environment(self.tools))
            for name, output in work.outputs.items(): shutil.copyfile(tree/name,output)
            return {"commands": [row]}
        return self._cached(action, inputs, {n:cwd/n for n in names}, produce, requested, cwd)


from build_admission import admitted_commands
