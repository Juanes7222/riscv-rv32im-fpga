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

**3. Feasible on Cyclone V M10K blocks.**  
Intel Cyclone V M10K blocks support asynchronous read mode. Quartus Prime
infers this behavior when the memory array is described as a combinational
`always_comb` block or via the `altsyncram` megafunction with
`OPERATION_MODE = "ROM"` and `ADDRESS_ACLR = "NONE"`. The timing penalty
relative to synchronous read is acceptable given the overall single-cycle
critical path, which also includes the register file read and ALU computation.

**4. Consistent with the reference implementation.**  
Harris & Harris (2021) use asynchronous instruction memory in their RV32I FPGA
reference design, which serves as the structural baseline for this project.

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
