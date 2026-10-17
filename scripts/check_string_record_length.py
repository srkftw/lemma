#!/usr/bin/env python3
"""Qualify the actual bounded Document7 fetch literal and object bytes."""
import argparse,copy,json,re,subprocess,sys,tempfile
from pathlib import Path
from core0_common import Core0Error,load_json,sha256,write_json
from lemmasim_readonly import validate_sums_record_length,validate_lookup,validate_object

def require(value,message):
 if not value:raise Core0Error(message)
def check(directory,output):
 unit=load_json(directory/'unit.json');ir=(directory/'program.opt.ll').read_text()
 def observe(text,u):
  sites,tables,removed=validate_sums_record_length(text,u)
  require(len(tables)==1 and tables[0]['literal_schema']=='document-v7-length-v1' and tables[0]['index_bound']==6 and tables[0]['values']==[1856,2496,2496,2496,2496,2496],'Actual Document7 literal authority absent')
  return {'sites':sorted(sites),'table':tables[0],'removed':sorted(removed)}
 baseline=observe(ir,unit);rejected=[]
 from audit_kernel import _ir_definition_body
 owner=_ir_definition_body(ir,baseline['table']['function'])
 require(owner is not None,'Actual complete Document7 owner absent')
 def reject(name,fn):
  try:fn()
  except Core0Error as e:rejected.append({'name':name,'error':str(e)});return
  raise Core0Error('Actual Document7 mutation admitted: '+name)
 for name,old,new in [('length','i64 1856,','i64 1857,'),('one_past_bound','%switch.tableidx, 6','%switch.tableidx, 7'),('inclusive_bound','icmp ult i64 %switch.tableidx','icmp ule i64 %switch.tableidx'),('version_origin','add i64 %action.call.value39, -2','add i64 %action.call.value39, -1')]:
  target=ir if name=='length' else owner
  require(old in target,'Actual literal/guard mutation anchor absent: '+name)
  changed=ir.replace(old,new,1) if name=='length' else ir.replace(owner,owner.replace(old,new,1),1)
  reject(name,lambda changed=changed:observe(changed,unit))
 for name,key,value in [('role','role','kernel'),('profile','contract_version','core0-user-v0.1'),('image','image_key','arithmetic')]:
  altered=copy.deepcopy(unit);altered[key]=value;reject(name,lambda altered=altered:observe(ir,altered))
 def tool(*argv):return subprocess.run(argv,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True).stdout
 section_text=tool('llvm-readelf','--sections','--wide',str(directory/'program.o'))
 symbols=tool('llvm-readelf','--symbols','--wide',str(directory/'program.o'))
 relocations=tool('llvm-readelf','--relocations','--wide',str(directory/'program.o'))
 _,tables,_=validate_lookup(ir,unit);raw={}
 with tempfile.TemporaryDirectory(prefix='lemma-string-literals-') as tmp:
  for name in ('.rodata','.rodata.cst32'):
   if re.search(r'\]\s+'+re.escape(name)+r'\s+',section_text):
    path=Path(tmp)/name[1:];tool('llvm-objcopy','--dump-section',name+'='+str(path),str(directory/'program.o'));raw[name]=path.read_bytes()
  obj=validate_object(section_text,symbols,relocations,raw,tables,str(directory/'program.o'))
  row=baseline['table'];label='.L'+row['global'];matches=[line.split() for line in symbols.splitlines() if line.split() and line.split()[-1]==label];require(len(matches)==1,'Actual literal object symbol absent')
  sym=matches[0];sections={m[1]:m[2] for m in re.finditer(r'(?m)^\s*\[\s*(\d+)\]\s+(\S+)\s+',section_text)};name=sections[sym[6]];changed=dict(raw);bytes_=bytearray(raw[name]);bytes_[int(sym[1],16)]^=1;changed[name]=bytes(bytes_)
  reject('changed_actual_object_length',lambda:validate_object(section_text,symbols,relocations,changed,tables,str(directory/'program.o')))
 # Exercise the complete real backend object gate as well as the leaf
 # literal checker. This caught the originally omitted 48-byte admission
 # and the genuine seven new bounded selection switches.
 import audit_kernel as audit
 from arithmetic_string_identity import NOTEBOOK_JUMPS,notebook_jump_spec,canonical
 names={canonical(row['source']):row for row in unit['functions']}
 dispatch=[]
 for source in NOTEBOOK_JUMPS:
  require(source in names,'Actual String Notebook dispatch owner missing')
  row=names[source];spec=notebook_jump_spec(ir,unit,source,row['symbol']);dispatch.append({'source':source,'count':spec[1],'cases':spec[4]})
  body=audit._ir_definition_body(ir,row['symbol']);cases=spec[4]
  anchor='i64 '+str(cases[0])+', label';require(anchor in body,'Actual switch mutation anchor absent')
  changed=ir.replace(body,body.replace(anchor,'i64 '+str(cases[0]-1)+', label',1),1)
  reject('changed_dispatch_body:'+source,lambda changed=changed,source=source,row=row:notebook_jump_spec(changed,unit,source,row['symbol']))
 first=names['Lemma.Applications.Notebook.pollArithmetic']
 for name,key,value in [('dispatch_role','role','kernel'),('dispatch_profile','contract_version','core0-user-v0.1'),('dispatch_image','image_key','arithmetic'),('dispatch_configuration','configuration','service-normal')]:
  altered=copy.deepcopy(unit);altered[key]=value
  reject(name,lambda altered=altered:notebook_jump_spec(ir,altered,'Lemma.Applications.Notebook.pollArithmetic',first['symbol']))
 inspection_logs=[];inspect=audit._artifact_inspector(Path(__file__).resolve().parents[1],directory,300,inspection_logs)
 backend=audit.inspect_backend_jump_tables(inspect,directory,object_file='program.o',section_text=section_text,symbol_text=symbols,relocation_text=relocations,unit=unit,optimization='O2',readonly_tables=obj['readonly_tables'])
 require({canonical(row['source']) for row in backend['jump_tables']} >= set(NOTEBOOK_JUMPS),'Actual String dispatch machine tables absent')
 result={'status':'PASS','dispatch_owners':dispatch,'backend_object':backend,'scope':'Actual genuine Document7 owner, exact unsigned version2..7 scalar fetch extent, independent literal and complete object byte accounting; not guest recovery execution','inputs':{n:sha256(directory/n) for n in ('unit.json','program.opt.ll','program.o')},'baseline':baseline,'object':obj,'rejected_actual_mutations':rejected};write_json(output,result);print('STRING_RECORD_LENGTH:PASS',len(rejected),'actual owner/object mutations')
def main():
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();require(not a.output.exists(),'Output exists');check(a.directory,a.output)
if __name__=='__main__':
 try:main()
 except (Core0Error,OSError,ValueError,subprocess.SubprocessError) as e:print('STRING_RECORD_LENGTH:FAIL',e,file=sys.stderr);raise SystemExit(1)
