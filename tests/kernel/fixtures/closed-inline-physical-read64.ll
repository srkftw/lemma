; Exact complete preIR guard/result fixture from independently qualified old A5
; target before this optimization; no target execution is inferred from fixture.
define { i64, i64 } @lemma_kernel_access(i64 %arg0) nounwind alwaysinline {
entry:
  %execution.mem.0.alignment-mask.0 = and i64 %arg0, 7
  %execution.mem.0.aligned.1 = icmp eq i64 %execution.mem.0.alignment-mask.0, 0
  br i1 %execution.mem.0.aligned.1, label %execution.mem.0.lookup.1, label %execution.mem.0.misaligned.2
execution.mem.0.misaligned.2:
  br label %execution.mem.0.outcome.0
execution.mem.0.lookup.1:
  %execution.mem.0.above-start.2 = icmp uge i64 %arg0, 2149580800
  br i1 %execution.mem.0.above-start.2, label %execution.mem.0.upper.3, label %execution.mem.0.next.5
execution.mem.0.upper.3:
  %execution.mem.0.below-limit.3 = icmp ule i64 %arg0, 2150629368
  br i1 %execution.mem.0.below-limit.3, label %execution.mem.0.access.4, label %execution.mem.0.next.5
execution.mem.0.access.4:
  %execution.mem.0.pointer.4 = inttoptr i64 %arg0 to ptr
  %execution.mem.0.loaded.5 = load volatile i64, ptr %execution.mem.0.pointer.4, align 8
  br label %execution.mem.0.outcome.0
execution.mem.0.next.5:
  %execution.mem.0.above-start.6 = icmp uge i64 %arg0, 2151677952
  br i1 %execution.mem.0.above-start.6, label %execution.mem.0.upper.6, label %execution.mem.0.next.8
execution.mem.0.upper.6:
  %execution.mem.0.below-limit.7 = icmp ule i64 %arg0, 2152726520
  br i1 %execution.mem.0.below-limit.7, label %execution.mem.0.access.7, label %execution.mem.0.next.8
execution.mem.0.access.7:
  %execution.mem.0.pointer.8 = inttoptr i64 %arg0 to ptr
  %execution.mem.0.loaded.9 = load volatile i64, ptr %execution.mem.0.pointer.8, align 8
  br label %execution.mem.0.outcome.0
execution.mem.0.next.8:
  %execution.mem.0.above-start.10 = icmp uge i64 %arg0, 2152726528
  br i1 %execution.mem.0.above-start.10, label %execution.mem.0.upper.9, label %execution.mem.0.next.11
execution.mem.0.upper.9:
  %execution.mem.0.below-limit.11 = icmp ule i64 %arg0, 2152792056
  br i1 %execution.mem.0.below-limit.11, label %execution.mem.0.access.10, label %execution.mem.0.next.11
execution.mem.0.access.10:
  %execution.mem.0.pointer.12 = inttoptr i64 %arg0 to ptr
  %execution.mem.0.loaded.13 = load volatile i64, ptr %execution.mem.0.pointer.12, align 8
  br label %execution.mem.0.outcome.0
execution.mem.0.next.11:
  %execution.mem.0.above-start.14 = icmp uge i64 %arg0, 2153775104
  br i1 %execution.mem.0.above-start.14, label %execution.mem.0.upper.12, label %execution.mem.0.next.14
execution.mem.0.upper.12:
  %execution.mem.0.below-limit.15 = icmp ule i64 %arg0, 2154823672
  br i1 %execution.mem.0.below-limit.15, label %execution.mem.0.access.13, label %execution.mem.0.next.14
execution.mem.0.access.13:
  %execution.mem.0.pointer.16 = inttoptr i64 %arg0 to ptr
  %execution.mem.0.loaded.17 = load volatile i64, ptr %execution.mem.0.pointer.16, align 8
  br label %execution.mem.0.outcome.0
execution.mem.0.next.14:
  %execution.mem.0.above-start.18 = icmp uge i64 %arg0, 2181038080
  br i1 %execution.mem.0.above-start.18, label %execution.mem.0.upper.15, label %execution.mem.0.next.17
execution.mem.0.upper.15:
  %execution.mem.0.below-limit.19 = icmp ule i64 %arg0, 2214592504
  br i1 %execution.mem.0.below-limit.19, label %execution.mem.0.access.16, label %execution.mem.0.next.17
execution.mem.0.access.16:
  %execution.mem.0.pointer.20 = inttoptr i64 %arg0 to ptr
  %execution.mem.0.loaded.21 = load volatile i64, ptr %execution.mem.0.pointer.20, align 8
  br label %execution.mem.0.outcome.0
execution.mem.0.next.17:
  %execution.mem.0.above-start.22 = icmp uge i64 %arg0, 2279604224
  br i1 %execution.mem.0.above-start.22, label %execution.mem.0.upper.18, label %execution.mem.0.next.20
execution.mem.0.upper.18:
  %execution.mem.0.below-limit.23 = icmp ule i64 %arg0, 2281701368
  br i1 %execution.mem.0.below-limit.23, label %execution.mem.0.access.19, label %execution.mem.0.next.20
execution.mem.0.access.19:
  %execution.mem.0.pointer.24 = inttoptr i64 %arg0 to ptr
  %execution.mem.0.loaded.25 = load volatile i64, ptr %execution.mem.0.pointer.24, align 8
  br label %execution.mem.0.outcome.0
execution.mem.0.next.20:
  br label %execution.mem.0.outcome.0
execution.mem.0.outcome.0:
  %execution.mem.0.status.26 = phi i8 [ 8, %execution.mem.0.misaligned.2 ], [ 0, %execution.mem.0.access.4 ], [ 0, %execution.mem.0.access.7 ], [ 0, %execution.mem.0.access.10 ], [ 0, %execution.mem.0.access.13 ], [ 0, %execution.mem.0.access.16 ], [ 0, %execution.mem.0.access.19 ], [ 7, %execution.mem.0.next.20 ]
  %execution.mem.0.value.27 = phi i64 [ 0, %execution.mem.0.misaligned.2 ], [ %execution.mem.0.loaded.5, %execution.mem.0.access.4 ], [ %execution.mem.0.loaded.9, %execution.mem.0.access.7 ], [ %execution.mem.0.loaded.13, %execution.mem.0.access.10 ], [ %execution.mem.0.loaded.17, %execution.mem.0.access.13 ], [ %execution.mem.0.loaded.21, %execution.mem.0.access.16 ], [ %execution.mem.0.loaded.25, %execution.mem.0.access.19 ], [ 0, %execution.mem.0.next.20 ]
  %action.result.status-word28 = zext i8 %execution.mem.0.status.26 to i64
  %action.result.partial29 = insertvalue { i64, i64 } poison, i64 %action.result.status-word28, 0
  %action.result.complete30 = insertvalue { i64, i64 } %action.result.partial29, i64 %execution.mem.0.value.27, 1
  ret { i64, i64 } %action.result.complete30
}
