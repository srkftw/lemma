"""Exact source/LLVM admission for the separately versioned Multimodal14 guest.

No inputs are interpreted and no sensor/notebook/tutor result is fabricated here.
Missing genuine catalog/corpus pins reject; collection emits candidate identities,
not an acceptance receipt. Ordinary artifact, memory, ISA and source audits remain
required independently.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

from core0_common import Core0Error
from multimodal_deployment import CONFIGURATIONS, PARAMETERIZED_CONFIGURATIONS, BOOT_ROOTS, NOTEBOOK_ROOT, SOFTWARE_DEPLOYMENT
from paper_next import canonical
from integrated_deployment import CONFIGURATIONS as INTEGRATED_CONFIGURATIONS

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / 'tooling/multimodal-target-authority.json'
VERSION = 'lemma-multimodal-target-authority/1'
PREFIX = 'Lemma.Platform.LemmaSim.NotebookKernel.'
ROLES = ('firmware', 'kernel', 'store', 'notebook', 'arithmetic', 'course')
USER_ROOTS = {'store': ('Lemma.Services.Store.ServerAwait.main', 1, 'core0-user-v0.1'),
              'notebook': (NOTEBOOK_ROOT, 2, 'core0-user-v0.2'),
              'arithmetic': ('Lemma.Services.Arithmetic.ServerV8.main', 3, 'core0-user-v0.7'),
              'course': ('Lemma.Courses.PackageInstaller.mainAwait', 4, 'core0-user-v0.1')}


def user_roots(configuration):
    return {**USER_ROOTS,'course':('Lemma.Courses.PackageInstaller.mainParameterized',4,'core0-user-v0.1')} if configuration in PARAMETERIZED_CONFIGURATIONS else USER_ROOTS


def require(condition, message):
    if not condition: raise Core0Error('Multimodal14: ' + message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def selected(unit):
    from integrated_deployment import CONFIGURATIONS as integrated
    return unit.get('configuration') in CONFIGURATIONS + integrated


def role_key(unit):
    role = unit.get('role')
    if role in ('kernel', 'firmware'): return role
    require(role == 'user' and unit.get('image_key') in USER_ROOTS, 'unknown role or image')
    return unit['image_key']


def catalog(unit):
    from school_target import selected as school_selected, catalog as school_catalog
    if school_selected(unit):return school_catalog(unit)
    from integrated_target import selected as integrated, catalog as integrated_catalog
    if integrated(unit):return integrated_catalog(unit)
    require(selected(unit), 'unknown exact configuration')
    key = role_key(unit)
    rows = unit.get('functions')
    require(isinstance(rows, list) and rows and all(isinstance(r, dict) for r in rows), 'empty or malformed genuine function catalog')
    names = {canonical(r.get('source', '')): r for r in rows}
    require(len(names) == len(rows) and len({r.get('symbol') for r in rows}) == len(rows), 'duplicate canonical source or symbol')
    require(unit.get('software_deployment') == SOFTWARE_DEPLOYMENT, 'hardware/software/role tuple differs')
    v7 = 'Lemma.Services.Arithmetic.ServerV7.'
    v8 = 'Lemma.Services.Arithmetic.ServerV8.'
    if any(source.startswith((v7, v8)) for source in names):
        require(key == 'arithmetic', 'arithmetic executable namespace escaped its isolated role')
        # V8 borrows only the copied-request engine; V7 executable loops,
        # roots and pressure fixtures remain outside this image authority.
        borrowed = {'incoming', 'outgoing', 'state', 'get', 'respondV7',
                    'delayedStep', 'delayed', 'reclaimed', 'processV7', 'processCopied'}
        require(all(source[len(v7):] in borrowed for source in names if source.startswith(v7)),
                'V8 borrowed another V7 executable or unknown source')
    roots = [(canonical(r.get('source', '')), r.get('id'), r.get('args')) for r in unit.get('roots', [])]
    if key == 'kernel':
        require(unit.get('contract_version') == 'core0-kernel-v0.9', 'kernel authority is not version 0.9')
        require(roots == [(PREFIX + BOOT_ROOTS[unit['configuration']], 1, []),
                          (PREFIX + 'dispatchMultimodalBulk', 2, ['u64'] * 3)], 'kernel roots or ABI differ')
    elif key in USER_ROOTS:
        source, identifier, profile = user_roots(unit['configuration'])[key]
        require((unit.get('image_id'), unit.get('contract_version')) == (identifier, profile), 'User role/profile differs')
        require(roots == [(source, 1, ['u64'])] and unit.get('used_device_ops') == [], 'User root or device authority differs')
        if key == 'notebook':
            operations = unit.get('used_execution_ops', [])
            require(len(operations) == 5 and {r.get('stable_id') for r in operations} == {
                'execution.virtual-read8', 'execution.virtual-read64', 'execution.virtual-write8',
                'execution.virtual-write64', 'execution.syscall'}, 'Notebook acquired an undeclared execution boundary')
            loops = unit.get('used_loops', [])
            require(len(loops) == 1 and loops[0].get('stable_id') == 'action.loop' and
                    canonical(loops[0].get('callback', '')) == 'Lemma.Applications.Notebook.multimodalStep', 'Notebook loop differs')
    return key, names


def _lean_without_comments(source):
    """Small lexical pass for the declared source gates, not a Lean parser."""
    output, position, depth, quoted = [], 0, 0, False
    while position < len(source):
        pair = source[position:position+2]
        if depth:
            if pair == '/-': depth += 1; position += 2
            elif pair == '-/': depth -= 1; position += 2
            else:
                if source[position] == '\n': output.append('\n')
                position += 1
        elif not quoted and pair == '/-': depth = 1; position += 2
        elif not quoted and pair == '--':
            newline = source.find('\n', position)
            position = len(source) if newline < 0 else newline
        else:
            char = source[position]; output.append(char); position += 1
            if quoted and char == "\\" and position < len(source):
                output.append(source[position]); position += 1
            elif char == '"': quoted = not quoted
    require(depth == 0 and not quoted, 'unterminated source comment/string')
    return ''.join(output)


def notebook_safety_sources(multimodal_source, notebook_source, backlog_source):
    """Independent, narrow source checks for the Notebook21 safety/layout repair.

    Check reviewed source ordering and disjoint fixed windows; full genuine LLVM
    pins, source admission and execution remain required. This is not a general
    Lean verifier or an end-to-end response-latency qualification.
    """
    mm, notebook, backlog = map(_lean_without_comments, (multimodal_source, notebook_source, backlog_source))
    compact = lambda value: ' '.join(value.split())
    def definition(source, name):
        matches = list(re.finditer(r'^(?:private )?def '+re.escape(name)+r'(?=\s|\()', source, re.M))
        require(len(matches) == 1, 'source safety definition absent/duplicate: '+name)
        start = matches[0].start()
        tail = re.search(r'^(?:(?:private )?def |end )', source[matches[0].end():], re.M)
        end = matches[0].end()+tail.start() if tail else len(source)
        return compact(source[start:end])
    def value(source, name):
        match = re.search(r'^(?:private )?def '+re.escape(name)+r' : UInt64 := ([^\n]+)$', source, re.M)
        require(match is not None, 'source layout constant missing: '+name)
        return compact(match.group(1))
    require(value(mm,'records') == '0x340000' and value(mm,'state') == 'records + 2048' and
            value(mm,'packet') == 'records + 2304', 'source layout fixed page/offsets differ')
    require(value(backlog,'base') == '0x20d00' and value(backlog,'capacity') == '8',
            'source layout historical control backlog differs')
    require(value(notebook,'tutorContext') == 'Lemma.User.Multimodal.records + 1024' and
            value(notebook,'tutorPacket') == 'Lemma.User.Multimodal.records + 1536' and
            value(notebook,'tutorState') == 'Lemma.User.Multimodal.state + 144' and
            value(notebook,'schoolContext') == 'Lemma.User.Multimodal.records + 1152' and
            value(notebook,'schoolPacket') == 'Lemma.User.Multimodal.records + 1792',
            'source layout actual tutor consumers differ')
    page, page_size = 0x340000, 4096
    windows = [('samples',0,8*64),('tutor context',1024,11*8),('school context',1152,13*8),('tutor proposal',1536,32*8),('JOIN packet',1792,13*8),
               ('state',2048,32*8),('configuration packet',2304,8*8)]
    for index, (name, offset, length) in enumerate(windows):
        require(offset % 8 == 0 and length > 0 and offset+length <= page_size,
                'source layout window out of page: '+name)
        for other, start, size in windows[index+1:]:
            require(offset+length <= start or start+size <= offset, 'source layout windows overlap: '+name+'/'+other)
        require(page+offset >= 0x20d00+32+8*64, 'source layout aliases old control backlog')
    initialize = definition(mm,'«initialize»')
    expected = compact('''def «initialize» (console : UInt64) : Action :=
      .bind (Syscall.allocatePage records) fun s address => if mmFailed s = true then .done s 0 else
      if mmDifferent address records = true then .done 95 0 else
      .boundedFoldU64 32 clearStep 32 0 0 0 0 0 fun s _ => if mmFailed s = true then .done s 0 else''')
    require(initialize.startswith(expected), 'source allocation/status/address must precede every clear/write')
    require(definition(mm,'clearStep') == compact('''private def clearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
      .bind (put (i.toUInt64 * 8) 0) fun s _ => .done s acc'''), 'source clear no longer bounded to allocated state')
    require(definition(notebook,'multimodalSafety') == compact('''private def multimodalSafety (operation : UInt64) : Action :=
      .bind (Lemma.User.Multimodal.control operation) fun status result =>
      .bind (get 24) fun s console => if mmFailed s = true then .done s 0 else
      .bind (CapabilityConsole.record console 0x712 operation status.toUInt64 result 0) fun s _ => if mmFailed s = true then .done s 0 else
      Memory.write64 (Lemma.User.Multimodal.state + 32) 1'''),
      'source local safety may only control/receipt/defer; framebuffer work rejected')
    require(definition(notebook,'multimodalBarTile') == compact('''private def multimodalBarTile (i _ : UInt32) (acc width _ _ _ : UInt64) : Action :=
      .bind (markDirtyTile (4 * ((width + 31) / 32) + 12 + i.toUInt64)) fun s _ => .done s acc'''),
      'source toolbar tile row/column/index differs')
    raw_capture = 'private def multimodalRawBase : UInt64 := 0x350000' in notebook
    owned_pcm = 'private def audioPage : UInt64 := 0x360000' in mm
    if 'private def requestMultimodalBarAfterRedraw' in notebook:
        require(definition(notebook,'requestMultimodalBarAfterRedraw') == compact('''private def requestMultimodalBarAfterRedraw : Action :=
          .bind (Memory.read64 rawCaptureReadyFlag) fun s ready => if statusFailed s = true then .done s 0 else
          if ready = 1 then Memory.write64 (Lemma.User.Multimodal.state + 32) 1 else .done 0 0'''),
          'source redraw bar allocation/deferral differs')
        redraw = definition(notebook,'redraw')
        require(compact('''.bind (Surface.background width height) fun s _ => if statusFailed s = true then .done s 0 else
          .bind requestMultimodalBarAfterRedraw fun s _ => if statusFailed s = true then .done s 0 else''') in redraw,
          'source redraw omitted optional bar request')
    school = 'private def schoolActivityFlag : UInt64 :=' in notebook
    require(not owned_pcm or school, 'source toolbar owned PCM requires the selected school layout')
    extent, packed, tiles = (1264,6480,28) if owned_pcm else (1120,5400,23)
    school_bar = compact('''.bind (Memory.read64 schoolActivityFlag) fun s school => if mmFailed s = true then .done s 0 else
      .bind (Memory.read64 (Lemma.User.Multimodal.records+2480)) fun s lost => if mmFailed s = true then .done s 0 else
      let enabled := enabled ||| (school <<< 8) ||| (lost <<< 16)''') if school else ''
    expected_bar = compact('''private def multimodalBar : Action :=
      .bind Lemma.User.Multimodal.active fun s enabled => if mmFailed s = true then .done s 0 else
      SCHOOL_BAR
      .bind (get 32) fun s width => if mmFailed s = true then .done s 0 else
      if width < 1120 then .done 16 0 else
      .boundedFoldU64 5400 multimodalBarStep 5400 0 enabled width 0 0 fun s _ => if mmFailed s = true then .done s 0 else
      .boundedFoldU64 23 multimodalBarTile 23 0 width 0 0 0 fun s _ => if mmFailed s = true then .done s 0 else
      dirty 400 132 1120 147''').replace('SCHOOL_BAR',school_bar).replace('1120',str(extent)).replace('5400',str(packed)).replace('23 multimodalBarTile 23',f'{tiles} multimodalBarTile {tiles}')
    require(definition(notebook,'multimodalBar') == compact(expected_bar),
      'source toolbar must match its versioned width, raster size and every intersected tile')
    if owned_pcm:
        require(value(mm,'audioPage') == '0x360000', 'source toolbar PCM page differs')
        require('let x := i.toUInt64 % 432 * 2 let y := i.toUInt64 / 432' in definition(notebook,'multimodalBarStep'),
                'source toolbar packed PCM raster extent differs')
        require('if operation = 9 then Lemma.User.Multimodal.testAudio' in definition(notebook,'multimodalControl'),
                'source toolbar PCM action no longer invokes the maintained consumer')
        require('if 1120 ≤ px then if px < 1264 then multimodalControl 9 else .done 0 0 else .done 0 0' in definition(notebook,'multimodalApplySample' if raw_capture else 'multimodalInputSample'),
                'source toolbar PCM input extent differs')
    require(definition(notebook,'multimodalPumpBar') == compact('''private def multimodalPumpBar : Action :=
      .bind (Memory.read64 (Lemma.User.Multimodal.state + 32)) fun s pending => if mmFailed s = true then .done s 0 else
      if pending = 0 then .done 0 0 else
      .bind (get 104) fun s stroke => if mmFailed s = true then .done s 0 else
      .bind (get 160) fun s store => if mmFailed s = true then .done s 0 else
      .bind (get 536) fun s checking => if mmFailed s = true then .done s 0 else
      .bind (get 336) fun s dirtyX => if mmFailed s = true then .done s 0 else
      if stroke ||| store ||| checking = 0 then if dirtyX = 0xffff then
      .bind (get 0) fun s surface => if mmFailed s = true then .done s 0 else
      .bind (Surface.status surface) fun s status => if mmFailed s = true then .done s 0 else
      if status &&& 1 = 0 then
        .bind multimodalBar fun s _ => if mmFailed s = true then .done s 0 else
        Memory.write64 (Lemma.User.Multimodal.state + 32) 0
      else .done 0 0 else .done 0 0 else .done 0 0'''), 'source deferred toolbar lost idle/frame ownership gates')
    input_ = definition(notebook,'multimodalApplySample' if raw_capture else 'multimodalInputSample')
    capture = definition(notebook,'multimodalInputSample') if raw_capture else input_
    safety_branch = compact('''if (if 132 ≤ safetyY then if safetyY < 160 then if 544 ≤ safetyX then if safetyX < 832 then true else false else false else false else false) = true then
      multimodalSafety (if safetyX < 640 then 1 else 2)
    else .bind (get 432)''')
    require(safety_branch in input_, 'source safety controls no longer precede busy/cancelled queue gate')
    prefix = input_[:input_.index(safety_branch)]
    capture_branch = compact('''.bind (if 132 ≤ safetyY then if safetyY < 160 then
      if 400 ≤ safetyX then if safetyX < 544 then Lemma.User.Multimodal.active
      else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0)
      fun s captureActive => if statusFailed s = true then .done s 0 else
      if different captureActive 0 = true then multimodalSafety 0 else''')
    if school:
        capture_branch = capture_branch.replace('if different captureActive', compact('''.bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else''')+' if different captureActive')
        capture_branch += ' '+compact('''if (if school = 1 then if 132 ≤ safetyY then if safetyY < 160 then if 760 ≤ safetyX then if safetyX < 832 then true else false else false else false else false else false) = true then
          if safetyX < 808 then multimodalQueueTutor 7 else multimodalControl 8 else''')
    require(capture_branch+' '+safety_branch in input_,
            'source CAPTURE may only inhibit an active session before the busy queue')
    require(all(token not in prefix for token in ('queueBookTap','get 160','get 536','ControlBacklog.count','cancelBookmarkWork')),
            'source local safety waits behind Store/check/backlog')
    require(all(token not in prefix for token in ('Surface.framebuffer','markDirtyTile','multimodalBar')),
            'source local inhibition renders before idle/frame ownership')
    require('if different active 0 = true then appendRaw else if flags &&& 1 = 0 then .done 0 0 else if previousContact = 1 then .done 0 0 else' in prefix,
            'source safety bypass changed pen contact/raw-stroke handling')
    for offset in (288,296,304):
        require('put '+str(offset) in capture if raw_capture else 'put '+str(offset) in prefix, 'source safety omitted original pen sequence/time/epoch tracking')
    require('Geometry.pixel (Geometry.normalized x maxX) width' in prefix and
            'Geometry.pixel (Geometry.normalized y maxY) height' in prefix,
            'source safety coordinates bypass declared pen geometry')
    intent_branch = compact('''if (if 132 ≤ safetyY then if safetyY < 160 then if 832 ≤ safetyX then if safetyX < 1120 then true else false else false else false else false) = true then
      multimodalQueueTutor (if safetyX < 928 then 3 else if safetyX < 1024 then 4 else 5)
    else .bind (get 512)''')
    require(intent_branch in input_ and input_.index(intent_branch) < input_.index('.bind (get 160)'),
            'source ASK/LOAD retention must precede the busy math queue')
    book_branch=compact('''if (if selectedCourse = 1 then if 660 ≤ safetyY then if safetyY < 680 then if 216 ≤ safetyX then if safetyX < 312 then true else false else false else false else false else false) = true then
      multimodalQueueBookLoad else .bind (get 136)''')
    require(book_branch in input_ and input_.index(book_branch)<input_.index('.bind (get 160)'),
            'source chooser LOAD retention must precede the busy math queue')
    book_queue=definition(notebook,'multimodalQueueBookLoad')
    require(all(token in book_queue for token in ('if pending = 0 then','get 80','packageGet 128','packageGet 136',
        'Memory.write64 (tutorState + 32) page','Memory.write64 (tutorState + 40) identity',
        'Memory.write64 (tutorState + 48) edition','multimodalQueueTutor 6')),
        'source chooser LOAD lost its bounded page/publication snapshot')
    book_dispatch=definition(notebook,'multimodalBookLoad')
    require('if course = 1 then if page = expectedPage then if identity = expectedIdentity then if edition = expectedEdition then packageControlPress 264 670' in book_dispatch
            and book_dispatch.count('.done 175 0')==4,'source queued chooser LOAD lost its page/publication cancellation')
    queued = definition(notebook,'multimodalQueueTutor')
    require(queued == compact('''private def multimodalQueueTutor (operation : UInt64) : Action :=
      .bind (Memory.read64 (tutorState + 16)) fun s pending => if statusFailed s = true then .done s 0 else
      .bind (if pending = 0 then Memory.write64 (tutorState + 16) operation else .done 0 0)
        fun s _ => if statusFailed s = true then .done s 0 else
      .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
      CapabilityConsole.record console 0x726 operation (if pending = 0 then 1 else if pending = operation then 2 else 3) 0 0'''),
      'source pending intent must retain/coalesce or report bounded Busy without acquiring work')
    pump = definition(notebook,'multimodalPumpTutor')
    deferred = 'private def rawIndexDeferredFlag : UInt64 :=' in notebook
    pump_gate = ('if deferredIndex ||| captured ||| stroke ||| rawCount ||| rawPending ||| store ||| checking = 0 then if dirtyX = 0xffff then' if deferred else
                 'if captured ||| stroke ||| rawCount ||| rawPending ||| store ||| checking = 0 then if dirtyX = 0xffff then' if school else
                 'if stroke ||| rawCount ||| rawPending ||| store ||| checking = 0 then if dirtyX = 0xffff then')
    require(pump_gate in pump and
            '.bind bookmarkBusy' in pump and '.bind Lemma.Notebook.ControlBacklog.count' in pump and
            'if work ||| waiting = 0 then' in pump and '.bind (Surface.status surface)' in pump and
            'if status &&& 1 = 0 then' in pump and
            '.bind (Memory.write64 (tutorState + 16) 0)' in pump and
            pump.index('if status &&& 1 = 0 then') < pump.index('Memory.write64 (tutorState + 16) 0') < pump.index('multimodalControl operation'),
            'source tutor intent dispatch lost work/display ownership or exact-once consumption')
    step = definition(notebook,'multimodalStep')
    abandon=definition(notebook,'multimodalAbandonPresentation')
    require(abandon == compact('''private def multimodalAbandonPresentation : Action :=
      .bind (packagePut 72 0) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (packagePut 144 0) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (packagePut 152 0) fun s _ => if statusFailed s = true then .done s 0 else
      packagePut 32 4'''), 'source rejected view must release only terminal presentation work')
    work=definition(notebook,'multimodalPackageWork')
    require(compact('''.bind multimodalAdmitTutor fun s marked => if statusFailed s = true then
      .bind multimodalAbandonPresentation fun cleanup _ => if statusFailed cleanup = true then .done cleanup 0 else courseError s''') in work,
      'source rejected view must abandon pending presentation before course error')
    for name,identity in (('multimodalLoadTutor',60001),('multimodalJoinSchool',60000)):
        envelope=definition(notebook,name)
        reset=compact('''.bind (packagePut 160 0) fun s _ => if statusFailed s = true then .done s 0 else
          .bind (packagePut 176 0) fun s _ => if statusFailed s = true then .done s 0 else''')
        require(reset+' .bind (beginPackageRead '+str(identity)+' sequence)' in envelope,
                'source school envelope inherited original reader CRC/node guards')
    tutor_route = ('.bind (if queueOwns = 0 then multimodalPumpTutor else .done 0 0)' if raw_capture else '.bind multimodalPumpTutor')
    require('.bind multimodalPumpBar' in step and tutor_route in step and '.bind (drainMultimodalInput input)' in step and
            'else multimodalInputSample' in step, 'source idle/busy paths do not route new input/deferred redraw')
    drain = definition(notebook,'drainMultimodalInput')
    loss = ('if s = 175 then .bind (multimodalRawLoss 3)' if raw_capture else 'if s = 175 then .bind cancelBookmarkInput')
    if raw_capture:
        require('if resync = 0 then multimodalRawPush else if flags &&& 1 = 0 then rawPut 40 0 else .done 0 0' in capture,
                'source raw capture lost input/resync ownership')
        require('if (if flags &&& 1 = 1 then if previousContact = 0 then true else false else false) = true then' in capture and
                'if 544 ≤ px then if px < 760 then' in capture and
                'multimodalSafety (if px < 640 then 1 else 2)' in capture and
                'if school = 1 then if px < 808 then multimodalQueueTutor 7 else multimodalControl 8 else multimodalSafety 2' in capture and
                'if capture = 1 then multimodalSafety 0 else ordinary resync flags' in capture,
                'source raw capture lost local inhibition before retained work')
        require(not any(token in capture for token in ('get 160','get 536','Surface.framebuffer','Surface.status','ControlBacklog.count','multimodalControl 9')),
                'source raw capture safety waits for work or starts PCM before ordered replay')
        require('if different sequence (previousSequence+1) = true then true else time < previousTime) = true then multimodalRawLoss 1' in capture,
                'source raw capture lost sequence/time discontinuity detection')
        require('Lemma.Services.Store.Format.copy raw row 72' in definition(notebook,'multimodalRawPush') and
                'Lemma.Services.Store.Format.copy row raw 72' in definition(notebook,'multimodalRawPump') and
                'multimodalApplySample x y flags' in definition(notebook,'multimodalRawPump'),
                'source raw capture lost exact record copy or ordered replay')
    require('.bind multimodalInputSample' in drain and loss in drain,
            'source busy input lost safety routing or lost-contact cancellation')
    return {'toolbar_variant': 'school23-owned-pcm2' if owned_pcm else 'school23' if school else 'legacy21',
            'toolbar_extent':extent,'toolbar_tiles':tiles,'coalesced_index':deferred,'captured_input':raw_capture,
            'allocated_page':page,'page_bytes':page_size,'disjoint_windows':windows,
            'historical_backlog':[0x20d00,0x20d00+32+8*64],
            'checks':['allocate/status/exact-address before clear','local inhibition before busy queues',
                      'no framebuffer work in local inhibition','deferred refresh requires idle framebuffer',
                      'pen contact/sequence/loss routing retained'],
            'scope':'reviewed source gates; genuine lowering, complete-corpus admission and execution are separate'}


def notebook_safety_source(root=ROOT):
    return notebook_safety_sources(*((Path(root)/path).read_text() for path in (
        'Lemma/User/Multimodal.lean','Lemma/Applications/Notebook.lean','Lemma/Notebook/ControlBacklog.lean')))


def owned_io_semantics(ir, rows):
    """Version2 only: closed source/IR edges and private-frame value flow."""
    from audit_kernel import _ir_definition_body, _local_call_arguments, _local_checked_result
    service='Lemma.Platform.LemmaSim.MultimodalService.'
    version=service+'version'
    if version not in rows:return None
    def body(source):
        require(source in rows,'ownedIO source absent: '+source)
        return _ir_definition_body(ir,rows[source]['symbol'])
    def calls(owner,target):
        require(target in rows,'ownedIO target absent: '+target)
        return _local_call_arguments(body(owner),rows[target]['symbol'])
    def value(owner,target,args):return _local_checked_result(body(owner),rows[target]['symbol'],args)[1]
    require(re.fullmatch(r'\s*entry:\s*ret i64 2\s*',body(version)) is not None,'ownedIO service version differs')
    allocate='Lemma.Kernel.Memory.Frames.allocate';resolve='Lemma.Kernel.Memory.Frames.resolvePurpose'
    configure=service+'configure';put=service+'put';get=service+'get'
    require(calls(configure,allocate)==['i64 1, i64 1']*2,'ownedIO private/metadata allocations differ')
    allocations=re.findall(r'(%[\w.$-]+) = call \{ i64, i64 \} @'+re.escape(rows[allocate]['symbol'])+r'\(i64 1, i64 1\)',body(configure))
    handles=[]
    for call in allocations:
        matches=re.findall(r'(%[\w.$-]+) = extractvalue \{ i64, i64 \} '+re.escape(call)+r', 1$',body(configure),re.M)
        require(len(matches)==1,'ownedIO allocation result differs');handles+=matches
    require(handles[0]!=handles[1] and calls(configure,put)==['i64 0, i64 %arg0','i64 8, i64 '+handles[0],'i64 16, i64 '+handles[1]],'ownedIO frame identities alias or metadata/private slots differ')
    begin=service+'beginRecord';finish=service+'finishRecord';current=service+'current'
    require(calls(begin,current)==['i64 %arg1, i64 %arg3, i64 3'],'ownedIO begin current permission differs')
    require(calls(finish,current)==['i64 %arg1, i64 %arg3, i64 3'],'ownedIO finish current permission differs')
    handle=value(begin,get,'i64 16');destination=value(begin,resolve,'i64 1, i64 '+handle+', i64 1')
    require(calls(begin,'Lemma.Kernel.Memory.UserCopy.validateWrite')==['i64 %arg0, i64 %arg2, i64 64'],'ownedIO begin writable logical span differs')
    require(calls(begin,'Lemma.Drivers.Multimodal.write')==['i64 %arg1, i64 160, i64 '+destination,'i64 %arg1, i64 168, i64 8','i64 %arg1, i64 176, i64 1'],'ownedIO DMA escaped private resolved frame or eight-word command')
    handle=value(finish,get,'i64 16')
    require(calls(finish,'Lemma.Kernel.Memory.UserCopy.copyToUser')==['i64 %arg0, i64 %arg2, i64 '+handle+', i64 0, i64 64'],'ownedIO finish logical copy differs')
    edges=[(service+'call',service+name) for name in ('beginRecord','finishRecord','pcmBatch')]
    edges += [(begin,service+'reclaimRetiredRecord'),(finish,service+'releaseRecord'),(service+'pcmStep',current)]
    for owner,target in edges:require(calls(owner,target),'ownedIO actual semantic edge omitted: '+owner+' -> '+target)
    require(calls(service+'call',begin)==['i64 %arg0, i64 %arg3, i64 %arg4, i64 %arg5'] and calls(service+'call',finish)==['i64 %arg0, i64 %arg3, i64 %arg4, i64 %arg5'] and calls(service+'call',service+'pcmBatch')==['i64 %arg0, i64 %arg3, i64 %arg4, i64 %arg5'],'ownedIO public call substituted owner/stream/logicaldest/epoch')
    require(calls(service+'pcmBatch',current)==['i64 8, i64 %arg3, i64 64'],'ownedIO batch grant differs')
    require(calls(service+'pcmStep',current)==['i64 8, i64 %arg4, i64 64'],'ownedIO per-sample live grant differs')
    return {'service_version':2,'metadata_frame_slot':8,'private_DMA_frame_slot':16,'record_bytes':64,'DMA_words':8,'actual_edges':edges,'scope':'exact compiled source/call/value binding; operating and fault behavior requires actual execution'}


def semantics(ir, unit):
    from school_target import selected as school_selected, semantics as school_semantics
    if school_selected(unit):return school_semantics(ir,unit)
    """Connect the complete pinned bodies to actual boot, grants and UI paths."""
    from audit_kernel import _ir_definition_body, _local_call_arguments
    key, rows = catalog(unit)
    owned_record_pcm=None
    def body(source):
        require(source in rows, 'semantic source absent: ' + source)
        return _ir_definition_body(ir, rows[source]['symbol'])
    def calls(owner, target):
        require(target in rows, 'semantic callee absent: ' + target)
        return _local_call_arguments(body(owner), rows[target]['symbol'])
    checked = []
    if key == 'kernel':
        boot = PREFIX + ('bootMultimodalParameterized' if unit['configuration'] in PARAMETERIZED_CONFIGURATIONS else 'bootMultimodal')
        wrapper = PREFIX + BOOT_ROOTS[unit['configuration']]
        mode = int(unit['configuration'].endswith('-initialize'))
        require(calls(wrapper, boot) == ['i64 ' + str(mode)], 'boot wrapper changed initialization operand')
        constructor = PREFIX + 'constructCourseMultimodal'
        process = 'Lemma.Kernel.Process.initMultimodal'
        aliases = 'Lemma.Kernel.Memory.AddressSpace.addMultimodalAliases'
        require(calls(boot, constructor) == ['i64 %arg0'],
                'exact multimodal four-role constructor operand differs')
        require(calls(constructor, process) == [''],
                'multimodal constructor bypassed its initial supervisor mapping')
        require(calls(process, 'Lemma.Kernel.Memory.AddressSpace.create') == ['i64 1'] and
                len(calls(process, aliases)) == 1,
                'initial supervisor root omitted exact extension aliases')
        alias_arguments = calls(constructor, aliases)
        require(len(alias_arguments) == len(set(alias_arguments)) == 4 and
                len(calls(constructor, 'Lemma.Kernel.Task.prepareManaged')) == 4 and
                len(calls(constructor, 'Lemma.Kernel.Task.activateManaged')) == 4,
                'four distinct prepared task roots lack multimodal supervisor aliases')
        for owner, target in ((boot, constructor), (constructor, process),
                              (process, aliases), (constructor, aliases)):
            checked.append((owner, target))
        for target in ('Lemma.Platform.LemmaSim.Descriptor.validateSiliconMultimodal',
                       'Lemma.Platform.LemmaSim.MachineServices.validateMultimodal',
                       'Lemma.Platform.LemmaSim.MultimodalService.configure', PREFIX + 'powerStepEntryV2'):
            require(len(calls(boot, target)) == 1, 'boot omitted or repeated ' + target)
            checked.append((boot, target))
        if unit['configuration'] in PARAMETERIZED_CONFIGURATIONS:
            from audit_kernel import _local_checked_result
            grant = PREFIX+'grantParameterizedInstaller'
            require(len(calls(boot,grant)) == 1, 'parameterized boot omitted owner-local installer grant')
            descriptor = 'Lemma.Kernel.Objects.registryDescriptor'
            lookup = 'Lemma.Kernel.Capability.lookup'
            boot_grant = 'Lemma.Kernel.Capability.bootGrant'
            discovered = 'Lemma.Kernel.Capability.grantDiscovered'
            gbody=body(grant)
            require(calls(grant,descriptor) == ['i64 1','i64 3'], 'parameterized registry roles differ')
            _,notebook=_local_checked_result(gbody,rows[descriptor]['symbol'],'i64 1')
            _,installer=_local_checked_result(gbody,rows[descriptor]['symbol'],'i64 3')
            require(calls(grant,'Lemma.Kernel.Task.lookup') == ['i64 '+notebook,'i64 '+installer],
                    'parameterized grant bypassed actual task registry rows')
            _,handle=_local_checked_result(gbody,rows[boot_grant]['symbol'],'i64 '+notebook+', i64 5')
            lookup_args=calls(grant,lookup)
            require(len(lookup_args) == 1, 'parameterized checking lookup inventory differs')
            operands=lookup_args[0].split(', ')
            require(len(operands) == 4 and operands[:2] == ['i64 '+notebook,'i64 '+handle],
                    'parameterized checking lookup changed owner or handle')
            for source,value,operand in (('Lemma.User.CapabilityABI.endpointType',2,operands[2]),
                                         ('Lemma.User.CapabilityABI.endpointCall',16,operands[3])):
                require(source in rows and re.fullmatch(r'\s*entry:\s*ret i64 '+str(value)+r'\s*',body(source)),
                        'parameterized lookup changed exact endpoint/Call registry constant')
                observed={'i64 '+str(value)} | {'i64 '+name for name in re.findall(
                    r'(%[-\w.$]+) = call i64 @'+re.escape(rows[source]['symbol'])+r'\(\)',gbody)}
                require(operand in observed,'parameterized lookup bypassed exact endpoint/Call value')
            _,checking=_local_checked_result(gbody,rows[lookup]['symbol'],lookup_args[0])
            require(calls(grant,discovered) == ['i64 '+installer+', i64 '+checking] and
                    calls(grant,'Lemma.Kernel.Capability.entryCount') == ['i64 '+installer]*2,
                    'installer grant changed descriptor, checked Call authority or count observations')
            for target in (descriptor,boot_grant,lookup,discovered): checked.append((grant,target))
        caller = PREFIX + 'deviceCallMultimodalAt'
        require(len(calls(PREFIX + 'dispatchMultimodalBulk', caller)) == 1, 'syscall dispatch omitted real Multimodal service bridge')
        require(len(calls(caller, 'Lemma.Platform.LemmaSim.MultimodalService.call')) == 1, 'syscall69 bypassed the guest service')
        service = 'Lemma.Platform.LemmaSim.MultimodalService.'
        for owner, target in ((service+'authorize', 'Lemma.Kernel.Capability.lookup'),
                              (service+'metadata', 'Lemma.Kernel.Memory.UserCopy.copyFromUser'),
                              (service+'metadata', 'Lemma.Kernel.Memory.Frames.resolvePurpose'),
                              (service+'take', 'Lemma.Kernel.Memory.UserCopy.validateWrite'),
                              (service+'take', 'Lemma.Drivers.Multimodal.take'),
                              (service+'take', 'Lemma.Kernel.Memory.UserCopy.copyToUser'),
                              (service+'configure', 'Lemma.Drivers.Multimodal.discover'),
                              (service+'configure', 'Lemma.Kernel.Memory.Frames.allocate'),
                              (service+'call', service+'authorize'), (service+'call', service+'grant'),
                              (service+'call', service+'revoke'), (service+'call', service+'configureStream'),
                              (service+'call', service+'take'), (service+'take', service+'current'),
                              (service+'configureStream', service+'current')):
            require(len(calls(owner, target)) == (2 if owner==service+'configure' and target=='Lemma.Kernel.Memory.Frames.allocate' and service+'version' in rows else 1), 'grant/current-epoch operation edge differs: ' + owner)
            checked.append((owner, target))
        owned_record_pcm=owned_io_semantics(ir,rows)
    elif key == 'arithmetic':
        server = 'Lemma.Services.Arithmetic.ServerV8.'
        for owner, target in ((server+'main', 'Lemma.User.Runtime.Arena.ensure'),
                              (server+'step', server+'processCopied'),
                              (server+'step', 'Lemma.Services.Arithmetic.ServerV7.processCopied'),
                              ('Lemma.Services.Arithmetic.ServerV7.processCopied', 'Lemma.Services.Arithmetic.ServerV7.processV7'),
                              (server+'processCopied', 'Lemma.Multimodal.Parameterized.evaluate'),
                              (server+'processCopied', 'Lemma.Services.Arithmetic.ProtocolV8.reply')):
            require(len(calls(owner,target)) == 1, 'parameterized/legacy isolated checker edge differs: '+owner)
            checked.append((owner,target))
        owner = 'Lemma.Multimodal.Parameterized.check'
        for target, arguments in (('Lemma.Mathematics.Exact.rational', 7),
                                  ('Lemma.Mathematics.Exact.polynomial', 8)):
            require(target in rows and rows[target]['args'] == ['u64']*arguments,
                    'parameterized exact checker scalar signature differs')
            require(len(re.findall(r'call i64 @'+re.escape(rows[target]['symbol'])+r'\(([^\n]*)\)', body(owner))) == 1,
                    'parameterized exact checker scalar edge differs: '+target)
            checked.append((owner,target))
    elif key == 'course' and unit['configuration'] in PARAMETERIZED_CONFIGURATIONS:
        installer='Lemma.Courses.PackageInstaller.'
        client='Lemma.Services.Arithmetic.ClientV8.'
        for owner,target in ((installer+'mainParameterized','Lemma.Courses.PackageAwaitClient.call'),
                             (installer+'mathReceive','Lemma.User.Capability.consoleRead'),
                             (installer+'mathExecute',client+'beginCall'),
                             (installer+'mathStep',client+'pollCall'),
                             (client+'beginCall','Lemma.User.IPC.callBegin'),
                             (client+'validate','Lemma.User.IPC.validate')):
            require(len(calls(owner,target)) == 1, 'parameterized independent IPC adapter edge differs: '+owner)
            checked.append((owner,target))
        require(calls(installer+'mainParameterized','Lemma.User.Capability.bootGrant') == ['i64 0','i64 1','i64 2'],
                'parameterized installer boot grants differ')
        poll=calls(client+'pollCall','Lemma.User.Syscall.call')
        require(len(poll) == 1 and poll[0].startswith('i64 67, '), 'parameterized result polling bypassed real IPC')
    elif key == 'notebook':
        notebook_safety_source()
        prefix = 'Lemma.Applications.Notebook.'
        for owner, target in ((NOTEBOOK_ROOT, 'Lemma.User.Multimodal.initialize'),
                              (NOTEBOOK_ROOT, prefix+'multimodalBar'),
                              (prefix+'multimodalStep', 'Lemma.User.Multimodal.pump'),
                              (prefix+'multimodalStep', prefix+'pumpBookControlBacklog'),
                              (prefix+'multimodalControl', 'Lemma.User.Multimodal.control'),
                              (prefix+'multimodalSafety', 'Lemma.User.Multimodal.control'),
                              (prefix+'multimodalBar', prefix+'multimodalBarTile'),
                              (prefix+'multimodalBarTile', prefix+'markDirtyTile'),
                              (prefix+'multimodalPumpBar', prefix+'multimodalBar'),
                              (prefix+'multimodalPumpBar', 'Lemma.Ink.Surface.status'),
                              (prefix+'multimodalStep', prefix+'multimodalPumpBar'),
                              (prefix+'multimodalStep', prefix+'multimodalPumpTutor'),
                              (prefix+'multimodalControl', prefix+'multimodalJoinSchool'),
                              (prefix+'multimodalControl', prefix+'multimodalBookLoad'),
                              (prefix+'multimodalBookLoad', prefix+'packageControlPress'),
                              (prefix+'multimodalInputSample.acceptSample', prefix+'multimodalQueueBookLoad'),
                              (prefix+'multimodalQueueBookLoad', prefix+'multimodalQueueTutor'),
                              (prefix+'multimodalAdmitTutor', prefix+'multimodalAdmitSchool'),
                              (prefix+'multimodalAdmitSchool', 'Lemma.Multimodal.SchoolPacket.decode'),
                              (prefix+'multimodalAdmitSchool', 'Lemma.Multimodal.SchoolPacket.acceptInvitation'),
                              (prefix+'multimodalAdmitTutor', 'Lemma.Multimodal.SchoolPacket.decode'),
                              (prefix+'multimodalAdmitTutor', 'Lemma.Multimodal.SchoolPacket.actionReason'),
                              (prefix+'multimodalAdmitTutor', 'Lemma.Multimodal.SchoolPacket.active'),
                              ('Lemma.Multimodal.SchoolPacket.actionReason', 'Lemma.Multimodal.TutorAction.validateVersion'),
                              ('Lemma.Multimodal.TutorAction.validate', 'Lemma.Multimodal.TutorAction.validateVersion'),
                              (prefix+'drainMultimodalInput.drainStep', prefix+'multimodalInputSample')):
            require(len(calls(owner, target)) == 1, 'Notebook omitted or repeated ' + target)
            checked.append((owner, target))
        owner=prefix+'multimodalInputSample.acceptSample'
        safety_calls=calls(owner,prefix+'multimodalSafety')
        require(len(safety_calls)==2 and safety_calls[0]=='i64 0',
                'Notebook active-stop and mute/revoke call inventory differs')
        variable=re.fullmatch(r'i64 (%[-A-Za-z0-9_.$]+)',safety_calls[1])
        require(variable is not None and len(re.findall(re.escape(variable[1])+r' = phi i64 \[ 1, %[-A-Za-z0-9_.$]+ \], \[ 2, %[-A-Za-z0-9_.$]+ \]',body(owner)))==1,
                'Notebook mute/revoke selector no longer contains exact operations1/2')
        checked.append((owner,prefix+'multimodalSafety'))
        invoke = 'Lemma.User.Multimodal.invoke'
        actual = calls(invoke, 'Lemma.User.Syscall.call')
        require(len(actual) == 1 and actual[0].startswith('i64 69, '), 'User sensor control bypasses syscall69')
        control_calls = calls('Lemma.User.Multimodal.control', invoke)
        require('i64 6, i64 8, i64 0, i64 0' in control_calls and
                'i64 6, i64 0, i64 0, i64 0' in control_calls,
                'local mute or modality revocation lost its exact guest operation')
        # Preserve the current chooser's source/revision/history guard.
        require(len(calls(prefix+'multimodalPackageWork', prefix+'readerPrepareSelection')) == 1,
                'reader lost the actual empty-selection guard')
        for owner, target in ((prefix+'multimodalStep',prefix+'multimodalPackageWork'),
                              (prefix+'multimodalPackageWork',prefix+'multimodalAdmitTutor'),
                              (prefix+'multimodalPackageWork',prefix+'multimodalAbandonPresentation'),
                              (prefix+'multimodalAdmitTutor','Lemma.Multimodal.TutorPackage.decode'),
                              (prefix+'multimodalAdmitTutor','Lemma.Multimodal.TutorAction.validate'),
                              (prefix+'multimodalAsk','Lemma.Courses.BrowseHistory.location')):
            require(len(calls(owner,target)) == 1, 'anchored tutor admission/guest context edge differs: '+owner)
            checked.append((owner,target))
    return {'role': key, 'explicit_call_edges': checked,
            **({'owned_record_pcm':owned_record_pcm} if owned_record_pcm is not None else {}),
            'scope': 'complete source/LLVM authority plus selected direct edges; connected execution remains separate'}


def complete(ir, unit, *, optimized=False):
    from usb_recovery_target import corpus
    # The maintained Surface optimization removes exactly two checked
    # callbacks after inlining. Retain their full original metadata in the
    # typed catalog and require the independent predecessor body/loop/access
    # checks before accounting for the missing standalone definitions.
    if optimized and 'surface_word_inline' in unit:
        from surface_word_inline import validate as validate_surface
        qualified = validate_surface(ir, unit, optimized=True)
        removed = set(qualified['removed_symbols'])
        require(len(removed) == 2 and role_key(unit) == 'notebook', 'unexpected inlined definition inventory')
        filtered = {**unit, 'functions':[row for row in unit['functions'] if row['symbol'] not in removed]}
        result = corpus(ir, filtered)
        result['validated_inline_callbacks'] = sorted(canonical(row['source']) for row in unit['functions'] if row['symbol'] in removed)
        return result
    return corpus(ir, unit)


def authority(unit):
    from school_target import selected as school_selected, authority as school_authority
    if school_selected(unit):return school_authority(unit)
    from integrated_target import selected as integrated, authority as integrated_authority
    if integrated(unit):return integrated_authority(unit)
    key, _ = catalog(unit)
    try: data = json.loads(AUTHORITY.read_text())
    except (OSError, ValueError) as exc: raise Core0Error('Multimodal14 genuine artifact authority unavailable: ' + str(exc)) from exc
    require(set(data) == {'schema', 'configurations'} and data['schema'] == VERSION and
            set(data['configurations']) == set(__import__('multimodal_deployment').LEGACY_CONFIGURATIONS), 'authority configuration inventory differs')
    item = data['configurations'][unit['configuration']]
    require(set(item) == set(ROLES), 'authority role inventory differs')
    pin = item[key]
    require(set(pin) == {'catalog_sha256', 'pre', 'post'} and pin['catalog_sha256'] == digest(unit), 'complete typed/effect/root catalog differs')
    for phase in ('pre', 'post'):
        require(isinstance(pin[phase], dict) and set(pin[phase]) == {'function_count', 'sha256'} and
                type(pin[phase]['function_count']) is int and pin[phase]['function_count'] > 0 and
                isinstance(pin[phase]['sha256'], str) and re.fullmatch('[a-f0-9]{64}', pin[phase]['sha256']),
                'missing/empty corpus pin: ' + phase)
    return key, pin


def validate(ir, unit, *, optimized):
    from school_target import selected as school_selected, validate as school_validate
    if school_selected(unit):return school_validate(ir,unit,optimized=optimized)
    from integrated_target import selected as integrated, validate as integrated_validate
    if integrated(unit):return integrated_validate(ir,unit,optimized=optimized)
    if not selected(unit):
        hardware_prefixes=('Lemma.User.Multimodal.', 'Lemma.Drivers.Multimodal.',
            'Lemma.Platform.LemmaSim.MultimodalService.', 'Lemma.Platform.Silicon.BindingMultimodal.')
        hardware_roots={NOTEBOOK_ROOT, PREFIX+'dispatchMultimodalBulk', PREFIX+'bootMultimodal',
                        PREFIX+'bootMultimodalParameterized',PREFIX+'grantParameterizedInstaller',
                        PREFIX+'constructCourseMultimodal','Lemma.Kernel.Process.initMultimodal',
                        'Lemma.Kernel.Memory.AddressSpace.addMultimodalAliases',
                        *(PREFIX+name for name in BOOT_ROOTS.values())}
        require(not any(canonical(r.get('source','')).startswith(hardware_prefixes) or
                        canonical(r.get('source','')) in hardware_roots for r in unit.get('functions', [])),
                'multimodal source escaped its exact deployment')
        return None
    key, pin = authority(unit)
    phase = 'post' if optimized else 'pre'
    actual = complete(ir, unit, optimized=optimized)
    require(len(actual['functions']) == pin[phase]['function_count'] and digest(actual) == pin[phase]['sha256'],
            'complete bodies/globals/callers differ: ' + key + '/' + phase)
    return {'contract_version': VERSION, 'role': key, 'phase': phase,
            'function_count': len(actual['functions']), 'complete_corpus_sha256': digest(actual),
            'semantics': semantics(ir, unit) if not optimized else None}


def capability_header_borrow(ir, unit):
    """Retain unchanged Capability borrow bodies beneath the new dispatcher.

    Source9 changes Paper MMIO lowering and Kernel9 replaces the two outer
    dispatcher bodies. Their complete current corpus is independently pinned;
    the four actual Capability bodies and their private incoming edges must
    still match the original lower-level borrow contract exactly.
    """
    report = validate(ir, unit, optimized=False)
    require(report is not None and role_key(unit) == 'kernel', 'header borrow escaped exact Kernel9 authority')
    from audit_kernel import _ir_definition_body, _local_call_arguments
    from surface_bulk_borrow import CAP, CALLERS, SIGNATURES, PINS, normalized_body
    rows = {canonical(row['source']):row for row in unit['functions']}
    names = {row['symbol']:source for source,row in rows.items()}
    observed = {}
    for suffix in ('headerAt','requireActiveAt','lookupEntryAt','lookupAt'):
        source = CAP+suffix
        require(source in rows, 'header borrow missing unchanged authority source: '+source)
        row = rows[source]
        arguments,effects = SIGNATURES[source]
        require(row['args'] == arguments and row['effects'] == effects, 'header borrow signature/effects differ: '+source)
        body = _ir_definition_body(ir,row['symbol'])
        identity = hashlib.sha256(normalized_body(body,names).encode()).hexdigest()
        require(identity == PINS['pre'][source], 'header borrow unchanged complete body differs: '+source)
        observed[source] = identity
        if source in CALLERS:
            incoming = {owner for owner,entry in rows.items() if
                _local_call_arguments(_ir_definition_body(ir,entry['symbol']),row['symbol'])}
            require(incoming == CALLERS[source], 'header borrow private caller inventory differs: '+source)
    return {'contract_version':'lemma-multimodal-capability-header-borrow/v1','body_identities':observed,
            'scope':'four unchanged Capability bodies/private callers plus complete current Kernel9 corpus; generic header/base/CFG checks remain required'}


def collect(directories):
    """Collect real producer outputs; never install pins or claim acceptance."""
    result = {'schema': VERSION, 'configurations': {}}
    for directory in directories:
        directory = Path(directory)
        kernel = json.loads((directory/'kernel/unit.json').read_text())
        configuration = kernel['configuration']
        require(configuration in CONFIGURATIONS and configuration not in result['configurations'], 'duplicate or unknown collection configuration')
        roles = {}
        for key in ROLES:
            base = directory/key if key in ('firmware', 'kernel') else directory/'users'/key
            unit = json.loads((base/'unit.json').read_text())
            require(unit.get('configuration') == configuration and role_key(unit) == key, 'mixed producer role/configuration')
            semantics((base/'program.ll').read_text(), unit)
            role = {'catalog_sha256': digest(unit)}
            for phase, name in (('pre', 'program.ll'), ('post', 'program.opt.ll')):
                actual = complete((base/name).read_text(), unit, optimized=phase == 'post')
                role[phase] = {'function_count': len(actual['functions']), 'sha256': digest(actual)}
            roles[key] = role
        result['configurations'][configuration] = roles
    require(set(result['configurations']) == set(CONFIGURATIONS), 'all four genuine configuration exports are required')
    return result



def validate_devices(ir, unit, optimized):
    """Only the real Kernel9 aligned, fenced volatile controller primitives."""
    from audit_kernel import _ir_definition_body, _line_functions
    validate(ir, unit, optimized=optimized)
    if unit.get('role') != 'kernel':
        require(not any(r.get('stable_id', '').startswith('lemmasim.device-') for r in unit.get('used_execution_ops', [])),
                'device execution authority escaped kernel')
        return set(), []
    owners = _line_functions(ir.splitlines())
    sites, report = set(), []
    expected = {'read32', 'write32', 'read64', 'write64'}
    observed = set()
    for row in unit['functions']:
        if not row['source'].startswith('Lemma.Platform.LemmaSim.IO.'): continue
        operation = row['source'].rsplit('.', 1)[1]
        require(operation in expected and operation not in observed, 'unknown or duplicate controller primitive')
        observed.add(operation)
        write, bits = operation.startswith('write'), int(operation[-2:])
        width = bits // 8
        require(row['args'] == (['u64', 'u64'] if write else ['u64']) and
                row['effects'] == ['checked-access', 'mmio-write' if write else 'mmio-read', 'io-order'],
                'controller primitive signature/effects differ')
        body = _ir_definition_body(ir, row['symbol'])
        regions = [(0x10001000, 0x10001200), (0xc000004, 0xc000048 if unit.get("configuration") in INTEGRATED_CONFIGURATIONS else 0xc00003c),
                   (0xc002080, 0xc002084), (0xc201000, 0xc201008),
                   (0xc00004c, 0xc000050)] if width == 4 else [
                   (0x10010000, 0x10011000), (0x10011000, 0x10012000), *([(0x10012000,0x10012400)] if unit.get('configuration') in INTEGRATED_CONFIGURATIONS else []), (0x10014000, 0x10016000)]
        if not optimized:
            require([int(v) for v in re.findall(r'icmp uge i64 %arg0, (\d+)', body)] == [a for a, _ in regions] and
                    [int(v) for v in re.findall(r'icmp ule i64 %arg0, (\d+)', body)] == [b-width for _, b in regions] and
                    len(re.findall(r'and i64 %arg0, '+str(width-1)+r'$', body, re.M)) == 1,
                    'controller primitive aperture/alignment differs')
        located = {i for i, line in enumerate(ir.splitlines()) if owners[i] == row['symbol'] and
                   re.search(r'\b(?:load|store) volatile i'+str(bits)+r'\b', line)}
        require(len(located) == (1 if optimized else len(regions)), 'controller volatile access inventory differs')
        sites |= located
        report.append({'source':row['source'], 'function':row['symbol'], 'width_bytes':width,
                       'direction':'write' if write else 'read', 'access_sites':len(located),
                       'apertures':regions, 'optimized':optimized,
                       'scope':'exact pinned Kernel9 guarded lowering; no connected execution claim'})
    require(observed == expected, 'incomplete real controller primitive family')
    return sites, report


def readonly_lookup(ir, unit, *, optimized):
    from school_target import selected as school_selected, readonly_lookup as school_readonly_lookup
    if school_selected(unit):return school_readonly_lookup(ir,unit,optimized=optimized)
    return _readonly_lookup(ir,unit,optimized=optimized)

def _readonly_lookup(ir, unit, *, optimized):
    """Pin every table and independently require a dominating unsigned index bound.

    This is a new exact-corpus authority, not permission for arbitrary readonly
    globals. Unknown element types, pointer escapes, uses or CFG forms reject.
    """
    from audit_kernel import _ir_definition_body, _line_functions, _structured_ir_blocks, _structured_successors, _structured_reachable
    validate(ir, unit, optimized=optimized)
    lines = ir.splitlines()
    globals_ = [line.strip() for line in lines if re.match(r'^\s*@', line)]
    if not globals_: return set(), [], set()
    require(optimized, 'pre-optimization module acquired a global')
    rows = {r['symbol']:r for r in unit['functions']}
    owners = _line_functions(lines)
    sites, tables, removed = set(), [], set()
    if role_key(unit) == 'notebook':
        # Preserve the existing exact five-row ControlRender pointer-PHI
        # supplement and capture-offset supplement. Its independent literal,
        # selection, column-bound, CFG and pointer-use checks remain intact.
        from package_notebook_target import readonly_lookup as package_lookup
        sites, tables, removed = package_lookup(ir, unit)
    for declaration in globals_:
        if declaration in removed: continue
        match = re.fullmatch(r'@(switch\.table\.([-A-Za-z0-9_.$]+)) = private unnamed_addr constant \[(\d+) x i64\] \[(.*)\], align 8', declaration)
        require(match is not None, 'unsupported readonly global form')
        table, _, size, raw = match.groups(); size = int(size)
        candidates = [symbol for symbol in rows if table == 'switch.table.'+symbol or table.startswith('switch.table.'+symbol+'.')]
        require(len(candidates) == 1 and 1 <= size <= 256, 'readonly table owner or bounded extent differs')
        symbol = candidates[0]; row = rows[symbol]
        tokens = raw.split(', ')
        require(len(tokens) == size and all(re.fullmatch(r'i64 (?:-?\d+|poison)', token) for token in tokens), 'readonly table value inventory differs')
        values = [None if token == 'i64 poison' else int(token[4:]) for token in tokens]
        body = '\n'.join(line.split(';', 1)[0].rstrip()
                         for line in _ir_definition_body(ir, symbol).splitlines())
        require(len(re.findall('@'+re.escape(table)+r'(?![A-Za-z0-9_.$-])', ir)) == 2, 'readonly table use or alias differs')
        gep = re.findall(r'(%[-\w.$]+) = getelementptr inbounds(?: nuw)? \['+str(size)+r' x i64\], ptr @'+re.escape(table)+r', i64 0, i64 (%[-\w.$]+)', body)
        require(len(gep) == 1, 'readonly table lacks one direct bounded GEP')
        pointer, index = gep[0]
        loads = re.findall(r'(%[-\w.$]+) = load i64, ptr '+re.escape(pointer)+r', align 8', body)
        require(len(loads) == 1 and len(re.findall(re.escape(pointer)+r'(?![A-Za-z0-9_.$-])', body)) == 2,
                'readonly pointer escapes its sole load')
        compared = index
        zext = re.findall(re.escape(index)+r' = zext(?: nneg)? i(8|32) (%[-\w.$]+) to i64', body)
        width = '64'
        if zext: width, compared = zext[0]
        blocks = _structured_ir_blocks(body)
        successors = dict(_structured_successors(blocks))
        # Account for every switch edge; the historical branch helper does not.
        for block, block_lines in blocks.items():
            starts = [i for i, line in enumerate(block_lines) if line.startswith('switch ')]
            if starts:
                require(len(starts) == 1 and block_lines[-1] == ']', 'unsupported multiline switch CFG')
                start = starts[0]
                head = re.fullmatch(r'switch i(8|32|64) %[-\w.$]+, label %([-\w.$]+) \[', block_lines[start])
                cases = [re.fullmatch(r'i(8|32|64) (-?\d+), label %([-\w.$]+)', line)
                         for line in block_lines[start+1:-1]]
                require(head is not None and cases and all(cases) and
                        all(row[1] == head[1] for row in cases) and
                        len({row[2] for row in cases}) == len(cases), 'malformed or repeated switch cases')
                successors[block] = (head[2], *(row[3] for row in cases))
                require(all(dest in blocks for dest in successors[block]), 'switch targets an unknown block')
        located_blocks = [block for block, block_lines in blocks.items() if any('@'+table+',' in line for line in block_lines)]
        require(len(located_blocks) == 1, 'readonly load block inventory differs')
        target = located_blocks[0]
        def dominates_true(block, condition):
            branch = re.fullmatch(r'br i1 '+re.escape(condition)+r', label %([-\w.$]+), label %([-\w.$]+)', blocks[block][-1])
            if not branch: return False
            success = branch[1]
            filtered = {name:tuple(dest for dest in dests if (name,dest) != (block,success)) for name,dests in successors.items()}
            return not _structured_reachable(filtered, 'entry', target) and _structured_reachable(successors, success, target)
        guarded = [(block, match[1]) for block, block_lines in blocks.items() for line in block_lines
                   if (match := re.fullmatch(r'(%[-\w.$]+) = icmp ult i'+width+' '+re.escape(compared)+', '+str(size), line))
                   and dominates_true(block, match[1])]
        require(len(guarded) == 1, 'readonly lookup lacks a dominating exact unsigned extent guard')
        guard = guarded[0][0]
        if None in values:
            # Poison holes are never valid observations. Check the bit mask
            # independently of the complete body pin, including its polarity
            # and dominance over this table's actual load.
            visible = sum(1 << ordinal for ordinal, value in enumerate(values) if value is not None)
            holes = []
            for block, block_lines in blocks.items():
                if len(block_lines) != 4: continue
                mask_index = re.fullmatch(r'(%[-\w.$]+) = trunc nuw i64 '+re.escape(index)+r' to i(8|16|32|64)', block_lines[0])
                if not mask_index: continue
                shifted = re.fullmatch(r'(%[-\w.$]+) = lshr i'+mask_index[2]+r' (-?\d+), '+re.escape(mask_index[1]), block_lines[1])
                if not shifted: continue
                bit = re.fullmatch(r'(%[-\w.$]+) = trunc i'+mask_index[2]+' '+re.escape(shifted[1])+r' to i1', block_lines[2])
                if (bit and size <= int(mask_index[2]) and
                        int(shifted[2]) % (1 << int(mask_index[2])) == visible and dominates_true(block, bit[1])):
                    holes.append(block)
            require(len(holes) == 1, 'readonly poison holes lack exact dominating exclusion mask')
        located = {i for i,line in enumerate(lines) if owners[i] == symbol and
                   re.fullmatch(r'\s*'+re.escape(loads[0])+r' = load i64, ptr '+re.escape(pointer)+r', align 8\s*',line)}
        require(len(located) == 1, 'readonly exact load site differs')
        sites |= located; removed.add(declaration)
        tables.append({'source':row['source'], 'function':symbol, 'global':table, 'values':values,
                       'element_bits':64, 'alignment_bytes':8, 'index_bound':size, 'guarded_loads':1,
                       'readonly':True, 'guard':guard, 'literal_schema':'lemma-multimodal-exact-corpus/1'})
    return sites, tables, removed


# Actual pinned LLVM20 O2 Kernel9 export has these six new table owners. Full
# corpus authority is required first; ordinary object/companion byte equality,
# exact case domains, relocations, owner bounds and unsigned JR guards remain
# independently enforced by audit_kernel. No User image gets this authority.
JUMP_SPECS = {
    'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordMultimodal':
        ('kernel', 7, ['u64']*2, [], list(range(96, 103))),
    'Lemma.Platform.LemmaSim.DescriptorDTB.leafPropertyMultimodal':
        ('kernel', 71, ['u64']*4, ['checked-access','physical-read','physical-write'],
         [32,33,34,35,38,51,98,99,100,101,102]),
    'Lemma.Platform.LemmaSim.DescriptorDTB.tokenStepMultimodal':
        ('kernel', 9, ['u32','u32',*(['u64']*5)], ['checked-access','physical-read','physical-write'], [1,2,3,4,9]),
    'Lemma.Platform.LemmaSim.Descriptor.geometryMultimodal':
        ('kernel', 7, ['u64'], ['checked-access','mmio-read','io-order','physical-read','physical-write'], list(range(1,8))),
    'Lemma.Platform.LemmaSim.MultimodalService.call':
        ('kernel', 12, ['u64']*6, ['checked-access','mmio-read','mmio-write','io-order','physical-read','physical-write'], list(range(12))),
    'Lemma.Platform.LemmaSim.NotebookKernel.deviceCallMultimodalAt':
        ('kernel', 6, ['u64']*4, ['checked-access','mmio-read','mmio-write','io-order','machine-state','physical-read','physical-write','firmware-call'], [64,65,66,68,69]),
}


def jump_spec(ir, unit, source, symbol):
    spec=JUMP_SPECS.get(source)
    if source=='Lemma.Platform.LemmaSim.MultimodalService.call':
        version=[row for row in unit.get('functions',[]) if canonical(row['source'])=='Lemma.Platform.LemmaSim.MultimodalService.version']
        if version:
            from audit_kernel import _ir_definition_body
            require(len(version)==1 and version[0]['args']==[] and version[0]['effects']==[] and
                    re.fullmatch(r'\s*entry:\s*ret i64 2\s*',_ir_definition_body(ir,version[0]['symbol'])),
                    'ownedIO jump owner lacks exact service version2')
            spec=('kernel',19,['u64']*6,['checked-access','mmio-read','mmio-write','io-order','physical-read','physical-write'],list(range(19)))
    if unit.get('configuration') in INTEGRATED_CONFIGURATIONS and source=='Lemma.Platform.LemmaSim.DescriptorDTB.tokenStepExecuted':
        spec=('kernel',9,['u32','u32',*(['u64']*5)],['checked-access','physical-read','physical-write'],[1,2,3,4,9])
    if not selected(unit) or spec is None: return None
    validate(ir, unit, optimized=True)
    rows = [row for row in unit['functions'] if canonical(row['source']) == source]
    require(len(rows) == 1 and rows[0]['symbol'] == symbol and unit['role'] == 'kernel',
            'backend table escaped its actual Kernel9 owner')
    return spec


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', type=Path, nargs=4, required=True, metavar='GENUINE_CONFIG_OUTPUT')
    args = parser.parse_args()
    print(json.dumps(collect(args.collect), indent=2))
