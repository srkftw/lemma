/* Functional synthetic hardware adapter. No guest policy. GPL-2.0-or-later. */
static void lemma_mm_schedule(LemmaDevices*s);
static LemmaMM *lemma_mm_core(LemmaDevices*s)
{
 return s->multimodal_controller_abi==2?&s->multimodal_v2.legacy:&s->multimodal;
}
static void lemma_mm_sync(LemmaDevices*s)
{
 if(!s->multimodal_enabled)return;
 LemmaMM*core=lemma_mm_core(s);uint64_t now=(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/10;
 if(s->multimodal_controller_abi==2) {
  bool write=false,held=false,error=false;uint64_t address=0,value=0,data=0;
  /* A functional shared-memory beat completes at the next real controller
   * tick. Repeated MMIO at one timestamp cannot drain arbitrary ring bytes. */
  if(now>core->tick)held=lemma_mm2_dma(&s->multimodal_v2,&write,&address,&value);
  if(held){uint8_t bytes[8];
   if(write){for(unsigned k=0;k<8;k++)bytes[k]=value>>(k*8);error=address_space_write(&address_space_memory,address,MEMTXATTRS_UNSPECIFIED,bytes,8)!=MEMTX_OK;}
   else {error=address_space_read(&address_space_memory,address,MEMTXATTRS_UNSPECIFIED,bytes,8)!=MEMTX_OK;if(!error)for(unsigned k=0;k<8;k++)data|=(uint64_t)bytes[k]<<(k*8);}
  }
  lemma_mm2_clock(&s->multimodal_v2,now,held,error,data);
 }else{
  lemma_mm_advance(core,now);uint64_t address,value;
  /* Historical ABI1 completion ordering is preserved. */
  if(lemma_mm_dma(core,&address,&value)) {
   uint8_t bytes[8];for(unsigned k=0;k<8;k++)bytes[k]=value>>(k*8);
   lemma_mm_dma_complete(core,address_space_write(&address_space_memory,address,MEMTXATTRS_UNSPECIFIED,bytes,8)!=MEMTX_OK);
  }
 }
 qemu_set_irq(s->multimodal_irq,lemma_mm_irq(core));
}
static void lemma_mm_timer(void*opaque)
{
 LemmaDevices*s=opaque;lemma_mm_sync(s);
 LemmaMM*core=lemma_mm_core(s);
 if(core->pcm_valid&&s->multimodal_audio) {
  uint64_t words[3]={core->pcm_tick,core->pcm_position,core->pcm_data};uint8_t b[24];
  for(unsigned i=0;i<3;i++)for(unsigned k=0;k<8;k++)b[i*8+k]=words[i]>>(k*8);
  if(fwrite(b,1,24,s->multimodal_audio)!=24){error_report("multimodal waveform write failed");exit(1);}
 }
 lemma_mm_schedule(s);
}
static void lemma_mm_schedule(LemmaDevices*s)
{
 LemmaMM*core=lemma_mm_core(s);uint64_t n=lemma_mm_next(core);
 if(s->multimodal_controller_abi==2?s->multimodal_v2.bus_kind!=0:core->dma_active)n=MIN(n,core->tick+1);
 if(n>INT64_MAX/10)timer_del(s->multimodal_timer);else timer_mod_ns(s->multimodal_timer,n*10);
}
static MemTxResult lemma_mm_qread(void*opaque,hwaddr a,uint64_t*v,unsigned size,MemTxAttrs attrs)
{
 LemmaDevices*s=opaque;if(size!=8||(a&7)||a>=0xa00){*v=0;return MEMTX_ERROR;}
 lemma_mm_sync(s);*v=s->multimodal_controller_abi==2?lemma_mm2_read(&s->multimodal_v2,a):lemma_mm_read(&s->multimodal,a);lemma_mm_schedule(s);return MEMTX_OK;
}
static MemTxResult lemma_mm_qwrite(void*opaque,hwaddr a,uint64_t v,unsigned size,MemTxAttrs attrs)
{
 LemmaDevices*s=opaque;if(size!=8||(a&7)||a>=0xa00)return MEMTX_ERROR;
 lemma_mm_sync(s);if(s->multimodal_controller_abi==2)lemma_mm2_write(&s->multimodal_v2,a,v);else lemma_mm_write(&s->multimodal,a,v);lemma_mm_schedule(s);
 qemu_set_irq(s->multimodal_irq,lemma_mm_irq(lemma_mm_core(s)));return MEMTX_OK;
}
static const MemoryRegionOps multimodal_ops={.read_with_attrs=lemma_mm_qread,.write_with_attrs=lemma_mm_qwrite,
 .endianness=DEVICE_LITTLE_ENDIAN,.valid={.min_access_size=8,.max_access_size=8},.impl={.min_access_size=8,.max_access_size=8}};
static void lemma_mm_inject(Object*obj,const char*value,Error**errp)
{
 LemmaDevices*s=LEMMA_PAPER_PEN(obj);g_auto(GStrv) words=g_strsplit(value," ",-1);uint64_t f[4];
 if(!s->multimodal_enabled||g_strv_length(words)!=4){error_setg(errp,"multimodal-stimulus needs id u32-code u32-reference quality at current virtual time");return;}
 for(unsigned i=0;i<4;i++){GError*e=NULL;if(!g_ascii_string_to_unsigned(words[i],10,0,i?i==3?65535:UINT32_MAX:7,&f[i],&e)){error_setg(errp,"invalid multimodal stimulus");g_clear_error(&e);return;}}
 lemma_mm_sync(s);lemma_mm_stimulus(lemma_mm_core(s),f[0],(int32_t)f[1],(int32_t)f[2],f[3]);lemma_mm_schedule(s);
}
static char*lemma_mm_state(Object*obj,Error**errp)
{
 LemmaDevices*s=LEMMA_PAPER_PEN(obj);GString*b=g_string_new(NULL);
 g_string_append_printf(b,"{\"enabled\":%s,\"tick\":%"PRIu64",\"scope\":\"synthetic-aperture/%u\",\"physical_qualified\":false,\"streams\":[",s->multimodal_enabled?"true":"false",lemma_mm_core(s)->tick,s->multimodal_controller_abi);
 for(unsigned i=0;i<9;i++){LemmaMMStream*t=&lemma_mm_core(s)->stream[i];g_string_append_printf(b,"%s{\"id\":%u,\"state\":%"PRIu64",\"error\":%"PRIu64",\"count\":%"PRIu64",\"epoch\":%"PRIu64",\"sequence\":%"PRIu64",\"consent\":%"PRIu64",\"consumed\":%"PRIu64",\"submitted\":%"PRIu64"}",i?",":"",i,t->state,t->error,t->count,t->epoch,t->sequence,t->consent,t->consumed,t->submitted);}
 g_string_append_printf(b,"],\"controller_abi\":%u",s->multimodal_controller_abi);
 if(s->multimodal_controller_abi==2){LemmaMM2*m=&s->multimodal_v2;g_string_append_printf(b,",\"ring\":{\"base\":%"PRIu64",\"capacity\":%"PRIu64",\"accepted\":%"PRIu64",\"fetched\":%"PRIu64",\"status\":%"PRIu64",\"eof\":%"PRIu64",\"end\":%"PRIu64",\"gaps\":%"PRIu64",\"held_kind\":%"PRIu64",\"held_address\":%"PRIu64",\"held_cancel\":%"PRIu64"}",m->base,m->capacity,m->producer,m->fetch,m->status,m->eof,m->end,m->gaps,m->bus_kind,m->bus_addr,m->bus_cancel);}
 g_string_append(b,"}");return g_string_free(b,false);
}
