"""Admission controls; actual-archive campaign requires explicit --archive.

Discovery runs only manifest/parser tests. The explicit campaign uses independently
produced artifacts; no fixture claims a successful compiler, audit or Wasm build.
Mutated clones use hard links, but every write replaces a link atomically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import lemmasim_browser_tci as subject
import lemmasim_browser as server


class ManifestParsing(unittest.TestCase):
    def test_native_mm2_continuation_rejects_before_browser_output(self):
        # Host admission boundary only: no invented successful runtime/guest.
        # Skip runtime inspection to isolate the subsequent native-scope check.
        from multimodal_native_bundle import SCHEMA
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'native';archive.mkdir();out=root/'must-not-exist'
            (archive/'bundle.json').write_text(json.dumps({'schema':SCHEMA,
                'checkpoint_binding':'lemma-silicon-fast-mm2-softtlb/0.1.0'}))
            args=SimpleNamespace(profile=subject.PROFILE,workbook='school',
                wasm_build=root/'not-inspected',guest_bundle=archive,output_dir=out)
            with patch.object(subject,'retained_runtime',return_value=(root,{})):
                with self.assertRaisesRegex(ValueError,'TCI cannot import native MM2 continuation'):
                    subject.bundle(args)
            self.assertFalse(out.exists())

    def test_duplicate_members_reject_at_each_object_depth(self):
        for text in ('{"x":1,"x":2}', '{"outer":{"x":1,"x":2}}'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'manifest.json'
                path.write_text(text)
                with self.assertRaisesRegex(ValueError, 'Duplicate'):
                    subject.read(path)

    def test_nonobject_and_nonfinite_json_reject(self):
        for text in ('[]', 'null', 'true', '{"x":NaN}', '{"x":Infinity}'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'manifest.json'
                path.write_text(text)
                with self.assertRaises(ValueError):
                    subject.read(path)

    def test_invalid_inventory_names_reject_before_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('/absolute', '../outside', 'a/../b', './a', 'a//b', 'a/', r'a\b'):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'path'):
                    subject.inventory(tmp, {name: '0' * 64}, set())

    def test_special_unlisted_member_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'ordinary').write_bytes(b'checked')
            os.mkfifo(root / 'not-a-regular-file')
            with self.assertRaisesRegex(ValueError, 'Nonregular'):
                subject.inventory(root, {'ordinary': subject.sha(root / 'ordinary')}, set())

    def test_nonregular_manifest_rejects_without_opening_fifo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'manifest.json'
            os.mkfifo(path)
            with self.assertRaisesRegex(ValueError, 'Invalid bounded manifest'):
                subject.read(path)


def actual_campaign(archive: Path, output: Path) -> bool:
    """Run mutations on the real archived output and record original identity."""
    output.mkdir(parents=True, exist_ok=False)
    before = subject.sha(archive / 'bundle.json')
    manifest = subject.read(archive / 'bundle.json')
    subject.validated_bundle(archive)
    started = time.monotonic()
    rows = []

    class ActualArchive(unittest.TestCase):
        def setUp(self):
            self.tmp = tempfile.TemporaryDirectory(prefix='lemma-tci-admission-')
            self.root = Path(self.tmp.name) / 'archive'
            shutil.copytree(archive, self.root, copy_function=os.link)
            self.manifest = subject.read(self.root / 'bundle.json')
            self.addCleanup(self.tmp.cleanup)

        def put(self, name, value):
            path = self.root / name
            temporary = path.with_name(path.name + '.new-control')
            temporary.write_text(json.dumps(value, indent=2) + '\n')
            temporary.replace(path)
            return subject.sha(path)

        def file(self, name, data):
            path = self.root / name
            temporary = path.with_name(path.name + '.new-control')
            temporary.write_bytes(data)
            temporary.replace(path)

        def guest(self, kind, change, role='notebook'):
            entry = self.manifest['workloads'][role]
            name = entry[kind]['path']
            data = subject.read(self.root / name)
            change(data)
            digest = self.put(name, data)
            self.manifest['files'][name] = digest
            entry[kind]['sha256'] = digest
            if kind == 'provenance':
                self.guest('build', lambda report: report.update(provenance_sha256=digest), role)

        def runtime(self, kind, change):
            name = 'runtime-source/' + kind
            data = subject.read(self.root / name)
            change(data)
            digest = self.put(name, data)
            self.manifest['files'][name] = digest
            admission = subject.read(self.root / 'runtime-source/runtime.json')
            admission['files'][kind] = digest
            if kind == 'original-build.json':
                admission['original_build']['sha256'] = digest
            elif kind == 'source-inputs.json':
                build = subject.read(self.root / 'runtime-source/original-build.json')
                build.update(source_closure_sha256=digest, source_file_count=len(data))
                build_digest = self.put('runtime-source/original-build.json', build)
                self.manifest['files']['runtime-source/original-build.json'] = build_digest
                admission['files']['original-build.json'] = build_digest
                admission['original_build']['sha256'] = build_digest
            digest = self.put('runtime-source/runtime.json', admission)
            self.manifest['files']['runtime-source/runtime.json'] = digest
            self.manifest['runtime_admission_sha256'] = digest

        def reject(self, case, mutate, reason=None):
            mutate()
            self.put('bundle.json', self.manifest)
            try:
                subject.validated_bundle(self.root)
            except (ValueError, RuntimeError, OSError, KeyError) as error:
                if reason is not None:
                    self.assertRegex(str(error), reason)
                rows.append({'case': case, 'result': 'REJECTED', 'reason': str(error)})
            else:
                rows.append({'case': case, 'result': 'INCORRECTLY_ACCEPTED'})
                self.fail(case + ' unexpectedly admitted')

        def test_actual_unmodified_archive_is_admitted(self):
            directory, files = subject.validated_bundle(self.root)
            self.assertEqual(directory, self.root)
            self.assertEqual(files['bundle.json'], before)
            self.assertEqual(server.validated_bundle(self.root), (directory, files))
            rows.append({'case': 'unchanged actual produced archive', 'result': 'ADMITTED', 'files': len(files)})

        def test_outer_corruption(self):
            cases = ('changed', 'missing', 'unlisted', 'file-symlink', 'directory-symlink', 'parent-symlink', 'duplicate-root', 'duplicate-nested')
            for case in cases:
                # A fresh independently restored clone per subcase.
                with self.subTest(case=case):
                    self.tearDown()
                    self.tmp.cleanup()
                    self.setUp()
                    def mutate():
                        if case == 'changed': self.file('worker.js', b'changed')
                        elif case == 'missing': (self.root / 'worker.js').unlink()
                        elif case == 'unlisted': (self.root / 'unexpected').write_bytes(b'x')
                        elif case == 'file-symlink':
                            (self.root / 'worker.js').unlink(); (self.root / 'worker.js').symlink_to(archive / 'worker.js')
                        elif case == 'directory-symlink':
                            shutil.rmtree(self.root / 'guest-source'); (self.root / 'guest-source').symlink_to(archive / 'guest-source', target_is_directory=True)
                        elif case == 'parent-symlink':
                            link = self.root.parent / 'linked-parent'; link.symlink_to(self.root, target_is_directory=True)
                            self.root = link
                    if case.startswith('duplicate-'):
                        text = (self.root / 'bundle.json').read_text()
                        duplicate = '"schema":"bad",' if case == 'duplicate-root' else '"factory":{},'
                        marker = '{' if case == 'duplicate-root' else '"runtime": {'
                        self.file('bundle.json', text.replace(marker, marker + duplicate, 1).encode())
                        with self.assertRaisesRegex(ValueError, 'Duplicate'):
                            subject.validated_bundle(self.root)
                        rows.append({'case': case, 'result': 'REJECTED', 'reason': 'duplicate JSON member'})
                    else: self.reject(case, mutate)

        def test_runtime_production_bindings(self):
            changes = {
                'runtime build unknown schema': ('schema', 'unknown/999'),
                'runtime build failed': ('result', 'FAIL'),
                'runtime build failed exit': ('exit_code', 1),
                'runtime boolean exit': ('exit_code', False),
                'runtime floating exit': ('exit_code', 0.0),
                'runtime source count': ('source_file_count', 1),
                'runtime floating source count': ('source_file_count', 43245.0),
                'runtime unknown output': ('outputs', {'unproduced.wasm': {}}),
            }
            for case, (key, value) in changes.items():
                with self.subTest(case=case):
                    self.tmp.cleanup(); self.setUp()
                    self.reject(case, lambda: self.runtime('original-build.json', lambda d: d.update({key: value})))

        def test_cpu_stop_feature_requires_bound_runtime(self):
            self.reject('unbound CPU stop acknowledgement',
                lambda: self.manifest.update(stop_boundary_contract='unknown'), 'CPU stop acknowledgement')

        def test_cpu_stop_production_contract_cannot_be_invented(self):
            self.reject('invented runtime CPU stop contract',
                lambda: self.runtime('original-build.json', lambda d: d.update(stop_boundary_contract='unknown')),
                'CPU stop observation')

        def test_support_report_contract_requires_its_actual_implementation(self):
            self.reject('unknown support contract', lambda: self.manifest.update(support_report_contract='unknown'), 'Unknown support report contract')
            self.tmp.cleanup(); self.setUp()
            def missing():
                self.manifest['support_report_contract']='lemma-client-support-report/1'
                if 'diagnostics.js' in self.manifest['files']:
                    del self.manifest['files']['diagnostics.js']
                    (self.root/'diagnostics.js').unlink()
            self.reject('support contract without implementation', missing, 'Missing support report implementation')

        def test_runtime_wasm_bytes_and_source_bindings(self):
            self.reject('wrong actual Wasm output bytes', lambda: self.runtime('original-build.json', lambda d: d['outputs']['qemu-system-riscv64.wasm'].update(bytes=1)), 'runtime output|PCM compiled output differs')

        def test_control_source_digest_cannot_be_relabelled(self):
            self.reject('control source ancestry changed', lambda: self.runtime('source-inputs.json', lambda d: d.update({'hw/riscv/lemma_browser_control.inc.c': '0' * 64})))

        def test_guest_production_bindings(self):
            cases = [
                ('build', 'schema_version', 99), ('build', 'configuration', 'wrong'),
                ('build', 'stage', 'user'), ('build', 'optimization', 'O0'),
                ('build', 'provenance_sha256', '0' * 64),
                ('audit', 'configuration', 'wrong'), ('audit', 'status', 'FAIL'),
                ('audit', 'image_sha256', '0' * 64), ('audit', 'source_commit', '0' * 40),
                ('provenance', 'configuration', 'wrong'), ('provenance', 'source_commit', '0' * 40),
                ('provenance', 'source_inputs', {}), ('provenance', 'lean_source_realization', {}),
            ]
            for kind, key, value in cases:
                with self.subTest(kind=kind, key=key):
                    self.tmp.cleanup(); self.setUp()
                    self.reject(kind + '/' + key, lambda: self.guest(kind, lambda d: d.update({key: value})))

        def test_guest_payload_pins_survive_rehashed_manifest(self):
            for artifact in ('image.elf', 'platform.dtb', 'descriptor.bin'):
                with self.subTest(artifact=artifact):
                    self.tmp.cleanup(); self.setUp()
                    self.reject('build payload pin ' + artifact, lambda: self.guest('build', lambda d: d['artifacts'].update({artifact: '0' * 64})), 'production artifact')

        def test_workbook_role_and_source_admission(self):
            self.reject('parameterized relabelled ordinary', lambda: self.manifest.update(multimodal_workbook='ordinary'), 'qualification')

        def test_entry_cannot_alias_other_role(self):
            self.reject('initializer aliases notebook', lambda: self.manifest['workloads'].update(initializer=self.manifest['workloads']['notebook']), 'Unbound guest')

        def test_required_contract_cannot_be_elided_from_all_manifests(self):
            def mutate():
                name = 'docs/contracts/007-converter-v1.html'
                del self.manifest['guest_sources'][name]
                del self.manifest['files']['guest-source/' + name]
                (self.root / 'guest-source' / name).unlink()
                for role in ('notebook', 'initializer'):
                    self.guest('provenance', lambda d: d['source_inputs'].pop(name), role)
            self.reject('required current contract elided coherently', mutate, 'Missing required multimodal dependency')

        def test_derived_ui_adapter_is_exact_source_plus_declared_suffix(self):
            def mutate():
                self.file('app.js', (self.root / 'app.js').read_bytes() + b'\n// unrecorded transformation\n')
                self.manifest['files']['app.js'] = subject.sha(self.root / 'app.js')
            self.reject('rehashed unknown UI transformation', mutate, 'UI transport adapter')

        def test_cli_dispatch_rejects_unadmitted_engine_options(self):
            base = [sys.executable, str(ROOT / 'scripts/lemmasim'), 'browser-build',
                    '--engine', 'qemu-tci', '--wasm-build', str(archive / 'runtime-source'),
                    '--output-dir', str(self.root / 'must-not-be-created')]
            for options in ([], ['--reuse-wasm'], ['--reuse-wasm', '--guest-bundle', str(archive), '--profile', 'lemma-silicon-dev/0.3.0']):
                with self.subTest(options=options):
                    completed = subprocess.run(base + options, capture_output=True, text=True, timeout=20)
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertIn('FAIL:', completed.stderr)
                    self.assertFalse((self.root / 'must-not-be-created').exists())
                    rows.append({'case': 'CLI rejects ' + repr(options), 'result': 'REJECTED', 'reason': completed.stderr.strip()})

        def test_runtime_unknown_file_even_with_hash_inventory(self):
            def mutate():
                self.file('runtime-source/unproduced.c', b'no producer')
                admission = subject.read(self.root / 'runtime-source/runtime.json')
                digest = subject.sha(self.root / 'runtime-source/unproduced.c')
                admission['files']['unproduced.c'] = digest
                self.manifest['files']['runtime-source/unproduced.c'] = digest
                digest = self.put('runtime-source/runtime.json', admission)
                self.manifest['files']['runtime-source/runtime.json'] = digest
                self.manifest['runtime_admission_sha256'] = digest
            self.reject('runtime unknown inventoried source', mutate, 'runtime closure|Unknown/incomplete PCM runtime archive')

        def test_runtime_cannot_claim_a_different_board_binding(self):
            def mutate():
                admission = subject.read(self.root / 'runtime-source/runtime.json')
                admission['admission_inputs']['sim/profiles/lemma-silicon-dev-0.14.0.json'] = '0' * 64
                digest = self.put('runtime-source/runtime.json', admission)
                self.manifest['files']['runtime-source/runtime.json'] = digest
                self.manifest['runtime_admission_sha256'] = digest
            self.reject('runtime and guest profile mismatch', mutate, 'board bindings')

        def test_packaging_bridge_cannot_be_rehashed_independently(self):
            def mutate():
                name = 'sim/browser/tci/worker.mjs'
                self.file('packaging-source/' + name, b'changed source')
                digest = subject.sha(self.root / 'packaging-source' / name)
                self.manifest['files']['packaging-source/' + name] = digest
                self.manifest['packaging_inputs'][name] = digest
            self.reject('packaged worker differs from source', mutate, 'packaged bridge input')

        def test_new_schema_cannot_omit_packaging_or_ui_source_closure(self):
            for key, reason in (('packaging_inputs', 'Missing packaging source closure'),
                                ('ui_transport_adapter', 'Missing UI source closure')):
                with self.subTest(key=key):
                    self.tmp.cleanup(); self.setUp()
                    self.reject('missing required ' + key, lambda: self.manifest.pop(key), reason)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ManifestParsing)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(ActualArchive))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    after = subject.sha(archive / 'bundle.json')
    if after != before: raise RuntimeError('Original produced archive changed')
    report = {'schema': 'lemma-browser-tci-actual-archive-negatives/1',
              'result': 'PASS' if result.wasSuccessful() else 'FAIL',
              'archive': str(archive), 'original_bundle_sha256': before,
              'validator_sha256': subject.sha(Path(subject.__file__)),
              'scope': 'Actual produced archive admission and corruption controls; no new target compilation, browser execution, P1/P2 or physical claim',
              'seconds': time.monotonic() - started, 'tests': result.testsRun, 'cases': rows}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return result.wasSuccessful()


def pcm_runtime_campaign(runtime: Path, output: Path) -> bool:
    """Consequential corruption checks over an actual one-object producer."""
    output.mkdir(parents=True, exist_ok=False)
    original = subject.sha(runtime / 'runtime.json')
    _, admitted = subject.retained_runtime(runtime)
    if admitted['schema'] != subject.RUNTIME_SCHEMA_WITH_PCM:
        raise ValueError('Actual admitted PCM runtime required')
    began = time.monotonic()
    cases = []
    def exercise(label, target, change):
        with tempfile.TemporaryDirectory(prefix='lemma-pcm-admission-', dir=output) as tmp:
            clone = Path(tmp) / 'runtime'
            shutil.copytree(runtime, clone, copy_function=os.link)
            manifest = subject.read(clone / 'runtime.json')
            path = clone / target
            body = subject.read(path)
            change(body)
            temporary = path.with_suffix('.replace')
            temporary.write_text(json.dumps(body, indent=2) + '\n')
            temporary.replace(path)  # Never mutate original hard-linked bytes.
            if target != 'runtime.json':
                manifest['files'][target] = subject.sha(path)
                if target == 'original-build.json':
                    manifest['original_build']['sha256'] = subject.sha(path)
                temporary = clone / 'manifest.replace'
                temporary.write_text(json.dumps(manifest, indent=2) + '\n')
                temporary.replace(clone / 'runtime.json')
            try:
                subject.retained_runtime(clone)
            except ValueError as error:
                cases.append({'case':label,'result':'REJECTED','reason':str(error)})
            else:
                cases.append({'case':label,'result':'UNEXPECTED_ACCEPT'})
    exercise('unknown execution binding', 'runtime.json', lambda x:x.update(execution_binding='full-integrated16'))
    exercise('controller ABI downgrade', 'runtime.json', lambda x:x.update(multimodal_controller_abi=1))
    exercise('controller contract downgrade', 'runtime.json', lambda x:x.update(controller_contract='lemma-multimodal-converter/1'))
    exercise('unknown CPU stop contract', 'runtime.json', lambda x:x.update(stop_boundary_contract='unknown'))
    exercise('invented producer stop contract', 'original-build.json', lambda x:x.update(stop_boundary_contract='unknown'))
    if admitted.get('stop_boundary_contract') is not None:
        exercise('missing CPU stop declaration', 'runtime.json', lambda x:x.pop('stop_boundary_contract'))
        exercise('unbound actual CPU stop bridge', 'original-build.json',
                 lambda x:x['inputs'].update({'tooling/lemmasim/tci/lemma_browser_control.inc.c':'0'*64}))
    exercise('two fresh objects claimed', 'original-build.json', lambda x:x.update(fresh_object_count=2))
    exercise('boolean object count', 'original-build.json', lambda x:x.update(fresh_object_count=True))
    exercise('missing dependency closure', 'original-build.json', lambda x:x.update(dependency_affected_objects=[]))
    exercise('floating source count', 'original-build.json', lambda x:x.update(source_file_count=float(x['source_file_count'])))
    exercise('unrelated source overlay', 'original-build.json', lambda x:x['changed_sources'].update({'tcg/tci.c':{'before':'0'*64,'after':'1'*64}}))
    exercise('forged observed helper route', 'runtime.json', lambda x:x.update(direct_helpers=not x['direct_helpers']))
    exercise('recursive predecessor', 'predecessor/runtime.json', lambda x:x.update(schema=subject.RUNTIME_SCHEMA_WITH_PCM))
    exercise('unknown compiler command', 'commands.json', lambda x:x['compile'][0].update(output='uncompiled-object.o'))
    exercise('wrong actual object size', 'original-build.json', lambda x:next(v for k,v in x['fresh_object_inputs'].items() if k.endswith('/multimodal.o')).update(bytes=1))
    if subject.sha(runtime / 'runtime.json') != original:
        raise RuntimeError('Original admitted runtime changed')
    passed = all(x['result']=='REJECTED' for x in cases)
    report = {'schema':'lemma-browser-pcm-runtime-negatives/1','status':'PASS' if passed else 'FAIL',
        'runtime':str(runtime),'runtime_sha256':original,'cases':cases,
        'seconds':time.monotonic()-began,'validator_sha256':subject.sha(Path(subject.__file__)),
        'scope':'Actual admitted compiler output and rehashed metadata corruption controls; no fresh compilation or guest/browser execution.'}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'cases':len(cases),'seconds':report['seconds']}))
    return passed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    selected=parser.add_mutually_exclusive_group(required=True)
    selected.add_argument('--archive', type=Path)
    selected.add_argument('--runtime', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    passed = pcm_runtime_campaign(args.runtime.absolute(),args.output_dir.absolute()) if args.runtime else actual_campaign(args.archive.absolute(), args.output_dir.absolute())
    raise SystemExit(0 if passed else 1)
