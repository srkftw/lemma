/* Digital Power-v2 reference model. Host only; no guest policy. */
#pragma once
#include "lemma_model.h"
typedef struct LemmaPowerSafety {
    LemmaPower legacy;
    uint64_t timeout,remaining,reset_remaining,reset_epoch;
    bool armed,power_good,brownout,last_safe,power_loss;
} LemmaPowerSafety;
void lemma_power_safety_reset(LemmaPowerSafety *,uint64_t,uint64_t);
bool lemma_power_safety_domain_reset(const LemmaPowerSafety *);
bool lemma_power_safety_access(uint32_t,unsigned,bool,uint64_t);
uint64_t lemma_power_safety_read(const LemmaPowerSafety *,uint32_t);
void lemma_power_safety_tick(LemmaPowerSafety *,bool,bool,uint64_t,bool,bool,uint32_t,unsigned,uint64_t,bool);
