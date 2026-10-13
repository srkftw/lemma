// Host-only qualification adapter: clock the actual USB RTL for every WAIT.
#include "Vlemma_usb_device.h"
#include "verilated.h"
#include <cstdint>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
int main() {
    VerilatedContext context;
    context.threads(1);
    Vlemma_usb_device model(&context);
    model.enabled=1; model.connected=1; model.bus_reset=0;
    model.valid=0; model.write=0; model.rx_valid=0; model.tx_ready=0;
    auto tick=[&]() { model.clk=0;model.eval();model.clk=1;model.eval(); };
    model.reset=1;tick();model.reset=0;
    std::string line; uint64_t total=0;
    while(std::getline(std::cin,line)) {
        std::istringstream words(line); std::string command,extra; uint64_t count=0;
        if(!(words>>command>>count) || words>>extra || command!="WAIT" ||
           (count!=1000 && count!=100000) || count>100000000-total)
            throw std::runtime_error("bounded WAIT request rejected");
        const uint64_t before=model.ticks;
        for(uint64_t i=0;i<count;++i)tick();
        if(model.ticks!=before+count)throw std::runtime_error("actual controller clocks differ");
        total+=count;
        std::cout<<"WAIT_DONE "<<before<<" "<<model.ticks<<"\n"<<std::flush;
    }
    model.final();
}
