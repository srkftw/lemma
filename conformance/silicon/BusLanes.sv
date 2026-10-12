// SPDX-License-Identifier: Apache-2.0
// Literal AHB data-phase and external-memory stimuli. The hart is held in
// reset; this bench tests real fabric circuitry and does not claim guest boot.
module BusLanes;
  import lemma_silicon_binding::*;
  logic clk=0,reset=1;
  always #5 clk=~clk;
  logic bus_valid=0,bus_write=0;
  logic [55:0] bus_address=0;
  logic [2:0] bus_size=2;
  logic [63:0] store_value=0,replicated_store;
  subwordwrite #(64) actual_cvw_store(.LSUFunct3M(bus_size),
    .IMAFWriteDataM(store_value),.LittleEndianWriteDataM(replicated_store));
  logic mem_valid,mem_write,mem_ready=1,mem_error=0;
  logic [55:0] mem_addr;
  logic [63:0] mem_wdata,mem_rdata;
  logic [7:0] mem_strb;
  logic dma_valid=0,dma_write=0;
  logic [63:0] dma_addr=0,dma_wdata=0;
  logic [2:0] dma_size=0;
  logic [63:0] memory_word=64'ha7b6c5d4e3f20188;
  integer memory_writes=0,memory_beats=0;
  integer paper_beats=0;
  assign mem_rdata=memory_word;
  always @(posedge clk) if(!reset&&mem_valid&&mem_ready) memory_beats<=memory_beats+1;
  always @(posedge clk) if(!reset&&soc.dev_valid&&soc.paper_sel&&soc.paper_ready)
    paper_beats<=paper_beats+1;
  always @(posedge clk) if(!reset&&mem_valid&&mem_ready&&mem_write&&!mem_error) begin
    for(integer i=0;i<8;i++) if(mem_strb[i]) memory_word[i*8+:8]<=mem_wdata[i*8+:8];
    memory_writes<=memory_writes+1;
  end
  lemma_soc soc(.clk,.reset,.preload_valid(1'b0),.preload_index(9'd0),.preload_data(64'd0),
    .mem_valid,.mem_write,.mem_addr,.mem_wdata,.mem_strb,.mem_rdata,.mem_ready,.mem_error,
    .uart_rx_valid(1'b0),.uart_rx_data(8'd0),.descriptor(2048'd0),.sample_valid(1'b0),
    .sample_time(64'd0),.sample_x(64'd0),.sample_y(64'd0),.sample_pressure(64'd0),
    .sample_flags(64'd0),.sample_tool(64'd0),.sample_buttons(64'd0),
    .fb_ready(1'b1),.fb_error(1'b0),.fb_rdata(8'd0),.panel_ready(1'b1),
    .media_ready(1'b0),.media_error(1'b0),.media_rdata(4096'd0));

  task automatic mmio_write(input logic [11:0] offset,input logic [31:0] value);
    @(negedge clk);bus_valid=1;bus_write=1;bus_address=56'(BLOCK_BASE)+offset;
    bus_size=2;store_value={32'd0,value};#1;
    if(!soc.compute.hready||soc.compute.hresp) $fatal(1,"MMIO transfer did not acknowledge");
    @(posedge clk);#1;@(negedge clk);bus_valid=0;bus_write=0;#1;
  endtask
  task automatic block_status(input logic [31:0] expected);
    @(negedge clk);bus_valid=1;bus_write=0;bus_address=56'(BLOCK_BASE)+112;bus_size=2;#1;
    if(soc.block_rdata!=={32'd0,expected})
      $fatal(1,"QueueNum AHB SW rejected: status=%h expected=%h actual replicated HWDATA=%h",
        soc.block_rdata,expected,replicated_store);
    @(negedge clk);bus_valid=0;#1;
  endtask
  task automatic paper_transfer(input bit writing,input logic[11:0] offset,
      input logic[2:0] size,input logic[63:0] value,input logic[63:0] expected,
      input bit rejected=0);
    integer beats,waits,error_waits;
    beats=paper_beats;waits=0;error_waits=0;
    @(negedge clk);bus_valid=1;bus_write=writing;bus_address=56'(PAPER_BASE)+offset;
    bus_size=size;store_value=value;#1;
    if(soc.compute.hready||soc.compute.hresp)
      $fatal(1,"PAPER registered request acknowledged before capture");
    while(!soc.compute.hready) begin
      if(soc.compute.hresp)error_waits++;
      @(posedge clk);#1;waits++;
      if(waits>64)$fatal(1,"PAPER bounded AHB response missing");
    end
    if(soc.compute.hresp!==rejected||error_waits!=(rejected?1:0))
      $fatal(1,"PAPER two-cycle AHB error response differs");
    if(!writing&&!rejected&&soc.compute.hrdata!==expected)
      $fatal(1,"PAPER AHB literal read differs");
    @(posedge clk);#1;@(negedge clk);bus_valid=0;bus_write=0;#1;
    if(paper_beats!=beats+1||soc.compute.dev_error_pending)
      $fatal(1,"PAPER terminal AHB response repeated or retained a request");
  endtask
  task automatic paper_bridge;
    integer beats;
    // Use the actual framebuffer clearing engine, never force controller
    // state. The hart remains reset only in this independent fabric bench.
    repeat(327690)@(negedge clk);
    paper_transfer(0,0,3,0,64'd1280331856);
    paper_transfer(0,32,3,0,512);
    paper_transfer(1,2056,3,64'h0123456789abcdef,0);
    paper_transfer(0,2056,3,0,64'h0123456789abcdef);
    paper_transfer(0,64,2,0,0,1);
    paper_transfer(0,24,3,0,0);
    paper_transfer(1,64,2,7,0,1);
    paper_transfer(0,24,3,0,1);
    // Reset between capture and peripheral acknowledgement cancels the
    // pending write. Its value must never appear in the reset staging bank.
    beats=paper_beats;
    @(negedge clk);bus_valid=1;bus_write=1;bus_address=56'(PAPER_BASE)+2056;
    bus_size=3;store_value=19;#1;
    if(soc.compute.hready)$fatal(1,"PAPER reset fixture acknowledged before capture");
    @(posedge clk);#1;@(negedge clk);reset=1;bus_valid=0;bus_write=0;
    repeat(2)@(posedge clk);
    @(negedge clk);reset=0;#1;
    paper_transfer(0,2056,3,0,64'hffffffffffffffff);
    if(paper_beats!=beats+1)$fatal(1,"PAPER captured write survived global reset");
    // An abandoned read must not supply data/ready to its replacement.
    beats=paper_beats;
    @(negedge clk);bus_valid=1;bus_write=0;bus_address=56'(PAPER_BASE)+2056;bus_size=3;#1;
    @(posedge clk);#1;
    if(soc.compute.hready)$fatal(1,"PAPER read cancellation fixture already completed");
    @(negedge clk);bus_valid=0;@(posedge clk);#1;
    paper_transfer(0,0,3,0,64'd1280331856);
    if(paper_beats!=beats+1)$fatal(1,"PAPER abandoned read supplied a terminal response");
    $display("PAPER registered MMIO AHB error retention single completion reset cancellation PASS");
  endtask
  task automatic read_dma(input logic [2:0] size,input logic [2:0] lane,input logic [63:0] expected);
    @(negedge clk);dma_valid=1;dma_write=0;dma_size=size;dma_addr=FRAME_POOL_BASE+lane;
    bus_valid=1;bus_write=0;bus_address=56'(FRAME_POOL_BASE+256);bus_size=3;mem_ready=0;#1;
    repeat(3) begin
      if(soc.dma_ready||soc.cpu_mem_ready||!mem_valid||mem_addr!==56'(FRAME_POOL_BASE))
        $fatal(1,"DMA/CPU backpressure or aligned address failed");
      @(negedge clk);#1;
    end
    mem_ready=1;#1;
    if(!soc.dma_ready||soc.cpu_mem_ready||soc.dma_error||soc.dma_rdata!==expected)
      $fatal(1,"narrow DMA read retained adjacent bytes: size=%d lane=%d observed=%h expected=%h",
        size,lane,soc.dma_rdata,expected);
    @(posedge clk);#1;@(negedge clk);dma_valid=0;#1;
    if(!soc.cpu_mem_ready||mem_addr!==56'(FRAME_POOL_BASE+256))
      $fatal(1,"CPU data phase did not resume after DMA handshake");
    bus_valid=0;#1;
  endtask
  task automatic write_dma(input logic [2:0] size,input logic [2:0] lane,
      input logic [63:0] value,input logic [63:0] expected);
    integer before_writes;
    before_writes=memory_writes;
    @(negedge clk);dma_valid=1;dma_write=1;dma_size=size;dma_addr=FRAME_POOL_BASE+lane;
    dma_wdata=value;mem_ready=0;#1;
    repeat(3) begin
      if(soc.dma_ready||memory_writes!=before_writes) $fatal(1,"stalled DMA write committed");
      @(negedge clk);#1;
    end
    mem_ready=1;#1;@(posedge clk);#1;@(negedge clk);dma_valid=0;#1;
    if(memory_word!==expected||memory_writes!=before_writes+1)
      $fatal(1,"DMA write corrupted adjacent lanes: observed=%h expected=%h writes=%d",memory_word,expected,memory_writes);
  endtask
  task automatic cpu_then_dma;
    integer beats,writes;
    beats=memory_beats;writes=memory_writes;
    @(negedge clk);bus_valid=1;bus_write=1;bus_size=3;
    bus_address=56'(FRAME_POOL_BASE+256);store_value=64'h1122334455667788;
    dma_valid=0;mem_ready=0;#1;
    @(posedge clk);#1;@(negedge clk);
    dma_valid=1;dma_write=1;dma_addr=FRAME_POOL_BASE+4;dma_size=2;dma_wdata=64'hdeadbeef;#1;
    repeat(3) begin
      if(!mem_valid||mem_addr!==56'(FRAME_POOL_BASE+256)||!mem_write||
         mem_wdata!==64'h1122334455667788||mem_strb!==8'hff||
         soc.dma_ready||soc.cpu_mem_ready||memory_beats!=beats||memory_writes!=writes)
        $fatal(1,"ARB stalled CPU beat stolen by newly asserted DMA");
      @(negedge clk);#1;
    end
    // An inactive master can change its next request without changing the
    // beat already owned by the stalled CPU.
    dma_addr=FRAME_POOL_BASE+3;dma_size=0;dma_wdata=64'haa;mem_ready=1;#1;
    if(!soc.cpu_mem_ready||soc.dma_ready||mem_addr!==56'(FRAME_POOL_BASE+256))
      $fatal(1,"ARB CPU owner did not receive its terminal response");
    @(posedge clk);#1;@(negedge clk);bus_valid=0;bus_write=0;#1;
    if(!soc.dma_ready||soc.cpu_mem_ready||mem_addr!==56'(FRAME_POOL_BASE)||
       mem_wdata!==64'h00000000aa000000||mem_strb!==8'h08)
      $fatal(1,"ARB pending DMA did not follow completed CPU beat");
    @(posedge clk);#1;@(negedge clk);dma_valid=0;#1;
    if(mem_valid||memory_beats!=beats+2||memory_writes!=writes+2||
       memory_word!==64'h11223344aa667788)
      $fatal(1,"ARB CPU/DMA beats duplicated or write payload changed");
  endtask
  task automatic dma_then_cpu;
    integer beats,writes;
    beats=memory_beats;writes=memory_writes;
    @(negedge clk);dma_valid=1;dma_write=0;dma_size=1;dma_addr=FRAME_POOL_BASE+2;
    bus_valid=0;mem_ready=0;#1;
    @(posedge clk);#1;@(negedge clk);bus_valid=1;bus_write=1;bus_size=3;
    bus_address=56'(FRAME_POOL_BASE+512);store_value=64'h0123456789abcdef;#1;
    repeat(3) begin
      if(!mem_valid||mem_write||mem_addr!==56'(FRAME_POOL_BASE)||
         mem_strb!==8'h0c||soc.dma_ready||soc.cpu_mem_ready||memory_beats!=beats)
        $fatal(1,"ARB stalled DMA beat changed after CPU arrival");
      @(negedge clk);#1;
    end
    bus_address=56'(FRAME_POOL_BASE+768);store_value=64'hfedcba9876543210;mem_ready=1;#1;
    if(!soc.dma_ready||soc.cpu_mem_ready||soc.dma_rdata!==64'haa66)
      $fatal(1,"ARB held DMA lane/size/owner response changed");
    @(posedge clk);#1;@(negedge clk);dma_valid=0;#1;
    if(!soc.cpu_mem_ready||mem_addr!==56'(FRAME_POOL_BASE+768)||
       !mem_write||mem_wdata!==64'hfedcba9876543210||mem_strb!==8'hff)
      $fatal(1,"ARB pending CPU did not follow completed DMA beat");
    @(posedge clk);#1;@(negedge clk);bus_valid=0;bus_write=0;#1;
    if(mem_valid||memory_beats!=beats+2||memory_writes!=writes+1||memory_word!==64'hfedcba9876543210)
      $fatal(1,"ARB DMA/CPU beats duplicated or write payload changed");
  endtask
  task automatic local_dma_error;
    integer beats;
    beats=memory_beats;
    @(negedge clk);dma_valid=1;dma_write=0;dma_size=2;dma_addr=FRAME_POOL_BASE+1;
    bus_valid=1;bus_write=0;bus_size=3;bus_address=56'(FRAME_POOL_BASE+1024);#1;
    if(mem_valid||!soc.dma_ready||!soc.dma_error||soc.cpu_mem_ready)
      $fatal(1,"ARB invalid DMA escaped bounded alignment fault");
    @(posedge clk);#1;@(negedge clk);dma_valid=0;#1;
    if(memory_beats!=beats||!mem_valid||!soc.cpu_mem_ready||soc.cpu_mem_error)
      $fatal(1,"ARB local DMA fault consumed/poisoned CPU memory beat");
    @(posedge clk);#1;@(negedge clk);bus_valid=0;#1;
    if(memory_beats!=beats+1) $fatal(1,"ARB local fault external beat count differs");
  endtask
  task automatic terminal_errors;
    integer beats,writes;
    beats=memory_beats;writes=memory_writes;
    @(negedge clk);bus_valid=1;bus_write=1;bus_size=3;
    bus_address=56'(FRAME_POOL_BASE+1280);store_value=64'hffffffffffffffff;
    dma_valid=0;mem_ready=0;mem_error=0;#1;
    repeat(2) begin
      if(soc.cpu_mem_ready||soc.cpu_mem_error||soc.compute.hresp||memory_beats!=beats)
        $fatal(1,"ARB CPU consumed error before terminal external handshake");
      @(negedge clk);#1;
    end
    mem_ready=1;mem_error=1;#1;
    if(!soc.cpu_mem_ready||!soc.cpu_mem_error||!soc.compute.hresp||soc.compute.hready)
      $fatal(1,"ARB CPU external error first AHB phase differs");
    @(posedge clk);#1;
    if(mem_valid||!soc.cpu_mem_ready||!soc.cpu_mem_error||!soc.compute.hresp||!soc.compute.hready)
      $fatal(1,"ARB failed CPU beat reissued during second AHB ERROR phase");
    @(negedge clk);dma_valid=1;dma_write=0;dma_size=2;dma_addr=FRAME_POOL_BASE+4;
    mem_ready=0;mem_error=0;#1;
    if(!mem_valid||mem_addr!==56'(FRAME_POOL_BASE)||
       !soc.cpu_mem_ready||!soc.cpu_mem_error||soc.dma_ready)
      $fatal(1,"ARB buffered CPU error changed after DMA arrival");
    @(posedge clk);#1;@(negedge clk);bus_valid=0;bus_write=0;mem_ready=1;mem_error=1;#1;
    if(!soc.dma_ready||!soc.dma_error||soc.cpu_mem_ready||soc.cpu_mem_error)
      $fatal(1,"ARB DMA terminal error delivered to wrong owner");
    @(posedge clk);#1;@(negedge clk);dma_valid=0;mem_error=0;#1;
    if(mem_valid||memory_beats!=beats+2||memory_writes!=writes)
      $fatal(1,"ARB error beat duplicated or failed write committed");
  endtask
  task automatic global_reset;
    integer beats,writes;
    beats=memory_beats;writes=memory_writes;
    for(integer owner=0;owner<2;owner++) begin
      @(negedge clk);mem_ready=0;bus_valid=(owner==0);bus_write=1;bus_size=3;
      bus_address=56'(FRAME_POOL_BASE+1536);store_value=64'hbadbadbadbadbad0;
      dma_valid=(owner==1);dma_write=1;dma_size=3;dma_addr=FRAME_POOL_BASE+1792;dma_wdata=64'hbadbadbadbadbad1;#1;
      @(posedge clk);#1;@(negedge clk);reset=1;mem_ready=1;#1;
      if(mem_valid||soc.cpu_mem_ready||soc.dma_ready)
        $fatal(1,"ARB global reset allowed a held external transaction");
      repeat(2) @(posedge clk);
      @(negedge clk);bus_valid=0;bus_write=0;dma_valid=0;reset=0;#1;
      if(mem_valid||soc.cpu_mem_error||soc.dma_error)
        $fatal(1,"ARB held request/error survived global reset");
      @(posedge clk);#1;
    end
    if(memory_beats!=beats||memory_writes!=writes)
      $fatal(1,"ARB reset emitted deferred write/response");
  endtask
  initial begin
    // Only the conformance bench overrides bus pins. No such hook exists in
    // the maintained simulator or executable target software.
    force soc.compute.core.reset=1'b1;
    force soc.compute.valid_d=bus_valid;
    force soc.compute.write_d=bus_write;
    force soc.compute.addr_d=bus_address;
    force soc.compute.size_d=bus_size;
    force soc.compute.hwdata=replicated_store;
    force soc.compute.hwstrb=8'hff;
    force soc.dma_valid=dma_valid;
    force soc.dma_write=dma_write;
    force soc.dma_addr=dma_addr;
    force soc.dma_size=dma_size;
    force soc.dma_wdata=dma_wdata;
    repeat(3) @(negedge clk);reset=0;#1;
    if(!$test$plusargs("dma-only")&&!$test$plusargs("arbitration-only")&&!$test$plusargs("error-only")) begin
      mmio_write(36,0);mmio_write(32,512);mmio_write(36,1);mmio_write(32,1);mmio_write(112,11);
      block_status(11);mmio_write(56,8);block_status(11);
      if(soc.blockdev.queue_num!==8) $fatal(1,"QueueNum did not retain the actual SW8");
      mmio_write(68,1);mmio_write(112,15);block_status(15);
      for(integer size=0;size<4;size++) begin
        @(negedge clk);bus_valid=0;bus_size=3'(size);store_value=64'h0123456789abcdef;
        bus_address=56'(BLOCK_BASE)+(size==0?3:size==1?6:size==2?4:0);#1;
        case(size)
          0: if(soc.dev_wdata!==64'hef) $fatal(1,"byte MMIO mask failed");
          1: if(soc.dev_wdata!==64'hcdef) $fatal(1,"halfword MMIO mask failed");
          2: if(soc.dev_wdata!==64'h89abcdef) $fatal(1,"word MMIO mask failed");
          3: if(soc.dev_wdata!==64'h0123456789abcdef) $fatal(1,"doubleword MMIO changed");
        endcase
      end
      $display("BUS actual CVW replicated SW QueueNum and MMIO byte/half/word/double lanes PASS");
      paper_bridge();
    end
    if(!$test$plusargs("arbitration-only")&&!$test$plusargs("error-only")) begin
      read_dma(0,3,64'he3);read_dma(1,2,64'he3f2);read_dma(2,4,64'ha7b6c5d4);
      write_dma(0,3,64'h5a,64'ha7b6c5d45af20188);
      write_dma(1,2,64'h1234,64'ha7b6c5d412340188);
      write_dma(2,4,64'hdeadbeef,64'hdeadbeef12340188);
      read_dma(0,3,64'h12);read_dma(1,2,64'h1234);read_dma(2,4,64'hdeadbeef);
    end
    if(!$test$plusargs("error-only")) begin cpu_then_dma();dma_then_cpu();local_dma_error();end
    terminal_errors();global_reset();
    $display("ARB held CPU/DMA owner payload backpressure terminal errors reset quiescence PASS");
    $display("DMA narrow reads adjacent bytes write strobes ready backpressure CPU resume PASS");
    $finish;
  end
  initial begin #10000000;$fatal(1,"bus lane bench deadline");end
endmodule
