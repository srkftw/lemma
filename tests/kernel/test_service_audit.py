import copy
import json
import re
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from audit_kernel import _jump_assembly_guard, _jump_service_default, BACKEND_JUMP_TABLES, BACKEND_JUMP_TABLE_CONFIGURATIONS, BACKEND_JUMP_TABLE_USER_IMAGES, validate_server_lease_scan, validate_server_application_expiry, validate_dynamic_copy_gate, validate_input_read_inventory
from core0_common import Core0Error

SERVICE_CASE_CONFIGURATIONS = {
    "service-normal", "service-development", "silicon-service-development", "service-halfword-ecall-development",
    "service-return-supervisor-development", "service-return-machine-development",
}


class ServiceTableFailures(unittest.TestCase):
    def fixture(self):
        assembly = """owner:
 addi sp, sp, -112
 addi a0, s3, -2
 li a2, 4
 bltu a2, a0, .LBB0_2
 slli a0, a0, 3
.Lpcrel_hi0:
 auipc a2, %pcrel_hi(.LJTI0_0)
 addi a2, a2, %pcrel_lo(.Lpcrel_hi0)
 add a0, a0, a2
 ld a0, 0(a0)
 ld a2, 112(sp)
 jr a0
.LBB0_1:
 addi sp, sp, 112
 ret
.LBB0_2:
 addi sp, sp, 112
 ret
 .size owner, .-owner
"""
        return dict(assembly=assembly, symbol="owner", table=".LJTI0_0", targets=[".LBB0_1"]*5,
                    count=5, minimum=2, source="Lemma.Services.Buffer.Server.existing",
                    configuration="service-normal", image_key="server")

    def test_exact_incoming_argument_reload_preserves_target(self):
        for configuration in sorted(SERVICE_CASE_CONFIGURATIONS):
            data=self.fixture();data["configuration"]=configuration
            report=_jump_assembly_guard(**data)
            self.assertEqual(report["target_preserving_reload"]["incoming_argument"],8)
            self.assertEqual(report["target_preserving_reload"]["preserved_target_register"],"a0")
            self.assertTrue(report["guard_dominates_load"])

    def test_reload_authority_cannot_escape_selected_source_or_image(self):
        for key,value in [("source",None),("source","Lemma.Services.Buffer.Server.other"),
                          ("configuration","ipc-development"),("configuration","normal"),
                          ("image_key","cli"),("image_key",None)]:
            data=self.fixture();data[key]=value
            with self.assertRaises(Core0Error):_jump_assembly_guard(**data)

    def test_reload_and_index_clobbers_are_rejected(self):
        for before,after in [("ld a2, 112(sp)","ld a0, 112(sp)"),("ld a2, 112(sp)","ld a3, 112(sp)"),
                             ("ld a2, 112(sp)","ld a2, 120(sp)"),("ld a2, 112(sp)","sd a2, 112(sp)"),
                             ("ld a2, 112(sp)","mv a0, a2"),("addi sp, sp, -112","addi sp, sp, -128"),
                             ("addi a0, s3, -2","addi a0, s4, -2"),("jr a0","jr a2"),
                             ("bltu a2, a0","blt a2, a0"),("slli a0, a0, 3","slli a0, a2, 3")]:
            data=self.fixture();data["assembly"]=data["assembly"].replace(before,after)
            with self.assertRaises(Core0Error):_jump_assembly_guard(**data)

    def test_user_tables_are_a_closed_source_config_image_catalog(self):
        self.assertEqual(set(BACKEND_JUMP_TABLE_USER_IMAGES),{
            "Lemma.Services.Buffer.Protocol.requestShape","Lemma.Services.Buffer.Server.existing"})
        for source in BACKEND_JUMP_TABLE_USER_IMAGES:
            self.assertEqual(BACKEND_JUMP_TABLE_USER_IMAGES[source],{"server"})
            self.assertEqual(BACKEND_JUMP_TABLE_CONFIGURATIONS[source], SERVICE_CASE_CONFIGURATIONS)
            self.assertEqual(BACKEND_JUMP_TABLES[source][0],"user")

    def test_sparse_development_commands_keep_genuine_default_acknowledgement(self):
        value=json.loads((Path(__file__).parent/'fixtures/service-command-default.json').read_text())
        data={k:v for k,v in value.items() if k not in ['scope','producer']}
        actual=_jump_service_default(**data)
        self.assertEqual(actual['holes'],list(range(52,64)))
        self.assertEqual(BACKEND_JUMP_TABLE_CONFIGURATIONS['Lemma.Kernel.Development.ServiceEntry.command'],
                         SERVICE_CASE_CONFIGURATIONS - {'service-normal'})
        body=data['optimized_ir']
        call=re.search(r'call \{ i64, i64 \} @[^\n]+\(i64 %arg0, i8 zeroext 17, i64 0, i64 %arg1\)',body)[0]
        for before,after in [('i8 zeroext 17','i8 zeroext 0'),('i64 0, i64 %arg1','i64 1, i64 %arg1'),
                             ('i64 %arg0, i8','i64 %arg1, i8'),('i64 0, i64 %arg1','i64 0, i64 %arg0')]:
            bad=copy.deepcopy(data);bad['optimized_ir']=body.replace(call,call.replace(before,after))
            with self.assertRaises(Core0Error):_jump_service_default(**bad)
        bad=copy.deepcopy(data);bad['targets'][3]=bad['targets'][0]
        with self.assertRaises(Core0Error):_jump_service_default(**bad)
        bad=copy.deepcopy(data);bad['unit']['functions'][0]['args'][1]='u64'
        with self.assertRaises(Core0Error):_jump_service_default(**bad)
        for before,after in [('and i64','or i64'),(', 255',', 127'),(', 0\n',', 1\n')]:
            bad=copy.deepcopy(data);bad['optimized_ir']=body.replace(before,after)
            with self.assertRaises(Core0Error):_jump_service_default(**bad)


class ServiceLeaseFailures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=json.loads((Path(__file__).parent/'fixtures/service-lease-scan.json').read_text())['cases']

    def test_genuine_post_receive_scan_and_historical_gap(self):
        current=self.cases['post_receive']
        self.assertEqual(validate_server_lease_scan(current['body'],**current['symbols'])['scan_rows'],4)
        old=self.cases['pre_receive_only']
        with self.assertRaises(Core0Error):validate_server_lease_scan(old['body'],**old['symbols'])

    def test_missing_reordered_or_unsuccessful_fresh_scan_rejected(self):
        current=self.cases['post_receive'];body=current['body'];symbols=current['symbols']
        clock_calls=re.findall(r'(%[A-Za-z0-9_.$-]+) = call \{ i64, i64 \} @'+re.escape(symbols['time'])+r'\(\)',body)
        clock_values=[re.findall(r'(%[A-Za-z0-9_.$-]+) = extractvalue \{ i64, i64 \} '+re.escape(result)+r', 1$',body,re.M)[0] for result in clock_calls]
        for bad in [
                body.replace('@'+symbols['expire']+'(', '@omitted_expire('),
                body.replace(clock_calls[1]+' = call { i64, i64 } @'+symbols['time'],clock_calls[1]+' = call { i64, i64 } @omitted_time'),
                body.replace('i64 '+clock_values[1]+', i64 0)','i64 '+clock_values[0]+', i64 0)'),
                body.replace('i32 signext 4,','i32 signext 3,'),
                body.replace('icmp ult i32 %action.fold.index53, 4','icmp ult i32 %action.fold.index53, 3'),
                body.replace('icmp eq i8 %action.fold.status62, 0','icmp eq i8 %action.fold.status62, 9'),
                body.replace('label %action.if.then.29, label %action.if.else.30','label %action.if.then.43, label %action.if.else.30'),
                body.replace('label %action.if.then.43, label %action.if.else.44','label %action.if.else.44, label %action.if.then.43')]:
            with self.assertRaises(Core0Error):validate_server_lease_scan(bad,**symbols)

    def test_copy_count_is_actual_dynamic_request_and_success_edge(self):
        body="""entry:
 %r = call { i64, i64 } @copy(i64 %desc, i64 %ptr, i64 %handle, i64 %scratch, i64 %count)
 %copied = extractvalue { i64, i64 } %r, 1
 %eq = icmp eq i64 %copied, %count
 br i1 %eq, label %advance, label %failure
advance:
 %write = call { i64, i64 } @put(i64 %head, i64 %next)
 ret { i64, i64 } %write
failure:
 ret { i64, i64 } zeroinitializer
"""
        validate_dynamic_copy_gate(body,'copy','put')
        for bad in [body.replace('%r, 1','%r, 0'),body.replace('%copied, %count','%copied, %other'),
                    body.replace('i64 %count)','i64 1)'),body.replace('label %advance, label %failure','label %failure, label %advance'),
                    body.replace('ret { i64, i64 } zeroinitializer','br label %advance')]:
            with self.assertRaises(Core0Error):validate_dynamic_copy_gate(bad,'copy','put')

    def test_application_expiry_uses_same_fresh_clock_before_create_or_renewal(self):
        value=json.loads((Path(__file__).parent/'fixtures/service-application-expiry.json').read_text())
        body=value['body'];symbols=value['symbols']
        self.assertEqual(validate_server_application_expiry(body,**symbols)['scan_rows'],4)
        variants=[
            body.replace('@'+symbols['expire']+'(', '@missing_application_expire('),
            body.replace('@'+symbols['time']+'(', '@missing_fresh_time('),
            body.replace('i64 %action.call.value71, i64 0)','i64 0, i64 0)'),
            body.replace('i32 signext 4,','i32 signext 3,'),
            body.replace('icmp eq i8 %action.fold.status86, 0','icmp eq i8 %action.fold.status86, 9'),
            body.replace('add i64 %action.call.value71,','add i64 %arg2,'),
            body.replace('label %action.if.then.53, label %action.if.else.54','label %action.if.else.54, label %action.if.then.53'),
            body.replace('label %action.if.then.39, label %action.if.else.40','label %action.if.then.59, label %action.if.else.40'),
            body.replace('br label %action.fold.header.47','br label %action.fold.done.51'),
            body.replace('icmp ult i32 %action.fold.index77, 4','icmp ult i32 %action.fold.index77, 3'),
        ]
        for bad in variants:
            with self.assertRaises(Core0Error):validate_server_application_expiry(bad,**symbols)

    def test_actual_input_copy_advancement_rejects_changed_counts_or_sources(self):
        value=json.loads((Path(__file__).parent/'fixtures/service-input-read.json').read_text())
        body=value['body'];arguments=value['arguments']
        self.assertEqual(validate_input_read_inventory(body,**arguments)['writes'],2)
        for before,after in [('i64 %action.call.value83,','i64 %arg0,'),
                             ('sub i64 %action.call.value35,','add i64 %action.call.value35,'),
                             ('add i64 %action.call.value48,','sub i64 %action.call.value48,'),
                             ('%action.call.value35, %if.else.69','%arg0, %if.else.69'),
                             ('urem i64 %bin106,','urem i64 %arg0,'),
                             ('i32 %cast57, 256','i32 %cast57, 255'),
                             ('i64 %bin122, i64 %bin125','i64 %bin103, i64 %bin125')]:
            bad=body.replace(before,after)
            self.assertNotEqual(body,bad,(before,after))
            with self.assertRaises(Core0Error):validate_input_read_inventory(bad,**arguments)


if __name__ == "__main__":unittest.main()
