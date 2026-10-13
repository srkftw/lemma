// SPDX-License-Identifier: Apache-2.0
// Bounded external-interface miter against the source-bound prior pen.
// Literal expectations are computed from the input corpus, not RTL storage.
`timescale 1ns/1ps
module PenIngress;
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
  lemma_pen pen(.clk,.reset_n,.valid,.write,.addr,.size,.wdata,.rdata,.ready,.error,.irq,.now_ticks,
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
    reset_machine();
    // An explicit white-box seed exercises upper sequence bits and the 32-bit
    // carry. All observations afterward use external MMIO and literal values.
    @(negedge clk);pen.next_sequence=seed;prior.next_sequence=seed;
    for(int lap=0;lap<2;lap++)begin
      // Keep valid asserted: every following edge admits the next payload.
      for(int i=lap*256;i<(lap+1)*256;i++)begin
        @(negedge clk);sample_valid=1;fields(i);tick();
        if(!sample_accepted)$fatal(1,"consecutive legal sample not accepted");
      end
      clear_bus();expect_word(32,256);
      // Full, malformed and unaccepted payloads must not replace any slot.
      @(negedge clk);sample_valid=1;fields(lap*256+256);sy=64'h0000080000000000;
      tick();if(sample_accepted)$fatal(1,"invalid full sample accepted");clear_bus();
      expect_word(32,1);expect_head(lap*256,seed+64'(lap*256));
      // Loss intentionally retains only its immutable head. Reset and repeat
      // the full corpus below before performing the complete wrap traversal.
      reset_machine();@(negedge clk);pen.next_sequence=seed+64'(lap*256);prior.next_sequence=seed+64'(lap*256);
      for(int i=lap*256;i<(lap+1)*256;i++)begin
        @(negedge clk);sample_valid=1;fields(i);tick();
      end
      clear_bus();
      for(int i=lap*256;i<(lap+1)*256;i++)begin
        expect_head(i,seed+64'(i));put(88,seed+64'(i));expect_word(32,64'((lap+1)*256-i-1));
      end
      expect_word(256,0);expect_word(264,0);
    end
    $display("PEN-INGRESS literal full256 fields high64 sequence/time consecutive/wrap PASS");
    // Malformed bounds, valid/write collision, malformed MMIO and exact ACK.
    for(int bad=0;bad<8;bad++)begin
      reset_machine();@(negedge clk);sample_valid=1;fields(0);tick();clear_bus();
      @(negedge clk);sample_valid=1;fields(1);
      case(bad)
        0:sx=65536;1:sy=64'h8000000000000000;2:sp=4096;3:sf=16;
        4:tool=3;5:buttons=8;6:st=0;7:st=64'hffffffffffffffff;
      endcase
      tick();if(sample_accepted)$fatal(1,"malformed sample accepted");clear_bus();
      expect_word(32,1);expect_head(0,1);expect_word(24,1);
    end
    reset_machine();@(negedge clk);sample_valid=1;fields(0);tick();
    @(negedge clk);fields(1);valid=1;write=1;addr=88;wdata=1;tick();
    if(sample_accepted)$fatal(1,"write collision admitted sample");clear_bus();expect_word(32,0);
    @(negedge clk);sample_valid=1;fields(2);tick();clear_bus();expect_head(2,2);
    put(88,64'h100000002);expect_word(32,1);expect_head(2,2);expect_word(24,2);
    // Reset at each refill edge cancels any queued or captured private payload.
    for(int stage=0;stage<2;stage++)begin
      reset_machine();for(int i=0;i<3;i++)begin @(negedge clk);sample_valid=1;fields(i);tick();end
      clear_bus();put(88,1);if(stage==1)tick();reset_machine();
      expect_word(32,0);expect_word(256,0);
      @(negedge clk);sample_valid=1;fields(3);tick();clear_bus();expect_head(3,1);
    end
    // Idle payload changes are deliberately aggressive: only the strobe owns
    // storage. Then exercise arbitrary public collisions with both machines.
    for(int i=0;i<2048;i++)begin
      @(negedge clk);fields(i);sample_valid=(i%3==0);valid=(i%5==0);write=(i%2==0);
      addr=12'((i%42)*8);wdata=64'(i);size=(i%7==0)?2:3;
      if(i%127==0)reset_n=0;else reset_n=1;
      tick();
    end
    reset_machine();expect_word(32,0);expect_word(256,0);
    $display("PEN-INGRESS every-edge old/new invalid full ACK reset collision PASS edges%0d",compared_edges);
    $finish;
  end
  initial begin #2000000;$fatal(1,"bounded ingress corpus deadline");end
endmodule
