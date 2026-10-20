/* Synthetic digital PCM ring controller ABI2. SPDX-License-Identifier: Apache-2.0 */
#include "lemma_multimodal_v2.h"
#include <string.h>
#include <limits.h>
#define BASE UINT64_C(0x82000000)
#define BYTES UINT64_C(0x2000000)
enum { IDLE=2,CONFIGURED=3,ARMED=4,RUNNING=5,DRAINING=6,FAULT=7,DISCONNECTED=8 };
enum { BAD_FORMAT=2,BAD_RANGE=3,STALE=4,INVALID_STATE=5,BUSY=6,PERMISSION=7,OVERFLOW=9,UNDERRUN=10,LINK_LOSS=11,CALIBRATION=12,EXHAUSTED=14,INHIBITED=15 };
static bool lemma_mm2_legacy_valid(const LemmaMM*);
#define lemma_mm_checkpoint_valid lemma_mm2_legacy_valid
#include "lemma_multimodal_checkpoint_valid.inc.c"
#undef lemma_mm_checkpoint_valid
static bool permitted(const LemmaMM2*m,uint64_t now) {
 const LemmaMMStream*s=&m->legacy.stream[8];
 return m->legacy.link && !m->legacy.inhibit && s->calibration==1 && s->consent && s->lease>now &&
  s->epoch==m->owner_epoch && s->consent==m->owner_consent && s->config==m->owner_config &&
  (s->state==ARMED||s->state==RUNNING);
}
static void cancel(LemmaMM2*m,uint64_t status,uint64_t error) {
 LemmaMMStream*s=&m->legacy.stream[8];
 m->enabled=0;m->status=status;
 if(m->bus_kind==2)m->bus_cancel=1;
 s->state=error?FAULT:((s->state==IDLE||s->state==FAULT||s->state==DISCONNECTED)?s->state:CONFIGURED);s->count=0;s->head=0;s->lease=0;
 if(error)s->error=error;
 m->legacy.pending|=256;
}
static bool reject(LemmaMM2*m,uint64_t error) {
 m->legacy.stream[8].error=error;m->legacy.pending|=256;return false;
}
static void finish(LemmaMM2*m) {
 if(m->enabled&&m->eof&&m->fetch==m->end&&!m->legacy.stream[8].count&&m->bus_kind!=2)
  cancel(m,2,0);
}
static void prepare(LemmaMM2*m) {
 if(m->bus_kind)return;
 LemmaMMStream*s=&m->legacy.stream[8];uint64_t available=m->producer-m->fetch;
 bool read=m->enabled&&permitted(m,m->legacy.tick)&&s->count<=12&&available&&(available>=4||m->eof);
 if(read&&(!m->legacy.dma_active||m->turn==1)) {
  m->bus_kind=2;m->bus_addr=m->base+((m->fetch&(m->capacity-1))*2);
  m->bus_data=0;m->bus_samples=available<4?available:4;m->bus_cancel=0;
 } else if(m->legacy.dma_active) {
  m->bus_kind=1;lemma_mm_dma(&m->legacy,&m->bus_addr,&m->bus_data);m->bus_samples=0;m->bus_cancel=0;
 }
}
void lemma_mm2_init(LemmaMM2*m) { memset(m,0,sizeof(*m));lemma_mm_init(&m->legacy); }
uint64_t lemma_mm2_read(const LemmaMM2*m,uint32_t a) {
 switch(a) {
 case 8:return 2;
 case 0x68:return m->base;case 0x70:return m->capacity;
 case 0x78:return m->producer;case 0x80:return m->fetch;
 case 0x88:return 0;case 0x90:return m->status;
 case 0x98:return m->eof?m->end:UINT64_MAX;
 case 0xa0:return m->gaps;case 0xa8:return m->bus_kind|(m->bus_cancel<<8);
 default:return lemma_mm_read(&m->legacy,a);
 }
}
bool lemma_mm2_write(LemmaMM2*m,uint32_t a,uint64_t v) {
 if(a&7)return false;
 LemmaMMStream*s=&m->legacy.stream[8];
 if(a==0x68||a==0x70) {
  if(m->enabled||m->bus_kind==2||s->count||(s->state!=CONFIGURED&&s->state!=ARMED))return reject(m,6);
  if(a==0x68)m->base=v;else m->capacity=v;
  return true;
 }
 if(a==0x78) {
  if(!m->enabled||m->eof||!permitted(m,m->legacy.tick))return reject(m,7);
  if(v<m->producer)return reject(m,4);
  if(v-m->fetch>m->capacity)return reject(m,3);
  m->producer=v;prepare(m);return true;
 }
 if(a==0x88) {
  if(v==1) {
   if(m->enabled||m->bus_kind==2||s->state!=ARMED||s->count)return reject(m,6);
   if(m->capacity<16||m->capacity>2048||(m->capacity&(m->capacity-1))||m->base<BASE||(m->base&7)||m->base>BASE+BYTES-m->capacity*2)return reject(m,3);
   m->owner_epoch=s->epoch;m->owner_consent=s->consent;m->owner_config=s->config;
   if(!permitted(m,m->legacy.tick))return reject(m,7);
   m->producer=0;m->fetch=0;m->end=0;m->eof=0;m->enabled=1;m->status=1;
   m->submitted_base=s->submitted;m->consumed_base=s->consumed;m->gaps=0;return true;
  }
  if(v==2) {
   if(!m->enabled||!permitted(m,m->legacy.tick))return reject(m,7);
   if(!m->eof){m->eof=1;m->end=m->producer;}finish(m);prepare(m);return true;
  }
  if(v==3){cancel(m,3,0);return true;}
  return reject(m,2);
 }
 /* Ring data and direct FIFO pushes cannot be mixed in one ownership epoch. */
 if(a==0x900+112&&(m->enabled||m->bus_kind==2))return reject(m,6);
 bool ok=lemma_mm_write(&m->legacy,a,v);
 if(m->enabled&&!permitted(m,m->legacy.tick))cancel(m,3,0);
 prepare(m);return ok;
}
bool lemma_mm2_dma(const LemmaMM2*m,bool*write,uint64_t*a,uint64_t*v) {
 if(!m->bus_kind)return false;
 *write=m->bus_kind==1;*a=m->bus_addr;*v=m->bus_data;return true;
}
static void complete(LemmaMM2*m,uint64_t now,bool error,uint64_t data) {
 if(m->bus_kind==1) {
  lemma_mm_dma_complete(&m->legacy,error);m->bus_kind=0;m->turn=1;return;
 }
 if(m->bus_kind!=2)return;
 LemmaMMStream*s=&m->legacy.stream[8];
 if(m->bus_cancel||!m->enabled||!permitted(m,now)) {
  bool active=m->enabled!=0; m->bus_kind=0;m->bus_cancel=0; if(active)cancel(m,3,0);m->turn=0;return;
 }
 uint64_t n=m->bus_samples;
 if(error){m->bus_kind=0;cancel(m,4,3);return;}
 if(UINT64_MAX-s->submitted<n){m->bus_kind=0;cancel(m,4,14);return;}
 if(s->count+n>16){m->bus_kind=0;cancel(m,4,9);return;}
 for(uint64_t i=0;i<n;i++) {
  s->fifo[(s->head+s->count)%16]=(LemmaMMRecord){.data=(data>>(i*16))&65535,.epoch=m->owner_consent};s->count++;
 }
 s->submitted+=n;m->fetch+=n;m->legacy.pending|=256;m->bus_kind=0;m->turn=0;
}
static void edge_guard(LemmaMM2*m,uint64_t now) {
 LemmaMMStream*s=&m->legacy.stream[8];finish(m);
 if(m->enabled&&s->state==RUNNING&&s->next==now) {
  if(s->count&&s->consumed==UINT64_MAX){cancel(m,4,14);return;}
  if(!s->count&&!(m->eof&&m->fetch==m->end)) {
   if(m->gaps==UINT64_MAX)cancel(m,4,14);else m->gaps++;
  }
 }
}
static void before(LemmaMM2*m,uint64_t bound) {
 uint64_t at;
 while((at=lemma_mm_next(&m->legacy))<=bound) {
  edge_guard(m,at);lemma_mm_advance(&m->legacy,at);finish(m);
 }
 lemma_mm_advance(&m->legacy,bound);
}
void lemma_mm2_clock(LemmaMM2*m,uint64_t now,bool ready,bool error,uint64_t data) {
 if(now<m->legacy.tick)return;
 if(now>m->legacy.tick)before(m,now-1);
 if(ready)complete(m,now,error,data);
 edge_guard(m,now);lemma_mm_advance(&m->legacy,now);
 if(m->enabled&&!permitted(m,now))cancel(m,3,0);
 finish(m);prepare(m);
}
bool lemma_mm2_valid(const LemmaMM2*m) {
 if(!m||!lemma_mm2_legacy_valid(&m->legacy)||m->enabled>1||m->eof>1||m->status>4||m->bus_kind>2||m->bus_cancel>1||m->turn>1||m->fetch>m->producer)return false;
 if(m->enabled||m->bus_kind==2) {
  if(m->capacity<16||m->capacity>2048||(m->capacity&(m->capacity-1))||(m->base&7)||m->base<BASE||m->base>BASE+BYTES-m->capacity*2||m->producer-m->fetch>m->capacity)return false;
 }
 if(m->eof&&m->end!=m->producer)return false;
 if(m->enabled&&(m->status!=1||!permitted(m,m->legacy.tick)))return false;
 if(m->fetch%4&&(!m->eof||m->fetch!=m->end))return false;
 if(m->status==2&&(!m->eof||m->fetch!=m->end))return false;
 if(m->bus_kind==1) {
  uint64_t address,value;
  if(!lemma_mm_dma(&m->legacy,&address,&value)||m->bus_addr!=address||m->bus_data!=value)return false;
 }
 if(m->bus_kind==2&&(m->bus_samples>m->producer-m->fetch||(m->bus_samples<4&&!m->eof)))return false;
 if(m->bus_kind==2&&(m->bus_samples<1||m->bus_samples>4||m->bus_addr!=m->base+((m->fetch&(m->capacity-1))*2)))return false;
 if(m->bus_cancel&&m->bus_kind!=2)return false;
 return true;
}
