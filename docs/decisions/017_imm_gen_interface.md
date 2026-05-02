# ADR 017 — Immediate Generator: Interface and Implementation

**Status:** Accepted  
**Date:** 2026-05-02

## Context

The immediate generator must extract and sign-extend five immediate formats
(I, S, B, U, J) from a 32-bit RISC-V instruction word. The module is shared
between the single-cycle and pipelined implementations. Its interface must be
consistent with the contract defined in `shared_modules.md` and its
implementation style must follow ADR 010.

Three specific decisions require justification: the choice of input port width,
the declaration style for the format encoding constants, and the output port
type.

## Decision

**1. Input port receives the full 32-bit instruction word.**  
The port is declared as `input logic [31:0] instruction`. Bit field extraction
is performed entirely inside the module.

**2. Format encoding constants are declared as `localparam`.**  
The five selectors (IMM_I through IMM_J) are internal implementation constants,
not module configuration points.

**3. Output is declared as `output logic`.**  
The output is driven by an `always_comb` block. Per ADR 010, all signals are
`logic`.

## Rationale

**Full 32-bit input:**  
The instantiating module (`top_single_cycle.sv` and later the pipeline ID
stage) connects the raw instruction bus directly to every consumer — control
unit, register file address fields, and immediate generator — without
pre-processing. Accepting the full word keeps all field extraction inside
the module boundary and prevents the top-level from carrying knowledge of
which bits encode the immediate. This is consistent with how `control_unit`
and `register_file` receive the instruction word.

**`localparam` for encoding constants:**  
`localparam` signals that the value is an implementation detail, not a
configuration point. It cannot be overridden at instantiation, which eliminates
the risk of a caller accidentally changing the encoding. Per ADR 010, constants
that are not module configuration parameters must be `localparam`.

**`output logic`:**  
In SystemVerilog, `logic` is the correct type for any signal regardless of
whether it is driven combinationally or sequentially. Using `output logic` on
a combinationally driven port accurately represents the intent and is
consistent with ADR 010.

## Normative RTL Specification

The following is the authoritative implementation for `rtl/shared/imm_gen.sv`.
Any deviation requires a new ADR.

```systemverilog
module imm_gen (
    input  logic [31:0] instruction,
    input  logic [2:0]  imm_src,
    output logic [31:0] imm_out
);

    localparam [2:0] IMM_I = 3'b000;
    localparam [2:0] IMM_S = 3'b001;
    localparam [2:0] IMM_B = 3'b010;
    localparam [2:0] IMM_U = 3'b011;
    localparam [2:0] IMM_J = 3'b100;

    always_comb begin
        case (imm_src)
            IMM_I: imm_out = {{20{instruction[31]}}, instruction[31:20]};

            IMM_S: imm_out = {{20{instruction[31]}},
                               instruction[31:25], instruction[11:7]};

            IMM_B: imm_out = {{19{instruction[31]}},
                               instruction[31],    instruction[7],
                               instruction[30:25], instruction[11:8], 1'b0};

            IMM_U: imm_out = {instruction[31:12], 12'b0};

            IMM_J: imm_out = {{11{instruction[31]}},
                               instruction[31],    instruction[19:12],
                               instruction[20],    instruction[30:21], 1'b0};

            default: imm_out = 32'b0;
        endcase
    end

endmodule
```

## Bit Extraction Reference

Each immediate format reassembles non-contiguous instruction bits. The table
below is the normative reference for verifying correctness against the RV32I
Base ISA Specification (Waterman & Asanović, 2019, p. 104).

| Format | `imm_out` bits | Source in `instruction` |
|--------|---------------|-------------------------|
| I | [31:12] sign | `{20{instruction[31]}}` |
| I | [11:0] | `instruction[31:20]` |
| S | [31:12] sign | `{20{instruction[31]}}` |
| S | [11:5] | `instruction[31:25]` |
| S | [4:0] | `instruction[11:7]` |
| B | [31:13] sign | `{19{instruction[31]}}` |
| B | [12] | `instruction[31]` |
| B | [11] | `instruction[7]` |
| B | [10:5] | `instruction[30:25]` |
| B | [4:1] | `instruction[11:8]` |
| B | [0] | `1'b0` |
| U | [31:12] | `instruction[31:12]` |
| U | [11:0] | `12'b0` |
| J | [31:21] sign | `{11{instruction[31]}}` |
| J | [20] | `instruction[31]` |
| J | [19:12] | `instruction[19:12]` |
| J | [11] | `instruction[20]` |
| J | [10:1] | `instruction[30:21]` |
| J | [0] | `1'b0` |

## Consequences

- `rtl/shared/imm_gen.sv` implements exactly the RTL specification above.
- The `default` branch returns `32'b0`. This is a safe don't-care value that
  prevents latch inference in `always_comb` for the three unused `imm_src`
  encodings (`3'b101`, `3'b110`, `3'b111`).
- The `imm_src` encoding (`000`–`100`) is defined in `control_signals.md`
  and `shared_modules.md`. This ADR does not redefine it.
- cocotb testbenches for this module drive `dut.instruction` with the full
  32-bit instruction word and verify `dut.imm_out` combinationally (no clock
  edge required).
