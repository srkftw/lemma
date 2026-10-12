"""Local distribution admission and actual HTTP boundaries, not guest execution."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from lemmasim_browser import validated_bundle, local_server, validate_wasm_inputs

def fixture(root):
    names=['index.html','worker.js','app.js','machine.mjs','machine.wasm','boot.bin']
    names += [w+'/'+k for w in ('notebook','initializer') for k in ('image','dtb','descriptor')]
    files={}
    for name in names:
        p=root/name;p.parent.mkdir(exist_ok=True);p.write_bytes(name.encode())
        files[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    wasm={'status':'BUILT','profile':'lemma-silicon-dev/0.3.0',
          'outputs':{n:files[n] for n in ('machine.mjs','machine.wasm')}}
    (root/'wasm-build.json').write_text(json.dumps(wasm))
    m={'schema':'lemmasim-browser-bundle/1','profile':wasm['profile'],'width':1650,'height':2200,
       'files':files,'rom':{'path':'boot.bin','sha256':files['boot.bin']},
       'wasm_build_sha256':hashlib.sha256((root/'wasm-build.json').read_bytes()).hexdigest(),
       'workloads':{w:{k:{'path':w+'/'+k,'sha256':files[w+'/'+k]} for k in ('image','dtb','descriptor')}
                    for w in ('notebook','initializer')}}
    (root/'bundle.json').write_text(json.dumps(m))
    return m

class BrowserBundleBoundary(unittest.TestCase):
    def test_reuse_checks_generator_policy_and_portable_runtime_not_only_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'built';source.mkdir()
            def item(name):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(name)
                return hashlib.sha256(path.read_bytes()).hexdigest()
            profile='sim/profiles/lemma-silicon-dev-0.3.0.json'
            m={'profile':'lemma-silicon-dev/0.3.0',
               'portable_inputs':{'adapter.cpp':item('adapter.cpp')},
               'binding_generator_inputs':{'generator.py':item('generator.py'),profile:item(profile)},
               'host_toolchain_inputs':{'flake.lock':item('flake.lock')},
               'sha256':{str(root/'model.sv'):item('model.sv')},
               'configuration_includes':{str(root/'config.vh'):item('config.vh')},
               'verilator_runtime_inputs':{str(root/'tool/runtime.h'):item('tool/runtime.h')},
               'host_include_dir':str(root/'binding'),
               'host_binding_sha256':item('binding/lemma_silicon_binding.h'),
               'profile_sha256':item(profile),
               'portable_verilator_patch':{n:item('built/verilator-portable/'+n)
                   for n in ('verilatedos_c.h','verilated_threads.cpp')},
               'outputs':{n:item('built/'+n) for n in ('machine.mjs','machine.wasm')}}
            for key,name in [('build_driver','driver.py'),('upstream_patch','patch.py')]:
                m[key]={'path':name,'sha256':item(name)}
            with patch('lemmasim_browser.ROOT',root):
                validate_wasm_inputs(source,m)
                for name in ('generator.py','driver.py','patch.py','tool/runtime.h',
                             'built/verilator-portable/verilated_threads.cpp'):
                    p=root/name;before=p.read_bytes();p.write_bytes(b'changed policy/runtime')
                    with self.subTest(input=name),self.assertRaises(ValueError):validate_wasm_inputs(source,m)
                    p.write_bytes(before)
                del m['binding_generator_inputs']
                with self.assertRaises(ValueError):validate_wasm_inputs(source,m)

    def test_missing_changed_unlisted_and_symlinked_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root);validated_bundle(root)
            p=root/'app.js';original=p.read_bytes();p.write_bytes(b'changed')
            with self.assertRaises(ValueError):validated_bundle(root)
            p.unlink()
            with self.assertRaises(ValueError):validated_bundle(root)
            p.symlink_to('/dev/null')
            with self.assertRaises(ValueError):validated_bundle(root)
            p.unlink();p.write_bytes(original);(root/'extra.js').write_bytes(b'extra')
            with self.assertRaises(ValueError):validated_bundle(root)

    def test_guest_and_wasm_identities_and_unique_metadata_are_load_bearing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);m=fixture(root);p=root/'bundle.json'
            m['workloads']['notebook']['image']['sha256']='a'*64;p.write_text(json.dumps(m))
            with self.assertRaises(ValueError):validated_bundle(root)
            m=fixture(root);m['wasm_build_sha256']='b'*64;p.write_text(json.dumps(m))
            with self.assertRaises(ValueError):validated_bundle(root)
            p.write_text('{"files":{},"files":{}}')
            with self.assertRaises(ValueError):validated_bundle(root)
            for path in ('../escape','/absolute','a//b','./index.html'):
                m=fixture(root);m['files'][path]='c'*64;p.write_text(json.dumps(m))
                with self.assertRaises(ValueError):validated_bundle(root)

    def test_loopback_http_serves_only_validated_bytes_and_rejects_later_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root);server=local_server(root,0)
            thread=threading.Thread(target=lambda:server.serve_forever(poll_interval=.02),daemon=True);thread.start()
            try:
                base='http://127.0.0.1:'+str(server.server_port)
                with urlopen(base+'/',timeout=2) as response:
                    self.assertEqual(response.read(),b'index.html')
                    self.assertEqual(response.headers['Cross-Origin-Embedder-Policy'],'require-corp')
                with urlopen(base+'/machine.wasm',timeout=2) as response:
                    self.assertEqual(response.headers['Content-Type'],'application/wasm')
                for path in ('/../outside','/%2e%2e/outside','/notebook/','/missing'):
                    with self.assertRaises(HTTPError) as failure:urlopen(base+path,timeout=2)
                    self.assertEqual(failure.exception.code,404)
                (root/'app.js').write_bytes(b'changed')
                with self.assertRaises(HTTPError) as failure:urlopen(base+'/app.js',timeout=2)
                self.assertEqual(failure.exception.code,503)
            finally:server.shutdown();server.server_close();thread.join(timeout=2)

if __name__=='__main__':unittest.main()
