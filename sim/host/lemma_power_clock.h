/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Host-only periodic digital clock adapter for the Power-v2 circuit model.
 * No guest policy. Every effect belongs to an explicit rising-edge identity. */
#pragma once
#include "lemma_power_safety.h"
typedef struct LemmaPowerClock {
    LemmaPowerSafety circuit;
    uint64_t edge,write_edge,write_value;
    uint32_t write_addr,write_size;
    bool write_pending,raw_good,raw_brownout;
    uint64_t raw_button;
} LemmaPowerClock;
void lemma_power_clock_reset(LemmaPowerClock *,uint64_t,uint64_t,uint64_t);
bool lemma_power_clock_enqueue(LemmaPowerClock *,uint64_t,uint32_t,unsigned,uint64_t);
/* Advances to at most the next effect boundary. The caller admits a reset
 * event before advancing farther. Events are 1 watchdog,2 loss,4 release. */
unsigned lemma_power_clock_advance(LemmaPowerClock *,uint64_t,bool);
uint64_t lemma_power_clock_next(const LemmaPowerClock *);
bool lemma_power_clock_validate(const LemmaPowerClock *,uint64_t);
