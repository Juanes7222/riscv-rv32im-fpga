# ADR 011 - Instruction Memory: Asynchronous Read

**Status:** Superseded in part by [ADR 046](046_single_cycle_imem_next_pc.md) —
the instruction memory of the single-cycle processor now uses a registered
read addressed with the next PC. The data memory decision stands.  
**Date:** 2026-04-24

## Context

The instruction memory must present a valid 32-bit instruction word in the same
clock cycle that the PC value is presented as an address. Two implementation
options exist for memory read behavior:

1. **Asynchronous read (combinational):** The output is a pure function of the
   address input. No clock edge is required to sample the output. The
   instruction is available in the same cycle as the address.

2. **Synchronous read (registered output):** The output is captured in a
   register on the rising clock edge. The instruction appears one cycle after
   the address is presented.

## Decision

The single-cycle instruction memory (`rtl/single_cycle/instruction_memory.sv`)
uses a **registered read addressed with the next PC** (ADR 046). The module has
`clk` and `fetch_en` ports: the word read with `next_pc` at the end of cycle N
is the instruction of cycle N+1, already available when it is executed, so the
memory's own address register acts as the IF/ID boundary without adding a
bubble and CPI stays 1. The out-of-range NOP mux sits after the output
register, otherwise Quartus does not infer the M10K block.

The pipelined processor keeps its own synchronous-read module
(`rtl/pipeline/instruction_memory_pipe.sv`): its IF/ID register captures the
instruction at the clock edge, so a clocked read is sufficient and Quartus maps
it to M10K blocks (see ADR 011 §1-3 as originally written).

ADR 011 §4 ("not feasible to convert single-cycle to synchronous read") is
superseded by ADR 046: presenting the next PC instead of the current PC lets
the registered read absorb the fetch without adding a stage or a stall.

> **Superseded in part by ADR 046.** The single-cycle instruction memory now
> uses a registered read addressed with the next PC and is inferred as M10K.
> What remains valid is §2 (the pipeline's IF stage needs the read it already
> has) and the M10K physics in §3. §1 and §4 argue that a registered read is
> incompatible with the single-cycle; ADR 046 shows that the incompatibility
> was an artefact of addressing with the current PC, and both arguments are
> left below only as the record of the original decision.

## Rationale

**1. Required by the single-cycle datapath.** *(Superseded by ADR 046, see the
note at the end of this section.)*
In the single-cycle processor, the entire instruction execution - fetch,
decode, execute, memory access, write-back - occurs within a single clock
cycle. A synchronous instruction memory would require the PC to be presented
one cycle before the instruction is needed, which is structurally incompatible
with a single-cycle design. The only alternative would be to add an implicit
pipeline stage between PC and decode, which changes the fundamental character
of the microarchitecture.

**2. Required by the pipelined IF stage.**  
In the five-stage pipeline, the Instruction Fetch (IF) stage must present a
valid instruction to the IF/ID pipeline register at the end of the same cycle
in which the PC is valid. A synchronous memory would add one cycle of latency
to every instruction fetch, which cannot be absorbed without adding a
sixth pipeline stage or using a stall.

**3. M10K blocks on Cyclone V require synchronous read.**  
Intel Cyclone V M10K embedded memory blocks always register the read operation
internally. The block has a configurable output register (`OUTDATA_REG`), but the
read from the memory array itself is clocked: data appears on the output a fixed
time after the rising clock edge, even when the output register is bypassed
(Intel Corporation, 2016, Section 3-4). A purely combinational read (`assign`
from an unpacked array) cannot be absorbed into an M10K block; Quartus Prime
implements it in logic cells (LUTs and flip-flops) regardless of any
`ramstyle = "M10K"` attribute.

For the single-cycle processor this trade-off was accepted at the time: the
instruction memory was small enough (2048 words for synthesis, 16384 for
simulation) for a logic-cell implementation to fit. ADR 046 reversed that
because CoreMark needs 4096 words and the logic-cell array does not route at
that size; the single-cycle memory is now a registered M10K read of 4096 words.

The pipelined processor uses `instruction_memory_pipe.sv`, which describes a
synchronous read. Quartus Prime maps it to M10K blocks, using the embedded
memory instead of consuming logic cells.

**4. Not feasible to convert single-cycle to synchronous read.**  
Adding a register between the instruction memory output and the decode logic
would change the microarchitecture from single-cycle to two-cycle for
instruction fetch, which is structurally incompatible with the design. This
would require adding an explicit pipeline stage (IF/ID) and an additional
stall cycle on branches, negating the single-cycle advantage of CPI = 1.

> **Superseded by ADR 046.** This argument assumes the address presented to the
> memory must be the current PC. Presenting the next PC instead - which the
> datapath already computes combinationally in the same cycle - lets the
> memory's own address register act as the IF/ID boundary without adding a
> bubble. The single-cycle instruction memory now uses a registered read and is
> inferred as M10K.

## Consequences

- `rtl/single_cycle/instruction_memory.sv` has `clk` and `fetch_en` ports and
  performs a registered read (ADR 046); `rtl/pipeline/instruction_memory_pipe.sv`
  keeps its synchronous read (pipeline, unchanged).
- The async-ROM configuration note in `docs/reproduction/synthesis_protocol.md`
  no longer applies to the single-cycle instruction memory.
- The single-cycle critical path no longer passes through a combinational
  instruction-memory read; it passes through the M10K output register, the
  next-PC mux and the M10K address setup (see `docs/architecture/single_cycle.md`,
  Critical Path Analysis section).
- `data_memory` is governed by ADR 020 and ADR 048 (half-cycle M10K read in the
  single-cycle, synchronous read in the pipeline).
