/* Independent Power-v1 register/edge expectations. Host only. */
#include "lemma_model.h"
#include <assert.h>
#include <stdint.h>
int main(void)
{
    LemmaPower p;lemma_power_init(&p);
    assert(lemma_power_read(&p,0)==UINT64_C(0x4c505752));
    assert(lemma_power_read(&p,8)==1 && lemma_power_read(&p,16)==0);
    assert(lemma_power_read(&p,32)==1 && !lemma_power_irq(&p));
    lemma_power_button(&p,1);
    assert(p.button_level==1 && p.epoch==1 && p.events==1 && p.state==0);
    lemma_power_button(&p,1);assert(p.epoch==1);
    assert(!lemma_power_write(&p,72,1,true));
    assert(p.state==0 && p.error==1 && p.events==1);
    lemma_power_write(&p,80,1,false);assert(!lemma_power_irq(&p));
    assert(lemma_power_write(&p,72,1,false));assert(p.state==1 && p.error==0);
    assert(!lemma_power_write(&p,72,1,false));assert(p.error==1 && p.state==1);
    lemma_power_write(&p,88,1,false);
    lemma_power_button(&p,0);assert(p.state==1 && p.epoch==1);
    lemma_power_button(&p,1);
    assert(p.state==0 && p.epoch==2 && p.events==2 && p.wake_cause==1);
    lemma_power_write(&p,80,4,false);assert(p.events==2 && p.error==2);
    lemma_power_write(&p,80,2,false);assert(p.events==0 && !lemma_power_irq(&p));
    lemma_power_warm_reset(&p);
    assert(p.reset_cause==2 && p.epoch==2 && p.button_level==1);
    assert(p.state==0 && p.error==0 && p.events==0 && p.wake_cause==0);
    lemma_power_init(&p);
    assert(p.reset_cause==1 && p.epoch==0 && p.button_level==0);
    p.epoch=UINT64_MAX;p.state=1;
    lemma_power_button(&p,1);
    assert(p.epoch==UINT64_MAX && p.error==2 && p.state==0 && p.events==2 && p.wake_cause==1);
    lemma_power_write(&p,72,1,false);assert(p.state==1 && p.error==0 && p.wake_cause==0);
    lemma_power_write(&p,72,1,false);assert(p.state==1 && p.error==1);
    lemma_power_write(&p,72,2,false);assert(p.state==0 && p.wake_cause==2 && p.events==2 && p.error==0);
    lemma_power_write(&p,88,2,false);assert(p.error==2);
    lemma_power_write(&p,72,2,false);assert(p.state==0 && p.error==0 && p.events==2 && p.wake_cause==2);
    lemma_power_button(&p,3);assert(p.error==2 && p.button_level==1);
    lemma_power_write(&p,16,1,false);assert(p.state==0 && p.error==2);
    return 0;
}
