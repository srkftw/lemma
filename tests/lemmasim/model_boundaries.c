/* Independently specified literal hardware traces, host-only GPL-2.0-or-later. */
#include "lemma_model.h"
#include <assert.h>
#include <stdio.h>
static void write8(LemmaPaper *p,unsigned a,uint64_t v) {lemma_paper_write(p,a,v,8,100);}
static void tile(LemmaPaper *p,uint64_t color) {
    write8(p,LEMMA_PAPER_TILE_X,0);write8(p,LEMMA_PAPER_TILE_Y,0);
    write8(p,LEMMA_PAPER_TILE_W,2);write8(p,LEMMA_PAPER_TILE_H,1);
    write8(p,LEMMA_PAPER_TILE_LEN,1);lemma_paper_write(p,LEMMA_PAPER_APERTURE,color,1,100);
    write8(p,LEMMA_PAPER_COMMAND,1);
}
static void refresh(LemmaPaper *p,uint64_t seq) {
    write8(p,LEMMA_PAPER_RECT_X,0);write8(p,LEMMA_PAPER_RECT_Y,0);
    write8(p,LEMMA_PAPER_RECT_W,2);write8(p,LEMMA_PAPER_RECT_H,1);
    write8(p,LEMMA_PAPER_MODE,1);write8(p,LEMMA_PAPER_SEQUENCE,seq);
    write8(p,LEMMA_PAPER_COMMAND,2);
}
int main(void) {
    LemmaPaper p;LemmaPen n;LemmaSample s={.x=100,.y=200,.pressure=2048,.flags=3,.tool=1};
    assert(lemma_paper_init(&p,1650,2200));assert(p.stride==825);
    assert(p.visible[0]==255);tile(&p,0x37);assert(p.target[0]==0x37 && p.visible[0]==255);
    refresh(&p,1);assert(p.status==1 && p.deadline_ns==2000100);
    tile(&p,0xff);assert(p.target[0]==255 && p.visible[0]==255);
    refresh(&p,2);assert(p.error==4 && p.last_sequence==1);
    lemma_paper_advance(&p,2000099);assert(p.visible[0]==255 && p.status&1);
    lemma_paper_advance(&p,2000100);assert(p.visible[0]==0 && p.completed==1);
    assert(lemma_paper_irq(&p));write8(&p,LEMMA_PAPER_ACK,1);assert(!lemma_paper_irq(&p));
    refresh(&p,2);assert(p.status&1);lemma_paper_reset(&p);
    assert(p.visible[0]==0 && p.target[0]==255 && p.status==8 && p.deadline_ns==0);
    assert(lemma_paper_read(&p,LEMMA_PAPER_SEQUENCE,8)==2);
    lemma_paper_advance(&p,99999999);assert(p.visible[0]==0);
    write8(&p,LEMMA_PAPER_RECT_W,0);write8(&p,LEMMA_PAPER_COMMAND,2);assert(p.error==3);
    lemma_paper_destroy(&p);
    assert(lemma_paper_init(&p,1404,1872));assert(p.stride==702);lemma_paper_destroy(&p);
    /* Quality preserves literal Gray4; only a full quality refresh clears
     * the interrupted-region condition after reset. */
    assert(lemma_paper_init(&p,32,32));tile(&p,0x37);
    refresh(&p,1);lemma_paper_reset(&p);assert(p.status==8);
    tile(&p,0x37);write8(&p,LEMMA_PAPER_RECT_W,32);write8(&p,LEMMA_PAPER_RECT_H,32);
    write8(&p,LEMMA_PAPER_MODE,2);write8(&p,LEMMA_PAPER_SEQUENCE,2);write8(&p,LEMMA_PAPER_COMMAND,2);
    assert(p.deadline_ns==25000100 && p.status==9);
    lemma_paper_advance(&p,25000099);assert(p.visible[0]==255);
    lemma_paper_advance(&p,25000100);assert(p.visible[0]==0x37 && p.status==2);
    lemma_paper_destroy(&p);
    lemma_pen_init(&n,65535,65535,4095);assert(!lemma_pen_irq(&n));
    assert(lemma_pen_push(&n,&s));assert(lemma_pen_read(&n,LEMMA_PEN_HEAD_SEQ)==1);
    s.x=101;assert(lemma_pen_push(&n,&s));assert(lemma_pen_read(&n,LEMMA_PEN_HEAD_X)==100);
    lemma_pen_write(&n,LEMMA_PEN_ACK,2);assert(n.count==2 && n.error==2);
    lemma_pen_write(&n,LEMMA_PEN_ACK,1);assert(lemma_pen_read(&n,LEMMA_PEN_HEAD_X)==101);
    for(unsigned i=1;i<256;i++)assert(lemma_pen_push(&n,&s));
    assert(n.count==256);assert(!lemma_pen_push(&n,&s));assert(n.count==1 && n.epoch==2 && n.lost==1);
    assert(lemma_pen_read(&n,LEMMA_PEN_HEAD_SEQ)==2 && lemma_pen_read(&n,LEMMA_PEN_HEAD_X)==101);
    assert(lemma_pen_irq(&n));assert(!lemma_pen_push(&n,&s));
    lemma_pen_write(&n,LEMMA_PEN_LOSS_ACK,1);assert(n.loss);
    lemma_pen_write(&n,LEMMA_PEN_LOSS_ACK,2);assert(!n.loss && n.resync);
    assert(!lemma_pen_push(&n,&s));s.flags=2;assert(!lemma_pen_push(&n,&s));
    s.flags=3;assert(lemma_pen_push(&n,&s));assert(n.count==1 && !n.resync);
    s.flags=8;assert(!lemma_pen_push(&n,&s));assert(n.count==1 && n.epoch==3 && n.loss);
    lemma_pen_init(&n,65535,65535,4095);s.flags=3;s.time=100;
    assert(lemma_pen_push(&n,&s));lemma_pen_advance(&n,10000099);assert(!n.loss);
    lemma_pen_advance(&n,10000100);assert(n.loss && n.count==1 && n.epoch==2);
    puts("literal pen/paper boundary traces observed");return 0;
}
