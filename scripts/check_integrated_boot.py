#!/usr/bin/env python3
"""Bounded actual Integrated development-ROM install, notebook and Save.

The host transports opaque image sectors and raw pen input. It never constructs
boot metadata, guest page tables, notebook data, checking or health receipts.
"""
import argparse,json,os,signal,subprocess,sys,time,shutil
from pathlib import Path
from types import SimpleNamespace
import lemmasim_auth as auth
import lemmasim_session as sessions
from product_native import sha
from development_install import load_package
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'conformance/lemmasim'))
from store_oracle import recover
from notebook_input import Input
from check_canonical_pen_pixels import expected_stroke
from check_integrated_saved_work import qualify as qualify_saved_work
from check_live_notebook import guest_events,visible_pixels


def require(value,message):
    if not value:raise RuntimeError(message)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=('lemma-silicon-dev/0.15.0','lemma-silicon-dev/0.16.0'),default='lemma-silicon-dev/0.15.0',help='Exact full SoC binding; Fast MM2 subset cannot qualify this path')
    for name in ('prepared','package','tag','user-medium','work-dir'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--capture-ready-checkpoint',action='store_true',help='Attempt ordinary nonmutating sealed checkpoint after actual Ready; no restore or guest execution shortcut')
    parser.add_argument('--factory-boot',type=Path,help='Offline hosted-Lean provisioned raw boot artifact; actual ROM still authenticates it')
    parser.add_argument('--factory-reject',choices=('metadata','tag'),help='Separate negative ROM case on a private corrupted factory copy; no notebook success claim')
    args=parser.parse_args();out=args.work_dir.resolve()
    require(not args.factory_reject or args.factory_boot is not None,'factory negative case requires a factory artifact')
    require(not out.exists() and out.is_relative_to(ROOT/'build'),'unused ignored output required');out.mkdir(parents=True)
    # Freeze the actual observer before execution. Historical failed observers
    # retain their own results; these bytes are never assigned retroactively.
    source=out/'observer-source';source.mkdir()
    prepared_record=json.loads((args.prepared/'prepared.json').read_text())
    observer_paths={Path(__file__).relative_to(ROOT).as_posix(),
      'conformance/lemmasim/store_oracle.py','conformance/lemmasim/notebook_input.py',
      'conformance/lemmasim/check_canonical_pen_pixels.py',
      'scripts/check_live_notebook.py','scripts/check_integrated_saved_work.py',
      'conformance/lemmasim/inspect_notebook.py','conformance/lemmasim/math_oracle.py',
      'conformance/lemmasim/check_notebook_workflow.py','conformance/lemmasim/notebook_pixels.py',
      'scripts/lemmasim_readonly.py',*prepared_record.get('host_scripts',{})}
    observer_inputs={}
    for name in sorted(observer_paths):
        original=ROOT/name;target=source/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(original,target);observer_inputs[name]=sha(target)
        require(sha(original)==observer_inputs[name],'observer changed during capture: '+name)
    (source/'source-inputs.json').write_text(json.dumps(observer_inputs,indent=2,sort_keys=True)+'\n')
    factory=args.factory_boot is not None
    start=time.monotonic();whole=start+(12000 if factory else 10800);process=None;log=None;total=0
    report={'schema':'lemma-integrated15-authenticated-guest/1','result':'FAIL','scope':__doc__,
      'limits':{'whole_seconds':10800,'install_cycles':600000000,'install_seconds':3600,'Ready_cycles':1300000000,'Ready_seconds':5400,'Save_cycles':300000000,'Save_seconds':1800},
      'observer_python':{'path':str(Path(sys.executable).resolve()),'sha256':sha(Path(sys.executable).resolve()),'version':sys.version},
      'observer_inputs':observer_inputs,'observer_archive_sha256':sha(source/'source-inputs.json'),'phases':[],'receipts':[],'compilation':'reused source-audited integrated guest/ROM/RTL; this run is fresh actual canonical execution'}
    if factory:
        report.update(schema='lemma-integrated15-factory-cold-guest/1',scope='Actual ROM/NV cold authentication of explicitly factory-provisioned bytes, then shared guest pen/Save/reset; not an update/install operation',limits={'whole_seconds':12000,'aggregate_cycles':1500000000,'Ready_cycles':1299800000,'Ready_seconds':10500,'Save_cycles':200000000,'Save_seconds':1800,'reset_cycles':200000,'output_bytes':2147483648,'runtime_rss_bytes':536870912})
    if args.profile.endswith('/0.16.0'):
        report['schema']=report['schema'].replace('integrated15','integrated16')
    report['selected_profile']=args.profile
    report['kernel_beacon']={'version':15,'meaning':'retained IntegratedKernel/Product10 guest interface; full selected machine identity is checked independently'}
    def publish():(out/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
    def call(value):
        require(time.monotonic()<whole,'original whole deadline')
        if factory:
            used=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
            require(used<=2147483648,'original output byte bound')
            pending=[process.pid] if process is not None and process.poll() is None else []
            maximum=0
            while pending:
                pid=pending.pop()
                try:
                    status=Path(f'/proc/{pid}/status').read_text()
                    maximum=max(maximum,next(int(line.split()[1])*1024 for line in status.splitlines() if line.startswith('VmRSS:')))
                    pending.extend(map(int,Path(f'/proc/{pid}/task/{pid}/children').read_text().split()))
                except (OSError,StopIteration):pass
            report['observed_resources']={'output_bytes':used,'peak_single_owned_process_rss_bytes':max(maximum,report.get('observed_resources',{}).get('peak_single_owned_process_rss_bytes',0))}
            require(maximum<=536870912,'original runtime process RSS bound')
        return sessions.request(out/'session',value,120)
    def phase(name,cycles,seconds,predicate):
        nonlocal total
        begin=call({'action':'inspect'})['machine']['cycle'];started=time.monotonic()
        while True:
            state=call({'action':'inspect'})['machine'];rows=guest_events(out/'session/uart.bin')
            require(not state['finished'] and not any(row[0] in (0xd4,0xf4,0x424) for row in rows),'actual guest failure in '+name)
            if predicate(state,rows):break
            used=state['cycle']-begin
            require(used<cycles and time.monotonic()-started<seconds,'original phase bound '+name)
            amount=min(1000000,cycles-used)
            if factory:require(total+amount<=1500000000,'original aggregate cycle bound')
            call({'action':'run','cycles':amount});total+=amount
            report['current']={'phase':name,'cycles':state['cycle']-begin,'cycle':state['cycle'],'seconds':time.monotonic()-started,'total_cycles':total};publish()
        report['phases'].append({'name':name,'cycles':state['cycle']-begin,'end_cycle':state['cycle'],'seconds':time.monotonic()-started});publish();print(name,state['cycle'],flush=True);return state
    try:
        admission,_,_=auth.prepared(args.prepared);require(admission['profile']==args.profile,'exact selected Integrated machine required')
        package,wire,tag=load_package(args.package,args.tag,sha)
        from integrated_deployment import CONFIGURATIONS
        require(package.get('configuration') in CONFIGURATIONS,'exact integrated guest required')
        from silicon_profile import configuration_profile
        from school_deployment import INTEGRATED_CONFIGURATIONS
        require(configuration_profile(package['configuration'])==args.profile,'compiled image configuration differs from selected full SoC profile')
        school=package.get('configuration') in INTEGRATED_CONFIGURATIONS
        report['inputs']={str(path.resolve()):sha(path) for path in (args.prepared/'prepared.json',args.package/'package.json',args.package/'image.bin',args.tag,args.user_medium)}
        boot=out/'boot.raw';disk=out/'user.raw'
        if factory:
            require(args.factory_boot.stat().st_size==auth.product.BOOT_BYTES,'factory boot capacity differs')
            with args.factory_boot.open('rb') as file:
                file.seek(1024);require(file.read(512)==tag,'factory tag is not the declared exact slot0 tag')
                file.seek(4096);require(file.read(len(wire))==wire,'factory payload is not the exact audited package')
            report['inputs'][str(args.factory_boot.resolve())]=sha(args.factory_boot)
            subprocess.run(['cp','--reflink=auto','--sparse=always',str(args.factory_boot),str(boot)],check=True)
        else:
            with boot.open('xb') as file:file.truncate(auth.product.BOOT_BYTES);file.flush();os.fsync(file.fileno())
        if args.factory_reject:
            with boot.open('r+b') as file:
                for offset in ((0,512) if args.factory_reject=='metadata' else (1024,)):
                    file.seek(offset);value=file.read(1);file.seek(offset);file.write(bytes([value[0]^1]))
            report['negative_stimulus']={'kind':args.factory_reject,'scope':'corrupt structural magic in private backing; no CRC or MAC repair','offsets':[0,512] if args.factory_reject=='metadata' else [1024]}
        subprocess.run(['cp','--reflink=auto','--sparse=always',str(args.user_medium),str(disk)],check=True)
        disk.chmod(0o600)
        _,sequence,before=recover(disk.read_bytes());report['initial_store_sequence']=sequence
        argv=[sys.executable,str(ROOT/'scripts/lemmasim_auth.py'),'--public-development-key','launch','--prepared',str(args.prepared.resolve()),'--session-dir',str(out/'session'),'--boot-medium',str(boot),'--disk',str(disk),'--paused','--headless','--mode','laboratory','--host-threads','1','--timeout','120']
        if not factory:argv.append('--recovery')
        report['launch']=argv;log=(out/'session.log').open('xb');process=subprocess.Popen(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+30
        while not(out/'session/session.json').is_file():
            require(process.poll() is None and time.monotonic()<deadline,'new session did not open');time.sleep(.05)
        if args.factory_reject:
            bounds={'metadata':(2000000,120),'tag':(200000000,2400)}[args.factory_reject]
            report['limits']={'whole_seconds':bounds[1],'aggregate_cycles':bounds[0]}
            client=auth.RecoveryClient(SimpleNamespace(session_dir=out/'session',timeout=bounds[1],cycles=bounds[0],quantum=100000,transaction=1))
            report['negative_beacon']=client.beacon();state=call({'action':'inspect'})['machine']
            require(not any(r[0] in (0x47c,0x420) for r in guest_events(out/'session/uart.bin')),'rejected factory bytes executed integrated guest')
            report.update(result='PASS_ACTUAL_ROM_REJECTED_FACTORY_'+args.factory_reject.upper(),total_cycles=client.used,scope='actual development ROM structural rejection and recovery beacon; not arbitrary MAC-negative or notebook execution qualification')
            return 0
        if not factory:
            client=auth.RecoveryClient(SimpleNamespace(session_dir=out/'session',timeout=3600,cycles=600000000,quantum=100000,transaction=1))
            report['beacon']=client.beacon();auth.product.install_extent(package,wire,client.call({'action':'inspect'})['identity']);staged=time.monotonic()
            for index in range(len(wire)//512):
                row=client.send(1,slot=0,relative=index,identity=package['identity'],payload=wire[index*512:index*512+512]);report['receipts'].append(row)
                require(row['status']==0,'actual opaque sector rejected')
                if index%32==0:publish()
            for operation,kw in ((5,{'slot':0,'identity':package['identity'],'payload':tag}),(2,{'slot':0,'identity':package['identity']}),(3,{})):
                row=client.send(operation,**kw);report['receipts'].append(row);require(row['status']==0,'actual authentication/publication/handoff rejected')
            require(row['value']==0x80000000,'actual ROM handoff entry differs')
            report['install']={'cycles':client.used,'seconds':time.monotonic()-staged,'sectors':len(wire)//512,'image_preloaded':False};publish()
        else:report['cold_boot']={'source':'explicit factory raw backing','elf_or_dtb_preloaded':False,'installed_via_uart':False}
        ready=phase('combined-kernel-and-notebook-Ready',1299800000 if factory else 1300000000,10500 if factory else 5400,lambda state,rows:any(r[:4]==(0x47c,15,8,9) for r in rows) and (not school or any(r==(0x731,2,512,262144,2) for r in rows)) and any(r[0]==0x420 for r in rows) and ((1,1) in before or any(r[0]==0x421 for r in rows)) and state['panel_completed']>0 and not state['paper_busy'] and not state['panel_pending_pixels'])
        panel=out/'ready.ppm';call({'action':'panel','path':str(panel)});width,height,pixels=visible_pixels(panel);require((width,height)==(1650,2200),'actual controller geometry differs')
        # Establish the actual journal frontier after any fresh-page Save. Its
        # receipt cannot satisfy the distinct pen-and-Save observation below.
        baseline=out/'before-pen-user.raw';call({'action':'export-medium','path':str(baseline)})
        _,pen_sequence,pen_before=recover(baseline.read_bytes())
        require((1,1) in pen_before,'ready notebook lacks its committed page')
        report['before_pen']={'store_sequence':pen_sequence,'user_sha256':sha(baseline)}
        if args.capture_ready_checkpoint:
            before_snapshot=call({'action':'inspect'})['machine']
            try:
                checkpoint=call({'action':'snapshot','path':str(out/'ready-checkpoint')})
            except RuntimeError as error:
                report['ready_checkpoint']={'result':'REJECTED','error':str(error),'scope':'Optional normal checkpoint; original guest execution continues independently'}
            else:
                report['ready_checkpoint']={'result':'CAPTURED','path':str(out/'ready-checkpoint'),
                    'manifest_sha256':sha(out/'ready-checkpoint/snapshot.json'),
                    'scope':'Actual Ready state captured; no restore or continuation claim from capture alone'}
            require(call({'action':'inspect'})['machine']==before_snapshot,'Ready checkpoint changed digital observation')
            publish()

        stream=Input(width,height,ready['ticks']+10000,100000,0);stream.sample(width//2,160,0,False);stream.stroke('integrated-written-work',1,1,3,1700);stroke=stream.events[1:].copy();stream.tool(7,'explicit Save')
        for event in stream.events:call({'action':'inject','kind':'pen','cycle':event[1]*10,'words':list(event[1:8])})
        saved=phase('actual-pen-and-Save',200000000 if factory else 300000000,1800,lambda state,rows:any(r[0]==0x421 and r[1]>=pen_sequence+3 for r in rows) and not any(state[k] for k in ('event_queue','pen_queue','paper_busy','panel_pending_pixels','block_state','dma_outstanding')))
        ack=out/'acknowledged-user.raw';nv=out/'acknowledged-boot.raw';call({'action':'export-medium','path':str(ack)});call({'action':'export-boot-medium','path':str(nv)})
        _,after_sequence,after=recover(ack.read_bytes());require(after_sequence>=pen_sequence+3,'pen Save missing new actual journal commits')
        linked_work=qualify_saved_work(baseline.read_bytes(),ack.read_bytes(),stroke)
        painted=out/'saved.ppm';call({'action':'panel','path':str(painted)});saved_width,saved_height,saved_pixels=visible_pixels(painted)
        require((saved_width,saved_height)==(width,height),'saved panel geometry changed')
        ink=expected_stroke(stroke,width,height)[1]
        require(ink and all(saved_pixels[(y*width+x)*3:(y*width+x)*3+3]==bytes(3) for x,y in ink),'actual pen pixels absent from controller output')
        require(any(pixels[(y*width+x)*3:(y*width+x)*3+3]!=bytes(3) for x,y in ink),'stroke adds no independently visible ink')
        require(all(after[key].payload==old.payload for key,old in before.items() if key not in ((1,1),(1,257))),'prior immutable work changed')
        report['saved']={'store_sequence':after_sequence,'user_sha256':sha(ack),'boot_sha256':sha(nv),'events':stream.events,'old_work_preserved':True,'new_ink_pixels':len(ink),'committed_page_index_changed':True,'linked_work':linked_work}
        if factory:
            call({'action':'warm-reset'});call({'action':'run','cycles':200000});total+=200000
            reset=call({'action':'inspect'})['machine'];require(not reset['finished'] and reset['event_queue']==0 and reset['pen_queue']==0,'actual reset did not clear pending input')
            reset_disk=out/'reset-user.raw';call({'action':'export-medium','path':str(reset_disk)});require(sha(reset_disk)==sha(ack),'reset changed acknowledged work')
            report['reset']={'cycles':200000,'machine':reset,'acknowledged_user_bytes_unchanged':True,'scope':'actual reset and initial ROM/NV re-entry; full cold notebook reopening remains separate'}
        report['total_cycles']=total
        report['result']='PASS_ACTUAL_INTEGRATED_FACTORY_ROM_NOTEBOOK_PEN_SAVE_RESET' if factory else 'PASS_ACTUAL_INTEGRATED_ROM_KERNEL_NOTEBOOK_PEN_SAVE'
        report['excluded']=['independent cold reopen','whole-panel oracle','enabled simultaneous raw acquisition','wired service traffic','ordinary Student school workflow','physical or educational qualification']
    except BaseException as error:report['error']=repr(error)
    finally:
        if process is not None:
            try:
                if process.poll() is None:sessions.request(out/'session',{'action':'destroy'},5)
                process.wait(timeout=10)
            except BaseException:
                if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
        if log:log.close()
        report['owned_processes_reaped']=process is None or process.poll() is not None;report['seconds']=time.monotonic()-start;publish();(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['result'],report.get('error',''));return 0 if report['result'].startswith('PASS_') else 1
if __name__=='__main__':raise SystemExit(main())
