// SPDX-License-Identifier: Apache-2.0
// Bounded external-interface miter against the source-bound prior pen.
// Literal expectations are computed from the input corpus, not RTL storage.
`timescale 1ns/1ps
module PenFaultCodes;
  logic clk=0, reset_n=0;
  always #5 clk=~clk;
  logic valid=0,write=0;
  logic [11:0] addr=0;
  logic [2:0] size=3;
  logic [63:0] wdata=0,now_ticks=0;
  logic sample_valid=0;
  logic [63:0] st=0,sx=0,sy=0,sp=0,sf=0,tool=0,buttons=0;
  wire [63:0] rdata,old_rdata;
  wire ready,error,irq,sample_ready,sample_accepted;
  wire old_ready,old_error,old_irq,old_sample_ready,old_sample_accepted;
  lemma_pen #(.IHP_SRAM(1)) pen(.clk,.reset_n,.valid,.write,.addr,.size,.wdata,.rdata,.ready,.error,.irq,.now_ticks,
    .sample_valid,.sample_ready,.sample_accepted,.sample_time(st),.sample_x(sx),.sample_y(sy),
    .sample_pressure(sp),.sample_flags(sf),.sample_tool(tool),.sample_buttons(buttons));
  lemma_pen_reference prior(.clk,.reset_n,.valid,.write,.addr,.size,.wdata,.rdata(old_rdata),
    .ready(old_ready),.error(old_error),.irq(old_irq),.now_ticks,.sample_valid,
    .sample_ready(old_sample_ready),.sample_accepted(old_sample_accepted),.sample_time(st),
    .sample_x(sx),.sample_y(sy),.sample_pressure(sp),.sample_flags(sf),.sample_tool(tool),.sample_buttons(buttons));
  int compared_edges=0;
  always @(posedge clk or negedge clk) begin
    #2;
    if ({rdata,ready,error,irq,sample_ready,sample_accepted} !==
        {old_rdata,old_ready,old_error,old_irq,old_sample_ready,old_sample_accepted})
      $fatal(1,"external-interface difference at edge%0d",compared_edges);
    compared_edges++;
  end
  task automatic tick(input int n=1);repeat(n)begin @(posedge clk);#3;end endtask
  task automatic clear_bus;
    @(negedge clk); valid=0;write=0;sample_valid=0;size=3;now_ticks=0;
  endtask
  task automatic reset_machine;
    clear_bus();reset_n=0;tick(2);@(negedge clk);reset_n=1;tick();
  endtask
  task automatic put(input int offset,input logic[63:0] value);
    @(negedge clk);valid=1;write=1;addr=12'(offset);wdata=value;
    while(!ready)tick();tick();clear_bus();
  endtask
  task automatic expect_word(input int offset,input logic[63:0] value);
    @(negedge clk);valid=1;write=0;addr=12'(offset);#3;
    while(!ready)tick();
    if(error||rdata!==value)$fatal(1,"literal offset%0d got%h expected%h",offset,rdata,value);
    tick();clear_bus();
  endtask
  task automatic fields(input int identity);
    st=64'h1234000000000000+64'(identity);
    sx=64'(identity*127%65536);sy=64'(65535-identity*31%65536);
    sp=64'(identity*53%4096);sf=2;tool=64'(identity%3);buttons=64'(identity%8);
  endtask
  task automatic expect_head(input int identity,input logic[63:0] seq);
    expect_word(256,seq);expect_word(264,64'h1234000000000000+64'(identity));
    expect_word(272,64'(identity*127%65536));expect_word(280,64'(65535-identity*31%65536));
    expect_word(288,64'(identity*53%4096));expect_word(296,2);
    expect_word(304,64'(identity%3));expect_word(312,64'(identity%8));
  endtask
  logic [63:0] seed=64'h11223344ffffffe0;
  initial begin
    reset_machine(); expect_word(24,0);
    // Public malformed access, failed acknowledgement and unsupported write.
    @(negedge clk);valid=1;write=1;addr=1;tick();clear_bus();expect_word(24,1);
    reset_machine();put(88,1);expect_word(24,2);
    reset_machine();put(0,1);expect_word(24,3);
    // Reach the full-width lifetime boundary directly in this finite fixture.
    // This is a declared component precondition, not a guest-visible setter.
    reset_machine();@(negedge clk);
    pen.epoch=64'hffffffffffffffff;prior.epoch=64'hffffffffffffffff;
    pen.losses=64'hffffffffffffffff;prior.losses=64'hffffffffffffffff;
    put(104,1);expect_word(24,5);
    expect_word(40,64'hffffffffffffffff);expect_word(48,64'hffffffffffffffff);
    expect_word(16,14);put(96,64'hffffffffffffffff);expect_word(24,0);
    reset_machine();expect_word(24,0);expect_word(40,1);expect_word(48,0);
    $display("PEN-FAULT full64-MMIO codes0/1/2/3/5, saturated64-bit epoch/losses, ACK/reset, external-interface reference PASS edges%0d",compared_edges);
    $finish;
  end
  initial begin #1000000;$fatal(1,"fault-code fixture deadline");end
endmodule
