#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independent integer geometry for the pinned simple-enclosure subset.
Not a complete DRC engine. Unknown shapes/clauses fail rather than disappear.
"""
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import re,struct

class GeometryError(ValueError): pass

def require(ok,why):
 if not ok:raise GeometryError(why)

def dbu(text):
 n=Decimal(text)*1000;require(n==int(n),'nonintegral nanometre coordinate');return int(n)

@dataclass(frozen=True)
class Rect:
 x0:int;y0:int;x1:int;y1:int
 def __post_init__(self):require(self.x0<self.x1 and self.y0<self.y1,'degenerate/inverted rectangle')
 def expanded(self,x,y):return Rect(self.x0-x,self.y0-y,self.x1+x,self.y1+y)
 def transformed(self,index):
  require(0<=index<8,'unknown orientation');points=[]
  for x,y in [(self.x0,self.y0),(self.x1,self.y0),(self.x1,self.y1),(self.x0,self.y1)]:
   if index>=4:x=-x
   for _ in range(index%4):x,y=-y,x
   points.append((x,y))
  return Rect(min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points))
 @property
 def size(self):return tuple(sorted((self.x1-self.x0,self.y1-self.y0)))

def covers(target,metal):
 """Exact rectangle-union coverage, including holes/notches; no bbox shortcut."""
 xs=sorted({target.x0,target.x1}|{max(target.x0,min(target.x1,x))for r in metal for x in [r.x0,r.x1]})
 for left,right in zip(xs,xs[1:]):
  if left==right:continue
  spans=sorted((max(target.y0,r.y0),min(target.y1,r.y1))for r in metal if r.x0<=left and right<=r.x1 and r.y0<target.y1 and target.y0<r.y1)
  upto=target.y0
  for low,high in spans:
   if low>upto:break
   upto=max(upto,high)
  if upto<target.y1:return False
 return True

def enclosure(cut,metal,first,second):
 require(first>=0 and second>=0,'negative enclosure')
 return covers(cut.expanded(first,second),metal)or covers(cut.expanded(second,first),metal)

def read_tech(path):
 text=Path(path).read_text();s=re.sub(r'#[^\n]*','',text);require('DATABASE MICRONS 1000'in s,'unsupported database units')
 layers={};order=[]
 for m in re.finditer(r'^LAYER\s+(\S+)\s*\n(.*?)^END\s+\1\s*$',s,re.M|re.S):
  name,body=m[1],m[2];order.append(name)
  if re.search(r'\bTYPE\s+CUT\s*;',body):
   rules=[]
   for r in re.finditer(r'(?m)^\s*ENCLOSURE\s+([^;]+);',body):
    v=r[1].split();side=v.pop(0)if v and v[0]in('ABOVE','BELOW')else'BOTH';require(len(v)==2,'unsupported enclosure clause');rules.append((side,dbu(v[0]),dbu(v[1])))
   require(rules,'cut layer with no simple enclosure');layers[name]={'body':body,'rules':rules,'classes':set(),'widths':re.findall(r'\bWIDTH\s+([\d.]+)\s*;',body)}
 vias=[]
 # LEF permits indentation on both declaration and END. The original strict
 # column-zero END pattern silently omitted ordinary Via1_YY/Via4_YX etc.;
 # fail-closed route consumers require the complete fixed-via library.
 for kind,pattern in [('fixed',r'^[ \t]*VIA\s+(\S+)[^\n]*\n(.*?)^[ \t]*END\s+\1\s*$'),('generated',r'^[ \t]*VIARULE\s+(\S+)[^\n]*\n(.*?)^[ \t]*END\s+\1\s*$')]:
  for m in re.finditer(pattern,s,re.M|re.S|re.I):
   sections={};current=None;parameters={};pitch=None
   for stmt in m[2].split(';'):
    words=stmt.split()
    if not words:continue
    if words[0].upper()=='LAYER':require(len(words)==2,'unknown via layer clause');current=words[1];sections.setdefault(current,[])
    elif words[0].upper()=='RECT':
     require(current is not None and len(words)==5,'unknown via rectangle');sections[current].append(Rect(*(dbu(x)for x in words[1:])))
    elif kind=='generated' and words[0].upper()=='ENCLOSURE':
     require(current is not None and len(words)==3,'unknown generated enclosure');parameters[current]=tuple(dbu(v)for v in words[1:])
    elif kind=='generated' and words[0].upper()=='SPACING':
     require(current in layers and len(words)==4 and words[2]=='BY','unknown generated spacing');pitch=(dbu(words[1]),dbu(words[3]))
    elif words[0].upper()in('POLYGON','PATH','VIA'):raise GeometryError('unsupported via shape')
   cuts=set(sections)&set(layers);require(len(cuts)==1,'via must have one classified cut layer');cut=next(iter(cuts));index=order.index(cut);lower,upper=order[index-1],order[index+1]
   require(set(sections)=={cut,lower,upper},'via layer order/coverage mismatch')
   require(sections[cut],'via with no cut rectangles')
   for r in sections[cut]:layers[cut]['classes'].add(r.size)
   vias.append({'name':m[1],'kind':kind,'cut':cut,'lower':lower,'upper':upper,'shapes':sections,'enclosures':parameters,'pitch':pitch})
 require(vias,'empty via corpus')
 return text,layers,vias

def check_fixed(layers,vias):
 rows=[]
 for v in vias:
  if v['kind']!='fixed':continue
  for side,a,b in layers[v['cut']]['rules']:
   for which in ['lower','upper']:
    if side=='ABOVE'and which!='upper'or side=='BELOW'and which!='lower':continue
    for index,cut in enumerate(v['shapes'][v['cut']]):
     metal=v['shapes'][v[which]]
     # All eight rigid orthogonal orientations must give the same predicate.
     ok=enclosure(cut,metal,a,b)
     require(all(enclosure(cut.transformed(k),[r.transformed(k)for r in metal],a,b)==ok for k in range(8)),'orientation changed enclosure semantics')
     rows.append({'via':v['name'],'cut_index':index,'layer':v['cut'],'side':which,'overhang_nm':[a,b],'original_enclosure_met':ok})
 return rows

def gds_real(raw):
 require(len(raw)==8,'bad GDS real width')
 if raw==b'\0'*8:return Fraction(0)
 sign=-1 if raw[0]&128 else 1;exponent=(raw[0]&127)-64;mantissa=int.from_bytes(raw[1:],'big')
 return sign*Fraction(mantissa,1<<56)*(Fraction(16)**exponent)

def scan_gds_cuts(path,layer_map):
 """Classify all cell-library cuts; reject transformed/nonrectangular unknowns.
Array positions do not change individual cut size. Only orthogonal rigid
reference transforms are admitted, so every referenced class remains exact.
"""
 data=Path(path).read_bytes();require(0<len(data)<=64<<20,'GDS size bound');offset=0;current=None;cell=None;unit=None;counts={n:0 for n in layer_map.values()};classes={n:set()for n in counts};refs=0;ended=False
 while offset<len(data):
  require(offset+4<=len(data),'truncated GDS header');length,typ,dtype=struct.unpack_from('>HBB',data,offset);require(length>=4 and length%2==0 and offset+length<=len(data),'bad GDS record');raw=data[offset+4:offset+length];offset+=length
  if typ==4:
   require(current is None and len(data)-offset<=2048 and not any(data[offset:]),'invalid trailing GDS data');ended=True;break
  if typ==3:require(len(raw)==16,'bad GDS units');require(raw==bytes.fromhex('3e4189374bc6a7f03944b82fa09b5a54'),'unsupported pinned GDS units encoding');unit=Fraction(1,1_000_000_000)
  elif typ==6:cell=raw.rstrip(b'\0').decode('ascii')
  elif typ in(8,9,10,11,12,21,45):require(current is None,'nested GDS element');current={'type':typ,'cell':cell}
  elif typ in(13,14)and current is not None:require(len(raw)==2,'bad GDS layer/datatype');current['layer'if typ==13 else'datatype']=struct.unpack('>H',raw)[0]
  elif typ==16 and current is not None:
   require(len(raw)%8==0,'bad GDS XY');current['points']=list(zip(*[iter(struct.unpack('>'+str(len(raw)//4)+'i',raw))]*2))
  elif typ==26 and current is not None:require(len(raw)==2 and struct.unpack('>H',raw)[0]&~0x8006==0,'unknown GDS transform flags')
  elif typ==27 and current is not None and current['type']in(10,11):require(gds_real(raw)==1,'scaled GDS reference not admitted')
  elif typ==28 and current is not None and current['type']in(10,11):require(gds_real(raw)%90==0,'nonorthogonal GDS reference not admitted')
  elif typ==17:
   require(current is not None,'GDS ENDEL outside element');key=(current.get('layer'),current.get('datatype'))
   if key in layer_map:
    name=layer_map[key];require(current['type']in(8,45),'nonarea/unsupported cut shape');points=current.get('points',[]);require(len(points)==5 and points[0]==points[-1],'cut must be an exact rectangle');rect=Rect(min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points));require(set(points[:-1])=={(rect.x0,rect.y0),(rect.x0,rect.y1),(rect.x1,rect.y0),(rect.x1,rect.y1)},'nonrectangular cut boundary');require(all(x==xx or y==yy for (x,y),(xx,yy)in zip(points,points[1:])),'diagonal cut boundary');classes[name].add(rect.size);counts[name]+=1
   if current['type']in(10,11):refs+=1
   current=None
 require(ended and current is None and unit is not None,'incomplete GDS library');require(sum(counts.values())>0,'empty classified cell cut corpus')
 return classes,counts,refs


def check_generators(layers,vias):
 rows=[]
 for v in vias:
  if v['kind']!='generated':continue
  require(len(v['shapes'][v['cut']])==1 and v['pitch']is not None,'unsupported generated cut template')
  cut=v['shapes'][v['cut']][0];px,py=v['pitch'];require(px>=cut.x1-cut.x0 and py>=cut.y1-cut.y0,'overlapping generated cut pitch')
  for which in ('lower','upper'):
   layer=v[which];require(layer in v['enclosures'],'missing generated enclosure');x,y=v['enclosures'][layer]
   for side,a,b in layers[v['cut']]['rules']:
    if side=='ABOVE'and which!='upper'or side=='BELOW'and which!='lower':continue
    require((x>=a and y>=b)or(x>=b and y>=a),'generated minimum enclosure violates original rule')
   # A multi-cut corner checks individual cuts, rather than one array bbox.
   cuts=[Rect(cut.x0+col*px,cut.y0+row*py,cut.x1+col*px,cut.y1+row*py)for row in range(2)for col in range(3)]
   hull=Rect(cuts[0].x0,cuts[0].y0,cuts[-1].x1,cuts[-1].y1).expanded(x,y)
   for side,a,b in layers[v['cut']]['rules']:
    if side=='ABOVE'and which!='upper'or side=='BELOW'and which!='lower':continue
    require(all(enclosure(c,[hull],a,b)for c in cuts),'generated array enclosure mismatch')
   rows.append({'generator':v['name'],'side':which,'minimum_nm':[x,y],'array':'2x3 individual cuts checked'})
 return rows


def run_tool(argv,log,timeout,stdin=None):
 import subprocess,os,signal,time
 started=time.monotonic()
 with Path(log).open('xb')as output:
  source=Path(stdin).open('rb')if stdin else subprocess.DEVNULL
  try:
   process=subprocess.Popen(argv,stdin=source,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
   try:code=process.wait(timeout=timeout)
   except BaseException:
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
    raise
  finally:
   if stdin:source.close()
 require(code==0,'tool failure; retained '+str(log))
 return {'argv':argv,'stdin':str(stdin)if stdin else None,'returncode':code,'seconds':time.monotonic()-started,'log_sha256':file_sha(log)}


def file_sha(path):
 import hashlib
 digest=hashlib.sha256()
 with Path(path).open('rb')as stream:
  for chunk in iter(lambda:stream.read(1<<20),b''):digest.update(chunk)
 return digest.hexdigest()


def verify_inputs(pdk_root, held):
 """Admit the complete pinned source closure before invoking either EDA tool."""
 require(isinstance(held,dict) and len(held)==34,'incomplete pinned PDK closure')
 for name,digest in held.items():
  relative=Path(name)
  require(not relative.is_absolute() and '..'not in relative.parts and
          isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest),
          'invalid pinned PDK input identity')
  require(file_sha(Path(pdk_root)/relative)==digest,'pinned PDK geometry/rules differ: '+name)


def magic_fixture(out,via):
 def record(typ,kind,raw=b''):return struct.pack('>HBB',len(raw)+4,typ,kind)+raw
 def string(typ,value):
  raw=value.encode('ascii');return record(typ,6,raw+b'\0'*(len(raw)%2))
 def short(typ,*values):return record(typ,2,struct.pack('>'+str(len(values))+'h',*values))
 def boundary(layer,r):
  xy=[r.x0,r.y0,r.x1,r.y0,r.x1,r.y1,r.x0,r.y1,r.x0,r.y0]
  return record(8,0)+short(13,layer)+short(14,0)+record(16,3,struct.pack('>10i',*xy))+record(17,0)
 dates=[2026,10,16,0,0,0]*2
 data=short(0,600)+short(1,*dates)+string(2,'LEMMA_ENCLOSURE')+record(3,5,bytes.fromhex('3e4189374bc6a7f03944b82fa09b5a54'))
 for name,repair in [('original',False),('repaired',True)]:
  data+=short(5,*dates)+string(6,name)
  for layer,rectangles in via['shapes'].items():
   for rectangle in rectangles:
    if repair and layer=='Metal1':rectangle=Rect(-105,rectangle.y0,rectangle.x1,rectangle.y1)
    data+=boundary({'Metal1':8,'Via1':19,'Metal2':10}[layer],rectangle)
  data+=record(7,0)
 (out/'via-geometry.gds').write_bytes(data+record(4,0))
 script=f'''cd {{{out}}}
if {{[catch {{
 gds readonly true
 gds read {{{out/'via-geometry.gds'}}}
 foreach name {{original repaired}} {{
  load $name
  select top cell
  expand
  drc style drc(full)
  drc on
  drc check
  drc catchup
  set f [open $name-drc.txt w]
  puts $f [drc list count total]
  puts $f [drc listall why]
  close $f
 }}
}} failure]}} {{puts stderr "Geometry validation failed: $failure";exit 1}}
quit -noprompt
'''
 (out/'via-geometry.tcl').write_text(script)


def prepare(pdk_root,out,repair_known_via,timeout):
 import json,shutil,subprocess,time
 root=Path(__file__).resolve().parents[1];profile_path=root/'tooling/silicon/enclosure-inputs-v1.json';profile=json.loads(profile_path.read_text())
 require(profile.get('schema')=='lemma-sg13g2-enclosure-inputs/1'and profile.get('dbu_per_micron')==1000,'unsupported input profile')
 pdk_root=Path(pdk_root).resolve();out=Path(out).resolve();require(not out.exists(),'unused output required');out.mkdir(parents=True)
 report={'schema':'lemma-sg13g2-enclosure-preflight/1','status':'FAIL','scope':'Closed original fixed/generated/cell cut geometry, simple enclosure predicates and native OpenDB import. Not routed-controller/process DRC, LVS, parasitic or timing qualification.','profile_sha256':file_sha(profile_path),'producer_sha256':file_sha(__file__),'commands':[]};started=time.monotonic()
 try:
  held=profile['source_inputs'];verify_inputs(pdk_root,held)
  report['source_inputs']=held
  std=pdk_root/'ihp-sg13g2/libs.ref/sg13g2_stdcell';text,layers,vias=read_tech(std/'lef/sg13g2_tech.lef');before=check_fixed(layers,vias);bad=[r for r in before if not r['original_enclosure_met']]
  require(len(bad)==1 and (bad[0]['via'],bad[0]['layer'],bad[0]['side'],bad[0]['cut_index'])==('Via1_DC2L','Via1','lower',0),'unexpected fixed geometry result')
  report['original_fixed_violation']=bad
  require(repair_known_via,'original Via1_DC2L enclosure fails; explicit --repair-known-via required')
  magic,openroad=shutil.which('magic'),shutil.which('openroad');require(magic and openroad,'pinned Magic/OpenROAD tools required')
  require(subprocess.check_output([magic,'--version'],text=True,timeout=15).strip()==profile['magic_version'],'Magic version differs')
  require(profile['openroad_version']in subprocess.check_output([openroad,'-version'],text=True,timeout=15),'OpenROAD version differs')
  report['tools']={name:{'path':str(Path(path).resolve()),'sha256':file_sha(Path(path).resolve())}for name,path in [('magic',magic),('openroad',openroad)]}
  magic_fixture(out,next(v for v in vias if v['name']=='Via1_DC2L'))
  rc=pdk_root/'ihp-sg13g2/libs.tech/magic/ihp-sg13g2.magicrc';report['commands'].append(run_tool([magic,'-dnull','-noconsole','-rcfile',str(rc)],out/'magic.log',timeout,out/'via-geometry.tcl'))
  original=(out/'original-drc.txt').read_text();repaired_result=(out/'repaired-drc.txt').read_text();require(original.splitlines()[0]=='1'and 'Metal1 overlap of Via1'in original and repaired_result.splitlines()[0]=='0','independent Magic original/repair outcomes differ')
  match=re.search(r'(?mi)^Via\s+Via1_DC2L\s+DEFAULT\s*\n(.*?)^END Via1_DC2L\s*$',text,re.S);require(match is not None,'fixed source via missing');block=match[0];needle='RECT -0.1 -0.145 0.52 0.145 ;';require(block.count(needle)==2,'unexpected source repair shape')
  changed=block.replace(needle,'RECT -0.105 -0.145 0.52 0.145 ;',1);repaired=text[:match.start()]+changed+text[match.end():];(out/'repaired-original.lef').write_text(repaired)
  _,layers,vias=read_tech(out/'repaired-original.lef');after=check_fixed(layers,vias);require(all(r['original_enclosure_met']for r in after),'fixed geometry still violates original enclosures');generated=check_generators(layers,vias)
  mapping={};aliases={'CONT':'Cont','VIA1':'Via1','VIA2':'Via2','VIA3':'Via3','VIA4':'Via4','VIA5':'TopVia1','VIA6':'TopVia2'}
  for m in re.finditer(r'(?m)^\s*calma\s+(\w+)\s+(\d+)\s+(\d+)\s*$',(pdk_root/'ihp-sg13g2/libs.tech/magic/ihp-sg13g2-cifin.tech').read_text()):
   if m[1]in aliases:mapping[int(m[2]),int(m[3])]=aliases[m[1]]
  require(set(mapping.values())==set(layers),'incomplete original cut layer map');cellclasses,cellcounts,refs=scan_gds_cuts(std/'gds/sg13g2_stdcell.gds',mapping)
  for name,sizes in cellclasses.items():layers[name]['classes']|=sizes
  current=None;pincounts={name:0 for name in layers}
  for line in re.sub(r'#[^\n]*','',(std/'lef/sg13g2_stdcell.lef').read_text()).splitlines():
   words=line.split()
   if not words:continue
   if words[0]=='LAYER':require(len(words)==3 and words[-1]==';','unknown cell layer');current=words[1]
   elif words[0]=='END':current=None
   elif current in layers and words[0]in('POLYGON','PATH','VIA'):raise GeometryError('unsupported pin cut geometry')
   elif current in layers and words[0]=='RECT':require(len(words)==6 and words[-1]==';','unknown pin cut rectangle');r=Rect(*(dbu(v)for v in words[1:5]));layers[current]['classes'].add(r.size);pincounts[current]+=1
  require(all(v['classes']for v in layers.values()),'unclassified cut layer');require(all(w==h for v in layers.values()for w,h in v['classes']),'non-square cut class requires separate qualification')
  require('LEF58_CUTCLASS'not in repaired and 'LEF58_ENCLOSURE'not in repaired,'unexpected existing modern properties');repaired=repaired.replace('PROPERTYDEFINITIONS\n','PROPERTYDEFINITIONS\n  LAYER LEF58_CUTCLASS STRING ;\n  LAYER LEF58_ENCLOSURE STRING ;\n',1);modern=[];fmt=lambda n:format(Decimal(n)/1000,'f')
  for name,layer in layers.items():
   classes=[];rules=[]
   for width,length in sorted(layer['classes']):
    cls=f'Lemma_{name}_{width}_{length}';classes.append(f'CUTCLASS {cls} WIDTH {fmt(width)} LENGTH {fmt(length)} CUTS 1 ;')
    for side,a,b in layer['rules']:
     rules.append(f'ENCLOSURE CUTCLASS {cls} '+(''if side=='BOTH'else side+' ')+f'{fmt(a)} {fmt(b)} ;');modern.append((name,cls,int(side=='ABOVE'),int(side=='BELOW'),a,b))
   addition='  PROPERTY LEF58_CUTCLASS "'+' '.join(classes)+'" ;\n  PROPERTY LEF58_ENCLOSURE "'+' '.join(rules)+'" ;\n';matches=list(re.finditer(r'(?m)^END '+re.escape(name)+r'\s*$',repaired));require(len(matches)==1,'ambiguous layer boundary');pos=matches[0].start();repaired=repaired[:pos]+addition+repaired[pos:]
  (out/'sg13g2_tech.lef').write_text(repaired)
  _,again,_=read_tech(out/'sg13g2_tech.lef');require({n:v['rules']for n,v in again.items()}=={n:v['rules']for n,v in layers.items()},'original mandatory enclosures lost or changed')
  script=f'''read_lef {{{out/'sg13g2_tech.lef'}}}
set f [open {{{out/'odb-rules.tsv'}}} w]
foreach layer [[ord::get_db_tech] getLayers] {{
 foreach cls [$layer getTechLayerCutClassRules] {{puts $f [join [list CLASS [$layer getName] [$cls getName] [$cls getWidth] [$cls getLength]] "\\t"]}}
 foreach rule [$layer getTechLayerCutEnclosureRules] {{
  set class -
  if {{[$rule isCutClassValid]}} {{set class [[$rule getCutClass] getName]}}
  puts $f [join [list RULE [$layer getName] $class [$rule isAbove] [$rule isBelow] [$rule getFirstOverhang] [$rule getSecondOverhang]] "\\t"]
 }}
}}
close $f
exit
''';(out/'import.tcl').write_text(script);report['commands'].append(run_tool([openroad,'-exit',str(out/'import.tcl')],out/'openroad.log',timeout))
  observed=[];legacy=[];observed_classes=[]
  for line in (out/'odb-rules.tsv').read_text().splitlines():
   fields=line.split('\t')
   if fields[0]=='CLASS':require(len(fields)==5,'malformed native class');observed_classes.append((fields[1],fields[2],int(fields[3]),int(fields[4])))
   else:
    require(fields[0]=='RULE'and len(fields)==7,'malformed native enclosure');row=(fields[1],fields[2],*(int(v)for v in fields[3:]));(legacy if fields[2]=='-'else observed).append(row)
  expected_classes=[(name,f'Lemma_{name}_{w}_{h}',w,h)for name,v in layers.items()for w,h in sorted(v['classes'])]
  expected_legacy=[(name,'-',int(side=='ABOVE'),int(side=='BELOW'),a,b)for name,v in layers.items()for side,a,b in v['rules']]
  require(sorted(observed_classes)==sorted(expected_classes)and sorted(observed)==sorted(modern)and sorted(legacy)==sorted(expected_legacy),'native class/rule coverage differs')
  verify_inputs(pdk_root,held)
  report.update(status='PASS_CLOSED_GEOMETRY_AND_NATIVE_ODB_IMPORT_NOT_ROUTED_DRC',repaired_fixed_checks=len(after),generator_checks=generated,cell_GDS_cut_counts=cellcounts,cell_pin_cut_counts=pincounts,orthogonal_cell_references=refs,classes=observed_classes,qualified_enclosures=observed,original_enclosures_retained=legacy,generated_lef_sha256=file_sha(out/'sg13g2_tech.lef'),geometry_repair='Via1_DC2L Metal1 minX -100→-105nm only; independent Magic original1/repaired0',remaining='Actual TritonRoute enforcement/fixed/generated/routed-pin suffix geometry and other rule coverage, complete-controller DRC/LVS/PEX/post-route timing/full-chip remain UNQUALIFIED. Original unsupported legacy clauses remain in the file; native duplicates do not erase warnings or establish process signoff.')
 except BaseException as error:
  report['error']=repr(error);raise
 finally:
  report['seconds']=time.monotonic()-started;(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 return report


def main():
 import argparse,resource,json
 parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);parser.add_argument('--pdk-root',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--repair-known-via',action='store_true');parser.add_argument('--timeout',type=int,default=180);args=parser.parse_args();require(15<=args.timeout<=300,'tool timeout must be15..300seconds')
 resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 result=prepare(args.pdk_root,args.output_dir,args.repair_known_via,args.timeout);print(json.dumps({'status':result['status'],'result':str(args.output_dir/'result.json')},indent=2))

if __name__=='__main__':main()
