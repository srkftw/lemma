"""Host-only closed-registry and multi-image provenance failure fixtures."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_kernel import (TASK_USER_IMAGES, TASK_FAULT_USER_IMAGES, image_specs, validate_user_image_catalog, validate_unit,
                          validate_user_primitive_catalog, validate_package_contract,
                          validate_package_payloads, validate_multi_commands, user_primitive_rows, audit_standalone_user,
                          validate_image_case_provenance, validate_image_attack_object, validate_user_attack_machine,
                          validate_machine, development_modules, CAPABILITY_USER_IMAGES, MANAGED_POLICY, IPC_USER_IMAGES, IPC_POLICY, managed_fields, validate_managed_provenance, validate_standalone_managed_provenance)
from build_kernel import CONTRACTS, LEAN_SOURCE_EXPRESSION
from build_core0 import LLC_ARGUMENTS, OPT_PASSES, STARTUP_ARGUMENTS
from core0_common import Core0Error


def catalog(configuration='tasks-development'):
    return {'schema_version':1, 'contract_version':'lemma-user-image-catalog-v1',
            'configuration':configuration,'stage':'supervisor','image_count':len(image_specs(configuration)),
            'images':copy.deepcopy(list(image_specs(configuration))), **managed_fields(configuration)}


def unit(key='compute',configuration='tasks-development'):
    image=next(row for row in image_specs(configuration) if row['key']==key)
    root={'id':1,'source':image['source'],'symbol':image['symbol_prefix']+'root','args':['u64']}
    return {'schema_version':2,'artifact_category':'development-user-unit','contract_version':CONTRACTS['user'],
            'configuration':configuration,'role':'user','image_key':key,'image_id':image['id'],
            'roots':[root],'functions':[{**{k:v for k,v in root.items() if k!='id'},'effects':[]}],
            'used_execution_ops':[],'used_device_ops':[],'used_loops':[],
            **({'startup_case':image['startup_case']} if configuration in {'tasks-fault-development','capabilities-development','ipc-development'} else {}),
            **managed_fields(configuration,image)}


def contract(configuration='tasks-development'):
    image={'entry':0x10000,'text_va':0x10000,'text_capacity':0xf000,'data_va':0x20000,
           'data_mem_bytes':4096,'stack_va':0x3fffc000,'stack_pages':2,'flags':0}
    return {'schema_version':2,'configuration':configuration,'startup_case':'normal','user_startup_case':'none',
            'contract_version':'lemma-boot-package-v1','magic':0x31474b50414d454c,'version':1,'image_count':len(image_specs(configuration)),
            'header_bytes':32,'descriptor_bytes':96,'offset_encoding':'generated-label-differences',
            'images':[{**image,'key':row['key'],'id':row['id'], **({'boot_role':row['boot_role']} if configuration in {'capabilities-development','ipc-development'} else {})} for row in image_specs(configuration)],
            **managed_fields(configuration)}


def packed_fixture(configuration='tasks-development'):
    count=len(image_specs(configuration))
    payloads=[(struct.pack('<II',i,i+10),struct.pack('<QQ',0,1)) for i in range(1,count+1)]
    data=bytearray(32+count*96)
    for index,(text,initialized) in enumerate(payloads):
        text_offset=len(data);data.extend(text);data_offset=len(data);data.extend(initialized)
        struct.pack_into('<12Q',data,32+index*96,index+1,0x10000,0x10000,text_offset,len(text),0x20000,
                         data_offset,len(initialized),4096,0x3fffc000,2,0)
    struct.pack_into('<4Q',data,0,0x31474b50414d454c,1,count,len(data))
    return bytes(data),payloads


class MultiImageAuditFailures(unittest.TestCase):
    def test_standalone_missing_evidence_removes_stale_pass_and_retains_failure(self):
        (ROOT/'build/user').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'build/user') as temporary:
            out=Path(temporary);(out/'audit.json').write_text('{"status":"PASS"}')
            with self.assertRaises((Core0Error,OSError)):
                audit_standalone_user(root=ROOT,output_dir=out)
            self.assertFalse((out/'audit.json').exists())
            self.assertEqual(json.loads((out/'audit-failure.json').read_text())['status'],'FAIL')

    def test_registry_rejects_reordering_path_escape_source_substitution_and_boolean_id(self):
        validate_user_image_catalog(catalog())
        bads=[]
        for field,value in [('directory','users/../compute'),('source',TASK_USER_IMAGES[1]['source']),
                            ('symbol_prefix','lemma_user_'),('id',True),('startup_case','supervisor-csr')]:
            bad=catalog();bad['images'][0][field]=value;bads.append(bad)
        bad=catalog();bad['images'].reverse();bads.append(bad)
        bad=catalog();bad['images']=[];bads.append(bad)
        for bad in bads:
            with self.assertRaises(Core0Error):validate_user_image_catalog(bad)

    def test_per_image_unit_rejects_peer_namespace_prefix_and_singleton_relabel(self):
        validate_unit(unit(),'user',configuration='tasks-development',image_key='compute')
        bads=[]
        for field,value in [('image_key','busy'),('image_id',2),('schema_version',1)]:
            bad=unit();bad[field]=value;bads.append(bad)
        bad=unit();bad['functions'][0]['symbol']='lemma_user_busy_root';bads.append(bad)
        bad=unit();bad['functions'].append({'source':'Lemma.User.Development.Tasks.Busy.tick',
                                         'symbol':'lemma_user_compute_foreign','args':[],'effects':[]});bads.append(bad)
        bad=unit();bad['functions'].append({'source':'_private.Lemma.User.Development.Tasks.Busy.0.Lemma.User.Development.Tasks.Busy.tick',
                                         'symbol':'lemma_user_compute_hidden','args':[],'effects':[]});bads.append(bad)
        for bad in bads:
            with self.assertRaises(Core0Error):validate_unit(bad,'user',configuration='tasks-development',image_key='compute')
        with self.assertRaises(Core0Error):validate_unit(unit(),'user',configuration='normal')
        with self.assertRaises(Core0Error):validate_unit(unit(),'user',configuration='tasks-development')

    def test_user_catalog_cannot_gain_privilege_or_attack_code(self):
        image=TASK_USER_IMAGES[0]
        good={'schema_version':1,'contract_version':'lemma-user-execution-v1','configuration':'tasks-development',
              'image_key':'compute','image_id':1,'startup_case':'none','symbols':user_primitive_rows('none')}
        validate_user_primitive_catalog(good,image)
        for field,value in [('image_id',2),('startup_case','supervisor-csr'),('symbols',user_primitive_rows('supervisor-csr'))]:
            bad=copy.deepcopy(good);bad[field]=value
            with self.assertRaises(Core0Error):validate_user_primitive_catalog(bad,image)
        bad=copy.deepcopy(good);bad['symbols'][0]['privilege']='S'
        with self.assertRaises(Core0Error):validate_user_primitive_catalog(bad,image)

    def test_package_binds_each_descriptor_and_every_payload_byte(self):
        validate_package_contract(contract(),configuration='tasks-development',catalog=catalog())
        raw,payloads=packed_fixture()
        self.assertEqual([x['id'] for x in validate_package_payloads(raw,contract(),payloads)],[1,2,3])
        mutations=[]
        for offset,value in [(32,2),(32+24,0),(32+96+24,320),(32+96+32,100000)]:
            bad=bytearray(raw);struct.pack_into('<Q',bad,offset,value);mutations.append(bytes(bad))
        bad=bytearray(raw);bad[-1]^=1;mutations.append(bytes(bad))
        bad=bytearray(raw)+b'\0';struct.pack_into('<Q',bad,24,len(bad));mutations.append(bytes(bad))
        for bad in mutations:
            with self.assertRaises(Core0Error):validate_package_payloads(bad,contract(),payloads)
        with self.assertRaises(Core0Error):validate_package_payloads(raw,contract(),payloads[:2])
        bad=contract();bad['images'][0]['id']=True
        with self.assertRaises(Core0Error):validate_package_contract(bad,configuration='tasks-development',catalog=catalog())

    def test_construction_rejects_wrong_cwd_foreign_object_missing_compile_and_modified_consumer(self):
        pin=json.loads((ROOT/'tooling/toolchain-lock.json').read_text())['tools'];image=TASK_USER_IMAGES[0]
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            out=Path(temporary);base=str(out.relative_to(ROOT));d='users/compute';(out/d).mkdir(parents=True)
            (out/'CatalogExport.lean').write_text('import Lemma.Compiler.KernelExport\n\n#lemma_export_user_catalog\n')
            (out/d/'Export.lean').write_text('import Lemma.User.Development.Tasks.Compute\nimport Lemma.Compiler.KernelExport\n\n#lemma_export_user_image "compute" [Lemma.User.Development.Tasks.Compute.main]\n')
            (out/'UserFilesExport.lean').write_text('import Lemma.Compiler.KernelExport\n\n#lemma_export_user_files "compute"\n')
            stores={'opt':pin['llvm']['store_path'],'llc':pin['llvm']['store_path'],'llvm-objcopy':pin['llvm']['store_path'],
                    'clang':pin['llvm']['outputs']['clang_unwrapped']['store_path'],'ld.lld':pin['lld']['store_path'],
                    'lake':pin['lean']['store_path']}
            def row(tool,args,cwd):return {'argv':[stores.get(tool,'/nix/store/host')+'/bin/'+tool,*args],'cwd':cwd,'returncode':0}
            rows=[row('nix',['build','--no-link','--print-out-paths','--impure','--expr',LEAN_SOURCE_EXPRESSION],'.'),
                  row('nix',['path-info','--json',pin['lean']['source_path']],'.')]
            rows += [row('lake',['env','lean',base+'/'+name],'.') for name in ['CatalogExport.lean',d+'/Export.lean','UserFilesExport.lean']]
            rows += [row('opt',['-S','-passes='+OPT_PASSES['O2'],'program.ll','-o','program.opt.ll'],base+'/'+d),
                     row('llc',[*LLC_ARGUMENTS,'-stack-size-section','-O2','program.opt.ll','-o','program.o'],base+'/'+d),
                     row('clang',[*STARTUP_ARGUMENTS,d+'/startup.S','-o',d+'/startup.o'],base),
                     row('ld.lld',['-m','elf64lriscv','--no-relax','-T',d+'/link.ld','-Map='+d+'/image.map',d+'/startup.o',d+'/program.o','-o',d+'/image.elf'],base),
                     row('llvm-objcopy',['-O','binary','--only-section=.text',d+'/image.elf',d+'/text.bin'],base),
                     row('llvm-objcopy',['-O','binary','--only-section=.data',d+'/image.elf',d+'/data.bin'],base)]
            args=dict(root=ROOT,output_dir=out,images=[image],optimization='O2',roles={},standalone=True)
            validate_multi_commands(rows,**args)
            # Same exact tool/root/object corpus under the additive host policy.
            from lean_export_host import policy, environment
            current = copy.deepcopy(rows)
            for entry in current:
                if entry['argv'][1:3] == ['env', 'lean']:
                    entry['argv'].insert(3, '-j2')
                    entry['host_environment'] = environment(policy())
            validate_multi_commands(current, **args, host_export_policy=policy())
            with self.assertRaises(Core0Error):
                validate_multi_commands(rows, **args, host_export_policy=policy())
            with self.assertRaises(Core0Error):
                validate_multi_commands(current, **args)
            bads=[];bad=copy.deepcopy(rows);bad[5]['cwd']=base+'/users/busy';bads.append(bad)
            bad=copy.deepcopy(rows);bad[8]['argv'].insert(-2,'foreign.o');bads.append(bad)
            bad=copy.deepcopy(rows);bad.pop(6);bads.append(bad)
            bad=copy.deepcopy(rows);bad[5]['argv'][0]='/tmp/opt';bads.append(bad)
            bad=copy.deepcopy(rows);bad[2]['argv'][0]='/tmp/lake';bads.append(bad)
            bad=copy.deepcopy(rows);bad[5]['returncode']=False;bads.append(bad)
            for bad in bads:
                with self.assertRaises(Core0Error):validate_multi_commands(bad,**args)
            (out/d/'Export.lean').write_text('import Lemma.User.Development.Tasks.Busy\n')
            with self.assertRaises(Core0Error):validate_multi_commands(rows,**args)


class FaultImageAuditFailures(unittest.TestCase):
    configuration='tasks-fault-development'

    def test_fourth_image_does_not_widen_f_registry_or_any_other_startup(self):
        value=catalog(self.configuration)
        validate_user_image_catalog(value,configuration=self.configuration)
        with self.assertRaises(Core0Error):validate_user_image_catalog(value,configuration='tasks-development')
        for mutate in [lambda rows:rows.pop(),lambda rows:rows.append(copy.deepcopy(rows[-1])),
                       lambda rows:rows[0].update(startup_case='supervisor-csr'),
                       lambda rows:rows[3].update(directory='users/compute'),
                       lambda rows:rows[3].update(id=3),lambda rows:rows[3].update(source=rows[0]['source'])]:
            bad=catalog(self.configuration);mutate(bad['images'])
            with self.assertRaises(Core0Error):validate_user_image_catalog(bad)

    def test_unit_case_and_source_are_bound_to_only_the_selected_image(self):
        for key in ['compute','sleeper','busy','fault']:
            good=unit(key,self.configuration)
            validate_unit(good,'user',configuration=self.configuration,image_key=key)
            for mutate in [lambda row:row.pop('startup_case'),
                           lambda row:row.update(startup_case='none' if key=='fault' else 'supervisor-csr'),
                           lambda row:row['functions'].append({'source':'Lemma.User.Development.Tasks.'+('Compute' if key=='fault' else 'Fault')+'.main',
                                                            'symbol':row['functions'][0]['symbol']+'_peer','args':['u64'],'effects':[]})]:
                bad=unit(key,self.configuration);mutate(bad)
                with self.assertRaises(Core0Error):validate_unit(bad,'user',configuration=self.configuration,image_key=key)
        with self.assertRaises(Core0Error):validate_unit(unit('fault',self.configuration),'user',configuration='tasks-development',image_key='fault')
        self.assertEqual(development_modules(self.configuration,'kernel'),('Lemma.Kernel.Development.FaultEntry','Lemma.Kernel.Development.TasksEntry','Lemma.Kernel.Development.Pressure'))
        self.assertEqual(development_modules('tasks-development','kernel'),('Lemma.Kernel.Development.TasksEntry',))

    def test_case_maps_catalogs_and_package_count_cannot_be_substituted(self):
        images=catalog(self.configuration)['images'];mapping={row['key']:row['startup_case'] for row in images}
        record={'user_startup_cases':mapping}
        validate_image_case_provenance(record,record,configuration=self.configuration,images=images)
        for bad in [{},{'user_startup_cases':{**mapping,'compute':'supervisor-csr'}},{'user_startup_cases':{**mapping,'fault':'none'}}]:
            with self.assertRaises(Core0Error):validate_image_case_provenance(record,bad,configuration=self.configuration,images=images)
        with self.assertRaises(Core0Error):validate_image_case_provenance(record,record,configuration='tasks-development',images=list(TASK_USER_IMAGES))
        image=TASK_FAULT_USER_IMAGES[-1]
        good={'schema_version':1,'contract_version':'lemma-user-execution-v1','configuration':self.configuration,
              'image_key':'fault','image_id':4,'startup_case':'supervisor-csr','symbols':user_primitive_rows('supervisor-csr')}
        validate_user_primitive_catalog(good,image,configuration=self.configuration)
        for key in ['compute','sleeper','busy']:
            selected=next(row for row in images if row['key']==key)
            bad={**good,'image_key':key,'image_id':selected['id']}
            with self.assertRaises(Core0Error):validate_user_primitive_catalog(bad,selected,configuration=self.configuration)
        package=contract(self.configuration)
        validate_package_contract(package,configuration=self.configuration,catalog=catalog(self.configuration))
        raw,payloads=packed_fixture(self.configuration)
        self.assertEqual([row['id'] for row in validate_package_payloads(raw,package,payloads)],[1,2,3,4])
        with self.assertRaises(Core0Error):validate_package_payloads(raw,package,payloads[:3])
        with self.assertRaises(Core0Error):validate_package_contract(package,configuration='tasks-development',catalog=catalog(self.configuration))

    def test_only_exact_fault_startup_object_and_csr_instruction_can_pass(self):
        symbol='lemma_user_attack_supervisor_csr'
        section='  [ 6] .text.user_adversarial PROGBITS 0000000000000000 0000a0 000008 00 AX 0 0 4\n'
        symbols=' 7: 0000000000000000 8 FUNC GLOBAL DEFAULT 6 '+symbol+'\n'
        assembly='.section .text.user_adversarial, "ax", @progbits\n'+symbol+':\n  csrr a0, sstatus\n  ret\n.size '+symbol+', . - '+symbol+'\n'
        raw=struct.pack('<2I',0x10002573,0x00008067)
        args=dict(configuration=self.configuration,image_key='fault')
        validate_image_attack_object(section,symbols,raw,assembly,**args)
        for key in ['compute','sleeper','busy']:
            with self.assertRaises(Core0Error):validate_image_attack_object(section,symbols,raw,assembly,configuration=self.configuration,image_key=key)
        with self.assertRaises(Core0Error):validate_image_attack_object(section,symbols,raw,assembly,configuration='tasks-development',image_key='fault')
        for fields in [(section.replace('AX','WAX'),symbols,raw,assembly),(section.replace('000008','00000c'),symbols,raw,assembly),
                       (section,symbols.replace('DEFAULT 6','DEFAULT 5'),raw,assembly),(section,symbols,struct.pack('<2I',0x100025f3,0x00008067),assembly),
                       (section,symbols,raw,assembly.replace('sstatus','satp')),(section,symbols,raw+raw,assembly)]:
            with self.assertRaises(Core0Error):validate_image_attack_object(*fields,**args)
        ranges={symbol:(0x10080,8)}
        machine=' 10080: 10002573 csrr a0, sstatus\n 10084: 00008067 ret\n'
        validate_user_attack_machine(machine,ranges,assembly,'supervisor-csr')
        validate_machine(' 10080: csrr a0, sstatus\n 10084: ret\n',user=True,ranges=ranges,user_csr_pc=0x10080)
        for pc in [None,0x10084]:
            with self.assertRaises(Core0Error):validate_machine(' 10080: csrr a0, sstatus\n 10084: ret\n',user=True,ranges=ranges,user_csr_pc=pc)
        with self.assertRaises(Core0Error):validate_user_attack_machine(machine.replace('10002573','100025f3'),ranges,assembly,'supervisor-csr')

class ManagedImageAuditFailures(unittest.TestCase):
    configuration='capabilities-development'

    def test_closed_roles_cannot_be_relabelled_or_added_to_prior_deployments(self):
        good=catalog(self.configuration)
        validate_user_image_catalog(good)
        for mutate in [lambda row:row.pop('managed_policy'),lambda row:row.update(managed_policy='unknown'),
                       lambda row:row['images'][0].update(boot_role='peer'),
                       lambda row:row['images'][1].pop('boot_role'),
                       lambda row:row['images'][3].update(startup_case='supervisor-csr'),
                       lambda row:row['images'][0].update(source=row['images'][1]['source'])]:
            bad=catalog(self.configuration);mutate(bad)
            with self.assertRaises(Core0Error):validate_user_image_catalog(bad)
        for prior in ['tasks-development','tasks-fault-development']:
            bad=catalog(prior);bad['managed_policy']=MANAGED_POLICY
            with self.assertRaises(Core0Error):validate_user_image_catalog(bad)

    def test_managed_unit_binds_source_role_and_rejects_privileged_closure(self):
        for image in CAPABILITY_USER_IMAGES:
            key=image['key'];good=unit(key,self.configuration)
            validate_unit(good,'user',configuration=self.configuration,image_key=key)
            for mutate in [lambda row:row.pop('managed_policy'),lambda row:row.pop('boot_role'),
                           lambda row:row.update(boot_role='other'),lambda row:row.update(startup_case='supervisor-csr')]:
                bad=unit(key,self.configuration);mutate(bad)
                with self.assertRaises(Core0Error):validate_unit(bad,'user',configuration=self.configuration,image_key=key)
            for source in ['Lemma.Kernel.Capability.lookup','Lemma.Compiler.Frontend.lower',
                           '_private.Lemma.Kernel.Capability.0.Lemma.Kernel.Capability.lookup']:
                bad=unit(key,self.configuration)
                bad['functions'].append({'source':source,'symbol':image['symbol_prefix']+'leak','args':[],'effects':[]})
                with self.assertRaises(Core0Error):validate_unit(bad,'user',configuration=self.configuration,image_key=key)

    def test_managed_primitive_and_package_authority_is_exact_and_contains_no_attack(self):
        validate_package_contract(contract(self.configuration),configuration=self.configuration,catalog=catalog(self.configuration))
        for image in CAPABILITY_USER_IMAGES:
            good={'schema_version':1,'contract_version':'lemma-user-execution-v1','configuration':self.configuration,
                  'image_key':image['key'],'image_id':image['id'],'startup_case':'none',
                  'symbols':user_primitive_rows('none'),**managed_fields(self.configuration,image)}
            validate_user_primitive_catalog(good,image,configuration=self.configuration)
            for mutate in [lambda row:row.pop('managed_policy'),lambda row:row.update(boot_role='tamper' if image['key']!='tamper' else 'peer'),
                           lambda row:row.update(symbols=user_primitive_rows('supervisor-csr'))]:
                bad=copy.deepcopy(good);mutate(bad)
                with self.assertRaises(Core0Error):validate_user_primitive_catalog(bad,image,configuration=self.configuration)
        bad=contract(self.configuration);bad['images'][0]['boot_role']='peer'
        with self.assertRaises(Core0Error):validate_package_contract(bad,configuration=self.configuration,catalog=catalog(self.configuration))
        raw,payloads=packed_fixture(self.configuration)
        self.assertEqual([row['id'] for row in validate_package_payloads(raw,contract(self.configuration),payloads)],[1,2,3,4])

    def test_independent_provenance_rejects_managed_labels_outside_or_between_images(self):
        for image in CAPABILITY_USER_IMAGES:
            good=managed_fields(self.configuration,image)
            validate_standalone_managed_provenance(good,copy.deepcopy(good),configuration=self.configuration,image=image)
            for bad in [{},{**good,'boot_role':'other'},{**good,'boot_roles':{image['key']:image['boot_role']}}]:
                with self.assertRaises(Core0Error):validate_standalone_managed_provenance(good,bad,configuration=self.configuration,image=image)
        for prior in ['tasks-development','tasks-fault-development']:
            with self.assertRaises(Core0Error):validate_standalone_managed_provenance({'managed_policy':MANAGED_POLICY},{},configuration=prior,image=image_specs(prior)[0])

    def test_both_provenance_records_require_identical_closed_managed_roles(self):
        good={'managed_policy':MANAGED_POLICY,'boot_roles':{row['key']:row['boot_role'] for row in CAPABILITY_USER_IMAGES}}
        args=dict(configuration=self.configuration,images=list(CAPABILITY_USER_IMAGES))
        validate_managed_provenance(good,copy.deepcopy(good),**args)
        for bad in [{},{'managed_policy':MANAGED_POLICY,'boot_roles':{'capabilities':'peer'}},
                    {'managed_policy':'unknown','boot_roles':good['boot_roles']}]:
            with self.assertRaises(Core0Error):validate_managed_provenance(good,bad,**args)
        for prior in ['tasks-development','tasks-fault-development']:
            with self.assertRaises(Core0Error):validate_managed_provenance(good,{},configuration=prior,images=list(image_specs(prior)))


class IPCImageAuditFailures(unittest.TestCase):
    configuration='ipc-development'

    def test_shared_client_module_retains_separate_exact_roots_and_roles(self):
        good=catalog(self.configuration);validate_user_image_catalog(good,configuration=self.configuration)
        self.assertEqual([r['key'] for r in IPC_USER_IMAGES],['server','clienta','clientb','busy','fault'])
        a,b=IPC_USER_IMAGES[1:3];self.assertEqual(a['module'],b['module']);self.assertNotEqual(a['source'],b['source'])
        self.assertNotEqual(a['symbol_prefix'],b['symbol_prefix'])
        for mutate in [lambda r:r.update(managed_policy=MANAGED_POLICY),lambda r:r['images'].reverse(),
                       lambda r:r['images'][1].update(source=b['source']),lambda r:r['images'][1].update(boot_role=b['boot_role']),
                       lambda r:r['images'][4].update(module='Lemma.User.Development.Tasks.Fault'),
                       lambda r:r['images'][4].update(startup_case='supervisor-csr')]:
            bad=copy.deepcopy(good);mutate(bad)
            with self.assertRaises(Core0Error):validate_user_image_catalog(bad,configuration=self.configuration)

    def test_per_image_policy_and_roots_do_not_cross_clients_or_old_configuration(self):
        for image in IPC_USER_IMAGES:
            good=unit(image['key'],self.configuration);validate_unit(good,'user',configuration=self.configuration,image_key=image['key'])
            for mutate in [lambda r:r.update(managed_policy=MANAGED_POLICY),lambda r:r.pop('boot_role'),
                           lambda r:r.update(boot_role='ipc-server'),lambda r:r.update(startup_case='supervisor-csr')]:
                bad=copy.deepcopy(good);mutate(bad)
                if bad==good:continue
                with self.assertRaises(Core0Error):validate_unit(bad,'user',configuration=self.configuration,image_key=image['key'])
        bad=unit('clienta',self.configuration);bad['roots'][0]['source']=IPC_USER_IMAGES[2]['source']
        with self.assertRaises(Core0Error):validate_unit(bad,'user',configuration=self.configuration,image_key='clienta')
        with self.assertRaises(Core0Error):validate_unit(unit('clienta',self.configuration),'user',configuration='capabilities-development',image_key='clienta')

    def test_package_primitives_and_both_provenance_records_have_exact_source_roles(self):
        good=catalog(self.configuration);validate_package_contract(contract(self.configuration),configuration=self.configuration,catalog=good)
        good={'managed_policy':IPC_POLICY,'boot_roles':{r['key']:r['boot_role'] for r in IPC_USER_IMAGES}}
        validate_managed_provenance(good,copy.deepcopy(good),configuration=self.configuration,images=list(IPC_USER_IMAGES))
        for image in IPC_USER_IMAGES:
            single=managed_fields(self.configuration,image)
            validate_standalone_managed_provenance(single,single,configuration=self.configuration,image=image)
            value={'schema_version':1,'contract_version':'lemma-user-execution-v1','configuration':self.configuration,
                   'image_key':image['key'],'image_id':image['id'],'startup_case':'none','symbols':user_primitive_rows('none'),**single}
            validate_user_primitive_catalog(value,image,configuration=self.configuration)
        for bad in [{**good,'managed_policy':MANAGED_POLICY},{**good,'boot_roles':{'server':'ipc-client-a'}}]:
            with self.assertRaises(Core0Error):validate_managed_provenance(bad,bad,configuration=self.configuration,images=list(IPC_USER_IMAGES))
        self.assertEqual(development_modules(self.configuration,'kernel'),('Lemma.Kernel.Development.IPCEntry','Lemma.Kernel.Development.TasksEntry'))

if __name__=='__main__':unittest.main()
