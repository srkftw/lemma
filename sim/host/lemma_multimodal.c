/* Host hardware model: no notebook, permissions policy, inference or derived physiological authority.
 * Synthetic-aperture/1 has a 100MHz clock, one converter per raw stream, fixed16-record FIFOs,
 * sample aperture followed by configured availability delay, explicit source-off windows and
 * signed24-bit EEG/microphones, unsigned24-bit optical integration, raw16-bin ToF and DCS event codes.
 * This bounded model does NOT claim a camera frame readout, qualified DCS/fNIRS physiology or physical DAC.
 * SPDX-License-Identifier: Apache-2.0 */
#include "lemma_multimodal.h"
#include <string.h>
#include <limits.h>
enum { IDLE=2,CONFIGURED=3,ARMED=4,RUNNING=5,DRAINING=6,FAULT=7,DISCONNECTED=8 };
enum { BAD_FORMAT=2, BAD_RANGE=3, STALE=4, INVALID_STATE=5, BUSY=6, PERMISSION=7, OVERFLOW=9, UNDERRUN=10, LINK_LOSS=11, CALIBRATION=12, EXHAUSTED=14, INHIBITED=15 };
static void fail(LemmaMM *m,unsigned i,uint64_t e){m->stream[i].error=e;m->pending|=UINT64_C(1)<<i;}
static bool optical(unsigned i){return i>=1&&i<=5;}
static bool output(unsigned i){return optical(i)||i==8;}
static bool enabled(const LemmaMM *m,unsigned i){const LemmaMMStream*s=&m->stream[i];return m->link&&s->consent&&s->lease>m->tick&&(!output(i)||(!m->inhibit&&s->calibration==1&&s->lease>m->tick));}
static bool emitter(const LemmaMM *m,unsigned i){const LemmaMMStream*s=&m->stream[i];return optical(i)&&enabled(m,i)&&s->state==RUNNING&&m->tick>=s->quiet&&!(s->selector&256);}
static void stop(LemmaMM*m,unsigned i,uint64_t state){LemmaMMStream*s=&m->stream[i];s->state=state;s->converting=0;s->count=0;s->head=0;s->lease=0;if(m->dma_active&&m->dma_stream==i){m->dma_cancel=1;}m->pending|=UINT64_C(1)<<i;}
void lemma_mm_init(LemmaMM*m){memset(m,0,sizeof(*m));m->inhibit=1;m->link=1;for(unsigned i=0;i<9;i++){m->stream[i].state=IDLE;m->stream[i].epoch=1;m->stream[i].gain=1;m->stream[i].period=100000;m->stream[i].exposure=8;}}
bool lemma_mm_stimulus(LemmaMM*m,unsigned i,int32_t v,int32_t r,uint64_t q){if(i>=8||q>65535)return false;m->stream[i].input=v;m->stream[i].reference=r;m->stream[i].source_quality=q;return true;}
static uint64_t convert(LemmaMMStream*s,unsigned i,uint64_t*q){
 int64_t v=(s->input-s->reference)*(int64_t)s->gain;
 if(optical(i)){if(s->selector&256)v=s->reference*(int64_t)s->gain;else v*=s->exposure;
  if(i==3)v+=(int64_t)(s->selector&255)*s->exposure*s->gain;
  /* ToF raw binding: bin index in bits31:24, unsigned24-bit event count below. */
  if(i==4){v=s->input>0?s->input*s->exposure:0;v&=0xffffff;return ((s->selector&15)<<24)|(uint64_t)v;}
  /* Flow raw binding: event count and timestamp-resolution/deadtime schedule identity.
   * This converter block emits windowed event counts; correlation/fitting is unsupported. */
  if(i==5)v=s->input>0?(s->input*s->exposure+3)/4:0;
  if(v<0){v=0;*q|=1;}if(v>0xffffff){v=0xffffff;*q|=1;}
 }else{if(i==0&&(s->selector&1)){v=(s->history+v)/2;s->history=v;}if(v<-8388608){v=-8388608;*q|=1;}if(v>8388607){v=8388607;*q|=1;}}
 return (uint64_t)v;
}
static void append(LemmaMM*m,unsigned i,LemmaMMRecord r){LemmaMMStream*s=&m->stream[i];if(s->count==16){fail(m,i,OVERFLOW);return;}if(s->sequence==UINT64_MAX){fail(m,i,EXHAUSTED);s->state=FAULT;return;}r.sequence=++s->sequence;s->fifo[(s->head+s->count)%16]=r;s->count++;m->pending|=UINT64_C(1)<<i;}
uint64_t lemma_mm_next(const LemmaMM*m){uint64_t n=UINT64_MAX;for(unsigned i=0;i<9;i++){const LemmaMMStream*s=&m->stream[i];if(s->converting&&s->available<n)n=s->available;if(s->state==RUNNING&&s->next<n)n=s->next;if((s->state==RUNNING||s->state==DRAINING)&&s->lease&&s->lease<n)n=s->lease;}return n;}
void lemma_mm_advance(LemmaMM*m,uint64_t end){if(end<m->tick)return;m->pcm_valid=0;uint64_t n;unsigned budget=0;while((n=lemma_mm_next(m))<=end){if(++budget>1000000){for(unsigned i=0;i<9;i++)if(m->stream[i].state==RUNNING){fail(m,i,OVERFLOW);stop(m,i,FAULT);}break;}m->tick=n;
 for(unsigned i=0;i<9;i++){LemmaMMStream*s=&m->stream[i];if(s->state!=RUNNING&&s->state!=DRAINING)continue;
  if(!enabled(m,i)){fail(m,i,s->consent?INHIBITED:PERMISSION);stop(m,i,CONFIGURED);continue;}
  if(s->converting&&s->available==n){append(m,i,(LemmaMMRecord){(uint64_t)s->latched,s->capture,n,s->latched_quality,0,s->epoch,s->config,s->selector});s->converting=0;if(s->state==DRAINING)s->state=CONFIGURED;}
  if(s->state!=RUNNING||s->next!=n)continue;
  if(s->period>UINT64_MAX-n){fail(m,i,EXHAUSTED);stop(m,i,FAULT);continue;}s->next=n+s->period;
  if(i==8){if(n<s->start)continue;if(!s->count){fail(m,i,UNDERRUN);m->pcm_data=0;m->pcm_tick=n;continue;}int64_t sample=(int16_t)(s->fifo[s->head].data&65535)*(int64_t)s->gain;if(sample< -32768)sample= -32768;if(sample>32767)sample=32767;m->pcm_data=(uint64_t)sample;m->pcm_tick=n;m->pcm_position=++s->consumed;m->pcm_valid=1;s->head=(s->head+1)%16;s->count--;m->pending|=256;continue;}
  if(n<s->quiet){fail(m,i,INHIBITED);continue;}
  if(s->converting){fail(m,i,BUSY);continue;}if(s->exposure>UINT64_MAX-n){fail(m,i,EXHAUSTED);stop(m,i,FAULT);continue;}
  s->capture=n;s->available=n+s->exposure;s->latched_quality=s->source_quality;s->latched_reference=s->reference;
  /* Simultaneous optical acquisition deliberately marks interference; no dropped promised raw mode. */
  if(optical(i))for(unsigned j=1;j<=5;j++)if(j!=i&&emitter(m,j)){s->latched_quality|=32;break;}
  if(i==0&&m->stream[8].state==RUNNING)s->latched_quality|=64;
  s->latched=(int64_t)convert(s,i,&s->latched_quality);s->converting=1;
 }}m->tick=end;}
bool lemma_mm_irq(const LemmaMM*m){uint64_t p=m->pending;for(unsigned i=0;i<9;i++)if(m->stream[i].count)p|=UINT64_C(1)<<i;return (p&m->mask)!=0;}
uint64_t lemma_mm_read(const LemmaMM*m,uint32_t a){if(a&7)return 0;if(a<256){switch(a){case 0:return LEMMA_MM_ID;case 8:return 1;case 16:return 0x1ff;case 24:return m->tick;case 32:{uint64_t p=m->pending;for(unsigned i=0;i<9;i++)if(m->stream[i].count)p|=UINT64_C(1)<<i;return p;}case 40:return m->mask;case 56:return m->inhibit;case 64:return m->link;case 72:return 100000000;case 80:return 16;case 88:return 64;case 96:return 0;default:return 0;}}
 unsigned i=a/256-1;if(i>=9)return 0;const LemmaMMStream*s=&m->stream[i];const LemmaMMRecord*r=&s->fifo[s->head];switch(a&255){case 0:return 0x4d4d0000+i;case 8:return s->state;case 16:return s->error;case 32:return s->epoch;case 40:return s->sequence;case 48:return s->gain;case 56:return s->period;case 64:return s->exposure;case 72:return s->selector;case 80:return s->consent;case 88:return s->reference;case 96:return s->calibration;case 104:return s->lease;case 112:return s->count?r->data:0;case 120:return s->count?r->capture:0;case 128:return s->count?r->available:0;case 136:return s->count?r->quality:0;case 144:return s->count;case 160:return s->dma_addr;case 168:return s->dma_words;case 184:return s->dma_status;case 192:return s->count?r->config:s->config;case 200:return emitter(m,i);case 208:return s->quiet;case 216:return s->latched_reference;case 224:return s->count?r->sequence:0;case 232:return s->consumed;case 240:return s->submitted;case 248:return s->start;default:return 0;}}
bool lemma_mm_write(LemmaMM*m,uint32_t a,uint64_t v){if(a&7)return false;if(a<256){switch(a){case 40:if(v>511)return false;m->mask=v;return true;case 48:if(v>511)return false;m->pending&=~v;return true;case 56:if(v>1)return false;m->inhibit=v;if(v)for(unsigned i=0;i<9;i++)if(output(i))stop(m,i,CONFIGURED);return true;case 64:if(v>1)return false;m->link=v;if(!v)for(unsigned i=0;i<9;i++){fail(m,i,LINK_LOSS);stop(m,i,DISCONNECTED);m->stream[i].consent=0;}return true;default:return false;}}
 unsigned i=a/256-1;if(i>=9)return false;LemmaMMStream*s=&m->stream[i];unsigned o=a&255;
 if(o==24){s->error=0;switch(v){case 1:if(s->epoch==UINT64_MAX){fail(m,i,EXHAUSTED);s->state=FAULT;return false;}stop(m,i,IDLE);s->epoch++;s->sequence=0;s->error=0;s->consent=0;s->calibration=0;s->history=0;return true;case 2:if(s->count){fail(m,i,BUSY);return false;}if(s->state!=IDLE&&s->state!=CONFIGURED){fail(m,i,INVALID_STATE);return false;}if(!s->gain||s->gain>64||s->period<8||s->period>UINT32_MAX||!s->exposure||s->exposure>65535||s->exposure>s->period){fail(m,i,BAD_RANGE);return false;}if(s->config==UINT64_MAX){fail(m,i,EXHAUSTED);return false;}s->config++;s->state=CONFIGURED;s->error=0;return true;case 3:if(s->state!=CONFIGURED){fail(m,i,INVALID_STATE);return false;}if(!enabled(m,i)){fail(m,i,PERMISSION);return false;}s->state=ARMED;return true;case 4:if(s->state!=ARMED){fail(m,i,INVALID_STATE);return false;}if(!enabled(m,i)){fail(m,i,PERMISSION);return false;}s->state=RUNNING;s->next=m->tick+1;return true;case 5:if(s->state!=RUNNING){fail(m,i,INVALID_STATE);return false;}s->state=s->converting?DRAINING:CONFIGURED;return true;case 6:stop(m,i,CONFIGURED);return true;case 7:stop(m,i,DISCONNECTED);s->consent=0;return true;case 8:if(s->state!=DISCONNECTED||!m->link){fail(m,i,INVALID_STATE);return false;}s->state=IDLE;return true;default:fail(m,i,BAD_FORMAT);return false;}}
 if(o==80){if(v&&v<=s->consent_floor){fail(m,i,STALE);return false;}s->consent=v;if(v)s->consent_floor=v;if(!v)stop(m,i,CONFIGURED);return true;}
 if(o==152){if(v!=1||!s->count||s->dma_status==1){fail(m,i,s->dma_status==1?BUSY:INVALID_STATE);return false;}s->head=(s->head+1)%16;s->count--;return true;}
 if(o==112&&i==8){if(!enabled(m,i)||(s->state!=ARMED&&s->state!=RUNNING)){fail(m,i,PERMISSION);return false;}if(s->submitted==UINT64_MAX){fail(m,i,EXHAUSTED);return false;}if(s->count==16){fail(m,i,OVERFLOW);return false;}s->fifo[(s->head+s->count)%16]=(LemmaMMRecord){.data=v,.epoch=s->consent};s->count++;s->submitted++;return true;}
 if(o==160||o==168){if(s->dma_status==1){fail(m,i,BUSY);return false;}if(o==160)s->dma_addr=v;else s->dma_words=v;return true;}
 if(o==176){if(v!=1||i==8||!s->count||m->dma_active||s->dma_words!=8||s->dma_addr<0x82000000||s->dma_addr>0x83ffffc0||(s->dma_addr&63)){fail(m,i,BAD_RANGE);return false;}m->dma_stream=i;m->dma_index=0;m->dma_active=1;m->dma_cancel=0;m->dma_record=s->fifo[s->head];s->dma_status=1;return true;}
 if(o==104){if(v<=m->tick||(output(i)&&(s->calibration!=1||m->inhibit))){fail(m,i,INHIBITED);return false;}s->lease=v;return true;}
 if(o==208){s->quiet=v;return true;}
 if(s->count||(s->state!=IDLE&&s->state!=CONFIGURED)){fail(m,i,BUSY);return false;}
 switch(o){case 48:s->gain=v;break;case 56:s->period=v;break;case 64:s->exposure=v;break;case 72:s->selector=v;break;case 88:fail(m,i,BAD_FORMAT);return false;case 96:if(v>1){fail(m,i,CALIBRATION);return false;}s->calibration=v;break;case 248:s->start=v;break;default:fail(m,i,BAD_FORMAT);return false;}return true;}
bool lemma_mm_dma(const LemmaMM*m,uint64_t*a,uint64_t*v){if(!m->dma_active)return false;*a=m->stream[m->dma_stream].dma_addr+m->dma_index*8;const uint64_t*words=(const uint64_t*)&m->dma_record;*v=words[m->dma_index];return true;}
void lemma_mm_dma_complete(LemmaMM*m,bool error){if(!m->dma_active)return;LemmaMMStream*s=&m->stream[m->dma_stream];if(m->dma_cancel){s->dma_status=3;m->dma_active=0;m->dma_cancel=0;}else if(error){s->dma_status=3;fail(m,m->dma_stream,BAD_RANGE);m->dma_active=0;}else if(++m->dma_index==8){s->dma_status=2;s->head=(s->head+1)%16;s->count--;m->pending|=UINT64_C(1)<<m->dma_stream;m->dma_active=0;}}
