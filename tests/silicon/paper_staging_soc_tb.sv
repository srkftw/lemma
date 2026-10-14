module paper_collision_tb;
logic clk=0,reset=1,valid=0,write=1;logic[31:0]address=0;logic[63:0]data=0;logic[2:0]size=3;logic[63:0]actual;bit collecting=0;integer pixel_count=0;
always #5 clk=~clk;
lemma_soc dut(.clk,.reset,.usb_host_phy_clk(1'b0),.usb_chip_phy_clk(1'b0),.raw_power_good(1'b1),.raw_brownout(1'b0),.raw_button_level(1'b0),.power_reset_cause(3'd1),.ble_coex_allow(1'b1),.usb_connected(1'b1),.usb_bus_reset(1'b0),.usb_rx_valid(1'b0),.usb_rx_last(1'b0),.usb_rx_byte(8'd0),.usb_tx_ready(1'b1),.external_media_busy(1'b0),.external_boot_media_busy(1'b0),.ble_peer_enabled(1'b0),.ble_peer_reset(1'b1),.ble_rx_sample_valid(1'b0),.ble_rx_sample_bit(1'b0),.sample_valid(1'b0),.mem_ready(1'b1),.mem_error(1'b0),.fb_ready(1'b1),.fb_error(1'b0),.media_ready(1'b0),.panel_ready(1'b1),.uart_rx_valid(1'b0));
function automatic logic[63:0] pattern(input integer row);
 return 64'hfedcba9876543210 ^ (64'h0101010101010101*64'(row));
endfunction
always @(posedge clk) if(collecting && dut.fb_valid && dut.fb_write) begin
 integer x,y,index;logic[7:0] packed_byte;logic[3:0] expected;
 x=int'(dut.fb_addr)%int'(lemma_silicon_binding::WIDTH)-9;
 y=int'(dut.fb_addr)/int'(lemma_silicon_binding::WIDTH)-23;
 if(x<0||x>=32||y<0||y>=32)$fatal(1,"actual tile pixel outside independent box");
 index=y*16+x/2;packed_byte=8'(pattern(index/8)>>(8*(index%8)));
 // Versioned Gray4 contract: even tile X is the high nibble.
 expected=x%2==0 ? packed_byte[7:4] : packed_byte[3:0];
 if(dut.fb_wdata!={4'b0,expected})$fatal(1,"actual controller pixel differs at %0d/%0d",x,y);
 pixel_count=pixel_count+1;
end
task automatic access(input bit w,input logic[31:0]a,input logic[63:0]d,input logic[2:0]z,input bit failure);
 bit done;integer n;
 @(negedge clk);valid=1;write=w;address=a;data=d;size=z;done=0;n=0;
 while(!done&&n<20)begin @(negedge clk);n=n+1;if(dut.dev_ready)begin
 if(dut.dev_error!=failure)$fatal(1,"MMIO error mismatch at %h",a);actual=dut.dev_rdata;done=1;end end
 if(!done)$fatal(1,"MMIO did notcomplete at %h",a);
 @(negedge clk);valid=0;
endtask
initial begin
 repeat(3)@(negedge clk);reset=0;
 repeat(3630010)@(negedge clk);
 if(dut.paper_busy)$fatal(1,"actual full canonical framebuffer clear incomplete");
 access(0,32'h10010008,0,3,0);if(actual!=lemma_silicon_binding::PAPER_VERSION)$fatal(1,"controller version differs from selected binding");
 access(0,32'h100100b8,0,3,0);if(actual!=(lemma_silicon_binding::PAPER_VERSION==2?3584:0))$fatal(1,"staging discovery differs from selected binding");
 if(lemma_silicon_binding::PAPER_VERSION==1)begin
 access(1,32'h10010800,0,3,1);if(!dut.ble_sel||dut.paper_sel)$fatal(1,"legacy first Paper word did not collide");
 access(1,32'h100109f8,0,3,1);if(!dut.ble_sel||dut.paper_sel)$fatal(1,"legacy last Paper word did not collide");
 $display("PASS retained legacy collision through actual BLE decode; unchanged Paper control/version");$finish;end
 for(integer row=0;row<64;row=row+1)access(1,32'h10010e00+32'(row*8),pattern(row),3,0);
 for(integer row=0;row<64;row=row+1)begin access(0,32'h10010e00+32'(row*8),0,3,0);if(actual!=pattern(row))$fatal(1,"actual512B stagedword mismatch row%0d",row);end
 // Cross the physical512B end with an unaligned two-byte write; no old or new byte may change.
 access(1,32'h10010fff,64'h0123,1,1);
 access(0,32'h10010ff8,0,3,0);if(actual!=pattern(63))$fatal(1,"rejected crossing changed last word");
 // The old alias remains ownedby real BLE, including read-onlyRX rejection.
 access(1,32'h10010800,0,3,1);if(!dut.ble_sel||dut.paper_sel)$fatal(1,"oldalias changedowner");
 access(1,32'h10010700,64'hda,3,0);if(!dut.ble_sel||dut.paper_sel)$fatal(1,"validBLEstaging changedowner");
 if(dut.sampled_ble.endpoint.tx_buffer[0]!=8'hda)$fatal(1,"realBLEdata staging notpreserved");
 access(0,32'h10010a00,0,3,0);if(actual!=64'h315645444253554c||!dut.usb_sel||dut.paper_sel)$fatal(1,"USB control ownership changed");
 access(1,32'h10010040,9,3,0);access(1,32'h10010048,23,3,0);
 access(1,32'h10010050,32,3,0);access(1,32'h10010058,32,3,0);access(1,32'h10010060,512,3,0);
 collecting=1;access(1,32'h10010068,1,3,0);
 repeat(7000)@(negedge clk);collecting=0;
 if(pixel_count!=1024||dut.paper_busy)$fatal(1,"actual complete32x32 pixel upload missing");
 $display("PASS full canonical clear; actual512B staging/readback/bounds,1024 exactpixels and BLE/USB ownership");$finish;
end
endmodule
