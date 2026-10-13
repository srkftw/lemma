"""Mutations of actual LLVM/MC output, not target programs or execution proof."""
import copy,json
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from core0_common import Core0Error
from audit_kernel import validate_ble_header_intrinsic,_jump_assembly_guard

class BLEOptimizer(unittest.TestCase):
 def test_generated_header_and_exact_intrinsic_scope(self):
  data=json.loads((ROOT/'tests/kernel/fixtures/ble-header-generated.json').read_text())
  for key,opt in [('pre',False),('optimized',True)]:
   report=validate_ble_header_intrinsic(data['ir'][key],data['unit'],optimized=opt,optimization='O2')
   self.assertEqual(report['output_bits'],[2,3])
  ir=data['ir']['optimized']
  for mutated in [ir.replace('and i4 %trunc, 3','and i4 %trunc, 7'),
                  ir.replace('bitreverse.i4','bitreverse.i8'),
                  ir+'define i4 @extra(i4 %x) {\nentry:\n%y = call i4 @llvm.bitreverse.i4(i4 %x)\nret i4 %y\n}\n']:
   with self.assertRaises(Core0Error):validate_ble_header_intrinsic(mutated,data['unit'],optimized=True,optimization='O2')
  for unit in [{**data['unit'],'configuration':'lemmasim-silicon-power-probe'},
               {**data['unit'],'role':'user'}]:
   with self.assertRaises(Core0Error):validate_ble_header_intrinsic(ir,unit,optimized=True,optimization='O2')
  changed=copy.deepcopy(data['unit']);next(row for row in changed['functions'] if row['source']=='Lemma.Radio.BLE.Link.headerResult')['effects']=['physical-read']
  with self.assertRaises(Core0Error):validate_ble_header_intrinsic(ir,changed,optimized=True,optimization='O2')

 def test_generated_pair_each_unsigned_guard_and_exact_jr_targets(self):
  data=json.loads((ROOT/'tests/kernel/fixtures/dtb-leaf-pair-generated.json').read_text())
  args={k:data[k] for k in ('assembly','symbol','source','configuration')}
  for table in data['tables']:
   report=_jump_assembly_guard(**args,**table)
   self.assertTrue(report['guard_dominates_load'])
   self.assertTrue(report['each_transfer_uses_own_targets'])
   self.assertEqual(report['closed_dtb_pair_transfers'],2)
  table=data['tables'][0]
  asm=data['assembly']
  for altered in [asm.replace('li\ta4, 14','li\ta4, 15'),
                  asm.replace('li\ta5, 8','li\ta5, 9'),
                  asm.replace('jr\ta4','jr\ta2'),
                  asm.replace('jr\ta2','jr\ta2\n\tjr\ta4')]:
   self.assertNotEqual(altered,asm)
   with self.assertRaises(Core0Error):_jump_assembly_guard(**{**args,'assembly':altered},**table)
  # Changing a sparse role hole into another valid local block must fail,
  # even though the target is in the owning function.
  altered=asm.replace('.LJTI569_1:\n\t.quad\t.LBB569_24\n\t.quad\t.LBB569_43\n\t.quad\t.LBB569_33',
                      '.LJTI569_1:\n\t.quad\t.LBB569_24\n\t.quad\t.LBB569_43\n\t.quad\t.LBB569_24')
  self.assertNotEqual(altered,asm)
  with self.assertRaises(Core0Error):_jump_assembly_guard(**{**args,'assembly':altered},**table)
  with self.assertRaises(Core0Error):_jump_assembly_guard(**{**args,'source':'Lemma.Other'},**table)

if __name__=='__main__':unittest.main()
