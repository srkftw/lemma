/* Raw external bytes only. Serial registers, FIFO, IRQs and guest parsing are
 * the existing QEMU16550 and maintained Lean software. No packet interpretation.
 * Included only by the explicit raw-UART backend derivation.
 * SPDX-License-Identifier: GPL-2.0-or-later */
#include "chardev/char.h"
#include "hw/core/cpu.h"

static void lemma_uart_poll(void *opaque)
{
    LemmaDevices *s = opaque;
    LemmaUARTIngress *u = &s->uart_ingress;
    uint64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    Chardev *chr = qemu_chr_find("serial0");
    if (u->poll_calls != UINT64_MAX) { u->poll_calls++; }
    if (!u->enabled || !u->count) {
        return;
    }
    if (!chr) {
        error_report("Lemma raw UART lost its declared serial0 frontend");
        exit(1);
    }
    if (u->flow && u->due[u->head] <= now && u->earliest_ns <= now &&
        qemu_chr_be_can_write(chr) <= 0) {
        /* flow/1: no retry timer while the actual 16550 cannot receive.
         * Its normal RBR read calls qemu_chr_fe_accept_input below. */
        u->blocked = true;
        return;
    }
    if (u->due[u->head] <= now && u->earliest_ns <= now &&
        qemu_chr_be_can_write(chr) > 0) {
        if (now > INT64_MAX - 10) {
            error_report("Lemma raw UART virtual polling clock exhausted");
            exit(1);
        }
        uint8_t byte = u->bytes[u->head];
        u->bytes[u->head] = 0;
        u->due[u->head] = 0;
        u->head = (u->head + 1) % LEMMA_UART_INGRESS_CAPACITY;
        u->count--;
        if (u->delivered == UINT64_MAX) {
            error_report("Lemma raw UART delivered counter exhausted");
            exit(1);
        }
        u->delivered++;
        u->earliest_ns = now + 10;
        /* can_write was checked under QEMU's device lock. This enters the
         * normal serial receive callback, never an MMIO/debugger write. */
        qemu_chr_be_write(chr, &byte, 1);
    }
    if (u->count) {
        if (now > INT64_MAX - 10) {
            error_report("Lemma raw UART virtual polling clock exhausted");
            exit(1);
        }
        timer_mod_ns(u->timer, MAX(now + 10, u->due[u->head]));
    }
}

/* Only the owned serial0 frontend can wake a flow/1 blocked admission.
 * Never deliver synchronously from a UART register read. The next timer is
 * at least 10ns after that read and no earlier than arrival/minimum byte gap.
 * This post-backpressure timing is an explicit successor to paced/1 polling. */
void lemma_raw_uart_accept_input(Chardev *chr)
{
    LemmaDevices *s = binding_devices;
    if (!s || !s->fast_binding || chr != qemu_chr_find("serial0")) { return; }
    LemmaUARTIngress *u = &s->uart_ingress;
    if (!u->enabled || !u->flow || !u->blocked || !u->count ||
        qemu_chr_be_can_write(chr) <= 0) { return; }
    uint64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (now > INT64_MAX - 10) {
        error_report("Lemma raw UART flow clock exhausted"); exit(1);
    }
    u->blocked = false;
    if (u->wakeups != UINT64_MAX) { u->wakeups++; }
    timer_mod_ns(u->timer, MAX(now + 10, MAX(u->due[u->head], u->earliest_ns)));
}

static char *lemma_uart_flow_version(Object *obj, Error **errp)
{
    return g_strdup(LEMMA_PAPER_PEN(obj)->fast_binding ?
                    "lemma-raw-uart-flow/1" : "disabled");
}

static void lemma_uart_flow_enable(Object *obj, const char *value, Error **errp)
{
    LemmaDevices *s = LEMMA_PAPER_PEN(obj);
    LemmaUARTIngress *u = &s->uart_ingress;
    if (strcmp(value, "lemma-raw-uart-flow/1") || !s->fast_binding ||
        !u->enabled || u->flow || u->count || runstate_is_running() ||
        qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) != 0) {
        error_setg(errp, "flow/1 requires an enabled reset paused raw UART");
        return;
    }
    u->flow = true;
}

static void lemma_uart_reset(LemmaDevices *s)
{
    LemmaUARTIngress *u = &s->uart_ingress;
    if (u->timer) {
        timer_del(u->timer);
    }
    if (UINT64_MAX - u->canceled < u->count) {
        error_report("Lemma raw UART cancellation counter exhausted");
        exit(1);
    }
    u->canceled += u->count;
    u->head = u->count = 0;
    u->blocked = false;
    u->earliest_ns = 0;
    memset(u->bytes, 0, sizeof(u->bytes));
    memset(u->due, 0, sizeof(u->due));
    if (u->enabled) {
        if (u->reset_epoch == UINT64_MAX) {
            error_report("Lemma raw UART reset epoch exhausted");
            exit(1);
        }
        u->reset_epoch++;
    }
}

static char *lemma_uart_version(Object *obj, Error **errp)
{
    return g_strdup(LEMMA_PAPER_PEN(obj)->fast_binding ? "lemma-raw-uart/1" : "disabled");
}

static void lemma_uart_enable(Object *obj, const char *value, Error **errp)
{
    LemmaDevices *s = LEMMA_PAPER_PEN(obj);
    Chardev *chr = qemu_chr_find("serial0");
    if (strcmp(value, "lemma-raw-uart/1") || !s->fast_binding ||
        qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) != 0 || runstate_is_running() ||
        !chr || qemu_chr_be_can_write(chr) <= 0 || s->uart_ingress.enabled) {
        error_setg(errp, "raw UART enable requires a reset paused fast CPU and its empty serial0 frontend");
        return;
    }
    s->uart_ingress.enabled = true;
    s->uart_ingress.reset_epoch = 1;
}

static void lemma_uart_inject(Object *obj, const char *value, Error **errp)
{
    LemmaUARTIngress *u = &LEMMA_PAPER_PEN(obj)->uart_ingress;
    g_auto(GStrv) words = g_strsplit(value, " ", -1);
    GError *error = NULL;
    uint64_t when;
    if (!u->enabled || runstate_is_running() || g_strv_length(words) != 2 ||
        !g_ascii_string_to_unsigned(words[0], 10, 0, INT64_MAX - 10, &when, &error)) {
        error_setg(errp, "raw UART requires an enabled port, bounded nanoseconds and one hex payload");
        g_clear_error(&error);
        return;
    }
    size_t hex = strlen(words[1]);
    if (!hex || hex % 2 || hex / 2 > LEMMA_UART_INGRESS_CAPACITY - u->count ||
        hex / 2 > UINT64_MAX - u->accepted ||
        when < (uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)) {
        error_setg(errp, "raw UART payload capacity or ordered delivery boundary exceeded");
        return;
    }
    for (size_t i = 0; i < hex; i++) {
        if (!g_ascii_isxdigit(words[1][i])) {
            error_setg(errp, "raw UART payload is not hexadecimal");
            return;
        }
    }
    /* Validate everything before mutating any byte, count or timer. Queued
     * timestamps are raw external input, not an assertion of guest receipt. */
    uint32_t amount = hex / 2, insertion = u->count;
    while (insertion &&
           u->due[(u->head + insertion - 1) % LEMMA_UART_INGRESS_CAPACITY] > when) {
        insertion--;
    }
    /* Move whole active bytes backwards. Equal-time admissions keep their
     * original order, including all bytes from one accepted request. */
    for (uint32_t i = u->count; i > insertion; i--) {
        uint32_t from = (u->head + i - 1) % LEMMA_UART_INGRESS_CAPACITY;
        uint32_t to = (u->head + i - 1 + amount) % LEMMA_UART_INGRESS_CAPACITY;
        u->bytes[to] = u->bytes[from];
        u->due[to] = u->due[from];
    }
    for (uint32_t i = 0; i < amount; i++) {
        uint32_t at = (u->head + insertion + i) % LEMMA_UART_INGRESS_CAPACITY;
        u->bytes[at] = (g_ascii_xdigit_value(words[1][2*i]) << 4) |
                       g_ascii_xdigit_value(words[1][2*i+1]);
        u->due[at] = when;
    }
    u->count += amount;
    u->accepted += amount;
    if (!insertion && !u->blocked) {
        timer_mod_ns(u->timer, MAX(when, u->earliest_ns));
    }
}

/* Additive external-stimulus admission. The historical equal-time packet and
 * actual16550/poll implementation above remain unchanged. Each byte below has
 * its own declared arrival time; no guest/device acknowledgement is implied. */
static char *lemma_uart_paced_version(Object *obj, Error **errp)
{
    return g_strdup(LEMMA_PAPER_PEN(obj)->fast_binding ?
                    "lemma-raw-uart-paced/1" : "disabled");
}

static void lemma_uart_inject_paced(Object *obj, const char *value, Error **errp)
{
    LemmaUARTIngress *u = &LEMMA_PAPER_PEN(obj)->uart_ingress;
    g_auto(GStrv) words = g_strsplit(value, " ", -1);
    GError *error = NULL;
    uint64_t when, interval;
    if (!u->enabled || runstate_is_running() || g_strv_length(words) != 3 ||
        !g_ascii_string_to_unsigned(words[0], 10, 0, INT64_MAX - 10, &when, &error)) {
        error_setg(errp, "paced UART requires an enabled paused port and when interval hex");
        g_clear_error(&error);
        return;
    }
    if (!g_ascii_string_to_unsigned(words[1], 10, 1, INT64_MAX - 10,
                                    &interval, &error)) {
        error_setg(errp, "paced UART interval must be positive bounded nanoseconds");
        g_clear_error(&error);
        return;
    }
    size_t hex = strlen(words[2]);
    uint64_t amount = hex / 2;
    if (!hex || hex % 2 || amount > LEMMA_UART_INGRESS_CAPACITY - u->count ||
        amount > UINT64_MAX - u->accepted ||
        when < (uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) ||
        amount - 1 > (INT64_MAX - 10 - when) / interval) {
        error_setg(errp, "paced UART capacity, timestamp or counter boundary exceeded");
        return;
    }
    for (size_t i = 0; i < hex; i++) {
        if (!g_ascii_isxdigit(words[2][i])) {
            error_setg(errp, "paced UART payload is not hexadecimal");
            return;
        }
    }
    /* Merge backwards in logical ring order. Each destination is at or after
     * its old source; the bounded active range never aliases unread bytes.
     * Existing equal-time bytes precede newly admitted equal-time bytes. All
     * validation precedes any mutation, including timer/counter updates. */
    uint32_t old = u->count, incoming = amount, output = old + incoming;
    while (incoming) {
        uint64_t due = when + (uint64_t)(incoming - 1) * interval;
        uint32_t at = (u->head + --output) % LEMMA_UART_INGRESS_CAPACITY;
        uint32_t last = (u->head + old - 1) % LEMMA_UART_INGRESS_CAPACITY;
        if (old && u->due[last] > due) {
            u->bytes[at] = u->bytes[last];
            u->due[at] = u->due[last];
            old--;
        } else {
            incoming--;
            u->bytes[at] = (g_ascii_xdigit_value(words[2][2 * incoming]) << 4) |
                           g_ascii_xdigit_value(words[2][2 * incoming + 1]);
            u->due[at] = due;
        }
    }
    u->count += amount;
    u->accepted += amount;
    if (!u->blocked) { timer_mod_ns(u->timer, MAX(u->due[u->head], u->earliest_ns)); }
}

static char *lemma_uart_state(Object *obj, Error **errp)
{
    LemmaUARTIngress *u = &LEMMA_PAPER_PEN(obj)->uart_ingress;
    Chardev *chr = qemu_chr_find("serial0");
    return g_strdup_printf("{\"enabled\":%s,\"flow\":%s,\"blocked\":%s,\"poll_calls\":%"PRIu64",\"wakeups\":%"PRIu64",\"pending\":%u,\"head\":%u,"
                           "\"reset_epoch\":%"PRIu64",\"accepted\":%"PRIu64","
                           "\"delivered\":%"PRIu64",\"canceled\":%"PRIu64","
                           "\"earliest_ns\":%"PRIu64",\"first_due_ns\":%"PRIu64","
                           "\"timer_pending\":%s,\"timer_expires_ns\":%"PRIu64","
                           "\"serial_can_receive\":%d}",
                           u->enabled ? "true" : "false", u->flow ? "true" : "false",
                           u->blocked ? "true" : "false", u->poll_calls, u->wakeups, u->count, u->head,
                           u->reset_epoch, u->accepted, u->delivered, u->canceled, u->earliest_ns,
                           u->count ? u->due[u->head] : 0,
                           timer_pending(u->timer) ? "true" : "false",
                           timer_pending(u->timer) ? timer_expire_time_ns(u->timer) : 0,
                           chr ? qemu_chr_be_can_write(chr) : -1);
}

static int lemma_uart_validate(void *opaque)
{
    LemmaUARTIngress *u = opaque;
    if (!u->enabled) {
        return (u->flow || u->blocked || u->reset_epoch || u->accepted || u->delivered || u->canceled || u->earliest_ns || u->head ||
                u->count || timer_pending(u->timer)) ? -EINVAL : 0;
    }
    if (!u->reset_epoch || u->head >= LEMMA_UART_INGRESS_CAPACITY ||
        u->count > LEMMA_UART_INGRESS_CAPACITY || u->earliest_ns > INT64_MAX ||
        u->delivered > u->accepted || u->canceled > u->accepted - u->delivered ||
        u->count != u->accepted - u->delivered - u->canceled) {
        return -EINVAL;
    }
    uint64_t previous = 0;
    for (uint32_t i = 0; i < u->count; i++) {
        uint32_t at = (u->head + i) % LEMMA_UART_INGRESS_CAPACITY;
        if (u->due[at] > INT64_MAX - 10 || (i && u->due[at] < previous)) {
            return -EINVAL;
        }
        previous = u->due[at];
    }
    if (u->blocked && (!u->flow || !u->count)) { return -EINVAL; }
    if (timer_pending(u->timer) != (u->count != 0 && !u->blocked)) {
        return -EINVAL;
    }
    if (u->count && !u->blocked) {
        uint64_t expires = timer_expire_time_ns(u->timer);
        if (expires > INT64_MAX || expires < MAX(u->earliest_ns, u->due[u->head])) {
            return -EINVAL;
        }
    }
    return 0;
}

static int lemma_uart_post_load(void *opaque, int version)
{
    return lemma_uart_validate(opaque);
}

static const VMStateDescription lemma_uart_state_vmstate = {
    .name = "lemma-raw-uart-state/2", .version_id = 2, .minimum_version_id = 2,
    .pre_save = lemma_uart_validate, .post_load = lemma_uart_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_BOOL(enabled, LemmaUARTIngress),
        VMSTATE_BOOL(flow, LemmaUARTIngress), VMSTATE_BOOL(blocked, LemmaUARTIngress),
        VMSTATE_UINT64(poll_calls, LemmaUARTIngress), VMSTATE_UINT64(wakeups, LemmaUARTIngress),
        VMSTATE_UINT32(head, LemmaUARTIngress), VMSTATE_UINT32(count, LemmaUARTIngress),
        VMSTATE_UINT64(reset_epoch, LemmaUARTIngress), VMSTATE_UINT64(accepted, LemmaUARTIngress),
        VMSTATE_UINT64(delivered, LemmaUARTIngress), VMSTATE_UINT64(canceled, LemmaUARTIngress),
        VMSTATE_UINT64(earliest_ns, LemmaUARTIngress),
        VMSTATE_UINT8_ARRAY(bytes, LemmaUARTIngress, LEMMA_UART_INGRESS_CAPACITY),
        VMSTATE_UINT64_ARRAY(due, LemmaUARTIngress, LEMMA_UART_INGRESS_CAPACITY),
        VMSTATE_TIMER_PTR(timer, LemmaUARTIngress), VMSTATE_END_OF_LIST()
    }
};

/* Pure observation: no controller sync, reads with side effects, timer change,
 * CPU wake, or HMP dispatch. Valid only at the ordinary paused boundary. */
static char *lemma_execution_state(Object *obj, Error **errp)
{
    LemmaDevices *s = LEMMA_PAPER_PEN(obj);
    CPUState *cpu = qemu_get_cpu(0);
    if (runstate_is_running()) { error_setg(errp, "execution-state requires pause"); return NULL; }
    GString *b = g_string_new(NULL);
    g_string_append_printf(b, "{\"schema\":\"lemma-execution-state/1\",\"cpu_halted\":%u,\"cpu_interrupt_request\":%u,\"virtual_ns\":%"PRIu64",\"pen_irq\":%s,\"pen_count\":%"PRIu64",\"mm_dma_active\":%"PRIu64",\"mm_dma_owner\":%"PRIu64",\"mm_dma_word\":%"PRIu64",\"mm_streams\":[", cpu ? cpu->halted : UINT32_MAX, cpu ? cpu->interrupt_request : UINT32_MAX, (uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL), lemma_pen_irq(&s->pen) ? "true" : "false", (uint64_t)s->pen.count, (uint64_t)s->multimodal.dma_active, s->multimodal.dma_stream, s->multimodal.dma_index);
    for (unsigned i = 0; i < 9; i++) {
        LemmaMMStream *t = &s->multimodal.stream[i];
        g_string_append_printf(b, "%s{\"id\":%u,\"state\":%"PRIu64",\"count\":%"PRIu64",\"converting\":%"PRIu64",\"next\":%"PRIu64",\"available\":%"PRIu64"}", i ? "," : "", i, t->state, t->count, t->converting, t->next, t->available);
    }
    g_string_append_printf(b, "],\"mm_timer_pending\":%s,\"mm_timer_expires_ns\":%"PRIu64"}", s->multimodal_timer && timer_pending(s->multimodal_timer) ? "true" : "false", s->multimodal_timer && timer_pending(s->multimodal_timer) ? (uint64_t)timer_expire_time_ns(s->multimodal_timer) : 0);
    return g_string_free(b, false);
}
