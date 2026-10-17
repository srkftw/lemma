// lemma-wifi-ofdm-data/1: bounded common legacy DATA dependency.
// 48 data + 4 pilot tones, 64-point integer IFFT/DFT, 16-sample cyclic prefix,
// BPSK, rate1/2 K7 BCC and terminated hard-decision Viterbi. No HE PPDU,
// preamble/acquisition, MAC, RF, regulatory, or whole-machine profile claim.
module lemma_wifi_ofdm_data (
 input logic clk,reset,enabled,coex_allow,
 input logic valid,write,input logic [9:0] addr,input logic [2:0] size,
 input logic [63:0] wdata,output logic [63:0] rdata,
 output logic ready,error,irq,controller_busy,
 input logic rx_sample_valid,input logic signed [15:0] rx_i,rx_q,
 output logic tx_sample_valid,output logic signed [15:0] tx_i,tx_q,
 output logic [63:0] ticks,tx_packets,rx_packets,tx_wire_samples,rx_wire_samples,
 output logic tx_active,rx_active,output logic [7:0] last_fault,
 output logic [9:0] last_metric
);
 import lemma_wifi_math::*;
 localparam logic [63:0] MAGIC=64'h31415441444d4657;
 localparam logic [9:0] INF=10'd1023;
 logic [7:0] tx_buffer[0:15],active_buffer[0:19],rx_work[0:19],rx_head[0:15];
 logic [4:0] tx_length,rx_expected,active_length,rx_length,head_length;
 logic [6:0] tx_seed,rx_seed,tx_scrambler,rx_scrambler,tx_pilot,rx_pilot;
 logic [5:0] tx_bcc;
 logic [47:0] tx_coded[0:1],rx_coded;
 logic tx_bank,prep_bank,prep_active;
 logic [1:0] tx_phase;
 logic [2:0] tx_divider;
 logic [6:0] tx_sample_index,rx_sample_index;
 logic [7:0] prep_index,total_bits,rx_total_bits,rx_tail_end,rx_bit_base;
 logic [3:0] tx_symbol,rx_symbols;
 logic [4:0] crc_index,rx_crc_index;
 logic [31:0] tx_crc,rx_crc;
 logic [2:0] events,event_base;
 logic rx_pending,rx_collecting,rx_started;
 logic [13:0] rx_wait;
 logic [3:0] rx_gap;
 logic signed [47:0] fft_acc[0:63],fft_last[0:63];
 logic [9:0] metric[0:63];
 logic [63:0] survivor[0:181];
 logic decoded[0:181];
 logic [2:0] decode_phase;
 logic [4:0] decode_index;
 logic [7:0] trace_index,descramble_index;
 logic [5:0] trace_state;
 logic known,write_ok,access_ok,cancel,release_head;
 logic [5:0] mod_index;
 logic signed [15:0] mod_i,mod_q;
 assign tx_active=tx_phase!=0;
 assign controller_busy=tx_active||rx_active||rx_pending||events!=0;
 assign ready=1;assign irq=events!=0;
 assign access_ok=size==3&&addr[2:0]==0;
 assign known=addr==0||addr==8||addr==16||addr==24||addr==32||addr==40||addr==48||
   addr==56||addr==64||addr==72||addr==80||addr==88||addr==96||addr==104||addr==112||
   addr==120||addr==128||addr==136||(addr>=256&&addr<=376)||(addr>=512&&addr<=632);
 assign write_ok=(addr==24&&wdata>=1&&wdata<=16)||(addr==32&&wdata>=1&&wdata<=127)||
   (addr==40&&wdata>=1&&wdata<=16)||(addr==48&&wdata>=1&&wdata<=127)||
   (addr==56&&wdata>=1&&wdata<=4)||(addr==64&&wdata<=7)||
   (addr>=256&&addr<=376&&wdata<=255);
 assign error=valid&&(!enabled||!access_ok||!known||(write&&!write_ok));
 assign event_base=(valid&&write&&!error&&addr==64)?events&~wdata[2:0]:events;
 assign cancel=valid&&write&&!error&&addr==56&&wdata==4;
 assign release_head=valid&&write&&!error&&addr==56&&wdata==3;
 assign mod_index=tx_sample_index<16?6'(tx_sample_index+48):6'(tx_sample_index-16);
 lemma_wifi_ofdm_modulator modulator(.bits_in(tx_coded[tx_bank]),
   .pilot_negative(tx_pilot[6]^tx_pilot[3]),.sample_index(mod_index),.i(mod_i),.q(mod_q));
 always_comb begin
  rdata=0;
  case(addr)
   0:rdata=MAGIC;8:rdata=1;16:rdata={59'b0,coex_allow,enabled,rx_pending,rx_active,tx_active};
   24:rdata={59'b0,tx_length};32:rdata={57'b0,tx_seed};40:rdata={59'b0,rx_expected};
   48:rdata={57'b0,rx_seed};64:rdata={61'b0,events};72:rdata={56'b0,last_fault};
   80:rdata=ticks;88:rdata={59'b0,head_length};96:rdata=tx_packets;104:rdata=rx_packets;
   112:rdata={54'b0,last_metric};120:rdata=rx_wire_samples;128:rdata=tx_wire_samples;136:rdata=16;
   default:begin
    if(addr>=256&&addr<=376)rdata={56'b0,tx_buffer[(addr-256)>>3]};
    if(addr>=512&&addr<=632)rdata={56'b0,rx_head[(addr-512)>>3]};
   end
  endcase
 end
 always_ff @(posedge clk)begin : engine
  logic raw_bit,scrambled_bit,feedback;
  logic [1:0] pair,received;
  logic [31:0] crc_next;
  logic [5:0] predecessor;
  logic [9:0] m0,m1;
  integer pos,p0,p1,next_state,n,bin;
  logic signed [47:0] increment;
  if(reset||!enabled)begin
   ticks<=0;tx_packets<=0;rx_packets<=0;tx_wire_samples<=0;rx_wire_samples<=0;
   tx_length<=1;rx_expected<=1;tx_seed<=127;rx_seed<=127;active_length<=0;rx_length<=0;head_length<=0;
   tx_scrambler<=0;rx_scrambler<=0;tx_pilot<=0;rx_pilot<=0;tx_bcc<=0;
   tx_coded[0]<=0;tx_coded[1]<=0;rx_coded<=0;tx_bank<=0;prep_bank<=0;prep_active<=0;
   tx_phase<=0;tx_divider<=0;tx_sample_index<=0;rx_sample_index<=0;prep_index<=0;total_bits<=0;
   rx_total_bits<=0;rx_tail_end<=0;rx_bit_base<=0;tx_symbol<=0;rx_symbols<=0;
   crc_index<=0;rx_crc_index<=0;tx_crc<=0;rx_crc<=0;events<=0;last_fault<=0;last_metric<=0;
   rx_pending<=0;rx_collecting<=0;rx_started<=0;rx_active<=0;rx_wait<=0;rx_gap<=0;
   decode_phase<=0;decode_index<=0;trace_index<=0;descramble_index<=0;trace_state<=0;
   tx_sample_valid<=0;tx_i<=0;tx_q<=0;
   for(integer k=0;k<16;k=k+1)begin tx_buffer[k]<=0;rx_head[k]<=0;end
   for(integer k=0;k<20;k=k+1)begin active_buffer[k]<=0;rx_work[k]<=0;end
   for(integer k=0;k<64;k=k+1)begin fft_acc[k]<=0;fft_last[k]<=0;metric[k]<=INF;end
   for(integer k=0;k<182;k=k+1)begin survivor[k]<=0;decoded[k]<=0;end
  end else begin
   ticks<=ticks+1;events<=event_base;tx_sample_valid<=0;
   if(valid&&error)begin last_fault<=1;events<=event_base|3'b100;end
   if(valid&&write&&!error)begin
    if(addr==64)events<=event_base;
    else if(addr==56)begin
     if(wdata==3)rx_pending<=0;
     else if(wdata==1)begin
      if(tx_active||rx_active||!coex_allow)begin last_fault<=2;events<=event_base|3'b100;end
      else begin
       for(integer k=0;k<16;k=k+1)active_buffer[k]<=tx_buffer[k];
       active_length<=tx_length;crc_index<=0;tx_crc<=32'hffffffff;tx_phase<=1;
       tx_scrambler<=tx_seed;tx_bcc<=0;tx_pilot<=7'd126;tx_bank<=0;prep_bank<=0;
       prep_index<=0;prep_active<=0;tx_symbol<=0;tx_sample_index<=0;tx_divider<=0;
       total_bits<=8'(((16+(int'(tx_length)+4)*8+6+23)/24)*24);
      end
     end else if(wdata==2)begin
      if(tx_active||rx_active||!coex_allow)begin last_fault<=2;events<=event_base|3'b100;end
      else begin
       rx_length<=rx_expected;rx_scrambler<=rx_seed;rx_pilot<=7'd126;rx_active<=1;
       rx_collecting<=1;rx_started<=0;rx_wait<=0;rx_gap<=0;rx_sample_index<=0;rx_symbols<=0;
       rx_total_bits<=8'(((16+(int'(rx_expected)+4)*8+6+23)/24)*24);
       rx_tail_end<=8'(16+(int'(rx_expected)+4)*8+6);rx_bit_base<=0;decode_phase<=0;
       decode_index<=0;rx_crc_index<=0;rx_crc<=32'hffffffff;last_metric<=0;
       for(integer k=0;k<64;k=k+1)begin fft_acc[k]<=0;fft_last[k]<=0;metric[k]<=k==0?10'd0:INF;end
       for(integer k=0;k<20;k=k+1)rx_work[k]<=0;
      end
     end
    end else if(tx_active||rx_active)begin last_fault<=2;events<=event_base|3'b100;end
    else case(addr)
     24:tx_length<=wdata[4:0];32:tx_seed<=wdata[6:0];40:rx_expected<=wdata[4:0];48:rx_seed<=wdata[6:0];
     default:if(addr>=256&&addr<=376)tx_buffer[(addr-256)>>3]<=wdata[7:0];
    endcase
   end
   if(cancel||(!coex_allow&&(tx_active||rx_active)))begin
    tx_phase<=0;prep_active<=0;rx_active<=0;rx_collecting<=0;decode_phase<=0;
    tx_sample_valid<=0;last_fault<=3;events<=event_base|3'b100;
   end else begin
    if(tx_phase==1)begin
     crc_next=crc_octet(tx_crc,active_buffer[crc_index]);tx_crc<=crc_next;
     if(crc_index+1==active_length)begin
      for(integer k=0;k<4;k=k+1)active_buffer[int'(active_length)+k]<=8'((~crc_next)>>(8*k));
      tx_phase<=2;prep_active<=1;prep_index<=0;prep_bank<=0;
     end else crc_index<=crc_index+1;
    end
    if(prep_active)begin
     pos=int'(prep_index);raw_bit=0;
     if(pos>=16&&pos<16+(int'(active_length)+4)*8)raw_bit=active_buffer[(pos-16)/8][(pos-16)%8];
     feedback=tx_scrambler[6]^tx_scrambler[3];scrambled_bit=raw_bit^feedback;
     if(pos>=16+(int'(active_length)+4)*8&&pos<16+(int'(active_length)+4)*8+6)scrambled_bit=0;
     tx_scrambler<=scramble_next(tx_scrambler);pair=bcc_pair(tx_bcc,scrambled_bit);tx_bcc<=bcc_next(tx_bcc,scrambled_bit);
     tx_coded[prep_bank][interleave48(2*(pos%24))]<=pair[0];
     tx_coded[prep_bank][interleave48(2*(pos%24)+1)]<=pair[1];prep_index<=prep_index+1;
     if(pos%24==23)begin
      if(tx_phase==2)begin tx_phase<=3;prep_bank<=1;prep_active<=total_bits>24;end
      else prep_active<=0;
     end
    end
    if(tx_phase==3)begin
     if(tx_divider==4)begin
      tx_divider<=0;tx_sample_valid<=1;tx_i<=mod_i;tx_q<=mod_q;tx_wire_samples<=tx_wire_samples+1;
      if(tx_sample_index==79)begin
       tx_sample_index<=0;
       if((int'(tx_symbol)+1)*24==int'(total_bits))begin tx_phase<=0;tx_packets<=tx_packets+1;events<=event_base|3'b001;end
       else begin
        tx_bank<=~tx_bank;tx_symbol<=tx_symbol+1;tx_pilot<=scramble_next(tx_pilot);
        prep_bank<=tx_bank;prep_active<=prep_index<total_bits;
       end
      end else tx_sample_index<=tx_sample_index+1;
     end else tx_divider<=tx_divider+1;
    end
    if(rx_active&&rx_collecting)begin
     if(!rx_started)begin
      if(rx_sample_valid)begin rx_started<=1;rx_gap<=0;rx_sample_index<=1;rx_wire_samples<=rx_wire_samples+1;end
      else if(rx_wait==8191)begin rx_active<=0;rx_collecting<=0;decode_phase<=0;last_fault<=4;events<=event_base|3'b100;end
      else rx_wait<=rx_wait+1;
     end else if(rx_sample_valid)begin
      if(rx_gap!=4)begin rx_active<=0;rx_collecting<=0;decode_phase<=0;last_fault<=4;events<=event_base|3'b100;end
      else begin
       rx_gap<=0;rx_wire_samples<=rx_wire_samples+1;
       if(rx_sample_index>=16)begin
        n=int'(rx_sample_index)-16;
        for(integer k=0;k<64;k=k+1)begin
         increment=48'($signed(rx_i)*$signed(cosine(k*n)))+48'($signed(rx_q)*$signed(sine(k*n)));
         if(rx_sample_index==79)begin fft_last[k]<=fft_acc[k]+increment;fft_acc[k]<=0;end
         else fft_acc[k]<=fft_acc[k]+increment;
        end
       end
       if(rx_sample_index==79)begin
        rx_sample_index<=0;rx_symbols<=rx_symbols+1;
        if(decode_phase!=0)begin rx_active<=0;rx_collecting<=0;decode_phase<=0;last_fault<=9;events<=event_base|3'b100;end
        else begin decode_phase<=1;decode_index<=0;end
        if((int'(rx_symbols)+1)*24==int'(rx_total_bits))rx_collecting<=0;
       end else rx_sample_index<=rx_sample_index+1;
      end
     end else if(rx_gap==4)begin rx_active<=0;rx_collecting<=0;decode_phase<=0;last_fault<=4;events<=event_base|3'b100;end
     else rx_gap<=rx_gap+1;
    end
    if(rx_active)begin
     case(decode_phase)
      1:begin
       for(integer k=0;k<48;k=k+1)rx_coded[k]<=fft_last[data_bin(k)]>=0;
       decode_phase<=2;
       if((fft_last[43]<0)!=(rx_pilot[6]^rx_pilot[3])||
          (fft_last[57]<0)!=(rx_pilot[6]^rx_pilot[3])||
          (fft_last[7]<0)!=(rx_pilot[6]^rx_pilot[3])||
          (fft_last[21]<0)==(rx_pilot[6]^rx_pilot[3]))begin
        rx_active<=0;rx_collecting<=0;decode_phase<=0;last_fault<=9;events<=event_base|3'b100;
       end else rx_pilot<=scramble_next(rx_pilot);
      end
      2:begin
       pos=int'(rx_bit_base)+int'(decode_index);
       received={rx_coded[interleave48(2*int'(decode_index)+1)],rx_coded[interleave48(2*int'(decode_index))]};
       if(pos<int'(rx_tail_end))begin
        for(integer k=0;k<64;k=k+1)begin
         p0=(k&31)*2;p1=p0+1;
         m0=metric[p0]>=INF?INF:metric[p0]+10'(distance2(bcc_pair(6'(p0),k>=32),received));
         m1=metric[p1]>=INF?INF:metric[p1]+10'(distance2(bcc_pair(6'(p1),k>=32),received));
         metric[k]<=m0<=m1?m0:m1;survivor[pos][k]<=m1<m0;
        end
       end
       if(decode_index==23)begin
        rx_bit_base<=rx_bit_base+24;decode_index<=0;
        if(int'(rx_bit_base)+24==int'(rx_total_bits))begin
         decode_phase<=3;trace_index<=rx_tail_end-1;trace_state<=0;
        end else decode_phase<=0;
       end else decode_index<=decode_index+1;
      end
      3:begin
       last_metric<=metric[0];
       if(metric[0]>4)begin rx_active<=0;decode_phase<=0;last_fault<=5;events<=event_base|3'b100;end
       else begin
        decoded[trace_index]<=trace_state[5];predecessor={trace_state[4:0],survivor[trace_index][trace_state]};trace_state<=predecessor;
        if(trace_index==0)begin
         if(predecessor!=0)begin rx_active<=0;decode_phase<=0;last_fault<=5;events<=event_base|3'b100;end
         else begin decode_phase<=4;descramble_index<=0;end
        end else trace_index<=trace_index-1;
       end
      end
      4:begin
       pos=int'(descramble_index);raw_bit=decoded[pos]^(rx_scrambler[6]^rx_scrambler[3]);rx_scrambler<=scramble_next(rx_scrambler);
       if(pos<16&&raw_bit)begin rx_active<=0;decode_phase<=0;last_fault<=7;events<=event_base|3'b100;end
       else if(pos>=16&&pos<16+(int'(rx_length)+4)*8)rx_work[(pos-16)/8][(pos-16)%8]<=raw_bit;
       if(pos+1==16+(int'(rx_length)+4)*8)begin decode_phase<=5;rx_crc_index<=0;rx_crc<=32'hffffffff;end
       else descramble_index<=descramble_index+1;
      end
      5:begin
       crc_next=crc_octet(rx_crc,rx_work[rx_crc_index]);rx_crc<=crc_next;
       if(rx_crc_index+1==rx_length)begin decode_phase<=6;end else rx_crc_index<=rx_crc_index+1;
      end
      6:begin
       rx_active<=0;decode_phase<=0;
       if({rx_work[int'(rx_length)+3],rx_work[int'(rx_length)+2],rx_work[int'(rx_length)+1],rx_work[int'(rx_length)]}!=~rx_crc)begin last_fault<=6;events<=event_base|3'b100;end
       else if(rx_pending&&!release_head)begin last_fault<=8;events<=event_base|3'b100;end
       else begin
        for(integer k=0;k<16;k=k+1)rx_head[k]<=k<int'(rx_length)?rx_work[k]:0;
        head_length<=rx_length;rx_pending<=1;rx_packets<=rx_packets+1;events<=event_base|3'b010;
       end
      end
      default:begin end
     endcase
    end
   end
  end
 end
endmodule
