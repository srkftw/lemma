// SPDX-License-Identifier: Apache-2.0
// Independent language-level oracle for the physical timestamp comparator.
module PenTimestamp;
  reg [63:0] left, right;
  wire less;
  wire [63:0] incremented;
  lemma_pen_timestamp_less dut(left, right, less);
  lemma_pen_sequence_increment counter(left, incremented);
  task check;
    begin
      #1;
      if (less !== (left < right))
        $fatal(1, "timestamp relational difference left=%h right=%h", left, right);
      if (incremented !== (left + 64'd1))
        $fatal(1, "counter arithmetic difference left=%h", left);
    end
  endtask
  initial begin
    left=0; right=0; check();
    left=0; right=64'hffffffffffffffff; check();
    left=64'hffffffffffffffff; right=0; check();
    for (integer bit_index=0; bit_index<64; bit_index=bit_index+1) begin
      left=64'b1<<bit_index; right=left-1; check();
      right=left; check(); right=left+1; check();
      left=0; right=64'hffffffffffffffff; left[bit_index]=1'bx; check();
      left=0; right=64'hffffffffffffffff; right[bit_index]=1'bx; check();
      left=64'hffffffffffffffff; right=0; left[bit_index]=1'bz; check();
      left=64'hffffffffffffffff; right=0; right[bit_index]=1'bz; check();
    end
    for (integer trial=0; trial<4096; trial=trial+1) begin
      left={$random,$random}; right={$random,$random}; check();
    end
    $display("PEN-TIMESTAMP full64 relational boundary randomized XZ PASS");
    $finish;
  end
endmodule
