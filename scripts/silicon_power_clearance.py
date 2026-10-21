#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual signal metal versus native PG: original420nm rectangle subset only.

Run check() inside the pinned OpenROAD Python interpreter. Every DEF segment,
via and patch binds the actual native wire decoder; unknown grammar fails.
No process DRC/LVS/connectivity/IR/EM/timing qualification follows.
"""
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from silicon_enclosure import read_tech, require
from silicon_route_enclosure import generated_arrays

METAL = ('Metal1','Metal2','Metal3','Metal4','Metal5')


def context(tech, raw):
    text,layers,definitions=read_tech(tech)
    widths={}
    for name in METAL:
        card=re.search(r'^LAYER '+name+r'\n(.*?)^END '+name+r'$',text,re.M|re.S)[1]
        widths[name]=round(float(re.search(r'^\s*WIDTH\s+(\d+(?:\.\d+)?)\s*;',card,re.M)[1])*1000)
    require(widths==dict(zip(METAL,[160,200,200,200,200])),'original layer widths changed')
    vias={v['name']:v for v in definitions+generated_arrays(raw,layers,definitions)if v['kind']=='fixed'}
    nd={}
    section=re.search(r'^NONDEFAULTRULES \d+ ;(.*?)^END NONDEFAULTRULES',raw,re.M|re.S)
    require(section is not None,'missing original nondefault rules')
    for name,body in re.findall(r'^\s*- (\S+)\s+(.*?);',section[1],re.M|re.S):
        require(name in ('CTS_NDR_0','CTS_NDR_1'),'unexpected nondefault rule')
        require(all('LAYER '+l+' WIDTH 200 SPACING 420' in body for l in METAL[1:]),'original CTS rules changed')
        nd[name]=200
    require(set(nd)=={'CTS_NDR_0','CTS_NDR_1'},'incomplete original CTS rules')
    return widths,vias,nd


def parse_paths(record, ctx):
    widths,vias,nd=ctx
    parts=re.split(r'\s+(?:\+\s+ROUTED|NEW)\s+',record)
    if len(parts)==1:
        require(not re.search(r'\+\s+(?:FIXED|COVER)\b',record),'unqualified signal route kind')
        return [],[]
    ndr=re.search(r'\+ NONDEFAULTRULE (\w+)',parts[0])
    require(ndr is None or ndr[1]in nd,'unbound nondefault rule')
    shapes=[];patches=[]
    for branch in parts[1:]:
        tokens=re.findall(r'\([^)]*\)|[^\s()]+',branch)
        require(tokens and tokens[0]in widths,'unqualified signal route layer')
        layer=tokens.pop(0);taper=bool(tokens and tokens[0]=='TAPER')
        if taper:tokens.pop(0)
        width=widths[layer]if not ndr or taper or layer=='Metal1'else nd[ndr[1]]
        point=None;extension=None;i=0
        while i<len(tokens):
            token=tokens[i];i+=1
            if token.startswith('('):
                words=token[1:-1].split();require(len(words)in(2,3),'unqualified route coordinate')
                require(point is not None or '*'not in words[:2],'unbound repeated coordinate')
                x=point[0]if words[0]=='*'else int(words[0]);y=point[1]if words[1]=='*'else int(words[1])
                ext=int(words[2])if len(words)==3 else width//2;require(ext>=0,'negative extension')
                if point is not None and [x,y]!=point:
                    px,py=point;oldext=extension;require(px==x or py==y,'nonorthogonal route')
                    if py==y:box=[min(px,x)-(oldext if px<x else ext),y-width//2,max(px,x)+(ext if px<x else oldext),y+width//2]
                    else:box=[x-width//2,min(py,y)-(oldext if py<y else ext),x+width//2,max(py,y)+(ext if py<y else oldext)]
                    shapes.append(('wire',layer,tuple(box),None,None))
                point=[x,y];extension=ext
            elif token=='RECT':
                require(point is not None and i<len(tokens),'unbound patch')
                words=tokens[i][1:-1].split();i+=1;require(len(words)==4,'patch coordinates')
                a,b,c,d=map(int,words);require(a<c and b<d,'patch area')
                x,y=point;shapes.append(('patch',layer,(a+x,b+y,c+x,d+y),None,None));patches.append((layer,tuple(point)))
            elif token in vias:
                require(point is not None,'unbound via')
                for current,boxes in vias[token]['shapes'].items():
                    if current not in METAL:continue
                    for box in boxes:shapes.append(('via',current,(box.x0+point[0],box.y0+point[1],box.x1+point[0],box.y1+point[1]),token,tuple(point)))
            else:raise ValueError('unknown emitted routing token '+token)
    return shapes,patches


def native_shapes(wire):
    import odb
    d=odb.dbWireDecoder();d.begin(wire);started=False;point=None;shapes=[];patches=[]
    while True:
        op=d.next()
        if op==d.END_DECODE:break
        if op==d.PATH:started=False
        elif op in(d.JUNCTION,d.SHORT,d.VWIRE):started=True;point=list(wire.getCoord(d.getJunctionValue()))
        elif op in(d.POINT,d.POINT_EXT):
            point=d.getPoint()if op==d.POINT else d.getPoint_ext()[:2]
            if started:
                s=odb.dbShape();wire.getShape(d.getJunctionId(),s);require(s.isSegment(),'expected native segment')
                shapes.append(('wire',s.getTechLayer().getName(),(s.xMin(),s.yMin(),s.xMax(),s.yMax()),None,None))
            started=True
        elif op in(d.VIA,d.TECH_VIA):
            s=odb.dbShape();wire.getShape(d.getJunctionId(),s);require(s.isVia(),'expected native via')
            x,y=s.getViaXY();v=s.getTechVia()or s.getVia();require(v is not None,'native via model missing')
            for box in v.getBoxes():
                l=box.getTechLayer().getName()
                if l in METAL:shapes.append(('via',l,(box.xMin()+x,box.yMin()+y,box.xMax()+x,box.yMax()+y),v.getName(),(x,y)))
        elif op==d.RECT:
            require(point is not None,'native patch without origin');patches.append((d.getLayer().getName(),tuple(point)))
        else:require(op in(d.ITERM,d.BTERM,d.RULE),'unknown native wire opcode')
    return shapes,patches


def rectangular_clearance(a,b):
    return max(b[0]-a[2],a[0]-b[2],b[1]-a[3],a[1]-b[3],0)


def check(source, tech, output):
    import odb
    from silicon_power_margin import pg_geometry
    source,tech,output=map(Path,(source,tech,output))
    db=odb.dbDatabase.create();odb.read_db(db,str(source));block=db.getChip().getBlock()
    require(block.getDbUnitsPerMicron()==1000,'original DB units')
    exported=output.with_suffix('.def');require(not exported.exists(),'unused native DEF export')
    odb.write_def(block,str(exported));raw=exported.read_text();ctx=context(tech,raw)
    section=re.search(r'^NETS\s+(\d+)\s*;(.*?)^END NETS',raw,re.M|re.S);require(section is not None,'missing net section')
    records={}
    for record in section[2].split(';'):
        if not record.strip():continue
        name=re.match(r'\s*- (\S+)',record);require(name is not None and name[1]not in records,'duplicate/invalid DEF net')
        records[name[1]]=record
    require(len(records)==int(section[1]),'incomplete DEF nets')
    _,metals,_=pg_geometry(block);native=Counter((l,a,b,c,d)for (_,l,a,b,c,d),n in metals.items()for _ in range(n)if l in METAL[1:])
    for inst in block.getInsts():
        if inst.getMaster().getType()!='BLOCK':continue
        for t in inst.getITerms():
            if t.getSigType()not in ('POWER','GROUND'):continue
            for l,q in t.getGeometries():native[(l.getName(),q.xMin(),q.yMin(),q.xMax(),q.yMax())]+=1
    buckets=defaultdict(set);power=list(native)
    for index,(l,a,b,c,d)in enumerate(power):
        for x in range((a-420)//25000,(c+420)//25000+1):
            for y in range((b-420)//25000,(d+420)//25000+1):buckets[l,x,y].add(index)
    count=0;routes=0;patch_count=0;bad=[];bad_count=0
    for net in block.getNets():
        if net.getSigType()in ('POWER','GROUND'):continue
        require(net.getName()in records,'native signal net missing from DEF')
        shapes,patches=parse_paths(records[net.getName()],ctx)
        if not net.getWire():
            require(not shapes and not patches,'DEF wire absent from actual native net');continue
        ns,np=native_shapes(net.getWire())
        require(Counter(s for s in shapes if s[0]!='patch')==Counter(ns),'actual native wire/via/extension differs: '+net.getName())
        require(Counter(patches)==Counter(np),'actual native patch origins differ: '+net.getName())
        routes+=1;patch_count+=len(patches)
        for kind,l,box,name,center in set(shapes):
            if l not in METAL[1:]:continue
            count+=1;a,b,c,d=box;indices=set()
            for x in range(a//25000,c//25000+1):
                for y in range(b//25000,d//25000+1):indices.update(buckets[l,x,y])
            for index in indices:
                _,pa,pb,pc,pd=power[index];distance=rectangular_clearance(box,(pa,pb,pc,pd))
                if distance>=420:continue
                bad_count+=1
                if len(bad)<200:bad.append({'net':net.getName(),'kind':kind,'layer':l,'signal_box_nm':box,'native_PG_box_nm':[pa,pb,pc,pd],'actual_rectangular_clearance_nm':distance})
    result={'status':'FAIL_NATIVE420NM_RECTANGLE_MARGIN'if bad_count else'PASS_ACTUAL_NATIVE420NM_RECTANGLE_SUBSET_ONLY',
            'scope':__doc__,'native_signal_nets_bound':routes,'native_wire_via_patch_shapes_checked':count,
            'actual_DEF_RECT_patches_bound':patch_count,'unique_native_PG_metal_rectangles':len(power),
            'violation_pairs':bad_count,'first_200_violation_pairs':bad,
            'not_checked':['process DRC/EOL/area/density/antenna','full connected layout/netlist comparison','timing','IR/EM','pads/package/board']}
    output.write_text(json.dumps(result,indent=2)+'\n')
    return result
