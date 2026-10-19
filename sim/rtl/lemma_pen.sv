// SPDX-License-Identifier: Apache-2.0
// Circuit implementation of Lemma pen v1. Host input is raw sample transport.
// Keep arithmetic separate through physical technology mapping. The final
// netlist is flattened after mapping; this adds no clock or architectural state.
module lemma_pen_increment_part(input wire [15:0] value, input wire carry,
  output wire [15:0] incremented);
  assign incremented = value + {15'b0, carry};
endmodule

module lemma_pen_sequence_increment(input wire [63:0] value,
  output wire [63:0] incremented);
  wire [3:0] carry;
  wire [63:0] parts;
  assign carry[0] = 1;
  for (genvar part = 1; part < 4; part++) begin : carry_prefix
    assign carry[part] = &value[part*16-1:0];
  end
  for (genvar part = 0; part < 4; part++) begin : increment
    (* keep_hierarchy = 1 *) lemma_pen_increment_part add_part(
      .value(value[part*16 +: 16]), .carry(carry[part]),
      .incremented(parts[part*16 +: 16]));
  end
  // Match the original vector arithmetic's all-X result for an X/Z operand.
  assign incremented = parts ^ {64{(^value) ^ (^value)}};
endmodule

// Four parallel 16-bit comparisons and a bounded lexicographic combine keep
// the timestamp input out of ABC's shared 64-bit range/control factoring.
// No state or cycle is added: acceptance still occurs on the offered edge.
module lemma_pen_timestamp_part(input wire [15:0] left, right,
  output wire less, equal);
  assign less = left < right;
  assign equal = left == right;
endmodule

module lemma_pen_timestamp_less(input wire [63:0] left, right,
  output wire less);
  wire [3:0] lt, eq;
  for (genvar part = 0; part < 4; part++) begin : compare
    (* keep_hierarchy = 1 *) lemma_pen_timestamp_part compare_part(
      .left(left[part*16 +: 16]), .right(right[part*16 +: 16]),
      .less(lt[part]), .equal(eq[part]));
  end
  wire ordered_less = lt[3] | (eq[3] & lt[2]) |
    (eq[3] & eq[2] & lt[1]) | (eq[3] & eq[2] & eq[1] & lt[0]);
  // A Verilog vector relational operator is X when any operand bit is X/Z,
  // even when a higher chunk decides the comparison. The self-XOR terms are
  // zero in circuitry and preserve that original four-state model behavior.
  assign less = ordered_less ^ ((^left) ^ (^left)) ^ ((^right) ^ (^right));
endmodule

// Keep independent input-validation cones apart during physical mapping.
// The routed sample_x -> sequence-D path previously crossed a single wide
// factored range/timestamp cone. These outputs retain the original full-width
// comparisons, including parameter promotion and four-state semantics.
module lemma_pen_sample_ranges #(parameter int PRESSURE_MAX = 4095) (
  input wire [63:0] x, y, pressure, flags, tool, buttons,
  output wire [5:0] invalid
);
  assign invalid = {x > 65535, y > 65535, pressure > PRESSURE_MAX,
                    flags > 15, tool > 2, buttons > 7};
endmodule

module lemma_pen #(
  parameter int FIFO_DEPTH = 256,
  parameter int PRESSURE_MAX = 4095,
  parameter bit IHP_SRAM = 0
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
  logic [63:0] epoch, head_epoch, next_sequence, losses;
  // Post-reset fault codes are exactly0,1,2,3,5. Compact internal storage
  // removes unreachable upper feedback bits; public MMIO remains full64.
  logic [2:0] fault;
  wire [63:0] sequence_incremented, epoch_incremented, losses_incremented;
  if (IHP_SRAM) begin : physical_increment
    (* keep_hierarchy = 1 *) lemma_pen_sequence_increment incrementer(
      .value(next_sequence), .incremented(sequence_incremented));
    // The first timestamp repair exposed a next_sequence→epoch critical
    // path: factoring the loss guard into the epoch carry chain made a
    // saturated counter update depend on a second64-bit reduction. Keep the
    // arithmetic independent before control muxing, just as for sequence.
    (* keep_hierarchy = 1 *) lemma_pen_sequence_increment epoch_incrementer(
      .value(epoch), .incremented(epoch_incremented));
    (* keep_hierarchy = 1 *) lemma_pen_sequence_increment losses_incrementer(
      .value(losses), .incremented(losses_incremented));
  end else begin : register_increment
    assign sequence_incremented = next_sequence + 64'd1;
    assign epoch_incremented = epoch + 64'd1;
    assign losses_incremented = losses + 64'd1;
  end
  logic [63:0] last_time, contact_deadline;
  logic loss, resync, release_seen, bad_sample;
  logic access_ok, lose;
  wire [5:0] range_errors;
  wire time_regressed, time_exhausted;
  if (IHP_SRAM) begin : physical_validation
    (* keep_hierarchy = 1 *) lemma_pen_sample_ranges #(.PRESSURE_MAX(PRESSURE_MAX)) ranges(
      .x(sample_x), .y(sample_y), .pressure(sample_pressure), .flags(sample_flags),
      .tool(sample_tool), .buttons(sample_buttons), .invalid(range_errors));
    (* keep_hierarchy = 1 *) lemma_pen_timestamp_less monotonic_time(
      .left(sample_time), .right(last_time), .less(time_regressed));
    (* keep_hierarchy = 1 *) lemma_pen_timestamp_less bounded_time(
      .left(64'hffffffff_ff67697f), .right(sample_time), .less(time_exhausted));
  end else begin : register_validation
    assign range_errors = {sample_x > 65535, sample_y > 65535,
      sample_pressure > PRESSURE_MAX, sample_flags > 15, sample_tool > 2, sample_buttons > 7};
    assign time_regressed = sample_time < last_time;
    assign time_exhausted = sample_time > 64'hffffffff_ff67697f;
  end

  if (IHP_SRAM) begin : physical_storage
    // Actual pinned SG13G2 one-port macros, not synthesis blackbox substitutes.
    // Existing refill edges serialize reads against delayed ingress writes.
    // All181 entry bits occupy three64-bit field banks; upper11 bits are zero.
    if (FIFO_DEPTH != 256) initial $fatal(1, "IHP SRAM requires full256 FIFO");
    wire [191:0] input_words = {{(192-$bits(ingress_entry)){1'b0}},ingress_entry};
    wire [191:0] output_words;
    wire read_rows = reset_n && refill == 2;
    wire write_rows = reset_n && ingress_pending;
    wire [7:0] row_address = write_rows ? ingress_index : head;
    for (genvar lane = 0; lane < 3; lane++) begin : field_bank
      RM_IHPSG13_1P_256x64_c2_bm_bist memory (
        .A_CLK(clk), .A_MEN(read_rows || write_rows),
        .A_WEN(write_rows), .A_REN(read_rows), .A_ADDR(row_address),
        .A_DIN(input_words[lane*64 +: 64]), .A_BM(64'hffffffffffffffff),
        .A_DLY(1'b1), .A_DOUT(output_words[lane*64 +: 64]),
        .A_BIST_CLK(1'b0), .A_BIST_EN(1'b0), .A_BIST_MEN(1'b0),
        .A_BIST_WEN(1'b0), .A_BIST_REN(1'b0), .A_BIST_ADDR(8'b0),
        .A_BIST_DIN(64'b0), .A_BIST_BM(64'b0));
    end
    for (genvar bank = 0; bank < BANKS; bank++) begin : head_alias
      assign bank_entry[bank] = output_words[$bits(ingress_entry)-1:0];
    end
`ifndef SYNTHESIS
    always @(posedge clk) if (read_rows && write_rows)
      $fatal(1, "pen SRAM single-port collision");
`endif
  end else begin : register_storage
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
  assign bad_sample = time_regressed || time_exhausted ||
    (|range_errors);
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
      24: rdata = {61'b0, fault};
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
      if (epoch != 64'hffffffffffffffff) epoch <= epoch_incremented;
      else fault <= 5;
      if (losses != 64'hffffffffffffffff) losses <= losses_incremented;
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
        next_sequence <= sequence_incremented;
        head_epoch <= epoch; last_time <= sample_time;
        contact_deadline <= sample_flags[0] ? sample_time + 10000000 : 0;
        resync <= 0; sample_accepted <= 1;
      end
    end
  end
endmodule
