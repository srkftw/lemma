"""Host-only fail-closed K observer fixtures, not guest execution evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_kernel_architecture as k
from core0_common import Core0Error
from buffer_transport import decode_uart


def record(words):
    return ("K1" + "".join(f" {word:016x}" for word in words) + "\n").encode()


class ArchitectureCheckerTests(unittest.TestCase):
    def binding(self, directory, case="halfword-ecall", managed=False):
        cfg = ("service-" if managed else "user-") + case + "-development"
        symbol, cause, stval, opcode, reason = k.CASES[case]
        body = bytes(16) + struct.pack("<II", 0x00730013, 0) if case == "halfword-ecall" else struct.pack("<I", opcode)
        offset = 18 if case == "halfword-ecall" else 0
        base = 0x10080
        row = {"case":case,"symbol":symbol,"base":base,"bytes":len(body),"raw_sha256":hashlib.sha256(body).hexdigest(),
               "fault_pc":base+offset,"instruction_site":{"pc":base+offset,"offset":offset,"instruction_bits":32,"opcode":opcode}}
        user = {"quarantined_startup":row,"exit_ecall_pc":0x10020,"syscall_bridge":{"ecall_pc":0x10020},
                "function_ranges":{"main":{"base":0x10000,"bytes":128},symbol:{"base":base,"bytes":len(body)}}}
        unit = {"configuration":cfg,"role":"user","roots":[{"source":"Lemma.User.Entry.main","symbol":"main","args":["u64"]}],
                "functions":[{"source":"Lemma.User.Entry.main","symbol":"main"}]}
        image = directory / "image.elf"; image.write_bytes(b"host fixture")
        unit_dir = directory / ("users/fault" if managed else "user"); unit_dir.mkdir(parents=True)
        (unit_dir/"unit.json").write_text(json.dumps(unit))
        text = bytes(128)+body
        (unit_dir/"text.bin" if managed else directory/"user-text.bin").write_bytes(text)
        (directory/"layout.json").write_text(json.dumps({"task_kernel_stack_pages":2,"task_kernel_stack_bytes":8192}))
        audit = {"status":"PASS","configuration":cfg,"stage":"supervisor","elf":{"users":{"fault":user}} if managed else {"user":user},
                 "task_kernel_stack":{"pages":2,"bytes":8192,"construction":"owned-physically-contiguous-pair",
                    "first_handle_offset":2400,"second_handle_offset":2480,
                    **({"base_owned_task_frames":16,"base_global_task_frames":17} if managed else {"base_owned_task_frames":17})}}
        p,q,t='Lemma.Kernel.Process.','Lemma.Kernel.Scheduler.','Lemma.Kernel.Task.'
        read,control='Lemma.Kernel.Memory.Access.read64','Lemma.Kernel.Console.record'
        context='Lemma.Kernel.Memory.AddressSpace.context'
        required={p+'validateFrame',read,control}|({q+'dispatch',q+'reportFault',q+'failed',q+'finish',q+'returnKernel',t+'capture',t+'failed',context}
                    if managed else {p+'dispatch',p+'userTrap',p+'failed',p+'finish'})
        sources={source:f'lemma_kernel_fixture_{i}' for i,source in enumerate(sorted(required))}
        pairs=[(q+'dispatch',t+'capture',q+'reportFault',q+'failed'),(t+'capture',p+'validateFrame',context,t+'failed'),
               (q+'reportFault',read,control,q+'failed'),(q+'reportFault',control,q+'finish',q+'failed')] if managed else [
               (p+'dispatch',p+'validateFrame',read,p+'failed')]
        audit['architecture_diagnostics']={'raw_status_offset':264,'diagnostic_tag':212,
            'diagnostic_words':['cause','pc','stval','original_hardware_status'],'termination_code':44,
            'halfword_ecall_return_reason':4 if managed else None,'hardware_fault_return_reason':5 if managed else None,
            'source_functions':sources,'ownership_gates':[{'source':caller,'checked':sources[checked],'protected':sources[protected],
                'failure_helper':sources[failed],'component':'status','equals':0,'gate':{'comparison':'%checked','success_when_true':False,
                'block':'entry','success':'ok','failure':'fail','protected_blocks':['ok']}} for caller,checked,protected,failed in pairs],
            'diagnostic_before_termination':{'before':sources[control],'after':sources[(q if managed else p)+'finish'],
                'protected_sites':[['ok',1]]}}
        kernel_sources=dict(sources)
        if managed:
            required_stack={"Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue",
                "Lemma.Kernel.Memory.Frames.allocateContiguous2","Lemma.Kernel.Loader.allocateStack",
                "Lemma.Kernel.Loader.installStackPair","Lemma.Kernel.Loader.storedStack","Lemma.Kernel.Loader.stackPair",
                "Lemma.Kernel.Loader.releaseStackHandle","Lemma.Kernel.Loader.teardown",
                "Lemma.Kernel.Process.validateFrame","Lemma.Kernel.Process.validateStack",
                "Lemma.Kernel.Loader.kernelStackHandleOffset","Lemma.Kernel.Loader.kernelStackSecondHandleOffset",
                "Lemma.Kernel.Development.ServiceEntry.dispatch","Lemma.Kernel.Scheduler.dispatch",
                "Lemma.Kernel.Task.capture","Lemma.Kernel.Task.context"}
            stack_sources={source:sources.get(source,f'lemma_kernel_stack_fixture_{i}') for i,source in enumerate(sorted(required_stack))}
            audit['task_kernel_stack']['source_functions']=stack_sources
            kernel_sources.update(stack_sources)
        kernel=directory/'kernel';kernel.mkdir(exist_ok=True)
        (kernel/'unit.json').write_text(json.dumps({'functions':[{'source':source,'symbol':symbol} for source,symbol in kernel_sources.items()]}))
        if managed:
            audit['user_images']={'fault':{'id':5,'source':'Lemma.User.Entry.main','module':'Lemma.User.Entry',
                'boot_role':'buffer-fault-client','text_bytes':len(text),'text_sha256':hashlib.sha256(text).hexdigest()}}
            audit['elf']['users'].update({key:{'quarantined_startup':{'case':'none'}} for key in ('server','cli','peer','busy')})
        return image,audit

    def test_site_matches_actual_linked_words_and_genuine_root(self):
        for case in k.CASES:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                image,audit=self.binding(Path(tmp),case)
                spec=k.require_case(image,audit)
                self.assertEqual(spec['site']['fault_pc'],spec['site']['base']+spec['site']['instruction_site']['offset'])
                corruptions=[('offset',True),('offset',2),('pc',0x10002),('opcode',0),('instruction_bits',16)]
                for field,value in corruptions:
                    changed=deepcopy(audit); changed['elf']['user']['quarantined_startup']['instruction_site'][field]=value
                    with self.subTest(field=field,value=value),self.assertRaises(Core0Error):k.require_case(image,changed)
                unit=json.loads((image.parent/'user/unit.json').read_text()); unit['roots'][0]['source']='Lemma.User.Development.Other.main'
                (image.parent/'user/unit.json').write_text(json.dumps(unit))
                with self.assertRaisesRegex(Core0Error,'genuine maintained'):k.require_case(image,audit)

    def test_managed_stack_uses_owner16_global17_and_genuine_sources_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            image,audit=self.binding(Path(tmp),managed=True)
            self.assertTrue(k.require_case(image,audit)['managed'])
            numeric={"pages":True,"bytes":4096,"first_handle_offset":2480,"second_handle_offset":2400,
                     "base_owned_task_frames":17,"base_global_task_frames":16}
            for field,value in numeric.items():
                changed=deepcopy(audit);changed['task_kernel_stack'][field]=value
                with self.subTest(field=field),self.assertRaises(Core0Error):k.require_case(image,changed)
            for field in ('base_owned_task_frames','base_global_task_frames'):
                changed=deepcopy(audit);changed['task_kernel_stack'][field]=True
                with self.subTest(boolean=field),self.assertRaises(Core0Error):k.require_case(image,changed)
            changed=deepcopy(audit);changed['task_kernel_stack']['source_functions']['Lemma.Kernel.Loader.allocateStack']='lemma_kernel_stale'
            with self.assertRaises(Core0Error):k.require_case(image,changed)
            unit=json.loads((image.parent/'kernel/unit.json').read_text())
            unit['functions']=[row for row in unit['functions'] if row['source']!='Lemma.Kernel.Memory.Frames.allocateContiguous2']
            (image.parent/'kernel/unit.json').write_text(json.dumps(unit))
            with self.assertRaises(Core0Error):k.require_case(image,audit)
        with tempfile.TemporaryDirectory() as tmp:
            image,audit=self.binding(Path(tmp))
            self.assertFalse(k.require_case(image,audit)['managed'])
            audit['task_kernel_stack']['base_owned_task_frames']=16
            with self.assertRaisesRegex(Core0Error,'task accounting lacks'):k.require_case(image,audit)

    def test_original_frame_diagnostic_requires_exact_sources_gates_and_order(self):
        for managed in (False,True):
            with self.subTest(managed=managed),tempfile.TemporaryDirectory() as tmp:
                image,audit=self.binding(Path(tmp),managed=managed)
                k.require_diagnostics(image,audit,managed)
                mutations=[lambda d:d.update(raw_status_offset=256),lambda d:d.update(diagnostic_words=['cause','pc','stval','sanitized_status']),
                    lambda d:d.update(ownership_gates=[]),lambda d:d['ownership_gates'][0].update(checked='lemma_kernel_wrong'),
                    lambda d:d['ownership_gates'][0]['gate'].update(success_when_true=True),
                    lambda d:d['diagnostic_before_termination'].update(protected_sites=[]),
                    lambda d:d['source_functions'].update({'Lemma.Kernel.Memory.Access.read64':'lemma_kernel_wrong'})]
                for mutation in mutations:
                    changed=deepcopy(audit);mutation(changed['architecture_diagnostics'])
                    with self.assertRaises(Core0Error):k.require_diagnostics(image,changed,managed)
                del audit['architecture_diagnostics']
                with self.assertRaises(Core0Error):k.require_diagnostics(image,audit,managed)

    def singleton(self,directory,case='halfword-ecall'):
        image,audit=self.binding(directory,case)
        spec=k.require_case(image,audit)
        kernel=0x82000000
        initial=[(0xa,0x87e00000,1,512,0x82000000),
                 (0xc0,0x534543414c4c0001,0x1b1b1f1818,0xb1ff,0x1446),
                 (0xc1,4,5,1,0),(0xc2,17,22,22,1000000),(0xd3,kernel,k.satp(kernel),500,0)]
        text=(directory/'user-text.bin').stat().st_size
        before=500-17-(text+4095)//4096
        rows=list(initial)
        for i,arg in enumerate(k.ARGUMENTS):
            root=0x82001000+i*0x1000
            rows.extend([(0xd0,512*(i+1),root,0x10000,text),
                         (0xd4,spec['cause'],spec['site']['fault_pc'],spec['stval'],k.USER_STATUS),
                         (0xd1 if spec['cause']==8 else 0xdc,spec['cause'],spec['site']['fault_pc'],k.USER_STATUS,k.satp(root)),
                         (0xd2,44,k.mix(arg),before,500)])
        class Session:
            def __init__(self): self.image,self.binding=image,audit;self.rows=iter(rows)
            def record(self): return next(self.rows)
            def command(self,*words): return self.record()
        return Session(),rows

    def test_singleton_exact_trap_status_containment_and_reclamation(self):
        for case in k.CASES:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                session,rows=self.singleton(Path(tmp),case)
                observed=k.check_singleton(session)
                self.assertEqual([r['argument'] for r in observed['instances']],[7,0,7])
                for index,field,value in [(6,3,0),(6,4,0x200000120),(7,2,0x10000),(8,1,0),(8,2,0),(8,4,499)]:
                    changed=deepcopy(rows);row=list(changed[index]);row[field]=value;changed[index]=tuple(row)
                    # A correct stval0 remains valid for halfwordECALL only.
                    if changed==rows:continue
                    session.rows=iter(changed)
                    with self.subTest(index=index,field=field),self.assertRaises(Core0Error):k.check_singleton(session)

    def test_full_singleton_replay_rejects_extra_suffix_or_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);session,rows=self.singleton(directory)
            observed=k.check_singleton(session)
            (directory/'audit.json').write_text(json.dumps(session.binding))
            raw=b''.join(record(row) for row in rows);events,_=decode_uart(raw)
            (directory/'received.bin').write_bytes(raw)
            sent=b''.join(struct.pack('<5Q',1,arg,0,0,0) for arg in k.ARGUMENTS)
            (directory/'sent.bin').write_bytes(sent)
            report={'observed':observed,'wire_format':'kernel-buffer-uart-v1','wire_events':events,'complete_raw_coverage':True}
            replay=k.validate_replay(ROOT,session.image,report,directory)
            self.assertTrue(replay['complete_semantic_replay'])
            extra=record((0xf3,512,0x82000000,99,0));(directory/'received.bin').write_bytes(raw+extra)
            report['wire_events']=decode_uart(raw+extra)[0]
            with self.assertRaisesRegex(Core0Error,'unexpected suffix'):k.validate_replay(ROOT,session.image,report,directory)
            (directory/'received.bin').write_bytes(raw);report['wire_events']=events
            (directory/'sent.bin').write_bytes(sent+b'\x00')
            with self.assertRaisesRegex(Core0Error,'input bytes'):k.validate_replay(ROOT,session.image,report,directory)

    def managed(self,directory,case='halfword-ecall'):
        from test_buffer_checker import BufferCheckerFailures
        _,session=BufferCheckerFailures().fixture(directory,'service-development')
        image,audit=self.binding(directory,case,True)
        fault=audit['elf']['users']['fault'];cfg=audit['configuration']
        session.binding['configuration']=cfg;session.binding['elf']['users']['fault']=fault
        session.binding['status']='PASS';session.binding['task_kernel_stack']=audit['task_kernel_stack']
        session.binding['architecture_diagnostics']=audit['architecture_diagnostics']
        for key in ('server','cli','peer','busy'):session.binding['elf']['users'][key]['quarantined_startup']={'case':'none'}
        raw=(directory/'users/fault/text.bin').read_bytes()
        session.binding['user_images']['fault']={'id':5,'text_bytes':len(raw),'text_sha256':hashlib.sha256(raw).hexdigest(),
            'source':'Lemma.User.Entry.main','module':'Lemma.User.Entry','boot_role':'buffer-fault-client'}
        trace=k.ArchitectureServiceTrace(session)
        for id,kind,rights in [(512,1,2),(512,2,8),(1024,1,3),(1024,4,1024),(1536,1,2),(1536,4,1024)]:
            slot=len(trace.grants.get(id,[]));serial=len(trace.serials)+1
            trace.observe((0xb1,id,(serial<<4)|slot,kind,rights))
        trace.observe((0xb4,512,51,424,0))
        for id,index,nonce,root in [(1024,1,1,0x82001000),(1536,2,2,0x82002000),(2048,3,3,0x82003000),(512,0,1,0x82004000)]:trace.observe((0xf1,id,index,nonce,root))
        trace.observe((0x300,512,51,1,1024))
        trace.begin_action({'kind':'diagnostic','index':7,'words':[0x33,4,7,0,0]})
        for kind,rights in ((1,2),(4,1024)):
            slot=len(trace.grants.get(2560,[]));serial=max(trace.serials)+1
            trace.observe((0xb1,2560,(serial<<4)|slot,kind,rights))
        trace.observe((0xf1,2560,4,7,0x82005000));trace.observe((0xf7,0x33,0,2560,4))
        trace.observe((0xf3,2560,0x82005000,1,1))
        return trace

    def test_managed_exception_is_bound_to_sole_fault_and_actual_prior_trap(self):
        for case in k.CASES:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                trace=self.managed(Path(tmp),case);spec=trace.case;pc=spec['site']['fault_pc']
                with self.assertRaises(Core0Error):trace.observe((0xf2,2560,spec['reason'],0,pc))
                with self.assertRaises(Core0Error):trace.observe((0xd4,spec['cause'],pc,spec['stval']^1,k.USER_STATUS))
                trace.observe((0xd4,spec['cause'],pc,spec['stval'],k.USER_STATUS))
                with self.assertRaises(Core0Error):trace.observe((0xf2,2560,4 if spec['reason']==5 else 5,0,pc))
                trace.observe((0xf2,2560,spec['reason'],0,pc))
                with self.assertRaises(Core0Error):trace.observe((0xf4,2560,44,7,spec['cause']))
                trace.observe((0xf4,2560,44,k.mix(7),spec['cause']))
                trace.observe((0xf5,2560,0,0,1));before=trace.remaining
                trace.observe((0xf6,2560,before,before+18,0))
                self.assertTrue(trace.tasks[2560]['reaped'])
                trace.current=1024
                with self.assertRaises(Core0Error):trace.observe((0xd4,spec['cause'],pc,spec['stval'],k.USER_STATUS))
                trace.current=1024
                with self.assertRaises(Core0Error):trace.observe((0xf2,1024,4,0,pc))

    def test_closed_matrix_and_timeout_fail_before_tools(self):
        self.assertEqual(len(k.MATRIX),12)
        self.assertEqual(set(opt for _,opt in k.MATRIX),{'O0','O2'})
        for timeout in (True,0,-1,float('inf'),float('nan'),301):
            with self.subTest(timeout=timeout),patch.object(k,'ArchitectureSession') as guest,self.assertRaises(Core0Error):
                k.observe(root=ROOT,image=ROOT/'absent',output_dir=ROOT/'absent-output',timeout=timeout)
            guest.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.json';path.write_text(json.dumps({'status':'PASS','cases':[]}))
            with patch.object(k,'source_identity',return_value={}):
                with self.assertRaises(Core0Error):k.validate_architecture(path,ROOT)

    def test_absolute_deadline_rejects_last_observation_and_final_revalidation_overrun(self):
        for stage in ('last-observation','final-revalidation'):
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);clock=[0.0]
                def built(**kwargs):
                    kwargs['output_dir'].mkdir(parents=True)
                    return {'status':'BUILT'}
                def observed(**kwargs):
                    if stage=='last-observation':clock[0]=501.0
                    return {'status':'PASS','records':[]}
                def validated(*args,**kwargs):clock[0]=501.0
                with patch.object(k,'MATRIX',(k.MATRIX[0],)),patch.object(k,'source_identity',return_value={}),\
                     patch.object(k,'source_inputs',return_value={}),patch.object(k,'acceptance_inputs',return_value={}),\
                     patch.object(k.time,'monotonic',side_effect=lambda:clock[0]),patch.object(k,'build',side_effect=built),\
                     patch.object(k,'observe',side_effect=observed),patch.object(k,'sha256',return_value='fixture'),\
                     patch.object(k,'validate_architecture',side_effect=validated):
                    result=k.matrix(root=root,work_dir=Path('build/kernel/deadline'),clean=True,timeout=300,deadline=500)
                self.assertEqual(result['status'],'FAIL');self.assertIn('absolute deadline expired',result['error'])
                retained=json.loads((root/'build/kernel/deadline/result.json').read_text())
                self.assertEqual(retained['status'],'FAIL');self.assertEqual(retained['deadline_seconds'],500)
                self.assertGreater(retained['elapsed_seconds'],retained['deadline_seconds'])

    def test_each_managed_fault_requires_its_own_service_peer_and_math_progress(self):
        tasks={i:{'key':'fault','nonce':arg,'reaped':True,'terminal':[0xf4,i,44,k.mix(arg),8],
                  'reaped_wire':i*10,'created_wire':(i-1)*10+9} for i,arg in enumerate(k.ARGUMENTS,1)}
        tasks[99]={'key':'busy'};events=[{'kind':'kernel','value':[0xf3,99,0,0,0]} for _ in range(40)]
        pairs=[];data=b'\x00\xff'+bytes(126)
        for i in range(1,4):
            index=i*10
            events[index+1]={'kind':'kernel','value':[0x334,77,0,0,i]}
            events[index+2]={'kind':'kernel','value':[0xf2,99,1,i,0x10100]}
            pairs.extend([{'input':{'index':index+3,'words':[2,1,i,0,128],'data_hex':data.hex()},'index':index+4,
                           'response':{'application_status':0,'transport_status':0}},
                          {'input':{'index':index+5,'words':[3,1,i,0,128],'data_hex':''},'index':index+6,
                           'response':{'count':128,'data_hex':data.hex()}}])
        trace=SimpleNamespace(require_settled_releases=lambda:None,tasks=tasks,faults=[{},{},{}],live=lambda:[],current=None,
            remaining=497,pending_rpc=None,pending_ack=None,creation_queue=[],pending_expiry={},publications=[{}],epoch=1,
            restart_witnesses=[],session=SimpleNamespace(events=events),rpc_pairs=pairs,busy_math_range={'tick':{'base':0x10100,'bytes':4}},busy_math=[1,2,3])
        self.assertEqual(k.managed_qualification(trace)['ordinary_continuations'],3)
        for i in range(1,4):
            for field in ('peer','math','bytes'):
                changed=deepcopy(trace)
                if field=='peer':changed.session.events[i*10+1]['value'][0]=0x333
                elif field=='math':changed.session.events[i*10+2]['value'][4]=0x10000
                else:changed.rpc_pairs[2*i-1]['response']['data_hex']=bytes(128).hex()
                with self.subTest(instance=i,field=field),self.assertRaises(Core0Error):k.managed_qualification(changed)


if __name__=='__main__':unittest.main()
