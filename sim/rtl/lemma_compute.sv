// SPDX-License-Identifier: Apache-2.0
// Lemma silicon development compute/fabric. Host ports carry only memory bytes,
// UART bytes and raw external interrupt wires; the RV64 core executes every instruction.
module lemma_compute import cvw::*; #(
  parameter int TIMER_DIV = int'(lemma_silicon_binding::CLOCK_HZ/lemma_silicon_binding::TIMEBASE_HZ)
)(
  input logic clk, reset,
  output logic mem_valid, mem_write,
  output logic [55:0] mem_addr,
  output logic [63:0] mem_wdata,
  output logic [7:0] mem_strb,
  input logic [63:0] mem_rdata,
  input logic mem_ready, mem_error,
  output logic dev_valid, dev_write,
  output logic [31:0] dev_addr,
  output logic [2:0] dev_size,
  output logic [63:0] dev_wdata,
  input logic [63:0] dev_rdata,
  input logic dev_ready, dev_error,
  input logic [31:0] external_irqs,
  input logic uart_rx_valid,
  input logic [7:0] uart_rx_data,
  output logic uart_rx_ready,
  output logic uart_tx_valid,
  output logic [7:0] uart_tx_data,
  output logic finish_valid,
  output logic [31:0] finish_code,
  output logic [63:0] timer_ticks,
  output logic [63:0] debug_pc,
  output logic [1:0] debug_privilege,
  output logic debug_retire,debug_trap,
  output logic [63:0] debug_cause
);
  import lemma_silicon_binding::*;
  `include "config.vh"
  `include "parameter-defs.vh"
  logic [55:0] haddr, addr_d;
  logic [63:0] hwdata, hrdata, mmio_data;
  logic [7:0] hwstrb;
  logic hwrite, hready, hresp, hclk, hresetn, lock;
  logic [2:0] hsize, burst, size_d;
  logic [3:0] prot;
  logic [1:0] trans;
  logic valid_d, write_d;
  logic [63:0] mtime, mtimecmp;
  logic [31:0] msip;
  logic [$clog2(TIMER_DIV+1)-1:0] timer_phase;
  logic sel_mem, sel_timer, sel_uart, sel_plic, sel_finish, sel_dev;
  logic [31:0] enables_m, enables_s, inflight;
  logic [2:0] priorities[31:0];
  logic [2:0] threshold_m, threshold_s;
  logic [31:0] pending;
  logic [1:0] uart_ier;
  logic uart_irq;
  logic [4:0] claim_m, claim_s;
  logic [63:0] write_value;
  logic bad_alignment, raw_error, response_ready, error_phase;
  logic dev_error_pending;
  logic [63:0] dev_error_data;
  logic timer_register, plic_register;
  integer i;

  wallypipelinedcore #(P) core(
    .clk, .reset, .MTimerInt(mtime >= mtimecmp), .MExtInt(claim_m != 0),
    .SExtInt(claim_s != 0), .MSwInt(msip[0]), .MTIME_CLINT(mtime),
    .HRDATA(hrdata), .HREADY(hready), .HRESP(hresp),
    .HCLK(hclk), .HRESETn(hresetn), .HADDR(haddr), .HWDATA(hwdata),
    .HWSTRB(hwstrb), .HWRITE(hwrite), .HSIZE(hsize), .HBURST(burst),
    .HPROT(prot), .HTRANS(trans), .HMASTLOCK(lock), .ExternalStall(1'b0)
  );
  assign debug_trap = core.TrapM && !core.StallM;
  assign debug_cause = {core.priv.priv.InterruptM,58'd0,core.priv.priv.CauseM};
  assign debug_pc = core.PCM;
  assign debug_privilege = core.PrivilegeModeW;
  assign debug_retire = core.InstrValidM && !core.StallM && !core.FlushM;
  assign timer_ticks = mtime;
  // CVW replicates sb/sh/sw across HWDATA. Only the selected transfer's
  // bytes belong to an MMIO register; higher replicated lanes are ignored.
  assign write_value = (hwdata >> (8*addr_d[2:0])) &
      (size_d == 0 ? 64'hff : size_d == 1 ? 64'hffff :
       size_d == 2 ? 64'hffffffff : 64'hffffffffffffffff);
  assign bad_alignment = (size_d > 3) || ((addr_d & ((56'd1 << size_d)-1)) != 0);
  assign sel_mem = (addr_d >= RAM_BASE && addr_d < RAM_BASE+RAM_BYTES) ||
                   (addr_d >= RESET_VECTOR && addr_d < RESET_VECTOR+ROM_BYTES);
  assign sel_timer = (addr_d >= TIMER_BASE && addr_d < TIMER_BASE+TIMER_SPAN);
  assign sel_uart = (addr_d >= UART_BASE && addr_d < UART_BASE+UART_SPAN);
  assign sel_plic = (addr_d >= PLIC_BASE && addr_d < PLIC_BASE+PLIC_SPAN);
  assign sel_finish = (addr_d == FINISHER_BASE);
  assign sel_dev = ((addr_d >= BLOCK_BASE && addr_d < BLOCK_BASE+BLOCK_SPAN) ||
                   (addr_d >= PAPER_BASE && addr_d < PAPER_BASE+PAPER_SPAN) ||
                   (addr_d >= PEN_BASE && addr_d < PEN_BASE+PEN_SPAN));
  assign mem_valid = valid_d && sel_mem && !bad_alignment;
  assign mem_write = write_d;
  assign mem_addr = {addr_d[55:3],3'b000};
  assign mem_wdata = hwdata;
  assign mem_strb = hwstrb;
  // A peripheral completes its transaction at its own ready handshake.
  // Keep a terminal error for AHB's second ERROR cycle, suppressing a repeat
  // of the already-consumed MMIO request while HREADY is low.
  assign dev_valid = valid_d && sel_dev && !bad_alignment && !dev_error_pending;
  assign dev_write = write_d;
  assign dev_addr = addr_d[31:0];
  assign dev_size = size_d;
  assign dev_wdata = write_value;
  assign uart_tx_valid = valid_d && sel_uart && write_d && addr_d[2:0] == 0 && hready && !hresp;
  assign uart_tx_data = write_value[7:0];
  assign uart_rx_ready = valid_d && sel_uart && !write_d && addr_d[2:0] == 0 && hready && !hresp;
  assign finish_valid = valid_d && sel_finish && write_d && hready && !hresp;
  assign finish_code = write_value[31:0];
  assign uart_irq=(uart_ier[0]&&uart_rx_valid)||uart_ier[1];
  assign pending = (external_irqs | (32'(uart_irq)<<lemma_silicon_binding::UART_IRQ)) & ~inflight;
  assign timer_register = (addr_d[15:0]==0 && size_d==2) ||
      ((addr_d[15:0]==16'(TIMER_MTIME-TIMER_BASE) ||
        addr_d[15:0]==16'(TIMER_MTIMECMP-TIMER_BASE)) && size_d==3);
  assign plic_register = addr_d[25:0]<26'(4*(PLIC_SOURCES+1)) ||
      addr_d[25:0]==26'h001000 || addr_d[25:0]==26'h002000 ||
      addr_d[25:0]==26'h002080 || addr_d[25:0]==26'h200000 ||
      addr_d[25:0]==26'h200004 || addr_d[25:0]==26'h201000 || addr_d[25:0]==26'h201004;

  always_comb begin
    claim_m = 0; claim_s = 0;
    // Priority first, lower source ID wins a tie. Source zero is reserved.
    for (int k=int'(PLIC_SOURCES); k>0; k=k-1) begin
      if (pending[k] && enables_m[k] && priorities[k] > threshold_m &&
          (claim_m == 0 || priorities[k] >= priorities[claim_m])) claim_m=5'(k);
      if (pending[k] && enables_s[k] && priorities[k] > threshold_s &&
          (claim_s == 0 || priorities[k] >= priorities[claim_s])) claim_s=5'(k);
    end
    mmio_data = 0;
    if (sel_timer) begin
      case (addr_d[15:0])
        16'h0000: mmio_data = {32'd0,msip};
        16'(TIMER_MTIMECMP-TIMER_BASE): mmio_data = mtimecmp;
        16'(TIMER_MTIME-TIMER_BASE): mmio_data = mtime;
        default: mmio_data = 0;
      endcase
    end else if (sel_uart) begin
      case (addr_d[2:0])
        0: mmio_data = {56'd0,uart_rx_data};
        1: mmio_data = {62'd0,uart_ier};
        2: mmio_data = (uart_ier[0]&&uart_rx_valid)?64'd4:uart_ier[1]?64'd2:64'd1;
        5: mmio_data = 64'h60 | {63'd0,uart_rx_valid};
        default: mmio_data = 0;
      endcase
    end else if (sel_plic) begin
      if (addr_d[25:0] < 26'h000080) mmio_data={61'd0,priorities[addr_d[6:2]]};
      else case (addr_d[25:0])
        26'h001000: mmio_data = {32'd0,pending};
        26'h002000: mmio_data = {32'd0,enables_m};
        26'h002080: mmio_data = {32'd0,enables_s};
        26'h200000: mmio_data = {61'd0,threshold_m};
        26'h200004: mmio_data = {59'd0,claim_m};
        26'h201000: mmio_data = {61'd0,threshold_s};
        26'h201004: mmio_data = {59'd0,claim_s};
        default: mmio_data = 0;
      endcase
    end else if (sel_dev) mmio_data = dev_error_pending ? dev_error_data : dev_rdata;
    hrdata = sel_mem ? mem_rdata : (mmio_data << (8*addr_d[2:0]));
    response_ready = !valid_d || bad_alignment || (sel_mem ? mem_ready : sel_dev ? (dev_error_pending || dev_ready) : 1'b1);
    raw_error = valid_d && (bad_alignment || (sel_uart && (addr_d[7:0]>=8 || size_d!=0)) ||
      (sel_timer && !timer_register) || (sel_plic && (!plic_register || size_d!=2)) ||
      (sel_finish && size_d!=2) ||
      !(sel_mem || sel_timer || sel_uart || sel_plic || sel_finish || sel_dev) ||
      (sel_mem && mem_error) || (sel_dev && (dev_error_pending || (dev_ready && dev_error))));
    // AHB-Lite requires a two-cycle ERROR response, holding the transaction.
    hready = raw_error ? error_phase : response_ready;
    hresp = raw_error;
  end

  always_ff @(posedge clk) begin
    if (reset) begin
      error_phase <= 0;
      dev_error_pending <= 0; dev_error_data <= 0;
      valid_d <= 0; addr_d <= 0; write_d <= 0; size_d <= 0;
      uart_ier <= 0;
      mtime <= 0; timer_phase <= 0; mtimecmp <= 64'hffffffffffffffff; msip<=0;
      enables_m<=0; enables_s<=0; threshold_m<=0; threshold_s<=0; inflight<=0;
      for(i=0;i<32;i=i+1) priorities[i]<=0;
    end else begin
      if(dev_valid && dev_ready && dev_error) begin
        dev_error_pending <= 1;
        dev_error_data <= dev_rdata;
      end else if(hready) dev_error_pending <= 0;
      if(raw_error && response_ready && !error_phase) error_phase<=1;
      else if(hready) error_phase<=0;
      if (timer_phase == TIMER_DIV-1) begin timer_phase<=0; mtime<=mtime+1; end
      else timer_phase<=timer_phase+1;
      if (hready) begin
        valid_d <= trans[1]; addr_d <= haddr; write_d <= hwrite; size_d <= hsize;
        if (valid_d && !hresp) begin
          if (sel_uart && write_d && addr_d[2:0]==1) uart_ier<=write_value[1:0];
          if (sel_timer && write_d) case(addr_d[15:0])
            16'h0000: msip<=write_value[31:0];
            16'(TIMER_MTIMECMP-TIMER_BASE): mtimecmp<=write_value;
            16'(TIMER_MTIME-TIMER_BASE): mtime<=write_value;
            default: ;
          endcase
          if (sel_plic) begin
            if (write_d) begin
              if (addr_d[25:0] < 26'h000080 && addr_d[6:2] != 0)
                priorities[addr_d[6:2]]<=write_value[2:0];
              else case(addr_d[25:0])
                26'h002000: enables_m<=write_value[31:0]&32'((64'd1<<(PLIC_SOURCES+1))-2);
                26'h002080: enables_s<=write_value[31:0]&32'((64'd1<<(PLIC_SOURCES+1))-2);
                26'h200000: threshold_m<=write_value[2:0];
                26'h201000: threshold_s<=write_value[2:0];
                26'h200004,26'h201004:
                  if (write_value>0 && write_value<32) inflight[write_value[4:0]]<=0;
                default: ;
              endcase
            end else if (addr_d[25:0] == 26'h200004 && claim_m!=0) inflight[claim_m]<=1;
            else if (addr_d[25:0] == 26'h201004 && claim_s!=0) inflight[claim_s]<=1;
          end
        end
      end
    end
  end
endmodule
