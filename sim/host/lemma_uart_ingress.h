/* Host-only raw UART ingress. SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef LEMMA_UART_INGRESS_H
#define LEMMA_UART_INGRESS_H

#define LEMMA_UART_INGRESS_CAPACITY 65536
typedef struct LemmaUARTIngress {
    bool enabled;
    uint32_t head, count;
    uint64_t reset_epoch, accepted, delivered, canceled, earliest_ns;
    uint8_t bytes[LEMMA_UART_INGRESS_CAPACITY];
    uint64_t due[LEMMA_UART_INGRESS_CAPACITY];
    QEMUTimer *timer;
} LemmaUARTIngress;

#endif
