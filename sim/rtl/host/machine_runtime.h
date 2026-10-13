// SPDX-License-Identifier: Apache-2.0
// Host-only reusable RTL machine. Guest computation is exclusively in Vlemma_soc.
#pragma once
#include "Vlemma_soc.h"
#include "verilated.h"
#include "../../host/backing_io.h"
#include "../../host/panel_pending.h"
#ifndef __EMSCRIPTEN__
#include "../../radio/ble_peer_transport.h"
#endif
#include "../../usb/usb_transport.h"
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
 unsigned deadline=120,host_threads=1;
 unsigned ble_peer_timeout_ms=10000,usb_peer_timeout_ms=60000;
 std::string usb_peer_executable,usb_capture_path;
 std::string boot_capture_path,boot_replay_path;
 std::vector<std::string> usb_peer_arguments;
 uint64_t ble_drop_packets=0;
 std::string ble_peer_executable,ble_capture_path,ble_replay_path,ble_wire_path;
 std::vector<std::string> ble_peer_arguments;
 uint64_t memory_latency=0;
 bool quiet_uart=false;
 std::string uart_path,trace_path,panel_path,block_trace_path,input_capture_path,stop_marker,drive_trace_path,fork_directory,backing_capture_path,backing_replay_path;
};
struct BleOutcome {
 uint64_t id=0,issued=0,accepted=0,header=0;
 std::vector<uint8_t> payload;
 std::string frame;
};
struct State {
 BackingState backing,boot_backing;
 std::map<uint64_t,std::array<uint8_t,512>> accepted_boot_medium;
 std::optional<BackingRequest> boot_pending;
 uint64_t boot_poll_cycle=0,boot_orphan=0,boot_medium_present=0;
 uint64_t boot_request_origin=0,boot_request_id=0,boot_request_kind=0,boot_request_sector=0;
 uint64_t boot_reset_origin=1,boot_reset_seen=1;
 std::vector<uint8_t> ram,rom,framebuffer,visible;
 std::map<uint64_t,std::array<uint8_t,4096>> boot_pages;
 std::map<uint64_t,std::array<uint8_t,512>> overlay,accepted_medium;
 // Logical external work; host sockets/pointers never enter a checkpoint.
 std::optional<BackingRequest> backing_pending;
 uint64_t backing_poll_cycle=0;
 uint64_t backing_orphan=0,backing_retry_ready=0;
 PanelPending optical_pending;
 std::vector<Event> input;
 // Derived from retained event payloads; reconstructed on restore and omitted
 // from the wire format, which continues to serialize every event exactly.
 uint64_t event_payload_bytes=0;
 std::deque<Event> samples;
 std::deque<uint8_t> rx;
 uint64_t event_index=0,cycle=0,reset_until=8,boot_cycle=0;
 uint64_t button_level=0,power_reset_cause=1;
 uint64_t power_good=1,brownout=0,power_domain_seen=0;
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
 uint64_t ble_attached=0,ble_ready=0,ble_coex=1,ble_next_id=1,ble_poll_cycle=0,ble_pending=0;
 uint64_t ble_request_cycle=0,ble_request_header=0;
 std::vector<uint8_t> ble_request_payload;
 std::string ble_accepted_state,ble_error;
 BleOutcome ble_last;
 uint64_t ble_peer_reset_until=8,ble_drop_remaining=0,ble_dropped_packets=0,ble_peer_sending=0,ble_peer_dropping=0;
 uint64_t ble_to_chip_valid=0,ble_to_chip_bit=0,ble_to_peer_valid=0,ble_to_peer_bit=0;
 uint64_t ble_raw_valid=0,ble_raw_bit=0,ble_ack_pending=0,ble_ack_header=0;
 uint64_t ble_chip_samples=0,ble_peer_samples=0,ble_rx_heads=0,ble_accepted_replies=0;
 std::deque<std::array<uint64_t,2>> ble_pio;
};
class Machine {
 std::unique_ptr<VerilatedContext> context;
 std::unique_ptr<Vlemma_soc> model;
 State s;
#ifndef __EMSCRIPTEN__
 std::unique_ptr<BlePeerTransport> ble_peer;
 std::unique_ptr<UsbProcessTransport> usb_peer;
#endif
 // USB6 external process state remains explicitly unadmitted for snapshots.
 std::optional<UsbRawCommand> usb_command;
 std::vector<uint8_t> usb_incoming,usb_outgoing;
 std::deque<std::vector<uint8_t>> usb_packets;
 uint64_t usb_cursor=0,usb_until=0,usb_reset_until=0,usb_next_poll=0,usb_capture_bytes=0;
 bool usb_connected=false,usb_rx_transfer=false,usb_tx_transfer=false;
 std::ofstream usb_capture;
 void usb_before_edge();
 void usb_after_edge();
 void usb_record(uint64_t,uint64_t,const std::string&);
 void usb_reply(const std::string&);
 std::vector<BleOutcome> ble_replay;
 uint64_t ble_replay_cursor=0;
 bool ble_fork_suspended=false;
 std::ofstream ble_capture,ble_wire;
 std::string active_ble_capture;
 uint64_t ble_capture_bytes=0,ble_capture_branch=0;
 void ble_before_edge();
 void ble_after_edge();
 uint64_t ble_read(uint64_t);
 void ble_queue(uint64_t,uint64_t);
 void ble_record(uint64_t,const BleOutcome&);
 void ble_accept(const BleOutcome&);
 void ble_reply_action(const std::string&);

 Options options;
 int boot_medium=-1,boot_capture=-1;
 std::shared_ptr<BackingPlatform> boot_platform;
 std::vector<TimedBackingRecord> boot_replay;
 uint64_t boot_capture_bytes=0,boot_replay_cursor=0,boot_capture_branch=0;
 bool boot_fork_suspended=false;
 std::string active_boot_capture,private_boot_medium_path;
 void boot_before_edge(bool);
 void capture_boot(uint64_t,const std::vector<uint8_t>&);
 std::optional<BackingOutcome> boot_operation(BackingKind,uint64_t,uint64_t,const uint8_t* = nullptr);
 std::optional<BackingOutcome> poll_boot();
 void observe_boot(const BackingRecord&);
 void initialize_boot_io();
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
 void open_boot_medium(const std::string&);
 void attach_boot_backing(std::shared_ptr<BackingPlatform>);
 void bind_boot_replay(const std::string&);
 void export_boot_medium(const std::string&) const;
 const std::string& boot_capture_path() const {return active_boot_capture;}
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
 void bind_ble_replay(const std::string&);
 const std::string& ble_capture_path() const {return active_ble_capture;}
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
