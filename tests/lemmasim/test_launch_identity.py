"""Fail-closed launch identity checks; these do not certify guest execution."""
from copy import deepcopy
from importlib.machinery import SourceFileLoader
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import tempfile
import tarfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
loader = SourceFileLoader('launch_identity_lemmasim', str(ROOT / 'scripts/lemmasim'))
spec = importlib.util.spec_from_loader(loader.name, loader)
sim = importlib.util.module_from_spec(spec)
loader.exec_module(sim)

OUTPUT = '/nix/store/literal-lemmasim-qemu'
DERIVATION = OUTPUT + '.drv'
BINARY = OUTPUT + '/bin/qemu-system-riscv64'
HASH = '1' * 64


def closure():
    return {'schema_version': 1, 'outPath': OUTPUT, 'drvPath': DERIVATION,
            'binary': {'path': BINARY, 'sha256': HASH},
            'derivation_sha256': HASH, 'qemu_recipe_sha256': HASH,
            'qemu_patch_sha256': HASH, 'flake_lock_sha256': HASH,
            'backend_sources': {'sim/host/lemma_model.c': HASH}}


def literal_policy():
    # Independently written frozen fixture, not copied from production policy.
    return {'core': 'lemma-one-core/0.1.0', 'binding': 'lemmasim-virt/0.1.0',
            'pressure_max': 4095, 'timebase_hz': 10000000, 'icount_shift': 3,
            'clock_policy': 'QEMU virtual clock, RTC origin2026-10-10T00:00:00, blkreplay completion ordering',
            'close_policy': 'record-SIGTERM/replay-no-shutdown/exact-instruction-boundary-v1',
            'random_seed': '0x4c454d4d413031', 'media_backend': 'lemma-durable/1'}


class LaunchIdentity(unittest.TestCase):
    def test_backend_evaluation_is_read_only_bounded_and_exact(self):
        answer = subprocess.CompletedProcess([], 0,
                 json.dumps({'output': OUTPUT, 'derivation': DERIVATION}), '')
        with patch.object(Path, 'is_file', return_value=True), \
                patch.object(sim.os, 'access', return_value=True), \
                patch.object(sim, 'sha', return_value=HASH), \
                patch.object(sim, 'backend_sources', return_value={'sim/host/lemma_model.c': HASH}), \
                patch.object(sim.subprocess, 'run', return_value=answer) as evaluate:
            identity = sim.backend_identity(BINARY, timeout=7)
            self.assertEqual(identity['binary']['path'], BINARY)
            command = evaluate.call_args.args[0]
            self.assertEqual(command[:4], ['nix-instantiate', '--eval', '--strict', '--json'])
            self.assertNotIn('build', command)
            self.assertEqual(evaluate.call_args.kwargs['timeout'], 7)
            with self.assertRaisesRegex(sim.Failure, 'current LemmaSim derivation'):
                sim.backend_identity('/nix/store/other-qemu/bin/qemu-system-riscv64')

    def test_immutable_saved_identity_needs_no_nix_and_rejects_missing_closure(self):
        identity = closure()
        metadata = {'qemu': identity['binary'], 'qemu_closure': identity}
        with patch.object(Path, 'is_file', return_value=True), \
                patch.object(sim.os, 'access', return_value=True), \
                patch.object(sim, 'sha', return_value=HASH), \
                patch.object(sim.subprocess, 'run', side_effect=AssertionError('launch must not evaluate Nix')):
            self.assertEqual(sim.validate_backend_identity(metadata), identity)
            with self.assertRaisesRegex(sim.Failure, 'unsupported'):
                sim.validate_backend_identity({'qemu': identity['binary']})
            mutations = []
            other = deepcopy(metadata);other['qemu']['path'] = '/nix/store/other/bin/qemu-system-riscv64';mutations.append(other)
            other = deepcopy(metadata);other['qemu_closure']['derivation_sha256'] = '2' * 64;mutations.append(other)
            other = deepcopy(metadata);other['backend_sources'] = {'sim/host/lemma_model.c': '2' * 64};mutations.append(other)
            other = deepcopy(metadata);other['qemu_closure']['qemu_patch_sha256'] = 'invalid';mutations.append(other)
            for mutated in mutations:
                with self.subTest(mutated=mutated), self.assertRaises(sim.Failure):
                    sim.validate_backend_identity(mutated)

    def test_replay_cannot_add_a_disk_to_its_original_session(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder) / 'session';session.mkdir()
            identity = {'schema_version': 1, 'binding': 'lemmasim-virt/0.1.0',
                        'close_policy': 'record-SIGTERM/replay-no-shutdown/exact-instruction-boundary-v1',
                        'build': {'qemu': {'path': BINARY, 'sha256': HASH},
                                  'notebook': {'path': '/literal/image.elf', 'sha256': HASH}},
                        'initial_media_sha256': HASH}
            payload = json.dumps(identity);(session / 'identity.json').write_text(payload)
            disk = session / 'new-replay.raw'
            with patch.object(sim, 'validate_backend_identity'), patch.object(sim, 'sha', return_value=HASH):
                with self.assertRaisesRegex(sim.Failure, 'outside the original session tree'):
                    sim.replay(SimpleNamespace(session=session, disk_copy=disk, timeout=10))
            self.assertFalse(disk.exists())
            self.assertEqual((session / 'identity.json').read_text(), payload)

    def test_altered_replay_policy_is_refused_before_destination_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);session = root / 'session';(session / 'run').mkdir(parents=True)
            identity = {'schema_version': 1, **literal_policy(), 'build': {},
                        'mode': 'developer', 'geometry': '1650x2200'}
            # None of these fixtures is a guest run. The changed policy must
            # reject before it can even request backend/media/input bytes.
            sim.write_json(session / 'run/result.json', {})
            sim.write_json(session / 'run/process.json', {})
            disk = root / 'fresh' / 'replay.raw'
            for field,value in (('icount_shift', 4), ('random_seed', '0x1'),
                                ('timebase_hz', 1), ('pressure_max', 1023),
                                ('clock_policy', 'host clock'), ('media_backend', 'other')):
                changed = dict(identity);changed[field] = value
                sim.write_json(session / 'identity.json', changed)
                with patch.object(sim, 'validate_backend_identity'), patch.object(sim.shutil, 'copyfile', side_effect=AssertionError('must not copy')):
                    with self.subTest(field=field), self.assertRaisesRegex(sim.Failure, 'frozen replay policy: ' + field):
                        sim.replay(SimpleNamespace(session=session, disk_copy=disk, timeout=10))
                self.assertFalse(disk.parent.exists())

    def test_replay_policy_matches_recorded_machine_and_process(self):
        metadata = {'core': 'lemma-one-core/0.1.0', 'profile': 'lemmasim-virt/0.1.0',
                    'qemu': {'path': BINARY, 'sha256': HASH}, 'notebook': {'sha256': HASH}}
        identity = {**literal_policy(), 'build': metadata, 'mode': 'developer',
                    'geometry': '1650x2200', 'fault_inputs': {},
                    'initial_media_sha256': HASH, 'machine_descriptor_sha256': HASH,
                    'actual_boot_dtb_sha256': HASH}
        original = {'mode': 'developer', 'geometry': [1650, 2200], 'fault_inputs': {},
                    'build_identity': metadata, 'argv': [BINARY], 'guest_sha256': HASH,
                    'initial_media_sha256': HASH, 'machine_descriptor_sha256': HASH,
                    'actual_boot_dtb_sha256': HASH, 'media_backend': 'lemma-durable/1',
                    'random_seed': '0x4c454d4d413031'}
        process = {'mode': 'developer', 'recording': True, 'replaying': False}
        sim.validate_replay_policy(identity, original, process)
        for field,value in (('mode', 'student'), ('geometry', [1404, 1872]),
                            ('fault_inputs', {'fail-flush': 1}), ('guest_sha256', '2' * 64)):
            changed = deepcopy(original);changed[field] = value
            with self.subTest(field=field), self.assertRaises(sim.Failure):
                sim.validate_replay_policy(identity, changed, process)

    def test_offline_archive_retains_only_identified_fixed_guest_files(self):
        # Literal files validate archive integrity/path policy, not ELF/audits.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);session = root / 'session';session.mkdir()
            sim.write_json(session / 'result.json', {'status': 'CLOSED', 'process_reaped': True})
            metadata = {'qemu_closure': closure()}
            for role in ('notebook', 'initializer'):
                build = root / role;build.mkdir()
                names = ('image.elf', 'build.json', 'provenance.json', 'audit.json') + (('capacity.json',) if role == 'notebook' else ())
                for name in names:(build / name).write_bytes((role + '/' + name).encode())
                (build / 'unidentified.txt').write_text('must not enter archive')
                metadata[role] = {'path': str(build / 'image.elf'), 'sha256': sim.sha(build / 'image.elf'),
                                  'artifacts': sim.guest_artifact_identity(build / 'image.elf', require_capacity=role == 'notebook')}
            sim.write_json(session / 'identity.json', {'build': metadata})
            archive = root / 'offline.tar.gz'
            with patch.object(sim, 'validate_backend_identity'):
                sim.archive_session(SimpleNamespace(session=session, to=archive))
            with tarfile.open(archive) as result:
                names = set(result.getnames())
                self.assertIn('artifacts/notebook/capacity.json', names)
                self.assertIn('artifacts/initializer/image.elf', names)
                self.assertNotIn('artifacts/initializer/capacity.json', names)
                self.assertFalse(any(name.endswith('unidentified.txt') for name in names))
                inventory = json.load(result.extractfile('inventory.json'))
                self.assertEqual(len(inventory['guest_artifacts']), 9)
                for item in inventory['guest_artifacts']:
                    data = result.extractfile(item['path']).read()
                    self.assertEqual(sim.hashlib.sha256(data).hexdigest(), item['sha256'])
            (root / 'notebook/provenance.json').write_text('changed')
            changed = root / 'changed.tar.gz'
            with patch.object(sim, 'validate_backend_identity'), self.assertRaisesRegex(sim.Failure, 'changed'):
                sim.archive_session(SimpleNamespace(session=session, to=changed))
            self.assertFalse(changed.exists())
            inside = session / 'archive.tar.gz'
            with self.assertRaisesRegex(sim.Failure, 'outside the original session tree'):
                sim.archive_session(SimpleNamespace(session=session, to=inside))

    def test_guest_artifact_paths_cannot_follow_a_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder);image = build / 'image.elf';image.write_bytes(b'literal image')
            for name in ('build.json', 'provenance.json', 'audit.json'):(build / name).write_bytes(name.encode())
            artifacts = sim.guest_artifact_identity(image)
            entry = {'path': str(image), 'sha256': sim.sha(image), 'artifacts': artifacts}
            self.assertEqual(len(sim.validate_guest_artifact_identity(entry)), 4)
            (build / 'provenance.json').unlink();(build / 'provenance.json').symlink_to(build / 'audit.json')
            with self.assertRaisesRegex(sim.Failure, 'symlinked'):
                sim.validate_guest_artifact_identity(entry)


if __name__ == '__main__':
    unittest.main()
