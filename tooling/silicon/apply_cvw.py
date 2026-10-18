#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Narrow pinned CVW patch: architectural AHB response access faults.

Upstream ebu explicitly ignores HRESP. Preserve every upstream source notice;
modified copies live under ignored build/, and exact replacements fail closed.
No instruction semantics, MMU identity mappings, or software policy substitutes.
"""
from pathlib import Path
import argparse, sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from action_cache import write_if_changed

def replace(text, old, new):
    if text.count(old)!=1: raise RuntimeError('pinned CVW patch anchor differs: '+old[:100])
    return text.replace(old,new)

def apply(dep, out):
    modifications={}
    p='src/wally/wallypipelinedcore.sv';t=(dep/p).read_text()
    t=replace(t,'  // instruction fetch unit: PC, branch prediction, instruction cache', '''  // Lemma patch: latch AHB data-phase ownership; upstream EBU ignores HRESP.
  logic BusPhaseValid, BusPhaseData, BusPhaseWrite;
  logic BusErrorComplete, IFUBusErrorHeld, LSULoadBusErrorHeld, LSUStoreBusErrorHeld;
  logic IFUBusAccessFaultF, LSULoadBusAccessFaultM, LSUStoreBusAccessFaultM;
  always_ff @(posedge clk) begin
    if (reset) begin
      BusPhaseValid <= 0; BusPhaseData <= 0; BusPhaseWrite <= 0;
      IFUBusErrorHeld <= 0; LSULoadBusErrorHeld <= 0; LSUStoreBusErrorHeld <= 0;
    end else begin
      if(HREADY) begin
        BusPhaseValid <= HTRANS[1]; BusPhaseData <= HPROT[0]; BusPhaseWrite <= HWRITE;
      end
      if(!StallF || FlushD) IFUBusErrorHeld <= 0;
      else if(BusErrorComplete && !BusPhaseData) IFUBusErrorHeld <= 1;
      if(!StallM || FlushM) begin LSULoadBusErrorHeld <= 0; LSUStoreBusErrorHeld <= 0; end
      else if(BusErrorComplete && BusPhaseData) begin
        LSULoadBusErrorHeld <= !BusPhaseWrite; LSUStoreBusErrorHeld <= BusPhaseWrite;
      end
    end
  end
  assign BusErrorComplete = BusPhaseValid && HRESP && HREADY;
  assign IFUBusAccessFaultF = IFUBusErrorHeld || (BusErrorComplete && !BusPhaseData);
  assign LSULoadBusAccessFaultM = LSULoadBusErrorHeld || (BusErrorComplete && BusPhaseData && !BusPhaseWrite);
  assign LSUStoreBusAccessFaultM = LSUStoreBusErrorHeld || (BusErrorComplete && BusPhaseData && BusPhaseWrite);

  // instruction fetch unit: PC, branch prediction, instruction cache''')
    t=replace(t,'  ifu #(P) ifu(.clk, .reset,','  ifu #(P) ifu(.clk, .reset, .IFUBusAccessFaultF,')
    t=replace(t,'  lsu #(P) lsu(\n    .clk, .reset,','  lsu #(P) lsu(\n    .clk, .reset, .LSULoadBusAccessFaultM, .LSUStoreBusAccessFaultM,')
    modifications[p]=t
    p='src/ifu/ifu.sv';t=(dep/p).read_text()
    t=replace(t,'  input  logic                 HPTWInstrAccessFaultF,', '  input  logic                 IFUBusAccessFaultF, // Lemma AHB response access fault\n  input  logic                 HPTWInstrAccessFaultF,')
    t=replace(t,'.InstrPageFaultF(InstrPageFaultRawF), .InstrAccessFaultF(InstrAccessFaultRawF),', '.InstrPageFaultF(InstrPageFaultRawF), .InstrAccessFaultF(InstrAccessFaultRawF | IFUBusAccessFaultF),')
    t=replace(t,'    assign InstrAccessFaultF = InstrAccessFaultRawF;', '    assign InstrAccessFaultF = InstrAccessFaultRawF | IFUBusAccessFaultF;')
    modifications[p]=t
    p='src/lsu/lsu.sv';t=(dep/p).read_text()
    t=replace(t,'  logic                  LSULoadAccessFaultM;', '  logic                  MMULoadAccessFaultM, MMUStoreAccessFaultM;\n  logic                  LSULoadAccessFaultM;')
    t=replace(t,'  logic                  LSUStoreAmoAccessFaultM;', '  logic                  LSUStoreAmoAccessFaultM;\n  assign LSULoadAccessFaultM = MMULoadAccessFaultM | LSULoadBusAccessFaultM;\n  assign LSUStoreAmoAccessFaultM = MMUStoreAccessFaultM | LSUStoreBusAccessFaultM;')
    t=replace(t,'  input  logic                    clk, reset,','  input  logic                    clk, reset,\n  input  logic                    LSULoadBusAccessFaultM, LSUStoreBusAccessFaultM,')
    t=replace(t,'.InstrAccessFaultF(), .LoadAccessFaultM(LSULoadAccessFaultM),', '.InstrAccessFaultF(), .LoadAccessFaultM(MMULoadAccessFaultM),')
    t=replace(t,'.StoreAmoAccessFaultM(LSUStoreAmoAccessFaultM), .InstrPageFaultF(),', '.StoreAmoAccessFaultM(MMUStoreAccessFaultM), .InstrPageFaultF(),')
    t=replace(t,'    assign {DTLBMissM, LSULoadAccessFaultM, LSUStoreAmoAccessFaultM, LoadMisalignedFaultM, StoreAmoMisalignedFaultM}', '    assign {DTLBMissM, MMULoadAccessFaultM, MMUStoreAccessFaultM, LoadMisalignedFaultM, StoreAmoMisalignedFaultM}')
    modifications[p]=t
    for p,t in modifications.items():
        write_if_changed(out/p,t.encode())
    return modifications.keys()
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('dependency',type=Path);ap.add_argument('output',type=Path);a=ap.parse_args();apply(a.dependency,a.output)
