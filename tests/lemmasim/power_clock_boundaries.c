/* SPDX-License-Identifier: Apache-2.0 */
#include "lemma_power_clock.h"
#include <assert.h>
#include <string.h>
int main(void)
{
 LemmaPowerClock p={0};lemma_power_clock_reset(&p,1,0,0);
 assert(lemma_power_clock_validate(&p,0));
 assert(lemma_power_clock_enqueue(&p,1,96,8,8));
 assert(!lemma_power_clock_enqueue(&p,1,104,8,1));
 assert(!lemma_power_clock_advance(&p,1,false));
 assert(lemma_power_clock_enqueue(&p,2,104,8,1));
 assert(!lemma_power_clock_advance(&p,2,false)&&p.circuit.remaining==8);
 assert(lemma_power_clock_next(&p)==10);
 assert(!lemma_power_clock_advance(&p,9,false)&&p.circuit.remaining==1);
 assert(lemma_power_clock_enqueue(&p,10,104,8,2));
 assert(!lemma_power_clock_advance(&p,10,false)&&p.circuit.remaining==8);
 assert(lemma_power_clock_advance(&p,1000000000,false)==1&&p.edge==18);
 assert(p.circuit.reset_remaining==8&&p.circuit.legacy.reset_cause==4);
 LemmaPowerClock saved=p;
 assert(!lemma_power_clock_advance(&p,25,false)&&p.circuit.reset_remaining==1);
 assert(lemma_power_clock_advance(&p,26,false)==4);
 assert(lemma_power_clock_advance(&saved,26,false)==4&&!memcmp(&p,&saved,sizeof(p)));
 p.raw_good=false;assert(lemma_power_clock_advance(&p,27,false)==2&&p.circuit.reset_epoch==2);
 assert(!lemma_power_clock_advance(&p,1000000000,false)&&p.circuit.reset_remaining==8);
 p.raw_good=true;assert(lemma_power_clock_advance(&p,1000000008,false)==4);
 assert(lemma_power_clock_validate(&p,1000000008));
 p.raw_button=1;assert(lemma_power_clock_next(&p)==p.edge+1);
 assert(!lemma_power_clock_advance(&p,p.edge+1,false));
 assert(p.circuit.legacy.button_level==1&&p.circuit.legacy.epoch==1);
 LemmaPowerClock saturated={0};lemma_power_clock_reset(&saturated,2,0,0);
 saturated.circuit.reset_epoch=UINT64_MAX;saturated.circuit.timeout=8;
 saturated.circuit.armed=true;saturated.circuit.remaining=1;
 assert(lemma_power_clock_advance(&saturated,1,false)==1);
 assert(saturated.circuit.reset_epoch==UINT64_MAX&&saturated.circuit.legacy.reset_cause==4);
 p.write_pending=true;p.write_edge=p.edge;
 assert(!lemma_power_clock_validate(&p,p.edge));
 return 0;
}
