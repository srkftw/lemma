#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile the real QEMU executable object closure and link its paced UART path.

Run inside the pinned shell.nix. The predecessor source, outputs and build tree
remain unchanged. Every link-consumed upstream object is compiled because the old producer did
not archive its object hashes. External host SDK libraries are content-bound
reused inputs. This is not a guest compiler or a fabricated runtime receipt.
"""
from pathlib import Path
import argparse,json,os,resource,shlex,shutil,signal,subprocess,time,tarfile
import build as producer
from concurrent.futures import ThreadPoolExecutor
from threading import Event,Lock

def main(a):
    out=a.output_dir.resolve();out.mkdir(exist_ok=False)
    start=time.monotonic();original=producer.read(a.receipt);source=a.source_root.resolve();obj=a.build_dir.resolve()
    inventory=a.receipt.parent/'source-inputs.json'
    previous=producer.read(inventory);observed_source=producer.identity(source)
    if original.get('result')!='BUILT_WASM64_QEMU_TCI' or original.get('exit_code')!=0 or original.get('source_file_count')!=len(previous) or producer.sha(inventory)!=original.get('source_closure_sha256'):raise ValueError('Predecessor production/source inventory differs')
    for name,item in original['outputs'].items():
        candidate=obj/name
        if producer.sha(candidate)!=item['sha256'] and a.retained_control:candidate=a.retained_control.parent/name
        if not candidate.is_file() or producer.sha(candidate)!=item['sha256'] or candidate.stat().st_size!=item['bytes']:raise ValueError('Predecessor retained actual output changed:'+name)
    initial=producer.sources();report={'schema':'lemma-tci-public-build/1','result':'FAIL','producer_input_root':str(producer.ROOT),'production_mode':'fresh-upstream-objects-and-real-link/1','inputs':initial,'direct_helpers':original.get('direct_helpers',False),'predecessor':{'receipt':str(a.receipt.resolve()),'sha256':producer.sha(a.receipt),'source_closure_sha256':producer.sha(inventory),'outputs':original['outputs']},'limits':{'whole_seconds':a.timeout,'jobs':2,'minimum_free_bytes':2<<30,'minimum_available_bytes':2<<30,'tree_rss_bytes':6<<30},'scope':'Fresh compilation of every upstream CPU/controller/object consumed by the real Wasm link; external host SDK libraries are content-bound reused inputs. No guest execution, browser responsiveness or RTL timing claim.'}
    process=None
    try:
        if shutil.disk_usage(out).free<4<<30:raise RuntimeError('4GiB staging floor')
        # Keep a complete byte-identical upstream source tree with an explicit
        # two-file overlay. Headers elsewhere retain their predecessor bytes.
        copy=out/'source';subprocess.run(['cp','-a','--reflink=auto',str(source),str(copy)],check=True)
        changed_old={k for k in previous.keys()|observed_source.keys() if previous.get(k)!=observed_source.get(k)}
        if changed_old:
            # The retained research tree may have advanced its optional helper
            # experiment after this producer. Reconstruct only exact upstream
            # helper bytes and the already archived original bridge, then
            # require the complete predecessor inventory before any overlay.
            helpers=set(producer.read(producer.HERE/'typed_helpers.json')['sources'])
            if not changed_old<=helpers|{'hw/riscv/lemma_browser_control.inc.c'} or not a.upstream_archive or not a.retained_control:raise ValueError('Unrecoverable predecessor source drift')
            dependency=next(x for x in producer.read(producer.HERE/'dependencies.json')['sources'] if x['filename']=='qemu-11.1.1.tar.xz')
            if producer.sha(a.upstream_archive)!=dependency['sha256']:raise ValueError('Original upstream source archive identity differs')
            with tarfile.open(a.upstream_archive) as archive:
                for name in changed_old&helpers:
                    value=archive.extractfile('qemu-11.1.1/'+name).read();(copy/name).write_bytes(value)
            if 'hw/riscv/lemma_browser_control.inc.c' in changed_old:shutil.copyfile(a.retained_control,copy/'hw/riscv/lemma_browser_control.inc.c')
            report['exact_predecessor_reconstruction']={'files':sorted(changed_old),'upstream_archive_sha256':producer.sha(a.upstream_archive),'retained_control_sha256':producer.sha(a.retained_control)}
        if producer.identity(copy)!=previous:raise ValueError('Reconstructed complete predecessor source identity differs')
        shutil.copyfile(producer.ROOT/'sim/host/lemma_uart_qemu.inc.c',copy/'hw/riscv/lemma_uart_qemu.inc.c')
        p=copy/'hw/riscv/lemma_qemu.c';text=p.read_text();anchor='    object_class_property_add_str(klass,"external-uart",NULL,lemma_uart_inject);\n'
        if text.count(anchor)!=1:raise ValueError('Exact predecessor UART property anchor differs')
        text=text.replace(anchor,anchor+'    object_class_property_add_str(klass,"raw-uart-paced-version",lemma_uart_paced_version,NULL);\n    object_class_property_add_str(klass,"external-uart-paced",NULL,lemma_uart_inject_paced);\n');p.write_text(text)
        shutil.copyfile(producer.HERE/'lemma_browser_control.inc.c',copy/'hw/riscv/lemma_browser_control.inc.c')
        current=producer.identity(copy);changed={k for k in previous.keys()|current.keys() if previous.get(k)!=current.get(k)}
        if not {'hw/riscv/lemma_qemu.c','hw/riscv/lemma_uart_qemu.inc.c'}<=changed or not changed<={'hw/riscv/lemma_qemu.c','hw/riscv/lemma_uart_qemu.inc.c','hw/riscv/lemma_browser_control.inc.c'}:raise ValueError('Controller-only source overlay differs')
        producer.write(out/'source-inputs.json',current);report['changed_sources']={k:{'before':previous[k],'after':current[k]} for k in sorted(changed)}
        database=json.loads(subprocess.check_output(['ninja','-t','compdb','-x'],cwd=obj,text=True))
        target='libqemu-riscv64-softmmu.a.p/hw_riscv_lemma_qemu.c.o'
        def command(output):
            matches=[x for x in database if x.get('output')==output]
            if len(matches)!=1:raise ValueError('Exact real Ninja command absent:'+output)
            return shlex.split(matches[0]['command'])
        original_link=command('qemu-system-riscv64.js');link=list(original_link)
        deps=subprocess.check_output(['ninja','-t','deps'],cwd=obj,text=True)
        producer.write(out/'dependency-observer.json',{'sha256':__import__('hashlib').sha256(deps.encode()).hexdigest(),'source_drift':sorted(changed_old)})
        # The predecessor did not archive object hashes. Recompile the entire
        # real executable object closure; do not infer old object provenance
        # from mutable research-tree timestamps or a matching old final Wasm.
        direct={arg for arg in original_link if arg.endswith('.o')}
        archives={arg for arg in original_link if arg.endswith('.a') and any(x.get('output')==arg for x in database)}
        archive_commands={}
        invalidated=set(direct)
        for name in sorted(archives):
            argv=command(name)
            if '&&' not in argv:raise ValueError('Unknown exact archive command')
            argv=argv[argv.index('&&')+1:]
            if not argv or argv[0]!='emar':raise ValueError('Unknown real archive compiler')
            archive_commands[name]=argv
            invalidated.update(arg for arg in argv if arg.endswith('.o'))
        if len(invalidated)<500:raise ValueError('Incomplete fresh executable object closure')
        compile_commands=[];replacements={}
        for number,name in enumerate(sorted(invalidated)):
            original_compile=command(name);compile=[];fresh=out/('fresh-'+str(number)+'.o');replacements[name]=str(fresh)
            for arg in original_compile:
                if arg==name:arg=str(fresh)
                elif arg==name+'.d':arg=str(fresh)+'.d'
                else:arg=arg.replace(str(source),str(copy)).replace('../source/qemu-11.1.1',str(copy))
                compile.append(arg)
            compile_commands.append({'output':name,'original':original_compile,'argv':compile})
        fresh_archives={name:str(out/('archive-'+str(i)+'.a')) for i,name in enumerate(sorted(archives))}
        for i,arg in enumerate(link):
            if arg in replacements:link[i]=replacements[arg]
            elif arg in fresh_archives:link[i]=fresh_archives[arg]
            elif arg=='qemu-system-riscv64.js':link[i]=str(out/'qemu-system-riscv64.js')
        if not all(link.count(replacements[name])==1 for name in direct):raise ValueError('Real link omitted fresh direct object')
        archive_steps=[]
        for name,argv in archive_commands.items():
            fresh=[replacements.get(arg,fresh_archives.get(arg,arg)) for arg in argv]
            archive_steps.append((name,fresh))
        auxiliary={str(p.resolve()):producer.sha(p) for p in obj.rglob('*') if p.is_file() and p.suffix in ('.h','.inc','.c','.cpp') and not p.is_symlink()}
        producer.write(out/'generated-build-inputs.json',auxiliary)
        report['generated_build_inputs_sha256']=producer.sha(out/'generated-build-inputs.json')
        report['fresh_object_count']=len(compile_commands);report['invalidated_objects']=sorted(invalidated)
        # Bind every retained link input and every consumed compile header.
        retained={}
        for arg in original_link:
            candidate=(obj/arg).resolve()
            if candidate.is_file() and arg.endswith('.a') and arg not in archives:retained[str(candidate)]=producer.sha(candidate)
        if len(retained)<5:raise ValueError('Incomplete external host SDK library closure')
        producer.write(out/'retained-link-inputs.json',retained);report['retained_link_inputs_sha256']=producer.sha(out/'retained-link-inputs.json');report['retained_link_input_count']=len(retained)
        producer.write(out/'commands.json',{'working_directory':str(obj),'original_link':original_link,'compile':compile_commands,'archives':archive_steps,'link':link})
        env=os.environ.copy();env.update(EMCC_CORES='1',BINARYEN_CORES='1',EM_CACHE=str(out/'emcache'))
        # Isolate the Emscripten cache; its existing compiled SDK libraries are
        # unchanged cache inputs, not fresh compiler production.
        oldcache=obj.parent/'emcache'
        if not oldcache.is_dir():raise ValueError('Retained SDK cache absent')
        subprocess.run(['cp','-a','--reflink=auto',str(oldcache),str(out/'emcache')],check=True)
        report['sdk_cache']='isolated copy of retained SDK cache; compiler/link actions below are fresh'
        cancelled=Event();active_groups=set();group_lock=Lock()
        def run_step(phase,argv):
            if cancelled.is_set():raise RuntimeError("Owned producer cancelled after failed action")
            with (out/(phase+'.log')).open('wb') as log:
                child=subprocess.Popen(argv,cwd=obj,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                with group_lock:active_groups.add(child.pid)
                try:
                    while child.poll() is None:
                        with group_lock:groups=set(active_groups)
                        rss=0
                        for stat in Path("/proc").glob("[0-9]*/stat"):
                            try:
                                fields=stat.read_text().rsplit(")",1)[1].split()
                                if int(fields[2]) in groups:rss+=int(fields[21])*os.sysconf("SC_PAGE_SIZE")
                            except (OSError,ValueError,IndexError):pass
                        report["peak_tree_rss_bytes"]=max(report.get("peak_tree_rss_bytes",0),rss)
                        if cancelled.is_set() or rss>6<<30:raise RuntimeError("Owned producer cancelled or6GiB tree RSS limit")
                        available=next(int(row.split()[1])*1024 for row in Path('/proc/meminfo').read_text().splitlines() if row.startswith('MemAvailable:'))
                        if time.monotonic()-start>a.timeout or shutil.disk_usage(out).free<2<<30 or available<2<<30:raise RuntimeError('Original whole/resource budget reached')
                        time.sleep(.25)
                    if child.returncode:raise RuntimeError(phase+' failed; inspect actual log')
                except BaseException:
                    cancelled.set();raise
                finally:
                    with group_lock:active_groups.discard(child.pid)
                    if child.poll() is None:
                        os.killpg(child.pid,signal.SIGTERM)
                        try:child.wait(timeout=5)
                        except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
        # Two independent actual compile subprocesses; archive/link remain
        # sequential after every required object has terminal success.
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(run_step,'compile-'+str(i),item['argv']) for i,item in enumerate(compile_commands)]
            for future in futures:future.result()
        for i,(name,argv) in enumerate(archive_steps):run_step('archive-'+str(i),argv)
        run_step('real-wasm-link',link)
        if any(producer.sha(name)!=value for name,value in auxiliary.items()):raise ValueError('Generated build/header input changed')
        if initial!=producer.sources() or producer.identity(source)!=observed_source or producer.identity(copy)!=current:raise ValueError('Source changed during controller production')
        for name,digest in retained.items():
            if producer.sha(name)!=digest:raise ValueError('Reused link input changed:'+name)
        report.update(producer.completed_build_metadata(out,copy,out));report['result']='BUILT_WASM64_QEMU_TCI'
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        report['elapsed_seconds']=time.monotonic()-start;report['peak_child_rss_bytes']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024;producer.write(out/'build.json',report)
    print(out/'build.json')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--build-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--timeout',type=int,default=1200);p.add_argument('--upstream-archive',type=Path);p.add_argument('--retained-control',type=Path);a=p.parse_args()
    if not 30<=a.timeout<=1200:raise ValueError('Whole budget outside30..1200seconds')
    main(a)
