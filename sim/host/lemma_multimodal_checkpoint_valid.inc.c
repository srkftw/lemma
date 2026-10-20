/* Structural admission of the full controller state. Staged gain/schedule
 * registers intentionally allow all uint64 values accepted by MMIO; their
 * configured/running semantics are checked by the actual controller commands. */
bool lemma_mm_checkpoint_valid(const LemmaMM *m)
{
 if (!m || m->tick > INT64_MAX/10 || m->mask > 511 || m->pending > 511 ||
     m->inhibit > 1 || m->link > 1 || m->pcm_valid > 1 ||
     m->dma_active > 1 || m->dma_cancel > 1 || m->dma_stream >= 8 ||
     m->dma_index > 8 || (m->dma_active && m->dma_index >= 8) ||
     (m->dma_cancel && !m->dma_active)) return false;
 for (unsigned i=0; i<LEMMA_MM_STREAMS; i++) {
  const LemmaMMStream *s=&m->stream[i];
  if (s->state < IDLE || s->state > DISCONNECTED || !s->epoch ||
      s->head >= LEMMA_MM_FIFO || s->count > LEMMA_MM_FIFO ||
      s->converting > 1 || s->calibration > 1 || s->source_quality > 65535 ||
      s->latched_quality > 65535 || s->dma_status > 3 ||
      s->input < INT32_MIN || s->input > INT32_MAX ||
      s->reference < INT32_MIN || s->reference > INT32_MAX ||
      (s->consent && s->consent != s->consent_floor)) return false;
  if (s->error && s->error != BAD_FORMAT && s->error != BAD_RANGE &&
      s->error != STALE && s->error != INVALID_STATE && s->error != BUSY &&
      s->error != PERMISSION && s->error != OVERFLOW && s->error != UNDERRUN &&
      s->error != LINK_LOSS && s->error != CALIBRATION &&
      s->error != EXHAUSTED && s->error != INHIBITED) return false;
  if (s->converting && ((s->state != RUNNING && s->state != DRAINING) ||
      s->available < s->capture)) return false;
  bool owned=m->dma_active && m->dma_stream==i;
  if ((s->dma_status == 1) != owned || (owned && !m->dma_cancel && !s->count)) return false;
 }
 return true;
}
