# ADR 018 — Branch Unit: Interface and Implementation

**Status:** Accepted  
**Date:** 2026-05-02

## Context

The branch unit evaluates whether a branch or jump is taken and produces the
control signals that drive PC selection in `pc_unit`. Two outputs are required:
`branch` (take the jump or branch this cycle) and `mask_pc_lsb` (force bit 0
of the JALR target to zero). The module is shared between the single-cycle and
pipelined implementations without modification.

Three design decisions require justification: the decomposition of `br_op` into
intermediate signals, the handling of unsigned comparisons without explicit
casting, and the placement of `mask_pc_lsb` responsibility in this module
rather than in the PC unit or the control unit.

## Decision

**1. `br_op[4:3]` and `br_op[2:0]` are extracted into named intermediate
signals** (`branch_type` and `branch_funct3`) via combinational `assign`
statements before the `always_comb` case block.

**2. BLTU and BGEU use direct `<` and `>=` operators without `$unsigned()`
casts** on `rs1_data` and `rs2_data`.

**3. `mask_pc_lsb` is an output of `branch_unit`**, asserted combinationally
when `branch_type == BR_TYPE_JALR`.

## Rationale

**Intermediate signal decomposition:**  
`br_op` encodes two semantically distinct fields: the instruction class
(`br_op[4:3]`) and the branch condition (`br_op[2:0]`, matching funct3 from
the instruction word). Extracting them into `branch_type` and `branch_funct3`
before the case statement makes the two-level decode structure (class first,
condition second) explicit and readable. It also prevents the need to write
`br_op[4:3]` and `br_op[2:0]` repeatedly inside the case body, reducing the
chance of a transposition error.

**Unsigned comparison without explicit cast:**  
In SystemVerilog, `logic` vectors are unsigned by default. A comparison
`rs1_data < rs2_data` between two `logic [31:0]` signals is inherently
unsigned. No `$unsigned()` cast is needed. Adding it would be redundant and
would suggest that unsigned behavior requires active intervention, which is
misleading. Signed comparisons (BLT, BGE) do require `$signed()` because the
default is unsigned — that asymmetry is intentional and correct.

**`mask_pc_lsb` belongs in branch_unit:**  
`mask_pc_lsb` is a function of `br_op` alone — specifically of whether the
instruction is JALR. The branch unit already decodes `br_op` to determine
`branch_type`. Placing `mask_pc_lsb` here avoids adding a parallel decode path
in either the control unit (which would need an extra output for a signal that
is purely a consequence of br_op) or the pc_unit (which should not decode
instruction type — it only consumes the result). The branch unit is the natural
and only owner of this signal (see [ADR 006](006_jalr_pc_masking.md)).

## Normative RTL Specification

```systemverilog
module branch_unit (
    input  logic [31:0] rs1_data,
    input  logic [31:0] rs2_data,
    input  logic [4:0]  br_op,
    output logic        branch,
    output logic        mask_pc_lsb
);

    localparam [1:0] BR_NONE   = 2'b00;
    localparam [1:0] BR_COND   = 2'b01;
    localparam [1:0] BR_JAL    = 2'b10;
    localparam [1:0] BR_JALR   = 2'b11;

    localparam [2:0] FUNCT3_BEQ  = 3'b000;
    localparam [2:0] FUNCT3_BNE  = 3'b001;
    localparam [2:0] FUNCT3_BLT  = 3'b100;
    localparam [2:0] FUNCT3_BGE  = 3'b101;
    localparam [2:0] FUNCT3_BLTU = 3'b110;
    localparam [2:0] FUNCT3_BGEU = 3'b111;

    logic [1:0] branch_type;
    logic [2:0] branch_funct3;

    assign branch_type   = br_op[4:3];
    assign branch_funct3 = br_op[2:0];
    assign mask_pc_lsb   = (branch_type == BR_JALR);

    always_comb begin
        branch = 1'b0;

        case (branch_type)
            BR_NONE: branch = 1'b0;

            BR_COND: begin
                case (branch_funct3)
                    FUNCT3_BEQ: branch = (rs1_data == rs2_data);
                    FUNCT3_BNE: branch = (rs1_data != rs2_data);
                    FUNCT3_BLT: branch = ($signed(rs1_data) <  $signed(rs2_data));
                    FUNCT3_BGE: branch = ($signed(rs1_data) >= $signed(rs2_data));
                    FUNCT3_BLTU: branch = (rs1_data <  rs2_data);
                    FUNCT3_BGEU: branch = (rs1_data >= rs2_data);
                    default: branch = 1'b0;
                endcase
            end

            BR_JAL:  branch = 1'b1;
            BR_JALR: branch = 1'b1;

            default: branch = 1'b0;
        endcase
    end

endmodule
```

## Consequences

- `mask_pc_lsb` is valid combinationally whenever `br_op` is stable. The
  `pc_unit` must not use `mask_pc_lsb` when `branch == 0`; its value in that
  case is a combinational don't-care.
- `rs1_data` and `rs2_data` are connected directly from the register file read
  ports in `top_single_cycle.sv`, bypassing the ALU operand muxes
  (see [ADR 007](007_branch_unit_inputs.md)). In the pipelined implementation
  these inputs receive forwarded values from the forwarding unit; the module
  itself does not change.
- The `default` branch in the outer case (`branch = 1'b0`) handles the
  encoding `2'b00` redundantly with `BR_NONE` and ensures no latch is inferred
  for any future encoding extension.
- localparam names use short prefixes (`BR_NONE`, `BR_COND`, `BR_JAL`,
  `BR_JALR`) rather than the verbose `BR_TYPE_*` pattern, consistent with the
  naming convention used in `alu_rv32im` and `imm_gen`.
