`timescale 1ns/1ps
module PowerSafety;
 logic clk=0,reset=1,raw_button_level=0,raw_power_good=1,raw_brownout=0,valid=0,write=0;
 logic[2:0] reset_cause=1,cause;
 logic[1:0] events;
 logic[5:0] busy_sources=0;
 logic[7:0] addr=0;
 logic[2:0] size=3;
 logic[63:0] wdata=0,rdata,fault,epoch,wake_cause,watchdog_timeout,watchdog_remaining,reset_remaining,reset_epoch;
 logic ready,error,irq,suspended,cancel_pen,domain_reset,power_loss,watchdog_armed;
 int cycles=0,losses=0;
 always #5 clk=~clk;
 always @(posedge clk)begin cycles<=cycles+1;if(power_loss)losses<=losses+1;end
 lemma_power #(.SAFETY(1)) power(.*);
 task automatic tick(input int n=1);repeat(n)begin @(posedge clk);#1;end endtask
 task automatic put(input int a,input logic[63:0]v,input bit rejected=0);
  @(negedge clk);addr=8'(a);valid=1;write=1;wdata=v;#1;
  if(error!==rejected)$fatal(1,"write admission %0d %0d",a,v);
  tick();@(negedge clk);valid=0;write=0;
 endtask
 task automatic restart; @(negedge clk);reset=1;tick(2);@(negedge clk);reset=0;tick();endtask
 initial begin
  restart();
  put(96,7,1);if(watchdog_timeout!=0||watchdog_armed)$fatal(1,"malformed timeout changed state");
  put(104,1);if(watchdog_armed||fault!=2)$fatal(1,"unconfigured arm");
  put(96,8);put(104,1);if(watchdog_remaining!=8)$fatal(1,"arm origin");
  // No processor-progress signal exists. Eight always-on rising edges expire.
  tick(7);if(domain_reset||watchdog_remaining!=1)$fatal(1,"watchdog deadline early");
  tick();if(!domain_reset||cause!=4||watchdog_armed||reset_remaining!=8||power_loss)$fatal(1,"watchdog expiry");
  tick(7);if(!domain_reset||reset_remaining!=1)$fatal(1,"reset duration early");
  tick();if(domain_reset||reset_remaining||reset_epoch!=1)$fatal(1,"reset duration late");
  $display("POWER2 watchdog expiry independent of guest progress exact8 reset clocks PASS");
  put(104,1);tick(7);
  // A valid heartbeat on the terminal edge wins over expiry.
  @(negedge clk);valid=1;write=1;addr=104;wdata=2;tick();
  @(negedge clk);valid=0;write=0;
  if(domain_reset||watchdog_remaining!=8)$fatal(1,"terminal kick priority");
  put(96,16);if(fault!=1||watchdog_timeout!=8)$fatal(1,"armed timeout change");
  put(104,3);tick(20);if(domain_reset||watchdog_armed)$fatal(1,"disarm");
  busy_sources=6'b100000;put(72,1);if(suspended||fault!=1)$fatal(1,"pending backing suspend accepted");
  busy_sources=0;put(72,1);if(!suspended)$fatal(1,"old suspend lost");
  raw_button_level=1;tick();if(suspended||wake_cause!=1||epoch!=1)$fatal(1,"old button wake lost");
  $display("POWER2 terminal kick malformed writes and Power1 suspend wake retained PASS");
  put(104,1);
  @(negedge clk);raw_brownout=1;raw_power_good=0;valid=1;write=1;addr=104;wdata=2;tick();
  @(negedge clk);valid=0;write=0;
  if(!domain_reset||cause!=5||!power_loss||watchdog_armed)$fatal(1,"brownout priority");
  tick(20);if(reset_remaining!=8||losses!=1)$fatal(1,"unsafe hold or repeated loss");
  @(negedge clk);raw_power_good=1;raw_brownout=0;tick(7);
  if(!domain_reset||reset_remaining!=1)$fatal(1,"power-good qualification early");
  tick();if(domain_reset||cause!=5||epoch!=1)$fatal(1,"power-good qualification late/epoch loss");
  @(negedge clk);raw_power_good=0;tick();if(cause!=6||!power_loss)$fatal(1,"power-good loss cause");
  tick(3);@(negedge clk);raw_power_good=1;tick(8);
  if(domain_reset||reset_epoch!=3)$fatal(1,"distinct reset origins");
  $display("POWER2 brownout priority actual domain reset unsafe hold8 good clocks PASS");
  $finish;
 end
 initial begin #1000000;$fatal(1,"bounded power2 deadline");end
endmodule
