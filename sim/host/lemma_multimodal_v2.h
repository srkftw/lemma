/* Synthetic digital PCM ring controller ABI2. SPDX-License-Identifier: Apache-2.0 */
#ifndef LEMMA_MULTIMODAL_V2_H
#define LEMMA_MULTIMODAL_V2_H
#include "lemma_multimodal.h"
typedef struct LemmaMM2 {
 LemmaMM legacy;
 uint64_t base,capacity,producer,fetch,end,eof,enabled,status;
 uint64_t owner_epoch,owner_consent,owner_config,submitted_base,consumed_base,gaps;
 uint64_t bus_kind,bus_addr,bus_data,bus_samples,bus_cancel,turn;
} LemmaMM2;
void lemma_mm2_init(LemmaMM2*);
uint64_t lemma_mm2_read(const LemmaMM2*,uint32_t);
bool lemma_mm2_write(LemmaMM2*,uint32_t,uint64_t);
/* At a declared controller edge, a held memory beat completes before the
 * playback/converter edge and MMIO. The caller supplies actual read data. */
void lemma_mm2_clock(LemmaMM2*,uint64_t,bool,bool,uint64_t);
bool lemma_mm2_dma(const LemmaMM2*,bool*,uint64_t*,uint64_t*);
bool lemma_mm2_valid(const LemmaMM2*);
#endif
