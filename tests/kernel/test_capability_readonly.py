"""Host-only mutations of the two exact observed H immutable lookups."""
import copy
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import validate_readonly_pmp_lookup,validate_h_readonly_sections
from core0_common import Core0Error

PMP=[536879103,537141247,553648127,67108895]
MASKS=[35,124,928,1056,1]
KINDS=[1,3,4]
SOURCES=['Lemma.Kernel.MachineServices.expectedPmp','Lemma.User.CapabilityABI.typeMask',
         '_private.Lemma.Kernel.Objects.0.Lemma.Kernel.Objects.initStep']

def fixture():
    unit={'role':'kernel','configuration':'capabilities-development','functions':[
        {'source':SOURCES[0],'symbol':'pmp','args':['u64'],'effects':[]},
        {'source':SOURCES[1],'symbol':'masks','args':['u64'],'effects':[]},
        {'source':SOURCES[2],'symbol':'kinds','args':['u32','u32','u64','u64','u64','u64','u64'],'effects':['checked-access','physical-write']},
        {'source':'Lemma.Kernel.Objects.put','symbol':'put','args':['u64','u64'],'effects':['checked-access','physical-write']}]}
    ir='\n'.join('@switch.table.'+name+' = private unnamed_addr constant ['+str(len(values))+' x i64] ['+', '.join('i64 '+str(x) for x in values)+'], align 8' for name,values in [('pmp',PMP),('masks',MASKS),('kinds',KINDS)])+'\n'+'''define i64 @pmp(i64 %arg0) {
entry:
  %0 = icmp ult i64 %arg0, 4
  br i1 %0, label %switch.lookup, label %if.merge.2
switch.lookup:
  %switch.gep = getelementptr inbounds nuw [4 x i64], ptr @switch.table.pmp, i64 0, i64 %arg0
  %switch.load = load i64, ptr %switch.gep, align 8
  br label %if.merge.2
if.merge.2:
  %if.result7 = phi i64 [ %switch.load, %switch.lookup ], [ 262655, %entry ]
  ret i64 %if.result7
}
define range(i64 0, 1057) i64 @masks(i64 %arg0) {
entry:
  %switch.tableidx = add i64 %arg0, -1
  %0 = icmp ult i64 %switch.tableidx, 5
  br i1 %0, label %switch.lookup, label %if.merge.2
switch.lookup:
  %switch.gep = getelementptr inbounds nuw [5 x i64], ptr @switch.table.masks, i64 0, i64 %switch.tableidx
  %switch.load = load i64, ptr %switch.gep, align 8
  br label %if.merge.2
if.merge.2:
  %if.result19 = phi i64 [ %switch.load, %switch.lookup ], [ 0, %entry ]
  ret i64 %if.result19
}
define { i64, i64 } @kinds(i32 signext %arg0, i32 signext %arg1, i64 %arg2, i64 %arg3, i64 %arg4, i64 %arg5, i64 %arg6) {
entry:
  %call1 = add i64 %arg3, 0
  br label %action.if.else.1
action.if.else.1:
  %bin15 = add i64 %call1, 16
  %0 = icmp ult i32 %arg0, 3
  br i1 %0, label %switch.lookup, label %if.merge.5
switch.lookup:
  %1 = zext nneg i32 %arg0 to i64
  %switch.gep = getelementptr inbounds nuw [3 x i64], ptr @switch.table.kinds, i64 0, i64 %1
  %switch.load = load i64, ptr %switch.gep, align 8
  br label %if.merge.5
if.merge.5:
  %if.result27 = phi i64 [ 0, %action.if.else.1 ], [ %switch.load, %switch.lookup ]
  %action.call.result28 = call { i64, i64 } @put(i64 %bin15, i64 %if.result27)
  ret { i64, i64 } %action.call.result28
}
'''
    return ir,unit

class CapabilityReadonlyFailures(unittest.TestCase):
    def test_exact_globals_guards_types_and_uses_required(self):
        ir,unit=fixture();sites,tables=validate_readonly_pmp_lookup(ir,unit,optimized=True)
        self.assertEqual(len(sites),3);
        self.assertEqual(len(validate_readonly_pmp_lookup(ir,{**unit,'configuration':'ipc-development'},optimized=True)[0]),3);
        with self.assertRaises(Core0Error):validate_readonly_pmp_lookup(ir.replace('[5 x i64] [i64 35, i64 124, i64 928, i64 1056, i64 1]','[4 x i64] [i64 35, i64 124, i64 928, i64 1056]'),unit,optimized=True)
        self.assertEqual([r['values'] for r in tables],[PMP,MASKS,KINDS])
        for bad in [ir.replace('i64 1056','i64 0'),ir.replace('i64 4], align','i64 5], align'),
                    ir.replace('private unnamed_addr constant [3','private unnamed_addr global [3'),
                    ir+'@foreign = constant i64 0\n',ir.replace('%switch.tableidx, 5','%switch.tableidx, 6'),
                    ir.replace('icmp ult i32 %arg0, 3','icmp slt i32 %arg0, 3'),
                    ir.replace('br label %action.if.else.1','br label %switch.lookup'),
                    ir.replace('i64 %if.result27)','i64 0)'),ir.replace('load i64, ptr %switch.gep','load i32, ptr %switch.gep')]:
            with self.assertRaises(Core0Error):validate_readonly_pmp_lookup(bad,unit,optimized=True)
        for role,config,opt in [('user','capabilities-development',True),('firmware','capabilities-development',True),
                                ('kernel','capabilities-development',False)]:
            with self.assertRaises(Core0Error):validate_readonly_pmp_lookup(ir,{**unit,'role':role,'configuration':config},optimized=opt)
        for field,value in [('source','Lemma.Kernel.Development.CapsEntry.other'),('args',['u64']),('effects',[])]:
            bad=copy.deepcopy(unit);bad['functions'][2][field]=value
            with self.assertRaises(Core0Error):validate_readonly_pmp_lookup(ir,bad,optimized=True)

    def test_exact_object_local_extents_bytes_permissions_and_no_relocations(self):
        ir,unit=fixture();tables=validate_readonly_pmp_lookup(ir,unit,optimized=True)[1]
        sections=' [11] .rodata.cst32 PROGBITS 0000000000000000 001000 000020 20 AM 0 0 8\n [7] .rodata PROGBITS 0000000000000000 002000 000050 00 A 0 0 8\n'
        symbols=' 1: 0000000000000000 32 OBJECT LOCAL DEFAULT 11 .Lswitch.table.pmp\n 2: 0000000000000010 40 OBJECT LOCAL DEFAULT 7 .Lswitch.table.masks\n 3: 0000000000000038 24 OBJECT LOCAL DEFAULT 7 .Lswitch.table.kinds\n'
        constants=struct.pack('<4Q',*PMP);rodata=b'\0'*16+struct.pack('<5Q',*MASKS)+struct.pack('<3Q',*KINDS)
        report=validate_h_readonly_sections(sections,symbols,'',constants,rodata,object_file='kernel/program.o',tables=tables)
        self.assertEqual([r['bytes'] for r in report['readonly_tables']],[32,40,24])
        self.assertEqual(validate_h_readonly_sections(sections,symbols,'',constants,rodata,object_file='kernel/program.o',tables=tables,configuration='ipc-development')['configuration'],'ipc-development')
        with self.assertRaises(Core0Error):validate_h_readonly_sections(sections,symbols,'',constants,rodata,object_file='kernel/program.o',tables=tables,configuration='unknown')
        for sec,sym,reloc,cst,ro in [(sections.replace('20 AM','20 AWM'),symbols,'',constants,rodata),
                                   (sections,symbols.replace('LOCAL','GLOBAL'),' ',constants,rodata),
                                   (sections,symbols.replace('0038 24','0030 24'),' ',constants,rodata),
                                   (sections,symbols+' 4: 0000 8 OBJECT LOCAL DEFAULT 7 foreign\n','',constants,rodata),
                                   (sections,symbols,'',constants[:-1]+b'\1',rodata),
                                   (sections,symbols,'',constants,rodata[:-1]+b'\1'),
                                   (sections,symbols,"Relocation section '.rela.rodata' at offset 0:\n0000000000000010 0000000000000000 R_RISCV_64 foreign + 0\n",constants,rodata)]:
            with self.assertRaises(Core0Error):validate_h_readonly_sections(sec,sym,reloc,cst,ro,object_file='kernel/program.o',tables=tables)
        with self.assertRaises(Core0Error):validate_h_readonly_sections(sections,symbols,'',constants,rodata,object_file='firmware/program.o',tables=tables)


    def test_reachable_normal_two_table_inventory_and_missing_source_rejection(self):
        ir,unit=fixture()
        ir=ir[:ir.index('define { i64, i64 } @kinds')]
        ir='\n'.join(line for line in ir.splitlines() if not line.startswith('@switch.table.kinds'))
        unit={**unit,'configuration':'normal','functions':unit['functions'][:2]}
        sites,tables=validate_readonly_pmp_lookup(ir,unit,optimized=True)
        self.assertEqual(len(sites),2);self.assertEqual([row['values'] for row in tables],[PMP,MASKS])
        for bad in [{**unit,'functions':unit['functions'][:1]}, {**unit,'role':'user'}, {**unit,'role':'firmware'}]:
            with self.assertRaises(Core0Error):validate_readonly_pmp_lookup(ir,bad,optimized=True)
        sections=' [11] .rodata.cst32 PROGBITS 0000000000000000 001000 000020 20 AM 0 0 8\n [7] .rodata PROGBITS 0000000000000000 002000 000028 00 A 0 0 8\n'
        symbols=' 1: 0000000000000000 32 OBJECT LOCAL DEFAULT 11 .Lswitch.table.pmp\n 2: 0000000000000000 40 OBJECT LOCAL DEFAULT 7 .Lswitch.table.masks\n'
        raw=struct.pack('<4Q',*PMP);rodata=struct.pack('<5Q',*MASKS)
        report=validate_h_readonly_sections(sections,symbols,'',raw,rodata,object_file='kernel/program.o',tables=tables,configuration='normal')
        self.assertEqual([row['bytes'] for row in report['readonly_tables']],[32,40])
        for sy,ro,cs in [(symbols.replace('0000 40','0008 40'),rodata,sections),
                         (symbols,rodata[:-1]+b'\1',sections),
                         (symbols,rodata,sections.replace('00 A','00 AW'))]:
            with self.assertRaises(Core0Error):validate_h_readonly_sections(cs,sy,'',raw,ro,object_file='kernel/program.o',tables=tables,configuration='normal')

if __name__=='__main__':unittest.main()
