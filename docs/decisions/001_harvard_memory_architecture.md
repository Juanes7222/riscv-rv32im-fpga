# ADR 001 — Harvard Memory Architecture

**Status:** Accepted  
**Date:** 2026-04-24

## Context

A RISC-V processor on FPGA can be implemented with either a unified memory
(Von Neumann) or separate instruction and data memories (Harvard). The target
device is the Intel Cyclone V 5CSEMA5F31C6 on the DE1-SoC board, which
provides M10K embedded memory blocks.

## Decision

Both the single-cycle and pipelined implementations use a **strict Harvard
architecture**: `instruction_memory` and `data_memory` are independent modules
with no shared address space.

## Rationale

1. **Eliminates structural hazards at the IF/MEM boundary.** In the pipelined
   implementation, the Instruction Fetch stage (IF) and the Memory Access stage
   (MEM) are active in the same clock cycle. A unified memory would require
   arbitration logic or stall insertion to prevent conflicts. Separate memories
   remove this hazard category entirely without hardware cost.

2. **Maps cleanly to Cyclone V M10K blocks.** Quartus Prime infers dual-port
   M10K blocks from synchronous memory descriptions. With Harvard, each memory
   can be independently sized and assigned to separate M10K blocks, simplifying
   timing closure.

3. **Consistent with the reference implementations.** Harris & Harris (2021)
   use a Harvard split for the RV32I FPGA reference implementation that this
   project uses as a structural baseline.

## Consequences

- `instruction_memory.sv` and `data_memory.sv` are independent modules placed
  in `rtl/shared/`.
- The top-level module instantiates both memories separately and routes the
  correct address and data buses to each.
- The address space is not unified; software running on the processor cannot
  treat instructions as data (no self-modifying code, no dynamic dispatch via
  memory). This is acceptable for the RV32IM benchmark workloads used in this
  project (riscv-tests, CoreMark).
- Memory sizing (depth of each memory) is documented in
  `docs/architecture/shared_modules.md`.
