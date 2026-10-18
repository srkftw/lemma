"""Admission must bind saved actual execution to the requested construction.

These host fixture tools execute real subprocesses; they do not establish Lean
compilation or target execution. Semantic mutations deliberately recompute outer
hashes so the tests exercise command relations, not just checksum failures.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from action_cache import _digest, _json
from build_actions import BuildActions, admitted_commands, retain_source
from core0_common import Core0Error, sha256, write_json


class BuildAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "build/kernel/result"
        self.output.mkdir(parents=True)
        self.write("scripts/build_actions.py", (ROOT/"scripts/build_actions.py").read_text())
        self.write("scripts/build_admission.py", (ROOT/"scripts/build_admission.py").read_text())
        for helper in ("core0_common.py", "action_worker.py", "build_dependencies.py"):
            self.write("scripts/"+helper, (ROOT/"scripts"/helper).read_text())
        self.write("scripts/audit_kernel.py", "fixture observer")
        self.write("lakefile.toml", 'name = "fixture"\n')
        self.write("lake-manifest.json", '{"packages": []}')
        self.write("lean-toolchain", "fixture-toolchain")
        self.write("Lemma/Compiler/KernelExport.lean", "def fixture : Nat := 7\n")
        executable = (
            f"#!{sys.executable}\n"
            "import os,pathlib,sys\n"
            "if '--version' in sys.argv:\n print('fixture tool 1');sys.exit(0)\n"
            "if pathlib.Path(sys.argv[0]).name=='lake':\n"
            " if sys.argv[1]=='build':sys.exit(0)\n"
            " target=pathlib.Path(os.environ['LEMMA_KERNEL_OUT']);target.mkdir(exist_ok=True)\n"
            " for name in ['program.ll','unit.json','normalized.txt','symbols.txt']:\n"
            "  (target/name).write_text('fixture generated '+name)\n"
            "else:\n"
            " args=sys.argv[1:];source=pathlib.Path(args[-3]);destination=pathlib.Path(args[-1])\n"
            " destination.write_bytes(source.read_bytes()+b'optimized')\n")
        self.tools = {}
        for name in ("lean", "lake", "opt", "llc", "clang", "ld.lld", "llvm-objcopy"):
            path = self.write("tools/"+name, executable)
            path.chmod(0o755)
            self.tools[name] = str(path)
        inventory = {p.relative_to(self.root).as_posix():sha256(p)
                     for p in (self.root/"scripts").glob("*.py")}
        inventory.update({name:sha256(self.root/name) for name in
                         ("lakefile.toml", "lake-manifest.json", "lean-toolchain", "Lemma/Compiler/KernelExport.lean")})
        retain_source(self.root, self.output, inventory)
        self.rows = []
        self.actions = BuildActions(self.root, self.output, self.tools, 10, self.rows)

    def write(self, name, payload):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload)
        return path

    def llvm(self):
        (self.output/"program.ll").write_text("IR fixture")
        self.actions.invoke(["opt", "-S", "-passes=default<O2>", "program.ll", "-o", "program.opt.ll"], self.output)

    def lean(self):
        consumer = self.output/"firmware/Export.lean"
        consumer.parent.mkdir()
        consumer.write_text('import Lemma.Compiler.KernelExport\n#lemma_export_unit "firmware" []\n')
        self.actions.invoke(["lake", "env", "lean", "-j2", consumer.relative_to(self.root).as_posix()], self.root,
                            {"LEMMA_KERNEL_OUT":str(consumer.parent), "LEMMA_KERNEL_CONFIGURATION":"fixture"})

    def admit(self):
        return admitted_commands(self.rows, root=self.root, output_dir=self.output, source_root=self.root)

    def mutate(self, change):
        row = self.rows[-1]
        path = self.output/row["admission"]
        receipt = json.loads(path.read_text())
        change(receipt)
        if "producer" in receipt:
            producer = receipt["producer"]
            producer["action_key"] = _digest(_json(producer["request"]))
            receipt["action_key"] = producer["action_key"]
            receipt["producer_receipt_id"] = _digest(_json(producer))
        write_json(path, receipt)
        row["admission_sha256"] = sha256(path)

    def test_fresh_and_warm_actual_llvm_relations_admit_without_cache_files(self):
        self.llvm()
        self.actions.invoke(["opt", "-S", "-passes=default<O2>", "program.ll", "-o", "program.opt.ll"], self.output)
        self.assertEqual([r["admitted_route"] for r in self.admit()], ["fresh", "reused"])
        import shutil
        shutil.rmtree(self.actions.cache.directory)
        self.assertEqual(len(self.admit()), 2)

    def test_foundation_negative_copy_rebinds_placement_and_keeps_producer_integrity(self):
        from check_foundation import _copy_audit_regression

        self.llvm()
        write_json(self.output/"provenance.json", {"commands": self.rows})
        original = {p.relative_to(self.output): p.read_bytes()
                    for p in self.output.rglob("*") if p.is_file()}
        copied = self.root/"build/foundation/negative-copy"
        _copy_audit_regression(self.output, copied, self.root)
        rows = json.loads((copied/"provenance.json").read_text())["commands"]
        source_receipt = json.loads((self.output/self.rows[0]["admission"]).read_text())
        copied_receipt = json.loads((copied/rows[0]["admission"]).read_text())
        self.assertEqual(copied_receipt["producer"], source_receipt["producer"])
        self.assertEqual(copied_receipt["producer_receipt_id"], source_receipt["producer_receipt_id"])
        self.assertEqual(copied_receipt["outputs"], source_receipt["outputs"])
        admitted = admitted_commands(rows, root=self.root, output_dir=copied)
        self.assertEqual([row["admitted_route"] for row in admitted], ["fresh"])
        self.assertEqual(original, {p.relative_to(self.output): p.read_bytes()
                                  for p in self.output.rglob("*") if p.is_file()})
        (copied/"program.opt.ll").write_text("corrupt copied payload")
        with self.assertRaisesRegex(Core0Error, "consumed/admitted file differs"):
            admitted_commands(rows, root=self.root, output_dir=copied)

    def test_llvm_rejects_different_actual_program_options_environment_and_cwd(self):
        for field in ("program", "option", "environment", "cwd", "failure", "extra-command"):
            with self.subTest(field=field):
                self.rows.clear(); self.llvm()
                def change(receipt):
                    commands = receipt["producer"]["executed"]["commands"]
                    if field == "program":commands[0]["argv"][0] = "/other/compiler"
                    elif field == "option":commands[0]["argv"][2] = "-passes=default<O0>"
                    elif field == "environment":commands[0]["environment"]["LEAN_PATH"] = "/foreign"
                    elif field == "cwd":commands[0]["cwd"] = str(self.root/"unprotected")
                    elif field == "failure":commands[0]["returncode"] = 1
                    else:commands.append(copy.deepcopy(commands[0]))
                self.mutate(change)
                with self.assertRaises(Core0Error):self.admit()

    def test_missing_output_and_input_inventory_cannot_be_self_certified(self):
        self.llvm()
        self.mutate(lambda r:r["producer"]["request"].update(output_names=[]))
        with self.assertRaisesRegex(Core0Error, "output inventory"):self.admit()
        self.rows.clear();self.llvm()
        def remove_input(receipt):
            producer = receipt["producer"]
            producer["request"]["inputs"] = {}
            producer["input_archive_sha256"] = _digest(_json({}))
        self.mutate(remove_input)
        with self.assertRaisesRegex(Core0Error, "dependency closure"):self.admit()

    def test_saved_boolean_returncode_cannot_be_normalized_as_executed_success(self):
        self.llvm()
        self.mutate(lambda receipt: receipt["producer"]["executed"]["commands"][0].update(returncode=False))
        with self.assertRaisesRegex(Core0Error, "original executed command"):
            self.admit()

    def test_wrong_tool_alias_and_archive_identity_rejected(self):
        self.llvm()
        self.mutate(lambda r:r["producer"]["request"]["action"]["tools"]["opt"].update(invoked_as="/other/opt"))
        with self.assertRaisesRegex(Core0Error, "tool invocation"):self.admit()
        self.rows.clear();self.llvm()
        self.mutate(lambda r:r["producer"].update(input_archive_sha256="0"*64))
        with self.assertRaisesRegex(Core0Error, "identities"):self.admit()

    def test_lean_export_and_preparation_are_bound_to_private_tree_and_imports(self):
        self.actions.invoke(["lake", "build", "Lemma.Compiler.KernelExport"], self.root)
        self.lean()
        self.assertEqual([r["admitted_route"] for r in self.admit()], ["incremental", "fresh"])
        self.mutate(lambda r:r["producer"]["executed"]["commands"][0].update(argv=[self.tools["lake"], "build", "Unrelated.Module"]))
        with self.assertRaisesRegex(Core0Error, "executed command"):self.admit()

    def test_lean_dependency_output_and_configuration_tampering_rejected(self):
        self.lean()
        original = json.loads((self.output/self.rows[-1]["admission"]).read_text())
        for field in ("compiler-input", "export-output", "configuration", "lake-tree"):
            with self.subTest(field=field):
                write_json(self.output/self.rows[-1]["admission"], original)
                def change(receipt):
                    producer = receipt["producer"]
                    if field == "compiler-input":
                        producer["request"]["inputs"].pop("Lemma/Compiler/KernelExport.lean")
                        producer["input_archive_sha256"] = _digest(_json(producer["request"]["inputs"]))
                    elif field == "export-output":producer["request"]["output_names"].remove("symbols.txt")
                    elif field == "configuration":producer["executed"]["commands"][1]["environment"]["LEMMA_KERNEL_CONFIGURATION"] = "foreign"
                    else:producer["executed"]["commands"][0]["cwd"] = str(self.root/".lake")
                self.mutate(change)
                with self.assertRaises(Core0Error):self.admit()


if __name__ == "__main__":
    unittest.main()
