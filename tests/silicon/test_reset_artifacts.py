# SPDX-License-Identifier: Apache-2.0
import copy, json, struct, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import silicon_guest as module

class ResetArtifactReuse(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.root_patch=mock.patch.object(module,'ROOT',self.root);self.root_patch.start();self.addCleanup(self.root_patch.stop)
        self.verify=mock.patch.object(module,'verify_guest_build');self.verify.start();self.addCleanup(self.verify.stop)
        source=self.root/'Lemma/Platform/Silicon/BootROM.lean';source.parent.mkdir(parents=True);source.write_text('literal structured source fixture')
        self.source=source
        common_binary=self.root/'rtl';common_binary.write_bytes(b'rtl-binary-fixture')
        common_build=self.root/'rtl-build.json';common_build.write_text('{}')
        self.tool=self.root/'tool';self.tool.write_bytes(b'immutable-tool-fixture')
        self.old=self.data('old',common_binary,common_build);self.new=self.data('new',common_binary,common_build)
        self.provenance={'tools':{'lean':{'path':'immutable/lean','version':'fixture'}},'lean_source_realization':{'revision':'immutable'},'source_inputs':{'binding':'fixed'}}
        self.old_guest=self.guest_dir('old-guest');self.new_guest=self.guest_dir('new-guest')
        self.old['workloads']={'service':{'build':module.identified(self.old_guest/'build.json'),'provenance':module.identified(self.old_guest/'provenance.json')}}
    def guest_dir(self,name):
        directory=self.root/name;directory.mkdir();(directory/'build.json').write_text(json.dumps({'optimization':'O2'}))
        (directory/'provenance.json').write_text(json.dumps(self.provenance));return directory
    def data(self,name,binary,build):
        directory=self.root/name;directory.mkdir()
        artifacts={'source':module.identified(self.source)}
        for key in ('assembly','object','elf'):
            path=directory/key;path.write_bytes(('same-'+key).encode());artifacts[key]=module.identified(path)
        path=directory/'rom.bin';path.write_bytes(struct.pack('<6I',0x00000513,0x43f00593,0x01559593,0x00100293,0x01f29293,0x00028067))
        artifacts['binary']=module.identified(path)
        audit={'status':'PASS','scope':'literal fixture scope','instruction_words':[0x00000513,0x43f00593,0x01559593,0x00100293,0x01f29293,0x00028067],**artifacts}
        audit_path=directory/'audit.json';audit_path.write_text(json.dumps(audit))
        return {'schema_version':1,'profile':'binding-fixture','profile_sha256':'same-profile','binary':module.identified(binary),
                'rtl_build':module.identified(build),'rtl_sources':{str(self.tool):module.sha(self.tool)},'memory':'external-fixture',
                'physical_conformance':'UNVERIFIED','rom':module.identified(path),'rom_audit':module.identified(audit_path)}
    def alter_audit(self,data,mutate):
        path=Path(data['rom_audit']['path']);audit=json.loads(path.read_text());mutate(audit);path.write_text(json.dumps(audit));data['rom_audit']=module.identified(path)
    def reuse(self):return module.reusable_reset_rom(self.old,self.new,self.new_guest)
    def test_unchanged_verified_artifacts_keep_original_ids(self):
        self.assertEqual(self.reuse(),{'rom':self.old['rom'],'rom_audit':self.old['rom_audit']})
    def test_source_snapshot_change_regenerates_instead_of_reusing(self):
        data=copy.deepcopy(self.provenance);data['source_inputs']['binding']='changed';(self.new_guest/'provenance.json').write_text(json.dumps(data));self.assertIsNone(self.reuse())
    def test_old_guest_audit_rejection_prevents_reuse(self):
        module.verify_guest_build.side_effect=ValueError('real audit rejected');self.assertIsNone(self.reuse())
    def test_binding_change_prevents_reuse(self):
        self.new['profile_sha256']='changed';self.assertIsNone(self.reuse())
    def test_tool_file_tampering_rejects(self):
        self.tool.write_bytes(b'changed');self.assertRaises(ValueError,self.reuse)
    def test_old_generated_object_tampering_rejects(self):
        audit=json.loads(Path(self.old['rom_audit']['path']).read_text());Path(audit['object']['path']).write_bytes(b'changed');self.assertRaises(ValueError,self.reuse)
    def test_new_validated_but_different_elf_rejects_reuse(self):
        def change(audit):
            path=Path(audit['elf']['path']);path.write_bytes(b'different');audit['elf']=module.identified(path)
        self.alter_audit(self.new,change);self.assertRaises(ValueError,self.reuse)
    def test_audit_fail_status_rejects(self):
        self.alter_audit(self.old,lambda a:a.update(status='FAIL'));self.assertRaises(ValueError,self.reuse)
    def test_unknown_instruction_inventory_rejects(self):
        self.alter_audit(self.old,lambda a:a.update(instruction_words=[0]*6));self.assertRaises(ValueError,self.reuse)
    def test_changed_binary_with_claimed_good_inventory_rejects(self):
        path=Path(self.old['rom']['path']);path.write_bytes(bytes(24));self.old['rom']=module.identified(path)
        self.alter_audit(self.old,lambda a:a.update(binary=self.old['rom']));self.assertRaises(ValueError,self.reuse)
    def test_atomic_publication_keeps_old_on_failure(self):
        publication=self.root/'prepared.json';publication.write_text('{"old":true}')
        with mock.patch.object(module,'PREPARED',publication),mock.patch.object(module.os,'replace',side_effect=OSError('interrupted')):
            self.assertRaises(OSError,module.publish_prepared,{'new':True})
        self.assertEqual(publication.read_text(),'{"old":true}');self.assertEqual(list(self.root.glob('prepared.json.*')),[])
    def test_atomic_publication_publishes_complete_json(self):
        publication=self.root/'prepared.json'
        with mock.patch.object(module,'PREPARED',publication):module.publish_prepared({'workloads':{'service':'literal-existing','initializer':'literal-new'}})
        self.assertEqual(json.loads(publication.read_text()),{'workloads':{'service':'literal-existing','initializer':'literal-new'}})

if __name__=='__main__':unittest.main(verbosity=2)
