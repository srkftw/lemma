#!/usr/bin/env python3
"""Pinned schema2 logical continuation; preserves the legacy schema1 patcher."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('source', type=Path)
p.add_argument('--helper', type=Path, required=True)
a=p.parse_args()
expected = {
    'system/cpu-timers.c': 'dc7d022db8e17a6323285e78897f9f8f15c537931f7bcd46094373f494758671',
    'cpu-common.c': '4c5677ed737f98cb2e1d2a4afd4ea0d5620a282d9b909d6cb1086b3d1641d595',
}
for name, digest in expected.items():
    if hashlib.sha256((a.source/name).read_bytes()).hexdigest() != digest:
        raise SystemExit('unsupported typed-work source identity: '+name)
# The legacy patch verifies every translation/cache layout input. Schema2 adds
# only the one pinned typed timer callback; arbitrary queued work stays rejected.
subprocess.run([sys.executable,str(Path(__file__).with_name('patch_soft_tlb.py')),
                str(a.source),'--helper',str(a.helper)], check=True)
import os
os.chdir(a.source)
p=Path('system/cpu-timers.c');s=p.read_text();anchor='void qemu_timer_notify_cb(void *opaque, QEMUClockType type)';assert s.count(anchor)==1
s=s.replace(anchor,'''/* Private pure observation, no CPU work execution or admission. */
bool lemma_cpu_timer_wake_identity(run_on_cpu_func fn, run_on_cpu_data data)
{
    return fn == do_nothing && data.host_ptr == NULL;
}

'''+anchor);p.write_text(s)
p=Path('cpu-common.c');s=p.read_text();s+='''
/* Private pure observation of the guarded logical-state boundary. */
extern bool lemma_cpu_timer_wake_identity(run_on_cpu_func, run_on_cpu_data);
void lemma_cpu_pending_work_stats(CPUState *cpu, uint64_t *total, uint64_t *wakes)
{
    struct qemu_work_item *wi;
    *total = *wakes = 0;
    qemu_mutex_lock(&cpu->work_mutex);
    QSIMPLEQ_FOREACH(wi, &cpu->work_list, node) {
        (*total)++;
        if (wi->free && !wi->exclusive && !wi->done &&
            lemma_cpu_timer_wake_identity(wi->func, wi->data)) { (*wakes)++; }
    }
    qemu_mutex_unlock(&cpu->work_mutex);
}
''';p.write_text(s)

p=Path('system/cpu-timers.c');s=p.read_text();s+='''
/* Only called by the validated never-run logical restore candidate. */
void lemma_cpu_timer_enqueue_wakes(CPUState *cpu, uint64_t count)
{
    while (count--) { async_run_on_cpu(cpu, do_nothing, RUN_ON_CPU_NULL); }
}
''';p.write_text(s)
p=Path('cpu-common.c');s=p.read_text();s+='''
extern void lemma_cpu_timer_enqueue_wakes(CPUState *, uint64_t);
bool lemma_cpu_restore_deadline_wakes(CPUState *cpu, uint64_t count)
{
    struct qemu_work_item *wi;
    if (count > 1024 || !cpu->stopped || cpu->running) { return false; }
    qemu_mutex_lock(&cpu->work_mutex);
    /* Validate every construction-time callback before replacing anything.
     * Never discard an unknown callback, run work, or modify source state. */
    QSIMPLEQ_FOREACH(wi, &cpu->work_list, node) {
        if (!wi->free || wi->exclusive || wi->done ||
            !lemma_cpu_timer_wake_identity(wi->func, wi->data)) {
            qemu_mutex_unlock(&cpu->work_mutex); return false;
        }
    }
    while (!QSIMPLEQ_EMPTY(&cpu->work_list)) {
        wi = QSIMPLEQ_FIRST(&cpu->work_list);
        QSIMPLEQ_REMOVE_HEAD(&cpu->work_list, node);
        g_free(wi);
    }
    qemu_mutex_unlock(&cpu->work_mutex);
    lemma_cpu_timer_enqueue_wakes(cpu, count);
    return true;
}
''';p.write_text(s)
