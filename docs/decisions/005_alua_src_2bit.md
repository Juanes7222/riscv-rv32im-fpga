# ADR 005 — ALU Operand-A Source Extended to 2 Bits

**Status:** Accepted  
**Date:** 2026-04-24

## Context

The original control unit design used a 1-bit `alua_src` signal to select the
first operand of the ALU: `0` for rs1 (register file) and `1` for PC (required
by AUIPC and branch target calculation).

During design review, the LUI instruction was identified as requiring a third
source: the constant zero. LUI must compute `rd = 0 + U_immediate`. With a
1-bit `alua_src`, the only available sources are rs1 and PC. Using rs1 for LUI
is incorrect because bits [19:15] of a U-type instruction encode part of the
immediate, not a register address. Reading register `inst[19:15]` produces an
arbitrary value that corrupts the LUI result.

## Decision

The `alua_src` control signal is **extended to 2 bits** with the following
encoding:

| `alua_src` | ALU operand A source |
|------------|----------------------|
| `2'b00` | rs1 (register file output) |
| `2'b01` | PC (current program counter) |
| `2'b10` | Constant 0 |
| `2'b11` | Reserved |

The datapath mux for operand A is updated from 2 to 3 entries accordingly.

The control unit sets `alua_src = 2'b10` for LUI and `alua_src = 2'b01` for
AUIPC, JAL, and BRANCH target calculation.

## Rationale

LUI semantics per the RISC-V specification: `rd = {imm[31:12], 12'b0}`. The
ALU computes `0 + U_immediate` using the ADD operation. Any other value in
operand A produces an incorrect result. The fix requires no new hardware beyond
widening the existing mux.

## Consequences

- `alua_src` changes from `logic` (1 bit) to `logic [1:0]` in the control unit
  port list and in the top-level module.
- The operand-A mux in the datapath gains a third input tied to `32'b0`.
- All existing assignments in the control unit that set `alua_src = 1'b0` or
  `1'b1` must be updated to `2'b00` and `2'b01` respectively.
- This change applies to both the single-cycle and pipeline control units.
