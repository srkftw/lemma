// lemma-wifi-ofdm-data/1 integer circuitry. No complete 802.11ax or RF claim.
package lemma_wifi_math;
 function automatic logic [6:0] scramble_next(input logic [6:0] s);
  scramble_next={s[5:0],s[6]^s[3]};
 endfunction
 function automatic logic [1:0] bcc_pair(input logic [5:0] s,input logic b);
  logic [6:0] reg7;
  begin reg7={b,s};bcc_pair={^(reg7&7'o171),^(reg7&7'o133)};end
 endfunction
 function automatic logic [5:0] bcc_next(input logic [5:0] s,input logic b);
  bcc_next={b,s[5:1]};
 endfunction
 function automatic integer interleave48(input integer k);
  interleave48=3*(k%16)+k/16;
 endfunction
 function automatic integer data_bin(input integer d);
  integer k;
  begin
   if(d<5)k=d-26;else if(d<18)k=d-25;else if(d<24)k=d-24;
   else if(d<30)k=d-23;else if(d<43)k=d-22;else k=d-21;
   data_bin=k<0?k+64:k;
  end
 endfunction
 // Q14 nearest-integer cos(n*pi/32), quarter-wave symmetry. These are fixed
 // implementation coefficients, not measured analog data or vendor IP.
 function automatic logic signed [15:0] cosine(input integer phase);
  integer p,q;logic signed [15:0] value;
  begin
   p=phase&63;q=p<16?p:p<32?32-p:p<48?p-32:64-p;
   case(q)
    0:value=16'sd16384;1:value=16'sd16305;2:value=16'sd16069;3:value=16'sd15679;
    4:value=16'sd15137;5:value=16'sd14449;6:value=16'sd13623;7:value=16'sd12665;
    8:value=16'sd11585;9:value=16'sd10394;10:value=16'sd9102;11:value=16'sd7723;
    12:value=16'sd6270;13:value=16'sd4756;14:value=16'sd3196;15:value=16'sd1606;
    default:value=16'sd0;
   endcase
   cosine=(p>=16&&p<48)?-value:value;
  end
 endfunction
 function automatic logic signed [15:0] sine(input integer phase);
  sine=cosine(phase+48);
 endfunction
 function automatic logic [31:0] crc_octet(input logic [31:0] s,input logic [7:0] b);
  logic [31:0] c;
  begin c=s^{24'b0,b};for(integer j=0;j<8;j=j+1)c=(c>>1)^(c[0]?32'hedb88320:32'b0);crc_octet=c;end
 endfunction
 function automatic integer distance2(input logic [1:0] a,b);
  distance2=(a[0]==b[0]?0:1)+(a[1]==b[1]?0:1);
 endfunction
endpackage
