// SPDX-License-Identifier: Apache-2.0
// USB full-speed digital hard-decision transceiver. The declared 48MHz
// clock is an independent 48MHz domain, four samples per symbol.
// Line values are {D-,D+}: J=01,K=10,SE0=00,SE1=11. No analog qualification.
module lemma_usb_fs_phy_clocked (
 input logic clk,reset,enabled,connected,
 input logic [1:0] line_in,
 input logic tx_valid,tx_last,input logic [7:0] tx_byte,output logic tx_ready,
 output logic tx_oe,tx_busy,output logic [1:0] line_out,
 output logic rx_valid,rx_last,output logic [7:0] rx_byte,input logic rx_ready,rx_admit,
 output logic rx_abort,bus_reset,controller_busy,
 output logic [63:0] sample_ticks,tx_packets,rx_packets,stuff_errors,line_errors,underflows
);
 localparam logic [1:0] J=2'b01,K=2'b10,SE0=2'b00,SE1=2'b11;
 localparam logic [2:0] T_IDLE=0,T_SYNC=1,T_DATA=2,T_TAIL=3,T_EOP2=4,T_J=5,T_RELEASE=6;
 localparam logic [2:0] R_IDLE=0,R_SYNC=1,R_DATA=2,R_EOP2=3,R_J=4,R_DROP=5;
 logic [1:0] tx_quarter;
 logic [3:0] guard_samples;
 logic [7:0] reset_clocks;
 logic [7:0] tx_buffer[0:66];
 logic [6:0] tx_count,tx_index;
 logic tx_final;
 logic tx_failed;
 logic [2:0] tx_state,tx_bit,tx_ones;
 logic [1:0] rx_previous,rx_sample_line,rx_timer;
 logic [2:0] rx_state,rx_bit,rx_ones;
 logic [7:0] rx_word,rx_held;
 logic rx_has_held;
 logic [6:0] rx_count;
 logic [3:0] drop_se0,drop_j;
 wire sample_enable=1'b1;
 assign bus_reset=connected&&reset_clocks==120;
 assign tx_ready=enabled&&connected&&!bus_reset&&!tx_final&&tx_count<67&&
                 (tx_state==T_IDLE||tx_state==T_SYNC||tx_state==T_DATA);
 assign tx_busy=tx_state!=T_IDLE||guard_samples!=0;
 assign controller_busy=tx_state!=T_IDLE||rx_state!=R_IDLE||rx_valid||rx_has_held||guard_samples!=0;
 task automatic bad_receive(input logic stuffing);
  begin
   rx_abort<=!(rx_valid&&rx_last&&!rx_ready);
   rx_state<=R_DROP;drop_se0<=(line_in==SE0||rx_state==R_EOP2||rx_state==R_J)?1:0;drop_j<=0;rx_has_held<=0;rx_count<=0;rx_word<=0;rx_bit<=0;rx_ones<=0;
   if(!(rx_valid&&rx_last&&!rx_ready))rx_valid<=0;
   if(stuffing)stuff_errors<=stuff_errors+1;else line_errors<=line_errors+1;
  end
 endtask
 always_ff @(posedge clk)begin : transceiver
  logic value;
  logic [7:0] completed;
  if(reset||!enabled||!connected)begin
   tx_quarter<=0;guard_samples<=0;reset_clocks<=0;
   tx_state<=T_IDLE;tx_count<=0;tx_index<=0;tx_final<=0;tx_failed<=0;tx_bit<=0;tx_ones<=0;tx_oe<=0;line_out<=J;
   rx_state<=R_IDLE;rx_previous<=J;rx_sample_line<=J;rx_timer<=0;
   rx_word<=0;rx_held<=0;rx_has_held<=0;rx_count<=0;rx_bit<=0;rx_ones<=0;drop_se0<=0;drop_j<=0;
   rx_valid<=0;rx_last<=0;rx_byte<=0;rx_abort<=0;
   sample_ticks<=0;tx_packets<=0;rx_packets<=0;stuff_errors<=0;line_errors<=0;underflows<=0;
   for(integer n=0;n<67;n=n+1)tx_buffer[n]<=0;
  end else begin
   rx_abort<=0;
   if(line_in==SE0)begin if(reset_clocks<120)reset_clocks<=reset_clocks+1;end
   else reset_clocks<=0;
   if(rx_valid&&rx_ready)rx_valid<=0;
   if(bus_reset)begin
    tx_state<=T_IDLE;tx_count<=0;tx_final<=0;tx_failed<=0;tx_oe<=0;line_out<=J;
    rx_state<=R_IDLE;rx_has_held<=0;rx_valid<=0;rx_count<=0;rx_abort<=0;
   end else begin
    if(tx_valid&&tx_ready)begin
     tx_buffer[tx_count]<=tx_byte;tx_count<=tx_count+1;
     if(tx_last)tx_final<=1;
     if(tx_state==T_IDLE)begin tx_state<=T_SYNC;tx_index<=0;tx_bit<=0;tx_ones<=0;tx_failed<=0;end
    end
    if(sample_enable)begin
     sample_ticks<=sample_ticks+1;tx_quarter<=tx_quarter+1;
     if(guard_samples!=0)guard_samples<=guard_samples-1;
     if(tx_quarter==0&&guard_samples==0)case(tx_state)
      T_SYNC:begin
       tx_oe<=1;value=tx_bit==7;
       if(!value)line_out<=line_out==J?K:J;
       tx_ones<=value?1:0;
       if(tx_bit==7)begin tx_bit<=0;tx_state<=T_DATA;end else tx_bit<=tx_bit+1;
      end
      T_DATA:begin
       if(tx_ones==6)begin line_out<=line_out==J?K:J;tx_ones<=0;end
       else if(tx_index>=tx_count)begin
        // A physical packet cannot stretch its bit clock for source starvation.
        underflows<=underflows+1;tx_failed<=1;line_out<=SE1;tx_ones<=0;tx_state<=T_TAIL;
       end else begin
        value=tx_buffer[tx_index][tx_bit];
        if(!value)line_out<=line_out==J?K:J;
        tx_ones<=value?tx_ones+1:0;
        if(tx_bit==7)begin
         tx_bit<=0;tx_index<=tx_index+1;
         if(tx_final&&tx_index+1==tx_count)tx_state<=T_TAIL;
        end else tx_bit<=tx_bit+1;
       end
      end
      T_TAIL:begin
       // A required stuffed zero is emitted even after the final data bit.
       if(tx_ones==6)begin line_out<=line_out==J?K:J;tx_ones<=0;end
       else begin line_out<=SE0;tx_state<=T_EOP2;end
      end
      T_EOP2:begin line_out<=SE0;tx_state<=T_J;end
      T_J:begin line_out<=J;tx_state<=T_RELEASE;end
      T_RELEASE:begin
       tx_oe<=0;tx_state<=T_IDLE;tx_count<=0;tx_final<=0;tx_index<=0;
       if(!tx_failed)tx_packets<=tx_packets+1;guard_samples<=8;
      end
      default:begin end
     endcase
     rx_sample_line<=line_in;
     if(rx_state==R_DROP)begin
      // Never accept a new SYNC from the tail of a rejected physical packet.
      if(line_in==SE0)begin if(drop_se0<8)drop_se0<=drop_se0+1;drop_j<=0;end
      else if(line_in==J&&drop_se0>=6)begin rx_state<=R_IDLE;drop_se0<=0;drop_j<=0;end
      else if(line_in==J&&drop_se0!=0)begin
       // A malformed short EOP cannot poison later transactions forever.
       // Require three idle J symbols after an observed SE0; do not seek
       // SYNC from a rejected packet's differential tail.
       if(drop_j==11)begin rx_state<=R_IDLE;drop_se0<=0;drop_j<=0;end
       else drop_j<=drop_j+1;
      end else begin drop_se0<=0;drop_j<=0;end
     end else if(tx_oe)begin rx_state<=R_IDLE;rx_previous<=J;rx_has_held<=0;rx_count<=0;end
     else if(rx_state==R_IDLE)begin
      if(line_in==K)begin
       if(!rx_admit)begin bad_receive(0);rx_abort<=0;end
       else if(rx_valid&&rx_last&&!rx_ready)bad_receive(0);
       else begin rx_state<=R_SYNC;rx_timer<=1;rx_previous<=J;rx_word<=0;rx_bit<=0;rx_ones<=0;rx_count<=0;rx_has_held<=0;end
      end
     end else if((line_in==J||line_in==K)&&(rx_sample_line==J||rx_sample_line==K)&&
                 line_in!=rx_sample_line)begin
      // Retiming only a real differential edge keeps the sampling point away
      // from transitions. Stuffing bounds transition-free packet intervals.
      rx_timer<=1;
     end else if(rx_timer!=0)rx_timer<=rx_timer-1;
     else begin
      rx_timer<=3;
      if(rx_state==R_EOP2)begin
       if(line_in==SE0)rx_state<=R_J;else bad_receive(0);
      end else if(rx_state==R_J)begin
       if(line_in==J&&rx_has_held&&(!rx_valid||rx_ready)&&
          (rx_bit==0||(rx_bit<=6&&rx_word==((8'b1<<rx_bit)-1))))begin
        rx_valid<=1;rx_last<=1;rx_byte<=rx_held;rx_has_held<=0;
        rx_state<=R_IDLE;rx_packets<=rx_packets+1;guard_samples<=8;
       end else bad_receive(0);
      end else if(line_in==SE1)bad_receive(0);
      else if(line_in==SE0)begin
       if(rx_state==R_DATA)rx_state<=R_EOP2;else bad_receive(0);
      end else begin
       value=line_in==rx_previous;rx_previous<=line_in;
       if(rx_state==R_DATA&&rx_ones==6)begin
        if(value)bad_receive(1);else rx_ones<=0;
       end else begin
        rx_ones<=value?rx_ones+1:0;
        completed=rx_word|(8'(value)<<rx_bit);
        if(rx_bit==7)begin
         rx_word<=0;rx_bit<=0;
         if(rx_state==R_SYNC)begin
          if(completed==8'h80)rx_state<=R_DATA;else bad_receive(0);
         end else if(rx_count==67||(rx_has_held&&rx_valid&&!rx_ready))bad_receive(0);
         else begin
          if(rx_has_held)begin rx_valid<=1;rx_last<=0;rx_byte<=rx_held;end
          rx_held<=completed;rx_has_held<=1;rx_count<=rx_count+1;
         end
        end else begin rx_word<=completed;rx_bit<=rx_bit+1;end
       end
      end
     end
    end
   end
  end
 end
endmodule
