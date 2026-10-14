// SPDX-License-Identifier: Apache-2.0
// Bounded dual-clock FIFO. Synchronizers are digital; no MTBF claim.
module lemma_usb_cdc_fifo #(parameter integer DATA_BITS=10,ADDR_BITS=7)(
 input logic wclk,rclk,reset,
 input logic wvalid,input logic [DATA_BITS-1:0] wdata,output logic wready,wempty,
 output logic rvalid,output logic [DATA_BITS-1:0] rdata,input logic rready
);
 localparam integer DEPTH=1<<ADDR_BITS;
 logic [DATA_BITS-1:0] memory[0:DEPTH-1];
 logic [ADDR_BITS:0] wbin,rbin,wgray,rgray;
 logic [ADDR_BITS:0] rgray_w1,rgray_w2,wgray_r1,wgray_r2;
 logic wfull,rempty;
 logic wlocal1,wlocal2,rlocal1,rlocal2,rup_w1,rup_w2,wup_r1,wup_r2;
 wire wfire=wvalid&&wready,rfire=rvalid&&rready;
 wire [ADDR_BITS:0] wnext=wbin+{{ADDR_BITS{1'b0}},wfire};
 wire [ADDR_BITS:0] rnext=rbin+{{ADDR_BITS{1'b0}},rfire};
 wire [ADDR_BITS:0] wgray_next=(wnext>>1)^wnext,rgray_next=(rnext>>1)^rnext;
 wire [ADDR_BITS:0] full_compare={~rgray_w2[ADDR_BITS:ADDR_BITS-1],rgray_w2[ADDR_BITS-2:0]};
 assign wready=wlocal2&&rup_w2&&!wfull;
 assign wempty=wgray==rgray_w2;
 assign rvalid=rlocal2&&wup_r2&&!rempty;
 assign rdata=rvalid?memory[rbin[ADDR_BITS-1:0]]:'0;
 always_ff @(posedge wclk or posedge reset)begin
  if(reset)begin wbin<=0;wgray<=0;rgray_w1<=0;rgray_w2<=0;wfull<=0;
   wlocal1<=0;wlocal2<=0;rup_w1<=0;rup_w2<=0;end
  else begin
   wlocal1<=1;wlocal2<=wlocal1;rup_w1<=rlocal2;rup_w2<=rup_w1;
   rgray_w1<=rgray;rgray_w2<=rgray_w1;
   if(wfire)memory[wbin[ADDR_BITS-1:0]]<=wdata;
   wbin<=wnext;wgray<=wgray_next;wfull<=wgray_next==full_compare;
  end
 end
 always_ff @(posedge rclk or posedge reset)begin
  if(reset)begin rbin<=0;rgray<=0;wgray_r1<=0;wgray_r2<=0;rempty<=1;
   rlocal1<=0;rlocal2<=0;wup_r1<=0;wup_r2<=0;end
  else begin
   rlocal1<=1;rlocal2<=rlocal1;wup_r1<=wlocal2;wup_r2<=wup_r1;
   wgray_r1<=wgray;wgray_r2<=wgray_r1;
   rbin<=rnext;rgray<=rgray_next;rempty<=rgray_next==wgray_r2;
  end
 end
endmodule
