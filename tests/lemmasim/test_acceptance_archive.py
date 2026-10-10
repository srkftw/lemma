"""Literal export identity/failure tests; these are not guest acceptance."""
from importlib.machinery import SourceFileLoader
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
loader = SourceFileLoader('acceptance_archive_command', str(ROOT / 'scripts/lemmasim'))
spec = importlib.util.spec_from_loader(loader.name, loader)
sim = importlib.util.module_from_spec(spec);loader.exec_module(sim)
COMMIT, TREE = '1' * 40, '2' * 40


def fixture(root):
    full = root / 'full';full.mkdir()
    metadata = {'schema_version':1,'commit':COMMIT,'source_tree':TREE,
                'core':'lemma-one-core/0.1.0','profile':'lemmasim-virt/0.1.0',
                'qemu':{'path':'/literal/qemu','sha256':'3'*64},'qemu_closure':{'literal':'test-only'}}
    for role in ('notebook','initializer'):
        directory = root / role;directory.mkdir()
        (directory/'image.elf').write_bytes(b'literal uncompiled '+role.encode())
        for name,value in [('build.json',{'status':'BUILT'}),('audit.json',{'status':'PASS'}),
                           ('provenance.json',{'source_commit':COMMIT,'dirty_paths':[]})]:sim.write_json(directory/name,value)
        if role=='notebook':sim.write_json(directory/'capacity.json',{'status':'PASS'})
        metadata[role]={'path':str(directory/'image.elf'),'sha256':sim.sha(directory/'image.elf'),
                        'artifacts':sim.guest_artifact_identity(directory/'image.elf',require_capacity=role=='notebook')}
    sim.write_json(full/'prepared.json',metadata)
    cases=[]
    for index,(workflow,geometry) in enumerate([('basic',[1650,2200]),('basic',[1650,2200]),
            ('editing',[1650,2200]),('basic',[1404,1872]),('loss-overflow',[1650,2200]),
            ('loss-disconnect',[1650,2200]),('loss-watchdog',[1650,2200]),('workload',[1650,2200])]):
        row={'workflow':workflow,'geometry':geometry}
        for key,digest in [('observation','sha256'),('cold_observation','cold_sha256')]:
            path=full/f'case{index}'/(key+'.json');sim.write_json(path,{'status':'PASS'})
            row[key]=str(path);row[digest]=sim.sha(path)
        cases.append(row)
    for folder in ('basic','workload','native-pointer'):
        directory=full/folder;directory.mkdir()
        disk=directory/('record.raw' if folder=='native-pointer' else 'disk.raw');disk.write_bytes(b'literal stable media '+folder.encode())
        exports=directory/'committed';exports.mkdir();(exports/'object.bin').write_bytes(b'literal exported guest bytes')
        sim.write_json(exports/'result.json',{'status':'OBSERVED','image_sha256':sim.sha(disk),
                       'objects':[{'export':'object.bin','sha256':sim.sha(exports/'object.bin')}]})
        run=directory/('session/run' if folder=='native-pointer' else 'run');run.mkdir(parents=True)
        for name in ('devices.jsonl','media.jsonl','serial.bin','raw.bin','visible.ppm','descriptor.bin','machine.dtb'):
            (run/name).write_bytes(('literal controller '+name).encode())
        sim.write_json(run/'result.json',{'process_reaped':True,'final_media_sha256':sim.sha(disk)})
    for name in ('input.bin','input.json','cold-navigation.bin','cold-navigation.json'):(full/'workload'/name).write_bytes(b'literal raw navigation')
    sim.write_json(full/'workload/owned-memory/result.json',{'status':'OBSERVED'})
    (full/'workload/owned-memory/0001-ownership.bin').write_bytes(b'literal readonly owned snapshot')
    session=full/'native-pointer/session';run=session/'run'
    (session/'initial.raw').write_bytes(b'literal captured initial medium');(session/'qemu.rr').write_bytes(b'literal QEMU RR input')
    initial_hash=sim.sha(session/'initial.raw')
    identity={'schema_version':1,**sim.RUN_POLICY,'build':metadata,'mode':'developer','geometry':'1650x2200',
              'fault_inputs':{},'initial_media_sha256':initial_hash,'rr_sha256':sim.sha(session/'qemu.rr'),
              'captured_raw_sha256':sim.sha(run/'raw.bin'),'machine_descriptor_sha256':sim.sha(run/'descriptor.bin'),
              'actual_boot_dtb_sha256':sim.sha(run/'machine.dtb')}
    recorded={'status':'HOST_STOPPED_AT_DEADLINE','process_reaped':True,'build_identity':metadata,
              'argv':['/literal/qemu'],'guest_sha256':metadata['notebook']['sha256'],
              'mode':'developer','geometry':[1650,2200],'fault_inputs':{},'initial_media_sha256':initial_hash,
              'media_backend':'lemma-durable/1','random_seed':'0x4c454d4d413031',
              'machine_descriptor_sha256':identity['machine_descriptor_sha256'],'actual_boot_dtb_sha256':identity['actual_boot_dtb_sha256'],
              'final_media_sha256':sim.sha(full/'native-pointer/record.raw'),'replay_boundary':{'icount':128}}
    sim.write_json(run/'result.json',recorded);sim.write_json(session/'identity.json',identity)
    sim.write_json(run/'process.json',{'recording':True,'replaying':False,'mode':'developer'})
    replay=full/'replay-observations';replay.mkdir()
    for name in ('devices.jsonl','media.jsonl','serial.bin','raw.bin','visible.ppm','descriptor.bin','machine.dtb'):
        (replay/name).write_bytes((run/name).read_bytes())
    sim.write_json(replay/'result.json',{**recorded,'status':'REPLAY_BOUNDARY_REACHED'})
    sim.write_json(replay/'comparison.json',{'status':'PASS','observations':{name:True for name in (
        'final_media_sha256','devices','storage','document_report','machine_descriptor_sha256','actual_boot_dtb_sha256',
        'devices.jsonl','visible.ppm','raw.bin','descriptor.bin','machine.dtb','serial.bin','ordered_medium_operations')}})
    native={'status':'PASS','record':str(session),'replay':str(replay)}
    sim.write_json(full/'native-pointer/result.json',native)
    for name in ('ingress.json','workflow.json','cold.json','reset.json'):sim.write_json(full/'native-pointer'/name,{'status':'PASS'})
    for name in ('pointer-commands.json','input.json'):sim.write_json(full/'native-pointer'/name,{'literal':'test-only'})
    for folder in ('publication-negative','input-negative'):
        (full/folder).mkdir();(full/folder/'negative-source.patch').write_bytes(b'literal quarantined source patch')
        summary={'status':'PASS','candidate_commit':COMMIT,'cases':[{'name':'positive','oracle_status':'PASS'},{'name':'negative','oracle_status':'FAIL'}],
                 'source_patch_sha256':sim.sha(full/folder/'negative-source.patch')}
        sim.write_json(full/folder/'result.json',summary);sim.write_json(full/folder/'negative-image.json',{'qualification':'UNQUALIFIED_NEGATIVE_ONLY'})
    sim.write_json(full/'faults/result.json',{'status':'PASS','fault_count':15})
    result={'status':'PASS','lane':'full','with_o0':True,'source':{'commit':COMMIT,'tree':TREE,'clean':True},
            'qemu_closure':metadata['qemu_closure'],'cases':cases,'initial_media_sha256':initial_hash,
            'faults':{'status':'PASS','fault_count':15},'publication_negative':{'status':'PASS'},
            'input_negative':{'status':'PASS'},'native_pointer':native}
    sim.write_json(full/'result.json',result)
    return full,result


class AcceptanceArchive(unittest.TestCase):
    def selection(self,full):
        with patch.object(sim,'validate_backend_identity'), patch.object(sim.subprocess,'check_output',return_value=TREE+'\n'):
            return sim.acceptance_archive_inputs(full)

    def test_literal_selection_includes_media_bytes_replay_and_fixed_guest_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            full,_=fixture(Path(folder));inventory,files=self.selection(full)
            names={name for _,name in files}
            for name in ('capture/initial.raw','capture/qemu.rr','capture/run/raw.bin','capture/run/visible.ppm',
                         'replay/comparison.json','artifacts/notebook/image.elf','artifacts/notebook/capacity.json',
                         'documents/workload/stable.raw','documents/basic/committed/object.bin',
                         'documents/native-pointer/committed/object.bin','workload/owned-memory/0001-ownership.bin'):
                self.assertIn(name,names)
            self.assertFalse(any('experimental-checkout' in name for name in names))
            self.assertEqual(inventory['source']['commit'],COMMIT)

    def test_missing_failed_dirty_mutated_or_unreaped_evidence_refuses_export(self):
        for change in ('failed','partial','dirty','workflow','media','replay','unreaped','symlink','parent_escape'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                full,result=fixture(Path(folder))
                if change=='failed':result['status']='FAIL'
                elif change=='partial':result['cases'].pop()
                elif change=='dirty':result['source']['clean']=False
                elif change=='workflow':Path(result['cases'][0]['observation']).unlink()
                elif change=='media':(full/'workload/disk.raw').write_bytes(b'changed')
                elif change=='replay':sim.write_json(full/'replay-observations/comparison.json',{'status':'PASS','observations':{}})
                elif change=='unreaped':sim.write_json(full/'basic/run/result.json',{'process_reaped':False})
                elif change=='symlink':
                    p=full/'workload/input.bin';p.unlink();p.symlink_to(full/'workload/cold-navigation.bin')
                else:
                    escaped=Path(folder)/'outside.json';sim.write_json(escaped,{'status':'PASS'})
                    result['cases'][0]['observation']=str(full/'case0'/'..'/'..'/'outside.json')
                    result['cases'][0]['sha256']=sim.sha(escaped)
                sim.write_json(full/'result.json',result)
                with self.assertRaises((sim.Failure,OSError)):
                    self.selection(full)

    def test_actual_small_git_bundle_retains_exact_implementation_and_export_is_immutable(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);repo=root/'source';repo.mkdir()
            def git(*args):return subprocess.check_output(['git',*args],cwd=repo,text=True,stderr=subprocess.DEVNULL,timeout=10).strip()
            git('init');(repo/'source.txt').write_text('literal source bundle fixture')
            git('add','source.txt');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','literal')
            commit=git('rev-parse','HEAD');tree=git('rev-parse','HEAD^{tree}')
            full=root/'full';full.mkdir();observed=full/'result.json';observed.write_bytes(b'literal validated selection')
            destination=root/'offline.tar.gz'
            inventory={'source':{'commit':commit,'tree':tree,'clean':True}}
            with patch.object(sim,'ROOT',repo), patch.object(sim,'acceptance_archive_inputs',return_value=(inventory,[(observed,'acceptance/result.json')])):
                sim.archive_acceptance(SimpleNamespace(acceptance=full,to=destination))
                with self.assertRaisesRegex(sim.Failure,'already exists'):
                    sim.archive_acceptance(SimpleNamespace(acceptance=full,to=destination))
            with tarfile.open(destination) as archive:
                exported=json.load(archive.extractfile('inventory.json'))
                for item in exported['files']:
                    self.assertEqual(sim.hashlib.sha256(archive.extractfile(item['path']).read()).hexdigest(),item['sha256'])
                bundle=root/'implementation.bundle';bundle.write_bytes(archive.extractfile('source/implementation.bundle').read())
            self.assertEqual(subprocess.check_output(['git','bundle','list-heads',str(bundle)],text=True,timeout=10).strip(),commit+' refs/heads/implementation')
            self.assertEqual(observed.read_bytes(),b'literal validated selection')


if __name__=='__main__':unittest.main()
