// Product-boot-v1 PIO nonvolatile controller. Opt-in profile7 integration.
// Circuitry transfers raw sectors; image/metadata policy lives in Lean.
module lemma_boot_nv #(
  parameter logic [63:0] CAPACITY_SECTORS = 65544
)(
  input logic clk, reset_n,
  input logic valid, write,
  input logic [9:0] addr,
  input logic [2:0] size,
  input logic [63:0] wdata,
  output logic [63:0] rdata,
  output logic ready, error, irq,
  output logic media_valid,
  output logic [63:0] media_id, media_sector,
  output logic [1:0] media_kind,
  output logic [4095:0] media_wdata,
  output logic media_cancel,
  input logic media_ready,
  input logic [63:0] reset_origin,
  output logic [63:0] media_origin,
  input logic [63:0] media_result,
  input logic [9:0] media_bytes,
  input logic [4095:0] media_rdata
);
  // 0 idle, 1 external pending, 2 completed, 3 cancelled completion.
  logic [1:0] state;
  logic [1:0] kind;
  logic [63:0] selected_sector, active_sector;
  logic [63:0] request_id, completed_id, result;
  logic [63:0] active_origin;
  logic [9:0] returned_bytes;
  logic [4095:0] buffer_data;
  logic cancel_pending, bus_ok;
  integer index;

  assign bus_ok = size == 3 && addr[2:0] == 0;
  // Pending external work never blocks reads/cancellation. Writes to request
  // fields or data while pending return an error instead of altering the port.
  assign ready = 1;
  assign error = valid && (!bus_ok || (addr >= 10'h200 && state == 1) || (write &&
    ((addr >= 10'h200 && state != 0) ||
     ((addr == 32 || addr == 40) && state != 0) ||
     (addr == 40 && (wdata < 1 || wdata > 3 || request_id == 64'hffffffffffffffff ||
                    (wdata != 3 && selected_sector >= CAPACITY_SECTORS))) ||
     (addr == 80 && (state < 2 || wdata != completed_id)) ||
     (addr == 88 && (state != 1 || wdata != request_id)) ||
     (addr < 10'h200 && addr != 32 && addr != 40 && addr != 80 && addr != 88))));
  assign irq = state == 2 || state == 3;
  assign media_valid = state == 1;
  assign media_id = request_id;
  assign media_kind = kind;
  assign media_sector = active_sector;
  assign media_origin = active_origin;
  assign media_wdata = buffer_data;
  assign media_cancel = state == 1 && cancel_pending;

  always_comb begin
    rdata = 0;
    if(bus_ok) begin
      if(addr >= 10'h200 && state != 1) rdata = buffer_data[addr[8:3]*64 +: 64];
      else case(addr)
        0:rdata = 64'h564e424c;
        8:rdata = 1;
        16:rdata = CAPACITY_SECTORS;
        24:rdata = {62'b0,state};
        32:rdata = selected_sector;
        40:rdata = {62'b0,kind};
        48:rdata = request_id;
        56:rdata = completed_id;
        64:rdata = result;
        72:rdata = {54'b0,returned_bytes};
        88:rdata = {63'b0,cancel_pending};
        96:rdata = reset_origin;
        default:rdata = 0;
      endcase
    end
  end

  always_ff @(posedge clk) begin
    if(!reset_n) begin
      state <= 0; kind <= 0; selected_sector <= 0; active_sector <= 0;
      request_id <= 0; completed_id <= 0; result <= 0; returned_bytes <= 0;
      active_origin <= 0;
      buffer_data <= 0; cancel_pending <= 0;
    end else begin
      // A cancelled write can already have modified backing bytes. Returning
      // cancellation never claims rollback or durability. A barrier receipt is
      // successful only after the platform's real barrier handshake.
      if(state == 1 && media_ready) begin
        completed_id <= request_id;
        if(media_bytes > 512 || (media_result == 0 &&
           ((kind == 3 && media_bytes != 0) || (kind != 3 && media_bytes != 512)))) begin
          result <= 64'hffffffffffffffff;
          returned_bytes <= media_bytes > 512 ? 512 : media_bytes;
        end else begin result <= media_result; returned_bytes <= media_bytes; end
        if(kind == 1) begin
          for(index=0;index<512;index=index+1)
            if(index < media_bytes) buffer_data[index*8 +: 8] <= media_rdata[index*8 +: 8];
        end
        // Same-edge cancellation wins over a completion; the raw returned
        // outcome/count is retained while the guest sees cancelled status3.
        state <= (cancel_pending || (valid && write && !error && addr == 88)) ? 3 : 2;
        cancel_pending <= 0;
      end
      if(valid && write && !error) begin
        if(addr >= 10'h200) buffer_data[addr[8:3]*64 +: 64] <= wdata;
        else case(addr)
          32:selected_sector <= wdata;
          40:begin
            state <= 1; kind <= wdata[1:0]; active_sector <= selected_sector;
            active_origin <= reset_origin;
            request_id <= request_id+1; returned_bytes <= 0; result <= 0;
            cancel_pending <= 0;
          end
          80:begin state <= 0; cancel_pending <= 0; end
          88:if(!media_ready) cancel_pending <= 1;
          default:begin end
        endcase
      end
    end
  end
endmodule
