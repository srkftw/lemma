"""Host-only archive/realization guards; fixtures never compile target code."""
import copy,json,os,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from core0_common import Core0Error,sha256
from kernel_source_workspace import FILES,archive_inputs,copy_inputs,prepare,validate_flake_input,validate_record

class CompilerSourceWorkspace(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.repo=Path(self.tmp.name);self.archive=self.repo/'build/original';self.archive.mkdir(parents=True)
  for name in FILES:
   for base in (self.repo,self.archive):
    p=base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
  for i in range(101):
   p=self.archive/f'Lemma/Fixture{i}.lean';p.parent.mkdir(exist_ok=True);p.write_text('-- quarantined host inventory fixture\n')
  self.original=self.inspect(self.archive)
  (self.archive/'source-inputs.json').write_text(json.dumps(self.original))
  self.work=self.repo/'build/kernel/private/target'
 def inspect(self,directory):
  files=[directory/n for n in FILES]+sorted((directory/'Lemma').rglob('*.lean'))
  return {p.relative_to(directory).as_posix():sha256(p) for p in files}
 def copied(self):
  return copy_inputs(self.archive,self.work,self.repo,self.inspect)
 def prepared(self):
  self.copied();out=self.work/'build/kernel/image';out.mkdir(parents=True)
  record,directory=prepare(self.work,out,self.archive,self.repo,self.inspect)
  record.update(parent_git_root=str(self.repo),parent_git_prefix=self.work.relative_to(self.repo).as_posix()+'/',
   parent_git_head='a'*40,host_orchestrator_inputs={f'scripts/fixture{i}.py':'b'*64 for i in range(31)})
  return record,directory,out
 def test_exact_archive_and_unused_copy(self):
  self.assertEqual(archive_inputs(self.archive,self.inspect),self.original)
  self.copied();self.assertEqual(self.inspect(self.work),self.original)
  with self.assertRaises(Core0Error):self.copied()
 def test_mixed_changed_manifest_and_additional_file(self):
  p=self.archive/'Lemma/Fixture0.lean';p.write_text('-- changed\n')
  with self.assertRaises(Core0Error):archive_inputs(self.archive,self.inspect)
  p.write_text('-- quarantined host inventory fixture\n')
  extra=self.archive/'unaccounted';extra.write_text('x')
  with self.assertRaises(Core0Error):archive_inputs(self.archive,self.inspect)
 def test_source_copy_with_ignored_cache_or_changed_input_rejects(self):
  self.copied();out=self.work/'build/kernel/image';out.mkdir(parents=True)
  cached=self.work/'.lake/stale';cached.parent.mkdir();cached.write_text('x')
  with self.assertRaises(Core0Error):prepare(self.work,out,self.archive,self.repo,self.inspect)
  cached.unlink();p=self.work/'Lemma/Fixture0.lean';p.write_text('changed')
  with self.assertRaises(Core0Error):prepare(self.work,out,self.archive,self.repo,self.inspect)
 def test_toolchain_realization_contains_only_the_locked_three_file_closure(self):
  record,directory,out=self.prepared()
  self.assertEqual(set(p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()),set(FILES))
  self.assertEqual(validate_flake_input(directory,record['flake_input_sha256']),record['flake_input_bytes'])
  (directory/'.lake').mkdir();(directory/'.lake/blob').write_text('must never enter Nix input')
  with self.assertRaises(Core0Error):validate_flake_input(directory,record['flake_input_sha256'])
 def test_symlink_realization_and_mixed_pinned_flake_reject(self):
  self.copied();out=self.work/'build/kernel/image';out.mkdir(parents=True)
  (self.repo/'flake.nix').write_text('different')
  with self.assertRaises(Core0Error):prepare(self.work,out,self.archive,self.repo,self.inspect)
  (self.repo/'flake.nix').write_bytes((ROOT/'flake.nix').read_bytes())
  record,directory=prepare(self.work,out,self.archive,self.repo,self.inspect)
  (directory/'flake.nix').unlink();(directory/'flake.nix').symlink_to(self.archive/'flake.nix')
  with self.assertRaises(Core0Error):validate_flake_input(directory,record['flake_input_sha256'])
 def test_special_file_cannot_enter_realization_input(self):
  record,directory,out=self.prepared()
  os.mkfifo(directory/'untracked-fifo')
  with self.assertRaises(Core0Error):validate_flake_input(directory,record['flake_input_sha256'])
 def test_record_requires_actual_separate_source_git_and_realization_bindings(self):
  record,directory,out=self.prepared()
  validate_record(record,source_origin=self.archive,output_dir=out,source_inputs=self.inspect)
  for key,value in [('schema_version',True),('maximum_flake_bytes',True),('flake_input_bytes',0),
   ('source_archive',str(self.work)),('source_workspace',str(self.archive)),('parent_git_prefix','../target'),
   ('parent_git_head','old-source-label'),('realization_cwd','.'),('host_orchestrator_inputs',{}),
   ('source_archive_inventory_sha256','0'*64),('flake_input_sha256',{})]:
   bad=copy.deepcopy(record);bad[key]=value
   with self.assertRaises(Core0Error,msg=key):validate_record(bad,source_origin=self.archive,output_dir=out,source_inputs=self.inspect)
  (out/'source-workspace-inputs.json').write_text('{}')
  with self.assertRaises(Core0Error):validate_record(record,source_origin=self.archive,output_dir=out,source_inputs=self.inspect)

 def test_private_construction_base_requires_exact_workspace_and_complete_lake_corpus(self):
  from unittest.mock import patch
  import audit_kernel as audit
  from audit_kernel import TASK_USER_IMAGES
  from build_kernel import configuration_modules,configuration_roots,BOOT_OBJECTS
  from build_core0 import OPT_PASSES,LLC_ARGUMENTS,STARTUP_ARGUMENTS
  record,directory,out=self.prepared();image=TASK_USER_IMAGES[0];d=image['directory'];base=out.relative_to(self.work).as_posix();roles=configuration_roots('tasks-development')
  (out/d).mkdir(parents=True)
  for name,contents in {'CatalogExport.lean':'import Lemma.Compiler.KernelExport\n\n#lemma_export_user_catalog\n',
   d+'/Export.lean':f'import {image["module"]}\nimport Lemma.Compiler.KernelExport\n\n#lemma_export_user_image "{image["key"]}" [{image["source"]}]\n',
   'BootExport.lean':'import Lemma.Compiler.KernelExport\n\n#lemma_export_boot_files\n'}.items():(out/name).write_text(contents)
  for role,module in configuration_modules('tasks-development').items():
   (out/role).mkdir()
   (out/role/'Export.lean').write_text(f'import {module}\nimport Lemma.Compiler.KernelExport\n\n#lemma_export_unit "{role}" ['+', '.join(source for source,_ in roles[role])+']\n')
  pin=json.loads((self.archive/'tooling/toolchain-lock.json').read_text())['tools']
  stores={'opt':pin['llvm']['store_path'],'llc':pin['llvm']['store_path'],'llvm-objcopy':pin['llvm']['store_path'],
   'clang':pin['llvm']['outputs']['clang_unwrapped']['store_path'],'ld.lld':pin['lld']['store_path'],'lake':pin['lean']['store_path']}
  def row(tool,args,cwd):return {'argv':[stores.get(tool,'/nix/store/host')+'/bin/'+tool,*args],'cwd':cwd,'returncode':0}
  rows=[row('nix',['build','--no-link','--print-out-paths','--impure','--expr',__import__('kernel_source_workspace').PATH_SOURCE_EXPRESSION],record['realization_cwd']),row('nix',['path-info','--json',pin['lean']['source_path']],'.')]
  rows += [row('lake',['build','Lemma.Compiler.KernelExport'],'.'),row('lake',['env','lean',base+'/CatalogExport.lean'],'.'),
   row('lake',['build',*configuration_modules('tasks-development').values(),image['module'],'Lemma.Compiler.KernelExport'],'.'),*(row('lake',['env','lean',base+'/'+role+'/Export.lean'],'.') for role in roles),row('lake',['env','lean',base+'/'+d+'/Export.lean'],'.'),row('lake',['env','lean',base+'/BootExport.lean'],'.')]
  rows += [r for role in roles for r in [row('opt',['-S','-passes='+OPT_PASSES['O2'],'program.ll','-o','program.opt.ll'],base+'/'+role),row('llc',[*LLC_ARGUMENTS,'-stack-size-section','-O2','program.opt.ll','-o','program.o'],base+'/'+role)]]
  rows += [row('opt',['-S','-passes='+OPT_PASSES['O2'],'program.ll','-o','program.opt.ll'],base+'/'+d),row('llc',[*LLC_ARGUMENTS,'-stack-size-section','-O2','program.opt.ll','-o','program.o'],base+'/'+d),row('clang',[*STARTUP_ARGUMENTS,d+'/startup.S','-o',d+'/startup.o'],base),row('ld.lld',['-m','elf64lriscv','--no-relax','-T',d+'/link.ld','-Map='+d+'/image.map',d+'/startup.o',d+'/program.o','-o',d+'/image.elf'],base),row('llvm-objcopy',['-O','binary','--only-section=.text',d+'/image.elf',d+'/text.bin'],base),row('llvm-objcopy',['-O','binary','--only-section=.data',d+'/image.elf',d+'/data.bin'],base),row('clang',[*STARTUP_ARGUMENTS,'boot-package.S','-o','boot-package.o'],base),row('clang',[*STARTUP_ARGUMENTS,'startup.S','-o','startup.o'],base),row('ld.lld',['-m','elf64lriscv','--no-relax','-T','link.ld','-Map=image.map',*BOOT_OBJECTS,'-o','image.elf'],base)]
  args=dict(root=self.repo,output_dir=out,images=[image],optimization='O2',roles=roles,standalone=False,configuration='tasks-development',compiler_source_workspace=record,source_root=self.archive)
  with patch.object(audit,'source_inputs',self.inspect):
   audit.validate_multi_commands(rows,**args)
   for index,r in enumerate(rows):
    bad=copy.deepcopy(rows);bad[index]['cwd']='unadmitted'
    with self.assertRaises(Core0Error,msg=f'cwd{index}'):audit.validate_multi_commands(bad,**args)
    bad=copy.deepcopy(rows);bad[index]['argv'][-1]+='-unadmitted'
    with self.assertRaises(Core0Error,msg=f'argv{index}'):audit.validate_multi_commands(bad,**args)
   for change in [dict(source_root=None),dict(compiler_source_workspace=None),dict(standalone=True),dict(root=self.work)]:
    with self.assertRaises(Core0Error):audit.validate_multi_commands(rows,**{**args,**change})
   bad=copy.deepcopy(rows);bad[2:2]=[copy.deepcopy(rows[2])]
   with self.assertRaises(Core0Error):audit.validate_multi_commands(bad,**args)

if __name__=='__main__':unittest.main()
