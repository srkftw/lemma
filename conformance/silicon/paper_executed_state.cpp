// Host-only raw-clock/MMIO and generated-state continuation test.
#include "VPaperExecutedState.h"
#include "verilated.h"
#include "verilated_save.h"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool yes,const char* reason){if(!yes)throw std::runtime_error(reason);}
static std::string bytes(const std::string& p){std::ifstream in(p,std::ios::binary);return {std::istreambuf_iterator<char>(in),{}};}
struct Circuit {
  std::unique_ptr<VerilatedContext> context=std::make_unique<VerilatedContext>();
  VPaperExecutedState top{context.get()};
  uint64_t cycle=0;
  std::vector<uint64_t> observations;
  void tick(unsigned n=1){for(unsigned i=0;i<n;i++){
    top.clk=0;top.eval();top.clk=1;top.eval();
    observations.insert(observations.end(),{top.panel_valid,top.panel_complete,top.panel_abort,
      top.sequence_id,top.panel_x,top.panel_y,top.panel_gray,top.drive_valid,
      top.power_enable,top.drive_phase,top.drive_code,top.drive_x,top.drive_y});
    top.clk=0;top.eval();cycle++;context->timeInc(1);
  }}
  uint64_t access(bool writing,unsigned offset,uint64_t value=0){
    top.valid=1;top.write=writing;top.addr=offset;top.size=3;top.wdata=value;tick();
    unsigned waited=0;while(!top.ready&&waited++<1000)tick();
    require(top.ready&&!top.error,"bounded real MMIO failed");
    uint64_t result=top.rdata;observations.push_back(result);tick();top.valid=0;tick();return result;
  }
  void put(unsigned o,uint64_t v){access(true,o,v);}
  uint64_t get(unsigned o){return access(false,o);}
  void reset(){top.reset_n=0;top.panel_ready=1;top.fb_stall=0;tick(2);top.reset_n=1;tick(40);}
  void refresh(uint64_t id,unsigned mode=2){put(112,id);put(120,0);put(128,0);put(136,8);put(144,4);put(152,mode);put(104,2);}
  void save(const std::string& p){VerilatedSave out;out.open(p.c_str());out<<cycle;out<<top;out.close();}
  void load(const std::string& p){VerilatedRestore in;in.open(p.c_str());in>>cycle;in>>top;in.close();context->time(cycle);}
  void exact_suffix(){
    tick(7);top.fb_stall=0;
    // Preparing a partial, fast configuration cannot change the accepted full quality frame.
    put(136,2);put(144,2);put(152,1);unsigned waited=0;
    while(get(160)!=1&&waited++<1000)tick();require(waited<1000,"scan completion missing");
    require(get(192)==1&&get(200)==0&&get(208)==0&&get(216)==8&&get(224)==4&&get(232)==2,
      "executed full quality authority changed after unissued configuration");
    put(168,1);require(get(192)==1,"ACK erased executed authority");
    put(176,1);tick(40);require(get(160)==1&&get(112)==1&&get(192)==0,
      "reset retained an authoritative old execution");
  }
};
int main(int argc,char** argv){try{
  require(argc==2,"output directory required");std::string dir=argv[1];Circuit original;
  original.reset();original.refresh(1);original.top.fb_stall=1;original.top.now_ticks=250000;
  original.tick(2);original.save(dir+"/pending.snap");original.save(dir+"/observational.snap");
  require(bytes(dir+"/pending.snap")==bytes(dir+"/observational.snap"),"snapshot changed controller state");
  auto boundary=original.cycle;original.observations.clear();original.exact_suffix();original.save(dir+"/complete.snap");
  Circuit fork;fork.load(dir+"/pending.snap");require(fork.cycle==boundary,"fork clock origin differs");
  fork.exact_suffix();fork.save(dir+"/fork-complete.snap");
  require(original.observations==fork.observations,"arbitrary stalled-scan suffix differs");
  require(bytes(dir+"/complete.snap")==bytes(dir+"/fork-complete.snap"),"authoritative generated state differs");
  // Restart from the accepted/old-completed boundary after real reset, rather than
  // flushing either comparison machine or forging a serialized metadata value.
  original.save(dir+"/reset.snap");original.observations.clear();original.refresh(2);original.tick(2);
  original.put(176,1);original.tick(40);require(original.get(160)==1&&original.get(192)==0,"active reset forged completion");
  original.save(dir+"/reset-suffix.snap");Circuit resetfork;resetfork.load(dir+"/reset.snap");
  resetfork.refresh(2);resetfork.tick(2);resetfork.put(176,1);resetfork.tick(40);
  require(resetfork.get(160)==1&&resetfork.get(192)==0,"restored active reset forged completion");
  resetfork.save(dir+"/reset-fork-suffix.snap");require(original.observations==resetfork.observations,
    "reset/old-completed suffix differs");require(bytes(dir+"/reset-suffix.snap")==bytes(dir+"/reset-fork-suffix.snap"),
    "reset generated state differs");
  std::cout<<"PAPER3-STATE PASS observational stalled accepted scan and reset/old-completed exact suffixes\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
