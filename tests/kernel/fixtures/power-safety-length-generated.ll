; Extracted from genuine PowerSafety a4 O2 generated artifact.
; Full LLVM SHA256 67ed6db2028354bd38a407ae90834c0cae2b61de8d2e213842ded07ca4f6ff7f
@switch.table.lemma_kernel_core0_scalar_31 = private unnamed_addr constant [75 x i64] [i64 1, i64 5, i64 4, i64 21, i64 19, i64 21, i64 29, i64 14, i64 16, i64 11, i64 21, i64 21, i64 21, i64 21, i64 21, i64 21, i64 21, i64 21, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 11, i64 4, i64 11, i64 17, i64 8, i64 19, i64 18, i64 12, i64 13, i64 12, i64 12, i64 19, i64 17, i64 15, i64 12, i64 17, i64 11, i64 21, i64 20, i64 16, i64 7, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 15, i64 13, i64 12, i64 30, i64 27, i64 9, i64 20, i64 11, i64 21, i64 25, i64 15, i64 15], align 8
define range(i64 0, 31) i64 @lemma_kernel_core0_scalar_31(i64 %arg0) local_unnamed_addr #1 {
entry:
  %switch.tableidx = add i64 %arg0, -1
  %0 = icmp ult i64 %switch.tableidx, 75
  br i1 %0, label %switch.lookup, label %if.merge.2

switch.lookup:                                    ; preds = %entry
  %switch.gep = getelementptr inbounds nuw [75 x i64], ptr @switch.table.lemma_kernel_core0_scalar_31, i64 0, i64 %switch.tableidx
  %switch.load = load i64, ptr %switch.gep, align 8
  br label %if.merge.2

if.merge.2:                                       ; preds = %entry, %switch.lookup
  %if.result101 = phi i64 [ %switch.load, %switch.lookup ], [ 0, %entry ]
  ret i64 %if.result101
}
