"""Host mutations of the exact compiler-generated local switch artifact contract."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import BACKEND_JUMP_TABLES, validate_backend_jump_tables
from core0_common import Core0Error


def fixture():
    source='Lemma.Platform.RiscV.Firmware.call';role,count,args,effects,cases=BACKEND_JUMP_TABLES[source]
    unit={'role':role,'functions':[dict(source=source,symbol='fw',args=args,effects=effects)]}
    section=' [2] .text PROGBITS 00000000 000040 00002c 00 AX 0 0 4\n [7] .rodata PROGBITS 00000000 000100 000028 00 A 0 0 8\n'
    symbols=''' 1: 00000000 44 FUNC GLOBAL DEFAULT 2 fw
 2: 00000000 0 NOTYPE LOCAL DEFAULT 7 .LJTI0_0
 3: 00000010 0 NOTYPE LOCAL DEFAULT 2 .Lpcrel_hi0
 4: 00000024 0 NOTYPE LOCAL DEFAULT 2 .L0
 5: 00000000 0 NOTYPE LOCAL DEFAULT 2 .L0
 6: 00000028 0 NOTYPE LOCAL DEFAULT 2 .L0
'''
    targets=['.LBB0_1','.LBB0_2','.LBB0_1','.LBB0_2','.LBB0_1']
    companion=symbols.replace('00000024 0 NOTYPE LOCAL DEFAULT 2 .L0','00000024 0 NOTYPE LOCAL DEFAULT 2 .LBB0_1').replace('00000028 0 NOTYPE LOCAL DEFAULT 2 .L0','00000028 0 NOTYPE LOCAL DEFAULT 2 .LBB0_2')
    relocs="Relocation section '.rela.text' at offset 0:\n00000010 0000000200000017 R_RISCV_PCREL_HI20 00000000 .LJTI0_0 + 0\n00000014 0000000300000018 R_RISCV_PCREL_LO12_I 00000010 .Lpcrel_hi0 + 0\nRelocation section '.rela.rodata' at offset 0:\n"
    companion_relocs=relocs
    for i,label in enumerate(targets):
        index,value=(4,36) if label=='.LBB0_1' else (6,40)
        row=f'{i*8:08x} {index:08x}00000002 R_RISCV_64 {value:08x} '
        relocs+=row+'.L0 + 0\n';companion_relocs+=row+label+' + 0\n'
    stack="Relocation section '.rela.stack_sizes' at offset 0:\n00000000 0000000500000002 R_RISCV_64 00000000 .L0 + 0\n"
    relocs+=stack;companion_relocs+=stack
    asm='''fw:
.Lfunc_begin0:
 addi a1, a1, -1
 li a2, 4
 bltu a2, a1, .LBB0_2
 slli a1, a1, 3
.Lpcrel_hi0:
 auipc a2, %pcrel_hi(.LJTI0_0)
 addi a2, a2, %pcrel_lo(.Lpcrel_hi0)
 add a1, a1, a2
 ld a1, 0(a1)
 jr a1
.LBB0_1:
 ret
.LBB0_2:
 ret
.Lfunc_end0:
 .size fw, .Lfunc_end0-fw
 .section .rodata,"a",@progbits
.LJTI0_0:
'''+''.join(' .quad '+target+'\n' for target in targets)
    ir='define { i64, i64 } @fw(i64 %arg0, i64 %arg1, i64 %arg2) {\nentry:\n switch i64 %arg1, label %default [\n'+''.join(' i64 '+str(value)+', label %good\n' for value in cases)+']\ndefault:\n ret { i64, i64 } zeroinitializer\ngood:\n ret { i64, i64 } zeroinitializer\n}\n'
    return dict(section_text=section,symbol_text=symbols,relocation_text=relocs,rodata=b'\0'*40,unit=unit,optimized_ir=ir,optimization='O2',readonly_tables=[],assembly=asm,companion_symbols=companion,companion_relocations=companion_relocs,text=b'\x13\0\0\0'*11,companion_text=b'\x13\0\0\0'*11)


class BackendJumpTableFailures(unittest.TestCase):
    def reject(self,**changes):
        data=fixture();data.update(changes)
        with self.assertRaises(Core0Error):validate_backend_jump_tables(**data)

    def test_source_count_role_signature_and_llvm_switch_domain(self):
        data=fixture();report=validate_backend_jump_tables(**data)
        self.assertEqual(report['jump_table_bytes'],40);self.assertEqual(report['rodata_bytes'],40)
        self.assertTrue(report['jump_tables'][0]['guard']['guard_dominates_load'])
        for field,value in [('source','Lemma.Platform.RiscV.Firmware.other'),('args',['u64']),('effects',[])]:
            unit=copy.deepcopy(data['unit']);unit['functions'][0][field]=value;self.reject(unit=unit)
        self.reject(unit={**data['unit'],'role':'user'});self.reject(optimization='O0')
        self.reject(optimized_ir=data['optimized_ir'].replace('i64 5, label','i64 6, label'))
        self.reject(assembly=data['assembly']+' .quad .LBB0_1\n')

    def test_exact_readonly_full_byte_coverage_and_companion_identity(self):
        data=fixture()
        self.reject(section_text=data['section_text'].replace('00 A 0','00 AW 0'))
        self.reject(rodata=b'\1'+b'\0'*39)
        self.reject(rodata=b'\0'*48,section_text=data['section_text'].replace('000028 00 A','000030 00 A'))
        self.reject(companion_text=b'\0'*44)
        self.reject(companion_relocations=data['companion_relocations'].replace('00000014','00000018'))
        self.reject(symbol_text=data['symbol_text'].replace('.LJTI0_0','.LJTI0_1'))
        self.reject(readonly_tables=[dict(section='.rodata',source='foreign',values=[0],offset=40,bytes=8)])

    def test_symbol_indices_target_ownership_and_alignment(self):
        data=fixture()
        self.reject(relocation_text=data['relocation_text'].replace('0000000400000002','0000000600000002',1))
        self.reject(symbol_text=data['symbol_text'].replace('00000024 0 NOTYPE LOCAL','00000024 0 NOTYPE GLOBAL'))
        self.reject(symbol_text=data['symbol_text'].replace('00000024 0 NOTYPE LOCAL DEFAULT 2','00000024 0 NOTYPE LOCAL DEFAULT 7'))
        self.reject(symbol_text=data['symbol_text'].replace('00000024 0','00000025 0'),relocation_text=data['relocation_text'].replace('00000024 .L0','00000025 .L0'))
        self.reject(symbol_text=data['symbol_text'].replace('00000000 44 FUNC','00000000 36 FUNC'))
        self.reject(relocation_text=data['relocation_text'].replace('.L0 + 0','.L0 + 4',1))
        self.reject(relocation_text=data['relocation_text'].replace('R_RISCV_64','R_RISCV_32',1))
        self.reject(companion_symbols=data['companion_symbols'].replace('00000024 0','00000028 0'))
        self.reject(assembly=data['assembly'].replace('.quad .LBB0_1','.quad .LBB1_1',1))

    def test_unsigned_bound_index_preservation_and_guard_bypass(self):
        data=fixture()
        for before,after in [('li a2, 4','li a2, 5'),('bltu a2, a1','blt a2, a1'),
                             ('addi a1, a1, -1','addi a1, a1, -2'),('slli a1, a1, 3','slli a1, a1, 2'),
                             ('ld a1, 0(a1)','ld a1, 8(a1)'),('jr a1','jr a2'),
                             ('fw:\n','fw:\n j .Lpcrel_hi0\n'),
                             ('slli a1, a1, 3','addi a1, a1, 1\n slli a1, a1, 3')]:
            self.reject(assembly=data['assembly'].replace(before,after))

    def test_unknown_absolute_or_extra_table_entry_relocations(self):
        data=fixture()
        self.reject(relocation_text=data['relocation_text']+"Relocation section '.rela.data' at offset 0:\n00000000 0000000500000002 R_RISCV_64 00000000 .L0 + 0\n")
        self.reject(relocation_text=data['relocation_text'].replace('00000020 0000000400000002','00000028 0000000400000002'))
        self.reject(relocation_text=data['relocation_text'].replace('00000000 0000000500000002','00000000 0000000400000002').replace('R_RISCV_64 00000000 .L0','R_RISCV_64 00000024 .L0'))


if __name__=='__main__':unittest.main()
