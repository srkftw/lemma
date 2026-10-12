/* LemmaSim QEMU hardware adapter. Host only. SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "qemu/units.h"
#include "qemu/error-report.h"
#include "qapi/error.h"
#include "hw/core/sysbus.h"
#include "hw/core/irq.h"
#include "hw/core/qdev-properties.h"
#include "hw/core/boards.h"
#include "hw/core/resettable.h"
#include "qemu/timer.h"
#include "ui/console.h"
#include "ui/input.h"
#include "system/device_tree.h"
#include "migration/vmstate.h"
#include "system/runstate.h"
#include "lemma_silicon_fast.h"
#include "lemma_model.h"
#define TYPE_LEMMA_PAPER_PEN "lemma-paper-pen"
OBJECT_DECLARE_SIMPLE_TYPE(LemmaDevices, LEMMA_PAPER_PEN)
struct LemmaDevices {
    SysBusDevice parent_obj;
    MemoryRegion paper_mmio,pen_mmio;
    qemu_irq paper_irq,pen_irq,power_irq;
    LemmaPaper paper; LemmaPen pen;
    LemmaPower power;
    bool power_enabled;
    uint32_t width,height,pressure_max;
    QEMUTimer *timer,*input_timer,*pen_timer,*run_timer;
    VMChangeStateEntry *runstate_entry;
    QemuConsole *console; QemuInputHandlerState *input;
    uint64_t mouse_x,mouse_y,mouse_flags;
    bool input_dirty;
    char *input_file,*output_file,*trace_file;
    FILE *trace,*raw_output;
    uint64_t ingress_sequence;
    LemmaSample *recorded;
    uint64_t recorded_count,recorded_next;
    uint32_t frame_bytes,external_head,external_count;
    LemmaSample external[4096];
    uint64_t external_delivery[4096];
    uint8_t external_kind[4096];
    bool dirty,reset_seen,run_stopping,fast_binding;
    uint64_t trace_limit,trace_rows,trace_omitted;
};
void lemma_binding_create(MachineState *,DeviceState *);
void lemma_binding_add_fdt(MachineState *);
void lemma_binding_set_dtb(uint64_t,uint64_t);
char *lemma_block_state_json(void);
bool lemma_fast_block_busy(void);
bool lemma_sim_stop_pending(void);
static LemmaDevices *binding_devices;
static void lemma_schedule_input(LemmaDevices *);
bool lemma_sim_stop_pending(void)
{ return binding_devices && binding_devices->run_stopping; }
static void lemma_trace(LemmaDevices *s,const char *event,uint64_t a,uint64_t b,uint64_t c)
{
    if(!s->trace)return;
    if(s->fast_binding && s->trace_rows>=s->trace_limit) {
        if(s->trace_omitted<UINT64_MAX)s->trace_omitted++;
        return;
    }
    s->trace_rows++;
    if(fprintf(s->trace,"%"PRIu64" %s %"PRIu64" %"PRIu64" %"PRIu64"\n",
        (uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),event,a,b,c)<0 || (!s->fast_binding && fflush(s->trace))) {
        error_report("LemmaSim device trace write failed");exit(1);
    }
}
static void lemma_update_irqs(LemmaDevices *s)
{
    qemu_set_irq(s->paper_irq,lemma_paper_irq(&s->paper));qemu_set_irq(s->pen_irq,lemma_pen_irq(&s->pen));
    if(s->power_enabled)qemu_set_irq(s->power_irq,lemma_power_irq(&s->power));
}
static void lemma_ingress(LemmaDevices *s,const LemmaSample *sample)
{
    /* Capture external ingress, including events rejected at a loss boundary.
     * Controller sequence/epoch remain independently observable in its head. */
    uint64_t fields[]={++s->ingress_sequence,sample->time,sample->x,sample->y,
        sample->pressure,sample->flags,sample->tool,sample->buttons,1};
    if(s->raw_output) {
        uint8_t bytes[72];
        for(unsigned i=0;i<9;i++)for(unsigned j=0;j<8;j++)bytes[i*8+j]=fields[i]>>(j*8);
        if(fwrite(bytes,1,sizeof(bytes),s->raw_output)!=sizeof(bytes) || fflush(s->raw_output)) {
            error_report("LemmaSim raw-output write failed");exit(1);
        }
    }
    bool suspended=s->power_enabled && s->power.state==1;
    bool accepted=!suspended && lemma_pen_push(&s->pen,sample);
    lemma_trace(s,suspended?"pen-input-discarded-suspend":accepted?"pen-input":"pen-input-rejected",s->ingress_sequence,
        accepted?s->pen.next_sequence-1:0,s->pen.epoch);
}
static void lemma_watchdog(void *opaque)
{
    LemmaDevices *s=opaque;
    uint64_t old=s->pen.epoch;
    lemma_pen_advance(&s->pen,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/100);
    if(old!=s->pen.epoch)lemma_trace(s,"pen-watchdog-loss",s->pen.epoch,s->pen.lost,0);
    lemma_update_irqs(s);
}
static void lemma_schedule_watchdog(LemmaDevices *s)
{
    if(s->pen.contact_deadline)timer_mod_ns(s->pen_timer,s->pen.contact_deadline*100);
    else timer_del(s->pen_timer);
}
static void lemma_timer(void *opaque)
{
    LemmaDevices *s=opaque;
    lemma_paper_advance(&s->paper,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));
    lemma_trace(s,"paper-complete",s->paper.completed,s->paper.status,0);
    lemma_update_irqs(s);
    s->dirty=true;
    qemu_console_update(s->console,s->paper.latched_x,s->paper.latched_y,s->paper.latched_w,s->paper.latched_h);
}
static void lemma_prune_pen_inputs(LemmaDevices *s)
{
    uint32_t kept=0;
    for(uint32_t i=0;i<s->external_count;i++) {
        uint32_t from=(s->external_head+i)%4096;
        if(s->external_kind[from]!=1)continue;
        uint32_t to=(s->external_head+kept++)%4096;
        s->external[to]=s->external[from];s->external_delivery[to]=s->external_delivery[from];s->external_kind[to]=1;
    }
    s->external_count=kept;s->recorded_next=s->recorded_count;s->input_dirty=false;
    lemma_schedule_input(s);
}
static bool lemma_power_address(LemmaDevices *s,hwaddr a)
{ return s->power_enabled && a>=LS_POWER_BASE-LEMMA_PAPER_BASE && a<LS_POWER_BASE-LEMMA_PAPER_BASE+LS_POWER_SPAN; }
static uint64_t lemma_paper_mmio_read(void *opaque,hwaddr a,unsigned size)
{
    LemmaDevices *s=opaque;
    if(lemma_power_address(s,a))return size==8 && !(a&7)?lemma_power_read(&s->power,a-(LS_POWER_BASE-LEMMA_PAPER_BASE)):0;
    lemma_paper_advance(&s->paper,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));return lemma_paper_read(&s->paper,a,size);
}
static void lemma_paper_mmio_write(void *opaque,hwaddr a,uint64_t v,unsigned size)
{
    LemmaDevices *s=opaque;
    if(lemma_power_address(s,a)) {
        bool accepted=false;
        if(size!=8 || (a&7))s->power.error=2;
        else accepted=lemma_power_write(&s->power,a-(LS_POWER_BASE-LEMMA_PAPER_BASE),v,
                                       (s->paper.status&1) || lemma_fast_block_busy());
        if(accepted) {
            lemma_pen_write(&s->pen,LEMMA_PEN_RESET,1);timer_del(s->pen_timer);lemma_prune_pen_inputs(s);
        }
        lemma_trace(s,"power-command",a,v,s->power.state);lemma_update_irqs(s);return;
    }
    lemma_paper_write(&s->paper,a,v,size,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));
    if(a==LEMMA_PAPER_COMMAND || a==LEMMA_PAPER_RESET || a==LEMMA_PAPER_ACK)
        lemma_trace(s,"paper-command",a,v,s->paper.status);
    if(s->paper.status&1)timer_mod_ns(s->timer,s->paper.deadline_ns);else timer_del(s->timer);
    lemma_update_irqs(s);
}
static uint64_t lemma_pen_mmio_read(void *opaque,hwaddr a,unsigned size)
{
    LemmaDevices *s=opaque;
    return size==8 && !(a&7) ? lemma_pen_read(&s->pen,a) : 0;
}
static void lemma_pen_mmio_write(void *opaque,hwaddr a,uint64_t v,unsigned size)
{
    LemmaDevices *s=opaque;
    if(size==8 && !(a&7))lemma_pen_write(&s->pen,a,v);else s->pen.error=3;
    lemma_schedule_watchdog(s);
    lemma_update_irqs(s);
}
static bool lemma_power_access(hwaddr a,unsigned size,bool write,uint64_t value)
{
    uint32_t offset=a-(LS_POWER_BASE-LEMMA_PAPER_BASE);
    if(size!=8 || (a&7))return false;
    if(write)return (offset==LEMMA_POWER_COMMAND && (value==1 || value==2)) ||
        (offset==LEMMA_POWER_ACK && value<=3) || (offset==LEMMA_POWER_CLEAR_ERROR && value==1);
    return offset==LEMMA_POWER_MAGIC || offset==LEMMA_POWER_VERSION || offset==LEMMA_POWER_STATE ||
        offset==LEMMA_POWER_ERROR || offset==LEMMA_POWER_RESET_CAUSE || offset==LEMMA_POWER_BUTTON_LEVEL ||
        offset==LEMMA_POWER_EVENTS || offset==LEMMA_POWER_EPOCH || offset==LEMMA_POWER_WAKE_CAUSE ||
        offset==LEMMA_POWER_COMMAND || offset==LEMMA_POWER_ACK || offset==LEMMA_POWER_CLEAR_ERROR;
}
static MemTxResult lemma_paper_read_attrs(void *opaque,hwaddr a,uint64_t *value,unsigned size,MemTxAttrs attrs)
{
    LemmaDevices *s=opaque;
    if(lemma_power_address(s,a) && !lemma_power_access(a,size,false,0)) {
        s->power.error=2;*value=0;return MEMTX_ERROR;
    }
    *value=lemma_paper_mmio_read(opaque,a,size);return MEMTX_OK;
}
static MemTxResult lemma_paper_write_attrs(void *opaque,hwaddr a,uint64_t value,unsigned size,MemTxAttrs attrs)
{
    LemmaDevices *s=opaque;
    if(lemma_power_address(s,a) && !lemma_power_access(a,size,true,value)) {
        s->power.error=2;return MEMTX_ERROR;
    }
    lemma_paper_mmio_write(opaque,a,value,size);return MEMTX_OK;
}
static bool lemma_paper_accepts(void *opaque,hwaddr a,unsigned size,bool write,MemTxAttrs attrs)
{
    LemmaDevices *s=opaque;
    if(!lemma_power_address(s,a))return true;
    uint32_t offset=a-(LS_POWER_BASE-LEMMA_PAPER_BASE);
    bool accepted=size==8 && !(a&7) && (write?
        (offset==LEMMA_POWER_COMMAND || offset==LEMMA_POWER_ACK || offset==LEMMA_POWER_CLEAR_ERROR):
        lemma_power_access(a,size,false,0));
    /* QEMU validates alignment before dispatching read/write_with_attrs.
     * Its accepts hook runs first, so malformed Power accesses latch their
     * controller error even when generic dispatch rejects the transaction. */
    if(!accepted)s->power.error=2;
    return accepted;
}
static const MemoryRegionOps paper_ops={.read_with_attrs=lemma_paper_read_attrs,.write_with_attrs=lemma_paper_write_attrs,
    .endianness=DEVICE_LITTLE_ENDIAN,.valid={.min_access_size=1,.max_access_size=8,.accepts=lemma_paper_accepts},
    .impl={.min_access_size=1,.max_access_size=8}};
static const MemoryRegionOps pen_ops={.read=lemma_pen_mmio_read,.write=lemma_pen_mmio_write,
    .endianness=DEVICE_LITTLE_ENDIAN,.valid={.min_access_size=8,.max_access_size=8},
    .impl={.min_access_size=8,.max_access_size=8}};
static bool lemma_gfx_update(void *opaque)
{
    LemmaDevices *s=opaque; DisplaySurface *surface=qemu_console_surface(s->console);
    uint64_t previous=s->paper.panel_beats,complete=s->paper.completed;
    if(!s->power_enabled)lemma_paper_advance(&s->paper,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));
    if(previous!=s->paper.panel_beats || complete!=s->paper.completed)s->dirty=true;
    /* A clean surface is a completed synchronous update. Returning false
     * promises an asynchronous callback and leaves QMP screendump waiting. */
    if(!s->dirty)return true;
    s->dirty=false;
    uint8_t *pixels=surface_data(surface);
    for(uint32_t y=0;y<s->height;y++)for(uint32_t x=0;x<s->width;x++) {
        /* Pixman may pad each host row beyond width*4; guest Gray4 remains
         * tightly packed with its independently declared controller stride. */
        uint32_t *row=(uint32_t *)(pixels+(size_t)y*surface_stride(surface));
        uint8_t q=s->paper.visible[y*s->paper.stride+x/2];
        uint32_t c=((x&1)?q&15:q>>4)*17;
        row[x]=0xff000000|c|(c<<8)|(c<<16);
    }
    qemu_console_update(s->console,0,0,s->width,s->height);
    return true;
}
static const GraphicHwOps lemma_gfx_ops={.gfx_update=lemma_gfx_update};
static void lemma_input_event(DeviceState *dev,QemuConsole *src,QemuInputEvent *evt)
{
    LemmaDevices *s=LEMMA_PAPER_PEN(dev);
    if(evt->type==INPUT_EVENT_KIND_ABS) {
        uint64_t v=qemu_input_scale_axis(evt->abs.value,INPUT_EVENT_ABS_MIN,
            INPUT_EVENT_ABS_MAX,0,65535);
        if(evt->abs.axis==INPUT_AXIS_X)s->mouse_x=v;
        if(evt->abs.axis==INPUT_AXIS_Y)s->mouse_y=v;
        s->input_dirty=true;
    } else if(evt->type==INPUT_EVENT_KIND_BTN && evt->btn.button==INPUT_BUTTON_LEFT) {
        if(evt->btn.down)s->mouse_flags|=LEMMA_PEN_CONTACT;else s->mouse_flags&=~LEMMA_PEN_CONTACT;
        s->input_dirty=true;
    }
}
static void lemma_input_sync(DeviceState *dev)
{
    LemmaDevices *s=LEMMA_PAPER_PEN(dev);
    LemmaSample sample={.time=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)/100,
        .x=s->mouse_x,.y=s->mouse_y,.pressure=(s->mouse_flags&1)?s->pressure_max/2:0,
        .flags=s->mouse_flags|LEMMA_PEN_PROXIMITY|LEMMA_PEN_SYNTHETIC,.tool=1};
    if(s->input_dirty) {lemma_ingress(s,&sample);lemma_schedule_watchdog(s);lemma_update_irqs(s);s->input_dirty=false;}
}
static const QemuInputHandler lemma_input_handler={.name="Lemma raw pointer (synthetic pressure)",
    .mask=INPUT_EVENT_MASK_ABS|INPUT_EVENT_MASK_BTN,.event=lemma_input_event,.sync=lemma_input_sync};
static void lemma_schedule_input(LemmaDevices *s)
{
    uint64_t next=UINT64_MAX;
    if(s->recorded_next<s->recorded_count)next=s->recorded[s->recorded_next].time;
    if(next!=UINT64_MAX)next*=100;
    if(s->external_count)next=MIN(next,s->external_delivery[s->external_head]);
    if(next!=UINT64_MAX)timer_mod_ns(s->input_timer,next);else timer_del(s->input_timer);
}
static void lemma_recorded_input(void *opaque)
{
    LemmaDevices *s=opaque;uint64_t now=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    /* At each physical sample boundary prepared-file pen ingress precedes
     * live ingress. All pen samples see the state before that boundary's
     * button edge. Equal-time raw button levels are sampled once, last level
     * wins; the queue and capture still retain every admitted raw level. */
    while(true) {
        LemmaSample *file=s->recorded_next<s->recorded_count?&s->recorded[s->recorded_next]:NULL;
        LemmaSample *live=s->external_count?&s->external[s->external_head]:NULL;
        uint64_t boundary=MIN(file?file->time*100:UINT64_MAX,
                              live?s->external_delivery[s->external_head]:UINT64_MAX);
        if(boundary==UINT64_MAX || boundary>now)break;
        bool button_seen=false;uint64_t button_level=0;
        while(s->recorded_next<s->recorded_count &&
              s->recorded[s->recorded_next].time*100==boundary)
            lemma_ingress(s,&s->recorded[s->recorded_next++]);
        while(s->external_count && s->external_delivery[s->external_head]==boundary) {
            LemmaSample *sample=&s->external[s->external_head];
            if(s->external_kind[s->external_head]==1) {
                button_seen=true;button_level=sample->flags;
            } else lemma_ingress(s,sample);
            s->external_head=(s->external_head+1)%4096;s->external_count--;
        }
        if(button_seen) {
            lemma_power_button(&s->power,button_level);
            lemma_trace(s,"power-button",s->power.button_level,s->power.epoch,s->power.events);
        }
    }
    lemma_schedule_watchdog(s);lemma_update_irqs(s);lemma_schedule_input(s);
}
static void lemma_enqueue_external(LemmaDevices *s,uint64_t delivery,uint8_t kind,LemmaSample sample,Error **errp)
{
    if(delivery<(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) ||
       (!s->power_enabled && s->external_count &&
        delivery<s->external_delivery[(s->external_head+s->external_count-1)%4096])) {
        error_setg(errp,"external timestamp precedes virtual now or historical queued ingress");return;
    }
    uint32_t insertion=s->external_count;
    /* The successor binding admits input at any future boundary, just as the
     * RTL scheduler does. Backward ring moves preserve raw fields and retain
     * admission order at equal timestamps. Historical profiles retain their
     * nondecreasing-admission restriction. Capacity was checked by the caller. */
    if(s->power_enabled)while(insertion &&
        s->external_delivery[(s->external_head+insertion-1)%4096]>delivery) {
        uint32_t from=(s->external_head+insertion-1)%4096,to=(s->external_head+insertion)%4096;
        s->external[to]=s->external[from];s->external_delivery[to]=s->external_delivery[from];s->external_kind[to]=s->external_kind[from];
        insertion--;
    }
    uint32_t at=(s->external_head+insertion)%4096;
    s->external[at]=sample;s->external_delivery[at]=delivery;s->external_kind[at]=kind;
    s->external_count++;lemma_schedule_input(s);
}
static void lemma_inject_event(Object *obj,const char *value,Error **errp)
{
    LemmaDevices *s=LEMMA_PAPER_PEN(obj);uint64_t fields[8];g_auto(GStrv) words=g_strsplit(value," ",-1);
    if(g_strv_length(words)!=8 || s->external_count==4096) {error_setg(errp,"external-event needs eight u64 fields; queue capacity4096");return;}
    for(unsigned i=0;i<8;i++) {
        GError *error=NULL;
        if(!g_ascii_string_to_unsigned(words[i],10,0,i==0?INT64_MAX:UINT64_MAX,&fields[i],&error)) {
            error_setg(errp,"invalid external-event field%u",i);g_clear_error(&error);return;
        }
    }
    LemmaSample sample={.time=fields[1],.x=fields[2],.y=fields[3],.pressure=fields[4],.flags=fields[5],.tool=fields[6],.buttons=fields[7]};
    lemma_enqueue_external(s,fields[0],0,sample,errp);
}
static void lemma_inject_button(Object *obj,const char *value,Error **errp)
{
    LemmaDevices *s=LEMMA_PAPER_PEN(obj);uint64_t fields[2];g_auto(GStrv) words=g_strsplit(value," ",-1);
    if(!s->power_enabled || g_strv_length(words)!=2 || s->external_count==4096) {
        error_setg(errp,"external-button requires enabled Power-v1 and two u64 fields; queue capacity4096");return;
    }
    for(unsigned i=0;i<2;i++) {
        GError *error=NULL;
        if(!g_ascii_string_to_unsigned(words[i],10,0,i==0?INT64_MAX:1,&fields[i],&error)) {
            error_setg(errp,"invalid external-button field%u",i);g_clear_error(&error);return;
        }
    }
    lemma_enqueue_external(s,fields[0],1,(LemmaSample){.flags=fields[1]},errp);
}
static uint64_t read_le64(const uint8_t *b)
{ uint64_t v=0;for(unsigned i=0;i<8;i++)v|=(uint64_t)b[i]<<(i*8);return v; }
static char *lemma_virtual_time(Object *obj,Error **errp)
{ return g_strdup_printf("%"PRIu64,(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)); }
static void lemma_run_stop(void *opaque)
{
    /* Timer dispatch may be on the vCPU thread, where vm_stop queues an
     * asynchronous stop. Prevent idle icount warp crossing that boundary. */
    LEMMA_PAPER_PEN(opaque)->run_stopping=true;
    vm_stop(RUN_STATE_PAUSED);
}
static void lemma_runstate_changed(void *opaque,bool running,RunState state)
{ if(running)LEMMA_PAPER_PEN(opaque)->run_stopping=false; }
static void lemma_run_until(Object *obj,const char *value,Error **errp)
{
    LemmaDevices *s=LEMMA_PAPER_PEN(obj);uint64_t deadline;GError *error=NULL;
    if(!object_dynamic_cast(OBJECT(qdev_get_machine()),MACHINE_TYPE_NAME("lemma-silicon-fast")) ||
       !g_ascii_string_to_unsigned(value,10,0,INT64_MAX,&deadline,&error) ||
       deadline<=(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)) {
        error_setg(errp,"run-until requires a future virtual-nanosecond boundary on silicon-fast");g_clear_error(&error);return;
    }
    s->run_stopping=false;timer_mod_ns(s->run_timer,deadline);
}
static void lemma_load_input(LemmaDevices *s,Error **errp)
{
    g_autofree gchar *bytes=NULL;gsize size=0;GError *err=NULL;
    if(!s->input_file)return;
    if(!g_file_get_contents(s->input_file,&bytes,&size,&err)) {
        error_setg(errp,"raw-input: %s",err->message);g_error_free(err);return;
    }
    if(!size || size%72 || size/72>1000000) {error_setg(errp,"raw-input must contain 1..1000000 complete 72-byte v1 records");return;}
    s->recorded_count=size/72;s->recorded=g_new0(LemmaSample,s->recorded_count);
    for(size_t i=0;i<s->recorded_count;i++) {
        const uint8_t *b=(uint8_t *)bytes+i*72;LemmaSample *v=&s->recorded[i];
        v->sequence=read_le64(b);v->time=read_le64(b+8);v->x=read_le64(b+16);v->y=read_le64(b+24);
        v->pressure=read_le64(b+32);v->flags=read_le64(b+40);v->tool=read_le64(b+48);
        v->buttons=read_le64(b+56);v->epoch=read_le64(b+64);
        if(v->sequence!=i+1 || v->epoch!=1 || v->time>INT64_MAX/100 ||
            (i && v->time<s->recorded[i-1].time)) {error_setg(errp,"raw-input sequence/epoch/time invalid at record %zu",i);return;}
    }
    lemma_schedule_input(s);
}
static void lemma_reset_enter(Object *obj,ResetType type)
{
    LemmaDevices *s=LEMMA_PAPER_PEN(obj);
    timer_del(s->timer);timer_del(s->pen_timer);
    if(s->reset_seen && object_dynamic_cast(OBJECT(qdev_get_machine()),MACHINE_TYPE_NAME("lemma-silicon-fast"))) {
        timer_del(s->input_timer);s->external_head=s->external_count=0;s->recorded_next=s->recorded_count;s->input_dirty=false;
    }
    bool initial_fast = !s->reset_seen && object_dynamic_cast(OBJECT(qdev_get_machine()),MACHINE_TYPE_NAME("lemma-silicon-fast"));
    if(s->power_enabled) {if(initial_fast)lemma_power_init(&s->power);else lemma_power_warm_reset(&s->power);}
    s->reset_seen=true;lemma_paper_reset(&s->paper);
    if(!initial_fast)lemma_pen_write(&s->pen,LEMMA_PEN_RESET,1);
    lemma_trace(s,"device-reset",s->paper.status,s->pen.epoch,0);
}
static void lemma_reset_exit(Object *obj,ResetType type)
{
    /* PLIC legacy hold resets pending bits; drive levels only after it finishes. */
    lemma_update_irqs(LEMMA_PAPER_PEN(obj));
}
static void lemma_realize(DeviceState *dev,Error **errp)
{
    LemmaDevices *s=LEMMA_PAPER_PEN(dev);
    s->fast_binding=object_dynamic_cast(OBJECT(qdev_get_machine()),MACHINE_TYPE_NAME("lemma-silicon-fast"))!=NULL;
    if(s->fast_binding && (!s->trace_limit || s->trace_limit>1000000)) {
        error_setg(errp,"fast trace-limit must be between1 and1000000 rows");return;
    }
    if(!lemma_paper_init(&s->paper,s->width,s->height)) {error_setg(errp,"invalid geometry or paper RAM allocation failed");return;}
    s->frame_bytes=s->paper.stride*s->paper.height;s->dirty=true;
    if(object_dynamic_cast(OBJECT(qdev_get_machine()),MACHINE_TYPE_NAME("lemma-silicon-fast"))) {
        s->paper.sequencer_enabled=LS_PAPER_SEQUENCER;s->paper.sequencer_clock_ns=1000000000ULL/LS_CLOCK_HZ;
        s->power_enabled=LS_POWER_ENABLED;lemma_power_init(&s->power);
    }
    lemma_pen_init(&s->pen,65535,65535,s->pressure_max);
    memory_region_init_io(&s->paper_mmio,OBJECT(s),&paper_ops,s,"lemma-paper-v1",4096);
    memory_region_init_io(&s->pen_mmio,OBJECT(s),&pen_ops,s,"lemma-pen-v1",4096);
    sysbus_init_mmio(SYS_BUS_DEVICE(s),&s->paper_mmio);sysbus_init_mmio(SYS_BUS_DEVICE(s),&s->pen_mmio);
    sysbus_init_irq(SYS_BUS_DEVICE(s),&s->paper_irq);sysbus_init_irq(SYS_BUS_DEVICE(s),&s->pen_irq);
    if(s->power_enabled)sysbus_init_irq(SYS_BUS_DEVICE(s),&s->power_irq);
    s->timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,lemma_timer,s);
    s->input_timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,lemma_recorded_input,s);
    s->pen_timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,lemma_watchdog,s);
    s->run_timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,lemma_run_stop,s);
    s->runstate_entry=qemu_add_vm_change_state_handler(lemma_runstate_changed,s);
    s->console=qemu_graphic_console_create(dev,0,&lemma_gfx_ops,s);
    qemu_console_resize(s->console,s->width,s->height);
    s->input=qemu_input_handler_register(dev,&lemma_input_handler);
    qemu_input_handler_activate(s->input);
    if(s->trace_file) {
        s->trace=fopen(s->trace_file,"wx");
        if(!s->trace) {error_setg(errp,"trace-file must be a new writable file: %s",strerror(errno));return;}
        if(s->fast_binding)setvbuf(s->trace,NULL,_IOFBF,65536);
    }
    if(s->output_file) {
        s->raw_output=fopen(s->output_file,"wx");
        if(!s->raw_output) {error_setg(errp,"raw-output must be a new writable file: %s",strerror(errno));return;}
    }
    lemma_load_input(s,errp);
}
static void lemma_finalize(Object *obj)
{
    LemmaDevices *s=LEMMA_PAPER_PEN(obj);
    if(s->input)qemu_input_handler_unregister(s->input);
    if(s->timer)timer_free(s->timer);
    if(s->input_timer)timer_free(s->input_timer);
    if(s->pen_timer)timer_free(s->pen_timer);
    if(s->run_timer)timer_free(s->run_timer);
    if(s->runstate_entry)qemu_del_vm_change_state_handler(s->runstate_entry);
    if(s->trace)fclose(s->trace);
    if(s->raw_output)fclose(s->raw_output);
    g_free(s->recorded);lemma_paper_destroy(&s->paper);
}
static const Property lemma_properties[]={
    DEFINE_PROP_UINT32("width",LemmaDevices,width,1650),
    DEFINE_PROP_UINT32("height",LemmaDevices,height,2200),
    DEFINE_PROP_UINT32("pressure-max",LemmaDevices,pressure_max,4095),
    DEFINE_PROP_STRING("raw-input",LemmaDevices,input_file),
    DEFINE_PROP_STRING("raw-output",LemmaDevices,output_file),
    DEFINE_PROP_STRING("trace-file",LemmaDevices,trace_file),
    DEFINE_PROP_UINT64("trace-limit",LemmaDevices,trace_limit,1000000),
};
static char *lemma_get_state(Object *obj,Error **errp)
{
    LemmaDevices *s=LEMMA_PAPER_PEN(obj);
    LemmaPaper observed=s->paper,*p=&s->paper;
    if(s->power_enabled) {
        /* Phase observation is a pure projection of accepted data and time.
         * At/after the completion deadline the actual timer owns publication;
         * inspection never executes its pending completion on the guest's behalf. */
        uint64_t now=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
        if((observed.status&1) && now<observed.deadline_ns)lemma_paper_advance(&observed,now);
        p=&observed;
    } else lemma_paper_advance(&s->paper,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));
    if(s->trace)fflush(s->trace);
    if(s->raw_output)fflush(s->raw_output);
    g_autofree gchar *target=g_compute_checksum_for_data(G_CHECKSUM_SHA256,s->paper.target,(size_t)s->paper.stride*s->height);
    g_autofree gchar *visible=g_compute_checksum_for_data(G_CHECKSUM_SHA256,s->paper.visible,(size_t)s->paper.stride*s->height);
    return g_strdup_printf("{\"abi\":1,\"pen\":{\"count\":%u,\"epoch\":%"PRIu64",\"loss\":%"PRIu64",\"resync\":%s,\"head_sequence\":%"PRIu64"},\"paper\":{\"status\":%"PRIu64",\"error\":%"PRIu64",\"completed\":%"PRIu64",\"pending_sequence\":%"PRIu64",\"target_sha256\":\"%s\",\"visible_sha256\":\"%s\",\"sequencer\":{\"enabled\":%s,\"phase\":%"PRIu64",\"drive_remaining\":%"PRIu64",\"drive_clocks\":%"PRIu64",\"scan_beats\":%"PRIu64",\"panel_beats\":%"PRIu64",\"power\":%s}}}",
        s->pen.count,s->pen.epoch,s->pen.lost,s->pen.resync?"true":"false",lemma_pen_read(&s->pen,LEMMA_PEN_HEAD_SEQ),p->status,p->error,p->completed,p->last_sequence,target,visible,p->sequencer_enabled?"true":"false",p->wave_phase,p->drive_remaining,p->drive_clocks,p->scan_beats,p->panel_beats,p->panel_power?"true":"false");
}
static char *lemma_get_trace_state(Object *obj,Error **errp)
{
    LemmaDevices *s=LEMMA_PAPER_PEN(obj);
    if(s->trace)fflush(s->trace);
    return g_strdup_printf("{\"rows\":%"PRIu64",\"omitted\":%"PRIu64",\"limit\":%"PRIu64"}",s->trace_rows,s->trace_omitted,s->trace_limit);
}
static char *lemma_get_storage_state(Object *obj,Error **errp)
{ return lemma_block_state_json(); }
static char *lemma_get_power_state(Object *obj,Error **errp)
{
    LemmaDevices *s=LEMMA_PAPER_PEN(obj);LemmaPower *p=&s->power;
    return g_strdup_printf("{\"enabled\":%s,\"state\":%"PRIu64",\"error\":%"PRIu64",\"reset_cause\":%"PRIu64",\"button_level\":%"PRIu64",\"events\":%"PRIu64",\"epoch\":%"PRIu64",\"wake_cause\":%"PRIu64"}",
        s->power_enabled?"true":"false",p->state,p->error,p->reset_cause,p->button_level,p->events,p->epoch,p->wake_cause);
}
static const VMStateDescription lemma_power_vmstate={.name="lemma-power/1",.version_id=1,.minimum_version_id=1,
    .fields=(const VMStateField[]){
        VMSTATE_UINT64(state,LemmaPower),VMSTATE_UINT64(error,LemmaPower),VMSTATE_UINT64(reset_cause,LemmaPower),
        VMSTATE_UINT64(button_level,LemmaPower),VMSTATE_UINT64(events,LemmaPower),VMSTATE_UINT64(epoch,LemmaPower),VMSTATE_UINT64(wake_cause,LemmaPower),VMSTATE_END_OF_LIST()}};
static const VMStateDescription lemma_sample_vmstate={.name="lemma-sample/1",.version_id=1,.minimum_version_id=1,
    .fields=(const VMStateField[]){
        VMSTATE_UINT64(sequence,LemmaSample),VMSTATE_UINT64(time,LemmaSample),VMSTATE_UINT64(x,LemmaSample),VMSTATE_UINT64(y,LemmaSample),
        VMSTATE_UINT64(pressure,LemmaSample),VMSTATE_UINT64(flags,LemmaSample),VMSTATE_UINT64(tool,LemmaSample),VMSTATE_UINT64(buttons,LemmaSample),VMSTATE_UINT64(epoch,LemmaSample),VMSTATE_END_OF_LIST()}};
#define P64(f) VMSTATE_UINT64(f,LemmaPen)
static const VMStateDescription lemma_pen_vmstate={.name="lemma-pen/1",.version_id=1,.minimum_version_id=1,
    .fields=(const VMStateField[]){
        VMSTATE_STRUCT_ARRAY(fifo,LemmaPen,LEMMA_PEN_FIFO,0,lemma_sample_vmstate,LemmaSample),VMSTATE_UINT32(head,LemmaPen),VMSTATE_UINT32(count,LemmaPen),
        P64(epoch),P64(next_sequence),P64(lost),P64(error),P64(max_x),P64(max_y),P64(pressure_max),P64(caps),
        VMSTATE_BOOL(loss,LemmaPen),VMSTATE_BOOL(resync,LemmaPen),VMSTATE_BOOL(release_seen,LemmaPen),P64(last_time),P64(contact_deadline),VMSTATE_END_OF_LIST()}};
#undef P64
#define P64(f) VMSTATE_UINT64(f,LemmaPaper)
static const VMStateDescription lemma_paper_vmstate={.name="lemma-paper/1",.version_id=1,.minimum_version_id=1,
    .fields=(const VMStateField[]){
        VMSTATE_UINT32_EQUAL(width,LemmaPaper),VMSTATE_UINT32_EQUAL(height,LemmaPaper),VMSTATE_UINT32_EQUAL(stride,LemmaPaper),VMSTATE_BUFFER(aperture,LemmaPaper),
        P64(status),P64(error),P64(tile_x),P64(tile_y),P64(tile_w),P64(tile_h),P64(tile_len),P64(sequence),P64(rect_x),P64(rect_y),P64(rect_w),P64(rect_h),P64(mode),
        P64(completed),P64(last_sequence),P64(deadline_ns),P64(fast_ns),P64(quality_ns),P64(latched_x),P64(latched_y),P64(latched_w),P64(latched_h),P64(latched_mode),
        VMSTATE_UINT64_ARRAY(descriptor,LemmaPaper,32),
        VMSTATE_BOOL(sequencer_enabled,LemmaPaper),P64(sequencer_clock_ns),P64(sequencer_start_ns),P64(sequencer_finish_ns),
        P64(wave_phase),P64(drive_remaining),P64(drive_x),P64(drive_y),P64(drive_code),P64(drive_clocks),P64(scan_beats),P64(panel_beats),VMSTATE_BOOL(panel_power,LemmaPaper),VMSTATE_END_OF_LIST()}};
#undef P64
static int lemma_post_load(void *opaque,int version)
{
    LemmaDevices *s=opaque;
    if(s->pen.head>=LEMMA_PEN_FIFO || s->pen.count>LEMMA_PEN_FIFO || s->external_head>=4096 || s->external_count>4096 ||
       s->recorded_next>s->recorded_count || s->paper.wave_phase>2 || s->paper.drive_remaining>2 ||
       s->paper.panel_beats>s->paper.latched_w*s->paper.latched_h ||
       s->paper.latched_x>s->width || s->paper.latched_y>s->height ||
       s->paper.latched_w>s->width-s->paper.latched_x || s->paper.latched_h>s->height-s->paper.latched_y)return -EINVAL;
    if(s->power_enabled!=(s->fast_binding && LS_POWER_ENABLED) || s->power.state>1 || s->power.error>2 || s->power.reset_cause>2 || (s->power_enabled && s->power.reset_cause==0) || s->power.button_level>1 || (s->power.events&~UINT64_C(3)) || s->power.wake_cause>2)return -EINVAL;
    for(uint32_t i=0;i<s->external_count;i++) {
        uint32_t at=(s->external_head+i)%4096;
        if(s->external_kind[at]>1 || (s->external_kind[at]==1 && (!s->power_enabled || s->external[at].flags>1)))return -EINVAL;
        if(s->external_delivery[at]>INT64_MAX || (i && s->external_delivery[at]<s->external_delivery[(s->external_head+i-1)%4096]))return -EINVAL;
    }
    s->dirty=true;lemma_update_irqs(s);return 0;
}
static int lemma_pre_save(void *opaque)
{
    LemmaDevices *s=opaque;if(!s->power_enabled)lemma_paper_advance(&s->paper,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));s->dirty=true;
    return 0;
}
static const VMStateDescription lemma_vmstate={.name="lemma-paper-pen/1",.version_id=2,.minimum_version_id=2,.pre_save=lemma_pre_save,.post_load=lemma_post_load,
    .fields=(const VMStateField[]){
        VMSTATE_UINT32_EQUAL(width,LemmaDevices),VMSTATE_UINT32_EQUAL(height,LemmaDevices),VMSTATE_UINT32_EQUAL(pressure_max,LemmaDevices),VMSTATE_UINT32_EQUAL(frame_bytes,LemmaDevices),
        VMSTATE_STRUCT(pen,LemmaDevices,0,lemma_pen_vmstate,LemmaPen),VMSTATE_STRUCT(paper,LemmaDevices,0,lemma_paper_vmstate,LemmaPaper),
        VMSTATE_BOOL(power_enabled,LemmaDevices),VMSTATE_STRUCT(power,LemmaDevices,0,lemma_power_vmstate,LemmaPower),
        VMSTATE_VBUFFER_UINT32(paper.target,LemmaDevices,0,NULL,frame_bytes),VMSTATE_VBUFFER_UINT32(paper.visible,LemmaDevices,0,NULL,frame_bytes),VMSTATE_VBUFFER_UINT32(paper.latched,LemmaDevices,0,NULL,frame_bytes),
        VMSTATE_UINT64(mouse_x,LemmaDevices),VMSTATE_UINT64(mouse_y,LemmaDevices),VMSTATE_UINT64(mouse_flags,LemmaDevices),VMSTATE_BOOL(input_dirty,LemmaDevices),VMSTATE_BOOL(reset_seen,LemmaDevices),VMSTATE_BOOL(run_stopping,LemmaDevices),
        VMSTATE_UINT64(ingress_sequence,LemmaDevices),VMSTATE_UINT64_EQUAL(recorded_count,LemmaDevices),VMSTATE_UINT64(recorded_next,LemmaDevices),
        VMSTATE_STRUCT_ARRAY(external,LemmaDevices,4096,0,lemma_sample_vmstate,LemmaSample),VMSTATE_UINT64_ARRAY(external_delivery,LemmaDevices,4096),VMSTATE_UINT32(external_head,LemmaDevices),VMSTATE_UINT32(external_count,LemmaDevices),
        VMSTATE_UINT8_ARRAY(external_kind,LemmaDevices,4096),
        VMSTATE_TIMER_PTR(timer,LemmaDevices),VMSTATE_TIMER_PTR(input_timer,LemmaDevices),VMSTATE_TIMER_PTR(pen_timer,LemmaDevices),VMSTATE_TIMER_PTR(run_timer,LemmaDevices),VMSTATE_END_OF_LIST()}};
static void lemma_class_init(ObjectClass *klass,const void *data)
{
    DeviceClass *dc=DEVICE_CLASS(klass);
    ResettableClass *rc=RESETTABLE_CLASS(klass);
    dc->realize=lemma_realize;
    rc->phases.enter=lemma_reset_enter;rc->phases.exit=lemma_reset_exit;
    device_class_set_props(dc,lemma_properties);
    object_class_property_add_str(klass,"device-state",lemma_get_state,NULL);
    object_class_property_add_str(klass,"trace-state",lemma_get_trace_state,NULL);
    object_class_property_add_str(klass,"storage-state",lemma_get_storage_state,NULL);
    object_class_property_add_str(klass,"power-state",lemma_get_power_state,NULL);
    object_class_property_add_str(klass,"external-event",NULL,lemma_inject_event);
    object_class_property_add_str(klass,"external-button",NULL,lemma_inject_button);
    object_class_property_add_str(klass,"virtual-time",lemma_virtual_time,NULL);
    object_class_property_add_str(klass,"run-until",NULL,lemma_run_until);
    dc->desc="LemmaSim project-owned paper/pen controllers v1 (host hardware only)";
    dc->vmsd=&lemma_vmstate;
    /* Historical virt block coroutines still lack exact checkpoints. Only the
     * matched silicon-fast controller declares a state-complete machine. */
}
static const TypeInfo lemma_type={.name=TYPE_LEMMA_PAPER_PEN,.parent=TYPE_SYS_BUS_DEVICE,
    .instance_size=sizeof(LemmaDevices),.class_init=lemma_class_init,.instance_finalize=lemma_finalize};
static void lemma_register_types(void) {type_register_static(&lemma_type);}
type_init(lemma_register_types)
static void descriptor_checksum(LemmaDevices *s)
{
    uint64_t sum=0;s->paper.descriptor[3]=0;
    for(unsigned i=0;i<32;i++)sum+=s->paper.descriptor[i];
    s->paper.descriptor[3]=sum;
}
void lemma_binding_set_dtb(uint64_t address,uint64_t bytes)
{
    if(binding_devices) {
        uint64_t *d=binding_devices->paper.descriptor;
        d[26]=address;d[27]=bytes;d[30]=address;d[31]=UINT64_C(0x88000000)-address;
        descriptor_checksum(binding_devices);
    }
}
void lemma_binding_create(MachineState *machine,DeviceState *irqchip)
{
    DeviceState *dev=qdev_new(TYPE_LEMMA_PAPER_PEN);LemmaDevices *s=LEMMA_PAPER_PEN(dev);
    uint64_t *d;
    bool fast=object_dynamic_cast(OBJECT(machine),MACHINE_TYPE_NAME("lemma-silicon-fast"))!=NULL;
    if(machine->ram_size!=128*MiB || machine->smp.cpus!=1 || (!fast && machine->dtb)) {
        error_report("lemmasim-virt/0.1.0 requires 128MiB, one hart, generated DTB");exit(1);
    }
    if(fast) {qdev_prop_set_uint32(dev,"width",LS_WIDTH);qdev_prop_set_uint32(dev,"height",LS_HEIGHT);qdev_prop_set_uint32(dev,"pressure-max",LS_PRESSURE_MAX);}
    dev->id=g_strdup("lemma-hardware");
    /* Fixed board hardware is outside the dynamic platform-bus inventory. */
    object_property_add_child(OBJECT(machine),dev->id,OBJECT(dev));
    sysbus_realize_and_unref(SYS_BUS_DEVICE(dev),&error_fatal);
    sysbus_mmio_map(SYS_BUS_DEVICE(dev),0,LEMMA_PAPER_BASE);sysbus_mmio_map(SYS_BUS_DEVICE(dev),1,LEMMA_PEN_BASE);
    sysbus_connect_irq(SYS_BUS_DEVICE(dev),0,qdev_get_gpio_in(irqchip,12));
    sysbus_connect_irq(SYS_BUS_DEVICE(dev),1,qdev_get_gpio_in(irqchip,13));
    if(s->power_enabled)sysbus_connect_irq(SYS_BUS_DEVICE(dev),2,qdev_get_gpio_in(irqchip,LS_POWER_IRQ));
    binding_devices=s;d=s->paper.descriptor;
    d[0]=LEMMA_DESCRIPTOR_MAGIC;d[1]=1;d[2]=256;d[4]=0x80000000;d[5]=128*MiB;
    d[6]=0x82000000;d[7]=32*MiB;d[8]=10000000;
    d[9]=LEMMA_PAPER_BASE;d[10]=4096;d[11]=12;d[12]=LEMMA_PEN_BASE;d[13]=4096;d[14]=13;
    d[15]=0x10001000;d[16]=4096;d[17]=1;d[18]=s->width;d[19]=s->height;d[20]=s->pressure_max;d[21]=3;
    d[22]=0x02000000;d[23]=0x0c000000;d[24]=0x10000000;d[25]=0x00101000;
    d[28]=0x80000000;d[29]=32*MiB;
    if(fast) {d[1]=LS_DESCRIPTOR_ABI;d[6]=LS_FRAME_POOL_BASE;d[7]=LS_FRAME_POOL_BYTES;d[8]=LS_TIMEBASE_HZ;d[25]=LS_POWER_ENABLED?LS_POWER_BASE:0;}
    descriptor_checksum(s);
}
void lemma_binding_add_fdt(MachineState *machine)
{
    uint32_t phandle=qemu_fdt_get_phandle(machine->fdt,"/soc/interrupt-controller@c000000");
    const char *nodes[]={"/soc/lemma-paper@10010000","/soc/lemma-pen@10011000"};
    const char *compat[]={"lemma,paper-v1","lemma,pen-v1"};
    const uint64_t bases[]={LEMMA_PAPER_BASE,LEMMA_PEN_BASE};
    for(unsigned i=0;i<2;i++) {
        qemu_fdt_add_subnode(machine->fdt,nodes[i]);
        qemu_fdt_setprop_string(machine->fdt,nodes[i],"compatible",compat[i]);
        qemu_fdt_setprop_cells(machine->fdt,nodes[i],"reg",0,bases[i],0,4096);
        qemu_fdt_setprop_cell(machine->fdt,nodes[i],"interrupt-parent",phandle);
        qemu_fdt_setprop_cell(machine->fdt,nodes[i],"interrupts",12+i);
        qemu_fdt_setprop_cell(machine->fdt,nodes[i],"lemma,abi-version",1);
    }
    qemu_fdt_setprop_cell(machine->fdt,nodes[0],"lemma,width",binding_devices->width);
    qemu_fdt_setprop_cell(machine->fdt,nodes[0],"lemma,height",binding_devices->height);
    qemu_fdt_setprop_cells(machine->fdt,nodes[0],"lemma,descriptor",0,LEMMA_PAPER_BASE+1024,0,256);
    qemu_fdt_setprop_cell(machine->fdt,nodes[1],"lemma,max-x",65535);
    qemu_fdt_setprop_cell(machine->fdt,nodes[1],"lemma,max-y",65535);
    qemu_fdt_setprop_cell(machine->fdt,nodes[1],"lemma,pressure-max",binding_devices->pressure_max);
}
