/* Host-only QEMU logical SoftTLB experiment. Never linked into RV64.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Included in pinned accel/tcg/cputlb.c by patch_soft_tlb.py. */
#include "qapi/error.h"
#include "qemu/timer.h"
#include "hw/core/boards.h"
#include "qom/object.h"
#include "system/cpus.h"
#include "system/runstate.h"
#include "exec/icount.h"

#define LEMMA_TLB_LIMIT (64U * 1024U * 1024U)
#define LEMMA_TLB_SLOTS_LIMIT (256U * 1024U)
#define LEMMA_TLB_BINDING "lemma-silicon-fast-softtlb/0.2.0"

typedef struct LemmaTLBReader {
    const uint8_t *data;
    size_t at, size;
    bool bad;
} LemmaTLBReader;
typedef struct LemmaTLBMode {
    CPUTLBDesc desc;
    CPUTLBDescFast fast;
} LemmaTLBMode;
typedef struct LemmaTLBCandidate {
    CPUTLBCommon common;
    LemmaTLBMode mode[NB_MMU_MODES];
    uint64_t boundary, wake_count;
    uint32_t halted, interrupts;
    int32_t exception;
} LemmaTLBCandidate;

bool lemma_softtlb_selected(void)
{
    return object_dynamic_cast(OBJECT(qdev_get_machine()),
        MACHINE_TYPE_NAME("lemma-silicon-fast-softtlb")) != NULL;
}

extern void lemma_cpu_pending_work_stats(CPUState *, uint64_t *, uint64_t *);
extern bool lemma_cpu_restore_deadline_wakes(CPUState *, uint64_t);
static bool lemma_tlb_boundary(CPUState *cpu, Error **errp)
{
    if (!lemma_softtlb_selected() || !icount_enabled() ||
        runstate_is_running() || !cpu || CPU_NEXT(cpu) || !cpu->stopped || cpu->running) {
        error_setg(errp, "SoftTLB2 requires its selected paused single-CPU binding");
        return false;
    }
    /* Function pointers/opaque work are not logical state in schema1.
     * Never drain them or manufacture a clean boundary for saving. */
    uint64_t pending, wakes;
    lemma_cpu_pending_work_stats(cpu, &pending, &wakes);
    if (pending > 1024 || wakes != pending) {
        error_setg(errp, "SoftTLB2 cannot represent pending CPU work: total=%"PRIu64" icount_deadline_wakes=%"PRIu64" unknown=%"PRIu64,
                   pending, wakes, pending - wakes);
        return false;
    }
    return true;
}

static bool lemma_tlb_capture_active;
static uint64_t lemma_tlb_capture_wakes;
bool lemma_softtlb_paused_capture(void)
{
    return lemma_tlb_capture_active;
}
bool lemma_softtlb_capture_begin(CPUState *cpu, Error **errp)
{
    if (!lemma_tlb_boundary(cpu, errp)) { return false; }
    if (lemma_tlb_capture_active || (global_dirty_tracking & GLOBAL_DIRTY_MIGRATION)) {
        error_setg(errp, "SoftTLB2 capture cannot overlap dirty logging/capture");
        return false;
    }
    uint64_t total, wakes;
    lemma_cpu_pending_work_stats(cpu, &total, &wakes);
    if (total != wakes || total > 1024) { error_setg(errp, "SoftTLB2 changed wake boundary"); return false; }
    lemma_tlb_capture_wakes = total;
    lemma_tlb_capture_active = true;
    return true;
}
void lemma_softtlb_capture_end(void)
{
    assert(lemma_tlb_capture_active);
    lemma_tlb_capture_active = false;
    lemma_tlb_capture_wakes = 0;
}

static void lemma_tlb_u64(GByteArray *out, uint64_t value)
{
    uint8_t bytes[8];
    stq_le_p(bytes, value);
    g_byte_array_append(out, bytes, 8);
}
static uint64_t lemma_tlb_read64(LemmaTLBReader *in)
{
    if (in->bad || in->at > in->size || in->size - in->at < 8) {
        in->bad = true;
        return 0;
    }
    uint64_t value = ldq_le_p(in->data + in->at);
    in->at += 8;
    return value;
}
static void lemma_tlb_string(GByteArray *out, const char *text)
{
    size_t n = strlen(text);
    lemma_tlb_u64(out, n);
    g_byte_array_append(out, (const uint8_t *)text, n);
}
static char *lemma_tlb_read_string(LemmaTLBReader *in)
{
    uint64_t n = lemma_tlb_read64(in);
    if (in->bad || n > 1024 || in->at > in->size ||
        n > in->size - in->at || memchr(in->data + in->at, 0, n)) {
        in->bad = true;
        return g_strdup("");
    }
    char *value = g_strndup((const char *)in->data + in->at, n);
    in->at += n;
    return value;
}
static uint64_t lemma_tlb_attrs(MemTxAttrs a)
{
    return a.secure | (uint64_t)a.space << 1 | (uint64_t)a.user << 3 |
        (uint64_t)a.memory << 4 | (uint64_t)a.debug << 5 |
        (uint64_t)a.requester_id << 6 | (uint64_t)a.pid << 22 |
        (uint64_t)a.address_type << 30 | (uint64_t)a.unspecified << 31;
}
static MemTxAttrs lemma_tlb_read_attrs(uint64_t value, LemmaTLBReader *in)
{
    MemTxAttrs a = { 0 };
    if (value >> 32) { in->bad = true; }
    a.secure = value & 1; a.space = (value >> 1) & 3;
    a.user = (value >> 3) & 1; a.memory = (value >> 4) & 1;
    a.debug = (value >> 5) & 1; a.requester_id = (value >> 6) & 65535;
    a.pid = (value >> 22) & 255; a.address_type = (value >> 30) & 1;
    a.unspecified = (value >> 31) & 1;
    return a;
}
static void lemma_tlb_nullable(GByteArray *out, const char *value)
{
    lemma_tlb_u64(out, value != NULL);
    if (value) { lemma_tlb_string(out, value); }
}
static char *lemma_tlb_read_nullable(LemmaTLBReader *in)
{
    uint64_t present = lemma_tlb_read64(in);
    if (present > 1) { in->bad = true; }
    return present == 1 ? lemma_tlb_read_string(in) : NULL;
}
static char *lemma_tlb_owner(MemoryRegion *mr)
{
    Object *owner = memory_region_owner(mr);
    char *path = owner ? object_get_canonical_path(owner) : NULL;
    return path;
}

/* Resolve stable physical topology, never the guest page table. No MMIO read
 * or access is performed. Do not refill/evict with tlb_set_page_full. */
static MemoryRegionSection *lemma_tlb_section(CPUState *cpu,
        CPUTLBEntryFull *full, hwaddr *xlat, Error **errp)
{
    hwaddr size = TARGET_PAGE_SIZE;
    int prot = full->prot;
    int asidx = cpu_asidx_from_attrs(cpu, full->attrs);
    MemoryRegionSection *section = address_space_translate_for_iotlb(cpu,
        asidx, full->phys_addr, xlat, &size, full->attrs, &prot);
    if (!section || !section->mr || size < TARGET_PAGE_SIZE ||
        memory_region_is_iommu(section->mr)) {
        error_setg(errp, "SoftTLB2 cannot bind the saved physical mapping");
        return NULL;
    }
    return section;
}
static void lemma_tlb_mapping(GByteArray *out, MemoryRegionSection *s,
                             hwaddr xlat)
{
    char *owner = lemma_tlb_owner(s->mr);
    lemma_tlb_nullable(out, memory_region_name(s->mr));
    lemma_tlb_nullable(out, object_get_typename(OBJECT(s->mr)));
    lemma_tlb_nullable(out, owner); g_free(owner);
    lemma_tlb_u64(out, s->offset_within_address_space);
    lemma_tlb_u64(out, s->offset_within_region);
    lemma_tlb_u64(out, int128_getlo(s->size));
    lemma_tlb_u64(out, int128_gethi(s->size));
    lemma_tlb_u64(out, s->readonly);
    lemma_tlb_u64(out, memory_region_is_ram(s->mr));
    lemma_tlb_u64(out, memory_region_is_romd(s->mr));
    lemma_tlb_u64(out, xlat);
}
static bool lemma_tlb_mapping_matches(LemmaTLBReader *in,
        MemoryRegionSection *s, hwaddr xlat)
{
    char *name = lemma_tlb_read_nullable(in), *type = lemma_tlb_read_nullable(in);
    char *old_owner = lemma_tlb_read_nullable(in), *owner = lemma_tlb_owner(s->mr);
    bool same = !g_strcmp0(name, memory_region_name(s->mr)) &&
        !g_strcmp0(type, object_get_typename(OBJECT(s->mr))) &&
        !g_strcmp0(owner, old_owner);
    g_free(name); g_free(type); g_free(owner); g_free(old_owner);
    same &= lemma_tlb_read64(in) == s->offset_within_address_space;
    same &= lemma_tlb_read64(in) == s->offset_within_region;
    same &= lemma_tlb_read64(in) == int128_getlo(s->size);
    same &= lemma_tlb_read64(in) == (uint64_t)int128_gethi(s->size);
    same &= lemma_tlb_read64(in) == s->readonly;
    same &= lemma_tlb_read64(in) == memory_region_is_ram(s->mr);
    same &= lemma_tlb_read64(in) == memory_region_is_romd(s->mr);
    same &= lemma_tlb_read64(in) == xlat;
    return same && !in->bad;
}
/* Unnamed subpage wrappers do not identify their leaf MMIO mappings.
 * Bind every mapped segment and every hole of the complete physical page. */
static bool lemma_tlb_page_identity(CPUState *cpu, CPUTLBEntryFull *full,
                                   uint8_t digest[32], Error **errp)
{
    AddressSpace *as = cpu_get_address_space(cpu, cpu_asidx_from_attrs(cpu, full->attrs));
    if (!as || !as->root || as->root->container) {
        error_setg(errp, "SoftTLB2 unsupported physical address-space root");
        return false;
    }
    GByteArray *out = g_byte_array_new();
    uint64_t offset = 0;
    while (offset < TARGET_PAGE_SIZE) {
        uint64_t at = full->phys_addr + offset, remain = TARGET_PAGE_SIZE - offset;
        MemoryRegionSection segment = memory_region_find(as->root, at, remain);
        if (!segment.mr) {
            lemma_tlb_u64(out, 0); lemma_tlb_u64(out, offset); lemma_tlb_u64(out, remain);
            offset += remain; continue;
        }
        if (segment.offset_within_address_space > at) {
            uint64_t gap = segment.offset_within_address_space - at;
            if (gap > remain) { memory_region_unref(segment.mr); goto bad; }
            lemma_tlb_u64(out, 0); lemma_tlb_u64(out, offset); lemma_tlb_u64(out, gap);
            offset += gap; at += gap; remain -= gap;
        }
        uint64_t length = int128_getlo(segment.size);
        if (int128_gethi(segment.size) || !length || length > remain ||
            segment.offset_within_address_space != at || memory_region_is_iommu(segment.mr)) {
            memory_region_unref(segment.mr); goto bad;
        }
        lemma_tlb_u64(out, 1); lemma_tlb_u64(out, offset); lemma_tlb_u64(out, length);
        lemma_tlb_mapping(out, &segment, segment.offset_within_region);
        memory_region_unref(segment.mr); offset += length;
    }
    GChecksum *sum = g_checksum_new(G_CHECKSUM_SHA256); gsize size = 32;
    g_checksum_update(sum, out->data, out->len); g_checksum_get_digest(sum, digest, &size);
    g_checksum_free(sum); g_byte_array_free(out, true); return true;
bad:
    g_byte_array_free(out, true);
    error_setg(errp, "SoftTLB2 incomplete/unsupported physical page topology");
    return false;
}
static uint64_t lemma_tlb_vpage(const CPUTLBEntry *entry, bool *ok)
{
    uint64_t page = UINT64_MAX;
    for (int i = 0; i < 3; i++) {
        if (entry->addr_idx[i] != (uintptr_t)-1) {
            if (entry->addr_idx[i] & ~(TARGET_PAGE_MASK | TLB_FLAGS_MASK)) {
                *ok = false;
            }
            uint64_t value = entry->addr_idx[i] & TARGET_PAGE_MASK;
            if (page != UINT64_MAX && value != page) { *ok = false; }
            page = value;
        }
    }
    return page;
}
static bool lemma_tlb_write_entry(CPUState *cpu, GByteArray *out,
        const CPUTLBEntry *entry, CPUTLBEntryFull *full, Error **errp)
{
    bool ok = true;
    lemma_tlb_u64(out, !tlb_entry_is_empty(entry));
    if (tlb_entry_is_empty(entry)) { return true; }
    uint64_t page = lemma_tlb_vpage(entry, &ok);
    hwaddr xlat;
    MemoryRegionSection *section = lemma_tlb_section(cpu, full, &xlat, errp);
    if (!section) { return false; }
    hwaddr iotlb = xlat;
    uintptr_t host = 0;
    if (memory_region_is_ram(section->mr)) {
        iotlb += memory_region_get_ram_addr(section->mr);
    }
    if (memory_region_is_ram(section->mr) || memory_region_is_romd(section->mr)) {
        host = (uintptr_t)memory_region_get_ram_ptr(section->mr) + xlat;
    }
    if (!ok || full->section != section || full->phys_addr & ~TARGET_PAGE_MASK ||
        full->xlat_offset != iotlb - page || entry->addend != host - page ||
        full->attrs._reserved1 || full->attrs._reserved2) {
        error_setg(errp, "SoftTLB2 cached mapping identity/addend is not admissible");
        return false;
    }
    for (int i = 0; i < 3; i++) { lemma_tlb_u64(out, entry->addr_idx[i]); }
    lemma_tlb_u64(out, full->phys_addr);
    lemma_tlb_u64(out, lemma_tlb_attrs(full->attrs));
    lemma_tlb_u64(out, full->prot); lemma_tlb_u64(out, full->lg_page_size);
    lemma_tlb_u64(out, full->tlb_fill_flags);
    for (int i = 0; i < MMU_ACCESS_COUNT; i++) {
        lemma_tlb_u64(out, full->slow_flags[i]);
    }
    lemma_tlb_u64(out, full->extra.arm.pte_attrs);
    lemma_tlb_u64(out, full->extra.arm.shareability);
    lemma_tlb_u64(out, full->extra.arm.guarded);
    lemma_tlb_mapping(out, section, xlat);
    uint8_t page_identity[32];
    if (!lemma_tlb_page_identity(cpu, full, page_identity, errp)) { return false; }
    g_byte_array_append(out, page_identity, 32);
    return out->len <= LEMMA_TLB_LIMIT;
}
static bool lemma_tlb_read_entry(CPUState *cpu, LemmaTLBReader *in,
        CPUTLBEntry *entry, CPUTLBEntryFull *full, Error **errp)
{
    uint64_t valid = lemma_tlb_read64(in);
    memset(entry, -1, sizeof(*entry)); memset(full, 0, sizeof(*full));
    if (!valid) { return !in->bad; }
    if (valid != 1) { in->bad = true; return false; }
    for (int i = 0; i < 3; i++) { entry->addr_idx[i] = lemma_tlb_read64(in); }
    full->phys_addr = lemma_tlb_read64(in);
    full->attrs = lemma_tlb_read_attrs(lemma_tlb_read64(in), in);
    uint64_t fields[6 + MMU_ACCESS_COUNT];
    for (int i = 0; i < ARRAY_SIZE(fields); i++) {
        fields[i] = lemma_tlb_read64(in);
        if (fields[i] > 255) { in->bad = true; }
    }
    full->prot = fields[0]; full->lg_page_size = fields[1];
    full->tlb_fill_flags = fields[2];
    for (int i = 0; i < MMU_ACCESS_COUNT; i++) { full->slow_flags[i] = fields[3+i]; }
    full->extra.arm.pte_attrs = fields[3+MMU_ACCESS_COUNT];
    full->extra.arm.shareability = fields[4+MMU_ACCESS_COUNT];
    full->extra.arm.guarded = fields[5+MMU_ACCESS_COUNT];
    bool ok = true; uint64_t page = lemma_tlb_vpage(entry, &ok);
    if (in->bad || !ok || tlb_entry_is_empty(entry) ||
        full->phys_addr & ~TARGET_PAGE_MASK || full->lg_page_size > 63 ||
        (full->prot & ~PAGE_RWX) ||
        fields[5+MMU_ACCESS_COUNT] > 1) {
        error_setg(errp, "SoftTLB2 malformed logical entry"); return false;
    }
    for (int i = 0; i < MMU_ACCESS_COUNT; i++) {
        if (full->slow_flags[i] & ~TLB_SLOW_FLAGS_MASK) {
            error_setg(errp, "SoftTLB2 unsupported slow flags"); return false;
        }
    }
    hwaddr xlat;
    MemoryRegionSection *section = lemma_tlb_section(cpu, full, &xlat, errp);
    if (!section) { return false; }
    if (!lemma_tlb_mapping_matches(in, section, xlat)) {
        error_setg(errp, "SoftTLB2 physical mapping identity mismatch"); return false;
    }
    uint8_t page_identity[32];
    if (!lemma_tlb_page_identity(cpu, full, page_identity, errp) || in->bad ||
        in->at > in->size || in->size - in->at < 32 ||
        memcmp(in->data + in->at, page_identity, 32)) {
        if (!*errp) { error_setg(errp, "SoftTLB2 complete physical page identity mismatch"); }
        return false;
    }
    in->at += 32;
    hwaddr iotlb = xlat; uintptr_t host = 0;
    if (memory_region_is_ram(section->mr)) { iotlb += memory_region_get_ram_addr(section->mr); }
    if (memory_region_is_ram(section->mr) || memory_region_is_romd(section->mr)) {
        host = (uintptr_t)memory_region_get_ram_ptr(section->mr) + xlat;
    }
    entry->addend = host - page;
    full->xlat_offset = iotlb - page; full->section = section;
    return !in->bad;
}
static bool lemma_tlb_hash_file(const char *filename, uint8_t bytes[32], Error **errp)
{
    int fd = open(filename, O_RDONLY | O_CLOEXEC); struct stat st;
    if (fd < 0 || fstat(fd, &st) || !S_ISREG(st.st_mode) ||
        st.st_size < 1 || st.st_size > 768LL * 1024 * 1024) {
        if (fd >= 0) { close(fd); }
        error_setg(errp, "SoftTLB2 invalid bound machine-state file"); return false;
    }
    GChecksum *sum = g_checksum_new(G_CHECKSUM_SHA256); uint8_t buffer[65536];
    ssize_t n; uint64_t size = 0;
    while ((n = read(fd, buffer, sizeof(buffer))) != 0) {
        if (n < 0) { if (errno == EINTR) { continue; } break; }
        size += n; g_checksum_update(sum, buffer, n);
    }
    close(fd); gsize digest_size = 32;
    bool ok = n == 0 && size == st.st_size;
    if (ok) { g_checksum_get_digest(sum, bytes, &digest_size); }
    else { error_setg(errp, "SoftTLB2 machine-state hash read failed"); }
    g_checksum_free(sum); return ok;
}
bool lemma_softtlb_save(CPUState *cpu, const char *filename,
                       const char *machine_state, Error **errp)
{
    RCU_READ_LOCK_GUARD();
    uint8_t digest[32];
    if (!lemma_tlb_boundary(cpu, errp) ||
        !lemma_tlb_hash_file(machine_state, digest, errp)) { return false; }
    uint64_t save_wake_count, save_known_wakes;
    lemma_cpu_pending_work_stats(cpu, &save_wake_count, &save_known_wakes);
    if (save_wake_count != save_known_wakes || save_wake_count != lemma_tlb_capture_wakes) { error_setg(errp, "SoftTLB2 source wake queue changed during capture"); return false; }
    GByteArray *out = g_byte_array_new();
    g_byte_array_append(out, (const uint8_t *)"LMTLB02\0", 8);
    lemma_tlb_u64(out, 2); lemma_tlb_string(out, LEMMA_TLB_BINDING);
    g_byte_array_append(out, digest, 32);
    lemma_tlb_u64(out, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));
    /* Explicit inactive-boundary witness and complete migrated CPU pending
     * fields. The typed icount-deadline wake queue is preserved; unknown work is rejected. */
    lemma_tlb_u64(out, cpu->cpu_index);
    lemma_tlb_u64(out, cpu->stopped); lemma_tlb_u64(out, cpu->running);
    lemma_tlb_u64(out, lemma_tlb_capture_wakes);
    lemma_tlb_u64(out, cpu->halted);
    lemma_tlb_u64(out, cpu->interrupt_request);
    lemma_tlb_u64(out, (uint32_t)cpu->exception_index);
    lemma_tlb_u64(out, NB_MMU_MODES); lemma_tlb_u64(out, TARGET_PAGE_BITS);
    lemma_tlb_u64(out, CPU_TLB_ENTRY_BITS);
    CPUTLBCommon *c = &cpu->neg.tlb.c;
    lemma_tlb_u64(out, c->dirty); lemma_tlb_u64(out, c->full_flush_count);
    lemma_tlb_u64(out, c->part_flush_count); lemma_tlb_u64(out, c->elide_flush_count);
    bool ok = true; size_t total = 0;
    qemu_spin_lock(&c->lock);
    for (int m = 0; m < NB_MMU_MODES && ok; m++) {
        CPUTLBDesc *d = &cpu->neg.tlb.d[m]; CPUTLBDescFast *f = cpu_tlb_fast(cpu, m);
        size_t entries = tlb_n_entries(f); total += entries;
        if (total > LEMMA_TLB_SLOTS_LIMIT) { ok = false; break; }
        lemma_tlb_u64(out, entries); lemma_tlb_u64(out, d->large_page_addr);
        lemma_tlb_u64(out, d->large_page_mask); lemma_tlb_u64(out, d->window_begin_ns);
        lemma_tlb_u64(out, d->window_max_entries); lemma_tlb_u64(out, d->n_used_entries);
        lemma_tlb_u64(out, d->vindex);
        for (size_t i = 0; i < entries && ok; i++) {
            ok = lemma_tlb_write_entry(cpu, out, &f->table[i], &d->fulltlb[i], errp);
        }
        for (int i = 0; i < CPU_VTLB_SIZE && ok; i++) {
            ok = lemma_tlb_write_entry(cpu, out, &d->vtable[i], &d->vfulltlb[i], errp);
        }
    }
    qemu_spin_unlock(&c->lock);
    if (!ok || out->len > LEMMA_TLB_LIMIT - 32) {
        if (!*errp) { error_setg(errp, "SoftTLB2 capture exceeds its logical-state bound"); }
        g_byte_array_free(out, true); return false;
    }
    GChecksum *sum = g_checksum_new(G_CHECKSUM_SHA256); gsize ds = 32;
    g_checksum_update(sum, out->data, out->len); g_checksum_get_digest(sum, digest, &ds);
    g_checksum_free(sum); g_byte_array_append(out, digest, 32);
    int fd = open(filename, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0) { error_setg(errp, "SoftTLB2 sidecar must be exclusively created"); ok = false; }
    size_t at = 0;
    while (ok && at < out->len) {
        ssize_t n = write(fd, out->data + at, out->len - at);
        if (n < 0 && errno == EINTR) { continue; }
        if (n <= 0) { ok = false; } else { at += n; }
    }
    if (fd >= 0) {
        if (fsync(fd)) { ok = false; }
        if (close(fd)) { ok = false; }
    }
    if (!ok && !*errp) { error_setg(errp, "SoftTLB2 sidecar publication failed"); }
    g_byte_array_free(out, true); return ok;
}
static void lemma_tlb_candidate_free(LemmaTLBCandidate *candidate)
{
    for (int m = 0; m < NB_MMU_MODES; m++) {
        g_free(candidate->mode[m].fast.table); g_free(candidate->mode[m].desc.fulltlb);
    }
    g_free(candidate);
}
/* Complete validation/rebinding in fresh arrays; caller adopts only after its
 * paired ordinary VMState restore succeeds. No original table is changed. */
void *lemma_softtlb_prepare(CPUState *cpu, const char *filename,
                          const char *machine_state, Error **errp)
{
    RCU_READ_LOCK_GUARD();
    uint8_t expected[32], actual[32]; struct stat st;
    if (!lemma_tlb_boundary(cpu, errp) ||
        !lemma_tlb_hash_file(machine_state, expected, errp)) { return NULL; }
    if (stat(filename, &st) || !S_ISREG(st.st_mode) || st.st_size < 160 ||
        st.st_size > LEMMA_TLB_LIMIT) {
        error_setg(errp, "SoftTLB2 sidecar length/type rejected"); return NULL;
    }
    gchar *bytes = NULL; gsize length;
    if (!g_file_get_contents(filename, &bytes, &length, NULL) || length != st.st_size) {
        g_free(bytes); error_setg(errp, "SoftTLB2 sidecar read failed"); return NULL;
    }
    GChecksum *sum = g_checksum_new(G_CHECKSUM_SHA256); gsize ds = 32;
    g_checksum_update(sum, (const uint8_t *)bytes, length - 32);
    g_checksum_get_digest(sum, actual, &ds); g_checksum_free(sum);
    if (memcmp(actual, bytes + length - 32, 32) || memcmp(bytes, "LMTLB02\0", 8)) {
        g_free(bytes); error_setg(errp, "SoftTLB2 checksum/magic mismatch"); return NULL;
    }
    LemmaTLBReader in = { .data = (uint8_t *)bytes, .at = 8, .size = length - 32 };
    uint64_t version = lemma_tlb_read64(&in); char *binding = lemma_tlb_read_string(&in);
    bool ok = version == 2 && !strcmp(binding, LEMMA_TLB_BINDING);
    g_free(binding);
    if (in.bad || in.size - in.at < 32 || memcmp(expected, in.data + in.at, 32)) { ok = false; }
    in.at += 32;
    /* Saved virtual time is adopted by ordinary VMState, not by this parser. */
    uint64_t boundary = lemma_tlb_read64(&in);
    ok &= lemma_tlb_read64(&in) == cpu->cpu_index;
    ok &= lemma_tlb_read64(&in) == 1;
    ok &= lemma_tlb_read64(&in) == 0;
    uint64_t wake_count = lemma_tlb_read64(&in);
    ok &= wake_count <= 1024;
    uint64_t halted = lemma_tlb_read64(&in);
    uint64_t interrupts = lemma_tlb_read64(&in);
    uint64_t exception = lemma_tlb_read64(&in);
    ok &= halted <= 1 && interrupts <= UINT32_MAX && exception <= UINT32_MAX;
    ok &= lemma_tlb_read64(&in) == NB_MMU_MODES;
    ok &= lemma_tlb_read64(&in) == TARGET_PAGE_BITS;
    ok &= lemma_tlb_read64(&in) == CPU_TLB_ENTRY_BITS;
    LemmaTLBCandidate *candidate = g_try_new0(LemmaTLBCandidate, 1);
    if (!candidate) { ok = false; }
    if (!ok || in.bad) {
        g_free(candidate); g_free(bytes); error_setg(errp, "SoftTLB2 bound schema/identity mismatch"); return NULL;
    }
    uint64_t dirty = lemma_tlb_read64(&in);
    candidate->common.dirty = dirty;
    candidate->boundary = boundary; candidate->wake_count = wake_count;
    candidate->halted = halted; candidate->interrupts = interrupts;
    candidate->exception = (int32_t)exception;
    candidate->common.full_flush_count = lemma_tlb_read64(&in);
    candidate->common.part_flush_count = lemma_tlb_read64(&in);
    candidate->common.elide_flush_count = lemma_tlb_read64(&in);
    if (dirty >> NB_MMU_MODES || boundary > INT64_MAX) { ok = false; }
    size_t total = 0;
    for (int m = 0; m < NB_MMU_MODES && ok; m++) {
        LemmaTLBMode *mode = &candidate->mode[m]; size_t entries = lemma_tlb_read64(&in);
        if (!is_power_of_2(entries) || entries < (1 << CPU_TLB_DYN_MIN_BITS) ||
            entries > LEMMA_TLB_SLOTS_LIMIT || total > LEMMA_TLB_SLOTS_LIMIT - entries) { ok = false; break; }
        total += entries; mode->fast.mask = (entries - 1) << CPU_TLB_ENTRY_BITS;
        mode->desc.large_page_addr = lemma_tlb_read64(&in);
        mode->desc.large_page_mask = lemma_tlb_read64(&in);
        mode->desc.window_begin_ns = lemma_tlb_read64(&in);
        mode->desc.window_max_entries = lemma_tlb_read64(&in);
        mode->desc.n_used_entries = lemma_tlb_read64(&in);
        mode->desc.vindex = lemma_tlb_read64(&in);
        if (mode->desc.window_begin_ns < 0 || mode->desc.window_begin_ns > boundary ||
            mode->desc.n_used_entries > entries || mode->desc.window_max_entries > entries) { ok = false; break; }
        mode->fast.table = g_try_new(CPUTLBEntry, entries);
        mode->desc.fulltlb = g_try_new(CPUTLBEntryFull, entries);
        if (!mode->fast.table || !mode->desc.fulltlb) { ok = false; break; }
        for (size_t i = 0; i < entries && ok; i++) {
            ok = lemma_tlb_read_entry(cpu, &in, &mode->fast.table[i], &mode->desc.fulltlb[i], errp);
            if (ok && !tlb_entry_is_empty(&mode->fast.table[i])) {
                bool tags_ok = true;
                uint64_t page = lemma_tlb_vpage(&mode->fast.table[i], &tags_ok);
                ok = tags_ok && ((page >> TARGET_PAGE_BITS) & (entries - 1)) == i;
            }
        }
        for (int i = 0; i < CPU_VTLB_SIZE && ok; i++) {
            ok = lemma_tlb_read_entry(cpu, &in, &mode->desc.vtable[i], &mode->desc.vfulltlb[i], errp);
        }
    }
    g_free(bytes);
    if (!ok || in.bad || in.at != in.size) {
        lemma_tlb_candidate_free(candidate);
        if (!*errp) { error_setg(errp, "SoftTLB2 malformed metadata/trailing bytes/allocation failure"); }
        return NULL;
    }
    return candidate;
}
void lemma_softtlb_discard(void *opaque)
{
    lemma_tlb_candidate_free(opaque);
}
bool lemma_softtlb_adopt(CPUState *cpu, void *opaque, Error **errp)
{
    LemmaTLBCandidate *candidate = opaque; CPUTLBCommon *c = &cpu->neg.tlb.c;
    if (!lemma_tlb_boundary(cpu, errp) ||
        qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) != candidate->boundary ||
        cpu->halted != candidate->halted ||
        cpu->interrupt_request != candidate->interrupts ||
        cpu->exception_index != candidate->exception) {
        if (!*errp) { error_setg(errp, "SoftTLB2 paired VMState virtual boundary mismatch"); }
        lemma_tlb_candidate_free(candidate); return false;
    }
    /* Complete the final fallible validation before replacing any cache table.
     * A rejected unknown callback leaves all original logical tables intact. */
    if (!lemma_cpu_restore_deadline_wakes(cpu, candidate->wake_count)) {
        error_setg(errp, "SoftTLB2 unknown construction-time work at adoption");
        lemma_tlb_candidate_free(candidate); return false;
    }
    qemu_spin_lock(&c->lock);
    c->dirty = candidate->common.dirty;
    c->full_flush_count = candidate->common.full_flush_count;
    c->part_flush_count = candidate->common.part_flush_count;
    c->elide_flush_count = candidate->common.elide_flush_count;
    for (int m = 0; m < NB_MMU_MODES; m++) {
        CPUTLBDescFast *f = cpu_tlb_fast(cpu, m);
        g_free(f->table); g_free(cpu->neg.tlb.d[m].fulltlb);
        *f = candidate->mode[m].fast; cpu->neg.tlb.d[m] = candidate->mode[m].desc;
        candidate->mode[m].fast.table = NULL; candidate->mode[m].desc.fulltlb = NULL;
    }
    qemu_spin_unlock(&c->lock);
    lemma_tlb_candidate_free(candidate);
    return true;
}
