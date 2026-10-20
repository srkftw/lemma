#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded actual327 power-grid predecessor; no signal-route qualification.

The physical rectangle margin remains420nm. Only the M2 router representation
uses275nm bloat plus the pinned original >=210nm Euclidean spacing. The VSS
grid changes only by the independently qualified b6a source variant.
"""
import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import re
import resource
import shutil
import sys
import time

from silicon_enclosure import require
from silicon_synth import ROOT, CommandFailure, run, sha

GRID_SHA = 'b6a3315d233f16e01a6d7a30279867964cdece162a1839b6bed3e01b735fb38e'
CORE = Path('/nix/store/52lmb0xv2vfcjybjnq3bjfmhkg8w1ign-openroad-26Q2/bin/openroad')
PINNED = Path('/nix/store/pi9m3br8ni97dfybd24lldfa185py07x-source')
TECH = ROOT/'build/silicon/task009-padded-sram-hold-route-a2/enclosure/repaired-original.lef'
GRID = ROOT/'build/silicon/task009-core-power-vss-only-pilot-a1/vss-shift/pen-power-grid.candidate.tcl'


def corner_proof(bloat=275, minimum_spacing=210, physical_margin=420):
    require((bloat,minimum_spacing,physical_margin)==(275,210,420), 'unadmitted routing-margin parameters')
    # Any point inside the original square has both distances to the smaller
    # rectangle <145nm, hence squared Euclidean distance <42050 <44100.
    worst_squared = 2*(physical_margin-bloat)**2
    require(worst_squared < minimum_spacing**2, 'corner underprotection')
    require(2*(380-210)**2 >= 210**2 and 380<420, 'unsafe210 counterexample')
    controls=[]
    for x,y in [(0,419),(419,0),(419,419),(415,415),(280,395)]:
        distance=max(x-bloat,0)**2+max(y-bloat,0)**2
        require(distance < minimum_spacing**2, 'source420nm deficient shape admitted')
        controls.append({'axis_gaps_nm':[x,y], 'router_admitted':False})
    for x,y in [(280,530),(0,485),(485,0)]:
        require(max(x-bloat,0)**2+max(y-bloat,0)**2>=minimum_spacing**2 and max(x,y)>=physical_margin, 'positive geometry rejected')
        controls.append({'axis_gaps_nm':[x,y], 'router_admitted':True})
    return {'physical_rectangle_margin_nm':physical_margin,'M2_router_bloat_nm':bloat,
            'minimum_original_Euclidean_spacing_nm':minimum_spacing,
            'worst_inside_corner_squared_nm2':worst_squared,'minimum_spacing_squared_nm2':minimum_spacing**2,
            'unsafe210_plus210_diagonal_nm':[380,380],'controls':controls,
            'scope':'Conservative representation, independent actual420nm checking still mandatory; no process closure.'}


def load(path):
    import odb
    db=odb.dbDatabase.create();odb.read_db(db,str(path))
    return db,db.getChip().getBlock()


def strip_grid(source, output):
    import odb
    from silicon_acceptance_launch import snapshot
    from silicon_sram_input_hold import padding
    db,b=load(source); before=snapshot(b)
    require(padding(b)['stdcells']==9031,'exact327 standard-cell inventory required')
    for name in ('dbWire_destroy','dbSWire_destroy','dbObstruction_destroy','dbBPin_destroy'):
        require(hasattr(odb,name),'missing public OpenDB operation '+name)
    for net in b.getNets():
        if net.getWire():odb.dbWire_destroy(net.getWire())
        if net.getName() in ('VDDlogic','VDDARRAY','VSS'):
            for wire in list(net.getSWires()):odb.dbSWire_destroy(wire)
            term=b.findBTerm(net.getName());require(term is not None,'missing existing power port')
            for pin in list(term.getBPins()):odb.dbBPin_destroy(pin)
    for obstruction in list(b.getObstructions()):odb.dbObstruction_destroy(obstruction)
    require(snapshot(b)[:2]==before[:2],'grid removal changed cells or terminals')
    odb.write_db(db,str(output))


def pg_geometry(block):
    stripes=Counter();metals=Counter();vias=Counter()
    for name in ('VDDlogic','VDDARRAY','VSS'):
        net=block.findNet(name);require(net is not None,'missing power net')
        for wire in net.getSWires():
            for z in wire.getWires():
                if z.isVia():
                    x,y=z.getViaXY();v=z.getBlockVia()or z.getTechVia();require(v is not None,'unbound PG via')
                    boxes=tuple(sorted((q.getTechLayer().getName(),q.xMin(),q.yMin(),q.xMax(),q.yMax()) for q in v.getBoxes()))
                    vias[(name,v.getName(),x,y,boxes)]+=1
                    for layer,a,b,c,d in boxes:
                        metals[(name,layer,a+x,b+y,c+x,d+y)]+=1
                else:
                    row=(name,z.getTechLayer().getName(),z.xMin(),z.yMin(),z.xMax(),z.yMax())
                    stripes[row]+=1;metals[row]+=1
    return stripes,metals,vias


def check_geometry(source, current, output):
    from silicon_acceptance_launch import snapshot
    from silicon_sram_input_hold import padding
    old_db,b=load(source);new_db,nb=load(current)
    before,after=snapshot(b),snapshot(nb)
    require(before[:3]==after[:3],'cell, signal/BIST/power terminal, functional/PG port geometry changed')
    pad=padding(nb);require(pad['stdcells']==9031,'full327 cell inventory')
    oldstr,oldmet,oldvia=pg_geometry(b);newstr,newmet,newvia=pg_geometry(nb)
    for net in ('VDDlogic','VDDARRAY'):
        require(Counter({x:n for x,n in oldmet.items() if x[0]==net})==Counter({x:n for x,n in newmet.items() if x[0]==net}), 'positive rail geometry changed')
    old5=Counter({x:n for x,n in oldstr.items() if x[1]=='Metal5'});new5=Counter({x:n for x,n in newstr.items() if x[1]=='Metal5'})
    removed,added=old5-new5,new5-old5
    require(sum(removed.values())==14 and {x[0]for x in removed}=={'VSS'},'exact fourteen core VSS stripes')
    require(Counter({(n,l,a,c+2000,d,e+2000):v for (n,l,a,c,d,e),v in removed.items()})==added,'VSS M5 is not exact+2um')
    edges={edge:edge+2000 for x in removed for edge in(x[3],x[5])}
    expected=Counter()
    for row,count in oldstr.items():
        n,l,a,c,d,e=row
        if n=='VSS' and l=='Metal5' and row in removed:row=(n,l,a,c+2000,d,e+2000)
        elif n=='VSS' and l=='Metal4':row=(n,l,a,edges.get(c,c),d,edges.get(e,e))
        elif n=='VSS' and l=='TopMetal1' and c==min(x[3]for x in removed):row=(n,l,a,c+2000,d,e)
        expected[row]+=count
    require(expected==newstr,'stripe change beyond source-derived VSS endpoints')
    expectedvia=Counter()
    for row,count in oldvia.items():
        n,name,x,y,boxes=row
        shifted=n=='VSS' and any(l=='Metal5'for l,*_ in boxes) and any(a<=x<=d and c<=y<=e for _,_,a,c,d,e in removed)
        expectedvia[(n,name,x,y+2000 if shifted else y,boxes)]+=count
    require(expectedvia==newvia,'PG via changed beyond exact source VSS rail translation')
    # Independently bind every new obstruction to actual native metal or SRAM
    # PG pin geometry; only Metal2 receives the conservative275nm expansion.
    native=Counter((l,a,c,d,e)for (_,l,a,c,d,e),v in newmet.items() for _ in range(v) if l in ('Metal2','Metal3','Metal4','Metal5'))
    for inst in nb.getInsts():
        if inst.getMaster().getType()!='BLOCK':continue
        for term in inst.getITerms():
            if term.getSigType()not in ('POWER','GROUND'):continue
            for l,q in term.getGeometries():native[(l.getName(),q.xMin(),q.yMin(),q.xMax(),q.yMax())]+=1
    want=Counter()
    for (l,a,c,d,e),v in native.items():
        require(0<min(d-a,e-c)<10000,'original spacing-table width domain')
        z=275 if l=='Metal2' else 420;want[(l,a-z,c-z,d+z,e+z)]+=v
    observed=Counter((o.getBBox().getTechLayer().getName(),o.getBBox().xMin(),o.getBBox().yMin(),o.getBBox().xMax(),o.getBBox().yMax())for o in nb.getObstructions()if o.isExceptPGNetsObstruction())
    def validate_obstructions(value):
        require(want==value and sum(want.values())==18718,'native PG/OBS source relation')
    validate_obstructions(observed)
    require(len(list(nb.getObstructions()))==18718,'unexpected obstruction inventory')
    negatives=[]
    m2=next(x for x in observed if x[0]=='Metal2')
    for label,changed in [('missing_native_PG_obstruction',None),('M2_bloat_underprotects_5nm',(m2[0],m2[1]+5,m2[2]+5,m2[3]-5,m2[4]-5)),
                          ('M2_silently_reverts_420nm',(m2[0],m2[1]-145,m2[2]-145,m2[3]+145,m2[4]+145))]:
        bad=observed.copy();bad[m2]-=1
        if not bad[m2]:del bad[m2]
        if changed:bad[changed]+=1
        try:validate_obstructions(bad)
        except ValueError:negatives.append(label)
        else:raise ValueError('geometry negative accepted '+label)
    # Exact original Via4 and track window, including the actual old400nm gap.
    via=new_db.getTech().findVia('Via4_YX');boxes={q.getTechLayer().getName():(q.xMin(),q.yMin(),q.xMax(),q.yMax())for q in via.getBoxes()}
    require(boxes['Metal4']==(-105,-145,105,145)and boxes['Metal5']==(-145,-100,145,100),'original Via4 geometry')
    top=nb.findInst('pen_sram_lane1').getBBox().yMax();require(top==468780,'fixed macro moved')
    require(any(x[3]==471640 and x[2]<426240<x[4]for x in added),'actual clock PG rail')
    lo=top+420-boxes['Metal4'][1];hi=471640-420-boxes['Metal5'][3]
    text=output.with_name('routed.def').read_text();track=re.search(r'^TRACKS Y (\d+) DO (\d+) STEP (\d+) LAYER Metal5',text,re.M)
    require(track is not None,'original M5 track definition')
    start,count,pitch=map(int,track.groups());legal=[start+i*pitch for i in range(count)if lo<=start+i*pitch<=hi]
    require(legal==[469560,469980,470400,470820],'source420nm legal Via4 window differs')
    # All real nonpower pins keep the independent420nm rectangular clearance.
    buckets=defaultdict(list)
    for l,a,c,d,e in native:
        for xx in range((a-420)//50000,(d+420)//50000+1):
            for yy in range((c-420)//50000,(e+420)//50000+1):buckets[l,xx,yy].append((a-420,c-420,d+420,e+420))
    def pin_clear(layer,box):
        a,c,d,e=box
        for xx in range(a//50000,d//50000+1):
            for yy in range(c//50000,e//50000+1):
                require(not any(min(d,z)>max(a,x)and min(e,w)>max(c,y)for x,y,z,w in buckets[layer,xx,yy]),'real pin enters original420nm PG keepout')
    pin_count=0
    for inst in nb.getInsts():
        for t in inst.getITerms():
            if t.getSigType()in ('POWER','GROUND'):continue
            for l,q in t.getGeometries():
                if l.getName()not in ('Metal2','Metal3','Metal4','Metal5'):continue
                pin_clear(l.getName(),(q.xMin(),q.yMin(),q.xMax(),q.yMax()));pin_count+=1
    for t in nb.getBTerms():
        if t.getSigType()in ('POWER','GROUND'):continue
        for p in t.getBPins():
            for q in p.getBoxes():
                if q.getTechLayer().getName()not in ('Metal2','Metal3','Metal4','Metal5'):continue
                pin_clear(q.getTechLayer().getName(),(q.xMin(),q.yMin(),q.xMax(),q.yMax()));pin_count+=1
    result={'status':'PASS_ACTUAL327_NEW_GRID_AND_CONSERVATIVE_M2_PREDECESSOR_NOT_ROUTED','padding':pad,
            'source_native_PG_shapes':sum(oldmet.values()),'new_native_PG_shapes':sum(newmet.values()),
            'positive_rails_exact':True,'VSS_shifted_stripes':sum(removed.values()),'VSS_via_relation_exact':True,
            'all_native_PG_OBS_relations':sum(want.values()),'real_signal_pin_shapes_checked_420nm':pin_count,
            'geometry_relation_negatives':negatives,
            'actual_old_clock_M5_gap_nm':400,'same_clock_coordinates_new_native_gap_nm':2400,
            'original420nm_legal_Via4_centers_nm':legal,'corner_proof':corner_proof()}
    output.write_text(json.dumps(result,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True)
    args=p.parse_args();out=args.work_dir.resolve();require(not out.exists(),'unused output required');out.mkdir(parents=True)
    started=time.monotonic();deadline=started+60
    resource.setrlimit(resource.RLIMIT_AS,(3<<30,3<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    r={'schema':'lemma-actual327-power-margin-predecessor/1','status':'FAIL','bounds':{'whole_seconds':60,'AS_bytes':3<<30,'output_bytes':1<<30,'available_floor_bytes':5<<30},'commands':[]}
    try:
        from silicon_capacity_launch import admit,PRODUCER,LIB_SHA
        source,receipt,inputs=admit(PRODUCER);require(sha(GRID)==GRID_SHA,'source-qualified VSS grid')
        available=int(re.search(r'MemAvailable:\s+(\d+)',Path('/proc/meminfo').read_text())[1])*1024
        r['available_bytes']=available;require(available>=5<<30,'3GiB pilot requires2GiB headroom')
        require(shutil.disk_usage(out).free>=8<<30 and os.statvfs(out).f_favail>=10000,'pilot storage floor')
        lib=ROOT/'build/silicon/deps/ihp-open-pdk/ihp-sg13g2/libs.ref/sg13g2_stdcell/lib/sg13g2_stdcell_typ_1p20V_25C.lib'
        macro=ROOT/'build/silicon/task009-powered-selection-maintained-map-a1/pdk/ihp-sg13g2/libs.ref/sg13g2_sram/lib/RM_IHPSG13_1P_256x64_c2_bm_bist_typ_1p20V_25C.lib'
        prior=ROOT/'build/silicon/task009-three-control-launch-route-a1'
        inputs += [Path(__file__),source,receipt,GRID,TECH,lib,macro,CORE,CORE.parent/'.openroad-wrapped',ROOT/'tooling/silicon/pen-power-grid.tcl',ROOT/'tooling/silicon/pen-power-edge.tcl',ROOT/'tooling/silicon/pen-power-check.tcl',prior/'routed.sdc',prior/'routed.def']
        inputs += [ROOT/'scripts'/n for n in ('silicon_capacity_launch.py','silicon_synth.py','silicon_enclosure.py','silicon_route_enclosure.py')]
        inputs += [PINNED/n for n in ['src/drt/src/gc/FlexGC_main.cpp','src/drt/src/io/io.cpp','src/odb/src/db/dbTech.cpp']]
        require(sha(lib)==LIB_SHA,'original public Liberty changed')
        text=TECH.read_text()
        for layer in ('Metal2','Metal3','Metal4','Metal5'):
            card=re.search(r'^LAYER '+layer+r'\n(.*?)^END '+layer+r'$',text,re.M|re.S)[1]
            require(all(s in card for s in ['WIDTH 0.00        0.21    0.21    0.21','WIDTH 0.39        0.21    0.24    0.24','WIDTH 10.0        0.21    0.24    0.60']),'original width/PRL tables changed')
        corner_proof()
        (out/'prepare.py').write_text(f'import sys\nfrom pathlib import Path\nsys.path.insert(0,{str(ROOT/"scripts")!r})\nfrom silicon_power_margin import strip_grid\nstrip_grid(Path({str(source)!r}),Path({str(out/"stripped.odb")!r}))\n')
        (out/'grid.tcl').write_text(f'''set_thread_count 1
read_liberty {{{lib}}}
read_liberty {{{macro}}}
read_db {{{out/'stripped.odb'}}}
read_sdc {{{prior/'routed.sdc'}}}
set out {{{out}}}
source {{{ROOT/'tooling/silicon/pen-power-check.tcl'}}}
set bindings [lemma_macro_bindings $out/macro-before.tsv]
source {{{GRID}}}
lemma_check_power_grid $bindings $out after-grid
source {{{ROOT/'tooling/silicon/pen-power-edge.tcl'}}}
set ::lemma_M2_route_bloat_nm 275
set geometry [lemma_add_power_geometry_clearance $out {{{prior/'routed.def'}}} {{{TECH}}}]
lemma_check_power_geometry_clearance $geometry
write_db $out/routed.odb
write_def $out/routed.def
write_verilog -include_pwr_gnd $out/power-connected.v
''')
        (out/'check.py').write_text(f'import sys\nfrom pathlib import Path\nsys.path.insert(0,{str(ROOT/"scripts")!r})\nfrom silicon_power_margin import check_geometry\ncheck_geometry(Path({str(source)!r}),Path({str(out/"routed.odb")!r}),Path({str(out/"geometry.json")!r}))\n')
        inputs += [out/n for n in ('prepare.py','grid.tcl','check.py')]
        r['source_inputs']={str(x):sha(x)for x in inputs};r['source_geometry']=str(source)
        (out/'plan.json').write_text(json.dumps(r,indent=2)+'\n')
        os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
        for name,mode in [('prepare','-python'),('grid','-no_init'),('check','-python')]:
            try:r['commands'].append(run([str(CORE),mode,'-exit',str(out/(name+('.tcl'if name=='grid'else'.py')))],out/(name+'.log'),deadline))
            except CommandFailure as e:r['commands'].append(e.record);raise
        from silicon_route_enclosure import audit
        r['geometry']=json.loads((out/'geometry.json').read_text());r['original_via_rule_subset']=audit(TECH,out/'routed.def',allow_generated=True)
        require(r['original_via_rule_subset']['status']=='PASS_FIXED_VIA_INTRINSIC_ENCLOSURE','actual generated PG via rule failure')
        r['power_grid']=json.loads((out/'power-grid-after-grid.json').read_text())
        require(r['power_grid']['all_power_terminals']==18071 and r['power_grid']['macro_power_pins']==9 and r['power_grid']['preserved_BIST_pins']==423,'exact327 PG/test inventory')
        r['source_seal_equal']=all(sha(Path(x))==v for x,v in r['source_inputs'].items())
        require(r['source_seal_equal'],'source changed during pilot')
        require(sum(x.stat().st_size for x in out.rglob('*')if x.is_file())<=1<<30,'output budget exceeded')
        r['status']='PASS_ACTUAL327_PG_AND_M2_ROUTING_REPRESENTATION_PREDECESSOR_NO_ROUTE'
    except BaseException as e:
        import traceback
        r['error']=repr(e);r['traceback']=traceback.format_exc()
    finally:
        r['seconds']=time.monotonic()-started
        r['within_original_budget']=r['seconds']<=60
        if not r['within_original_budget']:r['status']='FAIL_ORIGINAL60SECOND_PILOT_DEADLINE'
        (out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(r['status'],r.get('error'),r['seconds'])


if __name__=='__main__':main()
