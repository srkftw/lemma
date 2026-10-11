// SPDX-License-Identifier: Apache-2.0
// Independent literal bus stimuli. This simulation bench is not circuitry,
// guest execution, a journal oracle, or physical-panel evidence.
`timescale 1ns/1ps
module Devices;
  logic clk=0, reset_n=0;
  always #5 clk=~clk;
  logic valid=0,write=0;
  logic [11:0] addr=0;
  logic [2:0] size=3;
  logic [63:0] wdata=0,prdata,drdata,brdata;
  logic pready,derready,bready,perror,derror,berror,pirq,dirq,birq;
  logic [1:0] selected=0;
  logic [63:0] now_ticks=0;
  logic sample_valid=0,sample_ready,sample_accepted;
  logic [63:0] st=0,sx=0,sy=0,sp=0,sf=0,tool=1,buttons=0;
  lemma_pen pen(.clk,.reset_n,.valid(valid&&selected==0),.write,.addr,.size,.wdata,
    .rdata(prdata),.ready(pready),.error(perror),.irq(pirq),.now_ticks,
    .sample_valid,.sample_ready,.sample_time(st),.sample_x(sx),.sample_y(sy),
    .sample_pressure(sp),.sample_flags(sf),.sample_tool(tool),.sample_buttons(buttons),.sample_accepted);
  logic fb_valid,fb_write,fb_ready=1,fb_error=0;
  logic [31:0] fb_addr,px,py;
  logic [7:0] fb_wdata,fb_rdata;
  logic [7:0] framebuffer[2048];
  logic panel_valid,panel_ready=1,panel_complete,panel_abort;
  logic [3:0] gray;
  logic [63:0] panel_sequence;
  int outputs=0,completions=0,black_outputs=0,fb_transactions=0,fb_writes=0,aborts=0;
  lemma_paper #(.WIDTH(32),.HEIGHT(32)) paper(.clk,.reset_n,.valid(valid&&selected==1),
    .write,.addr,.size,.wdata,.rdata(drdata),.ready(derready),.error(derror),.irq(dirq),
    .now_ticks,.descriptor(2048'b0),.fb_valid,.fb_write,.fb_addr,.fb_wdata,.fb_ready,.fb_error,.fb_rdata,
    .panel_valid,.panel_ready,.panel_x(px),.panel_y(py),.panel_gray(gray),.panel_complete,.panel_abort,.panel_sequence);
  assign fb_rdata=framebuffer[fb_addr];
  always @(posedge clk) begin
    if(fb_valid&&fb_ready) begin
      fb_transactions<=fb_transactions+1;
      if(fb_write&&!fb_error) begin framebuffer[fb_addr]<=fb_wdata;fb_writes<=fb_writes+1;end
    end
    if(panel_valid&&panel_ready) begin
      outputs<=outputs+1; if(gray==0)black_outputs<=black_outputs+1;
    end
    if(panel_complete) completions<=completions+1;
    if(panel_abort) aborts<=aborts+1;
  end
  logic dma_valid,dma_write,dma_ready=1,dma_error=0;
  logic [63:0] dma_addr,dma_wdata,dma_rdata;
  logic [2:0] dma_size,media_kind;
  logic media_valid,media_ready=1,media_error=0;
  logic [63:0] media_sector;
  logic [4095:0] media_wdata,media_rdata,volatile_bytes=0,stable_bytes=0;
  logic [7:0] memory[4096];
  int medium_operations=0,flushes=0;
  logic rv=0,rw=0,rready,rerror,load_valid=0;
  logic[55:0] raddr=0;
  logic[63:0] rwrite=0,rread,load_data=0;
  logic[7:0] rstrb=0;
  logic[8:0] load_index=0;
  lemma_register_ram small_ram(.clk,.valid(rv),.write(rw),.addr(raddr),.wdata(rwrite),.strb(rstrb),
    .rdata(rread),.ready(rready),.error(rerror),.preload_valid(load_valid),.preload_index(load_index),.preload_data(load_data));
  lemma_block #(.DMA_BYTES(4096),.CAPACITY_SECTORS(16)) blockdev(
    .clk,.reset_n,.valid(valid&&selected==2),.write,.addr,.size,.wdata,
    .rdata(brdata),.ready(bready),.error(berror),.irq(birq),
    .dma_valid,.dma_write,.dma_addr,.dma_wdata,.dma_size,.dma_ready,.dma_error,.dma_rdata,
    .media_valid,.media_kind,.media_sector,.media_wdata,.media_ready,.media_error,.media_rdata);
  always_comb begin
    dma_rdata=0;
    for(int j=0;j<8;j++) if(j<(1<<dma_size) && dma_addr>=64'h82000000 && dma_addr+j<64'h82001000)
      dma_rdata[j*8+:8]=memory[int'(dma_addr-64'h82000000)+j];
    media_rdata=volatile_bytes;
  end
  always @(posedge clk) begin
    if(dma_valid&&dma_ready&&dma_write&&!dma_error)
      for(int j=0;j<8;j++) if(j<(1<<dma_size)) memory[int'(dma_addr-64'h82000000)+j]<=dma_wdata[j*8+:8];
    if(media_valid&&media_ready) begin
      medium_operations<=medium_operations+1;
      if(!media_error && media_kind==1) volatile_bytes<=media_wdata;
      if(!media_error && media_kind==4) begin stable_bytes<=volatile_bytes;flushes<=flushes+1;end
    end
  end

  task automatic tick(input int n=1); repeat(n) begin @(posedge clk);#1;end endtask
  task automatic await_response;
    int waited;
    waited=0;
    while(!(selected==0?pready:selected==1?derready:bready)) begin
      tick();waited++;if(waited>10000)$fatal(1,"bounded MMIO response missing");
    end
  endtask
  task automatic put(input int sel,input int offset,input logic[63:0] value,input int sz=3,input bit rejected=0);
    @(negedge clk);selected=2'(sel);addr=12'(offset);wdata=value;size=3'(sz);valid=1;write=1;#1;
    await_response();
    if((sel==0?perror:sel==1?derror:berror)!==rejected)$fatal(1,"MMIO write response differs");
    tick();@(negedge clk);valid=0;write=0;
  endtask
  task automatic expect_word(input int sel,input int offset,input logic[63:0] expected,input int sz=3,input bit rejected=0);
    @(negedge clk);selected=2'(sel);addr=12'(offset);size=3'(sz);valid=1;write=0;#1;
    await_response();
    if((sel==0?perror:sel==1?derror:berror)!==rejected)$fatal(1,"MMIO read response differs");
    if((sel==0?prdata:sel==1?drdata:brdata)!==expected)
      $fatal(1,"literal register mismatch device%0d offset%0d actual%h expected%h",sel,offset,(sel==0?prdata:sel==1?drdata:brdata),expected);
    tick();@(negedge clk);valid=0;
  endtask
  task automatic sample(input logic[63:0] timestamp,x,y,pressure,flags);
    @(negedge clk);st=timestamp;sx=x;sy=y;sp=pressure;sf=flags;sample_valid=1;
    while(!sample_ready)tick();tick();@(negedge clk);sample_valid=0;
  endtask
  task automatic tile(input logic[7:0] packed_byte);
    put(1,64,0);put(1,72,0);put(1,80,2);put(1,88,1);put(1,96,1);
    put(1,2048,{56'b0,packed_byte},0);put(1,104,1);tick(4);
  endtask
  task automatic refresh(input logic[63:0] seq,input logic[63:0] refresh_mode=2);
    put(1,112,seq);put(1,120,0);put(1,128,0);put(1,136,2);put(1,144,1);put(1,152,refresh_mode);put(1,104,2);
  endtask
  task automatic paper_aperture;
    logic [63:0] packed_bytes=64'h3736353433323130;
    int length;
    // Distinct single-byte sentinels independently expose each byte-enable,
    // unaligned lane wrap and neighboring byte. No RTL row decoder is reused.
    for(int sz=0;sz<4;sz++) for(int lane=0;lane<8;lane++) begin
      length=1<<sz;
      for(int i=0;i<16;i++)put(1,2064+i,64'(128+i),0);
      put(1,2064+lane,packed_bytes,sz);
      for(int i=0;i<16;i++)expect_word(1,2064+i,64'(i>=lane&&i<lane+length?48+i-lane:128+i),0);
      expect_word(1,2064+lane,packed_bytes&(64'hffffffffffffffff>>((8-length)*8)),sz);
    end
    for(int sz=0;sz<4;sz++) begin
      length=1<<sz;
      for(int i=0;i<16;i++)put(1,2544+i,64'(128+i),0);
      put(1,2560-length,packed_bytes,sz);
      put(1,2561-length,64'hdeadbeefcafebabe,sz,1);expect_word(1,24,1);
      for(int i=0;i<16;i++)expect_word(1,2544+i,64'(i>=16-length?48+i-(16-length):128+i),0);
      expect_word(1,2560-length,packed_bytes&(64'hffffffffffffffff>>((8-length)*8)),sz);put(1,168,5);
    end
    $display("PAPER banked aperture 32 lane-width cases and 4 boundary rejections PASS");
  endtask
  task automatic paper_protocol;
    int saved_writes,saved_transactions,saved_outputs,saved_black,saved_completions,saved_aborts;
    logic [40:0] held_fb;
    logic [131:0] held_panel;
    // Resolve the earlier interrupted refresh with actual full-quality output.
    tick(1030);put(1,168,3);
    put(1,112,5);put(1,120,0);put(1,128,0);put(1,136,32);put(1,144,32);put(1,152,2);put(1,104,2);
    now_ticks=1200000;tick(4200);expect_word(1,160,5);put(1,168,5);expect_word(1,16,0);
    paper_aperture();
    // Each odd-width row has its own padding nibble. Distinct row bytes
    // expose a bad narrowed row cursor even when framebuffer addresses match.
    put(1,64,5);put(1,72,6);put(1,80,3);put(1,88,3);put(1,96,6);
    put(1,2048,8'h12,0);put(1,2049,8'h30,0);put(1,2050,8'h45,0);
    put(1,2051,8'h60,0);put(1,2052,8'h78,0);put(1,2053,8'h90,0);
    saved_writes=fb_writes;put(1,104,1);
    // Staging admission waits for upload completion, independent of decode
    // pipeline latency; this same-value write cannot change the accepted tile.
    put(1,64,5);
    if(fb_writes!=saved_writes+9)$fatal(1,"odd multi-row tile write count differs");
    for(int row=0;row<3;row++) begin
      for(int col=0;col<3;col++)
        if(framebuffer[(6+row)*32+5+col]!==8'(1+row*3+col))
          $fatal(1,"odd multi-row tile row payload differs");
      if(framebuffer[(6+row)*32+4]!==8'd15||framebuffer[(6+row)*32+8]!==8'd15)
        $fatal(1,"odd multi-row tile row padding touched neighbor");
    end
    for(int col=0;col<3;col++)
      if(framebuffer[5*32+5+col]!==8'd15||framebuffer[9*32+5+col]!==8'd15)
        $fatal(1,"odd multi-row tile touched neighboring row");
    // Validate full64-bit fields before any framebuffer transaction. A high
    // bit cannot disappear into a narrowed execution counter or row decoder.
    for(int field=0;field<5;field++) begin
      put(1,64,0);put(1,72,0);put(1,80,2);put(1,88,1);put(1,96,1);
      put(1,64+field*8,64'h100000000+64'(field==2?2:field>=3?1:0));
      saved_transactions=fb_transactions;put(1,104,1);expect_word(1,24,3);expect_word(1,112,5);
      if(fb_transactions!=saved_transactions)$fatal(1,"malformed high-bit tile touched framebuffer");
      put(1,168,5);
    end
    for(int field=0;field<5;field++) begin
      put(1,112,6);put(1,120,0);put(1,128,0);put(1,136,2);put(1,144,1);put(1,152,2);
      put(1,120+field*8,64'h100000000+64'(field==2||field==4?2:field==3?1:0));
      saved_transactions=fb_transactions;put(1,104,2);expect_word(1,24,3);expect_word(1,112,5);
      if(fb_transactions!=saved_transactions)$fatal(1,"malformed high-bit refresh touched framebuffer");
      put(1,168,5);
    end
    put(1,64,31);put(1,72,31);put(1,80,2);put(1,88,1);put(1,96,1);
    saved_writes=fb_writes;put(1,104,1);expect_word(1,24,3);
    if(fb_writes!=saved_writes)$fatal(1,"overflowing edge tile mutated target");put(1,168,5);
    put(1,80,1);put(1,2048,8'h6f,0);put(1,104,1);tick(4);
    if(framebuffer[1023]!==8'd6||framebuffer[1022]!==8'd15)$fatal(1,"odd edge tile unpack differs");
    put(1,2559,8'h55,0);put(1,2559,64'hbbaa,1,1);expect_word(1,2559,8'h55,0);expect_word(1,24,1);put(1,168,5);
    expect_word(1,64,0,2,1);expect_word(1,66,0,3,1);expect_word(1,24,0);
    put(1,176,64'h100000001);expect_word(1,24,1);expect_word(1,112,5);put(1,168,5);
    put(1,1024,1);expect_word(1,1024,0);expect_word(1,24,1);put(1,168,5);
    // A blocked upload holds its exact external-memory payload. A later
    // aperture write waits, then commits once after the original two pixels.
    put(1,64,0);put(1,72,0);put(1,80,2);put(1,88,1);put(1,96,1);put(1,2048,8'h78,0);
    fb_ready=0;saved_transactions=fb_transactions;saved_writes=fb_writes;put(1,104,1);held_fb={fb_write,fb_addr,fb_wdata};
    if(!fb_valid||held_fb!=={1'b1,32'd0,8'd7})$fatal(1,"upload request missing");
    // Cancelling a request before its response must not leave a captured
    // command to execute later or prevent a replacement read from responding.
    @(negedge clk);selected=1;addr=104;size=3;wdata=1;valid=1;write=1;#1;
    tick(2);if(derready)$fatal(1,"blocked command responded before upload progress");
    @(negedge clk);valid=0;write=0;tick();expect_word(1,0,1280331856);
    @(negedge clk);selected=1;addr=2048;size=0;wdata=8'hff;valid=1;write=1;#1;
    repeat(5) begin tick();if(derready||!fb_valid||{fb_write,fb_addr,fb_wdata}!==held_fb||fb_transactions!=saved_transactions)
      $fatal(1,"stalled upload or pending aperture write changed");end
    fb_ready=1;await_response();tick();@(negedge clk);valid=0;write=0;
    expect_word(1,2048,8'hff,0);
    if(framebuffer[0]!==8'd7||framebuffer[1]!==8'd8||fb_writes!=saved_writes+2)
      $fatal(1,"pending aperture write or cancelled command changed accepted upload");
    saved_outputs=outputs;saved_black=black_outputs;saved_completions=completions;
    refresh(6,1);now_ticks=1220001;tick(20);expect_word(1,160,6);put(1,168,6);
    if(outputs!=saved_outputs+2||black_outputs!=saved_black+1||completions!=saved_completions+1)
      $fatal(1,"literal fast threshold7/8 differs");
    // Snapshot backpressure and a pending staging write cannot replace the
    // accepted rectangle. A later white upload changes target, never its latch.
    tile(8'h78);fb_ready=0;refresh(7);held_fb={fb_write,fb_addr,fb_wdata};
    if(!fb_valid||fb_write||fb_addr!=0)$fatal(1,"snapshot request missing");
    put(1,104,2);expect_word(1,24,4);expect_word(1,112,7);
    @(negedge clk);selected=1;addr=120;size=3;wdata=1;valid=1;write=1;#1;
    repeat(5) begin tick();if(derready||!fb_valid||{fb_write,fb_addr,fb_wdata}!==held_fb)
      $fatal(1,"snapshot or pending rectangle write changed while stalled");end
    fb_ready=1;await_response();tick();@(negedge clk);valid=0;write=0;
    tile(8'hff);
    if(framebuffer[0]!==8'd15||framebuffer[1]!==8'd15||framebuffer[1024]!==8'd7||framebuffer[1025]!==8'd8)
      $fatal(1,"later upload changed accepted quality snapshot");
    panel_ready=0;now_ticks=1500000;
    for(int n=0;n<30&&!panel_valid;n++)tick();
    if(!panel_valid||px!=0||py!=0||gray!=7||panel_sequence!=7)$fatal(1,"accepted first panel pixel differs");
    held_panel={panel_sequence,px,py,gray};saved_outputs=outputs;saved_completions=completions;
    repeat(5) begin tick();if(!panel_valid||{panel_sequence,px,py,gray}!==held_panel||outputs!=saved_outputs)
      $fatal(1,"panel payload changed under backpressure");end
    panel_ready=1;tick();panel_ready=0;tick(2);
    if(!panel_valid||px!=1||py!=0||gray!=8||panel_sequence!=7)$fatal(1,"accepted final panel pixel differs");
    held_panel={panel_sequence,px,py,gray};repeat(5)begin tick();if({panel_sequence,px,py,gray}!==held_panel)
      $fatal(1,"final panel payload changed under backpressure");end
    panel_ready=1;tick(3);expect_word(1,160,7);put(1,168,7);
    if(outputs!=saved_outputs+2||completions!=saved_completions+1)$fatal(1,"stalled quality update did not complete exactly once");
    // RESET is accepted even while the framebuffer is stalled; it preserves
    // completed/accepted sequence lifetime and repeated optical uncertainty.
    fb_ready=0;refresh(8);saved_aborts=aborts;put(1,176,1);tick(2);
    expect_word(1,16,12);expect_word(1,112,8);expect_word(1,160,7);
    if(!fb_valid||!fb_write||fb_addr!=0||fb_wdata!=15||aborts!=saved_aborts+1)$fatal(1,"reset did not cancel stalled snapshot");
    put(1,176,1);expect_word(1,16,12);fb_ready=1;tick(1030);put(1,168,7);expect_word(1,16,8);
    put(1,112,9);put(1,120,0);put(1,128,0);put(1,136,32);put(1,144,32);put(1,152,2);put(1,104,2);
    now_ticks=1800000;tick(4200);expect_word(1,160,9);put(1,168,9);expect_word(1,16,0);
    // An error presented without ready is not a response. Its eventual
    // handshake reports failure, does not write target, and never completes.
    fb_ready=0;fb_error=1;saved_writes=fb_writes;tile(8'h78);tick(5);expect_word(1,24,0);
    fb_ready=1;tick(3);fb_error=0;expect_word(1,24,1);expect_word(1,160,9);
    if(fb_writes!=saved_writes)$fatal(1,"failed framebuffer response wrote target");put(1,168,9);
    now_ticks=64'hfffffffffffffff0;refresh(10);expect_word(1,24,5);expect_word(1,112,9);put(1,168,9);now_ticks=2000000;
    tile(8'h3b);refresh(64'h10000000a);now_ticks=2300000;tick(20);expect_word(1,160,64'h10000000a);put(1,168,64'h10000000a);
    refresh(10);expect_word(1,24,5);expect_word(1,112,64'h10000000a);put(1,168,64'h10000000a);
  endtask
  task automatic word(input int offset,input logic[63:0] value,input int n=8);
    for(int j=0;j<n;j++)memory[offset+j]=value[j*8+:8];
  endtask
  task automatic request(input int operation,input int idx);
    word(0,64'h82000400);word(8,{16'd1,16'd1,32'd16});
    if(operation==4)begin word(16,64'h82000800);word(24,{16'd0,16'd2,32'd1});end
    else begin word(16,64'h82000600);word(24,{16'd2,(operation==0?16'd3:16'd1),32'd512});end
    word(32,64'h82000800);word(40,{16'd0,16'd2,32'd1});
    word(1024,64'(operation));word(1032,3);word(132+((idx-1)%8)*2,0,2);word(130,64'(idx),2);memory[2048]=255;
    put(2,80,0,2);
    for(int n=0;n<1000;n++)begin tick();if(birq)break;if(n==999)$fatal(1,"no block completion");end
    expect_word(2,96,1,2);put(2,100,1,2);
    if(memory[258]!==8'(idx)||memory[259]!==0)$fatal(1,"used index not published");
  endtask
  initial begin
    for(int i=0;i<4096;i++)memory[i]=0;
    tick(3);reset_n=1;tick(1030);
    expect_word(0,0,1280331854);expect_word(0,40,1);
    sample(10,123,456,789,3);sample(11,999,888,700,3);
    expect_word(0,256,1);expect_word(0,272,123);expect_word(0,280,456);
    put(0,88,99);expect_word(0,24,2);expect_word(0,256,1);
    // Overflow preserves all fields of the old immutable head.
    for(int i=0;i<255;i++)sample(64'(12+i),1,2,3,3);
    expect_word(0,32,1);expect_word(0,40,2);expect_word(0,48,1);
    expect_word(0,256,1);expect_word(0,264,10);expect_word(0,272,123);expect_word(0,320,1);
    put(0,96,2);sample(300,10,20,3,3);expect_word(0,32,0);
    sample(301,10,20,0,0);sample(302,10,20,100,3);expect_word(0,32,1);expect_word(0,320,2);
    now_ticks=10000303;tick();expect_word(0,40,3);expect_word(0,16,7);now_ticks=0;
    put(0,96,3);put(0,104,1);expect_word(0,40,4);
    $display("PEN stable-head overflow exact-ack resync watchdog reset PASS");
    put(1,2048,64'h0102030405060708);expect_word(1,2048,64'h0102030405060708);
    put(1,2051,64'haabbccdd,2);expect_word(1,2048,64'h01aabbccdd060708);
    put(1,2559,64'h55,0);expect_word(1,2559,64'h55,0);
    tile(8'h02);refresh(1);tick(10);expect_word(1,16,1);
    // A later target upload cannot affect the accepted snapshot.
    tile(8'hff);put(1,104,2);expect_word(1,24,4);expect_word(1,112,1);
    now_ticks=300000;tick(20);
    if(outputs!=2||black_outputs!=1||completions!=1)$fatal(1,"accepted snapshot raced upload");
    expect_word(1,160,1);put(1,168,1);expect_word(1,24,0);
    put(1,80,33);put(1,104,1);expect_word(1,24,3);
    put(1,168,1);put(1,104,7);expect_word(1,24,1);put(1,168,1);
    refresh(2);tick(10);put(1,176,1);expect_word(1,16,12);expect_word(1,24,6);tick(1030);
    if(completions!=1)$fatal(1,"reset completed interrupted update");
    expect_word(1,112,2);
    put(1,176,1);tick(1030);expect_word(1,16,12);expect_word(1,24,6);
    expect_word(1,112,2);expect_word(1,160,1);
    put(1,168,1);expect_word(1,16,8);expect_word(1,24,0);
    // Only an actual full-screen quality completion resolves optical uncertainty.
    put(1,112,3);put(1,120,0);put(1,128,0);put(1,136,32);put(1,144,32);
    put(1,152,2);put(1,104,2);now_ticks=600000;tick(4120);
    expect_word(1,16,2);expect_word(1,160,3);
    if(completions!=2)$fatal(1,"full-screen quality refresh did not complete");
    put(1,168,3);panel_ready=0;refresh(4);now_ticks=900000;tick(10);
    if(!panel_valid||px!=0||py!=0)$fatal(1,"missing first stalled panel pixel");
    panel_ready=1;tick();panel_ready=0;tick(2);
    if(!panel_valid||px!=1||py!=0)$fatal(1,"missing final stalled panel pixel");
    @(negedge clk);panel_ready=0;selected=1;addr=176;size=3;wdata=1;valid=1;write=1;#1;
    await_response();panel_ready=1;
    tick();@(negedge clk);valid=0;write=0;tick();
    expect_word(1,16,12);expect_word(1,112,4);expect_word(1,160,3);
    if(completions!=2)$fatal(1,"simultaneous RESET published a completion");
    paper_protocol();
    $display("PAPER latch Busy invalid-command bounds interrupted-reset PASS");
    put(2,20,0,2);expect_word(2,16,512,2);put(2,20,1,2);expect_word(2,16,1,2);
    put(2,36,0,2);put(2,32,512,2);put(2,36,1,2);put(2,32,1,2);put(2,112,11,2);
    put(2,48,0,2);put(2,56,8,2);put(2,128,64'h82000000,2);put(2,132,0,2);
    put(2,144,64'h82000080,2);put(2,148,0,2);put(2,160,64'h82000100,2);put(2,164,0,2);
    put(2,68,1,2);put(2,112,15,2);
    for(int i=0;i<512;i++)memory[1536+i]=8'(i^8'h5a);
    request(1,1);
    if(memory[2048]!=0||volatile_bytes[7:0]!=8'h5a||stable_bytes!=0)$fatal(1,"write bypassed volatile medium");
    request(4,2);if(stable_bytes!=volatile_bytes||flushes!=1)$fatal(1,"flush not ordered");
    for(int i=0;i<512;i++)memory[1536+i]=0;
    request(0,3);
    for(int i=0;i<512;i++)if(memory[1536+i]!=8'(i^8'h5a))$fatal(1,"DMA read payload differs");
    media_error=1;request(4,4);media_error=0;if(memory[2048]!=1||flushes!=1)$fatal(1,"failed flush returned success");
    // Invalid queue target must fail without an external-medium operation.
    word(0,64'h80000000);word(130,5,2);put(2,80,0,2);tick(20);expect_word(2,112,79,2);
    if(medium_operations!=4)$fatal(1,"bad descriptor executed medium request");
    put(2,112,0,2);tick(2);expect_word(2,112,0,2);expect_word(2,96,0,2);
    $display("BLOCK descriptors DMA payload used-ring flush error bounds reset PASS");
    for(int i=0;i<512;i++)begin @(negedge clk);load_valid=1;load_index=9'(i);load_data=64'(i);tick();end
    @(negedge clk);load_valid=0;rv=1;raddr=56'h80000000;#1;if(rerror||rread!=0)$fatal(1,"small RAM code window");
    raddr=56'h807ffe00;#1;if(rerror||rread!=384)$fatal(1,"small RAM stack aliases code");
    raddr=56'h81000000;#1;if(rerror||rread!=448)$fatal(1,"small RAM input aliases stack");
    rw=1;rwrite=64'hdeadbeefcafebabe;rstrb=8'h03;tick();@(negedge clk);rw=0;#1;
    if(rread!=64'hbabe)$fatal(1,"small RAM byte strobes");
    raddr=56'h80001000;#1;if(!rerror)$fatal(1,"absent RAM passed");
    raddr=56'h81000001;#1;if(!rerror)$fatal(1,"unaligned memory beat passed");
    rv=0;
    $display("RAM 4096-byte register implementation distinct sparse windows strobes faults PASS");
    $finish;
  end
  initial begin #1000000;$fatal(1,"bounded device bench deadline");end
endmodule
