// SPDX-License-Identifier: Apache-2.0
// Circuit implementation of Lemma pen v1. Host input is raw sample transport.
module lemma_pen #(
  parameter int FIFO_DEPTH = 256,
  parameter int PRESSURE_MAX = 4095
) (
  input logic clk, reset_n,
  input logic valid, write,
  input logic [11:0] addr,
  input logic [2:0] size,
  input logic [63:0] wdata,
  output logic [63:0] rdata,
  output logic ready, error, irq,
  input logic [63:0] now_ticks,
  input logic sample_valid,
  output logic sample_ready,
  input logic [63:0] sample_time, sample_x, sample_y, sample_pressure,
  input logic [63:0] sample_flags, sample_tool, sample_buttons,
  output logic sample_accepted
);
  localparam int PTR = $clog2(FIFO_DEPTH);
  // Power-of-two FIFO storage: low pointer bits select a bank, high bits a
  // row.  Neither capacity nor sample widths are reduced by this partition.
  localparam int BANK_BITS = PTR < 4 ? PTR : 4;
  localparam int BANKS = 1 << BANK_BITS;
  localparam int ROWS = FIFO_DEPTH / BANKS;
  // Narrowing follows validated ranges; sequence/time are never truncated.
  typedef struct packed {
    logic [63:0] sequence_id, timestamp;
    logic [15:0] x, y;
    logic [11:0] pressure;
    logic [3:0] flags;
    logic [1:0] tool;
    logic [2:0] buttons;
  } entry_t;
  entry_t bank_entry [BANKS];
  entry_t head_entry, ingress_entry;
  // Decode the bank before the existing second refill edge. A registered
  // one-hot choice drives a parallel mask/OR rather than broadcasting four
  // binary select bits across every bit of the181-bit sixteen-bank mux.
  logic [BANKS-1:0] refill_select;
  entry_t selected_head;
  logic [PTR-1:0] ingress_index;
  logic ingress_pending;
  // A completed pop advances the public FIFO once.  The next head is fetched
  // synchronously in two bounded stages; MMIO and ingress wait meanwhile.
  logic [1:0] refill;
  logic [PTR-1:0] head, tail;
  logic [PTR:0] count;
  logic [63:0] epoch, head_epoch, next_sequence, losses, fault;
  logic [63:0] last_time, contact_deadline;
  logic loss, resync, release_seen, bad_sample;
  logic access_ok, lose;

  // Separate bank memories give synthesis one local write and one local read
  // port per bank instead of a flattened array with BANKS competing writers.
  for (genvar bank = 0; bank < BANKS; bank++) begin : storage
    entry_t rows [ROWS];
    always @(posedge clk) begin
      if (reset_n && ingress_pending && ingress_index[BANK_BITS-1:0] == BANK_BITS'(bank))
        rows[ingress_index >> BANK_BITS] <= ingress_entry;
      if (reset_n && refill == 2)
        bank_entry[bank] <= rows[head >> BANK_BITS];
    end
  end

  always_comb begin
    selected_head = '0;
    for (int bank = 0; bank < BANKS; bank++)
      selected_head |= bank_entry[bank] & {$bits(entry_t){refill_select[bank]}};
  end

  assign ready = refill == 0;
  assign access_ok = size == 3 && addr[2:0] == 0;
  assign error = valid && !access_ok;
  assign irq = count != 0 || loss || fault != 0;
  // Serialize external ingress against register mutations; reads never pop.
  assign sample_ready = ready && !(valid && write) &&
                        !(contact_deadline != 0 && now_ticks >= contact_deadline);
  assign bad_sample = sample_time < last_time || sample_time > 64'hffffffff_ff67697f ||
    sample_x > 65535 || sample_y > 65535 || sample_pressure > PRESSURE_MAX ||
    sample_flags > 15 || sample_tool > 2 || sample_buttons > 7;
  assign lose = (contact_deadline != 0 && now_ticks >= contact_deadline) ||
    (sample_valid && sample_ready && !loss &&
      (bad_sample || sample_flags[3] || next_sequence == 64'hffffffffffffffff ||
       (!resync && count == FIFO_DEPTH)));

  always_comb begin
    rdata = 0;
    if (access_ok) case (addr)
      0: rdata = 1280331854;
      8: rdata = 1;
      16: rdata = {60'b0, fault != 0, resync, loss, count != 0};
      24: rdata = fault;
      32: rdata = {{(63-PTR){1'b0}},count};
      40: rdata = epoch;
      48: rdata = losses;
      56,64: rdata = 65535;
      72: rdata = PRESSURE_MAX;
      80: rdata = PRESSURE_MAX != 0 ? 1 : 0;
      256: rdata = head_entry.sequence_id;
      264: rdata = head_entry.timestamp;
      272: rdata = {48'b0,head_entry.x};
      280: rdata = {48'b0,head_entry.y};
      288: rdata = {52'b0,head_entry.pressure};
      296: rdata = {60'b0,head_entry.flags};
      304: rdata = {62'b0,head_entry.tool};
      312: rdata = {61'b0,head_entry.buttons};
      320: rdata = count != 0 ? head_epoch : 0;
      default: rdata = 0;
    endcase
  end

  task automatic mark_loss;
    begin
      count <= count != 0 ? 1 : 0;
      tail <= head + (count != 0 ? 1'b1 : 1'b0);
      contact_deadline <= 0;
      loss <= 1;
      resync <= 1;
      release_seen <= 0;
      if (epoch != 64'hffffffffffffffff) epoch <= epoch + 1;
      else fault <= 5;
      if (losses != 64'hffffffffffffffff) losses <= losses + 1;
    end
  endtask

  always @(posedge clk) begin
    sample_accepted <= 0;
    // The large storage array sees only registered data/address/enable.  Raw
    // sample bounds, loss decisions and 64-bit ACK comparisons do not drive
    // every storage flip-flop's enable in the same cycle.
    // Capture the private payload every clock. Only ingress_pending can commit
    // it to storage, so unaccepted samples remain unobservable. This keeps the
    // bounds/loss/ACK network out of the wide ingress register's hold mux; a
    // bank commit still reads the preceding accepted payload/address.
    ingress_entry <= {next_sequence, sample_time, sample_x[15:0], sample_y[15:0],
      sample_pressure[11:0],sample_flags[3:0],sample_tool[1:0],sample_buttons[2:0]};
    ingress_index <= tail;
    ingress_pending <= 0;
    if (!reset_n) begin
      head <= 0; tail <= 0; count <= 0;
      head_entry <= '0; ingress_entry <= '0; ingress_index <= 0;
      refill <= 0; refill_select <= '0;
      epoch <= 1; head_epoch <= 1; next_sequence <= 1;
      losses <= 0; fault <= 0; last_time <= 0; contact_deadline <= 0;
      loss <= 0; resync <= 0; release_seen <= 0;
    end else if (refill == 2) begin
      refill_select <= {{(BANKS-1){1'b0}},1'b1} << head[BANK_BITS-1:0];
      refill <= 1;
    end else if (refill == 1) begin
      head_entry <= selected_head;
      refill <= 0;
    end else if (lose) begin
      mark_loss();
      if (sample_valid && sample_ready && bad_sample) fault <= 1;
    end else if (valid && write) begin
      if (!access_ok) fault <= 1;
      else case (addr)
        88: if (count != 0 && head_entry.sequence_id == wdata) begin
          head <= head + 1'b1; count <= count - 1'b1;
          if (count > 1) refill <= 2;
          else head_entry <= '0;
        end else fault <= 2;
        96: if (loss && wdata == epoch) begin
          head <= 0; tail <= 0; count <= 0; loss <= 0; fault <= 0;
          head_entry <= '0;
          head_epoch <= epoch;
        end else fault <= 2;
        104: if (wdata == 1) mark_loss(); else fault <= 3;
        default: fault <= 3;
      endcase
    end else if (sample_valid && sample_ready && !loss) begin
      if (resync && !sample_flags[0]) release_seen <= 1;
      if (!resync || (release_seen && sample_flags[0])) begin
        ingress_pending <= 1;
        if (count == 0)
          head_entry <= {next_sequence, sample_time, sample_x[15:0], sample_y[15:0],
            sample_pressure[11:0],sample_flags[3:0],sample_tool[1:0],sample_buttons[2:0]};
        tail <= tail + 1'b1; count <= count + 1'b1;
        next_sequence <= next_sequence + 1;
        head_epoch <= epoch; last_time <= sample_time;
        contact_deadline <= sample_flags[0] ? sample_time + 10000000 : 0;
        resync <= 0; sample_accepted <= 1;
      end
    end
  end
endmodule
