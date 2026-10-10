"""K route/object/CFG rejection fixtures; these are not hardware evidence."""
import copy
import json
import re
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_kernel import (USER_ATTACKS, INSTRUCTION_CASES, image_specs, managed_fields,
                          validate_unit, validate_user_image_catalog, validate_image_case_provenance,
                          validate_instruction_selection, validate_user_attack_object,
                          validate_user_attack_machine, validate_machine,
                          validate_architecture_diagnostics, _attack_source)
from build_kernel import (CONTRACTS, USER_INSTRUCTION_CONFIGURATIONS,
                          SERVICE_INSTRUCTION_CONFIGURATIONS, configuration_roots,
                          configuration_development_modules, user_startup_case,
                          validate_configuration_stage, user_module_closure)
from core0_common import Core0Error


def unit(configuration, key=None):
    image = next(row for row in image_specs(configuration) if row["key"] == key) if key else None
    prefix = image["symbol_prefix"] if image else "lemma_user_"
    root = {"id": 1, "source": "Lemma.User.Entry.main", "symbol": prefix + "root", "args": ["u64"]}
    return {"schema_version": 2 if image else 1, "artifact_category": "development-user-unit",
            "contract_version": CONTRACTS["user"], "configuration": configuration, "role": "user",
            "roots": [root], "functions": [{k: v for k, v in root.items() if k != "id"} | {"effects": []}],
            "used_execution_ops": [], "used_device_ops": [], "used_loops": [],
            **({"image_key": key, "image_id": image["id"], "startup_case": image["startup_case"],
                **managed_fields(configuration, image)} if image else {})}


def startup_fixture(case, managed=False):
    configuration = ("service-" if managed else "user-") + case + "-development"
    symbol, _, words = USER_ATTACKS[case]
    assembly = '.section .text.user_adversarial, "ax", @progbits\n' + symbol + ":\n"
    assembly += "\n".join(_attack_source(case)) + "\n.size " + symbol + ", . - " + symbol + "\n"
    raw = struct.pack("<" + "I" * len(words), *words)
    section = f"  [ 6] .text.user_adversarial PROGBITS 0000000000000000 0000a0 {len(raw):06x} 00 AX 0 0 4\n"
    symbols = f" 7: 0000000000000000 {len(raw)} FUNC GLOBAL DEFAULT 6 {symbol}\n"
    relocations = ""
    if case == "halfword-ecall":
        symbols += " 8: 0000000000000000 0 NOTYPE LOCAL DEFAULT 6 $x\n"
        symbols += " 9: 0000000000000014 0 NOTYPE LOCAL DEFAULT 6 $d\n"
    return dict(section_text=section, symbol_text=symbols, raw=raw, assembly=assembly,
                configuration=configuration, image_key="fault" if managed else None,
                unit=unit(configuration, "fault" if managed else None), relocation_text=relocations)


class ArchitectureRoutes(unittest.TestCase):
    def test_exact_six_cases_preserve_ordinary_service_rows_and_stage_authority(self):
        self.assertEqual(set(USER_INSTRUCTION_CONFIGURATIONS), {"user-" + k + "-development" for k in INSTRUCTION_CASES})
        self.assertEqual(set(SERVICE_INSTRUCTION_CONFIGURATIONS), {"service-" + k + "-development" for k in INSTRUCTION_CASES})
        ordinary = image_specs("service-normal")
        for configuration, case in (*USER_INSTRUCTION_CONFIGURATIONS.items(), *SERVICE_INSTRUCTION_CONFIGURATIONS.items()):
            validate_configuration_stage(configuration, "supervisor")
            with self.assertRaises(Core0Error): validate_configuration_stage(configuration, "bootstrap-m")
            managed = configuration.startswith("service-")
            selected = unit(configuration, "fault" if managed else None)
            validate_instruction_selection(case, configuration=configuration, image_key="fault" if managed else None, unit=selected)
            if managed:
                images = image_specs(configuration)
                self.assertEqual(images[:4], ordinary)
                self.assertEqual(images[4]["source"], "Lemma.User.Entry.main")
                self.assertEqual(images[4]["startup_case"], case)
                self.assertEqual(user_startup_case(configuration), "none")
                self.assertEqual(configuration_development_modules(configuration, "kernel"), ("Lemma.Kernel.Development.ServiceEntry",))
                self.assertEqual(configuration_roots(configuration)["kernel"][0][0], "Lemma.Kernel.Development.ServiceEntry.boot")
            else:
                self.assertEqual(configuration_roots(configuration)["user"], (("Lemma.User.Entry.main", ("u64",)),))
                self.assertEqual(user_startup_case(configuration), case)
                self.assertEqual(configuration_development_modules(configuration, "user"), ())
        for unknown in ("service-return-machine", "service-normal-return-machine-development", "user-unknown-development"):
            with self.assertRaises(Core0Error): configuration_roots(unknown)

    def test_selected_case_cannot_cross_source_image_or_role(self):
        configuration = "service-return-machine-development"
        selected = unit(configuration, "fault")
        for case, cfg, key in (("return-supervisor", configuration, "fault"),
                               ("return-machine", "service-development", "fault"),
                               ("return-machine", configuration, "server"),
                               ("return-machine", configuration, None)):
            with self.assertRaises(Core0Error): validate_instruction_selection(case, configuration=cfg, image_key=key, unit=selected)
        for field, value in (("source", "Lemma.User.Development.BufferFault.main"), ("args", [])):
            bad = copy.deepcopy(selected); bad["roots"][0][field] = value
            with self.assertRaises(Core0Error): validate_instruction_selection("return-machine", configuration=configuration, image_key="fault", unit=bad)
        bad = copy.deepcopy(selected); bad["functions"].append({"source": "Lemma.Kernel.Process.dispatch", "symbol": "lemma_user_fault_bad", "args": [], "effects": []})
        with self.assertRaises(Core0Error): validate_unit(bad, "user", configuration=configuration, image_key="fault")

    def test_mixed_case_catalog_and_provenance_are_exact(self):
        configuration = "service-halfword-ecall-development"
        images = list(image_specs(configuration))
        catalog = {"schema_version": 1, "contract_version": "lemma-user-image-catalog-v1", "configuration": configuration,
                   "stage": "supervisor", "image_count": 5, "images": copy.deepcopy(images), **managed_fields(configuration)}
        validate_user_image_catalog(catalog)
        case_map = {row["key"]: row["startup_case"] for row in images}
        validate_image_case_provenance({"user_startup_cases": case_map}, {"user_startup_cases": case_map}, configuration=configuration, images=images)
        for index in range(5):
            bad = copy.deepcopy(catalog); bad["images"][index]["startup_case"] = "return-machine"
            with self.assertRaises(Core0Error): validate_user_image_catalog(bad)
        for bad in ({}, {"user_startup_cases": {**case_map, "server": "halfword-ecall"}}):
            with self.assertRaises(Core0Error): validate_image_case_provenance(bad, {"user_startup_cases": case_map}, configuration=configuration, images=images)
        image = images[-1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "Lemma/User").mkdir(parents=True)
            (root / "Lemma/User/Entry.lean").write_text("")
            self.assertEqual(len(user_module_closure(root, image, configuration)), 1)
            for foreign in ("Lemma.User.Development.BufferFault", "Lemma.Applications.BufferCLI", "Lemma.Kernel.Process"):
                path = root / (foreign.replace(".", "/") + ".lean"); path.parent.mkdir(parents=True, exist_ok=True); path.write_text("")
                (root / "Lemma/User/Entry.lean").write_text("import " + foreign + "\n")
                with self.assertRaises(Core0Error): user_module_closure(root, image, configuration)


class ArchitectureObjectFailures(unittest.TestCase):
    def test_actual_linked_decoder_two_zero_halves_are_confined_to_exact_window(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/architecture-halfword-linked.json").read_text())
        data = startup_fixture("halfword-ecall", True)
        symbol = USER_ATTACKS["halfword-ecall"][0]
        ranges = {symbol: (fixture["base"], fixture["size"])}
        result = validate_user_attack_machine("", ranges, data["assembly"], "halfword-ecall",
                    raw_bytes=bytes.fromhex(fixture["raw_hex"]), configuration=data["configuration"], image_key="fault", unit=data["unit"])
        validate_machine(fixture["disassembly"], user=True, ranges=ranges, user_attack=result)
        with self.assertRaises(Core0Error): validate_machine(fixture["disassembly"], user=True, ranges=ranges)
        bad = copy.deepcopy(result); bad["instruction_site"]["pc"] += 2
        with self.assertRaises(Core0Error): validate_machine(fixture["disassembly"], user=True, ranges=ranges, user_attack=bad)

    def test_genuine_assembler_resolved_object_rejects_unresolved_or_foreign_pair(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/architecture-halfword-object.json").read_text())
        data = {key: fixture[key] for key in ("section_text", "symbol_text", "assembly", "relocation_text")}
        data.update(raw=bytes.fromhex(fixture["raw_hex"]), configuration="service-halfword-ecall-development",
                    image_key="fault", unit=unit("service-halfword-ecall-development", "fault"))
        self.assertEqual(validate_user_attack_object(**data)["local_pair_resolution"]["pair_offset"], 16)
        for offset, word in ((4, 0x00028293), (4, 0x01428293), (8, 0x00428293), (16, 0x00730093), (20, 0x00000013)):
            bad = copy.deepcopy(data); raw = bytearray(bad["raw"]); struct.pack_into("<I", raw, offset, word); bad["raw"] = bytes(raw)
            with self.subTest(offset=offset, word=word), self.assertRaises(Core0Error): validate_user_attack_object(**bad)

    def test_three_exact_bodies_and_resolved_halfword_local_pair(self):
        for case in INSTRUCTION_CASES:
            for managed in (False, True):
                with self.subTest(case=case, managed=managed):
                    data = startup_fixture(case, managed)
                    result = validate_user_attack_object(**data)
                    self.assertEqual(result["instruction_site"]["offset"], 18 if case == "halfword-ecall" else 0)
                    self.assertEqual(result["object"], "users/fault/startup.o" if managed else "user/startup.o")
                    if case == "halfword-ecall": self.assertEqual(result["local_pair_resolution"],
                        {"kind": "assembler-resolved-local-pair", "pc_relative_start": 0, "pair_offset": 16, "halfword_offset": 2, "relocations": []})
                    for field, value in (("raw", data["raw"] + bytes(4)),
                                         ("section_text", data["section_text"].replace(" AX ", " WAX ")),
                                         ("symbol_text", data["symbol_text"].replace("GLOBAL DEFAULT 6", "GLOBAL DEFAULT 7")),
                                         ("assembly", data["assembly"].replace(".text.user_adversarial", ".text.user"))):
                        bad = copy.deepcopy(data); bad[field] = value
                        with self.assertRaises(Core0Error): validate_user_attack_object(**bad)

    def test_halfword_pair_branch_relocation_and_zero_mutations_reject(self):
        data = startup_fixture("halfword-ecall", True)
        variants = [("assembly", data["assembly"].replace("t0, t0, 2", "t0, t0, 4")),
                    ("assembly", data["assembly"].replace(".word 0x00000000", ".word 0x00000013")),
                    ("assembly", data["assembly"].replace("zero, t1, 7", "zero, t1, 6")),
                    ("relocation_text", "Relocation section '.rela.text.user_adversarial' at offset 0x100 contains 1 entry:\n0000000000000000 0000000100000017 R_RISCV_PCREL_HI20 0000000000000010 foreign + 0\n"),
                    ("symbol_text", data["symbol_text"].replace("0000000000000014 0 NOTYPE", "0000000000000010 0 NOTYPE")),
                    ("symbol_text", data["symbol_text"].replace("NOTYPE LOCAL DEFAULT 6", "NOTYPE GLOBAL DEFAULT 6"))]
        for field, value in variants:
            bad = copy.deepcopy(data); bad[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(Core0Error): validate_user_attack_object(**bad)
        for offset in (0, 8, 16, 20):
            bad = copy.deepcopy(data); raw = bytearray(bad["raw"]); raw[offset] ^= 1; bad["raw"] = bytes(raw)
            with self.subTest(offset=offset), self.assertRaises(Core0Error): validate_user_attack_object(**bad)

    def test_linked_bytes_derive_site_and_privilege_exception_is_only_at_that_word(self):
        for case in INSTRUCTION_CASES:
            data = startup_fixture(case)
            symbol, _, words = USER_ATTACKS[case]; base = 0x10080
            raw = struct.pack("<" + "I" * len(words), *words)
            ranges = {symbol: (base, len(raw))}
            machine = "".join(f" {base+i*4:x}: {word:08x} instruction\n" for i, word in enumerate(words))
            result = validate_user_attack_machine(machine, ranges, data["assembly"], case, raw_bytes=raw,
                        configuration=data["configuration"], unit=data["unit"])
            self.assertEqual(result["fault_pc"], base + INSTRUCTION_CASES[case][0])
            if case == "halfword-ecall":
                disassembly = " 10080: auipc t0, 0\n 10084: addi t0, t0, 16\n 10088: addi t0, t0, 2\n 1008c: jr t0\n 10090: addi zero, t1, 7\n 10094: <unknown>\n 10096: <unknown>\n"
                with self.assertRaises(Core0Error): validate_user_attack_machine(machine, ranges, data["assembly"], case, configuration=data["configuration"], unit=data["unit"])
            else: disassembly = f" 10080: {'sret' if case == 'return-supervisor' else 'mret'}\n"
            validate_machine(disassembly, user=True, ranges=ranges, user_attack=result)
            if case == "halfword-ecall":
                for bad in (disassembly.replace(" 10096: <unknown>\n", ""),
                            disassembly.replace("10096", "10098"),
                            disassembly.replace("10094: <unknown>", "10094: unimp"),
                            disassembly.replace("10094: <unknown>", "10094: <unknown> 0x0")):
                    with self.assertRaises(Core0Error): validate_machine(bad, user=True, ranges=ranges, user_attack=result)
            with self.assertRaises(Core0Error): validate_machine(disassembly, user=True, ranges=ranges)
            for field in ("pc", "offset", "opcode"):
                bad = copy.deepcopy(result); bad["instruction_site"][field] ^= 4
                with self.assertRaises(Core0Error): validate_machine(disassembly, user=True, ranges=ranges, user_attack=bad)
            extended = {**ranges, "ordinary": (0x100a0, 4)}
            for extra in ("sret", "mret", "unimp", "<unknown>"):
                with self.assertRaises(Core0Error): validate_machine(disassembly + f" 100a0: {extra}\n", user=True, ranges=extended, user_attack=result)


FAILED_BODY = """entry:
 %cmp0 = icmp eq i8 %arg0, 0
 br i1 %cmp0, label %if.then.0, label %if.else.1
if.then.0:
 br label %if.merge.2
if.else.1:
 br label %if.merge.2
if.merge.2:
 %if.result1 = phi i1 [ 0, %if.then.0 ], [ 1, %if.else.1 ]
 ret i1 %if.result1
"""


def checked(result, symbol, arguments, failed, success, suffix):
    return f""" %{result} = call {{ i64, i64 }} @{symbol}({arguments})
 %{result}.status = extractvalue {{ i64, i64 }} %{result}, 0
 %{result}.narrow = trunc i64 %{result}.status to i8
 %{result}.failed = call zeroext i1 @{failed}(i8 zeroext %{result}.narrow)
 %{result}.error = icmp eq i1 %{result}.failed, 1
 br i1 %{result}.error, label %fatal{suffix}, label %{success}
fatal{suffix}:
 ret {{ i64, i64 }} zeroinitializer
{success}:
"""


def diagnostic_fixture(managed):
    """Small synthetic CFG grammar fixture, deliberately not an exported unit."""
    p, s, t, a, c = "Lemma.Kernel.Process.", "Lemma.Kernel.Scheduler.", "Lemma.Kernel.Task.", "Lemma.Kernel.Memory.Access.", "Lemma.Kernel.Console."
    context = "Lemma.Kernel.Memory.AddressSpace.context"
    names = {p + "validateFrame", a + "read64", c + "record"}
    names |= ({s + "dispatch", s + "reportFault", s + "failed", s + "finish", s + "returnKernel", t + "capture", t + "failed", context}
              if managed else {p + "dispatch", p + "userTrap", p + "failed", p + "finish"})
    by = {name: "lemma_kernel_fixture_" + str(index) for index, name in enumerate(sorted(names))}
    bodies = {name: "entry:\n ret { i64, i64 } zeroinitializer\n" for name in names}
    if managed:
        bodies[s + "failed"] = bodies[t + "failed"] = FAILED_BODY
        bodies[t + "capture"] = "entry:\n" + checked("owned", by[p + "validateFrame"], "i64 %arg1", by[t + "failed"], "validated", "0")
        bodies[t + "capture"] += f" %context = call {{ i64, i64 }} @{by[context]}(i64 %arg0)\n ret {{ i64, i64 }} %context\n"
        bodies[s + "dispatch"] = "entry:\n" + checked("captured", by[t + "capture"], "i64 %descriptor, i64 %arg0", by[s + "failed"], "captured", "0")
        bodies[s + "dispatch"] += f""" br i1 %halfword, label %half, label %hardware
half:
 %half = call {{ i64, i64 }} @{by[s + 'reportFault']}(i64 %descriptor, i64 %arg0, i64 %arg1, i64 %arg2, i64 %pc)
 ret {{ i64, i64 }} %half
hardware:
 %fault = call {{ i64, i64 }} @{by[s + 'reportFault']}(i64 %descriptor, i64 %arg0, i64 %arg1, i64 %arg2, i64 %pc)
 ret {{ i64, i64 }} %fault
"""
        bodies[s + "reportFault"] = "entry:\n %status.address = add i64 %arg1, 264\n" + checked("loaded", by[a + "read64"], "i64 %status.address", by[s + "failed"], "loaded", "0")
        bodies[s + "reportFault"] += " %hardware.status = extractvalue { i64, i64 } %loaded, 1\n" + checked("recorded", by[c + "record"], "i64 212, i64 %arg2, i64 %arg4, i64 %arg3, i64 %hardware.status", by[s + "failed"], "recorded", "1")
        bodies[s + "reportFault"] += f" %finished = call {{ i64, i64 }} @{by[s + 'finish']}(i64 %arg0, i64 %arg2, i64 44, i64 %arg4, i64 %arg3)\n ret {{ i64, i64 }} %finished\n"
        bodies[s + "finish"] = f"""entry:
 %cause = icmp eq i64 %arg1, 8
 br i1 %cause, label %half, label %hardware
half:
 br label %return
hardware:
 br label %return
return:
 %reason = phi i64 [ 4, %half ], [ 5, %hardware ]
 %returned = call {{ i64, i64 }} @{by[s + 'returnKernel']}(i64 %arg0, i64 %reason, i64 %arg3)
 ret {{ i64, i64 }} %returned
"""
    else:
        bodies[p + "failed"] = FAILED_BODY
        bodies[p + "dispatch"] = "entry:\n" + checked("owned", by[p + "validateFrame"], "i64 %arg0", by[p + "failed"], "owned", "0")
        bodies[p + "dispatch"] += f""" %status.address = add i64 %arg0, 264
 %loaded = call {{ i64, i64 }} @{by[a + 'read64']}(i64 %status.address)
 %hardware.status = extractvalue {{ i64, i64 }} %loaded, 1
 %trapped = call {{ i64, i64 }} @{by[p + 'userTrap']}(i64 %descriptor, i64 %arg0, i64 %arg1, i64 %arg2, i64 %pc, i64 %hardware.status, i64 %translation)
 ret {{ i64, i64 }} %trapped
"""
        bodies[p + "userTrap"] = "entry:\n br i1 %halfword, label %half, label %hardware\n"
        for branch in ("half", "hardware"):
            bodies[p + "userTrap"] += f"""{branch}:
 %{branch}.record = call {{ i64, i64 }} @{by[c + 'record']}(i64 212, i64 %arg2, i64 %arg4, i64 %arg3, i64 %arg5)
 %{branch}.finish = call {{ i64, i64 }} @{by[p + 'finish']}(i64 %arg0, i64 %arg2, i64 44, i64 %arg4, i64 %arg5, i64 %arg6)
 ret {{ i64, i64 }} %{branch}.finish
"""
    selected = {"configuration": ("service-" if managed else "user-") + "halfword-ecall-development", "role": "kernel",
                "functions": [{"source": name, "symbol": symbol} for name, symbol in by.items()]}
    def render(values):
        return "\n".join(f"define {{ i64, i64 }} @{by[name]}() {{\n{body}}}" for name, body in values.items())
    return selected, bodies, by, render


class ArchitectureDiagnosticsFailures(unittest.TestCase):
    def test_genuine_managed_cfg_rejects_status_substitution_and_failed_capture(self):
        value = json.loads((Path(__file__).parent / "fixtures/architecture-managed-diagnostics.json").read_text())
        selected, ir = value["unit"], value["pre_ir"]
        report = validate_architecture_diagnostics(selected, ir)
        self.assertEqual(report["raw_status_offset"], 264)
        by = report["source_functions"]
        record = re.findall(r"call \{ i64, i64 \} @" + re.escape(by["Lemma.Kernel.Console.record"]) + r"\(i64 212, i64 %arg2, i64 %arg4, i64 %arg3, i64 (%[^)]+)\)", ir)
        self.assertEqual(len(record), 1)
        gate = report["ownership_gates"][0]["gate"]
        branch = "br i1 " + gate["comparison"] + ", label %" + gate["failure"] + ", label %" + gate["success"]
        variants = [ir.replace("add i64 %arg1, 264", "add i64 %arg1, 272"),
                    ir.replace("i64 %arg3, i64 " + record[0] + ")", "i64 %arg3, i64 8589934624)"),
                    ir.replace(branch, "br i1 " + gate["comparison"] + ", label %" + gate["success"] + ", label %" + gate["failure"]),
                    ir.replace("i64 %arg2, i64 44, i64 %arg4", "i64 %arg2, i64 0, i64 %arg4")]
        for bad in variants:
            self.assertNotEqual(ir, bad)
            with self.assertRaises(Core0Error): validate_architecture_diagnostics(selected, bad)

    def test_original_frame_word_success_gates_and_d4_before_termination(self):
        for managed in (False, True):
            selected, bodies, by, render = diagnostic_fixture(managed)
            report = validate_architecture_diagnostics(selected, render(bodies))
            self.assertEqual(report["raw_status_offset"], 264)
            self.assertEqual(len(report["ownership_gates"]), 4 if managed else 1)
            self.assertEqual(report["diagnostic_before_termination"]["before"], by["Lemma.Kernel.Console.record"])
            self.assertEqual(report["halfword_ecall_return_reason"], 4 if managed else None)

    def test_sanitized_status_wrong_original_frame_or_termination_rejected(self):
        for managed in (False, True):
            selected, bodies, by, render = diagnostic_fixture(managed)
            source = "Lemma.Kernel.Scheduler.reportFault" if managed else "Lemma.Kernel.Process.dispatch"
            changes = [(source, "264", "272"), (source, "add i64 %arg1" if managed else "add i64 %arg0", "add i64 %other"),
                       (source, "%loaded, 1", "%loaded, 0"),
                       (source, "i64 %hardware.status", "i64 8589934624"),
                       ("Lemma.Kernel.Scheduler.reportFault" if managed else "Lemma.Kernel.Process.userTrap", "i64 44", "i64 0")]
            if managed:
                changes += [("Lemma.Kernel.Scheduler.dispatch", "i64 %arg0, i64 %arg1", "i64 %other, i64 %arg1"),
                            ("Lemma.Kernel.Task.capture", "label %fatal0, label %validated", "label %validated, label %fatal0"),
                            ("Lemma.Kernel.Scheduler.reportFault", "label %fatal1, label %recorded", "label %recorded, label %fatal1"),
                            ("Lemma.Kernel.Scheduler.finish", "[ 4, %half ], [ 5, %hardware ]", "[ 5, %half ], [ 4, %hardware ]")]
            for name, before, after in changes:
                bad = copy.deepcopy(bodies); bad[name] = bad[name].replace(before, after)
                self.assertNotEqual(bad, bodies, (name, before))
                with self.subTest(managed=managed, before=before), self.assertRaises(Core0Error): validate_architecture_diagnostics(selected, render(bad))
            missing = copy.deepcopy(selected); missing["functions"] = [row for row in missing["functions"] if row["source"] != "Lemma.Kernel.Process.validateFrame"]
            with self.assertRaises(Core0Error): validate_architecture_diagnostics(missing, render(bodies))


if __name__ == "__main__": unittest.main()
