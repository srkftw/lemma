#!/usr/bin/env python3
"""One owner-local tutor exchange from an actual guest ASK record.
The guest owns original anchors/grants and sole installer owns UART. This tool
only calls local inference, constructs an untrusted immutable explanation package
through hosted Lean, and injects normal course-command bytes. It never changes
memory, pixels, checker results or durable media and issues no delivery receipt.
"""
import argparse,ast,hashlib,json,re,shutil,struct,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sim/companion/multimodal'))
from tutor import Tutor
from lemmasim_session import request as control
from lemmasim_course import frame

ROW=re.compile(rb'K1 ((?:[0-9a-f]{16} ){4}[0-9a-f]{16})\r?\n')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def source_inventory():
    paths=set();pending=['scripts/lemmasim_tutor.py','scripts/lemmasim_session.py','scripts/lemmasim_course.py','scripts/course_package.py',
        'sim/companion/multimodal/tutor.py','sim/companion/multimodal/policy.py','sim/companion/multimodal/speech.py']
    while pending:
        name=pending.pop()
        if name in paths:continue
        path=ROOT/name
        if not path.is_file():raise ValueError('missing host dependency '+name)
        paths.add(name)
        for node in ast.walk(ast.parse(path.read_text(),filename=name)):
            modules=[v.name for v in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
            for module in modules:
                first=module.split('.')[0]
                candidates=[path.parent/(first+'.py'),ROOT/'sim/companion/multimodal'/(first+'.py'),ROOT/'scripts'/(first+'.py'),ROOT/'sim/companion'/(first+'.py'),ROOT/'tooling/silicon'/(first+'.py'),ROOT/'conformance/lemmasim'/(first+'.py')]
                local=next((p for p in candidates if p.is_file()),None)
                if local is not None:pending.append(str(local.relative_to(ROOT)))
                elif first not in sys.stdlib_module_names and first!='__future__':raise ValueError('unknown host dependency '+module)
    pending=['sim/companion/PackageProposal.lean','Lemma/Multimodal/TutorPackage.lean']
    while pending:
        name=pending.pop()
        if name in paths:continue
        path=ROOT/name
        if not path.is_file():raise ValueError('missing package/guest dependency '+name)
        paths.add(name)
        for line in re.findall(r'(?m)^\s*import\s+([^\n]+)',path.read_text()):
            for module in line.split():
                if module.startswith('Lemma.'):
                    if not re.fullmatch(r'Lemma(?:\.[A-Za-z0-9_]+)+',module):raise ValueError('unknown project import '+module)
                    pending.append(module.replace('.','/')+'.lean')
                elif not any(module==prefix or module.startswith(prefix+'.') for prefix in ('Lean','Init','Std')):raise ValueError('unknown Lean dependency '+module)
    for name in ('flake.nix','flake.lock','lean-toolchain','lakefile.toml','lake-manifest.json','tooling/toolchain-lock.json','docs/document-map.json','sim/companion/multimodal/math-questions.gram'):
        if not (ROOT/name).is_file():raise ValueError('missing source/tool authority '+name)
        paths.add(name)
    return {name:sha(ROOT/name) for name in sorted(paths)}

def tool_inventory():
    tools={'python':Path(sys.executable).resolve()}
    for name in ('lake','lean','ollama'):
        value=shutil.which(name)
        if value is None:raise ValueError('missing required tool '+name)
        tools[name]=Path(value).resolve()
    result={name:{'path':str(path),'sha256':sha(path)} for name,path in tools.items()}
    result['python']['version']=sys.version
    for name in ('lake','lean','ollama'):
        version=subprocess.run([str(tools[name]),'--version'],capture_output=True,text=True,timeout=10)
        if version.returncode:raise ValueError('cannot identify actual tool '+name)
        result[name]['version']=(version.stdout+version.stderr).strip()
    return result

def ask_context(data):
    pending=[];complete=None
    for match in ROW.finditer(data):
        values=[int(x,16) for x in match.group(1).split()];tag,*words=values
        if tag==0x721:pending=[words]
        elif tag==0x722 and len(pending)==1:pending.append(words)
        elif tag==0x723 and len(pending)==2:
            session,revision,obj,sequence=pending[0];source,edition,task,cutoff=pending[1];consent,deadline,grants,max_pcm=words
            complete=dict(session=session,revision=revision,object=obj,sequence=sequence,source=source,edition=edition,task_id=task,
                cutoff=cutoff,now=cutoff,consent=consent,deadline=deadline,grants=grants,modality=1)
            if max_pcm!=0 or grants!=1:raise ValueError('this bridge admits text-only development ASK')
            pending=[]
    if complete is None or pending:raise ValueError('guest has no complete current721/722/723 ASK')
    if min(complete[k] for k in ('session','revision','object','sequence','source','edition','task_id','consent'))<=0:raise ValueError('malformed guest ASK identities')
    return complete

def uart_path(directory,metadata):
    argv=metadata.get('argv',[])
    if metadata.get('backend')=='qemu':
        if argv.count('-serial')!=1:raise ValueError('exact fast UART capture missing')
        value=argv[argv.index('-serial')+1]
        if not value.startswith('file:'):raise ValueError('fast UART capture is not a file')
        path=Path(value[5:])
    elif metadata.get('backend')=='rtl':
        if argv.count('--uart-output')!=1:raise ValueError('exact RTL UART capture missing')
        path=Path(argv[argv.index('--uart-output')+1])
    else:raise ValueError('unsupported session backend')
    path=path.resolve()
    if not path.is_relative_to(directory) or not path.is_file() or path.stat().st_size>8*1024*1024:raise ValueError('bounded owned UART capture required')
    return path

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session-dir',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--question',required=True);p.add_argument('--kind',choices=['rational-sum','polynomial-product'],required=True)
    for name in ('a','b','c','d'):p.add_argument('--'+name,type=int,required=True)
    p.add_argument('--model',default='qwen2.5:7b');p.add_argument('--inject',action='store_true',help='send generated course command to the paused admitted guest');a=p.parse_args()
    directory=a.session_dir.resolve();out=a.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'build'):p.error('unused ignored work directory required')
    out.mkdir(parents=True);started=time.monotonic();report={'status':'FAIL','scope':__doc__}
    try:
        report['source_inputs']=source_inventory();report['tools']=tool_inventory()
        archive=out/'consumed-source-root';archive.mkdir()
        for name,expected in report['source_inputs'].items():
            data=(ROOT/name).read_bytes()
            if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('source changed before archive '+name)
            target=archive/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        metadata=json.loads((directory/'session.json').read_text())
        report['session_metadata_sha256']=sha(directory/'session.json')
        if metadata.get('schema')!='lemmasim-live/1' or metadata.get('mode') not in ('developer','laboratory'):raise ValueError('owner-local Developer/Laboratory session required')
        identity=metadata.get('identity',{})
        if identity.get('profile')!='lemma-silicon-dev/0.14.0':raise ValueError('exact new Multimodal14 profile required')
        observed=control(directory,{'action':'inspect'},timeout=120)
        if observed.get('identity')!=identity or observed.get('running') is not False:raise ValueError('pause the exact machine before admitting tutor bytes')
        argv=metadata.get('argv',[]);flag='-kernel' if metadata['backend']=='qemu' else '--image'
        if argv.count(flag)!=1:raise ValueError('exact guest image missing')
        image=Path(argv[argv.index(flag)+1]);build=json.loads((image.parent/'build.json').read_text())
        if build.get('configuration') not in ('lemmasim-silicon-multimodal-notebook','lemmasim-silicon-multimodal-initialize','lemmasim-silicon-multimodal-parameterized-notebook','lemmasim-silicon-multimodal-parameterized-initialize') or sha(image)!=identity.get('guest'):raise ValueError('source-bound new guest required')
        uart=uart_path(directory,metadata);captured=uart.read_bytes();context=ask_context(captured)
        report['initial_observation']=observed
        report['guest_build_sha256']=sha(image.parent/'build.json')
        (out/'initial-guest-identity.json').write_text(json.dumps({'identity':identity,'argv':argv,'build':build},indent=2)+'\n')
        (out/'guest-ask.json').write_text(json.dumps(context,indent=2)+'\n')
        query={**context,'task':{'kind':a.kind,'a':a.a,'b':a.b,'c':a.c,'d':a.d},'question':a.question}
        #These public operands/questions are untrusted educational context;
        #they cannot change the guest's independently captured task authority.
        tutor=Tutor('http://127.0.0.1:11434',a.model);proposal=tutor.propose(query)
        (out/'request.json').write_text(json.dumps(query,indent=2)+'\n');(out/'proposal.json').write_text(json.dumps(proposal,indent=2)+'\n')
        package=out/'assistance.lcp'
        command=['lake','env','lean','--run','sim/companion/PackageProposal.lean','--proposal',str(out/'proposal.json'),'--output',str(package)]
        published=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=120);(out/'publisher.log').write_bytes(published.stdout+published.stderr)
        if published.returncode:raise ValueError('actual Lean package publisher failed')
        raw=package.read_bytes();package_identity,edition=struct.unpack_from('<2Q',raw,24);crc=struct.unpack_from('<Q',raw,80)[0]
        command_bytes=frame(1,package_identity,edition,len(raw),context['sequence'],crc)+raw
        #The actual guest request must still be current at byte admission. This
        #observation is only host routing; the guest independently gates later.
        if ask_context(uart.read_bytes())!=context:raise ValueError('guest ASK changed during inference')
        boundaries=[]
        if a.inject:
            actual=control(directory,{'action':'inspect'},timeout=120)
            if actual.get('identity')!=identity or actual.get('running') is not False:raise ValueError('machine state changed before admission')
            cycle=actual.get('machine',{}).get('cycle')
            if type(cycle) is not int or cycle<0:raise ValueError('actual scheduling cycle unavailable')
            for offset in range(0,len(command_bytes),4096):
                boundaries.append(control(directory,{'action':'inject','kind':'uart','cycle':cycle,'hex':command_bytes[offset:offset+4096].hex()},timeout=120))
        (out/'course-command.bin').write_bytes(command_bytes)
        report.update(status='RAW_TUTOR_COMMAND_ADMITTED' if a.inject else 'GENERATED_TUTOR_PACKAGE',guest_identity=identity,ask=context,uart_sha256=hashlib.sha256(captured).hexdigest(),inference=proposal['inference'],package_sha256=sha(package),command=command,admission=boundaries,
            transport='OWNER_LOCAL_INTEGRITY_ONLY',receipt='No Installed, displayed, audible or mathematical receipt; observe actual4b1/724/paper completion',next_step='Run guest until actual install commit, then use guest LOAD control')
    except BaseException as error:report['error']=repr(error)
    try:
        if report.get('source_inputs')!=source_inventory():raise ValueError('complete consumed source changed')
        for name,record in report.get('tools',{}).items():
            if sha(Path(record['path']))!=record['sha256']:raise ValueError('consumed tool changed '+name)
        report['consumed_inputs_unchanged']=True
    except BaseException as error:
        report['status']='FAIL';report['source_guard_error']=repr(error)
    report['seconds']=time.monotonic()-started;(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ('status','seconds','error','next_step')}));return 0 if report['status']!='FAIL' else 1
if __name__=='__main__':raise SystemExit(main())
