#!/usr/bin/env python3
"""Actual isolated RV64 arithmetic OOM/death/deadline/cancellation observations.

Raw pen is the only answer/editor stimulus. A separately linked Laboratory
server fills real owned objects, faults or withholds a reply. The observer never
writes a guest record/result or substitutes checker/kernel execution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import time
from check_math_session import MathChecker
from check_live_notebook import Input,idle,require,sha,visible_pixels
from store_oracle import recover

MANAGED_OOM_CONFIGURATION='lemmasim-silicon-power-arithmetic-oom-development'

def managed_oom_route(unit,ir):
    """Inspect real emitted calls independently of target events and catalog labels.

    The whole image still passes its ordinary strict audit at public startup.
    This observer additionally refuses to call a scalar allocation failure a
    managed constructor failure. It does not execute or interpret target code.
    """
    from audit_kernel import _ir_definition_body,parse_definitions_and_calls
    require(unit.get('contract_version')=='core0-user-v0.2' and
            unit.get('role')=='user' and unit.get('image_key')=='arithmetic' and
            unit.get('configuration')==MANAGED_OOM_CONFIGURATION,
            'managed OOM requires the exact User2 Arithmetic Laboratory unit')
    names={r['source']:r['symbol'] for r in unit['functions']}
    require(len(names)==len(unit['functions']) and len(set(names.values()))==len(names),
            'duplicate emitted source or symbol identity')
    def suffix(name):
        rows=[s for s in names if s.endswith(name)]
        require(len(rows)==1,'missing or ambiguous managed OOM source: '+name)
        return rows[0]
    p='Lemma.User.Runtime.Arena.';m='Lemma.User.Runtime.ManagedRecords.'
    entry='Lemma.Mathematics.ManagedRational.compareFiveSix'
    generated=entry+'.__lemma_managed_v02.'
    main='Lemma.Services.Arithmetic.Server.main'
    step=suffix('Lemma.Services.Arithmetic.Server.step')
    process=suffix('Lemma.Services.Arithmetic.Server.process')
    pressure=suffix('Lemma.Services.Arithmetic.Server.pressureStep')
    positive=suffix('Lemma.Mathematics.ManagedSubmission.positiveRational')
    allocate=suffix('Lemma.User.Runtime.Arena.allocate')
    routes=[(main,step),(step,process),(process,'Lemma.Mathematics.ManagedSubmission.check'),
      ('Lemma.Mathematics.ManagedSubmission.check',positive),
      (positive,generated+entry),(generated+entry,generated+'Lemma.Mathematics.ManagedRational.make'),
      (generated+'Lemma.Mathematics.ManagedRational.make',m+'allocate'),
      (m+'allocate',p+'newBytes'),(p+'newBytes',allocate),
      (main,pressure),(pressure,p+'newBox'),(p+'newBox',allocate),(allocate,p+'exhausted')]
    required={s for pair in routes for s in pair}|{p+'capacity'}
    require(required<=set(names),'managed OOM emitted constructor/runtime closure missing')
    bodies={s:_ir_definition_body(ir,names[s]) for s in required}
    require(all(body is not None for body in bodies.values()),'managed OOM emitted function body missing')
    for caller,callee in routes:
        require(names[callee] in parse_definitions_and_calls(bodies[caller])[2],
                'managed OOM emitted call route missing: '+caller+' -> '+callee)
    def call(caller,callee,args):
        require(len(re.findall(r'call \{ i64, i64 \} @'+re.escape(names[callee])+r'\('+args+r'\)',bodies[caller]))==1,
                'managed OOM constructor/helper arguments differ: '+caller)
    call(generated+'Lemma.Mathematics.ManagedRational.make',m+'allocate',r'i64 1, i64 24')
    call(m+'allocate',p+'newBytes',r'i64 %arg1')
    call(positive,generated+entry,r'i64 %arg0, i64 %arg1')
    require(re.search(r'icmp eq i64 %arg0, 1',bodies['Lemma.Mathematics.ManagedSubmission.check']) and
            re.search(r'icmp ult i64 %arg2, 8',bodies[positive]) and
            re.search(r'i32 signext 31, i64',bodies[main]) and
            re.search(r'icmp eq i64 %arg0, 1',bodies[main]),
            'managed OOM exact goal/budget/pressure mode path differs')
    require(re.fullmatch(r'\s*entry:\s*ret i8 237\s*',bodies[p+'exhausted']) and
            re.fullmatch(r'\s*entry:\s*ret i64 31\s*',bodies[p+'capacity']),
            'managed OOM arena capacity/exhaustion code differs')
    return {'contract':'core0-user-v0.2','constructor':'Lemma.Mathematics.ManagedRational.Fraction.mk',
      'shape':1,'bytes':24,'arena_capacity':31,'actual_failure_code':237,
      'emitted_routes':[list(pair) for pair in routes]}

SUMS_OOM_CONFIGURATION='lemmasim-silicon-sums-arithmetic-oom-development'

def sums_oom_route(unit,ir):
    from audit_kernel import _ir_definition_body,parse_definitions_and_calls
    from managed_sums import validate as validate_sums
    require(unit.get('contract_version')=='core0-user-v0.3' and unit.get('role')=='user' and
      unit.get('image_key')=='arithmetic' and unit.get('configuration')==SUMS_OOM_CONFIGURATION,
      'sum OOM requires the exact User3 isolated Laboratory unit')
    require(validate_sums(ir,unit,optimized=False) is not None,'ordinary sum/tag/layout closure absent')
    names={row['source']:row['symbol'] for row in unit['functions']}
    require(len(names)==len(unit['functions']) and len(set(names.values()))==len(names),'duplicate emitted source/symbol')
    def suffix(name):
        matches=[source for source in names if source.endswith(name)]
        require(len(matches)==1,'missing or ambiguous sum OOM source: '+name)
        return matches[0]
    server='Lemma.Services.Arithmetic.ServerV3.';p='Lemma.User.Runtime.Arena.'
    m='Lemma.User.Runtime.ManagedSums.';source='Lemma.Mathematics.ManagedResult.'
    entry=source+'compareFiveSix';generated=entry+'.__lemma_managed_sums_v03.'
    main=server+'main';step=suffix(server+'step');process=suffix(server+'processV3')
    pressure=suffix(server+'pressureStep');submission='Lemma.Mathematics.ManagedSumSubmission.'
    positive=suffix(submission+'positiveRational');allocate=suffix(p+'allocate')
    routes=[(main,step),(step,process),(process,submission+'check'),(submission+'check',positive),
      (positive,generated+entry),(generated+entry,generated+source+'compare'),
      (generated+source+'compare',m+'allocate'),(m+'allocate',p+'newBytes'),
      (p+'newBytes',allocate),(main,pressure),(pressure,p+'newBox'),
      (p+'newBox',allocate),(allocate,p+'exhausted')]
    required={source for pair in routes for source in pair}|{p+'capacity'}
    require(required<=set(names),'sum OOM constructor/runtime path missing')
    bodies={source:_ir_definition_body(ir,names[source]) for source in required}
    require(all(body is not None for body in bodies.values()),'sum OOM emitted body missing')
    for caller,callee in routes:
        require(names[callee] in parse_definitions_and_calls(bodies[caller])[2],
                'sum OOM emitted route missing: '+caller+' -> '+callee)
    require(re.search(r'icmp eq i64 %arg0, 1',bodies[submission+'check']) and
      re.search(r'icmp ult i64 %arg2, 8',bodies[positive]) and
      re.search(r'i32 signext 31, i64',bodies[main]) and
      re.search(r'icmp eq i64 %arg0, 1',bodies[main]),'sum OOM goal/budget/pressure mode differs')
    require(re.fullmatch(r'\s*entry:\s*ret i8 237\s*',bodies[p+'exhausted']) and
      re.fullmatch(r'\s*entry:\s*ret i64 31\s*',bodies[p+'capacity']),
      'sum OOM actual capacity/failure differs')
    return {'contract':'core0-user-v0.3','constructor':'Lemma.Mathematics.ManagedResult.Comparison.unequal',
      'shape':1,'tag':1,'bytes':16,'arena_capacity':31,'actual_failure_code':237,
      'emitted_routes':[list(pair) for pair in routes]}

BYTES_OOM_CONFIGURATION='lemmasim-silicon-bytes-arithmetic-oom-development'

def bytes_oom_route(unit,ir):
    """Inspect the actual ordinary ByteArray allocation route, not event labels."""
    from audit_kernel import _ir_definition_body,parse_definitions_and_calls
    from managed_bytes import validate as validate_bytes, GENERATED, PREFIX
    from arithmetic_bytes_identity import validate as validate_identity
    require(unit.get('contract_version')=='core0-user-v0.4' and unit.get('role')=='user' and
      unit.get('image_key')=='arithmetic' and unit.get('configuration')==BYTES_OOM_CONFIGURATION,
      'bytes OOM requires the exact User4 isolated Laboratory unit')
    require(validate_bytes(ir,unit,optimized=False) is not None and
      validate_identity(ir,unit,optimized=False) is not None,
      'ordinary ByteArray and complete implementation/version closure absent')
    names={row['source']:row['symbol'] for row in unit['functions']}
    require(len(names)==len(unit['functions']) and len(set(names.values()))==len(names),
      'duplicate emitted bytes source/symbol')
    def suffix(name):
        matches=[source for source in names if source.endswith(name)]
        require(len(matches)==1,'missing or ambiguous bytes OOM source: '+name)
        return matches[0]
    server='Lemma.Services.Arithmetic.ServerV4.';arena='Lemma.User.Runtime.Arena.'
    runtime='Lemma.User.Runtime.ManagedBytes.';submission='Lemma.Mathematics.ManagedByteSubmissionAction.'
    main=server+'main';step=suffix(server+'step');process=suffix(server+'processV4')
    pressure=suffix(server+'pressureStep');positive=suffix(submission+'positiveRational')
    allocate=suffix(arena+'allocate');bytes_allocate=suffix(runtime+'allocate')
    entry=GENERATED+PREFIX+'compareFiveSix';payload=GENERATED+PREFIX+'payload'
    empty=GENERATED+PREFIX+'empty'
    routes=[(main,step),(step,process),(process,submission+'check'),(submission+'check',positive),
      (positive,entry),(entry,payload),(payload,empty),(empty,runtime+'emptyWithCapacity'),
      (runtime+'emptyWithCapacity',bytes_allocate),(bytes_allocate,arena+'newBytes'),
      (arena+'newBytes',allocate),(main,pressure),(pressure,arena+'newBox'),
      (arena+'newBox',allocate),(allocate,arena+'exhausted')]
    required={source for pair in routes for source in pair}|{arena+'capacity'}
    require(required<=set(names),'bytes OOM ordinary allocation/runtime path missing')
    bodies={source:_ir_definition_body(ir,names[source]) for source in required}
    require(all(body is not None for body in bodies.values()),'bytes OOM emitted body missing')
    for caller,callee in routes:
        require(names[callee] in parse_definitions_and_calls(bodies[caller])[2],
          'bytes OOM emitted route missing: '+caller+' -> '+callee)
    def call(caller,callee,args):
        require(len(re.findall(r'call \{ i64, i64 \} @'+re.escape(names[callee])+r'\('+args+r'\)',bodies[caller]))==1,
          'bytes OOM actual allocation operands differ: '+caller)
    call(positive,entry,r'i64 %arg0, i64 %arg1')
    call(entry,payload,r'i64 16, i64 %arg0, i64 %arg1')
    call(bytes_allocate,arena+'newBytes',r'i64 64')
    require(re.search(r'icmp eq i64 %arg0, 1',bodies[submission+'check']) and
      re.search(r'icmp ult i64 %arg2, 8',bodies[positive]) and
      re.search(r'i32 signext 31, i64',bodies[main]) and
      re.search(r'icmp eq i64 %arg0, 1',bodies[main]),'bytes OOM goal/budget/pressure mode differs')
    require(re.fullmatch(r'\s*entry:\s*ret i8 237\s*',bodies[arena+'exhausted']) and
      re.fullmatch(r'\s*entry:\s*ret i64 31\s*',bodies[arena+'capacity']),
      'bytes OOM actual capacity/failure differs')
    return {'contract':'core0-user-v0.4','ordinary_source':PREFIX+'payload',
      'logical_payload_bytes':16,'arena_slot_bytes':64,'maximum_payload':48,
      'arena_capacity':31,'actual_failure_code':237,
      'emitted_routes':[list(pair) for pair in routes]}

ARRAY_OOM_CONFIGURATION='lemmasim-silicon-array-arithmetic-oom-development'

def array_oom_route(unit,ir):
    """Closed genuine Array code plus the actual pressure/allocator call path."""
    from audit_kernel import _ir_definition_body,parse_definitions_and_calls
    from managed_array import validate as validate_array,GENERATED,PREFIX
    from arithmetic_array_identity import validate as validate_identity
    require(unit.get('contract_version')=='core0-user-v0.5' and unit.get('role')=='user' and
      unit.get('image_key')=='arithmetic' and unit.get('configuration')==ARRAY_OOM_CONFIGURATION,
      'Array OOM requires the exact User5 isolated Laboratory unit')
    require(validate_array(ir,unit,optimized=False) is not None and
      validate_identity(ir,unit,optimized=False) is not None,
      'ordinary Array and complete implementation/version closure absent')
    names={row['source']:row['symbol'] for row in unit['functions']}
    require(len(names)==len(unit['functions']) and len(set(names.values()))==len(names),
      'duplicate emitted Array source/symbol')
    def suffix(name):
        matches=[source for source in names if source.endswith(name)]
        require(len(matches)==1,'missing or ambiguous Array OOM source: '+name)
        return matches[0]
    server='Lemma.Services.Arithmetic.ServerV5.';arena='Lemma.User.Runtime.Arena.'
    runtime='Lemma.User.Runtime.ManagedArray.';submission='Lemma.Mathematics.ManagedArraySubmissionAction.'
    main=server+'main';step=suffix(server+'step');process=suffix(server+'processV5')
    pressure=suffix(server+'pressureStep');positive=suffix(submission+'positiveRational')
    allocate=suffix(arena+'allocate');array_allocate=suffix(runtime+'allocate')
    entry=GENERATED+PREFIX+'compareFiveSix';payload=GENERATED+PREFIX+'payload'
    routes=[(main,step),(step,process),(process,submission+'check'),(submission+'check',positive),
      (positive,entry),(entry,payload),(payload,runtime+'emptyWithCapacity'),
      (runtime+'emptyWithCapacity',array_allocate),(array_allocate,arena+'newBytes'),
      (arena+'newBytes',allocate),(main,pressure),(pressure,arena+'newBox'),
      (arena+'newBox',allocate),(allocate,arena+'exhausted')]
    required={source for pair in routes for source in pair}|{arena+'capacity'}
    require(required<=set(names),'Array OOM ordinary allocation/runtime path missing')
    bodies={source:_ir_definition_body(ir,names[source]) for source in required}
    require(all(body is not None for body in bodies.values()),'Array OOM emitted body missing')
    for caller,callee in routes:
        require(names[callee] in parse_definitions_and_calls(bodies[caller])[2],
          'Array OOM emitted route missing: '+caller+' -> '+callee)
    def call(caller,callee,args):
        require(len(re.findall(r'call \{ i64, i64 \} @'+re.escape(names[callee])+r'\('+args+r'\)',bodies[caller]))==1,
          'Array OOM actual allocation operands differ: '+caller)
    call(positive,entry,r'i64 %arg0, i64 %arg1')
    call(entry,payload,r'i64 2, i64 %arg0, i64 %arg1')
    call(array_allocate,arena+'newBytes',r'i64 64')
    require(re.search(r'icmp eq i64 %arg0, 1',bodies[submission+'check']) and
      re.search(r'icmp ult i64 %arg2, 8',bodies[positive]) and
      re.search(r'i32 signext 31, i64',bodies[main]) and
      re.search(r'icmp eq i64 %arg0, 1',bodies[main]),'Array OOM goal/budget/pressure mode differs')
    require(re.fullmatch(r'\s*entry:\s*ret i8 237\s*',bodies[arena+'exhausted']) and
      re.fullmatch(r'\s*entry:\s*ret i64 31\s*',bodies[arena+'capacity']),
      'Array OOM actual capacity/failure differs')
    return {'contract':'core0-user-v0.5','ordinary_source':PREFIX+'payload',
      'element_bits':64,'logical_payload_elements':2,'arena_slot_bytes':64,'maximum_elements':6,
      'arena_capacity':31,'actual_failure_code':237,
      'emitted_routes':[list(pair) for pair in routes]}

STRING_OOM_CONFIGURATION='lemmasim-silicon-string-arithmetic-oom-development'

def string_oom_route(unit,ir):
    """Real ordinary hex/String workload's first owned byte-buffer allocation."""
    from audit_kernel import _ir_definition_body,parse_definitions_and_calls
    from managed_string import validate as validate_string,GENERATED,PREFIX,ENTRY
    from arithmetic_string_identity import validate as validate_identity,canonical
    require(unit.get('contract_version')=='core0-user-v0.6' and unit.get('role')=='user'
      and unit.get('image_key')=='arithmetic' and unit.get('configuration')==STRING_OOM_CONFIGURATION,
      'String OOM requires the exact User6 Laboratory unit')
    require(validate_string(ir,unit,optimized=False) is not None and validate_identity(ir,unit,optimized=False) is not None,
      'String OOM genuine ordinary IR/complete implementation authority absent')
    names={canonical(row['source']):row['symbol'] for row in unit['functions']}
    require(len(names)==len(unit['functions']) and len(set(names.values()))==len(names),'String OOM source inventory duplicated')
    server='Lemma.Services.Arithmetic.ServerV6.';arena='Lemma.User.Runtime.Arena.';runtime='Lemma.User.Runtime.ManagedBytes.';submission='Lemma.Mathematics.ManagedStringSubmissionAction.'
    main=server+'main';pressure=server+'pressureStep';positive=submission+'positiveRational';entry=GENERATED+ENTRY;encoded=GENERATED+PREFIX+'encoded';empty=GENERATED+PREFIX+'empty';parse=GENERATED+PREFIX+'parse'
    routes=[(main,server+'step'),(server+'step',server+'processV6'),(server+'processV6',submission+'check'),(submission+'check',positive),(positive,entry),(entry,encoded),(encoded,empty),(empty,runtime+'emptyWithCapacity'),(runtime+'emptyWithCapacity',runtime+'allocate'),(runtime+'allocate',arena+'newBytes'),(arena+'newBytes',arena+'allocate'),(arena+'allocate',arena+'exhausted'),(main,pressure),(pressure,arena+'newBox'),(arena+'newBox',arena+'allocate'),(entry,parse),(parse,'Lemma.User.Runtime.ManagedString.fromByteArray')]
    required={source for pair in routes for source in pair}|{arena+'capacity'};require(required<=set(names),'String OOM actual allocation/UTF8 path absent')
    bodies={source:_ir_definition_body(ir,names[source]) for source in required};require(all(bodies.values()),'String OOM emitted body missing')
    for caller,callee in routes:require(names[callee] in parse_definitions_and_calls(bodies[caller])[2],'String OOM actual route missing: '+caller+' -> '+callee)
    require(re.search(r'call \{ i64, i64 \} @'+re.escape(names[encoded])+r'\(i64 16, i64 %arg0\)',bodies[entry]),'String OOM actual sixteen-byte encoding absent')
    require(re.search(r'call \{ i64, i64 \} @'+re.escape(names[arena+'newBytes'])+r'\(i64 64\)',bodies[runtime+'allocate']), 'String OOM actual slot extent differs')
    require(re.search(r'icmp eq i64 %arg0, 1',bodies[submission+'check']) and re.search(r'icmp ult i64 %arg2, 8',bodies[positive]) and re.search(r'i32 signext 31, i64',bodies[main]) and re.search(r'icmp eq i64 %arg0, 1',bodies[main]),'String OOM goal/budget/pressure mode differs')
    require(re.fullmatch(r'\s*entry:\s*ret i8 237\s*',bodies[arena+'exhausted']) and re.fullmatch(r'\s*entry:\s*ret i64 31\s*',bodies[arena+'capacity']),'String OOM actual capacity/status differs')
    return {'contract':'core0-user-v0.6','ordinary_source':ENTRY,'maximum_utf8_bytes':40,'logical_payload_bytes':16,'arena_slot_bytes':64,'arena_capacity':31,'actual_failure_code':237,'failure_phase':'first ByteArray allocation before String.ofByteArray; no completed String-object construction claim','emitted_routes':[list(pair) for pair in routes]}


def managed_oom_artifacts(directory,*,sums=False,bytes_payload=False,array_payload=False,string_payload=False):
    from managed_records import validate as validate_records
    if string_payload:
        from managed_string import validate as validate_records
    elif array_payload:
        from managed_array import validate as validate_records
    elif sums:
        from managed_sums import validate as validate_records
    elif bytes_payload:
        from managed_bytes import validate as validate_records
    configuration=STRING_OOM_CONFIGURATION if string_payload else ARRAY_OOM_CONFIGURATION if array_payload else BYTES_OOM_CONFIGURATION if bytes_payload else SUMS_OOM_CONFIGURATION if sums else MANAGED_OOM_CONFIGURATION
    server='Lemma.Services.Arithmetic.ServerV6' if string_payload else 'Lemma.Services.Arithmetic.ServerV5' if array_payload else 'Lemma.Services.Arithmetic.ServerV4' if bytes_payload else 'Lemma.Services.Arithmetic.ServerV3' if sums else 'Lemma.Services.Arithmetic.Server'
    directory=Path(directory).resolve();arithmetic=directory/'users/arithmetic'
    unit=json.loads((arithmetic/'unit.json').read_text())
    catalog=json.loads((directory/'user-image-catalog.json').read_text())
    audit=json.loads((directory/'audit.json').read_text())
    expected={'id':3,'key':'arithmetic','directory':'users/arithmetic',
      'source':server+'.main','module':server,
      'boot_role':'arithmetic-server','args':['u64']}
    rows=[r for r in catalog.get('images',[]) if r.get('key')=='arithmetic']
    require(catalog.get('configuration')==configuration and
            catalog.get('stage')=='supervisor' and len(rows)==1 and
            all(rows[0].get(k)==v for k,v in expected.items()),
            'managed OOM exact separately linked Arithmetic catalog differs')
    require(audit.get('status')=='PASS' and audit.get('configuration')==configuration and
            audit.get('image_sha256')==sha(directory/'image.elf') and
            audit['user_images']['arithmetic']['image_sha256']==sha(arithmetic/'image.elf'),
            'managed OOM requires the exact audited combined and Arithmetic ELF bytes')
    pre=(arithmetic/'program.ll').read_text();optimized=(arithmetic/'program.opt.ll').read_text()
    require(validate_records(pre,unit,optimized=False) is not None and
            validate_records(optimized,unit,optimized=True) is not None,
            'managed OOM genuine ordinary source/checked helper closure absent')
    if string_payload:
        from arithmetic_string_identity import validate as validate_identity
        require(validate_identity(optimized,unit,optimized=True) is not None,'String complete optimized implementation authority absent')
    elif array_payload:
        from arithmetic_array_identity import validate as validate_identity
        require(validate_identity(optimized,unit,optimized=True) is not None,'Array complete optimized implementation authority absent')
    elif bytes_payload:
        from arithmetic_bytes_identity import validate as validate_identity
        require(validate_identity(optimized,unit,optimized=True) is not None,'bytes complete optimized implementation authority absent')
    result=string_oom_route(unit,pre) if string_payload else array_oom_route(unit,pre) if array_payload else bytes_oom_route(unit,pre) if bytes_payload else sums_oom_route(unit,pre) if sums else managed_oom_route(unit,pre)
    files=[directory/'audit.json',directory/'image.elf',directory/'user-image-catalog.json',
      arithmetic/'image.elf',arithmetic/'unit.json',arithmetic/'program.ll',arithmetic/'program.opt.ll']
    result['artifacts']={str(p.relative_to(directory)):sha(p) for p in files}
    return result

class IsolationChecker(MathChecker):
    def __init__(self,args):
        super().__init__(args)
        if getattr(args,'guest_source_root',None) is not None:
            self.report['bounds']['guest_source_root']=str(args.guest_source_root.resolve())
        self.allowed_error=False
        self.report.update(schema='lemmasim-arithmetic-isolation/1',case=args.case,
            scope='actual scalar Lean isolated arithmetic process and copied IPC; managed source constructors/proof kernel/full verifier remain unfinished')
        self.report['observer_sources']['scripts/check_arithmetic_isolation.py']=sha(Path(__file__))
        if args.require_managed_constructor or args.require_sums_constructor or getattr(args,'require_bytes_payload',False) or getattr(args,'require_array_payload',False) or getattr(args,'require_string_payload',False):
            self.report['scope']='actual ordinary Lean payload constructor OOM in isolated RV64 Arithmetic; bounded checked heap, pen/Save/cold recovery; general managed language/proof kernel remain unfinished'
    def settle(self,session,tick,completed=None):
        def done(state):
            rows=self.rows(session)
            require(not any(r[0] in (0x41f,0x424) for r in rows),'guest formatted or storage failed')
            if not self.allowed_error:
                require(not any(r[0] in (0x454,0xd4,0xf4) for r in rows),'unexpected early checker/process failure')
            else:
                server=[r[1] for r in rows if r[0]==0xf1 and r[2]==2]
                require(len(server)==1,'third image identity missing or duplicated')
                require(all(r[1]==server[0] for r in rows if r[0]==0xf4),'another service died')
                require(all(self.args.case=='fault' and r[1]==13 and r[3]==0x500000 for r in rows if r[0]==0xd4),'unexpected architectural fault')
            commits=[r for r in rows if r[0] in (0x421,0x423,0x424)]
            return state['ticks']>=tick+2000000 and idle(state) and (not commits or commits[-1][0]==0x421) and (completed is None or state['devices']['paper']['completed']>completed)
        return session.wait(done,self.args.action_seconds,quantum=200000)
    def raw_click(self,session,stream,x,y):
        first=len(stream.events);stream.tick=session.inspect()['machine']['ticks']+10000
        stream.sample(x,y,2048,True);stream.sample(x,y,0,False)
        session.admit(stream.events[first:]);return stream.events[-1][1]
    def ink(self,session,stream,name):
        first=len(stream.events);stream.tick=session.inspect()['machine']['ticks']+10000
        stream.stroke(name,1,1,6,1700);session.admit(stream.events[first:]);return first,stream.events[-1][1]
    def execute(self):
        if self.args.require_managed_constructor or self.args.require_sums_constructor or getattr(self.args,'require_bytes_payload',False) or getattr(self.args,'require_array_payload',False) or getattr(self.args,'require_string_payload',False):
            self.report['managed_constructor_admission']=managed_oom_artifacts(self.args.guest_build,sums=self.args.require_sums_constructor,bytes_payload=getattr(self.args,'require_bytes_payload',False),array_payload=getattr(self.args,'require_array_payload',False),string_payload=getattr(self.args,'require_string_payload',False))
        original=sha(self.args.disk);disk=self.directory/'live-input.raw';shutil.copyfile(self.args.disk,disk)
        live=self.session('live',disk);self.report['identity']=live.identity
        if self.args.require_managed_constructor or self.args.require_sums_constructor or getattr(self.args,'require_bytes_payload',False) or getattr(self.args,'require_array_payload',False) or getattr(self.args,'require_string_payload',False):
            require(live.identity['guest']==self.report['managed_constructor_admission']['artifacts']['image.elf'],
                    'live machine did not consume the admitted managed OOM ELF')
        self.report['boot']=live.boot()
        rows=self.rows(live);mode={'oom':1,'fault':2,'stall':3}[self.args.case]
        start=[r for r in rows if r[0]==0x456]
        require(start==[(0x456,mode,31 if mode==1 else 0,6 if getattr(self.args,'require_string_payload',False) else 5 if getattr(self.args,'require_array_payload',False) else 4 if getattr(self.args,'require_bytes_payload',False) else 3 if self.args.require_sums_constructor else 1,10000000)],'server did not execute actual declared mode/object pressure/deadline')
        if getattr(self.args,'require_string_payload',False):
            from math_oracle import STRING_EXECUTION_IDENTITIES
            require([row for row in rows if row[0]==0x45c]==[(0x45c,*STRING_EXECUTION_IDENTITIES)],
                    'actual Protocol6 String implementation/lowering/runtime/resource handshake differs')
        if getattr(self.args,'require_array_payload',False):
            from math_oracle import ARRAY_EXECUTION_IDENTITIES
            require([row for row in rows if row[0]==0x45c]==[(0x45c,*ARRAY_EXECUTION_IDENTITIES)],
                    'actual Protocol5 implementation/lowering/runtime/resource handshake differs')
        stream=Input(1650,2200,live.inspect()['machine']['ticks']+10000,100000,0)
        stream.sample(825,160,0,False);live.admit(stream.events)
        self.click(live,stream,'open course before isolated fault',320,140)
        prior_panel,prior_medium=live.export('before-check')
        prior_bytes,prior,_,_=self.record(prior_medium)
        require(prior['outcome']==0 and not prior['history'],'initial course already had manufactured evidence')
        if getattr(self.args,'require_string_payload',False):
            require(len(prior_bytes)==2496 and prior['format']=='lemma-mathematical-submission/7'
                    and prior['execution']['active']=={'origin':'Unknown'}
                    and all(entry=={'origin':'Unknown'} for entry in prior['execution']['history']),
                    'String OOM requires actual Document7 without manufactured evidence')
            self.report['string_protocol_document']={'status':'PASS','protocol':6,'document':7,
              'format_bytes':2496,'actual_handshake':(0x45c,*STRING_EXECUTION_IDENTITIES),
              'no_applicable_evidence_before_request':True}
        if getattr(self.args,'require_array_payload',False):
            require(len(prior_bytes)==2496 and prior['format']=='lemma-mathematical-submission/6' and
                    prior['execution']['active']=={'origin':'Unknown'} and
                    all(entry=={'origin':'Unknown'} for entry in prior['execution']['history']),
                    'Array OOM requires actual guest Document6 without manufactured evidence')
            self.report['array_protocol_document']={'status':'PASS','protocol':5,'document':6,
              'format_bytes':2496,'actual_handshake':(0x45c,*ARRAY_EXECUTION_IDENTITIES),
              'no_applicable_evidence_before_request':True}
        if self.args.require_managed_constructor or self.args.require_sums_constructor or getattr(self.args,'require_bytes_payload',False) or getattr(self.args,'require_array_payload',False) or getattr(self.args,'require_string_payload',False):
            require(prior['goal']==1 and prior['answer']==[0,1,0,0,0] and prior['budget']==8,
                    'managed OOM submitted object would not execute the admitted ordinary constructor')
        self.allowed_error=True
        submitted=len([r for r in self.rows(live) if r[0]==0x459])
        tick=self.raw_click(live,stream,40,245)
        state=live.wait(lambda s:len([r for r in self.rows(live) if r[0]==0x459])>submitted,self.args.action_seconds,quantum=10000)
        request=[r for r in self.rows(live) if r[0]==0x459][-1]
        self.report['submission']={'actual_guest_request':request,'observed_tick':state['ticks'],'raw_tick':tick}
        expected={'oom':237,'fault':96,'stall':93}[self.args.case]
        def expected_error(state):
            require(not any(r[0]==0x424 for r in self.rows(live)),'actual Store failure while checker pending')
            return any(r[0]==0x454 and r[1]==expected for r in self.rows(live))
        live.wait(expected_error,self.args.action_seconds,quantum=100000)
        self.settle(live,stream.events[-1][1]);self.wait_label(live,'SAVED',24,132)
        _,error_medium=live.export('after-error')
        require(self.record(error_medium)[0]==prior_bytes,'checker failure mutated acknowledged math record')
        require(not any(r[0]==0x450 and r[3]!=0 for r in self.rows(live)),'checker failure manufactured trusted evidence')
        if self.args.case=='oom':
            require(any(r[0]==0x455 and r[3:]==(237,0) for r in self.rows(live)),'OOM was not returned by real owned-object allocation')
            if self.args.require_managed_constructor or self.args.require_sums_constructor or getattr(self.args,'require_bytes_payload',False) or getattr(self.args,'require_array_payload',False) or getattr(self.args,'require_string_payload',False):
                result_rows=[r for r in self.rows(live) if r[0]==0x455 and r[1:3]==request[1:3]]
                require(len(result_rows)==1 and result_rows[0][3:]==(237,0),
                        'managed constructor OOM reply is not the actual submitted request/revision')
                self.report['managed_constructor_failure']={'status':'PASS','actual_status':237,
                  'goal':prior['goal'],'answer':prior['answer'],'budget':prior['budget'],
                  'actual_server_reply':result_rows[0],'live_slots':31,'no_evidence':True,'record_unchanged':True}
        if self.args.case=='fault':
            require(any(r[0]==0xd4 and r[1]==13 and r[3]==0x500000 for r in self.rows(live)),'unmapped user instruction never caused actual page fault')
            require(any(r[0]==0xf6 for r in self.rows(live)),'dead checker resources were not reaped')
        self.report['failed_request']={'status':'PASS','actual_error':expected,'math_sha256':hashlib.sha256(prior_bytes).hexdigest(),'no_new_evidence':True,'record_unchanged':True}
        # Ordinary ink remains available after each failure and survives cold.
        first,ink_tick=self.ink(live,stream,'ink after isolated checker failure')
        self.settle(live,ink_tick);self.wait_label(live,'SAVED',24,132)
        final_panel,final_medium=live.export('final')
        _,_,records=recover(final_medium.read_bytes());sample_sets=[]
        for key,record in records.items():
            if key[1]>0x10000 and len(record.payload)>=128:
                n=struct.unpack_from('<Q',record.payload,48)[0]
                sample_sets.append([struct.unpack_from('<9Q',record.payload,128+i*72) for i in range(n)])
        actual_samples=[sample for group in sample_sets for sample in group]
        require(all(sample in actual_samples for sample in stream.events[first:]),'post-failure raw ink was not constructed and persisted by guest')
        require(self.record(final_medium)[0]==prior_bytes,'post-failure writing changed mathematical record')
        if self.args.case=='stall':
            live.wait(lambda state:any(r[0]==0x45a and r[1]==request[1] and r[3] in (80,83) and r[4]==3 for r in self.rows(live)),self.args.action_seconds,quantum=1000000)
            self.click(live,stream,'reopen before writing-priority cancellation',320,140)
            started=len([r for r in self.rows(live) if r[0]==0x459])
            errors=len([r for r in self.rows(live) if r[0]==0x454])
            cancels=len([r for r in self.rows(live) if r[0]==0x458 and r[1:3]==(1,94)])
            self.raw_click(live,stream,40,245)
            state=live.wait(lambda state:len([r for r in self.rows(live) if r[0]==0x459])>started,self.args.action_seconds,quantum=10000)
            automatic_request=[r for r in self.rows(live) if r[0]==0x459][-1]
            live.wait(lambda state:any(r[0]==0x45b and r[1]==automatic_request[1] and r[2]==automatic_request[2] and r[3]==3 for r in self.rows(live)),self.args.action_seconds,quantum=10000)
            before_ink=len([r for r in self.rows(live) if r[0]==0x423])
            first,ink_tick=self.ink(live,stream,'writing while checker delays reply')
            def automatic_cancel(state):
                rows=self.rows(live)
                require(not any(r[0]==0x424 for r in rows),'writing-priority cancellation failed to free the real IPC slot')
                return state['devices']['pen']['count']==0 and len([r for r in rows if r[0]==0x423])>before_ink and len([r for r in rows if r[0]==0x458 and r[1:3]==(1,94)])>cancels
            admitted=live.wait(automatic_cancel,self.args.action_seconds,quantum=10000)
            require(admitted['ticks']-state['ticks']<10000000,'raw writing did not cancel/admit Store within the unchanged checker deadline')
            self.settle(live,ink_tick);self.wait_label(live,'SAVED',24,132)
            _,automatic_medium=live.export('automatic-cancel-ink')
            require(self.record(automatic_medium)[0]==prior_bytes,'automatic cancellation changed mathematical evidence/history')
            _,_,automatic_records=recover(automatic_medium.read_bytes())
            stored=[]
            for key,record in automatic_records.items():
                if key[1]>0x10000 and len(record.payload)>=128:
                    count=struct.unpack_from('<Q',record.payload,48)[0]
                    stored.extend(struct.unpack_from('<9Q',record.payload,128+i*72) for i in range(count))
            require(all(sample in stored for sample in stream.events[first:]),'writing-priority cancellation lost raw samples')
            self.report['while_stalled']={'status':'PASS','store_admission_tick':admitted['ticks'],'deadline_ticks':10000000,'raw_first_sequence':first+1,'raw_last_sequence':len(stream.events),'actual_consumed_terminal':94,'actual_guest_barrier_acknowledged':True}
            # Change a real submitted object after cancellation, before the old
            # server's predeclared twenty-second delay permits its reply.
            edited=self.press(live,stream,'edit numerator after cancelled check',27)
            require(edited[1]>automatic_request[2] and edited[3:]==(0,0),'edited submission retained old applicability')
            _,edited_medium=live.export('edited-before-late-reply')
            expected_math=self.record(edited_medium)[0]
            require(expected_math!=prior_bytes,'raw edit never changed the actual guest submission')
            require(not any(r[0]==0x45a and r[1]==automatic_request[1] for r in self.rows(live)),'selected delayed reply arrived before the edited-revision test boundary')
            def rejected_late_reply(state):
                require(not any(r[0]==0x424 for r in self.rows(live)),'late-reply boundary lost writing')
                return any(r[0]==0x45a and r[1]==automatic_request[1] and r[2]==automatic_request[2] and r[3] in (80,83) and r[4]==3 for r in self.rows(live))
            live.wait(rejected_late_reply,self.args.action_seconds,quantum=1000000)
            _,late_medium=live.export('late-reply-rejected')
            require(self.record(late_medium)[0]==expected_math and not any(r[0]==0x450 and r[3]!=0 for r in self.rows(live)),'late cancelled reply changed evidence or the edited record')
            self.report['stale_reply']={'status':'PASS','actual_request':automatic_request[1],'original_revision':automatic_request[2],'edited_revision':edited[1],'actual_retired_authority_rejection':True,'edited_record_unchanged':True}
            started=len([r for r in self.rows(live) if r[0]==0x459])
            cancels=len([r for r in self.rows(live) if r[0]==0x458 and r[1:3]==(1,94)])
            self.raw_click(live,stream,40,245)
            live.wait(lambda state:len([r for r in self.rows(live) if r[0]==0x459])>started,self.args.action_seconds,quantum=10000)
            close_tick=self.raw_click(live,stream,320,140)
            live.wait(lambda state:len([r for r in self.rows(live) if r[0]==0x458 and r[1:3]==(1,94)])>cancels,self.args.action_seconds,quantum=10000)
            self.settle(live,close_tick);self.wait_label(live,'SAVED',24,132)
            require(len([r for r in self.rows(live) if r[0]==0x454])==errors,'cancellation later published a terminal checker error')
            final_panel,final_medium=live.export('cancelled')
            require(self.record(final_medium)[0]==expected_math,'explicit cancellation changed edited mathematical evidence/history')
            self.report['cancellation']={'status':'PASS','actual_consumed_terminal':94,'record_unchanged':True,'reply_discarded':True}
            prior_bytes=expected_math
        live.close();self.sessions.remove(live)
        cold_disk=self.directory/'cold-input.raw';shutil.copyfile(final_medium,cold_disk)
        cold=self.session('cold',cold_disk);self.report['cold_boot']=cold.boot()
        require(cold.identity==self.report['identity'],'cold artifact identity changed')
        self.wait_label(cold,'SAVED',24,132);cold_panel,cold_medium=cold.export('cold-notebook')
        require(visible_pixels(cold_panel)==visible_pixels(final_panel),'cold complete controller output differs')
        require(self.record(cold_medium)[0]==prior_bytes,'cold recovered modified math/evidence')
        self.report['cold_recovery']={'status':'PASS','new_cpu':True,'complete_controller_pixels_equal':True,'acknowledged_math_unchanged':True,'raw_ink_preserved':True}
        cold.close();self.sessions.remove(cold)
        require(sha(self.args.disk)==original,'observer changed original medium')
        if self.args.require_managed_constructor or self.args.require_sums_constructor or getattr(self.args,'require_bytes_payload',False) or getattr(self.args,'require_array_payload',False) or getattr(self.args,'require_string_payload',False):
            require(all(sha(Path(self.args.guest_build)/name)==digest for name,digest in
                        self.report['managed_constructor_admission']['artifacts'].items()),
                    'admitted managed OOM artifacts changed during real observations')
        self.report['status']='PASS'
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=('oom','fault','stall'),required=True)
    parser.add_argument('--disk',type=Path,required=True);parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--native-bundle',required=True);parser.add_argument('--guest-build',required=True)
    parser.add_argument('--guest-source-root',type=Path,help='Complete original canonical Laboratory Array OOM consumed-source archive')
    parser.add_argument('--require-string-payload',action='store_true',help='Require exact User6 ordinary UTF8 String workload first allocation OOM and Protocol6/Document7 closure')
    parser.add_argument('--require-array-payload',action='store_true',help='Require exact User5 Array allocation and Protocol5/Document6 closure')
    parser.add_argument('--require-managed-constructor',action='store_true',
        help='fail unless exact User2 Lab artifact and emitted real constructor allocator path qualify OOM')
    parser.add_argument('--require-sums-constructor',action='store_true',
        help='fail unless exact User3 Lab artifact and genuine sum tags/layout/allocator path qualify OOM')
    parser.add_argument('--require-bytes-payload',action='store_true',
        help='fail unless exact User4 Lab artifact and genuine ByteArray allocation/access/lifetime path qualify OOM')
    parser.add_argument('--timeout',type=int,default=300);parser.add_argument('--boot-seconds',type=int,default=60)
    parser.add_argument('--action-seconds',type=int,default=30);parser.add_argument('--deadline',type=int,default=1200)
    args=parser.parse_args();args.checkpoint_relation='not-exercised';args.durable_suffix_from=None
    require(1<=args.timeout<=3600 and 1<=args.boot_seconds<=600 and 1<=args.action_seconds<=600 and 1<=args.deadline<=2400,'invalid predeclared resource bounds')
    require(sum((args.require_managed_constructor,args.require_sums_constructor,args.require_bytes_payload,args.require_array_payload,args.require_string_payload))<=1,'select one exact managed payload contract')
    require(not (args.require_managed_constructor or args.require_sums_constructor or getattr(args,'require_bytes_payload',False) or getattr(args,'require_array_payload',False) or getattr(args,'require_string_payload',False)) or args.case=='oom','managed constructor admission requires the OOM case')
    require(args.guest_source_root is None or args.require_array_payload,
            'archived Laboratory guest observation requires exact Array payload admission')
    checker=IsolationChecker(args)
    try:checker.execute()
    except BaseException as error:checker.report['error']=str(error);raise
    finally:checker.close()
    print(json.dumps({'status':checker.report['status'],'work_dir':str(checker.directory)}))
if __name__=='__main__':main()
