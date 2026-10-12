// lemma-ble-packet/1: uncoded LE1M packet engine at an explicit recovered-bit boundary.
// No RF/GFSK, connection establishment, authentication or Bluetooth qualification.
module lemma_ble_packet (
 input logic clk,reset,enabled,coex_allow,
 input logic valid,write,input logic [9:0] addr,input logic [2:0] size,
 input logic [63:0] wdata,output logic [63:0] rdata,
 output logic ready,error,irq,
 input logic rx_sample_valid,rx_sample_bit,
 output logic tx_sample_valid,tx_sample_bit,
 output logic [63:0] ticks,tx_packets,rx_packets,crc_errors,rx_errors,
 output logic tx_active,rx_active
);
 localparam logic [63:0] MAGIC=64'h31544b50454c4d4c;
 logic [31:0] access_address;
 logic [23:0] crc_init;
 logic [5:0] channel;
 logic [7:0] tx_header,tx_length,rx_header,rx_length;
 logic [7:0] tx_buffer[0:26],active_buffer[0:26],rx_buffer[0:26],rx_head[0:26];
 logic rx_pending;
 logic [7:0] fault;
 logic [3:0] events,event_base;
 logic [14:0] guard_ticks;
 logic [6:0] tx_divider;
 logic [1:0] tx_phase;
 logic [8:0] tx_index;
 logic [7:0] active_header,active_length;
 logic [23:0] tx_crc,rx_crc,received_crc;
 logic [6:0] tx_white,rx_white;
 logic [39:0] sync_shift;
 logic [1:0] rx_phase;
 logic [8:0] rx_index;
 logic [7:0] rx_octet,staging_header,staging_length;
 logic [6:0] rx_gap;
 logic known,write_ok,access_ok,raw_bit,plain_bit;
 logic [23:0] next_crc;
 logic [39:0] next_sync;
 function automatic logic address_ok(input logic [31:0] value);
   integer run_length,transitions,most_transitions,distance;
   logic previous;logic [31:0] reference;
   begin
     reference=32'h8e89bed6;run_length=1;transitions=0;most_transitions=0;distance=0;previous=value[0];address_ok=1;
     for(integer k=0;k<32;k=k+1)begin
       if(value[k]!=reference[k])distance=distance+1;
       if(k!=0)begin
         if(value[k]==previous)run_length=run_length+1;
         else begin run_length=1;transitions=transitions+1;if(k>=27)most_transitions=most_transitions+1;end
         if(run_length>6)address_ok=0;
         previous=value[k];
       end
     end
     if(distance<2||transitions>24||most_transitions<2||
       (value[7:0]==value[15:8]&&value[7:0]==value[23:16]&&value[7:0]==value[31:24]))address_ok=0;
   end
 endfunction
 function automatic logic [23:0] crc_step(input logic [23:0] state,input logic bit_in);
   crc_step={state[22:0],1'b0}^((state[23]^bit_in)?24'h00065b:24'h0);
 endfunction
 function automatic logic [6:0] white_step(input logic [6:0] state);
   white_step={1'b0,state[6:1]}^(state[0]?7'h44:7'h0);
 endfunction
 assign ready=1;
 assign access_ok=size==3&&addr[2:0]==0;
 assign known=addr==0||addr==8||addr==16||addr==24||addr==32||addr==40||addr==48||
   addr==56||addr==64||addr==72||addr==80||addr==88||addr==96||addr==104||
   (addr>=256&&addr<=464)||(addr>=512&&addr<=720);
 assign write_ok=(addr==24&&wdata<=64'hffffffff&&address_ok(wdata[31:0]))||(addr==32&&wdata<=64'hffffff)||
   (addr==40&&wdata<=36)||(addr==48&&wdata<=64'h1f&&wdata[1:0]!=0&&wdata[1:0]!=3)||
   (addr==56&&wdata<=27)||(addr==64&&wdata>=1&&wdata<=3)||(addr==72&&wdata<=15)||
   (addr>=256&&addr<=464&&wdata<=255);
 assign error=valid&&(!enabled||!access_ok||!known||(write&&!write_ok));
 assign irq=events!=0;
 assign event_base=(valid&&write&&!error&&addr==72)?events&~wdata[3:0]:events;
 assign rx_active=rx_phase!=0;
 always_comb begin
   rdata=0;
   if(enabled&&access_ok&&known) case(addr)
    0:rdata=MAGIC;8:rdata=1;
    16:rdata={59'b0,coex_allow,guard_ticks!=0,rx_pending,rx_active,tx_active};
    24:rdata={32'b0,access_address};32:rdata={40'b0,crc_init};40:rdata={58'b0,channel};
    48:rdata={56'b0,tx_header};56:rdata={56'b0,tx_length};
    72:rdata={60'b0,events};80:rdata={56'b0,fault};
    88:rdata={48'b0,rx_length,rx_header};96:rdata=ticks;104:rdata={49'b0,guard_ticks};
    default:begin
      if(addr>=256&&addr<=464)rdata={56'b0,tx_buffer[(addr-256)>>3]};
      if(addr>=512&&addr<=720&&rx_pending)rdata={56'b0,rx_head[(addr-512)>>3]};
    end
   endcase
   raw_bit=0;
   case(tx_phase)
    0:raw_bit=access_address[0]^tx_index[0];
    1:raw_bit=access_address[tx_index[4:0]];
    2:begin
      if(tx_index<8)raw_bit=active_header[tx_index[2:0]];
      else if(tx_index<16)raw_bit=active_length[tx_index[2:0]];
      else raw_bit=active_buffer[(tx_index-16)>>3][tx_index[2:0]];
    end
    3:raw_bit=tx_crc[23-tx_index[4:0]];
   endcase
   plain_bit=rx_sample_bit^rx_white[0];
   next_crc=crc_step(rx_crc,plain_bit);
   next_sync={rx_sample_bit,sync_shift[39:1]};
 end
 always_ff @(posedge clk) begin
   tx_sample_valid<=0;
   if(reset||!enabled)begin
     access_address<=32'hAA08192B;crc_init<=24'hC4C181;channel<=16;
     tx_header<=8'h02;tx_length<=0;rx_header<=0;rx_length<=0;rx_pending<=0;
     fault<=0;events<=0;guard_ticks<=0;tx_active<=0;tx_divider<=0;tx_phase<=0;tx_index<=0;
     active_header<=0;active_length<=0;tx_crc<=0;tx_white<=0;tx_sample_bit<=0;
     sync_shift<=0;rx_phase<=0;rx_index<=0;rx_octet<=0;staging_header<=0;staging_length<=0;
     rx_crc<=0;received_crc<=0;rx_white<=0;rx_gap<=0;
     ticks<=0;tx_packets<=0;rx_packets<=0;crc_errors<=0;rx_errors<=0;
     for(integer i=0;i<27;i=i+1)begin tx_buffer[i]<=0;active_buffer[i]<=0;rx_buffer[i]<=0;rx_head[i]<=0;end
   end else begin
     ticks<=ticks+1;
     if(guard_ticks!=0)guard_ticks<=guard_ticks-1;
     if(valid&&write)begin
       if(error)begin fault<=2;events<=event_base|8;end
       else if(addr==72)events<=events&~wdata[3:0];
       else if(addr==64&&wdata==2)begin rx_pending<=0;end
       else if(addr==64&&wdata==3)begin
         tx_active<=0;rx_phase<=0;sync_shift<=0;guard_ticks<=15000;fault<=6;events<=event_base|8;
       end else if(addr==64&&wdata==1)begin
         if(tx_active||rx_active||guard_ticks!=0||!coex_allow)begin fault<=3;events<=event_base|8;end
         else if(tx_length==0&&tx_header[1:0]!=1)begin fault<=2;events<=event_base|8;end
         else begin
           tx_active<=1;tx_divider<=99;tx_phase<=0;tx_index<=0;tx_crc<=crc_init;tx_white<={1'b1,channel};
           active_header<=tx_header;active_length<=tx_length;fault<=0;
           for(integer i=0;i<27;i=i+1)active_buffer[i]<=tx_buffer[i];
         end
       end else if(tx_active||rx_active)begin fault<=3;events<=event_base|8;end
       else case(addr)
         24:begin access_address<=wdata[31:0];sync_shift<=0;end
         32:begin crc_init<=wdata[23:0];sync_shift<=0;end
         40:begin channel<=wdata[5:0];sync_shift<=0;end
         48:tx_header<=wdata[7:0];56:tx_length<=wdata[7:0];
         default:if(addr>=256&&addr<=464)tx_buffer[(addr-256)>>3]<=wdata[7:0];
       endcase
     end
     if(tx_active)begin
       if(!coex_allow||(valid&&write&&!error&&addr==64&&wdata==3))begin
         tx_active<=0;guard_ticks<=15000;fault<=6;events<=event_base|8;
       end else if(tx_divider!=0)tx_divider<=tx_divider-1;
       else begin
         tx_divider<=99;tx_sample_valid<=1;tx_sample_bit<=raw_bit;
         if(tx_phase>=2)begin tx_sample_bit<=raw_bit^tx_white[0];tx_white<=white_step(tx_white);end
         if(tx_phase==2)tx_crc<=crc_step(tx_crc,raw_bit);
         if((tx_phase==0&&tx_index==7)||(tx_phase==1&&tx_index==31)||
            (tx_phase==2&&tx_index==(16+{1'b0,active_length[4:0],3'b0})-1))begin
           tx_phase<=tx_phase+1;tx_index<=0;
         end else if(tx_phase==3&&tx_index==23)begin
           tx_active<=0;guard_ticks<=15000;tx_packets<=tx_packets+1;events<=event_base|1;
         end else tx_index<=tx_index+1;
       end
     end
     // RX decisions have an explicit, exact 100-clock cadence once synchronized.
     if(!tx_active&&!(valid&&write&&!error&&addr==64&&wdata==3))begin
       if(rx_phase!=0)begin
         if(rx_gap<100)rx_gap<=rx_gap+1;
         if(!rx_sample_valid&&rx_gap==100)begin
           rx_phase<=0;sync_shift<=0;rx_errors<=rx_errors+1;fault<=5;events<=event_base|8;guard_ticks<=15000;
         end
       end
       if(rx_sample_valid)begin
         rx_gap<=0;
         if(rx_phase==0)begin
           sync_shift<=next_sync;
           if(next_sync=={access_address,(access_address[0]?8'h55:8'haa)})begin
             rx_phase<=1;rx_index<=0;rx_crc<=crc_init;received_crc<=0;rx_white<={1'b1,channel};rx_octet<=0;
           end
         end else if(rx_gap!=99)begin
           rx_phase<=0;sync_shift<=0;rx_errors<=rx_errors+1;fault<=5;events<=event_base|8;guard_ticks<=15000;
         end else begin
           rx_white<=white_step(rx_white);
           if(rx_phase==1)begin
             rx_crc<=next_crc;rx_octet[rx_index[2:0]]<=plain_bit;
             if(rx_index[2:0]==7)begin
               if(rx_index==7)begin
                 staging_header<={plain_bit,rx_octet[6:0]};
                 if(plain_bit||rx_octet[6:5]!=0||rx_octet[1:0]==0||rx_octet[1:0]==3)begin
                   rx_phase<=0;sync_shift<=0;rx_errors<=rx_errors+1;fault<=7;events<=event_base|8;
                 end
               end else if(rx_index==15)begin
                 staging_length<={plain_bit,rx_octet[6:0]};
                 if({plain_bit,rx_octet[6:0]}>27||({plain_bit,rx_octet[6:0]}==0&&staging_header[1:0]!=1))begin
                   rx_phase<=0;sync_shift<=0;rx_errors<=rx_errors+1;fault<=7;events<=event_base|8;
                 end else if({plain_bit,rx_octet[6:0]}==0)begin rx_phase<=2;rx_index<=0;end
               end else begin
                 rx_buffer[(rx_index-16)>>3]<={plain_bit,rx_octet[6:0]};
                 if(rx_index==16+{1'b0,staging_length[4:0],3'b0}-1)begin rx_phase<=2;rx_index<=0;end
               end
             end
             if(!(rx_index==15&&{plain_bit,rx_octet[6:0]}==0)&&
                !(rx_index>=16&&rx_index==16+{1'b0,staging_length[4:0],3'b0}-1))rx_index<=rx_index+1;
           end else if(rx_phase==2)begin
             received_crc<={received_crc[22:0],plain_bit};
             if(rx_index==23)begin
               rx_phase<=0;sync_shift<=0;guard_ticks<=15000;
               if({received_crc[22:0],plain_bit}!=rx_crc)begin crc_errors<=crc_errors+1;fault<=1;events<=event_base|8;end
               else if(rx_pending)begin rx_errors<=rx_errors+1;fault<=4;events<=event_base|8;end
               else begin
                 rx_header<=staging_header;rx_length<=staging_length;rx_pending<=1;rx_packets<=rx_packets+1;events<=event_base|2;fault<=0;
                 for(integer i=0;i<27;i=i+1)rx_head[i]<=i<staging_length?rx_buffer[i]:0;
               end
             end else rx_index<=rx_index+1;
           end
         end
       end
     end
   end
 end
endmodule
