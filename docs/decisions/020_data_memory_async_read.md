# ADR 020 - Data Memory: Read Behavior

**Status:** Superseded in part by [ADR 048](048_single_cycle_half_cycle_data_memory.md) —
the single-cycle data memory now reads on the second half of the cycle from a
four byte-lane M10K array. The pipeline keeps a synchronous read.  
**Date:** 2026-05-02

## Context

The data memory is implemented using Cyclone V M10K embedded memory blocks
(see [ADR 013](013_memory_sizes.md)). M10K blocks default to registered
(synchronous) read output: the data word appears one clock cycle after the
read address is presented.

## Decision

**Single-cycle data memory** (`rtl/single_cycle/data_memory.sv`): four byte-lane
`M10K` arrays with a **half-cycle read**. The write port is clocked by the
rising edge; the read address is captured on the falling edge
(`always_ff @(negedge clk)`) and the block output is combinational, so a load
completes in its own cycle and CPI stays 1 (ADR 048). The half/byte selection
and sign extension run after the block output.

**Pipelined data memory** (`rtl/pipeline/data_memory_pipe.sv`): keeps a
**synchronous read** (registered output on the rising edge); the load-use
interlock covers the extra cycle.

> **Superseded in part by ADR 048.** The single-cycle data memory no longer
> uses a purely combinational read from logic cells; it reads from M10K on the
> falling edge of the clock. ADR 020 §5 (M10K `outdata_reg_b = "UNREGISTERED"`)
> no longer applies to the single-cycle; the pipeline still uses registered
> M10K reads.

## Rationale

**Single-cycle requirement:**  
In the single-cycle datapath, the load instruction path is:
`PC --> instruction_memory --> control_unit --> register_file --> ALU -->`
`data_memory --> wb_mux --> register_file`. Every stage in this path is
combinational. Deferring the data-memory read by a full cycle would require a
load-use interlock and break CPI = 1. A purely asynchronous array in logic
cells does not route at 4 KB (ADR 048), so the memory uses both edges of the
cycle: write on the rising edge, read address captured on the falling edge,
combinational output. The load issued in a cycle presents its address after
the rising edge, the address register samples it mid-cycle, and the word is
stable at the block output before the rising edge that writes the register
file.

**Pipeline compatibility:**  
In the pipelined implementation the MEM stage presents the memory address at
the beginning of a clock cycle and the result must be available before the
MEM/WB pipeline register clocks at the end of that cycle. Synchronous read
satisfies this requirement without modification.

## Consequences

- The single-cycle load path (`ALU --> data_memory --> wb_mux`) is timed over
  the second half of the cycle (ADR 048). It remains part of the critical
  path for Fmax measurement.
- Write operations remain synchronous in both versions: memory is updated on
  the rising clock edge when `dm_wr == 1`.
- Read-during-write behavior (same address, same cycle): the read port
  returns the **old data** (value before the write). This is correct for both
  microarchitectures. The pipeline resolves load-use hazards via the
  forwarding unit, not via memory bypass.
- Natural alignment is assumed. Misaligned accesses produce undefined results;
  no exception is raised.
