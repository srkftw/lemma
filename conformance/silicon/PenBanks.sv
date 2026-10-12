// SPDX-License-Identifier: Apache-2.0
// Independent external-bus FIFO corpus. No hierarchical RTL state is read.
`timescale 1ns/1ps
module PenBanks;
  logic clk=0, reset_n=0;
  always #5 clk=~clk;
  logic valid=0,write=0,ready,error,irq;
  logic [11:0] addr=0;
  logic [2:0] size=3;
  logic [63:0] wdata=0,rdata,now_ticks=0;
  logic sample_valid=0,sample_ready,sample_accepted;
  logic [63:0] st=0,sx=0,sy=0,sp=0,sf=0,tool=0,buttons=0;
  lemma_pen pen(.clk,.reset_n,.valid,.write,.addr,.size,.wdata,.rdata,.ready,.error,.irq,.now_ticks,
    .sample_valid,.sample_ready,.sample_accepted,.sample_time(st),.sample_x(sx),.sample_y(sy),
    .sample_pressure(sp),.sample_flags(sf),.sample_tool(tool),.sample_buttons(buttons));
  task automatic tick(input int n=1);repeat(n)begin @(posedge clk);#1;end endtask
  task automatic wait_ready;
    int n=0;
    while(!ready)begin tick();n++;if(n>4)$fatal(1,"FIFO refill exceeded bounded latency");end
  endtask
  task automatic put(input int offset,input logic[63:0] value);
    @(negedge clk);valid=1;write=1;addr=12'(offset);wdata=value;#1;wait_ready();
    if(error)$fatal(1,"legal FIFO write rejected");
    tick();@(negedge clk);valid=0;write=0;
  endtask
  task automatic expect_word(input int offset,input logic[63:0] value);
    @(negedge clk);valid=1;write=0;addr=12'(offset);#1;wait_ready();
    if(error||rdata!==value)$fatal(1,"FIFO offset%0d actual%h expected%h",offset,rdata,value);
    tick();@(negedge clk);valid=0;
  endtask
  task automatic sample(input int identity,input logic[63:0] flags=2);
    @(negedge clk);sample_valid=1;st=64'h110000000+64'(identity);sx=64'(identity*127%65536);
    sy=64'(65535-identity*31%65536);sp=64'(identity*53%4096);sf=flags;
    tool=64'(identity%3);buttons=64'(identity%8);#1;
    wait_ready();if(!sample_ready)$fatal(1,"unblocked sample not ready");tick();
    if(!sample_accepted)$fatal(1,"bounded valid sample not accepted");
    @(negedge clk);sample_valid=0;
  endtask
  task automatic expect_head(input int identity,input int sequence_id,input logic[63:0] flags=2);
    expect_word(256,64'(sequence_id));expect_word(264,64'h110000000+64'(identity));
    expect_word(272,64'(identity*127%65536));expect_word(280,64'(65535-identity*31%65536));
    expect_word(288,64'(identity*53%4096));expect_word(296,flags);
    expect_word(304,64'(identity%3));expect_word(312,64'(identity%8));
  endtask
  task automatic reset_machine;
    @(negedge clk);reset_n=0;tick(2);@(negedge clk);reset_n=1;tick();
  endtask
  initial begin
    reset_machine();
    // Fill all 256 slots and traverse every bank and row, retaining all fields.
    for(int i=0;i<256;i++)sample(i);
    expect_word(32,256);
    for(int i=0;i<256;i++)begin
      expect_head(i,i+1);put(88,64'(i+1));expect_word(32,64'(255-i));
    end
    expect_word(256,0);expect_word(264,0);
    // A second full lap crosses the pointer wrap without aliasing old rows.
    for(int i=256;i<512;i++)sample(i);
    for(int i=256;i<512;i++)begin expect_head(i,i+1);put(88,64'(i+1));end
    // First-entry bypass plus a pop before its queued array write completes.
    sample(512);put(88,513);sample(513);expect_head(513,514);put(88,514);
    $display("PEN-BANKS full-capacity all-fields two-wrap and ingress bypass PASS");
    for(int stage=0;stage<2;stage++)begin
      reset_machine();sample(0);sample(1);
      put(88,1);
      if(ready||sample_ready)$fatal(1,"refill failed to apply bus/ingress backpressure");
      if(stage==1)tick();
      reset_machine();expect_word(32,0);expect_word(256,0);sample(2);expect_head(2,1);
    end
    // Drop valid after an acknowledged pop: refill still completes once.
    reset_machine();sample(0);sample(1);sample(2);put(88,1);wait_ready();
    expect_word(32,2);expect_head(1,2);put(88,2);wait_ready();expect_head(2,3);
    // Watchdog reached during refill retains the new immutable head, not the
    // already acknowledged one. It is handled at the next refill boundary.
    reset_machine();sample(0,3);sample(1,3);sample(2,3);put(88,1);
    now_ticks=64'h110000002+10000000;tick(3);expect_word(32,1);expect_word(40,2);
    expect_word(16,7);expect_head(1,2,3);expect_word(320,1);
    put(96,2);expect_word(32,0);expect_word(256,0);
    $display("PEN-BANKS refill backpressure reset cancellation and watchdog head PASS");
    $finish;
  end
  initial begin #1000000;$fatal(1,"bounded bank corpus deadline");end
endmodule
