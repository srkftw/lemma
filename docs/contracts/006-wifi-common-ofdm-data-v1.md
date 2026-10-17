<!--
# Wi-Fi construction dependency: lemma-wifi-ofdm-data/1

This version admits a bounded common legacy20MHz BPSK/rate1/2 DATA coding and
complex-sample component. It is an executable dependency toward Wi-Fi6, not an
HE PPDU, complete legacy PHY, MAC, connected machine radio, or RF implementation.
Hardwareprofile0.12 is reserved for later coordinated integration; no current
profile, SoC address, target device-region authority or runtime is changed.

## Public authority and mandatory/optional scope

The final [IEEE802.11ax-2021 catalog](https://standards.ieee.org/ieee/802.11ax/7180/)
was identified; final normative text was not obtained. The public
[TGax framework r17](https://mentor.ieee.org/802.11/dcn/15/11-15-0132-17-00ax-spec-framework.docx)
(May25,2016) is explicitly provisional and contains TBD fields. Its proposed
requirements below guide construction only; final mandatory closure is UNKNOWN.
No paid access, account agreement or outreach was used.

| Topic | Public r17 proposed requirement | Current admission |
| --- | --- | --- |
| HE-MCS | One stream MCS0..7 TX/RX mandatory; MCS8..11 optional | None; this component uses common BPSK/r1/2 coding |
| OFDMA/formats | DL/UL OFDMA and SU/MU/ER formats mandatory | None; no HE signaling, RU or trigger implementation |
| BCC/LDPC | BCC for at most4 streams and at most242 tones/20MHz; LDPC required for wider channels or more streams, otherwise optional | Common K7 BCC only; no HE allocation or LDPC |
| MU-MIMO | AP full-band DL TX conditional on TxNss>=4; non-AP full-band RX proposed mandatory | None |
| HE timing/acquisition | Legacy preamble plus HE signaling, channel estimation and specified guard intervals | None; receiver uses predeclared aligned DATA metadata |
| RF/regulatory/MAC/security | Not established by a coding dependency | UNKNOWN/unfinished |

Pinned IEEE primary numerical proposals are 99/107 AnnexE, 99/047r1 interleaver
and98/072r6 OFDM. They are not final standards. AnnexE Tables7/8 provide the
complete24-bit input0x00d064 and48-bit BCC answer0x0e45889f13b0. Its Table15
provides the first16 scrambling bits0x9836 from seed93. The first permutation
is16x3; BPSK's second permutation is identity. Table8 plus that formula yields
0x401d2970b596, corroborated by every visible Table9 entry. Table9 is clipped in
the source PDF. Table10's tone+11 sign conflicts with Table9 bit33=0 and the
Table8 permutation. Original KAT FAIL is retained; Table10 is not silently
normalized or used as a complete normative frequency vector. The historic98
proposal also differs in tail/seed framing, so no complete packet compatibility
claim is derived from it. URL/hash inventories and the visual table observation
are recorded in the companion evidence receipt.

## Component interface and exact state

The circuitry runs on the declared100MHz digital clock, emitting signed16-bit
complex Q14 I/Q with one valid strobe every5 clocks (20Msample/s), including
symbol boundaries. Each symbol has a16-sample cyclic prefix and64-point integer
IFFT. Forty-eight data tones are -26..26 excluding DC and pilots -21,-7,+7,+21.
BPSK maps0 to-1 and1 to+1. The pilot sequence skips the SIGNAL polarity and starts
at DATAp1, with base pilot signs(+,+,+,-). Q14 cosine ROM values are nearest
integers to16384*cos(2*pi*k/64), extended by symmetry. Summation is divided by64
with arithmetic floor; the independent numeric bound is1.5LSB, derived from
52 coefficient quantization errors plus one floor error. This numerical bound
is not a clock, physical EVM or RF signoff tolerance.

Local resource policy accepts1..16 payload bytes and appends a reflected IEEE
CRC32 FCS (EDB88320, initial/final allones, least-significant octet/bit first).
SERVICE is16 zero bits, then payload/FCS, six forced-zero BCC tail inputs and
scrambled zero padding to24 input bits/symbol. The seven-bit nonzero scrambling
state advances across the forced tail. K7 BCC emits133octal then171octal; new
input enters registerbit6. The state carries between symbols. Maximum PSDU20
bytes, eight DATA symbols,182 useful terminated Viterbi steps. Padding is not
used to change the known-zero terminal trellis state.

RX arm receives expected payload length and scrambler seed from an upstream
PLCP authority, absent in this version. The first valid sample defines aligned
CP start. There is no preamble acquisition, frequency/timing tracking, channel
estimation, equalization or noisy-channel claim. After acquisition every sample
must arrive exactly5 clocks later; early/late/drop strobes abort. No first sample
within8192 clocks aborts. Dropping the first sample can instead cause pilot/FEC
rejection because acquisition is not implemented. RX performs integer real DFT,
hard decisions, deinterleaving, deterministic64-state Viterbi (ties choose lower
predecessor), traceback from state0, SERVICE/CRC checks, and a local metric limit4.
A clean-code bad FCS must reach CRC rejection, independently of FEC rejection.

One immutable16-byte RX head exists. Overflow preserves its bytes/length;
ACK clears only validity, retaining old bytes until reset or replacement. New
publication wins coincident ACK. New events win coincident W1C. Reset or disabled
power clears all buffers, coding/DFT/trellis/survivor state, sample dividers,
counters, events and head. Explicit cancel/coexistence withdrawal aborts in-flight
TX/RX and preserves the published head. Coexistence arbitration itself is absent.

The leaf PIO interface has10-bit offsets, aligned64-bit accesses only, ready=1,
error for disabled, unknown, wrong-width or invalid-value accesses. No SoC map
is assigned. A rejected access raises fault1/event4 without changing its requested
configuration. Configuration/staging writes while either direction is active
raise fault2. Each TX submit captures its staged bytes privately before CRC.

| Offset | Meaning |
| --- | --- |
| 0/8 | Magic0x31415441444d4657/version1 |
| 16 | Bits0TXactive,1RXactive,2headvalid,3enabled,4coexallow |
| 24/32 | TX length1..16/seed1..127 |
| 40/48 | RX expected length1..16/seed1..127 |
| 56 | Command1TXsubmit,2RXarm,3headACK,4cancel |
| 64 | Events TX1,RX2,error4; W1C bits0..2 |
| 72/80/88 | Last fault/ticks/head length |
| 96/104/112 | TX packets/RX packets/last Viterbi metric |
| 120/128/136 | RX accepted wire samples/TX wire samples/max payload16 |
| 256+8i /512+8i | TX staging/RX retained head octet, i0..15 |

Faults:1badbus,2busy/admission,3cancel/coex,4cadence/timeout,5FEC/trace,
6CRC,7SERVICE,8head overflow,9pilot/internal decode overlap. Last fault is retained
until reset or another fault. Packet counters increment only on completed TX or
verified RX publication. The PIO bus does not inject a semantic success marker.

Private component snapshots preserve complete generated model state, including
TX banks, CRC/scrambler/BCC/pilot, IFFT position/divider, DFT accumulators/last
bins, all trellis metrics/survivors/decoded bits, traceback/descramble phase,
RX/TX buffers, head/events/counters and the pending complex sample between the
two separate endpoints. Six bounded original/private-fork suffixes compare every
clock's raw samples/public observations and the entire final state byte-for-byte.
This is finite component continuation evidence, not public untrusted snapshot
admission, whole-machine checkpoint completeness or QEMU/RTL migration.

## Lean authority and bounded qualification

Codec.lean implements packet CRC, scrambling, BCC, interleaving and selected
DATA-symbol coding state through genuinely checked scalar/bounded folds. The
pure codec uses existing language contracts; it gains no device/runtime authority.
The standalone M-mode development guest generates both payloads in its own RAM,
computes known-answer records and eight DATA coding carries. The exact ELF is
source-lowered/O2/object audited and runs on an unchanged qualified native RTL
core. Host only copies its resulting octets into the two leaf PIO staging ports;
this is not a guest-driven connected radio driver or0.12 integration claim.

Builds use unused outputs,300s bounds/two jobs; component runtime bound30s.
The purecodec guest bound is5M native clocks/120 host seconds. Lake operations
hold build/task006-lake.lock. Primary KAT, independent polynomial/delay/matrix
and floating DFT oracles, two actual endpoint exchanges, descriptor bounds,
correction, CRC/corruption/loss, reset/power/coex, head/IRQ collision and live
coding-state forks are separate observations. Original FAILs remain retained.
No synthesis/STA/DRC/LVS/RF or final Wi-Fi6 normative closure is inferred.
-->
