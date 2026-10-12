// Host-only C ABI for the shared C++ byte-I/O boundary. Never a target header.
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct LemmaBackingState {
  uint64_t next_id,completed,durable_barrier,observed_write,phase,poisoned;
} LemmaBackingState;
typedef struct LemmaBackingOutcome { uint64_t transferred,error; } LemmaBackingOutcome;
void *lemma_backing_create(int borrowed_fd,const char *client,const char *socket,
  const char *state,const char *writer,const char *helper,const char *capture,
  const char *identity,char *error,size_t error_bytes);
void lemma_backing_destroy(void *backing);
int lemma_backing_execute(void *backing,uint64_t kind,uint64_t boundary,
  uint64_t offset,uint64_t length,uint8_t *bytes,LemmaBackingOutcome *out,
  char *error,size_t error_bytes);
int lemma_backing_passive(void *backing,uint64_t offset,uint64_t length,
  uint8_t *bytes,char *error,size_t error_bytes);
int lemma_backing_get_state(void *backing,LemmaBackingState *state);
int lemma_backing_capture_checkpoint(void *backing,char *error,size_t error_bytes);
int lemma_backing_export(void *backing,const char *path,char *error,size_t error_bytes);
int lemma_backing_set_state(void *backing,const LemmaBackingState *state,
  char *error,size_t error_bytes);
#ifdef __cplusplus
}
#endif
