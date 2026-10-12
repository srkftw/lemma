// SPDX-License-Identifier: Apache-2.0
// Digital control and cooperative-suspend admission. No CPU clock gating.
module lemma_power (
 input logic clk,reset,
 input logic [1:0] reset_cause,
 input logic raw_button_level,
 input logic [5:0] busy_sources,
 input logic valid,write,
 input logic [7:0] addr,
 input logic [2:0] size,
 input logic [63:0] wdata,
 output logic [63:0] rdata,
 output logic ready,error,irq,suspended,cancel_pen,
 output logic [63:0] fault,epoch,wake_cause,
 output logic [1:0] cause,events
);
 import lemma_silicon_binding::*;
 logic button_level,access_ok,known,write_ok;
 assign ready=1;
 assign access_ok=size==3 && addr[2:0]==0;
 assign known=addr==POWER_MAGIC_OFFSET || addr==POWER_VERSION_OFFSET ||
   addr==POWER_STATE_OFFSET || addr==POWER_ERROR_OFFSET ||
   addr==POWER_RESET_CAUSE_OFFSET || addr==POWER_BUTTON_LEVEL_OFFSET ||
   addr==POWER_EVENTS_OFFSET || addr==POWER_EPOCH_OFFSET ||
   addr==POWER_WAKE_CAUSE_OFFSET || addr==POWER_COMMAND_OFFSET ||
   addr==POWER_ACK_OFFSET || addr==POWER_CLEAR_ERROR_OFFSET;
 assign write_ok=(addr==POWER_COMMAND_OFFSET && (wdata==1 || wdata==2)) ||
   (addr==POWER_ACK_OFFSET && wdata<=3) ||
   (addr==POWER_CLEAR_ERROR_OFFSET && wdata==1);
 assign error=valid && (!access_ok || !known || (write && !write_ok));
 assign irq=events!=0;
 always_comb begin
   rdata=0;
   if(access_ok && known) case(addr)
     POWER_MAGIC_OFFSET:rdata=POWER_MAGIC_VALUE;
     POWER_VERSION_OFFSET:rdata=1;
     POWER_STATE_OFFSET:rdata={63'b0,suspended};
     POWER_ERROR_OFFSET:rdata=fault;
     POWER_RESET_CAUSE_OFFSET:rdata={62'b0,cause};
     POWER_BUTTON_LEVEL_OFFSET:rdata={63'b0,button_level};
     POWER_EVENTS_OFFSET:rdata={62'b0,events};
     POWER_EPOCH_OFFSET:rdata=epoch;
     POWER_WAKE_CAUSE_OFFSET:rdata=wake_cause;
     default:;
   endcase
 end
 always_ff @(posedge clk) begin
   cancel_pen<=0;
   if(reset) begin
     suspended<=0;fault<=0;events<=0;wake_cause<=0;cause<=reset_cause;
     // Cold resets the external control domain; warm preserves its physical
     // level/epoch and synchronizes held level without manufacturing an edge.
     button_level<=raw_button_level;
     if(reset_cause==1) epoch<=0;
   end else begin
     button_level<=raw_button_level;
     if(valid) begin
       if(error) fault<=2;
       else if(write) case(addr)
         POWER_COMMAND_OFFSET:if(wdata==1) begin
           if(suspended || |busy_sources) fault<=1;
           else begin suspended<=1;fault<=0;wake_cause<=0;cancel_pen<=1;end
         end else begin
           if(suspended) begin suspended<=0;events<=events|2;wake_cause<=2;end
           fault<=0;
         end
         POWER_ACK_OFFSET:events<=events & ~wdata[1:0];
         POWER_CLEAR_ERROR_OFFSET:fault<=0;
         default:;
       endcase
     end
     // New physical events win W1C at the same edge. The old state determines
     // request versus wake; a coincident suspend plus press remains a request.
     if(raw_button_level && !button_level) begin
       if(epoch!=64'hffffffffffffffff) epoch<=epoch+1;
       else fault<=2;
       events<=(valid && write && !error && addr==POWER_ACK_OFFSET ?
         events & ~wdata[1:0] : events) | (suspended?2:1);
       if(suspended) begin suspended<=0;wake_cause<=1;end
     end
   end
 end
endmodule
