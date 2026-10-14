// Host-only validation against retained actual Machine archives and outcomes.
// This fixture never runs a CPU clock or starts a USB process.
#include "machine_runtime.h"
#include <fstream>
#include <iostream>
using namespace lemma;
static void need(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}
int main(int argc, char **argv) try {
    need(argc == 3, "retained component and unused output arguments required");
    std::string source = argv[1], output = argv[2];
    Options options;
    options.usb_recovery = true;
    options.quiet_uart = true;
    options.uart_path = output + "/validation.uart";
    options.fork_directory = output;
    Machine machine(options);
    machine.restore(source + "/after-attach.snap");
    machine.snapshot(output + "/before.snap");
    const auto original = bytes(output + "/before.snap");
    need(original == bytes(source + "/after-attach.snap"), "retained boundary differs");
    const auto before = machine.inspect();
    auto rejected = [&](const std::string &name, bool tape) {
        bool failed = false;
        std::string reason;
        try {
            if (tape) machine.bind_usb_replay(output + "/" + name + ".tape");
            else machine.restore(output + "/" + name + ".snap");
        } catch (const std::runtime_error &error) {
            failed = true;
            reason = error.what();
        }
        need(failed && machine.inspect() == before, "rejection changed inspected state");
        auto observed = output + "/after-" + name + ".snap";
        machine.snapshot(observed);
        need(bytes(observed) == original, "rejection changed authoritative state");
        std::cout << name << ": " << reason << '\n';
    };
    for (const auto *name : {"marker", "epoch-zero", "epoch-overflow", "container", "binding-hex"})
        rejected(name, false);
    for (const auto *name : {"tape-epoch", "tape-next-id", "tape-binding"})
        rejected(name, true);
    machine.bind_usb_replay(source + "/final.tape");
    machine.snapshot(output + "/bound.snap");
    need(bytes(output + "/bound.snap") == original, "valid binding changed boundary");
    std::cout << "NATIVE_USB_RECOVERY_VALIDATION_PASS eight structural negatives exact unchanged full archive zero clocks no peer\n";
    return 0;
} catch (const std::exception &error) {
    std::cerr << "FAIL " << error.what() << '\n';
    return 1;
}
