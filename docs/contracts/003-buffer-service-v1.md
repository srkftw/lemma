# Task 003 bounded buffer service v1 — construction design

This is the agreed Gate J interface design. It is not a gate pass, a compiled
artifact report, or a runtime observation. Gate I must pass before the target
implementation starts. The existing capability and copied IPC contracts remain
the authority boundary; the kernel does not implement buffer methods.

## Separately compiled programs and authority

The service configurations contain separately compiled U-mode Buffer Server,
command client, second client, and CPU-bound competitor images. A development
configuration additionally contains the reviewed fault client and a trusted
supervisor restart command. Normal applications use the reusable User syscall,
capability, discovery and IPC libraries.

The command client receives Console rights3 (read/write) and Directory
Discover1024. The second client receives Console Write2 and Directory
Discover1024. The competitor receives no grants. Discovery grants Endpoint
Call16 only. Ordinary clients receive neither management rights nor task or
service restart authority. The Server receives its reviewed Console and
Endpoint Receive grants before activation.

The normal service Entry imports no development command dispatcher, arbitrary
task selector, or restart implementation. A diagnostic command is supervisor
boot authority in a visibly separate development configuration; sending a
similarly numbered ordinary User command grants no such authority.

## One UART input boundary

These configurations use one Lean-authored `KernelInput` reader. They do not
also run `Development.TasksEntry`'s competing UART polling loop. Earlier A–I
entries retain their existing transport routes.

`KernelInput` owns one real owner1/purpose1 frame, allocated and validated by
the guest. The service baseline is therefore497 free frames after the stable
address space, task table, object table and input frame exist. Buffer backing
pages and task/Endpoint resources are additional measured allocations.

The input envelope is exactly8 bytes, little-endian:

| Offset | Field | Value |
| --- | --- | --- |
| 0 | u32 magic | `0x31494d4c` (bytes `LMI1`) |
| 4 | u8 class | 1 ordinary User bytes; 2 development diagnostics |
| 5 | u8 reserved | 0 |
| 6 | u16 payload length | Class-specific bounded length |

Class1 carries at most168 opaque bytes. The usual complete command is40 bytes
of five u64 words followed, for write/append, by at most128 binary bytes. The
kernel does not interpret those command words or bytes. It publishes a complete
validated envelope payload into a bounded512-byte User input ring. Only the
Console Read-granted command client can consume that stream.

Class2 carries exactly40 bytes of diagnostic commands. Normal input rejects
this class before dispatch and has no development dispatcher in its closure.
The development Entry consumes it through a separate bounded diagnostic queue.
Restart is not exposed through a User management syscall.

The frame contains parser metadata, one at-most168-byte pending payload, the
User ring, and one40-byte diagnostic queue. The poller reads at most64 UART bytes
per scheduler step. A complete payload that cannot yet fit its destination is
retained; the poller stops consuming UART until space exists. It does not drop
or partially publish ordinary input. Header bounds and reserved fields are
checked before publication. Console Read validates the full offered User range
before consuming buffered bytes; invalid destinations leave input available.
An empty nonblocking read returns the existing noByte12/count0 result.

## Practical command client and output framing

The ordinary40-byte command is five u64 words:
`(operation, epoch, handle, offset, lengthOrCapacity)`. For write and append,
exactly `lengthOrCapacity` bytes follow and the count is at most128. The command
client implements the parsing and service calls. The transport does not know
Buffer.Create, Buffer.Append, or any other service operation.

The client provides readable help/version and service responses, plus basic
read-only instance/frame information through discovery modes2/3. Binary bytes,
including00/ff and UTF-8 sequences, remain explicit-length data. A development
restart command uses the distinct diagnostic input class; the ordinary client
does not acquire destructive authority.

Each User output is one Console Write of an output envelope and complete
response. Its8-byte header uses u32 magic `0x314f4d4c` (bytes `LMO1`), class1,
reserved0 and u16 payload length. A response payload is at most192 bytes, so the
complete write is at most200 bytes and fits the existing256-byte Console bound.
The command client response uses the same eight application words and read
bytes. In its output-only word7, bits0..31 carry capacity/detail, bits32..39
carry the observed application status, and bits40..47 carry the observed IPC
transport status; bits48..63 are0. This preserves a complete128-byte read
within192 bytes while keeping service and transport errors distinct. The
client checks the original IPC packet before forming this output. Local
commands7(help/version),8(instance count),9(frame count) and10(discovery)
return this framing without invoking a Buffer method.

This magic is distinct from the kernel's88-byte ASCII `K1` records. The host
demultiplexer consumes exact envelope lengths; embedded binary bytes are never
parsed as control records. Kernel records can occur between complete Console
calls, not inside a single nonpreemptible write. Final post-cleanup validation
must cover every retained UART byte, including any drained suffix.

## Buffer request and response protocol

The Buffer application payload begins with eight little-endian u64 words.
The application magic is `0x31524642414d454c`, version1. The maximum application
payload is192 bytes:64 bytes of header plus128 binary bytes. With the existing
IPC64-byte kernel-stamped header, the complete packet is at most256 bytes.

| Word | Request | Response |
| --- | --- | --- |
| 0 | Application magic | Same magic |
| 1 | Version1 | Version1 |
| 2 | Operation | Same operation |
| 3 | Requested service epoch | Current service epoch |
| 4 | Buffer generation/slot handle | Checked resulting handle or0 on error |
| 5 | Offset | Current total buffer length or0 on error |
| 6 | Requested byte count | Actual operation byte count or0 on error |
| 7 | Operation argument | Capacity, or declared error detail |

The kernel IPC header supplies the authenticated full sender descriptor and
request ID. User-supplied application fields cannot substitute for the sender.
Requests and responses must have the exact operation-specific length. Unused
request fields are0. Service failures are the IPC reply's applicationStatus;
transport failures remain distinct syscall/IPC statuses.

| Operation | Request | Successful response |
| --- | --- | --- |
| 1 create | Handle/offset/count0; argument capacity1..4096 | New handle, length0, count0, capacity |
| 2 write | Checked handle, offset, count0..128, argument0; exactly count bytes | Resulting total length and actual count; no reply bytes |
| 3 read | Checked handle, offset, count0..128, argument0; no request bytes | Current total length, exact count and that many reply bytes |
| 4 append | Checked handle, offset0, count0..128, argument0; exactly count bytes | Resulting total length and actual count; no reply bytes |
| 5 status | Checked handle; offset/count/argument0 | Length, count0, capacity |
| 6 destroy | Checked handle; offset/count/argument0 | Handle/length/count/detail0 |

Only read responses append bytes. Other responses are exactly64 bytes even
when their operation count is nonzero. Invalid epoch, handle or owner responses
do not expose another client's length or capacity. Error responses carry0 in
handle/length/count/detail except allocation failure's documented underlying
allocator status in detail.

| applicationStatus | Meaning |
| --- | --- |
| 0 | Success |
| 200 | Wrong service epoch; volatile content is unavailable |
| 201 | Stale, absent or expired buffer generation |
| 202 | Authenticated caller is not the owner |
| 203 | Two-buffer per-client quota |
| 204 | Four-buffer global quota |
| 205 | Capacity, offset, length or overflow bounds |
| 206 | Malformed/version/operation packet |
| 207 | Buffer generation space exhausted |
| 208 | Real User page allocation failed; detail is its actual status |

These are service errors, not additions to the kernel's capability authority.

## Real storage, atomic bounds and leases

The Server has four fixed96-byte metadata rows in its own initialized data/BSS.
Each row contains state, generation, authenticated owner descriptor, capacity,
logical length and lease deadline. Each live row owns one real page obtained
through the existing User page-allocation syscall, at VA `0x40000+slot*4096`.
Creation publishes a live row only after allocation and initialization succeed.
It does not preallocate backing pages or use a host-created array.

There are at most two buffers per authenticated full caller descriptor and
four globally. Capacity is1..4096. A handle is `(generation<<2)|slot`, with
generation1..`2^62-1`; generation never wraps, and an exhausted slot retires.
Epoch is a separate field so a replacement Server cannot reuse an old tuple.
Actual compiled Server text must leave quota for four backing pages:
`16+ceil(textBytes/4096)+4 <= 32` owned pages. Artifact and runtime evidence must
establish this bound rather than assuming it.

Validation order is packet shape/version, epoch, live generation,
authenticated owner, then operation bounds. Write requires offset no greater
than the existing length and count no greater than `capacity-offset`; it may
extend length. Read requires the complete requested range within logical
length. Append checks count against `capacity-length` before writing. Failed
bounds or quota operations change neither bytes nor length nor allocation
inventory. Write/append are all-or-error within their bounded request, with no
silent partial write. A Server crash after application work but before reply
does not create an exactly-once execution guarantee; restart loses volatile
contents.

Every successful owner operation refreshes a fixed10-second lease using actual
time. Addition overflow is rejected before publication. The Server checks all
four rows before each request and on its100ms receive timeout. Expired rows
release their real pages and advance or retire their generation. Another
client cannot renew a lease. A dead client's buffers can remain until expiry;
its own kernel frame reclamation does not reclaim the Server's pages. This
bounded lease policy requires no raw task pointers or unrestricted management
grant. Actual tests must preserve a live client's renewed buffer while the
dead client's pages expire and are reclaimed.

## Discovery, epochs and trusted restart

Syscall26 takes `(DirectoryLocalHandle, mode, serviceID, 0, 0)` and requires a
checked Directory object with Discover1024. Modes0/1 accept serviceID1 only.

| Mode | Result |
| --- | --- |
| 0 | Receiver-local Endpoint Call16-only capability for the current live service |
| 1 | Current service epoch |
| 2 | Read-only active managed-instance count; serviceID0 |
| 3 | Actual `Frames.remaining`; serviceID0 |

Mode0 reuses an existing exact current-key/Call16 entry rather than consuming
serials and references on every lookup. If a new entry cannot be published,
ordinary capacity failure leaves objects, references and serials unchanged.
Modes0/1 validate the generation-tagged live Endpoint, its owner descriptor,
and active registration. An unavailable service returns a declared peer-death
error; it never hands out an unbound endpoint or old object key. Stats expose
counts, not task identities, pointers or mutation authority.

One generic service binding fits the validated Objects frame's reserved words
224..255: binding magicV1, epoch, full Endpoint key and full Server descriptor.
This avoids the Gate I primary key at160. An Endpoint withdrawal clears a
matching published binding before alias invalidation/queue release, preserving
the epoch. Directory imports Capability/Objects/Frames but no Task. The small
binding-withdraw hook lives below Directory so Objects has no import cycle.

Only trusted development Entry restart policy may stop/reap the old Server,
prepare the reviewed Server image with the next epoch, create its Endpoint,
complete grants, activate it and publish the checked binding before returning
to scheduling. Epoch advances only on successful publication; overflow is
rejected before resource effects. Failed preparation cleans its provisional
task and Endpoint. The normal image contains no restart command implementation.

Old pending calls receive existing IPC peer-death/revocation completion. Clients
reconnect through their Directory grant, obtain a fresh attenuated local Call
capability, and observe the larger epoch. An old `(epoch,handle)` is rejected;
new buffers are empty. No reply promises persistence or durable saving.

## Required actual evidence

O0 and O2 must run the same ordinary image with fresh runtime command streams.
Evidence includes two clients' independent buffers,00/ff and UTF-8 data,
128-byte chunk boundaries, quota/overflow/failed-append rollback, foreign-handle
denial, real CPU preemption, and actual fault containment. A surviving client
must read unchanged content while the dead client's lease expires and only
its service-owned pages are released.

The development restart observation must include an actually accepted pending
call failing on Server death, complete old resources reclaimed, epoch increase,
ordinary discovery reconnect, explicit old-handle rejection and a fresh empty
buffer. Repeat ordinary input after these transitions in the same VM to prove
UART progress. Output must bind complete raw transcripts, control records,
binary envelopes, artifact/source/runner hashes, live-before-cleanup state and
actual kill/reap results. A malformed transcript, unexplained suffix, missing
case, timeout or missing evidence is a failure. This design document establishes
none of those observations.
