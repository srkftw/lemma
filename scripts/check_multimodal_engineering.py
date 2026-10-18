#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual public-model circuit runs with independent nominal analytical gates.

Host engineering fixture only. No target program, sensor measurement, physical
protection/acoustic qualification, CAD compilation or manufacturing claim.
"""
from __future__ import annotations
import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
PDK_COMMIT = '5e6d592e4002946a4616f798c357f0f3c06cf3b6'
MODEL = 'ihp-sg13g2/libs.tech/ngspice/models/diodes.lib'
MODEL_SHA = '66fa37819fa8a5c8af4dbb85f11208c3e38faa49c117de55c35a1538786715e8'
CASES = ('electrode', 'optical', 'microphone', 'bone-driver')


def require(condition, message):
    if not condition: raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def capture(argv, *, cwd=ROOT):
    return subprocess.run([str(x) for x in argv], cwd=cwd, check=True,
                          capture_output=True, timeout=30).stdout


def samples(path):
    lines = path.read_text().splitlines()
    names = lines[0].split()
    require(names and names[0] == 'time' and len(names) == len(set(names)), 'malformed waveform header')
    result = []
    for line in lines[1:]:
        values = [float(value) for value in line.split()]
        require(len(values) == len(names) and all(math.isfinite(value) for value in values), 'malformed/nonfinite waveform')
        result.append(dict(zip(names, values)))
    require(len(result) >= 1000 and all(a['time'] <= b['time'] for a, b in zip(result,result[1:])),
            'empty/truncated/nonmonotonic transient')
    return result


def at(data, instant, name):
    times = [row['time'] for row in data]
    index = bisect.bisect_right(times, instant)-1
    require(0 <= index < len(data)-1, 'observation outside actual transient')
    a, b = data[index:index+2]
    require(b['time'] > a['time'], 'ambiguous interpolation interval')
    return a[name]+(b[name]-a[name])*(instant-a['time'])/(b['time']-a['time'])


def amplitude(data, name, start, stop, frequency):
    """Independent least-squares DC/sine/cosine fit, retaining actual timestamps."""
    matrix = [[0.0]*4 for _ in range(3)]
    count = 0
    for row in data:
        if not start <= row['time'] <= stop: continue
        basis = [1.0, math.sin(2*math.pi*frequency*row['time']), math.cos(2*math.pi*frequency*row['time'])]
        count += 1
        for i in range(3):
            for j in range(3): matrix[i][j] += basis[i]*basis[j]
            matrix[i][3] += basis[i]*row[name]
    require(count >= 100, 'insufficient held waveform window')
    for i in range(3):
        pivot = max(range(i,3), key=lambda k:abs(matrix[k][i]))
        matrix[i],matrix[pivot] = matrix[pivot],matrix[i]
        divisor = matrix[i][i]
        require(abs(divisor) > 1e-12, 'singular independent waveform fit')
        matrix[i] = [value/divisor for value in matrix[i]]
        for k in range(3):
            if k == i: continue
            factor = matrix[k][i]
            matrix[k] = [a-factor*b for a,b in zip(matrix[k],matrix[i])]
    return math.hypot(matrix[1][3],matrix[2][3])


def near(observed, expected, relative=0.03, absolute=1e-8):
    require(abs(observed-expected) <= absolute+relative*abs(expected),
            f'analytical tolerance failed: observed={observed!r}, expected={expected!r}')


def assess(directory):
    data = {name:samples(directory/(name+'.dat')) for name in CASES}
    electrode = data['electrode']
    # R/C transfer derived independently of the SPICE/B source implementation.
    # Model leakage/DC offsets are fitted separately; this is not input-noise,
    # CMRR, electrode accuracy, safety or effective ADC resolution evidence.
    gains = []
    for channel, resistance in (('v(out)',110001), ('v(outweak)',1100001)):
        observed = amplitude(electrode,channel,.1,.3,10)
        expected = .1/math.sqrt((1+resistance/1e9)**2+(2*math.pi*10*resistance*10e-9)**2)
        near(observed,expected)
        gains.append({'channel':channel,'volts_peak':observed,'independent_rc_expected':expected})
    require(gains[1]['volts_peak'] < .9*gains[0]['volts_peak'], 'changed contact path did not change response')
    fault_current = max(abs((r['v(contact)']-r['v(normal)'])/110000) for r in electrode)
    require(fault_current <= 13.01/110000, 'series protection current exceeds independently bounded input step')
    rail_min,rail_max = min(r['v(out)'] for r in electrode),max(r['v(out)'] for r in electrode)
    require(rail_min >= .2-1e-8 and rail_max <= 3.1+1e-8 and abs(rail_max-3.1)<1e-8,
            'declared functional gain clipping was absent or exceeded rails')
    require(max(abs(r['v(raw)']-r['v(contact)'])/1e12 for r in electrode if r['time']>.421) < 1e-10,
            'declared disconnected switch did not isolate its modeled input')
    no_diode = samples(directory/'electrode-no-diode-control.dat')
    diode_peak = max(r['v(normal)'] for r in electrode)
    no_diode_peak = max(r['v(normal)'] for r in no_diode)
    require(no_diode_peak > diode_peak+.1, 'negative control did not expose public diode response')

    optical = data['optical']
    def optical_delta(cycle, name, start, stop):
        begin,end = cycle*.001+start,cycle*.001+stop
        return (at(optical,end,name)-at(optical,begin,name))-(at(optical,end,'v(dark)')-at(optical,begin,'v(dark)'))
    optical_records=[]
    for cycle,multiplier in ((0,1),(4,2)):
        for name,current,start,stop in (('v(sense1)',100e-9,.00011,.00019),('v(sense2)',200e-9,.00031,.00039)):
            observed=optical_delta(cycle,name,start,stop)
            expected=current*multiplier*(stop-start)/10e-9
            near(observed,expected)
            optical_records.append({'cycle':cycle,'source':name,'volts_integrated_minus_dark':observed,
                                    'independent_charge_over_capacitance':expected})
    conflicts = [r for r in optical if r['v(requested1)']>.9 and r['v(requested2)']>.9]
    require(conflicts and max(abs(r['v(actual2)']) for r in conflicts)<1e-10,
            'conflicting source request was not actually inhibited')
    bad_dark = at(optical,.00219,'v(dark)')-at(optical,.00211,'v(dark)')
    require(bad_dark > 4*(10e-9*.00008/10e-9), 'corrupted dark reference was not distinguishable')
    require(abs(at(optical,.003159,'v(sense1)')-1)<1e-5,
            'reset during optical integration retained the old accumulated state')

    microphone = data['microphone']
    rc = 1/math.sqrt(1+(2*math.pi*300*1000*100e-9)**2)
    mic1 = amplitude(microphone,'v(out1)',.01,.03,300)
    mic2 = amplitude(microphone,'v(out2)',.01,.03,300)
    changed = amplitude(microphone,'v(out1)',.045,.055,300)
    near(mic1,.1*rc);near(mic2,.2*rc);near(changed,.2*rc)
    muted=max(max(abs(r['v(out1)']),abs(r['v(out2)'])) for r in microphone if r['time']>.061)
    require(muted<1e-10, 'declared analog output mute did not inhibit both channels')
    require(amplitude(microphone,'v(raw1)',.085,.095,300)>.009 and
            max(abs(r['v(raw2)']) for r in microphone if r['time']>.081)<1e-10,
            'independent channel2 loss incorrectly removed channel1')

    bone = data['bone-driver']
    emitted = max(abs(r['v(drive)']) for r in bone if r['time']<.00325)
    require(emitted>.29 and max(abs(r['v(drive)']) for r in bone if r['time']>.003251)<1e-10,
            'arbitrary PCM or local electrical mute missing')
    residual = abs(at(bone,.003251,'i(Lcoil)'))
    require(residual>1e-4, 'negative control failed: cancellation falsely erased stored coil energy')
    energy = lambda r:.5*.001*r['i(Lcoil)']**2+.5*10e-6*r['v(displacement)']**2
    released=[energy(r) for r in bone if r['time']>.003251]
    require(released[-1]<released[0]*1e-8 and max(b-a for a,b in zip(released,released[1:]))<released[0]*1e-5,
            'passive post-mute energy failed independent dissipation bound')
    return {'electrode':{'rc_fit':gains,'peak_series_current_A':fault_current,
                        'model_protected_peak_V':diode_peak,'no_diode_control_peak_V':no_diode_peak,
                        'functional_output_range_V':[rail_min,rail_max]},
            'optical':{'integrations':optical_records,'inhibited_conflict_samples':len(conflicts),
                       'corrupted_dark_delta_V':bad_dark,'mid_exposure_reset_V':at(optical,.003159,'v(sense1)')},
            'microphone':{'channel1_peak_V':mic1,'channel2_peak_V':mic2,'changed_gain_peak_V':changed,'muted_peak_V':muted},
            'bone_driver':{'actual_pcm_peak_V':emitted,'post_mute_coil_current_A':residual,
                           'post_mute_initial_energy_J':released[0],'final_energy_J':released[-1]},
            'sample_rows':{name:len(rows) for name,rows in data.items()},
            'tolerance':{'relative_analog_nominal':.03,'absolute_volts':1e-8,
                         'scope':'analytical nominal R/C/charge/energy checks; no measured biological/acoustic/physical accuracy'}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--pdk',type=Path,required=True)
    parser.add_argument('--ngspice',type=Path,required=True)
    args=parser.parse_args()
    out=args.work_dir.resolve();out.relative_to(ROOT/'build');out.mkdir(parents=True,exist_ok=False)
    source_paths=sorted((ROOT/'engineering/multimodal').glob('*'))+[Path(__file__).resolve()]
    sources={str(path.relative_to(ROOT)):digest(path) for path in source_paths if path.is_file()}
    report={'schema':'lemma-multimodal-engineering-observation/1','status':'FAIL','sources':sources,
            'commands':[],'scope':'synthetic nominal circuit transient; separate from machine/RTL, physical safety and human learning',
            'cad':'SOURCE_ONLY; OpenSCAD was not executed','timeout_seconds_per_command':30}
    started=time.monotonic()
    try:
        require(capture(['git','rev-parse','HEAD'],cwd=args.pdk).decode().strip()==PDK_COMMIT,'public PDK revision differs')
        require(not capture(['git','status','--porcelain'],cwd=args.pdk).strip(),'public PDK checkout is modified')
        model=capture(['git','show','HEAD:'+MODEL],cwd=args.pdk)
        require(hashlib.sha256(model).hexdigest()==MODEL_SHA,'public diode model bytes differ')
        require(b'Copyright 2023 IHP PDK Authors' in model and b'Apache License, Version 2.0' in model,
                'original model copyright/license absent')
        (out/'ihp-diodes.lib').write_bytes(model)
        (out/'IHP-LICENSE').write_bytes(capture(['git','show','HEAD:LICENSE'],cwd=args.pdk))
        version=capture([args.ngspice,'--version']).decode()
        require('ngspice-45 :' in version,'expected actual ngspice45 boundary unavailable')
        (out/'ngspice-version.log').write_text(version)
        report['model']={'commit':PDK_COMMIT,'path':MODEL,'sha256':MODEL_SHA,'retained_original':'ihp-diodes.lib'}
        report['tool']={'path':str(args.ngspice.resolve()),'sha256':digest(args.ngspice),'version':version}
        for name in CASES:shutil.copyfile(ROOT/'engineering/multimodal'/(name+'.cir'),out/(name+'.cir'))
        # Independently consequential negative control: removing the public
        # diode instance must change the fault response. Vendor bytes unchanged.
        control=(out/'electrode.cir').read_text().replace('Xnormal 0 normal dantenna l=10u w=10u\n','')
        control=control.replace('electrode.dat','electrode-no-diode-control.dat')
        (out/'electrode-no-diode-control.cir').write_text(control)
        consumed={path.name:digest(path) for path in out.iterdir()
                  if path.suffix in ('.cir','.lib') or path.name=='IHP-LICENSE'}
        report['consumed_input_copies']=consumed
        for name in (*CASES,'electrode-no-diode-control'):
            command=[str(args.ngspice.resolve()),'-b','-o',name+'.log',name+'.cir']
            report['commands'].append({'argv':command,'cwd':str(out)})
            run=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=30)
            (out/(name+'-invocation.log')).write_text(run.stdout+run.stderr)
            require(run.returncode==0,'actual ngspice execution failed: '+name)
            log=(out/(name+'.log')).read_text()
            require('No. of Data Rows' in log and not any(word in log.lower() for word in ('error','warning','ignored','unrecognized')),
                    'SPICE model error/warning or missing real transient: '+name)
        require(consumed=={name:digest(out/name) for name in consumed},'consumed model/netlist/license changed during execution')
        require(digest(args.ngspice)==report['tool']['sha256'],'SPICE executable changed during execution')
        report['observations']=assess(out)
        require(sources=={str(path.relative_to(ROOT)):digest(path) for path in source_paths if path.is_file()},'engineering inputs changed during observation')
        report['status']='PASS'
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        report['elapsed_seconds']=time.monotonic()-started
        report['retained']={str(path.relative_to(out)):digest(path) for path in sorted(out.iterdir()) if path.is_file() and path.name!='report.json'}
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'report':str(out/'report.json'),'elapsed_seconds':report['elapsed_seconds']}))


if __name__=='__main__':main()
