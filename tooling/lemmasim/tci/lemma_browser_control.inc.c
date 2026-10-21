/* GPL-2.0-or-later. Host-only bounded browser transport to actual QMP handlers.
 * No instruction, document, recovery, consent, checking or tutor implementation.
 * One request and one stable reply; execution occurs in the real main-loop BH.
 */
#include <emscripten/emscripten.h>
#include <emscripten/heap.h>
#include "qemu/main-loop.h"
#include "qemu/atomic.h"
#include "qapi/qmp-registry.h"
#include "qobject/qdict.h"
#include "qobject/qnum.h"
#include "qobject/qjson.h"
#include "system/system.h"
#include "hw/core/cpu.h"
extern QmpCommandList qmp_commands;
static QemuMutex lemma_browser_lock;
static bool lemma_browser_initialized;
static unsigned lemma_browser_state;
static uint64_t lemma_browser_last_id;
static char *lemma_browser_request,*lemma_browser_response;
static QDict *lemma_browser_error(const char *message)
{
 Error *err=NULL;error_setg(&err,"%s",message);return qmp_error_response(err);
}
static bool lemma_browser_allowed(QDict *request)
{
 const char *name=qdict_get_try_str(request,"execute");
 if(!name)return false;
 if(!strcmp(name,"stop")||!strcmp(name,"cont")||!strcmp(name,"query-status")||!strcmp(name,"system_reset"))return true;
 QDict *args=qdict_get_qdict(request,"arguments");if(!args)return false;
 if(!strcmp(name,"qom-get")||!strcmp(name,"qom-set")||!strcmp(name,"qom-list")){
  const char *path=qdict_get_try_str(args,"path");
  if(path&&!strcmp(path,"/machine/lemma-hardware"))return true;
  const char *property=qdict_get_try_str(args,"property");
  return path&&!strcmp(path,"/machine/lemma-block")&&property&&((!strcmp(name,"qom-get")&&(!strcmp(property,"storage-state")||!strcmp(property,"trace-state")))||(!strcmp(name,"qom-set")&&!strcmp(property,"retry-backing")));
 }
 if(!strcmp(name,"pmemsave")){
  const char *file=qdict_get_try_str(args,"filename");uint64_t address,size;
  QNum *a=qobject_to(QNum,qdict_get(args,"val")),*s=qobject_to(QNum,qdict_get(args,"size"));
  return a&&s&&qnum_get_try_uint(a,&address)&&qnum_get_try_uint(s,&size)&&size&&size<=1048576&&address>=0x80000000&&address<=0x88000000-size&&file&&strlen(file)<=64&&g_str_has_prefix(file,"/lab-")&&!strchr(file+1,'/');
 }
 return false;
}
static bool lemma_browser_write_panel(const uint8_t *pixels,size_t bytes)
{
 FILE *f=fopen("/panel.gray4","wb");bool failed=!f;
 if(f){if(fwrite(pixels,1,bytes,f)!=bytes)failed=true;if(fclose(f))failed=true;}
 return !failed;
}
/* BEGIN lemma-qemu-cpu-stop/1: pure direct CPU acknowledgement under BQL. */
static void lemma_browser_cpu_stop_observation(QDict *value)
{
 assert(bql_locked());
 uint64_t count=0,stopped=0;CPUState *cpu;
 CPU_FOREACH(cpu){count++;if(cpu->stopped)stopped++;}
 qdict_put_str(value,"stop_boundary_contract","lemma-qemu-cpu-stop/1");
 qdict_put_int(value,"cpu_count",count);qdict_put_int(value,"cpus_stopped",stopped);
 qdict_put_bool(value,"all_cpus_stopped",count!=0&&count==stopped);
}
/* END lemma-qemu-cpu-stop/1. */
static QDict *lemma_browser_presentation(QDict *request)
{
 const char *name=qdict_get_try_str(request,"execute");
 if(!name||(strcmp(name,"lemma-panel")&&strcmp(name,"lemma-waveform")&&strcmp(name,"lemma-clock")))return NULL;
 QDict *args=qdict_get_qdict(request,"arguments");if(args&&qdict_size(args))return lemma_browser_error("controller presentation commands accept no arguments");
 Object *object=object_resolve_path("/machine/lemma-hardware",NULL);
 if(!object)return lemma_browser_error("hardware presentation unavailable");
 LemmaDevices *s=LEMMA_PAPER_PEN(object);QDict *value=qdict_new();
 uint64_t capture_begin=(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
 if(!strcmp(name,"lemma-clock")){
  lemma_browser_cpu_stop_observation(value);
  uint8_t bytes[8];uint64_t ticks=0;
  if(address_space_read(&address_space_memory,LS_TIMER_MTIME,MEMTXATTRS_UNSPECIFIED,bytes,8)!=MEMTX_OK){qobject_unref(value);return lemma_browser_error("actual pure MTIME observation failed");}
  for(unsigned i=0;i<8;i++)ticks|=(uint64_t)bytes[i]<<(i*8);
  g_autofree char *count=g_strdup_printf("%"PRIu64,ticks),*begin=g_strdup_printf("%"PRIu64,capture_begin);
  qdict_put_str(value,"mtime_ticks",count);qdict_put_str(value,"capture_begin_ns",begin);qdict_put_int(value,"mtime_hz",LS_TIMEBASE_HZ);qdict_put_int(value,"controller_clock_hz",LS_CLOCK_HZ);qdict_put_str(value,"clock_model","qemu-icount8ns/ACLINT-reset-offset/1");qdict_put_int(value,"wasm_heap_bytes",emscripten_get_heap_size());
  g_autofree char *paper_completed=g_strdup_printf("%"PRIu64,s->paper.completed),*paper_accepted=g_strdup_printf("%"PRIu64,s->paper.last_sequence),*paper_status=g_strdup_printf("%"PRIu64,s->paper.status);
  qdict_put_str(value,"paper_completed",paper_completed);qdict_put_str(value,"paper_accepted",paper_accepted);qdict_put_str(value,"paper_status",paper_status);qdict_put_bool(value,"paper_power",s->paper.panel_power);
 }else if(!strcmp(name,"lemma-panel")){
  uint64_t bytes=s->paper.stride*s->paper.height;
  if(!bytes||bytes>8388608){qobject_unref(value);return lemma_browser_error("panel extent outside declared8MiB bound");}
  if(!lemma_browser_write_panel(s->paper.visible,bytes)){qobject_unref(value);return lemma_browser_error("actual panel byte publication failed");}
  qdict_put_str(value,"format","gray4-high-nibble-first/1");qdict_put_str(value,"path","/panel.gray4");qdict_put_int(value,"width",s->paper.width);qdict_put_int(value,"height",s->paper.height);qdict_put_int(value,"stride",s->paper.stride);qdict_put_int(value,"bytes",bytes);
  g_autofree char *sequence=g_strdup_printf("%"PRIu64,s->paper.completed);qdict_put_str(value,"completed",sequence);
 }else{
  if(!s->multimodal_audio||!s->multimodal_audio_path||strcmp(s->multimodal_audio_path,"/audio.bin")||fflush(s->multimodal_audio)){qobject_unref(value);return lemma_browser_error("modeled waveform file unavailable or flush failed");}
  qdict_put_str(value,"format","LMPCM001/mono-s16-low16/1");qdict_put_str(value,"path","/audio.bin");qdict_put_int(value,"source_clock_hz",100000000);
  g_autofree char *consumed=g_strdup_printf("%"PRIu64,s->multimodal.stream[8].consumed),*submitted=g_strdup_printf("%"PRIu64,s->multimodal.stream[8].submitted),*epoch=g_strdup_printf("%"PRIu64,s->multimodal.stream[8].epoch);
  qdict_put_str(value,"consumed",consumed);qdict_put_str(value,"submitted",submitted);qdict_put_str(value,"stream_epoch",epoch);
 }
 g_autofree char *clock=g_strdup_printf("%"PRIu64,(uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));qdict_put_str(value,"capture_ns",clock);if(!strcmp(name,"lemma-clock"))qdict_put_str(value,"virtual_ns",clock);
 QDict *response=qdict_new();qdict_put_obj(response,"return",QOBJECT(value));return response;
}
static void lemma_browser_dispatch(void *unused)
{
 (void)unused;assert(bql_locked());
 qemu_mutex_lock(&lemma_browser_lock);assert(lemma_browser_state==1);lemma_browser_state=2;
 char *text=lemma_browser_request;lemma_browser_request=NULL;qemu_mutex_unlock(&lemma_browser_lock);
 Error *err=NULL;QObject *request=qobject_from_json(text,&err);g_free(text);QDict *response=NULL;
 QDict *dict=qobject_to(QDict,request);uint64_t id=0;QNum *number=dict?qobject_to(QNum,qdict_get(dict,"id")):NULL;
 if(err)response=qmp_error_response(err);
 else if(!dict||!number||!qnum_get_try_uint(number,&id)||!id||id>UINT32_MAX)response=lemma_browser_error("ABI1 requires a monotonic uint32 request id1..4294967295");
 else if(id<=lemma_browser_last_id)response=lemma_browser_error("replayed/stale browser command id");
 else{
  lemma_browser_last_id=id;
  const char *name=qdict_get_try_str(dict,"execute");const QmpCommand *command=name?qmp_find_command(&qmp_commands,name):NULL;
  bool shape=qdict_size(dict)==(qdict_haskey(dict,"arguments")?3:2)&&qdict_haskey(dict,"execute")&&(!qdict_haskey(dict,"arguments")||qdict_get_qdict(dict,"arguments"));
  if(!shape)response=lemma_browser_error("unexpected/malformed browser request members");
  else response=lemma_browser_presentation(dict);
  if(response){}
  else if(!lemma_browser_allowed(dict))response=lemma_browser_error("command/path not admitted by lemma-qemu-wasm-control/1");
  else if(!command||(command->options&QCO_COROUTINE))response=lemma_browser_error("unknown/coroutine browser command unsupported");
  else response=qmp_dispatch(&qmp_commands,request,false,NULL);
 }
 if(!response)response=lemma_browser_error("missing required browser response");
 if(id)qdict_put_int(response,"id",id);
 GString *json=qobject_to_json(QOBJECT(response));qobject_unref(response);qobject_unref(request);
 if(json->len>1048576){g_string_free(json,true);response=lemma_browser_error("browser response exceeds1MiB; no truncated success");if(id)qdict_put_int(response,"id",id);json=qobject_to_json(QOBJECT(response));qobject_unref(response);}
 qemu_mutex_lock(&lemma_browser_lock);lemma_browser_response=g_string_free(json,false);lemma_browser_state=3;qemu_mutex_unlock(&lemma_browser_lock);
}
static void lemma_browser_machine_ready(Notifier *notifier,void *data)
{
 (void)notifier;(void)data;qatomic_set(&lemma_browser_initialized,true);
}
static Notifier lemma_browser_ready_notifier={.notify=lemma_browser_machine_ready};
static void lemma_browser_control_init(void)
{
 qemu_mutex_init(&lemma_browser_lock);qemu_add_machine_init_done_notifier(&lemma_browser_ready_notifier);
}
EMSCRIPTEN_KEEPALIVE const char *lemma_browser_abi(void){return "lemma-qemu-wasm-control/1";}
EMSCRIPTEN_KEEPALIVE int lemma_browser_ready(void){return qatomic_read(&lemma_browser_initialized);}
/* 0 queued;1 busy/unacknowledged;2 malformed/oversized;3 not ready. */
EMSCRIPTEN_KEEPALIVE int lemma_browser_submit(const char *request)
{
 if(!qatomic_read(&lemma_browser_initialized))return 3;
 if(!request||!request[0]||strnlen(request,4097)>4096)return 2;
 qemu_mutex_lock(&lemma_browser_lock);if(lemma_browser_state){qemu_mutex_unlock(&lemma_browser_lock);return 1;}
 lemma_browser_request=g_strdup(request);lemma_browser_state=1;qemu_mutex_unlock(&lemma_browser_lock);
 aio_bh_schedule_oneshot(iohandler_get_aio_context(),lemma_browser_dispatch,NULL);return 0;
}
EMSCRIPTEN_KEEPALIVE const char *lemma_browser_poll(void)
{
 if(!qatomic_read(&lemma_browser_initialized))return NULL;
 qemu_mutex_lock(&lemma_browser_lock);const char *response=lemma_browser_state==3?lemma_browser_response:NULL;qemu_mutex_unlock(&lemma_browser_lock);return response;
}
/* Explicit receipt ACK; does not acknowledge any guest/device event. */
EMSCRIPTEN_KEEPALIVE int lemma_browser_ack(void)
{
 if(!qatomic_read(&lemma_browser_initialized))return 3;
 qemu_mutex_lock(&lemma_browser_lock);if(lemma_browser_state!=3){qemu_mutex_unlock(&lemma_browser_lock);return 1;}
 g_free(lemma_browser_response);lemma_browser_response=NULL;lemma_browser_state=0;qemu_mutex_unlock(&lemma_browser_lock);return 0;
}
