#!/usr/bin/env python3
"""Exact product-ROM/native input validation; never installs a running image."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
PROFILE='lemma-silicon-dev/0.7.0'

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for part in iter(lambda:f.read(1048576),b''):h.update(part)
 return h.hexdigest()

def relative(path):
 p=Path(path)
 if p.is_absolute():p=p.relative_to(ROOT)
 if not p.parts or '..' in p.parts:raise ValueError('Unmapped product native input')
 return p.as_posix()

def native(build,archive=None):
 """Require current inputs or the explicit complete original consumed archive."""
 build=Path(build).resolve();m=json.loads((build/'build.json').read_text())
 if m.get('profile')!=PROFILE or m.get('configuration')!='external-ram-128MiB':
  raise ValueError('Product requires the declared canonical profile7 native core')
 expected={}
 def add(p,h):
  p=relative(p)
  if p in expected and expected[p]!=h:raise ValueError('Conflicting native input identity')
  if not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h):
   raise ValueError('Malformed native input identity')
  expected[p]=h
 for key in ('sha256','configuration_includes','host_runtime','host_toolchain_inputs','binding_generator_inputs'):
  if not isinstance(m.get(key),dict) or not m[key]:raise ValueError('Missing native consumed inputs')
  for p,h in m[key].items():add(p,h)
 for key in ('host_adapter','build_driver','upstream_patch'):add(m[key]['path'],m[key]['sha256'])
 add(Path(m['host_include_dir'])/'lemma_silicon_binding.h',m['host_binding_sha256'])
 add('sim/profiles/lemma-silicon-dev-0.7.0.json',m['profile_sha256'])
 origin=ROOT;receipt={'kind':'current-source','inputs':len(expected)}
 if archive is not None:
  archive=Path(archive).resolve();a=json.loads((archive.parent/'consumed-source-archive.json').read_text())
  if (a.get('schema')!='lemma-consumed-native-source-archive/1' or
      a.get('original_manifest_sha256')!=sha(build/'build.json') or
      a.get('snapshot_identity')!=m.get('snapshot_identity') or
      a.get('binary_sha256')!=m.get('binary_sha256') or a.get('inputs')!=expected):
   raise ValueError('Native archive differs from the complete original manifest')
  origin=archive;receipt={'kind':'explicit-consumed-source-archive','inputs':len(expected),
   'archive_manifest_sha256':sha(archive.parent/'consumed-source-archive.json'),
   'original_manifest_sha256':sha(build/'build.json')}
 for p,h in expected.items():
  path=origin/p
  if path.is_symlink() or not path.is_file() or sha(path)!=h:
   raise ValueError('Changed/missing native consumed input: '+p)
 for item in (m['runtime_identity_header'],{'path':str(build/'obj/lemma-rtl'),'sha256':m['binary_sha256']}):
  if sha(item['path'])!=item['sha256']:raise ValueError('Changed native executable/generated identity')
 return {'manifest':m,'binary':build/'obj/lemma-rtl','validation':receipt}

def rom(build,archive=None):
 build=Path(build).resolve();m=json.loads((build/'build.json').read_text())
 if m.get('schema')!='lemma-product-rom-build/1' or m.get('status')!='PASS':
  raise ValueError('Product ROM lacks a successful genuine build/audit')
 if not m.get('source_inputs') or not m.get('artifacts'):raise ValueError('Missing ROM provenance')
 origin=ROOT
 if archive is not None:
  archive=Path(archive).resolve();a=json.loads((archive.parent/'consumed-source-archive.json').read_text())
  if (a.get('schema')!='lemma-consumed-rom-source-archive/1' or
      a.get('original_manifest_sha256')!=sha(build/'build.json') or a.get('inputs')!=m['source_inputs']):
   raise ValueError('ROM archive differs from the complete original compiler/source inventory')
  origin=archive
 for p,h in m['source_inputs'].items():
  path=origin/relative(p)
  if path.is_symlink() or sha(path)!=h:raise ValueError('Changed ROM compiler/source: '+p)
 for p,h in m['artifacts'].items():
  if relative(p)!=p or sha(build/p)!=h:raise ValueError('Changed ROM artifact: '+p)
 for item in m['tools'].values():
  if not item['path'].startswith('/nix/store/') or sha(item['path'])!=item['sha256']:
   raise ValueError('Changed pinned ROM compiler tool')
 return {'manifest':m,'binary':build/'rom.bin','elf':build/'image.elf'}
