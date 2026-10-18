// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module Sar4Bench;
 logic clk=0,reset_n=0,start=0,cancel=0,comparator_high=0;
 wire sample_enable,busy,valid,cancelled,overrun;wire[3:0]trial,code;
 sar4_control dut(.*);
 logic [3:0] traces[0:18], expected[0:18];integer n,b,index;logic [3:0] previous;
 task tick;begin #500;clk=1;#500;clk=0;end endtask
 task require_true(input bit condition,input string message);
  if(!condition) $fatal(1,"%s case=%0d bit=%0d",message,n,b);
 endtask
 initial begin
  $readmemh("decisions.hex",traces);$readmemh("expected.hex",expected);
  tick;reset_n=1;tick;
  for(n=0;n<19;n=n+1) begin
   start=1;tick;start=0;require_true(busy&&sample_enable,"acquisition not enabled");
   tick;require_true(!sample_enable && trial==8,"aperture/trial boundary differs");
   previous=0;
   for(b=3;b>=0;b=b-1) begin
    require_true(trial==(previous|(4'b0001<<b)),"trial does not follow previous decision");
    comparator_high=traces[n][b];
    tick;tick;
    if(comparator_high)previous=previous|(4'b0001<<b);
   end
   require_true(valid&&!busy&&code==expected[n],"actual transistor decisions produced wrong code");
   tick;require_true(!valid,"completion repeated");
  end
  // Reset and cancel interrupt actual in-progress control without a completion.
  for(index=0;index<7;index=index+1) begin
   start=1;tick;start=0;repeat(index+1)tick;
   reset_n=0;tick;require_true(!busy&&!valid&&!sample_enable&&trial==0&&code==0,"reset retains output");
   reset_n=1;tick;
  end
  start=1;tick;start=0;tick;start=1;tick;start=0;
  require_true(overrun&&busy,"busy start not rejected");cancel=1;tick;cancel=0;
  require_true(cancelled&&!busy&&!valid&&trial==0&&code==0,"cancel published partial conversion");
  repeat(4)tick;require_true(!valid&&!cancelled,"side effect repeated after cancel");
  $display("PASS 19 actual transistor decision traces plus reset/cancel/overrun");$finish;
 end
endmodule
