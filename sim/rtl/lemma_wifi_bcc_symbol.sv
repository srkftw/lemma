// Reusable 24-input-bit -> 48 coded/interleaved bits component. It is a common
// legacy SIGNAL/DATA coding dependency; it does not construct an HE preamble.
module lemma_wifi_bcc_symbol (
 input logic [23:0] bits_in,input logic [5:0] initial_state,
 output logic [47:0] encoded,interleaved,output logic [5:0] final_state
);
 import lemma_wifi_math::*;
 logic [5:0] state;logic [1:0] pair;
 always_comb begin
  state=initial_state;encoded=0;interleaved=0;pair=0;
  for(integer k=0;k<24;k=k+1)begin
   pair=bcc_pair(state,bits_in[k]);state=bcc_next(state,bits_in[k]);
   encoded[2*k]=pair[0];encoded[2*k+1]=pair[1];
   interleaved[interleave48(2*k)]=pair[0];interleaved[interleave48(2*k+1)]=pair[1];
  end
  final_state=state;
 end
endmodule

// Real complex baseband sample values, 64-point IFFT normalization, signed Q14.
// The caller selects n including the cyclic prefix. There is no bit-wire
// substitute for the waveform; the receiver consumes these I/Q values.
module lemma_wifi_ofdm_modulator (
 input logic [47:0] bits_in,input logic pilot_negative,
 input logic [5:0] sample_index,output logic signed [15:0] i,q
);
 import lemma_wifi_math::*;
 integer sum_i,sum_q,c,s,sign_value;
 always_comb begin
  sum_i=0;sum_q=0;c=0;s=0;sign_value=0;
  for(integer d=0;d<48;d=d+1)begin
   c=int'(cosine(data_bin(d)*int'(sample_index)));s=int'(sine(data_bin(d)*int'(sample_index)));
   sign_value=bits_in[d]?1:-1;sum_i=sum_i+sign_value*c;sum_q=sum_q+sign_value*s;
  end
  for(integer d=0;d<4;d=d+1)begin
   c=int'(cosine((d==0?43:d==1?57:d==2?7:21)*int'(sample_index)));
   s=int'(sine((d==0?43:d==1?57:d==2?7:21)*int'(sample_index)));
   sign_value=(pilot_negative^(d==3))?-1:1;sum_i=sum_i+sign_value*c;sum_q=sum_q+sign_value*s;
  end
  i=16'(sum_i>>>6);q=16'(sum_q>>>6);
 end
endmodule
