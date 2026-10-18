#!/usr/bin/env python3
"""Bounded localhost browser observer of the actual portable RTL/Lean probe.

Only explicit synthetic component artifacts are served. This is no workbook,
consumer performance, sensor accuracy or physical qualification receipt.
"""
import argparse
import hashlib
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for key in ('wasm-build', 'guest', 'rom', 'binding', 'work-dir'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 600 or not 1024 <= args.port <= 65535:
        parser.error('bounded timeout and unprivileged port required')
    out = args.work_dir.resolve()
    if not out.is_relative_to(ROOT / 'build'):
        parser.error('ignored owned output required')
    out.mkdir(parents=True, exist_ok=False)
    files = {
        '/probe.mjs': ROOT / 'sim/browser/multimodal_probe.mjs',
        '/machine.mjs': args.wasm_build / 'machine.mjs',
        '/machine.wasm': args.wasm_build / 'machine.wasm',
        '/image.elf': args.guest, '/boot.bin': args.rom,
        '/machine.dtb': args.binding / 'platform.dtb',
        '/descriptor.bin': args.binding / 'descriptor.bin',
    }
    manifest = {key: {'path': str(path.resolve()), 'sha256': sha(path)}
                for key, path in files.items()}
    production = args.wasm_build / 'build.json'
    metadata = json.loads(production.read_text())
    if metadata.get('profile') != 'lemma-silicon-dev/0.14.0':
        raise ValueError('exact admitted portable profile required')
    manifest['production'] = {'path': str(production.resolve()), 'sha256': sha(production)}
    manifest['server'] = {'path': str(Path(__file__).resolve()), 'sha256': sha(Path(__file__))}
    report = {'schema': 'lemma-multimodal-browser-component/v1', 'result': 'FAIL',
              'scope': __doc__, 'inputs': manifest, 'limits': {'wall_seconds': args.timeout}}
    html = '''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Lemma portable RTL component verification</title>
<h1>Actual Lean controller probe in browser RTL/Wasm</h1>
<p>Synthetic component only. This does not qualify the complete workbook.</p>
<button id="run">Run actual guest</button><pre id="result">Ready</pre>
<script type="module">
import createMachine from './machine.mjs'; import {runProbe} from './probe.mjs';
const button=document.querySelector('#run'), output=document.querySelector('#result');
button.onclick=async()=>{button.disabled=true;output.textContent='RUNNING';let receipt;
try {const artifacts={};for(const name of ['image.elf','boot.bin','machine.dtb','descriptor.bin']) {
const response=await fetch('./'+name);if(!response.ok)throw Error(name+' fetch failed');
artifacts[name]=new Uint8Array(await response.arrayBuffer());}
receipt=await runProbe(createMachine,artifacts);receipt.records=Array.from(receipt.records);
receipt.uart=Array.from(receipt.uart);
}catch(error){receipt={result:'FAIL',error:String(error)};}
receipt.browser={userAgent:navigator.userAgent,hardwareConcurrency:navigator.hardwareConcurrency,
crossOriginIsolated,wasm:typeof WebAssembly==='object'};
const visible={result:receipt.result,error:receipt.error,scope:receipt.scope,
cycles:receipt.cycles,elapsedSeconds:receipt.elapsedSeconds,rawValues:receipt.rows?.map(row=>row[0]),
pcm:receipt.pcm,browser:receipt.browser};output.textContent=JSON.stringify(visible,null,2);
const saved=await fetch('./result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(receipt)});
if(!saved.ok)output.textContent+='\\nRECEIPT REJECTED';};
</script></html>'''.encode()
    complete = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, body, kind):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
            self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/':
                self.send(200, html, 'text/html; charset=utf-8')
            elif self.path in files:
                kind = 'application/wasm' if self.path.endswith('.wasm') else 'text/javascript' if self.path.endswith('.mjs') else 'application/octet-stream'
                self.send(200, files[self.path].read_bytes(), kind)
            else:
                self.send(404, b'unknown artifact', 'text/plain')

        def do_POST(self):
            nonlocal complete
            size = int(self.headers.get('Content-Length', '0'))
            if self.path != '/result' or not 0 < size <= 1048576:
                self.send(400, b'invalid receipt', 'text/plain')
                return
            receipt = json.loads(self.rfile.read(size))
            if receipt.get('result') not in ('PASS', 'FAIL') or not receipt.get('browser', {}).get('userAgent'):
                self.send(400, b'missing browser execution', 'text/plain')
                return
            if any(sha(Path(value['path'])) != value['sha256'] for value in manifest.values()):
                self.send(409, b'consumed source changed', 'text/plain')
                return
            report.update(receipt)
            report['inputs'] = manifest
            complete = True
            self.send(200, b'retained', 'text/plain')

    start = time.monotonic()
    server = HTTPServer(('127.0.0.1', args.port), Handler)
    server.timeout = 1
    print(f'http://127.0.0.1:{args.port}/', flush=True)
    try:
        while not complete and time.monotonic() - start < args.timeout:
            server.handle_request()
        if not complete:
            report['error'] = 'original browser wall deadline expired'
    finally:
        server.server_close()
        report['elapsed_seconds'] = time.monotonic() - start
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
