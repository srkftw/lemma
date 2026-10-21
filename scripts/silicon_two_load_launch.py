#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Two measured wire-load launches on the unselected well-repaired pen.

This precursor replaces only physical spacers needed by two original buf8s.
All old functional sites and terminals remain except the declared driver
outputs. No original signal route or SPEF survives onto the changed nets.
"""
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import time

from silicon_enclosure import require
from silicon_synth import ROOT, sha

SOURCE = ROOT/'build/silicon/task009-well-fill-completed-route-a2'
SOURCE_SHA = '5c43a20a33fe888af5c6cb683d3bc6e19b6d72396a95f7adaa904527fb9d6a9f'
LIB_SHA = '7677a8918689f452e80405ad16a83e744709342574f2aedcc507c2758986b396'
DRIVERS = (('_06992_', 'sg13g2_nand2_2', '_01842_', '0.558108'),
           ('_08744_', 'sg13g2_nor4_2', '_03075_', '0.311153'))


def wire_loads(spef):
    require(sha(spef) == 'f8689c3eef464baff07edc15c5992789404e2031c574806c361b4f604815c771',
            'exact completed nominal extraction required')
    text=spef.read_text();require('*C_UNIT 1 PF' in text, 'original capacitance units required')
    result=[]
    for driver,master,net,cap in DRIVERS:
        aliases=re.findall(r'(?m)^\*(\d+) '+re.escape(net)+r'$',text)
        require(len(aliases) == 1, 'literal native net alias required')
        match=re.search(r'(?ms)^\*D_NET \*'+aliases[0]+r' ([^\n]+)\n(.*?)^\*END$',text)
        require(match is not None and match[1] == cap, 'actual routed wire capacitance changed')
        sinks=re.findall(r'(?m)^\*I \*\S+ I \*D (\S+)$',match[2])
        require(len(sinks) == (2 if driver == '_06992_' else 1), 'actual load endpoint inventory changed')
        result.append({'driver':driver,'master':master,'net':net,'actual_nominal_total_pF':cap,'sink_cells':sinks})
    return result


def prepare(lib, directory):
    import odb
    from silicon_acceptance_launch import snapshot
    from silicon_buffered_pins import buffer_kind
    from silicon_filler_source import all_row_plan, lef_masters, signal_wire_identity
    from silicon_well_fill_route import master_library_relation
    started=time.monotonic();directory.mkdir()
    require(sha(SOURCE/'routed.odb') == SOURCE_SHA and sha(lib) == LIB_SHA, 'exact completed source/library required')
    loads=wire_loads(SOURCE/'nom.spef')
    plan_source=ROOT/'build/silicon/task009-repaired-spacer-insertion-a1/row-plan.json'
    require(sha(plan_source)=='993b940511465d3fb1c2f8af1266c8abc97b432d5eb7ceebf6e72e8fdb4dcd5d'and
            sha(SOURCE/'routed.def')=='ca940ec974024fbc09539a4166e2713ec07810ff90135be0cf31efa74ae0d78a',
            'literal original spacer plan and completed native DEF required')
    old_plan=json.loads(plan_source.read_text())
    require(len(old_plan['fillers']) == 40247, 'literal original source filler inventory required')
    db=odb.dbDatabase.create();odb.read_db(db,str(SOURCE/'routed.odb'));block=db.getChip().getBlock()
    before=snapshot(block);old_fill={row['name']:row for row in old_plan['fillers']}
    functional={name:value for name,value in before[1].items() if name not in old_fill}
    require(len(functional) == 9037 and len(before[1]) == 49284, 'source functional/spacer inventory differs')
    master=next(lib.findMaster('sg13g2_buf_8')for lib in db.getLibs()if lib.findMaster('sg13g2_buf_8'))
    require((master.getWidth(),master.getHeight()) == (6240,3780) and
            buffer_kind(master.getName(),lib.read_text()) == ('X',0), 'original noninverting buf8 required')
    occupied=defaultdict(list);macros=[]
    for name in functional:
        cell=block.findInst(name);box=cell.getBBox()
        if cell.getMaster().getType() == 'BLOCK':macros.append((box.xMin(),box.yMin(),box.xMax(),box.yMax()))
        else:occupied[box.yMin()].append((box.xMin(),box.xMax(),name))
    sites=[];changes={};added=set()
    for index,(driver,kind,net_name,_) in enumerate(DRIVERS):
        launch=block.findInst(driver);require(launch.getMaster().getName() == kind,'literal launch master required')
        pin=launch.findITerm('Y');old=pin.getNet();require(old.getName() == net_name,'literal launch net required')
        box=launch.getBBox();cx=(box.xMin()+box.xMax())//2;cy=box.yMin();options=[]
        for row in block.getRows():
            q=row.getBBox();rx,ry=q.xMin(),q.yMin()
            if abs(ry-cy)>50000 or row.getSite().getWidth()!=480 or row.getSite().getHeight()!=3780:continue
            require(row.getOrient()in('R0','MX'),'original row orientation required')
            forbidden=[(left-960,right+960)for left,right,_ in occupied[ry]]
            forbidden += [(left-3000,right+3000)for left,bottom,right,top in macros if ry+3780>bottom-3000 and ry<top+3000]
            cursor=rx+960
            for left,right in sorted(forbidden)+[(q.xMax()-960,q.xMax())]:
                lo=max(cursor,rx+960);hi=min(left-6240,q.xMax()-960-6240)
                if lo<=hi:
                    desired=max(lo,min(cx-3120,hi));x=rx+math.ceil((desired-rx)/480)*480
                    if x>hi:x-=480
                    if x>=lo and abs(x-cx)<=50000:options.append((abs(x-cx)+abs(ry-cy),x,ry,row.getOrient()))
                cursor=max(cursor,right)
        require(options,'no padded original row site within50um for '+driver)
        distance,x,y,orientation=min(options);name='task009_two_load_launch_'+str(index)
        cell=odb.dbInst_create(block,master,name);cell.setOrient(orientation);cell.setLocation(x,y);cell.setPlacementStatus('PLACED')
        new=odb.dbNet_create(block,name+'_driver');pin.connect(new)
        for terminal,net in [('A',new),('X',old),('VDD',block.findNet('VDDlogic')),('VSS',block.findNet('VSS'))]:cell.findITerm(terminal).connect(net)
        added.add(name);changes[(driver,'Y')]=new.getName();occupied[y].append((x,x+6240,name))
        sites.append({'driver':driver,'new_cell':name,'location':[x,y],'orientation':orientation,'distance_nm':distance})
    expected={'dbu_per_micron':1000,'instances':[]}
    for cell in block.getInsts():
        if cell.getName() in old_fill:continue
        x,y=cell.getLocation();height=cell.getMaster().getHeight();orient=cell.getOrient()
        expected['instances'].append({'name':cell.getName(),'master':cell.getMaster().getName(),'location':[x,y],
            'orientation':orient,'origin':[x,y+(height if orient=='MX'else 0)]})
    std=ROOT/'build/silicon/deps/ihp-open-pdk/ihp-sg13g2/libs.ref/sg13g2_stdcell/lef/sg13g2_stdcell.lef'
    sram=ROOT/'build/silicon/task009-slew-selected-current-map-a1/pdk/ihp-sg13g2/libs.ref/sg13g2_sram/lef/RM_IHPSG13_1P_256x64_c2_bm_bist.lef'
    masters=lef_masters(std.read_text()+sram.read_text())
    for item in expected['instances']:
        native=block.findInst(item['name']).getMaster();literal=masters[item['master']]
        require(literal['size_nm']==(native.getWidth(),native.getHeight())and
                literal['class']==str(native.getType()).replace('_',' '),
                'original LEF/native master class or dimensions differ')
    plan=all_row_plan((SOURCE/'routed.def').read_text(),expected,masters,macro_left_extra_sites=2,macro_right_extra_sites=2)
    old_at={(row['master'],tuple(row['location']),row['orientation']):row for row in old_fill.values()}
    reused=set();new_rows=[]
    for index,row in enumerate(plan['fillers']):
        key=(row['master'],tuple(row['location']),row['orientation'])
        if key in old_at:row['name']=old_at[key]['name'];reused.add(row['name'])
        else:row['name']='task009_two_load_fill_'+str(index);new_rows.append(row)
    removed=set(old_fill)-reused;affected_y={site['location'][1]for site in sites}
    require(all(old_fill[name]['location'][1]in affected_y for name in removed)and
            all(row['location'][1]in affected_y for row in new_rows),'spacer changes escape the two actual launch rows')
    for name in removed:odb.dbInst_destroy(block.findInst(name))
    for row in new_rows:
        kind=next(lib.findMaster(row['master'])for lib in db.getLibs()if lib.findMaster(row['master']))
        cell=odb.dbInst_create(block,kind,row['name']);cell.setOrient(row['orientation']);cell.setLocation(*row['location']);cell.setPlacementStatus('PLACED')
        cell.findITerm('VDD').connect(block.findNet('VDDlogic'));cell.findITerm('VSS').connect(block.findNet('VSS'))
    after=snapshot(block);final_fill={row['name']:row for row in plan['fillers']};expected_terms={key:value for key,value in before[0].items()if key[0]not in old_fill}
    for key,net in changes.items():expected_terms[key]=(net,expected_terms[key][1])
    require({k:v for k,v in after[0].items()if k[0]not in final_fill and k[0]not in added} == expected_terms,
            'functional/BIST/supply pins changed beyond exact two output launches')
    require({k:v for k,v in after[1].items()if k not in final_fill and k not in added} == functional and after[2:] == before[2:],
            'old placements/master/33delay/668ports/nativePG/OBS changed')
    rails=defaultdict(list)
    for (net,layer,a,b,c,d),count in before[3].items():
        if layer=='Metal1':rails[net].append((a,b,c,d))
    new_pg=[]
    for name in sorted(added|{row['name']for row in new_rows}):
        cell=block.findInst(name)
        for terminal,net in [('VDD','VDDlogic'),('VSS','VSS')]:
            pin=cell.findITerm(terminal);require(pin.getNet().getName()==net,'new cell supply retargeted')
            boxes=[box for layer,box in pin.getGeometries()if layer.getName()=='Metal1']
            require(boxes and any(min(box.xMax(),c)>max(box.xMin(),a)and min(box.yMax(),d)>max(box.yMin(),b)
                    for box in boxes for a,b,c,d in rails[net]),'new native PG pin does not overlap its immutable row rail')
            new_pg.append((name,terminal,net))
    def validate():
        for index,(driver,_,oldnet,_) in enumerate(DRIVERS):
            name='task009_two_load_launch_'+str(index);cell=block.findInst(name)
            site=sites[index]
            require(cell.getMaster().getName()=='sg13g2_buf_8'and list(cell.getLocation())==site['location']and
                    cell.getOrient()==site['orientation'],'declared launch master/site changed')
            require(block.findInst(driver).findITerm('Y').getNet().getName()==changes[(driver,'Y')],'old driver retargeted')
            for terminal,net in [('A',changes[(driver,'Y')]),('X',oldnet),('VDD','VDDlogic'),('VSS','VSS')]:
                require(cell.findITerm(terminal).getNet().getName()==net,'new launch bit/power differs')
        for row in new_rows:
            cell=block.findInst(row['name'])
            require(cell.getMaster().getName()==row['master']and list(cell.getLocation())==row['location']and
                    cell.getOrient()==row['orientation'],'new physical spacer site/master differs')
            require(cell.findITerm('VDD').getNet().getName()=='VDDlogic'and
                    cell.findITerm('VSS').getNet().getName()=='VSS','new physical spacer supply differs')
        pin=block.findInst('pen_sram_lane0').findITerm('A_BIST_DIN[32]')
        require(pin.getNet()is not None and pin.getNet().getName()==before[0][('pen_sram_lane0','A_BIST_DIN[32]')][0],
                'original BIST witness disconnected or retargeted')
    validate();negatives=[]
    for terminal,wrong in [('A','sample_ready'),('VDD','VSS')]:
        pin=block.findInst('task009_two_load_launch_0').findITerm(terminal);saved=pin.getNet();pin.connect(block.findNet(wrong))
        try:validate()
        except ValueError:negatives.append('actual_new_'+terminal+'_retarget')
        else:raise ValueError('launch negative admitted')
        pin.connect(saved);validate()
    cell=block.findInst('task009_two_load_launch_0');where=cell.getLocation()
    cell.setLocation(*block.findInst(DRIVERS[0][0]).getLocation())
    try:validate()
    except ValueError:negatives.append('actual_launch_wrong_site_and_overlap')
    else:raise ValueError('actual launch site negative admitted')
    cell.setLocation(*where);validate()
    pin=block.findInst('pen_sram_lane0').findITerm('A_BIST_DIN[32]');saved=pin.getNet();pin.disconnect()
    try:validate()
    except ValueError:negatives.append('actual_BIST_disconnect')
    else:raise ValueError('actual BIST negative admitted')
    pin.connect(saved);validate()
    if new_rows:
        pin=block.findInst(new_rows[0]['name']).findITerm('VDD');saved=pin.getNet();pin.connect(block.findNet('VSS'))
        try:validate()
        except ValueError:negatives.append('actual_new_spacer_supply_retarget')
        else:raise ValueError('actual spacer supply negative admitted')
        pin.connect(saved);validate()
    require(snapshot(block)==after,'private pin negatives did not restore')
    reference=odb.dbDatabase.create();odb.read_db(reference,str(SOURCE/'routed.odb'))
    library_relation=master_library_relation(reference,db,directory/'master-library')
    odb.dbDatabase.destroy(reference)
    for net in block.getNets():
        if net.getWire():odb.dbWire_destroy(net.getWire())
    require(not signal_wire_identity(block),'stale signal/clock wires remain')
    odb.write_db(db,str(directory/'unrouted.odb'));odb.write_def(block,str(directory/'unrouted.def'))
    (directory/'row-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    result={'status':'PASS_TWO_MEASURED_LOAD_LAUNCH_SITE_SPACER_ENDPOINT_PRECURSOR_NOT_ROUTED',
        'source_ODB_sha256':SOURCE_SHA,'geometry_ODB_sha256':sha(directory/'unrouted.odb'),'actual_nominal_loads':loads,
        'sites':sites,'old_functional_cells_moved':0,'old_functional_and_macro_instances':9037,'new_original_buf8':2,
        'old_spacers':40247,'new_spacers':len(plan['fillers']),'spacers_removed':sorted(removed),'spacers_added':new_rows,
        'affected_rows_y_nm':sorted(affected_y),'functional_padding_nm':960,'ports':len(after[2]),'native_PG_shapes':sum(after[3].values()),
        'new_supply_terminals_with_actual_row_overlap':len(new_pg),
        'OBS':len(after[4]),'original33delays_preserved':True,'negative_cases':negatives,'seconds':time.monotonic()-started,
        'native_master_library_relation':library_relation,
        'remaining':'ActualPGpin overlap/PSM, originalgate4state fixture, finalsource/master geometry, originalGDS/NWell, freshroute/native420/3RC/all9timing/process/LVS. No selection.'}
    (directory/'preparation.json').write_text(json.dumps(result,indent=2)+'\n');return result


GEOMETRY_SHA='37d86a7314d05b7c4b9367862b33348ceabb5dfab7b32c070643aef80d9a7070'
RECEIPT_SHA='94180fec90438a316c6311df49a12a340a74fb4bb8060be5ac26bf6575d33aa5'


def admit(directory):
    import ast
    import hashlib
    import tarfile
    directory=directory.resolve();receipt=ROOT/'build/silicon/task009-two-load-launch-completed-a1/result.json'
    require(directory==ROOT/'build/silicon/task009-two-load-launch-preflight-a2'and sha(receipt)==RECEIPT_SHA,
            'exact independently completed two-load precursor required')
    result=json.loads(receipt.read_text())
    require(result['status']=='PASS_COMPLETED_TWO_LOAD_BUF8_SOURCE_SITE_SPACER_PG_FOURSTATE_PRECURSOR_NOT_ROUTED'and
            result['source_seal_equal'],'completed source-sealed count assessment required')
    capsule=directory/'source-closure.tar.gz'
    require(sha(capsule)==result['source_archive_sha256'],'original finite/native producer capsule differs')
    inputs=[receipt,capsule]
    for name,digest in result['source_inputs'].items():
        path=Path(name).resolve()
        if sha(path)==digest:inputs.append(path);continue
        require(path==Path(__file__).resolve(),'qualified physical/model/tool input changed')
        with tarfile.open(capsule,'r:gz')as archive:
            members=[member for member in archive.getmembers()if member.isfile()and member.name.endswith('-'+path.name)]
            require(len(members)==1,'original producer module absent/ambiguous')
            original=archive.extractfile(members[0]).read()
        require(hashlib.sha256(original).hexdigest()==digest,'original source-module identity differs')
        old=ast.parse(original).body;current=ast.parse(path.read_text()).body
        require(len(current)>len(old)and all(ast.dump(a)==ast.dump(b)for a,b in zip(old,current)),
                'only additive source consumers may follow the exact original preparation body')
        suffix=current[len(old):]
        require(len(suffix)==5 and all(isinstance(node,ast.Assign)and len(node.targets)==1 and
                isinstance(node.targets[0],ast.Name)and node.targets[0].id==name and
                isinstance(node.value,ast.Constant)and type(node.value.value)is str
                for node,name in zip(suffix[:2],('GEOMETRY_SHA','RECEIPT_SHA'))),
                'only the two literal consumer identities may follow original preparation')
        require(all(isinstance(node,ast.FunctionDef)and node.name==name and not node.decorator_list and
                    not node.args.defaults and all(value is None or isinstance(value,ast.Constant)and value.value is None
                        for value in node.args.kw_defaults)
                    for node,name in zip(suffix[2:],('admit','assess','require_recipe'))),
                'consumer extension cannot shadow original functions/globals or run new top-level work')
        inputs.append(path)
    geometry=directory/'candidate/unrouted.odb'
    require(sha(geometry)==GEOMETRY_SHA and sha(directory/'candidate/row-plan.json')==
            '2f2b44683e03c916a6341e942db01a749723d9f24d326f96c28998ed09d768ec',
            'actual two-launch physical source/updated spacer plan differs')
    return geometry,receipt,inputs+[geometry,directory/'candidate/row-plan.json',directory/'candidate/preparation.json']


def assess(source,geometry,lib,output,*,fixed_geometry=None):
    import odb
    from silicon_acceptance_launch import snapshot
    from silicon_well_fill_route import master_library_relation
    require(sha(source)==SOURCE_SHA and sha(lib)==LIB_SHA,'exact completed well route and original library required')
    directory=ROOT/'build/silicon/task009-two-load-launch-preflight-a2'
    _,_,_=admit(directory)
    preparation=json.loads((directory/'candidate/preparation.json').read_text())
    plan=json.loads((directory/'candidate/row-plan.json').read_text())
    removed=set(preparation['spacers_removed']);added={row['name']:row for row in preparation['spacers_added']}
    sites={row['new_cell']:row for row in preparation['sites']};names=set(added)|set(sites)
    old_db,db=odb.dbDatabase.create(),odb.dbDatabase.create();odb.read_db(old_db,str(source));odb.read_db(db,str(geometry))
    block=db.getChip().getBlock();before=snapshot(old_db.getChip().getBlock());after=snapshot(block)
    expected={key:value for key,value in before[0].items()if key[0]not in removed}
    for index,(driver,_,_,_)in enumerate(DRIVERS):
        key=(driver,'Y');expected[key]=('task009_two_load_launch_'+str(index)+'_driver',expected[key][1])
    require({k:v for k,v in after[0].items()if k[0]not in names}==expected,'old functional/BIST/supply pins changed beyond two outputs')
    require({k:v for k,v in after[1].items()if k not in names}=={k:v for k,v in before[1].items()if k not in removed}and
            set(after[1])==(set(before[1])-removed)|names and after[2:]==before[2:],
            'old cells/ports/nativePG/OBS or declared new-cell inventory changed')
    for index,(driver,kind,oldnet,_)in enumerate(DRIVERS):
        old=old_db.getChip().getBlock().findInst(driver)
        require(old.getMaster().getName()==kind and old.findITerm('Y').getNet().getName()==oldnet,'original gate identity changed')
        name='task009_two_load_launch_'+str(index);cell=block.findInst(name);site=sites[name]
        require(cell.getMaster().getName()=='sg13g2_buf_8'and list(cell.getLocation())==site['location']and
                cell.getOrient()==site['orientation'],'actual original buffer site/master differs')
        for terminal,net in [('A',name+'_driver'),('X',oldnet),('VDD','VDDlogic'),('VSS','VSS')]:
            require(cell.findITerm(terminal).getNet().getName()==net,'new buffer signal/supply changed')
    for name,row in added.items():
        cell=block.findInst(name)
        require(cell.getMaster().getName()==row['master']and list(cell.getLocation())==row['location']and
                cell.getOrient()==row['orientation']and cell.findITerm('VDD').getNet().getName()=='VDDlogic'and
                cell.findITerm('VSS').getNet().getName()=='VSS','updated physical spacer site/master/supply changed')
    if fixed_geometry is None:
        require(sha(geometry)==GEOMETRY_SHA,'preparation must use exact completed geometry')
        fixed_geometry=geometry
    require(sha(fixed_geometry)==GEOMETRY_SHA,'exact finite-qualified geometry required')
    reference=odb.dbDatabase.create();odb.read_db(reference,str(fixed_geometry))
    require(snapshot(reference.getChip().getBlock())==after,'routing changed the fixed qualified sites/pins/padding/spacers')
    masters=master_library_relation(old_db,db,output.parent/(output.stem+'-masters'))
    result={'status':'PASS_TWO_MEASURED_LOAD_BUFFERS_UPDATED_SPACERS_FIXED_ENDPOINTS_AND_MASTER_RELATION',
        'source_ODB_sha256':sha(source),'geometry_ODB_sha256':sha(geometry),'fixed_geometry_ODB_sha256':GEOMETRY_SHA,
        'old_functional_and_macro_instances':9037,'old_functional_cells_moved':0,'new_original_buf8':2,
        'original_spacers':40247,'updated_spacers':len(plan['fillers']),'removed_spacers':len(removed),'added_spacers':len(added),
        'functional_padding_nm':960,'ports':len(after[2]),'native_PG_shapes':sum(after[3].values()),'OBS':len(after[4]),
        'original33_SRAM_delaycells_preserved':True,'native_master_library':masters,'finite_qualified_receipt_sha256':RECEIPT_SHA,
        'scope':'Exact original gate/buffer finite proof and actual fixed native physical endpoint relation; fresh route/RC/PVT/process/LVS remain separate'}
    output.write_text(json.dumps(result,indent=2)+'\n');return result


def require_recipe(args):
    if not getattr(args,'two_load_launch_from',None):return
    require(args.routed_eco_from and args.clock_min_routing_layer=='Metal3'and args.detail_route_iterations==8 and
            args.host_memory_gib==6 and not args.selected_implementation and
            not any(getattr(args,name,False)for name in('well_fill_from','decode_launch_buffer_from','slew_launch_buffer_from',
                'acceptance_launch_buffer','padded_sram_input_delay_from','control_launch_buffer_from','capacity_launch_buffer_from',
                'power_margin_from','preferred_access_from','preferred_access_preflight_only','preserve_routed_netlist',
                'fresh_core_power_grid','vss_clock_grid_source','protect_sram_power_edges','protect_sram_power_geometry',
                'completed_eco_route_from','completed_power_grid_route_from','completed_fresh_grid_route_from',
                'completed_well_fill_route_from','defer_global_eco','center_validation_cones','group_button_bus')),
            'two-load launch requires exact wellroute/updatedspacers/full8/clockM3/6GiB fresh routing only')
