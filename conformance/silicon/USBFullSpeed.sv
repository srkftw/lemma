// SPDX-License-Identifier: Apache-2.0
module USBFullSpeed (
 input logic clk,reset,connected,
 input logic host_valid,host_last,input logic [7:0] host_byte,output logic host_ready,
 output logic host_rx_valid,host_rx_last,output logic [7:0] host_rx_byte,input logic host_rx_ready,
 input logic force_wire,input logic [1:0] force_line,
 input logic mmio_valid,mmio_write,input logic [9:0] mmio_addr,input logic [63:0] mmio_wdata,
 output logic [63:0] mmio_rdata,output logic mmio_error,
 output logic [1:0] wire_line,host_line,chip_line,output logic host_oe,chip_oe,
 output logic [63:0] host_rx_packets,host_tx_packets,chip_rx_packets,chip_tx_packets,
 output logic [63:0] host_stuff_errors,chip_stuff_errors,host_line_errors,chip_line_errors,
 output logic [63:0] controller_errors,hs,cs,hu,cu,ct,crx,ctx,
 output logic hb,cb,htb,ctb,hr,ha,ready,busy,
 output logic [6:0] device_address,output logic configured,irq
);
 logic chip_rx_valid,chip_rx_last,chip_rx_ready,chip_abort,chip_reset;
 logic [7:0] chip_rx_byte;
 logic chip_tx_valid,chip_tx_last,chip_tx_ready;
 logic [7:0] chip_tx_byte;
 assign wire_line=force_wire?force_line:host_oe&&chip_oe&&host_line!=chip_line?2'b11:
                  host_oe?host_line:chip_oe?chip_line:2'b01;
 lemma_usb_fs_phy host(.clk,.reset,.enabled(1'b1),.connected,.line_in(wire_line),
   .tx_valid(host_valid),.tx_last(host_last),.tx_byte(host_byte),.tx_ready(host_ready),
   .tx_oe(host_oe),.tx_busy(htb),.line_out(host_line),.rx_valid(host_rx_valid),.rx_last(host_rx_last),
   .rx_byte(host_rx_byte),.rx_ready(host_rx_ready),.rx_abort(ha),.bus_reset(hr),.controller_busy(hb),
   .sample_ticks(hs),.tx_packets(host_tx_packets),.rx_packets(host_rx_packets),
   .stuff_errors(host_stuff_errors),.line_errors(host_line_errors),.underflows(hu));
 lemma_usb_fs_phy chip(.clk,.reset,.enabled(1'b1),.connected,.line_in(wire_line),
   .tx_valid(chip_tx_valid),.tx_last(chip_tx_last),.tx_byte(chip_tx_byte),.tx_ready(chip_tx_ready),
   .tx_oe(chip_oe),.tx_busy(ctb),.line_out(chip_line),.rx_valid(chip_rx_valid),.rx_last(chip_rx_last),
   .rx_byte(chip_rx_byte),.rx_ready(chip_rx_ready),.rx_abort(chip_abort),.bus_reset(chip_reset),.controller_busy(cb),
   .sample_ticks(cs),.tx_packets(chip_tx_packets),.rx_packets(chip_rx_packets),
   .stuff_errors(chip_stuff_errors),.line_errors(chip_line_errors),.underflows(cu));
 lemma_usb_device #(.PHY_ABORT(1)) endpoint(.clk,.reset,.enabled(1'b1),.connected,.bus_reset(chip_reset),
   .valid(mmio_valid),.write(mmio_write),.addr(mmio_addr),.size(3'd3),.wdata(mmio_wdata),
   .rdata(mmio_rdata),.ready,.error(mmio_error),.irq,.controller_busy(busy),
   .rx_valid(chip_rx_valid),.rx_last(chip_rx_last),.rx_byte(chip_rx_byte),.rx_ready(chip_rx_ready),.rx_abort(chip_abort),
   .tx_valid(chip_tx_valid),.tx_last(chip_tx_last),.tx_byte(chip_tx_byte),.tx_ready(chip_tx_ready),
   .ticks(ct),.rx_packets(crx),.tx_packets(ctx),.packet_errors(controller_errors),.device_address,.configured);
endmodule
