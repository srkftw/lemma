/* Timer-driven functional silicon block controller. Host circuitry model only.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * No document, journal, recovery, gesture or guest instruction interpretation. */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/error-report.h"
#include "qemu/timer.h"
#include "hw/core/sysbus.h"
#include "hw/core/boards.h"
#include "hw/core/irq.h"
#include "hw/core/qdev-properties.h"
#include "hw/core/resettable.h"
#include "migration/vmstate.h"
#include "system/address-spaces.h"
#include "system/runstate.h"
#include "companion/backing_c.h"
#include "lemma_silicon_fast.h"
#include <sys/file.h>

#define TYPE_LEMMA_FAST_BLOCK "lemma-fast-block"
#define OVERLAY_SECTORS 32768u
#define SECTOR_BYTES 512u
OBJECT_DECLARE_SIMPLE_TYPE(LemmaFastBlock, LEMMA_FAST_BLOCK)
typedef enum FastPhase { IDLE, AVAIL_INDEX, AVAIL_HEAD, DESC0, DESC1,
    HEADER_KIND, HEADER_SECTOR, WRITE_BUFFER, MEDIUM, READ_BUFFER,
    STATUS_BYTE, USED_ID, USED_LENGTH, USED_INDEX } FastPhase;
struct LemmaFastBlock {
    SysBusDevice parent_obj;
    MemoryRegion mmio;
    qemu_irq irq;
    QEMUTimer *timer;
    char *medium_path,*trace_path;
    char *peer_client,*peer_socket,*peer_state,*peer_writer,*peer_helper,*capture_path,*capture_identity;
    void *backing;
    LemmaBackingState backing_state;
    int fd;
    FILE *trace;
    uint32_t phase,status,feature_sel,driver_sel,driver_low,driver_high;
    uint32_t queue_sel,queue_num,queue_ready,interrupt_status;
    uint64_t desc_base,avail_base,used_base,desc_address,header_address,data_address,status_address,sector;
    uint16_t last_avail,used_index,head_id,desc_id;
    uint32_t chain,kind,word_index;
    uint8_t sector_buffer[512],result;
    uint64_t next_ns,media_deadline,step_ns,capacity_bytes;
    uint64_t writes,flushes,durable_flush;
    uint64_t fail_write,fail_flush,cut_before_flush,cut_after_flush;
    uint64_t delay_after_ns,delay_write_ns;
    bool delay_used,media_started;
    uint32_t pending_count,medium_present;
    uint64_t pending_number[OVERLAY_SECTORS];
    uint8_t pending_bytes[OVERLAY_SECTORS*SECTOR_BYTES];
    GHashTable *pending_index;
    uint8_t medium_digest[32];
    uint64_t trace_limit,trace_rows,trace_omitted;
};
static LemmaFastBlock *active_fast_block;
bool lemma_fast_block_busy(void)
{ return active_fast_block && (active_fast_block->phase!=IDLE || active_fast_block->interrupt_status || (active_fast_block->status&64)); }

static void block_irq(LemmaFastBlock *s) { qemu_set_irq(s->irq,s->interrupt_status!=0); }
static void block_trace(LemmaFastBlock *s,const char *event,uint64_t a,uint64_t b) {
    if(!s->trace)return;
    if(s->trace_rows>=s->trace_limit) {
        if(s->trace_omitted<UINT64_MAX)s->trace_omitted++;
        return;
    }
    s->trace_rows++;
    if(fprintf(s->trace,"%"PRIu64" %s %"PRIu64" %"PRIu64" %u\n",
        (uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),event,a,b,s->pending_count)<0) {
        error_report("LemmaSim fast media trace failed");_exit(87);
    }
}
static bool span_ok(uint64_t address,uint64_t bytes) {
    return address>=LS_FRAME_POOL_BASE && bytes<=LS_FRAME_POOL_BYTES &&
        address-LS_FRAME_POOL_BASE<=LS_FRAME_POOL_BYTES-bytes;
}
static bool dma_read(uint64_t address,unsigned bytes,uint64_t *value) {
    uint8_t b[8];*value=0;
    if(!bytes || bytes>8 || address%bytes || !span_ok(address,bytes) ||
       address_space_read(&address_space_memory,address,MEMTXATTRS_UNSPECIFIED,b,bytes)!=MEMTX_OK)return false;
    for(unsigned i=0;i<bytes;i++)*value|=(uint64_t)b[i]<<(8*i);
    return true;
}
static bool dma_write(uint64_t address,unsigned bytes,uint64_t value) {
    uint8_t b[8];
    if(!bytes || bytes>8 || address%bytes || !span_ok(address,bytes))return false;
    for(unsigned i=0;i<bytes;i++)b[i]=value>>(8*i);
    return address_space_write(&address_space_memory,address,MEMTXATTRS_UNSPECIFIED,b,bytes)==MEMTX_OK;
}
static void reject_queue(LemmaFastBlock *s) {
    s->status|=64;s->interrupt_status|=2;s->phase=IDLE;s->media_started=false;
    timer_del(s->timer);block_trace(s,"queue-rejected",s->status,0);block_irq(s);
}
static uint64_t buffer_word(const uint8_t *b) {
    uint64_t v=0;for(unsigned i=0;i<8;i++)v|=(uint64_t)b[i]<<(8*i);return v;
}
static void buffer_put(uint8_t *b,uint64_t v) { for(unsigned i=0;i<8;i++)b[i]=v>>(8*i); }
static bool backing_operation(LemmaFastBlock *s,uint64_t kind,uint64_t offset,uint64_t length,uint8_t *bytes) {
    LemmaBackingOutcome outcome;char error[256];
    if(lemma_backing_execute(s->backing,kind,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),offset,length,bytes,&outcome,error,sizeof error)) {
        lemma_backing_get_state(s->backing,&s->backing_state);
        error_report("LemmaSim backing persistence unresolved: %s",error);
        vm_stop(RUN_STATE_IO_ERROR);return false;
    }
    return !outcome.error && outcome.transferred==length;
}
static bool medium_hash(LemmaFastBlock *s,uint8_t digest[32]) {
    GChecksum *sum=g_checksum_new(G_CHECKSUM_SHA256);g_autofree uint8_t *b=g_malloc(1048576);gsize n=32;char error[256];
    for(uint64_t a=0;a<s->capacity_bytes;a+=1048576) {
        size_t bytes=MIN(UINT64_C(1048576),s->capacity_bytes-a);
        if(lemma_backing_passive(s->backing,a,bytes,b,error,sizeof error)) {g_checksum_free(sum);return false;}
        g_checksum_update(sum,b,bytes);
    }
    g_checksum_get_digest(sum,digest,&n);g_checksum_free(sum);return n==32;
}
static void medium_cut(LemmaFastBlock *s,const char *reason) {
    block_trace(s,reason,s->flushes,s->durable_flush);if(s->trace)fflush(s->trace);_exit(86);
}
static gint medium_sector_order(gconstpointer a,gconstpointer b,gpointer opaque) {
    LemmaFastBlock *s=opaque;uint64_t x=s->pending_number[*(const uint32_t *)a],y=s->pending_number[*(const uint32_t *)b];return x<y?-1:x>y?1:0;
}
static bool medium_operation(LemmaFastBlock *s) {
    if(!s->backing)return false;
    if(s->kind==0) {
        gpointer slot=g_hash_table_lookup(s->pending_index,&s->sector);
        if(slot) {memcpy(s->sector_buffer,s->pending_bytes+(GPOINTER_TO_UINT(slot)-1)*512,512);return true;}
        return backing_operation(s,0,s->sector*512,512,s->sector_buffer);
    }
    if(s->kind==1) {
        if(s->writes==UINT64_MAX)return false;
        s->writes++;
        if(s->writes==s->fail_write) {block_trace(s,"write-failed",s->sector*512,512);return false;}
        gpointer slot=g_hash_table_lookup(s->pending_index,&s->sector);uint32_t i;
        if(slot)i=GPOINTER_TO_UINT(slot)-1;
        else {
            if(s->pending_count==OVERLAY_SECTORS) {block_trace(s,"pending-full",s->sector*512,512);return false;}
            i=s->pending_count++;s->pending_number[i]=s->sector;
            g_hash_table_insert(s->pending_index,&s->pending_number[i],GUINT_TO_POINTER(i+1));
        }
        memcpy(s->pending_bytes+i*512,s->sector_buffer,512);
        block_trace(s,"write-volatile",s->sector*512,512);return true;
    }
    if(s->flushes==UINT64_MAX)return false;
    s->flushes++;block_trace(s,"flush-begin",s->flushes,s->durable_flush);
    if(s->flushes==s->cut_before_flush)medium_cut(s,"power-cut-before-flush");
    if(s->flushes==s->fail_flush) {block_trace(s,"flush-failed",s->flushes,0);return false;}
    /* Stable bytes are a separate external backing. The host barrier must
     * complete before status DMA. Pending bytes survive a failed barrier. */
    g_autofree uint32_t *order=g_new(uint32_t,s->pending_count);
    for(uint32_t i=0;i<s->pending_count;i++)order[i]=i;
    g_qsort_with_data(order,s->pending_count,sizeof(*order),medium_sector_order,s);
    for(uint32_t i=0;i<s->pending_count;i++)
        if(!backing_operation(s,1,s->pending_number[order[i]]*512,512,s->pending_bytes+order[i]*512))return false;
    if(!backing_operation(s,2,0,0,NULL))return false;
    s->durable_flush=s->flushes;s->pending_count=0;g_hash_table_remove_all(s->pending_index);
    block_trace(s,"flush-durable",s->flushes,0);
    if(s->flushes==s->cut_after_flush)medium_cut(s,"power-cut-after-flush");
    return true;
}
static void block_step(void *opaque) {
    LemmaFastBlock *s=opaque;uint64_t v=0;uint32_t length,flags,next;bool ok=true;
    switch(s->phase) {
    case IDLE:return;
    case AVAIL_INDEX:
        ok=dma_read(s->avail_base+2,2,&v);
        if(!ok)break;
        if((uint16_t)v==s->last_avail) {s->phase=IDLE;return;}
        if((uint16_t)v!=(uint16_t)(s->last_avail+1)) {ok=false;break;}
        s->phase=AVAIL_HEAD;break;
    case AVAIL_HEAD:
        ok=dma_read(s->avail_base+4+(s->last_avail%8)*2,2,&v);
        if(!ok || v>=8) {ok=false;break;}
        s->head_id=s->desc_id=v;s->chain=0;s->phase=DESC0;break;
    case DESC0:
        ok=dma_read(s->desc_base+s->desc_id*16,8,&s->desc_address);s->phase=DESC1;break;
    case DESC1:
        ok=dma_read(s->desc_base+s->desc_id*16+8,8,&v);
        length=v;flags=(v>>32)&65535;next=v>>48;
        if(!ok || !span_ok(s->desc_address,s->chain==0?16:(s->kind==4 || s->chain==2?1:512))) {ok=false;break;}
        if(s->chain==0) {
            if(length!=16 || flags!=1 || next>=8 || next==s->head_id) {ok=false;break;}
            s->header_address=s->desc_address;s->desc_id=next;s->phase=HEADER_KIND;
        } else if(s->chain==1 && s->kind!=4) {
            if(length!=512 || flags!=(s->kind==0?3:1) || next>=8 || next==s->desc_id || next==s->head_id) {ok=false;break;}
            s->data_address=s->desc_address;s->desc_id=next;s->chain=2;s->phase=DESC0;
        } else {
            if(length!=1 || flags!=2) {ok=false;break;}
            s->status_address=s->desc_address;s->word_index=0;s->result=0;s->media_started=false;
            s->phase=s->kind==1?WRITE_BUFFER:MEDIUM;
        }break;
    case HEADER_KIND:
        ok=dma_read(s->header_address,8,&v);
        if(!ok || (v!=0 && v!=1 && v!=4)) {ok=false;break;}
        s->kind=v;s->phase=HEADER_SECTOR;break;
    case HEADER_SECTOR:
        ok=dma_read(s->header_address+8,8,&s->sector);
        if(!ok || (s->kind!=4 && s->sector>=s->capacity_bytes/512)) {ok=false;break;}
        s->chain=1;s->phase=DESC0;break;
    case WRITE_BUFFER:
        ok=dma_read(s->data_address+s->word_index*8,8,&v);if(!ok)break;
        buffer_put(s->sector_buffer+s->word_index*8,v);
        if(++s->word_index==64) {s->word_index=0;s->phase=MEDIUM;}break;
    case MEDIUM:
        if(!s->media_started) {
            s->media_started=true;s->media_deadline=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
            if(s->kind==1 && s->delay_write_ns && !s->delay_used && s->media_deadline>=s->delay_after_ns) {
                s->delay_used=true;s->media_deadline+=s->delay_write_ns;
                block_trace(s,"write-delay-begin",s->sector*512,512);
            }
        }
        if((uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)<s->media_deadline) {
            s->next_ns=s->media_deadline;timer_mod_ns(s->timer,s->next_ns);return;
        }
        s->result=medium_operation(s)?0:1;s->word_index=0;
        if(s->backing_state.poisoned) {timer_del(s->timer);return;}
        s->phase=s->kind==0 && !s->result?READ_BUFFER:STATUS_BYTE;break;
    case READ_BUFFER:
        ok=dma_write(s->data_address+s->word_index*8,8,buffer_word(s->sector_buffer+s->word_index*8));
        if(++s->word_index==64) {s->word_index=0;s->phase=STATUS_BYTE;}break;
    case STATUS_BYTE:ok=dma_write(s->status_address,1,s->result);s->phase=USED_ID;break;
    case USED_ID:ok=dma_write(s->used_base+4+(s->used_index%8)*8,4,s->head_id);s->phase=USED_LENGTH;break;
    case USED_LENGTH:ok=dma_write(s->used_base+8+(s->used_index%8)*8,4,s->kind==0?513:1);s->phase=USED_INDEX;break;
    case USED_INDEX:
        ok=dma_write(s->used_base+2,2,(uint16_t)(s->used_index+1));
        if(ok) {s->used_index++;s->last_avail++;s->interrupt_status|=1;s->phase=IDLE;block_irq(s);return;}break;
    default:ok=false;
    }
    if(!ok) {reject_queue(s);return;}
    s->next_ns=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)+s->step_ns;timer_mod_ns(s->timer,s->next_ns);
}
static uint64_t block_read(void *opaque,hwaddr a,unsigned size) {
    LemmaFastBlock *s=opaque;
    if(size!=4 || (a&3))return 0;
    switch(a) {
    case 0:return 0x74726976;case 4:return 2;case 8:return 2;case 12:return 0x4c454d4d;
    case 16:return s->feature_sel==0?512:s->feature_sel==1?1:0;
    case 52:return s->queue_sel==0?8:0;case 68:return s->queue_ready;
    case 96:return s->interrupt_status;case 112:return s->status;
    case 256:return s->capacity_bytes/512;case 260:return (s->capacity_bytes/512)>>32;
    default:return 0;
    }
}
static void block_reset_state(LemmaFastBlock *s) {
    timer_del(s->timer);s->phase=IDLE;s->status=s->queue_ready=s->interrupt_status=0;
    s->driver_low=s->driver_high=s->last_avail=s->used_index=0;s->media_started=false;block_irq(s);
    /* Reset cancels in-flight DMA and preserves volatile external medium. */
}
static void block_write(void *opaque,hwaddr a,uint64_t v,unsigned size) {
    LemmaFastBlock *s=opaque;bool idle=s->phase==IDLE;
    if(size!=4 || (a&3)) {reject_queue(s);return;}
    switch(a) {
    case 20:s->feature_sel=v;return;case 36:s->driver_sel=v;return;
    case 32:if(s->driver_sel==0)s->driver_low=v;else if(s->driver_sel==1)s->driver_high=v;else reject_queue(s);return;
    case 48:if(idle)s->queue_sel=v;else reject_queue(s);return;
    case 56:if(idle && !s->queue_ready && !s->queue_sel && v==8)s->queue_num=8;else reject_queue(s);return;
    case 68:if(idle && !s->queue_sel && v<=1)s->queue_ready=v;else reject_queue(s);return;
    case 100:s->interrupt_status&=~v;block_irq(s);return;
    case 112:
        if(!v)block_reset_state(s);
        else s->status=(v&8) && (s->driver_low!=512 || s->driver_high!=1)?v&~8u:v;
        return;
    case 80:
        if(v || !idle || s->status!=15 || s->queue_ready!=1 || s->queue_num!=8 ||
            (s->desc_base&15) || (s->avail_base&1) || (s->used_base&3) ||
            !span_ok(s->desc_base,128) || !span_ok(s->avail_base,20) || !span_ok(s->used_base,68)) {reject_queue(s);return;}
        s->phase=AVAIL_INDEX;s->next_ns=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)+s->step_ns;timer_mod_ns(s->timer,s->next_ns);return;
    case 128:case 132:case 144:case 148:case 160:case 164: {
        if(!idle || s->queue_ready) {reject_queue(s);return;}
        uint64_t *base=a<144?&s->desc_base:a<160?&s->avail_base:&s->used_base;
        *base=(a&4)?(*base&UINT32_MAX)|(v<<32):(*base&~(uint64_t)UINT32_MAX)|(uint32_t)v;return;
    }
    default:reject_queue(s);
    }
}
static const MemoryRegionOps block_ops={.read=block_read,.write=block_write,.endianness=DEVICE_LITTLE_ENDIAN,
    .valid={.min_access_size=4,.max_access_size=4},.impl={.min_access_size=4,.max_access_size=4}};
static int block_pre_save(void *opaque) {
    LemmaFastBlock *s=opaque;char error[256];
    if(!s->backing)return 0;
    if(lemma_backing_capture_checkpoint(s->backing,error,sizeof error) ||
       lemma_backing_get_state(s->backing,&s->backing_state))return -EIO;
    return medium_hash(s,s->medium_digest)?0:-EIO;
}
static int block_post_load(void *opaque,int version) {
    LemmaFastBlock *s=opaque;uint8_t hash[32];char error[256];
    if(s->backing && lemma_backing_set_state(s->backing,&s->backing_state,error,sizeof error))return -EINVAL;
    if(s->phase>USED_INDEX || s->chain>2 || s->word_index>63 || s->head_id>=8 || s->desc_id>=8 ||
       s->pending_count>OVERLAY_SECTORS || s->step_ns!=100 ||
       (s->backing && (!medium_hash(s,hash) || memcmp(hash,s->medium_digest,32))))return -EINVAL;
    g_hash_table_remove_all(s->pending_index);
    for(uint32_t i=0;i<s->pending_count;i++) {
        if(s->pending_number[i]>=s->capacity_bytes/512 || g_hash_table_contains(s->pending_index,&s->pending_number[i]))return -EINVAL;
        g_hash_table_insert(s->pending_index,&s->pending_number[i],GUINT_TO_POINTER(i+1));
    }
    block_irq(s);return 0;
}
#define B32(f) VMSTATE_UINT32(f,LemmaFastBlock)
#define B64(f) VMSTATE_UINT64(f,LemmaFastBlock)
static const VMStateDescription block_vmstate={.name="lemma-fast-block/2",.version_id=2,.minimum_version_id=2,
    .pre_save=block_pre_save,.post_load=block_post_load,.fields=(const VMStateField[]){
        VMSTATE_UINT64_EQUAL(capacity_bytes,LemmaFastBlock),VMSTATE_UINT32_EQUAL(medium_present,LemmaFastBlock),B64(step_ns),
        B32(phase),B32(status),B32(feature_sel),B32(driver_sel),B32(driver_low),B32(driver_high),B32(queue_sel),B32(queue_num),B32(queue_ready),B32(interrupt_status),
        B64(desc_base),B64(avail_base),B64(used_base),B64(desc_address),B64(header_address),B64(data_address),B64(status_address),B64(sector),
        VMSTATE_UINT16(last_avail,LemmaFastBlock),VMSTATE_UINT16(used_index,LemmaFastBlock),VMSTATE_UINT16(head_id,LemmaFastBlock),VMSTATE_UINT16(desc_id,LemmaFastBlock),
        B32(chain),B32(kind),B32(word_index),VMSTATE_BUFFER(sector_buffer,LemmaFastBlock),VMSTATE_UINT8(result,LemmaFastBlock),
        B64(next_ns),B64(media_deadline),B64(writes),B64(flushes),B64(durable_flush),B64(fail_write),B64(fail_flush),B64(cut_before_flush),B64(cut_after_flush),B64(delay_after_ns),B64(delay_write_ns),
        VMSTATE_BOOL(delay_used,LemmaFastBlock),VMSTATE_BOOL(media_started,LemmaFastBlock),B32(pending_count),
        VMSTATE_UINT64_ARRAY(pending_number,LemmaFastBlock,OVERLAY_SECTORS),VMSTATE_BUFFER(pending_bytes,LemmaFastBlock),VMSTATE_BUFFER(medium_digest,LemmaFastBlock),
        B64(backing_state.next_id),B64(backing_state.completed),B64(backing_state.durable_barrier),
        B64(backing_state.observed_write),B64(backing_state.phase),B64(backing_state.poisoned),
        VMSTATE_TIMER_PTR(timer,LemmaFastBlock),VMSTATE_END_OF_LIST() }};
#undef B32
#undef B64
static void block_reset(Object *obj,ResetType type) {
    LemmaFastBlock *s=LEMMA_FAST_BLOCK(obj);block_reset_state(s);
    s->feature_sel=s->driver_sel=s->queue_sel=s->queue_num=0;
    s->desc_base=s->avail_base=s->used_base=s->desc_address=s->header_address=s->data_address=s->status_address=s->sector=0;
    s->head_id=s->desc_id=s->chain=s->kind=s->word_index=0;s->result=0;memset(s->sector_buffer,0,512);
}
static void block_realize(DeviceState *dev,Error **errp) {
    LemmaFastBlock *s=LEMMA_FAST_BLOCK(dev);struct stat st;
    if(active_fast_block || s->step_ns!=100 || !s->trace_limit || s->trace_limit>1000000 || s->delay_write_ns>10000000000ULL || s->delay_after_ns>3600000000000ULL) {
        error_setg(errp,"invalid or duplicate fast block controller");return;
    }
    if(s->medium_path && s->peer_client) {error_setg(errp,"local and companion backing are mutually exclusive");return;}
    if(s->medium_path) {
        s->fd=open(s->medium_path,O_RDWR|O_CLOEXEC);
        if(s->fd<0 || flock(s->fd,LOCK_EX|LOCK_NB) || fstat(s->fd,&st) || !S_ISREG(st.st_mode) || st.st_size!=268435456) {
            error_setg(errp,"fast medium must be an exclusively owned 256MiB raw regular file: %s",strerror(errno));return;
        }
    }
    if(s->fd>=0 || s->peer_client) {
        char error[256];
        s->backing=lemma_backing_create(s->fd,s->peer_client,s->peer_socket,s->peer_state,s->peer_writer,s->peer_helper,
            s->capture_path,s->capture_identity,error,sizeof error);
        if(!s->backing) {error_setg(errp,"backing initialization: %s",error);return;}
        lemma_backing_get_state(s->backing,&s->backing_state);
    }
    s->capacity_bytes=268435456;s->medium_present=s->backing!=NULL;s->pending_index=g_hash_table_new(g_int64_hash,g_int64_equal);
    s->timer=timer_new_ns(QEMU_CLOCK_VIRTUAL,block_step,s);
    memory_region_init_io(&s->mmio,OBJECT(s),&block_ops,s,"lemma-fast-block-v1",LS_BLOCK_SPAN);
    sysbus_init_mmio(SYS_BUS_DEVICE(s),&s->mmio);sysbus_init_irq(SYS_BUS_DEVICE(s),&s->irq);
    if(s->trace_path && !(s->trace=fopen(s->trace_path,"wx"))) {error_setg(errp,"fast block trace must be new");return;}
    if(s->trace)setvbuf(s->trace,NULL,_IOFBF,65536);
    active_fast_block=s;
}
static void block_finalize(Object *obj) {
    LemmaFastBlock *s=LEMMA_FAST_BLOCK(obj);
    if(active_fast_block==s)active_fast_block=NULL;
    if(s->timer)timer_free(s->timer);
    if(s->pending_index)g_hash_table_destroy(s->pending_index);
    if(s->trace)fclose(s->trace);
    lemma_backing_destroy(s->backing);
    if(s->fd>=0)close(s->fd);
}
static char *block_state(Object *obj,Error **errp) {
    LemmaFastBlock *s=LEMMA_FAST_BLOCK(obj);
    if(s->backing)lemma_backing_get_state(s->backing,&s->backing_state);
    return g_strdup_printf("{\"backend\":\"lemma-fast-block/2\",\"phase\":%u,\"kind\":%u,\"word_index\":%u,\"status\":%u,\"irq\":%u,\"pending_sectors\":%u,\"writes\":%"PRIu64",\"flushes\":%"PRIu64",\"durable_flush\":%"PRIu64",\"deadline_ns\":%"PRIu64",\"media_deadline_ns\":%"PRIu64",\"backing_next_id\":%"PRIu64",\"backing_completed\":%"PRIu64",\"backing_durable_barrier\":%"PRIu64",\"backing_observed_write\":%"PRIu64",\"backing_phase\":%"PRIu64",\"backing_poisoned\":%"PRIu64"}",
        s->phase,s->kind,s->word_index,s->status,s->interrupt_status,s->pending_count,s->writes,s->flushes,s->durable_flush,s->next_ns,s->media_deadline,
        s->backing_state.next_id,s->backing_state.completed,s->backing_state.durable_barrier,s->backing_state.observed_write,s->backing_state.phase,s->backing_state.poisoned);
}
static void block_export(Object *obj,const char *path,Error **errp) {
    LemmaFastBlock *s=LEMMA_FAST_BLOCK(obj);char error[256];
    if(runstate_is_running()) {error_setg(errp,"medium export requires paused execution");return;}
    if(lemma_backing_export(s->backing,path,error,sizeof error))error_setg(errp,"medium export: %s",error);
}
static char *block_trace_state(Object *obj,Error **errp) {
    LemmaFastBlock *s=LEMMA_FAST_BLOCK(obj);
    if(s->trace)fflush(s->trace);
    return g_strdup_printf("{\"rows\":%"PRIu64",\"omitted\":%"PRIu64",\"limit\":%"PRIu64"}",s->trace_rows,s->trace_omitted,s->trace_limit);
}
static const Property block_properties[]={
    DEFINE_PROP_STRING("medium",LemmaFastBlock,medium_path),DEFINE_PROP_STRING("trace-file",LemmaFastBlock,trace_path),
    DEFINE_PROP_STRING("companion-client",LemmaFastBlock,peer_client),DEFINE_PROP_STRING("companion-socket",LemmaFastBlock,peer_socket),
    DEFINE_PROP_STRING("companion-state",LemmaFastBlock,peer_state),DEFINE_PROP_STRING("companion-writer",LemmaFastBlock,peer_writer),
    DEFINE_PROP_STRING("companion-helper",LemmaFastBlock,peer_helper),DEFINE_PROP_STRING("backing-capture",LemmaFastBlock,capture_path),
    DEFINE_PROP_STRING("backing-identity",LemmaFastBlock,capture_identity),
    DEFINE_PROP_UINT64("trace-limit",LemmaFastBlock,trace_limit,1000000),
    DEFINE_PROP_UINT64("step-ns",LemmaFastBlock,step_ns,100),
    DEFINE_PROP_UINT64("fail-write",LemmaFastBlock,fail_write,0),DEFINE_PROP_UINT64("fail-flush",LemmaFastBlock,fail_flush,0),
    DEFINE_PROP_UINT64("cut-before-flush",LemmaFastBlock,cut_before_flush,0),DEFINE_PROP_UINT64("cut-after-flush",LemmaFastBlock,cut_after_flush,0),
    DEFINE_PROP_UINT64("delay-after-ns",LemmaFastBlock,delay_after_ns,0),DEFINE_PROP_UINT64("delay-write-ns",LemmaFastBlock,delay_write_ns,0),
};
static void block_class(ObjectClass *klass,const void *data) {
    DeviceClass *dc=DEVICE_CLASS(klass);ResettableClass *rc=RESETTABLE_CLASS(klass);
    dc->realize=block_realize;dc->vmsd=&block_vmstate;rc->phases.enter=block_reset;
    device_class_set_props(dc,block_properties);object_class_property_add_str(klass,"storage-state",block_state,NULL);
    object_class_property_add_str(klass,"trace-state",block_trace_state,NULL);
    object_class_property_add_str(klass,"export-medium",NULL,block_export);
}
static void fast_block_instance_init(Object *obj) {LEMMA_FAST_BLOCK(obj)->fd=-1;}
static const TypeInfo block_type={.name=TYPE_LEMMA_FAST_BLOCK,.parent=TYPE_SYS_BUS_DEVICE,.instance_size=sizeof(LemmaFastBlock),
    .instance_init=fast_block_instance_init,.instance_finalize=block_finalize,.class_init=block_class};
static void block_register(void) {type_register_static(&block_type);}type_init(block_register)
void lemma_fast_block_create(MachineState *,DeviceState *);
void lemma_fast_block_create(MachineState *machine,DeviceState *irqchip) {
    DeviceState *dev=qdev_new(TYPE_LEMMA_FAST_BLOCK);dev->id=g_strdup("lemma-block");
    object_property_add_child(OBJECT(machine),dev->id,OBJECT(dev));sysbus_realize_and_unref(SYS_BUS_DEVICE(dev),&error_fatal);
    sysbus_mmio_map(SYS_BUS_DEVICE(dev),0,LS_BLOCK_BASE);sysbus_connect_irq(SYS_BUS_DEVICE(dev),0,qdev_get_gpio_in(irqchip,LS_BLOCK_IRQ));
}
