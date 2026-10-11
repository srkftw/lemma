/* Host hardware only. SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef LEMMA_MODEL_H
#define LEMMA_MODEL_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "lemma_device_abi.h"
#define LEMMA_PEN_FIFO 256
#define LEMMA_PAPER_BUSY 1u
#define LEMMA_PAPER_DONE 2u
#define LEMMA_PAPER_ERROR_BIT 4u
#define LEMMA_PAPER_INTERRUPTED 8u
#define LEMMA_PEN_DATA 1u
#define LEMMA_PEN_LOSS_BIT 2u
#define LEMMA_PEN_RESYNC 4u
#define LEMMA_PEN_CONTACT 1u
#define LEMMA_PEN_PROXIMITY 2u
#define LEMMA_PEN_SYNTHETIC 4u
#define LEMMA_PEN_DISCONNECTED 8u
typedef struct LemmaSample {
    uint64_t sequence,time,x,y,pressure,flags,tool,buttons,epoch;
} LemmaSample;
typedef struct LemmaPen {
    LemmaSample fifo[LEMMA_PEN_FIFO];
    uint32_t head,count;
    uint64_t epoch,next_sequence,lost,error,max_x,max_y,pressure_max,caps;
    bool loss,resync,release_seen;
    uint64_t last_time,contact_deadline;
} LemmaPen;
typedef struct LemmaPaper {
    uint32_t width,height,stride;
    uint8_t *target,*visible,*latched;
    uint8_t aperture[512];
    uint64_t status,error,tile_x,tile_y,tile_w,tile_h,tile_len;
    uint64_t sequence,rect_x,rect_y,rect_w,rect_h,mode;
    uint64_t completed,last_sequence,deadline_ns,fast_ns,quality_ns;
    uint64_t latched_x,latched_y,latched_w,latched_h,latched_mode;
    uint64_t descriptor[32];
} LemmaPaper;
void lemma_pen_init(LemmaPen *,uint64_t,uint64_t,uint64_t);
bool lemma_pen_push(LemmaPen *,const LemmaSample *);
uint64_t lemma_pen_read(const LemmaPen *,uint32_t);
void lemma_pen_write(LemmaPen *,uint32_t,uint64_t);
bool lemma_pen_irq(const LemmaPen *);
void lemma_pen_advance(LemmaPen *,uint64_t);
bool lemma_paper_init(LemmaPaper *,uint32_t,uint32_t);
void lemma_paper_destroy(LemmaPaper *);
uint64_t lemma_paper_read(const LemmaPaper *,uint32_t,unsigned);
void lemma_paper_write(LemmaPaper *,uint32_t,uint64_t,unsigned,uint64_t);
void lemma_paper_advance(LemmaPaper *,uint64_t);
void lemma_paper_reset(LemmaPaper *);
bool lemma_paper_irq(const LemmaPaper *);
#endif
