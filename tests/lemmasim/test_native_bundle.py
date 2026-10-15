"""Fail-closed package boundary fixtures; no guest-execution claim."""
import hashlib
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from silicon_guest_bundle import inventory, read_json, development_configuration, ARITHMETIC_LAB_CONFIGURATIONS, origin_destination, SCHEMA, SCHEMA_WITH_SOURCE_VERSIONS, SCHEMA_WITH_SOFTWARE_DEPLOYMENT, MANAGED_DEPLOYMENT, MANAGED_CONFIGURATIONS, SUMS_DEPLOYMENT, SUMS_CONFIGURATIONS, SOFTWARE_DEPLOYMENTS, bundle_configurations

class NativeBundleBoundary(unittest.TestCase):
    def test_fast_refresh_rejects_mixed_or_implicit_selection_before_output(self):
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'must-not-be-created'
            base=[str(root/'scripts/lemmasim'),'native-bundle-build',
                  '--base-bundle',str(Path(directory)/'nonexistent-base'),
                  '--output-dir',str(output)]
            for options,message in [
                (['--refresh-fast'],'Fast refresh requires canonical base'),
                (['--refresh-fast','--expected-fast-sha256','0'*64,'--rtl-build','unused'],
                 'Fast refresh requires canonical base'),
                (['--expected-fast-sha256','0'*64],'Expected fast identity requires --refresh-fast')]:
                result=subprocess.run(base+options,cwd=root,capture_output=True,text=True,timeout=20)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(message,result.stderr+result.stdout)
                self.assertFalse(output.exists())

    def test_versioned_managed_deployment_cannot_be_mixed_or_injected_into_legacy(self):
        manifest={'profile':'lemma-silicon-dev/0.3.0','schema':SCHEMA_WITH_SOFTWARE_DEPLOYMENT,
                  'software_deployment':{'contract_version':MANAGED_DEPLOYMENT,
                                         'configurations':dict(MANAGED_CONFIGURATIONS)}}
        self.assertEqual(bundle_configurations(manifest),MANAGED_CONFIGURATIONS)
        for role in ('notebook','initializer'):
            bad=copy.deepcopy(manifest)
            bad['software_deployment']['configurations'][role]='lemmasim-silicon-power-notebook'
            with self.assertRaises(ValueError):bundle_configurations(bad)
        for version in (SCHEMA,SCHEMA_WITH_SOURCE_VERSIONS):
            bad=copy.deepcopy(manifest);bad['schema']=version
            with self.assertRaises(ValueError):bundle_configurations(bad)
            del bad['software_deployment']
            self.assertEqual(bundle_configurations(bad),{'notebook':'lemmasim-silicon-power-notebook',
                                                        'initializer':'lemmasim-silicon-power-initialize'})
        for profile in ('lemma-silicon-dev/0.2.0','lemma-silicon-dev/0.4.0'):
            bad=copy.deepcopy(manifest);bad['profile']=profile
            with self.assertRaises(ValueError):bundle_configurations(bad)

    def test_managed_guest_override_is_exact_and_available_in_ordinary_modes(self):
        # Course installation carries an owned package buffer and is an
        # explicitly restricted deployment, rather than an ordinary notebook.
        course = {'lemmasim-silicon-course-bulk-notebook',
                  'lemmasim-silicon-course-bulk-initialize',
                  'lemmasim-silicon-course-await-bulk-notebook',
                  'lemmasim-silicon-course-await-bulk-initialize',
                  'lemmasim-silicon-package-closure-entry2-bulk-notebook',
                  'lemmasim-silicon-package-closure-entry2-bulk-initialize'}
        for role,configuration in [item for configurations in SOFTWARE_DEPLOYMENTS.values() for item in configurations.items()]:
            if configuration in course:
                continue
            for mode in ('student','developer','laboratory'):
                self.assertEqual(development_configuration('lemma-silicon-dev/0.3.0',role,configuration,mode),configuration)
            with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.3.0',role,configuration,None)
            other='initializer' if role=='notebook' else 'notebook'
            with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.3.0',other,configuration,'developer')
        with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.4.0','notebook',MANAGED_CONFIGURATIONS['notebook'],'developer')

    def test_course_installer_requires_its_exact_developer_roles(self):
        from silicon_guest_bundle import COURSE_CONFIGURATIONS
        expected = {'notebook':'lemmasim-silicon-course-bulk-notebook',
                    'initializer':'lemmasim-silicon-course-bulk-initialize'}
        self.assertEqual(COURSE_CONFIGURATIONS, expected)
        for role, configuration in expected.items():
            for mode in ('developer', 'laboratory'):
                self.assertEqual(development_configuration(
                    'lemma-silicon-dev/0.3.0', role, configuration, mode), configuration)
            for mode in ('student', None):
                with self.assertRaises(ValueError):
                    development_configuration('lemma-silicon-dev/0.3.0', role, configuration, mode)
            other = 'initializer' if role == 'notebook' else 'notebook'
            for profile, wrong_role, wrong_configuration in (
                    ('lemma-silicon-dev/0.2.0', role, configuration),
                    ('lemma-silicon-dev/0.4.0', role, configuration),
                    ('lemma-silicon-dev/0.3.0', other, configuration),
                    ('lemma-silicon-dev/0.3.0', role, configuration+'-invented')):
                with self.assertRaises(ValueError):
                    development_configuration(profile, wrong_role, wrong_configuration, 'developer')

    def test_mount_await_native_package_has_its_exact_distinct_pair(self):
        from silicon_guest_bundle import COURSE_AWAIT_CONFIGURATIONS,COURSE_AWAIT_DEPLOYMENT
        expected={'notebook':'lemmasim-silicon-course-await-bulk-notebook',
                  'initializer':'lemmasim-silicon-course-await-bulk-initialize'}
        self.assertEqual(COURSE_AWAIT_CONFIGURATIONS,expected)
        self.assertEqual(COURSE_AWAIT_DEPLOYMENT,'lemma-course-mounted-await-bulk-deployment-v1')
        manifest={'profile':'lemma-silicon-dev/0.3.0','schema':SCHEMA_WITH_SOFTWARE_DEPLOYMENT,
                  'software_deployment':{'contract_version':COURSE_AWAIT_DEPLOYMENT,'configurations':expected}}
        self.assertEqual(bundle_configurations(manifest),expected)
        for role,configuration in expected.items():
            for mode in ('developer','laboratory'):
                self.assertEqual(development_configuration('lemma-silicon-dev/0.3.0',role,configuration,mode),configuration)
            for mode in ('student',None):
                with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.3.0',role,configuration,mode)
            other='initializer' if role=='notebook' else 'notebook'
            with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.3.0',other,configuration,'developer')
            bad=copy.deepcopy(manifest);bad['software_deployment']['configurations'][role]=configuration.replace('-await','')
            with self.assertRaises(ValueError):bundle_configurations(bad)
        for field,value in (('profile','lemma-silicon-dev/0.2.0'),('schema',SCHEMA_WITH_SOURCE_VERSIONS)):
            bad=copy.deepcopy(manifest);bad[field]=value
            with self.assertRaises(ValueError):bundle_configurations(bad)

    def test_package_closure_owner_installer_pair_has_exact_mode_authority(self):
        from silicon_guest_bundle import PACKAGE_CLOSURE_CONFIGURATIONS, PACKAGE_CLOSURE_DEPLOYMENT
        expected = {'notebook': 'lemmasim-silicon-package-closure-entry2-bulk-notebook',
                    'initializer': 'lemmasim-silicon-package-closure-entry2-bulk-initialize'}
        self.assertEqual(PACKAGE_CLOSURE_CONFIGURATIONS, expected)
        self.assertEqual(PACKAGE_CLOSURE_DEPLOYMENT, 'lemma-package-closure-entry2-bulk-deployment-v1')
        manifest = {'profile': 'lemma-silicon-dev/0.3.0', 'schema': SCHEMA_WITH_SOFTWARE_DEPLOYMENT,
                    'software_deployment': {'contract_version': PACKAGE_CLOSURE_DEPLOYMENT,
                                            'configurations': dict(expected)}}
        self.assertEqual(bundle_configurations(manifest), expected)
        for role, configuration in expected.items():
            for mode in ('developer', 'laboratory'):
                with self.subTest(role=role, mode=mode):
                    self.assertEqual(development_configuration(
                        'lemma-silicon-dev/0.3.0', role, configuration, mode), configuration)
            for mode in ('student', None, 'Developer', 'debug', True):
                with self.subTest(role=role, rejected_mode=mode), self.assertRaises(ValueError):
                    development_configuration('lemma-silicon-dev/0.3.0', role, configuration, mode)
            other = 'initializer' if role == 'notebook' else 'notebook'
            for wrong_role in (other, 'course', None):
                for mode in ('developer', 'laboratory'):
                    with self.subTest(role=role, wrong_role=wrong_role, mode=mode), self.assertRaises(ValueError):
                        development_configuration('lemma-silicon-dev/0.3.0', wrong_role, configuration, mode)
            for profile in ('lemma-silicon-dev/0.2.0', 'lemma-silicon-dev/0.4.0', 'lemma-silicon-dev/0.13.0'):
                for mode in ('developer', 'laboratory'):
                    with self.subTest(role=role, profile=profile, mode=mode), self.assertRaises(ValueError):
                        development_configuration(profile, role, configuration, mode)
            for lookalike in (configuration + '-invented', configuration + ' ',
                              configuration.replace('-entry2-', '-entry3-'),
                              configuration.replace('-package-', '-packages-')):
                for mode in ('developer', 'laboratory'):
                    with self.subTest(role=role, lookalike=lookalike, mode=mode), self.assertRaises(ValueError):
                        development_configuration('lemma-silicon-dev/0.3.0', role, lookalike, mode)
            for wrong_configuration in (expected[other], configuration.replace('-package', ''), configuration + '-invented'):
                bad = copy.deepcopy(manifest)
                bad['software_deployment']['configurations'][role] = wrong_configuration
                with self.subTest(role=role, mixed_manifest=wrong_configuration), self.assertRaises(ValueError):
                    bundle_configurations(bad)
        for field, value in (('profile', 'lemma-silicon-dev/0.2.0'), ('schema', SCHEMA_WITH_SOURCE_VERSIONS)):
            bad = copy.deepcopy(manifest); bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                bundle_configurations(bad)

    def test_sums_deployment_does_not_relabel_the_prior_record_runtime(self):
        manifest={'profile':'lemma-silicon-dev/0.3.0','schema':SCHEMA_WITH_SOFTWARE_DEPLOYMENT,
                  'software_deployment':{'contract_version':SUMS_DEPLOYMENT,
                                         'configurations':dict(SUMS_CONFIGURATIONS)}}
        self.assertEqual(bundle_configurations(manifest),SUMS_CONFIGURATIONS)
        for role in ('notebook','initializer'):
            changed=copy.deepcopy(manifest)
            changed['software_deployment']['configurations'][role]=MANAGED_CONFIGURATIONS[role]
            with self.assertRaises(ValueError):bundle_configurations(changed)
        for invalid in (MANAGED_DEPLOYMENT,'lemma-managed-sums-deployment-v2',None):
            changed=copy.deepcopy(manifest);changed['software_deployment']['contract_version']=invalid
            with self.assertRaises(ValueError):bundle_configurations(changed)
        changed=copy.deepcopy(manifest);changed['software_deployment']['runtime']='implicit'
        with self.assertRaises(ValueError):bundle_configurations(changed)

    def test_bytes_pair_cannot_masquerade_as_sums_or_mix_roles(self):
        from silicon_guest_bundle import BYTES_DEPLOYMENT, BYTES_CONFIGURATIONS
        manifest={'profile':'lemma-silicon-dev/0.3.0','schema':SCHEMA_WITH_SOFTWARE_DEPLOYMENT,
                  'software_deployment':{'contract_version':BYTES_DEPLOYMENT,
                                         'configurations':dict(BYTES_CONFIGURATIONS)}}
        self.assertEqual(bundle_configurations(manifest),BYTES_CONFIGURATIONS)
        for role in BYTES_CONFIGURATIONS:
            changed=copy.deepcopy(manifest)
            changed['software_deployment']['configurations'][role]=SUMS_CONFIGURATIONS[role]
            with self.assertRaises(ValueError):bundle_configurations(changed)
        changed=copy.deepcopy(manifest);changed['software_deployment']['contract_version']=SUMS_DEPLOYMENT
        with self.assertRaises(ValueError):bundle_configurations(changed)

    def test_string_pair_keeps_its_own_authority_and_oom_is_laboratory_only(self):
        manifest={'profile':'lemma-silicon-dev/0.3.0','schema':SCHEMA_WITH_SOFTWARE_DEPLOYMENT,
                  'software_deployment':{'contract_version':'lemma-managed-string-bulk-deployment-v1',
                    'configurations':{'notebook':'lemmasim-silicon-string-bulk-notebook',
                                      'initializer':'lemmasim-silicon-string-bulk-initialize'}}}
        self.assertEqual(bundle_configurations(manifest),manifest['software_deployment']['configurations'])
        for role in ('notebook','initializer'):
            for family in ('array','bytes','sums'):
                changed=copy.deepcopy(manifest)
                suffix='notebook' if role=='notebook' else 'initialize'
                changed['software_deployment']['configurations'][role]=f'lemmasim-silicon-{family}-bulk-{suffix}'
                with self.assertRaises(ValueError):bundle_configurations(changed)
        changed=copy.deepcopy(manifest)
        changed['software_deployment']['contract_version']='lemma-managed-array-bulk-deployment-v1'
        with self.assertRaises(ValueError):bundle_configurations(changed)
        cfg='lemmasim-silicon-string-arithmetic-oom-development'
        self.assertEqual(development_configuration('lemma-silicon-dev/0.3.0','notebook',cfg,'laboratory'),cfg)
        for mode in ('student','developer',None):
            with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.3.0','notebook',cfg,mode)

    def test_archived_backends_and_new_guests_keep_exact_source_versions(self):
        path='/same/consumed/source.lean';old='a'*64;new='b'*64
        manifest={'schema':SCHEMA_WITH_SOURCE_VERSIONS,'origins':{path:{old:'old',new:'new'}},
                  'files':{'old':{'sha256':old},'new':{'sha256':new}}}
        self.assertEqual(origin_destination(manifest,path,old),'old')
        self.assertEqual(origin_destination(manifest,path,new),'new')
        for digest in ('c'*64,'',None):
            with self.assertRaises(ValueError):origin_destination(manifest,path,digest)
        manifest['origins'][path]={old:'new'}
        with self.assertRaises(ValueError):origin_destination(manifest,path,old)
        manifest['origins'][path]='old'
        with self.assertRaises(ValueError):origin_destination(manifest,path,old)
        manifest['schema']=SCHEMA
        self.assertEqual(origin_destination(manifest,path,old),'old')
        with self.assertRaises(ValueError):origin_destination(manifest,path,new)

    def test_closure_pair_and_failures_have_separate_exact_authority(self):
        from silicon_guest_bundle import CLOSURE_DEPLOYMENT, CLOSURE_CONFIGURATIONS
        expected={'notebook':'lemmasim-silicon-closure-bulk-notebook',
                  'initializer':'lemmasim-silicon-closure-bulk-initialize'}
        self.assertEqual(CLOSURE_CONFIGURATIONS,expected)
        manifest={'profile':'lemma-silicon-dev/0.3.0','schema':SCHEMA_WITH_SOFTWARE_DEPLOYMENT,
                  'software_deployment':{'contract_version':CLOSURE_DEPLOYMENT,
                                         'configurations':dict(expected)}}
        self.assertEqual(bundle_configurations(manifest),expected)
        for role in expected:
            for family in ('string','array','sums','course'):
                bad=copy.deepcopy(manifest)
                suffix='notebook' if role=='notebook' else 'initialize'
                bad['software_deployment']['configurations'][role]=f'lemmasim-silicon-{family}-bulk-{suffix}'
                with self.assertRaises(ValueError):bundle_configurations(bad)
        for kind in ('oom','fault'):
            configuration=f'lemmasim-silicon-closure-arithmetic-{kind}-development'
            self.assertIn(configuration,ARITHMETIC_LAB_CONFIGURATIONS)
            self.assertEqual(development_configuration('lemma-silicon-dev/0.3.0','notebook',configuration,'laboratory'),configuration)
            bad=copy.deepcopy(manifest);bad['software_deployment']['configurations']['notebook']=configuration
            with self.assertRaises(ValueError):bundle_configurations(bad)
            for mode in ('student','developer',None):
                with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.3.0','notebook',configuration,mode)

    def test_development_configuration_requires_exact_laboratory_admission(self):
        profile='lemma-silicon-dev/0.3.0'
        for configuration in ARITHMETIC_LAB_CONFIGURATIONS:
            self.assertEqual(development_configuration(profile,'notebook',configuration,'laboratory'),configuration)
            for mode in (None,'student','developer'):
                with self.assertRaises(ValueError):development_configuration(profile,'notebook',configuration,mode)
            with self.assertRaises(ValueError):development_configuration(profile,'initializer',configuration,'laboratory')
            with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.2.0','notebook',configuration,'laboratory')
        with self.assertRaises(ValueError):development_configuration(profile,'notebook','lemmasim-silicon-power-arithmetic-invented-development','laboratory')
        self.assertEqual(development_configuration(profile,'notebook','lemmasim-silicon-power-notebook','student'),'lemmasim-silicon-power-notebook')
    def test_inventory_rejects_missing_changed_unlisted_and_symlinked_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'opaque.bin';p.write_bytes(b'actual bytes')
            (root/'bundle.json').write_text('{}')
            m={'files':{'opaque.bin':{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':12,'executable':False}}}
            inventory(root,m)
            p.write_bytes(b'changedbytes')
            with self.assertRaises(ValueError):inventory(root,m)
            p.unlink();p.symlink_to('/dev/null')
            with self.assertRaises(ValueError):inventory(root,m)
            p.unlink();p.write_bytes(b'actual bytes');(root/'surprise.bin').write_bytes(b'x')
            with self.assertRaises(ValueError):inventory(root,m)
            (root/'surprise.bin').unlink();p.unlink()
            with self.assertRaises(ValueError):inventory(root,m)
    def test_metadata_rejects_duplicate_keys_empty_and_escaping_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'bundle.json';p.write_text('{"schema":1,"schema":2}')
            with self.assertRaises(ValueError):read_json(p)
            for m in ({'files':{}},{'files':{'../other':{}}},{'files':{'/absolute':{}}}):
                with self.assertRaises(ValueError):inventory(root,m)

if __name__=='__main__':unittest.main()
