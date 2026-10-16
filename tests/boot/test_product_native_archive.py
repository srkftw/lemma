"""Host archive admission only; fixtures are never executed as machines."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import product_native as native


def digest(raw):return hashlib.sha256(raw).hexdigest()

class ProductNativeArchive(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.old=self.base/'absent-original';self.current=self.base/'different-source'
        self.archive=self.base/'archive/source';self.archive.mkdir(parents=True)
        self.build=self.base/'build';(self.build/'obj').mkdir(parents=True)
        payloads={'sim/rtl/lemma_soc.sv':b'module fixture', 'build/deps/config.vh':b'configuration',
          'sim/rtl/host/machine_runtime.cpp':b'host fixture','flake.lock':b'pinned',
          'scripts/binding.py':b'generator','sim/rtl/host/main.cpp':b'adapter',
          'scripts/silicon_compute.py':b'builder','tooling/core.patch':b'patch',
          'build/deps/binding/lemma_silicon_binding.h':b'header',
          'sim/profiles/lemma-silicon-dev-0.10.0.json':b'profile fixture'}
        self.inputs={n:digest(raw)for n,raw in payloads.items()}
        for n,raw in payloads.items():
            p=self.archive/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        binary=b'NONEXECUTABLE HOST VALIDATION FIXTURE';(self.build/'obj/lemma-rtl').write_bytes(binary)
        identity=('#pragma once\n#define LEMMA_RUNTIME_IDENTITY "'+'1'*64+'"\n').encode()
        (self.build/'generated').mkdir();(self.build/'generated/lemma_runtime_identity.h').write_bytes(identity)
        self.manifest={'profile':native.EXECUTED_PROFILE,'configuration':'external-ram-128MiB','top':'lemma_soc',
          'sources':[str(self.old/'sim/rtl/lemma_soc.sv')],
          'sha256':{'sim/rtl/lemma_soc.sv':self.inputs['sim/rtl/lemma_soc.sv']},
          'configuration_includes':{str(self.old/'build/deps/config.vh'):self.inputs['build/deps/config.vh']},
          'host_runtime':{'sim/rtl/host/machine_runtime.cpp':self.inputs['sim/rtl/host/machine_runtime.cpp']},
          'host_toolchain_inputs':{'flake.lock':self.inputs['flake.lock']},
          'binding_generator_inputs':{'scripts/binding.py':self.inputs['scripts/binding.py']},
          'host_include_dir':str(self.old/'build/deps/binding'),
          'host_binding_sha256':self.inputs['build/deps/binding/lemma_silicon_binding.h'],
          'profile_sha256':self.inputs['sim/profiles/lemma-silicon-dev-0.10.0.json'],
          'snapshot_identity':'1'*64,'binary_sha256':digest(binary),
          'runtime_identity_header':{'path':str(self.old/'build/native/generated/lemma_runtime_identity.h'),'sha256':digest(identity)}}
        for key,n in [('host_adapter','sim/rtl/host/main.cpp'),('build_driver','scripts/silicon_compute.py'),('upstream_patch','tooling/core.patch')]:
            self.manifest[key]={'path':n,'sha256':self.inputs[n]}
        self.publish()
        self.root=patch.object(native,'ROOT',self.current);self.root.start();self.addCleanup(self.root.stop)
    def publish(self):
        raw=(json.dumps(self.manifest,sort_keys=True)+'\n').encode();(self.build/'build.json').write_bytes(raw)
        self.receipt={'schema':'lemma-consumed-native-source-archive/1','original_manifest_sha256':digest(raw),
          'snapshot_identity':self.manifest['snapshot_identity'],'binary_sha256':self.manifest['binary_sha256'],
          'inputs':copy.deepcopy(self.inputs)}
        self.write_receipt()
    def write_receipt(self):
        (self.archive.parent/'consumed-source-archive.json').write_text(json.dumps(self.receipt)+'\n')
    def admit(self):return native.native(self.build,self.archive,native.EXECUTED_PROFILE)
    def test_complete_original_archive_works_from_different_checkout(self):
        self.assertFalse(self.old.exists())
        result=self.admit();self.assertEqual(result['validation']['inputs'],len(self.inputs))
        self.assertEqual(result['validation']['original_source_root'],str(self.old))
        self.assertFalse(self.old.exists())
    def test_missing_archive_member_never_falls_back_to_current_checkout(self):
        n='sim/rtl/lemma_soc.sv';p=self.current/n;p.parent.mkdir(parents=True);p.write_bytes((self.archive/n).read_bytes());(self.archive/n).unlink()
        with self.assertRaisesRegex(ValueError,'Changed/missing'):self.admit()
    def test_removed_local_identity_never_uses_still_present_original(self):
        old=Path(self.manifest['runtime_identity_header']['path']);old.parent.mkdir(parents=True)
        local=self.build/'generated/lemma_runtime_identity.h';old.write_bytes(local.read_bytes());local.unlink()
        with self.assertRaisesRegex(ValueError,'Changed/missing native generated identity'):self.admit()
    def test_relocated_identity_cannot_relabel_implementation(self):
        self.manifest['snapshot_identity']='2'*64;self.publish()
        with self.assertRaisesRegex(ValueError,'differs from implementation'):self.admit()
    def test_identity_path_cannot_escape_original_checkout(self):
        self.manifest['runtime_identity_header']['path']=str(self.base/'sibling/generated/lemma_runtime_identity.h');self.publish()
        with self.assertRaises(ValueError):self.admit()
    def test_changed_archive_member_rejects(self):
        (self.archive/'sim/rtl/lemma_soc.sv').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Changed/missing'):self.admit()
    def test_incomplete_receipt_rejects(self):
        del self.receipt['inputs']['flake.lock'];self.write_receipt()
        with self.assertRaisesRegex(ValueError,'complete original manifest'):self.admit()
    def test_ambiguous_original_root_rejects(self):
        self.manifest['sources'].append(str(self.base/'other/sim/rtl/lemma_soc.sv'));self.publish()
        with self.assertRaisesRegex(ValueError,'not unique'):self.admit()
    def test_absolute_input_outside_declared_original_root_rejects(self):
        self.manifest['configuration_includes']={str(self.base/'sibling/build/deps/config.vh'):self.inputs['build/deps/config.vh']};self.publish()
        with self.assertRaises(ValueError):self.admit()
    def test_tampered_original_manifest_receipt_rejects(self):
        self.receipt['original_manifest_sha256']='0'*64;self.write_receipt()
        with self.assertRaisesRegex(ValueError,'identity/inventory'):self.admit()
    def test_nonarchive_mode_keeps_current_checkout_boundary(self):
        with self.assertRaises(ValueError):native.native(self.build,None,native.EXECUTED_PROFILE)

if __name__=='__main__':unittest.main()
