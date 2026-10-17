define { i64, i64 } @user_wrapper_core0_action_0(i64 %arg0) nounwind alwaysinline {
entry:
  %execution.mem.0.alignment-mask.0 = and i64 %arg0, 7
  %execution.mem.0.aligned.1 = icmp eq i64 %execution.mem.0.alignment-mask.0, 0
  br i1 %execution.mem.0.aligned.1, label %execution.mem.0.lookup.1, label %execution.mem.0.misaligned.2
execution.mem.0.misaligned.2:
  br label %execution.mem.0.outcome.0
execution.mem.0.lookup.1:
  %execution.mem.0.above-start.2 = icmp uge i64 %arg0, 65536
  br i1 %execution.mem.0.above-start.2, label %execution.mem.0.upper.3, label %execution.mem.0.next.5
execution.mem.0.upper.3:
  %execution.mem.0.below-limit.3 = icmp ule i64 %arg0, 1073741816
  br i1 %execution.mem.0.below-limit.3, label %execution.mem.0.access.4, label %execution.mem.0.next.5
execution.mem.0.access.4:
  %execution.mem.0.pointer.4 = inttoptr i64 %arg0 to ptr
  %execution.mem.0.loaded.5 = load volatile i64, ptr %execution.mem.0.pointer.4, align 8
  br label %execution.mem.0.outcome.0
execution.mem.0.next.5:
  br label %execution.mem.0.outcome.0
execution.mem.0.outcome.0:
  %execution.mem.0.status.6 = phi i8 [ 8, %execution.mem.0.misaligned.2 ], [ 0, %execution.mem.0.access.4 ], [ 7, %execution.mem.0.next.5 ]
  %execution.mem.0.value.7 = phi i64 [ 0, %execution.mem.0.misaligned.2 ], [ %execution.mem.0.loaded.5, %execution.mem.0.access.4 ], [ 0, %execution.mem.0.next.5 ]
  %action.result.status-word8 = zext i8 %execution.mem.0.status.6 to i64
  %action.result.partial9 = insertvalue { i64, i64 } poison, i64 %action.result.status-word8, 0
  %action.result.complete10 = insertvalue { i64, i64 } %action.result.partial9, i64 %execution.mem.0.value.7, 1
  ret { i64, i64 } %action.result.complete10

}

define { i64, i64 } @user_wrapper_core0_action_2(i64 %arg0, i64 %arg1) nounwind alwaysinline {
entry:
  %execution.mem.0.alignment-mask.0 = and i64 %arg0, 7
  %execution.mem.0.aligned.1 = icmp eq i64 %execution.mem.0.alignment-mask.0, 0
  br i1 %execution.mem.0.aligned.1, label %execution.mem.0.lookup.1, label %execution.mem.0.misaligned.2
execution.mem.0.misaligned.2:
  br label %execution.mem.0.outcome.0
execution.mem.0.lookup.1:
  %execution.mem.0.above-start.2 = icmp uge i64 %arg0, 65536
  br i1 %execution.mem.0.above-start.2, label %execution.mem.0.upper.3, label %execution.mem.0.next.5
execution.mem.0.upper.3:
  %execution.mem.0.below-limit.3 = icmp ule i64 %arg0, 1073741816
  br i1 %execution.mem.0.below-limit.3, label %execution.mem.0.access.4, label %execution.mem.0.next.5
execution.mem.0.access.4:
  %execution.mem.0.pointer.4 = inttoptr i64 %arg0 to ptr
  store volatile i64 %arg1, ptr %execution.mem.0.pointer.4, align 8
  br label %execution.mem.0.outcome.0
execution.mem.0.next.5:
  br label %execution.mem.0.outcome.0
execution.mem.0.outcome.0:
  %execution.mem.0.status.5 = phi i8 [ 8, %execution.mem.0.misaligned.2 ], [ 0, %execution.mem.0.access.4 ], [ 7, %execution.mem.0.next.5 ]
  %execution.mem.0.value.6 = phi i64 [ 0, %execution.mem.0.misaligned.2 ], [ 0, %execution.mem.0.access.4 ], [ 0, %execution.mem.0.next.5 ]
  %action.result.status-word7 = zext i8 %execution.mem.0.status.5 to i64
  %action.result.partial8 = insertvalue { i64, i64 } poison, i64 %action.result.status-word7, 0
  %action.result.complete9 = insertvalue { i64, i64 } %action.result.partial8, i64 %execution.mem.0.value.6, 1
  ret { i64, i64 } %action.result.complete9

}
