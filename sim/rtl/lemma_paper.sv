// SPDX-License-Identifier: Apache-2.0
// Paper v1 controller. Target/latch SRAM and the optical panel are external
// interfaces, never host implementations of these MMIO transactions.
module lemma_paper #(
  parameter int WIDTH = 512,
  parameter int HEIGHT = 640
) (
  input logic clk, reset_n,
  input logic valid, write,
  input logic [11:0] addr,
  input logic [2:0] size,
  input logic [63:0] wdata,
  output logic [63:0] rdata,
  output logic ready, error, irq,
  input logic [63:0] now_ticks,
  input logic [2047:0] descriptor,
  output logic fb_valid, fb_write,
  output logic [31:0] fb_addr,
  output logic [7:0] fb_wdata,
  input logic fb_ready, fb_error,
  input logic [7:0] fb_rdata,
  output logic panel_valid,
  input logic panel_ready,
  output logic [31:0] panel_x, panel_y,
  output logic [3:0] panel_gray,
  output logic panel_complete, panel_abort,
  output logic [63:0] panel_sequence
);
  localparam int PIXELS = WIDTH * HEIGHT;
  typedef enum logic [3:0] {CLEAR,IDLE,UPLOAD,SNAPSHOT_READ,SNAPSHOT_WRITE,
    WAIT_TIME,PANEL_READ,PANEL_SEND} state_t;
  state_t state;
  logic [7:0] aperture [512];
  logic [63:0] tile_x,tile_y,tile_w,tile_h,tile_len;
  logic [63:0] req_sequence,rect_x,rect_y,rect_w,rect_h,mode;
  logic [63:0] last_sequence,completed,fault,deadline;
  logic busy,done_flag,interrupted;
  logic [31:0] lx,ly,lw,lh,ix,iy,clear_index;
  logic [31:0] tx,ty,tw,th;
  logic [63:0] lm;
  logic [3:0] pixel_latch;
  logic aperture_access,control_access,accepted;
  integer byte_index;
  assign aperture_access = addr >= 2048 && {1'b0,addr} + (13'd1 << size) <= 2560 && size <= 3;
  assign control_access = size == 3 && addr[2:0] == 0;
  assign ready = !write || state == IDLE || state == WAIT_TIME ||
    (control_access && (addr == 176 || (addr == 104 && wdata == 2 && busy)));
  assign error = valid && ready && !(aperture_access || control_access);
  assign accepted = valid && ready && write;
  assign irq = done_flag || fault != 0 || interrupted;
  assign panel_sequence = last_sequence;

  // Each byte is one bounded register bank. Static byte addresses avoid a
  // 4096-bit variable-write barrel network while preserving unaligned 1..8
  // byte MMIO accesses. Validation gates every byte before any mutation.
  for (genvar byte_number=0; byte_number<512; byte_number++) begin: tile_bytes
    localparam logic [12:0] BYTE_ADDR = 13'(2048 + byte_number);
    logic byte_write;
    logic [2:0] write_lane;
    assign byte_write = accepted && aperture_access &&
      {1'b0,addr} <= BYTE_ADDR && BYTE_ADDR < {1'b0,addr} + (13'd1 << size);
    assign write_lane = 3'(BYTE_ADDR - {1'b0,addr});
    always @(posedge clk) begin
      if (!reset_n || (accepted && control_access && addr == 176 && wdata == 1))
        aperture[byte_number] <= 8'hff;
      else if (byte_write)
        aperture[byte_number] <= wdata[write_lane*8 +: 8];
    end
  end

  always_comb begin
    rdata = 0;
    if (aperture_access) begin
      for (int i=0;i<8;i++) if (i < (1 << size))
        rdata[i*8 +: 8] = aperture[int'(addr)-2048+i];
    end else if (control_access) begin
      if (addr >= 1024 && addr < 1280)
        rdata = descriptor[(addr-1024)*8 +: 64];
      else case(addr)
        0: rdata = 1280331856;
        8: rdata = 1;
        16: rdata = {60'b0,interrupted,fault != 0,done_flag,busy};
        24: rdata = fault;
        32: rdata = WIDTH;
        40: rdata = HEIGHT;
        48: rdata = (WIDTH+1)/2;
        56: rdata = 3;
        112: rdata = last_sequence;
        160: rdata = completed;
        default: rdata = 0;
      endcase
    end
    fb_valid = 0; fb_write = 0; fb_addr = 0; fb_wdata = 0;
    byte_index = 0;
    panel_valid = state == PANEL_SEND;
    panel_x = lx + ix; panel_y = ly + iy; panel_gray = pixel_latch;
    case(state)
      CLEAR: begin
        fb_valid = 1; fb_write = 1; fb_addr = clear_index; fb_wdata = 15;
      end
      UPLOAD: begin
        fb_valid = 1; fb_write = 1; fb_addr = (ty+iy)*WIDTH+tx+ix;
        byte_index = iy*((tw+1)/2) + ix/2;
        fb_wdata = ix[0] ? {4'b0,aperture[byte_index][3:0]} :
          {4'b0,aperture[byte_index][7:4]};
      end
      SNAPSHOT_READ: begin
        fb_valid = 1; fb_addr = (ly+iy)*WIDTH+lx+ix;
      end
      SNAPSHOT_WRITE: begin
        fb_valid = 1; fb_write = 1; fb_addr = PIXELS+(ly+iy)*WIDTH+lx+ix;
        fb_wdata = {4'b0,pixel_latch};
      end
      PANEL_READ: begin
        fb_valid = 1; fb_addr = PIXELS+(ly+iy)*WIDTH+lx+ix;
      end
      default: begin end
    endcase
  end

  task automatic advance_pixel(input state_t next_pixel,input state_t last_pixel);
    begin
      if (ix+1 < lw) begin ix <= ix+1; state <= next_pixel; end
      else if (iy+1 < lh) begin ix <= 0; iy <= iy+1; state <= next_pixel; end
      else begin ix <= 0; iy <= 0; state <= last_pixel; end
    end
  endtask

  always @(posedge clk) begin
    panel_complete <= 0; panel_abort <= 0;
    if (!reset_n) begin
      state <= CLEAR; clear_index <= 0;
      tile_x <= 0; tile_y <= 0; tile_w <= 0; tile_h <= 0; tile_len <= 0;
      req_sequence <= 0; rect_x <= 0; rect_y <= 0; rect_w <= 0; rect_h <= 0; mode <= 0;
      last_sequence <= 0; completed <= 0; fault <= 0; deadline <= 0;
      busy <= 0; done_flag <= 0; interrupted <= 0;
      lx <= 0; ly <= 0; lw <= 0; lh <= 0; ix <= 0; iy <= 0; lm <= 0; pixel_latch <= 15;
      tx <= 0; ty <= 0; tw <= 0; th <= 0;
    end else begin
      // RESET wins a simultaneous final-pixel handshake. Staged optical data
      // is aborted; no completion pulse or sequence publication may escape.
      if (!(accepted && control_access && addr == 176 && wdata == 1)) begin
      case(state)
        CLEAR: if(fb_ready) begin
          if(fb_error) begin fault <= 1; state <= IDLE; end
          else if(clear_index+1 == PIXELS) begin clear_index <= 0; state <= IDLE; end
          else clear_index <= clear_index+1;
        end
        UPLOAD: if(fb_ready) begin
          if(fb_error) begin fault <= 1; state <= busy ? WAIT_TIME : IDLE; end
          else if(ix+1 < tw) ix <= ix+1;
          else if(iy+1 < th) begin ix <= 0; iy <= iy+1; end
          else begin ix <= 0; iy <= 0; state <= busy ? WAIT_TIME : IDLE; end
        end
        SNAPSHOT_READ: if(fb_ready) begin
          if(fb_error) begin fault <= 1; busy <= 0; state <= IDLE; panel_abort <= 1; end
          else begin
            pixel_latch <= lm == 1 ? (fb_rdata[3:0] < 8 ? 0 : 15) : fb_rdata[3:0];
            state <= SNAPSHOT_WRITE;
          end
        end
        SNAPSHOT_WRITE: if(fb_ready) begin
          if(fb_error) begin fault <= 1; busy <= 0; state <= IDLE; panel_abort <= 1; end
          else advance_pixel(SNAPSHOT_READ,WAIT_TIME);
        end
        WAIT_TIME: if(now_ticks >= deadline) begin ix <= 0; iy <= 0; state <= PANEL_READ; end
        PANEL_READ: if(fb_ready) begin
          if(fb_error) begin fault <= 1; busy <= 0; state <= IDLE; panel_abort <= 1; end
          else begin pixel_latch <= fb_rdata[3:0]; state <= PANEL_SEND; end
        end
        PANEL_SEND: if(panel_ready) begin
          advance_pixel(PANEL_READ,IDLE);
          if(ix+1 == lw && iy+1 == lh) begin
            busy <= 0; done_flag <= 1; completed <= last_sequence; panel_complete <= 1;
            if(lm == 2 && lx == 0 && ly == 0 && lw == WIDTH && lh == HEIGHT) interrupted <= 0;
          end
        end
        default: begin end
      endcase
      end
      if (accepted) begin
        if(aperture_access) begin end
        else if(!control_access) fault <= 1;
        else case(addr)
          64: tile_x <= wdata;
          72: tile_y <= wdata;
          80: tile_w <= wdata;
          88: tile_h <= wdata;
          96: tile_len <= wdata;
          112: req_sequence <= wdata;
          120: rect_x <= wdata;
          128: rect_y <= wdata;
          136: rect_w <= wdata;
          144: rect_h <= wdata;
          152: mode <= wdata;
          168: if(wdata == completed) begin done_flag <= 0; fault <= 0; end else fault <= 2;
          176: if(wdata == 1) begin
            // Warm reset cannot erase an earlier uncertain optical result.
            // Only a completed full-screen quality refresh clears Interrupted.
            if(busy || interrupted) begin interrupted <= 1; fault <= 6; end
            else fault <= 0;
            busy <= 0; done_flag <= 0; state <= CLEAR; clear_index <= 0; panel_abort <= 1;
            tile_x <= 0; tile_y <= 0; tile_w <= 0; tile_h <= 0; tile_len <= 0;
            rect_x <= 0; rect_y <= 0; rect_w <= 0; rect_h <= 0; mode <= 0; req_sequence <= 0;
          end else fault <= 1;
          104: if(wdata == 1) begin
            if(tile_w == 0 || tile_h == 0 || tile_w > 32 || tile_h > 32 ||
               tile_x >= WIDTH || tile_y >= HEIGHT || tile_w > WIDTH-tile_x || tile_h > HEIGHT-tile_y ||
               tile_len != ((tile_w+1)/2)*tile_h || tile_len > 512) fault <= 3;
            else begin
              tx <= tile_x[31:0]; ty <= tile_y[31:0]; tw <= tile_w[31:0]; th <= tile_h[31:0];
              ix <= 0; iy <= 0; state <= UPLOAD;
            end
          end else if(wdata == 2) begin
            if(busy) fault <= 4;
            else if(rect_w == 0 || rect_h == 0 || rect_x >= WIDTH || rect_y >= HEIGHT ||
              rect_w > WIDTH-rect_x || rect_h > HEIGHT-rect_y || mode < 1 || mode > 2) fault <= 3;
            else if(req_sequence == 0 || req_sequence <= last_sequence ||
              now_ticks > 64'hffffffffffffffff - (mode == 1 ? 20000 : 250000)) fault <= 5;
            else begin
              lx <= rect_x[31:0]; ly <= rect_y[31:0]; lw <= rect_w[31:0]; lh <= rect_h[31:0];
              lm <= mode; ix <= 0; iy <= 0;
              last_sequence <= req_sequence; busy <= 1;
              deadline <= now_ticks + (mode == 1 ? 20000 : 250000); state <= SNAPSHOT_READ;
            end
          end else fault <= 1;
          default: fault <= 1;
        endcase
      end
    end
  end
endmodule
