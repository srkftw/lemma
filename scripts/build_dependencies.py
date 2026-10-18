"""Closed file/option grammar for the maintained LLVM action recipes.

Generated packaging may embed explicitly named raw files. Other textual file
directives, preprocessing, assembly macros and IR assembly are outside these
recipes and reject before a cache lookup or compiler invocation.
"""
from pathlib import Path
import re

from core0_common import Core0Error

SCHEMA = 'lemma-llvm-dependencies/1'


def _relative(name):
    if (not isinstance(name, str) or re.fullmatch(r'[A-Za-z0-9_./-]+', name) is None or
            name.startswith('-') or Path(name).is_absolute() or '..' in Path(name).parts or
            Path(name).as_posix() != name or name == '.'):
        raise Core0Error('LLVM action requires a canonical relative file name: ' + str(name))
    return name


def embedded_inputs(path: Path) -> list[str]:
    """Return only fully declared canonical packaging incbins; reject unknowns."""
    path = Path(path)
    if path.suffix == '.o':
        data = path.read_bytes()
        # LLD also interprets textual files passed as objects as linker scripts.
        # Require actual RV64 ELF relocatables before treating them as opaque.
        if (len(data) < 64 or data[:7] != b'\x7fELF\x02\x01\x01' or
                int.from_bytes(data[16:18], 'little') != 1 or
                int.from_bytes(data[18:20], 'little') != 243 or
                any(name in data for name in (b'.deplibs\0', b'.linker-options\0'))):
            raise Core0Error('unsupported object/linker dependency; require ordinary RV64 ELF relocatable')
        return []
    if path.suffix not in ('.S', '.s', '.ld', '.ll'):
        return []
    text = path.read_text()
    # Clang's assembler-with-cpp splices lines before parsing directives, even
    # with intervening horizontal whitespace. read_text normalizes CR/CRLF.
    # Reject this unsupported syntax before looking for file-consuming tokens.
    if re.search(r'\\[^\S\n]*\n', text):
        raise Core0Error('unsupported LLVM input line continuation dependency')
    # Conservative matching deliberately includes comments. An irrelevant
    # comment can be removed; an unaccounted external input cannot be admitted.
    if path.suffix == '.ll':
        if re.search(r'\b(?:asm|llvm\.dependent-libraries|llvm\.linker\.options)\b|\.\s*(?:include|incbin)\b', text, re.I):
            raise Core0Error('undeclared LLVM IR assembly/linker dependency')
        return []
    if re.search(r'(?m)^\s*(?:#|%:|\?\?=)|(?:#|%:|\?\?=)\s*(?:include(?:_next)?|import|embed|define|undef)\b|\.\s*(?:include|macro|purgem|irp|irpc)\b|\bINCLUDE(?=\s|[\"\x27(])|\b(?:INPUT|GROUP|SEARCH_DIR|STARTUP|AS_NEEDED|OUTPUT)\s*\(', text, re.I):
        raise Core0Error('undeclared assembly/preprocessor/linker dependency')
    # Linker comments may separate a directive from its argument list. Token
    # rejection avoids depending on LLD's whitespace/comment normalization.
    if path.suffix == '.ld' and re.search(r'(?<![\w./-])(?:INCLUDE|INPUT|GROUP|SEARCH_DIR|STARTUP|AS_NEEDED|OUTPUT)(?![\w.-]|/(?!\*))', text, re.I):
        raise Core0Error('undeclared linker directive dependency')
    found = []
    for line in text.splitlines():
        if not re.search(r'\.\s*incbin\b', line, re.I):
            continue
        match = re.fullmatch(r'\s*\.incbin\s+"([A-Za-z0-9_./-]+)"\s*', line)
        if path.suffix == '.ld' or match is None:
            raise Core0Error('unsupported embedded-file directive; require one canonical incbin line')
        name = _relative(match[1])
        if name not in found:
            found.append(name)
    return found


def validate_llvm_arguments(kind: str, args) -> None:
    """Accept the actual bounded recipes, including option arity and values."""
    from build_core0 import LLC_ARGUMENTS, STARTUP_ARGUMENTS
    if kind not in {'opt', 'llc', 'clang', 'ld.lld', 'llvm-objcopy'} or not isinstance(args, (list, tuple)) or not args or any(not isinstance(arg, str) or not arg or arg.startswith('@') for arg in args):
        raise Core0Error('unsupported LLVM action recipe/response-file dependency')
    singles = {
        'opt': {'-S', '-passes=verify', '-passes=default<O2>'},
        'llc': {*LLC_ARGUMENTS, '-stack-size-section', '-O0', '-O2'},
        'clang': set(STARTUP_ARGUMENTS),
        'ld.lld': {'--no-relax', '--discard-none'},
        'llvm-objcopy': {'--only-section=.text', '--only-section=.data'},
    }[kind]
    seen, pairs, positional = set(), {}, []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in singles:
            if arg in seen:
                raise Core0Error('duplicate LLVM action option: ' + arg)
            seen.add(arg);index += 1;continue
        paired = {'-O'} if kind == 'llvm-objcopy' else {'-o'} | ({'-m', '-T'} if kind == 'ld.lld' else set())
        if arg in paired:
            if arg in pairs or index + 1 >= len(args):
                raise Core0Error('missing/duplicate LLVM action option value: ' + arg)
            value = args[index + 1]
            if (arg == '-m' and value != 'elf64lriscv') or (arg == '-O' and value != 'binary'):
                raise Core0Error('unsupported LLVM action option value: ' + arg)
            pairs[arg] = value if arg in {'-m', '-O'} else _relative(value)
            index += 2;continue
        if kind == 'ld.lld' and arg.startswith('-Map='):
            if '-Map' in pairs:
                raise Core0Error('duplicate linker map output')
            pairs['-Map'] = _relative(arg[len('-Map='):]);index += 1;continue
        if arg.startswith('-'):
            raise Core0Error('unsupported LLVM action option/dependency: ' + arg)
        positional.append(_relative(arg));index += 1
    if kind == 'llvm-objcopy':
        valid = set(pairs) == {'-O'} and len(seen) == 1 and len(positional) == 2
        inputs, outputs = positional[:1], positional[1:]
    else:
        inputs, outputs = positional, [pairs.get('-o')]
        valid = '-o' in pairs and bool(inputs)
        if kind == 'opt':
            valid = valid and len(inputs) == 1 and '-S' in seen and len(seen) == 2
        elif kind == 'llc':
            valid = valid and len(inputs) == 1 and set(LLC_ARGUMENTS) <= seen and len(seen & {'-O0', '-O2'}) == 1
        elif kind == 'clang':
            valid = valid and len(inputs) == 1 and seen == set(STARTUP_ARGUMENTS)
        elif kind == 'ld.lld':
            valid = valid and {'-m', '-T', '-o'} <= set(pairs) and '--no-relax' in seen
            inputs = [*inputs, pairs.get('-T')]
            if '-Map' in pairs:outputs.append(pairs['-Map'])
    if not valid or len(set(outputs)) != len(outputs) or set(inputs) & set(outputs):
        raise Core0Error('LLVM action option arity/input/output grammar differs')
    suffixes = {'opt': {'.ll'}, 'llc': {'.ll'}, 'clang': {'.S', '.s'},
                'ld.lld': {'.o'}, 'llvm-objcopy': {'.elf'}}[kind]
    ordinary = positional[:1] if kind == 'llvm-objcopy' else positional
    if any(Path(name).suffix not in suffixes for name in ordinary) or (kind == 'ld.lld' and Path(pairs['-T']).suffix != '.ld'):
        raise Core0Error('LLVM action input kind is outside its declared scanner grammar')
