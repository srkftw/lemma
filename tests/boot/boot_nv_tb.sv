module boot_nv_tb;
  logic clk=0, reset_n=0, valid=0, write=0, media_ready=0;
  logic [9:0] addr=0;
  logic [2:0] size=3;
  logic [63:0] wdata=0,rdata,media_id,media_sector,media_result=0;
  logic [63:0] reset_origin=9,media_origin;
  logic ready,error,irq,media_valid,media_cancel;
  logic [1:0] media_kind;
  logic [4095:0] media_wdata,media_rdata=0;
  logic [9:0] media_bytes=0;
  lemma_boot_nv dut(.*);
  always #5 clk=~clk;
  task tick; begin @(posedge clk); #1; end endtask
  task wr(input [9:0] a,input [63:0] d,input bit fail);
    begin @(negedge clk);valid=1;write=1;addr=a;wdata=d;#1;
      if(!ready || error!==fail) $fatal(1,"WRITE %h error %b expected %b",a,error,fail);
      tick; @(negedge clk);valid=0;write=0;end
  endtask
  task rd(input [9:0] a,input [63:0] expected,input bit fail);
    begin @(negedge clk);valid=1;write=0;addr=a;#1;
      if(!ready || error!==fail || (!fail && rdata!==expected))
        $fatal(1,"READ %h=%h expected %h error%b",a,rdata,expected,error);
      tick;@(negedge clk);valid=0;end
  endtask
  task complete(input [63:0] status,input [9:0] bytes);
    begin @(negedge clk);media_result=status;media_bytes=bytes;media_ready=1;
      tick;@(negedge clk);media_ready=0;end
  endtask
  initial begin
    tick;tick;reset_n=1;tick;
    rd(0,64'h564e424c,0);rd(16,65544,0);
    wr(512,64'h1122334455667788,0);wr(32,42,0);wr(40,2,0);
    if(!media_valid || media_id!=1 || media_sector!=42 || media_kind!=2 ||
       media_origin!=9 || media_wdata[63:0]!=64'h1122334455667788) $fatal(1,"actual write request");
    // Backpressure cannot alter raw request bytes or identity.
    wr(512,0,1);wr(32,99,1);wr(40,1,1);rd(512,0,1);
    repeat(5) tick;
    if(media_id!=1 || media_sector!=42 || media_wdata[63:0]!=64'h1122334455667788) $fatal(1,"unstable pending request");
    complete(7,17);rd(24,2,0);rd(56,1,0);rd(64,7,0);rd(72,17,0);
    if(!irq) $fatal(1,"completion irq");wr(80,2,1);wr(80,1,0);
    // Failed write retains observed partial persistence count; no success.
    rd(24,0,0);wr(32,8,0);wr(40,1,0);
    media_rdata[63:0]=64'h8877665544332211;
    complete(9,3);rd(72,3,0);rd(512,64'h1122334455332211,0);wr(80,2,0);
    // Successful read requires exactly one sector.
    wr(40,1,0);media_rdata='1;complete(0,511);rd(64,64'hffffffffffffffff,0);wr(80,3,0);
    // Cancellation does not rerun/erase the pending external transaction.
    wr(40,2,0);wr(88,4,0);repeat(3)tick;
    if(!media_cancel || !media_valid || media_id!=4) $fatal(1,"cancel handoff");
    complete(0,512);rd(24,3,0);rd(72,512,0);wr(80,4,0);
    // A real barrier is a distinct operation and cannot succeed with bytes.
    wr(40,3,0);if(media_kind!=3 || media_id!=5) $fatal(1,"barrier request");
    complete(0,1);rd(64,64'hffffffffffffffff,0);wr(80,5,0);
    wr(40,3,0);complete(0,0);rd(64,0,0);rd(72,0,0);wr(80,6,0);
    // Width/alignment/out-of-medium and stale receipts fail closed.
    wr(32,65544,0);wr(40,1,1);wr(88,6,1);wr(80,6,1);
    size=2;rd(0,0,1);size=3;rd(1,0,1);
    reset_n=0;tick;reset_origin=10;reset_n=1;tick;
    wr(32,8,0);wr(40,1,0);
    if(media_origin!=10 || media_id!=1) $fatal(1,"new reset origin");
    complete(0,512);wr(80,1,0);
    $display("BOOT_NV_LITERAL:PASS sector outcomes, pending stability, partial bytes, cancellation, barriers, IRQ, reset identity");
    $finish;
  end
  initial begin #20000;$fatal(1,"test deadline");end
endmodule
