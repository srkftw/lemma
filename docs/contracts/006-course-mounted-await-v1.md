<!--+# Completion-driven course mount readiness

`lemma-course-mounted-await/1` is an additive guest protocol in
`PackageAwaitProtocol.lean`, `PackageAwaitClient.lean` and
`Store/ServerAwait.lean`. Its operation16/wire version2 is separate from
historical Store status8 and recovery14/15. All historical Store, kernel,
compiler and Notebook definitions retain their behavior. Its new root has
passed component qualification; selecting and booting it in a full machine
remains required.

The request is64 copied bytes: Store magic, version2, operation16, namespace,
object0, initializer flag0/1, reserved0, reserved0. Existing endpoint Call grants
and kernel-stamped full sender/reply handles remain the authority. Initializer1
is accepted only by the kernel-selected initializing Store deployment. It waits
through unformatted mode2; it never formats a medium or grants that permission.
Ordinary callers receive Unformatted221. Unknown mandatory wire versions return
Unsupported222, malformed shapes return220 and a full queue returns Busy231.

The Store retains at most four private48-byte rows: real reply handle, full
sender, namespace, initializer flag, bounded lease deadline and full Store
identity. Rows occupy state512..703; the four-bit occupancy mask is state496.
Publication writes row ownership before its reply/mask. The declared root
explicitly zeroes its complete private state before starting the ordinary guest
mount. No unvalidated root candidate, admitted request, pending READ or timer
sleep produces Ready.

After the unchanged engine/settlement/staging prefix, a successful response
requires Engine operation0, Store mode1, read-only latch0 and a positive root
generation from the validated mount. The64-byte response is magic/version2/
operation16/namespace/object0/actual sequence/mode/actual root generation. The
client requires the exact128-byte kernel envelope, original request ID, reply
kind, nonzero authenticated sender, reply handle0, namespace, operation and
bounded sequence/generation. Success identifies a mounted writable Store. It
does not create Installed, Saved or another durability receipt, nor reserve
the Store against later concurrent operations.

The positive root generation is medium identity, not an authentication or
device/session epoch. Every waiter also binds the service's full identity; a
different service lifetime cannot use its row. Real kernel handles enforce
transaction/generation ownership. Caller death, revocation and cancellation
invalidate the reply grant; those terminal reply errors clear the row without
publishing success. Reset starts a new kernel/service lifetime and zero rows.
Same-backend observational checkpoints retain guest RAM rows and kernel
transactions; no host pointer, drain or completion is added.

Both IPC and retained-row leases are bounded to300000000 ticks at the declared
10MHz timebase. Kernel deadlines independently wake the caller. A new waiter
may reclaim an expired row; terminal kernel reply errors remain errors. Pending
mounts do not walk the rows, issue another readiness RPC or add a per-sector
100ms sleep. The actual block completion/IRQ and Store engine remain responsible
for mount progress. The original Store block-pending1ms policy is unchanged.
`pollCall` leaves wouldBlock unconsumed. `cancel` consumes the terminal handle
once and discards even a Ready reply already accepted by the kernel.

```sh
nix develop --no-write-lock-file --command python3 scripts/check_course_await.py \
  --output-dir build/courses/course-await-new
```

The retained component has68 complete source inputs and278 genuinely checked
User2 functions. Real imported Actions exercise queue ownership, pending and
published states, unformatted/read-only roots, initializer admission, lease
reuse, service identity, revocation, client framing and cancellation. Eleven
independent literal envelope/reference mutations reject. LLVM O2 and a real
RV64IM object pass with only the declared syscall bridge unresolved. This does
not establish CPU execution, a completed guest mount or new cold Ready/Load.

The separately retained startup2 cold run failed at the original60-million-
cycle Ready boundary in189.700s. It completed23 reads and issued3 status RPCs,
versus7 reads/11 RPCs in the earlier1ms failure. It was still mounting its final
header; no Load was admitted and no write/barrier occurred. Those failures
remain failures, and operation counts are not a causal processor timing proof.
Full image audits and the unchanged60M Ready/100M-per-Load checks remain required
before this new readiness path qualifies connected package loading.
-->
