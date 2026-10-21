// SPDX-License-Identifier: Apache-2.0
// OpticalFrame/1: raw digital codes, scheduling, bounded SG DMA and delivery pins.
// No application, image interpretation or analog sensor policy lives here.
module lemma_optical (
 input logic clk,por_reset,reset,
 input logic valid,write,input logic [12:0] addr,input logic [2:0] size,input logic [63:0] wdata,
 output logic [63:0] rdata,output logic ready,error,irq,busy,
 input logic source_valid,input logic [63:0] source_endpoint,source_kind,source_data,source_bytes,source_quality,
 output logic source_ready,
 output logic dma_valid,dma_write,output logic [63:0] dma_addr,dma_wdata,
 output logic [2:0] dma_size,input logic dma_ready,dma_error,input logic [63:0] dma_rdata,
 output logic [63:0] acquisition_tick
);
 localparam logic [63:0] MAX_ID=64'h7ffffffffffffffe,MAX_TICK=64'h0ccccccccccccccc;
 localparam logic [63:0] POOL=64'h82000000,POOL_BYTES=64'h2000000;
 localparam integer IDLE=2,CONFIGURED=3,ARMED=4,RUNNING=5,DRAINING=6,FAULT=7,DISCONNECTED=8;
 localparam integer FREE=0,FILLING=1,READY=2,CANCELLED=3;
 localparam integer FORMAT=2,RANGE=3,STALE=4,STATE=5,BUSY=6,PERMISSION=7,EXPIRED=8,OVERFLOW=9,GAP=10,LINK=11,CALIBRATION=12,EXHAUSTED=14,INHIBITED=15;
 typedef struct packed {
  logic [18:0][63:0] pages;
  logic [63:0] capacity,generation,state;
  logic [31:0][63:0] header;
 } slot_t;
 typedef struct packed {
  logic [63:0] state,fault,epoch,completed,source_sequence,config_revision;
  logic [63:0] width,height,stride,format,gain,exposure,row_ticks,period,calibration;
  logic [63:0] consent,consent_floor,expiry,dropped,accepted,last_sof;
  logic [63:0] received,written,packing,packing_hi,packing_bytes,pixel_low,header_index;
  integer active_slot;
  logic have_sof,eof,discard;
 } endpoint_t;
 slot_t slots[6];endpoint_t ep[3];
 logic [63:0] tick,controller_epoch,pending,mask,inhibit,link,fault,last_reset_epoch;
 logic reset_seen,reset_fenced,exhausted;
 logic [63:0] table_base,table_status,table_index,table_candidate[192];
 logic table_valid,reset_pending;
 logic [63:0] held_kind,held_address,held_data,held_endpoint,held_slot,held_offset;
 logic held_cancel;
 logic [63:0] completed_dma_bytes,turn;
 logic [63:0] lease_endpoint_stage,lease_sequence_stage,lease_status,lease_endpoint,lease_sequence,lease_slot,lease_generation,lease_consent;
 integer i,j,k,e,offset,index;
 logic advertised,accepted;
 logic [63:0] now_tick;

 function automatic integer pages_for(input integer n);return n<2?5:19;endfunction
 function automatic logic identity(input logic [63:0] n);return n!=0&&n<=MAX_ID;endfunction
 function automatic logic register_access(input integer a,input logic writing);
  integer o;
  if(a%8!=0||a>=1024)return 0;
  if(a<256)begin
   if(writing)case(a)
    40,48,56,64,96,104,112,184,192,200:return 1;
    default:return 0;
   endcase
   else case(a)
    48,112,200:return 0;
    default:return 1;
   endcase
  end
  o=a%256;
  if(writing)case(o)
   24,48,56,64,72,80,88,96,104,112,120,128,184:return 1;
   default:return 0;
  endcase
  return o!=184;
 endfunction
 function automatic logic page(input logic [63:0] n);return n[11:0]==0&&n>=POOL&&n<=POOL+POOL_BYTES-4096;endfunction
 function automatic logic permission(input integer n,input logic [63:0] now_value);
  return !exhausted&&table_valid&&table_status==2&&link!=0&&inhibit==0&&ep[n].consent!=0&&ep[n].expiry>now_value&&now_value<=MAX_TICK;
 endfunction
 function automatic logic owner_held(input integer n);return held_kind>=2&&held_slot==64'(n);endfunction
 function automatic logic pinned(input integer n);return lease_status!=0&&lease_slot==64'(n);endfunction
 function automatic integer head(input integer n);
  integer result;result=-1;
  for(integer s=0;s<2;s++)if(slots[n*2+s].state==READY)
   if(result<0)result=n*2+s;else if(slots[n*2+s].header[3]<slots[result].header[3])result=n*2+s;
  return result;
 endfunction
 function automatic logic [63:0] ready_count(input integer n);
  return 64'(slots[n*2].state==READY)+64'(slots[n*2+1].state==READY);
 endfunction
 function automatic logic [63:0] irq_pending();
  logic [63:0] value;value=pending|(fault!=0?64'd8:64'd0);
  for(integer n=0;n<3;n++)if(ep[n].fault!=0||ready_count(n)!=0)value=value|(64'd1<<n);
  return value;
 endfunction
 task automatic quarantine();
  exhausted=1;fault=EXHAUSTED;pending=pending|8;inhibit=1;table_valid=0;table_status=0;
  if(held_kind!=0)held_cancel=1;if(lease_status!=0)lease_status=2;
  for(integer n=0;n<3;n++)begin
   ep[n].consent=0;ep[n].expiry=0;ep[n].state=FAULT;ep[n].fault=EXHAUSTED;
   ep[n].active_slot=-1;ep[n].packing=0;ep[n].packing_hi=0;ep[n].packing_bytes=0;ep[n].pixel_low=0;ep[n].eof=0;
  end
  for(integer n=0;n<6;n++)if(slots[n].state!=FREE)slots[n].state=CANCELLED;
 endtask
 task automatic global_error(input logic [63:0] code);
  if(code==EXHAUSTED)quarantine();fault=exhausted?EXHAUSTED:code;pending=pending|8;
 endtask
 task automatic reject(input integer n,input logic [63:0] code);
  if(code==EXHAUSTED)quarantine();ep[n].fault=exhausted?EXHAUSTED:code;pending=pending|(64'd1<<n);
 endtask
 task automatic retire_slot(input integer n);
  if(owner_held(n)||pinned(n))slots[n].state=CANCELLED;
  else if(slots[n].state!=FREE)begin
   if(slots[n].generation==MAX_ID)begin
    slots[n].state=CANCELLED;ep[n/2].state=FAULT;ep[n/2].consent=0;ep[n/2].expiry=0;reject(n/2,EXHAUSTED);
   end else begin slots[n].generation=slots[n].generation+1;slots[n].state=FREE;end
  end
 endtask
 task automatic fence(input integer n,input logic [63:0] code,status);
  ep[n].consent=0;ep[n].expiry=0;ep[n].state=status;ep[n].discard=0;
  if(held_kind>=2&&held_endpoint==64'(n))held_cancel=1;
  if(lease_status!=0&&lease_endpoint==64'(n))lease_status=2;
  for(integer s=0;s<2;s++)if(slots[n*2+s].state!=FREE)retire_slot(n*2+s);
  ep[n].active_slot=-1;ep[n].packing=0;ep[n].packing_hi=0;ep[n].packing_bytes=0;ep[n].pixel_low=0;ep[n].eof=0;
  if(code!=0)reject(n,code);
 endtask
 function automatic logic endpoint_empty(input integer n);
  return ep[n].active_slot<0&&slots[n*2].state==FREE&&slots[n*2+1].state==FREE&&
   !(held_kind>=2&&held_endpoint==64'(n))&&!(lease_status!=0&&lease_endpoint==64'(n));
 endfunction
 function automatic logic table_idle();
  logic empty;empty=!exhausted&&held_kind==0&&lease_status==0&&!reset_pending;
  for(integer n=0;n<3;n++)if((ep[n].state!=IDLE&&ep[n].state!=CONFIGURED)||!endpoint_empty(n))empty=0;
  return empty;
 endfunction
 task automatic default_config(input integer n);
  ep[n].width=n==2?320:n==0?16:160;ep[n].height=n==2?240:n==0?16:120;
  ep[n].stride=n==2?320:n==0?32:160;ep[n].format=n==0?1:2;
  ep[n].gain=1;ep[n].exposure=8;ep[n].row_ticks=1;
  ep[n].period=n==2?6666667:n==0?1000000:1666667;ep[n].calibration=0;
 endtask
 task automatic initialize();
  tick=0;controller_epoch=1;pending=0;mask=0;inhibit=1;link=1;fault=0;last_reset_epoch=0;reset_seen=0;reset_fenced=0;exhausted=0;
  table_base=0;table_status=0;table_index=0;table_valid=0;reset_pending=0;
  held_kind=0;held_address=0;held_data=0;held_endpoint=0;held_slot=0;held_offset=0;held_cancel=0;
  completed_dma_bytes=0;turn=0;lease_endpoint_stage=0;lease_sequence_stage=0;
  lease_status=0;lease_endpoint=0;lease_sequence=0;lease_slot=0;lease_generation=0;lease_consent=0;
  for(integer s=0;s<6;s++)slots[s]='0;
  for(integer word_index=0;word_index<192;word_index++)table_candidate[word_index]=0;
  for(integer n=0;n<3;n++)begin ep[n]='0;ep[n].state=IDLE;ep[n].epoch=1;ep[n].active_slot=-1;default_config(n);end
 endtask
 task automatic reset_authority();
  logic maximum_epoch,maximum;
  pending=0;mask=0;inhibit=1;fault=0;last_reset_epoch=0;reset_fenced=1;
  table_valid=0;table_status=0;table_index=0;maximum_epoch=controller_epoch==MAX_ID;
  if(!maximum_epoch)begin controller_epoch=controller_epoch+1;last_reset_epoch=controller_epoch;end
  for(integer n=0;n<3;n++)begin
   maximum=ep[n].epoch==MAX_ID;fence(n,0,IDLE);
   if(!maximum)ep[n].epoch=ep[n].epoch+1;
   ep[n].have_sof=0;default_config(n);
   if(maximum||maximum_epoch||ep[n].fault==EXHAUSTED)begin ep[n].state=FAULT;reject(n,EXHAUSTED);end
   else ep[n].fault=0;
  end
  if(maximum_epoch||exhausted)global_error(EXHAUSTED);
  if(held_kind!=0)begin held_cancel=1;reset_pending=1;end
 endtask
 function automatic logic configuration(input integer n);
  logic geometry;logic [63:0] minimum;
  geometry=(n==0&&ep[n].format==1&&ep[n].width==16&&ep[n].height==16&&ep[n].stride==32)||
   (n<2&&ep[n].format==2&&ep[n].width==160&&ep[n].height==120&&ep[n].stride==160)||
   (n==2&&ep[n].format==2&&ep[n].width==320&&ep[n].height==240&&ep[n].stride==320);
  minimum=n==2?6666667:(n==0&&ep[n].format==1)?1000000:1666667;
  return geometry&&ep[n].gain>=1&&ep[n].gain<=64&&ep[n].exposure>=1&&ep[n].exposure<=65535&&
   ep[n].row_ticks>=1&&ep[n].row_ticks<=65535&&ep[n].period>=minimum&&ep[n].period<=64'hffffffff&&
   ep[n].period>=ep[n].exposure+ep[n].height*ep[n].row_ticks&&ep[n].calibration<=1;
 endfunction
 function automatic logic candidate_valid();
  logic good;logic [63:0] seen[58],address;integer used,n;
  good=controller_epoch!=MAX_ID;used=0;
  for(integer s=0;s<6;s++)begin
   n=pages_for(s/2);
   if(table_candidate[s*32]!=64'(n)||table_candidate[s*32+1]!=64'(n)*4096||
      !identity(table_candidate[s*32+2])||table_candidate[s*32+2]<=slots[s].generation||table_candidate[s*32+3]!=0)good=0;
   for(integer p=0;p<19;p++)begin
    address=table_candidate[s*32+4+p];
    if(p>=n)begin if(address!=0)good=0;end
    else begin
     if(!page(address)||address==table_base)good=0;
     for(integer prior=0;prior<58;prior++)if(prior<used&&address==seen[prior])good=0;
     if(used<58)seen[used]=address;used=used+1;
    end
   end
   for(integer word_index=23;word_index<32;word_index++)if(table_candidate[s*32+word_index]!=0)good=0;
  end
  return good&&used==58;
 endfunction
 task automatic publish_table();
  for(integer s=0;s<6;s++)begin
   for(integer p=0;p<19;p++)slots[s].pages[p]=table_candidate[s*32+4+p];
   slots[s].capacity=table_candidate[s*32+1];slots[s].generation=table_candidate[s*32+2];slots[s].state=FREE;
  end
  controller_epoch=controller_epoch+1;table_valid=1;table_status=2;
 endtask
 function automatic logic [63:0] slot_address(input integer n,input logic [63:0] byte_offset);
  return slots[n].pages[byte_offset/4096]+byte_offset%4096;
 endfunction
 task automatic prepare();
  logic chosen;integer n,s;chosen=0;
  if(!exhausted&&held_kind==0&&!reset_pending)begin
   if(table_status==1)begin held_kind=1;held_address=table_base+table_index*8;held_data=0;held_offset=table_index;end
   else for(integer attempt=0;attempt<3;attempt++)begin
    n=int'((turn+64'(attempt))%3);
    if(!chosen&&ep[n].active_slot>=0)begin
     s=ep[n].active_slot;
     if(slots[s].state==FILLING)begin
      if(ep[n].packing_bytes>=8)begin held_kind=2;held_offset=256+ep[n].written;held_data=ep[n].packing;chosen=1;end
      else if(ep[n].eof&&ep[n].written==ep[n].received&&ep[n].packing_bytes==0&&ep[n].header_index<32)begin
       held_kind=3;held_offset=ep[n].header_index*8;held_data=slots[s].header[ep[n].header_index];chosen=1;
      end
      if(chosen)begin held_endpoint=64'(n);held_slot=64'(s);held_cancel=0;held_address=slot_address(s,held_offset);end
     end
    end
   end
  end
 endtask
 task automatic complete();
  logic [63:0] kind;integer n,s;logic cancelled,count_beat;
  kind=held_kind;n=int'(held_endpoint);s=int'(held_slot);cancelled=held_cancel;held_kind=0;held_cancel=0;count_beat=1;
  if(reset_pending)begin reset_pending=0;if(kind>=2)retire_slot(s);end
  else if(exhausted)begin if(kind>=2)retire_slot(s);end
  else if(completed_dma_bytes>64'hfffffffffffffff7)begin
   global_error(EXHAUSTED);for(integer p=0;p<3;p++)fence(p,EXHAUSTED,FAULT);
  end else begin
   if(kind==1)begin
    if(dma_error)begin table_status=3;table_valid=0;global_error(RANGE);count_beat=0;end
    else begin
     table_candidate[table_index]=dma_rdata;table_index=table_index+1;
     if(table_index==192)begin
      if(candidate_valid())publish_table();
      else begin table_status=3;table_valid=0;global_error(RANGE);for(integer p=0;p<3;p++)fence(p,PERMISSION,CONFIGURED);end
     end
    end
   end else if(kind>=2)begin
    turn=64'((n+1)%3);
    if(cancelled||!permission(n,tick))begin
     retire_slot(s);if(ep[n].active_slot==s)fence(n,EXPIRED,CONFIGURED);count_beat=0;
    end else if(dma_error)begin fence(n,RANGE,FAULT);count_beat=0;end
    else if(kind==2)begin ep[n].written=ep[n].written+8;ep[n].packing=ep[n].packing_hi;ep[n].packing_hi=0;ep[n].packing_bytes=ep[n].packing_bytes-8;end
    else begin
     ep[n].header_index=ep[n].header_index+1;
     if(ep[n].header_index==32)begin
      slots[s].state=READY;ep[n].completed=slots[s].header[3];ep[n].active_slot=-1;ep[n].eof=0;
      pending=pending|(64'd1<<n);if(ep[n].state==DRAINING)ep[n].state=CONFIGURED;
     end
    end
   end
   if(count_beat)completed_dma_bytes=completed_dma_bytes+8;
  end
 endtask
 function automatic logic bad_source();
  if(source_quality>65535||source_kind>3)return 1;
  if(source_kind==1)begin
   if(source_bytes<1||source_bytes>8)return 1;
   return source_bytes<8&&(source_data>>(source_bytes*8))!=0;
  end
  if(source_bytes!=0)return 1;
  return source_kind==3?source_data==0:source_data!=0;
 endfunction
 function automatic logic source_can_accept(input logic [63:0] now_value);
  integer n,s;logic [63:0] expected,last_row,deadline,produced;
  if(!source_valid||reset_pending)return 0;
  if(source_endpoint<1||source_endpoint>3)return 1;
  n=int'(source_endpoint)-1;
  if(bad_source()||!permission(n,now_value)||(ep[n].state!=RUNNING&&ep[n].state!=DRAINING))return 1;
  if(source_kind==0||source_kind==3||ep[n].discard)return 1;
  s=ep[n].active_slot;if(s<0||ep[n].eof)return 1;
  expected=ep[n].stride*ep[n].height;
  if(source_kind==1)begin
   if(ep[n].received>expected||source_bytes>expected-ep[n].received)return 1;
   last_row=(ep[n].received+source_bytes-1)/ep[n].stride;
   deadline=slots[s].header[7]+last_row*ep[n].row_ticks;
   produced=ep[n].format==1?2*(((ep[n].received&1)+source_bytes)/2):source_bytes;
   return now_value>=deadline&&ep[n].packing_bytes+produced<=16;
  end
  if(ep[n].received!=expected)return 1;
  deadline=slots[s].header[7]+ep[n].height*ep[n].row_ticks;
  return now_value>=deadline&&ep[n].packing_bytes==0&&ep[n].written==ep[n].received&&!(held_kind>=2&&held_endpoint==64'(n));
 endfunction
 task automatic dropped(input integer n,input logic [63:0] amount,code);
  if(amount>MAX_ID-ep[n].dropped)fence(n,EXHAUSTED,FAULT);
  else begin ep[n].dropped=ep[n].dropped+amount;reject(n,code);end
 endtask
 task automatic source_accept();
  integer n,s,old,unit;logic early;logic [63:0] maximum,value;
  if(source_endpoint<1||source_endpoint>3)global_error(FORMAT);
  else begin
   n=int'(source_endpoint)-1;
   if(bad_source())fence(n,FORMAT,FAULT);
   else if(!permission(n,tick))fence(n,PERMISSION,FAULT);
   else if(ep[n].state!=RUNNING&&ep[n].state!=DRAINING)fence(n,STATE,FAULT);
   else if(source_kind==3)begin
    dropped(n,source_data,GAP);
    if(ep[n].active_slot>=0&&!ep[n].eof)slots[ep[n].active_slot].header[18]=slots[ep[n].active_slot].header[18]|8|source_quality;
   end else if(source_kind==0)begin
    if(ep[n].state!=RUNNING)reject(n,STATE);
    else if(ep[n].source_sequence==MAX_ID)fence(n,EXHAUSTED,FAULT);
    else begin
     ep[n].source_sequence=ep[n].source_sequence+1;
     early=ep[n].have_sof&&(tick<ep[n].last_sof||tick-ep[n].last_sof<ep[n].period);
     ep[n].last_sof=tick;ep[n].have_sof=1;ep[n].discard=0;
     if(ep[n].active_slot>=0)begin
      if(!ep[n].eof)begin
       old=ep[n].active_slot;if(owner_held(old))held_cancel=1;
       retire_slot(old);ep[n].active_slot=-1;ep[n].packing=0;ep[n].packing_hi=0;ep[n].packing_bytes=0;ep[n].pixel_low=0;
      end
      ep[n].discard=1;dropped(n,1,OVERFLOW);
     end else if(early)begin ep[n].discard=1;dropped(n,1,RANGE);end
     else begin
      s=-1;for(integer t=0;t<2;t++)if(s<0&&slots[n*2+t].state==FREE)s=n*2+t;
      if(s<0)begin ep[n].discard=1;dropped(n,1,OVERFLOW);end
      else if(tick>MAX_TICK-ep[n].exposure-ep[n].height*ep[n].row_ticks)fence(n,EXHAUSTED,FAULT);
      else begin
       slots[s].state=FILLING;slots[s].header='0;
       slots[s].header[0]=64'h31304652494e4d4c;slots[s].header[1]=1;slots[s].header[2]=64'(n+1);
       slots[s].header[3]=ep[n].source_sequence;slots[s].header[4]=ep[n].epoch;slots[s].header[5]=ep[n].config_revision;
       slots[s].header[6]=tick;slots[s].header[7]=tick+ep[n].exposure;slots[s].header[9]=ep[n].period;
       slots[s].header[12]=ep[n].width;slots[s].header[13]=ep[n].height;slots[s].header[14]=ep[n].gain;
       slots[s].header[15]=ep[n].exposure;slots[s].header[16]=ep[n].row_ticks;slots[s].header[17]=ep[n].consent;
       slots[s].header[18]=source_quality|(ep[n].calibration!=0?64'd0:64'd16);slots[s].header[19]=ep[n].stride*ep[n].height;
       slots[s].header[20]=32;slots[s].header[21]=100000000;slots[s].header[22]=850;slots[s].header[24]=1;
       slots[s].header[25]=ep[n].calibration;slots[s].header[26]=1;slots[s].header[27]=ep[n].format;
       slots[s].header[28]=n==0?(ep[n].format==1?1:2):64'(n+2);slots[s].header[29]=1;
       ep[n].active_slot=s;ep[n].received=0;ep[n].written=0;ep[n].packing=0;ep[n].packing_hi=0;ep[n].packing_bytes=0;ep[n].pixel_low=0;ep[n].header_index=0;ep[n].eof=0;
      end
     end
    end
   end else if(ep[n].discard)begin if(source_kind==2)ep[n].discard=0;end
   else if(ep[n].active_slot<0||ep[n].eof)fence(n,STATE,FAULT);
   else begin
    s=ep[n].active_slot;slots[s].header[18]=slots[s].header[18]|source_quality;
    if(source_kind==2)begin
     if(ep[n].received!=slots[s].header[19])fence(n,RANGE,FAULT);
     else begin slots[s].header[8]=tick;slots[s].header[23]=ep[n].dropped;ep[n].eof=1;end
    end else if(source_bytes>slots[s].header[19]-ep[n].received)fence(n,RANGE,FAULT);
    else if(ep[n].accepted>64'hffffffffffffffff-source_bytes)fence(n,EXHAUSTED,FAULT);
    else begin
     unit=ep[n].format==1?2:1;maximum=ep[n].format==1?65535:255;
     // Keep complete output bytes across DMA words and a raw low byte across
     // source beats. Gain/clamping occurs only when the whole pixel exists.
     for(integer byte_index=0;byte_index<8;byte_index++)if(64'(byte_index)<source_bytes)begin
      value=(source_data>>(8*byte_index))&255;
      if(unit==2&&((ep[n].received+64'(byte_index))&1)==0)ep[n].pixel_low=value;
      else begin
       if(unit==2)begin value=ep[n].pixel_low|(value<<8);ep[n].pixel_low=0;end
       value=value*ep[n].gain;
       if(value>maximum)begin value=maximum;slots[s].header[18]=slots[s].header[18]|1;end
       for(integer b=0;b<2;b++)if(b<unit)begin
        if(ep[n].packing_bytes<8)ep[n].packing=ep[n].packing|(((value>>(8*b))&255)<<(ep[n].packing_bytes*8));
        else ep[n].packing_hi=ep[n].packing_hi|(((value>>(8*b))&255)<<((ep[n].packing_bytes-8)*8));
        ep[n].packing_bytes=ep[n].packing_bytes+1;
       end
      end
     end
     ep[n].received=ep[n].received+source_bytes;ep[n].accepted=ep[n].accepted+source_bytes;
    end
   end
  end
 endtask
 task automatic consume(input integer n,input logic [63:0] requested_sequence,input logic use_lease);
  integer s;s=head(n);
  if(s<0)reject(n,STALE);
  else if(slots[s].header[3]!=requested_sequence)reject(n,STALE);
  else if(!permission(n,tick)||slots[s].header[17]!=ep[n].consent)reject(n,PERMISSION);
  else if(owner_held(s)||(!use_lease&&pinned(s)))reject(n,BUSY);
  else begin if(use_lease)lease_status=0;retire_slot(s);end
 endtask
 task automatic write_register(input integer a,input logic [63:0] value);
  integer n,o,s;logic cancelled;logic [63:0] expiry;
  if(a%8!=0||a>=1024)global_error(FORMAT);
  else if(reset_pending)global_error(BUSY);
  else if(exhausted&&!((a==200&&value==3)||(a==56&&value==1)||a==48))global_error(EXHAUSTED);
  else if(a<256)case(a)
   40:if((value&~64'd15)!=0)global_error(FORMAT);else mask=value;
   48:if((value&~64'd15)!=0)global_error(FORMAT);else pending=pending&~value;
   56,64:begin
    if(value>1)global_error(FORMAT);
    else begin
     if(a==56)inhibit=value;else link=value;
     if((a==56&&value!=0)||(a==64&&value==0))
      for(integer p=0;p<3;p++)fence(p,a==56?INHIBITED:LINK,a==56?CONFIGURED:DISCONNECTED);
     else if(a==64&&value!=0)for(integer p=0;p<3;p++)if(ep[p].state==DISCONNECTED)ep[p].state=IDLE;
    end
   end
   96:if(!table_idle())global_error(BUSY);else if(!page(value))global_error(RANGE);else table_base=value;
   104:if(!table_idle())global_error(BUSY);else if(value!=1536)global_error(RANGE);
   112:begin
    if(!table_idle())global_error(BUSY);
    else if(value==1)begin
     if(!page(table_base))global_error(RANGE);
     else if(controller_epoch==MAX_ID)global_error(EXHAUSTED);
     else begin reset_fenced=0;table_status=1;table_index=0;table_valid=0;fault=0;prepare();end
    end else if(value==2)begin
     if(controller_epoch==MAX_ID)global_error(EXHAUSTED);
     else begin reset_fenced=0;controller_epoch=controller_epoch+1;table_status=0;table_valid=0;fault=0;for(integer p=0;p<3;p++)fence(p,0,ep[p].state);end
    end else global_error(FORMAT);
   end
   184,192:if(lease_status!=0)global_error(BUSY);else if(a==184)lease_endpoint_stage=value;else lease_sequence_stage=value;
   200:begin
    if(value==1)begin
     if(lease_status!=0)global_error(BUSY);
     else if(lease_endpoint_stage<1||lease_endpoint_stage>3)global_error(RANGE);
     else begin
      n=int'(lease_endpoint_stage)-1;s=head(n);
      if(s<0)reject(n,STALE);
      else if(slots[s].header[3]!=lease_sequence_stage)reject(n,STALE);
      else if(owner_held(s))reject(n,BUSY);
      else if(!permission(n,tick)||slots[s].header[17]!=ep[n].consent)reject(n,PERMISSION);
      else begin
       lease_status=1;lease_endpoint=64'(n);lease_sequence=lease_sequence_stage;lease_slot=64'(s);
       lease_generation=slots[s].generation;lease_consent=ep[n].consent;
      end
     end
    end else if(value==2)begin
     if(lease_status!=1)global_error(STALE);
     else begin
      n=int'(lease_endpoint);
      if(slots[lease_slot].generation!=lease_generation||ep[n].consent!=lease_consent)reject(n,STALE);
      else consume(n,lease_sequence,1);
     end
    end else if(value==3)begin
     if(lease_status==0)global_error(STALE);
     else if(owner_held(int'(lease_slot)))global_error(BUSY);
     else begin cancelled=lease_status==2;lease_status=0;if(cancelled)retire_slot(int'(lease_slot));end
    end else global_error(FORMAT);
   end
   default:global_error(FORMAT);
  endcase
  else begin
   n=a/256-1;o=a%256;
   if((o>=48&&o<=104)||o==128)begin
    if((ep[n].state!=IDLE&&ep[n].state!=CONFIGURED)||!endpoint_empty(n))reject(n,BUSY);
    else case(o)
     48:ep[n].width=value;56:ep[n].height=value;64:ep[n].stride=value;72:ep[n].format=value;
     80:ep[n].gain=value;88:ep[n].exposure=value;96:ep[n].row_ticks=value;104:ep[n].period=value;128:ep[n].calibration=value;
     default:reject(n,FORMAT);
    endcase
   end else if(o==112)begin
    if(value!=0&&(!identity(value)||value<=ep[n].consent_floor))reject(n,STALE);
    else if(value!=0&&(ep[n].expiry<=tick||ep[n].expiry>MAX_TICK))reject(n,EXPIRED);
    else begin
     expiry=ep[n].expiry;fence(n,0,ep[n].state==IDLE?IDLE:CONFIGURED);
     if(value!=0)begin reset_fenced=0;ep[n].consent=value;ep[n].consent_floor=value;ep[n].expiry=expiry;end
    end
   end else if(o==120)begin
    if(value<=tick||value>MAX_TICK)reject(n,RANGE);
    else if((ep[n].state!=IDLE&&ep[n].state!=CONFIGURED)||!endpoint_empty(n))reject(n,BUSY);
    else ep[n].expiry=value;
   end else if(o==184)consume(n,value,0);
   else if(o!=24)reject(n,FORMAT);
   else case(value)
    1:if(ep[n].epoch==MAX_ID)reject(n,EXHAUSTED);else begin
      fence(n,0,IDLE);ep[n].epoch=ep[n].epoch+1;ep[n].completed=0;ep[n].source_sequence=0;ep[n].have_sof=0;default_config(n);ep[n].fault=0;
     end
    2:if((ep[n].state!=IDLE&&ep[n].state!=CONFIGURED)||!endpoint_empty(n))reject(n,BUSY);
      else if(!configuration(n))reject(n,FORMAT);else if(ep[n].config_revision==MAX_ID)reject(n,EXHAUSTED);
      else begin ep[n].config_revision=ep[n].config_revision+1;ep[n].state=CONFIGURED;ep[n].fault=0;end
    3:if(ep[n].state!=CONFIGURED)reject(n,STATE);else if(ep[n].config_revision==0||!configuration(n))reject(n,FORMAT);
      else if(!permission(n,tick))reject(n,PERMISSION);else begin ep[n].state=ARMED;ep[n].fault=0;end
    4:if(ep[n].state!=ARMED)reject(n,STATE);else if(!permission(n,tick))reject(n,PERMISSION);
      else begin ep[n].state=RUNNING;ep[n].fault=0;end
    5:if(ep[n].state!=RUNNING&&ep[n].state!=DRAINING)reject(n,STATE);
      else begin ep[n].state=ep[n].active_slot>=0?DRAINING:CONFIGURED;ep[n].fault=0;end
    6:begin fence(n,0,CONFIGURED);ep[n].fault=0;end
    default:reject(n,FORMAT);
   endcase
  end
 endtask
 function automatic logic [63:0] read_register(input integer a);
  integer n,s;logic [63:0] value;value=0;
  if(a%8!=0||a>=1024)return 0;
  if(a<256)case(a)
   0:value=64'h4c4d4f31;8:value=1;16:value=15;24:value=tick;32:value=irq_pending();40:value=mask;
   56:value=inhibit;64:value=link;72:value=100000000;80:value=controller_epoch;88:value=256;
   96:value=table_base;104:value=1536;120:value=table_status;128:value=fault;
   136:value=held_kind|(64'(held_cancel)<<8);144:value=held_address;152:value=completed_dma_bytes;
   160:value=3;168:value=1;176:value=76800;184:value=lease_endpoint_stage;192:value=lease_sequence_stage;
   208:value=lease_status;216:if(lease_status!=0)value=lease_slot%2;
   224:if(lease_status!=0)value=lease_generation;232:if(lease_status!=0)value=lease_consent;
   240:value=last_reset_epoch;248:value=64'(reset_fenced);
   default:value=0;
  endcase
  else begin
   n=a/256-1;s=head(n);
   case(a%256)
    0:value=64'h4f460000+64'(n+1);8:value=ep[n].state;16:value=ep[n].fault;24:value=ep[n].consent_floor;
    32:value=ep[n].epoch;40:value=ep[n].completed;48:value=ep[n].width;56:value=ep[n].height;
    64:value=ep[n].stride;72:value=ep[n].format;80:value=ep[n].gain;88:value=ep[n].exposure;
    96:value=ep[n].row_ticks;104:value=ep[n].period;112:value=ep[n].consent;120:value=ep[n].expiry;
    128:value=ep[n].calibration;136:if(s>=0)value=slots[s].header[18];144:value=ready_count(n);
    152:if(s>=0)value=64'(s%2);160:if(s>=0)value=slots[s].header[3];
    168:if(s>=0)value=256+slots[s].header[19];176:if(s>=0)value=slots[s].header[8];
    192:value=ep[n].dropped;200:if(s>=0)value=slots[s].header[5];208:value=ep[n].config_revision;
    216:value=ep[n].accepted;224:value=slots[n*2].state;232:value=slots[n*2+1].state;
    240:value=slots[n*2].generation;248:value=slots[n*2+1].generation;default:value=0;
   endcase
  end
  return value;
 endfunction
 assign acquisition_tick=tick;
 // POR is a separately admitted equipment initialization, never ordinary Reset.
 // Ordinary reset retains the presented memory transaction until acknowledgement.
 assign dma_valid=held_kind!=0&&!por_reset;
 assign dma_write=held_kind!=1;
 assign dma_addr=held_address;assign dma_wdata=held_data;assign dma_size=3;
 always_comb begin
  source_ready=!reset&&!por_reset&&source_can_accept(tick+1);
  ready=valid&&!reset&&!por_reset;error=ready&&(size!=3||!register_access(int'(addr),write));
  rdata=read_register(int'(addr));irq=!reset&&!por_reset&&(irq_pending()&mask)!=0;
  busy=held_kind!=0||table_status==1||lease_status!=0;
  for(integer n=0;n<3;n++)if(ep[n].active_slot>=0||ready_count(n)!=0||ep[n].state==RUNNING||ep[n].state==DRAINING)busy=1;
 end
 // Blocking assignments intentionally implement completion -> fences -> source ->
 // MMIO. A beat may accept only if ready was advertised from pre-edge state.
 always @(posedge clk)begin
  if(por_reset)initialize();
  else if(reset)begin
   tick=tick+1;
   if(dma_ready&&held_kind!=0)complete();
   if(!reset_seen)reset_authority();reset_seen=1;
  end else begin
   reset_seen=0;
   now_tick=tick+1;advertised=source_can_accept(now_tick);tick=now_tick;
   if(dma_ready&&held_kind!=0)complete();
   if(tick>MAX_TICK)begin global_error(EXHAUSTED);for(i=0;i<3;i++)fence(i,EXHAUSTED,FAULT);end
   for(i=0;i<3;i++)if(ep[i].consent!=0&&!permission(i,tick))fence(i,link!=0?(inhibit!=0?INHIBITED:EXPIRED):LINK,link!=0?CONFIGURED:DISCONNECTED);
   accepted=advertised&&source_can_accept(tick);if(accepted)source_accept();prepare();
   if(valid&&size==3&&register_access(int'(addr),write)&&write)write_register(int'(addr),wdata);
  end
 end
endmodule
