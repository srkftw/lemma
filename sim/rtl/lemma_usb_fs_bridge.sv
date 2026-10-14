// SPDX-License-Identifier: Apache-2.0
// Raw byte/abort transport across controller100MHz/PHY48MHz domains.
module lemma_usb_fs_bridge(
 input logic clk,phy_clk,reset,enabled,connected,input logic [1:0] line_in,
 input logic tx_valid,tx_last,input logic [7:0] tx_byte,output logic tx_ready,
 output logic tx_oe,tx_busy,output logic [1:0] line_out,
 output logic rx_valid,rx_last,output logic [7:0] rx_byte,input logic rx_ready,
 output logic rx_abort,bus_reset,controller_busy,
 output logic [63:0] sample_ticks,tx_packets,rx_packets,stuff_errors,line_errors,underflows
);
 logic en1,en2,con1,con2;
 logic p_tx_valid,p_tx_last,p_tx_ready,p_rx_valid,p_rx_last,p_rx_ready,p_rx_abort,p_reset,p_busy,p_tx_busy;
 logic [7:0] p_tx_byte,p_rx_byte;
 logic [8:0] tx_fifo_head;
 logic [9:0] rx_fifo_head;
 logic tx_empty,rx_empty,rx_fifo_ready,rx_fifo_valid,abort_pending,phy_reset1,phy_reset2;
 logic busy1,busy2,txbusy1,txbusy2,reset1,reset2;
 logic consumed_toggle,consumed_p1,consumed_p2,consumed_seen,rx_locked;
 wire cancel=reset||!enabled||!connected||p_reset;
 lemma_usb_cdc_fifo #(.DATA_BITS(9)) to_phy(.wclk(clk),.rclk(phy_clk),.reset(cancel),
  .wvalid(tx_valid),.wdata({tx_last,tx_byte}),.wready(tx_ready),.wempty(tx_empty),
  .rvalid(p_tx_valid),.rdata(tx_fifo_head),.rready(p_tx_ready&&!phy_reset2));
 assign {p_tx_last,p_tx_byte}=tx_fifo_head;
 lemma_usb_cdc_fifo #(.DATA_BITS(10)) to_controller(.wclk(phy_clk),.rclk(clk),.reset(cancel),
  .wvalid(abort_pending||p_rx_valid),.wdata(abort_pending?10'h200:{1'b0,p_rx_last,p_rx_byte}),
  .wready(rx_fifo_ready),.wempty(rx_empty),.rvalid(rx_fifo_valid),.rdata(rx_fifo_head),.rready(rx_fifo_head[9]||rx_ready));
 assign p_rx_ready=rx_fifo_ready&&!abort_pending;
 assign rx_valid=rx_fifo_valid&&!rx_fifo_head[9];
 assign rx_abort=rx_fifo_valid&&rx_fifo_head[9];
 assign {rx_last,rx_byte}=rx_fifo_head[8:0];
 assign bus_reset=reset2;
 assign tx_busy=!tx_empty||txbusy2;
 assign controller_busy=!tx_empty||rx_fifo_valid||busy2;
 always_ff @(posedge clk or posedge reset)begin
  if(reset)begin busy1<=0;busy2<=0;txbusy1<=0;txbusy2<=0;reset1<=0;reset2<=0;end
  else begin busy1<=p_busy||!rx_empty||rx_locked;busy2<=busy1;txbusy1<=p_tx_busy;txbusy2<=txbusy1;reset1<=p_reset;reset2<=reset1;end
 end
 always_ff @(posedge clk or posedge cancel)begin
  if(cancel)consumed_toggle<=0;
  else if(rx_fifo_valid&&(rx_fifo_head[9]||rx_ready)&&(rx_fifo_head[9]||rx_fifo_head[8]))consumed_toggle<=!consumed_toggle;
 end
 always_ff @(posedge phy_clk or posedge cancel)begin
  if(cancel)begin consumed_p1<=0;consumed_p2<=0;consumed_seen<=0;rx_locked<=0;end
  else begin
   consumed_p1<=consumed_toggle;consumed_p2<=consumed_p1;
   if(consumed_p2!=consumed_seen)begin consumed_seen<=consumed_p2;rx_locked<=0;end
   if(rx_fifo_ready&&(abort_pending||(p_rx_valid&&p_rx_last)))rx_locked<=1;
  end
 end
 always_ff @(posedge phy_clk or posedge reset)begin
  if(reset)begin en1<=0;en2<=0;con1<=0;con2<=0;abort_pending<=0;phy_reset1<=1;phy_reset2<=1;end
  else begin
   phy_reset1<=0;phy_reset2<=phy_reset1;
   en1<=enabled;en2<=en1;con1<=connected;con2<=con1;
   if(!en2||!con2||p_reset)abort_pending<=0;
   else if(p_rx_abort)abort_pending<=1;
   else if(abort_pending&&rx_fifo_ready)abort_pending<=0;
  end
 end
 lemma_usb_fs_phy_clocked transceiver(.clk(phy_clk),.reset(phy_reset2),.enabled(en2),.connected(con2),.line_in,
  .tx_valid(p_tx_valid),.tx_last(p_tx_last),.tx_byte(p_tx_byte),.tx_ready(p_tx_ready),
  .tx_oe,.tx_busy(p_tx_busy),.line_out,.rx_valid(p_rx_valid),.rx_last(p_rx_last),.rx_byte(p_rx_byte),.rx_ready(p_rx_ready),.rx_admit(!rx_locked&&!abort_pending),
  .rx_abort(p_rx_abort),.bus_reset(p_reset),.controller_busy(p_busy),.sample_ticks,.tx_packets,.rx_packets,.stuff_errors,.line_errors,.underflows);
endmodule
