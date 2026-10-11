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
  integer memory_writes=0;
  assign mem_rdata=memory_word;
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
  initial begin
    // Only the conformance bench overrides bus pins. No such hook exists in
    // the maintained simulator or executable target software.
    force soc.compute.core.reset=1'b1;
    force soc.compute.valid_d=bus_valid;
    force soc.compute.write_d=bus_write;
    force soc.compute.addr_d=bus_address;
    force soc.compute.size_d=bus_size;
    force soc.compute.hwdata=replicated_store;
    force soc.dma_valid=dma_valid;
    force soc.dma_write=dma_write;
    force soc.dma_addr=dma_addr;
    force soc.dma_size=dma_size;
    force soc.dma_wdata=dma_wdata;
    repeat(3) @(negedge clk);reset=0;#1;
    if(!$test$plusargs("dma-only")) begin
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
    end
    read_dma(0,3,64'he3);read_dma(1,2,64'he3f2);read_dma(2,4,64'ha7b6c5d4);
    write_dma(0,3,64'h5a,64'ha7b6c5d45af20188);
    write_dma(1,2,64'h1234,64'ha7b6c5d412340188);
    write_dma(2,4,64'hdeadbeef,64'hdeadbeef12340188);
    read_dma(0,3,64'h12);read_dma(1,2,64'h1234);read_dma(2,4,64'hdeadbeef);
    $display("DMA narrow reads adjacent bytes write strobes ready backpressure CPU resume PASS");
    $finish;
  end
  initial begin #10000;$fatal(1,"bus lane bench deadline");end
endmodule
