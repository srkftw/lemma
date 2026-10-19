"""Real host-file transport tests; fixture bytes are never target execution."""
import copy
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import kernel_shard_artifact as artifact


class ShardArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='lemma-shard-artifact-')
        self.root = Path(self.temporary.name)
        self.source = self.root/'build/kernel/original/shards/O0'
        self.source.mkdir(parents=True)
        (self.source/'result.json').write_bytes(b'{"host_fixture":true}\n')
        (self.source/'bin').mkdir()
        (self.source/'bin/image.elf').write_bytes(b'host fixture bytes, never executed\n')
        (self.source/'bin/image.elf').chmod(0o755)
        (self.source/'received.bin').write_bytes(b'')
        (self.source/'received.bin').chmod(0o640)
        (self.source/'cache').mkdir()
        (self.source/'cache/private-state').write_bytes(b'ephemeral')
        self.transport = self.root/'build/transport'
        self.transport.mkdir()
        self.archive = self.transport/'O0.tar'
        self.manifest = self.transport/'O0.pack.json'
        self.destination = self.root/'build/kernel/restored/shards/O0'
        self.receipt = self.transport/'O0.extract.json'
        self.unrelated = self.root/'build/kernel/unrelated'
        self.unrelated.mkdir()
        (self.unrelated/'keep').write_bytes(b'original unrelated data')

    def tearDown(self):
        self.temporary.cleanup()

    def pack(self, **kwargs):
        return artifact.pack(root=self.root, shard_dir=self.source, optimization='O0',
                             archive=self.archive, receipt=self.manifest, **kwargs)

    def unpack(self, **kwargs):
        return artifact.unpack(**{**dict(root=self.root, optimization='O0', archive=self.archive,
                                        manifest=self.manifest, destination=self.destination,
                                        receipt=self.receipt), **kwargs})

    def assert_unrelated(self):
        self.assertEqual((self.unrelated/'keep').read_bytes(), b'original unrelated data')

    def rewrite_manifest(self, value):
        value['archive_sha256'] = artifact.sha256(self.archive)
        value['archive_bytes'] = self.archive.stat().st_size
        self.manifest.write_text(json.dumps(value))

    def hostile_tar(self, extra, *, duplicate=False):
        value = self.pack()
        with tarfile.open(self.archive, 'w', format=tarfile.USTAR_FORMAT) as stream:
            for name, item in value['files'].items():
                entry = tarfile.TarInfo(name);entry.mode=item['mode'];entry.size=item['size']
                stream.addfile(entry, io.BytesIO((self.source/name).read_bytes()))
            if duplicate:
                entry = tarfile.TarInfo('result.json');entry.size=(self.source/'result.json').stat().st_size
                stream.addfile(entry, io.BytesIO((self.source/'result.json').read_bytes()))
            elif extra is not None:
                stream.addfile(extra, io.BytesIO(b'x'*extra.size) if extra.isreg() else None)
        self.rewrite_manifest(value)

    def test_real_executable_mode_roundtrip_through_0644_artifact_blob(self):
        original = (self.source/'bin/image.elf').stat()
        value = self.pack()
        self.archive.chmod(0o644)
        restored = self.unpack()
        self.assertEqual(restored['schema'], artifact.EXTRACTION_SCHEMA)
        self.assertEqual(restored['file_count'], 3)
        self.assertEqual(stat.S_IMODE((self.destination/'bin/image.elf').stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((self.destination/'received.bin').stat().st_mode), 0o640)
        self.assertFalse((self.destination/'cache').exists())
        self.assertEqual(artifact.inventory(self.root,self.destination), value['files'])
        current = (self.source/'bin/image.elf').stat()
        self.assertEqual((original.st_ino,original.st_mode),(current.st_ino,current.st_mode))
        self.assertEqual(restored['manifest_sha256'], artifact.sha256(self.manifest))
        self.assertFalse(self.receipt.is_relative_to(self.source))
        self.assert_unrelated()

    def test_existing_archive_receipt_or_destination_are_never_replaced(self):
        self.pack();original=self.archive.read_bytes();manifest=self.manifest.read_bytes()
        with self.assertRaisesRegex(artifact.ArtifactError,'replace'):self.pack()
        self.assertEqual(self.archive.read_bytes(),original);self.assertEqual(self.manifest.read_bytes(),manifest)
        self.destination.mkdir(parents=True);(self.destination/'keep').write_bytes(b'existing output')
        with self.assertRaisesRegex(artifact.ArtifactError,'replace'):self.unpack()
        self.assertEqual((self.destination/'keep').read_bytes(),b'existing output')
        self.assertFalse(self.receipt.exists());self.assert_unrelated()

    def test_pack_refuses_symlink_directory_file_fifo_and_special_modes(self):
        for kind in ('file-link','directory-link','fifo','setuid'):
            with self.subTest(kind=kind):
                path=self.source/'bad'
                if kind=='file-link':path.symlink_to(self.unrelated/'keep')
                elif kind=='directory-link':path.symlink_to(self.unrelated,target_is_directory=True)
                elif kind=='fifo':os.mkfifo(path)
                else:path.write_bytes(b'fixture');path.chmod(0o4755)
                try:
                    with self.assertRaises(artifact.ArtifactError):self.pack()
                    self.assertFalse(self.archive.exists());self.assertFalse(self.manifest.exists())
                    self.assert_unrelated()
                finally:path.unlink()

    def test_absolute_parent_noncanonical_and_backslash_names_fail_before_writes(self):
        for name in ('/tmp/escape','../escape','x/../../escape','./result.json','x//y','x\\y',''):
            with self.subTest(name=name):
                self.archive.unlink(missing_ok=True);self.manifest.unlink(missing_ok=True)
                member=tarfile.TarInfo(name);member.size=1
                self.hostile_tar(member)
                with self.assertRaises(artifact.ArtifactError):self.unpack()
                self.assertFalse(self.destination.exists());self.assertFalse(self.receipt.exists());self.assert_unrelated()

    def test_symlinks_hardlinks_directories_and_special_tar_members_are_rejected(self):
        for kind in (tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.DIRTYPE,tarfile.FIFOTYPE,
                     tarfile.CHRTYPE,tarfile.BLKTYPE,tarfile.GNUTYPE_LONGNAME,tarfile.XHDTYPE):
            with self.subTest(kind=kind):
                self.archive.unlink(missing_ok=True);self.manifest.unlink(missing_ok=True)
                member=tarfile.TarInfo('bad');member.type=kind;member.linkname='../unrelated/keep'
                self.hostile_tar(member)
                with self.assertRaises(artifact.ArtifactError):self.unpack()
                self.assertFalse(self.destination.exists());self.assert_unrelated()

    def test_duplicate_tar_names_are_rejected(self):
        self.hostile_tar(None,duplicate=True)
        with self.assertRaisesRegex(artifact.ArtifactError,'duplicate'):self.unpack()
        self.assertFalse(self.destination.exists());self.assert_unrelated()

    def test_truncated_checksum_and_trailing_data_are_rejected(self):
        for kind in ('truncated','checksum','trailing'):
            with self.subTest(kind=kind):
                self.archive.unlink(missing_ok=True);self.manifest.unlink(missing_ok=True)
                value=self.pack();data=self.archive.read_bytes()
                if kind=='truncated':data=data[:700]
                elif kind=='checksum':data=b'X'+data[1:]
                else:data+=b'x'+bytes(511)
                self.archive.write_bytes(data);self.rewrite_manifest(value)
                with self.assertRaises(artifact.ArtifactError):self.unpack()
                self.assertFalse(self.destination.exists());self.assert_unrelated()

    def test_digest_size_mode_unknown_keys_and_prefix_conflicts_are_rejected(self):
        original=self.pack()
        mutations=[]
        value=copy.deepcopy(original);value['files']['result.json']['sha256']='0'*64;mutations.append(value)
        value=copy.deepcopy(original);value['files']['result.json']['mode']=0o4755;mutations.append(value)
        value=copy.deepcopy(original);value['files']['result.json']['size']+=1;value['file_bytes']+=1;mutations.append(value)
        value=copy.deepcopy(original);value['unexpected']=True;mutations.append(value)
        value=copy.deepcopy(original);value['file_count']=0;mutations.append(value)
        value=copy.deepcopy(original);value['files']['bin']=copy.deepcopy(value['files']['result.json']);value['file_count']+=1;value['file_bytes']+=value['files']['bin']['size'];mutations.append(value)
        value=copy.deepcopy(original);value['files']['cache/foreign']=copy.deepcopy(value['files']['result.json']);value['file_count']+=1;value['file_bytes']+=value['files']['cache/foreign']['size'];mutations.append(value)
        for value in mutations:
            with self.subTest(value=value):
                self.manifest.write_text(json.dumps(value))
                with self.assertRaises(artifact.ArtifactError):self.unpack()
                self.assertFalse(self.destination.exists());self.assert_unrelated()

    def test_duplicate_json_keys_and_wrong_optimization_are_rejected(self):
        value=self.pack();encoded=json.dumps(value)
        self.manifest.write_text('{"schema":"wrong",'+encoded[1:])
        with self.assertRaisesRegex(artifact.ArtifactError,'duplicate'):self.unpack()
        self.manifest.write_text(encoded)
        with self.assertRaises(artifact.ArtifactError):self.unpack(optimization='O2')
        self.assertFalse(self.destination.exists())

    def test_member_file_total_archive_and_manifest_bounds_are_enforced(self):
        for limits in (artifact.Limits(members=1),artifact.Limits(file_bytes=1),
                       artifact.Limits(total_bytes=1),artifact.Limits(archive_bytes=512)):
            with self.subTest(limits=limits),self.assertRaises(artifact.ArtifactError):self.pack(limits=limits)
            self.assertFalse(self.archive.exists());self.assertFalse(self.manifest.exists())
        self.pack()
        for limits in (artifact.Limits(members=1),artifact.Limits(file_bytes=1),
                       artifact.Limits(total_bytes=1),artifact.Limits(archive_bytes=512)):
            with self.subTest(limits=limits),self.assertRaises(artifact.ArtifactError):self.unpack(limits=limits)
            self.assertFalse(self.destination.exists())

    def test_escaped_symlink_destination_and_in_producer_receipts_are_rejected(self):
        self.pack()
        for destination in (self.root/'elsewhere/shards/O0',self.root/'build/kernel/../escape/shards/O0'):
            with self.subTest(destination=destination),self.assertRaises(artifact.ArtifactError):self.unpack(destination=destination)
        linked=self.root/'build/kernel/link';linked.symlink_to(self.unrelated,target_is_directory=True)
        with self.assertRaises(artifact.ArtifactError):self.unpack(destination=linked/'shards/O0')
        with self.assertRaises(artifact.ArtifactError):self.unpack(receipt=self.source/'must-not-write.json')
        with self.assertRaises(artifact.ArtifactError):self.unpack(receipt=self.destination/'receipt.json')
        self.assertFalse(self.destination.exists());self.assert_unrelated()

    def test_materialization_failure_removes_only_new_owned_destination(self):
        self.pack();actual=artifact._scan_tar;calls=[]
        def fail(archive,files,limits,*,destination=None):
            calls.append(destination)
            if destination is not None:
                (destination/'partial').write_bytes(b'new partial bytes')
                raise artifact.ArtifactError('explicit host IO failure fixture')
            return actual(archive,files,limits,destination=destination)
        with patch.object(artifact,'_scan_tar',side_effect=fail),self.assertRaisesRegex(artifact.ArtifactError,'IO failure'):
            self.unpack()
        self.assertEqual(len(calls),2)
        self.assertFalse(self.destination.exists());self.assertFalse(self.receipt.exists());self.assert_unrelated()


if __name__=='__main__':unittest.main()
