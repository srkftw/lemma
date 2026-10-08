; Audit-regression fixture: both unwanted runtime functions are defined here, so
; a check that only looks for unresolved symbols would miss this dependency.
target datalayout = "e-m:e-p:64:64-i64:64-i128:128-n32:64-S128"
target triple = "riscv64-unknown-unknown-elf"

declare void @core0_io_fence()

define i64 @lemma_forbidden_foreign_runtime(i64 %value) {
entry:
  ret i64 %value
}

define i64 @lean_alloc_object(i64 %value) {
entry:
  call void @core0_io_fence()
  %result = call i64 @lemma_forbidden_foreign_runtime(i64 %value)
  ret i64 %result
}
