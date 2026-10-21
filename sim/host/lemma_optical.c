/* Raw optical digital front end and scatter/gather controller, ABI1.
 * This is synthetic hardware, not analog integration or guest interpretation.
 * SPDX-License-Identifier: Apache-2.0 */
#include "lemma_optical.h"
#include <string.h>

enum { IDLE=2,CONFIGURED=3,ARMED=4,RUNNING=5,DRAINING=6,FAULT=7,DISCONNECTED=8 };
enum { FREE=0,FILLING=1,READY=2,CANCELLED=3 };
enum { FORMAT=2,RANGE=3,STALE=4,STATE=5,BUSY=6,PERMISSION=7,EXPIRED=8,
 OVERFLOW=9,GAP=10,LINK=11,CALIBRATION=12,EXHAUSTED=14,INHIBITED=15 };

static unsigned pages_for(unsigned e) { return e<2?5:19; }
static bool id(uint64_t n) { return n && n<=LEMMA_OF_MAX_ID; }
static bool page(uint64_t p) {
 return !(p&4095) && p>=LEMMA_OF_POOL && p<=LEMMA_OF_POOL+LEMMA_OF_POOL_BYTES-4096;
}
static bool permission(const LemmaOptical*m,unsigned e,uint64_t now) {
 const LemmaOFEndpoint*p=&m->endpoint[e];
 return !m->exhausted && m->table_valid && m->table_status==2 && m->link && !m->inhibit &&
  p->consent && p->expiry>now && now<=LEMMA_OF_MAX_TICK;
}
static bool owner_held(const LemmaOptical*m,unsigned slot) {
 return m->held_kind>=2 && m->held_slot==slot;
}
static bool pinned(const LemmaOptical*m,unsigned slot) {
 return m->lease_status && m->lease_slot==slot;
}
static void quarantine(LemmaOptical*m) {
 /* Exhausted identities cannot become fresh acquisition authority. A pending
  * physical beat and orphan copy pin still need their real retirement. */
 m->exhausted=true;m->error=EXHAUSTED;m->pending|=8;m->inhibit=1;
 m->table_valid=false;m->table_status=0;
 if(m->held_kind)m->held_cancel=true;
 if(m->lease_status)m->lease_status=2;
 for(unsigned e=0;e<3;e++) {
  LemmaOFEndpoint*p=&m->endpoint[e];p->consent=0;p->expiry=0;p->state=FAULT;p->error=EXHAUSTED;
  p->active_slot=-1;p->packing=0;p->packing_hi=0;p->packing_bytes=0;p->pixel_low=0;p->eof=false;
 }
 for(unsigned i=0;i<6;i++)if(m->slots[i].state!=FREE)m->slots[i].state=CANCELLED;
}
static void global_error(LemmaOptical*m,uint64_t code) {
 if(code==EXHAUSTED)quarantine(m);
 m->error=m->exhausted?EXHAUSTED:code;m->pending|=8;
}
static bool reject(LemmaOptical*m,unsigned e,uint64_t code) {
 if(code==EXHAUSTED)quarantine(m);
 m->endpoint[e].error=m->exhausted?EXHAUSTED:code;m->pending|=UINT64_C(1)<<e;return false;
}
static int head(const LemmaOptical*m,unsigned e) {
 int result=-1;
 for(unsigned i=e*2;i<e*2+2;i++)if(m->slots[i].state==READY &&
   (result<0 || m->slots[i].header[3]<m->slots[result].header[3]))result=(int)i;
 return result;
}
static unsigned ready_count(const LemmaOptical*m,unsigned e) {
 return (m->slots[e*2].state==READY)+(m->slots[e*2+1].state==READY);
}
bool lemma_of_access(uint32_t a,bool write,unsigned bytes) {
 if(bytes!=8||(a&7)||a>=1024)return false;
 if(a<256) {
  if(write)switch(a) {
   case 40:case 48:case 56:case 64:case 96:case 104:case 112:case 184:case 192:case 200:return true;
   default:return false;
  }
  switch(a) {
   case 0:case 8:case 16:case 24:case 32:case 40:case 56:case 64:case 72:case 80:case 88:
   case 96:case 104:case 120:case 128:case 136:case 144:case 152:case 160:case 168:case 176:
   case 184:case 192:case 208:case 216:case 224:case 232:case 240:case 248:return true;
   default:return false;
  }
 }
 unsigned offset=a&255;
 if(write)switch(offset) {
  case 24:case 48:case 56:case 64:case 72:case 80:case 88:case 96:case 104:case 112:case 120:case 128:case 184:return true;
  default:return false;
 }
 return offset!=184;
}
static uint64_t pending(const LemmaOptical*m) {
 uint64_t n=m->pending|(m->error?8:0);
 for(unsigned e=0;e<3;e++)if(m->endpoint[e].error||ready_count(m,e))n|=UINT64_C(1)<<e;
 return n;
}
bool lemma_of_irq(const LemmaOptical*m) { return (pending(m)&m->mask)!=0; }
static void retire_slot(LemmaOptical*m,unsigned i) {
 LemmaOFSlot*s=&m->slots[i];
 if(owner_held(m,i)||pinned(m,i)){s->state=CANCELLED;return;}
 if(s->state==FREE)return;
 if(s->generation==LEMMA_OF_MAX_ID) {
  s->state=CANCELLED;m->endpoint[i/2].state=FAULT;m->endpoint[i/2].consent=0;
  m->endpoint[i/2].expiry=0;reject(m,i/2,EXHAUSTED);return;
 }
 s->generation++;s->state=FREE;
}
static void fence(LemmaOptical*m,unsigned e,uint64_t code,uint64_t state) {
 LemmaOFEndpoint*p=&m->endpoint[e];
 p->consent=0;p->expiry=0;p->state=state;p->discard=false;
 if(m->held_kind>=2 && m->held_endpoint==e)m->held_cancel=true;
 if(m->lease_status && m->lease_endpoint==e)m->lease_status=2;
 for(unsigned i=e*2;i<e*2+2;i++)if(m->slots[i].state!=FREE)retire_slot(m,i);
 p->active_slot=-1;p->packing=0;p->packing_hi=0;p->packing_bytes=0;p->pixel_low=0;p->eof=false;
 if(code)reject(m,e,code);
}
static bool endpoint_empty(const LemmaOptical*m,unsigned e) {
 return m->endpoint[e].active_slot<0 && m->slots[e*2].state==FREE &&
  m->slots[e*2+1].state==FREE && !(m->held_kind>=2&&m->held_endpoint==e) &&
  !(m->lease_status&&m->lease_endpoint==e);
}
static bool table_idle(const LemmaOptical*m) {
 if(m->exhausted || m->held_kind || m->lease_status || m->reset_pending)return false;
 for(unsigned e=0;e<3;e++)if((m->endpoint[e].state!=IDLE &&
   m->endpoint[e].state!=CONFIGURED)||!endpoint_empty(m,e))return false;
 return true;
}
static void default_config(LemmaOFEndpoint*p,unsigned e) {
 p->width=e==2?320:e==0?16:160;p->height=e==2?240:e==0?16:120;
 p->stride=e==2?320:e==0?32:160;p->format=e==0?1:2;
 p->gain=1;p->exposure=8;p->row_ticks=1;p->period=e==2?6666667:e==0?1000000:1666667;
 p->calibration=0;
}
void lemma_of_init(LemmaOptical*m) {
 memset(m,0,sizeof(*m));m->epoch=1;m->inhibit=1;m->link=1;
 for(unsigned e=0;e<3;e++) {
  m->endpoint[e].state=IDLE;m->endpoint[e].epoch=1;
  m->endpoint[e].active_slot=-1;default_config(&m->endpoint[e],e);
 }
}
void lemma_of_reset(LemmaOptical*m) {
 /* Clock, identities and floors survive ordinary reset. Only equipment POR
  * seeds them. A live kernel copy becomes a revoked, unreusable orphan pin;
  * the new kernel needs the hardware reset witness before releasing it. */
 m->pending=0;m->mask=0;m->inhibit=1;m->error=0;m->last_reset_epoch=0;m->reset_fenced=true;
 m->table_valid=false;m->table_status=0;m->table_index=0;
 bool exhausted=m->epoch==LEMMA_OF_MAX_ID;
 if(!exhausted){m->epoch++;m->last_reset_epoch=m->epoch;}
 for(unsigned e=0;e<3;e++) {
  LemmaOFEndpoint*p=&m->endpoint[e];bool maximum=p->epoch==LEMMA_OF_MAX_ID;
  fence(m,e,0,IDLE);
  if(!maximum)p->epoch++;
  p->have_sof=false;default_config(p,e);
  if(maximum||exhausted||p->error==EXHAUSTED){p->state=FAULT;reject(m,e,EXHAUSTED);}
  else p->error=0;
 }
 if(exhausted||m->exhausted)global_error(m,EXHAUSTED);
 if(m->held_kind){m->held_cancel=true;m->reset_pending=true;}
}
static bool configuration(const LemmaOFEndpoint*p,unsigned e) {
 bool geometry=(e==0&&p->format==1&&p->width==16&&p->height==16&&p->stride==32)||
  (e<2&&p->format==2&&p->width==160&&p->height==120&&p->stride==160)||
  (e==2&&p->format==2&&p->width==320&&p->height==240&&p->stride==320);
 uint64_t minimum=e==2?6666667:(e==0&&p->format==1)?1000000:1666667;
 return geometry && p->gain>=1&&p->gain<=64&&p->exposure>=1&&p->exposure<=65535&&
  p->row_ticks>=1&&p->row_ticks<=65535&&p->period>=minimum&&p->period<=UINT32_MAX&&
  p->period>=p->exposure+p->height*p->row_ticks&&p->calibration<=1;
}
static bool table_candidate(LemmaOptical*m) {
 uint64_t seen[58];unsigned used=0;
 for(unsigned i=0;i<6;i++) {
  uint64_t*v=&m->table_candidate[i*32];unsigned n=pages_for(i/2);
  if(v[0]!=n||v[1]!=(uint64_t)n*4096||!id(v[2])||v[2]<=m->slots[i].generation||v[3])return false;
  for(unsigned k=0;k<19;k++) {
   uint64_t address=v[4+k];
   if(k>=n){if(address)return false;continue;}
   if(!page(address)||address==m->table_base)return false;
   for(unsigned j=0;j<used;j++)if(address==seen[j])return false;
   seen[used++]=address;
  }
  for(unsigned k=23;k<32;k++)if(v[k])return false;
 }
 if(used!=58 || m->epoch==LEMMA_OF_MAX_ID)return false;
 for(unsigned i=0;i<6;i++) {
  uint64_t*v=&m->table_candidate[i*32];LemmaOFSlot*s=&m->slots[i];
  memcpy(s->pages,v+4,sizeof(s->pages));s->capacity=v[1];s->generation=v[2];s->state=FREE;
 }
 m->epoch++;m->table_valid=true;m->table_status=2;return true;
}
static uint64_t slot_address(const LemmaOptical*m,unsigned i,uint64_t offset) {
 return m->slots[i].pages[offset/4096]+offset%4096;
}
static void prepare(LemmaOptical*m) {
 if(m->exhausted||m->held_kind||m->reset_pending)return;
 if(m->table_status==1) {
  m->held_kind=1;m->held_address=m->table_base+m->table_index*8;
  m->held_data=0;m->held_offset=m->table_index;return;
 }
 for(unsigned j=0;j<3;j++) {
  unsigned e=(unsigned)((m->turn+j)%3);LemmaOFEndpoint*p=&m->endpoint[e];
  if(p->active_slot<0)continue;
  unsigned i=(unsigned)p->active_slot;
  if(m->slots[i].state!=FILLING)continue;
  if(p->packing_bytes>=8) {
   m->held_kind=2;m->held_offset=256+p->written;m->held_data=p->packing;
  } else if(p->eof&&p->written==p->received&&p->packing_bytes==0&&p->header_index<32) {
   m->held_kind=3;m->held_offset=p->header_index*8;
   m->held_data=m->slots[i].header[p->header_index];
  } else continue;
  m->held_endpoint=e;m->held_slot=i;m->held_cancel=false;
  m->held_address=slot_address(m,i,m->held_offset);return;
 }
}
bool lemma_of_dma(const LemmaOptical*m,bool*write,uint64_t*address,uint64_t*data) {
 if(!m->held_kind)return false;
 *write=m->held_kind!=1;*address=m->held_address;*data=m->held_data;return true;
}
uint64_t lemma_of_read(const LemmaOptical*m,uint32_t a) {
 if((a&7)||a>=1024)return 0;
 if(a<256)switch(a) {
  case 0:return LEMMA_OF_MAGIC;case 8:return 1;case 16:return 15;case 24:return m->tick;
  case 32:return pending(m);case 40:return m->mask;case 56:return m->inhibit;case 64:return m->link;
  case 72:return 100000000;case 80:return m->epoch;case 88:return 256;
  case 96:return m->table_base;case 104:return 1536;case 120:return m->table_status;
  case 128:return m->error;case 136:return m->held_kind|((uint64_t)m->held_cancel<<8);
  case 144:return m->held_address;case 152:return m->completed_dma_bytes;case 160:return 3;
  case 168:return 1;case 176:return 76800;case 184:return m->lease_endpoint_stage;
  case 192:return m->lease_sequence_stage;case 208:return m->lease_status;
  case 216:return m->lease_status?m->lease_slot%2:0;case 224:return m->lease_status?m->lease_generation:0;
  case 232:return m->lease_status?m->lease_consent:0;case 240:return m->last_reset_epoch;
  case 248:return m->reset_fenced;default:return 0;
 }
 unsigned e=a/256-1;const LemmaOFEndpoint*p=&m->endpoint[e];int i=head(m,e);
 const LemmaOFSlot*s=i<0?NULL:&m->slots[i];
 switch(a&255) {
  case 0:return UINT64_C(0x4f460000)+e+1;case 8:return p->state;case 16:return p->error;case 24:return p->consent_floor;
  case 32:return p->epoch;case 40:return p->completed;case 48:return p->width;case 56:return p->height;
  case 64:return p->stride;case 72:return p->format;case 80:return p->gain;case 88:return p->exposure;
  case 96:return p->row_ticks;case 104:return p->period;case 112:return p->consent;case 120:return p->expiry;
  case 128:return p->calibration;case 136:return s?s->header[18]:0;case 144:return ready_count(m,e);
  case 152:return s?(unsigned)i%2:0;case 160:return s?s->header[3]:0;
  case 168:return s?256+s->header[19]:0;case 176:return s?s->header[8]:0;
  case 192:return p->dropped;case 200:return s?s->header[5]:0;case 208:return p->config;
  case 216:return p->accepted;case 224:return m->slots[e*2].state;case 232:return m->slots[e*2+1].state;
  case 240:return m->slots[e*2].generation;case 248:return m->slots[e*2+1].generation;default:return 0;
 }
}

static void complete(LemmaOptical*m,bool error,uint64_t data) {
 uint64_t kind=m->held_kind;unsigned e=(unsigned)m->held_endpoint,i=(unsigned)m->held_slot;
 bool cancelled=m->held_cancel;
 m->held_kind=0;m->held_cancel=false;
 if(m->reset_pending){m->reset_pending=false;if(kind>=2)retire_slot(m,i);return;}
 if(m->exhausted){if(kind>=2)retire_slot(m,i);return;}
 if(m->completed_dma_bytes>UINT64_MAX-8) {
  global_error(m,EXHAUSTED);
  for(unsigned n=0;n<3;n++)fence(m,n,EXHAUSTED,FAULT);
  return;
 }
 if(kind==1) {
  if(error){m->table_status=3;m->table_valid=false;global_error(m,RANGE);return;}
  m->table_candidate[m->table_index++]=data;
  if(m->table_index==192 && !table_candidate(m)) {
   m->table_status=3;m->table_valid=false;global_error(m,RANGE);
   for(unsigned n=0;n<3;n++)fence(m,n,PERMISSION,CONFIGURED);
  }
 } else if(kind>=2) {
  m->turn=(e+1)%3;
  if(cancelled || !permission(m,e,m->tick)) {
   retire_slot(m,i);
   if(m->endpoint[e].active_slot==(int)i)fence(m,e,EXPIRED,CONFIGURED);
   return;
  }
  if(error){fence(m,e,RANGE,FAULT);return;}
  LemmaOFEndpoint*p=&m->endpoint[e];
  if(kind==2){p->written+=8;p->packing=p->packing_hi;p->packing_hi=0;p->packing_bytes-=8;}
  else if(++p->header_index==32) {
   m->slots[i].state=READY;p->completed=m->slots[i].header[3];
   p->active_slot=-1;p->eof=false;m->pending|=UINT64_C(1)<<e;
   if(p->state==DRAINING)p->state=CONFIGURED;
  }
 }
 m->completed_dma_bytes+=8;
}
static bool bad_source(const LemmaOFSource*s) {
 if(s->quality>65535||s->kind>3)return true;
 if(s->kind==1) {
  if(s->bytes<1||s->bytes>8)return true;
  return s->bytes<8 && (s->data>>(s->bytes*8))!=0;
 }
 if(s->bytes)return true;
 return s->kind==3?!s->data:s->data!=0;
}
bool lemma_of_source_ready(const LemmaOptical*m,uint64_t now,const LemmaOFSource*s) {
 if(!s||!s->valid||m->reset_pending)return false;
 if(s->endpoint<1||s->endpoint>3)return true;
 unsigned e=(unsigned)s->endpoint-1;const LemmaOFEndpoint*p=&m->endpoint[e];
 if(bad_source(s)||!permission(m,e,now)||(p->state!=RUNNING&&p->state!=DRAINING))return true;
 if(s->kind==0||s->kind==3||p->discard)return true;
 if(p->active_slot<0||p->eof)return true;
 uint64_t expected=p->stride*p->height;
 if(s->kind==1) {
  if(p->received>expected || s->bytes>expected-p->received)return true;
  uint64_t last_row=(p->received+s->bytes-1)/p->stride;
  uint64_t deadline=m->slots[p->active_slot].header[7]+last_row*p->row_ticks;
  uint64_t produced=p->format==1?2*(((p->received&1)+s->bytes)/2):s->bytes;
  return now>=deadline && p->packing_bytes+produced<=16;
 }
 if(p->received!=expected)return true;
 uint64_t deadline=m->slots[p->active_slot].header[7]+p->height*p->row_ticks;
 return now>=deadline && p->packing_bytes==0 && p->written==p->received &&
  !(m->held_kind>=2&&m->held_endpoint==e);
}
static void dropped(LemmaOptical*m,unsigned e,uint64_t amount,uint64_t code) {
 LemmaOFEndpoint*p=&m->endpoint[e];
 if(amount>LEMMA_OF_MAX_ID-p->dropped){fence(m,e,EXHAUSTED,FAULT);return;}
 p->dropped+=amount;reject(m,e,code);
}
static void source_accept(LemmaOptical*m,const LemmaOFSource*s) {
 if(s->endpoint<1||s->endpoint>3){global_error(m,FORMAT);return;}
 unsigned e=(unsigned)s->endpoint-1;LemmaOFEndpoint*p=&m->endpoint[e];
 if(bad_source(s)){fence(m,e,FORMAT,FAULT);return;}
 if(!permission(m,e,m->tick)){fence(m,e,PERMISSION,FAULT);return;}
 if(p->state!=RUNNING&&p->state!=DRAINING){fence(m,e,STATE,FAULT);return;}
 if(s->kind==3) {
  dropped(m,e,s->data,GAP);
  if(p->active_slot>=0&&!p->eof)m->slots[p->active_slot].header[18]|=8|s->quality;
  return;
 }
 if(s->kind==0) {
  if(p->state!=RUNNING){reject(m,e,STATE);return;}
  if(p->source_sequence==LEMMA_OF_MAX_ID){fence(m,e,EXHAUSTED,FAULT);return;}
  p->source_sequence++;
  bool early=p->have_sof && (m->tick<p->last_sof||m->tick-p->last_sof<p->period);
  p->last_sof=m->tick;p->have_sof=true;p->discard=false;
  if(p->active_slot>=0) {
   if(!p->eof) {
    unsigned old=(unsigned)p->active_slot;
    if(owner_held(m,old))m->held_cancel=true;
    retire_slot(m,old);p->active_slot=-1;p->packing=0;p->packing_hi=0;p->packing_bytes=0;p->pixel_low=0;
   }
   p->discard=true;dropped(m,e,1,OVERFLOW);return;
  }
  if(early){p->discard=true;dropped(m,e,1,RANGE);return;}
  int chosen=-1;
  for(unsigned i=e*2;i<e*2+2;i++)if(m->slots[i].state==FREE){chosen=(int)i;break;}
  if(chosen<0){p->discard=true;dropped(m,e,1,OVERFLOW);return;}
  if(m->tick>LEMMA_OF_MAX_TICK-p->exposure-p->height*p->row_ticks) {
   fence(m,e,EXHAUSTED,FAULT);return;
  }
  LemmaOFSlot*slot=&m->slots[chosen];slot->state=FILLING;memset(slot->header,0,sizeof(slot->header));
  uint64_t*h=slot->header;
  h[0]=LEMMA_OF_FRAME_MAGIC;h[1]=1;h[2]=e+1;h[3]=p->source_sequence;
  h[4]=p->epoch;h[5]=p->config;h[6]=m->tick;h[7]=m->tick+p->exposure;
  h[9]=p->period;h[12]=p->width;h[13]=p->height;h[14]=p->gain;
  h[15]=p->exposure;h[16]=p->row_ticks;h[17]=p->consent;
  h[18]=s->quality|(p->calibration?0:16);h[19]=p->stride*p->height;
  h[20]=32;h[21]=100000000;h[22]=850;h[24]=1;h[25]=p->calibration;
  h[26]=1;h[27]=p->format;h[28]=e==0?(p->format==1?1:2):e+2;h[29]=1;
  p->active_slot=chosen;p->received=p->written=p->packing=p->packing_hi=p->packing_bytes=p->pixel_low=p->header_index=0;p->eof=false;
  return;
 }
 if(p->discard){if(s->kind==2)p->discard=false;return;}
 if(p->active_slot<0||p->eof){fence(m,e,STATE,FAULT);return;}
 LemmaOFSlot*slot=&m->slots[p->active_slot];uint64_t*h=slot->header;
 h[18]|=s->quality;
 if(s->kind==2) {
  if(p->received!=h[19]){fence(m,e,RANGE,FAULT);return;}
  h[8]=m->tick;h[23]=p->dropped;p->eof=true;return;
 }
 if(s->bytes>h[19]-p->received){fence(m,e,RANGE,FAULT);return;}
 if(p->accepted>UINT64_MAX-s->bytes){fence(m,e,EXHAUSTED,FAULT);return;}
 /* A source beat may cross a DMA word, a row, or an LE16 pixel. Keep
  * at most two complete output words plus the raw low byte of one pixel.
  * Gain is applied exactly once, only after that pixel's high byte arrives. */
 unsigned unit=p->format==1?2:1;uint64_t maximum=p->format==1?65535:255;
 for(unsigned k=0;k<s->bytes;k++) {
  uint64_t value=(s->data>>(8*k))&255;
  if(unit==2) {
   if(((p->received+k)&1)==0){p->pixel_low=value;continue;}
   value=p->pixel_low|(value<<8);p->pixel_low=0;
  }
  value*=p->gain;
  if(value>maximum){value=maximum;h[18]|=1;}
  for(unsigned b=0;b<unit;b++) {
   uint64_t byte=(value>>(8*b))&255;
   if(p->packing_bytes<8)p->packing|=byte<<(p->packing_bytes*8);
   else p->packing_hi|=byte<<((p->packing_bytes-8)*8);
   p->packing_bytes++;
  }
 }
 p->received+=s->bytes;p->accepted+=s->bytes;
}
bool lemma_of_clock_reset(LemmaOptical*m,uint64_t now,bool ready,bool error,uint64_t data,const LemmaOFSource*s,bool reset) {
 if(now<m->tick)return false;
 if(reset) {
  m->tick=now;
  if(ready&&m->held_kind)complete(m,error,data);
  if(!m->reset_asserted)lemma_of_reset(m);
  m->reset_asserted=true;return false;
 }
 m->reset_asserted=false;
 bool advertised=lemma_of_source_ready(m,now,s);
 m->tick=now;
 if(ready&&m->held_kind)complete(m,error,data);
 if(now>LEMMA_OF_MAX_TICK) {
  global_error(m,EXHAUSTED);
  for(unsigned e=0;e<3;e++)fence(m,e,EXHAUSTED,FAULT);
 }
 for(unsigned e=0;e<3;e++)if(m->endpoint[e].consent&&!permission(m,e,now))
  fence(m,e,m->link?(m->inhibit?INHIBITED:EXPIRED):LINK,m->link?CONFIGURED:DISCONNECTED);
 bool accept=advertised&&lemma_of_source_ready(m,now,s);
 if(accept)source_accept(m,s);
 prepare(m);return accept;
}
bool lemma_of_clock(LemmaOptical*m,uint64_t now,bool ready,bool error,uint64_t data,const LemmaOFSource*s) {
 return lemma_of_clock_reset(m,now,ready,error,data,s,false);
}
static bool consume(LemmaOptical*m,unsigned e,uint64_t sequence,bool lease) {
 int i=head(m,e);
 if(i<0||m->slots[i].header[3]!=sequence)return reject(m,e,STALE);
 if(!permission(m,e,m->tick)||m->slots[i].header[17]!=m->endpoint[e].consent)return reject(m,e,PERMISSION);
 if(owner_held(m,(unsigned)i)||(!lease&&pinned(m,(unsigned)i)))return reject(m,e,BUSY);
 if(lease)m->lease_status=0;
 retire_slot(m,(unsigned)i);return m->slots[i].state==FREE;
}
bool lemma_of_write(LemmaOptical*m,uint32_t a,uint64_t v) {
 if(!lemma_of_access(a,true,8))return false;
 if(m->reset_pending){global_error(m,BUSY);return false;}
 if(m->exhausted && !((a==200&&v==3)||(a==56&&v==1)||a==48)) {
  global_error(m,EXHAUSTED);return false;
 }
 if(a<256) {
  switch(a) {
   case 40:if(v&~UINT64_C(15)){global_error(m,FORMAT);return false;}m->mask=v;return true;
   case 48:if(v&~UINT64_C(15)){global_error(m,FORMAT);return false;}m->pending&=~v;return true;
   case 56:case 64:
    if(v>1){global_error(m,FORMAT);return false;}
    if(a==56)m->inhibit=v;else m->link=v;
    if((a==56&&v)||(a==64&&!v))for(unsigned e=0;e<3;e++)fence(m,e,a==56?INHIBITED:LINK,a==56?CONFIGURED:DISCONNECTED);
    else if(a==64&&v)for(unsigned e=0;e<3;e++)if(m->endpoint[e].state==DISCONNECTED)m->endpoint[e].state=IDLE;
    return true;
   case 96:
    if(!table_idle(m)){global_error(m,BUSY);return false;}
    if(!page(v)){global_error(m,RANGE);return false;}m->table_base=v;return true;
   case 104:
    if(!table_idle(m)){global_error(m,BUSY);return false;}
    if(v!=1536){global_error(m,RANGE);return false;}return true;
   case 112:
    if(!table_idle(m)){global_error(m,BUSY);return false;}
   if(v==1) {
     if(!page(m->table_base)){global_error(m,RANGE);return false;}
     if(m->epoch==LEMMA_OF_MAX_ID){global_error(m,EXHAUSTED);return false;}
     m->reset_fenced=false;m->table_status=1;m->table_index=0;m->table_valid=false;m->error=0;prepare(m);return true;
    }
    if(v==2) {
     if(m->epoch==LEMMA_OF_MAX_ID){global_error(m,EXHAUSTED);return false;}
     m->reset_fenced=false;m->epoch++;m->table_status=0;m->table_valid=false;m->error=0;
     for(unsigned n=0;n<3;n++)fence(m,n,0,m->endpoint[n].state);
     return true;
    }
    global_error(m,FORMAT);return false;
   case 184:case 192:
    if(m->lease_status){global_error(m,BUSY);return false;}
    if(a==184)m->lease_endpoint_stage=v;else m->lease_sequence_stage=v;return true;
   case 200:
    if(v==1) {
     if(m->lease_status){global_error(m,BUSY);return false;}
     if(m->lease_endpoint_stage<1||m->lease_endpoint_stage>3){global_error(m,RANGE);return false;}
     unsigned e=(unsigned)m->lease_endpoint_stage-1;int i=head(m,e);
     if(i<0||m->slots[i].header[3]!=m->lease_sequence_stage)return reject(m,e,STALE);
     if(owner_held(m,(unsigned)i))return reject(m,e,BUSY);
     if(!permission(m,e,m->tick)||m->slots[i].header[17]!=m->endpoint[e].consent)return reject(m,e,PERMISSION);
     m->lease_status=1;m->lease_endpoint=e;m->lease_sequence=m->lease_sequence_stage;
     m->lease_slot=(unsigned)i;m->lease_generation=m->slots[i].generation;m->lease_consent=m->endpoint[e].consent;return true;
    }
    if(v==2) {
     if(m->lease_status!=1){global_error(m,STALE);return false;}
     unsigned e=(unsigned)m->lease_endpoint;
     if(m->slots[m->lease_slot].generation!=m->lease_generation||m->endpoint[e].consent!=m->lease_consent)return reject(m,e,STALE);
     return consume(m,e,m->lease_sequence,true);
    }
    if(v==3) {
     if(!m->lease_status){global_error(m,STALE);return false;}
     unsigned i=(unsigned)m->lease_slot;
     if(owner_held(m,i)){global_error(m,BUSY);return false;}
     bool cancelled=m->lease_status==2;m->lease_status=0;
     if(cancelled){retire_slot(m,i);}
     return true;
    }
    global_error(m,FORMAT);return false;
   default:global_error(m,FORMAT);return false;
  }
 }
 unsigned e=a/256-1;unsigned offset=a&255;LemmaOFEndpoint*p=&m->endpoint[e];
 if((offset>=48&&offset<=104&&!(offset&7)) || offset==128) {
  if((p->state!=IDLE&&p->state!=CONFIGURED)||!endpoint_empty(m,e))return reject(m,e,BUSY);
  switch(offset) {
   case 48:p->width=v;break;case 56:p->height=v;break;case 64:p->stride=v;break;
   case 72:p->format=v;break;case 80:p->gain=v;break;case 88:p->exposure=v;break;
   case 96:p->row_ticks=v;break;case 104:p->period=v;break;case 128:p->calibration=v;break;
  }
  return true;
 }
 if(offset==112) {
  if(v && (!id(v)||v<=p->consent_floor))return reject(m,e,STALE);
  if(v && (p->expiry<=m->tick||p->expiry>LEMMA_OF_MAX_TICK))return reject(m,e,EXPIRED);
  uint64_t expiry=p->expiry;
  fence(m,e,0,p->state==IDLE?IDLE:CONFIGURED);
  if(v){m->reset_fenced=false;p->consent=v;p->consent_floor=v;p->expiry=expiry;}return true;
 }
 if(offset==120) {
  if(v<=m->tick||v>LEMMA_OF_MAX_TICK)return reject(m,e,RANGE);
  if((p->state!=IDLE&&p->state!=CONFIGURED)||!endpoint_empty(m,e))return reject(m,e,BUSY);
  p->expiry=v;return true;
 }
 if(offset==184)return consume(m,e,v,false);
 if(offset!=24)return reject(m,e,FORMAT);
 if(v==1) {
  if(p->epoch==LEMMA_OF_MAX_ID)return reject(m,e,EXHAUSTED);
  fence(m,e,0,IDLE);p->epoch++;p->completed=p->source_sequence=0;p->have_sof=false;
  default_config(p,e);p->error=0;return true;
 }
 if(v==2) {
  if((p->state!=IDLE&&p->state!=CONFIGURED)||!endpoint_empty(m,e))return reject(m,e,BUSY);
  if(!configuration(p,e))return reject(m,e,FORMAT);
  if(p->config==LEMMA_OF_MAX_ID)return reject(m,e,EXHAUSTED);
  p->config++;p->state=CONFIGURED;p->error=0;return true;
 }
 if(v==3) {
  if(p->state!=CONFIGURED)return reject(m,e,STATE);
  if(!p->config||!configuration(p,e))return reject(m,e,FORMAT);
  if(!permission(m,e,m->tick))return reject(m,e,PERMISSION);
  p->state=ARMED;p->error=0;return true;
 }
 if(v==4) {
  if(p->state!=ARMED)return reject(m,e,STATE);
  if(!permission(m,e,m->tick))return reject(m,e,PERMISSION);
  p->state=RUNNING;p->error=0;return true;
 }
 if(v==5) {
  if(p->state!=RUNNING&&p->state!=DRAINING)return reject(m,e,STATE);
  p->state=p->active_slot>=0?DRAINING:CONFIGURED;p->error=0;return true;
 }
 if(v==6){fence(m,e,0,CONFIGURED);p->error=0;return true;}
 return reject(m,e,FORMAT);
}
