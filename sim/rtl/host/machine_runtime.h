// SPDX-License-Identifier: Apache-2.0
// Host-only reusable RTL machine. Guest computation is exclusively in Vlemma_soc.
#pragma once
#include "Vlemma_soc.h"
#include "verilated.h"
#include "../../host/backing_io.h"
#include <array>
#include <cstdint>
#include <deque>
#include <fstream>
#include <map>
#include <memory>
#include <string>
#include <vector>
namespace lemma {
struct Event { uint64_t cycle=0; std::string kind; std::vector<uint64_t> words; std::string payload; };
uint64_t number(const std::string&);
std::vector<uint8_t> bytes(const std::string&);
std::vector<uint8_t> hexbytes(const std::string&);
Event parse_event(const std::string&);
std::vector<Event> events(const std::string&);
struct Options {
 uint64_t trace_limit=10000,stop_panels=0,fail_flush=0,observer_cycle=0;
 unsigned deadline=120;
 uint64_t memory_latency=0;
 bool quiet_uart=false;
 std::string uart_path,trace_path,panel_path,block_trace_path,input_capture_path,stop_marker,drive_trace_path,fork_directory,backing_capture_path,backing_replay_path;
};
struct State {
 BackingState backing;
 std::vector<uint8_t> ram,rom,framebuffer,visible;
 std::map<uint64_t,std::array<uint8_t,4096>> boot_pages;
 std::map<uint64_t,std::array<uint8_t,512>> overlay,accepted_medium;
 // Logical external work; host sockets/pointers never enter a checkpoint.
 std::optional<BackingRequest> backing_pending;
 uint64_t backing_poll_cycle=0;
 uint64_t backing_orphan=0,backing_retry_ready=0;
 std::map<uint64_t,uint8_t> optical_pending;
 std::vector<Event> input;
 // Derived from retained event payloads; reconstructed on restore and omitted
 // from the wire format, which continues to serialize every event exactly.
 uint64_t event_payload_bytes=0;
 std::deque<Event> samples;
 std::deque<uint8_t> rx;
 uint64_t event_index=0,cycle=0,reset_until=8,boot_cycle=0;
 uint64_t button_level=0,power_reset_cause=1;
 uint64_t retired=0,traps=0,timer_traps=0,flushes=0,media_requests=0,pen_ingress=0,pen_accepted=0,panel_completed=0,panel_aborted=0;
 uint64_t drive_clocks=0,drive_pixels=0,drive_hash=14695981039346656037ULL;
 std::array<uint64_t,3> drive_phases{};
 uint64_t fb_reads=0,fb_writes=0,panel_pixels=0,transitions=0,block_rows=0,block_omitted=0,previous_block_state=~uint64_t(0);
 std::array<uint64_t,4> privilege_cycles{};
 unsigned old_privilege=3;
 bool finished=false,stopped=false,isolated=false,medium_present=false;
 uint32_t finish=0;
 std::string uart_text,stop_marker;
 uint64_t fail_flush=0,stop_panels=0,observer_cycle=0;
 uint64_t memory_latency=0,memory_pending=0,memory_wait=0,memory_addr=0,memory_write=0,memory_wdata=0,memory_strb=0;
 uint64_t media_active=0,media_kind=0,media_sector=0,flush_active=0,flush_cursor=0;
};
class Machine {
 std::unique_ptr<VerilatedContext> context;
 std::unique_ptr<Vlemma_soc> model;
 State s;
 Options options;
 int medium=-1,backing_capture=-1;
 std::shared_ptr<BackingPlatform> backing;
 std::vector<TimedBackingRecord> backing_replay;
 // Fork execution binding is host ownership, separate from authoritative state.
 bool backing_fork_suspended=false;
 uint64_t backing_capture_bytes=0,backing_replay_cursor=0,backing_capture_branch=0;
 std::string active_backing_capture;
 std::optional<BackingOutcome> backing_operation(BackingKind,uint64_t,uint64_t,const uint8_t* = nullptr);
 std::optional<BackingOutcome> poll_backing();
 void capture_backing(uint64_t,const std::vector<uint8_t>&);
 void abandon_media();
 void observe_backing(const BackingRecord&);
 // File handles and private paths are external ownership, never checkpoint
 // state. A restored session has its own persistent backing and lock.
 std::string private_medium_path;
 std::ofstream uart,trace,panel_log,input_capture,block_trace,drive_trace;
 bool prepared=false;
 void tick();
 void block_row(uint64_t,const char*,unsigned,unsigned,uint64_t,uint64_t,uint64_t,uint64_t,unsigned);
 void model_save(const std::string&);
 void export_backing(const std::string&) const;
public:
 explicit Machine(const Options&);
 ~Machine();
 Machine(const Machine&)=delete; Machine& operator=(const Machine&)=delete;
 void put(uint64_t,const uint8_t*,size_t);
 void load_elf(const std::string&);
 void load_rom(const std::string&);
 void descriptor(const std::string&);
 void open_medium(const std::string&);
 void attach_backing(std::shared_ptr<BackingPlatform>);
 void rebind_private_backing(std::shared_ptr<BackingPlatform>);
 const std::string& backing_capture_path() const { return active_backing_capture; }
 void prepare();
 void schedule(Event);
 void schedule_all(const std::vector<Event>&);
 void initial_uart(const std::vector<uint8_t>&);
 uint64_t run(uint64_t);
 void snapshot(const std::string&);
 void restore(const std::string&);
 void warm_reset(uint64_t=8);
 void cold_cycle();
 void retry_backing();
 // An isolated pending fork never reissues its inherited external operation.
 // Bind a complete, validated outcome tape before its virtual clock advances.
 void bind_backing_replay(const std::string&);
 void panel(const std::string&) const;
 void export_medium(const std::string&) const;
 // Export already-private accepted bytes for a platform rebind. Never reads
 // the original Pending adapter or manufactures guest durability.
 void export_private_medium(const std::string&) const;
 void ram_dump(uint64_t,uint64_t,const std::string&) const;
 std::string inspect() const;
 void report(const std::string&) const;
 const State& state() const { return s; }
 Vlemma_soc& soc() { return *model; }
};
}
