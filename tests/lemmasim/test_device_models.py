"""Host hardware checks with literal independently chosen boundary outcomes."""
import json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class DeviceModels(unittest.TestCase):
    def test_behavioral_mutations_are_rejected(self):
        original=(ROOT/'sim/host/lemma_model.c').read_text()
        changes=[('busy', 'if(p->status&1) {paper_error(p,4);return;}', '/* faulty replacement of in-flight refresh */'),
                 ('loss', 'p->count=p->count?1:0; p->contact_deadline=0;', 'p->count=p->count; p->contact_deadline=0;'),
                 ('repeat-reset', 'bool interrupted=(p->status&(1|8))!=0;',
                  'bool interrupted=(p->status&1)!=0;')]
        for name,before,after in changes:
            with self.subTest(name=name),tempfile.TemporaryDirectory(prefix='lemma-mutant-') as d:
                self.assertEqual(original.count(before),1)
                source=Path(d)/'model.c';source.write_text(original.replace(before,after))
                exe=Path(d)/'model'
                subprocess.run(['cc','-std=c11','-O2','-I',str(ROOT/'sim/host'),str(source),
                    str(ROOT/'tests/lemmasim/model_boundaries.c'),'-o',str(exe)],check=True,timeout=60)
                result=subprocess.run([str(exe)],capture_output=True,timeout=20)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(b'Assertion',result.stderr)

    def test_generated_abi_is_current(self):
        subprocess.run(['python3',str(ROOT/'sim/host/generate_constants.py'),'--check'],check=True,timeout=20)
    def test_binding_map_has_no_collisions(self):
        inventory=json.loads((ROOT/'sim/profiles/virt-fixed-inventory-0.1.0.json').read_text())
        ranges=sorted((int(v['base'],0),int(v['base'],0)+int(v['bytes'],0),v['name']) for v in inventory['intervals'])
        self.assertGreater(len(ranges),20)
        for left,right in zip(ranges,ranges[1:]):self.assertLessEqual(left[1],right[0],(left,right))
        irqs=[irq for v in inventory['intervals'] for irq in v.get('irqs',[])]
        self.assertEqual(len(irqs),len(set(irqs)))
        self.assertIn(12,irqs);self.assertIn(13,irqs);self.assertIn(11,irqs)
    def test_literal_boundaries(self):
        with tempfile.TemporaryDirectory(prefix='lemma-device-') as d:
            exe=Path(d)/'model'
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
                '-I',str(ROOT/'sim/host'),str(ROOT/'sim/host/lemma_model.c'),
                str(ROOT/'tests/lemmasim/model_boundaries.c'),'-o',str(exe)],check=True,timeout=60)
            result=subprocess.run([str(exe)],check=True,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.stdout,'literal pen/paper boundary traces observed\n')
if __name__=='__main__':unittest.main()
