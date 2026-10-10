/* LemmaSim block-media hardware backend v1. Host only.
 * Ordinary completed writes are volatile. Only flush reaches the stable image.
 * This code does not parse guest records, documents, commits or namespaces.
 * SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/error-report.h"
#include "qemu/module.h"
#include "qemu/option.h"
#include "qemu/iov.h"
#include "qemu/coroutine.h"
#include "qemu/timer.h"
#include "block/block-io.h"
#include "block/block_int.h"

#define SECTOR_BYTES 512
#define MAX_REQUEST_BYTES 65536
typedef struct LemmaSector {
    uint64_t number;
    uint8_t bytes[SECTOR_BYTES];
} LemmaSector;
typedef struct BDRVLemmaDurable {
    GHashTable *pending;
    CoMutex lock;
    uint64_t limit,write_number,flush_number,durable_flush;
    uint64_t fail_write,fail_flush,cut_before_flush,cut_after_flush,tear_flush;
    FILE *trace;
} BDRVLemmaDurable;
static BDRVLemmaDurable *active_medium;
char *lemma_block_state_json(void);
char *lemma_block_state_json(void)
{
    BDRVLemmaDurable *s=active_medium;
    if(!s)return g_strdup("{\"backend\":\"ABSENT\"}");
    return g_strdup_printf("{\"backend\":\"lemma-durable/1\",\"pending_sectors\":%u,\"pending_limit\":%"PRIu64",\"writes\":%"PRIu64",\"flushes\":%"PRIu64",\"durable_flush\":%"PRIu64"}",
        g_hash_table_size(s->pending),s->limit,s->write_number,s->flush_number,s->durable_flush);
}
static void medium_trace(BDRVLemmaDurable *s,const char *event,uint64_t a,uint64_t b)
{
    if(s->trace && (fprintf(s->trace,"%"PRIu64" %s %"PRIu64" %"PRIu64" %u\n",
        (uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),event,a,b,g_hash_table_size(s->pending))<0 || fflush(s->trace))) {
        error_report("LemmaSim media trace write failed");_exit(87);
    }
}
static void medium_cut(BDRVLemmaDurable *s,const char *event)
{
    medium_trace(s,event,s->flush_number,s->durable_flush);
    /* No QEMU cleanup or flush: RAM overlay is physically lost. This is a
     * diagnosed power cut, not an apparently complete record/replay session. */
    _exit(86);
}
static QemuOptsList medium_options={
    .name="lemma-durable",.head=QTAILQ_HEAD_INITIALIZER(medium_options.head),
    .desc={
        {.name="pending-sectors",.type=QEMU_OPT_NUMBER},
        {.name="fail-write",.type=QEMU_OPT_NUMBER},
        {.name="fail-flush",.type=QEMU_OPT_NUMBER},
        {.name="cut-before-flush",.type=QEMU_OPT_NUMBER},
        {.name="cut-after-flush",.type=QEMU_OPT_NUMBER},
        {.name="tear-flush",.type=QEMU_OPT_NUMBER},
        {.name="trace-file",.type=QEMU_OPT_STRING},
        { }
    }
};
static int medium_open(BlockDriverState *bs,QDict *options,int flags,Error **errp)
{
    BDRVLemmaDurable *s=bs->opaque;
    QemuOpts *opts=qemu_opts_create(&medium_options,NULL,0,&error_abort);
    int ret=-EINVAL;
    if(!qemu_opts_absorb_qdict(opts,options,errp))goto end;
    s->limit=qemu_opt_get_number(opts,"pending-sectors",32768);
    s->fail_write=qemu_opt_get_number(opts,"fail-write",0);
    s->fail_flush=qemu_opt_get_number(opts,"fail-flush",0);
    s->cut_before_flush=qemu_opt_get_number(opts,"cut-before-flush",0);
    s->cut_after_flush=qemu_opt_get_number(opts,"cut-after-flush",0);
    s->tear_flush=qemu_opt_get_number(opts,"tear-flush",0);
    if(!s->limit || s->limit>262144 || (flags&BDRV_O_NO_FLUSH)) {
        error_setg(errp,"lemma-durable needs 1..262144 pending sectors and enabled flushes");goto end;
    }
    if(active_medium) {error_setg(errp,"lemmasim-virt/0.1.0 permits one lemma-durable medium");goto end;}
    const char *path=qemu_opt_get(opts,"trace-file");
    if(path && !(s->trace=fopen(path,"wx"))) {
        error_setg(errp,"media trace-file must be a new writable file: %s",strerror(errno));goto end;
    }
    ret=bdrv_open_file_child(NULL,options,"file",bs,errp);
    if(ret<0)goto end;
    BlockDriverState *stable=bs->file->bs;
    if(!stable->drv->format_name || strcmp(stable->drv->format_name,"raw") ||
       !stable->file || !stable->file->bs->drv->protocol_name ||
       strcmp(stable->file->bs->drv->protocol_name,"file") ||
       ((stable->open_flags|stable->file->bs->open_flags)&BDRV_O_NO_FLUSH)) {
        error_setg(errp,"stable medium requires local raw/file graph with enabled flushes");ret=-EINVAL;goto end;
    }
    s->pending=g_hash_table_new_full(g_int64_hash,g_int64_equal,NULL,g_free);
    qemu_co_mutex_init(&s->lock);active_medium=s;
    /* FUA is deliberately not claimed: block core must turn it into a flush. */
    bs->supported_write_flags=BDRV_REQ_WRITE_UNCHANGED;
    medium_trace(s,"medium-open",s->limit,1);
end:
    qemu_opts_del(opts);
    if(ret<0 && s->trace) {fclose(s->trace);s->trace=NULL;}
    return ret;
}
static void medium_close(BlockDriverState *bs)
{
    BDRVLemmaDurable *s=bs->opaque;
    if(active_medium==s)active_medium=NULL;
    if(s->trace) {medium_trace(s,"medium-close",s->write_number,s->durable_flush);fclose(s->trace);}
    if(s->pending)g_hash_table_destroy(s->pending);
    /* Closing does not publish outstanding volatile data. */
}
static int64_t coroutine_fn GRAPH_RDLOCK medium_length(BlockDriverState *bs)
{return bdrv_co_getlength(bs->file->bs);}
static int coroutine_fn GRAPH_RDLOCK medium_check(BlockDriverState *bs,int64_t offset,int64_t bytes)
{
    int64_t length=bdrv_co_getlength(bs->file->bs);
    if(length<0)return length;
    if(offset<0 || bytes<=0 || bytes>MAX_REQUEST_BYTES || offset%512 || bytes%512 || bytes>length || offset>length-bytes)return -EINVAL;
    return 0;
}
static int coroutine_fn GRAPH_RDLOCK medium_read(BlockDriverState *bs,int64_t offset,int64_t bytes,QEMUIOVector *qiov,BdrvRequestFlags flags)
{
    BDRVLemmaDurable *s=bs->opaque;int ret=medium_check(bs,offset,bytes);
    if(ret<0)return ret;
    qemu_co_mutex_lock(&s->lock);
    ret=bdrv_co_preadv(bs->file,offset,bytes,qiov,flags);
    if(!ret)for(int64_t n=0;n<bytes;n+=512) {
        uint64_t sector=(offset+n)/512;
        LemmaSector *v=g_hash_table_lookup(s->pending,&sector);
        if(v)qemu_iovec_from_buf(qiov,n,v->bytes,512);
    }
    qemu_co_mutex_unlock(&s->lock);return ret;
}
static int coroutine_fn GRAPH_RDLOCK medium_write(BlockDriverState *bs,int64_t offset,int64_t bytes,QEMUIOVector *qiov,BdrvRequestFlags flags)
{
    BDRVLemmaDurable *s=bs->opaque;int ret=medium_check(bs,offset,bytes);
    if(ret<0)return ret;
    qemu_co_mutex_lock(&s->lock);
    if(s->write_number==UINT64_MAX) {ret=-EOVERFLOW;goto end;}
    s->write_number++;
    if(s->write_number==s->fail_write) {medium_trace(s,"write-failed",offset,bytes);ret=-EIO;goto end;}
    uint64_t needed=0;
    for(int64_t n=0;n<bytes;n+=512) {
        uint64_t sector=(offset+n)/512;
        if(!g_hash_table_contains(s->pending,&sector))needed++;
    }
    if(needed>s->limit-g_hash_table_size(s->pending)) {ret=-ENOSPC;medium_trace(s,"pending-full",offset,bytes);goto end;}
    /* Capacity is preflighted before exposing any portion of this request. */
    for(int64_t n=0;n<bytes;n+=512) {
        uint64_t sector=(offset+n)/512;
        LemmaSector *v=g_hash_table_lookup(s->pending,&sector);
        if(!v) {v=g_new(LemmaSector,1);v->number=sector;g_hash_table_insert(s->pending,&v->number,v);}
        qemu_iovec_to_buf(qiov,n,v->bytes,512);
    }
    medium_trace(s,"write-volatile",offset,bytes);ret=0;
end:
    qemu_co_mutex_unlock(&s->lock);return ret;
}
static gint sector_order(gconstpointer a,gconstpointer b,gpointer unused)
{
    uint64_t x=**(uint64_t *const *)a,y=**(uint64_t *const *)b;
    return x<y?-1:x>y?1:0;
}
static int coroutine_fn GRAPH_RDLOCK medium_flush(BlockDriverState *bs)
{
    BDRVLemmaDurable *s=bs->opaque;int ret=0;guint count=0;
    qemu_co_mutex_lock(&s->lock);
    if(s->flush_number==UINT64_MAX) {ret=-EOVERFLOW;goto end;}
    s->flush_number++;medium_trace(s,"flush-begin",s->flush_number,s->durable_flush);
    if(s->flush_number==s->cut_before_flush)medium_cut(s,"power-cut-before-flush");
    if(s->flush_number==s->fail_flush) {ret=-EIO;medium_trace(s,"flush-failed",s->flush_number,0);goto end;}
    gpointer *keys=g_hash_table_get_keys_as_array(s->pending,&count);
    if(s->flush_number==s->tear_flush && !count) {
        g_free(keys);ret=-EINVAL;medium_trace(s,"tear-no-pending-sector",s->flush_number,0);goto end;
    }
    g_qsort_with_data(keys,count,sizeof(*keys),sector_order,NULL);
    for(guint i=0;i<count;i++) {
        LemmaSector *v=g_hash_table_lookup(s->pending,keys[i]);
        QEMUIOVector vector;
        uint8_t torn[512];
        if(s->flush_number==s->tear_flush && i==0) {
            qemu_iovec_init_buf(&vector,torn,512);
            ret=bdrv_co_preadv(bs->file,v->number*512,512,&vector,0);
            if(ret<0)break;
            memcpy(torn,v->bytes,256);
            ret=bdrv_co_pwritev(bs->file,v->number*512,512,&vector,0);
            if(ret<0)break;
            ret=bdrv_co_flush(bs->file->bs);
            if(ret<0)break;
            medium_trace(s,"sector-torn-durable",v->number,256);
            medium_cut(s,"power-cut-torn-flush");
        }
        qemu_iovec_init_buf(&vector,v->bytes,512);
        ret=bdrv_co_pwritev(bs->file,v->number*512,512,&vector,0);
        if(ret<0)break;
    }
    g_free(keys);
    if(ret<0) {medium_trace(s,"stable-write-failed",s->flush_number,-ret);goto end;}
    ret=bdrv_co_flush(bs->file->bs);
    if(ret<0) {medium_trace(s,"stable-flush-failed",s->flush_number,-ret);goto end;}
    s->durable_flush=s->flush_number;g_hash_table_remove_all(s->pending);
    medium_trace(s,"flush-durable",s->flush_number,0);
    if(s->flush_number==s->cut_after_flush)medium_cut(s,"power-cut-after-flush");
end:
    qemu_co_mutex_unlock(&s->lock);return ret;
}
static BlockDriver medium_driver={
    .format_name="lemma-durable",.instance_size=sizeof(BDRVLemmaDurable),.is_filter=true,
    .bdrv_open=medium_open,.bdrv_close=medium_close,.bdrv_child_perm=bdrv_default_perms,
    .bdrv_co_getlength=medium_length,.bdrv_co_preadv=medium_read,
    .bdrv_co_pwritev=medium_write,.bdrv_co_flush=medium_flush,
};
static void medium_register(void) {bdrv_register(&medium_driver);}
block_init(medium_register);
