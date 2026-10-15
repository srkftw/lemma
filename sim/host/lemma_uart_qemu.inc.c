/* Raw external bytes only. Serial registers, FIFO, IRQs and guest parsing are
 * the existing QEMU16550 and maintained Lean software. No packet interpretation.
 * Included only by the explicit raw-UART backend derivation.
 * SPDX-License-Identifier: GPL-2.0-or-later */
#include "chardev/char.h"

static void lemma_uart_poll(void *opaque)
{
    LemmaDevices *s = opaque;
    LemmaUARTIngress *u = &s->uart_ingress;
    uint64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    Chardev *chr = qemu_chr_find("serial0");
    if (!u->enabled || !u->count) {
        return;
    }
    if (!chr) {
        error_report("Lemma raw UART lost its declared serial0 frontend");
        exit(1);
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
    if (!insertion) {
        timer_mod_ns(u->timer, MAX(when, u->earliest_ns));
    }
}

static char *lemma_uart_state(Object *obj, Error **errp)
{
    LemmaUARTIngress *u = &LEMMA_PAPER_PEN(obj)->uart_ingress;
    Chardev *chr = qemu_chr_find("serial0");
    return g_strdup_printf("{\"enabled\":%s,\"pending\":%u,\"head\":%u,"
                           "\"reset_epoch\":%"PRIu64",\"accepted\":%"PRIu64","
                           "\"delivered\":%"PRIu64",\"canceled\":%"PRIu64","
                           "\"earliest_ns\":%"PRIu64",\"first_due_ns\":%"PRIu64","
                           "\"timer_pending\":%s,\"timer_expires_ns\":%"PRIu64","
                           "\"serial_can_receive\":%d}",
                           u->enabled ? "true" : "false", u->count, u->head,
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
        return (u->reset_epoch || u->accepted || u->delivered || u->canceled || u->earliest_ns || u->head ||
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
    if (timer_pending(u->timer) != (u->count != 0)) {
        return -EINVAL;
    }
    if (u->count) {
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
    .name = "lemma-raw-uart-state/1", .version_id = 1, .minimum_version_id = 1,
    .pre_save = lemma_uart_validate, .post_load = lemma_uart_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_BOOL(enabled, LemmaUARTIngress),
        VMSTATE_UINT32(head, LemmaUARTIngress), VMSTATE_UINT32(count, LemmaUARTIngress),
        VMSTATE_UINT64(reset_epoch, LemmaUARTIngress), VMSTATE_UINT64(accepted, LemmaUARTIngress),
        VMSTATE_UINT64(delivered, LemmaUARTIngress), VMSTATE_UINT64(canceled, LemmaUARTIngress),
        VMSTATE_UINT64(earliest_ns, LemmaUARTIngress),
        VMSTATE_UINT8_ARRAY(bytes, LemmaUARTIngress, LEMMA_UART_INGRESS_CAPACITY),
        VMSTATE_UINT64_ARRAY(due, LemmaUARTIngress, LEMMA_UART_INGRESS_CAPACITY),
        VMSTATE_TIMER_PTR(timer, LemmaUARTIngress), VMSTATE_END_OF_LIST()
    }
};
