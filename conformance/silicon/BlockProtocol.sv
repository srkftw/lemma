// SPDX-License-Identifier: Apache-2.0
// Independent literal bus/medium stimuli; not guest or durability evidence.
`timescale 1ns/1ps
module BlockProtocol;
  logic clk=0, reset_n=0;
  always #5 clk=~clk;
  logic valid=0,write=0;
  logic [11:0] addr=0;
  logic [2:0] size=2;
  logic [63:0] wdata=0,rdata;
  logic ready,error,irq;
  logic dma_valid,dma_write,dma_ready=1,dma_error=0;
  logic [63:0] dma_addr,dma_wdata,dma_rdata;
  logic [2:0] dma_size,media_kind;
  logic media_valid,media_ready=1,media_error=0;
  logic [63:0] media_sector;
  logic [4095:0] media_wdata,media_rdata=0;
  byte unsigned memory[4096];
  int dma_beats=0,medium_operations=0,checks=0;
  logic held_dma=0,held_media=0;
  logic [63:0] held_dma_addr,held_dma_wdata,held_media_sector;
  logic [4095:0] held_media_wdata;
  logic held_dma_write;
  logic [2:0] held_dma_size,held_media_kind;
  lemma_block #(.DMA_BYTES(4096),.CAPACITY_SECTORS(16)) dut(.*);
  always_comb begin
    dma_rdata=0;
    for(int j=0;j<8;j++) if(j<(1<<dma_size) && dma_addr>=64'h82000000 && dma_addr+64'(j)<64'h82001000)
      dma_rdata[j*8+:8]=memory[int'(dma_addr-64'h82000000)+j];
  end
  // An independent request observer checks every stalled beat, including the
  // edge on which ready finally accepts it. Cancellation may follow that edge.
  always @(posedge clk) begin
    if(!reset_n) begin
      dma_beats<=0;medium_operations<=0;held_dma<=0;held_media<=0;
    end else begin
      if(held_dma && (!dma_valid || dma_addr!==held_dma_addr ||
          dma_wdata!==held_dma_wdata || dma_write!==held_dma_write || dma_size!==held_dma_size))
        $fatal(1,"stalled DMA request changed before handshake");
      if(held_media && (!media_valid || media_kind!==held_media_kind ||
          media_sector!==held_media_sector || media_wdata!==held_media_wdata))
        $fatal(1,"stalled medium request changed before handshake");
      held_dma<=dma_valid&&!dma_ready;
      if(dma_valid&&!dma_ready)begin
        held_dma_addr<=dma_addr;held_dma_wdata<=dma_wdata;
        held_dma_write<=dma_write;held_dma_size<=dma_size;
      end
      held_media<=media_valid&&!media_ready;
      if(media_valid&&!media_ready)begin
        held_media_kind<=media_kind;held_media_sector<=media_sector;held_media_wdata<=media_wdata;
      end
      if(dma_valid&&dma_ready)begin
        dma_beats<=dma_beats+1;
        if(dma_write&&!dma_error)
          for(int j=0;j<8;j++)if(j<(1<<dma_size))memory[int'(dma_addr-64'h82000000)+j]<=dma_wdata[j*8+:8];
      end
      if(media_valid&&media_ready)medium_operations<=medium_operations+1;
    end
  end
  task automatic tick(input int n=1);repeat(n)begin @(posedge clk);#1;end endtask
  task automatic put(input int a,input logic[63:0] d);
    @(negedge clk);valid=1;write=1;addr=12'(a);wdata=d;
    for(int n=0;n<100;n++)begin
      #1;if(ready)break;
      if(n==99)$fatal(1,"bounded MMIO write did not become ready");
      tick();@(negedge clk);
    end
    tick();@(negedge clk);valid=0;write=0;
  endtask
  task automatic word(input int a,input logic[63:0] d,input int bytes=8);
    for(int j=0;j<bytes;j++)memory[a+j]=d[j*8+:8];
  endtask
  task automatic restart;
    @(negedge clk);reset_n=0;valid=0;write=0;dma_ready=1;media_ready=1;dma_error=0;media_error=0;tick(3);
    @(negedge clk);reset_n=1;tick();
    for(int i=0;i<4096;i++)memory[i]=0;
    put(36,0);put(32,512);put(36,1);put(32,1);put(112,11);
    put(48,0);put(56,8);put(128,64'h82000000);put(132,0);
    put(144,64'h82000080);put(148,0);put(160,64'h82000100);put(164,0);
    put(68,1);put(112,15);
  endtask
  task automatic flush_request;
    word(0,64'h82000400);word(8,{16'd1,16'd1,32'd16});
    word(16,64'h82000800);word(24,{16'd0,16'd2,32'd1});
    word(1024,4);word(1032,0);word(130,1,2);word(132,0,2);
    put(80,0);
  endtask
  task automatic wait_medium;
    for(int n=0;n<100;n++)begin
      tick();if(media_valid)break;
      if(n==99)$fatal(1,"no medium transaction");
    end
  endtask
  task automatic wait_used_index;
    for(int n=0;n<100;n++)begin
      @(negedge clk);
      if(dma_valid&&dma_write&&dma_addr==64'h82000102)break;
      if(n==99)$fatal(1,"no used-index publication");
    end
  endtask
  initial begin
    // A base write remains unaccepted while the original DMA beat is stalled.
    restart();dma_ready=0;put(80,0);tick(2);
    if(!dma_valid||dma_addr!=64'h82000082)$fatal(1,"missing stalled avail-index transaction");
    put(112,0);tick();
    if(dut.status!=15||!dma_valid)$fatal(1,"reset acknowledged before quiescence");
    @(negedge clk);valid=1;write=1;addr=144;wdata=64'h82000180;
    repeat(4)begin tick();if(ready||dma_addr!=64'h82000082||dut.avail_base!=64'h82000080)
      $fatal(1,"reset allowed pending queue-base mutation");end
    @(negedge clk);dma_ready=1;tick();
    if(dma_valid||dut.status!=0||dma_beats!=1||dut.avail_base!=64'h82000080)
      $fatal(1,"reset did not retire exactly the pending beat");
    tick();if(dut.avail_base!=64'h82000180)$fatal(1,"held base write not accepted after reset acknowledgement");
    @(negedge clk);valid=0;write=0;tick(3);
    if(dma_valid||dma_beats!=1)$fatal(1,"deferred DMA survived reset acknowledgement");
    checks++;

    // A ready beat on the reset-request edge is consumed once, not replayed
    // and not followed by the next descriptor/ring transfer.
    restart();word(130,1,2);dma_ready=0;put(80,0);tick(2);
    @(negedge clk);dma_ready=1;valid=1;write=1;addr=112;wdata=0;tick();
    if(dma_valid||dma_beats!=1)$fatal(1,"reset-request edge emitted an extra DMA transaction");
    @(negedge clk);valid=0;write=0;tick(3);
    if(dut.status!=0||dma_beats!=1)$fatal(1,"ready reset request failed to quiesce");checks++;

    // An illegal write reports a fault while preserving the currently stalled
    // DMA request. A queue selector cannot mutate an active queue either.
    restart();dma_ready=0;put(80,0);tick(2);put(200,1);tick(4);
    if(!dma_valid||dma_addr!=64'h82000082||dut.status!=79||!irq)
      $fatal(1,"fault withdrew pending DMA transaction");
    dma_ready=1;tick();if(dma_valid||dma_beats!=1||dut.status!=79)$fatal(1,"fault did not stop at quiescent boundary");
    tick(3);if(dma_valid||dma_beats!=1)$fatal(1,"fault issued deferred DMA");checks++;
    restart();dma_ready=0;put(80,0);tick(2);put(48,1);tick(3);
    if(dut.queue_sel!=0||!dma_valid||dut.status!=79)$fatal(1,"active queue selector mutated");
    put(112,0);dma_ready=1;tick(3);
    if(dma_valid||dut.status!=0||dma_beats!=1)$fatal(1,"fault-to-reset quiescence failed");checks++;

    // Reset/error also wait for a medium request under backpressure. The
    // external operation may complete, but no cancelled guest used entry does.
    restart();media_ready=0;flush_request();wait_medium();put(112,0);tick(5);
    if(!media_valid||dut.status!=15||medium_operations!=0)$fatal(1,"reset withdrew stalled medium request");
    media_ready=1;tick();if(media_valid||dut.status!=0||medium_operations!=1)$fatal(1,"medium reset handshake failed");
    tick(5);if(dma_valid||memory[258]!=0||medium_operations!=1)$fatal(1,"cancelled medium reset published completion");checks++;
    restart();media_ready=0;flush_request();wait_medium();put(200,1);tick(5);
    if(!media_valid||dut.status!=79||medium_operations!=0)$fatal(1,"fault withdrew stalled medium request");
    media_ready=1;tick();if(media_valid||medium_operations!=1)$fatal(1,"medium fault handshake failed");
    tick(5);if(dma_valid||memory[258]!=0||medium_operations!=1)$fatal(1,"cancelled medium fault published completion");checks++;
    $display("BLOCK-PROTOCOL DMA/media backpressure reset/error quiescence queue stability PASS");

    // New completion wins zero ACK, same-bit ACK and both-bit ACK.
    for(int ack=0;ack<=3;ack++)begin
      restart();flush_request();wait_used_index();
      valid=1;write=1;addr=100;wdata=64'(ack);tick();
      @(negedge clk);valid=0;write=0;tick();
      if(memory[258]!=1||!irq||dut.interrupt_status!=1)$fatal(1,"simultaneous ACK%0d lost completion",ack);
      put(100,1);if(irq||dut.interrupt_status!=0)$fatal(1,"ordinary completion ACK failed");checks++;
    end
    // A newly detected descriptor fault likewise dominates a simultaneous ACK.
    restart();word(0,64'h80000000);word(8,{16'd1,16'd1,32'd16});word(130,1,2);word(132,0,2);put(80,0);
    for(int n=0;n<100;n++)begin
      @(negedge clk);if(dma_valid&&!dma_write&&dma_addr==64'h82000008)break;
      if(n==99)$fatal(1,"no invalid descriptor validation");
    end
    valid=1;write=1;addr=100;wdata=2;tick();@(negedge clk);valid=0;write=0;tick();
    if(!irq||dut.interrupt_status!=2||dut.status!=79||medium_operations!=0)
      $fatal(1,"simultaneous ACK lost descriptor fault");checks++;
    put(100,2);if(irq)$fatal(1,"ordinary fault ACK failed");
    $display("BLOCK-PROTOCOL simultaneous completion/error IRQ ACK event precedence PASS");
    restart();flush_request();tick(40);
    if(memory[258]!=1||!irq||dut.interrupt_status!=1||medium_operations!=1)$fatal(1,"normal flush flow regressed");checks++;
    if(checks!=12)$fatal(1,"incomplete bounded protocol corpus %0d",checks);
    $display("BLOCK-PROTOCOL normal flush and 12 independent cases PASS");
    $finish;
  end
  initial begin #100000;$fatal(1,"bounded protocol bench deadline");end
endmodule
