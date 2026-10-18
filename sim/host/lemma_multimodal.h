/* Synthetic digital acquisition/playback circuitry only. SPDX-License-Identifier: Apache-2.0 */
#ifndef LEMMA_MULTIMODAL_H
#define LEMMA_MULTIMODAL_H
#include <stdint.h>
#include <stdbool.h>
#define LEMMA_MM_STREAMS 9
#define LEMMA_MM_FIFO 16
#define LEMMA_MM_ID UINT64_C(0x4c4d4d32)
/* Eight words are copied atomically from an immutable completion into owned DMA. */
typedef struct LemmaMMRecord { uint64_t data,capture,available,quality,sequence,epoch,config,selector; } LemmaMMRecord;
typedef struct LemmaMMStream {
 uint64_t state,error,epoch,sequence,gain,period,exposure,selector,consent,calibration,lease,quiet;
 uint64_t consent_floor,config,next,capture,available,latched_quality,latched_reference,dma_addr,dma_words,dma_status,consumed,submitted,start;
 int64_t input,reference,latched,history;
 LemmaMMRecord fifo[LEMMA_MM_FIFO];
 uint64_t head,count,converting,source_quality;
} LemmaMMStream;
typedef struct LemmaMM {
 uint64_t tick,mask,inhibit,link,pending,pcm_valid,pcm_data,pcm_position,pcm_tick;
 uint64_t dma_stream,dma_index,dma_active,dma_cancel;
 LemmaMMRecord dma_record;
 LemmaMMStream stream[LEMMA_MM_STREAMS];
} LemmaMM;
void lemma_mm_init(LemmaMM *);
void lemma_mm_advance(LemmaMM *,uint64_t);
uint64_t lemma_mm_next(const LemmaMM *);
uint64_t lemma_mm_read(const LemmaMM *,uint32_t);
bool lemma_mm_write(LemmaMM *,uint32_t,uint64_t);
bool lemma_mm_stimulus(LemmaMM *,unsigned,int32_t,int32_t,uint64_t);
bool lemma_mm_irq(const LemmaMM *);
bool lemma_mm_dma(const LemmaMM *,uint64_t *,uint64_t *);
void lemma_mm_dma_complete(LemmaMM *,bool);
#endif
