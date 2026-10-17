#include "lemma_power_safety.h"
#include <assert.h>
int main(void)
{
 LemmaPowerSafety p={0};lemma_power_safety_reset(&p,1,0);
 assert(lemma_power_safety_read(&p,8)==2);
 assert(!lemma_power_safety_access(96,8,true,7)&&!lemma_power_safety_access(97,8,true,8));
 lemma_power_safety_tick(&p,1,0,0,1,1,96,8,8,0);
 lemma_power_safety_tick(&p,1,0,0,1,1,104,8,1,0);
 for(int i=0;i<7;i++)lemma_power_safety_tick(&p,1,0,0,0,0,0,8,0,0);
 assert(p.remaining==1&&!lemma_power_safety_domain_reset(&p));
 lemma_power_safety_tick(&p,1,0,0,1,1,104,8,2,0);assert(p.remaining==8&&p.armed);
 for(int i=0;i<8;i++)lemma_power_safety_tick(&p,1,0,0,0,0,0,8,0,0);
 assert(p.legacy.reset_cause==4&&p.reset_remaining==8&&p.reset_epoch==1&&!p.power_loss);
 for(int i=0;i<8;i++)lemma_power_safety_tick(&p,1,0,0,0,0,0,8,0,0);
 assert(!lemma_power_safety_domain_reset(&p));
 lemma_power_safety_tick(&p,0,1,1,1,1,104,8,1,0);
 assert(p.power_loss&&p.legacy.reset_cause==5&&p.reset_epoch==2&&!p.armed);
 for(int i=0;i<20;i++)lemma_power_safety_tick(&p,0,1,1,0,0,0,8,0,0);
 assert(!p.power_loss&&p.reset_remaining==8&&p.reset_epoch==2&&p.legacy.epoch==0);
 for(int i=0;i<8;i++)lemma_power_safety_tick(&p,1,0,1,0,0,0,8,0,0);
 assert(!lemma_power_safety_domain_reset(&p)&&p.legacy.epoch==0);
 lemma_power_safety_tick(&p,1,0,0,0,0,0,8,0,0);
 lemma_power_safety_tick(&p,1,0,1,0,0,0,8,0,0);assert(p.legacy.epoch==1&&p.legacy.events==1);
 lemma_power_safety_reset(&p,2,1);assert(p.reset_epoch==2&&p.legacy.epoch==1);
 return 0;
}
