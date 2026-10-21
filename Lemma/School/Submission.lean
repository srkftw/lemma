import Lean
import Lemma.School.Client
import Lemma.School.Review
import Lemma.School.Digest
import Lemma.Courses.PackageWorkspace
import Lemma.Documents.Ink
import Lemma.Services.Arithmetic.ProtocolV9

/-! Decoder for the exact immutable bytes exported by an ordinary guest.
The read-only interpreter executes the maintained document/workspace validators;
it has no device, filesystem, or guest mutation operations. Admission, durable
commit and human assessment are separate from structural/checker validation. -/
namespace Lemma.School.Submission
open Lean Lemma.Core0.Memory Lemma.Courses Lemma.Documents

def magic : UInt64  :=  0x31425553534d454c
def version : UInt64  :=  1
/-- Version1 remains immutable; version2 raises complete raw chunk capacity. -/
def currentVersion : UInt64 := 2
def maximumChunks (wireVersion : UInt64) : UInt64 :=
  if wireVersion == 1 then 8 else if wireVersion == 2 then Ink.maximumEntries else 0
def maximumMetadata (wireVersion : UInt64) : UInt64 :=
  if wireVersion == 1 then 16384 else if wireVersion == 2 then 24576 else 0
def headerBytes : Nat  :=  256
def maximumBytes : Nat  :=  262144
def queuePrefix : UInt64  :=  0x5351000000000000

def word (bytes : ByteArray) (offset : Nat) : Except String UInt64  :=  do
  if offset + 8 > bytes.size then throw "submission word exceeds immutable artifact"
  return (List.range 8).foldl (fun value i => value |||
    (bytes[offset+i]!.toUInt64 <<< (i.toUInt64*8))) 0

/-- CRC32/ISO-HDLC receipt checksum, distinct from SHA256 replay identity. -/
def crc32 (bytes : ByteArray) : Nat :=
  ((bytes.data.foldl (fun state byte => PackageFormat.crcByte state byte.toUInt64) 0xffffffff) ^^^ 0xffffffff).toNat

private def require (condition : Bool) (message : String) : Except String Unit  := 
  if condition then .ok () else .error message

/-- The depth and each admitted fold are finite. Only actual imported read-only
validators can run; unexpected primitive operations fail closed. The artifact
is mapped at aligned address0, and every access remains inside its exact bytes. -/
private def readOnly (bytes : ByteArray) : Nat → Action → Except String (UInt8 × UInt64)
  | 0, _ => .error "submission validator depth budget exhausted"
  | _fuel+1, .done status value => .ok (status,value)
  | fuel+1, .bind first next => do
      let (status,value) ← readOnly bytes fuel first
      readOnly bytes fuel (next status value)
  | fuel+1, .boundedFoldU64 budget step count initial a b c d next => do
      require (count.toNat <= budget && budget <= 4096) "submission validator fold budget exceeded"
      let mut status : UInt8  :=  0
      let mut value  :=  initial
      for i in [:count.toNat] do
        if status == 0 then
          let result ← readOnly bytes fuel (step i.toUInt32 count value a b c d)
          status  :=  result.1
          value  :=  result.2
      readOnly bytes fuel (next status value)
  | fuel+1, .platform op address _ _ _ _ _ next => do
      if op == .virtualRead64 then
        let value ← word bytes address.toNat
        readOnly bytes fuel (next 0 value)
      else if op == .virtualRead8 then
        require (address.toNat < bytes.size) "submission byte exceeds immutable artifact"
        readOnly bytes fuel (next 0 bytes[address.toNat]!.toUInt64)
      else throw "submission validator requested mutation/device operation"
  | _, _ => .error "submission validator requested unsupported Action"

private def checked (bytes : ByteArray) (action : Action) : Except String UInt64  :=  do
  let (status,value) ← readOnly bytes 1024 action
  require (status == 0) s!"maintained guest validator rejected submission: status{status}"
  return value

private def hex (bytes : ByteArray) : String  := 
  String.ofList <| bytes.data.toList.flatMap fun byte =>
    let digit (n : Nat) : Char  :=  Char.ofNat (if n < 10 then 48+n else 87+n)
    [digit (byte.toNat / 16),digit (byte.toNat % 16)]

structure Chunk where
  object : Nat
  stroke : Nat
  visible : Bool
  offset : Nat
  bytes : Nat
  samples : Nat
  lifecycle : Nat
  deriving Repr, FromJson, ToJson

structure Envelope where
  wireVersion : Nat
  queueObject : Nat
  captureFrontier : Nat
  documentNamespace : Nat
  page : Nat
  documentRevision : Nat
  course : Nat
  edition : Nat
  node : Nat
  packageCRC : Nat
  policy : Nat
  workKind : Nat
  captureTime : Nat
  guestOutcome : Nat
  authority : String
  bindingRecord : Nat
  generation : Nat
  guestDeadline : Nat
  guestSession : Nat
  goal : Nat
  values : Array Nat
  checker : Nat
  domain : Nat
  assumptions : Nat
  budget : Nat
  evidenceRevision : Nat
  guestRequest : Nat
  executionOrigin : Nat
  executionIdentity : Array Nat
  hints : Nat
  documentPolicy : Nat
  documentReviewMode : Nat
  events : Array (Array Nat)
  eventFormat : Nat := 1
  inkIndexBytes : Nat
  inkEditCount : Nat
  inkEditCursor : Nat
  chunks : Array Chunk
  deriving Repr, FromJson, ToJson

/-- Durable remote assistance provenance. A prepared event has uncertain
presentation; raster completion is not panel visibility. -/
structure RemoteExposure where
  documentRevision : Nat
  goal : Nat
  scope : Nat
  requestSequence : Nat
  workObject : Nat
  bindingRecord : Nat
  authority : String
  deriving BEq, Repr, FromJson, ToJson

/-- An advisory local calculation is distinct from checker evidence and remote
assistance. Every row, including an interrupted prepared request, is retained. -/
structure LocalToolExposure where
  documentRevision : Nat
  postRevision : Nat
  goal : Nat
  scope : Nat
  outcome : Nat
  requestSequence : Nat
  serviceIdentity : Nat
  source : Nat
  edition : Nat
  node : Nat
  packageCRC : Nat
  workObject : Nat
  beforeNumerator : Nat
  beforeDenominator : Nat
  afterNumerator : Nat
  afterDenominator : Nat
  session : Nat
  policy : Nat
  deriving BEq, Repr, FromJson, ToJson

structure ParsedEvents where
  ordinary : Array (Array Nat) := #[]
  remote : Array RemoteExposure := #[]
  localTools : Array LocalToolExposure := #[]
  deriving Repr

private def preparedTool (event : LocalToolExposure) : LocalToolExposure :=
  {event with
    scope := 1
    outcome := 0
    postRevision := 0
    afterNumerator := 0
    afterDenominator := 0}

private def authorityHex (words : Array Nat) : String := hex <| Id.run do
  let mut bytes := ByteArray.empty
  for value in words do
    for i in [:8] do bytes := bytes.push ((value >>> (i*8)) % 256).toUInt8
  return bytes

/-- Payload rows are never interpreted as local hints or learner events.
The original raw rows remain in the envelope. -/
def parseDocumentEvents (format : Nat) (rows : Array (Array Nat)) :
    Except String ParsedEvents := do
  require (format == 1 || format == 2 || format == 3) "unsupported document event format"
  require (rows.size <= 64 && rows.all (fun row => row.size == 2 &&
    row.all (· <= 0xffffffffffffffff))) "document event rows exceed bounded word format"
  let mut ordinary := #[]
  let mut remote : Array RemoteExposure := #[]
  let mut localTools : Array LocalToolExposure := #[]
  let mut skip := 0
  for i in [:rows.size] do
    if skip > 0 then skip := skip-1 else
      let row := rows[i]!
      let tag := row[1]!
      if tag % 256 == 7 then
        require (format >= 2 && i+3 < rows.size && (tag >>> 24) % 256 == 4)
          "remote event requires four complete format2 rows"
        let scope := (tag >>> 16) % 256
        let authority := authorityHex #[rows[i+2]![0]!,rows[i+2]![1]!,rows[i+3]![0]!,rows[i+3]![1]!]
        let event : RemoteExposure := {
          documentRevision := row[0]!, goal := (tag >>> 8) % 256,
          scope, requestSequence := tag >>> 32,
          workObject := rows[i+1]![0]!, bindingRecord := rows[i+1]![1]!, authority }
        require (event.documentRevision > 0 && event.goal > 0 && event.goal <= 3 &&
          (scope == 1 || scope == 2) && event.requestSequence > 0 &&
          event.workObject > 0x504b000000000000 && event.workObject <= 0x504b000000000040 &&
          event.bindingRecord > 0 && event.bindingRecord <= 0x7ffffffffffffffe &&
          authority != String.ofList (List.replicate 64 '0')) "remote event context outside admitted format"
        if scope == 2 then
          require (remote.any (fun prior => {prior with scope := 2} == event))
            "remote raster completion lacks its exact prepared event"
        require (!(remote.any (fun prior => prior.authority == event.authority &&
          prior.bindingRecord == event.bindingRecord && prior.requestSequence == event.requestSequence &&
          prior.scope == event.scope))) "duplicate remote event identity"
        remote := remote.push event
        skip := 3
      else if tag % 256 == 8 then
        require (format == 3 && i+7 < rows.size && (tag >>> 24) % 256 == 8)
          "local tool event requires eight complete format3 rows"
        let event : LocalToolExposure := {
          documentRevision := row[0]!, postRevision := rows[i+1]![0]!,
          goal := (tag >>> 8) % 256, scope := (tag >>> 16) % 256,
          outcome := tag >>> 32, requestSequence := rows[i+1]![1]!,
          serviceIdentity := rows[i+2]![0]!, source := rows[i+2]![1]!,
          edition := rows[i+3]![0]!, node := rows[i+3]![1]!,
          packageCRC := rows[i+4]![0]!, workObject := rows[i+4]![1]!,
          beforeNumerator := rows[i+5]![0]!, beforeDenominator := rows[i+5]![1]!,
          afterNumerator := rows[i+6]![0]!, afterDenominator := rows[i+6]![1]!,
          session := rows[i+7]![0]!, policy := rows[i+7]![1]! }
        let knownSource := if event.source == 0 then
            event.edition == 0 && event.node == 0 && event.packageCRC == 0 else
            event.source <= 65535 && event.source != 60000 && event.source != 60001 &&
            event.edition > 0 && event.edition <= 0xffffffff && event.node > 0 &&
            event.node <= 16 && event.packageCRC <= 0xffffffff
        require (event.documentRevision > 0 && event.documentRevision <= 0x7ffffffffffffffe &&
          event.goal == 1 && event.requestSequence > 0 && event.requestSequence <= 0x7ffffffffffffffe &&
          event.serviceIdentity == Lemma.Services.Arithmetic.ProtocolV9.serviceIdentity.toNat &&
          knownSource && event.workObject > 0x504b000000000000 && event.workObject <= 0x504b000000000040 &&
          event.beforeNumerator <= 99 && event.beforeDenominator > 0 && event.beforeDenominator <= 99 &&
          event.session <= 0x7ffffffffffffffe && event.policy <= 0x7ffffffffffffffe &&
          ((event.session == 0) == (event.policy == 0))) "local tool context outside admitted format"
        if event.scope == 1 then
          require (event.outcome == 0 && event.postRevision == 0 &&
            event.afterNumerator == 0 && event.afterDenominator == 0)
            "prepared local tool contains a terminal result"
          require (!(localTools.any (fun prior => prior.requestSequence == event.requestSequence)))
            "duplicate local tool request identity"
        else
          require (localTools.any (fun prior => prior == preparedTool event))
            "local tool terminal lacks its exact prepared event"
          require (!(localTools.any (fun prior => prior.requestSequence == event.requestSequence && prior.scope != 1)))
            "conflicting local tool terminal"
          if event.scope == 2 then
            let same := event.afterNumerator == event.beforeNumerator &&
              event.afterDenominator == event.beforeDenominator
            require (event.documentRevision < 0x7ffffffffffffffe &&
              event.postRevision == event.documentRevision+1 &&
              event.afterNumerator <= 99 && event.afterDenominator > 0 && event.afterDenominator <= 99 &&
              event.outcome == (if same then 2 else 1)) "applied local tool revision/result differs"
          else
            require (event.scope == 3 && event.outcome >= 3 && event.outcome <= 5 &&
              event.postRevision == 0 && event.afterNumerator == 0 && event.afterDenominator == 0)
              "unsupported local tool terminal outcome"
        localTools := localTools.push event
        skip := 7
      else
        require (tag % 256 > 0 && tag % 256 <= 6) "unsupported learner event kind"
        ordinary := ordinary.push row
  return {ordinary,remote,localTools}

/-- The legacy pair-returning API cannot silently drop a format3 calculation.
New admission consumes parseDocumentEvents and all three provenance classes. -/
def parseEvents (format : Nat) (rows : Array (Array Nat)) :
    Except String (Array (Array Nat) × Array RemoteExposure) := do
  require (format == 1 || format == 2) "use parseDocumentEvents for local tool event format3"
  let parsed ← parseDocumentEvents format rows
  return (parsed.ordinary, parsed.remote)

/-- Validate bounded headers and the complete Doc8, including exact typed
results and their original Known/Unknown execution identities. Opaque work is
retained as opaque even when a previous typed checker result remains in Doc8.
All raw chunks, including invisible chunks, are present in index order. -/
def decode (bytes : ByteArray) : Except String Envelope  :=  do
  require (bytes.size >= headerBytes + 3712 + 128 && bytes.size <= maximumBytes)
    "guest submission artifact length outside256..262144-byte envelope"
  let w  :=  word bytes
  let wireVersion ← w 8
  require ((← w 0) == magic && maximumChunks wireVersion > 0 && (← w 16).toNat == bytes.size &&
    (← w 232) == 256 && (← w 240) == PackageWorkspace.bytes) "guest submission header/version/length differs"
  let queue ← w 24
  let frontier ← w 32
  require (frontier < 0xffffffffffff && queue == queuePrefix ||| (frontier+1))
    "guest submission queue identity differs from durable frontier"
  let ns ← w 40
  let page ← w 48
  let revision ← w 56
  let course ← w 64
  let edition ← w 72
  let node ← w 80
  let crc ← w 88
  let policy ← w 96
  let workKind ← w 104
  let captureTime ← w 112
  let outcome ← w 120
  require (course > 0 && course <= 65535 && course != 60000 && course != 60001 &&
    edition > 0 && edition <= 0xffffffff && node > 0 && node <= 16 && crc <= 0xffffffff &&
    policy > 0 && policy <= 0x7ffffffffffffffe && captureTime <= 0x7ffffffffffffffe &&
    (workKind == 1 || workKind == 2)) "guest submission publication/policy/work-kind outside profile"
  require ((← w 128) == 0x314e494f4a484353 && (← w 136) == 1)
    "guest submission lacks admitted school context"
  let authorityBytes  :=  bytes.extract 144 176
  require (!(authorityBytes.data.all (· == 0))) "guest submission empty school authority"
  let binding ← w 176
  let generation ← w 184
  let deadline ← w 192
  let sessionPolicy ← w 200
  let guestSession ← w 208
  require (binding > 0 && binding <= 0x7ffffffffffffffe && generation > 0 &&
    generation <= 0x7ffffffffffffffe && guestSession > 0 && guestSession <= 0x7ffffffffffffffe &&
    deadline <= 0x7ffffffffffffffe && sessionPolicy == policy && (← w 216) == course && (← w 224) == edition)
    "guest submission school context/publication differs"
  let _ ← checked bytes (PackageWorkspace.validate 256 ns page)
  let document  :=  256 + PackageWorkspace.inner.toNat
  require ((← w (document+40)) == revision && (← w (document+96)) == outcome)
    "guest submission document revision/checker outcome differs"
  let goal ← w (document+48)
  let domain ← w (document+120)
  let assumptions ← w (document+128)
  let budget ← w (document+136)
  if workKind == 1 then
    require (((← w (256+48)) &&& 256) == 256) "typed submission has no known selected publication"
    let selection  :=  256+PackageWorkspace.selection.toNat
    require ((← w (selection+16)) == course && (← w (selection+24)) == edition &&
      (← w (selection+32)) == crc && (← w (selection+40)) == node &&
      (← w (selection+120)) == revision && (← w (selection+64)) == goal &&
      (← w (selection+80)) == domain && (← w (selection+88)) == assumptions &&
      (← w (selection+96)) == budget) "typed submission selection is stale or names another task"
  let indexBytes ← w 248
  let index  :=  256+3712
  require (indexBytes >= 128 && indexBytes <= Ink.pageBytes && index+indexBytes.toNat <= bytes.size &&
    index.toUInt64+indexBytes <= maximumMetadata wireVersion)
    "guest submission ink index length outside owned record"
  require ((← w index) == Ink.magic && (← w (index+8)) == 2 && (← w (index+16)) == 2 &&
    (← w (index+24)) == page) "guest submission packed ink index header differs"
  let count ← w (index+32)
  let edits ← w (index+40)
  let cursor ← w (index+48)
  require (count <= maximumChunks wireVersion && edits <= Ink.maximumEdits && cursor <= edits &&
    indexBytes == 128 + count*24 + edits*16) "guest submission packed ink count/length differs"
  for i in [:9] do require ((← w (index+56+i*8)) == 0) "guest submission packed ink reserved field set"
  let mut chunks : Array Chunk  :=  #[]
  let mut offset  :=  index+indexBytes.toNat
  for i in [:count.toNat] do
    let entry  :=  index+128+i*24
    let object ← w entry
    let stroke ← w (entry+8)
    let visible ← w (entry+16)
    require (object > 0x10000 && stroke > 0 && visible <= 1 &&
      !chunks.any (fun chunk => chunk.object == object.toNat)) "guest submission ink identity/visibility differs"
    let length ← checked bytes (Ink.validateChunkHeader offset.toUInt64 page stroke)
    require (offset+length.toNat <= bytes.size) "guest submission raw ink chunk truncated"
    chunks := chunks.push {
      object := object.toNat
      stroke := stroke.toNat
      visible := visible == 1
      offset := offset
      bytes := length.toNat
      samples := (← w (offset+48)).toNat
      lifecycle := (← w (offset+112)).toNat }
    offset  :=  offset+length.toNat
  for i in [:edits.toNat] do
    let entry  :=  index+128+count.toNat*24+i*16
    let kind ← w entry
    let stroke ← w (entry+8)
    require ((kind == 1 || kind == 2) && stroke > 0 && chunks.any (fun chunk => chunk.stroke == stroke.toNat))
      "guest submission ink edit refers to absent stroke"
  require (offset == bytes.size) "guest submission has unreferenced trailing bytes"
  let mut values : Array Nat  :=  #[]
  for i in [:5] do values  :=  values.push (← w (document+56+i*8)).toNat
  let mut identity : Array Nat  :=  #[]
  for i in [:8] do identity  :=  identity.push (← w (document+1920+i*8)).toNat
  let eventCount ← w (document+192)
  let mut events : Array (Array Nat)  :=  #[]
  for i in [:eventCount.toNat] do events  :=  events.push #[(← w (document+832+i*16)).toNat,(← w (document+840+i*16)).toNat]
  let eventFormat := (← w (document+208)).toNat
  let parsed ← parseDocumentEvents eventFormat events
  require (parsed.localTools.all (fun event => event.documentRevision <= revision.toNat &&
    event.postRevision <= revision.toNat)) "local tool refers to a future document revision"
  return {
    wireVersion := wireVersion.toNat
    queueObject := queue.toNat
    captureFrontier := frontier.toNat
    documentNamespace := ns.toNat
    
    page := page.toNat
    documentRevision := revision.toNat
    course := course.toNat
    edition := edition.toNat
    
    node := node.toNat
    packageCRC := crc.toNat
    policy := policy.toNat
    workKind := workKind.toNat
    
    captureTime := captureTime.toNat
    guestOutcome := outcome.toNat
    authority := hex authorityBytes
    
    bindingRecord := binding.toNat
    generation := generation.toNat
    guestDeadline := deadline.toNat
    
    guestSession := guestSession.toNat
    goal := goal.toNat
    values
    
    checker := (← w (document+112)).toNat
    domain := domain.toNat
    assumptions := assumptions.toNat
    
    budget := budget.toNat
    evidenceRevision := (← w (document+104)).toNat
    
    guestRequest := identity[0]!
    executionOrigin := identity[7]!
    executionIdentity := identity
    
    hints := (← w (document+152)).toNat
    documentPolicy := (← w (document+176)).toNat
    
    documentReviewMode := (← w (document+184)).toNat
    events
    eventFormat
    inkIndexBytes := indexBytes.toNat
    
    inkEditCount := edits.toNat
    inkEditCursor := cursor.toNat
    chunks}

/-- Resolve historical provenance without requiring an expired or cancelled
session to become live again. This grants no admission or execution authority. -/
private def remoteContext (state : Lemma.School.State) (actor : String)
    (event : RemoteExposure) : Except String (Client.SessionBinding × Client.GuestAsk) := do
  let row ← (state.records.find? (fun row => row.sequence == event.bindingRecord &&
    row.kind == "session")).toExcept "remote original school binding absent"
  let binding : Client.SessionBinding ← fromJson? row.data
  require (row.actor == actor && binding.actor == actor && binding.school == state.school &&
    binding.bindingRecord == event.bindingRecord && binding.authority == event.authority)
    "remote original principal or authority differs"
  let invitation ← (state.latest "invitation" (toString event.bindingRecord)).toExcept
    "remote original invitation absent"
  let ask : Client.GuestAsk ← Lemma.School.field invitation.data "ask" >>= fromJson?
  require (invitation.actor == actor && ask.session == binding.guestSession &&
    ask.sequence == event.requestSequence && ask.object == event.workObject &&
    ask.revision == event.documentRevision && ask.source == binding.course &&
    ask.edition == binding.revision) "remote event differs from immutable original ASK"
  return (binding,ask)

private def remoteDecision (state : Lemma.School.State) (actor : String)
    (binding : Client.SessionBinding) (ask : Client.GuestAsk) : Option Lemma.School.Record :=
  state.records.find? (fun row => row.kind == "decision" && row.actor == actor &&
    binding.bindingRecord < row.sequence &&
    match Lemma.School.field row.data "input" >>= fromJson? (α := Client.AssistInput) with
    | .ok input => input.school == binding.school && input.actor == binding.actor &&
        input.session == binding.session && input.course == binding.course &&
        input.revision == binding.revision && input.policy == binding.policy &&
        input.generation == binding.generation && input.ask == ask
    | .error _ => false)

/-- Exact old requests remain attributable across reconnect and later edits of
the same work. Other known tasks/objects never acquire this work's exposure.
An unresolved event on the current work remains conservatively uncertain. -/
def remoteAssistance (state : Lemma.School.State) (actor : String) (envelope : Envelope)
    (events : Array RemoteExposure) : Bool × Bool × Array Lemma.School.Record × Array Json := Id.run do
  let mut exposed := false
  let mut uncertain := false
  let mut decisions : Array Lemma.School.Record := #[]
  let mut observations : Array Json := #[]
  for event in events do
    let sameWork := event.workObject == (PackageWorkspace.object envelope.page.toUInt64).toNat &&
      event.documentRevision <= envelope.documentRevision
    let presentation := if event.scope == 1 then "prepared; presentation uncertain" else
      "guest raster routine completed; panel visibility unestablished"
    match remoteContext state actor event with
    | .error reason =>
        exposed := exposed || sameWork
        uncertain := uncertain || sameWork
        observations := observations.push (Lemma.School.object [("event",toJson event),
          ("appliesToCurrentWork",toJson sameWork),("contextMatched",toJson false),
          ("reason",toJson reason),("presentation",toJson presentation)])
    | .ok (binding,ask) =>
        let applies := sameWork && binding.course == envelope.course &&
          binding.revision == envelope.edition && binding.policy == envelope.policy &&
          ask.task_id == envelope.node
        let decision := remoteDecision state actor binding ask
        exposed := exposed || applies
        uncertain := uncertain || (applies && (event.scope == 1 || decision.isNone))
        if applies then
          if let some row := decision then
            if !decisions.any (fun old => old.sequence == row.sequence) then decisions := decisions.push row
        observations := observations.push (Lemma.School.object [("event",toJson event),
          ("appliesToCurrentWork",toJson applies),("contextMatched",toJson true),
          ("decision",toJson (decision.map (·.key))),
          ("presentation",toJson presentation)])
  return (exposed,uncertain,decisions,observations)

/-- Classification consumes the complete immutable event history. A later
cancellation cannot erase an applied result; a prepared request is uncertain
only until its exact no-apply/applied terminal is present. Unknown offline
source context remains conservative on the same document and goal. -/
def localToolAssistance (events : Array LocalToolExposure)
    (page revision course edition node crc policy goal : Nat) : Bool × Bool × Array Json := Id.run do
  let mut exposed := false
  let mut uncertain := false
  let mut observations : Array Json := #[]
  for event in events do
    let known := event.source != 0
    let contextMatches := known && event.source == course && event.edition == edition &&
      event.node == node && event.packageCRC == crc && (event.policy == 0 || event.policy == policy)
    let applies := event.workObject == (PackageWorkspace.object page.toUInt64).toNat &&
      event.documentRevision <= revision && event.postRevision <= revision &&
      (known || event.goal == goal) && (!known || contextMatches)
    let terminal := events.find? (fun later => later.scope != 1 && preparedTool later == preparedTool event)
    let unresolved := event.scope == 1 && terminal.isNone
    let delivered := event.scope == 2
    let potential := unresolved || delivered
    exposed := exposed || (applies && potential)
    uncertain := uncertain || (applies && potential && (unresolved || !known))
    let presentation := if delivered then "local advisory calculation applied; checker invalidated; no proof claim"
      else if unresolved then "prepared local calculation; application uncertain after interruption"
      else if event.scope == 1 then "prepared local calculation has an exact terminal observation"
      else "local calculation terminated without application"
    observations := observations.push (Lemma.School.object [("event",toJson event),
      ("appliesToCurrentWork",toJson applies),("contextMatched",toJson contextMatches),
      ("sourceKnown",toJson known),("unresolvedPrepared",toJson unresolved),
      ("deliveredLocalCalculation",toJson delivered),("presentation",toJson presentation)])
  return (exposed,uncertain,observations)


/-- A durable queue object names one immutable work artifact under its original
joined binding. An exact retry returns its original commit even after a session
expires or a new execution generation begins; fresh admission uses current
principal, enrollment, generation, cancellation and original publication policy.
Neither transport request fields nor the current latest UART reply supply work. -/
def admit (state : Lemma.School.State) (actor : String) (envelope : Envelope)
    (digest : String) (checksum now : Nat) : Except String (Lemma.School.State × Json) := do
  let id := s!"guest.{envelope.bindingRecord}.{envelope.queueObject}"
  if let some prior := state.latest "guest-submission" id then
    require (prior.actor == actor && Lemma.School.optionalStr prior.data "artifact" == digest &&
      Lemma.School.optionalNat prior.data "queueObject" == envelope.queueObject &&
      Lemma.School.optionalNat prior.data "bindingRecord" == envelope.bindingRecord)
      "guest queue identity already committed with different immutable work"
    let fields ← prior.data.getObj?
    return (state,Json.obj (fields.insert "reused" (toJson true)))
  let original ← (state.records.find? (fun row => row.sequence == envelope.bindingRecord && row.kind == "session")).toExcept "original guest school binding absent"
  let binding : Lemma.School.Client.SessionBinding ← fromJson? original.data
  require (binding.actor == actor && binding.school == state.school && binding.authority == envelope.authority &&
    binding.bindingRecord == envelope.bindingRecord && binding.generation == envelope.generation &&
    binding.course == envelope.course && binding.revision == envelope.edition && binding.policy == envelope.policy &&
    binding.guestSession == envelope.guestSession) "guest envelope differs from original actor/publication/session binding"
  let live ← (state.latest "session" binding.session).toExcept "current guest school session absent"
  let current : Lemma.School.Client.SessionBinding ← fromJson? live.data
  require (current == binding && !current.cancelled && current.generation == state.generation && current.expires > now)
    "guest school binding cancelled, replaced, expired or stale"
  require ((state.latest "enrollment" binding.enrollment).any (fun row => !Lemma.School.flag row.data "revoked"))
    "guest learner enrollment revoked or absent"
  let invitation ← (state.latest "invitation" (toString envelope.bindingRecord)).toExcept "original guest invitation absent"
  let ask : Lemma.School.Client.GuestAsk ← Lemma.School.field invitation.data "ask" >>= fromJson?
  require (ask.deadline == envelope.guestDeadline && envelope.captureTime <= envelope.guestDeadline)
    "guest envelope differs from original invitation deadline or was captured after expiry"
  let publication ← (state.latest "publication" s!"{envelope.course}.{envelope.edition}").toExcept "original publication absent"
  require (Lemma.School.optionalNat publication.data "policy" == envelope.policy) "guest original publication policy differs"
  let unit ← Lemma.School.field publication.data "definition" >>= Lemma.School.Authoring.decode
  let activity ← (unit.activities.find? (fun activity => activity.node+1 == envelope.node)).toExcept "guest selected node is not a published activity"
  let goal := match activity.goal with | .fractionAddition => 1 | .binomialSquare => 2 | .unsupported => 3
  require ((envelope.workKind == 1 && goal != 3 && envelope.goal == goal) ||
    (envelope.workKind == 2)) "guest work kind/goal differs from original activity"
  let outcomes := Lemma.Documents.Mathematics.result envelope.goal.toUInt64
    envelope.values[0]!.toUInt64 envelope.values[1]!.toUInt64 envelope.values[2]!.toUInt64
    envelope.values[3]!.toUInt64 envelope.values[4]!.toUInt64 envelope.budget.toUInt64
  let outcome := if envelope.workKind == 2 then 4 else outcomes.toNat
  let currentWork := ask.session == envelope.guestSession && ask.source == envelope.course &&
    ask.edition == envelope.edition && ask.task_id == envelope.node &&
    ask.revision == envelope.documentRevision &&
    ask.object == (PackageWorkspace.object envelope.page.toUInt64).toNat
  let currentDecisions := state.records.filter (fun row => currentWork && row.kind == "decision" &&
    row.actor == actor && binding.bindingRecord < row.sequence &&
    match Lemma.School.field row.data "input" >>= fromJson? (α := Lemma.School.Client.AssistInput) with
    | .ok input => input.school == binding.school && input.actor == binding.actor &&
        input.session == binding.session && input.course == binding.course &&
        input.revision == binding.revision && input.policy == binding.policy &&
        input.generation == binding.generation && input.ask == ask
    | .error _ => false)
  let parsed ← parseDocumentEvents envelope.eventFormat envelope.events
  let ordinaryEvents := parsed.ordinary
  let (remoteExposure,remoteUncertain,historicalDecisions,remoteObservations) :=
    remoteAssistance state actor envelope parsed.remote
  let (toolExposure,toolUncertain,toolObservations) := localToolAssistance parsed.localTools
    envelope.page envelope.documentRevision envelope.course envelope.edition envelope.node
    envelope.packageCRC envelope.policy envelope.goal
  let decisions := historicalDecisions.foldl (fun rows row =>
    if rows.any (fun old => old.sequence == row.sequence) then rows else rows.push row) currentDecisions
  let delivery := state.records.filter (fun row => row.kind == "delivery" &&
    decisions.any (fun decision => Lemma.School.optionalStr row.data "decision" == decision.key))
  let currentHint := ordinaryEvents.any (fun event => event[0]! == envelope.documentRevision && event[1]! % 256 == 2)
  let unknownHint := ordinaryEvents.any (fun event => event[1]! % 256 == 6)
  let assisted := !decisions.isEmpty || currentHint || unknownHint || remoteExposure || toolExposure
  require (!(activity.assessment.independent && assisted)) "guest independent assessment contains assistance exposure"
  let reviewId := Lemma.School.optionalStr invitation.data "reviewId"
  let request := Lemma.School.object [("id",toJson id),("course",toJson envelope.course),
    ("revision",toJson envelope.edition),("activity",toJson activity.id),("reviewId",toJson reviewId),
    ("values",toJson envelope.values),("observationArtifact",toJson digest)]
  Lemma.School.Review.admitResponse state actor request now
  let data := Lemma.School.object [("request",request),("course",toJson envelope.course),("revision",toJson envelope.edition),
    ("activity",toJson activity.id),("policy",toJson envelope.policy),("definition",toJson (Lemma.School.optionalStr publication.data "artifact")),
    ("assisted",toJson assisted),("independent",toJson activity.assessment.independent),("outcome",toJson outcome),
    ("checker",toJson activity.assessment.checker),("checkingScope",toJson (if envelope.workKind == 2 then
      "opaque original guest work; human review required; no handwriting/proof interpretation" else
      "hosted exact check of immutable typed Doc8 fields; original guest result/execution retained separately")),
    ("origin",toJson "immutable guest submission envelope/1"),("guestEnvelope",toJson envelope),
    ("assistanceDecisions",toJson decisions),("deliveryObservations",toJson delivery),
    ("localHintExposure",toJson currentHint),("legacyHintExposureUnknown",toJson unknownHint),
    ("remoteAssistance",toJson remoteObservations),("remoteCurrentWorkExposure",toJson remoteExposure),
    ("remotePresentationUncertain",toJson remoteUncertain),
    ("localToolObservations",toJson toolObservations),("localToolCurrentWorkExposure",toJson toolExposure),
    ("localToolApplicationUncertain",toJson toolUncertain),
    ("localToolScope",toJson "local advisory calculation; distinct from remote assistance and checked correctness"),
    ("assistanceScope",toJson "conservative exposure flag; decision and transport acknowledgement alone do not establish visible presentation"),
    ("estimate",toJson "uncertain; no educational-effect claim")]
  let refs := publication.artifacts.push digest
  let next ← state.add "attempt" id actor now data refs
  let next ← Lemma.School.Review.linkResponse next actor request now outcome
  let next ← next.add "review" id actor now (Lemma.School.object [("learner",toJson actor),
    ("course",toJson envelope.course),("revision",toJson envelope.edition),("activity",toJson unit.review.activityId),
    ("sourceAttempt",toJson id),("reviewPolicy",toJson unit.review.version),("policy",toJson envelope.policy),
    ("due",toJson (now+unit.review.delaySeconds*1000)),("assisted",toJson assisted),
    ("recommendation",toJson (if assisted || outcome != 1 then "practice" else "later independent review")),
    ("status",toJson "due"),("disabled",toJson false)]) refs
  let receipt := Lemma.School.object [("attempt",toJson id),("queueObject",toJson envelope.queueObject),
    ("bindingRecord",toJson envelope.bindingRecord),("artifact",toJson digest),("envelopeCRC32",toJson checksum),
    ("commitSequence",toJson (next.records.size+1)),("documentRevision",toJson envelope.documentRevision),
    ("course",toJson envelope.course),("edition",toJson envelope.edition),("policy",toJson envelope.policy),
    ("outcome",toJson outcome),("reused",toJson false)]
  let next ← next.add "guest-submission" id actor now receipt #[digest]
  return (next,receipt)

end Lemma.School.Submission
