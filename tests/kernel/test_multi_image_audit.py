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
from audit_kernel import (TASK_USER_IMAGES, validate_user_image_catalog, validate_unit,
                          validate_user_primitive_catalog, validate_package_contract,
                          validate_package_payloads, validate_multi_commands, user_primitive_rows, audit_standalone_user)
from build_kernel import CONTRACTS, LEAN_SOURCE_EXPRESSION
from build_core0 import LLC_ARGUMENTS, OPT_PASSES, STARTUP_ARGUMENTS
from core0_common import Core0Error


def catalog():
    return {'schema_version':1, 'contract_version':'lemma-user-image-catalog-v1',
            'configuration':'tasks-development','stage':'supervisor','image_count':3,
            'images':copy.deepcopy(list(TASK_USER_IMAGES))}


def unit(key='compute'):
    image=next(row for row in TASK_USER_IMAGES if row['key']==key)
    root={'id':1,'source':image['source'],'symbol':image['symbol_prefix']+'root','args':['u64']}
    return {'schema_version':2,'artifact_category':'development-user-unit','contract_version':CONTRACTS['user'],
            'configuration':'tasks-development','role':'user','image_key':key,'image_id':image['id'],
            'roots':[root],'functions':[{**{k:v for k,v in root.items() if k!='id'},'effects':[]}],
            'used_execution_ops':[],'used_device_ops':[],'used_loops':[]}


def contract():
    image={'entry':0x10000,'text_va':0x10000,'text_capacity':0xf000,'data_va':0x20000,
           'data_mem_bytes':4096,'stack_va':0x3fffc000,'stack_pages':2,'flags':0}
    return {'schema_version':2,'configuration':'tasks-development','startup_case':'normal','user_startup_case':'none',
            'contract_version':'lemma-boot-package-v1','magic':0x31474b50414d454c,'version':1,'image_count':3,
            'header_bytes':32,'descriptor_bytes':96,'offset_encoding':'generated-label-differences',
            'images':[{**image,'key':row['key'],'id':row['id']} for row in TASK_USER_IMAGES]}


def packed_fixture():
    payloads=[(struct.pack('<II',i,i+10),struct.pack('<QQ',0,1)) for i in range(1,4)]
    data=bytearray(32+3*96)
    for index,(text,initialized) in enumerate(payloads):
        text_offset=len(data);data.extend(text);data_offset=len(data);data.extend(initialized)
        struct.pack_into('<12Q',data,32+index*96,index+1,0x10000,0x10000,text_offset,len(text),0x20000,
                         data_offset,len(initialized),4096,0x3fffc000,2,0)
    struct.pack_into('<4Q',data,0,0x31474b50414d454c,1,3,len(data))
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

if __name__=='__main__':unittest.main()
