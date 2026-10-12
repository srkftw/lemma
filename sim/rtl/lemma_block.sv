// SPDX-License-Identifier: Apache-2.0
// Modern VirtIO MMIO split-ring block subset. Queue execution and DMA are
// circuits; the medium port transfers only one sector or a flush barrier.
module lemma_block #(
  parameter logic [63:0] DMA_BASE = 64'h82000000,
  parameter logic [63:0] DMA_BYTES = 64'h02000000,
  parameter logic [63:0] CAPACITY_SECTORS = 524288
) (
  input logic clk, reset_n,
  input logic valid, write,
  input logic [11:0] addr,
  input logic [2:0] size,
  input logic [63:0] wdata,
  output logic [63:0] rdata,
  output logic ready, error, irq,
  output logic dma_valid, dma_write,
  output logic [63:0] dma_addr, dma_wdata,
  output logic [2:0] dma_size,
  input logic dma_ready, dma_error,
  input logic [63:0] dma_rdata,
  output logic media_valid,
  output logic [2:0] media_kind,
  output logic [63:0] media_sector,
  output logic [4095:0] media_wdata,
  input logic media_ready, media_error,
  input logic [4095:0] media_rdata
);
  typedef enum logic [4:0] {IDLE,AVAIL_INDEX,AVAIL_HEAD,DESC0,DESC1,
    HEADER_KIND,HEADER_SECTOR,WRITE_BUFFER,MEDIUM,READ_BUFFER,
    STATUS_BYTE,USED_ID,USED_LENGTH,USED_INDEX} state_t;
  state_t state;
  logic [31:0] status,feature_sel,driver_sel,driver_low,driver_high;
  logic [31:0] queue_sel,queue_num,queue_ready,interrupt_status;
  logic [63:0] desc_base,avail_base,used_base;
  logic [15:0] last_avail,used_index,head_id,desc_id;
  logic [1:0] chain;
  logic [63:0] desc_address,header_address,data_address,status_address,sector;
  logic [31:0] kind;
  logic [6:0] word_index;
  logic [4095:0] sector_buffer;
  logic [7:0] result;
  logic notify,reset_pending,fault_pending;
  logic access_ok,descriptor_ok,external_quiescent,configuration_idle;
  logic [31:0] irq_events,irq_ack;
  function automatic logic span_ok(input logic [63:0] base,input logic [63:0] length);
    return base >= DMA_BASE && length <= DMA_BYTES && base-DMA_BASE <= DMA_BYTES-length;
  endfunction
  // Pending cancellation holds the current external request unchanged until
  // its ready handshake. Reads, IRQ ACK and repeated reset remain available;
  // configuration writes wait until no outstanding transaction survives.
  assign ready = !write || (!reset_pending && !fault_pending) ||
    (access_ok && ((addr == 112 && wdata == 0) || addr == 100));
  assign external_quiescent = (!dma_valid || dma_ready) && (!media_valid || media_ready);
  assign configuration_idle = state == IDLE && !notify && !reset_pending && !fault_pending;
  assign access_ok = size == 2 && addr[1:0] == 0;
  assign error = valid && ready && !access_ok;
  assign irq = interrupt_status != 0;
  assign descriptor_ok = span_ok(desc_address,chain == 0 ? 16 : (kind == 4 || chain == 2 ? 1 : 512));
  assign media_valid = state == MEDIUM;
  assign media_kind = kind[2:0];
  assign media_sector = sector;
  assign media_wdata = sector_buffer;

  always_comb begin
    rdata = 0;
    if(access_ok) case(addr)
      0: rdata = 64'h74726976;
      4: rdata = 2;
      8: rdata = 2;
      12: rdata = 64'h4c454d4d;
      16: rdata = feature_sel == 0 ? 512 : (feature_sel == 1 ? 1 : 0);
      52: rdata = queue_sel == 0 ? 8 : 0;
      68: rdata = {32'b0,queue_ready};
      96: rdata = {32'b0,interrupt_status};
      112: rdata = {32'b0,status};
      252: rdata = 0;
      256: rdata = {32'b0,CAPACITY_SECTORS[31:0]};
      260: rdata = {32'b0,CAPACITY_SECTORS[63:32]};
      default: rdata = 0;
    endcase
    dma_valid = state != IDLE && state != MEDIUM;
    dma_write = 0; dma_addr = 0; dma_wdata = 0; dma_size = 3;
    case(state)
      AVAIL_INDEX: begin dma_addr = avail_base+2; dma_size = 1; end
      AVAIL_HEAD: begin dma_addr = avail_base+4+{48'b0,last_avail%8}*2; dma_size = 1; end
      DESC0: dma_addr = desc_base+{48'b0,desc_id}*16;
      DESC1: dma_addr = desc_base+{48'b0,desc_id}*16+8;
      HEADER_KIND: begin dma_addr = header_address; dma_size = 3; end
      HEADER_SECTOR: dma_addr = header_address+8;
      WRITE_BUFFER: dma_addr = data_address+{57'b0,word_index}*8;
      READ_BUFFER: begin
        dma_write = 1; dma_addr = data_address+{57'b0,word_index}*8;
        dma_wdata = sector_buffer[word_index*64 +: 64];
      end
      STATUS_BYTE: begin dma_write = 1; dma_addr = status_address; dma_size = 0; dma_wdata = {56'b0,result}; end
      USED_ID: begin
        dma_write = 1; dma_addr = used_base+4+{48'b0,used_index%8}*8;
        dma_size = 2; dma_wdata = {48'b0,head_id};
      end
      USED_LENGTH: begin
        dma_write = 1; dma_addr = used_base+8+{48'b0,used_index%8}*8;
        dma_size = 2; dma_wdata = kind == 0 ? 513 : 1;
      end
      USED_INDEX: begin
        dma_write = 1; dma_addr = used_base+2; dma_size = 1;
        dma_wdata = {48'b0,used_index+16'd1};
      end
      default: dma_valid = 0;
    endcase
  end

  task automatic reject_queue;
    begin
      status <= status | 64; irq_events = irq_events | 32'd2; notify <= 0;
      if(external_quiescent) begin state <= IDLE; fault_pending <= 0; end
      else fault_pending <= 1;
    end
  endtask
  always @(posedge clk) begin
    // Combine acknowledgements with new events once; a concurrent event wins
    // even if ACK clears the same bit, and ACK0 cannot erase a completion.
    irq_events = 0; irq_ack = 0;
    if(!reset_n) begin
      state <= IDLE; status <= 0; feature_sel <= 0; driver_sel <= 0;
      driver_low <= 0; driver_high <= 0; queue_sel <= 0; queue_num <= 0; queue_ready <= 0;
      interrupt_status <= 0; desc_base <= 0; avail_base <= 0; used_base <= 0;
      last_avail <= 0; used_index <= 0; head_id <= 0; desc_id <= 0; chain <= 0;
      desc_address <= 0; header_address <= 0; data_address <= 0; status_address <= 0;
      sector <= 0; kind <= 0; word_index <= 0; sector_buffer <= 0; result <= 0;
      notify <= 0; reset_pending <= 0; fault_pending <= 0;
    end else if(reset_pending && external_quiescent) begin
      // Status reaches zero only after the current external transaction is
      // quiescent. No deferred DMA survives this reset acknowledgement.
      state <= IDLE; status <= 0; queue_ready <= 0; interrupt_status <= 0;
      notify <= 0; reset_pending <= 0; fault_pending <= 0; driver_low <= 0; driver_high <= 0;
      last_avail <= 0; used_index <= 0;
    end else begin
      if(fault_pending) begin
        if(external_quiescent) begin state <= IDLE; notify <= 0; fault_pending <= 0; end
      end else if(!reset_pending && state == IDLE && notify && status == 15 && queue_ready == 1) begin
        if(queue_num != 8 || desc_base[3:0] != 0 || avail_base[0] || used_base[1:0] != 0 ||
           !span_ok(desc_base,128) || !span_ok(avail_base,20) || !span_ok(used_base,68)) reject_queue();
        else begin notify <= 0; state <= AVAIL_INDEX; end
      end else if(dma_valid && dma_ready && !reset_pending) begin
        if(dma_error || !span_ok(dma_addr,64'd1 << dma_size)) reject_queue();
        else case(state)
          AVAIL_INDEX: if(dma_rdata[15:0] == last_avail) state <= IDLE;
            else if(dma_rdata[15:0] == last_avail+16'd1) state <= AVAIL_HEAD;
            else reject_queue();
          AVAIL_HEAD: if(dma_rdata < 8) begin
            head_id <= dma_rdata[15:0]; desc_id <= dma_rdata[15:0]; chain <= 0; state <= DESC0;
          end else reject_queue();
          DESC0: begin desc_address <= dma_rdata; state <= DESC1; end
          DESC1: if(!descriptor_ok) reject_queue();
            else if(chain == 0) begin
              if(dma_rdata[31:0] != 16 || dma_rdata[47:32] != 1 || dma_rdata[63:48] >= 8 || dma_rdata[63:48] == head_id)
                reject_queue();
              else begin header_address <= desc_address; desc_id <= dma_rdata[63:48]; state <= HEADER_KIND; end
            end else if(chain == 1 && kind != 4) begin
              if(dma_rdata[31:0] != 512 || dma_rdata[47:32] != (kind == 0 ? 3 : 1) ||
                 dma_rdata[63:48] >= 8 || dma_rdata[63:48] == desc_id || dma_rdata[63:48] == head_id) reject_queue();
              else begin data_address <= desc_address; desc_id <= dma_rdata[63:48]; chain <= 2; state <= DESC0; end
            end else if(dma_rdata[31:0] != 1 || dma_rdata[47:32] != 2) reject_queue();
            else begin status_address <= desc_address; word_index <= 0; result <= 0;
              state <= kind == 1 ? WRITE_BUFFER : MEDIUM; end
          HEADER_KIND: if(dma_rdata[63:32] != 0 || (dma_rdata[31:0] != 0 && dma_rdata[31:0] != 1 && dma_rdata[31:0] != 4)) reject_queue();
            else begin kind <= dma_rdata[31:0]; state <= HEADER_SECTOR; end
          HEADER_SECTOR: if(kind != 4 && dma_rdata >= CAPACITY_SECTORS) reject_queue();
            else begin sector <= dma_rdata; chain <= 1; state <= DESC0; end
          WRITE_BUFFER: begin
            sector_buffer[word_index*64 +: 64] <= dma_rdata;
            if(word_index == 63) begin word_index <= 0; state <= MEDIUM; end
            else word_index <= word_index+1'b1;
          end
          READ_BUFFER: if(word_index == 63) begin word_index <= 0; state <= STATUS_BYTE; end
            else word_index <= word_index+1'b1;
          STATUS_BYTE: state <= USED_ID;
          USED_ID: state <= USED_LENGTH;
          USED_LENGTH: state <= USED_INDEX;
          USED_INDEX: begin
            used_index <= used_index+16'd1; last_avail <= last_avail+16'd1;
            irq_events = irq_events | 32'd1; state <= IDLE;
          end
          default: reject_queue();
        endcase
      end else if(media_valid && media_ready && !reset_pending) begin
        result <= media_error ? 1 : 0;
        if(kind == 0 && !media_error) begin sector_buffer <= media_rdata; word_index <= 0; state <= READ_BUFFER; end
        else state <= STATUS_BYTE;
      end
      if(valid && write && ready) begin
        if(!access_ok) reject_queue();
        else case(addr)
          20: feature_sel <= wdata[31:0];
          36: driver_sel <= wdata[31:0];
          32: if(driver_sel == 0) driver_low <= wdata[31:0];
              else if(driver_sel == 1) driver_high <= wdata[31:0]; else reject_queue();
          48: if(configuration_idle) queue_sel <= wdata[31:0]; else reject_queue();
          56: if(configuration_idle && queue_sel == 0 && queue_ready == 0 && wdata == 8) queue_num <= 8; else reject_queue();
          68: if(configuration_idle && queue_sel == 0 && wdata == 1) queue_ready <= 1;
              else if(configuration_idle && wdata == 0) queue_ready <= 0; else reject_queue();
          80: if(wdata == 0 && status == 15 && queue_ready == 1 && state == IDLE) notify <= 1; else reject_queue();
          100: irq_ack = wdata[31:0];
          112: if(wdata == 0) begin
                 reset_pending <= 1; queue_ready <= 0; notify <= 0;
                 if(external_quiescent) state <= IDLE;
               end
               else if(wdata[3] && (driver_low != 512 || driver_high != 1)) status <= wdata[31:0] & ~32'd8;
               else status <= wdata[31:0];
          128: if(configuration_idle && queue_ready == 0) desc_base[31:0] <= wdata[31:0]; else reject_queue();
          132: if(configuration_idle && queue_ready == 0) desc_base[63:32] <= wdata[31:0]; else reject_queue();
          144: if(configuration_idle && queue_ready == 0) avail_base[31:0] <= wdata[31:0]; else reject_queue();
          148: if(configuration_idle && queue_ready == 0) avail_base[63:32] <= wdata[31:0]; else reject_queue();
          160: if(configuration_idle && queue_ready == 0) used_base[31:0] <= wdata[31:0]; else reject_queue();
          164: if(configuration_idle && queue_ready == 0) used_base[63:32] <= wdata[31:0]; else reject_queue();
          default: reject_queue();
        endcase
      end
      interrupt_status <= (interrupt_status & ~irq_ack) | irq_events;
    end
  end
endmodule
