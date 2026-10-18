"""Check the closed grammar against real assembler file-consuming behavior."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_dependencies import embedded_inputs, validate_llvm_arguments
from build_core0 import LLC_ARGUMENTS, STARTUP_ARGUMENTS
from core0_common import Core0Error


class EmbeddedDependencyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def source(self, name, content):
        path = self.root / name;path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def clang(self, source):
        pin = json.loads((ROOT / 'tooling/toolchain-lock.json').read_text())
        locked = Path(pin['tools']['llvm']['outputs']['clang_unwrapped']['executable'])
        command = Path(shutil.which('clang') or locked)
        self.assertTrue(command.is_file(), 'actual pinned Clang is required; run inside nix develop')
        self.assertEqual(command.resolve(), locked.resolve(), 'foreign Clang cannot qualify this fixture')
        result = subprocess.run([str(command), *STARTUP_ARGUMENTS, str(source), '-o', str(source.with_suffix('.o'))],
                                cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(source.with_suffix('.o').is_file())

    def test_actual_label_prefixed_include_and_cpp_import_are_rejected(self):
        extra = self.source('extra.S', 'addi a0,zero,1\n')
        for name, directive in [('label', f'label: .include "{extra}"'),
                                ('import', f'#import "{extra}"')]:
            with self.subTest(name=name):
                source = self.source(name + '.S', '.section .text\n' + directive + '\n')
                self.clang(source)  # These are valid external-file consumers.
                with self.assertRaisesRegex(Core0Error, 'dependency'):
                    embedded_inputs(source)

    def test_actual_absolute_labelled_and_offset_incbin_are_rejected(self):
        data = self.root / 'data.bin';data.write_bytes(b'opaque fixture bytes')
        for name, directive in [('absolute', f'.incbin "{data}"'),
                                ('label', 'label: .incbin "data.bin"'),
                                ('offset', '.incbin "data.bin", 1, 3')]:
            with self.subTest(name=name):
                source = self.source(name + '.S', '.section .rodata\n' + directive + '\n')
                self.clang(source)
                with self.assertRaises(Core0Error):embedded_inputs(source)

    def test_actual_canonical_packaging_declares_every_embedded_file(self):
        (self.root / 'users/notebook').mkdir(parents=True)
        (self.root / 'users/notebook/text.bin').write_bytes(b'first compiled payload')
        (self.root / 'users/notebook/data.bin').write_bytes(b'second compiled payload')
        source = self.source('package.S', '.section .rodata\n.balign 8\n'
                             '  .incbin "users/notebook/text.bin"\n'
                             '  .incbin "users/notebook/data.bin"\n')
        self.clang(source)
        self.assertEqual(embedded_inputs(source), ['users/notebook/text.bin', 'users/notebook/data.bin'])
        self.assertEqual(embedded_inputs(source.with_suffix('.o')), [])

    def test_macros_preprocessing_linker_and_ir_variants_fail_closed(self):
        cases = [('preprocess.S', '#include_next "other.S"\n'),
                 ('digraph.S', '%:import "/outside.S"\n'),
                 ('macro.S', '.macro file x\n.\\x "/outside.S"\n.endm\nfile include\n'),
                 ('search.ld', 'SECTIONS {} SEARCH_DIR("/outside")\n'),
                 ('include.ld', 'SECTIONS {} INCLUDE "/outside.ld"\n'),
                 ('input.ld', 'SECTIONS {} INPUT("/outside.o")\n'),
                 ('group.ld', 'SECTIONS {} GROUP("/outside.a")\n'),
                 ('startup.ld', 'SECTIONS {} STARTUP("/outside.o")\n'),
                 ('output.ld', 'OUTPUT("/outside.elf")\nSECTIONS {}\n'),
                 ('escaped.S', '.incbin "\\057outside.bin"\n'),
                 ('asm.ll', 'module asm ".include \\22/outside.S\\22"\n'),
                 ('inline.ll', 'call void asm sideeffect ".incbin \\22/outside\\22", ""()\n'),
                 ('library.ll', '!llvm.dependent-libraries = !{!0}\n!0 = !{!"outside"}\n')]
        for name, content in cases:
            with self.subTest(name=name), self.assertRaises(Core0Error):
                embedded_inputs(self.source(name, content))

    def test_linker_output_format_and_normal_ir_have_no_external_files(self):
        self.assertEqual(embedded_inputs(self.source('link.ld', 'OUTPUT_FORMAT("elf64-littleriscv")\nOUTPUT_ARCH(riscv)\nENTRY(_start)\n'
                                                   'SECTIONS { . = 0x80000000; .text : { KEEP(startup.o(.text.init)) *(.text .text.*) } }\n')), [])
        self.assertEqual(embedded_inputs(self.source('program.ll', 'define i64 @f() { ret i64 1 }\n')), [])
        with self.assertRaisesRegex(Core0Error, 'ordinary RV64 ELF'):
            embedded_inputs(self.source('disguised.o', 'INPUT("/outside/other.o")\n'))


class ArgumentGrammarTests(unittest.TestCase):
    def test_current_optimization_object_link_and_packaging_recipes_are_accepted(self):
        cases = [('opt', ['-S', '-passes=verify', 'program.ll', '-o', 'program.opt.ll']),
                 ('opt', ['-S', '-passes=default<O2>', 'program.ll', '-o', 'program.opt.ll']),
                 ('llc', [*LLC_ARGUMENTS, '-stack-size-section', '-O2', 'program.opt.ll', '-o', 'program.o']),
                 ('clang', [*STARTUP_ARGUMENTS, 'startup.S', '-o', 'startup.o']),
                 ('ld.lld', ['-m', 'elf64lriscv', '--no-relax', '--discard-none', '-T', 'link.ld', '-Map=image.map', 'startup.o', 'program.o', '-o', 'image.elf']),
                 ('llvm-objcopy', ['-O', 'binary', '--only-section=.text', 'image.elf', 'text.bin'])]
        for kind, args in cases:
            with self.subTest(kind=kind):validate_llvm_arguments(kind, args)

    def test_unknown_joined_response_plugins_and_malformed_options_reject(self):
        cases = [('opt', ['-S', '-passes=verify', '-load-pass-plugin=foreign.so', 'a.ll', '-o', 'b.ll']),
                 ('opt', ['-S', '-passes=verify', '@foreign.rsp', '-o', 'b.ll']),
                 ('opt', ['-S', '-passes=verify', 'a.ll', '-o']),
                 ('opt', ['-S', '-passes=verify', 'a.ll', '-o', 'a.ll']),
                 ('opt', ['-S', '-passes=verify', '-passes=default<O2>', 'a.ll', '-o', 'b.ll']),
                 ('llc', [*LLC_ARGUMENTS, '-O0', '-O2', 'a.ll', '-o', 'a.o']),
                 ('clang', [*STARTUP_ARGUMENTS, '-include', '/foreign.h', 'a.S', '-o', 'a.o']),
                 ('ld.lld', ['-m', 'elf64lriscv', '--no-relax', '-Tforeign.ld', 'a.o', '-o', 'a.elf']),
                 ('ld.lld', ['-m', 'elf64lriscv', '--no-relax', '-T', 'local.ld', 'a.o', '-o', '../outside.elf']),
                 ('ld.lld', ['-m', 'elf64lriscv', '--no-relax', '-T', 'local.ld', 'a.o', '-o', 'a.elf', '-Map=one.map', '-Map=two.map']),
                 ('ld.lld', ['-m', 'elf64lriscv', '--no-relax', '-T', 'hidden.extension', 'a.o', '-o', 'a.elf']),
                 ('llvm-objcopy', ['-O', 'elf64-littleriscv', '--only-section=.text', 'a.elf', 'a.bin'])]
        for kind, args in cases:
            with self.subTest(kind=kind, args=args), self.assertRaises(Core0Error):
                validate_llvm_arguments(kind, args)


if __name__ == '__main__':
    unittest.main()
