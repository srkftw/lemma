#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded original-process differential track/hold engineering pilot.

Original PSP transmission gates and CMIM capacitors drive the maintained HBT
preamp/comparator path. This exact TT/1.2V/27C20-cycle pilot and actual controls
are not PVT, noise, mismatch, ADCresolution, layout or safety qualification.
QS/NQS compact-model compilation is explicitly reused from its model capsule.
"""
import argparse,hashlib,os,sys,time,resource,threading,json,shutil,subprocess,re,math,tarfile,signal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
HOST_INPUTS=('check_sg13g2_sample_hold.py','check_sg13g2_comparator.py','silicon_pen_process.py','silicon_enclosure.py','silicon_power_ports.py','silicon_lvs_alias.py','silicon_synth.py')
STARTUP_INPUTS={str(ROOT/'scripts'/name):hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest()for name in HOST_INPUTS}
from check_sg13g2_comparator import bind_originals,REVISION,PREFIX,sha,require,invoke
from silicon_pen_process import OwnedProcessStop


def model_tree(directory):
 """Seal every relative model filename, directory and regular-file byte."""
 directory=Path(directory)
 require(directory.is_dir() and not directory.is_symlink(),'literal model directory required')
 files={};directories=[]
 for parent,names,filenames in os.walk(directory,followlinks=False):
  for name in names:
   path=Path(parent)/name
   require(path.is_dir() and not path.is_symlink(),'model subtree must contain literal directories')
   directories.append(path.relative_to(directory).as_posix())
  for name in filenames:
   path=Path(parent)/name
   require(path.is_file() and not path.is_symlink(),'model subtree must contain regular files')
   files[path.relative_to(directory).as_posix()]=sha(path)
 require(files,'complete nonempty model tree required')
 return {'files':dict(sorted(files.items())),'directories':sorted(directories)}


def require_model_tree(directory,expected):
 require(model_tree(directory)==expected,'copied model filenames and bytes differ from original adopted tree')


def inspect(rows):
 require(len(rows)>=20000 and all(len(row)==16 and all(math.isfinite(v)for v in row)for row in rows),'complete finite16column rawdata')
 require(abs(rows[0][0])<1e-15 and abs(rows[-1][0]-2e-6)<1e-12 and all(0<=b[0]-a[0]<=101e-12 for a,b in zip(rows,rows[1:])),'declared2us100ps transient endpoint/gaps')
 counts={k:0 for k in('acquisition','held_positive','held_negative','direct_positive','direct_negative','preamp_positive','preamp_negative','reset')};failures=[];max_acq=0.;max_hold_error=0.
 for row in rows:
  t,sample,clock,ip,inn,hp,hn,dp,dn,pp,pn,php,phn,op,on,current=row;k=int(t/1e-7+1e-9);phase=t-k*1e-7
  if not 2<=k<=18:continue
  expected=1 if k%2==0 else-1;checks=[]
  if 20e-9<phase<35e-9:
   counts['acquisition']+=1;err=max(abs(hp-ip),abs(hn-inn));max_acq=max(max_acq,err);checks.append(('acquisition',err<.001))
  if 70e-9<phase<85e-9 and clock>1.08:
   held='held_positive'if expected==1 else'held_negative';direct='direct_positive'if expected==1 else'direct_negative';counts[held]+=1;counts[direct]+=1
   checks.append((held,expected*(hp-hn)>.002));checks.append((direct,(dp>1.08 and dn<.12)if expected==1 else(dn>1.08 and dp<.12)));max_hold_error=max(max_hold_error,abs((hp-hn)-expected*.010))
   if k in(6,7):counts['preamp_positive']+=1;checks.append(('preamp_positive',php-phn>.001 and op>1.08 and on<.12))
   if k in(16,17,18):counts['preamp_negative']+=1;checks.append(('preamp_negative',phn-php>.001 and on>1.08 and op<.12))
  if 20e-9<phase<35e-9 and clock<.12:counts['reset']+=1;checks.append(('reset',max(dp,dn,op,on)<.12))
  for label,ok in checks:
   if not ok and len(failures)<12:failures.append({'check':label,'time_s':t,'values':row})
 require(all(n>=20 for n in counts.values()),'missing actual settled acquisition/held/decision/reset observations')
 return counts,failures,{'max_acquisition_error_V':max_acq,'max_held_differential_error_V':max_hold_error,'peak_supply_current_A':max(abs(row[15])for row in rows)}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--pdk',type=Path,required=True)
 p.add_argument('--ngspice',type=Path,required=True)
 p.add_argument('--model-capsule',type=Path,required=True)
 p.add_argument('--work-dir',type=Path,required=True)
 args=p.parse_args()
 root=ROOT;out=args.work_dir.resolve();require(not out.exists()and out.is_relative_to(ROOT/'build'),'unused ignored output required');out.mkdir(parents=True);start=time.monotonic();deadline=start+60
 cap=384<<20;reserve=8<<30
 os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1');resource.setrlimit(resource.RLIMIT_AS,(1<<30,1<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(128<<20,128<<20));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 ns=args.ngspice.resolve();pdk=args.pdk.resolve();capsule=args.model_capsule.resolve()
 circuit=root/'engineering/multimodal/differential-sample-hold-sg13g2.cir';comparator=root/'engineering/multimodal/clocked-comparator-sg13g2.cir';preamp=root/'engineering/multimodal/microphone-preamp-sg13g2.cir'
 inputs=[Path(__file__).resolve(),root/'scripts/check_sg13g2_comparator.py',root/'scripts/silicon_pen_process.py',root/'scripts/silicon_synth.py',ns,capsule,circuit,comparator,preamp]
 r={'status':'FAIL','scope':'Original PSP transmission gates+sourceCMIM sample/hold driving unchanged comparator and HBTpreamp, nominal operatingpilot and actual failure controls only. Not ADCresolution/digitalvalid/controller/layout/safety qualification.','bounds':{'whole_seconds':60,'per_case_seconds':12,'AS_bytes':1<<30,'combined_owned_RSS_bytes':cap,'continuing_host_reserve_bytes':reserve,'output_bytes':128<<20},'source_inputs':dict(STARTUP_INPUTS,**{str(p):sha(p)for p in inputs}),'cases':[],'peak_RSS_bytes':0}
 stop=threading.Event();errors=[];stopper=OwnedProcessStop();observed=set()
 def monitor():
  while not stop.wait(.05):
   q=[os.getpid()];seen=set();rss=0
   while q:
    pid=q.pop()
    if pid in seen:continue
    seen.add(pid)
    try:rss+=int(Path(f'/proc/{pid}/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE');q.extend(map(int,Path(f'/proc/{pid}/task/{pid}/children').read_text().split()))
    except(OSError,ValueError,IndexError):pass
   observed.update(seen-{os.getpid()});r['peak_RSS_bytes']=max(r['peak_RSS_bytes'],rss)
   available=next(int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines()if s.startswith('MemAvailable:'))
   size=sum(p.stat().st_size for p in out.rglob('*')if p.is_file())
   if(rss>cap or available<reserve or size>128<<20 or time.monotonic()>=deadline-2)and not errors:errors.append({'RSS_bytes':rss,'available_bytes':available,'output_bytes':size,'elapsed':time.monotonic()-start})
   if errors:stopper.stop(seen-{os.getpid()})
 thread=threading.Thread(target=monitor,daemon=True)
 try:
  available=next(int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines()if s.startswith('MemAvailable:'));require(available>=reserve+cap+(512<<20),'fresh shared canonical512MiB+owned384MiB+8GiBreserve');require(shutil.disk_usage(out).free>=128<<20,'free outputs')
  r['launch_available_bytes']=available;thread.start();require(sha(ns)=='689be776737abed4fc759d872c594ad935e2e9ba38487c8c0b95f0d84fdc53a8','exact qualified ngspice45 tool required');require(all(sha(Path(name))==h for name,h in STARTUP_INPUTS.items()),'source changed before original model policy use');(out/'plan.json').write_text(json.dumps(r,indent=2)+'\n');require(sha(circuit)=='2b3392a517d7a2d0f59f9a255059bdc775564836ec3543cc26ca5f61c49e910a'and sha(comparator)=='35ba47e1114925944ec7e298fe1bbb30d6af138fce6508f6beaadfb7e0dbcda1','exact actual circuit predecessors')
  r['original_MOS_HBT_models']=bind_originals(pdk,out,json.loads(capsule.read_text()));pending=['cornerCAP.lib'];seen=set();capmodels={}
  while pending:
   name=pending.pop()
   if name in seen:continue
   require(re.fullmatch(r'[A-Za-z0-9_]+\.lib',name),'literal originalCAPinclude')
   source=PREFIX+'ngspice/models/'+name;require(deadline-time.monotonic()>0,'original wholebudget before CAP source read');raw=subprocess.check_output(['git','-C',str(pdk),'show',REVISION+':'+source],timeout=min(5,deadline-time.monotonic()))
   (out/'models'/name).write_bytes(raw);seen.add(name);capmodels[source]=sha(out/'models'/name);pending.extend(re.findall(r'(?im)^\s*\.include\s+(\S+)',raw.decode('latin1')))
  r['model_tree']=model_tree(out/'models')
  r['original_CAP_include_closure']=capmodels;r['adopted_inputs']={str(p):sha(p)for p in list((out/'models').glob('*'))+[out/'psp-qs.osdi',out/'psp-nqs.osdi',out/'inverter-load.cir']}
  with tarfile.open(out/'source-closure.tar.gz','x:gz')as archive:
   for i,path in enumerate(dict.fromkeys([*map(Path,r['source_inputs']),*map(Path,r['adopted_inputs'])])):
    if path.suffix in('.py','.json','.cir','.lib'):archive.add(path,arcname=f'inputs/{i:03d}-{path.name}')
  r['source_archive_sha256']=sha(out/'source-closure.tar.gz')
  for name in('nominal','continuous-track','crossed-held-pair'):
   require(deadline-time.monotonic()>1,'original wholebudget before case');case=out/name;case.mkdir();shutil.copytree(out/'models',case/'models');require_model_tree(case/'models',r['model_tree'])
   for source,target in((preamp,'preamp.cir'),(comparator,'comparator.cir'),(circuit,'sample-hold.cir'),(out/'inverter-load.cir','inverter-load.cir')):shutil.copyfile(source,case/target)
   points=[(0.,.940)]
   for k in range(20):
    sign=1 if k%2==0 else-1;points.extend([((k*100+44.5)*1e-9,.935+sign*.005),((k*100+45)*1e-9,.935-sign*.005)])
   points.append((2e-6,points[-1][1]));pwl=lambda inverse:' '.join(f'{t:.12g} {1.87-v if inverse else v:.12g}'for t,v in points)
   sample='1.2'if name=='continuous-track'else'PULSE(1.2 0 39n 500p 500p 60n 100n)';ports='holdn holdp'if name=='crossed-held-pair'else'holdp holdn'
   (case/'stimulus.cir').write_text(f'Original processsample/hold {name}\n.lib models/cornerMOSlv.lib mos_tt\n.lib models/cornerHBT.lib hbt_typ\n.lib models/cornerCAP.lib cap_typ\n.include inverter-load.cir\n.include comparator.cir\n.include preamp.cir\n.include sample-hold.cir\n.temp 27\nVdd vdd 0 1.2\nVsample sample 0 {sample}\nVclock clock 0 PULSE(0 1.2 50n 500p 500p 49n 100n)\nVin microphone 0 PWL(0 0 100n 0 101n 2m 850n 2m 851n -2m 2u -2m)\nXpreamp microphone vdd preamp_p preamp_n 0 lemma_mic_preamp\nXprehold preamp_p preamp_n sample vdd pholdp pholdn 0 lemma_diff_sample_hold\nXdecision pholdp pholdn clock vdd decisionp decisionn 0 lemma_clocked_comparator\nVdirectp directinputp 0 PWL({pwl(False)})\nVdirectn directinputn 0 PWL({pwl(True)})\nXhold directinputp directinputn sample vdd holdp holdn 0 lemma_diff_sample_hold\nXdirect {ports} clock vdd directp directn 0 lemma_clocked_comparator\nCnextp decisionp 0 20f\nCnextn decisionn 0 20f\nCdirectp directp 0 20f\nCdirectn directn 0 20f\n.end\n')
   (case/'loader.cir').write_text(f'Originalmodels, strict sample/hold pilot\n.control\nset noaskquit\nset num_threads=1\nset wr_vecnames\nset wr_singlescale\npre_osdi {out/"psp-qs.osdi"}\npre_osdi {out/"psp-nqs.osdi"}\nsource stimulus.cir\ntran 100p 2u 0 100p\nwrdata waveform.dat v(sample) v(clock) v(directinputp) v(directinputn) v(holdp) v(holdn) v(directp) v(directn) v(preamp_p) v(preamp_n) v(pholdp) v(pholdn) v(decisionp) v(decisionn) i(Vdd)\nquit\n.endc\n.end\n')
   require_model_tree(out/'models',r['model_tree']);require_model_tree(case/'models',r['model_tree'])
   item={'name':name,'status':'FAIL','source_inputs':{p.name:sha(p)for p in case.glob('*.cir')},'model_inputs':r['model_tree']};r['cases'].append(item)
   log,elapsed=invoke([ns,'-b','loader.cir'],case,case/'ngspice.log',deadline-3,12);item['seconds']=elapsed;require(not re.search(r'(?im)^\s*(warning|error|fatal)\b|timestep too small|doAnalyses:.*failed',log),'unknown model/warning or SPICEfailure')
   rows=[[float(v)for v in line.split()]for line in(case/'waveform.dat').read_text().splitlines()[1:]];counts,failed,measures=inspect(rows);item.update(observations=counts,failures=failed,measures=measures,raw_sha256=sha(case/'waveform.dat'),rows=len(rows))
   if name=='nominal':require(not failed,'nominal operatinglimit');item['status']='PASS_DECLARED_NOMINAL_MODEL_OPERATION'
   else:require(any(f['check'].startswith(('held_','direct_'))for f in failed),'actual continuouslytracking/crossedwire failurecontrol survived');item['status']='PASS_REJECTED_ACTUAL_FAILURE_CONTROL'
   require(not errors,'ownedresourcebound');(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
  require(len(r['cases'])==3 and all(c['status'].startswith('PASS_')for c in r['cases']),'incomplete actualpilot/controls')
  r['status']='PASS_DECLARED_PROCESS_SAMPLE_HOLD_NOMINAL_AND_FAILURE_CONTROLS_ONLY'
 except BaseException as e:r['error']=repr(e)
 finally:
  stop.set()
  if thread.is_alive():thread.join()
  allinputs=dict(r['source_inputs'],**r.get('adopted_inputs',{}))
  for case in r['cases']:
   allinputs.update({str(out/case['name']/name):digest for name,digest in case['source_inputs'].items()})
  try:
   if 'model_tree'in r:
    require_model_tree(out/'models',r['model_tree'])
    for case in r['cases']:
     require_model_tree(out/case['name']/'models',r['model_tree'])
     allinputs.update({str(out/case['name']/'models'/name):digest for name,digest in case['model_inputs']['files'].items()})
   source_equal=all(sha(Path(p))==v for p,v in allinputs.items())
  except(OSError,RuntimeError)as e:source_equal=False;r['source_seal_error']=repr(e)
  r.update(seconds=time.monotonic()-start,original_whole_deadline_met=time.monotonic()<=deadline,resource_errors=errors,source_seal_equal=source_equal,owned_observed_PIDs_absent=all(not Path(f'/proc/{p}').exists()for p in observed))
  if errors or not r['source_seal_equal']or not r['original_whole_deadline_met']or not r['owned_observed_PIDs_absent']:r['status']='FAIL'
  (out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(r['status'],r.get('error'),r['seconds'],flush=True)
 return 0 if r['status'].startswith('PASS_')else 1


if __name__=='__main__':raise SystemExit(main())
