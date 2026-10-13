/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "lemma_power_clock.h"
#include <string.h>
void lemma_power_clock_reset(LemmaPowerClock *p,uint64_t cause,uint64_t button,uint64_t edge)
{
    uint64_t epoch=p->circuit.legacy.epoch,resets=p->circuit.reset_epoch;
    memset(p,0,sizeof(*p));p->circuit.legacy.epoch=epoch;p->circuit.reset_epoch=resets;
    lemma_power_safety_reset(&p->circuit,cause,button);
    p->edge=edge;p->raw_good=true;p->raw_button=button;
}
bool lemma_power_clock_enqueue(LemmaPowerClock *p,uint64_t edge,uint32_t a,unsigned size,uint64_t value)
{
    if(p->write_pending||edge<=p->edge||!lemma_power_safety_access(a,size,true,value))return false;
    p->write_pending=true;p->write_edge=edge;p->write_addr=a;p->write_size=size;p->write_value=value;return true;
}
uint64_t lemma_power_clock_next(const LemmaPowerClock *p)
{
    uint64_t delta=UINT64_MAX;
    if(p->write_pending)delta=p->write_edge-p->edge;
    if(p->raw_button!=p->circuit.legacy.button_level)delta=1;
    if(!p->raw_good||p->raw_brownout){if(p->circuit.last_safe)delta=1;}
    else if(p->circuit.reset_remaining){if(p->circuit.reset_remaining<delta)delta=p->circuit.reset_remaining;}
    else if(p->circuit.armed&&p->circuit.remaining<delta)delta=p->circuit.remaining;
    if(delta==UINT64_MAX||delta>UINT64_MAX-p->edge)return UINT64_MAX;
    return p->edge+delta;
}
unsigned lemma_power_clock_advance(LemmaPowerClock *p,uint64_t target,bool busy)
{
    if(target<=p->edge)return 0;
    uint64_t next=lemma_power_clock_next(p),end=target<next?target:next;
    uint64_t delta=end-p->edge;
    if(delta>1){
        uint64_t skip=delta-1;
        if(p->raw_good&&!p->raw_brownout){
            if(p->circuit.reset_remaining)p->circuit.reset_remaining-=skip;
            else if(p->circuit.armed)p->circuit.remaining-=skip;
        }
        p->edge+=skip;
    }
    bool held=lemma_power_safety_domain_reset(&p->circuit);
    bool armed=p->circuit.armed;
    bool write=p->write_pending&&p->write_edge==end;
    lemma_power_safety_tick(&p->circuit,p->raw_good,p->raw_brownout,p->raw_button,
        write,write,p->write_addr,p->write_size,p->write_value,busy);
    p->edge=end;if(write)p->write_pending=false;
    if(p->circuit.power_loss)return 2;
    if(armed&&!p->circuit.armed&&p->circuit.reset_remaining==8&&p->circuit.legacy.reset_cause==4)return 1;
    return held&&!lemma_power_safety_domain_reset(&p->circuit)?4:0;
}
bool lemma_power_clock_validate(const LemmaPowerClock *p,uint64_t now_edge)
{
    const LemmaPowerSafety *c=&p->circuit;
    if(p->edge>now_edge||p->raw_button>1||c->remaining>c->timeout||c->reset_remaining>8||
       c->timeout>UINT32_MAX||(c->timeout&&c->timeout<8)||c->legacy.state>1||c->legacy.error>2||
       c->legacy.reset_cause<1||c->legacy.reset_cause>6||c->legacy.button_level>1||c->legacy.events>3||
       c->legacy.wake_cause>2||(c->armed&&!c->remaining)||(!c->armed&&c->remaining)||
       (c->reset_remaining&&c->armed))return false;
    if(p->write_pending&&(p->write_edge<=p->edge||
       !lemma_power_safety_access(p->write_addr,p->write_size,true,p->write_value)))return false;
    return true;
}
