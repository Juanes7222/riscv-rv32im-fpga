# ADR 003 — RV32I First, Extension M as Second Iteration

**Status:** Accepted (updated 2026-05-02 for consistency with ADR 018)  
**Date:** 2026-04-24

## Context

The target ISA is RV32IM. The M extension adds eight multiply and divide
instructions. The ALU (`alu_rv32im.sv`) includes M-extension logic from the
first implementation, gated by opcode (see [ADR 018](018_alu_rv32im.md)).
The question is whether the control unit enables M opcodes from the start or
in a separate iteration after RV32I is verified.

## Decision

The control unit is first implemented and verified for **RV32I only**. M
extension opcodes are enabled in the control unit in a second iteration,
after all `rv32ui` riscv-tests pass. The ALU is not subject to this
iteration boundary — it includes M-extension logic from the first commit.

## Rationale

1. **Reduces the debugging search space.** If a test fails during initial
   development, the bug space is constrained to the 37 RV32I instructions
   decoded by the control unit. Enabling M opcodes before the base is verified
   adds 8 new failure sources without a clean baseline to compare against.

2. **The ALU interface does not change between iterations.** `alu_rv32im`
   already reserves opcodes `5'b01010` through `5'b10001` for M operations.
   Enabling M support in the control unit is a localized change with no
   interface impact on any other module.

3. **Verification coverage is additive.** The `rv32um` test suite runs as an
   additional layer on top of the already-passing `rv32ui` suite. This keeps
   verification incremental and traceable.

## Consequences

- The first clean simulation milestone is: all `rv32ui` tests pass with the
  RV32I-only control unit.
- The second milestone is: all `rv32um` tests pass after M opcodes are added
  to the control unit.
- The first synthesis replica for Fmax measurement is performed after both
  milestones are complete (full RV32IM verification).
- `alu_rv32im.sv` contains M-extension logic from the first commit and is
  never modified between iterations. Only `control_unit.sv` changes between
  iteration 1 and iteration 2.
