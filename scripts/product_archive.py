"""Retain exact immutable Product10 components, without any user media.

This is a local prepared-component archive. The maintained host command and
the inventoried external Nix tools/libraries remain required. It does not
install a guest image or turn a development key into a production identity.
"""
from pathlib import Path
import copy
import json
import shutil
from product_native import sha


def create(source, destination, validate):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('Unused product archive output required')
    data, native, rom = validate(source)
    if not data.get('native_source_archive') or not data.get('rom_source_archive'):
        raise ValueError('Product archive requires both complete consumed-source archives')
    selected = {}

    def add(path, name):
        path, name = Path(path), Path(name)
        if (name.is_absolute() or '..' in name.parts or not name.parts or
                path.is_symlink() or not path.is_file() or name.as_posix() in selected):
            raise ValueError('Invalid/duplicate product archive member')
        selected[name.as_posix()] = (path, sha(path))

    for name in ('build.json', 'obj/lemma-rtl', 'generated/lemma_runtime_identity.h'):
        add(Path(data['native_build']) / name, Path('native') / name)
    add(Path(data['rom_build']) / 'build.json', 'rom/build.json')
    for name in rom['manifest']['artifacts']:
        add(Path(data['rom_build']) / name, Path('rom') / name)
    for role in ('native', 'rom'):
        origin = Path(data[role + '_source_archive'])
        receipt = origin.parent / 'consumed-source-archive.json'
        manifest = json.loads(receipt.read_text())
        add(receipt, Path(role + '-source') / receipt.name)
        for name in manifest['inputs']:
            add(origin / name, Path(role + '-source/consumed-source-root') / name)
    for name in ('discovery.dts', 'discovery.dtb', 'descriptor.bin', 'DEPENDENCIES.txt'):
        add(source / name, name)
    sizes = [path.stat().st_size for path, _ in selected.values()]
    if not 1 <= len(selected) <= 8192 or max(sizes) > 64 << 20 or sum(sizes) > 256 << 20:
        raise ValueError('Product archive exceeds8192 files/64MiB file/256MiB total bound')
    destination.mkdir(parents=True)
    for name, (path, digest) in selected.items():
        output = destination / name
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, output)
        if sha(output) != digest:
            raise ValueError('Changed product archive copy: ' + name)
        if name == 'native/obj/lemma-rtl':
            output.chmod(0o755)
    relocated = copy.deepcopy(data)
    for role in ('native', 'rom'):
        relocated[role + '_build'] = str(destination / role)
        relocated[role + '_source_archive'] = str(destination / (role + '-source/consumed-source-root'))
    (destination / 'prepared.json').write_text(json.dumps(relocated, indent=2) + '\n')
    actual, _, _ = validate(destination)
    if {k: v for k, v in actual.items() if k not in ('native_build', 'rom_build', 'native_source_archive', 'rom_source_archive')} != {
            k: v for k, v in data.items() if k not in ('native_build', 'rom_build', 'native_source_archive', 'rom_source_archive')}:
        raise ValueError('Relocation changed product semantics')
    inventory = {name: digest for name, (_, digest) in selected.items()}
    inventory['prepared.json'] = sha(destination / 'prepared.json')
    report = {
        'schema': 'lemma-local-product-component-archive/1',
        'status': 'PASS_EXACT_LOCAL_PRODUCT_COMPONENT_ARCHIVE',
        'source_prepared_sha256': sha(source / 'prepared.json'),
        'profile': data['profile'], 'runtime_identity': data['runtime_identity'],
        'rom_sha256': data['rom_sha256'], 'inputs': inventory,
        'files': len(inventory), 'bytes': sum((destination / name).stat().st_size for name in inventory),
        'scope': __doc__,
        'external_dependencies': 'Exact prepared host sources, Nix audit tools, dtc and runtime libraries remain required.',
        'user_media_included': False,
    }
    (destination / 'archive.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
