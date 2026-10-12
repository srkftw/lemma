// SPDX-License-Identifier: Apache-2.0
// Paper v1 controller: registered MMIO, bounded geometry, banked tile registers.
// Target/latch SRAM and the optical panel remain external interfaces.
module lemma_paper #(
  parameter int WIDTH = 512,
  parameter int HEIGHT = 640,
  parameter bit ENABLE_SEQUENCER = 0
) (
  input logic clk, reset_n,
  input logic valid, write,
  input logic [11:0] addr,
  input logic [2:0] size,
  input logic [63:0] wdata,
  output logic [63:0] rdata,
  output logic ready, error, irq,
  output logic controller_busy,
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
  output logic [63:0] panel_sequence,
  output logic panel_drive_valid, panel_power_enable,
  output logic panel_gate_clock, panel_source_clock,
  output logic [1:0] panel_drive_phase, panel_drive_code,
  output logic [31:0] panel_drive_x, panel_drive_y
);
  localparam int PIXELS = WIDTH * HEIGHT;
  localparam int X_BITS = WIDTH > 1 ? $clog2(WIDTH) : 1;
  localparam int Y_BITS = HEIGHT > 1 ? $clog2(HEIGHT) : 1;
  localparam int W_BITS = $clog2(WIDTH+1);
  localparam int H_BITS = $clog2(HEIGHT+1);
  localparam int FRAME_BITS = PIXELS > 1 ? $clog2(PIXELS) : 1;
  localparam int TILE_X_END = (X_BITS > 6 ? X_BITS : 6)+1;
  localparam int TILE_Y_END = (Y_BITS > 6 ? Y_BITS : 6)+1;
  typedef enum logic [4:0] {CLEAR,IDLE,UPLOAD,SNAPSHOT_READ,SNAPSHOT_WRITE,
    WAIT_TIME,PANEL_READ,PANEL_SEND,UPLOAD_SELECT,UPLOAD_BANKS,UPLOAD_VALUE,
    POWER_UP,SCAN_READ,SCAN_DRIVE,PHASE_GAP,POWER_DOWN} state_t;
  state_t state;
  logic [63:0] tile_x,tile_y,tile_w,tile_h,tile_len;
  logic [63:0] req_sequence,rect_x,rect_y,rect_w,rect_h,mode;
  logic [63:0] last_sequence,completed,fault,deadline;
  logic busy,done_flag,interrupted;
  assign controller_busy = busy || state != IDLE;
  logic [X_BITS-1:0] lx,ix;
  logic [Y_BITS-1:0] ly,iy;
  logic [W_BITS-1:0] lw;
  logic [H_BITS-1:0] lh;
  logic [5:0] tw,th;
  logic [FRAME_BITS-1:0] clear_index,frame_cursor,frame_start,tile_cursor;
  logic [W_BITS:0] frame_row_step,tile_row_step;
  logic [8:0] tile_byte_row,tile_byte_index;
  logic [5:0] tile_row_bytes;
  logic [63:0] upload_row_select,upload_bank_latched;
  logic [2:0] upload_lane_select;
  logic [7:0] upload_byte_latch,first_upload_byte;
  logic [1:0] lm;
  logic [3:0] pixel_latch;
  logic [1:0] wave_phase, drive_remaining, power_remaining;
  logic [63:0] drive_clocks, scan_beats;
  logic sequencer_power;
  // virtual-panel-synthetic/1 is deliberately old-pixel independent. Codes
  // are logical symbols, not voltage levels or qualified panel waveforms:
  // condition(3), desired dark/light(1/2), neutral(0), each held two clocks.
  assign sequencer_power = ENABLE_SEQUENCER && (state==POWER_UP || state==SCAN_READ ||
    state==SCAN_DRIVE || state==PHASE_GAP || state==PANEL_READ || state==PANEL_SEND || state==POWER_DOWN);
  assign panel_power_enable = reset_n && !reset_command && sequencer_power;
  assign panel_drive_valid = reset_n && !reset_command && ENABLE_SEQUENCER && state==SCAN_DRIVE;
  assign panel_drive_phase = ENABLE_SEQUENCER ? wave_phase : 0;
  assign panel_drive_x = panel_drive_valid ? 32'(lx)+32'(ix) : 0;
  assign panel_drive_y = panel_drive_valid ? 32'(ly)+32'(iy) : 0;
  assign panel_drive_code = !panel_drive_valid ? 0 : wave_phase==0 ? 3 :
    wave_phase==1 ? (pixel_latch<8 ? 1 : 2) : 0;
  assign panel_source_clock = panel_drive_valid && drive_remaining==2;
  assign panel_gate_clock = panel_source_clock && ix==0;

  // A request is captured once, then acknowledged only when its operation
  // can execute. The master holds valid through ready. No raw address/data
  // input drives a tile byte write or the command acceptance logic.
  typedef enum logic [1:0] {READ_SELECT,READ_BANKS,READ_VALUE,READ_READY} read_state_t;
  read_state_t read_state;
  logic request_pending,request_write,response_valid,response_error;
  logic [63:0] response_data,control_read_value,control_read_latched;
  logic [31:0] descriptor_select;
  logic [63:0] bank_read_latched,bank_read_word,rotated_read_word,read_mask;
  logic [11:0] op_addr;
  logic [2:0] op_size;
  logic [63:0] op_wdata;
  logic aperture_access,control_access,accepted,reset_command,write_admitted;
  logic [3:0] transfer_bytes;
  assign transfer_bytes = 4'b0001 << op_size;
  assign aperture_access = op_addr >= 2048 && op_addr < 2560 && op_size <= 3 &&
    {1'b0,op_addr} + {9'b0,transfer_bytes} <= 2560;
  assign control_access = op_size == 3 && op_addr[2:0] == 0;
  assign write_admitted=state==IDLE || state==WAIT_TIME ||
    (control_access && (op_addr==176 || (op_addr==104 && op_wdata==2 && busy)));
  assign ready=reset_n && request_pending && (request_write ? write_admitted : response_valid);
  assign error = valid && ready && (request_write ? !(aperture_access || control_access) : response_error);
  assign accepted = valid && ready && request_write;
  assign reset_command = accepted && control_access && op_addr == 176 && op_wdata == 1;
  assign irq = done_flag || fault != 0 || interrupted;
  assign panel_sequence = last_sequence;
  always @(posedge clk) begin
    if (!reset_n) begin
      request_pending<=0; request_write<=0; op_addr<=0; op_size<=0; op_wdata<=0;
      response_valid<=0; response_error<=0; response_data<=0; control_read_latched<=0;
      descriptor_select<=0; read_state<=READ_SELECT;
    end else if (!valid || ready) begin request_pending<=0; response_valid<=0; end
    else if (!request_pending) begin
      request_pending<=1; request_write<=write; op_addr<=addr; op_size<=size; op_wdata<=wdata;
      response_valid<=0; read_state<=READ_SELECT;
    end else if (!request_write) case(read_state)
      READ_SELECT: begin
        for(int word=0;word<32;word++) descriptor_select[word]<=op_addr[7:3]==5'(word);
        read_state<=READ_BANKS;
      end
      READ_BANKS: begin control_read_latched<=control_read_value; read_state<=READ_VALUE; end
      READ_VALUE: begin
        response_data<=aperture_access ? (rotated_read_word & read_mask) : control_read_latched;
        response_error<=!(aperture_access || control_access); response_valid<=1; read_state<=READ_READY;
      end
      default: begin end
    endcase
  end

  // Retain full 64-bit staging. Narrow operands are used only after all upper
  // bits have been checked, so high-bit malformed coordinates cannot wrap.
  logic tile_valid,rectangle_valid;
  logic [5:0] tile_width,tile_height,packed_row_bytes;
  logic [11:0] packed_bytes;
  logic [TILE_X_END-1:0] tile_right;
  logic [TILE_Y_END-1:0] tile_bottom;
  logic [W_BITS:0] rectangle_right;
  logic [H_BITS:0] rectangle_bottom;
  assign tile_width=tile_w[5:0]; assign tile_height=tile_h[5:0];
  assign packed_row_bytes=6'(({1'b0,tile_width}+7'd1)>>1);
  assign packed_bytes=12'(packed_row_bytes)*12'(tile_height);
  assign tile_right=TILE_X_END'(tile_x[X_BITS-1:0])+TILE_X_END'(tile_width);
  assign tile_bottom=TILE_Y_END'(tile_y[Y_BITS-1:0])+TILE_Y_END'(tile_height);
  assign tile_valid=tile_x[63:X_BITS]==0 && tile_y[63:Y_BITS]==0 && tile_w[63:6]==0 &&
    tile_h[63:6]==0 && tile_len[63:10]==0 && tile_width!=0 && tile_width<=32 &&
    tile_height!=0 && tile_height<=32 && (X_BITS+1)'(tile_x[X_BITS-1:0])<(X_BITS+1)'(WIDTH) && (Y_BITS+1)'(tile_y[Y_BITS-1:0])<(Y_BITS+1)'(HEIGHT) &&
    tile_right<=TILE_X_END'(WIDTH) && tile_bottom<=TILE_Y_END'(HEIGHT) && {2'b0,tile_len[9:0]}==packed_bytes && packed_bytes<=512;
  assign rectangle_right=(W_BITS+1)'(rect_x[X_BITS-1:0])+(W_BITS+1)'(rect_w[W_BITS-1:0]);
  assign rectangle_bottom=(H_BITS+1)'(rect_y[Y_BITS-1:0])+(H_BITS+1)'(rect_h[H_BITS-1:0]);
  assign rectangle_valid=rect_x[63:X_BITS]==0 && rect_y[63:Y_BITS]==0 &&
    rect_w[63:W_BITS]==0 && rect_h[63:H_BITS]==0 && rect_w[W_BITS-1:0]!=0 && rect_h[H_BITS-1:0]!=0 &&
    (X_BITS+1)'(rect_x[X_BITS-1:0])<(X_BITS+1)'(WIDTH) && (Y_BITS+1)'(rect_y[Y_BITS-1:0])<(Y_BITS+1)'(HEIGHT) && rectangle_right<=(W_BITS+1)'(WIDTH) &&
    rectangle_bottom<=(H_BITS+1)'(HEIGHT) && (mode==1 || mode==2);

  // Eight independent byte lanes, with one shared row/byte selection per
  // lane. Unaligned accesses wrap across adjacent rows, never across the
  // aperture boundary. Each row has a small local six-bit write decode.
  logic [7:0] upload_byte;
  assign tile_byte_index=tile_byte_row+9'(ix>>1);
  for (genvar lane=0;lane<8;lane++) begin: tile_lanes
    logic [7:0] bytes [64];
    logic [2:0] displacement;
    logic [5:0] access_row;
    logic lane_write;
    logic [7:0] lane_wdata;
    assign displacement=3'(lane)-op_addr[2:0];
    assign access_row=op_addr[8:3]+6'(lane<op_addr[2:0]);
    assign lane_write=accepted && aperture_access && {1'b0,displacement}<transfer_bytes;
    assign lane_wdata=op_wdata[displacement*8 +: 8];
    logic [63:0] read_select;
    logic [7:0] selected_byte;
    // Registered one-hot rows put the bank selection close to its eight data
    // bits. No six-bit address net drives every bank's read multiplexer.
    always @(posedge clk) begin
      if (!reset_n) read_select<=0;
      else if(valid && request_pending && !request_write && read_state==READ_SELECT)
        for(int row=0;row<64;row++) read_select[row]<=access_row==6'(row);
      if (!reset_n) bank_read_latched[lane*8 +: 8]<=0;
      else if(valid && request_pending && !request_write && read_state==READ_BANKS)
        bank_read_latched[lane*8 +: 8]<=selected_byte;
    end
    always_comb begin
      selected_byte=0;
      for(int row=0;row<64;row++) selected_byte|=bytes[row] & {8{read_select[row]}};
    end
    logic [7:0] selected_upload_byte;
    always_comb begin
      selected_upload_byte=0;
      for(int row=0;row<64;row++) selected_upload_byte|=bytes[row] & {8{upload_row_select[row]}};
    end
    if(lane==0) assign first_upload_byte=bytes[0];
    always @(posedge clk) begin
      if(!reset_n) upload_bank_latched[lane*8 +: 8]<=8'hff;
      else if(state==UPLOAD_BANKS && !reset_command)
        upload_bank_latched[lane*8 +: 8]<=selected_upload_byte;
    end
    for (genvar row=0;row<64;row++) begin: rows
      always @(posedge clk) begin
        if (!reset_n || reset_command) bytes[row]<=8'hff;
        else if (lane_write && access_row==6'(row)) bytes[row]<=lane_wdata;
      end
    end
  end
  always_comb begin
    bank_read_word=bank_read_latched;
    rotated_read_word=(bank_read_word >> (op_addr[2:0]*8)) | (bank_read_word << ((8-op_addr[2:0])*8));
    case(op_size)
      0: read_mask=64'hff;
      1: read_mask=64'hffff;
      2: read_mask=64'hffffffff;
      3: read_mask=64'hffffffffffffffff;
      default: read_mask=0;
    endcase
    upload_byte=upload_bank_latched[upload_lane_select*8 +: 8];
    rdata=response_data;
    control_read_value=0;
    if(control_access) begin
      if(op_addr>=1024 && op_addr<1280) begin
        for(int word=0;word<32;word++)
          control_read_value|=descriptor[word*64 +: 64] & {64{descriptor_select[word]}};
      end else case(op_addr)
        0: control_read_value=1280331856;
        8: control_read_value=1;
        16: control_read_value={60'b0,interrupted,fault!=0,done_flag,busy};
        24: control_read_value=fault;
        32: control_read_value=64'(WIDTH);
        40: control_read_value=64'(HEIGHT);
        48: control_read_value=(64'(WIDTH)+1)/2;
        56: control_read_value=3;
        112: control_read_value=last_sequence;
        160: control_read_value=completed;
        384: control_read_value=ENABLE_SEQUENCER ? 1 : 0;
        392: control_read_value=ENABLE_SEQUENCER ? 64'h31504d53 : 0;
        400: if(ENABLE_SEQUENCER) control_read_value={46'b0,drive_remaining,6'b0,wave_phase,7'b0,sequencer_power};
        408: if(ENABLE_SEQUENCER) control_read_value=32'(lx)+32'(ix);
        416: if(ENABLE_SEQUENCER) control_read_value=32'(ly)+32'(iy);
        424: if(ENABLE_SEQUENCER) control_read_value={62'b0,panel_drive_code};
        432: if(ENABLE_SEQUENCER) control_read_value=drive_clocks;
        440: if(ENABLE_SEQUENCER) control_read_value={63'b0,panel_power_enable};
        448: if(ENABLE_SEQUENCER) control_read_value=scan_beats;
        default: control_read_value=0;
      endcase
    end
    fb_valid=0; fb_write=0; fb_addr=0; fb_wdata=0;
    panel_valid=state==PANEL_SEND;
    panel_x=32'(lx)+32'(ix); panel_y=32'(ly)+32'(iy); panel_gray=pixel_latch;
    case(state)
      CLEAR: begin fb_valid=1; fb_write=1; fb_addr=32'(clear_index); fb_wdata=15; end
      UPLOAD: begin
        fb_valid=1; fb_write=1; fb_addr=32'(tile_cursor);
        fb_wdata=ix[0] ? {4'b0,upload_byte_latch[3:0]} : {4'b0,upload_byte_latch[7:4]};
      end
      SNAPSHOT_READ: begin fb_valid=1; fb_addr=32'(frame_cursor); end
      SNAPSHOT_WRITE: begin fb_valid=1; fb_write=1; fb_addr=PIXELS+32'(frame_cursor); fb_wdata={4'b0,pixel_latch}; end
      PANEL_READ,SCAN_READ: begin fb_valid=1; fb_addr=PIXELS+32'(frame_cursor); end
      default: begin end
    endcase
  end

  task automatic advance_pixel(input state_t next_pixel,input state_t last_pixel);
    begin
      if (W_BITS'(ix)!=(lw-1'b1)) begin ix<=ix+1'b1; frame_cursor<=frame_cursor+1'b1; state<=next_pixel; end
      else if (H_BITS'(iy)!=(lh-1'b1)) begin
        ix<=0; iy<=iy+1'b1; frame_cursor<=frame_cursor+FRAME_BITS'(frame_row_step); state<=next_pixel;
      end else begin ix<=0; iy<=0; frame_cursor<=frame_start; state<=last_pixel; end
    end
  endtask

  always @(posedge clk) begin
    panel_complete<=0; panel_abort<=0;
    if (!reset_n) begin
      state<=CLEAR; clear_index<=0;
      tile_x<=0; tile_y<=0; tile_w<=0; tile_h<=0; tile_len<=0;
      req_sequence<=0; rect_x<=0; rect_y<=0; rect_w<=0; rect_h<=0; mode<=0;
      last_sequence<=0; completed<=0; fault<=0; deadline<=0;
      busy<=0; done_flag<=0; interrupted<=0;
      lx<=0; ly<=0; lw<=0; lh<=0; ix<=0; iy<=0; lm<=0; pixel_latch<=15;
      tw<=0; th<=0; frame_cursor<=0; frame_start<=0; tile_cursor<=0;
      frame_row_step<=0; tile_row_step<=0; tile_byte_row<=0; tile_row_bytes<=0;
      upload_row_select<=0; upload_lane_select<=0; upload_byte_latch<=8'hff;
      wave_phase<=0; drive_remaining<=0; power_remaining<=0; drive_clocks<=0; scan_beats<=0;
    end else begin
      // RESET wins the actual acknowledgement edge, including a simultaneous
      // final panel handshake; capture alone has no device side effects.
      if (!reset_command) begin
        case(state)
          CLEAR: if(fb_ready) begin
            if(fb_error) begin fault<=1; state<=IDLE; end
            else if(clear_index==FRAME_BITS'(PIXELS-1)) begin clear_index<=0; state<=IDLE; end
            else clear_index<=clear_index+1'b1;
          end
          UPLOAD: if(fb_ready) begin
            if(fb_error) begin fault<=1; state<=busy?WAIT_TIME:IDLE; end
            else if(6'(ix)!=(tw-1'b1)) begin
              ix<=ix+1'b1; tile_cursor<=tile_cursor+1'b1;
              if(ix[0]) state<=UPLOAD_SELECT;
            end
            else if(6'(iy)!=(th-1'b1)) begin
              ix<=0; iy<=iy+1'b1; tile_cursor<=tile_cursor+FRAME_BITS'(tile_row_step);
              tile_byte_row<=tile_byte_row+9'(tile_row_bytes); state<=UPLOAD_SELECT;
            end else begin ix<=0; iy<=0; state<=busy?WAIT_TIME:IDLE; end
          end
          // Prepare the next packed byte while no frame transaction is
          // exposed. The selected byte then remains latched for both pixels
          // and throughout any frame backpressure. The first byte is fixed
          // aperture byte0 and is captured at command acceptance.
          UPLOAD_SELECT: begin
            for(int row=0;row<64;row++) upload_row_select[row]<=tile_byte_index[8:3]==6'(row);
            upload_lane_select<=tile_byte_index[2:0]; state<=UPLOAD_BANKS;
          end
          UPLOAD_BANKS: state<=UPLOAD_VALUE;
          UPLOAD_VALUE: begin upload_byte_latch<=upload_byte; state<=UPLOAD; end
          SNAPSHOT_READ: if(fb_ready) begin
            if(fb_error) begin fault<=1; busy<=0; state<=IDLE; panel_abort<=1; end
            else begin pixel_latch<=lm==1?(fb_rdata[3:0]<8?0:15):fb_rdata[3:0]; state<=SNAPSHOT_WRITE; end
          end
          SNAPSHOT_WRITE: if(fb_ready) begin
            if(fb_error) begin fault<=1; busy<=0; state<=IDLE; panel_abort<=1; end
            else advance_pixel(SNAPSHOT_READ,WAIT_TIME);
          end
          WAIT_TIME: if(now_ticks>=deadline) begin
            ix<=0; iy<=0; frame_cursor<=frame_start;
            if(ENABLE_SEQUENCER) begin state<=POWER_UP; power_remaining<=2; end
            else state<=PANEL_READ;
          end
          POWER_UP: if(power_remaining>1) power_remaining<=power_remaining-1'b1;
            else begin power_remaining<=0; state<=SCAN_READ; end
          SCAN_READ: if(fb_ready) begin
            if(fb_error) begin fault<=1; busy<=0; state<=IDLE; panel_abort<=1; end
            else begin pixel_latch<=fb_rdata[3:0]; drive_remaining<=2; state<=SCAN_DRIVE; end
          end
          SCAN_DRIVE: begin
            drive_clocks<=drive_clocks+1'b1;
            if(drive_remaining>1) drive_remaining<=drive_remaining-1'b1;
            else begin
              drive_remaining<=0; scan_beats<=scan_beats+1'b1;
              advance_pixel(SCAN_READ,PHASE_GAP);
            end
          end
          PHASE_GAP: if(wave_phase<2) begin wave_phase<=wave_phase+1'b1; state<=SCAN_READ; end
            else state<=PANEL_READ;
          PANEL_READ: if(fb_ready) begin
            if(fb_error) begin fault<=1; busy<=0; state<=IDLE; panel_abort<=1; end
            else begin pixel_latch<=fb_rdata[3:0]; state<=PANEL_SEND; end
          end
          PANEL_SEND: if(panel_ready) begin
            advance_pixel(PANEL_READ,ENABLE_SEQUENCER?POWER_DOWN:IDLE);
            if(W_BITS'(ix)==(lw-1'b1) && H_BITS'(iy)==(lh-1'b1)) begin
              if(ENABLE_SEQUENCER) power_remaining<=2;
              else begin
                busy<=0; done_flag<=1; completed<=last_sequence; panel_complete<=1;
                if(lm==2 && lx==0 && ly==0 && lw==W_BITS'(WIDTH) && lh==H_BITS'(HEIGHT)) interrupted<=0;
              end
            end
          end
          POWER_DOWN: if(power_remaining>1) power_remaining<=power_remaining-1'b1;
            else begin
              power_remaining<=0; state<=IDLE; busy<=0; done_flag<=1;
              completed<=last_sequence; panel_complete<=1;
              if(lm==2 && lx==0 && ly==0 && lw==W_BITS'(WIDTH) && lh==H_BITS'(HEIGHT)) interrupted<=0;
            end
          default: begin end
        endcase
      end
      if(accepted) begin
        if(aperture_access) begin end
        else if(!control_access) fault<=1;
        else case(op_addr)
          64: tile_x<=op_wdata;
          72: tile_y<=op_wdata;
          80: tile_w<=op_wdata;
          88: tile_h<=op_wdata;
          96: tile_len<=op_wdata;
          112: req_sequence<=op_wdata;
          120: rect_x<=op_wdata;
          128: rect_y<=op_wdata;
          136: rect_w<=op_wdata;
          144: rect_h<=op_wdata;
          152: mode<=op_wdata;
          168: if(op_wdata==completed) begin done_flag<=0; fault<=0; end else fault<=2;
          176: if(op_wdata==1) begin
            if(busy || interrupted) begin interrupted<=1; fault<=6; end else fault<=0;
            busy<=0; done_flag<=0; state<=CLEAR; clear_index<=0; panel_abort<=1;
            wave_phase<=0; drive_remaining<=0; power_remaining<=0;
            tile_x<=0; tile_y<=0; tile_w<=0; tile_h<=0; tile_len<=0;
            rect_x<=0; rect_y<=0; rect_w<=0; rect_h<=0; mode<=0; req_sequence<=0;
          end else fault<=1;
          104: if(op_wdata==1) begin
            if(!tile_valid) fault<=3;
            else begin
              tw<=tile_width; th<=tile_height; ix<=0; iy<=0; tile_byte_row<=0; tile_row_bytes<=packed_row_bytes;
              upload_byte_latch<=first_upload_byte;
              tile_cursor<=FRAME_BITS'(tile_y[Y_BITS-1:0])*FRAME_BITS'(WIDTH)+FRAME_BITS'(tile_x[X_BITS-1:0]);
              tile_row_step<=(W_BITS+1)'(WIDTH)-(W_BITS+1)'(tile_width)+1'b1; state<=UPLOAD;
            end
          end else if(op_wdata==2) begin
            if(busy) fault<=4;
            else if(!rectangle_valid) fault<=3;
            else if(req_sequence==0 || req_sequence<=last_sequence ||
              now_ticks>64'hffffffffffffffff-(mode==1?20000:250000)) fault<=5;
            else begin
              lx<=rect_x[X_BITS-1:0]; ly<=rect_y[Y_BITS-1:0]; lw<=rect_w[W_BITS-1:0]; lh<=rect_h[H_BITS-1:0];
              lm<=mode[1:0]; ix<=0; iy<=0;
              frame_start<=FRAME_BITS'(rect_y[Y_BITS-1:0])*FRAME_BITS'(WIDTH)+FRAME_BITS'(rect_x[X_BITS-1:0]);
              frame_cursor<=FRAME_BITS'(rect_y[Y_BITS-1:0])*FRAME_BITS'(WIDTH)+FRAME_BITS'(rect_x[X_BITS-1:0]);
              frame_row_step<=(W_BITS+1)'(WIDTH)-(W_BITS+1)'(rect_w[W_BITS-1:0])+1'b1;
              last_sequence<=req_sequence; busy<=1;
              deadline<=now_ticks+(mode==1?20000:250000); state<=SNAPSHOT_READ;
              wave_phase<=0; drive_remaining<=0; power_remaining<=0; drive_clocks<=0; scan_beats<=0;
            end
          end else fault<=1;
          default: fault<=1;
        endcase
      end
    end
  end
endmodule
