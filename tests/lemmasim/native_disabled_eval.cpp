// SPDX-License-Identifier: Apache-2.0
// Host-only paired circuit execution. All CPU work is the audited guest ELF.
#include "machine_runtime.h"
#include "lemma_silicon_binding.h"
#include <chrono>
#include <ctime>
#include <fstream>
#include <iostream>
#include <stdexcept>

using namespace lemma;
using Clock = std::chrono::steady_clock;

static void require(bool value, const std::string& message) {
 if (!value) throw std::runtime_error(message);
}

static Options options(const std::string& dir, const std::string& name, bool reference) {
 Options o;
 o.quiet_uart = true;
 o.trace_limit = 0;
 o.deadline = 120;
 o.memory_latency = 3;
 o.reference_disabled_usb_eval = reference;
 o.fork_directory = dir;
 o.uart_path = dir + "/" + name + ".uart";
 return o;
}

static double run(Machine& machine, uint64_t cycles, double* cpuSeconds = nullptr) {
 const auto before = machine.state().cycle;
 const auto start = Clock::now();
 timespec cpuStart{}, cpuEnd{};
 require(clock_gettime(CLOCK_THREAD_CPUTIME_ID, &cpuStart) == 0, "thread CPU timer failed");
 require(machine.run(cycles) == cycles && machine.state().cycle == before + cycles,
         "actual circuit did not execute exact requested clocks");
 require(!machine.state().finished, "guest finished before the declared cut");
 require(clock_gettime(CLOCK_THREAD_CPUTIME_ID, &cpuEnd) == 0, "thread CPU timer failed");
 if (cpuSeconds) *cpuSeconds += double(cpuEnd.tv_sec - cpuStart.tv_sec) +
                               double(cpuEnd.tv_nsec - cpuStart.tv_nsec) / 1000000000;
 return std::chrono::duration<double>(Clock::now() - start).count();
}

static void snapshot(Machine& machine, const std::string& path) {
 const auto before = machine.inspect();
 machine.snapshot(path);
 require(machine.inspect() == before, "snapshot changed the machine boundary");
}

static void equalSnapshots(Machine& reference, Machine& optimized,
                           const std::string& dir, const std::string& name) {
 const auto a = dir + "/" + name + "-reference.chk";
 const auto b = dir + "/" + name + "-optimized.chk";
 snapshot(reference, a);
 snapshot(optimized, b);
 // Same binary, so the complete container, implementation identity, wrapper,
 // generated RTL, and both checksums must match. No field is excluded.
 require(bytes(a) == bytes(b), "full checkpoint differs at " + name);
 require(reference.state().cycle == optimized.state().cycle,
         "virtual boundary differs at " + name);
}

int main(int argc, char** argv) {
 try {
  if (argc == 4 && std::string(argv[1]) == "--resume") {
   const std::string dir = argv[2], source = argv[3];
   std::cout << "{\"status\":\"PASS_RETAINED_SUFFIX_CPU_COMPARISON\",\"samples\":[";
   for (unsigned i = 0; i < 4; ++i) {
    const auto name = "sample" + std::to_string(i);
    Machine reference(options(dir, name + "-reference", true));
    Machine optimized(options(dir, name + "-optimized", false));
    reference.restore(source);
    optimized.restore(source);
    require(reference.state().memory_pending && reference.state().memory_wait &&
            reference.state().isolated && optimized.state().isolated,
            "retained cut lacks the actual privately backed held RAM request");
    double refCPU = 0, optCPU = 0, refWall = 0, optWall = 0;
    // Balance execution order; no cold prefix, input reinjection or clean-up
    // fence is added to the authoritative retained boundary.
    if (i % 2 == 0) {
     refWall = run(reference, 1000003, &refCPU);
     optWall = run(optimized, 1000003, &optCPU);
    } else {
     optWall = run(optimized, 1000003, &optCPU);
     refWall = run(reference, 1000003, &refCPU);
    }
    equalSnapshots(reference, optimized, dir, name);
    if (i) std::cout << ',';
    std::cout << "{\"reference_cpu_seconds\":" << refCPU
              << ",\"optimized_cpu_seconds\":" << optCPU
              << ",\"reference_wall_seconds\":" << refWall
              << ",\"optimized_wall_seconds\":" << optWall << '}';
   }
   std::cout << "],\"suffix_clocks\":1000003,\"complete_checkpoint_pairs\":4,\"masked_fields\":0}\n";
   return 0;
  }
  require(argc == 9, "require output, guest, ROM, DTB, descriptor, two media and DTB address");
  require(!BINDING_USB_ENABLED && !BINDING_BLE_ENABLED && !BINDING_WIFI_ENABLED &&
          !BINDING_BOOT_NV_ENABLED && !BINDING_POWER_SAFETY,
          "reference experiment requires every optional domain to be absent");
  const std::string dir = argv[1];
  double referenceSeconds = 0, optimizedSeconds = 0;
  uint64_t pendingCycle = 0;
  {
   Machine reference(options(dir, "cold-reference", true));
   Machine optimized(options(dir, "cold-optimized", false));
   auto load = [&](Machine& machine, const char* medium) {
    machine.load_elf(argv[2]);
    machine.load_rom(argv[3]);
    const auto dtb = bytes(argv[4]);
    machine.put(number(argv[8]), dtb.data(), dtb.size());
    machine.descriptor(argv[5]);
    machine.open_medium(medium);
    machine.schedule({17, "pen", {1, 1234, 4567, 2048, 3, 1, 0}, {}});
    machine.schedule({23, "pen", {2, 1234, 4567, 0, 2, 1, 0}, {}});
    // A queued wake edge and a later pen event remain in the pending snapshot.
    machine.schedule({10002048, "button", {1}, {}});
    machine.schedule({10002058, "button", {0}, {}});
    machine.schedule({10002100, "pen", {1000000, 3333, 7777, 1024, 3, 1, 0}, {}});
   };
   load(reference, argv[6]);
   load(optimized, argv[7]);
   equalSnapshots(reference, optimized, dir, "cycle0");
   for (const uint64_t cut : {9ULL, 32ULL, 1000000ULL, 10000000ULL}) {
    const auto amount = cut - reference.state().cycle;
    referenceSeconds += run(reference, amount);
    optimizedSeconds += run(optimized, amount);
    require(reference.inspect() == optimized.inspect(), "cold observations differ");
    equalSnapshots(reference, optimized, dir, "cycle" + std::to_string(cut));
   }
   // Prospectively selected meaningful cut: first actual held RAM transaction
   // after 10M, within 1024 clocks. No controller/pipeline register is injected.
   for (unsigned i = 0; i <= 1024; ++i) {
    require(reference.state().memory_pending == optimized.state().memory_pending &&
            reference.state().memory_wait == optimized.state().memory_wait,
            "RAM admission or fractional wait differs");
    if (reference.state().memory_pending && reference.state().memory_wait) {
     pendingCycle = reference.state().cycle;
     break;
    }
    if (i < 1024) {
     referenceSeconds += run(reference, 1);
     optimizedSeconds += run(optimized, 1);
    }
   }
   require(pendingCycle != 0, "no actual in-flight RAM request at declared cut");
   require(reference.state().retired > 0 && reference.state().pen_ingress == 2 &&
           reference.state().input.size() - reference.state().event_index == 3 &&
           reference.state().flushes == 0 && reference.state().backing.observed_write == 0,
           "meaningful guest/raw/pending/storage observations missing");
   equalSnapshots(reference, optimized, dir, "pending-ram");
  }
  {
   // Two independently backed forks restore the entire retained generated
   // pipeline and held RAM request. They never contact either original medium.
   Machine reference(options(dir, "fork-reference", true));
   Machine optimized(options(dir, "fork-optimized", false));
   reference.restore(dir + "/pending-ram-reference.chk");
   optimized.restore(dir + "/pending-ram-optimized.chk");
   require(reference.state().isolated && optimized.state().isolated,
           "restored branches are not private");
   referenceSeconds += run(reference, 1000003);
   optimizedSeconds += run(optimized, 1000003);
   equalSnapshots(reference, optimized, dir, "pending-suffix");
   require(reference.state().input.size() == reference.state().event_index &&
           reference.state().pen_ingress == 3,
           "queued raw inputs were not actually admitted on the suffix");
   reference.warm_reset(8);
   optimized.warm_reset(8);
   referenceSeconds += run(reference, 11);
   optimizedSeconds += run(optimized, 11);
   equalSnapshots(reference, optimized, dir, "warm-reset-edge");
  }
  require(bytes(dir + "/cold-reference.uart") == bytes(dir + "/cold-optimized.uart") &&
          bytes(dir + "/fork-reference.uart") == bytes(dir + "/fork-optimized.uart"),
          "actual guest UART suffix differs");
  std::cout << "{\"status\":\"PASS_FULL_STATE_AND_PENDING_SUFFIX\",\"pending_cycle\":"
            << pendingCycle << ",\"reference_run_seconds\":" << referenceSeconds
            << ",\"optimized_run_seconds\":" << optimizedSeconds
            << ",\"memory_latency\":3,\"suffix_clocks\":1000003,"
            << "\"complete_checkpoint_pairs\":8,\"masked_fields\":0}\n";
  return 0;
 } catch (const std::exception& error) {
  std::cerr << "FAIL: " << error.what() << '\n';
  return 1;
 }
}
