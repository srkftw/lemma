/* Host hardware only; no notebook, brush, document or journal algorithms.
 * SPDX-License-Identifier: GPL-2.0-or-later */
#include "lemma_model.h"
#include <stdlib.h>
#include <string.h>
#include <limits.h>
static void pen_loss(LemmaPen *p)
{
    /* Preserve the immutable old head across loss; discard its followers. */
    p->count=p->count?1:0; p->contact_deadline=0; p->loss=true; p->resync=true; p->release_seen=false;
    if (p->epoch != UINT64_MAX) p->epoch++; else p->error=5;
    if (p->lost != UINT64_MAX) p->lost++;
}
void lemma_pen_init(LemmaPen *p,uint64_t x,uint64_t y,uint64_t pressure)
{
    memset(p,0,sizeof(*p)); p->epoch=1; p->next_sequence=1;
    p->max_x=x; p->max_y=y; p->pressure_max=pressure; p->caps=pressure?1:0;
}
bool lemma_pen_push(LemmaPen *p,const LemmaSample *s)
{
    LemmaSample v=*s;
    if ((v.flags & LEMMA_PEN_DISCONNECTED) || p->next_sequence==UINT64_MAX) {
        pen_loss(p); return false;
    }
    if (v.time<p->last_time || v.time>UINT64_MAX-10000000 || v.x>p->max_x || v.y>p->max_y || v.pressure>p->pressure_max ||
        (v.flags & ~UINT64_C(15)) || v.tool>2 || (v.buttons & ~UINT64_C(7))) {
        p->error=1; pen_loss(p); return false;
    }
    if (p->loss) return false;
    if (p->resync) {
        if (!(v.flags & LEMMA_PEN_CONTACT)) p->release_seen=true;
        if (!p->release_seen || !(v.flags & LEMMA_PEN_CONTACT)) return false;
        p->resync=false;
    }
    if (p->count==LEMMA_PEN_FIFO) { pen_loss(p); return false; }
    v.sequence=p->next_sequence++; v.epoch=p->epoch;
    p->last_time=v.time;p->contact_deadline=(v.flags&1)?v.time+10000000:0;
    p->fifo[(p->head+p->count)%LEMMA_PEN_FIFO]=v; p->count++;
    return true;
}
void lemma_pen_advance(LemmaPen *p,uint64_t now)
{ if(p->contact_deadline && now>=p->contact_deadline)pen_loss(p); }
bool lemma_pen_irq(const LemmaPen *p) { return p->count || p->loss || p->error; }
uint64_t lemma_pen_read(const LemmaPen *p,uint32_t a)
{
    const LemmaSample *s=p->count ? &p->fifo[p->head] : NULL;
    switch(a) {
    case LEMMA_PEN_MAGIC:return LEMMA_PEN_IDENTITY;
    case LEMMA_PEN_VERSION:return 1;
    case LEMMA_PEN_STATUS:return (p->count?1:0)|(p->loss?2:0)|(p->resync?4:0)|(p->error?8:0);
    case LEMMA_PEN_ERROR:return p->error;
    case LEMMA_PEN_COUNT:return p->count;
    case LEMMA_PEN_EPOCH:return p->epoch;
    case LEMMA_PEN_LOSS:return p->lost;
    case LEMMA_PEN_MAX_X:return p->max_x;
    case LEMMA_PEN_MAX_Y:return p->max_y;
    case LEMMA_PEN_PRESSURE_MAX:return p->pressure_max;
    case LEMMA_PEN_CAPS:return p->caps;
    default:
        if (a>=LEMMA_PEN_HEAD_SEQ && a<=LEMMA_PEN_HEAD_EPOCH && !(a&7)) {
            if (!s) return 0;
            switch ((a-LEMMA_PEN_HEAD_SEQ)/8) {
            case 0:return s->sequence; case 1:return s->time; case 2:return s->x;
            case 3:return s->y;case 4:return s->pressure;case 5:return s->flags;
            case 6:return s->tool;case 7:return s->buttons;case 8:return s->epoch;
            }
        }
        return 0;
    }
}
void lemma_pen_write(LemmaPen *p,uint32_t a,uint64_t v)
{
    if(a==LEMMA_PEN_ACK) {
        if(p->count && p->fifo[p->head].sequence==v) {
            p->head=(p->head+1)%LEMMA_PEN_FIFO; p->count--;
        } else p->error=2;
    } else if(a==LEMMA_PEN_LOSS_ACK) {
        if(p->loss && v==p->epoch) { p->head=p->count=0; p->loss=false; p->error=0; }
        else p->error=2;
    } else if(a==LEMMA_PEN_RESET && v==1) {
        pen_loss(p);
    } else p->error=3;
}
static uint8_t pixel(const uint8_t *b,uint32_t stride,uint64_t x,uint64_t y)
{ uint8_t v=b[y*stride+x/2]; return (x&1)?v&15:v>>4; }
static void put_pixel(uint8_t *b,uint32_t stride,uint64_t x,uint64_t y,uint8_t v)
{ uint8_t *d=&b[y*stride+x/2]; *d=(x&1)?((*d&240)|v):((*d&15)|(v<<4)); }
bool lemma_paper_init(LemmaPaper *p,uint32_t w,uint32_t h)
{
    size_t n;
    memset(p,0,sizeof(*p));
    if(w<32 || h<32 || w>4096 || h>4096) return false;
    p->width=w; p->height=h;p->stride=(w+1)/2;n=(size_t)p->stride*h;
    p->target=malloc(n);p->visible=malloc(n);p->latched=malloc(n);
    if(!p->target || !p->visible || !p->latched) { lemma_paper_destroy(p);return false; }
    memset(p->target,255,n);memset(p->visible,255,n);memset(p->latched,255,n);
    p->fast_ns=2000000;p->quality_ns=25000000;
    return true;
}
void lemma_paper_destroy(LemmaPaper *p)
{ free(p->target);free(p->visible);free(p->latched);p->target=p->visible=p->latched=NULL; }
static void paper_error(LemmaPaper *p,uint64_t e) { p->error=e;p->status|=4; }
bool lemma_paper_irq(const LemmaPaper *p) { return (p->status & (2|4|8))!=0; }
void lemma_paper_reset(LemmaPaper *p)
{
    bool interrupted=(p->status&(1|8))!=0;
    memset(p->target,255,(size_t)p->stride*p->height);memset(p->aperture,255,512);
    p->status=interrupted?8:0;p->error=interrupted?6:0;p->deadline_ns=0;
    p->tile_x=p->tile_y=p->tile_w=p->tile_h=p->tile_len=0;
    p->rect_x=p->rect_y=p->rect_w=p->rect_h=p->sequence=p->mode=0;
    /* completed visible pixels and monotonic sequence lifetime are retained. */
}
uint64_t lemma_paper_read(const LemmaPaper *p,uint32_t a,unsigned size)
{
    uint64_t v=0;unsigned i;
    if(a>=LEMMA_PAPER_APERTURE && a+size<=LEMMA_PAPER_APERTURE+512) {
        for(i=0;i<size;i++) v|=(uint64_t)p->aperture[a-LEMMA_PAPER_APERTURE+i]<<(8*i);
        return v;
    }
    if(size!=8 || (a&7)) return 0;
    if(a>=LEMMA_PAPER_DESCRIPTOR && a<LEMMA_PAPER_DESCRIPTOR+256) return p->descriptor[(a-LEMMA_PAPER_DESCRIPTOR)/8];
    switch(a) {
    case LEMMA_PAPER_MAGIC:return LEMMA_PAPER_IDENTITY;
    case LEMMA_PAPER_VERSION:return 1;case LEMMA_PAPER_STATUS:return p->status;
    case LEMMA_PAPER_ERROR:return p->error;case LEMMA_PAPER_WIDTH:return p->width;
    case LEMMA_PAPER_HEIGHT:return p->height;case LEMMA_PAPER_STRIDE:return p->stride;
    case LEMMA_PAPER_CAPS:return 3;case LEMMA_PAPER_COMPLETED:return p->completed;
    case LEMMA_PAPER_SEQUENCE:return p->last_sequence;
    default:return 0;
    }
}
void lemma_paper_write(LemmaPaper *p,uint32_t a,uint64_t v,unsigned size,uint64_t now)
{
    uint64_t x,y,w,h,len;unsigned i;
    if(a>=LEMMA_PAPER_APERTURE && size<=8 && a+size<=LEMMA_PAPER_APERTURE+512) {
        for(i=0;i<size;i++) p->aperture[a-LEMMA_PAPER_APERTURE+i]=(uint8_t)(v>>(8*i));
        return;
    }
    if(size!=8 || (a&7)) {paper_error(p,1);return;}
    switch(a) {
    case LEMMA_PAPER_TILE_X:p->tile_x=v;return;case LEMMA_PAPER_TILE_Y:p->tile_y=v;return;
    case LEMMA_PAPER_TILE_W:p->tile_w=v;return;case LEMMA_PAPER_TILE_H:p->tile_h=v;return;
    case LEMMA_PAPER_TILE_LEN:p->tile_len=v;return;case LEMMA_PAPER_SEQUENCE:p->sequence=v;return;
    case LEMMA_PAPER_RECT_X:p->rect_x=v;return;case LEMMA_PAPER_RECT_Y:p->rect_y=v;return;
    case LEMMA_PAPER_RECT_W:p->rect_w=v;return;case LEMMA_PAPER_RECT_H:p->rect_h=v;return;
    case LEMMA_PAPER_MODE:p->mode=v;return;
    case LEMMA_PAPER_ACK:
        if (v==p->completed) {p->status&=~(2u|4u);p->error=0;} else paper_error(p,2);return;
    case LEMMA_PAPER_RESET:if(v==1)lemma_paper_reset(p);else paper_error(p,1);return;
    case LEMMA_PAPER_COMMAND:break;
    default:paper_error(p,1);return;
    }
    if(v==1) {
        x=p->tile_x;y=p->tile_y;w=p->tile_w;h=p->tile_h;len=p->tile_len;
        if(!w||!h||w>32||h>32||x>p->width||y>p->height||w>p->width-x||h>p->height-y||len!=((w+1)/2)*h||len>512) {paper_error(p,3);return;}
        for(uint64_t yy=0;yy<h;yy++)for(uint64_t xx=0;xx<w;xx++)put_pixel(p->target,p->stride,x+xx,y+yy,pixel(p->aperture,(w+1)/2,xx,yy));
        return;
    }
    if(v!=2) {paper_error(p,1);return;}
    if(p->status&1) {paper_error(p,4);return;}
    x=p->rect_x;y=p->rect_y;w=p->rect_w;h=p->rect_h;
    if(!w||!h||x>p->width||y>p->height||w>p->width-x||h>p->height-y||p->mode<1||p->mode>2) {paper_error(p,3);return;}
    if(!p->sequence || p->sequence<=p->last_sequence || p->last_sequence==UINT64_MAX) {paper_error(p,5);return;}
    p->latched_x=x;p->latched_y=y;p->latched_w=w;p->latched_h=h;p->latched_mode=p->mode;
    for(uint64_t yy=y;yy<y+h;yy++)for(uint64_t xx=x;xx<x+w;xx++) {
        uint8_t q=pixel(p->target,p->stride,xx,yy);
        /* Fast is deterministic threshold conversion, not a physical waveform. */
        put_pixel(p->latched,p->stride,xx,yy,p->mode==1?(q<8?0:15):q);
    }
    p->last_sequence=p->sequence;p->status|=1;
    uint64_t duration=p->mode==1?p->fast_ns:p->quality_ns;
    if(now>UINT64_MAX-duration) {p->status&=~1u;paper_error(p,5);return;}
    p->deadline_ns=now+duration;
}
void lemma_paper_advance(LemmaPaper *p,uint64_t now)
{
    if(!(p->status&1) || now<p->deadline_ns)return;
    for(uint64_t y=p->latched_y;y<p->latched_y+p->latched_h;y++)for(uint64_t x=p->latched_x;x<p->latched_x+p->latched_w;x++)put_pixel(p->visible,p->stride,x,y,pixel(p->latched,p->stride,x,y));
    p->completed=p->last_sequence;p->status=(p->status&~1u)|2;
    if(p->latched_mode==2 && p->latched_x==0 && p->latched_y==0 && p->latched_w==p->width && p->latched_h==p->height)p->status&=~8u;
}
