// SPDX-License-Identifier: Apache-2.0
// Literal external expectations, independent of controller implementation.
`timescale 1ns/1ps
module PowerControl;
  logic clk=0,reset=1,raw_button_level=0,valid=0,write=0;
  logic [2:0] reset_cause=1,cause;
  logic[1:0] events;
  logic raw_power_good=1,raw_brownout=0,domain_reset,power_loss,watchdog_armed;
  logic[63:0]watchdog_timeout,watchdog_remaining,reset_remaining,reset_epoch;
  logic [5:0] busy_sources=0;
  logic [7:0] addr=0;
  logic [2:0] size=3;
  logic [63:0] wdata=0,rdata,fault,epoch,wake_cause;
  logic ready,error,irq,suspended,cancel_pen;
  int cancellations=0;
  always #5 clk=~clk;
  always @(posedge clk) if(cancel_pen) cancellations<=cancellations+1;
  lemma_power power(.*);
  task automatic tick(input int n=1);repeat(n)begin @(posedge clk);#1;end endtask
  task automatic put(input int offset,input logic[63:0] value,input bit reject=0,input int width=3);
    @(negedge clk);valid=1;write=1;addr=8'(offset);size=3'(width);wdata=value;#1;
    if(!ready||error!==reject)$fatal(1,"power write%0d value%h error differs",offset,value);
    tick();@(negedge clk);valid=0;write=0;
  endtask
  task automatic expect_word(input int offset,input logic[63:0] expected);
    @(negedge clk);valid=1;write=0;addr=8'(offset);size=3;#1;
    if(!ready||error||rdata!==expected)$fatal(1,"power read%0d got%h wanted%h",offset,rdata,expected);
    tick();@(negedge clk);valid=0;
  endtask
  task automatic level(input bit value);
    @(negedge clk);raw_button_level=value;tick();
  endtask
  initial begin
    tick(2);@(negedge clk);reset=0;tick();
    expect_word(0,64'h4c505752);expect_word(8,1);expect_word(16,0);
    expect_word(24,0);expect_word(32,1);expect_word(56,0);
    if(irq||cancel_pen||cancellations)$fatal(1,"cold reset fabricated request");
    // Each independent source is sufficient. BUSY neither cancels nor finishes
    // an outstanding device, and clearing the error never grants suspend.
    for(int i=0;i<6;i++)begin
      busy_sources=6'(1<<i);put(72,1);
      expect_word(16,0);expect_word(24,1);
      if(cancel_pen||cancellations||irq)$fatal(1,"BUSY fabricated a power effect");
      put(88,1);expect_word(24,0);
    end
    busy_sources=0;
    // Every unsupported write/width is an error with no command effect.
    put(72,3,1);expect_word(16,0);expect_word(24,2);put(88,1);
    put(72,1,1,2);expect_word(16,0);expect_word(24,2);put(88,1);
    put(73,1,1);expect_word(16,0);expect_word(24,2);put(88,1);
    put(16,1,1);expect_word(16,0);expect_word(24,2);put(88,1);
    put(96,1,1);expect_word(16,0);expect_word(24,2);put(88,1);
    put(80,4,1);expect_word(48,0);expect_word(24,2);put(88,1);
    $display("POWER six independent BUSY sources malformed MMIO no false completion PASS");

    level(1);expect_word(40,1);expect_word(48,1);expect_word(56,1);
    if(!irq||suspended)$fatal(1,"raw button bypassed guest suspend decision");
    tick(5);expect_word(56,1); // Held level is not repeated input.
    level(0);
    // A simultaneous W1C cannot consume a newly arriving edge.
    @(negedge clk);raw_button_level=1;valid=1;write=1;addr=80;size=3;wdata=1;
    tick();@(negedge clk);valid=0;write=0;
    expect_word(48,1);expect_word(56,2);put(80,1);
    if(irq)$fatal(1,"exact request ACK did not clear level IRQ");
    put(72,1);
    if(!suspended||!cancel_pen)$fatal(1,"accepted suspend lacks pen loss pulse");
    tick(3);expect_word(16,1);expect_word(64,0);
    if(cancel_pen||cancellations!=1)$fatal(1,"pen cancellation not exactly one pulse");
    put(72,1);expect_word(16,1);expect_word(24,1);put(88,1);
    level(0);
    @(negedge clk);raw_button_level=1;valid=1;write=1;addr=80;size=3;wdata=3;
    tick();@(negedge clk);valid=0;write=0;
    expect_word(16,0);expect_word(48,2);expect_word(56,3);expect_word(64,1);
    if(!irq||cancellations!=1)$fatal(1,"physical wake fabricated cancel or lost IRQ");
    put(80,2);put(72,1);tick(2);put(72,2);
    expect_word(16,0);expect_word(48,2);expect_word(64,2);expect_word(56,3);
    if(cancellations!=2)$fatal(1,"authorized resume changed cancellation count");
    $display("POWER raw edge guest decision exact cancel wake and W1C precedence PASS");

    // A held physical level and epoch survive warm reset; cold control-domain
    // reset clears both only after the declared external level is zero.
    @(negedge clk);reset_cause=2;reset=1;tick(3);@(negedge clk);reset=0;tick(3);
    expect_word(16,0);expect_word(24,0);expect_word(32,2);
    expect_word(40,1);expect_word(48,0);expect_word(56,3);expect_word(64,0);
    if(irq||cancel_pen||cancellations!=2)$fatal(1,"warm reset manufactured edge/cancel");
    level(0);level(1);expect_word(48,1);expect_word(56,4);
    @(negedge clk);raw_button_level=0;reset_cause=1;reset=1;tick(3);
    @(negedge clk);reset=0;tick(3);
    expect_word(32,1);expect_word(40,0);expect_word(48,0);expect_word(56,0);
    if(suspended||irq||cancel_pen)$fatal(1,"cold reset retained volatile control state");
    $display("POWER warm held-button epoch retention and cold control reset PASS");
    $finish;
  end
  initial begin #1000000;$fatal(1,"bounded power controller deadline");end
endmodule
