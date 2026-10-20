"""Closed version selection; no guest execution or compiler success claim."""
from pathlib import Path
import importlib.machinery
import importlib.util
import os
import copy
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import school_deployment as school
import lemmasim_fast as fast
import multimodal_native_bundle as native
import school_target as target
from core0_common import Core0Error
loader=importlib.machinery.SourceFileLoader('school_selection_cli',str(ROOT/'scripts/lemmasim'))
spec=importlib.util.spec_from_loader(loader.name,loader);cli=importlib.util.module_from_spec(spec);loader.exec_module(cli)


class SchoolDeploymentSelection(unittest.TestCase):
    def test_legacy_exports_and_metadata_remain_exact(self):
        self.assertEqual(school.CONFIGURATIONS,(
            'lemmasim-silicon-school-notebook','lemmasim-silicon-school-initialize',
            'lemmasim-silicon-integrated-school-notebook','lemmasim-silicon-integrated-pcm-school-notebook'))
        expected={'contract_version':'lemma-school-notebook-deployment/2','notebook_version':23,
            'silicon_profile':'lemma-silicon-dev/0.14.0','machine_profile':'lemma-one-multimodal/0.2.0',
            'reader_contract':'lemma-course-reader-location/1','chooser_contract':'lemma-course-empty-selection-chooser/1',
            'stream_contract':'lemma-multimodal-converter/1','selection_contract':'lemma-school-course-selection/1',
            'submission_contract':'lemma-school-guest-submission/2','user_profiles':{
                'store':'core0-user-v0.2','notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.7','course':'core0-user-v0.1'}}
        self.assertEqual(school.software_deployment_for(school.FAST),expected)
        self.assertEqual(school.software_deployment_for(school.INTEGRATED),expected|{
            'silicon_profile':'lemma-silicon-dev/0.15.0','boot_image_contract':'lemma-product10-image-compatibility/1'})
        self.assertEqual(school.software_deployment_for(school.INTEGRATED_PCM),expected|{
            'contract_version':'lemma-school-notebook-deployment/3','silicon_profile':'lemma-silicon-dev/0.16.0',
            'boot_image_contract':'lemma-product10-image-compatibility/1','stream_contract':'lemma-multimodal-converter/2',
            'multimodal_service_version':3})

    def test_explicit_successor_has_closed_names_and_two_changed_roots(self):
        expected=('lemmasim-silicon-school24-notebook','lemmasim-silicon-school24-initialize',
                  'lemmasim-silicon-integrated-school24-notebook','lemmasim-silicon-integrated-pcm-school24-notebook')
        self.assertEqual(school.configurations_for(24),expected)
        for configuration in expected:
            roots=school.user_roots_for(configuration)
            self.assertEqual(school.version_for_configuration(configuration),24)
            deployment=school.software_deployment_for(configuration)
            self.assertEqual(deployment['contract_version'],'lemma-school-notebook-deployment/4')
            self.assertEqual(deployment['extension_contract'],'lemma-school-exact-reduction-advisory/1')
            self.assertEqual(deployment['assistance_event_format'],3)
            self.assertEqual(deployment['submission_contract'],'lemma-school-guest-submission/2')
            self.assertEqual(roots['notebook'],('Lemma.Applications.Notebook.mainMultimodalSchool24',2,'core0-user-v0.2'))
            self.assertEqual(roots['arithmetic'],('Lemma.Services.Arithmetic.ServerV9.main',3,'core0-user-v0.7'))
            self.assertEqual({key:roots[key] for key in ('store','course')},
                             {key:school.USER_ROOTS[key] for key in ('store','course')})

    def test_unknown_or_coerced_selection_rejects(self):
        for version in (None,True,23.0,'24',22,25,object()):
            with self.subTest(version=version),self.assertRaises(ValueError):school.configuration_for(version,'notebook')
        for role in ('initializer','arithmetic','main','../notebook',None):
            with self.subTest(role=role),self.assertRaises(ValueError):school.configuration_for(24,role)
        for configuration in ('lemmasim-silicon-school25-notebook',school.FAST+'-other','Lemma.Services.Arithmetic.ServerV9.main',None):
            with self.subTest(configuration=configuration),self.assertRaises(ValueError):school.user_roots_for(configuration)

    def test_returned_roots_cannot_change_shared_authority(self):
        roots=school.user_roots_for(school.configuration_for(24,'notebook'))
        roots['store']=('arbitrary',0,'other')
        self.assertEqual(school.user_roots_for(school.FAST),school.USER_ROOTS)
        self.assertEqual(school.user_roots_for(school.configuration_for(24,'notebook'))['store'],school.USER_ROOTS['store'])

    def test_integrated_ready_requires_actual_school_queue_for_both_versions(self):
        from check_integrated_boot import school_queue_ready
        ready=[(0x47c,15,8,9,0),(0x420,0,0,0,0)]
        for version in (23,24):
            for role in ('integrated','integrated-pcm'):
                configuration=school.configuration_for(version,role)
                self.assertFalse(school_queue_ready(configuration,ready))
                self.assertFalse(school_queue_ready(configuration,ready+[(0x731,2,512,262144,1)]))
                self.assertTrue(school_queue_ready(configuration,ready+[(0x731,2,512,262144,2)]))
        self.assertTrue(school_queue_ready('lemmasim-silicon-integrated-notebook',ready))

    def test_integrated_successor_ready_requires_exact_actual_v9_startup(self):
        from check_integrated_boot import school_arithmetic_ready
        ready=[(0x47c,15,8,9,0),(0x420,1,1,0,0),(0x731,2,512,262144,2)]
        exact=(0x739,1,0x0001000052444331,144,176)
        for role in ('integrated','integrated-pcm'):
            successor=school.configuration_for(24,role)
            self.assertFalse(school_arithmetic_ready(successor,ready))
            for column in range(len(exact)):
                changed=list(exact);changed[column]+=1
                self.assertFalse(school_arithmetic_ready(successor,ready+[tuple(changed)]))
            self.assertTrue(school_arithmetic_ready(successor,ready+[exact]))
            self.assertTrue(school_arithmetic_ready(school.configuration_for(23,role),ready))
        self.assertTrue(school_arithmetic_ready('lemmasim-silicon-integrated-notebook',ready))

    def test_shared_deployment_consumers_select_the_exact_versioned_tuple(self):
        from silicon_profile import configuration_profile
        from closure_deployment import software_deployment_for as closure_software
        from course_await_deployment import software_deployment_for as await_software
        from managed_records import recovery_store_profile_allowed,contract
        for version in (23,24):
            for configuration in school.configurations_for(version):
                expected=school.software_deployment_for(configuration)
                self.assertEqual(configuration_profile(configuration),expected['silicon_profile'])
                self.assertEqual(closure_software(configuration),expected)
                self.assertEqual(await_software(configuration),expected)
                unit={'configuration':configuration,'role':'user','image_key':'store',
                      'contract_version':'core0-user-v0.2','functions':[],'software_deployment':expected}
                self.assertTrue(recovery_store_profile_allowed(unit));self.assertIsNone(contract(unit))
                changed=copy.deepcopy(unit);changed['software_deployment']=school.software_deployment_for(
                    school.configuration_for(24 if version==23 else 23,'notebook'))
                with self.assertRaises(Core0Error):contract(changed)

    def test_native_pair_rejects_mixed_version_or_arbitrary_role(self):
        for version in (23,24):
            self.assertEqual(native.school_version_for_pair(native.school_pair(version)),version)
        for selected in (native.school_pair(24)|{'initializer':school.INITIALIZE},
                         native.school_pair(23)|{'arithmetic':'arbitrary'},
                         {'notebook':school.FAST},None):
            with self.subTest(selected=selected),self.assertRaises(ValueError):native.school_version_for_pair(selected)

    def test_successor_cli_scope_does_not_change_student_authority(self):
        base={'school_notebook_version':24,'profile':'lemma-silicon-dev/0.14.0',
              'command':'build','backend':'qemu','workload':'school-notebook',
              'school_deployment':True,'engine':'qemu-tci','workbook':'school','mode':'student'}
        with mock.patch.dict(os.environ,{},clear=True):
            for command in ('build','native-bundle-build','browser-build'):
                args=SimpleNamespace(**(base|{'command':command}));cli.select_school_notebook_version(args)
                self.assertEqual(args.mode,'student');self.assertEqual(dict(os.environ),{})
            for changes in ({'profile':'lemma-silicon-dev/0.16.0'},{'backend':'rtl'},
                            {'workload':'notebook'},{'command':'native-bundle-build','school_deployment':False},
                            {'command':'browser-build','workbook':'ordinary'},
                            {'command':'browser-build','engine':'rtl'},
                            {'checkpoint_binding':'native-mm2-logical2'},
                            {'checkpoint_binding':'native-logical2'},
                            {'school_notebook_version':True},{'command':'run'}):
                with self.subTest(changes=changes),self.assertRaises(cli.Failure):
                    cli.select_school_notebook_version(SimpleNamespace(**(base|changes)))
                self.assertEqual(dict(os.environ),{})

    def test_successor_cannot_inherit_legacy_checkpoint_admission(self):
        # Reject before loading any runtime or validating a candidate medium.
        for binding in (fast.MM2_CHECKPOINT_BINDING,fast.LOGICAL2_BINDING):
            with self.subTest(binding=binding),self.assertRaisesRegex(ValueError,'local-tool IPC continuation'):
                fast.validate_checkpoint_binding({'school_notebook_version':24,'checkpoint_binding':binding})
        self.assertFalse(fast.validate_checkpoint_binding({'school_notebook_version':24}))

    def test_preparation_selects_only_complete_versioned_pair(self):
        legacy=fast.workload_configurations('lemma-silicon-dev/0.14.0')
        successor=fast.workload_configurations('lemma-silicon-dev/0.14.0',24)
        self.assertEqual(legacy['school-notebook'],school.FAST)
        self.assertEqual(successor['school-notebook'],school.configuration_for(24,'notebook'))
        self.assertEqual(successor['school-initializer'],school.configuration_for(24,'initialize'))
        self.assertEqual({k:v for k,v in legacy.items() if not k.startswith('school-')},
                         {k:v for k,v in successor.items() if not k.startswith('school-')})
        with self.assertRaises(ValueError):fast.workload_configurations('lemma-silicon-dev/0.16.0',24)

    def test_source_catalog_cannot_retarget_or_borrow_sibling_executables(self):
        configuration=school.configuration_for(24,'notebook')
        source='Lemma.Services.Arithmetic.ServerV9.main'
        unit={'configuration':configuration,'software_deployment':school.software_deployment_for(configuration),
              'role':'user','image_key':'arithmetic','image_id':3,'contract_version':'core0-user-v0.7',
              'used_device_ops':[],'roots':[{'source':source,'id':1,'args':['u64']}],
              'functions':[{'source':source,'symbol':'main'},{'source':'Lemma.Services.Arithmetic.ServerV8.processCopied','symbol':'copied'}]}
        self.assertEqual(target.catalog(unit)[0],'arithmetic')
        for source in ('Lemma.Services.Arithmetic.ServerV8.main','Lemma.Services.Arithmetic.ServerV8.step',
                       'Lemma.Services.Arithmetic.ServerV8.put','Lemma.Services.Arithmetic.ServerV7.main',
                       'Lemma.Services.Arithmetic.ServerV7.pressureStep'):
            changed=copy.deepcopy(unit);changed['functions'][1]['source']=source
            with self.subTest(source=source),self.assertRaises(Core0Error):target.catalog(changed)
        for changes in ({'configuration':school.FAST,'software_deployment':school.software_deployment_for(school.FAST)},
                        {'image_id':1},{'contract_version':'core0-user-v0.2'},
                        {'used_device_ops':[{'stable_id':'device.mmio'}]},
                        {'roots':[{'source':'Lemma.Services.Arithmetic.ServerV8.main','id':1,'args':['u64']}]}):
            with self.subTest(changes=changes),self.assertRaises(Core0Error):target.catalog(unit|changes)

    def test_whole_V9_identity_keeps_checker_wire_and_closes_deployment_dispatch(self):
        import arithmetic_closure_identity as identity
        names=['ServerV9.main','ServerV9.step','ServerV9.processCopied','ServerV8.processCopied',
               'ServerV7.processCopied','ProtocolV9.evaluate','ProtocolV9.reply','ProtocolV9.serviceIdentity',
               'ReductionV1.calculate','ProtocolV7.reply','ProtocolV7.validateRequest','ProtocolV8.reply']
        rows=[{'source':'Lemma.Services.Arithmetic.'+name,'symbol':'symbol'+str(i)} for i,name in enumerate(names)]
        rows.append({'source':'Lemma.Multimodal.Parameterized.evaluate','symbol':'checker'})
        for configuration in school.configurations_for(24):
            unit={'configuration':configuration,'software_deployment':school.software_deployment_for(configuration),
                  'role':'user','image_key':'arithmetic','image_id':3,'contract_version':'core0-user-v0.7',
                  'functions':rows,'roots':[{'source':'Lemma.Services.Arithmetic.ServerV9.main','id':1,'args':['u64']}],
                  identity.FIELD:copy.deepcopy(identity.LOCAL_REDUCTION_REGISTRY)}
            self.assertEqual(identity.contract(unit)['parameterized'],identity.PARAMETERIZED_REGISTRY['parameterized'])
            with mock.patch('multimodal_target.validate',return_value='multimodal') as mm,\
                 mock.patch('integrated_target.validate',return_value='integrated') as integrated:
                expected='integrated' if configuration in school.ALL_INTEGRATED_CONFIGURATIONS else 'multimodal'
                self.assertEqual(identity.validate('unexecuted host-routing fixture',unit,optimized=False),expected)
                (integrated if expected=='integrated' else mm).assert_called_once()
                (mm if expected=='integrated' else integrated).assert_not_called()
            for changes in ({identity.FIELD:identity.PARAMETERIZED_REGISTRY}, {'image_id':2},
                            {'contract_version':'core0-user-v0.6'}, {'configuration':school.FAST},
                            {'software_deployment':school.software_deployment_for(school.FAST)},
                            {'roots':[{'source':'Lemma.Services.Arithmetic.ServerV8.main','id':1,'args':['u64']}]},
                            {'functions':rows+[{'source':'Lemma.Services.Arithmetic.ServerV8.main','symbol':'sibling'}]},
                            {'functions':[row for row in rows if row['source']!='Lemma.Services.Arithmetic.ReductionV1.calculate']}):
                with self.subTest(configuration=configuration,changes=changes),self.assertRaises(Core0Error):
                    identity.contract(unit|changes)


if __name__=='__main__':unittest.main()
