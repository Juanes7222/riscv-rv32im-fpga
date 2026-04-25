# ADR 009 — MULHSU Implemented via 33-Bit Sign/Zero Extension

**Status:** Accepted  
**Date:** 2026-04-24

## Context

MULHSU computes the upper 32 bits of a signed × unsigned 32-bit multiplication.
A naive implementation using Verilog/SystemVerilog type casting produces
incorrect results because of how the language resolves mixed signed/unsigned
expressions: when one operand is declared `signed` and the other `unsigned`,
both are treated as unsigned before the operation, discarding the sign
information of the first operand.

The following pattern does **not** produce MULHSU-correct results:

```verilog
wire signed [31:0] a_signed = a;
wire        [31:0] b_unsigned = b;
assign mul_result_su = a_signed * b_unsigned;  // Both treated as unsigned
```

## Decision

MULHSU is implemented by **sign-extending operand A to 33 bits and
zero-extending operand B to 33 bits**, then performing a signed 33×33
multiplication:

```systemverilog
logic signed [32:0] a_33;
logic signed [32:0] b_33;
logic signed [65:0] mulhsu_result;

assign a_33 = {a[31], a};       // Sign-extend: preserves two's complement sign
assign b_33 = {1'b0, b};        // Zero-extend: forces positive signed value
assign mulhsu_result = a_33 * b_33;
// mulhsu_result[63:32] is the correct MULHSU upper half
```

The 33-bit representation makes both operands unambiguously `signed` to the
tool. A positive `b_33` (MSB = 0) is equivalent to treating `b` as an unsigned
value in a signed multiplication.

## Rationale

The 33-bit technique is the standard hardware pattern for mixed-sign
multiplication. It is deterministic across simulators (Icarus, ModelSim,
Verilator) and synthesis tools (Quartus) because no implicit type conversion is
involved. The `rv32um-mulhsu` test in riscv-tests exercises this case
explicitly.

## Consequences

- The `alu_rv32im.sv` module uses 33-bit intermediate signals for MULHSU only.
  MUL, MULH, and MULHU continue to use 32-bit or 64-bit intermediates as
  appropriate.
- The synthesis impact is negligible: Quartus maps 33-bit multipliers to the
  same variable-precision DSP blocks used for 32-bit multiplications.
