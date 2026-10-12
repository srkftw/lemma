// SPDX-License-Identifier: Apache-2.0
// Always-on digital control. Power-v1 remains selected by SAFETY=0.
// Power-v2 watchdog and sampled supply inputs reset the supervised domain;
// this clock keeps running independently of guest retirement/WFI/bus stalls.
module lemma_power #(parameter bit SAFETY=0) (
 input logic clk,reset,
 input logic [2:0] reset_cause,
 input logic raw_power_good,raw_brownout,
 input logic raw_button_level,
 input logic [5:0] busy_sources,
 input logic valid,write,
 input logic [7:0] addr,
 input logic [2:0] size,
 input logic [63:0] wdata,
 output logic [63:0] rdata,
 output logic ready,error,irq,suspended,cancel_pen,
 output logic [63:0] fault,epoch,wake_cause,
 output logic [2:0] cause,
 output logic [1:0] events,
 output logic domain_reset,power_loss,
 output logic [63:0] watchdog_timeout,watchdog_remaining,reset_remaining,reset_epoch,
 output logic watchdog_armed
);
 import lemma_silicon_binding::*;
 logic button_level,access_ok,known,write_ok;
 logic sampled_power_good,sampled_brownout,last_safe;
 logic safety_known,watchdog_reload;
 assign domain_reset=SAFETY&&(reset_remaining!=0||!raw_power_good||raw_brownout);
 assign watchdog_reload=valid&&write&&!error&&addr==104&&(wdata==1||(wdata==2&&watchdog_armed))&&watchdog_timeout!=0;
 assign safety_known=SAFETY&&(addr==96||addr==104||addr==112||addr==120||addr==128||addr==136||addr==144||addr==152);
 assign ready=1;
 assign access_ok=size==3 && addr[2:0]==0;
 assign known=addr==POWER_MAGIC_OFFSET || addr==POWER_VERSION_OFFSET ||
   addr==POWER_STATE_OFFSET || addr==POWER_ERROR_OFFSET ||
   addr==POWER_RESET_CAUSE_OFFSET || addr==POWER_BUTTON_LEVEL_OFFSET ||
   addr==POWER_EVENTS_OFFSET || addr==POWER_EPOCH_OFFSET ||
   addr==POWER_WAKE_CAUSE_OFFSET || addr==POWER_COMMAND_OFFSET ||
   addr==POWER_ACK_OFFSET || addr==POWER_CLEAR_ERROR_OFFSET || safety_known;
 assign write_ok=(addr==POWER_COMMAND_OFFSET && (wdata==1 || wdata==2)) ||
   (addr==POWER_ACK_OFFSET && wdata<=3) ||
   (addr==POWER_CLEAR_ERROR_OFFSET && wdata==1) ||
   (SAFETY && addr==96 && wdata>=8 && wdata<=64'hffffffff) ||
   (SAFETY && addr==104 && wdata>=1 && wdata<=3);
 assign error=valid && (!access_ok || !known || (write && !write_ok));
 assign irq=events!=0;
 always_comb begin
   rdata=0;
   if(access_ok && known) case(addr)
     POWER_MAGIC_OFFSET:rdata=POWER_MAGIC_VALUE;
     POWER_VERSION_OFFSET:rdata=SAFETY?2:1;
     POWER_STATE_OFFSET:rdata={63'b0,suspended};
     POWER_ERROR_OFFSET:rdata=fault;
     POWER_RESET_CAUSE_OFFSET:rdata={61'b0,cause};
     POWER_BUTTON_LEVEL_OFFSET:rdata={63'b0,button_level};
     POWER_EVENTS_OFFSET:rdata={62'b0,events};
     POWER_EPOCH_OFFSET:rdata=epoch;
     POWER_WAKE_CAUSE_OFFSET:rdata=wake_cause;
     96:rdata=SAFETY?watchdog_timeout:0;
     112:rdata=SAFETY?watchdog_remaining:0;
     120:rdata={63'b0,SAFETY&&watchdog_armed};
     128:rdata={62'b0,SAFETY&&sampled_brownout,!SAFETY||sampled_power_good};
     136:rdata={62'b0,!domain_reset,domain_reset};
     144:rdata=SAFETY?reset_remaining:0;
     152:rdata=SAFETY?reset_epoch:0;
     default:;
   endcase
 end
 always_ff @(posedge clk) begin
   cancel_pen<=0;power_loss<=0;
   if(reset) begin
     suspended<=0;fault<=0;events<=0;wake_cause<=0;cause<=reset_cause;
     // Cold resets the external control domain; warm preserves its physical
     // level/epoch and synchronizes held level without manufacturing an edge.
     button_level<=raw_button_level;
     watchdog_timeout<=0;watchdog_remaining<=0;watchdog_armed<=0;reset_remaining<=0;
     sampled_power_good<=raw_power_good;sampled_brownout<=raw_brownout;last_safe<=1;
     if(reset_cause==1)begin epoch<=0;reset_epoch<=0;end
   end else begin
     button_level<=raw_button_level;
     sampled_power_good<=raw_power_good;sampled_brownout<=raw_brownout;
     last_safe<=raw_power_good&&!raw_brownout;
     if(SAFETY&&(!raw_power_good||raw_brownout)) begin
       reset_remaining<=8;watchdog_armed<=0;watchdog_remaining<=0;
       suspended<=0;events<=0;wake_cause<=0;fault<=0;cause<=raw_brownout?5:6;
       if(last_safe)begin power_loss<=1;if(reset_epoch!=64'hffffffffffffffff)reset_epoch<=reset_epoch+1;end
     end else if(SAFETY&&reset_remaining!=0)begin
       reset_remaining<=reset_remaining-1;
     end else if(SAFETY&&watchdog_armed&&watchdog_remaining==1&&!watchdog_reload)begin
       reset_remaining<=8;watchdog_remaining<=0;watchdog_armed<=0;cause<=4;
       suspended<=0;events<=0;wake_cause<=0;fault<=0;
       if(reset_epoch!=64'hffffffffffffffff)reset_epoch<=reset_epoch+1;
     end else begin
     if(SAFETY&&watchdog_armed)watchdog_remaining<=watchdog_remaining-1;
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
         96:if(SAFETY)begin if(watchdog_armed)fault<=1;else begin watchdog_timeout<=wdata;fault<=0;end end
         104:if(SAFETY)begin
           if(wdata==3)begin watchdog_armed<=0;watchdog_remaining<=0;fault<=0;end
           else if(watchdog_timeout==0||(wdata==2&&!watchdog_armed))fault<=2;
           else begin watchdog_armed<=1;watchdog_remaining<=watchdog_timeout;fault<=0;end
         end
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
 end
endmodule
