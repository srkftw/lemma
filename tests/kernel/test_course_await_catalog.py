"""Exact new four-image course wait deployment; no machine boot claim."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from audit_kernel import image_specs,kernel_contract,software_deployment_fields,validate_user_image_catalog
from build_kernel import configuration_roots,managed_policy,user_module_closure
from silicon_profile import configuration_profile
from silicon_guest_bundle import development_configuration
from course_await_deployment import library_source_allowed
from core0_common import Core0Error

class CourseAwaitCatalog(unittest.TestCase):
    def test_literal_roles_profiles_roots_and_durable_predecessor_remain(self):
        expected=[('store',1,'Lemma.Services.Store.ServerAwait','Lemma.Services.Store.ServerAwait.main','store-server'),
          ('notebook',2,'Lemma.Applications.Notebook','Lemma.Applications.Notebook.mainArrayBulk','notebook'),
          ('arithmetic',3,'Lemma.Services.Arithmetic.ServerV5','Lemma.Services.Arithmetic.ServerV5.main','arithmetic-server'),
          ('course',4,'Lemma.Courses.PackageInstaller','Lemma.Courses.PackageInstaller.mainAwait','course-installer')]
        deployment={'contract_version':'lemma-course-mounted-await-bulk-deployment-v1',
          'silicon_profile':'lemma-silicon-dev/0.3.0','user_profiles':{'store':'core0-user-v0.1',
            'notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.5','course':'core0-user-v0.1'}}
        for config,boot in (('lemmasim-silicon-course-await-bulk-notebook','siliconCourseAwaitBoot'),
                            ('lemmasim-silicon-course-await-bulk-initialize','siliconCourseAwaitInitializeMedium')):
            rows=list(image_specs(config))
            self.assertEqual([(r['key'],r['id'],r['module'],r['source'],r['boot_role']) for r in rows],expected)
            self.assertEqual(configuration_profile(config),'lemma-silicon-dev/0.3.0')
            self.assertEqual(kernel_contract(config),'core0-kernel-v0.4')
            self.assertEqual(configuration_roots(config)['kernel'][0][0],'Lemma.Platform.LemmaSim.NotebookKernel.'+boot)
            self.assertEqual(managed_policy(config),'lemma-notebook-arithmetic-v1')
            self.assertEqual(software_deployment_fields(config),{'software_deployment':deployment})
            value={'schema_version':1,'contract_version':'lemma-user-image-catalog-v1','configuration':config,
              'stage':'supervisor','image_count':4,'images':rows,'managed_policy':'lemma-notebook-arithmetic-v1',
              'software_deployment':deployment}
            validate_user_image_catalog(value)
            for bad in (rows[:3],rows[:2]+[rows[3],rows[2]],
                        [{**rows[0],'module':'Lemma.Services.Store.Server','source':'Lemma.Services.Store.Server.courseMain'}]+rows[1:],
                        rows[:3]+[{**rows[3],'source':'Lemma.Courses.PackageInstaller.main'}],
                        rows[:3]+[{**rows[3],'boot_role':'arithmetic-server'}]):
                with self.assertRaises(Core0Error):validate_user_image_catalog({**value,'images':bad})
        self.assertEqual(image_specs('lemmasim-silicon-course-bulk-notebook')[0]['source'],'Lemma.Services.Store.Server.courseMain')
        self.assertEqual(image_specs('lemmasim-silicon-course-bulk-notebook')[3]['source'],'Lemma.Courses.PackageInstaller.main')

    def test_only_new_store_root_can_borrow_library_not_executable_entries(self):
        image=image_specs('lemmasim-silicon-course-await-bulk-notebook')[0]
        self.assertTrue(library_source_allowed('user','Lemma.Services.Store.Server',image))
        self.assertTrue(library_source_allowed('user','Lemma.Services.Store.Server.courseService',image))
        self.assertTrue(library_source_allowed('user','Lemma.Services.Store.Server.courseApplication',image))
        for source in ('Lemma.Services.Store.Server.main','Lemma.Services.Store.Server.step',
                       'Lemma.Services.Store.Server.courseMain','Lemma.Services.Store.Server.courseStep'):
            self.assertFalse(library_source_allowed('user',source,image))
        for bad in ({**image,'key':'notebook'},{**image,'module':'Lemma.Services.Store.Server'},
                    {**image,'source':'Lemma.Services.Store.Server.main'}):
            self.assertFalse(library_source_allowed('user','Lemma.Services.Store.Server.courseService',bad))
        self.assertFalse(library_source_allowed('kernel','Lemma.Services.Store.Server.courseService',image))

    def test_raw_installer_is_exact_developer_laboratory_only(self):
        for workload,config in (('notebook','lemmasim-silicon-course-await-bulk-notebook'),
                               ('initializer','lemmasim-silicon-course-await-bulk-initialize')):
            for mode in ('developer','laboratory'):
                self.assertEqual(development_configuration('lemma-silicon-dev/0.3.0',workload,config,mode),config)
            for profile,mode in (('lemma-silicon-dev/0.3.0','student'),('lemma-silicon-dev/0.13.0','developer')):
                with self.assertRaises(ValueError):development_configuration(profile,workload,config,mode)
        for unknown in ('lemmasim-silicon-course-await-notebook','lemmasim-silicon-course-await-bulk-any-development'):
            with self.assertRaises(Core0Error):configuration_roots(unknown)

    def test_source_closure_borrows_only_exact_waiter_store_and_checks_nested_imports(self):
        def source(root,module,text=''):
            path=root/(module.replace('.','/')+'.lean')
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text+'\n')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source(root,'Lemma.Services.Store.Engine')
            source(root,'Lemma.Services.Store.Server','import Lemma.Services.Store.Engine')
            source(root,'Lemma.Services.Store.ServerAwait','import Lemma.Services.Store.Server')
            for config in ('lemmasim-silicon-course-await-bulk-notebook',
                           'lemmasim-silicon-course-await-bulk-initialize'):
                image=image_specs(config)[0]
                self.assertEqual(set(user_module_closure(root,image,config)),{
                  'Lemma/Services/Store/ServerAwait.lean','Lemma/Services/Store/Server.lean',
                  'Lemma/Services/Store/Engine.lean'})
                for bad in ({**image,'key':'notebook'},{**image,'id':2},{**image,'id':True},
                            {**image,'source':'Lemma.Services.Store.Server.main'},
                            {**image,'source':'Lemma.Services.Store.ServerAwait.any'},
                            {**image,'boot_role':'notebook'}):
                    with self.assertRaisesRegex(Core0Error,'another executable module'):
                        user_module_closure(root,bad,config)
                for other in ('lemmasim-silicon-course-bulk-notebook','lemmasim-notebook','service-normal'):
                    with self.assertRaisesRegex(Core0Error,'another executable module'):
                        user_module_closure(root,image,other)
                for foreign,error in (
                    ('Lemma.Applications.Notebook','another executable module'),
                    ('Lemma.Services.Store.Server.Other','another executable module'),
                    ('Lemma.Services.Buffer.Server','another executable module'),
                    ('Lemma.Kernel.Memory.Frames','privileged/compiler code'),
                    ('Lemma.Compiler.Core0','privileged/compiler code'),
                    ('Lemma.Services.Store.Development.Unregistered','development code')):
                    source(root,foreign)
                    source(root,'Lemma.Services.Store.Engine','import '+foreign)
                    with self.assertRaisesRegex(Core0Error,error):
                        user_module_closure(root,image,config)
                    source(root,'Lemma.Services.Store.Engine')

if __name__=='__main__':unittest.main()
