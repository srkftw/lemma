/* Raw synthetic optical-frame controller/1. SPDX-License-Identifier: Apache-2.0 */
#ifndef LEMMA_OPTICAL_H
#define LEMMA_OPTICAL_H
#include <stdbool.h>
#include <stdint.h>

#define LEMMA_OF_MAGIC UINT64_C(0x4c4d4f31)
#define LEMMA_OF_FRAME_MAGIC UINT64_C(0x31304652494e4d4c)
#define LEMMA_OF_MAX_ID UINT64_C(0x7ffffffffffffffe)
#define LEMMA_OF_MAX_TICK UINT64_C(0x0ccccccccccccccc)
#define LEMMA_OF_POOL UINT64_C(0x82000000)
#define LEMMA_OF_POOL_BYTES UINT64_C(0x2000000)

typedef struct LemmaOFSource {
 bool valid;
 uint64_t endpoint,kind,data,bytes,quality;
} LemmaOFSource;

typedef struct LemmaOFSlot {
 uint64_t pages[19],capacity,generation,state,header[32];
} LemmaOFSlot;

typedef struct LemmaOFEndpoint {
 uint64_t state,error,epoch,completed,source_sequence,config;
 uint64_t width,height,stride,format,gain,exposure,row_ticks,period,calibration;
 uint64_t consent,consent_floor,expiry,dropped,accepted,last_sof;
 uint64_t received,written,packing,packing_hi,packing_bytes,pixel_low,header_index;
 int active_slot;
 bool have_sof,eof,discard;
} LemmaOFEndpoint;

typedef struct LemmaOptical {
 uint64_t tick,epoch,pending,mask,inhibit,link,error,last_reset_epoch;
 uint64_t table_base,table_status,table_index,table_candidate[192];
 bool table_valid,reset_pending,reset_asserted,reset_fenced,exhausted;
 LemmaOFSlot slots[6];
 LemmaOFEndpoint endpoint[3];
 /* A presented beat is immutable until acknowledgement, including cancellation. */
 uint64_t held_kind,held_address,held_data,held_endpoint,held_slot,held_offset;
 bool held_cancel;
 uint64_t completed_dma_bytes,turn;
 uint64_t lease_endpoint_stage,lease_sequence_stage;
 uint64_t lease_status,lease_endpoint,lease_sequence,lease_slot,lease_generation,lease_consent;
} LemmaOptical;

void lemma_of_init(LemmaOptical *);
/* One ordinary/domain reset assertion, distinct from equipment init/POR.
 * Cancels authority and advances epochs while retaining monotonic floors. An
 * existing held beat and revoked delivery pin must retire before reuse. The
 * caller keeps the memory path clocked and invokes this once per assertion. */
void lemma_of_reset(LemmaOptical *);
uint64_t lemma_of_read(const LemmaOptical *,uint32_t);
/* Actual bus admission uses byte width, independently of semantic command
 * acceptance. Unsupported offsets/directions/width/alignment never mutate. */
bool lemma_of_access(uint32_t,bool,unsigned);
bool lemma_of_write(LemmaOptical *,uint32_t,uint64_t);
bool lemma_of_source_ready(const LemmaOptical *,uint64_t,const LemmaOFSource *);
/* Ready is advertised from pre-edge state. Completion, permission fences, raw
 * source, then the caller's MMIO operation. A retiring beat may expose ready on
 * the following edge; it cannot accept a source beat advertised as held.
 * Returns actual ready/valid acceptance; it does not invent source pixels. */
bool lemma_of_clock(LemmaOptical *,uint64_t,bool,bool,uint64_t,const LemmaOFSource *);
/* Port-level ordinary reset: completion precedes one authority reset at the
 * assertion edge; later asserted edges only advance/retire held memory. */
bool lemma_of_clock_reset(LemmaOptical *,uint64_t,bool,bool,uint64_t,const LemmaOFSource *,bool);
bool lemma_of_dma(const LemmaOptical *,bool *,uint64_t *,uint64_t *);
bool lemma_of_irq(const LemmaOptical *);
#endif
