#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Joint two read-decode launches and eight setup-positive SRAM DIN delays.

This precursor replaces only physical spacers needed by two original buf8s.
All old functional sites remain. Only two declared driver outputs and eight
source-qualified SRAM DIN inputs change through original noninverting cells. No original signal route or SPEF survives onto the changed nets.
"""
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import time

from silicon_enclosure import require
from silicon_synth import ROOT, sha

SOURCE = ROOT/'build/silicon/task009-two-load-route-a2'
SOURCE_SHA = '8bc1121b7e62f022a4f60819f74618fb5e5410bf89817a454ea46c31dcc92bf6'
LIB_SHA = '7677a8918689f452e80405ad16a83e744709342574f2aedcc507c2758986b396'
DRIVERS = (('_06323_', 'sg13g2_nor3_2', '_01245_', '0.666955'),
           ('_06651_', 'sg13g2_a21oi_2', 'rdata[6]', '0.705495'))
DIN_ENDPOINTS = tuple([f'pen_sram_lane0/A_DIN[{x}]'for x in(49,50,53)] + [f'pen_sram_lane1/A_DIN[{x}]'for x in(17,23,24,26)] + ['pen_sram_lane2/A_DIN[39]'])


def wire_loads(spef):
    require(sha(spef) == '6f1afb7cf2998dc2c909b735cb037771a5ef553ac85e5f3eb555b6b9b5110878',
            'exact completed nominal extraction required')
    text=spef.read_text();require('*C_UNIT 1 PF' in text, 'original capacitance units required')
    result=[]
    for driver,master,net,cap in DRIVERS:
        aliases=re.findall(r'(?m)^\*(\d+) '+re.escape(net)+r'$',text)
        require(len(aliases) == 1, 'literal native net alias required')
        match=re.search(r'(?ms)^\*D_NET \*'+aliases[0]+r' ([^\n]+)\n(.*?)^\*END$',text)
        require(match is not None and match[1] == cap, 'actual routed wire capacitance changed')
        sinks=re.findall(r'(?m)^\*I \*\S+ I \*D (\S+)$',match[2])
        require(len(sinks) == (2 if driver == '_06323_' else 0), 'actual load endpoint inventory changed')
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
    plan_source=ROOT/'build/silicon/task009-two-load-launch-preflight-a2/candidate/row-plan.json'
    require(sha(plan_source)=='2f2b44683e03c916a6341e942db01a749723d9f24d326f96c28998ed09d768ec'and
            sha(SOURCE/'routed.def')=='95ac5ca4f5b8b4059b5c44eee27176c45edd2bb9311beded3d206f4e1289054b',
            'literal original spacer plan and completed native DEF required')
    old_plan=json.loads(plan_source.read_text())
    require(len(old_plan['fillers']) == 40241, 'literal original source filler inventory required')
    db=odb.dbDatabase.create();odb.read_db(db,str(SOURCE/'routed.odb'));block=db.getChip().getBlock()
    before=snapshot(block);old_fill={row['name']:row for row in old_plan['fillers']}
    functional={name:value for name,value in before[1].items() if name not in old_fill}
    require(len(functional) == 9039 and len(before[1]) == 49280, 'source functional/spacer inventory differs')
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
        distance,x,y,orientation=min(options);name='task009_hold_decode_launch_'+str(index)
        cell=odb.dbInst_create(block,master,name);cell.setOrient(orientation);cell.setLocation(x,y);cell.setPlacementStatus('PLACED')
        new=odb.dbNet_create(block,name+'_driver');pin.connect(new)
        for terminal,net in [('A',new),('X',old),('VDD',block.findNet('VDDlogic')),('VSS',block.findNet('VSS'))]:cell.findITerm(terminal).connect(net)
        added.add(name);changes[(driver,'Y')]=new.getName();occupied[y].append((x,x+6240,name))
        sites.append({'driver':driver,'new_cell':name,'location':[x,y],'orientation':orientation,'distance_nm':distance})
    # Delay only these exact setup-positive DIN branches. ADDR0 and control
    # endpoints remain untouched because they also have negative setup.
    inventory=ROOT/'build/silicon/task009-two-load-hold-inventory-a1/result.json'
    require(sha(inventory)=='edd0b142d5b3f71c7c048fc77520d74aae662234d95edd375f9083afae0edd93','literal all9 endpoint inventory required')
    witness=json.loads(inventory.read_text());rows={r['endpoint']:r for r in witness['endpoints']}
    require(set(DIN_ENDPOINTS)=={k for k,v in rows.items()if v['kind']=='NEW_SRAM'and v['minimum_setup_ns']>8},'exact eight setup-positive DIN endpoints required')
    delay=next(l.findMaster('sg13g2_dlygate4sd3_1')for l in db.getLibs()if l.findMaster('sg13g2_dlygate4sd3_1'))
    require(buffer_kind(delay.getName(),lib.read_text())==('X',0),'original noninverting delay required')
    delay_sites=[]
    for index,endpoint in enumerate(DIN_ENDPOINTS):
        instance,pinname=endpoint.split('/');pin=block.findInst(instance).findITerm(pinname);oldnet=pin.getNet()
        boxes=[b for _,b in pin.getGeometries()];require(boxes,'actual SRAM input geometry required')
        cx=(min(b.xMin()for b in boxes)+max(b.xMax()for b in boxes))//2;cy=(min(b.yMin()for b in boxes)+max(b.yMax()for b in boxes))//2
        width=delay.getWidth();options=[]
        for row in block.getRows():
            q=row.getBBox();rx,ry=q.xMin(),q.yMin()
            if abs(ry-cy)>50000 or row.getSite().getWidth()!=480 or row.getSite().getHeight()!=3780:continue
            require(row.getOrient()in('R0','MX'),'original row orientation required')
            forbidden=[(left-960,right+960)for left,right,_ in occupied[ry]]
            forbidden +=[(left-3000,right+3000)for left,bottom,right,top in macros if ry+3780>bottom-3000 and ry<top+3000]
            cursor=rx+960
            for left,right in sorted(forbidden)+[(q.xMax()-960,q.xMax())]:
                lo=max(cursor,rx+960);hi=min(left-width,q.xMax()-960-width)
                if lo<=hi:
                    desired=max(lo,min(cx-width//2,hi));x=rx+math.ceil((desired-rx)/480)*480
                    if x>hi:x-=480
                    if x>=lo and abs(x+width//2-cx)<=50000:options.append((abs(x+width//2-cx)+abs(ry-cy),x,ry,row.getOrient()))
                cursor=max(cursor,right)
        require(options,'no padded original row site within50um of '+endpoint)
        distance,x,y,orientation=min(options);name='task009_hold_decode_delay_'+str(index)
        cell=odb.dbInst_create(block,delay,name);cell.setOrient(orientation);cell.setLocation(x,y);cell.setPlacementStatus('PLACED')
        new=odb.dbNet_create(block,name+'_out');pin.connect(new)
        for terminal,net in [('A',oldnet),('X',new),('VDD',block.findNet('VDDlogic')),('VSS',block.findNet('VSS'))]:cell.findITerm(terminal).connect(net)
        added.add(name);changes[(instance,pinname)]=new.getName();occupied[y].append((x,x+width,name))
        delay_sites.append({'endpoint':endpoint,'name':name,'input_net':oldnet.getName(),'output_net':new.getName(),'location':[x,y],'orientation':orientation,'distance_to_native_pin_nm':distance,'minimum_setup_ns':rows[endpoint]['minimum_setup_ns'],'worst_hold_ns':rows[endpoint]['worst_hold_ns']})
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
        else:row['name']='task009_hold_decode_fill_'+str(index);new_rows.append(row)
    removed=set(old_fill)-reused;affected_y={site['location'][1]for site in sites+delay_sites}
    require(all(old_fill[name]['location'][1]in affected_y for name in removed)and
            all(row['location'][1]in affected_y for row in new_rows),'spacer changes escape the actual launch/delay rows')
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
            name='task009_hold_decode_launch_'+str(index);cell=block.findInst(name)
            site=sites[index]
            require(cell.getMaster().getName()=='sg13g2_buf_8'and list(cell.getLocation())==site['location']and
                    cell.getOrient()==site['orientation'],'declared launch master/site changed')
            require(block.findInst(driver).findITerm('Y').getNet().getName()==changes[(driver,'Y')],'old driver retargeted')
            for terminal,net in [('A',changes[(driver,'Y')]),('X',oldnet),('VDD','VDDlogic'),('VSS','VSS')]:
                require(cell.findITerm(terminal).getNet().getName()==net,'new launch bit/power differs')
        for row in delay_sites:
            cell=block.findInst(row['name']);instance,pinname=row['endpoint'].split('/')
            require(cell.getMaster().getName()=='sg13g2_dlygate4sd3_1'and list(cell.getLocation())==row['location']and cell.getOrient()==row['orientation'],'delay master/site changed')
            require(block.findInst(instance).findITerm(pinname).getNet().getName()==row['output_net'],'delay bypassed or target bit changed')
            for terminal,net in [('A',row['input_net']),('X',row['output_net']),('VDD','VDDlogic'),('VSS','VSS')]:require(cell.findITerm(terminal).getNet().getName()==net,'delay input/output/power changed')
        require(block.findInst('pen_sram_lane0').findITerm('A_ADDR[0]').getNet().getName()==before[0][('pen_sram_lane0','A_ADDR[0]')][0],'setup-negative ADDR0 was changed')
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
        pin=block.findInst('task009_hold_decode_launch_0').findITerm(terminal);saved=pin.getNet();pin.connect(block.findNet(wrong))
        try:validate()
        except ValueError:negatives.append('actual_new_'+terminal+'_retarget')
        else:raise ValueError('launch negative admitted')
        pin.connect(saved);validate()
    cell=block.findInst('task009_hold_decode_launch_0');where=cell.getLocation()
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
    for label,pin,wrong in [('actual_delay_bypass',block.findInst('pen_sram_lane0').findITerm('A_DIN[49]'),delay_sites[0]['input_net']),('actual_delay_bit_retarget',block.findInst('pen_sram_lane0').findITerm('A_DIN[49]'),delay_sites[1]['output_net']),('actual_delay_input_retarget',block.findInst(delay_sites[0]['name']).findITerm('A'),'sample_ready'),('actual_delay_supply_retarget',block.findInst(delay_sites[0]['name']).findITerm('VDD'),'VSS'),('actual_ADDR0_unadmitted_delay',block.findInst('pen_sram_lane0').findITerm('A_ADDR[0]'),delay_sites[0]['output_net'])]:
        saved=pin.getNet();pin.connect(block.findNet(wrong))
        try:validate()
        except ValueError:negatives.append(label)
        else:raise ValueError('delay negative admitted: '+label)
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
    result={'status':'PASS_JOINT_TWO_DECODE_LAUNCH_EIGHT_DIN_DELAY_SPACER_ENDPOINT_PRECURSOR_NOT_ROUTED',
        'source_ODB_sha256':SOURCE_SHA,'geometry_ODB_sha256':sha(directory/'unrouted.odb'),'actual_nominal_loads':loads,
        'sites':sites,'delay_sites':delay_sites,'old_functional_cells_moved':0,'old_functional_and_macro_instances':9039,'new_original_buf8':2,'new_original_delaycells':8,'unresolved_ADDR0_setup_ns':rows['pen_sram_lane0/A_ADDR[0]']['minimum_setup_ns'],
        'old_spacers':40241,'new_spacers':len(plan['fillers']),'spacers_removed':sorted(removed),'spacers_added':new_rows,
        'affected_rows_y_nm':sorted(affected_y),'functional_padding_nm':960,'ports':len(after[2]),'native_PG_shapes':sum(after[3].values()),
        'new_supply_terminals_with_actual_row_overlap':len(new_pg),
        'OBS':len(after[4]),'original33delays_preserved':True,'negative_cases':negatives,'seconds':time.monotonic()-started,
        'native_master_library_relation':library_relation,
        'remaining':'ActualPGpin overlap/PSM, originalgate4state fixture, finalsource/master geometry, originalGDS/NWell, freshroute/native420/3RC/all9timing/process/LVS. No selection.'}
    (directory/'preparation.json').write_text(json.dumps(result,indent=2)+'\n');return result



JOINT_GEOMETRY_SHA='cf942d361ca31d36fa11e3f7906d47a03f7cd1ed74a6e3bae9bfd2eb3cf6c41c'
JOINT_PREPARE_SHA='3fd458a32d7e8b26a614bb6999e01a7172f1e54476715dd3b6a942f8b2db9ff2'
JOINT_READBACK_SHA='84ee925b12ad652f6cc9d2826da1919a01946a8cf57af154fa23215a662e9579'
JOINT_GDS_SHA='2c8865cce528e666b10f8b66c3938257ca1825edaf4dfbd174cd42dfbba0a6e4'
JOINT_NWELL_SHA='662684dc35e1a704b3cd60b1079639bc166f62f8df5d4c58d0e16257801f55ff'


def admit(directory):
    import ast
    directory=directory.resolve();base=ROOT/'build/silicon/task009-joint-hold-decode-preflight-a1'
    require(directory==base and sha(base/'repair.py')==JOINT_PREPARE_SHA and
            sha(base/'candidate/unrouted.odb')==JOINT_GEOMETRY_SHA,'exact actual joint source geometry required')
    original=(base/'repair.py').read_text();current=Path(__file__).read_text()
    require(current.startswith(original),'promoted preparation bytes differ from actual producer')
    tail=ast.parse(current[len(original):]).body
    names={'JOINT_GEOMETRY_SHA','JOINT_PREPARE_SHA','JOINT_READBACK_SHA','JOINT_GDS_SHA','JOINT_NWELL_SHA'}
    require(len(tail)==8,'only five literal pins and three reviewed consumer definitions may extend original preparation')
    seen=set()
    for node in tail:
        if isinstance(node,ast.Assign):
            require(len(node.targets)==1 and isinstance(node.targets[0],ast.Name)and node.targets[0].id in names and
                    isinstance(node.value,ast.Constant)and type(node.value.value)is str,'unreviewed top-level preparation extension')
            seen.add(node.targets[0].id)
        else:require(isinstance(node,ast.FunctionDef)and node.name in('admit','assess','require_recipe')and
                     not node.decorator_list and not node.args.defaults and all(x is None or isinstance(x,ast.Constant)and x.value is None for x in node.args.kw_defaults),
                     'unreviewed preparation consumer definition')
    require(seen==names,'literal qualification identities missing')
    receipts=[(base/'result.json','4449eedb3d0044e15859c4c2d0067f7a81e8d688dd9ab1ca83613560ea149460'),
        (ROOT/'build/silicon/task009-joint-hold-decode-readback-a2/result.json',JOINT_READBACK_SHA),
        (ROOT/'build/silicon/task009-joint-hold-decode-gds-a2/result.json',JOINT_GDS_SHA),
        (ROOT/'build/silicon/task009-joint-hold-decode-original-nwell-a1/result.json',JOINT_NWELL_SHA)]
    inputs=[]
    for path,digest in receipts:
        require(sha(path)==digest,'exact completed joint producer differs')
        r=json.loads(path.read_text());require(r['status'].startswith('PASS_')and r['source_seal_equal']and not r['resource_errors'],
                                             'joint source/resource component did not pass')
        for name,value in r['source_inputs'].items():
            require(sha(Path(name))==value,'joint qualified input differs: '+name);inputs.append(Path(name))
        inputs.append(path)
    first=json.loads(receipts[0][0].read_text());require([x['exit_code']for x in first['commands'][:6]]==[0,0,0,1,0,1]and
            first['power']['all_power_terminals']==98559 and first['power']['macro_power_pins']==9 and first['power']['preserved_BIST_pins']==423,
            'actual original four-state controls and power component required')
    native=json.loads(receipts[1][0].read_text());require(native['geometry']['instances']==49278 and native['all_owned_reaped'],
            'fresh native source-plan/master readback required')
    gds=json.loads(receipts[2][0].read_text());require(gds['geometry']['actual_native_instances']==49278 and
            all(x['XOR_area_nm2']==0 for x in gds['geometry']['mask_unions'])and gds['all_owned_reaped'],
            'actual original GDS/native PG/port unions required')
    nw=json.loads(receipts[3][0].read_text());require(nw['owned_observed_PIDs_absent']and nw['original_whole_deadline_met']and
            len(nw['results'])==1 and nw['results'][0]['total']==0,'original NWell table did not pass')
    # The old preparation's two unenumerated imports remain a scoped gap.
    # Fresh native readback and originalGDS/NWell independently bind the same
    # geometry; every current consumed helper is pinned again by the caller.
    inputs += [base/'candidate/preparation.json',base/'candidate/row-plan.json',base/'repair.py']
    return base/'candidate/unrouted.odb',receipts[-1][0],list(dict.fromkeys(inputs))


def assess(source,geometry,lib,output,*,fixed_geometry=None):
    import odb
    from silicon_acceptance_launch import snapshot
    from silicon_well_fill_route import master_library_relation
    require(sha(source)==SOURCE_SHA and sha(lib)==LIB_SHA and fixed_geometry is not None and
            sha(fixed_geometry)==JOINT_GEOMETRY_SHA,'exact joint source/library/fixed geometry required')
    started=time.monotonic();old,new,ref=[odb.dbDatabase.create()for _ in range(3)]
    for db,path in((old,source),(new,geometry),(ref,fixed_geometry)):odb.read_db(db,str(path))
    before=snapshot(old.getChip().getBlock());block=new.getChip().getBlock();after=snapshot(block)
    base=ROOT/'build/silicon/task009-joint-hold-decode-preflight-a1';prepared=json.loads((base/'candidate/preparation.json').read_text())
    oldplan=json.loads((ROOT/'build/silicon/task009-two-load-launch-preflight-a2/candidate/row-plan.json').read_text())
    newplan=json.loads((base/'candidate/row-plan.json').read_text());oldfills={x['name']for x in oldplan['fillers']};fills={x['name']for x in newplan['fillers']}
    added={x['new_cell']for x in prepared['sites']}|{x['name']for x in prepared['delay_sites']}
    require(len(oldfills)==40241 and len(fills)==40229 and len(added)==10 and len(after[1])==49278,'literal joint inventory differs')
    expected={key:value for key,value in before[0].items()if key[0]not in oldfills}
    for index,row in enumerate(prepared['sites']):
        key=row['driver'],'Y';expected[key]=('task009_hold_decode_launch_'+str(index)+'_driver',expected[key][1])
    for row in prepared['delay_sites']:
        key=tuple(row['endpoint'].split('/'));require(expected[key][0]==row['input_net'],'original DIN bit differs');expected[key]=(row['output_net'],expected[key][1])
    require({k:v for k,v in after[0].items()if k[0]not in fills and k[0]not in added}==expected,'old terminal changed beyond exact2launch/8DIN')
    require({k:v for k,v in after[1].items()if k not in fills and k not in added}=={k:v for k,v in before[1].items()if k not in oldfills}and
            after[2:]==before[2:],'old sites/master/668ports/nativePG/OBS changed')
    require(snapshot(ref.getChip().getBlock())==after,'routing changed fixed qualified joint sites/pins/spacers')
    native=master_library_relation(old,new,Path(output).parent/'joint-master-library')
    r={'status':'PASS_EXACT_JOINT_DECODE_HOLD_FIXED_ENDPOINTS_MASTER_PADDING_SPACERS','source_ODB_sha256':SOURCE_SHA,
        'geometry_ODB_sha256':sha(geometry),'fixed_geometry_ODB_sha256':JOINT_GEOMETRY_SHA,'old_functional_and_macro_instances':9039,
        'old_functional_cells_moved':0,'new_original_buf8':2,'new_original_delaycells':8,'original_spacers':40241,'updated_spacers':40229,
        'functional_padding_nm':960,'ports':len(after[2]),'native_PG_shapes':sum(after[3].values()),'OBS':len(after[4]),
        'original33_SRAM_delaycells_preserved':True,'BIST_pins_preserved':423,'ADDR0_unmodified':True,'native_master_library':native,
        'actual_qualifying_native_readback_sha256':JOINT_READBACK_SHA,'original_NWell_predecessor_sha256':JOINT_NWELL_SHA,
        'seconds':time.monotonic()-started,'scope':'Exact original-model finite and native endpoint/master/fixed-source relation only. New route/PG/native420/RC/all9 and process/LVS remain independently required.'}
    Path(output).write_text(json.dumps(r,indent=2)+'\n');return r


def require_recipe(args):
    if not getattr(args,'hold_decode_from',None):return
    require(args.routed_eco_from and args.clock_min_routing_layer=='Metal3'and args.detail_route_iterations==8 and
            args.host_memory_gib==6 and not getattr(args,'selected_implementation',False)and
            not any(getattr(args,name,False)for name in('two_load_launch_from','well_fill_from','decode_launch_buffer_from','slew_launch_buffer_from',
                'acceptance_launch_buffer','padded_sram_input_delay_from','control_launch_buffer_from','capacity_launch_buffer_from','power_margin_from',
                'preferred_access_from','preferred_access_preflight_only','preserve_routed_netlist','fresh_core_power_grid','vss_clock_grid_source',
                'protect_sram_power_edges','protect_sram_power_geometry','completed_eco_route_from','completed_power_grid_route_from',
                'completed_fresh_grid_route_from','completed_well_fill_route_from','defer_global_eco','center_validation_cones','group_button_bus')),
            'joint hold/decode requires exact qualified8bc source/full8/clockM3/6AS, no other recipe')
