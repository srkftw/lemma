// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
// Private generic digital prototype; no process, ADC timing or physical claim.
module sar4_control #(parameter integer ACQUIRE_CYCLES=1, SETTLE_CYCLES=2)(
 input logic clk, reset_n, start, cancel, comparator_high,
 output logic sample_enable,busy,valid,cancelled,overrun,
 output logic [3:0] trial,code);
 logic [1:0] phase;
 logic [1:0] bit_index;
 integer remaining;
 logic [3:0] decided;
 always_comb decided=comparator_high?trial:(trial & ~(4'b0001<<bit_index));
 always_ff @(posedge clk or negedge reset_n) begin
  if(!reset_n) begin
   phase<=0;bit_index<=0;remaining<=0;sample_enable<=0;busy<=0;
   valid<=0;cancelled<=0;overrun<=0;trial<=0;code<=0;
  end else begin
   valid<=0;cancelled<=0;
   if(start && busy) overrun<=1;
   if(cancel && busy) begin
    phase<=0;sample_enable<=0;busy<=0;trial<=0;code<=0;cancelled<=1;
   end else case(phase)
    0:if(start) begin
       phase<=1;remaining<=ACQUIRE_CYCLES;sample_enable<=1;busy<=1;
       trial<=0;code<=0;bit_index<=3;
      end
    1:if(remaining<=1) begin
       sample_enable<=0;trial<=8;phase<=2;remaining<=SETTLE_CYCLES;
      end else remaining<=remaining-1;
    2:if(remaining<=1) begin
       if(bit_index==0) begin
        code<=decided;trial<=decided;valid<=1;busy<=0;phase<=0;
       end else begin
        trial<=decided|(4'b0001<<(bit_index-1));bit_index<=bit_index-1;
        remaining<=SETTLE_CYCLES;
       end
      end else remaining<=remaining-1;
    default:begin phase<=0;sample_enable<=0;busy<=0;trial<=0;code<=0;end
   endcase
  end
 end
endmodule
