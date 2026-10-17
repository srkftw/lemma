#!/usr/bin/env python3
"""Opt-in pinned host-only logical SoftTLB derivative; legacy defaults unchanged."""
import argparse
import hashlib
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('source', type=Path)
p.add_argument('--helper', type=Path, required=True)
a = p.parse_args()
root = a.source
expected = {
    'accel/tcg/cputlb.c': 'a990689aea048a90e89f617bc72acaabca3a51acf355b56a16956dfdfc530260',
    'include/hw/core/cpu.h': '90d57f645d810418fa93ea44921d472b7cb44efa6190ef7a3c6249f081bcf598',
    'include/exec/cputlb.h': 'dab45f69bd1af262cafc043fdcb2785828ef4d558e74a91f4d9335b4f2caf08c',
    'include/exec/memattrs.h': 'cf65c7334c8e9367e35ccac1a73bda5227d5aa58c1290689cc7b1f2d284fe1cf',
    'include/exec/tlb-common.h': '2722692c90ab611f1b15dc7d89e061dff138d9b2367ac0b1c29160372bad0853',
}
for name, digest in expected.items():
    if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
        raise SystemExit('unsupported SoftTLB source identity: ' + name)

def replace(name, before, after):
    path = root / name
    text = path.read_text()
    if text.count(before) != 1:
        raise SystemExit('SoftTLB patch anchor ambiguous: ' + name)
    path.write_text(text.replace(before, after))

declarations = '''
/* Experimental, separately named machine binding only. */
bool lemma_softtlb_selected(void);
int64_t lemma_softtlb_window_ns(void);
bool lemma_softtlb_paused_capture(void);
bool lemma_softtlb_capture_begin(CPUState *, Error **);
void lemma_softtlb_capture_end(void);
bool lemma_softtlb_save(CPUState *, const char *, const char *, Error **);
void *lemma_softtlb_prepare(CPUState *, const char *, const char *, Error **);
bool lemma_softtlb_adopt(CPUState *, void *, Error **);
void lemma_softtlb_discard(void *);
'''
header = root / 'include/exec/cputlb.h'
text = header.read_text(); position = text.rfind('#endif')
if position < 0:
    raise SystemExit('SoftTLB header end missing')
header.write_text(text[:position] + declarations + '\n' + text[position:])
name = 'accel/tcg/cputlb.c'
replace(name, '#include "qemu/main-loop.h"',
        '#include "qemu/main-loop.h"\n#include "qemu/timer.h"')
replace(name, '/* DEBUG defines, enable DEBUG_TLB_LOG', '''
/* This separately named derivative makes eviction windows deterministic.
 * Historical machines retain the upstream host-time behavior. */
static int64_t lemma_tlb_window_clock(void)
{
    return lemma_softtlb_selected() ? lemma_softtlb_window_ns()
                                   : get_clock_realtime();
}

/* DEBUG defines, enable DEBUG_TLB_LOG''')
path = root / name
text = path.read_text(); text = text.replace('get_clock_realtime()', 'lemma_tlb_window_clock()')
text = text.replace(': lemma_tlb_window_clock();', ': get_clock_realtime();')
path.write_text(text)
replace(name, '    while (fast->table == NULL || desc->fulltlb == NULL) {', '''
    if (lemma_softtlb_selected() && (!fast->table || !desc->fulltlb)) {
        error_report("SoftTLB1 allocation would change logical cache capacity");
        abort();
    }
    while (fast->table == NULL || desc->fulltlb == NULL) {''')
path.write_text(path.read_text() + '\n#include "lemma_softtlb_qemu.inc.c"\n')
(root / 'accel/tcg/lemma_softtlb_qemu.inc.c').write_bytes(a.helper.read_bytes())

# Derive the existing canonical hardware class; dynamic casts to its parent
# continue to select its existing reset/ELF/device behavior.
path = root / 'hw/riscv/lemma_qemu.c'
path.write_text(path.read_text() + '''
static const TypeInfo lemma_softtlb_machine_type = {
    .name = MACHINE_TYPE_NAME("lemma-silicon-fast-softtlb"),
    .parent = MACHINE_TYPE_NAME("lemma-silicon-fast"),
};
static void lemma_softtlb_register_machine(void)
{
    type_register_static(&lemma_softtlb_machine_type);
}
type_init(lemma_softtlb_register_machine)
''')
path = root / 'qapi/migration.json'
path.write_text(path.read_text() + '''
##
# @lemma-save-machine-softtlb:
#
# Experimental paused logical SoftTLB pair.
#
# The machine binding is separately named.
#
# @filename: Exclusively created ordinary machine archive.
# @cache-filename: Exclusively created archive-bound logical sidecar.
#
# Since: 11.1
##
{ 'command': 'lemma-save-machine-softtlb',
  'data': { 'filename': 'str', 'cache-filename': 'str' } }
##
# @lemma-load-machine-softtlb:
#
# Validate a logical pair before adoption in a fresh private fork.
#
# @filename: Exact ordinary machine archive bound by the sidecar.
# @cache-filename: Complete logical sidecar.
#
# Since: 11.1
##
{ 'command': 'lemma-load-machine-softtlb',
  'data': { 'filename': 'str', 'cache-filename': 'str' } }
''')
path = root / 'migration/savevm.c'
text = path.read_text()
if text.count('void qmp_lemma_save_machine(') != 1 or text.count('void qmp_lemma_load_machine(') != 1:
    raise SystemExit('SoftTLB requires the exact maintained machine QMP boundary')
path.write_text(text + '''
#include "exec/cputlb.h"
#include "exec/icount.h"
void qmp_lemma_save_machine_softtlb(const char *filename,
                                   const char *cache_filename, Error **errp)
{
    if (!lemma_softtlb_selected() || !strcmp(filename, cache_filename)) {
        error_setg(errp, "SoftTLB1 requires its separately named binding and distinct files");
        return;
    }
    if (!lemma_softtlb_capture_begin(first_cpu, errp)) { return; }
    qmp_lemma_save_machine(filename, errp);
    if (!*errp) { lemma_softtlb_save(first_cpu, cache_filename, filename, errp); }
    lemma_softtlb_capture_end();
}
void qmp_lemma_load_machine_softtlb(const char *filename,
                                   const char *cache_filename, Error **errp)
{
    if (icount_get_raw() != 0 || !strcmp(filename, cache_filename)) {
        error_setg(errp, "SoftTLB1 restore requires a fresh never-run private fork");
        return;
    }
    void *logical = lemma_softtlb_prepare(first_cpu, cache_filename, filename, errp);
    if (!logical) { return; }
    /* Use the legal private incoming lifecycle; PRELAUNCH -> PAUSED is not
     * an upstream runstate edge. This changes no CPU/device execution state. */
    if (runstate_check(RUN_STATE_PRELAUNCH)) { runstate_set(RUN_STATE_INMIGRATE); }
    qmp_lemma_load_machine(filename, errp);
    if (*errp) { lemma_softtlb_discard(logical); return; }
    if (!lemma_softtlb_adopt(first_cpu, logical, errp)) { return; }
    /* The exclusively owned fresh destination starts in PRELAUNCH. Complete
     * successful adoption as PAUSED without running a CPU, notifying devices,
     * flushing caches or entering the ordinary block-draining stop path. */
    runstate_set(RUN_STATE_PAUSED);
}
''')

# This helper reads the same precise fixed-clock state without updating a CPU
# budget or requiring can_do_io. TLB flushes also occur inside SFENCE helpers.
name = 'accel/tcg/icount-common.c'
if hashlib.sha256((root/name).read_bytes()).hexdigest() != 'e24fcdcb35716a3ba77fa0acd510b78a5cfda4c9de8b767eadab95d7850d015b':
    raise SystemExit('unsupported applied icount source identity')
path = root/name
path.write_text(path.read_text() + '''
/* Experimental logical-cache resize window; no host wall time and no mutation. */
int64_t lemma_softtlb_window_ns(void)
{
    int64_t value;
    unsigned start;
    do {
        start = seqlock_read_begin(&timers_state.vm_clock_seqlock);
        int64_t raw = qatomic_read(&timers_state.qemu_icount);
        CPUState *cpu = current_cpu;
        if (cpu && cpu->running) {
            raw += icount_get_executed(cpu);
        }
        value = qatomic_read(&timers_state.qemu_icount_bias) + icount_to_ns(raw);
    } while (seqlock_read_retry(&timers_state.vm_clock_seqlock, start));
    return value;
}
''')

# A paused, complete pair needs all initially-dirty RAM pages, but no migration
# dirty-log transaction: that transaction flushes the original through tcg_commit.
name = 'migration/ram.c'
if hashlib.sha256((root/name).read_bytes()).hexdigest() != '0c941730301aecc6577437ce1e4fe62f492bcac0ee8f40d7163bacc6fb71379d':
    raise SystemExit('unsupported RAM migration source identity')
replace(name, '#include "savevm.h"', '#include "savevm.h"\n#include "exec/cputlb.h"')
path=root/name
text=path.read_text()
for start_marker,end_marker in [('static void ram_save_cleanup(', 'static void'),
                                 ('static bool ram_init_bitmaps(', 'static int')]:
    start=text.index(start_marker)
    end=text.index(end_marker,start+len(start_marker))
    section=text[start:end]
    before='if (!migrate_background_snapshot()) {'
    if section.count(before)!=1:raise SystemExit('ambiguous paused RAM boundary')
    section=section.replace(before,'if (!migrate_background_snapshot() && !lemma_softtlb_paused_capture()) {')
    text=text[:start]+section+text[end:]
path.write_text(text)
