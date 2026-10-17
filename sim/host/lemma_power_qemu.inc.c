/* Selected Power-v2 QEMU hardware adapter. Host only, GPL-2.0-or-later.
 * Included after LemmaDevices by the profile0.4-only checked patch. */
static void lemma_power2_schedule(LemmaDevices *s);
bool lemma_power2_domain_held(void);
bool lemma_power2_rom_reload(void);
void lemma_power2_before_system_reset(void);
void lemma_power2_after_system_reset(void);
static void lemma_trace(LemmaDevices *,const char *,uint64_t,uint64_t,uint64_t);
static void lemma_update_irqs(LemmaDevices *);
static void lemma_prune_pen_inputs(LemmaDevices *);
static void lemma_recorded_input(void *);
static void lemma_schedule_input(LemmaDevices *);
void lemma_fast_block_power_loss(void);
static bool lemma_power2_held(LemmaDevices *s)
{ return s && s->fast_binding && (s->power_reset_pending || lemma_power_safety_domain_reset(&s->power_clock.circuit)); }
bool lemma_power2_domain_held(void) { return lemma_power2_held(binding_devices); }
bool lemma_power2_rom_reload(void) { return binding_devices && binding_devices->power_reset_loss; }
static void lemma_power2_request(LemmaDevices *s,bool release,bool loss)
{
    g_assert(!s->power_reset_pending);
    s->power_reset_pending=true;s->power_reset_release=release;s->power_reset_loss=loss;
    CPUState *cpu;CPU_FOREACH(cpu){cpu->halted=true;cpu_exit(cpu);qemu_cpu_kick(cpu);}
    qemu_system_reset_request(SHUTDOWN_CAUSE_SUBSYSTEM_RESET);
}
static void lemma_power2_advance(LemmaDevices *s,uint64_t edge)
{
    if(!s->fast_binding || s->power_reset_pending)return;
    while(s->power_clock.edge<edge) {
        bool suspended=s->power_clock.circuit.legacy.state==1;
        unsigned event=lemma_power_clock_advance(&s->power_clock,edge,
                                (s->paper.status&1)||lemma_fast_block_busy());
        if(!suspended&&s->power_clock.circuit.legacy.state==1){
            lemma_pen_write(&s->pen,LEMMA_PEN_RESET,1);timer_del(s->pen_timer);lemma_prune_pen_inputs(s);
        }
        if(event) {
            lemma_trace(s,"power-domain",event,s->power_clock.edge,s->power_clock.circuit.reset_epoch);
            lemma_power2_request(s,event==4,event==2);return;
        }
    }
    lemma_update_irqs(s);
}
static void lemma_power2_timer(void *opaque)
{
    LemmaDevices *s=opaque;
    /* The central clock admits equal-time raw supply/button levels before
     * the pending bus write and timeout decision, independent of timer order. */
    lemma_recorded_input(s);
    lemma_power2_advance(s,(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/10);
    lemma_power2_schedule(s);
}
static void lemma_power2_schedule(LemmaDevices *s)
{
    if(!s->fast_binding || s->power_reset_pending){timer_del(s->power_timer);return;}
    uint64_t next=lemma_power_clock_next(&s->power_clock);
    if(next>INT64_MAX/10)timer_del(s->power_timer);
    else timer_mod_ns(s->power_timer,next*10);
}
static void lemma_power2_paper_reset(LemmaDevices *s)
{
    LemmaPaper *p=&s->paper;
    uint8_t *target=p->target,*visible=p->visible,*latched=p->latched;
    uint64_t descriptor[32],fast=p->fast_ns,quality=p->quality_ns;
    memcpy(descriptor,p->descriptor,sizeof descriptor);
    memset(p,0,sizeof *p);p->target=target;p->visible=visible;p->latched=latched;
    p->width=s->width;p->height=s->height;p->stride=(s->width+1)/2;
    p->fast_ns=fast;p->quality_ns=quality;p->sequencer_enabled=LS_PAPER_SEQUENCER;p->sequencer_clock_ns=10;
    memcpy(p->descriptor,descriptor,sizeof descriptor);
    memset(target,255,s->frame_bytes);memset(latched,255,s->frame_bytes);
    s->dirty=true;
}
void lemma_power2_before_system_reset(void)
{
    LemmaDevices *s=binding_devices;
    if(!s || !s->fast_binding)return;
    if(s->power_reset_loss) {
        MachineState *m=MACHINE(qdev_get_machine());g_assert(m->ram_size==LS_RAM_BYTES);
        memset(memory_region_get_ram_ptr(m->ram),0,LS_RAM_BYTES);
        memory_region_set_dirty(m->ram,0,LS_RAM_BYTES);
        lemma_fast_block_power_loss();
    }
}
void lemma_power2_after_system_reset(void)
{
    LemmaDevices *s=binding_devices;
    if(!s || !s->fast_binding)return;
    bool release=s->power_reset_pending&&s->power_reset_release;
    s->power_reset_pending=s->power_reset_loss=s->power_reset_release=false;
    if(release) {
        lemma_pen_write(&s->pen,LEMMA_PEN_RESET,1);
        lemma_trace(s,"power-release",s->power_clock.edge,s->power_clock.circuit.legacy.reset_cause,s->power_clock.circuit.reset_epoch);
    }
    CPUState *cpu;CPU_FOREACH(cpu)cpu->halted=lemma_power2_held(s);
    lemma_power2_schedule(s);lemma_update_irqs(s);lemma_schedule_input(s);
}
static uint64_t lemma_power2_read(LemmaDevices *s,hwaddr a,unsigned size)
{
    if(!lemma_power_safety_access(a,size,false,0))return 0;
    lemma_power2_advance(s,(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/10);
    return lemma_power_safety_read(&s->power_clock.circuit,a);
}
static void lemma_power2_write(LemmaDevices *s,hwaddr a,uint64_t value,unsigned size)
{
    uint64_t edge=(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/10;
    lemma_power2_advance(s,edge);
    if(!lemma_power_clock_enqueue(&s->power_clock,edge+1,a,size,value)) {
        /* The fast CPU has no hardware bus-stall mechanism. Do not fabricate
         * a guest controller error or drop a legitimate second store. This
         * unimplemented overlap halts this functional backend explicitly. */
        error_report("Power-v2 fast MMIO overlap requires RTL bus timing; pending write retained");
        vm_stop(RUN_STATE_INTERNAL_ERROR);return;
    }
    lemma_power2_schedule(s);
}
static void lemma_inject_supply(Object *obj,const char *value,Error **errp)
{
    LemmaDevices *s=LEMMA_PAPER_PEN(obj);uint64_t fields[3];g_auto(GStrv) words=g_strsplit(value," ",-1);
    if(!s->fast_binding || g_strv_length(words)!=3 || s->external_count==4096) {
        error_setg(errp,"external-supply requires Power-v2: ns kind(2good/3brownout) level; queue capacity4096");return;
    }
    for(unsigned i=0;i<3;i++) {
        GError *error=NULL;
        if(!g_ascii_string_to_unsigned(words[i],10,i==1?2:0,i==0?INT64_MAX:i==1?3:1,&fields[i],&error)) {
            error_setg(errp,"invalid external-supply field%u",i);g_clear_error(&error);return;
        }
    }
    if(fields[0]%10){error_setg(errp,"Power-v2 raw inputs require declared 10ns clock edges");return;}
    lemma_enqueue_external(s,fields[0],fields[1],(LemmaSample){.flags=fields[2]},errp);
}
static char *lemma_get_power2_state(Object *obj,Error **errp)
{
    LemmaDevices *s=LEMMA_PAPER_PEN(obj);LemmaPowerClock observed=s->power_clock;
    /* Observational projection cannot execute a pending effect, reset, I/O,
     * or IRQ publication. The accepted timer owns every effect boundary. */
    uint64_t now=(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/10,next=lemma_power_clock_next(&observed);
    if(!s->power_reset_pending&&now<next)lemma_power_clock_advance(&observed,now,(s->paper.status&1)||lemma_fast_block_busy());
    LemmaPowerSafety *c=&observed.circuit;LemmaPower *p=&c->legacy;
    return g_strdup_printf("{\"enabled\":true,\"safety\":true,\"state\":%"PRIu64",\"error\":%"PRIu64",\"reset_cause\":%"PRIu64",\"button_level\":%"PRIu64",\"events\":%"PRIu64",\"epoch\":%"PRIu64",\"wake_cause\":%"PRIu64",\"power_good\":%s,\"brownout\":%s,\"domain_reset\":%s,\"watchdog_armed\":%s,\"watchdog_remaining\":%"PRIu64",\"reset_remaining\":%"PRIu64",\"reset_epoch\":%"PRIu64",\"clock_edge\":%"PRIu64",\"write_pending\":%s,\"write_edge\":%"PRIu64",\"system_reset_pending\":%s}",
        p->state,p->error,p->reset_cause,p->button_level,p->events,p->epoch,p->wake_cause,c->power_good?"true":"false",c->brownout?"true":"false",lemma_power2_held(s)?"true":"false",c->armed?"true":"false",c->remaining,c->reset_remaining,c->reset_epoch,observed.edge,observed.write_pending?"true":"false",observed.write_edge,s->power_reset_pending?"true":"false");
}
