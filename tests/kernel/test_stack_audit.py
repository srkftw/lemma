import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_kernel import machine_frame, weighted_stack_graph, validate_compiled_stack, validate_stack_entries, validate_owned_task_stack
from core0_common import Core0Error

IR = '''define { i64, i64 } @root() {
entry:
  %v = call { i64, i64 } @leaf()
  ret { i64, i64 } %v
}
define { i64, i64 } @leaf() {
entry:
  %v = call i64 @bridge()
  ret { i64, i64 } zeroinitializer
}
declare i64 @bridge()
'''


class StackAuditTests(unittest.TestCase):
    def test_checked_pair_graph_accounts_external_frame_and_exact_object_stack(self):
        graph = weighted_stack_graph(IR, {'root': 48, 'leaf': 16}, {'bridge': 16})
        self.assertEqual(graph['weighted_frame_chains']['root']['bytes'], 80)
        self.assertEqual(graph['weighted_frame_chains']['root']['chain'], ['root', 'leaf', 'bridge'])
        machine = '0000 <root>:\n 0: addi sp, sp, -48\n 4: sd ra, 40(sp)\n 8: addi sp, sp, 48\n000c <leaf>:\n c: addi sp, sp, -16\n 10: addi sp, sp, 16\n'
        validate_compiled_stack(machine, {'root': 48, 'leaf': 16})
        for bad in [machine.replace('-48', '-64'), machine.replace('addi sp, sp, -48', 'sub sp, sp, a0'),
                    machine.replace('addi sp, sp, -48', 'mv sp, a0')]:
            with self.assertRaises(Core0Error): validate_compiled_stack(bad, {'root': 48, 'leaf': 16})

    def test_missing_cycle_indirect_dynamic_and_unknown_external_fail(self):
        for ir, frames, primitives in [
            (IR, {'root': 48}, {'bridge': 16}),
            (IR.replace('@bridge()', '@foreign()'), {'root': 48, 'leaf': 16}, {'bridge': 16}),
            (IR.replace('call i64 @bridge()', 'call i64 %dynamic()'), {'root': 48, 'leaf': 16}, {'bridge': 16}),
            (IR.replace('call i64 @bridge()', 'call { i64, i64 } @root()'), {'root': 48, 'leaf': 16}, {'bridge': 16}),
            (IR.replace('  %v = call i64 @bridge()', '  %p = alloca i64\n  %v = call i64 @bridge()'), {'root': 48, 'leaf': 16}, {'bridge': 16})]:
            with self.assertRaises(Core0Error): weighted_stack_graph(ir, frames, primitives)

    def test_dispatch_vector_consumes_same_task_stack_and_strict_limit_rejects(self):
        graph = weighted_stack_graph(IR, {'root': 48, 'leaf': 16}, {'bridge': 16})
        unit = {'role': 'kernel', 'roots': [{'source': 'boot', 'symbol': 'root'}, {'source': 'dispatch', 'symbol': 'leaf'}]}
        capacities = {'machine': 65536, 'boot': 61440, 'kernel-trap': 8192, 'user': 8192}
        entries = validate_stack_entries(unit, graph, capacities=capacities, vector_bytes=288)
        self.assertEqual(entries[1]['total_bytes'], 320)
        self.assertEqual(entries[1]['margin_bytes'], 7872)
        bad = copy.deepcopy(graph); bad['weighted_frame_chains']['leaf']['bytes'] = 8192 - 288
        with self.assertRaises(Core0Error): validate_stack_entries(unit, bad, capacities=capacities, vector_bytes=288)

    def test_typed_fixed_spill_is_counted_and_dynamic_arithmetic_rejected(self):
        body = 'bridge:\n  addi sp, sp, -16\n  addi sp, sp, 16\n.size bridge, . - bridge\n'
        self.assertEqual(machine_frame(body, 'bridge'), 16)
        with self.assertRaises(Core0Error): machine_frame(body.replace('addi sp, sp, -16', 'sub sp, sp, a0'), 'bridge')
        for write in ('addi sp, a0, -8192', 'mv sp, a0', 'li sp, 0', 'ld sp, 0(a0)'):
            with self.assertRaises(Core0Error): machine_frame(body.replace('addi sp, sp, -16', write), 'bridge')
        with self.assertRaises(Core0Error): machine_frame(body, 'missing')

    def test_larger_capacity_requires_actual_declared_pair_construction_and_cleanup(self):
        names = ['Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue',
                 'Lemma.Kernel.Memory.Frames.allocateContiguous2','Lemma.Kernel.Loader.allocateStack',
                 'Lemma.Kernel.Loader.installStackPair','Lemma.Kernel.Loader.storedStack','Lemma.Kernel.Loader.stackPair',
                 'Lemma.Kernel.Loader.releaseStackHandle','Lemma.Kernel.Loader.teardown','Lemma.Kernel.Process.dispatch',
                 'Lemma.Kernel.Loader.kernelStackHandleOffset','Lemma.Kernel.Loader.kernelStackSecondHandleOffset',
                 'Lemma.Kernel.Process.validateFrame','Lemma.Kernel.Process.validateStack',
                 'Lemma.Kernel.Development.TasksEntry.dispatch','Lemma.Kernel.Scheduler.dispatch',
                 'Lemma.Kernel.Task.capture','Lemma.Kernel.Task.context']
        symbols = {source:'f'+str(index) for index,source in enumerate(names)}
        constants = {names[0]:8192,names[9]:2400,names[10]:2480}
        edges = {names[2]:[names[1]],names[3]:[names[5]],names[7]:[names[4],names[6]],
                 names[4]:[names[0]],names[8]:[names[11]],names[11]:[names[12]],names[12]:[names[0]],
                 names[13]:[names[14]],names[14]:[names[15]],names[15]:[names[11]],names[16]:[names[12]]}
        ir=''
        for source,symbol in symbols.items():
            calls=''.join(f'  %v{index} = call i64 @{symbols[callee]}()\n' for index,callee in enumerate(edges.get(source,[])))
            ir+=f'define i64 @{symbol}() {{\nentry:\n{calls}  ret i64 {constants.get(source,0)}\n}}\n'
        unit={'functions':[{'source':source,'symbol':symbol} for source,symbol in symbols.items()]}
        layout={'task_kernel_stack_pages':2,'task_kernel_stack_bytes':8192}
        self.assertEqual(validate_owned_task_stack(layout,unit,ir)['base_owned_task_frames'],17)
        multi={**unit,'configuration':'tasks-development'}
        self.assertEqual(validate_owned_task_stack(layout,multi,ir)['bytes'],8192)
        for caller,callee in [(names[14],names[15]),(names[15],names[11]),(names[16],names[12])]:
            altered=ir.replace(f'call i64 @{symbols[callee]}()',f'call i64 @{symbols[names[5]]}()')
            with self.assertRaises(Core0Error):validate_owned_task_stack(layout,multi,altered)
        for changed in [ir.replace('ret i64 8192','ret i64 4096'),ir.replace('ret i64 2480','ret i64 2400'),
                        ir.replace('call i64 @f1()','call i64 @f5()')]:
            with self.assertRaises(Core0Error):validate_owned_task_stack(layout,unit,changed)
        with self.assertRaises(Core0Error):validate_owned_task_stack(layout,{'functions':unit['functions'][1:]},ir)


if __name__ == '__main__': unittest.main()
