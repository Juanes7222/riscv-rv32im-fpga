# ADR 010 — Unified SystemVerilog Style: logic + always_comb

**Status:** Accepted  
**Date:** 2026-04-24

## Context

The project uses SystemVerilog (IEEE 1800-2017) as the implementation language,
as stated in the thesis document. Legacy Verilog constructs (`reg`, `wire`,
`always @(*)`) are syntactically valid in a `.sv` file but create ambiguity:
`reg` does not imply a register in synthesis, and `always @(*)` is less precise
than `always_comb` about sensitivity list intent.

Mixed use of Verilog and SystemVerilog constructs within the same file has been
observed in the initial ALU and control unit prototypes.

## Decision

All RTL source files in the project use the following conventions:

- **`logic`** is used for all signal declarations, replacing both `wire` and
  `reg`. Ports, internal signals, and intermediate values all use `logic`.
- **`always_comb`** replaces `always @(*)` for all combinational blocks.
  `always_comb` has a precisely defined sensitivity list and is checked by
  synthesis tools for combinational completeness.
- **`always_ff @(posedge clk)`** is used for all synchronous sequential blocks.
- **`localparam`** is used for constants. `parameter` is reserved for module
  parameters exposed at the instantiation boundary.
- **Continuous assignment (`assign`)** is used for simple combinational
  expressions that do not require a procedural block.

## Rationale

Quartus Prime and the cocotb simulation flow (Icarus Verilog or ModelSim) both
support the chosen constructs fully. Using `always_comb` instead of
`always @(*)` causes the simulator to report an error if the sensitivity list
is incomplete, catching a class of combinational bugs at simulation time rather
than during hardware testing. Uniform style also reduces cognitive load when
reading across modules.

## Consequences

- All prototype modules (control unit, ALU, branch unit) must be updated to
  replace `reg` with `logic` and `always @(*)` with `always_comb` before
  committing to `rtl/`.
- The Quartus project settings must specify SystemVerilog as the HDL version
  for all `.sv` files.
- Icarus Verilog must be invoked with the `-g2012` flag (or equivalent) to
  enable SystemVerilog-2012 parsing.
