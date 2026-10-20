"""Closed School25 source and emitted-call admission, separate from execution.

The complete genuine pre/post body authority remains mandatory. These guards
bind only the reviewed mode, owned bounded capture and Console byte producer.
"""
from pathlib import Path
from core0_common import Core0Error
from school_reduction_target import definition,compact

COMPONENTS={'notebook':'Lemma/Applications/Notebook.lean',
            'submission':'Lemma/Courses/SchoolSubmission.lean',
            'stream':'Lemma/Courses/SchoolStream.lean',
            'console':'Lemma/User/Console.lean'}

def require(value,message):
    if not value:raise Core0Error('School25 stream: '+message)


def notebook_source(source):
    from multimodal_target import _lean_without_comments
    source=_lean_without_comments(source)
    exact={
      'schoolStreamFlag':'private def schoolStreamFlag : UInt64 := state + 656',
      'mainMultimodalSchoolV3':'def mainMultimodalSchoolV3 (bootArgument : UInt64) : Action := mainMultimodalConfigured bootArgument 3',
      'configureSchoolMode':'''private def configureSchoolMode (school : UInt64) : Action :=
        if school ≤ 3 then
        .bind (Memory.write64 schoolStreamFlag (if school = 3 then 1 else 0)) fun s _ => if statusFailed s = true then .done s 0 else
        .bind (Memory.write64 schoolActivityFlag (if 2 ≤ school then 1 else school)) fun s _ => if statusFailed s = true then .done s 0 else
        Memory.write64 reductionEnabled (if 2 ≤ school then 1 else 0) else .done 234 0''',
      'multimodalAdvanceInput':'''private def multimodalAdvanceInput : Action :=
        .bind (Memory.read64 schoolStreamFlag) fun s enabled => if statusFailed s = true then .done s 0 else
        if enabled = 1 then multimodalAdvanceCaptured else multimodalRawPump''',
      'multimodalAdvanceCaptured':'''private def multimodalAdvanceCaptured : Action :=
        .boundedFoldU64 8 advance 8 0 0 0 0 0 fun status rounds =>
          if status = Status.iterationStop then .done 0 rounds else .done status rounds
        where
          advance (_ _ : UInt32) (rounds _ _ _ _ : UInt64) : Action :=
            .bind (rawGet 16) fun s before => if statusFailed s = true then .done s 0 else
            if before = 0 then .done Status.iterationStop rounds else
            .bind multimodalRawPump fun s _ => if statusFailed s = true then .done s 0 else
            .bind schoolQueueOwnsIPC fun s queueOwns => if statusFailed s = true then .done s 0 else
            .bind (if queueOwns = 0 then pumpBookmarkSave else .done 0 0) fun s _ =>
              if statusFailed s = true then .done s 0 else
            .bind (rawGet 16) fun s after => if statusFailed s = true then .done s 0 else
            .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
            if before = after then if pending = 0 then .done Status.iterationStop (rounds+1)
              else .done 0 (rounds+1) else .done 0 (rounds+1)''',
      'multimodalIdleInput':'''private def multimodalIdleInput : Action :=
        .bind (Memory.read64 schoolStreamFlag) fun s enabled => if statusFailed s = true then .done s 0 else
        if enabled = 1 then
          .bind (rawGet 16) fun s captured => if statusFailed s = true then .done s 0 else
          if 0 < captured then Syscall.yield else Syscall.sleep 10000
        else Syscall.sleep 10000''',
      'multimodalDrainInput':'''private def multimodalDrainInput (input : UInt64) : Action :=
        .bind (drainMultimodalInput input) fun s consumed =>
        if statusFailed s = true then .done s 0 else
        if consumed = 0 then multimodalIdleInput else .done 0 consumed'''}
    for name,body in exact.items():require(definition(source,name)==compact(body),'School25 exact mode/capture/idle source differs: '+name)
    require('(Memory.write64 schoolStreamFlag 0)' in definition(source,'clearStep'),'School25 flag did not clear before optional mappings')
    initialize=definition(source,'schoolQueueInitialize')
    ordered=['Lemma.Courses.SchoolSubmission.initializeQueue endpoint console (request + 1)',
             'Memory.read64 schoolStreamFlag','if wire = 1 then Lemma.Courses.SchoolSubmission.enableWire96 else .done 0 0',
             'Memory.write64 schoolQueueReadyFlag 1','Lemma.Courses.SchoolSubmission.restore 1']
    require(all(x in initialize for x in ordered) and [initialize.index(x) for x in ordered]==sorted(initialize.index(x) for x in ordered),
            'wire selection must follow successful fresh initialization and precede recovery')
    main=definition(source,'mainMultimodalConfigured');step=definition(source,'multimodalStep')
    require('if school = 3 then CapabilityConsole.record console 0x740 1 96 230 256 else .done 0 0' in main,'wire startup announcement lost its exact selected mode/tuple')
    require(step.startswith('private def multimodalStep : Action := .bind multimodalAdvanceInput fun s _ => if statusFailed s = true then .done s 0 else'),
            'actual mainloop did not retire the selected bounded captured prefix first')
    require('Syscall.call 65 input 1 raw 0 0' in step and 'if s = 174 then multimodalIdleInput else' in step and
            step.count('else multimodalDrainInput input')==2,'nonblocking input/suffix lost selected idle/yield policy')
    return {'mode':3,'legacy_modes':[0,1,2],'flag_offset':656,'capture_rounds':8,'wire_startup':[0x740,1,96,230,256],
            'scope':'source admission; op1 input is nonblocking, no CPU throughput or no-loss claim'}


def sources(values):
    from multimodal_target import _lean_without_comments
    require(set(values)==set(COMPONENTS),'complete School25 stream source inventory differs')
    source={key:_lean_without_comments(value) for key,value in values.items()};result=notebook_source(source['notebook'])
    queue=source['submission'];wire=source['stream']
    require(definition(source['console'],'packetAddress')=='def packetAddress : UInt64 := 0x20200' and
            definition(source['notebook'],'raw')=='def raw : UInt64 := 0x20300' and
            0x20200+230<=0x20300,'actual230-byte Console frame overlaps Notebook raw input')
    require(definition(queue,'enableWire96')==compact('''def enableWire96 : Action :=
      .bind (get 0) fun s phase => if s = 0 then
      .bind (get 336) fun s enabled => if s = 0 then
      if phase = 0 then if enabled = 0 then put 336 1 else bad else bad
      else .done s 0 else .done s 0'''),'wire enable escaped fresh phase0/exact one-shot flag')
    initialize=definition(queue,'initializeQueue')
    require('.boundedFoldU64 48 zeroStep 48' in initialize and definition(queue,'zeroStep')==compact('''private def zeroStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
      .bind (put (i.toUInt64*8) 0) fun s _ => .done s acc'''),
      'new wire flag is not in the genuine queue initialization clear extent')
    start=definition(queue,'streamStart');emit=definition(queue,'emitWords')
    require('if wire = 1 then .bind (get 16) fun s console => if s = 0 then SchoolStream.start console queue sequence total ns else .done s 0 else record 0x72e queue sequence total ns' in start,
            'queue start lost actual wire selection/old K1 fallback')
    require('let count := minimum (if wire = 1 then 96 else 16) available' in emit and
            'SchoolStream.send console queue offset source count else .done s 0 else' in emit,
            'queue chunks lost exact96/legacy16 selection and actual source/offset')
    after='fun s _ => if s = 0 then .bind (crcWords source count) fun s _ => if s = 0 then .bind (put 160 (offset+count))'
    require(after in emit,'payload frontier/CRC advances without successful actual Console emission')
    require('.boundedFoldU64 96 crcStep count.toUInt32' in definition(queue,'crcWords'),'bounded CRC does not cover the complete emitted chunk')
    for name,body in [('maximumPayload','def maximumPayload : UInt64 := 96'),('packet','def packet : UInt64 := Console.packetAddress')]:
        require(definition(wire,name)==body,'wire count/Console scratch differs: '+name)
    for name,body in {
      'wordStep':'''private def wordStep (i _ : UInt32) (acc address value _ _ : UInt64) : Action :=
        .bind (Memory.write8 (address+i.toUInt64) (Console.digit ((value >>> (60-i.toUInt64*4)) &&& 15))) fun s _ =>
        .done s (acc+1)''',
      'word':'''private def word (address value : UInt64) : Action :=
        .boundedFoldU64 16 wordStep 16 0 address value 0 0 fun s count =>
        if s = 0 then if count = 16 then .done 0 0 else .done malformed count else .done s 0''',
      'byteStep':'''private def byteStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
        .bind (Memory.read8 (source+i.toUInt64)) fun s value => if s = 0 then
        .bind (Memory.write8 (target+i.toUInt64*2) (Console.digit (value >>> 4))) fun s _ => if s = 0 then
        .bind (Memory.write8 (target+i.toUInt64*2+1) (Console.digit (value &&& 15))) fun s _ =>
        .done s (acc+1) else .done s acc else .done s acc'''
    }.items():require(definition(wire,name)==compact(body),'exact S1 hex encoding source differs: '+name)
    prepare=definition(wire,'prepare')
    prefix=compact('''def prepare (queue offset source count : UInt64) : Action :=
      if queue >>> 48 = 0x5351 then if 0 < (queue &&& 0x0000ffffffffffff) then
      if offset < 262144 then if 0 < count then if count ≤ maximumPayload then
      if count ≤ 262144-offset then''')
    require(prepare.startswith(prefix),'S1 queue/offset/count authority or total allocation bound differs')
    for fragment in ['Memory.write8 packet 83','Memory.write8 (packet+1) 49','Memory.write8 (packet+2) 32',
                     'word (packet+3) queue','Memory.write8 (packet+19) 32','word (packet+20) (offset ||| (count <<< 48))',
                     'Memory.write8 (packet+36) 32','.boundedFoldU64 96 byteStep count.toUInt32 0 source (packet+37) 0 0',
                     'if copied = count then','Memory.write8 (packet+37+count*2) 10','if s = 0 then .done 0 (38+count*2) else .done s 0']:
        require(fragment in prepare,'S1 actual byte preparation differs: '+fragment)
    require(definition(wire,'send')==compact('''def send (console queue offset source count : UInt64) : Action :=
      .bind (prepare queue offset source count) fun s length => if s = 0 then
      .bind (Capability.consoleWrite console packet length) fun s actual =>
      if s = 0 then if actual = length then .done 0 count else .done Console.failure actual
      else .done s actual else .done s 0'''),'short/error Console writes must preserve their actual irreversible prefix and never count payload')
    require(definition(wire,'start')==compact('''def start (console queue sequence total ns : UInt64) : Action :=
      .bind (Console.prepareRecord 0x72e queue sequence total ns) fun s length => if s = 0 then
      if length = 88 then
      .boundedFoldU64 88 shiftStartStep 88 0 0 0 0 0 fun s shifted => if s = 0 then
      if shifted = 88 then
      .bind (Memory.write8 packet 10) fun s _ => if s = 0 then
      .bind (Capability.consoleWrite console packet 89) fun s actual =>
      if s = 0 then if actual = 89 then .done 0 0 else .done Console.failure actual
      else .done s actual else .done s 0
      else .done malformed shifted else .done s 0
      else .done malformed length else .done s 0'''),'fresh start must resynchronize the entire real K1 record in one actual89-byte write')
    require(definition(wire,'shiftStartStep')==compact('''private def shiftStartStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
      .bind (Memory.read8 (packet+87-i.toUInt64)) fun s value => if s = 0 then
      .bind (Memory.write8 (packet+88-i.toUInt64) value) fun s _ => .done s (acc+1) else .done s acc'''),
      'fresh start must shift the original actual K1 bytes backwards without clobbering unread input')
    return {**result,'maximum_payload':96,'maximum_frame':230,'console_limit':256,
            'packet_extent':[0x20200,0x20200+230],'raw_input_base':0x20300,'source_byte_semantics':True}


def source_root(root):return sources({key:(Path(root)/name).read_text() for key,name in COMPONENTS.items()})


def llvm_semantics(ir,rows,configuration):
    from audit_kernel import _ir_definition_body,_local_call_arguments
    from school_deployment import user_roots_for,version_for_configuration
    prefix='Lemma.Applications.Notebook.';queue='Lemma.Courses.SchoolSubmission.';wire='Lemma.Courses.SchoolStream.'
    def calls(owner,target):
        require(owner in rows and target in rows,'School25 emitted source edge absent: '+owner+' -> '+target)
        return _local_call_arguments(_ir_definition_body(ir,rows[owner]['symbol']),rows[target]['symbol'])
    mode={23:1,24:2,25:3}[version_for_configuration(configuration)]
    root=user_roots_for(configuration)['notebook'][0]
    exact=[(root,prefix+'mainMultimodalConfigured','i64 %arg0, i64 '+str(mode)),
           (wire+'send',wire+'prepare','i64 %arg1, i64 %arg2, i64 %arg3, i64 %arg4'),
           (wire+'start','Lemma.User.Console.prepareRecord','i64 1838, i64 %arg1, i64 %arg2, i64 %arg3, i64 %arg4')]
    for owner,target,arguments in exact:require(calls(owner,target)==[arguments],'School25 emitted call operands retargeted: '+owner)
    edges=[(prefix+'multimodalStep',prefix+'multimodalAdvanceInput'),(prefix+'multimodalAdvanceInput',prefix+'multimodalAdvanceCaptured'),
           (prefix+'multimodalAdvanceInput',prefix+'multimodalRawPump'),(prefix+'multimodalIdleInput','Lemma.User.Syscall.yield'),
           (prefix+'multimodalDrainInput',prefix+'multimodalIdleInput'),(prefix+'schoolQueueInitialize',queue+'enableWire96'),
           (queue+'streamStart',wire+'start'),(queue+'emitWords',wire+'send')]
    for owner,target in edges:require(calls(owner,target),'School25 actual emitted call edge absent: '+owner+' -> '+target)
    return {'exact_operand_edges':exact,'actual_edges':edges,'scope':'checked pre-LLVM operands/calls plus exact source semantics and mandatory complete pre/post body pins; actual CPU execution separate'}
