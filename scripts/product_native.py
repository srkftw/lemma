#!/usr/bin/env python3
"""Exact product-ROM/native input validation; never installs a running image."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
PROFILE='lemma-silicon-dev/0.7.0'
NEXT_PROFILE='lemma-silicon-dev/0.9.0'
EXECUTED_PROFILE='lemma-silicon-dev/0.10.0'
PROFILES={EXECUTED_PROFILE:('lemmasim-silicon-product-executed-boot','Lemma.Boot.RecoveryExecuted.entry',0x000a000300010001),PROFILE:('lemmasim-silicon-product-boot','Lemma.Boot.Recovery.entry',0x0007000300010001),NEXT_PROFILE:('lemmasim-silicon-product-next-boot','Lemma.Boot.RecoveryNext.entry',0x0009000300010001)}

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for part in iter(lambda:f.read(1048576),b''):h.update(part)
 return h.hexdigest()

def relative(path,original_root=None):
 p=Path(path)
 if '..' in p.parts:raise ValueError('Unmapped product native input')
 if p.is_absolute():p=p.relative_to(ROOT if original_root is None else original_root)
 if not p.parts or '..' in p.parts:raise ValueError('Unmapped product native input')
 return p.as_posix()

def archived_original_root(manifest):
 """Logical checkout prefix from the original top source; never read it.

 The complete archive/manifest/binary identities remain mandatory. All absolute
 consumed paths must use this one prefix; suffix guessing and filesystem
 fallback are forbidden.
 """
 sources=manifest.get('sources')
 if manifest.get('top')!='lemma_soc' or not isinstance(sources,list) or not sources or any(not isinstance(s,str) for s in sources):
  raise ValueError('Archived native top/source inventory malformed')
 anchors=[Path(s) for s in sources if Path(s).is_absolute() and Path(s).parts[-3:]==('sim','rtl','lemma_soc.sv')]
 if len(anchors)!=1 or '..' in anchors[0].parts:raise ValueError('Archived native original checkout prefix is not unique')
 return anchors[0].parents[2]

def native(build,archive=None,profile=PROFILE):
 """Require current inputs or the explicit complete original consumed archive."""
 build=Path(build).resolve();m=json.loads((build/'build.json').read_text())
 if profile not in PROFILES or m.get('profile')!=profile or m.get('configuration')!='external-ram-128MiB':
  raise ValueError('Product requires the selected canonical versioned native core')
 a=None;original_root=ROOT
 if archive is not None:
  archive=Path(archive).resolve();a=json.loads((archive.parent/'consumed-source-archive.json').read_text())
  if (a.get('schema')!='lemma-consumed-native-source-archive/1' or a.get('original_manifest_sha256')!=sha(build/'build.json') or
      a.get('snapshot_identity')!=m.get('snapshot_identity') or a.get('binary_sha256')!=m.get('binary_sha256') or
      not isinstance(a.get('inputs'),dict) or not a['inputs']):
   raise ValueError('Native archive identity/inventory differs')
  original_root=archived_original_root(m)
 expected={}
 def add(p,h):
  p=relative(p,original_root)
  if p in expected and expected[p]!=h:raise ValueError('Conflicting native input identity')
  if not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h):
   raise ValueError('Malformed native input identity')
  expected[p]=h
 for key in ('sha256','configuration_includes','host_runtime','host_toolchain_inputs','binding_generator_inputs'):
  if not isinstance(m.get(key),dict) or not m[key]:raise ValueError('Missing native consumed inputs')
  for p,h in m[key].items():add(p,h)
 for key in ('host_adapter','build_driver','upstream_patch'):add(m[key]['path'],m[key]['sha256'])
 add(Path(m['host_include_dir'])/'lemma_silicon_binding.h',m['host_binding_sha256'])
 add('sim/profiles/'+profile.replace('/','-')+'.json',m['profile_sha256'])
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
   'original_manifest_sha256':sha(build/'build.json'),'original_source_root':str(original_root)}
 for p,h in expected.items():
  path=origin/p
  if path.is_symlink() or not path.is_file() or sha(path)!=h:
   raise ValueError('Changed/missing native consumed input: '+p)
 identity=m['runtime_identity_header'];header=Path(identity['path'])
 if archive is not None:
  # Generated output belongs to this explicit build, not the old checkout.
  # Its original path remains metadata; never consult it during admission.
  relative(header,original_root)
  if not header.is_absolute() or header.parts[-2:]!=('generated','lemma_runtime_identity.h'):
   raise ValueError('Archived native generated identity path malformed')
  header=build/'generated/lemma_runtime_identity.h'
 if header.is_symlink() or not header.is_file() or sha(header)!=identity['sha256']:
  raise ValueError('Changed/missing native generated identity')
 if archive is not None and header.read_text()!=('#pragma once\n#define LEMMA_RUNTIME_IDENTITY "'+m['snapshot_identity']+'"\n'):
  raise ValueError('Archived native generated identity differs from implementation')
 binary=build/'obj/lemma-rtl'
 if binary.is_symlink() or sha(binary)!=m['binary_sha256']:
  raise ValueError('Changed native executable')
 return {'manifest':m,'binary':build/'obj/lemma-rtl','validation':receipt}

def rom(build,archive=None,profile=PROFILE):
 build=Path(build).resolve();m=json.loads((build/'build.json').read_text())
 if profile not in PROFILES:raise ValueError('Unsupported exact product ROM hardware profile')
 if m.get('schema')!='lemma-product-rom-build/1' or m.get('status')!='PASS':
  raise ValueError('Product ROM lacks a successful genuine build/audit')
 if not m.get('source_inputs') or not m.get('artifacts'):raise ValueError('Missing ROM provenance')
 unit=json.loads((build/'unit.json').read_text());configuration,root,compatibility=PROFILES[profile]
 if unit.get('configuration')!=configuration or unit.get('root')!=root or unit.get('contract_version')!='core0-boot-v0.1':
  raise ValueError('ROM root/configuration differs from selected hardware profile')
 if profile in (NEXT_PROFILE,EXECUTED_PROFILE) and (unit.get('hardware_profile')!=profile or unit.get('image_compatibility')!=compatibility or m.get('hardware_profile')!=profile or m.get('image_compatibility')!=compatibility):
  raise ValueError('Successor Product ROM compatibility/profile identity differs')
 if profile==PROFILE and any(k in unit for k in ('hardware_profile','image_compatibility')):
  raise ValueError('Historical Product7 ROM cannot carry successor identity')
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
