#!/usr/bin/env python3
"""Bounded source/tool-bound native CommonOFDM profile12 build.
Build qualification only; actual guest/device/IRQ/owned-queue qualification is
separate. The existing CVW/LemmaSim host runtime supplies raw clocks and wires.
"""
from __future__ import annotations
import argparse,hashlib,json,shutil,time
from pathlib import Path
from check_silicon import ROOT,sha,device_build
from silicon_compute import prepare,source_manifest,snapshot_inputs

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--jobs',type=int,choices=[1,2],default=2);p.add_argument('--timeout',type=int,default=600)
 a=p.parse_args();out=a.work_dir.resolve()
 if not out.is_relative_to(ROOT/'build') or out.exists() or not 30<=a.timeout<=600:p.error('unused build output and30..600s bound required')
 out.mkdir(parents=True);start=time.monotonic();result={'schema':'lemma-common-ofdm-native12-build/1','status':'FAIL','scope':'actual changed-source build only; no CPU/IRQ/radio integration PASS','plan':{'build_seconds':a.timeout,'jobs':a.jobs}}
 try:
  dep=ROOT/'build/silicon/deps/cvw';prepare(dep);m=source_manifest(dep,'lemma-silicon-dev/0.12.0');m['configuration']='external-ram-128MiB';identity=snapshot_inputs(m,dep);m['snapshot_identity']=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  headers=out/'generated';headers.mkdir();header=headers/'lemma_runtime_identity.h';header.write_text('#pragma once\n#define LEMMA_RUNTIME_IDENTITY "'+m['snapshot_identity']+'"\n');m['runtime_identity_header']={'path':str(header),'sha256':sha(header)}
  files={Path(n):v for field in ('sha256','configuration_includes') for n,v in m[field].items()}
  for field in ('host_toolchain_inputs','binding_generator_inputs','host_runtime'):
   files.update({ROOT/k:v for k,v in m[field].items()})
  for field in ('build_driver','upstream_patch','host_adapter'):files[ROOT/m[field]['path']]=m[field]['sha256']
  files[Path(m['host_include_dir'])/'lemma_silicon_binding.h']=m['host_binding_sha256']
  files[header]=m['runtime_identity_header']['sha256']
  files[ROOT/'scripts/check_wifi_machine.py']=sha(ROOT/'scripts/check_wifi_machine.py')
  files[ROOT/'sim/profiles/lemma-silicon-dev-0.12.0.json']=m['profile_sha256']
  archive=out/'consumed-source-root';archive.mkdir()
  for f,digest in files.items():
   if sha(f)!=digest:raise RuntimeError('native input moved before compilation: '+str(f))
   relative=f.relative_to(ROOT);dst=archive/relative;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dst)
  # Archive before admission; exact final source checks close this real build.
  result['source_archive']=str(archive);result['source_inventory']={str(k.relative_to(ROOT)):v for k,v in files.items()}
  (out/'sources.json').write_text(json.dumps(m,indent=2)+'\n');result['manifest_sha256']=sha(out/'sources.json')
  argv=['verilator',*m['build_options']['verilator'],'-j',str(a.jobs),'--Mdir',str(out/'obj'),'-o','lemma-rtl','-MAKEFLAGS',m['build_options']['make_flags'],'-CFLAGS',m['build_options']['host_cflags']+' -I'+str(headers)+' -I'+m['host_include_dir']]
  argv+=['-I'+d for d in m['include_dirs']]+m['sources']+[str(ROOT/'sim/rtl/host/main.cpp'),str(ROOT/'sim/rtl/host/machine_runtime.cpp'),str(ROOT/'sim/host/backing_io.cpp'),str(ROOT/'sim/host/backing_io_posix.cpp'),str(ROOT/'sim/companion/backing_peer.cpp'),str(ROOT/'sim/radio/ble_peer_transport.cpp'),str(ROOT/'sim/usb/usb_transport.cpp')]
  built,tools=device_build(argv,out/'tools.json',out/'build.log',a.timeout);result['command']=built;result['tools']=tools
  if any(sha(f)!=digest for f,digest in files.items()):raise RuntimeError('native input moved during real build; artifact unqualified')
  binary=out/'obj/lemma-rtl';m['binary_sha256']=sha(binary);m['build_jobs']=a.jobs;m['build_argv']=built['argv'];(out/'build.json').write_text(json.dumps(m,indent=2)+'\n')
  result.update(status='PASS_NATIVE_BUILD_ONLY',runtime_identity=m['snapshot_identity'],binary={'path':str(binary),'sha256':sha(binary)},build_manifest_sha256=sha(out/'build.json'),input_count=len(files))
 except BaseException as e:result['error']=repr(e);raise
 finally:result['wall_seconds']=time.monotonic()-start;(out/'result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 print('COMMON_OFDM_NATIVE12:PASS_NATIVE_BUILD_ONLY; actual guest qualification NOT_RUN')
if __name__=='__main__':main()
