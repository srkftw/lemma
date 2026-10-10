"""Host-only command contract for pinned source realization."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_kernel
from core0_common import Core0Error


class SourceRealizationCommands(unittest.TestCase):
    def run_realization(self, *, output=None, nar_hash=None, uint_hash=None):
        pin = json.loads((ROOT / "tooling/toolchain-lock.json").read_text())
        lean = pin["tools"]["lean"]
        versions = {"lean": "4.34.1", "lake": "5.0.0-src", "opt": "20.1.8", "llc": "20.1.8",
                    "clang": "20.1.8", "ld.lld": "20.1.8", "qemu-system-riscv64": "11.1.1", "dtc": "1.8.1"}
        tool_stores = {"lean": "lean", "lake": "lean", "llc": "llvm", "opt": "llvm",
                       "llvm-objcopy": "llvm", "llvm-readelf": "llvm", "llvm-nm": "llvm",
                       "llvm-objdump": "llvm", "ld.lld": "lld", "qemu-system-riscv64": "qemu"}
        tools = {name: pin["tools"][key]["store_path"] + "/bin/" + name
                 for name, key in tool_stores.items()}
        tools["clang"] = pin["tools"]["llvm"]["outputs"]["clang_unwrapped"]["store_path"] + "/bin/clang"
        tools["dtc"] = "/fixture/bin/dtc"
        calls = []

        def invoke(argv, cwd):
            self.assertEqual(cwd, ROOT)
            calls.append(tuple(argv))
            if len(argv) == 2 and argv[1] == "--version":
                return versions[argv[0]].encode()
            if argv[:2] == ("nix", "build"):
                self.assertEqual(argv[:6], ("nix", "build", "--no-link", "--print-out-paths", "--impure", "--expr"))
                self.assertEqual(argv[6], build_kernel.LEAN_SOURCE_EXPRESSION)
                self.assertIn('builtins.getFlake ("git+file://" + toString ./.)', argv[6])
                self.assertNotIn("builtins.getFlake (toString ./.)", argv[6])
                self.assertTrue(argv[6].endswith("in pkgs.lean4.src"))
                return (lean["source_path"] + "\n" if output is None else output).encode()
            self.assertEqual(argv, ("nix", "path-info", "--json", lean["source_path"]))
            return json.dumps({lean["source_path"]: {"narHash": nar_hash or lean["source_sha256"],
                                                     "narSize": lean["source_nar_size"]}}).encode()

        source = Path(lean["source_path"]) / "src/Init/Data/UInt/Basic.lean"
        def is_file(path):
            self.assertEqual(path, source)
            return True

        with mock.patch.object(build_kernel, "load_json", return_value=copy.deepcopy(pin)), \
             mock.patch.object(Path, "is_file", is_file), \
             mock.patch.object(build_kernel, "sha256", return_value=uint_hash or build_kernel.LEAN_UINT_SOURCE_SHA256):
            result = build_kernel.realize_toolchain(ROOT, tools, invoke)
        return result, calls

    def test_exact_realization_command_keeps_locked_nar_and_uint(self):
        (_, source), calls = self.run_realization()
        self.assertEqual([c[:2] for c in calls[-2:]], [("nix", "build"), ("nix", "path-info")])
        self.assertEqual(source["uint_source_sha256"], build_kernel.LEAN_UINT_SOURCE_SHA256)

    def test_filtered_context_does_not_admit_foreign_realized_output(self):
        with self.assertRaisesRegex(Core0Error, "immutable locked store path"):
            self.run_realization(output="/nix/store/foreign-source\n")

    def test_filtered_context_does_not_admit_foreign_nar(self):
        with self.assertRaisesRegex(Core0Error, "NAR differs"):
            self.run_realization(nar_hash="sha256-foreign")

    def test_filtered_context_does_not_admit_changed_uint_source(self):
        with self.assertRaisesRegex(Core0Error, "UInt source differs"):
            self.run_realization(uint_hash="0" * 64)
