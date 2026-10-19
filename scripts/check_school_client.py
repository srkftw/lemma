#!/usr/bin/env python3
"""Bounded school-to-real-guest scenario using the public pen/UART interfaces.

Requires an enrolled published unit with identity1 and a declared edition, a genuinely
initialized empty medium, and a source-admitted Multimodal14 native bundle.
All school decisions execute in the real Lean authority. Pixel and medium
observations are independent host test oracles, never client implementations.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
import shutil
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_multimodal_workbook import Workflow, Input, require, decode, idle, visible_pixels, ask_context
from course_pixel_oracle import course_body_matches
from course_pixel_oracle import label_matches
from notebook_pixels import empty_pixels
from store_oracle import recover
from check_canonical_pen_pixels import expected_stroke
from check_course_math_workflow import CourseMathWorkflow
from lemmasim_school import school_call


class SchoolWorkflow(Workflow):
    course_loads = frozenset(('study-open-published-unit','reopen-original-before-document-change',
        'normal-learner-course-resume','reopen-independent-task-for-teacher-review',
        'ordinary-reader-opens-developer-edition'))

    def anchored_ask(self, session, stream, name):
        before=sum(row[0]==0x721 for row in self.rows(session))
        controls=sum(row[0]==0x712 and row[1]==3 for row in self.rows(session))
        first,_=self.raw(session,stream,870,140)
        panel=self.directory/(name+'-control-bar.ppm')
        labels=(('CAPTURE',400),('MUTE',544),('EEG OFF',640),('ASK',832),('LOAD',928),('JOIN',1024))
        receipt_panel=None
        first_receipt_paper=None
        receipt_idle_paper=None
        def completed(st):
            nonlocal receipt_panel,first_receipt_paper,receipt_idle_paper
            rows=self.rows(session);accepted=[row for row in rows if row[0]==0x712 and row[1]==3]
            if sum(row[0]==0x721 for row in rows)<=before:return False
            if len(accepted)<=controls or accepted[-1][2]!=0:return False
            if first_receipt_paper is None:
                first_receipt_paper=dict(panel_completed=st['panel_completed'],paper=st['devices']['paper'])
            if not idle(st):return False
            if receipt_panel is None:
                receipt_idle_paper=dict(panel_completed=st['panel_completed'],paper=st['devices']['paper'])
                receipt_panel=st['panel_completed'];return False
            if st['panel_completed']<=receipt_panel:return False
            session.control(dict(action='panel',path=str(panel)))
            return all(label_matches(panel,text,x,132) for text,x in labels)
        # ASK receipt and its queued control-bar presentation share the same
        # original150M bound, before any following ordinary navigation tap.
        state=self.phase(session,name,150_000_000,completed,quantum=100_000)
        context=ask_context((session.directory/'uart-0.bin').read_bytes())
        self.report['interactions'].append(dict(name=name,pixel=[870,140],first_raw_sequence=first+1,
            last_raw_sequence=len(stream.events),actual_guest_operation=3,actual_guest_context=context,
            complete_control_bar_pixels=True,receipt_idle_panel=receipt_panel,
            completed_panel=state['panel_completed'],first_receipt_paper=first_receipt_paper,
            receipt_idle_paper=receipt_idle_paper,
            completed_paper=dict(panel_completed=state['panel_completed'],paper=state['devices']['paper'])))
        return context

    def check(self, session, stream, name, outcome):
        publication=decode(self.packages[-1])
        ordinal=next(i for i,item in enumerate(publication['nodes']) if item['kind']==3 and item['goal']==2)
        self.check_presentation=dict(name=name,body=publication['nodes'][ordinal]['body'],
            requested=f"REQ I{publication['identity']:04X} E{publication['edition']:08X} N{ordinal+1:02d} R01",
            loaded=f"READ I{publication['identity']:04X} E{publication['edition']:08X}",
            old_requests=sum(row[0]==0x459 for row in self.rows(session)))
        try:return super().check(session,stream,name,outcome)
        finally:self.check_presentation=None

    def phase(self, session, name, cap, predicate, quantum=1_000_000):
        # CourseMathWorkflow.phase already declares400M for COURSEactualpackage
        # and cold-reopen-installed-body. New descriptive names must retain that
        # package-read bound. Ordinary views and action delivery remain100M;
        # the earlier actual100M failures remain separate retained failures.
        course_load=name in self.course_loads
        checking=getattr(self,'check_presentation',None)
        ack_panel=None
        first_reply_paper=None
        ack_idle_paper=None
        if checking and checking['name']==name:
            original=predicate;panel=self.directory/(name+'-completed-controls.ppm')
            def presented(st):
                nonlocal ack_panel,first_reply_paper,ack_idle_paper
                rows=self.rows(session);requests=[row for row in rows if row[0]==0x459];replies=[row for row in rows if row[0]==0x455]
                if (first_reply_paper is None and len(requests)>checking['old_requests'] and replies and
                    replies[-1][1]==requests[-1][1]):
                    first_reply_paper=dict(panel_completed=st['panel_completed'],paper=st['devices']['paper'])
                # First require the entire original own-reply/Saved/idle
                # predicate. A previous worksheet refresh cannot satisfy the
                # subsequently required controller completion.
                if not original(st):return False
                if ack_panel is None:
                    ack_idle_paper=dict(panel_completed=st['panel_completed'],paper=st['devices']['paper'])
                    ack_panel=st['panel_completed'];return False
                if st['panel_completed']<=ack_panel:return False
                session.control(dict(action='panel',path=str(panel)))
                return (label_matches(panel,'SAVED') and course_body_matches(panel,checking['body']) and
                    label_matches(panel,checking['requested'],24,700) and
                    label_matches(panel,checking['loaded'],24,720) and
                    label_matches(panel,'NODE+',24,640) and label_matches(panel,'USE',312,640))
            predicate=presented;quantum=100_000
        state=super().phase(session,name,400_000_000 if course_load else cap,predicate,quantum)
        if ack_panel is not None:
            self.report['phases'][-1].update(own_checker_saved_idle_panel=ack_panel,
                completed_controls_panel=state['panel_completed'],complete_body_and_source_controls_pixels=True,
                first_actual_checker_reply_paper=first_reply_paper,own_checker_saved_idle_paper=ack_idle_paper,
                completed_controls_paper=dict(panel_completed=state['panel_completed'],paper=state['devices']['paper']))
            self.progress()
        if course_load:
            row=self.report['phases'][-1]
            row['budget_source']='existing CourseMathWorkflow.phase COURSEactualpackage/cold-reopen-installed-body400M'
            row['original_generic100M_view']=('FAIL_ORIGINAL100M_CLOCK_CEILING' if row['execution_units']>100_000_000 else 'WITHIN_ORIGINAL100M_CLOCK_CEILING')
            self.report.setdefault('original100M_course_load_observations',[]).append(dict(name=name,
                execution_units=row['execution_units'],status=row['original_generic100M_view']))
            self.progress()
        return state

    def source_path(self, label):
        prefix, relative = label.split('/', 1)
        return (self.args.machine_source_root if prefix == 'machine' else ROOT) / relative

    def census(self):
        result = {}
        for path in self.pending_census:
            if path.is_file():
                result.update({'machine/'+name: digest for name, digest in json.loads(path.read_text()).items()})
        for module in list(sys.modules.values()):
            filename = getattr(module, '__file__', None)
            if filename:
                path = Path(filename).resolve()
                if path.suffix == '.py' and path.is_relative_to(ROOT) and path.is_file():
                    result['observer/'+str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        for relative in ('scripts/check_school_client.py', 'scripts/lemmasim_school.py','scripts/school_transport.py'):
            result['observer/'+relative] = hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()
        return result

    def check_sources(self):
        require(all(hashlib.sha256(self.source_path(label).read_bytes()).hexdigest() == digest
                    for label, digest in self.frozen.items()), 'actual consumed machine/observer source changed')
        for path in self.pending_census:
            if path.is_file():
                require({'machine/'+name for name in json.loads(path.read_text())} <= set(self.frozen),
                        'future machine CLI import outside initially observed closure')

    def session(self, name, disk, fail_flush=None):
        session = CourseMathWorkflow.session(self, name, disk, fail_flush)
        original_export = session.export
        def sparse_export(label):
            panel, medium = original_export(label)
            self.sparsify(medium)
            return panel, medium
        session.export = sparse_export
        archive = self.directory / 'consumed-host-source-root'
        if not archive.exists():
            for label, digest in self.frozen.items():
                data = self.source_path(label).read_bytes()
                require(hashlib.sha256(data).hexdigest() == digest, 'source changed before exact archive')
                target = archive / label; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        return session

    def close(self):
        for session in list(self.sessions):
            try:
                session.close()
            finally:
                self.sessions.remove(session)
        self.commands.close()
        self.report['elapsed_seconds'] = time.monotonic() - self.started
        self.report['consumed_host_current_equal'] = all(hashlib.sha256(self.source_path(label).read_bytes()).hexdigest() == digest
                                                        for label, digest in self.frozen.items())
        self.progress()
        (self.directory / 'result.json').write_text(json.dumps(self.report, default=str, indent=2)+'\n')

    def launch(self, args, **kw):
        if self.args.machine_source_root == ROOT:
            return super().launch(args, **kw)
        # The existing archive binds absolute original host origins. This
        # explicit option uses those actual original admitted launcher sources;
        # it does not relabel the archived guest as a current-source build.
        args = list(args)
        if args and args[0] == 'session':
            args[args.index('--workload')+1] = 'parameterized-notebook'
        self.launches += 1
        census = self.directory / ('imports-' + str(self.launches) + '.json')
        self.pending_census.append(census)
        command = [sys.executable, str(self.args.machine_source_root / 'scripts/host_import_census.py'),
                   str(census), str(self.args.machine_source_root / 'scripts/lemmasim'), *args]
        self.commands.write(json.dumps(command) + '\n'); self.commands.flush()
        return subprocess.Popen(command, cwd=self.args.machine_source_root, **kw)

    def bridge(self, session, action, label, *extra):
        out = self.directory / label
        command = [sys.executable, str(ROOT / 'scripts/lemmasim_school.py'), action,
            '--school-root', str(self.args.school_root), '--school-executable', str(self.args.school_executable),
            '--session-dir', str(session.directory), '--work-dir', str(out),
            '--school', self.args.school, '--actor', self.args.actor, '--course', str(self.args.course), '--revision', str(self.args.revision),
            '--session', 'native-client-1', '--now', '100', '--expires', '100000',
            '--policy', str(self.args.policy), '--transaction', str(1000+len(self.report['phases'])), *extra]
        self.tool(label, command, 120)
        report = json.loads((out / 'result.json').read_text())
        require(report['status'] != 'FAIL', 'actual school bridge failed')
        self.report.setdefault('school_bridge', []).append(dict(action=action, result=report))
        self.progress()
        return out, report

    def restart_school_and_observe_due(self):
        """Real process termination; controlled school clock, not retention."""
        def process_exchange(label, now, killed):
            command = [str(self.args.school_executable), str(self.args.school_root), 'serve']
            self.commands.write(json.dumps(command)+'\n'); self.commands.flush()
            with (self.directory/(label+'-stderr.log')).open('xb') as log:
                child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log)
                request = dict(op='progress', school=self.args.school, actor=self.args.actor, now=now)
                try:
                    child.stdin.write(json.dumps(request).encode()+b'\n'); child.stdin.flush()
                    line = child.stdout.readline(1048576)
                    response = json.loads(line)
                    require(response.get('ok') is True, 'actual restarted school rejected progress')
                    (self.directory/(label+'-response.json')).write_bytes(line)
                    if killed:
                        child.kill(); child.wait(timeout=10)
                        require(child.returncode == -9, 'school process was not actually forcibly terminated')
                    else:
                        child.stdin.close(); child.wait(timeout=10)
                        require(child.returncode == 0, 'restarted school did not close normally')
                    return dict(request=request, response=response, pid=child.pid, exit=child.returncode)
                finally:
                    if child.poll() is None:
                        child.kill(); child.wait(timeout=10)
        first = process_exchange('school-before-forced-termination', 100, True)
        after = process_exchange('school-after-forced-termination-due', 100+self.args.review_delay_seconds*1000, False)
        due = after['response']['result']['due']
        require(any(row['key'] == 'native-verified' for row in due), 'acknowledged school attempt review not due after actual process restart')
        self.report['school_process_restart_and_due'] = dict(before=first, after=after,
            clock_scope=f'controlled school milliseconds; predeclared{self.args.review_delay_seconds}-second production scheduling delay; no retention claim')

    def authority_negatives(self, ask):
        """Actual authority rejections, separate from guest admission evidence."""
        directory=self.directory/'authority-negative-requests'; directory.mkdir()
        common=dict(op='assist',school=self.args.school,actor=self.args.actor,
            session='native-client-1',course=self.args.course,revision=self.args.revision,policy=self.args.policy,now=100,ask=ask)
        rows=[]
        for label,changes,expected in (
            ('different-school',{'school':self.args.school+'-other'},'school'),
            ('changed-document',{'ask':dict(ask,revision=ask['revision']+1)},'exact joined'),
            ('expired-school-session',{'now':100000},'expired')):
            try:
                school_call(self.args.school_executable,self.args.school_root,common|changes,directory,label)
                raise RuntimeError('authority unexpectedly accepted '+label)
            except ValueError as error:
                require(expected in str(error),'wrong actual authority rejection: '+str(error))
                rows.append(dict(case=label,error=str(error),admitted=False))
        school_call(self.args.school_executable,self.args.school_root,
            dict(op='cancel-session',school=self.args.school,actor=self.args.actor,session='native-client-1',now=100),directory,'cancel')
        try:
            school_call(self.args.school_executable,self.args.school_root,common,directory,'cancelled-school-session')
            raise RuntimeError('cancelled authority session unexpectedly accepted')
        except ValueError as error:
            require('cancelled' in str(error),'wrong actual cancellation rejection')
            rows.append(dict(case='cancelled-school-session',error=str(error),admitted=False))
        self.report['actual_authority_negative_requests']=dict(cases=rows,
            scope='real Lean authority; guest live checks are independently exercised by SchoolPacket Action tests and actual replay rejection')

    def attempt_record(self, key, now, label):
        directory=self.directory/label;directory.mkdir()
        progress=school_call(self.args.school_executable,self.args.school_root,
            dict(op='progress',school=self.args.school,actor=self.args.actor,now=now),directory,'progress')
        matches=[row for row in progress['attempts'] if row['key']==key]
        require(len(matches)==1,'exact durable attempt absent from actual progress')
        return matches[0]['data']

    def developer_extension(self, session, stream):
        """Publish a Lean-authored revision, then use the ordinary guest reader."""
        if self.args.extension_definition is None:return
        directory=self.directory/'developer-extension'; directory.mkdir()
        authored=json.loads(self.args.extension_definition.read_text())
        edition=int(authored['course']['edition'])
        require(int(authored['course']['identity'])==self.args.course and edition==self.args.revision+1,
                'extension must be the next normal authored publication')
        now=100+self.args.review_delay_seconds*1000
        common=dict(school=self.args.school,actor=self.args.operator,now=now)
        school_call(self.args.school_executable,self.args.school_root,
            dict(op='publish',definition=authored,policy=self.args.policy,**common),directory,'publish')
        school_call(self.args.school_executable,self.args.school_root,
            dict(op='enroll',learner=self.args.actor,course=self.args.course,revision=edition,**common),directory,'enroll')
        out,_=self.bridge(session,'install','developer-extension-raw-install','--revision',str(edition),'--now',str(now))
        package=(out/'package.lcp').read_bytes(); published=decode(package)
        require(published['edition']==edition,'extension transport returned a different revision')
        self.packages.append(package)
        self.objects[(1,4850376798678024192 | self.args.course<<32 | edition)]=package
        crc=struct.unpack_from('<Q',package,80)[0]
        self.phase(session,'guest-durably-installs-developer-extension',150_000_000,
            lambda st:idle(st) and self.installed(session,self.args.course,edition,crc))
        self.click(session,stream,'ordinary-chooser-selects-developer-edition',168,670)
        self.click(session,stream,'ordinary-reader-opens-developer-edition',264,670,text=published['nodes'][0]['body'])
        routine=next(i for i,node in enumerate(published['nodes']) if node['kind']==3 and node['goal']==2)
        for node in range(1,routine+1):
            self.click(session,stream,'developer-edition-node-'+str(node+1),72,650,text=published['nodes'][node]['body'])
        self.click(session,stream,'use-developer-edition-exercise',360,650,mutation=True)
        checked=self.check(session,stream,'developer-edition-actual-Verified',1)
        self.bridge(session,'submit','developer-edition-record-verified','--revision',str(edition),'--now',str(now),
            '--attempt','developer-extension-verified','--activity',self.args.activity,'--task-id',str(routine+1),
            '--values',json.dumps(checked[3]['document']['answer']))
        delay=authored['review']['delaySeconds']; due_now=now+delay*1000
        progress=school_call(self.args.school_executable,self.args.school_root,
            dict(op='progress',school=self.args.school,actor=self.args.actor,now=due_now),directory,'extension-due')
        due=next((row for row in progress['due'] if row['key']=='developer-extension-verified'),None)
        require(due is not None,'developer review timing change not observable in the actual authority')
        review_out,review=self.bridge(session,'review','developer-edition-due-review','--revision',str(edition),
            '--now',str(due_now),'--review-id','developer-extension-verified')
        original=review['school_result']; require(original['edition']==edition,'developer due review lost revision')
        require((review_out/'package.lcp').read_bytes()==package,'developer due review changed its immutable publication')
        for node in range(routine+1,original['node']+1):
            self.click(session,stream,'developer-due-review-node-'+str(node+1),72,650,text=published['nodes'][node]['body'])
        preserved=any(row['key']=='native-verified' and row['data']['revision']==self.args.revision for row in progress['attempts'])
        require(preserved,'developer publication discarded the original acknowledged attempt')
        self.report['developer_extension']=dict(definition_sha256=hashlib.sha256(self.args.extension_definition.read_bytes()).hexdigest(),
            package_sha256=hashlib.sha256(package).hexdigest(),edition=edition,delay_seconds=delay,
            actual_checker_outcome=1,actual_due_review=due,complete_review_body_pixels=True,
            original_revision_attempt_preserved=preserved)

    def stale_guest_document(self, session, stream, original_body):
        """Change the real document after a joined proposal, before LOAD."""
        ask=self.anchored_ask(session,stream,'fresh-ASK-before-document-change')
        invitation_out,_=self.bridge(session,'join','revision-negative-join')
        invitation=(invitation_out/'package.lcp').read_bytes(); parsed=decode(invitation)
        crc=struct.unpack_from('<Q',invitation,80)[0]
        self.phase(session,'revision-negative-invitation-durable',150_000_000,
            lambda st:idle(st) and self.installed(session,60000,ask['sequence'],crc))
        joined=sum(row[0]==0x727 for row in self.rows(session))
        self.click(session,stream,'revision-negative-explicit-JOIN',1070,140,text=parsed['nodes'][0]['body'])
        require(sum(row[0]==0x727 for row in self.rows(session))==joined+1,'revision-negative school JOIN absent')
        out,result=self.bridge(session,'help','revision-negative-authored-help')
        proposal=(out/'package.lcp').read_bytes();crc=struct.unpack_from('<Q',proposal,80)[0]
        self.phase(session,'revision-negative-proposal-durable',150_000_000,
            lambda st:idle(st) and self.installed(session,60001,ask['sequence'],crc))
        # Close the invitation, reopen the remembered original exercise, then
        # USE it again. The guest alone creates the new document revision.
        self.raw(session,stream,320,140)
        self.close_rejected_view(session,'close-invitation-before-document-change')
        self.click(session,stream,'reopen-original-before-document-change',320,140,text=original_body)
        self.click(session,stream,'actual-USE-changes-document-revision',360,650,mutation=True)
        before=sum(row[0]==0x725 for row in self.rows(session))
        rejected=sum(row[0]==0x724 and row[1]==3 for row in self.rows(session))
        self.raw(session,stream,970,140)
        self.phase(session,'guest-rejects-school-proposal-after-document-change',100_000_000,
            lambda st:idle(st) and sum(row[0]==0x724 and row[1]==3 for row in self.rows(session))>rejected)
        require(sum(row[0]==0x725 for row in self.rows(session))==before,'stale school proposal acquired guest raster acceptance')
        self.close_rejected_view(session,'complete-home-after-revision-rejection')
        self.report['actual_guest_revision_rejection']=dict(ask=ask,proposal_sha256=hashlib.sha256(proposal).hexdigest(),
            reason=3,new_raster_acceptances=0,decision=result['school_result']['decision'],
            scope='real guest document USE after joined proposal; no host document/framebuffer edits')
        return ask

    def close_rejected_view(self, session, name):
        """Observe rejected or explicitly closed home before another control.

        A724/454 receipt can precede the full background redraw. Its historical
       500M close bound is separate from the next ordinary150M ASK control.
        The entire body plane is literal empty paper before drawing, or the
        independently cold-verified acknowledged home after drawing.
        """
        before=session.inspect()['machine']['panel_completed']
        expected=getattr(self,'home_body_baseline',None)
        if expected is None:expected=empty_pixels(1650,2200)[160*1650*3:]
        panel=self.directory/(name+'.ppm')
        def completed(st):
            if not idle(st) or st['panel_completed']<=before:return False
            session.control(dict(action='panel',path=str(panel)))
            width,height,pixels=visible_pixels(panel)
            return (width,height)==(1650,2200) and pixels[160*width*3:]==expected and label_matches(panel,'SAVED')
        self.phase(session,name,self.report['phase_caps']['close'],completed)
        self.report.setdefault('rejection_close_observations',[]).append(dict(name=name,
            body_pixels=1650*(2200-160),body_sha256=hashlib.sha256(expected).hexdigest(),
            basis='acknowledged independently cold-verified home' if hasattr(self,'home_body_baseline') else 'literal empty ruled-paper oracle',
            new_controller_completion=True,saved_label=True,
            budget_source='existing CourseMathWorkflow close500M; admission receipt and next ASK150M remain separate'))
        self.progress()

    def independent_work(self, session, stream, node):
        """Actual unsupported proof task; drawing is retained for teacher review."""
        old_checks=sum(row[0]==0x455 for row in self.rows(session))
        errors=sum(row[0]==0x454 for row in self.rows(session))
        self.raw(session,stream,360,650)
        # Admission is its own receipt, before the error's full redraw. The
        # next stage independently observes the entire completed home plane.
        self.phase(session,'independent-USE-explicitly-unsupported',100_000_000,
            lambda st:sum(row[0]==0x454 for row in self.rows(session))>errors and
                [row for row in self.rows(session) if row[0]==0x454][-1][1]==241)
        self.close_rejected_view(session,'complete-home-after-unsupported-independent-USE')
        published=decode(self.args.package[0].read_bytes())
        routine=next(i for i,item in enumerate(published['nodes']) if item['kind']==3 and item['goal']==2)
        # Unsupported USE never commits a new selection. COURSE resumes the
        # acknowledged exact exercise; navigate back to the task normally.
        self.click(session,stream,'reopen-independent-task-for-teacher-review',320,140,
            text=published['nodes'][routine]['body'])
        for ordinal in range(routine+1,node+1):
            self.click(session,stream,'return-to-independent-task-'+str(ordinal+1),72,650,
                text=published['nodes'][ordinal]['body'])
        stream.tick=session.inspect()['machine']['ticks']+10000;first=len(stream.events)
        stream.stroke('independent-unrecognized-proof-stroke',1,1,3,1950)
        samples=stream.events[first:];session.admit(samples);points=expected_stroke(samples)[1]
        panel=self.directory/'independent-proof-ink.ppm'
        def drawn(st):
            if not idle(st) or not self.saved(session):return False
            session.control(dict(action='panel',path=str(panel)));width,_,pixels=visible_pixels(panel)
            return all(pixels[(y*width+x)*3:(y*width+x)*3+3]==bytes(3) for x,y in points)
        self.phase(session,'actual-independent-raw-work-retained',300_000_000,drawn)
        observed=self.checkpoint_record(session,'actual-independent-work-observation')
        work=self.directory/'independent-work-artifact.json'
        work.write_text(json.dumps(dict(schema='lemma-explicit-teacher-review-work/1',
            course=self.args.course,revision=self.args.revision,node=node,guest_identity=session.inspect()['identity'],
            raw_pen_samples=samples,actual_uart_hex=(session.directory/'uart-0.bin').read_bytes().hex(),
            panel_sha256=hashlib.sha256(panel.read_bytes()).hexdigest(),
            scope='owner-local actual raw drawing; no handwriting recognition or arbitrary proof verification'),indent=2)+'\n')
        require(sum(row[0]==0x455 for row in self.rows(session))==old_checks,
                'unsupported independent task reused an exact checker verdict')
        now=100+self.args.review_delay_seconds*1000
        _,recorded=self.bridge(session,'submit','record-independent-teacher-review-work','--now',str(now),
            '--attempt','native-independent','--activity','reason','--task-id',str(node+1),
            '--values',json.dumps(observed[3]['document']['answer']),'--teacher-review','--work-artifact',str(work))
        row=self.attempt_record('native-independent',now,'independent-durable-attempt')
        require(row['independent'] is True and row['assisted'] is False and row['outcome']==4 and row['checker']=='teacher-review/1',
                'independent task acquired unsupported proof or assistance authority')
        ask=self.anchored_ask(session,stream,'ASK-after-unsupported-independent-selection')
        # Unsupported USE creates no exact checking binding. Its actual ASK
        # therefore remains attached to the earlier supported mathematics.
        # Exercise the independent policy with a separately labelled negative
        # request; never call this synthetic task field a guest observation.
        policy_ask=dict(ask,task_id=node+1)
        directory=self.directory/'independent-assistance-refusal';directory.mkdir()
        try:
            school_call(self.args.school_executable,self.args.school_root,
                dict(op='assist',school=self.args.school,actor=self.args.actor,session='native-client-1',
                     course=self.args.course,revision=self.args.revision,policy=self.args.policy,now=now,ask=policy_ask),directory,'assist')
            raise RuntimeError('independent activity unexpectedly authored assistance')
        except ValueError as error:
            require('prohibits assistance' in str(error),'independent activity failed at a different boundary')
        self.report['actual_independent_work']=dict(activity='reason',node=node,actual_guest_USE_rejection=241,hosted_authority_outcome=4,
            school_record=row,raw_stroke_samples=samples,complete_stroke_pixels=True,assistance_refused=True,
            actual_guest_ask=ask,independent_policy_negative_request=dict(ask=policy_ask,
                scope='synthetic task-field mutation of the actual ASK; actual Lean policy refusal, no independent guest checking binding claimed'),
            work_artifact_sha256=hashlib.sha256(work.read_bytes()).hexdigest(),
            scope='actual raw drawing and explicit unsupported selection; authority typed metadata and teacher review, no guest arbitrary-proof verdict')

    def execute(self):
        package = self.args.package[0].read_bytes(); published = decode(package)
        require(self.args.course == 1 and 1 <= self.args.revision <= 16 and published['identity'] == self.args.course and published['edition'] == self.args.revision,
                'identity1 authoring variant and bounded declared edition required')
        require(len(published['nodes']) >= 6, 'substantive unit, including independent work, required')
        self.report.update(schema='lemma-school-real-client/1', scope=__doc__,
            school=self.args.school, learner=self.args.actor, published_sha256=hashlib.sha256(package).hexdigest(),
            machine_source_root=str(self.args.machine_source_root),
            guest_school_credential='explicit school-session/1 JOIN and assistance/3; local-owner integrity boundary',
            aggregate_cap=4_000_000_000, aggregate_cycles=4_000_000_000)
        disk = self.directory / 'private.raw'; self.sparse_copy(self.args.disk, disk)
        session = self.session('first', disk)
        self.phase(session, 'cold-Ready-and-installed-course-service', 1_000_000_000,
            lambda st: idle(st) and st['panel_completed'] > 0 and any(r[0] == 0x420 for r in self.rows(session)) and any(r[0] == 0x72d for r in self.rows(session)))
        out, _ = self.bridge(session, 'install', 'school-course-install')
        require((out / 'package.lcp').read_bytes() == package, 'school retrieval differs from authored immutable package')
        crc = struct.unpack_from('<Q', package, 80)[0]
        self.phase(session, 'guest-durable-installs-school-publication', 150_000_000,
            lambda st: idle(st) and self.installed(session, self.args.course, self.args.revision, crc))
        stream = Input(1650, 2200, session.inspect()['machine']['ticks']+10000, 100000, 0)
        self.click(session, stream, 'study-open-actual-course-chooser', 320, 140)
        for edition in range(1,self.args.revision):
            self.click(session,stream,'choose-published-edition-'+str(edition+1),168,670)
        self.click(session, stream, 'study-open-published-unit', 264, 670, text=published['nodes'][0]['body'])
        routine = next(i for i, node in enumerate(published['nodes']) if node['kind'] == 3 and node['goal'] == 2)
        for index in range(1, routine+1):
            self.click(session, stream, 'study-node-'+str(index+1), 72, 650, text=published['nodes'][index]['body'])
        self.click(session, stream, 'use-exact-school-exercise', 360, 650, mutation=True)
        # Vary actual guest work: its fresh zero coefficients are Invalid, then
        # public raw field taps produce1,2,1 and the same isolated checker runs.
        invalid = self.check(session, stream, 'actual-school-coefficients-Invalid', 2)
        self.bridge(session, 'submit', 'record-actual-invalid-in-school', '--attempt', 'native-invalid',
            '--activity', self.args.activity, '--task-id', str(routine+1), '--values', json.dumps(invalid[3]['document']['answer']))
        for field, count in ((148, 1), (184, 2), (220, 1)):
            self.click(session, stream, 'select-coefficient-'+str(field), field, 225, mutation=True)
            for index in range(count):
                self.click(session, stream, 'increment-coefficient-'+str(field)+'-'+str(index), 364, 225, mutation=True)
        verified = self.check(session, stream, 'actual-school-coefficients-Verified', 1)
        self.bridge(session, 'submit', 'record-actual-verified-in-school', '--attempt', 'native-verified',
            '--activity', self.args.activity, '--task-id', str(routine+1), '--values', json.dumps(verified[3]['document']['answer']))
        self.report['varying_exact_work'] = dict(invalid=invalid[3], verified=verified[3], scope='fixed admitted Q[x] coefficients only')
        ask = self.anchored_ask(session, stream, 'learner-ASK-for-published-hint')
        invitation_out, invitation_result = self.bridge(session, 'join', 'enrolled-school-session')
        invitation = (invitation_out/'package.lcp').read_bytes(); join_package = decode(invitation)
        join_crc=struct.unpack_from('<Q',invitation,80)[0]
        self.phase(session,'guest-durably-installs-enrollment-invitation',150_000_000,
            lambda st: idle(st) and self.installed(session,60000,ask['sequence'],join_crc))
        joined_before=sum(row[0]==0x727 for row in self.rows(session))
        self.click(session,stream,'explicit-guest-JOIN-school-session',1070,140,text=join_package['nodes'][0]['body'])
        require(sum(row[0]==0x727 for row in self.rows(session))==joined_before+1,'explicit guest school binding acceptance absent')
        binding=invitation_result['school_result']['binding']
        require(any(row[0]==0x727 and row[1:4]==(binding['bindingRecord'],binding['generation'],binding['policy']) for row in self.rows(session)),
                'guest joined a different school binding/generation/policy')
        self.report['guest_school_join']=dict(binding=binding,receipt727=True,complete_body_pixels=True,scope='owner-local integrity; not authenticated remote enrollment')
        assistance, result = self.bridge(session, 'help', 'school-assistance')
        hint = (assistance / 'package.lcp').read_bytes(); hint_package = decode(hint)
        sequence = ask['sequence']; hint_crc = struct.unpack_from('<Q', hint, 80)[0]
        self.phase(session, 'guest-durably-installs-school-assistance', 150_000_000,
            lambda st: idle(st) and self.installed(session, 60001, sequence, hint_crc))
        before = sum(row[0] == 0x725 for row in self.rows(session))
        self.click(session, stream, 'actual-school-hint-visible', 970, 140, text=hint_package['nodes'][0]['body'])
        require(sum(row[0] == 0x725 for row in self.rows(session)) == before+1, 'actual guest raster admission absent')
        panel, medium = session.export('school-hint-controller-and-durable-bytes')
        require(course_body_matches(panel, hint_package['nodes'][0]['body']), 'complete actual hint body pixels differ')
        _, _, records = recover(medium.read_bytes())
        require(records[(1, 4850376798678024192 | (60001 << 32) | sequence)].payload == hint, 'guest assistance bytes not durably exact')
        decision = result['school_result']['decision']
        self.bridge(session, 'receipts', 'school-actual-raster-receipt', '--decision', decision, '--receipt-sequence', str(sequence))
        self.report['visible_hint'] = dict(package_sha256=hashlib.sha256(hint).hexdigest(), actual_guest_sequence=sequence,
            body=hint_package['nodes'][0]['body'], complete_body_pixels=True, panel_completed=session.inspect()['machine']['panel_completed'])
        _,assisted=self.bridge(session,'submit','record-verified-work-after-visible-assistance','--attempt','native-assisted',
            '--activity',self.args.activity,'--task-id',str(routine+1),'--values',json.dumps(verified[3]['document']['answer']))
        assisted_row=self.attempt_record('native-assisted',100,'assisted-durable-attempt')
        require(assisted_row['assisted'] is True and assisted_row['independent'] is False and assisted_row['outcome']==1,
                'actual assisted resubmission lost its assistance classification')
        self.report['actual_assisted_resubmission']=dict(record=assisted_row,
            scope='resubmission of the unchanged previously guest-verified typed work after visible assistance; no new proof claim')
        # A second LOAD must not replay the consumed proposal.
        accepted = sum(row[0] == 0x725 for row in self.rows(session)); self.raw(session, stream, 970, 140)
        self.phase(session, 'guest-rejects-completed-hint-replay', 100_000_000,
            lambda st: idle(st) and any(row[0] == 0x724 and row[1] == 5 for row in self.rows(session)))
        require(sum(row[0] == 0x725 for row in self.rows(session)) == accepted, 'completed hint replayed')
        self.close_rejected_view(session,'complete-home-after-replay-rejection')
        latest_ask=self.stale_guest_document(session,stream,published['nodes'][routine]['body'])
        self.authority_negatives(latest_ask)
        before_ink_acks=sum(row[0]==0x421 for row in self.rows(session))
        stream.tick = session.inspect()['machine']['ticks']+10000
        first = len(stream.events); stream.stroke('school-raw-drawing', 1, 1, 3, 1900)
        samples = stream.events[first:]; session.admit(samples)
        points = expected_stroke(samples)[1]; drawing = self.directory / 'drawing.ppm'
        def ink(st):
            if not idle(st): return False
            session.control(dict(action='panel', path=str(drawing)))
            width, _, pixels = visible_pixels(drawing)
            return all(pixels[(y*width+x)*3:(y*width+x)*3+3] == bytes(3) for x, y in points)
        self.phase(session, 'raw-drawing-after-school-assistance', 300_000_000, ink)
        mute_receipts=sum(row[0]==0x712 and row[1]==1 for row in self.rows(session))
        self.raw(session,stream,592,140)
        mute_panel=self.directory/'actual-local-MUTE-bar.ppm'
        bar_labels=(('CAPTURE',400),('MUTE',544),('EEG OFF',640),('ASK',832),('LOAD',928),('JOIN',1024))
        def mute_presented(st):
            receipts=[row for row in self.rows(session) if row[0]==0x712 and row[1]==1]
            if not idle(st) or len(receipts)<=mute_receipts or receipts[-1][2]!=0:return False
            if any(row['consent'] for row in st['devices']['multimodal']['streams']):return False
            session.control(dict(action='panel',path=str(mute_panel)))
            return all(label_matches(mute_panel,text,x,132) for text,x in bar_labels)
        self.phase(session,'explicit-local-MUTE-before-Save',150_000_000,mute_presented)
        muted=session.inspect()['machine']
        receipt=[row for row in self.rows(session) if row[0]==0x712 and row[1]==1][-1]
        require(receipt[2]==0,'actual local MUTE rejected')
        self.report['actual_local_mute']=dict(receipt712=list(receipt),cycle=muted['cycle'],
            modeled_controller=muted['devices']['multimodal'],complete_bar_label_pixels=True,
            scope='actual local privacy control and guest bar repaint before Save; no CAPTURE request in this scenario; no physical or remote microphone claim')
        # The toolbar's explicit Save confirms acknowledged work. A paper or
        # MUTE completion can precede automatic ink persistence, while the
        # existing toolbar deliberately declines busy Save. Observe its actual
        # Saved receipt and pixels before the first explicit Save tap.
        saved_panel=self.directory/'acknowledged-drawing-before-explicit-Save.ppm'
        def ink_acknowledged(st):
            if not idle(st) or not self.saved(session):return False
            if sum(row[0]==0x421 for row in self.rows(session))<=before_ink_acks:return False
            session.control(dict(action='panel',path=str(saved_panel)))
            return label_matches(saved_panel,'SAVED')
        self.phase(session,'acknowledged-drawing-before-explicit-Save',self.report['phase_caps']['ink'],ink_acknowledged)
        self.click(session, stream, 'explicit-Save-of-school-work', 1370, 64, mutation=True)
        home, saved = session.export('school-Saved'); session.close(); self.sessions.remove(session)
        cold_disk = self.directory / 'cold.raw'; self.sparse_copy(saved, cold_disk)
        cold = self.session('cold', cold_disk)
        self.phase(cold, 'new-CPU-cold-resume-acknowledged-school-work', 1_000_000_000,
            lambda st: idle(st) and st['panel_completed'] > 0 and any(row[0] == 0x420 for row in self.rows(cold)))
        cold_panel, cold_medium = cold.export('cold-school-work')
        require(saved.read_bytes() == cold_medium.read_bytes(), 'cold medium differs from acknowledged bytes')
        require(visible_pixels(home) == visible_pixels(cold_panel), 'cold complete controller pixels differ')
        self.home_body_baseline=visible_pixels(cold_panel)[2][160*1650*3:]
        require(not any(row[0] == 0x725 for row in self.rows(cold)), 'cold recovery replayed live assistance')
        self.restart_school_and_observe_due()
        review_out, review = self.bridge(cold, 'review', 'select-original-due-review', '--review-id', 'native-verified', '--now', str(100+self.args.review_delay_seconds*1000))
        original = review['school_result']
        require((original['identity'], original['edition'], original['policy']) == (self.args.course,self.args.revision,self.args.policy), 'due review lost original publication/policy')
        require((review_out/'package.lcp').read_bytes() == package, 'due review publication bytes changed')
        resumed = Input(1650,2200,cold.inspect()['machine']['ticks']+10000,100000,0)
        self.click(cold, resumed, 'normal-learner-course-resume', 320,140,text=published['nodes'][routine]['body'])
        for node in range(routine+1,original['node']+1):
            self.click(cold,resumed,'normal-due-review-node-'+str(node+1),72,650,text=published['nodes'][node]['body'])
            if node==5:self.independent_work(cold,resumed,node)
        review_panel, _ = cold.export('actual-due-review-opened')
        require(course_body_matches(review_panel,published['nodes'][original['node']]['body']), 'due original review not actually visible')
        self.report['actual_due_review_opened'] = dict(identity=self.args.course, edition=self.args.revision, node=original['node'], policy=original['policy'], complete_body_pixels=True)
        self.developer_extension(cold,resumed)
        self.report.update(status='PASS_SCOPED_SCHOOL_REAL_CLIENT', execution_units=self.cycles,
            independent_cold=dict(all_medium_bytes=saved.stat().st_size, all_pixels=1650*2200, no_live_assistance_replay=True),
            unexecuted=['browser school workflow', 'protected remote enrollment/authentication', 'physical device',
                'student free-form proof checking', 'all arbitrary school endpoint discovery/teacher editing controls'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('disk', 'package', 'native-bundle', 'work-dir', 'school-root'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--school-executable', type=Path, default=ROOT / '.lake/build/bin/school')
    parser.add_argument('--machine-source-root', type=Path, default=ROOT)
    parser.add_argument('--school', required=True); parser.add_argument('--actor', required=True)
    parser.add_argument('--policy', type=int, default=1)
    parser.add_argument('--course', type=int, default=1); parser.add_argument('--revision', type=int, default=1)
    parser.add_argument('--activity', default='coefficients'); parser.add_argument('--review-delay-seconds',type=int,default=86400)
    parser.add_argument('--extension-definition',type=Path); parser.add_argument('--operator',default='owner')
    args = parser.parse_args()
    args.disk = args.disk.resolve(); args.package = [args.package.resolve()]
    args.native_bundle = str(args.native_bundle.resolve()); args.machine_source_root = args.machine_source_root.resolve()
    args.school_root = args.school_root.resolve(); args.school_executable = args.school_executable.resolve()
    args.guest_build = None; args.guest_source_root = None; args.timeout = 120; args.deadline = 1800
    args.checkpoint_relation = 'independent cold only'; args.durable_suffix_from = None
    if args.work_dir.exists() or not args.work_dir.resolve().is_relative_to(ROOT / 'build'):
        parser.error('unused retained build directory required')
    actor = SchoolWorkflow(args)
    original_executable = args.school_executable
    private_executable = actor.directory / 'school-authority'
    shutil.copyfile(original_executable,private_executable); private_executable.chmod(0o755)
    executable_hash = hashlib.sha256(private_executable.read_bytes()).hexdigest()
    require(hashlib.sha256(original_executable.read_bytes()).hexdigest() == executable_hash, 'school executable changed during private immutable copy')
    args.school_executable = private_executable
    pending = ['Lemma/School/Main.lean']; school_inputs = {}
    while pending:
        name = pending.pop()
        if name in school_inputs: continue
        data = (ROOT/name).read_bytes(); school_inputs[name] = hashlib.sha256(data).hexdigest()
        target = actor.directory / 'consumed-school-source-root' / name
        target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
        for imports in re.findall(r'(?m)^import\s+([^\n]+)',data.decode()):
            pending.extend(module.replace('.','/')+'.lean' for module in imports.split() if module.startswith('Lemma.'))
    for name in ('lakefile.toml','lake-manifest.json','lean-toolchain','flake.nix','flake.lock','tooling/toolchain-lock.json'):
        data=(ROOT/name).read_bytes(); school_inputs[name]=hashlib.sha256(data).hexdigest()
        target=actor.directory/'consumed-school-source-root'/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
    actor.report['school_authority'] = dict(original_executable=str(original_executable), executable_sha256=executable_hash, source_inputs=school_inputs)
    try:
        actor.execute()
        require(all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest for name,digest in school_inputs.items()), 'consumed school source changed during actual scenario')
    except BaseException as error:
        actor.report.update(status='FAIL', error=repr(error))
        raise
    finally:
        actor.close()
    print(actor.report['status'])


if __name__ == '__main__':
    main()
