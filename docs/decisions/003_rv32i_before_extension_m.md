# ADR 003 — RV32I First, Extension M as Second Iteration

**Status:** Accepted  
**Date:** 2026-04-24

## Context

The target ISA is RV32IM. The M extension adds eight multiply and divide
instructions. These can be implemented simultaneously with the base RV32I
instruction set or as a separate iteration after RV32I is verified.

## Decision

The single-cycle processor is first implemented and verified for **RV32I only**
(no M extension). The M extension is added to the ALU and control unit in a
second iteration, after all `rv32ui` riscv-tests pass.

## Rationale

1. **Reduces the debugging search space.** If a test fails during initial
   development, the bug space is constrained to 47 RV32I instructions. Adding
   8 M-extension instructions before the base is verified doubles the potential
   failure sources unnecessarily.

2. **The ALU interface does not change between iterations.** The `alu_rv32im`
   module already reserves opcodes `5'b01010` through `5'b10001` for M
   operations. Adding M support is an internal ALU change with no interface
   impact on any other module.

3. **Verification coverage is additive.** The `rv32um` test suite is run as an
   additional layer on top of the already-passing `rv32ui` suite. This keeps
   verification incremental and traceable.

## Consequences

- The first synthesis replica for Fmax measurement is performed after RV32IM
  verification is complete, not after RV32I only.
- The ALU file (`rtl/shared/alu_rv32im.sv`) contains M-extension logic from
  the first commit; it is gated only by opcode, not by a compile-time flag.
  This avoids maintaining two versions of the same file.
