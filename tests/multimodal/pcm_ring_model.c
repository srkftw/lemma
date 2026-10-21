/* Hardware model qualification. SPDX-License-Identifier: Apache-2.0 */
#include "lemma_multimodal_v2.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
#define A(o) (0x900+(o))
static uint16_t memory[2048];
static uint16_t waveform(uint64_t i){return (uint16_t)(i*7919+311);}
static void setup(LemmaMM2*m,uint64_t capacity,uint64_t expiry){
 lemma_mm2_init(m);assert(lemma_mm2_read(m,8)==2);
 assert(lemma_mm2_write(m,56,0));assert(lemma_mm2_write(m,A(80),1));assert(lemma_mm2_write(m,A(96),1));assert(lemma_mm2_write(m,A(104),expiry));
 assert(lemma_mm2_write(m,A(56),6250));assert(lemma_mm2_write(m,A(24),2));assert(lemma_mm2_write(m,A(24),3));
 assert(lemma_mm2_write(m,0x68,0x82000000));assert(lemma_mm2_write(m,0x70,capacity));assert(lemma_mm2_write(m,0x88,1));assert(lemma_mm2_valid(m));
}
static uint64_t data_at(uint64_t address){uint64_t data=0;assert(address>=0x82000000&&address<=0x82000000+4096-8&&!(address&7));for(unsigned i=0;i<4;i++)data|=(uint64_t)memory[(address-0x82000000)/2+i]<<(i*16);return data;}
static void beat(LemmaMM2*m){bool write;uint64_t addr,value;assert(lemma_mm2_dma(m,&write,&addr,&value));assert(!write);lemma_mm2_clock(m,m->legacy.tick+1,true,false,data_at(addr));assert(lemma_mm2_valid(m));}
static void publish(LemmaMM2*m,uint64_t to){for(uint64_t i=m->producer;i<to;i++)memory[i&(m->capacity-1)]=waveform(i);assert(lemma_mm2_write(m,0x78,to));}
static void long_stream(void){
 LemmaMM2 m;setup(&m,2048,200000000);uint64_t total=20003;publish(&m,1024);
 while(m.legacy.stream[8].count<16)beat(&m);
 assert(m.legacy.stream[8].submitted==16&&m.producer==1024&&m.fetch==16);assert(lemma_mm2_write(&m,A(24),4));
 uint64_t emitted=0,reads=4;bool eof=false;
 while(m.status==1){
  if(total-m.producer&&m.producer-m.fetch<=1536){uint64_t n=total-m.producer;if(n>512)n=512;publish(&m,m.producer+n);}
  if(m.producer==total&&!eof){assert(lemma_mm2_write(&m,0x88,2));eof=true;}
  bool write;uint64_t addr,value;bool dma=lemma_mm2_dma(&m,&write,&addr,&value);uint64_t next=lemma_mm_next(&m.legacy);if(dma&&m.legacy.tick+1<next)next=m.legacy.tick+1;
  assert(next!=UINT64_MAX);lemma_mm2_clock(&m,next,dma,false,dma?data_at(addr):0);if(dma)reads++;
  if(m.legacy.pcm_valid){assert((int64_t)m.legacy.pcm_data==(int16_t)waveform(emitted));assert(m.legacy.pcm_position==emitted+1);emitted++;}
  assert(lemma_mm2_valid(&m));assert(m.gaps==0);
 }
 assert(m.status==2&&emitted==total&&m.fetch==total&&m.legacy.stream[8].submitted==total&&m.legacy.stream[8].consumed==total&&m.legacy.stream[8].error==0);
 printf("long PCM samples=%llu beats=%llu ticks=%llu EOF-tail=3 gaps=0\n",(unsigned long long)emitted,(unsigned long long)reads,(unsigned long long)m.legacy.tick);
}
static void cancellation(void){
 LemmaMM2 m;setup(&m,16,100000);publish(&m,8);bool write;uint64_t addr,value;assert(lemma_mm2_dma(&m,&write,&addr,&value));
 uint64_t held=addr;assert(lemma_mm2_write(&m,56,1));assert(lemma_mm2_dma(&m,&write,&addr,&value)&&!write&&addr==held&&m.bus_cancel);
 assert(!lemma_mm2_write(&m,0x68,0x82001000));assert(m.base==held);
 lemma_mm2_clock(&m,1,true,false,UINT64_MAX);assert(m.bus_kind==0&&m.legacy.stream[8].submitted==0&&m.legacy.stream[8].consumed==0&&!m.legacy.stream[8].count&&m.status==3);assert(lemma_mm2_valid(&m));
 setup(&m,16,100000);publish(&m,8);assert(lemma_mm2_write(&m,A(24),1));assert(m.legacy.stream[8].state==2&&m.legacy.stream[8].epoch==2&&m.bus_cancel);lemma_mm2_clock(&m,1,true,false,UINT64_MAX);assert(m.legacy.stream[8].state==2&&m.legacy.stream[8].epoch==2&&m.legacy.stream[8].submitted==0);assert(lemma_mm2_valid(&m));
 setup(&m,16,100000);publish(&m,8);assert(lemma_mm2_write(&m,64,0));assert(m.legacy.stream[8].state==8&&m.bus_cancel);lemma_mm2_clock(&m,1,true,false,UINT64_MAX);assert(m.legacy.stream[8].state==8&&m.legacy.stream[8].submitted==0);assert(lemma_mm2_valid(&m));
 setup(&m,16,100000);publish(&m,8);assert(lemma_mm2_write(&m,A(80),0));assert(lemma_mm2_write(&m,A(24),1));assert(lemma_mm2_write(&m,A(96),1));assert(lemma_mm2_write(&m,A(24),2));assert(lemma_mm2_write(&m,A(80),2));assert(lemma_mm2_write(&m,A(104),100000));assert(lemma_mm2_write(&m,A(24),3));assert(!lemma_mm2_write(&m,A(112),7));assert(m.legacy.stream[8].count==0);lemma_mm2_clock(&m,1,true,false,UINT64_MAX);assert(m.legacy.stream[8].state==4&&m.legacy.stream[8].epoch==2&&m.legacy.stream[8].lease==100000);assert(lemma_mm2_write(&m,A(112),7));assert(m.legacy.stream[8].count==1);assert(lemma_mm2_valid(&m));
 setup(&m,16,10);publish(&m,8);lemma_mm2_clock(&m,10,true,false,UINT64_MAX);assert(m.legacy.stream[8].submitted==0&&!m.bus_kind&&m.status==3);assert(lemma_mm2_valid(&m));
}
static void fairness_and_copy(void){
 LemmaMM2 m;setup(&m,16,100000);publish(&m,16);bool write;uint64_t addr,value;assert(lemma_mm2_dma(&m,&write,&addr,&value)&&!write);uint64_t held=addr;
 assert(lemma_mm_stimulus(&m.legacy,0,1234,6,2));assert(lemma_mm2_write(&m,0x100+80,1));assert(lemma_mm2_write(&m,0x100+104,100000));assert(lemma_mm2_write(&m,0x100+56,1000));assert(lemma_mm2_write(&m,0x100+64,4));assert(lemma_mm2_write(&m,0x100+24,2));assert(lemma_mm2_write(&m,0x100+24,3));assert(lemma_mm2_write(&m,0x100+24,4));lemma_mm2_clock(&m,5,false,false,0);assert(m.legacy.stream[0].count==1);assert(lemma_mm2_write(&m,0x100+160,0x82001000));assert(lemma_mm2_write(&m,0x100+168,8));assert(lemma_mm2_write(&m,0x100+176,1));
 assert(lemma_mm2_dma(&m,&write,&addr,&value)&&!write&&addr==held);beat(&m);
 assert(lemma_mm2_dma(&m,&write,&addr,&value)&&write&&addr==0x82001000&&value==1228);
 LemmaMM2 copy=m;
 for(unsigned i=0;i<20&&(m.legacy.dma_active||m.bus_kind);i++){
  assert(lemma_mm2_dma(&m,&write,&addr,&value));uint64_t data=write?0:data_at(addr);
  lemma_mm2_clock(&m,m.legacy.tick+1,true,false,data);lemma_mm2_clock(&copy,copy.legacy.tick+1,true,false,data);assert(memcmp(&m,&copy,sizeof(m))==0);
 }
 assert(!m.legacy.dma_active&&m.legacy.stream[0].dma_status==2&&m.fetch==16);
}
static void negatives(void){
 LemmaMM2 m;setup(&m,16,100000);publish(&m,8);uint64_t old=m.producer;
 assert(!lemma_mm2_write(&m,0x78,7)&&m.producer==old);assert(!lemma_mm2_write(&m,0x78,17)&&m.producer==old);assert(!lemma_mm2_write(&m,A(112),1));
 assert(lemma_mm2_write(&m,0x88,2));assert(!lemma_mm2_write(&m,0x78,12)&&m.producer==old);
 setup(&m,16,100000);publish(&m,4);m.legacy.stream[8].submitted=UINT64_MAX-2;beat(&m);assert(m.status==4&&m.legacy.stream[8].error==14&&m.legacy.stream[8].submitted==UINT64_MAX-2);
 setup(&m,16,100000);publish(&m,4);beat(&m);assert(lemma_mm2_write(&m,A(24),4));m.legacy.stream[8].consumed=UINT64_MAX;lemma_mm2_clock(&m,m.legacy.tick+1,false,false,0);assert(m.legacy.stream[8].consumed==UINT64_MAX&&m.status==4);
 setup(&m,16,100000);assert(lemma_mm2_write(&m,A(24),4));lemma_mm2_clock(&m,1,false,false,0);assert(m.gaps==1&&m.legacy.stream[8].error==10);
 setup(&m,16,100000);publish(&m,3);bool w;uint64_t a,v;assert(!lemma_mm2_dma(&m,&w,&a,&v));assert(lemma_mm2_write(&m,0x88,2));assert(lemma_mm2_dma(&m,&w,&a,&v));beat(&m);assert(m.fetch==3&&m.legacy.stream[8].count==3);
 LemmaMM2 bad=m;bad.bus_kind=2;bad.bus_samples=5;assert(!lemma_mm2_valid(&bad));
 bad=m;bad.legacy.stream[0].epoch=0;assert(!lemma_mm2_valid(&bad));
 bad=m;bad.bus_kind=1;bad.legacy.dma_active=0;assert(!lemma_mm2_valid(&bad));
}
int main(void){long_stream();cancellation();fairness_and_copy();negatives();puts("PASS private PCM ring controller model: long arbitrary content, EOF, held reads, cancel/expiry, fairness, copy, wrap and malformed guards");}
