#!/usr/bin/env python3
"""Focused exact course boot/reset and startup-owner observer qualification.

Inputs are real genuine compiled artifact files. Mutations change the observer
inputs only; they do not substitute for target execution or compiler proof.
"""
import argparse,copy,json,re
from pathlib import Path
from core0_common import Core0Error,sha256,write_json
from audit_kernel import validate_kernel_uart_initialize,validate_user_abi_data,_ir_definition_body

def check(build):
 u=json.loads((build/'kernel/unit.json').read_text());ir=(build/'kernel/program.ll').read_text()
 normalized=lambda n:re.sub(r'^_private\..*?\.[0-9]+\.','',n)
 names={normalized(r['source']):r['symbol'] for r in u['functions']}
 init=names['Lemma.Platform.LemmaVM.ConsoleDevice.initialize14'];boot=names['Lemma.Platform.LemmaSim.NotebookKernel.bootCourseSelected']
 body=_ir_definition_body(ir,boot);calls=re.findall(r'call[^\n]*?@([^ (]+)\(',body)
 if not calls or calls[0]!=init or calls.count(init)!=1 or len(re.findall(r'call[^\n]*?@'+re.escape(init)+r'\(',ir))!=1:raise Core0Error('independent first/sole reset observation differs')
 validate_kernel_uart_initialize(ir,u,optimized=False)
 bad=copy.deepcopy(u);bad['functions']=[r for r in bad['functions'] if normalized(r['source'])!='Lemma.Platform.LemmaSim.NotebookKernel.bootCourseSelected']
 tests={'missing-selected-boot':(ir,bad)}
 bad=copy.deepcopy(u);bad['functions']=[r for r in bad['functions'] if r['symbol']!=init];tests['missing-reset-source']=(ir,bad)
 line=next(l for l in body.splitlines() if re.search(r'call.*@'+re.escape(init)+r'\(',l))
 tests['duplicate-reset']=(ir.replace(line,line+'\n  %course.duplicate.reset = call { i64, i64 } @'+init+'()',1),u)
 tests['first-effect-not-reset']=(ir.replace(line,line.replace('@'+init+'()', '@'+names['Lemma.Kernel.BootInfo.validate']+'()'),1),u)
 rejected={}
 for name,(changed,unit) in tests.items():
  try:validate_kernel_uart_initialize(changed,unit,optimized=False)
  except Core0Error as e:rejected[name]=str(e)
  else:raise Core0Error('accepted independent FIFO mutation:'+name)
 d=build/'users/course';section=(d/'audit-startup.o-sections.txt').read_text();symbols=(d/'audit-startup.o-symbols.txt').read_text();data=(d/'audit-abi-object.bin').read_bytes();assembly=(d/'startup.S').read_text()
 validate_user_abi_data(section,data,symbols,assembly,object_file='users/course/startup.o',configuration=u['configuration'])
 for name,content,config,owner in [('wrong-course-deployment',data,'lemmasim-silicon-array-bulk-notebook','users/course/startup.o'),
  ('wrong-image-owner',data,u['configuration'],'users/other/startup.o'),('changed-ABI-bytes',data[:-1]+bytes([data[-1]^1]),u['configuration'],'users/course/startup.o')]:
  try:validate_user_abi_data(section,content,symbols,assembly,object_file=owner,configuration=config)
  except Core0Error as e:rejected[name]=str(e)
  else:raise Core0Error('accepted independent startup-owner mutation:'+name)
 return {'status':'PASS_FOCUSED_COURSE_BOOT_OBSERVERS','build':str(build),'unit_sha256':sha256(build/'kernel/unit.json'),
  'pre_llvm_sha256':sha256(build/'kernel/program.ll'),'sole_first_reset':init,'negative_rejections':rejected,
  'observer_sha256':sha256(Path(__file__).with_name('audit_kernel.py')),'checker_sha256':sha256(Path(__file__)),
  'scope':'genuine original LLVM/object observer mutations; CPU/durability NOT_RUN'}

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():p.error('refuse retained result')
 result=check(a.build.resolve());write_json(a.output,result);print(result['status'])
if __name__=='__main__':main()
