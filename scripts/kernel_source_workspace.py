"""Bounded archived-source compiler workspace, below target compilation policy.

This separates an exact original target/compiler source copy from a tiny pinned
Nix realization input. It does not create Git state or load a guest machine.
"""
from __future__ import annotations
import json,re,shutil
from pathlib import Path
from core0_common import Core0Error,sha256,write_json

CONTRACT='lemma-archived-compiler-workspace-v1'
FILES=('flake.nix','flake.lock','tooling/toolchain-lock.json')
MAXIMUM_FLAKE_BYTES=262144
PATH_SOURCE_EXPRESSION=('let flake = builtins.getFlake ("path:" + toString ./.); '
 'pkgs = import flake.inputs.nixpkgs { system = builtins.currentSystem; }; in pkgs.lean4.src')

def _files(directory):
 result=set()
 for path in directory.rglob('*'):
  if path.is_symlink():raise Core0Error('archived compiler input contains a symlink')
  if path.is_file():result.add(path.relative_to(directory).as_posix())
  elif not path.is_dir():raise Core0Error('archived compiler input contains a special file')
 return result

def archive_inputs(source_archive,source_inputs):
 source_archive=source_archive.resolve()
 manifest=source_archive/'source-inputs.json'
 try:value=json.loads(manifest.read_text())
 except (OSError,ValueError) as error:raise Core0Error('archived compiler source inventory missing/malformed') from error
 if not isinstance(value,dict) or len(value)<100:raise Core0Error('archived compiler inventory empty/truncated')
 for name,digest in value.items():
  if (not isinstance(name,str) or Path(name).is_absolute() or '..' in Path(name).parts or
      not isinstance(digest,str) or re.fullmatch('[0-9a-f]{64}',digest) is None):
   raise Core0Error('archived compiler inventory path/digest malformed')
 if _files(source_archive)!=set(value)|{'source-inputs.json'} or source_inputs(source_archive)!=value:
  raise Core0Error('archived compiler source is not its exact complete original inventory')
 return value

def copy_inputs(source_archive,workspace,repository_root,source_inputs):
 source_archive=source_archive.resolve();workspace=workspace.resolve();repository_root=repository_root.resolve()
 if (workspace.exists() or not workspace.is_relative_to(repository_root/'build/kernel') or
     not source_archive.is_relative_to(repository_root/'build')):
  raise Core0Error('unused ignored archived compiler source workspace required')
 original=archive_inputs(source_archive,source_inputs)
 workspace.mkdir(parents=True)
 for name,digest in original.items():
  target=workspace/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source_archive/name,target)
  if sha256(target)!=digest:raise Core0Error('archive source changed during private copy: '+name)
 if source_inputs(workspace)!=original:raise Core0Error('copied compiler source inventory differs')
 return workspace

def validate_flake_input(directory,expected):
 if not isinstance(expected,dict) or set(expected)!=set(FILES):raise Core0Error('compiler flake closure differs')
 if _files(directory)!=set(FILES):raise Core0Error('compiler flake input contains additional files')
 total=0
 for name,digest in expected.items():
  if not isinstance(digest,str) or re.fullmatch('[0-9a-f]{64}',digest) is None or sha256(directory/name)!=digest:
   raise Core0Error('compiler flake input bytes differ: '+name)
  total+=(directory/name).stat().st_size
 if not 0<total<=MAXIMUM_FLAKE_BYTES:raise Core0Error('compiler flake input exceeds declared copy bound')
 return total

def prepare(root,output_dir,source_archive,repository_root,source_inputs):
 root=root.resolve();output_dir=output_dir.resolve();source_archive=source_archive.resolve();repository_root=repository_root.resolve()
 if (root==repository_root or not root.is_relative_to(repository_root/'build/kernel') or
     not source_archive.is_relative_to(repository_root/'build') or source_archive==root or
     not output_dir.is_relative_to(root/'build/kernel') or (root/'.git').exists()):
  raise Core0Error('archive compiler requires a private ignored source copy and independent original archive')
 original=archive_inputs(source_archive,source_inputs)
 if source_inputs(root)!=original or _files(root)!=set(original):
  raise Core0Error('private compiler source copy is not fresh byte-exact original input')
 flake_hashes={name:original[name] for name in FILES}
 # The host toolchain pin/locked realization closure cannot change implicitly.
 if any(sha256(repository_root/name)!=digest for name,digest in flake_hashes.items()):
  raise Core0Error('archive compiler flake/pin differs from current qualified toolchain')
 directory=output_dir/'toolchain-flake';directory.mkdir()
 for name,digest in flake_hashes.items():
  target=directory/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source_archive/name,target)
 total=validate_flake_input(directory,flake_hashes)
 write_json(output_dir/'source-workspace-inputs.json',original)
 return {'schema_version':1,'contract_version':CONTRACT,'source_archive':str(source_archive),
  'source_archive_inventory_sha256':sha256(source_archive/'source-inputs.json'),
  'source_workspace':str(root),'realization_cwd':directory.relative_to(root).as_posix(),
  'flake_input_sha256':flake_hashes,'flake_input_bytes':total,
  'maximum_flake_bytes':MAXIMUM_FLAKE_BYTES},directory

def host_inputs(repository_root,source_inputs):
 return {name:digest for name,digest in source_inputs(repository_root).items()
         if name.startswith('scripts/') or name in FILES or name.startswith('sim/profiles/')}

def validate_record(value,*,source_origin,output_dir,source_inputs):
 if (not isinstance(value,dict) or type(value.get('schema_version')) is not int or value['schema_version']!=1 or
     value.get('contract_version')!=CONTRACT or type(value.get('maximum_flake_bytes')) is not int or
     value['maximum_flake_bytes']!=MAXIMUM_FLAKE_BYTES or type(value.get('flake_input_bytes')) is not int):
  raise Core0Error('archived compiler workspace metadata differs')
 if any(not isinstance(value.get(k),str) or not value[k] for k in ('source_workspace','source_archive','parent_git_root','parent_git_head','realization_cwd')):
  raise Core0Error('archived compiler workspace paths/Git fields malformed')
 original=archive_inputs(source_origin,source_inputs)
 workspace=Path(value.get('source_workspace','')).resolve()
 archive=Path(value.get('source_archive','')).resolve()
 if (archive!=source_origin.resolve() or value.get('source_archive_inventory_sha256')!=sha256(archive/'source-inputs.json') or
     workspace==archive or not output_dir.resolve().is_relative_to(workspace/'build/kernel')):
  raise Core0Error('archived compiler workspace/source/output binding differs')
 copied=json.loads((output_dir/'source-workspace-inputs.json').read_text())
 if copied!=original:raise Core0Error('archived compiler consumed source inventory differs')
 parent=Path(value.get('parent_git_root','')).resolve()
 prefix=value.get('parent_git_prefix')
 if (not isinstance(prefix,str) or Path(prefix).is_absolute() or '..' in Path(prefix).parts or
     (parent/prefix).resolve()!=workspace or not workspace.is_relative_to(parent/'build/kernel') or
     not isinstance(value.get('parent_git_head'),str) or re.fullmatch('[0-9a-f]{40}',value['parent_git_head']) is None):
  raise Core0Error('archived compiler actual Git context differs')
 expected={name:original[name] for name in FILES}
 directory=output_dir/'toolchain-flake'
 if value.get('flake_input_sha256')!=expected or value.get('realization_cwd')!=directory.relative_to(workspace).as_posix():
  raise Core0Error('archived compiler realization closure/cwd differs')
 if validate_flake_input(directory,expected)!=value['flake_input_bytes']:
  raise Core0Error('archived compiler bounded realization bytes differ')
 inputs=value.get('host_orchestrator_inputs')
 if not isinstance(inputs,dict) or len(inputs)<30 or any(not isinstance(n,str) or not isinstance(h,str) or re.fullmatch('[0-9a-f]{64}',h) is None for n,h in inputs.items()):
  raise Core0Error('archived compiler host orchestrator identities missing/malformed')
 return {'contract_version':CONTRACT,'source_archive_inventory_sha256':value['source_archive_inventory_sha256'],
  'flake_input_bytes':value['flake_input_bytes'],'parent_git_head':value['parent_git_head'],
  'source_workspace':str(workspace),'scope':'original source byte identity; actual parent Git identity is separately recorded'}
