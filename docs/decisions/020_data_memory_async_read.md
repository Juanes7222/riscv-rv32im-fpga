# ADR 020 — Data Memory: Asynchronous Read

**Status:** Accepted  
**Date:** 2026-05-02

## Context

The data memory is implemented using Cyclone V M10K embedded memory blocks
(see [ADR 013](013_memory_sizes.md)). M10K blocks default to registered
(synchronous) read output: the data word appears one clock cycle after the
read address is presented. The single-cycle processor requires the read result
within the same clock cycle that the address is valid, since address
computation, memory read, and register write-back all occur in a single cycle.

## Decision

The data memory is configured with **unregistered (combinational) read output**.
The read address is presented to the M10K combinationally; the output data is
available without a clock edge.

## Rationale

**Single-cycle requirement:**  
In the single-cycle datapath, the load instruction path is:
`PC → instruction_memory → control_unit → register_file → ALU → data_memory → wb_mux → register_file`.
Every stage in this path is combinational. A synchronous memory read would
require a second clock cycle to capture the result, breaking the CPI = 1
invariant for load instructions.

**Pipeline compatibility:**  
In the pipelined implementation the MEM stage presents the memory address at
the beginning of a clock cycle and the result must be available before the
MEM/WB pipeline register clocks at the end of that cycle. Asynchronous read
satisfies this requirement without modification. Synchronous read would require
an additional pipeline stage for memory access, which is not part of the
five-stage pipeline architecture defined for this project.

**Consistency with instruction memory:**  
The instruction memory uses asynchronous read for the same reason
(see [ADR 011](011_instruction_memory_async_read.md)). Using asynchronous
read for both memories keeps the memory interface model uniform across the
design and simplifies timing analysis.

**M10K support:**  
Quartus Prime supports unregistered output mode for simple dual-port M10K
blocks on Cyclone V. The read port output register is disabled via the
megafunction parameter `outdata_reg_b = "UNREGISTERED"`. This is a
first-class supported configuration, not a workaround.

## Consequences

- The load instruction path (`ALU → data_memory → wb_mux`) is purely
  combinational and contributes to the critical path for Fmax measurement.
  This is the expected and desired behavior for the single-cycle design.
- Write operations remain synchronous: data is written to memory on the
  rising clock edge when `dm_wr = 1`. Read and write use separate ports
  of the simple dual-port M10K configuration.
- Read-during-write behavior (same address, same cycle): the read port
  returns the **old data** (value before the write). This is the default
  behavior of simple dual-port M10K with unregistered output and is
  correct for both microarchitectures. The pipeline resolves load-use
  hazards via the forwarding unit, not via memory bypass.
