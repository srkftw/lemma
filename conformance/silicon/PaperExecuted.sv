// SPDX-License-Identifier: Apache-2.0
// External observations of virtual-panel-synthetic/1 circuitry, not optics.
`timescale 1ns/1ps
module PaperExecuted #(parameter int VERSION=3);
  logic clk=0,reset_n=0,valid=0,write=0;
  always #5 clk=~clk;
  logic [11:0] addr=0;
  logic [2:0] size=3;
  logic [63:0] wdata=0,rdata,now_ticks=0,sequence_id;
  logic ready,error,irq,fb_valid,fb_write,fb_ready=1,fb_error=0;
  logic [31:0] fb_addr,x,y,dx,dy;
  logic [7:0] fb_wdata,fb_rdata,frames[64];
  logic panel_valid,panel_ready=1,complete,abort;
  logic [3:0] gray;
  logic drive_valid,power_enable,gate_clock,source_clock;
  logic [1:0] phase,code;
  logic [3:0] pending[32],visible[32];
  int drive_clocks=0,source_beats=0,gate_beats=0,pixels=0,completions=0,aborts=0;
  bit observe=0;
  lemma_paper #(.WIDTH(8),.HEIGHT(4),.ENABLE_SEQUENCER(1),.VERSION(VERSION),.STAGING_OFFSET(VERSION==1?2048:3584)) paper(
    .clk,.reset_n,.valid,.write,.addr,.size,.wdata,.rdata,.ready,.error,.irq,.now_ticks,
    .descriptor(2048'b0),.fb_valid,.fb_write,.fb_addr,.fb_wdata,.fb_ready,.fb_error,.fb_rdata,
    .panel_valid,.panel_ready,.panel_x(x),.panel_y(y),.panel_gray(gray),.panel_complete(complete),
    .panel_abort(abort),.panel_sequence(sequence_id),.panel_drive_valid(drive_valid),
    .panel_power_enable(power_enable),.panel_gate_clock(gate_clock),.panel_source_clock(source_clock),
    .panel_drive_phase(phase),.panel_drive_code(code),.panel_drive_x(dx),.panel_drive_y(dy));
  assign fb_rdata=frames[fb_addr];
  function automatic logic[3:0] expected_gray(input int p);
    case(p)0:expected_gray=1;1:expected_gray=7;2:expected_gray=10;default:expected_gray=15;endcase
  endfunction
  always @(posedge clk) begin
    if(fb_valid&&fb_ready&&fb_write&&!fb_error)frames[fb_addr]<=fb_wdata;
    if(drive_valid&&observe)begin
      int pixel_index,phase_index;
      pixel_index=(drive_clocks%8)/2;phase_index=drive_clocks/8;
      if(!power_enable||phase!==2'(phase_index)||dx!==32'(3+pixel_index%2)||dy!==32'(1+pixel_index/2))
        $fatal(1,"digital scan order/power differs at clock%0d",drive_clocks);
      if(code!==2'(phase_index==0?3:phase_index==1?(pixel_index<2?1:2):0))$fatal(1,"synthetic phase table differs");
      if(source_clock!==(drive_clocks%2==0)||gate_clock!==((drive_clocks%2==0)&&(pixel_index%2==0)))
        $fatal(1,"source/gate scan clock differs");
      drive_clocks<=drive_clocks+1;
      if(source_clock)source_beats<=source_beats+1;
      if(gate_clock)gate_beats<=gate_beats+1;
    end
    if(panel_valid&&panel_ready)begin
      pending[y*8+x]<=gray;
      if(observe)begin
        if(drive_clocks!=24||source_beats!=12||x!==32'(3+pixels%2)||y!==32'(1+pixels/2)||gray!==expected_gray(pixels))
          $fatal(1,"visible commit precedes scans or changed accepted data");
        pixels<=pixels+1;
      end
    end
    if(complete)begin
      completions<=completions+1;
      for(int i=0;i<32;i++)visible[i]<=pending[i];
      if(observe&&(power_enable||drive_valid||pixels!=4))$fatal(1,"completion before safe powerdown/complete frame");
    end
    if(abort)aborts<=aborts+1;
  end
  task automatic tick(input int n=1);repeat(n)begin @(posedge clk);#1;end endtask
  task automatic await_ready;
    int n=0;while(!ready)begin tick();n++;if(n>1000)$fatal(1,"bounded paper MMIO stalled");end
  endtask
  task automatic put(input int offset,input logic[63:0] value,input int width=3);
    @(negedge clk);valid=1;write=1;addr=12'(offset);wdata=value;size=3'(width);#1;await_ready();
    if(error)$fatal(1,"valid paper write rejected");tick();@(negedge clk);valid=0;write=0;
  endtask
  task automatic expect_word(input int offset,input logic[63:0] value);
    @(negedge clk);valid=1;write=0;addr=12'(offset);size=3;#1;await_ready();
    if(error||rdata!==value)$fatal(1,"paper register%0d actual%h expected%h",offset,rdata,value);
    tick();@(negedge clk);valid=0;
  endtask
  task automatic tile(input logic[7:0] a,b);
    put(64,3);put(72,1);put(80,2);put(88,2);put(96,2);put(VERSION==1?2048:3584,a,0);put(VERSION==1?2049:3585,b,0);put(104,1);tick(8);
  endtask
  task automatic refresh(input int seq,input int m=2);
    put(112,64'(seq));put(120,3);put(128,1);put(136,2);put(144,2);put(152,64'(m));put(104,2);tick(10);
  endtask
  initial begin
    for(int i=0;i<32;i++)begin pending[i]=15;visible[i]=15;end
    tick(2);@(negedge clk);reset_n=1;tick(40);
    expect_word(384,1);expect_word(392,64'h31504d53);
    tile(8'h17,8'haf);refresh(1);tile(8'hff,8'hff);
    observe=1;now_ticks=250000;
    while(!power_enable)tick();
    // An external frame-memory stall cannot skip scan reads or invent drive.
    fb_ready=0;tick(4);
    if(!fb_valid||fb_write||fb_addr!=43||drive_valid)$fatal(1,"scan read/backpressure missing");
    tick(4);if(!fb_valid||fb_addr!=43||drive_clocks!=0)$fatal(1,"stalled scan changed");
    fb_ready=1;
    while(completions==0)tick();tick();observe=0;
    expect_word(160,1);expect_word(432,24);expect_word(448,12);expect_word(440,0);
    expect_word(120,0);expect_word(128,0);expect_word(136,0);expect_word(144,0);
    expect_word(192,VERSION==3?1:0);expect_word(200,VERSION==3?3:0);
    expect_word(208,VERSION==3?1:0);expect_word(216,VERSION==3?2:0);
    expect_word(224,VERSION==3?2:0);expect_word(232,VERSION==3?2:0);
    // Writable unissued full-screen configuration cannot forge executed geometry.
    put(120,0);put(128,0);put(136,8);put(144,4);put(152,1);
    expect_word(192,VERSION==3?1:0);expect_word(200,VERSION==3?3:0);
    expect_word(216,VERSION==3?2:0);expect_word(224,VERSION==3?2:0);expect_word(232,VERSION==3?2:0);
    // Acknowledgment clears notification only; the accepted execution persists.
    put(168,1);expect_word(192,VERSION==3?1:0);
    // Idle reset retains optical completion but invalidates the execution witness.
    put(176,1);tick(40);expect_word(160,1);expect_word(112,1);
    expect_word(192,0);expect_word(200,0);expect_word(208,0);
    expect_word(216,0);expect_word(224,0);expect_word(232,0);
    if(drive_clocks!=24||gate_beats!=6||pixels!=4)$fatal(1,"digital scan/commit inventory differs");
    for(int i=0;i<4;i++)if(visible[(1+i/2)*8+3+i%2]!==expected_gray(i))$fatal(1,"immutable final pixels differ");
    $display("PAPER-SEQUENCER immutable 3-phase row/source clocks backpressure powerdown PASS");
    put(168,1);
    refresh(2,3);expect_word(24,3);expect_word(112,1);expect_word(432,24);put(168,1);
    // Reset during a real active drive aborts without making the panel white.
    refresh(2);now_ticks=500000;while(!drive_valid)tick();put(176,1);tick(40);
    if(power_enable||drive_valid||completions!=1||aborts!=2)$fatal(1,"reset failed to cancel digital drive");
    expect_word(160,1);expect_word(24,6);expect_word(112,2);expect_word(192,0);expect_word(216,0);
    for(int i=0;i<4;i++)if(visible[(1+i/2)*8+3+i%2]!==expected_gray(i))$fatal(1,"controller reset erased retained panel");
    put(168,1);
    // FB error during sequencing is an abort, with no fabricated completion.
    refresh(3);now_ticks=750000;while(!power_enable)tick();fb_error=1;tick(5);fb_error=0;tick(2);
    if(power_enable||drive_valid||completions!=1||aborts!=3)$fatal(1,"scan memory failure fabricated completion");
    expect_word(24,1);expect_word(160,1);expect_word(192,0);expect_word(216,0);expect_word(232,0);
    $display("PAPER-EXECUTED version%0d immutable accepted geometry, ACK, unissued configuration, idle/active reset and scan-error invalidation PASS",VERSION);
    $finish;
  end
  initial begin #1000000;$fatal(1,"bounded digital paper deadline");end
endmodule
