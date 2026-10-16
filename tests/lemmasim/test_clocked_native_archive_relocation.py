"""Complete host archive fixtures; bytes here are never executed as a machine."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import silicon_guest as guest


def sha(raw): return hashlib.sha256(raw).hexdigest()
def encoded(value): return (json.dumps(value, sort_keys=True) + '\n').encode()


def fixture(directory):
    original = directory / 'original-checkout-does-not-exist'
    source = directory / 'archive' / 'source'
    build = directory / 'relocated-native'
    source.mkdir(parents=True); (build / 'obj').mkdir(parents=True)
    inputs = {}
    def put(name, raw):
        target = source / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw); inputs[name] = sha(raw)
        return inputs[name]
    profile = guest.USB_CLOCKED_PROFILE_FILE
    profile_hash = put(profile, encoded({'schema_version':1,'profile':guest.USB_CLOCKED_PROFILE_NAME}))
    top = 'sim/rtl/lemma_soc.sv'; generated = 'build/binding/lemma_silicon_binding.sv'
    top_hash = put(top,b'fixture RTL source only\n'); generated_hash = put(generated,b'fixture binding only\n')
    config = 'sim/rtl/config.svh'; config_hash = put(config,b'fixture config\n')
    runtime = 'sim/rtl/host/machine_runtime.cpp'; runtime_hash = put(runtime,b'fixture host source\n')
    tools = 'tooling/silicon/sim.nix'; tools_hash = put(tools,b'fixture tool closure\n')
    header = 'build/binding/lemma_silicon_binding.h'; header_hash = put(header,b'fixture host binding\n')
    identities = {}
    for key,name in [('host_adapter','sim/rtl/host/main.cpp'),('build_driver','scripts/silicon_compute.py'),('upstream_patch','tooling/silicon/apply_cvw.py')]:
        identities[key] = {'path':name,'sha256':put(name,('fixture '+key+'\n').encode())}
    dependency = {'schema_version':1,'core':{'repository':'fixture-only-core','revision':'a'*40}}
    put('tooling/silicon/dependencies.json',encoded(dependency))
    m = {'top':'lemma_soc','profile':guest.USB_CLOCKED_PROFILE_NAME,'profile_sha256':profile_hash,
        'configuration':'external-ram-128MiB','core_repository':'fixture-only-core','core_revision':'a'*40,
        'sources':[str(original/top),str(original/generated)],
        'sha256':{str(original/top):top_hash,str(original/generated):generated_hash},
        'configuration_includes':{str(original/config):config_hash},
        'host_runtime':{runtime:runtime_hash},'host_toolchain_inputs':{tools:tools_hash},
        'binding_generator_inputs':{profile:profile_hash},'host_include_dir':str(original/'build/binding'),
        'host_binding_sha256':header_hash,**identities}
    identity = {k:v for k,v in m.items() if k not in ('sources','host_include_dir')}
    identity['identity_schema']='lemmasim-rtl-implementation/2'
    identity['sha256']={'repository/'+top:top_hash,'generated/lemma_silicon_binding.sv':generated_hash}
    identity['configuration_includes']={'repository/'+config:config_hash}
    snapshot=sha(json.dumps(identity,sort_keys=True,separators=(',',':')).encode())
    identity_header='build/native/runtime_identity.h'
    identity_hash=put(identity_header,('#pragma once\n#define LEMMA_RUNTIME_IDENTITY "'+snapshot+'"\n').encode())
    binary=b'host archive fixture, never executed\n';(build/'obj/lemma-rtl').write_bytes(binary)
    m.update(snapshot_identity=snapshot,binary_sha256=sha(binary),runtime_identity_header={'path':str(original/identity_header),'sha256':identity_hash})
    manifest=encoded(m);(build/'build.json').write_bytes(manifest)
    original_build=original/'build/native'
    receipt={'schema_version':1,'profile':m['profile'],'profile_sha256':profile_hash,
        'rtl_build':{'path':str(original_build/'build.json'),'sha256':sha(manifest)},
        'binary':{'path':str(original_build/'obj/lemma-rtl'),'sha256':sha(binary)},
        'rtl_sources':{str(original/name):digest for name,digest in inputs.items()}}
    archive={'schema':'lemma-usb-native-source-archive/2','build_manifest_sha256':sha(manifest),
        'binary_sha256':sha(binary),'snapshot_identity':snapshot,'source_inputs':inputs,
        'selected_profile':{'path':profile,'sha256':profile_hash}}
    (source.parent/'consumed-runtime-receipt.json').write_bytes(encoded(receipt))
    (source.parent/'consumed-source-archive.json').write_bytes(encoded(archive))
    return build,source,original,snapshot


class ClockedArchiveRelocation(unittest.TestCase):
    def test_relocated_build_and_originally_absent_checkout_validate_complete_archive(self):
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name);build,source,original,snapshot=fixture(directory)
            self.assertFalse(original.exists())
            with patch.object(guest,'ROOT',directory/'different-caller'):
                manifest,inputs,_=guest.native_source_archive(build,source,guest.USB_CLOCKED_PROFILE_NAME)
            self.assertEqual(manifest['snapshot_identity'],snapshot)
            self.assertTrue(inputs and all(Path(path).is_relative_to(original) for path in inputs))
            self.assertFalse(original.exists())

    def test_missing_archive_input_never_uses_the_callers_matching_shadow_file(self):
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name);build,source,_,_=fixture(directory)
            shadow=directory/'different-caller';path='sim/rtl/lemma_soc.sv'
            (shadow/path).parent.mkdir(parents=True);(shadow/path).write_bytes((source/path).read_bytes())
            (source/path).unlink()
            with patch.object(guest,'ROOT',shadow),self.assertRaisesRegex(ValueError,'missing or unlisted'):
                guest.native_source_archive(build,source,guest.USB_CLOCKED_PROFILE_NAME)
