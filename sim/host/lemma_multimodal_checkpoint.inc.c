/* Full digital-controller continuation, separately admitted on the logical
 * translation machine. Host file handles and outputs are never serialized. */
static bool lemma_mm_checkpoint_selected(void)
{
 return !strcmp(object_get_typename(OBJECT(qdev_get_machine())),
                MACHINE_TYPE_NAME("lemma-silicon-fast-softtlb"));
}
static const VMStateDescription lemma_mm_record_vmstate = {
 .name="lemma-mm-record/1", .version_id=1, .minimum_version_id=1,
 .fields=(const VMStateField[]){
  VMSTATE_UINT64(data,LemmaMMRecord),
  VMSTATE_UINT64(capture,LemmaMMRecord),
  VMSTATE_UINT64(available,LemmaMMRecord),
  VMSTATE_UINT64(quality,LemmaMMRecord),
  VMSTATE_UINT64(sequence,LemmaMMRecord),
  VMSTATE_UINT64(epoch,LemmaMMRecord),
  VMSTATE_UINT64(config,LemmaMMRecord),
  VMSTATE_UINT64(selector,LemmaMMRecord),
  VMSTATE_END_OF_LIST()}};
static const VMStateDescription lemma_mm_stream_vmstate = {
 .name="lemma-mm-stream/1", .version_id=1, .minimum_version_id=1,
 .fields=(const VMStateField[]){
  VMSTATE_UINT64(state,LemmaMMStream),
  VMSTATE_UINT64(error,LemmaMMStream),
  VMSTATE_UINT64(epoch,LemmaMMStream),
  VMSTATE_UINT64(sequence,LemmaMMStream),
  VMSTATE_UINT64(gain,LemmaMMStream),
  VMSTATE_UINT64(period,LemmaMMStream),
  VMSTATE_UINT64(exposure,LemmaMMStream),
  VMSTATE_UINT64(selector,LemmaMMStream),
  VMSTATE_UINT64(consent,LemmaMMStream),
  VMSTATE_UINT64(calibration,LemmaMMStream),
  VMSTATE_UINT64(lease,LemmaMMStream),
  VMSTATE_UINT64(quiet,LemmaMMStream),
  VMSTATE_UINT64(consent_floor,LemmaMMStream),
  VMSTATE_UINT64(config,LemmaMMStream),
  VMSTATE_UINT64(next,LemmaMMStream),
  VMSTATE_UINT64(capture,LemmaMMStream),
  VMSTATE_UINT64(available,LemmaMMStream),
  VMSTATE_UINT64(latched_quality,LemmaMMStream),
  VMSTATE_UINT64(latched_reference,LemmaMMStream),
  VMSTATE_UINT64(dma_addr,LemmaMMStream),
  VMSTATE_UINT64(dma_words,LemmaMMStream),
  VMSTATE_UINT64(dma_status,LemmaMMStream),
  VMSTATE_UINT64(consumed,LemmaMMStream),
  VMSTATE_UINT64(submitted,LemmaMMStream),
  VMSTATE_UINT64(start,LemmaMMStream),
  VMSTATE_INT64(input,LemmaMMStream),
  VMSTATE_INT64(reference,LemmaMMStream),
  VMSTATE_INT64(latched,LemmaMMStream),
  VMSTATE_INT64(history,LemmaMMStream),
  VMSTATE_STRUCT_ARRAY(fifo,LemmaMMStream,LEMMA_MM_FIFO,0,lemma_mm_record_vmstate,LemmaMMRecord),
  VMSTATE_UINT64(head,LemmaMMStream),
  VMSTATE_UINT64(count,LemmaMMStream),
  VMSTATE_UINT64(converting,LemmaMMStream),
  VMSTATE_UINT64(source_quality,LemmaMMStream),
  VMSTATE_END_OF_LIST()}};
static const VMStateDescription lemma_mm_model_vmstate = {
 .name="lemma-mm-model/1", .version_id=1, .minimum_version_id=1,
 .fields=(const VMStateField[]){
  VMSTATE_UINT64(tick,LemmaMM),
  VMSTATE_UINT64(mask,LemmaMM),
  VMSTATE_UINT64(inhibit,LemmaMM),
  VMSTATE_UINT64(link,LemmaMM),
  VMSTATE_UINT64(pending,LemmaMM),
  VMSTATE_UINT64(pcm_valid,LemmaMM),
  VMSTATE_UINT64(pcm_data,LemmaMM),
  VMSTATE_UINT64(pcm_position,LemmaMM),
  VMSTATE_UINT64(pcm_tick,LemmaMM),
  VMSTATE_UINT64(dma_stream,LemmaMM),
  VMSTATE_UINT64(dma_index,LemmaMM),
  VMSTATE_UINT64(dma_active,LemmaMM),
  VMSTATE_UINT64(dma_cancel,LemmaMM),
  VMSTATE_STRUCT(dma_record,LemmaMM,0,lemma_mm_record_vmstate,LemmaMMRecord),
  VMSTATE_STRUCT_ARRAY(stream,LemmaMM,LEMMA_MM_STREAMS,0,lemma_mm_stream_vmstate,LemmaMMStream),
  VMSTATE_END_OF_LIST()}};
static int lemma_mm_checkpoint_validate(LemmaDevices *s)
{
 if (!s->multimodal_enabled || !lemma_mm_checkpoint_selected() ||
     !(s->multimodal_controller_abi==2?lemma_mm2_valid(&s->multimodal_v2):lemma_mm_checkpoint_valid(&s->multimodal))) return -EINVAL;
 LemmaMM*core=lemma_mm_core(s);uint64_t next=lemma_mm_next(core);
 if(s->multimodal_controller_abi==2?s->multimodal_v2.bus_kind!=0:core->dma_active)next=MIN(next,core->tick+1);
 if(next>INT64_MAX/10) {
  if(timer_pending(s->multimodal_timer))return -EINVAL;
 } else if(!timer_pending(s->multimodal_timer) ||
           timer_expire_time_ns(s->multimodal_timer)!=(int64_t)(next*10))return -EINVAL;
 return 0;
}
static bool lemma_mm_checkpoint_needed(void *opaque)
{
 LemmaDevices*s=opaque;return s->multimodal_enabled&&s->multimodal_controller_abi==1;
}
static int lemma_mm_checkpoint_post_load(void *opaque,int version)
{
 LemmaDevices *s=opaque;
 if(s->multimodal_controller_abi!=1||lemma_mm_checkpoint_validate(s))return -EINVAL;
 s->multimodal_state_loaded=true;
 /* The migrated PLIC already owns the pending/claimed observation. A saved
  * high converter level is not a new interrupt assertion during loading. */
 return 0;
}
static const VMStateDescription lemma_mm_checkpoint_vmstate = {
 .name="lemma-paper-pen/1/multimodal-v1", .version_id=1, .minimum_version_id=1,
 .needed=lemma_mm_checkpoint_needed, .post_load=lemma_mm_checkpoint_post_load,
 .fields=(const VMStateField[]){
  VMSTATE_STRUCT(multimodal,LemmaDevices,0,lemma_mm_model_vmstate,LemmaMM),
  VMSTATE_TIMER_PTR(multimodal_timer,LemmaDevices),VMSTATE_END_OF_LIST()}};

/* ABI2 includes the immutable outstanding read/record owner, all ring
 * positions and permission stamps. It is never loaded as ABI1 state. */
static const VMStateDescription lemma_mm2_model_vmstate = {
 .name="lemma-mm-model/2",.version_id=2,.minimum_version_id=2,
 .fields=(const VMStateField[]){
  VMSTATE_STRUCT(legacy,LemmaMM2,0,lemma_mm_model_vmstate,LemmaMM),
  VMSTATE_UINT64(base,LemmaMM2),
  VMSTATE_UINT64(capacity,LemmaMM2),
  VMSTATE_UINT64(producer,LemmaMM2),
  VMSTATE_UINT64(fetch,LemmaMM2),
  VMSTATE_UINT64(end,LemmaMM2),
  VMSTATE_UINT64(eof,LemmaMM2),
  VMSTATE_UINT64(enabled,LemmaMM2),
  VMSTATE_UINT64(status,LemmaMM2),
  VMSTATE_UINT64(owner_epoch,LemmaMM2),
  VMSTATE_UINT64(owner_consent,LemmaMM2),
  VMSTATE_UINT64(owner_config,LemmaMM2),
  VMSTATE_UINT64(submitted_base,LemmaMM2),
  VMSTATE_UINT64(consumed_base,LemmaMM2),
  VMSTATE_UINT64(gaps,LemmaMM2),
  VMSTATE_UINT64(bus_kind,LemmaMM2),
  VMSTATE_UINT64(bus_addr,LemmaMM2),
  VMSTATE_UINT64(bus_data,LemmaMM2),
  VMSTATE_UINT64(bus_samples,LemmaMM2),
  VMSTATE_UINT64(bus_cancel,LemmaMM2),
  VMSTATE_UINT64(turn,LemmaMM2),
  VMSTATE_END_OF_LIST()}};
static bool lemma_mm2_checkpoint_needed(void*opaque)
{
 LemmaDevices*s=opaque;return s->multimodal_enabled&&s->multimodal_controller_abi==2;
}
static int lemma_mm2_checkpoint_post_load(void*opaque,int version)
{
 LemmaDevices*s=opaque;
 if(s->multimodal_controller_abi!=2||lemma_mm_checkpoint_validate(s))return -EINVAL;
 s->multimodal_state_loaded=true;return 0;
}
static const VMStateDescription lemma_mm2_checkpoint_vmstate = {
 .name="lemma-paper-pen/1/multimodal-v2",.version_id=2,.minimum_version_id=2,
 .needed=lemma_mm2_checkpoint_needed,.post_load=lemma_mm2_checkpoint_post_load,
 .fields=(const VMStateField[]){
  VMSTATE_STRUCT(multimodal_v2,LemmaDevices,0,lemma_mm2_model_vmstate,LemmaMM2),
  VMSTATE_TIMER_PTR(multimodal_timer,LemmaDevices),VMSTATE_END_OF_LIST()}};
