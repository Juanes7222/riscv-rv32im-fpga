# ADR 011 — Instruction Memory: Asynchronous Read

**Status:** Accepted  
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

The `instruction_memory` module uses **asynchronous (combinational) read**.
The module has no `clk` port. The instruction output is valid combinationally
whenever the address input is stable.

## Rationale

**1. Required by the single-cycle datapath.**  
In the single-cycle processor, the entire instruction execution — fetch,
decode, execute, memory access, write-back — occurs within a single clock
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

For the single-cycle processor, this is an acceptable trade-off. The instruction
memory is small enough (2048 words for synthesis, 16384 for simulation) that
the logic-cell implementation fits within the device logic budget. The critical
path through the combinational memory read is part of the overall single-cycle
datapath and is measured directly by the Timing Analyzer.

The pipelined processor, in contrast, uses `instruction_memory_pipe.sv` which
describes a synchronous read. Quartus Prime maps this to M10K blocks (64 blocks
for 16384 words), using the embedded memory efficiently instead of consuming
logic cells.

**4. Not feasible to convert single-cycle to synchronous read.**  
Adding a register between the instruction memory output and the decode logic
would change the microarchitecture from single-cycle to two-cycle for
instruction fetch, which is structurally incompatible with the design.
This would require adding an explicit pipeline stage (IF/ID) and an additional
stall cycle on branches, negating the single-cycle advantage of CPI = 1.

## Consequences

- `instruction_memory.sv` has no `clk` port and no sequential logic.
- Quartus synthesis must be configured to allow asynchronous ROM inference for
  this module. This is documented in `docs/reproduction/synthesis_protocol.md`.
- The critical path of the single-cycle processor passes through the
  instruction memory combinational read delay. This is expected and reflected
  in `docs/architecture/single_cycle.md` (Critical Path Analysis section).
- `data_memory` uses **asynchronous read as well** for consistency and to avoid
  a one-cycle load-use stall in the single-cycle design. The write path of
  `data_memory` remains synchronous.
