// Host-clocked raw controller fixture; no replacement processor or guest.
module PaperExecutedState(
  input logic clk,reset_n,valid,write,fb_stall,fb_error,panel_ready,
  input logic[11:0]addr,input logic[2:0]size,input logic[63:0]wdata,now_ticks,
  output logic[63:0]rdata,sequence_id,
  output logic ready,error,panel_valid,panel_complete,panel_abort,drive_valid,power_enable,
  output logic[31:0]panel_x,panel_y,drive_x,drive_y,
  output logic[3:0]panel_gray,output logic[1:0]drive_phase,drive_code);
  logic fb_valid,fb_write;
  logic[31:0]fb_addr;
  logic[7:0]fb_wdata,fb_rdata;
  logic[7:0]frames[64];
  assign fb_rdata=frames[fb_addr];
  always @(posedge clk) if(fb_valid&&!fb_stall&&fb_write&&!fb_error)
    frames[fb_addr]<=fb_wdata;
  lemma_paper #(.WIDTH(8),.HEIGHT(4),.VERSION(3),.STAGING_OFFSET(3584),.ENABLE_SEQUENCER(1)) paper(
    .clk,.reset_n,.valid,.write,.addr,.size,.wdata,.now_ticks,.rdata,.ready,.error,
    .descriptor(2048'b0),.fb_valid,.fb_write,.fb_addr,.fb_wdata,.fb_rdata,
    .fb_ready(!fb_stall),.fb_error,.panel_ready,.panel_valid,.panel_complete,.panel_abort,
    .panel_sequence(sequence_id),.panel_x,.panel_y,.panel_gray,
    .panel_drive_valid(drive_valid),.panel_power_enable(power_enable),
    .panel_drive_phase(drive_phase),.panel_drive_code(drive_code),
    .panel_drive_x(drive_x),.panel_drive_y(drive_y));
endmodule
