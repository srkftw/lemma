"""Exact additive course mount-await deployment; no guest policy implementation."""
CONFIGURATIONS=('lemmasim-silicon-course-await-bulk-notebook',
                'lemmasim-silicon-course-await-bulk-initialize')
SOFTWARE_DEPLOYMENT={'contract_version':'lemma-course-mounted-await-bulk-deployment-v1',
 'silicon_profile':'lemma-silicon-dev/0.3.0',
 'user_profiles':{'store':'core0-user-v0.1','notebook':'core0-user-v0.2',
                  'arithmetic':'core0-user-v0.5','course':'core0-user-v0.1'}}
BOOT_ROOTS=dict(zip(CONFIGURATIONS,('siliconCourseAwaitBoot','siliconCourseAwaitInitializeMedium')))
STORE_ROOT='Lemma.Services.Store.ServerAwait.main'
INSTALLER_ROOT='Lemma.Courses.PackageInstaller.mainAwait'
from package_closure_deployment import (CONFIGURATIONS as PACKAGE_CONFIGURATIONS,
 SOFTWARE_DEPLOYMENT as PACKAGE_SOFTWARE_DEPLOYMENT)
from package_companion_deployment import ALL_CONFIGURATIONS as JOINED_CONFIGURATIONS, SOFTWARE_DEPLOYMENT as JOINED_SOFTWARE_DEPLOYMENT, USER_ROOTS
from reader_deployment import CONFIGURATIONS as READER_CONFIGURATIONS, SOFTWARE_DEPLOYMENT as READER_SOFTWARE_DEPLOYMENT
from product_reader_deployment import ALL_CONFIGURATIONS as PRODUCT_READER_CONFIGURATIONS, SOFTWARE_DEPLOYMENT as PRODUCT_READER_SOFTWARE_DEPLOYMENT
from chooser_reader_deployment import CONFIGURATIONS as CHOOSER_CONFIGURATIONS, SOFTWARE_DEPLOYMENT as CHOOSER_SOFTWARE_DEPLOYMENT
ALL_CONFIGURATIONS=CONFIGURATIONS+PACKAGE_CONFIGURATIONS+JOINED_CONFIGURATIONS+READER_CONFIGURATIONS+PRODUCT_READER_CONFIGURATIONS+CHOOSER_CONFIGURATIONS
def software_deployment_for(configuration):
 if configuration in CHOOSER_CONFIGURATIONS:return CHOOSER_SOFTWARE_DEPLOYMENT
 if configuration in PRODUCT_READER_CONFIGURATIONS:
  from product_reader_deployment import software_deployment_for as product_software
  return product_software(configuration)
 if configuration in READER_CONFIGURATIONS:return READER_SOFTWARE_DEPLOYMENT
 if configuration in JOINED_CONFIGURATIONS:
  from package_companion_deployment import software_deployment_for as package_software
  return package_software(configuration)
 if configuration in CONFIGURATIONS:return SOFTWARE_DEPLOYMENT
 if configuration in PACKAGE_CONFIGURATIONS:return PACKAGE_SOFTWARE_DEPLOYMENT
 raise ValueError('Unknown exact Await software tuple')

def library_source_allowed(role,source,image):
 """Only this exact Store root borrows the old engine/dispatcher library.

 Old main/step/courseMain/courseStep remain executable roots and are excluded.
 Caller and primitive authority still undergo the full ordinary artifact audit.
 """
 return (role=='user' and isinstance(image,dict) and image.get('key')=='store' and
         image.get('module')=='Lemma.Services.Store.ServerAwait' and
         image.get('source')==STORE_ROOT and
         (source=='Lemma.Services.Store.Server' or source.startswith('Lemma.Services.Store.Server.')) and source not in
         ('Lemma.Services.Store.Server.main','Lemma.Services.Store.Server.step',
          'Lemma.Services.Store.Server.courseMain','Lemma.Services.Store.Server.courseStep'))

# One new pure owner reaches a split LLVM backend table: status0 is handled
# separately, 220..231 is dense, and93 uses the fallback path. Full source/IR,
# caller, constants and machine-cell relation are required before this scope
# can supplement ordinary relocation/guard/local-code checks.
RESULT_SOURCE='Lemma.Courses.PackageAwaitProtocol.resultValid'
RESULT_CALLER='Lemma.Courses.PackageAwaitClient.validate'
RESULT_CASES=[0,220,221,222,223,231]
RESULT_CLUSTER=[220,221,222,223,231]
_RESULT_PINS={
 False:{RESULT_SOURCE:'c72c1d876e399344c572c4459c640c243cf947b415dc537b4d63eb04e1ba3a6a',
        RESULT_CALLER:'3c28163b02eb2b3d4f2cf6f7b42fd5443f0e2213ea860bc0092842e54c774d5e'},
 True:{RESULT_SOURCE:'c118049fbf3a4855f765d58232f5e24ed470246c7733906238efd8c5cd542b4d',
       RESULT_CALLER:'408233ea4859c7cdec594f851983a4aef1995fcda5b47b75356436f947170d5b'}}
_RESULT_CONSTANTS={
 'Lemma.Services.Store.Format.maximumSequence':('i64',9223372036854775807),
 'Lemma.Services.Store.Format.unformatted':('i8',221),
 'Lemma.Services.Store.Format.readOnly':('i8',223),
 'Lemma.Services.Store.Protocol.busy':('i8',231),
 'Lemma.Services.Store.Format.malformed':('i8',220),
 'Lemma.Services.Store.Format.unsupported':('i8',222),
 'Lemma.User.IPCABI.timeout':('i8',93)}

def _canonical(source):
 import re
 return re.sub(r'^_private\..*?\.[0-9]+\.','',source)

def _body(ir,symbol):
 import re
 from core0_common import Core0Error
 rows=re.findall(r'(?ms)^define [^\n]*@'+re.escape(symbol)+r'\([^\n]*\)[^\n]*\{\n(.*?)^\}',ir)
 if len(rows)!=1:raise Core0Error('mount-result LLVM owner missing/duplicated: '+symbol)
 return rows[0]

def _normalized(body,names):
 import re
 body=re.sub(r'@([^ (]+)',lambda m:'@'+names.get(m[1],m[1]),body)
 return ' '.join(' '.join(line.split(';',1)[0].strip() for line in body.splitlines()).split())

def validate_mount_reply(ir,unit,*,optimized):
 """Exact owner/caller admission, never a generic pure-function grant."""
 import hashlib,re
 from core0_common import Core0Error
 rows=unit.get('functions',[])
 actual=[r for r in rows if _canonical(r.get('source',''))==RESULT_SOURCE]
 if not actual:return None
 installer=(unit.get('image_key')=='course' and type(unit.get('image_id')) is int and
     unit['image_id']==4 and unit.get('contract_version')=='core0-user-v0.1' and
     unit.get('boot_role')=='course-installer' and
     [{k:r.get(k) for k in ('source','id','args')} for r in unit.get('roots',[])]==
       [{'source':INSTALLER_ROOT,'id':1,'args':['u64']}])
 package_root=USER_ROOTS['notebook'][1] if unit.get('configuration') in JOINED_CONFIGURATIONS else 'Lemma.Applications.Notebook.mainPackageClosureBulk'
 from dirty_batch_notebook_target import numeric_candidate,numeric_contract,numeric_root
 if numeric_candidate(unit):
  numeric_contract(unit)
  package_root=numeric_root(unit)
 package_notebook=(unit.get('configuration') in PACKAGE_CONFIGURATIONS+JOINED_CONFIGURATIONS+READER_CONFIGURATIONS+PRODUCT_READER_CONFIGURATIONS+CHOOSER_CONFIGURATIONS and
     unit.get('image_key')=='notebook' and type(unit.get('image_id')) is int and
     unit['image_id']==2 and unit.get('contract_version')=='core0-user-v0.2' and
     unit.get('boot_role')=='notebook' and
     [{k:r.get(k) for k in ('source','id','args')} for r in unit.get('roots',[])]==
       [{'source':package_root,'id':1,'args':['u64']}])
 if (len(actual)!=1 or unit.get('configuration') not in ALL_CONFIGURATIONS or
     unit.get('role')!='user' or not (installer or package_notebook) or
     type(unit.get('schema_version')) is not int or unit['schema_version']!=2 or
     unit.get('artifact_category')!='development-user-unit' or
     unit.get('used_device_ops')!=[] or
     unit.get('software_deployment')!=software_deployment_for(unit.get('configuration'))):
  raise Core0Error('mount-result owner escapes exact installer/Package notebook authority')
 names={r['symbol']:_canonical(r.get('source','')) for r in rows}
 selected={}
 for source in (RESULT_SOURCE,RESULT_CALLER):
  matches=[r for r in rows if _canonical(r.get('source',''))==source]
  effects=[] if source==RESULT_SOURCE else ['checked-access','virtual-read']
  if len(matches)!=1 or matches[0].get('args')!=['u64']*4 or matches[0].get('effects')!=effects:
   raise Core0Error('mount-result owner/caller signature/effects differ: '+source)
  row=matches[0];body=_normalized(_body(ir,row['symbol']),names)
  if hashlib.sha256(body.encode()).hexdigest()!=_RESULT_PINS[optimized][source]:
   raise Core0Error('mount-result complete source-derived LLVM body differs: '+source)
  selected[source]=row['symbol']
 for source,(kind,value) in _RESULT_CONSTANTS.items():
  matches=[r for r in rows if _canonical(r.get('source',''))==source]
  if len(matches)!=1 or matches[0].get('args')!=[] or matches[0].get('effects')!=[]:
   raise Core0Error('mount-result constant authority differs: '+source)
  if optimized and kind=='i8' and value>=128:value-=256
  if _normalized(_body(ir,matches[0]['symbol']),names)!=f'entry: ret {kind} {value}':
   raise Core0Error('mount-result exact constant differs: '+source)
 removed=set()
 if optimized:
  from surface_word_inline import validate as validate_surface_word_inline, removed_symbols
  if validate_surface_word_inline(ir,unit,optimized=True) is not None:
   removed=removed_symbols(unit)
 callers=[]
 for r in rows:
  if r['symbol'] in removed:continue
  if re.search(r'\bcall[^@\n]*@'+re.escape(selected[RESULT_SOURCE])+r'\(',_body(ir,r['symbol'])):
   callers.append(_canonical(r['source']))
 if callers!=[RESULT_CALLER]:raise Core0Error('mount-result escaped its single exact framing validator')
 return {'contract_version':'lemma-course-mounted-reply-table-v1',
         'source':RESULT_SOURCE,'caller':RESULT_CALLER,'optimized':optimized,
         'llvm_switch_cases':RESULT_CASES,'table_interval':[220,231],
         'table_slots':12,'scope':'source/IR/object observer; no CPU or mounted Ready claim'}

def result_jump_spec(ir,unit,source,symbol):
 if source!=RESULT_SOURCE:return None
 validate_mount_reply(ir,unit,optimized=True)
 rows=[r for r in unit['functions'] if r['source']==RESULT_SOURCE]
 if len(rows)!=1 or rows[0]['symbol']!=symbol:
  from core0_common import Core0Error
  raise Core0Error('mount-result backend owner symbol differs')
 return ('user',12,['u64']*4,[],RESULT_CLUSTER)

def validate_result_split(ir,unit,assembly,symbol,table,targets,code,labels):
 """Bind all12 cells, holes and separate0/93 branches to the exact owner."""
 import re
 from core0_common import Core0Error
 validate_mount_reply(ir,unit,optimized=True)
 body=_body(ir,symbol)
 switches=[sorted(int(v) for v in re.findall(r'i64 (-?\d+), label',block))
           for block in re.findall(r'switch i64 [^\n]+\[([^]]+)\]',body,re.S)]
 if switches!=[RESULT_CASES]:raise Core0Error('mount-result split escaped the exact six LLVM cases')
 normalized=[]
 for operation,arguments in code:
  words=[]
  for argument in arguments:
   if argument in labels:words.append('@'+str(labels[argument]))
   elif argument=='%pcrel_hi('+table+')':words.append('%TABLE')
   elif re.fullmatch(r'%pcrel_lo\(\.Lpcrel_hi\d+\)',argument):
    low=argument[len('%pcrel_lo('):-1]
    if labels.get(low)!=5:raise Core0Error('mount-result split PC-relative low target differs')
    words.append('%LOW5')
   else:words.append(argument)
  normalized.append((operation,words))
 expected=[('bltz',['a2','@12']),('addi',['a2','a0','-220']),('li',['a4','11']),
  ('bltu',['a4','a2','@14']),('slli',['a2','a2','3']),('auipc',['a3','%TABLE']),
  ('addi',['a3','a3','%LOW5']),('add',['a2','a2','a3']),('ld',['a2','0(a2)']),('jr',['a2']),
  ('seqz',['a0','a1']),('ret',[]),('li',['a0','0']),('ret',[]),
  ('bnez',['a0','@20']),('addi',['a1','a1','-1']),('seqz',['a0','a1']),
  ('sgtz',['a1','a3']),('and',['a0','a0','a1']),('ret',[]),
  ('xori',['a0','a0','93']),('or',['a0','a0','a1']),('seqz',['a0','a0']),('ret',[]),
  ('addi',['a1','a1','-2']),('seqz',['a0','a1']),('ret',[]),
  ('addi',['a1','a1','-3']),('seqz',['a0','a1']),('ret',[])]
 if normalized!=expected or [labels.get(t) for t in targets]!=[10,24,10,27,20,20,20,20,20,20,20,10]:
  raise Core0Error('mount-result split machine body/table-cell semantic relation differs')
 return {'status_interval':[220,231],'llvm_cases':RESULT_CASES,
         'table_case_modes':{220:0,221:2,222:0,223:3,231:0},
         'holes':[224,225,226,227,228,229,230],'holes_false':True,
         'separate_success':{'status':0,'mode':1,'sequence_max':9223372036854775807,'generation_min':1,'generation_max':9223372036854775807},
         'separate_timeout':{'status':93,'mode':0},'all30_machine_instructions_bound':True}
