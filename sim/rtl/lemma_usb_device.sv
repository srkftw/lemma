// lemma-usb-device/1: full-speed EP0 + bulk IN1/OUT2 at decoded packet-byte
// boundary. External bytes retain PID, token CRC5 and DATA CRC16. NRZI,
// bit stuffing, electrical attach and recovered 12MHz PHY are separate.
module lemma_usb_device #(parameter bit PHY_ABORT=0) (
 input logic clk,reset,enabled,connected,bus_reset,
 input logic valid,write,input logic [9:0] addr,input logic [2:0] size,
 input logic [63:0] wdata,output logic [63:0] rdata,
 output logic ready,error,irq,controller_busy,
 input logic rx_valid,rx_last,rx_abort,input logic [7:0] rx_byte,
 output logic rx_ready,
 output logic tx_valid,tx_last,output logic [7:0] tx_byte,input logic tx_ready,
 output logic [63:0] ticks,rx_packets,tx_packets,packet_errors,
 output logic [6:0] device_address,output logic configured
);
 localparam logic [63:0] MAGIC=64'h315645444253554c;
 localparam logic [7:0] OUT=8'he1,IN=8'h69,SETUP=8'h2d,SOF=8'ha5,
   DATA0=8'hc3,DATA1=8'h4b,ACK=8'hd2,NAK=8'h5a,STALL=8'h1e;
 logic [7:0] rx_packet[0:66],tx_packet[0:66];
 logic [6:0] rx_count,tx_count,tx_index;
 logic rx_overflow,tx_active,wait_ack,ack_ep;
 logic [7:0] tx_stage[0:1][0:63],tx_head[0:1][0:63],rx_head[0:1][0:63];
 logic [6:0] tx_length[0:1],head_length[0:1],rx_length[0:1];
 logic [1:0] tx_queued,rx_pending,in_toggle,out_toggle,halt_in;
 logic halt_out,rx_setup;
 logic [5:0] events;
 logic [7:0] fault;
 logic [19:0] reset_count;
 logic reset_seen,was_connected;
 logic token_pending,token_setup,token_ep;
 logic [13:0] token_timeout,ack_timeout;
 logic address_pending,config_pending;
 logic [6:0] pending_address;
 logic pending_configuration;
 logic [63:0] setup_generation,expected_setup;
 logic known,access_ok,write_ok;
 logic [5:0] event_base;
 function automatic logic [15:0] crc16_byte(input logic [15:0] state,input logic [7:0] value);
   logic [15:0] c;
   begin c=state;for(integer b=0;b<8;b=b+1)c=(c>>1)^((c[0]^value[b])?16'ha001:16'h0);return c;end
 endfunction
 function automatic logic [4:0] crc5_token(input logic [10:0] value);
   logic [4:0] c;
   begin c=5'h1f;for(integer b=0;b<11;b=b+1)c=(c>>1)^((c[0]^value[b])?5'h14:5'h0);return ~c;end
 endfunction
 task automatic send_handshake(input logic [7:0] pid);
   begin tx_packet[0]<=pid;tx_count<=1;tx_index<=0;tx_active<=1;end
 endtask
 task automatic clear_link;
   begin
     device_address<=0;configured<=0;tx_queued<=0;rx_pending<=0;
     in_toggle<=0;out_toggle<=0;halt_in<=0;halt_out<=0;
     address_pending<=0;config_pending<=0;pending_address<=0;pending_configuration<=0;
     tx_active<=0;wait_ack<=0;token_pending<=0;token_timeout<=0;ack_timeout<=0;
     rx_count<=0;rx_overflow<=0;rx_setup<=0;ack_ep<=0;token_ep<=0;token_setup<=0;
     tx_count<=0;tx_index<=0;
     for(integer e=0;e<2;e=e+1)begin tx_length[e]<=0;head_length[e]<=0;rx_length[e]<=0;end
   end
 endtask
 assign ready=1;
 assign access_ok=size==3&&addr[2:0]==0;
 assign known=addr<=168||(addr>=256&&addr<=376)||(addr>=512&&addr<=632);
 assign write_ok=(addr==40&&wdata<=63)||(addr==48&&wdata==0)||(addr==56&&wdata[63:16]==0&&wdata[15:8]<=2&&wdata[7:0]>=1&&wdata[7:0]<=5)||
   ((addr==64||addr==72)&&wdata<=64)||(addr==96&&wdata<=127)||(addr==104&&wdata<=1)||
   addr==168||(addr>=256&&addr<=376);
 assign error=valid&&(!enabled||!access_ok||!known||(write&&(!write_ok||((!connected||bus_reset)&&addr!=40&&addr!=48))));
 assign irq=events!=0;
 assign controller_busy=tx_active||wait_ack||token_pending||rx_count!=0||tx_queued!=0||rx_pending!=0||events!=0;
 assign rx_ready=enabled&&connected&&!bus_reset&&!tx_active;
 assign tx_valid=enabled&&connected&&!bus_reset&&tx_active;
 assign tx_byte=tx_packet[tx_index];
 assign tx_last=tx_index+1==tx_count;
 assign event_base=(valid&&write&&!error&&addr==40)?events&~wdata[5:0]:events;
 always_comb begin
   rdata=0;
   if(enabled&&access_ok&&known)case(addr)
    0:rdata=MAGIC;8:rdata=1;
    16:rdata={54'b0,wait_ack,tx_active,tx_queued,rx_pending,configured,device_address!=0,reset_seen,connected};
    24:rdata={57'b0,device_address};32:rdata={63'b0,configured};40:rdata={58'b0,events};48:rdata={56'b0,fault};
    64:rdata={57'b0,tx_length[0]};72:rdata={57'b0,tx_length[1]};
    80:rdata={54'b0,out_toggle[0],rx_setup,1'b0,rx_length[0]};
    88:rdata={56'b0,out_toggle[1],rx_length[1]};
    112:rdata=rx_packets;120:rdata=tx_packets;128:rdata={44'b0,reset_count};136:rdata=ticks;
    144:rdata={54'b0,config_pending,pending_configuration,address_pending,pending_address};
    152:rdata={57'b0,halt_out,halt_in,out_toggle,in_toggle};
    160:rdata=setup_generation;168:rdata=expected_setup;
    default:begin
      if(addr>=256&&addr<=376)for(integer b=0;b<8;b=b+1)rdata[b*8+:8]=tx_stage[addr>=320][int'(addr[5:0])+b];
      if(addr>=512&&addr<=632&&rx_pending[addr>=576])for(integer b=0;b<8;b=b+1)rdata[b*8+:8]=rx_head[addr>=576][int'(addr[5:0])+b];
    end
   endcase
 end
 always_ff @(posedge clk)begin : transition
   logic [15:0] checksum;
   logic [7:0] packet_pid;
   logic [10:0] token_value;
   logic [4:0] token_check;
   integer ep,n;
   if(reset||!enabled)begin
     clear_link();events<=0;fault<=0;ticks<=0;rx_packets<=0;tx_packets<=0;packet_errors<=0;
     reset_count<=0;reset_seen<=0;was_connected<=connected;
     setup_generation<=0;expected_setup<=0;
     for(integer e=0;e<2;e=e+1)for(integer b=0;b<64;b=b+1)begin tx_stage[e][b]<=0;tx_head[e][b]<=0;rx_head[e][b]<=0;end
     for(integer b=0;b<67;b=b+1)begin rx_packet[b]<=0;tx_packet[b]<=0;end
   end else begin
     ticks<=ticks+1;was_connected<=connected;
     if(valid&&write&&!error&&addr==40)events<=events&~wdata[5:0];
     if(valid&&write&&!error&&addr==48)fault<=0;
     if(!connected)begin
       clear_link();reset_count<=0;reset_seen<=0;
       if(was_connected)begin events<=event_base|16;fault<=8;expected_setup<=0;if(setup_generation!=64'hffffffffffffffff)setup_generation<=setup_generation+1;end
     end else if(bus_reset)begin
       // Full-speed reset qualification is 10ms in the declared 100MHz domain.
       tx_active<=0;wait_ack<=0;token_pending<=0;rx_count<=0;rx_overflow<=0;
       if(reset_count<1000000)reset_count<=reset_count+1;
       if(reset_count==999999&&!reset_seen)begin clear_link();reset_seen<=1;events<=event_base|1;fault<=0;expected_setup<=0;if(setup_generation!=64'hffffffffffffffff)setup_generation<=setup_generation+1;end
     end else begin
       reset_count<=0;reset_seen<=0;
       if(token_pending)begin
         if(token_timeout==0)begin token_pending<=0;fault<=7;events<=event_base|32;end
         else token_timeout<=token_timeout-1;
       end
       if(wait_ack)begin
         if(ack_timeout==0)begin wait_ack<=0;fault<=7;events<=event_base|32;end
         else ack_timeout<=ack_timeout-1;
       end
       if(valid&&write)begin
         if(error)begin fault<=2;events<=event_base|32;end
         else if(addr==40)events<=events&~wdata[5:0];
         else if(addr==48)fault<=0;
         else if(addr==168)begin
           if(wdata!=setup_generation||wdata==64'hffffffffffffffff)begin expected_setup<=64'hffffffffffffffff;fault<=2;events<=event_base|32;end
           else expected_setup<=wdata;
         end else if((addr==64||addr==96||addr==104||(addr>=256&&addr<=312)||(addr==56&&wdata[15:8]==0))&&expected_setup!=setup_generation)begin fault<=2;events<=event_base|32;end
         else if(addr==64||addr==72)begin
           if(tx_queued[addr==72])begin fault<=3;events<=event_base|32;end
           else tx_length[addr==72]<=wdata[6:0];
         end else if(addr>=256&&addr<=376)begin
           if(tx_queued[addr>=320])begin fault<=3;events<=event_base|32;end
           else for(integer b=0;b<8;b=b+1)tx_stage[addr>=320][int'(addr[5:0])+b]<=wdata[b*8+:8];
         end else if(addr==96||addr==104)begin
           if(!rx_pending[0]||!rx_setup||rx_head[0][0]!=0||rx_head[0][1]!=(addr==96?5:9)||
             rx_head[0][2]!=wdata[7:0]||rx_head[0][3]!=0||rx_head[0][4]!=0||rx_head[0][5]!=0||
             rx_head[0][6]!=0||rx_head[0][7]!=0||(addr==104&&device_address==0))begin fault<=2;events<=event_base|32;end
           else if(addr==96)begin address_pending<=1;pending_address<=wdata[6:0];end
           else begin config_pending<=1;pending_configuration<=wdata[0];end
         end else if(addr==56)begin
           ep=(wdata[15:8]==0)?0:1;
           if(wdata[7:0]==1)begin
             if(wdata[15:8]>1||tx_queued[ep]||(ep==1&&!configured))begin fault<=3;events<=event_base|32;end
             else begin tx_queued[ep]<=1;head_length[ep]<=tx_length[ep];
               for(integer b=0;b<64;b=b+1)tx_head[ep][b]<=b<tx_length[ep]?tx_stage[ep][b]:0;
             end
           end else if(wdata[7:0]==2)begin
             if(wdata[15:8]==1)begin fault<=2;events<=event_base|32;end
             else rx_pending[ep]<=0;
           end else if(wdata[7:0]==3||wdata[7:0]==4)begin
             if(wdata[15:8]==2)begin halt_out<=wdata[7:0]==3;if(wdata[7:0]==4)out_toggle[1]<=0;end
             else begin halt_in[ep]<=wdata[7:0]==3;if(wdata[7:0]==4)in_toggle[ep]<=0;end
           end else begin
             tx_queued[ep]<=0;rx_pending[ep]<=0;
             if(ep==0)begin address_pending<=0;config_pending<=0;end
             if(wait_ack&&ack_ep==ep[0])wait_ack<=0;
             if(tx_active&&ack_ep==ep[0]&&(tx_packet[0]==DATA0||tx_packet[0]==DATA1))tx_active<=0;
             if(token_pending&&token_ep==ep[0])token_pending<=0;
             fault<=6;events<=event_base|32;
           end
         end
       end
       if(tx_active&&tx_ready)begin
         if(tx_last)begin
           tx_active<=0;tx_packets<=tx_packets+1;
           if(tx_packet[0]==DATA0||tx_packet[0]==DATA1)begin wait_ack<=1;ack_timeout<=10000;end
         end else tx_index<=tx_index+1;
       end
       if(rx_valid&&rx_ready)begin
         if(rx_count<67)rx_packet[rx_count]<=rx_byte;else rx_overflow<=1;
         if(!rx_last)begin if(rx_count<67)rx_count<=rx_count+1;end
         else begin
           rx_count<=0;rx_overflow<=0;rx_packets<=rx_packets+1;
           // Last byte is used directly: nonblocking staging is not yet visible.
           n=int'(rx_count)+1;
           packet_pid=rx_count==0?rx_byte:rx_packet[0];
           if(rx_overflow||n>67||(packet_pid[7:4] != ~packet_pid[3:0]))begin
             packet_errors<=packet_errors+1;fault<=1;events<=event_base|32;
           end else if(n==1&&rx_byte==ACK&&wait_ack)begin
             wait_ack<=0;tx_queued[ack_ep]<=0;in_toggle[ack_ep]<=~in_toggle[ack_ep];events<=event_base|8;
             if(!ack_ep&&head_length[0]==0)begin
               if(address_pending)begin device_address<=pending_address;address_pending<=0;end
               if(config_pending)begin configured<=pending_configuration;config_pending<=0;in_toggle[1]<=0;out_toggle[1]<=0;
                 tx_queued[1]<=0;rx_pending[1]<=0;halt_in[1]<=0;halt_out<=0;
               end
             end
           end else if(n==3&&(rx_packet[0]==OUT||rx_packet[0]==IN||rx_packet[0]==SETUP||rx_packet[0]==SOF))begin
             token_value={rx_byte[2:0],rx_packet[1]};token_check=rx_byte[7:3];
             if(token_check!=crc5_token(token_value))begin packet_errors<=packet_errors+1;fault<=1;events<=event_base|32;end
             else if(rx_packet[0]!=SOF&&token_value[6:0]==device_address)begin
               wait_ack<=0;
               if(rx_packet[0]==IN&&(token_value[10:7]==0||(token_value[10:7]==1&&configured)))begin
                 ep=token_value[10:7]==0?0:1;
                 if(halt_in[ep])send_handshake(STALL);
                 else if(!tx_queued[ep])send_handshake(NAK);
                 else begin
                   tx_packet[0]<=in_toggle[ep]?DATA1:DATA0;checksum=16'hffff;
                   for(integer b=0;b<64;b=b+1)if(b<head_length[ep])begin tx_packet[b+1]<=tx_head[ep][b];checksum=crc16_byte(checksum,tx_head[ep][b]);end
                   tx_packet[head_length[ep]+1]<=~checksum[7:0];tx_packet[head_length[ep]+2]<=~checksum[15:8];
                   tx_count<=head_length[ep]+3;tx_index<=0;tx_active<=1;ack_ep<=ep[0];
                 end
               end else if((rx_packet[0]==SETUP&&token_value[10:7]==0)||
                 (rx_packet[0]==OUT&&(token_value[10:7]==0||(token_value[10:7]==2&&configured))))begin
                 token_pending<=1;token_setup<=rx_packet[0]==SETUP;token_ep<=token_value[10:7]==2;token_timeout<=10000;
               end
             end
           end else if(n>=3&&(rx_packet[0]==DATA0||rx_packet[0]==DATA1)&&token_pending)begin
             token_pending<=0;checksum=16'hffff;
             for(integer b=0;b<64;b=b+1)if(b<n-3)checksum=crc16_byte(checksum,rx_packet[b+1]);
             if(rx_packet[n-2]!=~checksum[7:0]||rx_byte!=~checksum[15:8]||(token_setup&&(n!=11||rx_packet[0]!=DATA0)))begin
               packet_errors<=packet_errors+1;fault<=1;events<=event_base|32;
             end else if(token_setup&&setup_generation==64'hffffffffffffffff)begin fault<=9;events<=event_base|32;end
             else if(token_setup)begin
               // A valid SETUP aborts the older EP0 transfer, including pending
               // address/configuration. Firmware must admit this new request.
               halt_in[0]<=0;tx_queued[0]<=0;address_pending<=0;config_pending<=0;
               setup_generation<=setup_generation+1;
               in_toggle[0]<=1;out_toggle[0]<=1;rx_pending[0]<=1;rx_setup<=1;rx_length[0]<=8;
               for(integer b=0;b<64;b=b+1)rx_head[0][b]<=b<8?rx_packet[b+1]:0;
               events<=event_base|2;send_handshake(ACK);
             end else if(token_ep&&halt_out)send_handshake(STALL);
             else if((rx_packet[0]==DATA1)!=out_toggle[token_ep])send_handshake(ACK);
             else if(rx_pending[token_ep])send_handshake(NAK);
             else begin
               rx_pending[token_ep]<=1;rx_length[token_ep]<=7'(n-3);out_toggle[token_ep]<=~out_toggle[token_ep];
               if(!token_ep)rx_setup<=0;
               for(integer b=0;b<64;b=b+1)rx_head[token_ep][b]<=b<n-3?rx_packet[b+1]:0;
               events<=event_base|4;send_handshake(ACK);
             end
           end else if(n!=1||rx_byte!=ACK)begin packet_errors<=packet_errors+1;fault<=1;events<=event_base|32;end
         end
       end
     end
     if(PHY_ABORT&&rx_abort)begin rx_count<=0;rx_overflow<=0;token_pending<=0;packet_errors<=packet_errors+1;fault<=1;events<=event_base|32;end
   end
 end
endmodule
