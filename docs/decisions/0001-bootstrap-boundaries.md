# ADR 0001 — Preserve the freestanding boundary before building applications

Status: baseline decision from the project requirements.

The first construction result is a small but real Lean-authored Core0 program lowered
through LLVM to RV64 and executed on a pinned bare-metal virtual platform. Ordinary
Lean's managed runtime is a later implementation, not a hidden prerequisite.

We permit host upstream Lean/LLVM/QEMU and host orchestration. We do not permit target
C/assembly bootstrap sources, ARM substitution, hosted Linux execution, default
OpenSBI, or unexplained linked helpers in the first image. Generated low-level code
needs an explicit, small Lean-authored primitive boundary and artifact provenance.

The first task audits the upstream emitter and either adapts an applicable path or
implements an honestly scoped Lean-authored subset emitter. A manually constructed
AST demonstration is not evidence of compiling ordinary elaborated Lean declarations.

A successful first slice is not completion of the full G1 conformance suite and is not
proof of compiler correctness. Preserve the remaining Stage I obligations in the backlog.
