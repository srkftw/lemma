import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_kernel import audit, validate_unit, validate_ir, validate_machine, _primitive_declaration_matches, function_ranges, validate_catalog, validate_startup_case, validate_pmp_constant_section, MACHINE_SYMBOLS, M_SYMBOLS, PRIMITIVE_EFFECTS
from build_kernel import CONTRACTS, ROLE_ROOTS, configuration_roots, module_closure, validate_configuration_stage
from core0_common import Core0Error

def unit(role='user',configuration='normal'):
    roots = [{'id':index+1,'source':source,'symbol':'lemma_'+role+'_root_'+str(index),'args':list(args)} for index,(source,args) in enumerate(configuration_roots(configuration)[role])]
    return {'schema_version':1,'artifact_category':('production' if configuration=='normal' else 'development')+'-'+role+'-unit','configuration':configuration,'contract_version':CONTRACTS[role],
            'role':role,'roots':roots,'functions':[{**{key:value for key,value in row.items() if key!='id'},'effects':[]} for row in roots],
            'used_execution_ops':[],'used_device_ops':[],'used_loops':[]}

class KernelAuditFailures(unittest.TestCase):
    def reject(self,value,role='user'):
        with self.assertRaises(Core0Error): validate_unit(value,role)
    def test_configuration_cannot_relabel_or_import_development_roots(self):
        dev=unit('kernel','frames-development')
        validate_unit(dev,'kernel',configuration='frames-development')
        with self.assertRaises(Core0Error): validate_unit(dev,'kernel')
        dev['configuration']='normal'; dev['artifact_category']='production-kernel-unit'
        self.reject(dev,'kernel')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); path=root/'Lemma/Kernel/Entry.lean'; path.parent.mkdir(parents=True)
            path.write_text('import Lemma.Kernel.Development.Hidden\n')
            with self.assertRaisesRegex(Core0Error,'development code'): module_closure(root,'Lemma.Kernel.Entry')
    def test_machine_origin_case_cannot_select_supervisor_or_development_roots(self):
        validate_configuration_stage('machine-origin-development','bootstrap-m')
        with self.assertRaisesRegex(Core0Error,'requires bootstrap-m'):
            validate_configuration_stage('machine-origin-development','supervisor')
        fixture=unit('kernel','machine-origin-development')
        validate_unit(fixture,'kernel',configuration='machine-origin-development')
        fixture['roots'][0]['source']='Lemma.Kernel.Development.FramesEntry.boot'
        with self.assertRaises(Core0Error): validate_unit(fixture,'kernel',configuration='machine-origin-development')
    def test_machine_origin_catalog_admits_only_its_machine_vector(self):
        symbols=MACHINE_SYMBOLS|{'lemma_machine_vector'}
        catalog={'schema_version':1,'contract_version':'lemma-execution-v1','stage':'bootstrap-m',
                 'configuration':'machine-origin-development','startup_case':'machine-origin-probe',
                 'symbols':[{'symbol':s,'privilege':'M' if s in M_SYMBOLS else 'S','effect':PRIMITIVE_EFFECTS[s]} for s in sorted(symbols)],
                 'user_symbols':[{'symbol':'_user_start','privilege':'U','effect':'user-entry/exit'}, {'symbol':'lemma_exec_syscall','privilege':'U','effect':'user-syscall'}]}
        self.assertEqual(validate_catalog(catalog,configuration='machine-origin-development',stage='bootstrap-m'),symbols)
        for mutate in [lambda c:c.update(startup_case='normal'),
                       lambda c:c['symbols'].append({'symbol':'lemma_supervisor_vector','privilege':'S','effect':'supervisor-trap/context'}),
                       lambda c:next(r for r in c['symbols'] if r['symbol']=='lemma_machine_vector').update(privilege='S')]:
            bad=copy.deepcopy(catalog);mutate(bad)
            with self.assertRaises(Core0Error):validate_catalog(bad,configuration='machine-origin-development',stage='bootstrap-m')
    def test_startup_ecall_cannot_escape_its_explicit_case(self):
        ranges={'_start':(0x80000000,8),'other':(0x80000008,4)}
        text=' 80000000: li a7, 3\n 80000004: ecall\n 80000008: ecall\n'
        self.assertEqual(validate_startup_case(text,ranges,'machine-origin-probe')['start_ecall_pcs'],[0x80000004])
        with self.assertRaises(Core0Error):validate_startup_case(text,ranges,'normal')
        with self.assertRaises(Core0Error):validate_startup_case(text.replace(' 80000004: ecall',' 80000004: ret'),ranges,'machine-origin-probe')
    def test_optimizer_pmp_table_rejects_wrong_mutable_foreign_and_unguarded_content(self):
        fixture=unit('kernel');symbol='lemma_kernel_core0_scalar_33'
        fixture['functions'].append({'source':'Lemma.Kernel.MachineServices.expectedPmp','symbol':symbol,'args':['u64'],'effects':[]})
        table='switch.table.'+symbol
        ir=f'''target triple = "riscv64-unknown-unknown-elf"
@{table} = private unnamed_addr constant [4 x i64] [i64 536879103, i64 537141247, i64 553648127, i64 67108895], align 8
define i64 @{symbol}(i64 %arg0) {{
entry:
  %0 = icmp ult i64 %arg0, 4
  br i1 %0, label %switch.lookup, label %if.merge.2
switch.lookup: ; preds = %entry
  %switch.gep = getelementptr inbounds nuw [4 x i64], ptr @{table}, i64 0, i64 %arg0
  %switch.load = load i64, ptr %switch.gep, align 8
  br label %if.merge.2
if.merge.2: ; preds = %entry, %switch.lookup
  %if.result7 = phi i64 [ %switch.load, %switch.lookup ], [ 262655, %entry ]
  ret i64 %if.result7
}}
'''
        report=validate_ir(ir,fixture,optimized=True)
        self.assertEqual(report['readonly_optimizer_tables'][0]['guarded_loads'],1)
        self.assertEqual(report['memory_access_counts']['read64'],0)
        for changed in [ir.replace('i64 67108895','i64 0'),ir.replace('constant [4','global [4'),
                        ir.replace(table,'foreign_table'),ir+'@foreign = global i64 0\n',
                        ir.replace('icmp ult i64 %arg0, 4','icmp ult i64 %arg0, 5'),
                        ir.replace('br i1 %0, label %switch.lookup, label %if.merge.2','br label %switch.lookup')]:
            with self.assertRaises(Core0Error):validate_ir(changed,fixture,optimized=True)
    def test_pmp_constant_object_section_requires_exact_readonly_bytes_and_source(self):
        import struct
        values=[0x20001fff,0x20041fff,0x20ffffff,0x0400001f]
        tables=[{'source':'Lemma.Kernel.MachineServices.expectedPmp','values':values,'readonly':True}]
        section='  [11] .rodata.cst32 PROGBITS 0000000000000000 0029c8 000020 20 AM 0 0 8\n'
        raw=struct.pack('<4Q',*values)
        validate_pmp_constant_section(section,raw,object_file='kernel/program.o',tables=tables)
        for text,data,obj,metadata in [(section.replace('AM','AWM'),raw,'kernel/program.o',tables),
                                      (section.replace('000020 20','000040 20'),raw,'kernel/program.o',tables),
                                      (section,raw+b'\0','kernel/program.o',tables),
                                      (section,struct.pack('<4Q',*values[:-1],0),'kernel/program.o',tables),
                                      (section,raw,'firmware/program.o',tables),(section,raw,'kernel/program.o',[])]:
            with self.assertRaises(Core0Error):validate_pmp_constant_section(text,data,object_file=obj,tables=metadata)
    def test_loop_role_signature_and_effect_catalog_rejected_when_stale(self):
        fixture=unit(); source=fixture['functions'][0]['source']
        fixture['used_loops']=[{'stable_id':'action.loop','callback':source}]
        self.reject(fixture)
        fixture['functions'][0]['effects']=['may-diverge']; validate_unit(fixture,'user')
        fixture['used_loops'][0]['callback']='Lemma.User.Entry.unknown'; self.reject(fixture)
        fixture['used_loops'][0]['callback']=source; fixture['functions'][0]['args']=['u64']; self.reject(fixture)
        firmware=unit('firmware'); firmware['used_loops']=[{'stable_id':'action.loop','callback':firmware['functions'][0]['source']}]
        self.reject(firmware,'firmware')
    def test_pending_primitive_is_kernel_only(self):
        operation={'stable_id':'execution.supervisor-pending','source_identity':'Lemma.Core0.Execution.Op.readSupervisorPending','primitive_symbol':'lemma_exec_supervisor_pending','arguments':[],'returnkind':'word'}
        fixture=unit('kernel'); fixture['used_execution_ops']=[operation]; validate_unit(fixture,'kernel')
        for role in ['firmware','user']:
            bad=unit(role); bad['used_execution_ops']=[operation]; self.reject(bad,role)
    def test_unknown_version_and_empty_corpus_rejected(self):
        fixture=unit(); fixture['contract_version']='unreviewed'; self.reject(fixture)
        fixture=unit(); fixture['functions']=[]; self.reject(fixture)
    def test_user_physical_memory_authority_rejected(self):
        fixture=unit(); fixture['functions'][0]['effects']=['physical-write']; self.reject(fixture)
        fixture=unit(); fixture['used_execution_ops']=[{'stable_id':'execution.physical-read8','source_identity':'Lemma.Core0.Execution.Op.physicalRead8','primitive_symbol':None,'arguments':[],'returnkind':'word'}]; self.reject(fixture)
    def test_renamed_test_module_cannot_gain_production_provenance(self):
        fixture=unit(); fixture['functions'][0]['source']='Lemma.Compiler.Test.Hidden.main'; self.reject(fixture)
    def test_root_and_declared_function_must_match(self):
        fixture=unit(); fixture['roots'][0]['symbol']='lemma_user_different'; self.reject(fixture)
    def test_indirect_or_unknown_runtime_call_rejected(self):
        fixture=unit(); valid='target triple = "riscv64-unknown-unknown-elf"\ndefine { i64, i64 } @lemma_user_root_0() {\n ret { i64, i64 } zeroinitializer\n}\n'
        validate_ir(valid,fixture,optimized=False)
        for call in [' call void @malloc()',' call void %unknown()']:
            bad=valid.replace(' ret ',call+'\n ret ')
            with self.assertRaises(Core0Error): validate_ir(bad,fixture,optimized=False)
    def test_primitive_abi_attributes_cannot_claim_purity(self):
        expected="declare i64 @lemma_exec_read_time()"
        self.assertTrue(_primitive_declaration_matches(expected+" nounwind\n",expected))
        self.assertTrue(_primitive_declaration_matches(expected+" local_unnamed_addr #0\nattributes #0 = { nounwind }\n",expected))
        for suffix in [" nounwind memory(none)\n", " local_unnamed_addr #0\nattributes #0 = { nounwind memory(none) }\n", " #0\n"]:
            self.assertFalse(_primitive_declaration_matches(expected+suffix,expected))
        self.assertFalse(_primitive_declaration_matches("declare i32 @lemma_exec_read_time() nounwind\n",expected))
    def test_ssa_call_named_values_do_not_create_indirect_calls(self):
        fixture=unit()
        ir='target triple = "riscv64-unknown-unknown-elf"\ndefine { i64, i64 } @lemma_user_root_0() {\n entry.call:\n %r.call.value = add i64 1, 2\n ret { i64, i64 } zeroinitializer\n}\n'
        validate_ir(ir,fixture,optimized=False)
    def test_actual_user_csr_and_unknown_machine_opcode_rejected(self):
        for machine in [' 10000: csrr a0, mstatus',' 10000: vadd.vv v0, v1, v2']:
            with self.assertRaises(Core0Error): validate_machine(machine,user=True)
    def test_all_function_bytes_checked_without_decoding_constant_data(self):
        ranges={"main":(0x10000,8)}
        validate_machine(" 10000: li a0, 0\n 10004: ret\n 10008: <unknown>",user=True,ranges=ranges)
        for text in [" 10000: li a0, 0", " 10000: li a0, 0\n 10004: <unknown>", " 10000: li a0, 0\n 10002: ret\n 10004: ret"]:
            with self.assertRaises(Core0Error): validate_machine(text,user=True,ranges=ranges)
        with self.assertRaises(Core0Error): function_ranges(" 1: 00010000 8 FUNC GLOBAL DEFAULT 1 first\n 2: 00010004 8 FUNC GLOBAL DEFAULT 1 second")
    def test_malformed_input_invalidates_previous_audit_pass(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            out=Path(temporary); (out/'audit.json').write_text('{"status":"PASS"}')
            (out/'build.json').write_text('{"status":"BUILT"}')
            (out/'provenance.json').write_text('{}')
            with self.assertRaises(Core0Error): audit(root=ROOT,output_dir=out)
            self.assertFalse((out/'audit.json').exists())
            self.assertEqual(json.loads((out/'audit-failure.json').read_text())['status'],'FAIL')

if __name__=='__main__': unittest.main(verbosity=2)
