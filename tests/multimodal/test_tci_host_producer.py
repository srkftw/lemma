"""Host producer faults and the actual C observer body; no RV64/browser claim."""
from pathlib import Path
import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
import shutil
import subprocess
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
def module(name):
    spec=importlib.util.spec_from_file_location('tci_'+name,ROOT/'tooling/lemmasim/tci'/f'{name}.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

class TciProducer(unittest.TestCase):
    def test_public_archive_checksum_rejects_before_extraction(self):
        builder=module('build')
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);(p/'source.tar').write_bytes(b'corrupted public source')
            with self.assertRaisesRegex(ValueError,'identity differs'):
                builder.acquire(dict(filename='source.tar',sha256='0'*64),p,p)

    def test_unsafe_archive_cannot_escape_source_root(self):
        builder=module('build')
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);archive=p/'bad.tar';out=p/'out';out.mkdir()
            with tarfile.open(archive,'w') as t:
                entry=tarfile.TarInfo('../escaped');entry.size=1;t.addfile(entry,io.BytesIO(b'x'))
            with self.assertRaises(tarfile.OutsideDestinationError):builder.extract(archive,out)
            self.assertFalse((p/'escaped').exists())

    def test_fresh_staging_floor_rejects_without_output(self):
        builder=module('build')
        with tempfile.TemporaryDirectory() as name:
            out=Path(name)/'unused'
            with patch.object(builder.shutil,'disk_usage',return_value=type('Disk',(),dict(free=4*1024**3-1))()):
                with self.assertRaisesRegex(RuntimeError,'4GiB'):builder.build(type('Args',(),dict(work_dir=out))())
            self.assertFalse(out.exists())

    def test_other_qemu_version_does_not_mutate_sources(self):
        patcher=module('patch_wasm')
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);(p/'VERSION').write_text('11.1.2\n');before={q.name:q.read_bytes() for q in p.iterdir()}
            with self.assertRaisesRegex(ValueError,'exact QEMU11.1.1'):patcher.apply(p,ROOT/'tooling/lemmasim/tci/lemma_browser_control.inc.c')
            self.assertEqual(before,{q.name:q.read_bytes() for q in p.iterdir()})

    def test_changed_first_upstream_anchor_rejects(self):
        patcher=module('patch_wasm')
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);(p/'VERSION').write_text('11.1.1\n');(p/'meson.build').write_text('changed upstream input\n')
            with self.assertRaisesRegex(ValueError,'anchor differs: meson.build'):patcher.apply(p,ROOT/'tooling/lemmasim/tci/lemma_browser_control.inc.c')
            self.assertEqual((p/'meson.build').read_text(),'changed upstream input\n')

class TciProducerMetadata(unittest.TestCase):
    """Filesystem metadata fixtures only: these modules never claim QEMU execution."""
    def fixture(self,root):
        builder=module('build');source=root/'source';source.mkdir();(source/'VERSION').write_text('11.1.1\n')
        build=root/'obj';build.mkdir();(build/'qemu-system-riscv64.js').write_text('/* metadata-only fixture */\n')
        (build/'qemu-system-riscv64.wasm').write_bytes(b'\x00asm\x01\x00\x00\x00')
        builder.write(root/'source-inputs.json',builder.identity(source))
        return builder,source,build

    def test_successful_metadata_binds_actual_source_and_required_fields(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);builder,source,build=self.fixture(root)
            value=builder.completed_build_metadata(root,source,build)
            self.assertEqual(value['exit_code'],0);self.assertEqual(value['source_file_count'],1)
            self.assertEqual(value['source_closure_sha256'],builder.sha(root/'source-inputs.json'))
            self.assertEqual(value['outputs']['qemu-system-riscv64.wasm']['sha256'],builder.sha(build/'qemu-system-riscv64.wasm'))
            self.assertEqual(value['outputs']['qemu-system-riscv64.wasm']['bytes'],8)

    def test_changed_actual_source_rejects_success_metadata(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);builder,source,build=self.fixture(root);(source/'VERSION').write_text('11.1.2\n')
            with self.assertRaisesRegex(ValueError,'source changed'):builder.completed_build_metadata(root,source,build)

    def test_missing_actual_output_rejects_success_metadata(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);builder,source,build=self.fixture(root);(build/'qemu-system-riscv64.wasm').unlink()
            with self.assertRaisesRegex(ValueError,'output missing'):builder.completed_build_metadata(root,source,build)

    def test_bad_wasm_header_rejects_success_metadata(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);builder,source,build=self.fixture(root);(build/'qemu-system-riscv64.wasm').write_bytes(b'not-wasm')
            with self.assertRaisesRegex(ValueError,'not a WebAssembly1'):builder.completed_build_metadata(root,source,build)

    def test_symlinked_actual_output_rejects_success_metadata(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);builder,source,build=self.fixture(root);p=build/'qemu-system-riscv64.js';p.unlink();p.symlink_to(source/'VERSION')
            with self.assertRaisesRegex(ValueError,'output missing'):builder.completed_build_metadata(root,source,build)

    def test_retained_exit_code_requires_exact_integer_zero(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);builder,source,build=self.fixture(root)
            metadata=builder.completed_build_metadata(root,source,build);metadata['result']='BUILT_WASM64_QEMU_TCI'
            builder.retained_source_identity(metadata,root/'source-inputs.json',source)
            for value in [False,0.0,None,'0',1]:
                with self.subTest(value=value):
                    with self.assertRaisesRegex(ValueError,'identity differs'):
                        builder.retained_source_identity(dict(metadata,exit_code=value),root/'source-inputs.json',source)

    def test_retained_source_count_requires_exact_positive_integer(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);builder,source,build=self.fixture(root)
            metadata=builder.completed_build_metadata(root,source,build);metadata['result']='BUILT_WASM64_QEMU_TCI'
            for value in [True,1.0,None,'1',0,2]:
                with self.subTest(value=value):
                    with self.assertRaisesRegex(ValueError,'identity differs'):
                        builder.retained_source_identity(dict(metadata,source_file_count=value),root/'source-inputs.json',source)

    def test_known_schema_roots_are_distinct_and_unknown_rejected(self):
        builder=module('build');receipt=Path('/retained/run/build.json')
        self.assertEqual(builder.retained_producer_input_root({'schema':'lemma-tci-wasm-build/1'},receipt),Path('/retained'))
        self.assertEqual(builder.retained_producer_input_root({'schema':'lemma-tci-public-build/1','producer_input_root':str(builder.ROOT)},receipt),builder.ROOT)
        with self.assertRaisesRegex(ValueError,'input root differs'):
            builder.retained_producer_input_root({'schema':'lemma-tci-public-build/1','producer_input_root':'/unadmitted'},receipt)
        with self.assertRaisesRegex(ValueError,'Unknown retained'):
            builder.retained_producer_input_root({'schema':'made-up-host-build/1'},receipt)

class TciStoppedCpuObservation(unittest.TestCase):
    def test_actual_c_body_uses_thread_acknowledgement_even_when_paused_or_wfi(self):
        body=(ROOT/'tooling/lemmasim/tci/lemma_browser_control.inc.c').read_text()
        begin=body.index('/* BEGIN lemma-qemu-cpu-stop/1:')
        end=body.index('/* END lemma-qemu-cpu-stop/1. */',begin)
        actual=body[begin:end]
        cc=shutil.which('cc') or shutil.which('clang')
        if not cc:raise RuntimeError('actual stopped-CPU C observer check requires the pinned host C compiler')
        prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef struct { bool stopped,halted; } CPUState;
typedef struct { uint64_t count,stopped; bool all; } QDict;
static CPUState cpus[3];static unsigned n;static bool running;
#define CPU_FOREACH(cpu) for(unsigned i=0;i<n&&((cpu)=&cpus[i],1);i++)
static bool bql_locked(void){return true;}
static bool cpu_is_stopped(CPUState *c){return c->stopped||!running;}
static void qdict_put_str(QDict *d,const char*k,const char*v){(void)d;assert(!strcmp(k,"stop_boundary_contract")&&!strcmp(v,"lemma-qemu-cpu-stop/1"));}
static void qdict_put_int(QDict *d,const char*k,uint64_t v){if(!strcmp(k,"cpu_count"))d->count=v;else{assert(!strcmp(k,"cpus_stopped"));d->stopped=v;}}
static void qdict_put_bool(QDict *d,const char*k,bool v){assert(!strcmp(k,"all_cpus_stopped"));d->all=v;}
'''
        suffix=r'''
int main(void){
 QDict d={0};running=false;n=1;cpus[0]=(CPUState){.stopped=false,.halted=true};
 lemma_browser_cpu_stop_observation(&d);if(d.count!=1||d.stopped||d.all)return 1;
 cpus[0].stopped=true;lemma_browser_cpu_stop_observation(&d);if(d.stopped!=1||!d.all)return 2;
 n=0;lemma_browser_cpu_stop_observation(&d);if(d.count||d.stopped||d.all)return 3;
 n=3;cpus[1].stopped=false;cpus[2].stopped=true;
 lemma_browser_cpu_stop_observation(&d);if(d.count!=3||d.stopped!=2||d.all)return 4;
 cpus[1].stopped=true;lemma_browser_cpu_stop_observation(&d);if(d.stopped!=3||!d.all)return 5;
 return 0;
}
'''
        mutant=actual.replace('if(cpu->stopped)','if(cpu_is_stopped(cpu))')
        self.assertNotEqual(actual,mutant)
        with tempfile.TemporaryDirectory(prefix='lemma-stop-observer-') as tmp:
            root=Path(tmp)
            for label,fragment,expected in [('actual',actual,0),('paused-runstate-mutant',mutant,1)]:
                source=root/(label+'.c');binary=root/label;source.write_text(prefix+fragment+suffix)
                built=subprocess.run([cc,'-std=c11',str(source),'-o',str(binary)],capture_output=True,timeout=15)
                self.assertEqual(built.returncode,0,built.stderr.decode())
                result=subprocess.run([str(binary)],cwd=root,timeout=5)
                self.assertEqual(result.returncode,expected)

if __name__=='__main__':unittest.main()
