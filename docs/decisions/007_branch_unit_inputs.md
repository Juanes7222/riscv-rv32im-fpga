# ADR 007 — Branch Unit Receives rs1/rs2 Directly from Register File

**Status:** Accepted  
**Date:** 2026-04-24

## Context

The branch unit evaluates conditions (BEQ, BNE, BLT, BGE, BLTU, BGEU) by
comparing two operands. In the datapath, operands can be sourced from the
register file directly or from the ALU source muxes (which may substitute
an immediate or PC for one operand).

## Decision

The `branch_unit` receives **rs1 and rs2 directly from the register file
outputs**, bypassing the ALU operand-A and operand-B source muxes.

## Rationale

All six RV32I branch instructions compare register values: `rs1` vs `rs2`.
None of them compare a register against an immediate. The ALU source muxes
exist to prepare operands for the address calculation (`PC + B_immediate`),
which runs in parallel on the ALU and is unrelated to the branch condition
evaluation.

Connecting the branch unit after the muxes would mean that for branch
instructions, `alua_src` must be set to something that passes rs1 through —
which reintroduces coupling between the ALU path and the branch path. Direct
connection from the register file is structurally cleaner and avoids this
dependency.

In the pipelined implementation, the forwarding unit provides the resolved
values of rs1 and rs2 to both the ALU and the branch unit inputs. The branch
unit module itself does not change; the forwarding unit is responsible for
presenting the correct values.

## Consequences

- The branch unit has two dedicated 32-bit input ports: `rs1_data` and
  `rs2_data`, connected directly to the register file read ports in the
  single-cycle top-level.
- In the pipeline, `rs1_data` and `rs2_data` must receive forwarded values from
  the forwarding unit before the branch condition is evaluated.
- The ALU path for branch instructions continues to compute `PC + B_immediate`
  for the jump target, independent of the condition evaluation.
