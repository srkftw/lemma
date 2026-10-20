// SPDX-License-Identifier: Apache-2.0
// Synthetic-aperture/1: digital converter/readout/control circuitry, not sensor physics.
// One retained transaction per DMA beat. No target application or tutor policy.
module lemma_multimodal #(
 parameter logic [63:0] CONTROLLER_ABI=1,
 parameter logic [63:0] DMA_BASE=64'h82000000,DMA_BYTES=64'h2000000
)(input logic clk,reset,
 input logic valid,write,input logic [12:0] addr,input logic [2:0] size,input logic [63:0] wdata,
 output logic [63:0] rdata,output logic ready,error,irq,busy,
 input logic [255:0] stimulus,reference_input,input logic [127:0] source_quality,
 output logic pcm_valid,output logic [63:0] pcm_data,pcm_position,pcm_tick,
 output logic dma_valid,dma_write,output logic [63:0] dma_addr,dma_wdata,
 output logic [2:0] dma_size,input logic dma_ready,dma_error,input logic [63:0] dma_rdata,
 output logic [63:0] acquisition_tick
);
 localparam integer IDLE=2,CONFIGURED=3,ARMED=4,RUNNING=5,DRAINING=6,FAULT=7,DISCONNECTED=8;
 logic [63:0] tick,mask,inhibit,link,pending;
 logic [63:0] state[9],fault[9],epoch[9],sequence_no[9],gain[9],period[9],exposure[9],selector[9],consent[9],calibration[9],lease[9],quiet_until[9];
 logic [63:0] consent_floor[9],config_revision[9],next_sample[9],capture[9],available[9],quality[9],latched_reference[9],dma_pointer[9],dma_words[9],dma_status[9],consumed[9],submitted[9],scheduled_start[9];
 logic signed [63:0] latched[9],history[9];
 logic [63:0] head[9],count[9],converting[9];
 logic [63:0] records[9][16][8],dma_record[8];
 logic dma_active,dma_cancel;integer dma_stream,dma_index;
 logic [63:0] ring_base,ring_capacity,producer,fetch,eof_end,ring_eof,ring_enabled,ring_status;
 logic [63:0] owner_epoch,owner_consent,owner_config,submitted_base,consumed_base,gaps;
 logic [63:0] bus_kind,bus_address,bus_data,bus_samples,bus_cancel,turn;
 integer i,j,k,s,o,index;
 logic signed [63:0] value,source,refvalue;
 logic [63:0] q,raw;
 function automatic logic optical(input integer n);return n>=1&&n<=5;endfunction
 function automatic logic output_stream(input integer n);return optical(n)||n==8;endfunction
 function automatic logic enabled(input integer n);return link!=0&&consent[n]!=0&&lease[n]>tick&&(!output_stream(n)||(inhibit==0&&calibration[n]==1));endfunction
 function automatic logic emitter(input integer n);return optical(n)&&enabled(n)&&state[n]==RUNNING&&tick>=quiet_until[n]&&(selector[n]&256)==0;endfunction
 task automatic reject(input integer n,input logic [63:0] code);fault[n]=code;pending=pending|(64'd1<<n);endtask
 task automatic stop_stream(input integer n,input logic [63:0] status);
  state[n]=status;converting[n]=0;count[n]=0;head[n]=0;lease[n]=0;
  if(dma_active&&dma_stream==n)begin dma_cancel=1;end
  pending=pending|(64'd1<<n);
 endtask
 function automatic logic ring_permitted();
  return link!=0&&inhibit==0&&calibration[8]==1&&consent[8]!=0&&lease[8]>tick&&
   epoch[8]==owner_epoch&&consent[8]==owner_consent&&config_revision[8]==owner_config&&(state[8]==ARMED||state[8]==RUNNING);
 endfunction
 task automatic cancel_ring(input logic [63:0] status,input logic [63:0] code);
  ring_enabled=0;ring_status=status;if(bus_kind==2)bus_cancel=1;
  state[8]=code!=0?FAULT:((state[8]==IDLE||state[8]==FAULT||state[8]==DISCONNECTED)?state[8]:CONFIGURED);count[8]=0;head[8]=0;lease[8]=0;
  if(code!=0)fault[8]=code;pending=pending|256;
 endtask
 task automatic finish_ring();
  if(ring_enabled!=0&&ring_eof!=0&&fetch==eof_end&&count[8]==0&&bus_kind!=2)cancel_ring(2,0);
 endtask
 task automatic prepare_bus();
  if(bus_kind==0)begin
   if(ring_enabled!=0&&ring_permitted()&&count[8]<=12&&producer!=fetch&&(producer-fetch>=4||ring_eof!=0)&&(!dma_active||turn==1))begin
    bus_kind=2;bus_address=ring_base+((fetch&(ring_capacity-1))*2);bus_data=0;
    bus_samples=producer-fetch<4?producer-fetch:4;bus_cancel=0;
   end else if(dma_active)begin
    bus_kind=1;bus_address=dma_pointer[dma_stream]+64'(dma_index)*8;bus_data=dma_record[dma_index];bus_samples=0;bus_cancel=0;
   end
  end
 endtask
 assign acquisition_tick=tick;
 assign dma_valid=(CONTROLLER_ABI==1?dma_active:bus_kind!=0)&&!reset;
 assign dma_write=CONTROLLER_ABI==1?1:bus_kind==1;
 assign dma_addr=CONTROLLER_ABI==1?dma_pointer[dma_stream]+64'(dma_index)*8:bus_address;
 assign dma_wdata=CONTROLLER_ABI==1?dma_record[dma_index]:bus_data;
 assign dma_size=3;
 always_comb begin
  ready=valid;error=valid&&(size!=3||addr[2:0]!=0||addr>=13'ha00);
  rdata=0;busy=dma_active||bus_kind!=0||ring_enabled!=0;irq=0;
  for(integer n=0;n<9;n++)begin if(state[n]==RUNNING||converting[n]!=0)busy=1;if(mask[n]&&(pending[n]||count[n]!=0))irq=1;end
  if(addr<256)case(addr)
   0:rdata=64'h4c4d4d32;8:rdata=CONTROLLER_ABI;16:rdata=511;24:rdata=tick;
   32:begin rdata=pending;for(integer n=0;n<9;n++)if(count[n]!=0)rdata[n]=1;end
   40:rdata=mask;56:rdata=inhibit;64:rdata=link;72:rdata=100000000;80:rdata=16;88:rdata=64;96:rdata=0;
   104:rdata=CONTROLLER_ABI==2?(ring_base):0;112:rdata=CONTROLLER_ABI==2?(ring_capacity):0;120:rdata=CONTROLLER_ABI==2?(producer):0;128:rdata=CONTROLLER_ABI==2?(fetch):0;
   136:rdata=0;144:rdata=CONTROLLER_ABI==2?(ring_status):0;152:rdata=CONTROLLER_ABI==2?(ring_eof!=0?eof_end:64'hffffffffffffffff):0;
   160:rdata=CONTROLLER_ABI==2?(gaps):0;168:rdata=CONTROLLER_ABI==2?(bus_kind|(bus_cancel<<8)):0;default:rdata=0;
  endcase
  else if(addr<2560)begin
   case(addr[7:0])
    0:rdata=64'h4d4d0000+64'(int'(addr[12:8])-1);
    8:rdata=state[int'(addr[12:8])-1];16:rdata=fault[int'(addr[12:8])-1];32:rdata=epoch[int'(addr[12:8])-1];40:rdata=sequence_no[int'(addr[12:8])-1];
    48:rdata=gain[int'(addr[12:8])-1];56:rdata=period[int'(addr[12:8])-1];64:rdata=exposure[int'(addr[12:8])-1];72:rdata=selector[int'(addr[12:8])-1];
    80:rdata=consent[int'(addr[12:8])-1];88:if(addr[12:8]<9)rdata=64'($signed(reference_input[32*(int'(addr[12:8])-1)+:32]));96:rdata=calibration[int'(addr[12:8])-1];104:rdata=lease[int'(addr[12:8])-1];
    112,120,128,136:if(count[int'(addr[12:8])-1]!=0)rdata=records[int'(addr[12:8])-1][head[int'(addr[12:8])-1]][(int'(addr[7:0])-112)/8];
    144:rdata=count[int'(addr[12:8])-1];160:rdata=dma_pointer[int'(addr[12:8])-1];168:rdata=dma_words[int'(addr[12:8])-1];184:rdata=dma_status[int'(addr[12:8])-1];
    192:rdata=count[int'(addr[12:8])-1]!=0?records[int'(addr[12:8])-1][head[int'(addr[12:8])-1]][6]:config_revision[int'(addr[12:8])-1];
    200:rdata=64'(emitter(int'(addr[12:8])-1));208:rdata=quiet_until[int'(addr[12:8])-1];216:rdata=latched_reference[int'(addr[12:8])-1];
    224:if(count[int'(addr[12:8])-1]!=0)rdata=records[int'(addr[12:8])-1][head[int'(addr[12:8])-1]][4];
    232:rdata=consumed[int'(addr[12:8])-1];240:rdata=submitted[int'(addr[12:8])-1];248:rdata=scheduled_start[int'(addr[12:8])-1];default:rdata=0;
   endcase
  end
 end
 // All state belongs to this edge process. Blocking next-state assignments
 // give completion-before-software-command ordering at equal clock edges,
 // including simultaneous FIFO arrival/pop and cancellation of a completed DMA.
 always @(posedge clk)begin
  if(reset)begin
   tick=0;mask=0;inhibit=1;link=1;pending=0;dma_active=0;dma_cancel=0;dma_stream=0;dma_index=0;
   pcm_valid=0;pcm_data=0;pcm_position=0;pcm_tick=0;
   ring_base=0;ring_capacity=0;producer=0;fetch=0;eof_end=0;ring_eof=0;ring_enabled=0;ring_status=0;
   owner_epoch=0;owner_consent=0;owner_config=0;submitted_base=0;consumed_base=0;gaps=0;
   bus_kind=0;bus_address=0;bus_data=0;bus_samples=0;bus_cancel=0;turn=0;
   for(i=0;i<9;i++)begin
    state[i]=IDLE;fault[i]=0;epoch[i]=1;sequence_no[i]=0;gain[i]=1;period[i]=100000;exposure[i]=8;selector[i]=0;consent[i]=0;calibration[i]=0;lease[i]=0;quiet_until[i]=0;
    consent_floor[i]=0;config_revision[i]=0;next_sample[i]=0;capture[i]=0;available[i]=0;quality[i]=0;latched_reference[i]=0;dma_pointer[i]=0;dma_words[i]=0;dma_status[i]=0;consumed[i]=0;submitted[i]=0;scheduled_start[i]=0;
    latched[i]=0;history[i]=0;head[i]=0;count[i]=0;converting[i]=0;
    for(j=0;j<16;j++)for(k=0;k<8;k++)records[i][j][k]=0;
   end
   for(k=0;k<8;k++)dma_record[k]=0;
  end else begin
   tick=tick+1;pcm_valid=0;
   if(bus_kind==2&&dma_ready)begin
    if(bus_cancel!=0||ring_enabled==0||!ring_permitted())begin bus_kind=0;bus_cancel=0;if(ring_enabled!=0)cancel_ring(3,0);turn=0;end
    else if(dma_error)begin bus_kind=0;cancel_ring(4,3);end
    else if(submitted[8]>64'hffffffffffffffff-bus_samples)begin bus_kind=0;cancel_ring(4,14);end
    else if(count[8]+bus_samples>16)begin bus_kind=0;cancel_ring(4,9);end
    else begin
     for(j=0;j<4;j++)if(64'(j)<bus_samples)begin
      index=int'((head[8]+count[8])%16);for(k=0;k<8;k++)records[8][index][k]=0;
      records[8][index][0]=(dma_rdata>>(16*j))&65535;records[8][index][5]=owner_consent;count[8]=count[8]+1;
     end
     submitted[8]=submitted[8]+bus_samples;fetch=fetch+bus_samples;pending=pending|256;bus_kind=0;turn=0;
    end
   end else if(bus_kind==1&&dma_ready)begin
    bus_kind=0;turn=1;
    if(dma_cancel)begin dma_status[dma_stream]=3;dma_active=0;dma_cancel=0;end
    else if(dma_error)begin dma_status[dma_stream]=3;reject(dma_stream,3);dma_active=0;end
    else if(dma_index==7)begin dma_status[dma_stream]=2;head[dma_stream]=(head[dma_stream]+1)%16;count[dma_stream]=count[dma_stream]-1;pending=pending|(64'd1<<dma_stream);dma_active=0;end
    else dma_index=dma_index+1;
   end
   finish_ring();
   if(ring_enabled!=0&&state[8]==RUNNING&&next_sample[8]==tick)begin
    if(count[8]!=0&&consumed[8]==64'hffffffffffffffff)cancel_ring(4,14);
    else if(count[8]==0&&!(ring_eof!=0&&fetch==eof_end))begin
     if(gaps==64'hffffffffffffffff)cancel_ring(4,14);else gaps=gaps+1;
    end
   end
   for(i=0;i<9;i++)if(state[i]==RUNNING||state[i]==DRAINING)begin
    if(!enabled(i))begin reject(i,consent[i]!=0?15:7);stop_stream(i,CONFIGURED);end
    else begin
     if(converting[i]!=0&&available[i]==tick)begin
      if(count[i]==16)reject(i,9);
      else if(sequence_no[i]==64'hffffffffffffffff)begin reject(i,14);state[i]=FAULT;end
      else begin
       sequence_no[i]=sequence_no[i]+1;index=int'((head[i]+count[i])%16);
       records[i][index][0]=latched[i];records[i][index][1]=capture[i];records[i][index][2]=tick;records[i][index][3]=quality[i];records[i][index][4]=sequence_no[i];records[i][index][5]=epoch[i];records[i][index][6]=config_revision[i];records[i][index][7]=selector[i];
       count[i]=count[i]+1;pending=pending|(64'd1<<i);
      end
      converting[i]=0;if(state[i]==DRAINING)state[i]=CONFIGURED;
     end
     if(state[i]==RUNNING&&next_sample[i]==tick)begin
      if(period[i]>64'hffffffffffffffff-tick)begin reject(i,14);stop_stream(i,FAULT);end
      else begin
       next_sample[i]=tick+period[i];
       if(i==8)begin
        if(tick>=scheduled_start[i])begin
         if(count[i]==0)begin reject(i,10);pcm_data=0;pcm_tick=tick;end
         else begin value=$signed(16'(records[i][head[i]][0]))*$signed(gain[i]);if(value< -32768)value= -32768;if(value>32767)value=32767;pcm_data=64'(value);pcm_tick=tick;consumed[i]=consumed[i]+1;pcm_position=consumed[i];pcm_valid=1;head[i]=(head[i]+1)%16;count[i]=count[i]-1;pending=pending|256;end
        end
       end else if(tick<quiet_until[i])reject(i,15);
       else if(converting[i]!=0)reject(i,6);
       else if(exposure[i]>64'hffffffffffffffff-tick)begin reject(i,14);stop_stream(i,FAULT);end
       else begin
        capture[i]=tick;available[i]=tick+exposure[i];q=64'(source_quality[16*i+:16]);source=$signed(stimulus[32*i+:32]);refvalue=$signed(reference_input[32*i+:32]);latched_reference[i]=refvalue;
        if(optical(i))for(j=1;j<=5;j++)if(j!=i&&emitter(j))q=q|32;
        if(i==0&&state[8]==RUNNING)q=q|64;
        value=(source-refvalue)*$signed(gain[i]);
        if(optical(i))begin
         if((selector[i]&256)!=0)value=refvalue*$signed(gain[i]);else value=value*$signed(exposure[i]);
         if(i==3)value=value+$signed(selector[i]&255)*$signed(exposure[i])*$signed(gain[i]);
         if(i==4)begin value=source>0?source*$signed(exposure[i]):0;raw=((selector[i]&15)<<24)|(64'(value)&64'hffffff);end
         else begin
          if(i==5)value=source>0?(source*$signed(exposure[i])+3)/4:0;
          if(value<0)begin value=0;q=q|1;end
          if(value>16777215)begin value=16777215;q=q|1;end
          raw=64'(value);
         end
        end else begin
         if(i==0&&(selector[i]&1)!=0)begin value=(history[i]+value)/2;history[i]=value;end
         if(value< -8388608)begin value= -8388608;q=q|1;end
         if(value>8388607)begin value=8388607;q=q|1;end
         raw=64'(value);
        end
        latched[i]=$signed(raw);quality[i]=q;converting[i]=1;
       end
      end
     end
    end
   end
   if(valid&&write&&!error)begin
    if(addr<256)case(addr)
     40:if(wdata<=511)mask=wdata;
     48:if(wdata<=511)pending=pending&~wdata;
     56:if(wdata<=1)begin inhibit=wdata;if(wdata!=0)for(i=0;i<9;i++)if(output_stream(i))stop_stream(i,CONFIGURED);end
     104,112:if(CONTROLLER_ABI==2)begin
      if(ring_enabled!=0||bus_kind==2||count[8]!=0||(state[8]!=CONFIGURED&&state[8]!=ARMED))reject(8,6);
      else if(addr==104)ring_base=wdata;else ring_capacity=wdata;
     end
     120:if(CONTROLLER_ABI==2)begin
      if(ring_enabled==0||ring_eof!=0||!ring_permitted())reject(8,7);
      else if(wdata<producer)reject(8,4);
      else if(wdata-fetch>ring_capacity)reject(8,3);else producer=wdata;
     end
     136:if(CONTROLLER_ABI==2)case(wdata)
      1:begin
       if(ring_enabled!=0||bus_kind==2||state[8]!=ARMED||count[8]!=0)reject(8,6);
       else if(ring_capacity<16||ring_capacity>2048||(ring_capacity&(ring_capacity-1))!=0||ring_base<DMA_BASE||(ring_base&7)!=0||ring_base>DMA_BASE+DMA_BYTES-ring_capacity*2)reject(8,3);
       else begin
        owner_epoch=epoch[8];owner_consent=consent[8];owner_config=config_revision[8];
        if(!ring_permitted())reject(8,7);
        else begin producer=0;fetch=0;eof_end=0;ring_eof=0;ring_enabled=1;ring_status=1;submitted_base=submitted[8];consumed_base=consumed[8];gaps=0;end
       end
      end
      2:if(ring_enabled==0||!ring_permitted())reject(8,7);else begin if(ring_eof==0)begin ring_eof=1;eof_end=producer;end finish_ring();end
      3:cancel_ring(3,0);
      default:reject(8,2);
     endcase
     64:if(wdata<=1)begin link=wdata;if(wdata==0)for(i=0;i<9;i++)begin reject(i,11);stop_stream(i,DISCONNECTED);consent[i]=0;end end
     default:begin end
    endcase
    else begin
     s=int'(addr[12:8])-1;o=int'(addr[7:0]);
     if(o==24)begin
      fault[s]=0;
      case(wdata)
       1:if(epoch[s]==64'hffffffffffffffff)begin reject(s,14);state[s]=FAULT;end else begin stop_stream(s,IDLE);epoch[s]=epoch[s]+1;sequence_no[s]=0;fault[s]=0;consent[s]=0;calibration[s]=0;history[s]=0;end
       2:if(count[s]!=0)reject(s,6);else if(state[s]!=IDLE&&state[s]!=CONFIGURED)reject(s,5);else if(gain[s]==0||gain[s]>64||period[s]<8||period[s]>64'hffffffff||exposure[s]==0||exposure[s]>65535||exposure[s]>period[s])reject(s,3);else if(config_revision[s]==64'hffffffffffffffff)reject(s,14);else begin config_revision[s]=config_revision[s]+1;state[s]=CONFIGURED;end
       3:if(state[s]!=CONFIGURED)reject(s,5);else if(!enabled(s))reject(s,7);else state[s]=ARMED;
       4:if(state[s]!=ARMED)reject(s,5);else if(!enabled(s))reject(s,7);else begin state[s]=RUNNING;next_sample[s]=tick+1;end
       5:if(state[s]!=RUNNING)reject(s,5);else state[s]=converting[s]!=0?DRAINING:CONFIGURED;
       6:stop_stream(s,CONFIGURED);
       7:begin stop_stream(s,DISCONNECTED);consent[s]=0;end
       8:if(state[s]!=DISCONNECTED||link==0)reject(s,5);else state[s]=IDLE;
       default:reject(s,2);
      endcase
     end else if(o==80)begin
      if(wdata!=0&&wdata<=consent_floor[s])reject(s,4);else begin consent[s]=wdata;if(wdata!=0)consent_floor[s]=wdata;if(wdata==0)stop_stream(s,CONFIGURED);end
     end else if(o==152)begin
      if(wdata!=1||count[s]==0||dma_status[s]==1)reject(s,dma_status[s]==1?6:5);else begin head[s]=(head[s]+1)%16;count[s]=count[s]-1;end
     end else if(o==112&&s==8)begin
      if(ring_enabled!=0||bus_kind==2)reject(8,6);
      else if(!enabled(s)||(state[s]!=ARMED&&state[s]!=RUNNING))reject(s,7);
      else if(submitted[s]==64'hffffffffffffffff)reject(s,14);else if(count[s]==16)reject(s,9);
      else begin index=int'((head[s]+count[s])%16);records[s][index][0]=wdata;records[s][index][5]=consent[s];count[s]=count[s]+1;submitted[s]=submitted[s]+1;end
     end else if(o==160||o==168)begin
      if(dma_status[s]==1)reject(s,6);else if(o==160)dma_pointer[s]=wdata;else dma_words[s]=wdata;
     end else if(o==176)begin
      if(wdata!=1||s==8||count[s]==0||dma_active||dma_words[s]!=8||dma_pointer[s]<DMA_BASE||dma_pointer[s]>DMA_BASE+DMA_BYTES-64||(dma_pointer[s]&63)!=0)reject(s,3);
      else begin dma_stream=s;dma_index=0;dma_active=1;dma_cancel=0;for(k=0;k<8;k++)dma_record[k]=records[s][head[s]][k];dma_status[s]=1;end
     end else if(o==104)begin if(wdata<=tick||(output_stream(s)&&(calibration[s]!=1||inhibit!=0)))reject(s,15);else lease[s]=wdata;end
     else if(o==208)quiet_until[s]=wdata;
     else if(count[s]!=0||(state[s]!=IDLE&&state[s]!=CONFIGURED))reject(s,6);
     else case(o)
      48:gain[s]=wdata;56:period[s]=wdata;64:exposure[s]=wdata;72:selector[s]=wdata;
      88:reject(s,2); // Environmental reference is a source port, not guest-writable stimulus.
      96:if(wdata>1)reject(s,12);else calibration[s]=wdata;
      248:scheduled_start[s]=wdata;default:reject(s,2);
     endcase
    end
   end
   if(ring_enabled!=0&&!ring_permitted())cancel_ring(3,0);
   finish_ring();prepare_bus();
  end
 end
endmodule
