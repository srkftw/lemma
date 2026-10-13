// Literal component fixture; not a SoC mapping or target software.
module WiFiDataProbe (
 input logic clk,reset,enabled,coex_allow,
 input logic valid,write,input logic [9:0] addr,input logic [2:0] size,
 input logic [63:0] wdata,output logic [63:0] rdata,
 output logic ready,error,irq,controller_busy,
 input logic rx_sample_valid,input logic signed [15:0] rx_i,rx_q,
 output logic tx_sample_valid,output logic signed [15:0] tx_i,tx_q,
 output logic [63:0] ticks,tx_packets,rx_packets,tx_wire_samples,rx_wire_samples,
 output logic tx_active,rx_active,output logic [7:0] last_fault,output logic [9:0] last_metric,
 input logic [23:0] probe_bits,input logic [5:0] probe_state,probe_index,
 input logic probe_pilot,output logic [47:0] probe_encoded,probe_interleaved,
 output logic [5:0] probe_final,output logic signed [15:0] probe_i,probe_q,
 output logic [2:0] observed_decode_phase
);
 lemma_wifi_ofdm_data dut(.*);
 lemma_wifi_bcc_symbol symbol(.bits_in(probe_bits),.initial_state(probe_state),
  .encoded(probe_encoded),.interleaved(probe_interleaved),.final_state(probe_final));
 lemma_wifi_ofdm_modulator known_sample(.bits_in(probe_interleaved),.pilot_negative(probe_pilot),
  .sample_index(probe_index),.i(probe_i),.q(probe_q));
 assign observed_decode_phase=dut.decode_phase;
endmodule
