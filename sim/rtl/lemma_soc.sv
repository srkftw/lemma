// SPDX-License-Identifier: Apache-2.0
// Reusable silicon development motherboard: CVW compute, real custom controllers,
// external working-memory port, external framebuffer SRAM, raw medium and panel ports.
module lemma_soc #(parameter bit REGISTER_RAM=0) (
 input logic clk, reset,
 input logic preload_valid,
 input logic [8:0] preload_index,
 input logic [63:0] preload_data,
 output logic register_memory_enabled,
 output logic mem_valid,mem_write,
 output logic [55:0] mem_addr,
 output logic [63:0] mem_wdata,
 output logic [7:0] mem_strb,
 input logic [63:0] mem_rdata,
 input logic mem_ready,mem_error,
 input logic uart_rx_valid,
 input logic [7:0] uart_rx_data,
 output logic uart_rx_ready,uart_tx_valid,
 output logic [7:0] uart_tx_data,
 output logic finish_valid,
 output logic [31:0] finish_code,
 output logic [63:0] timer_ticks,debug_pc,
 output logic [1:0] debug_privilege,
 output logic debug_retire,debug_trap,
 output logic [63:0] debug_cause,
 input logic [2047:0] descriptor,
 input logic sample_valid,
 output logic sample_ready,sample_accepted,
 input logic [63:0] sample_time,sample_x,sample_y,sample_pressure,sample_flags,sample_tool,sample_buttons,
 output logic fb_valid,fb_write,
 output logic [31:0] fb_addr,
 output logic [7:0] fb_wdata,
 input logic fb_ready,fb_error,
 input logic [7:0] fb_rdata,
 output logic panel_valid,
 input logic panel_ready,
 output logic [31:0] panel_x,panel_y,
 output logic [3:0] panel_gray,
 output logic panel_complete,panel_abort,
 output logic [63:0] panel_sequence,
 output logic media_valid,
 output logic [2:0] media_kind,
 output logic [63:0] media_sector,
 output logic [4095:0] media_wdata,
 input logic media_ready,media_error,
 input logic [4095:0] media_rdata
);
 import lemma_silicon_binding::*;
 logic dev_valid,dev_write,dev_ready,dev_error;
 logic [31:0] dev_addr;
 logic [2:0] dev_size;
 logic [63:0] dev_wdata,dev_rdata;
 logic cpu_mem_valid,cpu_mem_write,cpu_mem_ready,cpu_mem_error;
 logic [55:0] cpu_mem_addr;
 logic [63:0] cpu_mem_wdata,cpu_mem_rdata;
 logic [7:0] cpu_mem_strb;
 logic dma_valid,dma_write,dma_ready,dma_error;
 logic [63:0] dma_addr,dma_wdata,dma_rdata;
 logic [2:0] dma_size;
 logic [63:0] pen_rdata,paper_rdata,block_rdata;
 logic pen_ready,paper_ready,block_ready,pen_error,paper_error,block_error;
 logic pen_irq,paper_irq,block_irq;
 logic [31:0] irqs;
 logic pen_sel,paper_sel,block_sel,dma_grant,dma_alignment,dma_span;
 logic external_ready,external_error;
 logic [63:0] external_rdata;
 assign register_memory_enabled=REGISTER_RAM;
 generate if(REGISTER_RAM) begin: small_ram
   logic small_ready,small_error;
   logic [63:0] small_rdata;
   lemma_register_ram memory(.clk,.valid(mem_valid),.write(mem_write),.addr(mem_addr),
      .wdata(mem_wdata),.strb(mem_strb),.rdata(small_rdata),.ready(small_ready),.error(small_error),
      .preload_valid,.preload_index,.preload_data);
   assign external_ready=mem_addr<RESET_VECTOR+ROM_BYTES?mem_ready:small_ready;
   assign external_error=mem_addr<RESET_VECTOR+ROM_BYTES?mem_error:small_error;
   assign external_rdata=mem_addr<RESET_VECTOR+ROM_BYTES?mem_rdata:small_rdata;
 end else begin: large_external
   assign external_ready=mem_ready;assign external_error=mem_error;assign external_rdata=mem_rdata;
 end endgenerate
 assign pen_sel=dev_addr>=PEN_BASE&&dev_addr<PEN_BASE+PEN_SPAN;
 assign paper_sel=dev_addr>=PAPER_BASE&&dev_addr<PAPER_BASE+PAPER_SPAN;
 assign block_sel=dev_addr>=BLOCK_BASE&&dev_addr<BLOCK_BASE+BLOCK_SPAN;
 assign dev_rdata=pen_sel?pen_rdata:paper_sel?paper_rdata:block_rdata;
 assign dev_ready=pen_sel?pen_ready:paper_sel?paper_ready:block_sel?block_ready:1'b1;
 assign dev_error=pen_sel?pen_error:paper_sel?paper_error:block_sel?block_error:1'b1;
 assign irqs=(32'(pen_irq)<<PEN_IRQ)|(32'(paper_irq)<<PAPER_IRQ)|(32'(block_irq)<<BLOCK_IRQ);
 lemma_compute compute(
   .clk,.reset,.mem_valid(cpu_mem_valid),.mem_write(cpu_mem_write),.mem_addr(cpu_mem_addr),
   .mem_wdata(cpu_mem_wdata),.mem_strb(cpu_mem_strb),.mem_rdata(cpu_mem_rdata),
   .mem_ready(cpu_mem_ready),.mem_error(cpu_mem_error),.dev_valid,.dev_write,.dev_addr,.dev_size,
   .dev_wdata,.dev_rdata,.dev_ready,.dev_error,.external_irqs(irqs),.uart_rx_valid,.uart_rx_data,
   .uart_rx_ready,.uart_tx_valid,.uart_tx_data,.finish_valid,.finish_code,.timer_ticks,
   .debug_pc,.debug_privilege,.debug_retire,.debug_trap,.debug_cause
 );
 lemma_pen #(.FIFO_DEPTH(int'(PEN_FIFO)),.PRESSURE_MAX(int'(PRESSURE_MAX))) pen(
   .clk,.reset_n(!reset),.valid(dev_valid&&pen_sel),.write(dev_valid&&pen_sel&&dev_write),
   .addr((dev_valid&&pen_sel)?dev_addr[11:0]:12'd0),
   .size((dev_valid&&pen_sel)?dev_size:3'd0),.wdata((dev_valid&&pen_sel)?dev_wdata:64'd0),
   .rdata(pen_rdata),.ready(pen_ready),.error(pen_error),.irq(pen_irq),
   .now_ticks(timer_ticks),.sample_valid,.sample_ready,.sample_time,.sample_x,.sample_y,
   .sample_pressure,.sample_flags,.sample_tool,.sample_buttons,.sample_accepted
 );
 lemma_paper #(.WIDTH(int'(WIDTH)),.HEIGHT(int'(HEIGHT))) paper(
   .clk,.reset_n(!reset),.valid(dev_valid&&paper_sel),.write(dev_valid&&paper_sel&&dev_write),
   .addr((dev_valid&&paper_sel)?dev_addr[11:0]:12'd0),
   .size((dev_valid&&paper_sel)?dev_size:3'd0),.wdata((dev_valid&&paper_sel)?dev_wdata:64'd0),
   .rdata(paper_rdata),.ready(paper_ready),.error(paper_error),.irq(paper_irq),
   .now_ticks(timer_ticks),.descriptor,.fb_valid,.fb_write,.fb_addr,.fb_wdata,.fb_ready,.fb_error,.fb_rdata,
   .panel_valid,.panel_ready,.panel_x,.panel_y,.panel_gray,.panel_complete,.panel_abort,.panel_sequence
 );
 lemma_block #(.DMA_BASE(FRAME_POOL_BASE),.DMA_BYTES(FRAME_POOL_BYTES)) blockdev(
   .clk,.reset_n(!reset),.valid(dev_valid&&block_sel),.write(dev_valid&&block_sel&&dev_write),
   .addr((dev_valid&&block_sel)?dev_addr[11:0]:12'd0),
   .size((dev_valid&&block_sel)?dev_size:3'd0),.wdata((dev_valid&&block_sel)?dev_wdata:64'd0),
   .rdata(block_rdata),.ready(block_ready),.error(block_error),.irq(block_irq),
   .dma_valid,.dma_write,.dma_addr,.dma_wdata,.dma_size,.dma_ready,.dma_error,.dma_rdata,
   .media_valid,.media_kind,.media_sector,.media_wdata,.media_ready,.media_error,.media_rdata
 );
 // One-beat arbitration: DMA wins a ready memory beat, CPU data phase holds.
 // D-cache is disabled; CPU data and DMA touch this one byte-coherent interface.
 // The 4KiB instruction cache remains subject to the guest's actual fence.i.
 assign dma_grant=dma_valid;
 assign dma_alignment=dma_size<=3&&(dma_addr&((64'd1<<dma_size)-1))==0;
 assign dma_span=dma_addr>=FRAME_POOL_BASE && dma_addr<=FRAME_POOL_BASE+FRAME_POOL_BYTES-(64'd1<<dma_size);
 assign mem_valid=dma_grant?(dma_alignment&&dma_span):cpu_mem_valid;
 assign mem_write=dma_grant?dma_write:cpu_mem_write;
 assign mem_addr=dma_grant?{dma_addr[55:3],3'b000}:cpu_mem_addr;
 assign mem_wdata=dma_grant?(dma_wdata<<(8*dma_addr[2:0])):cpu_mem_wdata;
 assign mem_strb=dma_grant?(8'((9'd1<<(1<<dma_size))-1)<<dma_addr[2:0]):cpu_mem_strb;
 assign cpu_mem_ready=!dma_grant&&external_ready;
 assign cpu_mem_error=!dma_grant&&external_error;
 assign cpu_mem_rdata=external_rdata;
 assign dma_ready=dma_grant&&((dma_alignment&&dma_span)?external_ready:1'b1);
 assign dma_error=dma_grant&&(!dma_alignment||!dma_span||external_error);
 assign dma_rdata=external_rdata>>(8*dma_addr[2:0]);
endmodule
