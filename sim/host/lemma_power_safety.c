/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "lemma_power_safety.h"
void lemma_power_safety_reset(LemmaPowerSafety *p,uint64_t cause,uint64_t button)
{
    uint64_t epoch=p->legacy.epoch,reset_epoch=p->reset_epoch;
    lemma_power_init(&p->legacy);
    p->legacy.reset_cause=cause;p->legacy.button_level=button;
    if(cause!=1)p->legacy.epoch=epoch;
    p->timeout=p->remaining=p->reset_remaining=0;p->armed=false;
    p->power_good=true;p->brownout=false;p->last_safe=true;p->power_loss=false;
    p->reset_epoch=cause==1?0:reset_epoch;
}
bool lemma_power_safety_domain_reset(const LemmaPowerSafety *p)
{return p->reset_remaining||!p->power_good||p->brownout;}
bool lemma_power_safety_access(uint32_t a,unsigned size,bool write,uint64_t v)
{
    if(size!=8||(a&7))return false;
    if(write)return (a==72&&(v==1||v==2))||(a==80&&v<=3)||(a==88&&v==1)||
        (a==96&&v>=8&&v<=UINT32_MAX)||(a==104&&v>=1&&v<=3);
    return a<=152;
}
uint64_t lemma_power_safety_read(const LemmaPowerSafety *p,uint32_t a)
{
    switch(a){case 8:return 2;case 96:return p->timeout;case 112:return p->remaining;
    case 120:return p->armed;case 128:return p->power_good|(p->brownout<<1);
    case 136:return lemma_power_safety_domain_reset(p)?1:2;
    case 144:return p->reset_remaining;case 152:return p->reset_epoch;
    default:return lemma_power_read(&p->legacy,a);}
}
static void safety_reset_event(LemmaPowerSafety *p,uint64_t cause)
{
    p->legacy.state=p->legacy.events=p->legacy.wake_cause=p->legacy.error=0;
    p->legacy.reset_cause=cause;p->armed=false;p->remaining=0;p->reset_remaining=8;
    if(p->reset_epoch!=UINT64_MAX)p->reset_epoch++;
}
void lemma_power_safety_tick(LemmaPowerSafety *p,bool good,bool brownout,uint64_t button,
                            bool valid,bool write,uint32_t a,unsigned size,uint64_t v,bool busy)
{
    bool safe=good&&!brownout,old_safe=p->last_safe;
    bool admissible=lemma_power_safety_access(a,size,write,v);
    bool reload=valid&&write&&admissible&&a==104&&p->timeout&&(v==1||(v==2&&p->armed));
    p->power_good=good;p->brownout=brownout;p->last_safe=safe;p->power_loss=false;
    if(!safe){
        if(old_safe){safety_reset_event(p,brownout?5:6);p->power_loss=true;}
        p->legacy.reset_cause=brownout?5:6;p->reset_remaining=8;p->armed=false;p->remaining=0;
        p->legacy.state=p->legacy.events=p->legacy.wake_cause=p->legacy.error=0;
        p->legacy.button_level=button;return;
    }
    if(p->reset_remaining){p->reset_remaining--;p->legacy.button_level=button;return;}
    if(p->armed&&p->remaining==1&&!reload){safety_reset_event(p,4);p->legacy.button_level=button;return;}
    if(p->armed)p->remaining--;
    if(valid){
        if(!admissible)p->legacy.error=2;
        else if(write){
            if(a==96){if(p->armed)p->legacy.error=1;else{p->timeout=v;p->legacy.error=0;}}
            else if(a==104){
                if(v==3){p->armed=false;p->remaining=0;p->legacy.error=0;}
                else if(!p->timeout||(v==2&&!p->armed))p->legacy.error=2;
                else{p->armed=true;p->remaining=p->timeout;p->legacy.error=0;}
            }else lemma_power_write(&p->legacy,a,v,busy);
        }
    }
    lemma_power_button(&p->legacy,button);
}
