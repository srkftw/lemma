/* Independent literal virtual-panel program observations. Host hardware only. */
#include "lemma_model.h"
#include <assert.h>
static void put(LemmaPaper *p,unsigned reg,uint64_t value,uint64_t now) {lemma_paper_write(p,reg,value,8,now);}
static void upload(LemmaPaper *p,uint8_t pixels,uint64_t now) {
    lemma_paper_write(p,LEMMA_PAPER_APERTURE,pixels,1,now);
    put(p,LEMMA_PAPER_TILE_X,0,now);put(p,LEMMA_PAPER_TILE_Y,0,now);
    put(p,LEMMA_PAPER_TILE_W,2,now);put(p,LEMMA_PAPER_TILE_H,1,now);put(p,LEMMA_PAPER_TILE_LEN,1,now);
    put(p,LEMMA_PAPER_COMMAND,1,now);
}
static void refresh(LemmaPaper *p,uint64_t sequence,uint64_t now) {
    put(p,LEMMA_PAPER_RECT_X,0,now);put(p,LEMMA_PAPER_RECT_Y,0,now);
    put(p,LEMMA_PAPER_RECT_W,2,now);put(p,LEMMA_PAPER_RECT_H,1,now);
    put(p,LEMMA_PAPER_MODE,2,now);put(p,LEMMA_PAPER_SEQUENCE,sequence,now);put(p,LEMMA_PAPER_COMMAND,2,now);
}
int main(void) {
    LemmaPaper p;assert(lemma_paper_init(&p,32,32));
    p.sequencer_enabled=true;p.sequencer_clock_ns=10;
    upload(&p,0x2a,100);refresh(&p,1,100);
    uint64_t start=25000100;
    assert(p.sequencer_start_ns==start && p.deadline_ns==start+290);
    assert(p.visible[0]==255 && p.status==1);
    lemma_paper_advance(&p,start-1);assert(!p.panel_power);
    lemma_paper_advance(&p,start);assert(p.panel_power && p.drive_remaining==0);
    lemma_paper_advance(&p,start+30);assert(p.wave_phase==0 && p.drive_remaining==2 && p.drive_code==3 && p.scan_beats==0 && p.drive_clocks==0);
    lemma_paper_advance(&p,start+40);assert(p.drive_remaining==1 && p.drive_clocks==1);
    lemma_paper_advance(&p,start+80);assert(p.scan_beats==2 && p.drive_clocks==4 && p.drive_x==0 && p.drive_y==0 && p.drive_remaining==0);
    upload(&p,255,start+80); /* accepted-update pixels remain immutable */
    lemma_paper_advance(&p,start+100);assert(p.wave_phase==1 && p.drive_remaining==2 && p.drive_code==1 && p.scan_beats==2 && p.drive_clocks==4);
    lemma_paper_advance(&p,start+130);assert(p.wave_phase==1 && p.drive_code==2 && p.drive_x==1 && p.drive_y==0);
    lemma_paper_advance(&p,start+170);assert(p.wave_phase==2 && p.drive_code==0 && p.drive_remaining==2);
    lemma_paper_advance(&p,start+230);assert(p.scan_beats==6 && p.drive_clocks==12 && p.visible[0]==255 && p.panel_beats==0);
    lemma_paper_advance(&p,start+250);assert(p.visible[0]==255 && p.panel_beats==1 && p.status==1);
    lemma_paper_advance(&p,start+270);assert(p.visible[0]==255 && p.panel_beats==2 && p.panel_power && p.status==1 && p.drive_x==0 && p.drive_y==0);
    lemma_paper_advance(&p,start+290);assert(p.visible[0]==0x2a && !p.panel_power && p.status==2 && p.completed==1 && lemma_paper_irq(&p));
    assert(lemma_paper_read(&p,384,8)==1 && lemma_paper_read(&p,392,8)==0x31504d53 && lemma_paper_read(&p,432,8)==12);
    put(&p,LEMMA_PAPER_ACK,1,start+290);assert(p.status==0);
    refresh(&p,2,start+300);lemma_paper_advance(&p,p.sequencer_start_ns+250);
    assert(p.panel_beats==1 && p.visible[0]==0x2a);
    put(&p,LEMMA_PAPER_RESET,1,p.sequencer_start_ns+250);
    assert(p.status==8 && p.error==6 && !p.panel_power && p.drive_remaining==0 && p.panel_beats==0 && p.visible[0]==0x2a);
    lemma_paper_advance(&p,UINT64_MAX);assert(p.status==8 && p.completed==1);
    lemma_paper_destroy(&p);return 0;
}
