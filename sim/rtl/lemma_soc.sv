// SPDX-License-Identifier: Apache-2.0
// Reusable silicon development motherboard: CVW compute, real custom controllers,
// external working-memory port, external framebuffer SRAM, raw medium and panel ports.
module lemma_soc #(parameter bit REGISTER_RAM=0) (
 input logic clk, reset,
 input logic [1:0] power_reset_cause,
 input logic raw_button_level,
 output logic power_suspended,power_cancel_pen,
 output logic [63:0] power_error,power_epoch,power_events,power_wake_cause,
 output logic [1:0] power_cause,
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
 output logic panel_drive_valid,panel_power_enable,panel_gate_clock,panel_source_clock,
 output logic [1:0] panel_drive_phase,panel_drive_code,
 output logic [31:0] panel_drive_x,panel_drive_y,
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
 logic [63:0] pen_rdata,paper_rdata,block_rdata,power_rdata;
 logic pen_ready,paper_ready,block_ready,pen_error,paper_error,block_error;
 logic pen_irq,paper_irq,block_irq,power_irq,power_ready,power_bus_error,paper_busy,block_busy,pen_sample_ready;
 logic [5:0] power_busy_sources;
 logic [1:0] power_event_flags;
 logic [31:0] irqs;
 logic pen_sel,paper_sel,block_sel,power_sel,dma_grant,dma_alignment,dma_span;
 logic external_ready,external_error;
 logic [63:0] external_rdata;
 logic port_held,held_dma,held_write;
 logic [55:0] held_addr;
 logic [63:0] held_wdata,cpu_error_rdata;
 logic [7:0] held_strb;
 logic [2:0] held_lane,held_size;
 logic cpu_error_pending,selected_valid,selected_fault;
 logic [2:0] active_dma_lane,active_dma_size;
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
 assign power_sel=POWER_ENABLED!=0&&dev_addr>=POWER_BASE&&dev_addr<POWER_BASE+POWER_SPAN;
 assign paper_sel=dev_addr>=PAPER_BASE&&dev_addr<PAPER_BASE+PAPER_SPAN&&!power_sel;
 assign block_sel=dev_addr>=BLOCK_BASE&&dev_addr<BLOCK_BASE+BLOCK_SPAN;
 assign dev_rdata=power_sel?power_rdata:pen_sel?pen_rdata:paper_sel?paper_rdata:block_rdata;
 assign dev_ready=power_sel?power_ready:pen_sel?pen_ready:paper_sel?paper_ready:block_sel?block_ready:1'b1;
 assign dev_error=power_sel?power_bus_error:pen_sel?pen_error:paper_sel?paper_error:block_sel?block_error:1'b1;
 assign irqs=(32'(pen_irq)<<PEN_IRQ)|(32'(paper_irq)<<PAPER_IRQ)|(32'(block_irq)<<BLOCK_IRQ)|(32'(power_irq)<<POWER_IRQ);
 lemma_compute compute(
   .clk,.reset,.mem_valid(cpu_mem_valid),.mem_write(cpu_mem_write),.mem_addr(cpu_mem_addr),
   .mem_wdata(cpu_mem_wdata),.mem_strb(cpu_mem_strb),.mem_rdata(cpu_mem_rdata),
   .mem_ready(cpu_mem_ready),.mem_error(cpu_mem_error),.dev_valid,.dev_write,.dev_addr,.dev_size,
   .dev_wdata,.dev_rdata,.dev_ready,.dev_error,.external_irqs(irqs),.uart_rx_valid,.uart_rx_data,
   .uart_rx_ready,.uart_tx_valid,.uart_tx_data,.finish_valid,.finish_code,.timer_ticks,
   .debug_pc,.debug_privilege,.debug_retire,.debug_trap,.debug_cause
 );
 lemma_pen #(.FIFO_DEPTH(int'(PEN_FIFO)),.PRESSURE_MAX(int'(PRESSURE_MAX))) pen(
   .clk,.reset_n(!reset),.valid((dev_valid&&pen_sel)||power_cancel_pen),.write((dev_valid&&pen_sel&&dev_write)||power_cancel_pen),
   .addr(power_cancel_pen?12'd104:(dev_valid&&pen_sel)?dev_addr[11:0]:12'd0),
   .size(power_cancel_pen?3'd3:(dev_valid&&pen_sel)?dev_size:3'd0),.wdata(power_cancel_pen?64'd1:(dev_valid&&pen_sel)?dev_wdata:64'd0),
   .rdata(pen_rdata),.ready(pen_ready),.error(pen_error),.irq(pen_irq),
   .now_ticks(timer_ticks),.sample_valid(sample_valid&&!power_suspended&&!power_cancel_pen),.sample_ready(pen_sample_ready),.sample_time,.sample_x,.sample_y,
   .sample_pressure,.sample_flags,.sample_tool,.sample_buttons,.sample_accepted
 );
 lemma_paper #(.WIDTH(int'(WIDTH)),.HEIGHT(int'(HEIGHT)),.ENABLE_SEQUENCER(PAPER_SEQUENCER!=0)) paper(
   .clk,.reset_n(!reset),.valid(dev_valid&&paper_sel),.write(dev_valid&&paper_sel&&dev_write),
   .addr((dev_valid&&paper_sel)?dev_addr[11:0]:12'd0),
   .size((dev_valid&&paper_sel)?dev_size:3'd0),.wdata((dev_valid&&paper_sel)?dev_wdata:64'd0),
   .rdata(paper_rdata),.ready(paper_ready),.error(paper_error),.irq(paper_irq),.controller_busy(paper_busy),
   .now_ticks(timer_ticks),.descriptor,.fb_valid,.fb_write,.fb_addr,.fb_wdata,.fb_ready,.fb_error,.fb_rdata,
   .panel_valid,.panel_ready,.panel_x,.panel_y,.panel_gray,.panel_complete,.panel_abort,.panel_sequence,
   .panel_drive_valid,.panel_power_enable,.panel_gate_clock,.panel_source_clock,
   .panel_drive_phase,.panel_drive_code,.panel_drive_x,.panel_drive_y
 );
 lemma_block #(.DMA_BASE(FRAME_POOL_BASE),.DMA_BYTES(FRAME_POOL_BYTES)) blockdev(
   .clk,.reset_n(!reset),.valid(dev_valid&&block_sel),.write(dev_valid&&block_sel&&dev_write),
   .addr((dev_valid&&block_sel)?dev_addr[11:0]:12'd0),
   .size((dev_valid&&block_sel)?dev_size:3'd0),.wdata((dev_valid&&block_sel)?dev_wdata:64'd0),
   .rdata(block_rdata),.ready(block_ready),.error(block_error),.irq(block_irq),.busy(block_busy),
   .dma_valid,.dma_write,.dma_addr,.dma_wdata,.dma_size,.dma_ready,.dma_error,.dma_rdata,
   .media_valid,.media_kind,.media_sector,.media_wdata,.media_ready,.media_error,.media_rdata
 );
 assign sample_ready=pen_sample_ready&&!power_suspended&&!power_cancel_pen;
 assign power_busy_sources={media_valid,(dma_valid||!pen_ready),port_held,block_irq,block_busy,paper_busy};
 generate if(POWER_ENABLED!=0) begin: control_domain
   lemma_power power(.clk,.reset,.reset_cause(power_reset_cause),.raw_button_level,
     .busy_sources(power_busy_sources),.valid(dev_valid&&power_sel),.write(dev_write),
     .addr(dev_addr[7:0]),.size(dev_size),.wdata(dev_wdata),.rdata(power_rdata),
     .ready(power_ready),.error(power_bus_error),.irq(power_irq),
     .suspended(power_suspended),.cancel_pen(power_cancel_pen),.fault(power_error),
     .epoch(power_epoch),.wake_cause(power_wake_cause),.cause(power_cause),.events(power_event_flags));
   assign power_events={62'b0,power_event_flags};
 end else begin: no_control_domain
   assign power_rdata=0;assign power_ready=1;assign power_bus_error=0;assign power_irq=0;
   assign power_suspended=0;assign power_cancel_pen=0;assign power_error=0;assign power_epoch=0;
   assign power_event_flags=0;assign power_events=0;assign power_wake_cause=0;assign power_cause=0;
 end endgenerate
 // DMA has priority only at an idle external port. A request which sees
 // backpressure retains its owner and complete beat until its response;
 // arrivals from the other master cannot replace an outstanding request.
 // D-cache is disabled; CPU data and DMA touch this one byte-coherent interface.
 // The 4KiB instruction cache remains subject to the guest's actual fence.i.
 assign dma_grant=port_held?held_dma:dma_valid;
 assign dma_alignment=dma_size<=3&&(dma_addr&((64'd1<<dma_size)-1))==0;
 assign dma_span=dma_addr>=FRAME_POOL_BASE && dma_addr<=FRAME_POOL_BASE+FRAME_POOL_BYTES-(64'd1<<dma_size);
 assign selected_valid=port_held?1'b1:dma_grant?dma_valid:(cpu_mem_valid&&!cpu_error_pending);
 assign selected_fault=!port_held&&dma_grant&&(!dma_alignment||!dma_span);
 assign mem_valid=!reset&&selected_valid&&!selected_fault;
 assign mem_write=port_held?held_write:dma_grant?dma_write:cpu_mem_write;
 assign mem_addr=port_held?held_addr:dma_grant?{dma_addr[55:3],3'b000}:cpu_mem_addr;
 assign mem_wdata=port_held?held_wdata:dma_grant?(dma_wdata<<(8*dma_addr[2:0])):cpu_mem_wdata;
 assign mem_strb=port_held?held_strb:dma_grant?(8'((9'd1<<(1<<dma_size))-1)<<dma_addr[2:0]):cpu_mem_strb;
 assign cpu_mem_ready=!reset&&(cpu_error_pending||(!dma_grant&&external_ready));
 assign cpu_mem_error=!reset&&(cpu_error_pending||(!dma_grant&&mem_valid&&external_ready&&external_error));
 assign cpu_mem_rdata=cpu_error_pending?cpu_error_rdata:external_rdata;
 assign dma_ready=!reset&&dma_grant&&(selected_fault||external_ready);
 assign dma_error=!reset&&dma_grant&&(selected_fault||(external_ready&&external_error));
 assign active_dma_lane=port_held?held_lane:dma_addr[2:0];
 assign active_dma_size=port_held?held_size:dma_size;
 // Return a right-justified transfer, rather than unrelated bytes from the
 // remainder of the shared 64-bit memory beat.
 assign dma_rdata=(external_rdata>>(8*active_dma_lane)) &
   (active_dma_size==0?64'hff:active_dma_size==1?64'hffff:active_dma_size==2?64'hffffffff:64'hffffffffffffffff);
 always_ff @(posedge clk) begin
   if(reset) begin
     port_held<=0;held_dma<=0;held_write<=0;held_addr<=0;held_wdata<=0;held_strb<=0;
     held_lane<=0;held_size<=0;cpu_error_pending<=0;cpu_error_rdata<=0;
   end else begin
     if(port_held) begin
       if(external_ready) port_held<=0;
     end else if(mem_valid&&!external_ready) begin
       port_held<=1;held_dma<=dma_grant;held_write<=mem_write;held_addr<=mem_addr;
       held_wdata<=mem_wdata;held_strb<=mem_strb;held_lane<=dma_addr[2:0];held_size<=dma_size;
     end
     // The AHB adapter needs two cycles for ERROR. Retain its terminal
     // response without issuing the failed external beat a second time.
     cpu_error_pending<=mem_valid&&!dma_grant&&external_ready&&external_error;
     if(mem_valid&&!dma_grant&&external_ready&&external_error) cpu_error_rdata<=external_rdata;
   end
 end
endmodule
