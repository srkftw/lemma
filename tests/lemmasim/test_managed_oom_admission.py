"""Routing-observer negatives, never target compiler or execution evidence.

Actual OOM acceptance separately requires genuinely compiled User2 artifacts,
their strict image audit and real request/allocation/pen/cold observations.
"""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from check_arithmetic_isolation import MANAGED_OOM_CONFIGURATION,managed_oom_route

def fixture():
    server='Lemma.Services.Arithmetic.Server.';arena='Lemma.User.Runtime.Arena.'
    records='Lemma.User.Runtime.ManagedRecords.';submission='Lemma.Mathematics.ManagedSubmission.'
    fraction='Lemma.Mathematics.ManagedRational.'
    generated=fraction+'compareFiveSix.__lemma_managed_v02.'
    sources=[server+'main',server+'step',server+'process',server+'pressureStep',
      submission+'check',submission+'positiveRational',generated+fraction+'compareFiveSix',
      generated+fraction+'make',records+'allocate',arena+'newBytes',arena+'newBox',
      arena+'allocate',arena+'exhausted',arena+'capacity']
    names={source:'route_'+str(i) for i,source in enumerate(sources)}
    def call(source,args=''):
        return '  call { i64, i64 } @'+names[source]+'('+args+')\n'
    bodies={s:'' for s in sources}
    bodies[server+'main']=('  icmp eq i64 %arg0, 1\n'+call(server+'step')+
      call(server+'pressureStep','i32 signext 0, i32 signext 31, i64 0'))
    bodies[server+'step']=call(server+'process')
    bodies[server+'process']=call(submission+'check')
    bodies[server+'pressureStep']=call(arena+'newBox')
    bodies[submission+'check']='  icmp eq i64 %arg0, 1\n'+call(submission+'positiveRational')
    bodies[submission+'positiveRational']='  icmp ult i64 %arg2, 8\n'+call(generated+fraction+'compareFiveSix','i64 %arg0, i64 %arg1')
    bodies[generated+fraction+'compareFiveSix']=call(generated+fraction+'make')
    bodies[generated+fraction+'make']=call(records+'allocate','i64 1, i64 24')
    bodies[records+'allocate']=call(arena+'newBytes','i64 %arg1')
    bodies[arena+'newBytes']=call(arena+'allocate');bodies[arena+'newBox']=call(arena+'allocate')
    bodies[arena+'allocate']=call(arena+'exhausted')
    bodies[arena+'exhausted']='  ret i8 237\n';bodies[arena+'capacity']='  ret i64 31\n'
    ir=''.join('define i64 @'+names[s]+'() {\nentry:\n'+bodies[s]+'}\n' for s in sources)
    unit={'configuration':MANAGED_OOM_CONFIGURATION,'contract_version':'core0-user-v0.2',
      'role':'user','image_key':'arithmetic','functions':[{'source':s,'symbol':names[s]} for s in sources]}
    return unit,ir,names

class ManagedOOMAdmission(unittest.TestCase):
    def test_constructor_and_pressure_share_actual_allocator_route(self):
        unit,ir,_=fixture();result=managed_oom_route(unit,ir)
        self.assertEqual((result['shape'],result['bytes'],result['arena_capacity'],result['actual_failure_code']),(1,24,31,237))

    def test_scalar_or_other_deployment_cannot_acquire_managed_oom_claim(self):
        unit,ir,_=fixture()
        for key,value in [('contract_version','core0-user-v0.1'),('role','kernel'),
          ('image_key','notebook'),('configuration','lemmasim-silicon-power-notebook')]:
            changed=copy.deepcopy(unit);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):managed_oom_route(changed,ir)

    def test_broken_constructor_or_shared_pressure_route_is_rejected(self):
        unit,ir,names=fixture()
        for before,after in [('i64 1, i64 24','i64 1, i64 8'),('ret i8 237','ret i8 0'),
          ('ret i64 31','ret i64 32'),('i32 signext 31','i32 signext 30'),
          ('icmp ult i64 %arg2, 8','icmp ult i64 %arg2, 0'),
          ('@'+names['Lemma.User.Runtime.Arena.newBytes']+'(i64 %arg1)',
           '@'+names['Lemma.User.Runtime.Arena.newBox']+'(i64 %arg1)')]:
            with self.subTest(before=before),self.assertRaises(ValueError):
                managed_oom_route(unit,ir.replace(before,after))

if __name__=='__main__':unittest.main()
