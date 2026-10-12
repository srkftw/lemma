// SPDX-License-Identifier: Apache-2.0
// 34-cell bounded repair-journal sensitivity circuit.
module journal_minimal(input clk, input data_in, output data_out);
wire q;
sg13g2_dfrbp_1 launch(.CLK(clk), .D(data_in), .RESET_B(1'b1), .Q(q), .Q_N());
wire n0; sg13g2_buf_1 b0(.A(q), .X(n0));
wire n1; sg13g2_buf_1 b1(.A(n0), .X(n1));
wire n2; sg13g2_buf_1 b2(.A(n1), .X(n2));
wire n3; sg13g2_buf_1 b3(.A(n2), .X(n3));
wire n4; sg13g2_buf_1 b4(.A(n3), .X(n4));
wire n5; sg13g2_buf_1 b5(.A(n4), .X(n5));
wire n6; sg13g2_buf_1 b6(.A(n5), .X(n6));
wire n7; sg13g2_buf_1 b7(.A(n6), .X(n7));
wire n8; sg13g2_buf_1 b8(.A(n7), .X(n8));
wire n9; sg13g2_buf_1 b9(.A(n8), .X(n9));
wire n10; sg13g2_buf_1 b10(.A(n9), .X(n10));
wire n11; sg13g2_buf_1 b11(.A(n10), .X(n11));
wire n12; sg13g2_buf_1 b12(.A(n11), .X(n12));
wire n13; sg13g2_buf_1 b13(.A(n12), .X(n13));
wire n14; sg13g2_buf_1 b14(.A(n13), .X(n14));
wire n15; sg13g2_buf_1 b15(.A(n14), .X(n15));
wire n16; sg13g2_buf_1 b16(.A(n15), .X(n16));
wire n17; sg13g2_buf_1 b17(.A(n16), .X(n17));
wire n18; sg13g2_buf_1 b18(.A(n17), .X(n18));
wire n19; sg13g2_buf_1 b19(.A(n18), .X(n19));
wire n20; sg13g2_buf_1 b20(.A(n19), .X(n20));
wire n21; sg13g2_buf_1 b21(.A(n20), .X(n21));
wire n22; sg13g2_buf_1 b22(.A(n21), .X(n22));
wire n23; sg13g2_buf_1 b23(.A(n22), .X(n23));
wire n24; sg13g2_buf_1 b24(.A(n23), .X(n24));
wire n25; sg13g2_buf_1 b25(.A(n24), .X(n25));
wire n26; sg13g2_buf_1 b26(.A(n25), .X(n26));
wire n27; sg13g2_buf_1 b27(.A(n26), .X(n27));
wire n28; sg13g2_buf_1 b28(.A(n27), .X(n28));
wire n29; sg13g2_buf_1 b29(.A(n28), .X(n29));
wire n30; sg13g2_buf_1 b30(.A(n29), .X(n30));
wire n31; sg13g2_buf_1 b31(.A(n30), .X(n31));
sg13g2_dfrbp_1 capture(.CLK(clk), .D(n31), .RESET_B(1'b1), .Q(data_out), .Q_N());
endmodule
