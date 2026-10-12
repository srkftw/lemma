// SPDX-License-Identifier: Apache-2.0
// Explicit 4 KiB register implementation of the motherboard memory port.
// Named small configurations may preload through this external byte interface
// while the hart is held in reset. This is not a nonvolatile boot solution.
module lemma_register_ram (
  input logic clk,
  input logic valid, write,
  input logic [55:0] addr,
  input logic [63:0] wdata,
  input logic [7:0] strb,
  output logic [63:0] rdata,
  output logic ready, error,
  input logic preload_valid,
  input logic [8:0] preload_index,
  input logic [63:0] preload_data
);
  logic [63:0] words [512];
  logic [8:0] index;
  logic selected;
  // 3 KiB text/BSS, 512-byte top-of-stack, 512-byte scalar input. Sparse
  // physical windows preserve the existing Core0 scalar image's fixed layout.
  // The rest of the historical 128 MiB envelope is absent and faults.
  always_comb begin
    selected = 1; index = 0;
    if(addr >= 56'h80000000 && addr < 56'h80000c00) index = addr[11:3];
    else if(addr >= 56'h807ffe00 && addr < 56'h80800000) index = 9'd384+{3'b0,addr[8:3]};
    else if(addr >= 56'h81000000 && addr < 56'h81000200) index = 9'd448+{3'b0,addr[8:3]};
    else selected = 0;
    rdata = selected ? words[index] : 0;
  end
  assign ready = 1;
  assign error = valid && (!selected || addr[2:0] != 0 || preload_valid);
  always @(posedge clk) begin
    if(preload_valid) words[preload_index] <= preload_data;
    else if(valid && write && !error)
      for(int b=0;b<8;b++) if(strb[b]) words[index][b*8 +: 8] <= wdata[b*8 +: 8];
  end
endmodule
