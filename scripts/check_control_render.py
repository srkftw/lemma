#!/usr/bin/env python3
"""Genuine course-control aligned spans1: independent Actions/LLVM/RV64 object.
Component only: no installed Notebook, CPU speedup or controller completion.
"""
import argparse,fcntl,json,os,re,resource,subprocess,time
from pathlib import Path
from build_core0 import LLC_ARGUMENTS
from core0_common import run_bounded,sha256,require_tools
from build_kernel import source_inputs
ROOT=Path(__file__).resolve().parents[1]
EXPECTED={'Lemma.Courses.ControlRender.'+n for n in ['validGeometry','hexDigit','identityCharacter','character','bytesStep','spanStep','renderControls','renderIdentity']}
EXPECTED|={'Lemma.Ink.Surface.framebuffer','Lemma.Ink.Surface.letter','Lemma.Courses.PackageRender.glyph','Lemma.Courses.PackageRender.packedCellRow','Lemma.Courses.PackageRender.alignedSpanWord','Lemma.User.Memory.write64','Lemma.User.Memory.write8'}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);a=p.parse_args();out=a.work_dir.resolve()
 if out.exists() or not out.is_relative_to(ROOT/'build'):p.error('unused ignored output required')
 out.mkdir(parents=True);start=time.monotonic();resource.setrlimit(resource.RLIMIT_AS,(16<<30,16<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30));r={'status':'FAIL','scope':__doc__,'bounds':{'whole_seconds':600,'command_seconds':180,'address_space_bytes':16<<30,'file_bytes':1<<30},'commands':[]}
 try:
  before=source_inputs(ROOT)
  for n in ('scripts/check_control_render.py','scripts/control_render_reference.py','tests/courses/ControlRender.lean'):before[n]=sha256(ROOT/n)
  r.update(source_inputs=before,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),dirty_paths=subprocess.check_output(['git','status','--short'],text=True).splitlines())
  tools=require_tools(('lake','lean','opt','llc','llvm-nm','llvm-readelf','llvm-objdump'));r['tools']={n:{'path':v,'sha256':sha256(Path(v))}for n,v in tools.items()}
  if any(not n.startswith('/nix/store/')for n in tools.values()):raise ValueError('pinned tools required')
  def run(label,argv,env=None,cwd=ROOT):
   remaining=600-(time.monotonic()-start)
   if remaining<=0:raise RuntimeError('original aggregate deadline')
   q=run_bounded(argv,cwd=cwd,env={**os.environ,'LEAN_NUM_THREADS':'2',**(env or {})},timeout_seconds=min(180,remaining));(out/(label+'.log')).write_bytes(q.stdout+q.stderr);r['commands'].append({'label':label,'argv':list(q.argv),'seconds':q.elapsed_seconds,'returncode':q.returncode})
   if q.returncode:raise RuntimeError('actual command failed: '+label)
   return q.stdout.decode()
  run('independent-reference',['python3',str(ROOT/'scripts/control_render_reference.py'),'--output-dir',str(out/'reference')])
  with (ROOT/'build/task006-lake.lock').open('a')as lock:
   fcntl.flock(lock,fcntl.LOCK_EX);run('build',[tools['lake'],'build','Lemma.Courses.ControlRender','Lemma.Compiler.ControlRenderExport'])
   text=run('actions',[tools['lake'],'env','lean','--run',str(ROOT/'tests/courses/ControlRender.lean')],{'LEMMA_CONTROL_REFERENCE':str(out/'reference')})
   if text.count('CONTROL_ALIGNED1:PASS')!=1:raise RuntimeError('missing independent actual Action result')
   export=out/'Export.lean';export.write_text('import Lemma.Compiler.ControlRenderExport\n#lemma_export_controls\n');text=run('export',[tools['lake'],'env','lean',str(export)],{'LEMMA_CONTROL_OUT':str(out/'component')})
   if text.count('CONTROL_GENUINE_EXPORT:PASS')!=1:raise RuntimeError('missing genuine export')
  d=out/'component';u=json.loads((d/'unit.json').read_text());canonical=lambda n:re.sub(r'^_private\.[^.]+(?:\.[^.]+)*?\.[0-9]+\.(Lemma\..*)$',r'\1',n)
  names={canonical(x['source']):x['symbol']for x in u['functions']}
  if u['schema']!='lemma-course-control-aligned/1' or u['contract_version']!='core0-user-v0.1' or set(names)!=EXPECTED or len(u['functions'])!=15 or set(u['execution_ops'])!={'execution.virtual-write8','execution.virtual-write64'}or u['device_ops']:raise RuntimeError('source/profile/effect closure differs')
  symbols=set(names.values());run('verify',[tools['opt'],'-passes=verify','-disable-output',str(d/'program.ll')]);run('opt',[tools['opt'],'-S','-passes=default<O2>',str(d/'program.ll'),'-o',str(d/'program.opt.ll')])
  for phase in ('program.ll','program.opt.ll'):
   ir=(d/phase).read_text();defs=set(re.findall(r'(?m)^define[^\n]*@([A-Za-z_0-9.$]+)\(',ir));decls=set(re.findall(r'(?m)^declare[^\n]*@([A-Za-z_0-9.$]+)\(',ir));calls=set(re.findall(r'\bcall[^\n]*@([A-Za-z_0-9.$]+)\(',ir))
   if not defs or not defs<=symbols or phase=='program.ll' and defs!=symbols or not decls<= {'llvm.umin.i64','llvm.umax.i64'}or not calls<=defs|decls or re.search(r'\basm\b|\b(?:alloca|invoke|callbr|indirectbr|blockaddress)\b|\bcall[^\n]*%[A-Za-z_][A-Za-z_0-9]*\(',ir):raise RuntimeError('unknown LLVM dispatch/runtime')
  run('object',[tools['llc'],*LLC_ARGUMENTS,'-O2','-stack-size-section',str(d/'program.opt.ll'),'-o',str(d/'program.o')]);undefined=run('undefined',[tools['llvm-nm'],'--undefined-only',str(d/'program.o')]);attrs=run('attributes',[tools['llvm-readelf'],'-h','-A','-r',str(d/'program.o')]);run('machine',[tools['llvm-objdump'],'-d','--no-show-raw-insn',str(d/'program.o')])
  if undefined.strip() or 'rv64i2p1_m2p0'not in attrs or re.search(r'\bR_RISCV_(?:RVC|TLS)',attrs):raise RuntimeError('foreign RV64 helper/ISA')
  if any(sha256(ROOT/n)!=h for n,h in before.items()):raise RuntimeError('actual consumed source changed')
  r.update(status='PASS_GENUINE_CONTROL_ALIGNED_COMPONENT_ONLY',genuine_functions=15,framebuffer_stores=3615,previous_canonical_stores=20520,exact_footprint_bytes=23040,target_execution='NOT_RUN_BY_COMPONENT',installed_notebook='NOT_YET_CONNECTED',artifacts={str(f.relative_to(out)):sha256(f)for f in d.iterdir()if f.is_file()})
 except BaseException as e:r['error']=repr(e)
 finally:r['seconds']=time.monotonic()-start;(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 print(r['status'],r.get('error'),r['seconds']);return 0 if r['status'].startswith('PASS_')else 1
if __name__=='__main__':raise SystemExit(main())
