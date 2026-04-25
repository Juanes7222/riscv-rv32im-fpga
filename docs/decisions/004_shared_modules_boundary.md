# ADR 004 — Boundary Between Shared and Microarchitecture-Specific Modules

**Status:** Accepted  
**Date:** 2026-04-24

## Context

The experimental protocol requires that any measured performance difference
between the single-cycle and pipelined implementations be attributable to
microarchitecture, not to differences in secondary components. This requires a
precise definition of which modules are shared verbatim between both designs.

## Decision

The following modules are placed in `rtl/shared/` and instantiated **without
modification** by both microarchitectures:

| Module | File | Justification |
|--------|------|---------------|
| ALU | `alu_rv32im.sv` | Purely combinational, no microarchitectural state |
| Register file | `register_file.sv` | Synchronous write, asynchronous read; no internal forwarding |
| Instruction memory | `instruction_memory.sv` | Address-in / instruction-out; interface identical in both |
| Data memory | `data_memory.sv` | Receives address, write data, dm_wr, dm_ctrl; interface identical |
| Immediate generator | `imm_gen.sv` | Purely combinational, five format types, no state |
| Branch unit | `branch_unit.sv` | Decision logic only; inputs are always rs1/rs2 regardless of microarchitecture |

The following modules are **not** shared:

| Module | Reason |
|--------|--------|
| `control_unit.sv` | Pipeline version must propagate signals through inter-stage registers and support flush |
| `pc_unit.sv` | Pipeline version requires stall (PC hold) and flush inputs absent in single-cycle |
| Inter-stage registers | Exclusive to the pipeline |
| Hazard detection unit | Exclusive to the pipeline |
| Forwarding unit | Exclusive to the pipeline |
| Top-level modules | By definition microarchitecture-specific |

## Rationale

The key criterion is: **does the module's interface or internal behavior need
to change for the pipeline?** If the answer is no, the module is shared. If any
signal is added, removed, or reinterpreted, the module belongs in the
microarchitecture-specific directory.

The register file is shared on the condition that it has **no internal
forwarding**. All forwarding in the pipeline is handled by the dedicated
`forwarding_unit.sv`, which selects the correct operand value before it reaches
the ALU. This keeps the shared register file interface stable.

## Consequences

- The interface of every module in `rtl/shared/` is frozen once both
  microarchitectures are instantiating it. Interface changes require a new ADR.
- Interfaces for all shared modules are documented in
  `docs/architecture/shared_modules.md`.
